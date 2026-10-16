"""Use existing p=.05 checkpoints; new inference and calibration, no retraining."""
import json,subprocess
from pathlib import Path
root=Path('results/mc005_demo_jobs_20261015');root.mkdir(parents=True,exist_ok=True)
p=root/'jobs.json';record=json.loads(p.read_text()) if p.exists() else {}
base=['/usr/local/slurm/current/bin/sbatch','--parsable','--partition=gpu','--gres=gpu:1',
 '--constraint=(h100|h200|6000ada|a6000)&avx2','--prefer=h100|h200|6000ada',
 '--exclude=monakhova-compute-01,nikola-compute-15,bhattacharjee-compute-02',
 '--cpus-per-task=2','--mem=48G','--time=06:00:00','--requeue',
 '--output=logs/mc005_eval_%A_%a.out','--error=logs/mc005_eval_%A_%a.err']
def submit(key,args):
 if key not in record:
  record[key]=subprocess.check_output(base+args,text=True).strip().split(';')[0]
  p.write_text(json.dumps(record,indent=2))
submit('exports',['--job-name=mc005-demo','--array=0-1%1','--wrap',
 '$HOME/.conda/envs/convrml/bin/python -u scripts/export_corrected_milestone.py --task "$((3+4*SLURM_ARRAY_TASK_ID))" --method mc_005 --epoch 50 --count 50'])
submit('curves',['--job-name=mc005-curves','--array=0-19%2','--wrap',
 'i=$SLURM_ARRAY_TASK_ID; if [ "$i" -lt 10 ]; then c=rml; else c=diffuser; fi; $HOME/.conda/envs/convrml/bin/python -u scripts/evaluate_interval_curves.py --camera "$c" --method mc_005 --epoch "$((5*(i%10+1)))"'])
print(json.dumps(record,indent=2))
