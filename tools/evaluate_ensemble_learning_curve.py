"""Evaluate the averaged ten-member prediction on all 5,000 validation images."""
import argparse,json,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import torch
from torch.utils.data import DataLoader
from torchmetrics.functional.image import structural_similarity_index_measure as ssim
from scripts.export_corrected_milestone import predictor
from scripts.corrected_comparison_study import paths,write
from scripts.formal_rml_train import Pairs
from scripts.training_records import manifest_digest

@torch.inference_mode()
def main():
 p=argparse.ArgumentParser();p.add_argument('--task',type=int,required=True);a=p.parse_args()
 if not 0<=a.task<20:raise ValueError('Task must be 0..19')
 camera=['rml','diffuser'][a.task%2];epoch=5*(a.task//2+1)
 dest=Path('results/ensemble10_validation_curves_20261015')/camera/f'epoch_{epoch:03d}.json'
 if dest.exists():
  report=json.loads(dest.read_text())
  assert report['epoch']==epoch and report['validation']['count']==5000 and report['members']==10
  print('Already complete',dest);return
 torch.set_num_threads(2);torch.manual_seed(20261015+a.task)
 data,_=paths(camera);dataset=Pairs('val',data)
 if len(dataset)!=5000:raise ValueError('Expected full validation split')
 predict,provenance=predictor(camera,'ensemble10',epoch)
 sums=dict(psnr=0.,ssim=0.,mse=0.);count=0;start=time.monotonic()
 for batch in DataLoader(dataset,batch_size=4,num_workers=2,pin_memory=True,shuffle=False):
  y,x=batch[:,0].cuda(non_blocking=True),batch[:,1].cuda(non_blocking=True)
  with torch.autocast('cuda',dtype=torch.bfloat16):mean,_,_=predict(y)
  # Average raw member means first, then clip the combined reconstruction.
  mean=mean.float().clamp(0,1)
  if mean.shape!=x.shape or not torch.isfinite(mean).all():raise ValueError('Invalid prediction')
  mse=(mean-x).square().mean((1,2,3))
  sums['mse']+=float(mse.sum());sums['psnr']+=float((-10*mse.clamp_min(1e-12).log10()).sum())
  sums['ssim']+=float(ssim(mean,x,data_range=1.,reduction='none').sum());count+=len(x)
  if count%500==0:print(camera,epoch,count,'/5000',flush=True)
 if count!=5000:raise ValueError('Incomplete validation')
 report=dict(camera=camera,epoch=epoch,members=10,split='val',manifest_sha256=manifest_digest(data),
  validation={**{k:v/count for k,v in sums.items()},'count':count,'clipped':True,'reconstruction':'mean of 10 raw member predictions, clipped after averaging'},
  provenance=provenance,seconds=time.monotonic()-start,gpu=torch.cuda.get_device_name(),
  calibration_used=False,note='PSNR/SSIM computed per image after averaging predictions, then averaged over the full validation set. No retraining; no averaging of member metrics.')
 write(dest,report);print(json.dumps(report),flush=True)
if __name__=='__main__':main()
