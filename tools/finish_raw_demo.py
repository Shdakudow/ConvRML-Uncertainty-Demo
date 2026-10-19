"""Publish refreshed calibration and fifty examples once all four exports finish.

Run as a short-lived local LaunchAgent. Does not submit training or change legacy
metrics. Stops after successful publication or after 48 hours.
"""
import datetime,fcntl,json,os,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
WORK=Path.home()/'.local/share/convrml-raw-demo-20261019';ASSETS=WORK/'assets'
SSH=['ssh','-i',str(Path.home()/'.ssh/id_ed25519'),'-o','BatchMode=yes','-o','ConnectTimeout=15','jy2228@unicorn-login-02.coecis.cornell.edu']
REMOTE='/home/jy2228/ConvRML/experiments/raw_diffuser_demo_20261019'
PYTHON=Path.home()/'ConvRML/.venv/bin/python'
BROWSER_PYTHON=Path.home()/'Downloads/ConvRML_MRI_Local/.venv/bin/python'
def run(args,**kw):return subprocess.check_output([str(a) for a in args],cwd=ROOT,text=True,**kw).strip()
def status(stage,**kw):
 obj=dict(stage=stage,time=datetime.datetime.now(datetime.timezone.utc).isoformat(),**kw);(WORK/'publisher_status.json').write_text(json.dumps(obj,indent=2));print(json.dumps(obj),flush=True)
def main():
 WORK.mkdir(parents=True,exist_ok=True)
 lock=(WORK/'publisher.lock').open('w')
 try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 except BlockingIOError:return
 if (WORK/'published_final.json').exists():return
 expiry=WORK/'publisher_expires.json'
 if not expiry.exists():expiry.write_text(json.dumps({'expires':(datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(hours=48)).isoformat()}))
 if datetime.datetime.now(datetime.timezone.utc)>datetime.datetime.fromisoformat(json.loads(expiry.read_text())['expires']):status('expired');return
 probe="import json,pathlib; r=pathlib.Path('"+REMOTE+"/exports'); print(json.dumps({s+'/'+m:json.loads((r/s/m/'summary.json').read_text()).get('refreshed',False) for s in ['clean','corrupted'] for m in ['qutcc','im2im']}))"
 ready=json.loads(run(SSH+['python3 -'],input=probe,timeout=60))
 if not all(ready.values()):status('waiting_for_calibration_exports',ready=ready);return
 status('downloading',ready=ready)
 run(['rsync','-az','-e','ssh -i '+str(Path.home()/'.ssh/id_ed25519')+' -o BatchMode=yes',f'jy2228@unicorn-login-02.coecis.cornell.edu:{REMOTE}/exports/',str(ASSETS/'exports')+'/'],timeout=1200)
 # Pure audit before any publication; use an isolated output directory first.
 run([PYTHON,'tools/build_raw_demo.py',ASSETS,'--output',WORK/'validated'],timeout=300)
 run(['git','-C',ASSETS,'add','exports'])
 if run(['git','-C',ASSETS,'diff','--cached','--name-only']):run(['git','-C',ASSETS,'commit','-m','Refresh raw DiffuserCam calibration and fifty paired test examples per study'])
 run(['git','-C',ASSETS,'push','origin','raw-diffuser-assets-20261019'],timeout=1200)
 asset_commit=run(['git','-C',ASSETS,'rev-parse','HEAD'])
 run([PYTHON,'tools/build_raw_demo.py',ASSETS,'--output','raw-diffusercam'],timeout=300)
 (ROOT/'raw-diffusercam/assets.json').write_text(json.dumps({'base':f'https://raw.githubusercontent.com/Shdakudow/ConvRML-Uncertainty-Demo/{asset_commit}/exports'},indent=2)+'\n')
 status('browser_validation',asset_commit=asset_commit)
 (WORK/'final_browser_validation.txt').write_text(run([BROWSER_PYTHON,'tools/verify_raw_demo.py'],timeout=600))
 run(['git','diff','--check'])
 run(['git','add','--','raw-diffusercam/data.json','raw-diffusercam/assets.json'])
 if run(['git','diff','--cached','--name-only']):run(['git','commit','-m','Update raw DiffuserCam demo with refreshed calibration and fifty examples'])
 commit=run(['git','rev-parse','HEAD']);run(['git','push','origin','main'],timeout=600)
 (WORK/'published_final.json').write_text(json.dumps({'commit':commit,'asset_commit':asset_commit,'ready':ready,'url':'https://shdakudow.github.io/ConvRML-Uncertainty-Demo/raw-diffusercam/'},indent=2));status('published_final',commit=commit,asset_commit=asset_commit)
if __name__=='__main__':
 try:main()
 except Exception as e:status('retry_after_error',error=repr(e));raise
