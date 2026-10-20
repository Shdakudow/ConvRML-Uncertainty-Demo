"""Export the first 50 fixed test pairs using saved epoch-50 quantile calibration."""
import argparse,json,sys,hashlib,time
from pathlib import Path
import numpy as np
import torch
from torchmetrics.functional.image import structural_similarity_index_measure as ssim
ROOT=Path.home()/'ConvRML/experiments/qutcc_paper_style_20261018'
sys.path.insert(0,str(ROOT))
from model import Model
from data import Pairs,identity
@torch.inference_mode()
def main():
 p=argparse.ArgumentParser();p.add_argument('--camera',choices=['rml','diffuser'],required=True);a=p.parse_args()
 src=ROOT/'results'/a.camera/'qutcc';report=json.loads((src/'evaluation/epoch_050/report.json').read_text());cal=report['calibration']
 ckpath=src/'checkpoints/epoch_050.pt';ck=torch.load(ckpath,map_location='cpu',weights_only=False)
 assert ck['config']['dataset_identity']==identity(a.camera) and report['epoch']==50
 torch.set_num_threads(2);model=Model('qutcc');model.load_state_dict(ck['model'],strict=True);model=model.cuda().eval();model.requires_grad_(False)
 data=Pairs(a.camera,'test');arrays={k:[] for k in ['measurement','target','prediction','lower','upper']};rows=[];micro=report['config']['microbatch']
 for i in range(0,50,micro):
  b=torch.stack([data[j] for j in range(i,min(i+micro,50))]);y,x=b[:,0].cuda(),b[:,1].cuda()
  pred=model(y);lo=model(y,y.new_full((len(y),),cal['lower_q']));hi=model(y,y.new_full((len(y),),cal['upper_q']))
  pred,lo,hi=[t.clamp(0,1) for t in [pred,lo,hi]]
  assert all(torch.isfinite(t).all() for t in [pred,lo,hi])
  for key,t in zip(arrays,[y,x,pred,lo,hi]):arrays[key].append(t.cpu().numpy())
  for j in range(len(y)):
   e=pred[j:j+1]-x[j:j+1];v=dict(psnr=float(-10*e.square().mean().clamp_min(1e-12).log10()),ssim=float(ssim(pred[j:j+1],x[j:j+1],data_range=1.)),mae=float(e.abs().mean()),coverage=float(((x[j]>=lo[j])&(x[j]<=hi[j])).float().mean()),width=float((hi[j]-lo[j]).mean()))
   expected=report['per_image'][i+j];assert str(expected['id'])==str(data.rows[i+j]['id'])
   # Float32 kernels can vary slightly across GPU architectures. Keep explicit tolerances.
   for k in v:assert abs(v[k]-expected['clipped'][k])<(0.002 if k=='psnr' else 0.0001),(i+j,k,v[k],expected['clipped'][k])
   rows.append(dict(id=data.rows[i+j]['id'],**v))
 out=Path.home()/'ConvRML/results/paper_qutcc50_demo_20261019'/a.camera;out.mkdir(parents=True,exist_ok=True)
 np.savez_compressed(out/'examples.npz',**{k:np.concatenate(v) for k,v in arrays.items()})
 with ckpath.open('rb') as f:digest=hashlib.file_digest(f,'sha256').hexdigest()
 (out/'report.json').write_text(json.dumps(dict(camera=a.camera,epoch=50,count=50,ids=[r['id'] for r in rows],per_image=rows,aggregate={k:float(np.mean([r[k] for r in rows])) for k in ['psnr','ssim','mae','coverage','width']},calibration=cal,checkpoint_sha256=digest,validation_history=ck['history'],full_test_metrics=report['metrics'],source_experiment='qutcc_paper_style_20261018',evaluations=[{k:d[k] for k in ['epoch','metrics','calibration','test_count']} for d in [json.loads(f.read_text()) for f in sorted((src/'evaluation').glob('epoch_*/report.json'))]]),indent=2))
 print('Export complete',out,flush=True)
if __name__=='__main__':main()
