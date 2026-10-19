"""Append paired 55..80 milestone curves without changing epoch-50 example arrays."""
import datetime,fcntl,hashlib,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];WORK=Path.home()/'.local/share/convrml-raw-demo-20261019'
SSH=['ssh','-i',str(Path.home()/'.ssh/id_ed25519'),'-o','BatchMode=yes','-o','ConnectTimeout=15','jy2228@unicorn-login-02.coecis.cornell.edu']
def run(args,**kw):return subprocess.check_output([str(a) for a in args],cwd=ROOT,text=True,**kw).strip()
def main():
 if (WORK/'epoch20_update_requested').exists() or not (WORK/'published_final.json').exists():return
 previous=WORK/'raw80_curve_publication.json';old=json.loads(previous.read_text()) if previous.exists() else {}
 if old.get('milestone')==80:return
 lock=(WORK/'publisher.lock').open('w')
 try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 except BlockingIOError:return
 probe='''import json,pathlib
root=pathlib.Path.home()/'ConvRML/experiments/raw_diffuser_continue80_20261019/results/raw';result={}
for m in ['qutcc','im2im']:
 p=root/m;rows=[]
 for epoch in range(55,81,5):
  d=p/'evaluation'/f'epoch_{epoch:03d}'
  if (d/'report.json').exists():
   r=json.loads((d/'report.json').read_text());rows.append(dict(epoch=epoch,status='complete',metrics=r['metrics'],calibration=r['calibration'],test_count=r['test_count']))
  elif (d/'failure.json').exists():rows.append(dict(epoch=epoch,status='failed',failure=json.loads((d/'failure.json').read_text())))
 h=p/'history.json';result[m]=dict(history=json.loads(h.read_text()) if h.exists() else [],evaluations=rows)
print(json.dumps(result))
'''
 current=json.loads(run(SSH+['python3 -'],input=probe,timeout=60));common=min([max([r['epoch'] for r in current[m]['evaluations']],default=50) for m in current])
 if common<=old.get('milestone',50):return
 file=ROOT/'raw-diffusercam/data.json';data=json.loads(file.read_text())
 for m in ('qutcc','im2im'):
  s=data['studies']['clean'][m];s['history']=[r for r in current[m]['history'] if r['epoch']<=common]
  s['evaluations']=[r for r in s['evaluations'] if r['epoch']<=50]+[r for r in current[m]['evaluations'] if r['epoch']<=common]
  s['continuation']=dict(latest_milestone=common,target_epoch=80,initial_epoch=50,schedule='Adam moments retained; cosine restart 1e-5 to 1e-9 over epochs 51-80',example_checkpoint_epoch=50)
 file.write_text(json.dumps(data,separators=(',',':'))+'\n')
 py=Path.home()/'Downloads/ConvRML_MRI_Local/.venv/bin/python'
 run([py,'tools/verify_raw_demo.py'],timeout=600)
 staged=set(run(['git','diff','--cached','--name-only']).splitlines());assert staged.issubset({'raw-diffusercam/data.json'}),'Unrelated staged changes; retry later'
 run(['git','add','--','raw-diffusercam/data.json'])
 if run(['git','diff','--cached','--name-only']):run(['git','commit','-m',f'Update raw DiffuserCam curves through paired epoch {common}'])
 run(['git','push','origin','main'],timeout=600);previous.write_text(json.dumps(dict(milestone=common,commit=run(['git','rev-parse','HEAD']),time=datetime.datetime.now(datetime.timezone.utc).isoformat()),indent=2))
 print('Published raw curves through epoch',common,flush=True)
if __name__=='__main__':main()
