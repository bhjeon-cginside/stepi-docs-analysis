#!/usr/bin/env python3
from pathlib import Path
import subprocess, os, json, shutil, re, time

ROOT = Path('40년 기관 생산 발간물')
OUT_ROOT = Path('internal_archives_extracted')
LOG_JSON = Path('internal_archive_extract_log.json')
SUMMARY_MD = Path('internal_archive_extract_summary.md')

UNALZ = Path('.tools/apt/unalz_pkg/usr/bin/unalz').resolve()
UNAR = Path('.tools/apt/unar_pkg/usr/bin/unar').resolve()
UNAR_DEPS = Path('.tools/apt/unar_deps').resolve()
SEVENZ = shutil.which('7z') or shutil.which('7za')

ARCHIVE_EXTS = {'zip','alz','sit'}

def safe_part(s: str) -> str:
    # Keep names readable but avoid path separators and control chars.
    s = s.replace('/', '_').replace('\\', '_')
    s = re.sub(r'[\x00-\x1f]', '_', s)
    return s[:180]

def out_dir_for(archive: Path) -> Path:
    rel = archive.relative_to(ROOT)
    parts = list(rel.parts)
    parts[-1] = safe_part(parts[-1]) + '__extracted'
    return OUT_ROOT.joinpath(*parts)

def run(cmd, timeout=None, env=None):
    p = subprocess.run(cmd, text=True, errors='replace', stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout, env=env)
    return p.returncode, p.stdout

def extract_archive(archive: Path):
    ext = archive.suffix.lower().lstrip('.')
    dest = out_dir_for(archive)
    dest.mkdir(parents=True, exist_ok=True)
    before = time.time()
    if ext == 'alz':
        if not UNALZ.exists():
            return {'status':'failed','reason':'unalz not found'}
        cmd = [str(UNALZ), '-utf8', '-d', str(dest), str(archive)]
        code, out = run(cmd)
    elif ext == 'sit':
        if not UNAR.exists():
            return {'status':'failed','reason':'unar not found'}
        env = os.environ.copy()
        ld = [str(UNAR_DEPS/'usr/lib'), str(UNAR_DEPS/'usr/lib/x86_64-linux-gnu'), str(UNAR_DEPS/'lib/x86_64-linux-gnu')]
        env['LD_LIBRARY_PATH'] = ':'.join(ld + ([env['LD_LIBRARY_PATH']] if env.get('LD_LIBRARY_PATH') else []))
        cmd = [str(UNAR), '-quiet', '-force-overwrite', '-output-directory', str(dest), str(archive)]
        code, out = run(cmd, env=env)
    elif ext == 'zip':
        # 7z is robust for nested directories and large ZIPs. Use overwrite within the per-archive output only.
        cmd = [SEVENZ, 'x', '-y', f'-o{dest}', str(archive)]
        code, out = run(cmd)
    else:
        return {'status':'skipped','reason':f'unsupported extension {ext}'}
    files = [p for p in dest.rglob('*') if p.is_file()] if dest.exists() else []
    dirs = [p for p in dest.rglob('*') if p.is_dir()] if dest.exists() else []
    size = sum(p.stat().st_size for p in files)
    status = 'ok' if code == 0 else 'failed'
    return {
        'status': status,
        'returncode': code,
        'command': cmd,
        'output_dir': str(dest),
        'extracted_files': len(files),
        'extracted_dirs': len(dirs),
        'extracted_size_bytes': size,
        'elapsed_sec': round(time.time()-before, 2),
        'log_tail': out[-4000:],
    }

def fmt(n):
    n=float(n)
    for u in ['B','KB','MB','GB','TB']:
        if n < 1024 or u == 'TB':
            return f'{n:.1f}{u}' if u != 'B' else f'{int(n)}B'
        n /= 1024

archives = sorted([p for p in ROOT.rglob('*') if p.is_file() and p.suffix.lower().lstrip('.') in ARCHIVE_EXTS])
OUT_ROOT.mkdir(exist_ok=True)
results=[]
for i, arc in enumerate(archives, 1):
    print(f'[{i}/{len(archives)}] {arc}', flush=True)
    res = {'archive': str(arc), 'extension': arc.suffix.lower().lstrip('.'), 'archive_size_bytes': arc.stat().st_size}
    try:
        res.update(extract_archive(arc))
    except Exception as e:
        res.update({'status':'failed','error':repr(e)})
    results.append(res)
    LOG_JSON.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')

from collections import Counter
cnt=Counter(r['status'] for r in results)
extcnt=Counter(r['extension'] for r in results)
ok_files=sum(r.get('extracted_files',0) for r in results if r.get('status')=='ok')
ok_size=sum(r.get('extracted_size_bytes',0) for r in results if r.get('status')=='ok')
failed=[r for r in results if r.get('status')!='ok']
lines=[]
lines += ['# 내부 압축파일 해제 결과','']
lines += [f'- 대상 루트: `{ROOT}`', f'- 해제 위치: `{OUT_ROOT}`', f'- 대상 압축파일: **{len(results):,}개** ({", ".join(f"{k.upper()} {v}" for k,v in sorted(extcnt.items()))})', f'- 성공: **{cnt.get("ok",0):,}개**', f'- 실패/스킵: **{len(failed):,}개**', f'- 해제 산출 파일 수: **{ok_files:,}개**', f'- 해제 산출 용량: **{fmt(ok_size)}**', f'- 상세 로그: `{LOG_JSON}`','']
if failed:
    lines += ['## 실패/스킵 목록','| 유형 | 압축파일 | 사유/로그 |','|---|---|---|']
    for r in failed:
        reason = r.get('reason') or r.get('error') or (r.get('log_tail','').splitlines()[-1] if r.get('log_tail') else '')
        reason = reason.replace('|','/')[:500]
        lines.append(f"| {r.get('extension','')} | `{r.get('archive','')}` | {reason} |")
SUMMARY_MD.write_text('\n'.join(lines)+'\n', encoding='utf-8')
print('\n'.join(lines))
