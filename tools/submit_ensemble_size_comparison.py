"""Frozen epoch-50, separately calibrated five-versus-ten member evaluation."""
import json, subprocess
from pathlib import Path
root=Path('results/ensemble_size_comparison_20261015');root.mkdir(parents=True,exist_ok=True)
if (root/'jobs.json').exists():
 print((root/'jobs.json').read_text());raise SystemExit
args=['/usr/local/slurm/current/bin/sbatch','--parsable','--job-name=ensemble-size-test','--partition=gpu','--gres=gpu:1',
 '--constraint=(h100|h200|6000ada|a6000)&avx2','--prefer=h100|h200|6000ada',
 '--exclude=monakhova-compute-01,nikola-compute-15,bhattacharjee-compute-02',
 '--cpus-per-task=2','--mem=48G','--time=06:00:00','--requeue','--array=0-3%2',
 '--output=logs/ensemble_size_%A_%a.out','--error=logs/ensemble_size_%A_%a.err',
 '--wrap','$HOME/.conda/envs/convrml/bin/python -u scripts/export_ensemble_size_comparison.py --task $SLURM_ARRAY_TASK_ID --epoch 50 --count 5000']
job=subprocess.check_output(args,text=True).strip().split(';')[0]
record=dict(job=job,cameras=['rml','diffuser'],members=[5,10],epoch=50,calibration_count=2048,test_count=5000,max_concurrent_gpus=2)
(root/'jobs.json').write_text(json.dumps(record,indent=2));print(json.dumps(record))
