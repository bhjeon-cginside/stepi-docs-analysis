#!/usr/bin/env python3
from pathlib import Path
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv, json, os, re, subprocess, html, math, statistics, shutil, time

ROOTS = [Path('40년 기관 생산 발간물'), Path('internal_archives_extracted')]
CSV = Path('document_inventory_files.csv')
DOCS = Path('docs')
ASSETS = DOCS / 'assets'
CAPTURES = ASSETS / 'pdf_captures_multi'
DATA_DIR = DOCS / 'data'
LOCAL_REPORT_MD = Path('stepi_publication_analysis_overview.md')
PAGECOUNT_JSON = Path('pdf_page_count_summary.json')
SAMPLES_JSON = DATA_DIR / 'pdf_capture_samples.json'

PDFINFO = Path('.tools/apt/poppler_pkg/usr/bin/pdfinfo').resolve()
PDFTOPPM = Path('.tools/apt/poppler_pkg/usr/bin/pdftoppm').resolve()
PDFTOTEXT = Path('.tools/apt/poppler_pkg/usr/bin/pdftotext').resolve()
POPPLER_LIB = Path('.tools/apt/poppler_deps/usr/lib/x86_64-linux-gnu').resolve()

def clean(s):
    return str(s or '').encode('utf-8','replace').decode('utf-8','replace')

def fmt_bytes(n):
    n=float(n or 0)
    for u in ['B','KB','MB','GB','TB']:
        if n < 1024 or u == 'TB': return f'{n:.1f}{u}' if u!='B' else f'{int(n)}B'
        n/=1024

def fmt_num(n): return f'{int(n):,}'

def ext_of(p): return p.suffix.lower().lstrip('.') or '(없음)'

def logical_type(ext):
    if ext == 'pdf' or ext.startswith(' '): return 'PDF'
    if ext in {'hwp','hwpx','bak'}: return 'HWP/HWPX'
    if ext in {'doc','docx','rtf','tmp'}: return 'Word/RTF'
    if ext in {'xls','xlsx','csv','sav'}: return 'Excel/Data'
    if ext in {'ppt','pptx'}: return 'PowerPoint'
    if ext in {'jpg','jpeg','png','gif','bmp','tif','tiff','webp','wmf','psp','eps'}: return 'Image/Graphic'
    if ext in {'zip','tar','gz','tgz','7z','rar','alz','sit'}: return 'Archive'
    if ext in {'txt','md','html','htm','xml','json'}: return 'Text/Web/Data'
    if ext in {'ttf','otf'}: return 'Font'
    if ext in {'ldh','pldh'}: return 'Auxiliary/Lock(LDH)'
    if ext == 'vsd': return 'Visio/Diagram'
    if ext == 'rsrc': return 'Mac Resource Fork'
    return 'Other/Unknown'

def category_for(rel): return rel.parts[0] if rel.parts else '(root)'

def year_for(rel):
    for part in rel.parts:
        if re.fullmatch(r'(19|20)\d{2}', part): return part
    m=re.search(r'(19|20)\d{2}', str(rel))
    return m.group(0) if m else ''

def cat_key(x):
    m=re.match(r'(\d+)', clean(x))
    return (int(m.group(1)) if m else 9999, clean(x))

def run_poppler(cmd, timeout=60):
    env=os.environ.copy()
    env['LD_LIBRARY_PATH'] = str(POPPLER_LIB) + (':' + env['LD_LIBRARY_PATH'] if env.get('LD_LIBRARY_PATH') else '')
    return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors='replace', timeout=timeout, env=env)

def safe_name(s):
    s=clean(s)
    s=re.sub(r'[\\/:*?"<>|\x00-\x1f]+','_',s)
    s=re.sub(r'\s+',' ',s).strip()
    return s[:100] or 'sample'

# Load combined rows from CSV if possible (preserves source archive mapping)
rows=[]
if CSV.exists():
    with CSV.open(encoding='utf-8-sig', errors='replace') as f:
        for r in csv.DictReader(f):
            r={k:clean(v) for k,v in r.items()}
            try: r['size_bytes']=int(r.get('size_bytes') or 0)
            except: r['size_bytes']=0
            rows.append(r)
else:
    for root in ROOTS:
        if not root.exists(): continue
        scope='original_tar_extracted' if root.name.startswith('40') else 'internal_archive_extracted'
        for p in root.rglob('*'):
            if p.is_file():
                rel=p.relative_to(root); e=ext_of(p); s=p.stat().st_size
                rows.append({'source_scope':scope,'path':clean(str(rel)),'full_path':clean(str(p)),'source_archive':'','category':clean(category_for(rel)),'year':year_for(rel),'extension':clean(e),'logical_type':logical_type(e),'size_bytes':s,'size_human':fmt_bytes(s)})

# Existing PDF rows only. CSV may contain paths with replacement chars; recover from full_path where possible.
pdf_rows=[r for r in rows if r.get('logical_type')=='PDF' and Path(r.get('full_path','')).exists()]

# Type/category/year stats from combined rows
type_count=Counter(r.get('logical_type') for r in rows)
type_size=Counter(); cat_count=Counter(); cat_size=Counter(); year_count=Counter(); year_size=Counter(); scope_count=Counter(); scope_size=Counter()
for r in rows:
    s=int(r.get('size_bytes') or 0)
    type_size[r.get('logical_type')]+=s
    cat_count[r.get('category')]+=1; cat_size[r.get('category')]+=s
    if r.get('year'):
        year_count[r.get('year')]+=1; year_size[r.get('year')]+=s
    scope_count[r.get('source_scope')]+=1; scope_size[r.get('source_scope')]+=s

# PDF page count for all accessible PDFs
def page_info_for(row):
    p=Path(row['full_path'])
    try:
        proc=run_poppler([str(PDFINFO), str(p)], timeout=45)
        m=re.search(r'^Pages:\s*(\d+)', proc.stdout, re.M)
        pages=int(m.group(1)) if m else None
        encrypted=bool(re.search(r'^Encrypted:\s+yes', proc.stdout, re.M|re.I))
        return {'path':row['full_path'],'category':row.get('category',''),'year':row.get('year',''),'scope':row.get('source_scope',''),'size_bytes':row.get('size_bytes',0),'pages':pages,'ok':pages is not None and proc.returncode==0,'encrypted':encrypted,'log':proc.stdout[-1000:] if pages is None else ''}
    except Exception as e:
        return {'path':row['full_path'],'category':row.get('category',''),'year':row.get('year',''),'scope':row.get('source_scope',''),'size_bytes':row.get('size_bytes',0),'pages':None,'ok':False,'encrypted':False,'log':repr(e)}

page_infos=[]
start=time.time()
with ThreadPoolExecutor(max_workers=8) as ex:
    futs=[ex.submit(page_info_for,r) for r in pdf_rows]
    for fut in as_completed(futs):
        page_infos.append(fut.result())
page_ok=[p for p in page_infos if p['ok'] and p['pages']]
page_fail=[p for p in page_infos if not p['ok']]
total_pages=sum(p['pages'] for p in page_ok)
page_by_cat=defaultdict(lambda: {'files':0,'pages':0})
page_by_year=defaultdict(lambda: {'files':0,'pages':0})
for p in page_ok:
    page_by_cat[p['category']]['files']+=1; page_by_cat[p['category']]['pages']+=p['pages']
    if p['year']:
        page_by_year[p['year']]['files']+=1; page_by_year[p['year']]['pages']+=p['pages']
page_summary={
    'accessible_pdf_files': len(pdf_rows),
    'pdfinfo_success': len(page_ok),
    'pdfinfo_failed': len(page_fail),
    'total_pdf_pages_success_only': total_pages,
    'mean_pages_per_pdf': round(total_pages/len(page_ok),2) if page_ok else 0,
    'median_pages_per_pdf': statistics.median([p['pages'] for p in page_ok]) if page_ok else 0,
    'max_pages_pdf': max(page_ok, key=lambda p:p['pages']) if page_ok else None,
    'elapsed_sec': round(time.time()-start,2),
    'by_category': {k:v for k,v in sorted(page_by_cat.items(), key=lambda kv: cat_key(kv[0]))},
    'by_year': {k:page_by_year[k] for k in sorted(page_by_year)},
    'failures_sample': page_fail[:30],
}
PAGECOUNT_JSON.write_text(json.dumps(page_summary, ensure_ascii=False, indent=2), encoding='utf-8', errors='replace')

# Select samples: one representative per category + internal examples. Avoid inaccessible PDFs.
pages_by_path={p['path']:p for p in page_infos}
by_cat=defaultdict(list)
for r in pdf_rows:
    if r.get('source_scope')=='original_tar_extracted' and pages_by_path.get(r['full_path'],{}).get('ok'):
        by_cat[r.get('category','')].append(r)
selected=[]
for cat in sorted(by_cat, key=cat_key):
    # Prefer older/smaller path as stable representative, but require >=3 pages if possible
    cands=sorted(by_cat[cat], key=lambda r:(0 if (pages_by_path[r['full_path']]['pages'] or 0)>=3 else 1, r.get('year') or '9999', len(r.get('path','')), r.get('path','')))
    if cands:
        selected.append({'sample_group':'문서유형 대표', **cands[0]})
internal=[r for r in pdf_rows if r.get('source_scope')=='internal_archive_extracted' and pages_by_path.get(r['full_path'],{}).get('ok')]
chosen=[]; seen=set()
# examples from alz and zip where possible; SIT extracted EPS only, no PDF expected
for marker in ['.alz','.zip']:
    c=[r for r in internal if marker in (r.get('source_archive') or '').lower()]
    if c:
        r=sorted(c, key=lambda x:(x.get('category',''), x.get('path','')))[0]
        chosen.append(r); seen.add(r['full_path'])
for r in sorted(internal, key=lambda r:(r.get('category',''), r.get('year') or '', r.get('path',''))):
    if len(chosen)>=6: break
    if r['full_path'] not in seen:
        chosen.append(r); seen.add(r['full_path'])
for r in chosen:
    selected.append({'sample_group':'내부압축 PDF 예시', **r})

# Capture multi pages per selected PDF: first + several content pages.
CAPTURES.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)
def capture_page(path, page, out_prefix):
    cmd=[str(PDFTOPPM), '-f', str(page), '-l', str(page), '-singlefile', '-png', '-scale-to-x', '900', '-scale-to-y', '-1', str(path), str(out_prefix)]
    proc=run_poppler(cmd, timeout=120)
    out=Path(str(out_prefix)+'.png')
    return proc.returncode==0 and out.exists(), out, proc.stdout[-1000:]

def extract_text_pages(path, first, last):
    if not PDFTOTEXT.exists(): return None
    try:
        proc=run_poppler([str(PDFTOTEXT), '-f', str(first), '-l', str(last), '-layout', str(path), '-'], timeout=90)
        txt=proc.stdout or ''
        stripped=re.sub(r'\s+','',txt)
        return {'ok':proc.returncode==0, 'chars':len(txt), 'nonspace_chars':len(stripped), 'text_density_note': '텍스트 추출 적음/스캔 가능성' if len(stripped)<200 else '텍스트 추출 가능'}
    except Exception as e:
        return {'ok':False,'chars':0,'nonspace_chars':0,'text_density_note':repr(e)}

sample_results=[]
for idx,r in enumerate(selected,1):
    p=Path(r['full_path'])
    pages=pages_by_path[r['full_path']]['pages'] or 1
    wanted=[1]
    for pg in [2,3,5,10, max(1, pages//2), pages]:
        if 1 <= pg <= pages and pg not in wanted:
            wanted.append(pg)
        if len(wanted)>=5: break
    base=f'{idx:02d}_{safe_name(r.get("category") or r.get("path"))}'
    caps=[]
    for pg in wanted:
        out_prefix=CAPTURES / f'{base}_p{pg}'
        ok,out,log=capture_page(p, pg, out_prefix)
        caps.append({'page':pg,'ok':ok,'path':clean(str(out)) if ok else '', 'log':clean(log) if not ok else ''})
    text_info=extract_text_pages(p, 1, min(5,pages))
    rr=dict(r)
    rr.update({'pages':pages,'capture_pages':wanted,'captures':caps,'text_probe':text_info})
    sample_results.append(rr)
SAMPLES_JSON.write_text(json.dumps(sample_results, ensure_ascii=False, indent=2), encoding='utf-8', errors='replace')

# HTML helpers
css='''
:root { --fg:#1f2937; --muted:#6b7280; --line:#e5e7eb; --bg:#f8fafc; --card:#fff; --blue:#1d4ed8; }
* { box-sizing:border-box; } body { margin:0; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Noto Sans KR",Arial,sans-serif; color:var(--fg); background:var(--bg); }
header { padding:36px 28px; background:linear-gradient(135deg,#0f172a,#1d4ed8); color:white; }
header h1 { margin:0 0 8px; font-size:32px; } header p { margin:4px 0; opacity:.9; }
main { max-width:1180px; margin:0 auto; padding:24px; }
nav { background:#fff; border:1px solid var(--line); border-radius:14px; padding:14px 18px; margin-top:-22px; box-shadow:0 8px 18px rgba(15,23,42,.08); position:sticky; top:8px; z-index:2; }
nav a { margin-right:14px; color:var(--blue); text-decoration:none; font-weight:600; font-size:14px; }
section { margin:28px 0; } h2 { margin:0 0 14px; font-size:24px; } h3 { margin:18px 0 10px; }
.grid { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:14px; } .stat { background:var(--card); border:1px solid var(--line); border-radius:14px; padding:16px; }
.stat .num { font-size:26px; font-weight:800; margin-top:6px; } .stat .label { color:var(--muted); font-size:13px; }
table { width:100%; border-collapse:collapse; background:#fff; border:1px solid var(--line); border-radius:12px; overflow:hidden; } th,td { border-bottom:1px solid var(--line); padding:9px 10px; text-align:left; vertical-align:top; } th { background:#f1f5f9; } td.num, th.num { text-align:right; font-variant-numeric:tabular-nums; }
.note { background:#fff7ed; border:1px solid #fed7aa; border-radius:12px; padding:14px; color:#7c2d12; }
.card { background:#fff; border:1px solid var(--line); border-radius:16px; padding:18px; margin:18px 0; box-shadow:0 2px 10px rgba(15,23,42,.04); }
.badge { display:inline-block; padding:4px 8px; border-radius:999px; background:#dbeafe; color:#1e40af; font-size:12px; font-weight:700; }
.path { color:var(--muted); font-size:12px; word-break:break-all; }
.shots { display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:12px; margin-top:14px; }
.shot { border:1px solid var(--line); border-radius:12px; padding:8px; background:#fafafa; } .shot img { width:100%; border:1px solid #ddd; background:white; } .shot .cap { font-size:12px; color:var(--muted); margin-bottom:6px; }
footer { color:var(--muted); padding:24px; text-align:center; }
@media (max-width:860px){ .grid{grid-template-columns:repeat(2,1fr);} nav{position:static;margin-top:0}.shots{grid-template-columns:1fr;} }
'''

def rows_table(headers, rows_html):
    return '<table><thead><tr>' + ''.join(f'<th{(" class=\"num\"" if h[1] else "")}>{html.escape(h[0])}</th>' for h in headers) + '</tr></thead><tbody>' + ''.join(rows_html) + '</tbody></table>'

def tr(cells):
    return '<tr>' + ''.join(f'<td{(" class=\"num\"" if num else "")}>{val}</td>' for val,num in cells) + '</tr>'

type_rows=[]
for k,c in type_count.most_common():
    type_rows.append(tr([(html.escape(clean(k)),False),(fmt_num(c),True),(fmt_bytes(type_size[k]),True)]))
year_rows=[]
for y in sorted(year_count):
    pc=page_by_year.get(y,{'files':0,'pages':0})
    year_rows.append(tr([(y,False),(fmt_num(year_count[y]),True),(fmt_bytes(year_size[y]),True),(fmt_num(pc['files']),True),(fmt_num(pc['pages']),True)]))
cat_rows=[]
for cat in sorted(cat_count, key=cat_key):
    pc=page_by_cat.get(cat,{'files':0,'pages':0})
    cat_rows.append(tr([(html.escape(clean(cat)),False),(fmt_num(cat_count[cat]),True),(fmt_bytes(cat_size[cat]),True),(fmt_num(pc['files']),True),(fmt_num(pc['pages']),True)]))

sample_cards=[]
for r in sample_results:
    text=r.get('text_probe') or {}
    shots=''.join(f'<div class="shot"><div class="cap">p.{c["page"]}</div><img src="{html.escape(os.path.relpath(c["path"], DOCS))}" loading="lazy"></div>' for c in r['captures'] if c['ok'])
    source_archive=f'<p class="path"><b>원 압축:</b> {html.escape(clean(r.get("source_archive")))}</p>' if r.get('source_archive') else ''
    sample_cards.append(f'''
    <article class="card">
      <span class="badge">{html.escape(clean(r.get('sample_group')))}</span>
      <h3>{html.escape(clean(r.get('category')))} · {html.escape(clean(r.get('year')))} · {fmt_bytes(r.get('size_bytes'))} · {r.get('pages')}쪽</h3>
      <p><b>텍스트 추출 진단:</b> {html.escape(clean(text.get('text_density_note','')))} / 1~5쪽 비공백 문자 {fmt_num(text.get('nonspace_chars',0))}자</p>
      <p class="path">{html.escape(clean(r.get('full_path')))}</p>{source_archive}
      <div class="shots">{shots}</div>
    </article>''')

max_pdf=page_summary['max_pages_pdf'] or {}
index_html=f'''<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>STEPI 간행물 분석 개요</title><style>{css}</style></head><body>
<header><h1>STEPI(과학기술정책연구원) 간행물 분석 개요</h1><p>40년 기관 생산 발간물: 원본 tar 해제본과 내부 압축 해제 산출물을 포함한 문서 현황 및 PDF 파싱 난이도 검토</p><p>생성일: 2026-07-02</p></header>
<main>
<nav><a href="#summary">요약</a><a href="#types">문서 형식</a><a href="#years">연도별</a><a href="#categories">문서유형별</a><a href="#pages">페이지 규모</a><a href="#captures">PDF 다중 캡처</a><a href="#deploy">배포</a></nav>
<section id="summary"><h2>전체 요약</h2><div class="grid">
<div class="stat"><div class="label">전체 물리 파일</div><div class="num">{fmt_num(len(rows))}</div></div>
<div class="stat"><div class="label">전체 용량</div><div class="num">{fmt_bytes(sum(int(r.get('size_bytes') or 0) for r in rows))}</div></div>
<div class="stat"><div class="label">PDF 파일</div><div class="num">{fmt_num(type_count['PDF'])}</div></div>
<div class="stat"><div class="label">PDF 총 페이지(산출 가능분)</div><div class="num">{fmt_num(total_pages)}</div></div>
</div>
<p class="note">전체 파일 수는 원본 폴더에 남아 있는 압축파일과, 그 압축파일을 별도 해제한 산출물을 모두 포함한 물리 파일 기준입니다. 고유 문서 수로 해석할 때는 압축파일 자체와 내부 산출물의 중복 가능성을 고려해야 합니다.</p>
</section>
<section id="types"><h2>문서 형식별 수량</h2>{rows_table([('유형',False),('파일 수',True),('용량',True)], type_rows)}</section>
<section id="years"><h2>연도별 문서 수량</h2>{rows_table([('연도',False),('전체 파일 수',True),('용량',True),('PDF 산출 파일 수',True),('PDF 페이지 수',True)], year_rows)}</section>
<section id="categories"><h2>문서유형별 수량</h2><p>문서유형은 최상위 폴더명 기준입니다. 예: 정책연구, 기초연구, 수시연구 등.</p>{rows_table([('문서유형',False),('전체 파일 수',True),('용량',True),('PDF 산출 파일 수',True),('PDF 페이지 수',True)], cat_rows)}</section>
<section id="pages"><h2>전체 보고서 분량/페이지 규모 검토</h2>
<ul>
<li>PDF 페이지 수는 <code>pdfinfo</code>로 정확히 산출 가능한 범위에서 집계했습니다.</li>
<li>접근 가능한 PDF: {fmt_num(page_summary['accessible_pdf_files'])}개 / 페이지 산출 성공: {fmt_num(page_summary['pdfinfo_success'])}개 / 실패: {fmt_num(page_summary['pdfinfo_failed'])}개</li>
<li>PDF 총 페이지: <b>{fmt_num(total_pages)}쪽</b>, 평균 {page_summary['mean_pages_per_pdf']}쪽, 중앙값 {page_summary['median_pages_per_pdf']}쪽</li>
<li>최대 페이지 PDF: {fmt_num(max_pdf.get('pages',0))}쪽 · <span class="path">{html.escape(clean(max_pdf.get('path','')))}</span></li>
</ul>
<p class="note">HWP/HWPX, Word, PPT는 별도 변환기/오피스 엔진 없이는 페이지 수를 일관되게 산출하기 어렵습니다. 따라서 현재 “전체 보고서 분량”은 PDF 기준으로는 가능하며, 비PDF 문서는 파일 수·용량·유형 분포로 보조 판단하는 것이 안전합니다.</p>
</section>
<section id="captures"><h2>PDF 파싱 난이도 파악용 다중 페이지 캡처</h2><p>표지만으로는 실제 본문 구조를 알기 어려워 각 대표 PDF에서 1쪽 외에 2·3·5·10쪽 또는 중간/마지막 쪽을 함께 캡처했습니다. 캡처와 텍스트 추출 진단을 함께 보며 스캔본/텍스트 PDF 여부, 표·그림 비중, OCR 필요성을 판단할 수 있습니다.</p>{''.join(sample_cards)}</section>
<section id="deploy"><h2>GitHub Pages 배포 상태</h2><p>이 정적 사이트는 <code>docs/</code> 폴더에 생성되어 GitHub Pages 소스로 바로 사용할 수 있습니다.</p><p class="note">현재 작업 경로는 Git 저장소가 아니며 원격 GitHub 저장소 정보가 없어 실제 <code>github.io</code> 원격 배포(push)는 수행할 수 없습니다. GitHub 저장소에 이 폴더를 커밋한 뒤 Pages 설정에서 <b>Deploy from a branch / main / docs</b>를 선택하면 배포됩니다.</p></section>
</main><footer>Generated from document_inventory_files.csv, pdfinfo, pdftoppm</footer></body></html>'''
(DOCS/'index.html').write_text(index_html, encoding='utf-8', errors='replace')

# Markdown overview without "작성 방식" section
md=[]
md += ['# STEPI(과학기술정책연구원) 간행물 분석 개요','']
md += ['## 핵심 요약','']
md += [f'- 전체 물리 파일: **{fmt_num(len(rows))}개**', f'- 전체 용량: **{fmt_bytes(sum(int(r.get("size_bytes") or 0) for r in rows))}**', f'- PDF 파일: **{fmt_num(type_count["PDF"])}개**', f'- PDF 총 페이지(산출 가능분): **{fmt_num(total_pages)}쪽**', f'- 내부 압축 해제: **261개 성공 / 0개 실패**', f'- GitHub Pages용 사이트: `docs/index.html`']
md += ['','## 문서 형식별 수량','| 유형 | 파일 수 | 용량 |','|---|---:|---:|']
for k,c in type_count.most_common(): md.append(f'| {clean(k)} | {fmt_num(c)} | {fmt_bytes(type_size[k])} |')
md += ['','## 연도별 문서 수량','| 연도 | 전체 파일 수 | PDF 페이지 수 |','|---:|---:|---:|']
for y in sorted(year_count): md.append(f'| {y} | {fmt_num(year_count[y])} | {fmt_num(page_by_year.get(y,{"pages":0})["pages"])} |')
md += ['','## 문서유형별 수량','| 문서유형 | 전체 파일 수 | PDF 페이지 수 |','|---|---:|---:|']
for cat in sorted(cat_count,key=cat_key): md.append(f'| {clean(cat)} | {fmt_num(cat_count[cat])} | {fmt_num(page_by_cat.get(cat,{"pages":0})["pages"])} |')
md += ['','## 전체 보고서 분량/페이지 규모 검토','']
md += [f'- PDF 기준 총 페이지는 **{fmt_num(total_pages)}쪽**입니다.', f'- 페이지 수 산출 성공 PDF는 **{fmt_num(page_summary["pdfinfo_success"])}개**, 실패는 **{fmt_num(page_summary["pdfinfo_failed"])}개**입니다.', '- HWP/HWPX, Word, PPT는 현 환경에서 페이지 수를 안정적으로 산출할 변환기가 없어 전체 페이지 수에 포함하지 않았습니다.', '- 비PDF까지 포함한 전체 분량은 현재 파일 수·용량·문서 유형 분포로 보조 추정하는 방식이 적절합니다.']
md += ['','## PDF 다중 캡처 보고서','']
md += ['- 정적 웹 보고서: `docs/index.html`', '- 캡처 이미지: `docs/assets/pdf_captures_multi/`', '- 샘플 메타데이터: `docs/data/pdf_capture_samples.json`']
LOCAL_REPORT_MD.write_text('\n'.join(md)+'\n', encoding='utf-8', errors='replace')

# Copy data artifacts into docs/data for download
for src in [CSV, Path('document_inventory_summary.json'), PAGECOUNT_JSON]:
    if src.exists(): shutil.copy2(src, DATA_DIR/src.name)
print(json.dumps({
    'docs_index':'docs/index.html',
    'markdown':str(LOCAL_REPORT_MD),
    'samples':len(sample_results),
    'capture_images':sum(1 for r in sample_results for c in r['captures'] if c['ok']),
    'pdf_pages':total_pages,
    'pdfinfo_success':len(page_ok),
    'pdfinfo_failed':len(page_fail),
    'site_files':sum(1 for p in DOCS.rglob('*') if p.is_file()),
}, ensure_ascii=False, indent=2))
