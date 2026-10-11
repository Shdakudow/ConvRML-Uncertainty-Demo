"""Replace only QUTCC predictions/bounds with the simultaneously certified minimum-width search."""
import argparse,base64,gzip,json,struct
from pathlib import Path
import numpy as np
BASELINE_COMMIT='115a797a9b5390f710e16cba6f61b77af587f9c5'

def shuffled(a):
 return np.asarray(a,dtype='<f4').reshape(-1).view('uint8').reshape(-1,4).T.copy().tobytes()
def decode(b):
 return np.frombuffer(b,dtype='uint8').reshape(4,-1).T.copy().view('<f4').reshape(3,256,256)
def main():
 p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('--root',type=Path,default=Path('corrected-epoch25'));a=p.parse_args()
 for camera in ['rml','diffuser']:
  src=a.source/camera;primary=json.loads((src/'report.json').read_text());alternative=json.loads((src/'fixed_sequence/report.json').read_text())
  arrays=dict(np.load(src/'examples.npz'));out=a.root/'data'/camera
  meta=json.loads((out/'manifest.js').read_text()[len('window.DATASET='):-1]);protocol=json.loads((out/'protocol.json').read_text())
  assert primary['epoch']==meta['epoch']==25 and primary['manifest_sha256']==meta['manifest_sha256']
  assert primary.get('search_policy','simultaneous')=='simultaneous' and primary['test_count']==5000
  if 'scaled_baseline' not in meta:meta['scaled_baseline']={k:meta[k] for k in ['aggregate','factors','notes']}
  meta['scaled_baseline']['commit']=BASELINE_COMMIT
  # Copy nested objects before modifying the searched variant.
  meta['aggregate']=dict(meta['aggregate']);meta['factors']=dict(meta['factors'])
  max_mean_change=0.
  for i in range(50):
   path=out/f'example_{i:02d}.bin.gz';buffer=gzip.decompress(path.read_bytes());n=struct.unpack('<I',buffer[:4])[0]
   header=json.loads(buffer[4:4+n]);data=buffer[4+n:];obj=header['example'];chunks=[];offset=0
   assert obj['id']==primary['per_image'][i]['id']
   for d in header['arrays']:
    b=data[d['offset']:d['offset']+d['length']]
    if d['path'][:2]==['models','conditioned']:
     key=d['path'][-1];name='prediction' if key=='mean' else key
     if key=='mean':max_mean_change=max(max_mean_change,float(np.max(np.abs(decode(b)-arrays[name][i]))))
     b=shuffled(arrays[name][i]);assert np.array_equal(decode(b),arrays[name][i])
    if d['path']==['target']:assert np.array_equal(np.frombuffer(b,dtype='uint8').reshape(3,256,256),np.rint(arrays['target'][i]*255).astype('uint8'))
    chunks.append(b);d['offset']=offset;d['length']=len(b);offset+=len(b)
   row=primary['per_image'][i]
   obj['models']['conditioned']['metrics']={**{k:row[k] for k in ['id','psnr','ssim','mae','native_crossing']},'coverage':row['searched_coverage'],'width':row['searched_width']}
   h=json.dumps(header,separators=(',',':')).encode();raw=struct.pack('<I',len(h))+h+b''.join(chunks)
   z=gzip.compress(raw,compresslevel=6,mtime=0);assert gzip.decompress(z)==raw;path.write_bytes(z)
  v=primary['demo_aggregate'];meta['aggregate']['conditioned']={**{k:v[k] for k in ['psnr','ssim','mae','native_crossing']},'coverage':v['searched_coverage'],'width':v['searched_width']}
  meta['factors'].pop('conditioned',None)
  widths=(arrays['upper']-arrays['lower']).mean(1)
  meta['mapMax']=max(meta['mapMax'],float(np.quantile(widths.ravel()[::16],.995)))
  meta['q_search']={name:{k:report[k] for k in ['selection','aggregate','demo_aggregate','calibration_count','test_count','endpoint_policy','selection_policy','limitation']} for name,report in [('asymmetric',primary),('fixed_sequence',alternative)]}
  meta['q_search']['maximum_prediction_change']=max_mean_change
  meta['notes']='QUTCC uses calibrated quantile queries with median anchoring; no multiplicative interval scale. The default is minimum-calibration-width asymmetric search with simultaneous HB bounds. Equal-tail fixed-sequence search is reported separately. Other models retain separate lower/upper RCPS scales. 2048 calibration images; 5000-image held-out QUTCC comparison. Display averages use only 50 manifest-ordered examples. Target coverage is 90%, not exactly 90% per image. All metrics and bounds clipped to [0,1].'
  (out/'manifest.js').write_text('window.DATASET='+json.dumps(meta,separators=(',',':'))+';')
  protocol.update(meta);protocol['reports']['conditioned']={k:v for k,v in primary.items() if k!='per_image'}
  (out/'protocol.json').write_text(json.dumps(protocol,indent=2))
  (out/'quantile_search_results.json').write_text(json.dumps({'primary':primary,'asymmetric':alternative},indent=2))
  print(camera,'selected',primary['selection']['lower_q'],primary['selection']['upper_q'],'prediction change',max_mean_change,'full test',primary['aggregate'],flush=True)
if __name__=='__main__':main()
