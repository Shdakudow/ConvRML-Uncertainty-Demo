"""Native image-adaptive QUTCC bounds; no post-hoc calibration or scale fitting."""
import argparse, gc, json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import torch
from torchmetrics.functional.image import structural_similarity_index_measure as ssim
from baselines.mc_dropout import dropout_inference
from scripts.corrected_comparison_study import ROOT, load_model, paths, write
from scripts.formal_rml_train import Pairs
from scripts.training_records import manifest_digest

from scripts.train_constrained_adaptive50 import load_checkpoint
ADAPTIVE_ROOT=Path('results/adaptive_q_coverage90_scratch50_20261014')

def predictor(camera, method, epoch):
    checkpoint=ADAPTIVE_ROOT/camera/('epoch_%03d.pt'%epoch)
    model,ck=load_checkpoint(checkpoint)
    if ck['epoch']!=epoch or ck['camera']!=camera:raise ValueError('Wrong checkpoint')
    if ck['manifest_sha256']!=manifest_digest(paths(camera)[0]):raise ValueError('Training/test manifest mismatch')
    provenance=[dict(arm=method,epoch=epoch,seed=ck['seed'],protocol=ck['protocol'],
        initialization=ck['initialization'],checkpoint=str(checkpoint),
        training_hours=sum(r['segment_seconds'] for r in ck.get('history',[]))/3600)]
    def predict(y):
        result=model.interval_prediction(y)
        predict.quantiles=torch.stack([result['q_lower'],result['q_upper']],dim=1).detach().cpu().numpy()
        return result['prediction'],result['lower'],result['upper']
    predict.history=ck.get('history',[])
    return predict,provenance

@torch.inference_mode()
def main():
    p = argparse.ArgumentParser(); p.add_argument('--task', type=int, required=True)
    p.add_argument('--epoch', type=int, default=20);p.add_argument('--smoke',action='store_true'); p.add_argument('--count', type=int, default=50)
    a = p.parse_args(); camera = ['rml', 'diffuser'][a.task]; method = 'adaptive_qutcc'
    if a.epoch!=20 and not a.smoke:raise ValueError('Only the exact epoch-20 milestone may be exported')
    if not 1 <= a.count <= 5000: raise ValueError('Invalid count')
    out = Path('results/adaptive_q20_native_demo_20261015')/camera/method
    out.mkdir(parents=True, exist_ok=True)
    if not a.smoke and (out/'report.json').exists(): print('Already complete', out); return
    torch.set_num_threads(2); torch.manual_seed(20261011+a.task)
    predict, provenance = predictor(camera, method, a.epoch)
    data, _ = paths(camera)
    def run(b):
        y, x = b[:, 0].cuda(), b[:, 1].cuda()
        with torch.autocast('cuda', dtype=torch.bfloat16): r, lo, hi = predict(y)
        if not all(torch.isfinite(t).all() for t in [r, lo, hi]): raise ValueError('Nonfinite output')
        return x, r, lo, hi
    if a.smoke:
        dataset=Pairs('val',data);x,r,lo,hi=run(torch.stack([dataset[0],dataset[1]]))
        assert (lo<=r).all() and (r<=hi).all() and np.all(predict.quantiles[:,0]<predict.quantiles[:,1])
        print(json.dumps(dict(smoke=True,camera=camera,epoch=a.epoch,shape=list(r.shape),q=predict.quantiles.tolist())),flush=True)
        return
    dataset = Pairs('test', data); records = json.loads((data/'manifest.json').read_text())['test'][:a.count]
    arrays = {k: [] for k in ['measurement', 'target', 'prediction', 'lower', 'upper']}; rows = []
    t = time.monotonic()
    for i in range(0, a.count, 4):
        b = torch.stack([dataset[j] for j in range(i, min(i+4, a.count))])
        x, r, lo, hi = run(b)
        lower, upper = lo, hi
        prediction = r.clamp(0,1)
        for key, v in zip(arrays, [b[:,0], x, prediction, lower, upper]): arrays[key].append(v.cpu().numpy())
        for j in range(len(x)):
            e = prediction[j]-x[j]
            rows.append(dict(id=records[i+j]['id'],q_lower=float(predict.quantiles[j,0]),q_upper=float(predict.quantiles[j,1]), psnr=float(-10*e.square().mean().clamp_min(1e-12).log10()),
                ssim=float(ssim(prediction[j:j+1], x[j:j+1], data_range=1.)), mae=float(e.abs().mean()),
                coverage=float(((x[j]>=lower[j]) & (x[j]<=upper[j])).float().mean()),
                width=float((upper[j]-lower[j]).mean()), native_crossing=float((lo[j]>hi[j]).float().mean())))
    inference_seconds = time.monotonic()-t
    np.savez_compressed(out/'examples.npz', **{k:np.concatenate(v) for k,v in arrays.items()})
    history = {}
    for arm in [r['arm'] for r in provenance]:
        history[arm] = predict.history
    report = dict(camera=camera, method=method, epoch=a.epoch, count=a.count, calibration_count=0, calibration_used=False, interval_method="native_learned_image_quantiles",
        alpha=.1, delta=None, factors=None, calibration=None, per_image=rows,
        aggregate={k:float(np.mean([r[k] for r in rows])) for k in ['psnr','ssim','mae','coverage','width','native_crossing']},
        provenance=provenance, validation_history=history, manifest_sha256=manifest_digest(data),
        calibration_sha256=None, gpu=torch.cuda.get_device_name(),
        calibration_seconds=0, inference_seconds=inference_seconds,
        notes='New image-adaptive QUTCC trained jointly from random initialization, exact epoch 20. Same first 50 held-out test images as the epoch-50 baselines; unequal training budgets are explicitly labeled. Native learned image-specific q endpoints; no RCPS, no fitted scales, no calibration images. Alpha=.10 is a training target, not a coverage guarantee. Prediction is q=.5. Clipped [0,1]. No test-based q tuning. Not a full-test aggregate.')
    write(out/'report.json', report); print('COMPLETE', camera, method, flush=True)

if __name__ == '__main__': main()
