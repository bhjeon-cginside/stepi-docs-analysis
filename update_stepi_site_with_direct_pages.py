#!/usr/bin/env python3
from pathlib import Path
from collections import Counter
import csv,json,html,os,re,subprocess,shutil
CSV=Path('document_inventory_files.csv'); PAGE=Path('pdf_page_count_summary.json')
DOCS=Path('docs'); MD=Path('stepi_publication_analysis_overview.md')
CAPTURES=DOCS/'assets'/'pdf_captures_multi'; DATA_DIR=DOCS/'data'; SAMPLES_JSON=DATA_DIR/'pdf_capture_samples.json'
PDFTOPPM=Path('.tools/apt/poppler_pkg/usr/bin/pdftoppm').resolve(); PDFTOTEXT=Path('.tools/apt/poppler_pkg/usr/bin/pdftotext').resolve(); POPPLER_LIB=Path('.tools/apt/poppler_deps/usr/lib/x86_64-linux-gnu').resolve()
def clean(s): return str(s or '').encode('utf-8','replace').decode('utf-8','replace')
def fmt_bytes(n):
    n=float(n or 0)
    for u in ['B','KB','MB','GB','TB']:
        if n<1024 or u=='TB': return f'{n:.1f}{u}' if u!='B' else f'{int(n)}B'
        n/=1024
def fmt_num(n): return f'{int(n or 0):,}'
def cat_key(x):
    m=re.match(r'(\d+)',clean(x)); return (int(m.group(1)) if m else 9999,clean(x))
def safe_name(s):
    s=clean(s); s=re.sub(r'[\\/:*?"<>|\x00-\x1f]+','_',s); s=re.sub(r'\s+',' ',s).strip(); return s[:100] or 'sample'
def run_poppler(cmd, timeout=120):
    env=os.environ.copy(); env['LD_LIBRARY_PATH']=str(POPPLER_LIB)+(':'+env['LD_LIBRARY_PATH'] if env.get('LD_LIBRARY_PATH') else '')
    return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors='replace', timeout=timeout, env=env)
def even_pages(total_pages):
    if total_pages <= 0: return [1]
    raw=[1]+[round(total_pages*i/8) for i in range(1,8)]
    raw=[min(total_pages,max(1,int(x))) for x in raw]
    pages=[]
    for p in raw:
        if p not in pages: pages.append(p)
    if len(pages)<min(8,total_pages):
        for p in range(1,total_pages+1):
            if p not in pages: pages.append(p)
            if len(pages)>=min(8,total_pages): break
    return pages[:min(8,total_pages)]
def capture_page(path,page,out_prefix):
    cmd=[str(PDFTOPPM),'-f',str(page),'-l',str(page),'-singlefile','-png','-scale-to-x','900','-scale-to-y','-1',str(path),str(out_prefix)]
    proc=run_poppler(cmd)
    out=Path(str(out_prefix)+'.png')
    return proc.returncode==0 and out.exists(), out, proc.stdout[-1000:]
def extract_text_probe(path,pages):
    if not PDFTOTEXT.exists(): return None
    try:
        first=min(pages); last=max(pages)
        proc=run_poppler([str(PDFTOTEXT),'-f',str(first),'-l',str(last),'-layout',str(path),'-'],timeout=120)
        txt=proc.stdout or ''; stripped=re.sub(r'\s+','',txt)
        warnings='Adobe-Korea1' in txt or 'Syntax Error' in txt
        note='텍스트 추출 적음/스캔 가능성' if len(stripped)<200 else '텍스트 추출 가능'
        if warnings: note += ' · 한글 CID 폰트 매핑 경고 있음'
        return {'ok':proc.returncode==0,'chars':len(txt),'nonspace_chars':len(stripped),'text_density_note':note}
    except Exception as e:
        return {'ok':False,'chars':0,'nonspace_chars':0,'text_density_note':repr(e)}
with CSV.open(encoding='utf-8-sig',errors='replace') as f: rows=list(csv.DictReader(f))
for r in rows:
    try: r['size_bytes']=int(r.get('size_bytes') or 0)
    except: r['size_bytes']=0
page=json.loads(PAGE.read_text(encoding='utf-8'))
type_count=Counter(r.get('logical_type') for r in rows); type_size=Counter()
year_count=Counter(); year_size=Counter(); cat_count=Counter(); cat_size=Counter()
for r in rows:
    s=r['size_bytes']; type_size[r.get('logical_type')]+=s
    if r.get('year'): year_count[r['year']]+=1; year_size[r['year']]+=s
    cat_count[r.get('category')]+=1; cat_size[r.get('category')]+=s
page_by_year=page.get('by_year',{}); page_by_cat=page.get('by_category',{})
# Rebuild capture sample metadata using previous selected docs, but recapture evenly spaced 8 pages.
old_samples=json.loads(SAMPLES_JSON.read_text(encoding='utf-8')) if SAMPLES_JSON.exists() else []
# Clear old captures to avoid stale page references.
if CAPTURES.exists(): shutil.rmtree(CAPTURES)
CAPTURES.mkdir(parents=True, exist_ok=True); DATA_DIR.mkdir(parents=True, exist_ok=True)
samples=[]
for idx,r in enumerate(old_samples,1):
    full_path=clean(r.get('full_path'))
    p=Path(full_path)
    if not p.exists():
        # Skip samples with non-roundtrippable paths; current sample set should not hit this.
        continue
    pages=int(r.get('pages') or 1)
    wanted=even_pages(pages)
    base=f'{idx:02d}_{safe_name(r.get("category") or r.get("path"))}'
    caps=[]
    for pg in wanted:
        ok,out,log=capture_page(p,pg,CAPTURES/f'{base}_p{pg}')
        caps.append({'page':pg,'ok':ok,'path':clean(str(out)) if ok else '', 'log':clean(log) if not ok else ''})
    nr=dict(r); nr['capture_pages']=wanted; nr['captures']=caps; nr['text_probe']=extract_text_probe(p,wanted)
    samples.append(nr)
SAMPLES_JSON.write_text(json.dumps(samples,ensure_ascii=False,indent=2),encoding='utf-8',errors='replace')
css='''
:root{--fg:#1f2937;--muted:#6b7280;--line:#e5e7eb;--bg:#f8fafc;--card:#fff;--blue:#1d4ed8}*{box-sizing:border-box}body{margin:0;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Noto Sans KR",Arial,sans-serif;color:var(--fg);background:var(--bg)}header{padding:36px 28px;background:linear-gradient(135deg,#0f172a,#1d4ed8);color:white}header h1{margin:0 0 8px;font-size:32px}header p{margin:4px 0;opacity:.9}main{max-width:1180px;margin:0 auto;padding:24px}nav{background:#fff;border:1px solid var(--line);border-radius:14px;padding:14px 18px;margin-top:-22px;box-shadow:0 8px 18px rgba(15,23,42,.08);position:sticky;top:8px;z-index:2}nav a{margin-right:14px;color:var(--blue);text-decoration:none;font-weight:600;font-size:14px}section{margin:28px 0}h2{margin:0 0 14px;font-size:24px}h3{margin:18px 0 10px}.grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px}.stat{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px}.stat .num{font-size:26px;font-weight:800;margin-top:6px}.stat .label{color:var(--muted);font-size:13px}table{width:100%;border-collapse:collapse;background:#fff;border:1px solid var(--line);border-radius:12px;overflow:hidden}th,td{border-bottom:1px solid var(--line);padding:9px 10px;text-align:left;vertical-align:top}th{background:#f1f5f9}td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}.total-row td{font-weight:800;background:#f8fafc;border-top:2px solid #cbd5e1}.note{background:#fff7ed;border:1px solid #fed7aa;border-radius:12px;padding:14px;color:#7c2d12}.card{background:#fff;border:1px solid var(--line);border-radius:16px;padding:18px;margin:18px 0;box-shadow:0 2px 10px rgba(15,23,42,.04)}.badge{display:inline-block;padding:4px 8px;border-radius:999px;background:#dbeafe;color:#1e40af;font-size:12px;font-weight:700}.path{color:var(--muted);font-size:12px;word-break:break-all}.shots{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px;margin-top:14px}.shot{border:1px solid var(--line);border-radius:12px;padding:8px;background:#fafafa}.shot img{width:100%;border:1px solid #ddd;background:white}.shot .cap{font-size:12px;color:var(--muted);margin-bottom:6px}footer{color:var(--muted);padding:24px;text-align:center}@media(max-width:860px){.grid{grid-template-columns:repeat(2,1fr)}nav{position:static;margin-top:0}.shots{grid-template-columns:1fr}}
'''
def tr(cells, cls=''):
    row_class=f' class="{cls}"' if cls else ''
    return '<tr'+row_class+'>'+''.join(f'<td{(" class=\"num\"" if num else "")}>{val}</td>' for val,num in cells)+'</tr>'
def table(headers, body): return '<table><thead><tr>'+''.join(f'<th{(" class=\"num\"" if n else "")}>{html.escape(h)}</th>' for h,n in headers)+'</tr></thead><tbody>'+''.join(body)+'</tbody></table>'
total_files=sum(type_count.values()); total_size=sum(type_size.values())
type_rows=[tr([(html.escape(clean(k)),False),(fmt_num(c),True),(f'{(c/total_files*100):.1f}%',True),(fmt_bytes(type_size[k]),True)]) for k,c in type_count.most_common()]
type_rows.append(tr([('<strong>합계</strong>',False),(fmt_num(total_files),True),('100.0%',True),(fmt_bytes(total_size),True)], 'total-row'))
year_rows=[tr([(y,False),(fmt_num(year_count[y]),True),(fmt_bytes(year_size[y]),True),(fmt_num(page_by_year.get(y,{}).get('files',0)),True),(fmt_num(page_by_year.get(y,{}).get('pages',0)),True)]) for y in sorted(year_count)]
year_rows.append(tr([('<strong>합계</strong>',False),(fmt_num(sum(year_count.values())),True),(fmt_bytes(sum(year_size.values())),True),(fmt_num(sum(v.get('files',0) for v in page_by_year.values())),True),(fmt_num(sum(v.get('pages',0) for v in page_by_year.values())),True)], 'total-row'))
cat_rows=[tr([(html.escape(clean(cat)),False),(fmt_num(cat_count[cat]),True),(fmt_bytes(cat_size[cat]),True),(fmt_num(page_by_cat.get(cat,{}).get('files',0)),True),(fmt_num(page_by_cat.get(cat,{}).get('pages',0)),True)]) for cat in sorted(cat_count,key=cat_key)]
cat_rows.append(tr([('<strong>합계</strong>',False),(fmt_num(sum(cat_count.values())),True),(fmt_bytes(sum(cat_size.values())),True),(fmt_num(sum(v.get('files',0) for v in page_by_cat.values())),True),(fmt_num(sum(v.get('pages',0) for v in page_by_cat.values())),True)], 'total-row'))
cards=[]
for r in samples:
    text=r.get('text_probe') or {}
    shots=''.join(f'<div class="shot"><div class="cap">p.{c["page"]}</div><img src="{html.escape(os.path.relpath(c["path"],DOCS))}" loading="lazy"></div>' for c in r.get('captures',[]) if c.get('ok'))
    source=f'<p class="path"><b>원 압축:</b> {html.escape(clean(r.get("source_archive")))}</p>' if r.get('source_archive') else ''
    cards.append(f'<article class="card"><span class="badge">{html.escape(clean(r.get("sample_group")))}</span><h3>{html.escape(clean(r.get("category")))} · {html.escape(clean(r.get("year")))} · {fmt_bytes(r.get("size_bytes"))} · {fmt_num(r.get("pages"))}쪽</h3><p><b>텍스트 추출 진단:</b> {html.escape(clean(text.get("text_density_note","")))} / 추출 구간 비공백 문자 {fmt_num(text.get("nonspace_chars",0))}자</p><p class="path">{html.escape(clean(r.get("full_path")))}</p>{source}<div class="shots">{shots}</div></article>')
max_pdf=page.get('max_pages_pdf') or {}
total_size_all=sum(r['size_bytes'] for r in rows)
html_doc=f'''<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>STEPI 간행물 분석 개요</title><style>{css}</style></head><body><header><h1>STEPI(과학기술정책연구원) 간행물 분석 개요</h1><p>40년 기관 생산 발간물: 문서 현황 및 PDF 파일 기준 페이지 수, 상세 페이지 예시</p><p>생성일: 2026-07-02</p></header><main><nav><a href="#summary">요약</a><a href="#types">문서 형식</a><a href="#years">연도별</a><a href="#categories">문서유형별</a><a href="#pages">페이지 규모</a><a href="#captures">상세 페이지 예시</a></nav><section id="summary"><h2>전체 요약</h2><div class="grid"><div class="stat"><div class="label">전체 물리 파일</div><div class="num">{fmt_num(len(rows))}</div></div><div class="stat"><div class="label">전체 용량</div><div class="num">{fmt_bytes(total_size_all)}</div></div><div class="stat"><div class="label">PDF 파일</div><div class="num">{fmt_num(type_count['PDF'])}</div></div><div class="stat"><div class="label">PDF 총 페이지</div><div class="num">{fmt_num(page['total_pdf_pages_success_only'])}</div></div></div><p class="note">실제 고유 문서 수는 중복파일의 존재로 인해 달라질 수 있습니다.</p></section><section id="types"><h2>문서 형식별 수량</h2>{table([('유형',False),('파일 수',True),('비율',True),('용량',True)],type_rows)}</section><section id="years"><h2>연도별 문서 수량</h2>{table([('연도',False),('전체 파일 수',True),('용량',True),('PDF 산출 파일 수',True),('PDF 페이지 수',True)],year_rows)}</section><section id="categories"><h2>문서유형별 수량</h2><p>문서유형은 최상위 폴더명 기준입니다. 예: 정책연구, 기초연구, 수시연구 등.</p>{table([('문서유형',False),('전체 파일 수',True),('용량',True),('PDF 산출 파일 수',True),('PDF 페이지 수',True)],cat_rows)}</section><section id="pages"><h2>전체 보고서 분량/페이지 규모 검토</h2><ul><li>PDF 페이지 수는 <code>pdfinfo</code>로 산출했습니다.</li><li>파일시스템 기준 PDF: {fmt_num(page['filesystem_pdf_files'])}개 / 페이지 산출 성공: {fmt_num(page['pdfinfo_success'])}개 / 실패: {fmt_num(page['pdfinfo_failed'])}개</li><li>PDF 총 페이지: <b>{fmt_num(page['total_pdf_pages_success_only'])}쪽</b>, 평균 {page['mean_pages_per_pdf']}쪽</li><li>최대 페이지 PDF: {fmt_num(max_pdf.get('pages',0))}쪽 · <span class="path">{html.escape(clean(max_pdf.get('path','')))}</span></li></ul><p class="note">현재 페이지수는 PDF 기준으로만 추출 가능하여 PDF 페이지수를 참고, 추후 전체 페이지 수 산출 예정</p></section><section id="captures"><h2>PDF 상세 페이지 예시</h2><p>각 대표 PDF에서 첫 장과 전체 페이지의 1/8~7/8 지점에 해당하는 총 8개 위치를 골고루 추출했습니다. 표지 중심 샘플링을 피하고 본문·표·그림·스캔 여부를 함께 확인하기 위한 예시입니다.</p>{''.join(cards)}</section></main><footer>Generated from document_inventory_files.csv, pdfinfo, pdftoppm</footer></body></html>'''
(DOCS/'index.html').write_text(html_doc,encoding='utf-8',errors='replace')
md=['# STEPI(과학기술정책연구원) 간행물 분석 개요','', '40년 기관 생산 발간물: 문서 현황 및 PDF 파일 기준 페이지 수, 상세 페이지 예시','', '## 핵심 요약','',f'- 전체 물리 파일: **{fmt_num(len(rows))}개**',f'- 전체 용량: **{fmt_bytes(total_size_all)}**',f'- PDF 파일: **{fmt_num(type_count["PDF"])}개**',f'- PDF 총 페이지: **{fmt_num(page["total_pdf_pages_success_only"])}쪽**',f'- 내부 압축 해제: **261개 성공 / 0개 실패**',f'- GitHub Pages용 사이트: `docs/index.html`','', '> 실제 고유 문서 수는 중복파일의 존재로 인해 달라질 수 있습니다.','', '## 문서 형식별 수량','| 유형 | 파일 수 | 비율 | 용량 |','|---|---:|---:|---:|']
for k,c in type_count.most_common(): md.append(f'| {clean(k)} | {fmt_num(c)} | {(c/total_files*100):.1f}% | {fmt_bytes(type_size[k])} |')
md.append(f'| **합계** | **{fmt_num(sum(type_count.values()))}** | **100.0%** | **{fmt_bytes(sum(type_size.values()))}** |')
md += ['','## 연도별 문서 수량','| 연도 | 전체 파일 수 | PDF 페이지 수 |','|---:|---:|---:|']
for y in sorted(year_count): md.append(f'| {y} | {fmt_num(year_count[y])} | {fmt_num(page_by_year.get(y,{}).get("pages",0))} |')
md.append(f'| **합계** | **{fmt_num(sum(year_count.values()))}** | **{fmt_num(sum(v.get("pages",0) for v in page_by_year.values()))}** |')
md += ['','## 문서유형별 수량','| 문서유형 | 전체 파일 수 | PDF 페이지 수 |','|---|---:|---:|']
for cat in sorted(cat_count,key=cat_key): md.append(f'| {clean(cat)} | {fmt_num(cat_count[cat])} | {fmt_num(page_by_cat.get(cat,{}).get("pages",0))} |')
md.append(f'| **합계** | **{fmt_num(sum(cat_count.values()))}** | **{fmt_num(sum(v.get("pages",0) for v in page_by_cat.values()))}** |')
md += ['','## 전체 보고서 분량/페이지 규모 검토','',f'- PDF 기준 총 페이지는 **{fmt_num(page["total_pdf_pages_success_only"])}쪽**입니다.',f'- 페이지 수 산출 성공 PDF는 **{fmt_num(page["pdfinfo_success"])}개**, 실패는 **{fmt_num(page["pdfinfo_failed"])}개**입니다.','- 현재 페이지수는 PDF 기준으로만 추출 가능하여 PDF 페이지수를 참고, 추후 전체 페이지 수 산출 예정','', '## PDF 상세 페이지 예시','', '- 정적 웹 보고서: `docs/index.html`','- 캡처 이미지: `docs/assets/pdf_captures_multi/`','- 샘플 메타데이터: `docs/data/pdf_capture_samples.json`','- 각 대표 PDF는 첫 장과 1/8~7/8 지점의 상세 페이지 예시를 포함합니다.']
MD.write_text('\n'.join(md)+'\n',encoding='utf-8',errors='replace')
# copy key data
(DOCS/'data'/'pdf_page_count_summary.json').write_text(PAGE.read_text(encoding='utf-8'),encoding='utf-8')
if CSV.exists(): shutil.copy2(CSV, DOCS/'data'/'document_inventory_files.csv')
print('updated', DOCS/'index.html', MD, 'samples', len(samples), 'captures', sum(1 for s in samples for c in s.get('captures',[]) if c.get('ok')))
