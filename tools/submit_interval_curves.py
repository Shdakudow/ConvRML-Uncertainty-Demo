"""Evaluate frozen checkpoints, without retraining or touching training jobs."""
import json,subprocess
from pathlib import Path
root=Path('results/current_interval_curves_20261015');root.mkdir(parents=True,exist_ok=True)
p=root/'jobs.json';record=json.loads(p.read_text()) if p.exists() else dict(jobs=[])
base=['/usr/local/slurm/current/bin/sbatch','--parsable','--partition=gpu','--gres=gpu:1',
 '--constraint=(h100|h200|6000ada|a6000)&avx2','--prefer=h100|h200|6000ada',
 '--exclude=monakhova-compute-01,nikola-compute-15,bhattacharjee-compute-02',
 '--cpus-per-task=2','--mem=48G','--time=06:00:00','--requeue',
 '--output=logs/interval_curves_%A_%a.out','--error=logs/interval_curves_%A_%a.err']
def save():
 tmp=p.with_suffix('.tmp');tmp.write_text(json.dumps(record,indent=2));tmp.replace(p)
def submit(key,args):
 if key not in record:record[key]=subprocess.check_output(base+args,text=True).strip().split(';')[0];save()
 return record[key]
# One small real-data check for the RCPS path and one for native QUTCC.
smoke=submit('smoke_job',['--job-name=interval-smoke','--array=0-1%2','--wrap',
 'if [ "$SLURM_ARRAY_TASK_ID" = 0 ]; then m=im2im; else m=adaptive_qutcc; fi; $HOME/.conda/envs/convrml/bin/python -u scripts/evaluate_interval_curves.py --camera rml --method "$m" --epoch 5 --smoke'])
wrap='i=$SLURM_ARRAY_TASK_ID; if [ "$i" -lt 40 ]; then c=rml; else c=diffuser; fi; case $(((i / 10) % 4)) in 0) m=im2im;; 1) m=ensemble5;; 2) m=ensemble10;; 3) m=mc_010;; esac; $HOME/.conda/envs/convrml/bin/python -u scripts/evaluate_interval_curves.py --camera "$c" --method "$m" --epoch "$((5 * (i % 10 + 1)))"'
submit('baseline_array',['--job-name=interval-baselines','--array=0-79%2','--dependency=afterok:'+smoke,'--wrap',wrap])
training=json.loads(Path('results/adaptive_q_coverage90_scratch50_20261014/resumed_native_jobs_20261015.json').read_text())['jobs']
for c in ['rml','diffuser']:
 for epoch in range(5,51,5):
  key=f'qutcc_{c}_{epoch:03d}';deps=[smoke]
  ck=Path('results/adaptive_q_coverage90_scratch50_20261014')/c/f'epoch_{epoch:03d}.pt'
  if not ck.exists():deps.append(next(r['job'] for r in training if r['camera']==c and r['target_epoch']==((epoch+1)//2)*2))
  submit(key,['--job-name=interval-q-'+c,'--dependency=afterok:'+':'.join(deps),'--wrap',
   f'$HOME/.conda/envs/convrml/bin/python -u scripts/evaluate_interval_curves.py --camera {c} --method adaptive_qutcc --epoch {epoch}'])
print(json.dumps(record,indent=2))
