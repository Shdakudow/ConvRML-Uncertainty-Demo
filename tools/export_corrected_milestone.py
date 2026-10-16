"""Frozen milestone demo: independent calibration, first 50 manifest test cases."""
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
from scripts.asymmetric_rcps import select_asymmetric_factors

METHODS = ['conditioned', 'im2im', 'ensemble10', 'mc_010']

def predictor(camera, method, epoch):
    members = {'ensemble5': 5, 'ensemble10': 10}.get(method)
    arms = [f'ensemble_{i:02d}' for i in range(members)] if members else [method]
    models, provenance = [], []
    for arm in arms:
        model, ck = load_model(camera, arm, epoch)
        models.append(model.cuda().eval())
        provenance.append(dict(arm=arm, epoch=ck['epoch'], seeds=ck['seeds'],
                               training_hours=sum(r['seconds'] for r in ck['history'])/3600))
    if method.startswith('mc_'):
        rates=[m.p for m in models[0].modules() if isinstance(m,torch.nn.Dropout)]
        expected={'mc_005':.05,'mc_010':.1,'mc_020':.2}[method]
        if len([p for p in rates if p>0])!=48 or any(p>0 and abs(p-expected)>1e-8 for p in rates):raise ValueError('Unexpected dropout layout or rate')
    def predict(y):
        if members:
            mu = second = None
            for model in models:
                r, v = model(y); r, v = r.float(), v.float()
                mu = r if mu is None else mu+r
                second = v+r.square() if second is None else second+v+r.square()
            r = mu/members; var = (second/members-r.square()).clamp_min(0)
        elif method in ('mc_005','mc_010','mc_020'):
            r = m2 = None
            with dropout_inference(models[0]):
                for i in range(30):
                    sample = models[0](y).float()
                    if r is None: r, m2 = sample, torch.zeros_like(sample)
                    else:
                        d = sample-r; r = r+d/(i+1); m2 = m2+d*(sample-r)
            var = m2/30
        else:
            return tuple(t.float() for t in models[0].bounds(y))
        radius = 1.6448536269514722*var.sqrt()
        return r, r-radius, r+radius
    return predict, provenance

@torch.inference_mode()
def main():
    p = argparse.ArgumentParser(); p.add_argument('--task', type=int, required=True)
    p.add_argument('--method',choices=['mc_005','mc_010','mc_020']); p.add_argument('--epoch', type=int, default=25); p.add_argument('--count', type=int, default=50)
    a = p.parse_args(); camera = ['rml', 'diffuser'][a.task//4]; method = a.method or METHODS[a.task%4]
    if not 1 <= a.count <= 5000: raise ValueError('Invalid count')
    out = Path(f'results/corrected_demo_epoch{a.epoch}_20261011')/camera/method
    out.mkdir(parents=True, exist_ok=True)
    if (out/'report.json').exists(): print('Already complete', out); return
    torch.set_num_threads(2); torch.manual_seed(20261011+a.task)
    predict, provenance = predictor(camera, method, a.epoch)
    data, caldir = paths(camera); cal = np.load(caldir/'pairs.npy', mmap_mode='r')
    def run(b):
        y, x = b[:, 0].cuda(), b[:, 1].cuda()
        with torch.autocast('cuda', dtype=torch.bfloat16): r, lo, hi = predict(y)
        if not all(torch.isfinite(t).all() for t in [r, lo, hi]): raise ValueError('Nonfinite output')
        return x, r, lo, hi
    t = time.monotonic()
    files = [out/'lower_scores.tmp.npy', out/'upper_scores.tmp.npy']
    scores = [np.lib.format.open_memmap(f, mode='w+', dtype=np.float32, shape=(len(cal), *cal.shape[2:])) for f in files]
    for i in range(0, len(cal), 4):
        x, r, lo, hi = run(torch.from_numpy(np.array(cal[i:i+4], copy=True)).float()/255)
        scores[0][i:i+len(x)] = ((r-x)/(r-lo).clamp_min(1e-6)).cpu().numpy()
        scores[1][i:i+len(x)] = ((x-r)/(hi-r).clamp_min(1e-6)).cpu().numpy()
        if i % 256 == 0: print(camera, method, 'calibration', i, '/', len(cal), flush=True)
    for s in scores: s.flush()
    factors, audit, _ = select_asymmetric_factors(*scores)
    del scores, s; gc.collect()
    for f in files: f.unlink()
    cal_seconds = time.monotonic()-t
    print(camera, method, 'calibration complete', factors, flush=True)
    dataset = Pairs('test', data); records = json.loads((data/'manifest.json').read_text())['test'][:a.count]
    arrays = {k: [] for k in ['measurement', 'target', 'prediction', 'lower', 'upper']}; rows = []
    t = time.monotonic()
    for i in range(0, a.count, 4):
        b = torch.stack([dataset[j] for j in range(i, min(i+4, a.count))])
        x, r, lo, hi = run(b); f = factors['rcps_hb']
        lower = (r-f['lower']*(r-lo).clamp_min(1e-6)).clamp(0,1)
        upper = (r+f['upper']*(hi-r).clamp_min(1e-6)).clamp(0,1)
        prediction = r.clamp(0,1)
        for key, v in zip(arrays, [b[:,0], x, prediction, lower, upper]): arrays[key].append(v.cpu().numpy())
        for j in range(len(x)):
            e = prediction[j]-x[j]
            rows.append(dict(id=records[i+j]['id'], psnr=float(-10*e.square().mean().clamp_min(1e-12).log10()),
                ssim=float(ssim(prediction[j:j+1], x[j:j+1], data_range=1.)), mae=float(e.abs().mean()),
                coverage=float(((x[j]>=lower[j]) & (x[j]<=upper[j])).float().mean()),
                width=float((upper[j]-lower[j]).mean()), native_crossing=float((lo[j]>hi[j]).float().mean())))
    inference_seconds = time.monotonic()-t
    np.savez_compressed(out/'examples.npz', **{k:np.concatenate(v) for k,v in arrays.items()})
    history = {}
    for arm in [r['arm'] for r in provenance]:
        history[arm] = json.loads((ROOT/camera/arm/'history.json').read_text())
    report = dict(camera=camera, method=method, epoch=a.epoch, count=a.count, calibration_count=len(cal),
        alpha=.1, delta=.05, factors=factors, calibration=audit, per_image=rows,
        aggregate={k:float(np.mean([r[k] for r in rows])) for k in ['psnr','ssim','mae','coverage','width','native_crossing']},
        provenance=provenance, validation_history=history, manifest_sha256=manifest_digest(data),
        calibration_sha256=manifest_digest(caldir), gpu=torch.cuda.get_device_name(),
        calibration_seconds=cal_seconds, inference_seconds=inference_seconds,
        notes=f'First 50 held-out test images in manifest order; not full-test aggregates. RCPS independent lower/upper scaling, alpha=.1, delta=.05. Clipped [0,1]. QUTCC native q=.05/.95 followed by scale calibration, not quantile-query calibration. MC dropout rate follows the selected checkpoint ({method}); 30 stochastic passes. p=.05 selected from epoch-50 deterministic validation, not test results. Width need not equal absolute error. Image-level coverage is not guaranteed to be 90%.')
    write(out/'report.json', report); print('COMPLETE', camera, method, flush=True)

if __name__ == '__main__': main()
