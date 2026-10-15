"""Resume unchanged image-adaptive training; inference uses native bounds, no RCPS."""
import json,subprocess
from pathlib import Path
import torch
root=Path('results/adaptive_q_coverage90_scratch50_20261014')
record_path=root/'resumed_native_jobs_20261015.json'
record=json.loads(record_path.read_text()) if record_path.exists() else dict(protocol='joint_adaptive_q_coverage90_scratch50_v1',inference='native_no_rcps',jobs=[],resume={})
for camera in ['rml','diffuser']:
 ck=torch.load(root/camera/'latest.pt',map_location='cpu',weights_only=False)
 assert ck['protocol']==record['protocol'] and ck['camera']==camera
 assert ck['initialization']=='random_no_pretrained' and 'optimizer' in ck
 if camera not in record['resume']:record['resume'][camera]=dict(next_epoch=ck['next_epoch'],next_offset=ck['next_offset'],validated_epoch=ck['history'][-1]['epoch'])
 start=record['resume'][camera]['next_epoch'];del ck
 previous=None
 for epoch in range(((start+1)//2)*2,51,2):
  existing=next((r for r in record['jobs'] if r['camera']==camera and r['target_epoch']==epoch),None)
  if existing:previous=existing['job'];continue
  args=['/usr/local/slurm/current/bin/sbatch','--parsable','--job-name=native-q50-'+camera]
  if previous:args+=['--dependency=afterok:'+previous]
  args+=['scripts/constrained_adaptive50.sbatch','train','--camera',camera,'--target-epoch',str(epoch)]
  job=subprocess.check_output(args,text=True).strip().split(';')[0]
  record['jobs'].append(dict(camera=camera,target_epoch=epoch,job=job,dependency=previous));previous=job
  tmp=record_path.with_suffix('.tmp');tmp.write_text(json.dumps(record,indent=2));tmp.replace(record_path)
print(json.dumps(dict(resume=record['resume'],jobs=len(record['jobs']),first=[r for r in record['jobs'] if r['target_epoch']==10],milestone20=[r for r in record['jobs'] if r['target_epoch']==20]),indent=2))
