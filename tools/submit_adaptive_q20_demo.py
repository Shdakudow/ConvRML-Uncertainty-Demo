"""Submit read-only exports gated on successful smoke tests and epoch-20 training."""
import json,subprocess
from pathlib import Path
root=Path('results/adaptive_q20_demo_20261015');root.mkdir(parents=True,exist_ok=True)
record=root/'jobs.json'
if record.exists():
 print(record.read_text());raise SystemExit
training=json.loads(Path('results/adaptive_q_coverage90_scratch50_20261014/jobs.json').read_text())['jobs']
base=['/usr/local/slurm/current/bin/sbatch','--parsable','--partition=gpu','--gres=gpu:1',
 '--constraint=(h100|h200|6000ada|a6000)&avx2','--prefer=h100|h200|6000ada',
 '--exclude=monakhova-compute-01,nikola-compute-15,bhattacharjee-compute-02',
 '--cpus-per-task=2','--mem=48G','--time=03:00:00','--requeue',
 '--output=logs/adaptive_q20_demo_%A_%a.out','--error=logs/adaptive_q20_demo_%A_%a.err']
def submit(args):return subprocess.check_output(base+args,text=True).strip().split(';')[0]
smoke=submit(['--job-name=q20-demo-smoke','--array=0-1%2','--wrap',
 '$HOME/.conda/envs/convrml/bin/python -u scripts/export_adaptive_q20_demo.py --task $SLURM_ARRAY_TASK_ID --epoch 0 --smoke'])
info=dict(smoke_job=smoke,jobs=[])
for i,camera in enumerate(['rml','diffuser']):
 parent=next(j['job'] for j in training if j['camera']==camera and j['target_epoch']==20)
 job=submit(['--job-name=q20-demo-'+camera,'--dependency=afterok:'+parent+':'+smoke,
 '--wrap',f'$HOME/.conda/envs/convrml/bin/python -u scripts/export_adaptive_q20_demo.py --task {i} --epoch 20 --count 50'])
 info['jobs'].append(dict(camera=camera,job=job,training_dependency=parent,epoch=20))
record.write_text(json.dumps(info,indent=2));print(json.dumps(info,indent=2))
