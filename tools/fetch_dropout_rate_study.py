"""Export the existing Unicorn validation sweep and matched saved test examples.

Read-only on Unicorn. No training, checkpoint changes, or new model selection.
"""

import io
from pathlib import Path
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[1]
REMOTE = r'''
import io, json, tarfile
from pathlib import Path
import numpy as np
from PIL import Image
from matplotlib import colormaps
root=Path('/home/jy2228/ConvRML/results')
payload={}
study={'epoch':50,'validation_count':5000,'cameras':{},'example_count':8,
 'example_protocol':'First eight saved test images in manifest order; 30 stochastic passes, clipped [0,1]. No quality filtering. p=0.20 example arrays were not saved. Width maps use the existing per-model asymmetric RCPS calibration, alpha=0.10 and delta=0.05.',
 'trend_protocol':'Each dropout rate was trained for 50 epochs. Validation uses 5000 images and dropout active at 30, 60 and 100 passes. Selection maximizes validation SSIM at 100 passes; test data were not used. Curves are a single trained run per rate, not repeated-seed confidence intervals.'}
def rgb(a): return np.round(np.clip(a.transpose(1,2,0),0,1)*255).astype('uint8')
def png(name,a):
 b=io.BytesIO(); Image.fromarray(a).save(b,format='PNG'); payload[name]=b.getvalue()
for camera in ['rml','diffuser']:
 base=root/'corrected_comparison_20261006'/camera
 reports=[]
 for arm in ['mc_005','mc_010','mc_020']:
  report=json.loads((base/'dropout_validation'/f'{arm}.json').read_text())
  assert report['epoch']==50 and report['validation_count']==5000 and not report['test_used']
  reports.append(report)
  payload[f'sources/{camera}_{arm}.json']=json.dumps(report,indent=2).encode()
 policy=json.loads((base/'dropout_policy.json').read_text())
 assert policy['arm']=='mc_005' and len({r['manifest_sha256'] for r in reports})==1
 arrays={}; saved={}
 for arm in ['mc_005','mc_010']:
  path=root/'corrected_demo_epoch50_20261011'/camera/arm
  saved[arm]=json.loads((path/'report.json').read_text())
  with np.load(path/'examples.npz') as z:
   arrays[arm]={k:z[k][:8] for k in ['measurement','target','prediction','lower','upper']}
 assert [r['id'] for r in saved['mc_005']['per_image'][:8]]==[r['id'] for r in saved['mc_010']['per_image'][:8]]
 for key in ['target','measurement']:
  assert np.array_equal(arrays['mc_005'][key],arrays['mc_010'][key])
 maps={arm:{'error':np.abs(a['prediction']-a['target']).mean(1),
             'width':(a['upper']-a['lower']).mean(1)} for arm,a in arrays.items()}
 scale=float(np.percentile(np.concatenate([v.ravel() for m in maps.values() for v in m.values()]),99.5))
 examples=[]
 for i in range(8):
  prefix=f'images/{camera}/{i:02d}'
  example={'id':saved['mc_005']['per_image'][i]['id'],'models':{}}
  for key in ['measurement','target']:
   name=f'{prefix}_{key}.png'; png(name,rgb(arrays['mc_005'][key][i])); example[key]=name
  for arm,a in arrays.items():
   name=f'{prefix}_{arm}_prediction.png'; png(name,rgb(a['prediction'][i]))
   entry={'prediction':name,'metrics':saved[arm]['per_image'][i]}
   for key in ['error','width']:
    name=f'{prefix}_{arm}_{key}.png'
    png(name,np.round(colormaps['magma'](np.clip(maps[arm][key][i]/max(scale,1e-9),0,1))[...,:3]*255).astype('uint8'))
    entry[key]=name
   example['models'][arm]=entry
  examples.append(example)
 study['cameras'][camera]={'rates':reports,'selected_p':policy['dropout_probability'],
  'selection':policy['selection'],'map_max':scale,'examples':examples,
  'example_factors':{arm:saved[arm]['factors']['rcps_hb'] for arm in saved}}
payload['data.json']=json.dumps(study,indent=2).encode()
with tarfile.open(fileobj=__import__('sys').stdout.buffer,mode='w|gz') as tar:
 for name,data in payload.items():
  item=tarfile.TarInfo(name); item.size=len(data); tar.addfile(item,io.BytesIO(data))
'''


def main():
    result = subprocess.run(
        [
            "ssh", "-i", str(Path.home() / ".ssh/id_ed25519"),
            "-o", "BatchMode=yes", "-o", "ConnectTimeout=15",
            "jy2228@unicorn-login-02.coecis.cornell.edu",
            "/home/jy2228/.conda/envs/convrml/bin/python -",
        ],
        input=REMOTE.encode(), capture_output=True, check=True,
    )
    destination = ROOT / "corrected-epoch50/dropout-study"
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(result.stdout), mode="r:gz") as archive:
        for member in archive:
            path = destination / member.name
            if not path.resolve().is_relative_to(destination.resolve()) or not member.isfile():
                raise ValueError("Unexpected archive entry")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(archive.extractfile(member).read())
    print(f"Exported existing sweep and eight matched examples per camera to {destination}")


if __name__ == "__main__":
    main()
