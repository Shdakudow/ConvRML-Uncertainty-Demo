"""Wait for job 260398, validate exports, and publish the requested milestone demo.

Run with the existing MRI review venv (numpy and websocket-client). Requires SSH,
git push credentials, Chrome, and gh. Writes status to Downloads/ConvRML_Demo_Refresh.
Stops on failure instead of publishing partial results. Does not submit training.
"""
import functools, hashlib, http.server, json, os, shutil, subprocess, sys, threading, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = Path.home()/'Downloads/ConvRML_Demo_Refresh'
OUT.mkdir(parents=True, exist_ok=True)
SSH = ['ssh','-i',str(Path.home()/'.ssh/id_ed25519'),'-o','BatchMode=yes','-o','ConnectTimeout=15','jy2228@unicorn-login-02.coecis.cornell.edu']
METHODS = ['conditioned','im2im','ensemble10','mc_010']
EPOCHS = {'rml':40,'diffuser':35}

def run(args, **kw):
    return subprocess.check_output(args, cwd=ROOT, text=True, **kw).strip()

def status(stage, **details):
    result = dict(stage=stage, time=time.strftime('%Y-%m-%d %H:%M:%S'), **details)
    (OUT/'status.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result), flush=True)

def main():
    start_head = run(['git','rev-parse','HEAD'])
    watched = [p for d in ['corrected-latest','tools'] for p in (ROOT/d).glob('*') if p.is_file()]
    hashes = {str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in watched}
    remote = """import json,pathlib,subprocess
rows=[]
for camera,epoch in [('rml',40),('diffuser',35)]:
 for method in ['conditioned','im2im','ensemble10','mc_010']:
  p=pathlib.Path.home()/'ConvRML'/('results/corrected_demo_epoch%d_20261011'%epoch)/camera/method
  if (p/'report.json').exists() and (p/'examples.npz').exists():
   r=json.loads((p/'report.json').read_text())
   if r['epoch']!=epoch or r['count']!=50 or r['calibration_count']!=2048:raise ValueError('Invalid export')
   rows.append(camera+'/'+method)
queue=subprocess.run(['/usr/local/slurm/current/bin/squeue','-j','260398','-h','-o','%i %T %R'],text=True,capture_output=True).stdout
print(json.dumps(dict(ready=rows,queue=queue)))
"""
    for attempt in range(1440):
        try:
            info=json.loads(run(SSH+['python3 -'], input=remote, timeout=60))
        except (subprocess.SubprocessError, ValueError) as exc:
            status('connection_retry',error=str(exc)); time.sleep(60); continue
        status('waiting_for_inference',**info)
        if len(info['ready'])==8: break
        if not info['queue'].strip(): raise RuntimeError('Inference jobs ended with missing exports; inspect Slurm logs')
        time.sleep(60)
    else: raise TimeoutError('Inference not complete after 24 hours; no publication')
    if run(['git','rev-parse','HEAD'])!=start_head: raise RuntimeError('Repository HEAD changed while waiting; review before publishing')
    for name,digest in hashes.items():
        if hashlib.sha256(Path(name).read_bytes()).hexdigest()!=digest: raise RuntimeError('Prepared file changed: '+name)
    for camera,epoch in EPOCHS.items():
        run(['rsync','-az','-e','ssh -i '+str(Path.home()/'.ssh/id_ed25519')+' -o BatchMode=yes',
             'jy2228@unicorn-login-02.coecis.cornell.edu:ConvRML/results/corrected_demo_epoch%d_20261011/%s'%(epoch,camera),str(OUT)+'/'])
    status('building_and_validating')
    run([sys.executable,'tools/build_corrected_demo.py',str(OUT),'--output','corrected-latest/data'])
    run([sys.executable,'tools/pack_demo_assets.py','corrected-latest'])
    run(['node','--check','corrected-latest/app.js'])
    # Browser validation happens before changes to the old demo or publication.
    server=http.server.ThreadingHTTPServer(('127.0.0.1',8773),functools.partial(http.server.SimpleHTTPRequestHandler,directory=str(ROOT)))
    threading.Thread(target=server.serve_forever,daemon=True).start()
    try:
        result=run([sys.executable,'tools/verify_latest_browser.py','http://127.0.0.1:8773/','--expected-epochs'],timeout=600)
        (OUT/'browser_validation.txt').write_text(result)
    finally: server.shutdown();server.server_close()
    old=ROOT/'corrected-epoch25'
    archive=OUT/'archived_epoch25_demo'
    if archive.exists(): raise FileExistsError(archive)
    shutil.move(str(old),str(archive))
    old.mkdir()
    (old/'index.html').write_text('''<!doctype html><meta charset="utf-8"><title>Latest ConvRML comparison</title><p>The comparison has moved to <a href="../corrected-latest/">the latest checkpoints</a>.</p><script>location.replace('../corrected-latest/'+location.search+location.hash)</script>''')
    p=ROOT/'index.html'
    p.write_text(p.read_text().replace('href="corrected-epoch25/"','href="corrected-latest/"').replace('New: corrected models at epoch 25','Updated: RML epoch 40 · DiffuserCam epoch 35'))
    p=ROOT/'README.md';text=p.read_text();text=text[:text.index('## Corrected experiment:')]+'''## Latest corrected experiment

[Open the updated comparison](https://shdakudow.github.io/ConvRML-Uncertainty-Demo/corrected-latest/).
RML uses epoch 40; DiffuserCam uses epoch 35. Within each camera, all four methods
use the same saved epoch. There are 50 test examples per camera, with independent
RCPS calibration on 2,048 images (alpha=0.10, delta=0.05).

Compare end-to-end im2im, sampled-q pinball QUTCC with 48 FiLM sites, ten-member
NLL ensemble, and MC dropout (p=0.1, 30 draws). QUTCC bounds use q=.05/.95 then
separate RCPS scale factors. No learned-q head is included. The current refresh
uses checkpoint-specific scale calibration, not the earlier quantile-grid search.

Reconstruction, absolute error, interval width, lower/upper images, clipped
metrics, and linked pixel inspection use saved float32 outputs. Sample averages
cover these 50 cases only; reconstruction learning curves use 5,000 validation
images. See corrected-latest/README.txt for details.

The legacy 50-epoch experiment remains at the repository root. The earlier
epoch-25 comparison is archived in Git commit 34262cb; its old URL redirects to
the latest comparison. Training checkpoints are not hosted in this repository.
'''
    p.write_text(text)
    size=sum(p.stat().st_size for p in ROOT.rglob('*') if p.is_file() and '.git' not in p.relative_to(ROOT).parts)
    if size>1024**3:raise RuntimeError('Site exceeds 1 GiB; review packaging before publication')
    run(['git','diff','--check'])
    status('publishing',site_bytes=size)
    run(['git','add','--','corrected-latest','corrected-epoch25','index.html','README.md','tools/build_corrected_demo.py','tools/verify_latest_browser.py','tools/refresh_latest_demo.py'])
    run(['git','commit','-m','Refresh corrected demo: RML epoch 40 and DiffuserCam epoch 35 with RCPS'])
    commit=run(['git','rev-parse','HEAD'])
    run(['git','push','origin','main'],timeout=600)
    status('pushed_waiting_for_pages',commit=commit)
    # Verify the actual deployment for this commit, not an earlier successful run.
    for _ in range(120):
        runs=json.loads(run(['gh','run','list','--limit','10','--json','headSha,status,conclusion,databaseId']))
        matching=[r for r in runs if r['headSha']==commit]
        if matching and all(r['status']=='completed' for r in matching):
            if any(r['conclusion']!='success' for r in matching):raise RuntimeError('Pages deployment failed')
            break
        time.sleep(15)
    else:raise TimeoutError('Pages deployment not confirmed')
    live=run([sys.executable,'tools/verify_latest_browser.py','https://shdakudow.github.io/ConvRML-Uncertainty-Demo/','--expected-epochs'],timeout=600)
    (OUT/'live_validation.txt').write_text(live)
    status('complete',commit=commit,url='https://shdakudow.github.io/ConvRML-Uncertainty-Demo/corrected-latest/')

if __name__=='__main__':
    try:main()
    except Exception as exc:
        status('failed',error=repr(exc));raise
