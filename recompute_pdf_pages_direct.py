#!/usr/bin/env python3
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict
import subprocess, os, re, json, time
PDFINFO=Path('.tools/apt/poppler_pkg/usr/bin/pdfinfo').resolve()
POPPLER_LIB=Path('.tools/apt/poppler_deps/usr/lib/x86_64-linux-gnu').resolve()
roots=[('original_tar_extracted',Path('40년 기관 생산 발간물')),('internal_archive_extracted',Path('internal_archives_extracted'))]
def clean(s): return str(s or '').encode('utf-8','replace').decode('utf-8','replace')
def category_for(rel): return rel.parts[0] if rel.parts else '(root)'
def year_for(rel):
    for part in rel.parts:
        if re.fullmatch(r'(19|20)\d{2}', part): return part
    m=re.search(r'(19|20)\d{2}', clean(rel)); return m.group(0) if m else ''
def is_pdf(p):
    e=p.suffix.lower().lstrip('.')
    return e=='pdf' or e.startswith(' ')
def run(path):
    env=os.environ.copy(); env['LD_LIBRARY_PATH']=str(POPPLER_LIB)+(':'+env['LD_LIBRARY_PATH'] if env.get('LD_LIBRARY_PATH') else '')
    try:
        pr=subprocess.run([str(PDFINFO), str(path)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors='replace', timeout=60, env=env)
        m=re.search(r'^Pages:\s*(\d+)', pr.stdout, re.M)
        pages=int(m.group(1)) if m else None
        return pages, pr.returncode, pr.stdout[-1000:]
    except Exception as e:
        return None, -1, repr(e)
items=[]
for scope,root in roots:
    for p in root.rglob('*'):
        if p.is_file() and is_pdf(p):
            rel=p.relative_to(root)
            items.append({'path_obj':p,'path':clean(p),'scope':scope,'category':clean(category_for(rel)),'year':year_for(rel),'size_bytes':p.stat().st_size})
start=time.time(); results=[]
with ThreadPoolExecutor(max_workers=8) as ex:
    futs={ex.submit(run,it['path_obj']):it for it in items}
    for fut in as_completed(futs):
        it=futs[fut]; pages,code,log=fut.result(); it=it.copy(); it.pop('path_obj',None)
        it.update({'pages':pages,'ok':pages is not None and code==0,'returncode':code,'log':log if pages is None else ''})
        results.append(it)
ok=[r for r in results if r['ok']]
fail=[r for r in results if not r['ok']]
by_cat=defaultdict(lambda:{'files':0,'pages':0})
by_year=defaultdict(lambda:{'files':0,'pages':0})
for r in ok:
    by_cat[r['category']]['files']+=1; by_cat[r['category']]['pages']+=r['pages']
    if r['year']:
        by_year[r['year']]['files']+=1; by_year[r['year']]['pages']+=r['pages']
summary={'filesystem_pdf_files':len(items),'pdfinfo_success':len(ok),'pdfinfo_failed':len(fail),'total_pdf_pages_success_only':sum(r['pages'] for r in ok),'mean_pages_per_pdf':round(sum(r['pages'] for r in ok)/len(ok),2) if ok else 0,'max_pages_pdf':max(ok,key=lambda r:r['pages']) if ok else None,'elapsed_sec':round(time.time()-start,2),'by_category':dict(sorted(by_cat.items())),'by_year':dict(sorted(by_year.items())),'failures_sample':fail[:20]}
Path('pdf_page_count_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8',errors='replace')
print(json.dumps({k:summary[k] for k in ['filesystem_pdf_files','pdfinfo_success','pdfinfo_failed','total_pdf_pages_success_only','elapsed_sec']},ensure_ascii=False,indent=2))
