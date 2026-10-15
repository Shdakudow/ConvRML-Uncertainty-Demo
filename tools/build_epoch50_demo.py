"""Build exact-float32, compressed static examples from frozen milestone inference."""
import argparse,base64,gzip,json
from pathlib import Path
import numpy as np

METHODS=['im2im','ensemble10','mc_010']
def enc(a):
 a=np.asarray(a,dtype='<f4')
 if not np.isfinite(a).all():raise ValueError('Nonfinite export')
 packed=a.reshape(-1).view('uint8').reshape(-1,4).T.copy().tobytes()
 restored=np.frombuffer(packed,dtype='uint8').reshape(4,-1).T.copy().view('<f4').reshape(a.shape)
 assert np.array_equal(restored,a)
 return base64.b64encode(packed).decode()

def main():
 global METHODS
 p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('--output',type=Path,default=Path('corrected-epoch25/data'));p.add_argument('--camera',choices=['rml','diffuser']);p.add_argument('--methods',default=','.join(METHODS));a=p.parse_args();METHODS=a.methods.split(',')
 for camera in ([a.camera] if a.camera else ['rml','diffuser']):
  reports={m:json.loads((a.source/camera/m/'report.json').read_text()) for m in METHODS}
  arrays={m:dict(np.load(a.source/camera/m/'examples.npz')) for m in METHODS}
  baseline=arrays['im2im']; count=len(baseline['target']);maps=[]
  for m in METHODS:
   r=reports[m];v=arrays[m]
   assert r['epoch']==(20 if m=='adaptive_qutcc' else 50) and r['count']==count==50 and r['calibration_count']==2048
   assert r['calibration_sha256']==reports['im2im']['calibration_sha256']
   assert r['alpha']==.1 and r['delta']==.05
   assert r['manifest_sha256']==reports['im2im']['manifest_sha256']
   assert [x['id'] for x in r['per_image']]==[x['id'] for x in reports['im2im']['per_image']]
   assert np.array_equal(v['target'],baseline['target']) and np.array_equal(v['measurement'],baseline['measurement'])
   assert all(np.isfinite(x).all() for x in v.values())
   assert np.all(v['lower']<=v['upper'])
   maps.extend([(v['upper']-v['lower']).mean(1).ravel()[::16],np.abs(v['prediction']-v['target']).mean(1).ravel()[::16]])
   # Recompute stored metrics from actual arrays before publication.
   coverage=((v['target']>=v['lower'])&(v['target']<=v['upper'])).mean((1,2,3))
   width=(v['upper']-v['lower']).mean((1,2,3))
   assert np.allclose(coverage,[x['coverage'] for x in r['per_image']],atol=1e-7)
   assert np.allclose(width,[x['width'] for x in r['per_image']],atol=1e-6)
  out=a.output/camera;out.mkdir(parents=True,exist_ok=True)
  for i in range(count):
   obj=dict(id=reports['im2im']['per_image'][i]['id'],models={})
   for key in ['measurement','target']:obj[key]=base64.b64encode(np.rint(baseline[key][i]*255).astype('uint8').tobytes()).decode()
   for m in METHODS:
    v=arrays[m];obj['models'][m]=dict(mean=enc(v['prediction'][i]),lower=enc(v['lower'][i]),upper=enc(v['upper'][i]),metrics=reports[m]['per_image'][i])
   raw=('window.receiveExample('+str(i)+','+json.dumps(obj,separators=(',',':'))+');').encode()
   zipped=gzip.compress(raw,compresslevel=6,mtime=0)
   assert gzip.decompress(zipped)==raw
   (out/f'example_{i:02d}.js.gz').write_bytes(zipped)
  meta=dict(methods=METHODS,epochs={m:r['epoch'] for m,r in reports.items()},pendingMethods=[m for m in ['im2im','ensemble10','mc_010','adaptive_qutcc'] if m not in METHODS],study='RML' if camera=='rml' else 'DiffuserCam',epoch=reports['im2im']['epoch'],count=count,ids=[r['id'] for r in reports['im2im']['per_image']],encoding='float32-shuffled',metricClipping='[0,1]',trainCount=60000,
    mapMax=float(np.quantile(np.concatenate(maps),.995)),aggregate={m:r['aggregate'] for m,r in reports.items()},
    factors={m:r['factors']['rcps_hb'] for m,r in reports.items()},calibrationCount=2048,calibrationMethod='RCPS (Hoeffding–Bentkus), separate lower/upper scaling',alpha=.1,delta=.05,
    history={m:[x for x in reports[m]['validation_history'][m] if x['epoch']<=reports['im2im']['epoch']] for m in METHODS if not m.startswith('ensemble')},
    notes='Epoch 50; 60,000 training images, 5,000 validation, 5,000 test, 2,048 independent calibration. First 50 test images shown without quality selection. RCPS alpha=.10 delta=.05; separate lower/upper factors. Clipped float32 metrics. MC p=.10, 30 draws fixed for continuity, not claimed validation-optimal. Adaptive QUTCC, when available, uses epoch 20: unequal training budgets, explicitly labeled. Its q endpoints are learned per image before separate RCPS scale calibration.',manifest_sha256=reports['im2im']['manifest_sha256'])
  (out/'manifest.js').write_text('window.DATASET='+json.dumps(meta,separators=(',',':'))+';')
  (out/'protocol.json').write_text(json.dumps({**meta,'reports':reports},indent=2))
  print(camera,count,'examples; sample aggregate',meta['aggregate'],flush=True)

if __name__=='__main__':main()
