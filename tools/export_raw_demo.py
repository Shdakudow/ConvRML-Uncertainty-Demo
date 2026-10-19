"""Raw DiffuserCam demo export, independent of immutable training source trees."""
import argparse,gzip,hashlib,json,struct,sys,time
from pathlib import Path
import numpy as np
PROJECT=Path.home()/'ConvRML'
SOURCE={'clean':PROJECT/'experiments/qutcc_paper_style_20261018','corrupted':PROJECT/'experiments/raw_diffuser_corruptions_20261018'}
EPOCH={'clean':50,'corrupted':10}
EXPORT_VARIANT=None
REUSE_EVALUATION=False
ROOT=PROJECT/'experiments/raw_diffuser_demo_20261019'

def write(path,obj):
 path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(obj,indent=2));tmp.replace(path)
def sha(path):
 with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def pack(path,idx,identifier,arrays,metrics,calibration):
 chunks=[];descriptors=[];offset=0
 for key,value in arrays.items():
  if key in ('measurement','target'):a=np.rint(value*255).astype('uint8');encoding='uint8';raw=a.tobytes()
  else:
   a=np.asarray(value,dtype='<f4');encoding='float32-shuffled';raw=a.reshape(-1).view('uint8').reshape(-1,4).T.copy().tobytes()
  assert np.isfinite(a).all()
  descriptors.append(dict(name=key,shape=list(a.shape),offset=offset,length=len(raw),encoding=encoding,sha256=hashlib.sha256(raw).hexdigest()));chunks.append(raw);offset+=len(raw)
 header=json.dumps(dict(index=idx,id=identifier,arrays=descriptors,metrics=metrics,calibration=calibration),separators=(',',':')).encode()
 binary=struct.pack('<I',len(header))+header+b''.join(chunks);compressed=gzip.compress(binary,compresslevel=6,mtime=0)
 assert gzip.decompress(compressed)==binary
 path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_suffix('.tmp');tmp.write_bytes(compressed);tmp.replace(path)

def summarize(study,method):
 source=SOURCE[study]/'results/raw'/method;epoch=EPOCH[study];out=ROOT/'exports'/study/method
 history=json.loads((source/'history.json').read_text());evaluations=[]
 for path in sorted((source/'evaluation').glob('epoch_*')):
  report=path/'report.json';failure=path/'failure.json'
  if report.exists():
   row=json.loads(report.read_text());assert row['test_count']==2000
   evaluations.append(dict(epoch=row['epoch'],status='complete',metrics=row['metrics'],calibration=row['calibration'],test_count=row['test_count'],calibration_seconds=row['calibration_seconds'],inference_seconds=row['inference_seconds']))
  elif failure.exists():evaluations.append(dict(epoch=int(path.name.split('_')[-1]),status='failed',failure=json.loads(failure.read_text())))
 source_report=json.loads((source/'evaluation'/f'epoch_{epoch:03d}'/'report.json').read_text())
 summary=dict(study=study,method=method,epoch=epoch,config=source_report['config'],history=history,evaluations=evaluations,metrics=source_report['metrics'],calibration=source_report['calibration'],test_count=2000,calibration_count=3000,example_count=10,refreshed=False,source_report_sha256=sha(source/'evaluation'/f'epoch_{epoch:03d}'/'report.json'))
 baseline=source/'baseline_validation.json'
 if baseline.exists():summary['baseline_validation']=json.loads(baseline.read_text())
 return summary

def snapshot():
 for study in SOURCE:
  for method in ('qutcc','im2im'):
   summary=summarize(study,method);source=SOURCE[study]/'results/raw'/method/'evaluation'/f'epoch_{EPOCH[study]:03d}';report=json.loads((source/'report.json').read_text());out=ROOT/'exports'/study/method
   with np.load(source/'examples.npz') as examples:
    for i in range(10):
     arrays={key:examples[f'{i}_{key}'] for key in ('measurement','target','prediction','lower','upper')}
     for key in ('prediction','lower','upper'):arrays[key]=np.clip(arrays[key],0,1)
     row=report['per_image'][i];coverage=float(((arrays['target']>=arrays['lower'])&(arrays['target']<=arrays['upper'])).mean());assert abs(coverage-row['clipped']['coverage'])<1e-6
     pack(out/f'example_{i:02d}.bin.gz',i,row['id'],arrays,row['clipped'],summary['calibration'])
   write(out/'summary.json',summary);print(study,method,'snapshot complete',flush=True)

@__import__('contextlib').contextmanager
def source_import(study):
 sys.path.insert(0,str(SOURCE[study]));yield

def refresh(study,method):
 import torch
 from torch.utils.data import DataLoader,Subset
 torch.set_num_threads(2)
 with source_import(study):
  import evaluate as evaluation
  from model import Model
  from data import Pairs,identity
  from calibration import CalibrationFailure
  from torchmetrics.functional.image import structural_similarity_index_measure as ssim
  epoch=EPOCH[study];source=SOURCE[study]/'results/raw'/method;work=ROOT/'refresh'/study/method
  cp=work/'results/raw'/method/'checkpoints'/f'epoch_{epoch:03d}.pt';cp.parent.mkdir(parents=True,exist_ok=True)
  if not cp.exists():cp.symlink_to(source/'checkpoints'/cp.name)
  if study=='corrupted':(work/'TRAINING_APPROVED').write_text('User authorized calibration and demo exports on 2026-10-19.\n')
  evaluation.ROOT=work;evaluation.TASKS=[('raw',method)]
  # Native original protocol and data identity are checked inside evaluation.run.
  report_path=(source if REUSE_EVALUATION else work/'results/raw'/method)/'evaluation'/f'epoch_{epoch:03d}'/'report.json'
  if REUSE_EVALUATION and not report_path.exists():
   print('Calibration unavailable at this milestone; no calibrated examples exported.',flush=True);return
  if not REUSE_EVALUATION:evaluation.run(argparse.Namespace(task=0,epoch=epoch))
  report=json.loads(report_path.read_text());ck=torch.load(cp,map_location='cpu',weights_only=False)
  assert ck['config']['dataset_identity']==identity('raw');model=Model(method);model.load_state_dict(ck['model'],strict=True);model=model.cuda().eval();del ck
  fitted=report['calibration'];test=Pairs('raw','test');out=ROOT/'exports'/(EXPORT_VARIANT or study)/method;rows=[]
  with torch.inference_mode():
   for index,pair in enumerate(DataLoader(Subset(test,range(50)),batch_size=1,num_workers=2)):
    y,x=pair[:,0].cuda(),pair[:,1].cuda()
    if method=='qutcc':
     prediction=model(y);lower=model(y,y.new_full((1,),fitted['lower_q']));upper=model(y,y.new_full((1,),fitted['upper_q']))
    else:
     z=model(y);prediction=z[:,1];lower=prediction-fitted['scales']['lower']*(prediction-z[:,0]).clamp_min(1e-6);upper=prediction+fitted['scales']['upper']*(z[:,2]-prediction).clamp_min(1e-6)
    prediction,lower,upper=[a.clamp(0,1) for a in (prediction,lower,upper)]
    metrics=dict(psnr=float(-10*(prediction-x).square().mean().clamp_min(1e-12).log10()),ssim=float(ssim(prediction,x,data_range=1.)),mae=float((prediction-x).abs().mean()),coverage=float(((x>=lower)&(x<=upper)).float().mean()),width=float((upper-lower).mean()),crossing=float((lower>upper).float().mean()))
    assert all(np.isfinite(v) for v in metrics.values())
    # Same IDs, targets and metric conventions as full-test evaluation.
    assert test.rows[index]['id']==report['per_image'][index]['id']
    for key in metrics:assert abs(metrics[key]-report['per_image'][index]['clipped'][key])<2e-5,(index,key)
    arrays={key:a[0].cpu().numpy() for key,a in [('measurement',y),('target',x),('prediction',prediction),('lower',lower),('upper',upper)]}
    pack(out/f'example_{index:02d}.bin.gz',index,test.rows[index]['id'],arrays,metrics,fitted);rows.append(metrics)
  summary=summarize(study,method);summary.update(asset_study=EXPORT_VARIANT or study,example_count=50,refreshed=True,metrics=report['metrics'],calibration=fitted,refresh_report_sha256=sha(report_path),gpu=torch.cuda.get_device_name(),example_metrics=rows)
  # Update the final milestone with the independently refreshed calibration/test results.
  for row in summary['evaluations']:
   if row['epoch']==epoch:row.update(metrics=report['metrics'],calibration=fitted,refreshed=True)
  write(out/'summary.json',summary);print(json.dumps({'study':study,'method':method,'status':'complete','examples':50,'metrics':report['metrics']}),flush=True)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--snapshot',action='store_true');p.add_argument('--study',choices=SOURCE);p.add_argument('--method',choices=['qutcc','im2im']);p.add_argument('--epoch',type=int);p.add_argument('--source-extension');p.add_argument('--output-variant');p.add_argument('--reuse-evaluation',action='store_true');a=p.parse_args()
 if a.epoch:EPOCH[a.study]=a.epoch
 if a.source_extension:SOURCE[a.study]=PROJECT/'experiments'/a.source_extension
 EXPORT_VARIANT=a.output_variant;REUSE_EVALUATION=a.reuse_evaluation
 if a.snapshot:snapshot()
 else:refresh(a.study,a.method)
