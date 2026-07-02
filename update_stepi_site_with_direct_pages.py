#!/usr/bin/env python3
from pathlib import Path
from collections import Counter
import csv,json,html,os,re
CSV=Path('document_inventory_files.csv'); PAGE=Path('pdf_page_count_summary.json'); SAMPLES=Path('docs/data/pdf_capture_samples.json')
DOCS=Path('docs'); MD=Path('stepi_publication_analysis_overview.md')
def clean(s): return str(s or '').encode('utf-8','replace').decode('utf-8','replace')
def fmt_bytes(n):
    n=float(n or 0)
    for u in ['B','KB','MB','GB','TB']:
        if n<1024 or u=='TB': return f'{n:.1f}{u}' if u!='B' else f'{int(n)}B'
        n/=1024
def fmt_num(n): return f'{int(n or 0):,}'
def cat_key(x):
    m=re.match(r'(\d+)',clean(x)); return (int(m.group(1)) if m else 9999,clean(x))
with CSV.open(encoding='utf-8-sig',errors='replace') as f: rows=list(csv.DictReader(f))
for r in rows:
    try: r['size_bytes']=int(r.get('size_bytes') or 0)
    except: r['size_bytes']=0
page=json.loads(PAGE.read_text(encoding='utf-8'))
samples=json.loads(SAMPLES.read_text(encoding='utf-8')) if SAMPLES.exists() else []
type_count=Counter(r.get('logical_type') for r in rows); type_size=Counter()
year_count=Counter(); year_size=Counter(); cat_count=Counter(); cat_size=Counter()
for r in rows:
    s=r['size_bytes']; type_size[r.get('logical_type')]+=s
    if r.get('year'): year_count[r['year']]+=1; year_size[r['year']]+=s
    cat_count[r.get('category')]+=1; cat_size[r.get('category')]+=s
page_by_year=page.get('by_year',{}); page_by_cat=page.get('by_category',{})
css='''
:root{--fg:#1f2937;--muted:#6b7280;--line:#e5e7eb;--bg:#f8fafc;--card:#fff;--blue:#1d4ed8}*{box-sizing:border-box}body{margin:0;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Noto Sans KR",Arial,sans-serif;color:var(--fg);background:var(--bg)}header{padding:36px 28px;background:linear-gradient(135deg,#0f172a,#1d4ed8);color:white}header h1{margin:0 0 8px;font-size:32px}header p{margin:4px 0;opacity:.9}main{max-width:1180px;margin:0 auto;padding:24px}nav{background:#fff;border:1px solid var(--line);border-radius:14px;padding:14px 18px;margin-top:-22px;box-shadow:0 8px 18px rgba(15,23,42,.08);position:sticky;top:8px;z-index:2}nav a{margin-right:14px;color:var(--blue);text-decoration:none;font-weight:600;font-size:14px}section{margin:28px 0}h2{margin:0 0 14px;font-size:24px}h3{margin:18px 0 10px}.grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px}.stat{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px}.stat .num{font-size:26px;font-weight:800;margin-top:6px}.stat .label{color:var(--muted);font-size:13px}table{width:100%;border-collapse:collapse;background:#fff;border:1px solid var(--line);border-radius:12px;overflow:hidden}th,td{border-bottom:1px solid var(--line);padding:9px 10px;text-align:left;vertical-align:top}th{background:#f1f5f9}td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}.note{background:#fff7ed;border:1px solid #fed7aa;border-radius:12px;padding:14px;color:#7c2d12}.card{background:#fff;border:1px solid var(--line);border-radius:16px;padding:18px;margin:18px 0;box-shadow:0 2px 10px rgba(15,23,42,.04)}.badge{display:inline-block;padding:4px 8px;border-radius:999px;background:#dbeafe;color:#1e40af;font-size:12px;font-weight:700}.path{color:var(--muted);font-size:12px;word-break:break-all}.shots{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px;margin-top:14px}.shot{border:1px solid var(--line);border-radius:12px;padding:8px;background:#fafafa}.shot img{width:100%;border:1px solid #ddd;background:white}.shot .cap{font-size:12px;color:var(--muted);margin-bottom:6px}footer{color:var(--muted);padding:24px;text-align:center}@media(max-width:860px){.grid{grid-template-columns:repeat(2,1fr)}nav{position:static;margin-top:0}.shots{grid-template-columns:1fr}}
'''
def tr(cells): return '<tr>'+''.join(f'<td{(" class=\"num\"" if num else "")}>{val}</td>' for val,num in cells)+'</tr>'
def table(headers, body): return '<table><thead><tr>'+''.join(f'<th{(" class=\"num\"" if n else "")}>{html.escape(h)}</th>' for h,n in headers)+'</tr></thead><tbody>'+''.join(body)+'</tbody></table>'
type_rows=[tr([(html.escape(clean(k)),False),(fmt_num(c),True),(fmt_bytes(type_size[k]),True)]) for k,c in type_count.most_common()]
year_rows=[tr([(y,False),(fmt_num(year_count[y]),True),(fmt_bytes(year_size[y]),True),(fmt_num(page_by_year.get(y,{}).get('files',0)),True),(fmt_num(page_by_year.get(y,{}).get('pages',0)),True)]) for y in sorted(year_count)]
cat_rows=[tr([(html.escape(clean(cat)),False),(fmt_num(cat_count[cat]),True),(fmt_bytes(cat_size[cat]),True),(fmt_num(page_by_cat.get(cat,{}).get('files',0)),True),(fmt_num(page_by_cat.get(cat,{}).get('pages',0)),True)]) for cat in sorted(cat_count,key=cat_key)]
cards=[]
for r in samples:
    text=r.get('text_probe') or {}
    shots=''.join(f'<div class="shot"><div class="cap">p.{c["page"]}</div><img src="{html.escape(os.path.relpath(c["path"],DOCS))}" loading="lazy"></div>' for c in r.get('captures',[]) if c.get('ok'))
    source=f'<p class="path"><b>원 압축:</b> {html.escape(clean(r.get("source_archive")))}</p>' if r.get('source_archive') else ''
    cards.append(f'<article class="card"><span class="badge">{html.escape(clean(r.get("sample_group")))}</span><h3>{html.escape(clean(r.get("category")))} · {html.escape(clean(r.get("year")))} · {fmt_bytes(r.get("size_bytes"))} · {fmt_num(r.get("pages"))}쪽</h3><p><b>텍스트 추출 진단:</b> {html.escape(clean(text.get("text_density_note","")))} / 1~5쪽 비공백 문자 {fmt_num(text.get("nonspace_chars",0))}자</p><p class="path">{html.escape(clean(r.get("full_path")))}</p>{source}<div class="shots">{shots}</div></article>')
max_pdf=page.get('max_pages_pdf') or {}
total_size=sum(r['size_bytes'] for r in rows)
html_doc=f'''<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>STEPI 간행물 분석 개요</title><style>{css}</style></head><body><header><h1>STEPI(과학기술정책연구원) 간행물 분석 개요</h1><p>40년 기관 생산 발간물: 원본 tar 해제본과 내부 압축 해제 산출물을 포함한 문서 현황 및 PDF 파싱 난이도 검토</p><p>생성일: 2026-07-02</p></header><main><nav><a href="#summary">요약</a><a href="#types">문서 형식</a><a href="#years">연도별</a><a href="#categories">문서유형별</a><a href="#pages">페이지 규모</a><a href="#captures">PDF 다중 캡처</a><a href="#deploy">배포</a></nav><section id="summary"><h2>전체 요약</h2><div class="grid"><div class="stat"><div class="label">전체 물리 파일</div><div class="num">{fmt_num(len(rows))}</div></div><div class="stat"><div class="label">전체 용량</div><div class="num">{fmt_bytes(total_size)}</div></div><div class="stat"><div class="label">PDF 파일</div><div class="num">{fmt_num(type_count['PDF'])}</div></div><div class="stat"><div class="label">PDF 총 페이지</div><div class="num">{fmt_num(page['total_pdf_pages_success_only'])}</div></div></div><p class="note">전체 파일 수는 원본 폴더에 남아 있는 압축파일과, 그 압축파일을 별도 해제한 산출물을 모두 포함한 물리 파일 기준입니다. 고유 문서 수로 해석할 때는 압축파일 자체와 내부 산출물의 중복 가능성을 고려해야 합니다.</p></section><section id="types"><h2>문서 형식별 수량</h2>{table([('유형',False),('파일 수',True),('용량',True)],type_rows)}</section><section id="years"><h2>연도별 문서 수량</h2>{table([('연도',False),('전체 파일 수',True),('용량',True),('PDF 산출 파일 수',True),('PDF 페이지 수',True)],year_rows)}</section><section id="categories"><h2>문서유형별 수량</h2><p>문서유형은 최상위 폴더명 기준입니다. 예: 정책연구, 기초연구, 수시연구 등.</p>{table([('문서유형',False),('전체 파일 수',True),('용량',True),('PDF 산출 파일 수',True),('PDF 페이지 수',True)],cat_rows)}</section><section id="pages"><h2>전체 보고서 분량/페이지 규모 검토</h2><ul><li>PDF 페이지 수는 <code>pdfinfo</code>로 산출했습니다.</li><li>파일시스템 기준 PDF: {fmt_num(page['filesystem_pdf_files'])}개 / 페이지 산출 성공: {fmt_num(page['pdfinfo_success'])}개 / 실패: {fmt_num(page['pdfinfo_failed'])}개</li><li>PDF 총 페이지: <b>{fmt_num(page['total_pdf_pages_success_only'])}쪽</b>, 평균 {page['mean_pages_per_pdf']}쪽</li><li>최대 페이지 PDF: {fmt_num(max_pdf.get('pages',0))}쪽 · <span class="path">{html.escape(clean(max_pdf.get('path','')))}</span></li></ul><p class="note">HWP/HWPX, Word, PPT는 별도 변환기/오피스 엔진 없이는 페이지 수를 일관되게 산출하기 어렵습니다. 따라서 현재 “전체 보고서 분량”은 PDF 기준으로는 가능하며, 비PDF 문서는 파일 수·용량·유형 분포로 보조 판단하는 것이 안전합니다.</p></section><section id="captures"><h2>PDF 파싱 난이도 파악용 다중 페이지 캡처</h2><p>표지만으로는 실제 본문 구조를 알기 어려워 각 대표 PDF에서 1쪽 외에 2·3·5·10쪽 또는 중간/마지막 쪽을 함께 캡처했습니다. 캡처와 텍스트 추출 진단을 함께 보며 스캔본/텍스트 PDF 여부, 표·그림 비중, OCR 필요성을 판단할 수 있습니다.</p>{''.join(cards)}</section><section id="deploy"><h2>GitHub Pages 배포 상태</h2><p>이 정적 사이트는 <code>docs/</code> 폴더에 생성되어 GitHub Pages 소스로 바로 사용할 수 있습니다.</p><p class="note">GitHub 저장소에 push한 뒤 Pages 설정에서 <b>Deploy from a branch / main / docs</b>를 선택하면 <code>github.io</code>로 게시됩니다.</p></section></main><footer>Generated from document_inventory_files.csv, pdfinfo, pdftoppm</footer></body></html>'''
(DOCS/'index.html').write_text(html_doc,encoding='utf-8',errors='replace')
md=['# STEPI(과학기술정책연구원) 간행물 분석 개요','', '## 핵심 요약','',f'- 전체 물리 파일: **{fmt_num(len(rows))}개**',f'- 전체 용량: **{fmt_bytes(total_size)}**',f'- PDF 파일: **{fmt_num(type_count["PDF"])}개**',f'- PDF 총 페이지: **{fmt_num(page["total_pdf_pages_success_only"])}쪽**',f'- 내부 압축 해제: **261개 성공 / 0개 실패**',f'- GitHub Pages용 사이트: `docs/index.html`','', '## 문서 형식별 수량','| 유형 | 파일 수 | 용량 |','|---|---:|---:|']
for k,c in type_count.most_common(): md.append(f'| {clean(k)} | {fmt_num(c)} | {fmt_bytes(type_size[k])} |')
md += ['','## 연도별 문서 수량','| 연도 | 전체 파일 수 | PDF 페이지 수 |','|---:|---:|---:|']
for y in sorted(year_count): md.append(f'| {y} | {fmt_num(year_count[y])} | {fmt_num(page_by_year.get(y,{}).get("pages",0))} |')
md += ['','## 문서유형별 수량','| 문서유형 | 전체 파일 수 | PDF 페이지 수 |','|---|---:|---:|']
for cat in sorted(cat_count,key=cat_key): md.append(f'| {clean(cat)} | {fmt_num(cat_count[cat])} | {fmt_num(page_by_cat.get(cat,{}).get("pages",0))} |')
md += ['','## 전체 보고서 분량/페이지 규모 검토','',f'- PDF 기준 총 페이지는 **{fmt_num(page["total_pdf_pages_success_only"])}쪽**입니다.',f'- 페이지 수 산출 성공 PDF는 **{fmt_num(page["pdfinfo_success"])}개**, 실패는 **{fmt_num(page["pdfinfo_failed"])}개**입니다.','- HWP/HWPX, Word, PPT는 현 환경에서 페이지 수를 안정적으로 산출할 변환기가 없어 전체 페이지 수에 포함하지 않았습니다.','- 비PDF까지 포함한 전체 분량은 현재 파일 수·용량·문서 유형 분포로 보조 추정하는 방식이 적절합니다.','', '## PDF 다중 캡처 보고서','', '- 정적 웹 보고서: `docs/index.html`','- 캡처 이미지: `docs/assets/pdf_captures_multi/`','- 샘플 메타데이터: `docs/data/pdf_capture_samples.json`']
MD.write_text('\n'.join(md)+'\n',encoding='utf-8',errors='replace')
# copy corrected page summary into docs data
(DOCS/'data'/'pdf_page_count_summary.json').write_text(PAGE.read_text(encoding='utf-8'),encoding='utf-8')
print('updated', DOCS/'index.html', MD)
