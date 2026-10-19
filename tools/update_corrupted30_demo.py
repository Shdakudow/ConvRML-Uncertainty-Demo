"""Publish paired corruption-adaptation milestones, calibrated curves and examples."""
import fcntl,json,subprocess,datetime
from pathlib import Path
import numpy as np
from build_raw_demo import decode
ROOT=Path(__file__).resolve().parents[1];WORK=Path.home()/'.local/share/convrml-raw-demo-20261019';ASSETS=WORK/'assets'
SSH=['ssh','-i',str(Path.home()/'.ssh/id_ed25519'),'-o','BatchMode=yes','-o','ConnectTimeout=15','jy2228@unicorn-login-02.coecis.cornell.edu']
def run(args,**kw):return subprocess.check_output([str(a) for a in args],cwd=ROOT,text=True,**kw).strip()
def main():
 if not (WORK/'published_final.json').exists() or (WORK/'epoch20_update_requested').exists():return
 record=WORK/'corrupted30_publication.json';previous=json.loads(record.read_text()) if record.exists() else {}
 if previous.get('milestone')==30:return
 lock=(WORK/'publisher.lock').open('w')
 try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 except BlockingIOError:return
 probe='''import json,pathlib
project=pathlib.Path.home()/'ConvRML/experiments';root=project/'raw_corrupted_continue30_20261019/results/raw';out={}
for method in ['qutcc','im2im']:
 p=root/method;rows=[]
 for epoch in [15,20,25,30]:
  d=p/'evaluation'/f'epoch_{epoch:03d}'
  if (d/'report.json').exists():
   r=json.loads((d/'report.json').read_text());rows.append(dict(epoch=epoch,status='complete',metrics=r['metrics'],calibration=r['calibration'],test_count=r['test_count']))
  elif (d/'failure.json').exists():rows.append(dict(epoch=epoch,status='failed',failure=json.loads((d/'failure.json').read_text())))
 h=p/'history.json';out[method]=dict(history=json.loads(h.read_text()) if h.exists() else [],evaluations=rows)
exports=project/'raw_diffuser_demo_20261019/exports';out['paired_exports']=[epoch for epoch in [15,20,25,30] if all((exports/f'corrupted_epoch_{epoch:03d}'/m/'summary.json').exists() for m in ['qutcc','im2im'])]
print(json.dumps(out))
'''
 info=json.loads(run(SSH+['python3 -'],input=probe,timeout=60));methods=['qutcc','im2im']
 common=min(max([r['epoch'] for r in info[m]['evaluations']],default=10) for m in methods)
 if common<=previous.get('milestone',10):return
 # If calibration passed for both, wait for the corresponding paired examples.
 if all(any(r['epoch']==common and r['status']=='complete' for r in info[m]['evaluations']) for m in methods) and common not in info['paired_exports']:return
 file=ROOT/'raw-diffusercam/data.json';data=json.loads(file.read_text());current=min(data['studies']['corrupted'][m]['epoch'] for m in methods)
 latest=max([e for e in info['paired_exports'] if e<=common],default=current)
 if latest>current:
  variant=f'corrupted_epoch_{latest:03d}'
  run(['rsync','-az','-e','ssh -i '+str(Path.home()/'.ssh/id_ed25519')+' -o BatchMode=yes',f'jy2228@unicorn-login-02.coecis.cornell.edu:/home/jy2228/ConvRML/experiments/raw_diffuser_demo_20261019/exports/{variant}/',str(ASSETS/'exports'/variant)+'/'],timeout=1200)
  summaries={m:json.loads((ASSETS/'exports'/variant/m/'summary.json').read_text()) for m in methods}
  for m,s in summaries.items():
   assert s['epoch']==latest and s['example_count']==50 and s['test_count']==2000 and s['calibration_count']==3000
   assert s['config']['dataset_identity']==data['studies']['corrupted'][m]['config']['dataset_identity']
  for i in range(50):
   decoded={m:decode(ASSETS/'exports'/variant/m/f'example_{i:02d}.bin.gz') for m in methods};a,b=[decoded[m] for m in methods]
   assert a[0]['id']==b[0]['id']
   for key in ['target','measurement']:assert np.array_equal(a[1][key],b[1][key])
   for m,(meta,arrays) in decoded.items():
    coverage=np.mean((arrays['target']>=arrays['lower'])&(arrays['target']<=arrays['upper']));width=np.mean(arrays['upper']-arrays['lower'])
    assert abs(float(coverage)-meta['metrics']['coverage'])<2e-6 and abs(float(width)-meta['metrics']['width'])<2e-6
  run(['git','-C',ASSETS,'add','--','exports/'+variant])
  if run(['git','-C',ASSETS,'diff','--cached','--name-only']):run(['git','-C',ASSETS,'commit','-m',f'Add corrupted DiffuserCam adaptation epoch {latest} examples'])
  run(['git','-C',ASSETS,'push','origin','raw-diffuser-assets-20261019'],timeout=1200)
  commit=run(['git','-C',ASSETS,'rev-parse','HEAD']);(ROOT/'raw-diffusercam/assets.json').write_text(json.dumps({'base':f'https://raw.githubusercontent.com/Shdakudow/ConvRML-Uncertainty-Demo/{commit}/exports'},indent=2)+'\n')
  for m in methods:
   old=data['studies']['corrupted'][m];base_rows=[r for r in old['evaluations'] if r['epoch']<=10];baseline=old.get('baseline_validation')
   old.update(summaries[m]);old['evaluations']=base_rows
   if baseline:old['baseline_validation']=baseline
 for m in methods:
  s=data['studies']['corrupted'][m];s['history']=[r for r in info[m]['history'] if r['epoch']<=common]
  s['evaluations']=[r for r in s['evaluations'] if r['epoch']<=10]+[r for r in info[m]['evaluations'] if r['epoch']<=common]
  s['continuation']=dict(initial_epoch=10,target_epoch=30,latest_milestone=common,schedule='Continue constant 1e-5 with Adam moments and RNG retained',example_checkpoint_epoch=s['epoch'])
 file.write_text(json.dumps(data,separators=(',',':'))+'\n')
 run([Path.home()/'Downloads/ConvRML_MRI_Local/.venv/bin/python','tools/verify_raw_demo.py'],timeout=600)
 staged=set(run(['git','diff','--cached','--name-only']).splitlines());assert staged.issubset({'raw-diffusercam/data.json','raw-diffusercam/assets.json'}),'Unrelated staged files; retry later'
 run(['git','add','--','raw-diffusercam/data.json','raw-diffusercam/assets.json'])
 if run(['git','diff','--cached','--name-only']):run(['git','commit','-m',f'Update corrupted raw comparison through adaptation epoch {common}'])
 run(['git','push','origin','main'],timeout=600)
 record.write_text(json.dumps(dict(milestone=common,example_epoch=latest,commit=run(['git','rev-parse','HEAD']),time=datetime.datetime.now(datetime.timezone.utc).isoformat()),indent=2));print('Published corrupted adaptation curves through',common,flush=True)
if __name__=='__main__':main()
