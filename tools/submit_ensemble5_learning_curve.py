"""Submit one inference task per camera/epoch, with at most two GPUs at once."""
import json,subprocess
from pathlib import Path
root=Path('results/ensemble5_validation_curves_20261015');root.mkdir(parents=True,exist_ok=True)
if (root/'jobs.json').exists():print((root/'jobs.json').read_text());raise SystemExit
for camera in ['rml','diffuser']:
 for epoch in range(5,51,5):
  for member in range(5):
   p=Path('results/corrected_comparison_20261006')/camera/f'ensemble_{member:02d}'/'checkpoints'/f'epoch_{epoch:03d}.pt'
   if not p.exists():raise FileNotFoundError(p)
args=['/usr/local/slurm/current/bin/sbatch','--parsable','--job-name=ensemble5-val-curve','--partition=gpu','--gres=gpu:1',
 '--constraint=(h100|h200|6000ada|a6000)&avx2','--prefer=h100|h200|6000ada',
 '--exclude=monakhova-compute-01,nikola-compute-15,bhattacharjee-compute-02',
 '--cpus-per-task=2','--mem=48G','--time=03:00:00','--requeue','--array=0-19%2',
 '--output=logs/ensemble5_curve_%A_%a.out','--error=logs/ensemble5_curve_%A_%a.err',
 '--wrap','$HOME/.conda/envs/convrml/bin/python -u scripts/evaluate_ensemble_learning_curve.py --task $SLURM_ARRAY_TASK_ID --members 5']
job=subprocess.check_output(args,text=True).strip().split(';')[0]
record=dict(job=job,cameras=['rml','diffuser'],epochs=list(range(5,51,5)),members=5,validation_count=5000,max_concurrent_gpus=2)
(root/'jobs.json').write_text(json.dumps(record,indent=2));print(json.dumps(record))
