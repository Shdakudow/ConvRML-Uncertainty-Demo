#!/bin/bash
#SBATCH --account=monakhova
#SBATCH --qos=normal
#SBATCH --partition=gpu
#SBATCH --gres=gpu:1
#SBATCH --constraint=6000ada&avx2
#SBATCH --exclude=monakhova-compute-01,nikola-compute-15,bhattacharjee-compute-02
#SBATCH --cpus-per-task=4
#SBATCH --mem=48G
#SBATCH --time=12:00:00
#SBATCH --requeue
#SBATCH --signal=B:USR1@180

set -euo pipefail
export OMP_NUM_THREADS=2 MKL_NUM_THREADS=2
task_root=/home/jy2228/ConvRML/experiments/experiment4_epoch_intervals_20261103
task_index=$((SLURM_ARRAY_TASK_ID / 2))
task_epoch=$((task_index == 0 ? 100 : task_index * 10))
task_method=qutcc
if (( SLURM_ARRAY_TASK_ID % 2 )); then task_method=im2im; fi
child=''
trap 'if [ -n "$child" ]; then kill -USR1 "$child" 2>/dev/null || true; fi' USR1
trap 'if [ -n "$child" ]; then kill -TERM "$child" 2>/dev/null || true; fi' TERM
/home/jy2228/.conda/envs/convrml/bin/python -u "$task_root/evaluate_exp4_epoch_intervals.py" \
    --method "$task_method" --epoch "$task_epoch" \
    --output "$task_root/output/$task_method/epoch_$task_epoch" &
child=$!
set +e
wait "$child"
task_status=$?
if kill -0 "$child" 2>/dev/null; then wait "$child"; task_status=$?; fi
if [ "$task_status" -eq 75 ]; then
    /usr/local/slurm/current/bin/scontrol requeue "${SLURM_ARRAY_JOB_ID}_${SLURM_ARRAY_TASK_ID}"
    exit 0
fi
exit "$task_status"
