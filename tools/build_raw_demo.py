"""Build raw-study metadata and audit lossless binary exports before publication."""
import argparse,gzip,hashlib,json,struct
from pathlib import Path
import numpy as np
STUDIES=('clean','corrupted');METHODS=('qutcc','im2im')
def decode(path):
 raw=gzip.decompress(path.read_bytes());n=struct.unpack_from('<I',raw)[0];meta=json.loads(raw[4:4+n]);start=4+n;arrays={}
 for d in meta['arrays']:
  b=raw[start+d['offset']:start+d['offset']+d['length']];assert hashlib.sha256(b).hexdigest()==d['sha256']
  if d['encoding']=='uint8':a=np.frombuffer(b,dtype=np.uint8).reshape(d['shape']).astype(np.float32)/255
  else:a=np.frombuffer(b,dtype=np.uint8).reshape(4,-1).T.copy().view('<f4').reshape(d['shape'])
  assert np.isfinite(a).all();arrays[d['name']]=a
 return meta,arrays

def build(assets,dest):
 data={'studies':{},'metric_clipping':'[0,1]','width_units':'normalized intensity','target_alpha':.1,'generated_from':'immutable milestone checkpoints and disjoint 3000/2000 calibration/test splits'}
 for study in STUDIES:
  data['studies'][study]={};summaries={m:json.loads((assets/'exports'/study/m/'summary.json').read_text()) for m in METHODS}
  for m,s in summaries.items():
   assert s['test_count']==2000 and s['calibration_count']==3000 and s['epoch']==(50 if study=='clean' else 10)
   assert all(np.isfinite(v) for v in s['metrics']['clipped'].values())
   assert s['config']['counts']=={'train':17999,'val':2000,'test':2000,'calibration':3000}
   reference=assets/'exports/epoch20_reference.json'
   if study=='clean' and m=='qutcc' and reference.exists():
    ref=json.loads(reference.read_text())
    for row in s['evaluations']:
     if row['epoch']==20:
      if ref['calibrated']:row.update(status='complete',metrics=ref['metrics'],calibration=ref['calibration'],rechecked=True)
      else:row['reference']={k:ref[k] for k in ['status','metrics','calibration','calibration_failure','calibration_trace','per_tail_target','test_count']}
   data['studies'][study][m]=s
  count=min(s['example_count'] for s in summaries.values())
  for i in range(count):
   decoded={m:decode(assets/'exports'/study/m/f'example_{i:02d}.bin.gz') for m in METHODS}
   a,b=[decoded[m] for m in METHODS];assert a[0]['id']==b[0]['id']
   for key in ('target','measurement'):assert np.array_equal(a[1][key],b[1][key]),(study,i,key)
   for m,(meta,arrays) in decoded.items():
    assert all(v.shape==(3,270,480) for v in arrays.values())
    assert all(np.all((v>=0)&(v<=1)) for v in arrays.values())
    coverage=np.mean((arrays['target']>=arrays['lower'])&(arrays['target']<=arrays['upper']));width=np.mean(arrays['upper']-arrays['lower']);mae=np.mean(abs(arrays['prediction']-arrays['target']))
    for key,v in [('coverage',coverage),('width',width),('mae',mae)]:assert abs(float(v)-meta['metrics'][key])<2e-6,(study,m,i,key)
  print(study,count,'paired, exact examples verified',flush=True)
 dest.mkdir(parents=True,exist_ok=True);(dest/'data.json').write_text(json.dumps(data,separators=(',',':'))+'\n')
 return data
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('assets',type=Path);p.add_argument('--output',type=Path,default=Path('raw-diffusercam'));a=p.parse_args();build(a.assets,a.output)
