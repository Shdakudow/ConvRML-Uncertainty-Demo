"""Publish audited epoch-50 image overlays when each camera's export finishes."""
import fcntl,json,os,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
WORK=Path.home()/'.local/share/convrml-paper50-demo-20261019'
ASSETS=WORK/'assets';BASELINE=Path.home()/'.local/share/convrml-epoch50-auto/results/assets/data'
SSH=['ssh','-i',str(Path.home()/'.ssh/id_ed25519'),'-o','BatchMode=yes','-o','ConnectTimeout=20','jy2228@unicorn-login-02.coecis.cornell.edu']
BRANCH='paper-qutcc50-demo-assets-20261019'
FILES=['corrected-epoch50/app.js','corrected-epoch50/dataset.js','corrected-epoch50/index.html','corrected-epoch50/paper_qutcc_assets.json','tools/export_paper_qutcc50_demo.py','tools/build_paper_qutcc50_assets.py','tools/publish_paper_qutcc50.py','tools/verify_previous_demos.py']
def run(cmd,**kw):return subprocess.check_output(cmd,text=True,cwd=kw.pop('cwd',ROOT),**kw).strip()
def main():
 WORK.mkdir(parents=True,exist_ok=True)
 with (Path.home()/'.local/share/convrml-raw-demo-20261019/publisher.lock').open('a') as lock:
  try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  except BlockingIOError:print('Other publisher active');return
  if run(['git','diff','--cached','--name-only']):raise RuntimeError('Unrelated staged changes; retry later')
  status=WORK/'published.json';previous=json.loads(status.read_text()) if status.exists() else {}
  if set(previous)=={'rml','diffuser'}:print('Both cameras published');return
  code="import pathlib,json; p=pathlib.Path.home()/'ConvRML/results/paper_qutcc50_demo_20261019';print(json.dumps([c for c in ['rml','diffuser'] if (p/c/'report.json').exists() and (p/c/'examples.npz').exists()]))"
  ready=json.loads(run(SSH+['python3 -c '+__import__('shlex').quote(code)],timeout=60));new=[c for c in ready if c not in previous]
  if not new:print('Waiting for exports',ready,flush=True);return
  ASSETS.mkdir(exist_ok=True)
  if not (ASSETS/'.git').exists():
   run(['git','init','--initial-branch='+BRANCH],cwd=ASSETS);run(['git','remote','add','origin','https://github.com/Shdakudow/ConvRML-Uncertainty-Demo.git'],cwd=ASSETS)
  metadata=ROOT/'corrected-epoch50/paper_qutcc_assets.json';settings=json.loads(metadata.read_text()) if metadata.exists() else {'cameras':{}}
  for camera in new:
   dest=WORK/camera;dest.mkdir(exist_ok=True)
   for filename in ['report.json','examples.npz']:
    run(['rsync','-az','-e','ssh -i '+str(Path.home()/'.ssh/id_ed25519')+' -o BatchMode=yes','jy2228@unicorn-login-02.coecis.cornell.edu:ConvRML/results/paper_qutcc50_demo_20261019/'+camera+'/'+filename,str(dest)+'/'],timeout=600)
   run([sys.executable,'tools/build_paper_qutcc50_assets.py',str(dest),str(BASELINE/camera),str(ASSETS/camera)],timeout=300)
   report=json.loads((dest/'report.json').read_text());settings['cameras'][camera]=report
  run(['git','add','.'],cwd=ASSETS)
  if run(['git','diff','--cached','--name-only'],cwd=ASSETS):run(['git','commit','-m','Add verified calibrated epoch-50 QUTCC images'],cwd=ASSETS)
  sha=run(['git','rev-parse','HEAD'],cwd=ASSETS);run(['git','push','origin',BRANCH],cwd=ASSETS,timeout=600)
  for camera in settings['cameras']:settings['cameras'][camera]['base']='https://raw.githubusercontent.com/Shdakudow/ConvRML-Uncertainty-Demo/'+sha+'/'+camera
  metadata.write_text(json.dumps(settings,indent=2)+'\n')
  run(['/Users/shdakudow/Downloads/ConvRML_MRI_Local/.venv/bin/python','tools/verify_previous_demos.py'],timeout=300)
  run(['git','add',*FILES]);run(['git','diff','--cached','--check'])
  if run(['git','diff','--cached','--name-only']):run(['git','commit','-m','Switch ready Experiment 2 QUTCC cameras to calibrated epoch-50 image inference'])
  run(['git','push','origin','main'],timeout=300)
  for camera in new:previous[camera]={'asset_commit':sha,'published_at':time.strftime('%Y-%m-%d %H:%M:%S')}
  status.write_text(json.dumps(previous,indent=2)+'\n');print('Published',new,sha,flush=True)
if __name__=='__main__':main()
