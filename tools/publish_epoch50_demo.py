"""Wait for frozen epoch-50 exports, verify the demo, and publish it separately.

Does not modify existing demos. Exact float32 assets live on a dedicated branch
of the same public repository; the page pins the immutable asset commit.
"""
import functools, hashlib, http.server, json, math, os, subprocess, sys, threading, time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
AUTO=Path.home()/'.local/share/convrml-epoch50-auto'
OUT=AUTO/'results'
ASSETS=OUT/'assets'
OUT.mkdir(parents=True,exist_ok=True)
SSH=['ssh','-i',str(Path.home()/'.ssh/id_ed25519'),'-o','BatchMode=yes','-o','ConnectTimeout=20','jy2228@unicorn-login-02.coecis.cornell.edu']
REMOTE='https://github.com/Shdakudow/ConvRML-Uncertainty-Demo.git'
METHODS=['im2im','ensemble10','ensemble5','mc_010','adaptive_qutcc']

def run(args,**kw):
 return subprocess.check_output(args,cwd=ROOT,text=True,**kw).strip()

def status(stage,**kw):
 row=dict(stage=stage,time=time.strftime('%Y-%m-%d %H:%M:%S'),**kw)
 (OUT/'status.json').write_text(json.dumps(row,indent=2));print(json.dumps(row),flush=True)

class Handler(http.server.SimpleHTTPRequestHandler):
 def translate_path(self,path):
  if path.startswith('/epoch50-assets/'):
   rel=path.split('?',1)[0][len('/epoch50-assets/'):]
   p=(ASSETS/rel).resolve()
   if not p.is_relative_to(ASSETS.resolve()):return '/dev/null'
   return str(p)
  return super().translate_path(path)
 def log_message(self,*args):pass

def check_browser(base):
 result=run([sys.executable,'tools/verify_epoch50_browser.py',base,'--expected-epochs','--screenshot'],timeout=600)
 return result

def main(require_all=False,once=False):
 force='--force' in sys.argv or (OUT/'force_publish_once').exists()
 saved=OUT/'auto_published.json'
 previous=json.loads(saved.read_text()) if saved.exists() else {}
 if once and len(previous.get('ready',[]))==10 and previous.get('curve_count')==20 and previous.get('curve5_count')==20 and previous.get('comparison_count')==4 and not force:return True
 head=run(['git','rev-parse','HEAD'])
 remote='''import json,pathlib,subprocess
root=pathlib.Path.home()/'ConvRML/results/corrected_demo_epoch50_20261011'
ready=[]
for camera in ['rml','diffuser']:
 for method in ['im2im','ensemble10','ensemble5','mc_010','adaptive_qutcc']:
  p=(pathlib.Path.home()/'ConvRML/results/adaptive_q20_demo_20261015' if method=='adaptive_qutcc' else pathlib.Path.home()/'ConvRML/results/ensemble_size_comparison_20261015' if method=='ensemble5' else root)/camera/method
  if (p/'report.json').exists() and (p/'examples.npz').exists():
   r=json.loads((p/'report.json').read_text())
   assert r['epoch']==(20 if method=='adaptive_qutcc' else 50) and r['count']==50 and r['calibration_count']==2048
   ready.append(camera+'/'+method)
q=subprocess.run(['/usr/local/slurm/current/bin/squeue','-j','288027,288028,288596,288597','-h','-o','%i %T %R'],text=True,capture_output=True).stdout
curve_root=pathlib.Path.home()/'ConvRML/results/ensemble10_validation_curves_20261015'
curves={c:[json.loads(p.read_text()) for p in sorted((curve_root/c).glob('epoch_*.json'))] for c in ['rml','diffuser']}
curve_count=sum(len(v) for v in curves.values())
if curve_count!=20:curves={c:[] for c in ['rml','diffuser']}
curve5_root=pathlib.Path.home()/'ConvRML/results/ensemble5_validation_curves_20261015'
curves5={c:[json.loads(p.read_text()) for p in sorted((curve5_root/c).glob('epoch_*.json'))] for c in ['rml','diffuser']}
comparison={}
for c in ['rml','diffuser']:
 comparison[c]={}
 for m in ['ensemble5','ensemble10']:
  p=pathlib.Path.home()/'ConvRML/results/ensemble_size_comparison_20261015'/c/m/'report.json'
  if p.exists():
   report=json.loads(p.read_text())
   assert report['full_test_count']==5000 and report['epoch']==50
   comparison[c][m]={k:report[k] for k in ['epoch','full_test_count','full_test_aggregate','aggregate','manifest_sha256','calibration_sha256','calibration_count','alpha','delta','factors']}
print(json.dumps(dict(ready=ready,queue=q,curves=curves,curve_count=curve_count,curves5=curves5,comparison=comparison)))
'''
 for _ in range(1440):
  try:info=json.loads(run(SSH+['python3 -'],input=remote,timeout=60))
  except (ValueError,subprocess.SubprocessError) as exc:
   status('connection_retry',error=str(exc));time.sleep(45);continue
  status('waiting_for_exports',**info)
  if once or len(info['ready']) >= (8 if require_all else 5):break
  if not info['queue'].strip():raise RuntimeError('Exports incomplete and no inference jobs remain')
  if 'DependencyNeverSatisfied' in info['queue']:raise RuntimeError('Failed training dependency; no publication')
  time.sleep(45)
 else:raise TimeoutError('24-hour export wait exceeded')
 curve_hash=hashlib.sha256(json.dumps([info['curves'],info['curves5'],info['comparison']],sort_keys=True).encode()).hexdigest()
 if once and curve_hash==previous.get('curve_hash') and sorted(info['ready'])==sorted(previous.get('ready',[])) and not force:
  status('monitoring',ready=info['ready'],ensemble_curve_milestones=info['curve_count'],url=previous.get('url'));return len(info['ready'])==8
 if not all(c+'/im2im' in info['ready'] for c in ['rml','diffuser']):return False
 for camera in ['rml','diffuser']:
  for method in METHODS:
   if camera+'/'+method not in info['ready']:continue
   dest=OUT/camera/method;dest.mkdir(parents=True,exist_ok=True)
   for name in ['report.json','examples.npz']:
    run(['rsync','-az','-e','ssh -i '+str(Path.home()/'.ssh/id_ed25519')+' -o BatchMode=yes',
      'jy2228@unicorn-login-02.coecis.cornell.edu:ConvRML/results/'+('adaptive_q20_demo_20261015' if method=='adaptive_qutcc' else 'ensemble_size_comparison_20261015' if method=='ensemble5' else 'corrected_demo_epoch50_20261011')+'/'+camera+'/'+method+'/'+name,str(dest)+'/'],timeout=600)
 for camera,rows in info['curves'].items():
  if rows:
   assert [row['epoch'] for row in rows]==list(range(5,51,5))
   manifest=json.loads((OUT/camera/'im2im/report.json').read_text())['manifest_sha256']
   for row in rows:
    assert row['camera']==camera and row['members']==10 and row['split']=='val'
    assert row['manifest_sha256']==manifest and row['validation']['count']==5000 and row['validation']['clipped']
    assert all(math.isfinite(row['validation'][k]) for k in ['psnr','ssim','mse'])
 (ROOT/'corrected-epoch50/ensemble_curves.json').write_text(json.dumps(dict(method='ensemble10',aggregation='average member predictions before computing metrics',members=10,validation_count=5000,cameras=info['curves']),indent=2)+'\n')
 for camera,rows in info['curves5'].items():
  manifest=json.loads((OUT/camera/'im2im/report.json').read_text())['manifest_sha256']
  for row in rows:
   assert row['camera']==camera and row['members']==5 and row['split']=='val'
   assert row['manifest_sha256']==manifest and row['validation']['count']==5000 and row['validation']['clipped']
   assert all(math.isfinite(row['validation'][k]) for k in ['psnr','ssim','mse'])
  for report in info['comparison'][camera].values():
   baseline=json.loads((OUT/camera/'im2im/report.json').read_text())
   assert report['manifest_sha256']==manifest and report['calibration_sha256']==baseline['calibration_sha256']
   assert report['calibration_count']==2048 and report['alpha']==.1 and report['delta']==.05
   assert all(math.isfinite(v) for v in report['full_test_aggregate'].values())
 (ROOT/'corrected-epoch50/ensemble5_curves.json').write_text(json.dumps(dict(cameras=info['curves5']),indent=2)+'\n')
 (ROOT/'corrected-epoch50/ensemble_comparison.json').write_text(json.dumps(dict(cameras=info['comparison'],difference='five minus ten',members5=list(range(5)),members10=list(range(10)),epoch=50),indent=2)+'\n')
 status('building')
 reusable='--reuse-assets' in sys.argv
 for camera in ['rml','diffuser']:
  p=ASSETS/'data'/camera/'protocol.json'
  methods=[m for m in METHODS if camera+'/'+m in info['ready']]
  reusable=reusable and p.exists() and json.loads(p.read_text()).get('methods')==methods and len(list(p.parent.glob('example_*.bin.gz')))==50
 if not reusable:
  for camera in ['rml','diffuser']:
   methods=[m for m in METHODS if camera+'/'+m in info['ready']]
   run([sys.executable,'tools/build_epoch50_demo.py',str(OUT),'--output',str(ASSETS/'data'),'--camera',camera,'--methods',','.join(methods)],timeout=600)
  run([sys.executable,'tools/pack_demo_assets.py',str(ASSETS)],timeout=600)
 run(['node','--check','corrected-epoch50/app.js'])
 config=ROOT/'corrected-epoch50/assets.json'
 config.write_text(json.dumps({'base':'http://127.0.0.1:8775/epoch50-assets'}))
 server=http.server.ThreadingHTTPServer(('127.0.0.1',8775),functools.partial(Handler,directory=str(ROOT)))
 threading.Thread(target=server.serve_forever,daemon=True).start()
 try:
  status('browser_validation')
  (OUT/'browser_validation.txt').write_text(check_browser('http://127.0.0.1:8775/'))
  if run(['git','rev-parse','HEAD'])!=head:raise RuntimeError('Main repository changed; review before publishing')
  status('publishing_assets')
  if not (ASSETS/'.git').exists():
   run(['git','init','-b','epoch50-assets-20261015',str(ASSETS)])
  run(['git','-C',str(ASSETS),'add','data'])
  if run(['git','-C',str(ASSETS),'diff','--cached','--name-only']):
   run(['git','-C',str(ASSETS),'commit','-m','Frozen epoch-50 float32 demo assets and independent RCPS reports'])
  asset_commit=run(['git','-C',str(ASSETS),'rev-parse','HEAD'])
  run(['git','-C',str(ASSETS),'push',REMOTE,'HEAD:refs/heads/epoch50-assets-20261015'],timeout=1800)
  config.write_text(json.dumps(dict(base='https://raw.githubusercontent.com/Shdakudow/ConvRML-Uncertainty-Demo/'+asset_commit,commit=asset_commit),indent=2)+'\n')
  # Test actual cross-origin asset requests before publishing the page.
  (OUT/'remote_asset_validation.txt').write_text(check_browser('http://127.0.0.1:8775/'))
 finally:server.shutdown();server.server_close()
 run(['git','diff','--check'])
 run(['git','add','--','corrected-epoch50','tools/build_epoch50_demo.py','tools/verify_epoch50_browser.py','tools/publish_epoch50_demo.py','tools/export_adaptive_q20_demo.py','tools/submit_adaptive_q20_demo.py','tools/evaluate_ensemble_learning_curve.py','tools/submit_ensemble_learning_curve.py','tools/export_corrected_milestone.py','tools/export_ensemble_size_comparison.py','tools/submit_ensemble_size_comparison.py','tools/submit_ensemble5_learning_curve.py'])
 if run(['git','diff','--cached','--name-only']):run(['git','commit','-m','Update completed baselines and adaptive-QUTCC epoch-20 demo availability'])
 commit=run(['git','rev-parse','HEAD'])
 run(['git','push','origin','main'],timeout=600)
 status('waiting_for_pages',commit=commit,asset_commit=asset_commit)
 for _ in range(120):
  runs=json.loads(run(['gh','run','list','--limit','10','--json','headSha,status,conclusion,databaseId']))
  matching=[r for r in runs if r['headSha']==commit]
  if matching and all(r['status']=='completed' for r in matching):
   if any(r['conclusion']!='success' for r in matching):raise RuntimeError('Pages deployment failed')
   break
  time.sleep(15)
 else:raise TimeoutError('Pages deployment not confirmed')
 (OUT/'live_validation.txt').write_text(check_browser('https://shdakudow.github.io/ConvRML-Uncertainty-Demo/'))
 status('complete' if len(info['ready'])==8 else 'published_monitoring_pending_models',ready=info['ready'],commit=commit,asset_commit=asset_commit,url='https://shdakudow.github.io/ConvRML-Uncertainty-Demo/corrected-epoch50/')

 saved.write_text(json.dumps(dict(curve5_count=sum(map(len,info['curves5'].values())),comparison_count=sum(map(len,info['comparison'].values())),curve_hash=curve_hash,curve_count=sum(len(v) for v in info['curves'].values()),ready=info['ready'],commit=commit,asset_commit=asset_commit,url='https://shdakudow.github.io/ConvRML-Uncertainty-Demo/corrected-epoch50/'),indent=2))
 (OUT/'force_publish_once').unlink(missing_ok=True)
 return len(info['ready'])==8

if __name__=='__main__':
 try:
  if '--verify-only' in sys.argv:
   server=http.server.ThreadingHTTPServer(('127.0.0.1',8775),functools.partial(Handler,directory=str(ROOT)))
   threading.Thread(target=server.serve_forever,daemon=True).start()
   try:print(check_browser('http://127.0.0.1:8775/'))
   finally:server.shutdown();server.server_close()
   sys.exit(0)
  if '--replace-pid' in sys.argv:
   import signal
   old=int(sys.argv[sys.argv.index('--replace-pid')+1])
   command=run(['ps','-p',str(old),'-o','command='])
   if 'python' not in command.lower() or 'tools/publish_epoch50_demo.py' not in command:raise RuntimeError('Refusing to stop unrelated process')
   os.kill(old,signal.SIGTERM)
  import fcntl
  lock=(OUT/'publisher.lock').open('w')
  try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  except BlockingIOError:sys.exit(0)
  if '--install-agent' in sys.argv:
   import plistlib,datetime
   path=Path.home()/'Library/LaunchAgents/edu.cornell.convrml.adaptive20-demo.plist'
   expiry=(datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(days=30)).isoformat()
   (OUT/'automation_expires.json').write_text(json.dumps(dict(expires=expiry)))
   path.write_bytes(plistlib.dumps(dict(Label='edu.cornell.convrml.adaptive20-demo',ProgramArguments=[str(AUTO/'venv/bin/python'),str(Path(__file__).resolve()),'--once','--reuse-assets'],WorkingDirectory=str(ROOT),EnvironmentVariables=dict(PATH='/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin'),StartInterval=300,RunAtLoad=True,StandardOutPath=str(OUT/'automation.log'),StandardErrorPath=str(OUT/'automation.error.log'))))
   subprocess.run(['/bin/launchctl','bootout','gui/'+str(os.getuid())+'/edu.cornell.convrml.adaptive20-demo'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
   run(['/bin/launchctl','bootstrap','gui/'+str(os.getuid()),str(path)])
   print('Installed automatic publisher:',path);sys.exit(0)
  if '--once' in sys.argv:
   import datetime
   expiry=OUT/'automation_expires.json'
   if expiry.exists() and datetime.datetime.now(datetime.timezone.utc)>datetime.datetime.fromisoformat(json.loads(expiry.read_text())['expires']):sys.exit(0)
   main(once=True)
  elif not main():main(require_all=True)
 except Exception as e:status('failed',error=repr(e));raise
