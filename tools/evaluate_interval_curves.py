"""Full held-out interval curves: baseline RCPS; native adaptive QUTCC."""
import argparse,gc,json,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
import torch
from torch.utils.data import DataLoader
from torchmetrics.functional.image import structural_similarity_index_measure as ssim
from scripts.corrected_comparison_study import paths,write
from scripts.formal_rml_train import Pairs
from scripts.training_records import manifest_digest
from scripts.export_corrected_milestone import predictor
from scripts.asymmetric_rcps import select_asymmetric_factors
from scripts.train_constrained_adaptive50 import load_checkpoint
ROOT=Path('results/current_interval_curves_20261015')
METHODS=['im2im','ensemble5','ensemble10','mc_010','adaptive_qutcc']

@torch.inference_mode()
def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--camera',choices=['rml','diffuser'],required=True)
 p.add_argument('--method',choices=METHODS,required=True)
 p.add_argument('--epoch',type=int,choices=list(range(5,51,5)),required=True)
 p.add_argument('--smoke',action='store_true');a=p.parse_args()
 native=a.method=='adaptive_qutcc';data,caldir=paths(a.camera)
 out=ROOT/('smoke' if a.smoke else 'reports')/a.camera/a.method/f'epoch_{a.epoch:03d}.json'
 out.parent.mkdir(parents=True,exist_ok=True)
 if out.exists():
  r=json.loads(out.read_text());assert r['test_count']==(4 if a.smoke else 5000) and r['calibration_used']==(not native)
  print('Already complete',out);return
 seed=202610150+METHODS.index(a.method)+10*(a.camera=='diffuser')
 torch.set_num_threads(2);torch.manual_seed(seed)
 common=dict(camera=a.camera,method=a.method,epoch=a.epoch,split='test',test_count=4 if a.smoke else 5000,
  clipped=True,alpha=.1,delta=None if native else .05,calibration_used=not native,
  interval_method='native_learned_image_quantiles' if native else 'rcps_hb_asymmetric',
  manifest_sha256=manifest_digest(data),seed=seed,mc_passes=30 if a.method=='mc_010' else None)
 # Reuse completed full-test ensemble evaluations instead of repeating them.
 reuse=Path('results/ensemble_size_comparison_20261015')/a.camera/a.method/'report.json'
 if not a.smoke and a.epoch==50 and a.method.startswith('ensemble') and reuse.exists():
  r=json.loads(reuse.read_text())
  assert r['full_test_count']==5000 and r['epoch']==50 and r['alpha']==.1 and r['delta']==.05
  assert r['manifest_sha256']==common['manifest_sha256'] and r['calibration_sha256']==manifest_digest(caldir)
  write(out,dict(**common,metrics=r['full_test_aggregate'],calibration_count=r['calibration_count'],
   calibration_sha256=r['calibration_sha256'],factors=r['factors']['rcps_hb'],source=str(reuse),provenance=r['provenance']))
  print('Reused',out,flush=True);return
 if native:
  checkpoint=Path('results/adaptive_q_coverage90_scratch50_20261014')/a.camera/f'epoch_{a.epoch:03d}.pt'
  model,ck=load_checkpoint(checkpoint)
  assert ck['camera']==a.camera and ck['epoch']==a.epoch and ck['manifest_sha256']==common['manifest_sha256']
  predict=model.bounds;provenance=[dict(checkpoint=str(checkpoint),protocol=ck['protocol'],epoch=ck['epoch'])]
 else:predict,provenance=predictor(a.camera,a.method,a.epoch)
 def run(batch):
  y,x=batch[:,0].cuda(),batch[:,1].cuda()
  with torch.autocast('cuda',dtype=torch.bfloat16):r,lo,hi=predict(y)
  if not all(torch.isfinite(t).all() for t in [r,lo,hi]):raise ValueError('Nonfinite prediction')
  return x,r.float(),lo.float(),hi.float()
 start=time.monotonic();factors=None;cal_count=0
 if not native:
  cal=np.load(caldir/'pairs.npy',mmap_mode='r');cal_count=len(cal)
  if not a.smoke and cal_count!=2048:raise ValueError('Wrong calibration split')
  files=[out.with_suffix('.lower.tmp.npy'),out.with_suffix('.upper.tmp.npy')]
  scores=[np.lib.format.open_memmap(f,mode='w+',dtype=np.float32,shape=(cal_count,*cal.shape[2:])) for f in files]
  try:
   for i in range(0,cal_count,4):
    x,r,lo,hi=run(torch.from_numpy(np.array(cal[i:min(i+4,cal_count)],copy=True)).float()/255)
    scores[0][i:i+len(x)]=((r-x)/(r-lo).clamp_min(1e-6)).cpu().numpy()
    scores[1][i:i+len(x)]=((x-r)/(hi-r).clamp_min(1e-6)).cpu().numpy()
   for score in scores:score.flush()
   selected,_,_=select_asymmetric_factors(*scores);factors=selected['rcps_hb']
  finally:
   del scores;gc.collect()
   for f in files:f.unlink(missing_ok=True)
 calibration_seconds=time.monotonic()-start
 # Smoke uses validation images; production curves use the entire test split.
 dataset=Pairs('val' if a.smoke else 'test',data)
 if len(dataset)!=5000:raise ValueError('Expected 5000 images')
 loader=DataLoader(torch.utils.data.Subset(dataset,range(common['test_count'])),batch_size=4,num_workers=2,pin_memory=True)
 totals=dict(width=0.,coverage=0.,psnr=0.,ssim=0.,mae=0.);count=0;start=time.monotonic()
 for b in loader:
  x,r,lo,hi=run(b)
  if native:lower,upper=lo,hi
  else:
   lower=(r-factors['lower']*(r-lo).clamp_min(1e-6)).clamp(0,1)
   upper=(r+factors['upper']*(hi-r).clamp_min(1e-6)).clamp(0,1)
  if not (lower<=upper).all():raise ValueError('Crossed bounds')
  pred=r.clamp(0,1);error=pred-x
  vals=dict(width=(upper-lower).mean((1,2,3)),coverage=((x>=lower)&(x<=upper)).float().mean((1,2,3)),
   psnr=-10*error.square().mean((1,2,3)).clamp_min(1e-12).log10(),
   ssim=ssim(pred,x,data_range=1.,reduction='none'),mae=error.abs().mean((1,2,3)))
  for k,v in vals.items():totals[k]+=float(v.sum())
  count+=len(x)
  if count%500==0:print(a.camera,a.method,a.epoch,count,'/5000',flush=True)
 assert count==common['test_count']
 if a.smoke:common['split']='val_smoke'
 write(out,dict(**common,metrics={k:v/count for k,v in totals.items()},calibration_count=cal_count,
  calibration_sha256=None if native else manifest_digest(caldir),factors=factors,provenance=provenance,
  calibration_seconds=calibration_seconds,inference_seconds=time.monotonic()-start,gpu=torch.cuda.get_device_name()))
 print('COMPLETE',str(out),flush=True)
if __name__=='__main__':main()
