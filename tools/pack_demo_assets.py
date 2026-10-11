"""Lossless binary packaging of existing JSONP example exports for static hosting."""
import base64,gzip,json,struct
from pathlib import Path
import numpy as np

def pack(root):
 for camera in ['rml','diffuser']:
  data=root/'data'/camera
  mp=data/'manifest.js'
  if not mp.exists():continue
  meta=json.loads(mp.read_text()[len('window.DATASET='):-1]);shuffle=meta['encoding']=='float32'
  for p in sorted(data.glob('example_*.js.gz')):
   raw=gzip.decompress(p.read_bytes()).decode();obj=json.loads(raw[raw.index(',')+1:-2]);chunks=[];desc=[];offset=0
   def take(d,k,path):
    nonlocal offset
    b=base64.b64decode(d.pop(k));before=b
    if path and shuffle:
     b=np.frombuffer(b,dtype='uint8').reshape(-1,4).T.copy().tobytes()
     assert np.frombuffer(b,dtype='uint8').reshape(4,-1).T.copy().tobytes()==before
    chunks.append(b);desc.append(dict(path=path+[k],offset=offset,length=len(b)));offset+=len(b)
   for k in ['measurement','target']:take(obj,k,[])
   for m,v in obj['models'].items():
    for k in list(v):
     if isinstance(v[k],str):take(v,k,['models',m])
   h=json.dumps(dict(example=obj,arrays=desc),separators=(',',':')).encode()
   b=struct.pack('<I',len(h))+h+b''.join(chunks);z=gzip.compress(b,compresslevel=6,mtime=0)
   assert gzip.decompress(z)==b
   dest=p.with_name(p.name.replace('.js.gz','.bin.gz'));dest.write_bytes(z);p.unlink()
  meta['encoding']='float32-shuffled';mp.write_text('window.DATASET='+json.dumps(meta,separators=(',',':'))+';')
  protocol=data/'protocol.json'
  if protocol.exists():
   r=json.loads(protocol.read_text());r['encoding']='float32-shuffled';protocol.write_text(json.dumps(r,indent=2))
  print('Packed',data,flush=True)
if __name__=='__main__':
 import sys
 for path in sys.argv[1:]:pack(Path(path))
