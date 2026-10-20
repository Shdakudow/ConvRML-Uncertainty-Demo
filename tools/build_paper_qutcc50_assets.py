"""Package and audit a paper-style QUTCC overlay against the existing 50 examples."""
import gzip,json,struct,argparse
from pathlib import Path
import numpy as np

def main():
 p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('baseline',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
 report=json.loads((a.source/'report.json').read_text());z=np.load(a.source/'examples.npz');a.output.mkdir(parents=True,exist_ok=True)
 assert report['epoch']==50 and report['count']==50
 for i,row in enumerate(report['per_image']):
  old=gzip.decompress((a.baseline/f'example_{i:02d}.bin.gz').read_bytes());size=struct.unpack('<I',old[:4])[0];header=json.loads(old[4:4+size]);body=old[4+size:]
  assert str(row['id'])==str(header['example']['id'])
  chunks=[];desc=[];offset=0
  obj={'id':row['id'],'models':{'paper_qutcc':{'metrics':{k:row[k] for k in ['psnr','ssim','mae','coverage','width']}}}}
  for name in ['measurement','target']:
   value=(z[name][i]*255).round().astype('uint8').tobytes();oldentry=next(t for t in header['arrays'] if t['path']==[name]);assert value==body[oldentry['offset']:oldentry['offset']+oldentry['length']],(i,name)
   chunks.append(value);desc.append(dict(path=[name],offset=offset,length=len(value)));offset+=len(value)
  for dest,source in [('mean','prediction'),('lower','lower'),('upper','upper')]:
   array=np.asarray(z[source][i],dtype='<f4');assert np.isfinite(array).all() and array.min()>=0 and array.max()<=1
   value=np.frombuffer(array.tobytes(),dtype='uint8').reshape(-1,4).T.copy().tobytes();chunks.append(value);desc.append(dict(path=['models','paper_qutcc',dest],offset=offset,length=len(value)));offset+=len(value)
  target=z['target'][i];pred=z['prediction'][i];lo=z['lower'][i];hi=z['upper'][i]
  for key,value in [('psnr',-10*np.log10(np.maximum(np.mean((pred-target)**2),1e-12))),('width',np.mean(hi-lo)),('coverage',np.mean((target>=lo)&(target<=hi)))]:assert abs(value-row[key])<1e-5,(i,key)
  h=json.dumps(dict(example=obj,arrays=desc),separators=(',',':')).encode();(a.output/f'example_{i:02d}.bin.gz').write_bytes(gzip.compress(struct.pack('<I',len(h))+h+b''.join(chunks),compresslevel=6,mtime=0))
 (a.output/'protocol.json').write_text(json.dumps(report,indent=2)+'\n');print('Verified and packed 50 paired examples',a.output)
if __name__=='__main__':main()
