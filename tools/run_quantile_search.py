"""Compare learned-q intervals against fixed-q scaling with frozen epoch-25 weights."""
import argparse,json,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
import torch
from torchmetrics.functional.image import structural_similarity_index_measure as ssim
from scripts.corrected_comparison_study import load_model,paths,write
from scripts.formal_rml_train import Pairs
from scripts.quantile_search_calibration import LOWER_GRID,UPPER_GRID,select_pair,select_fixed_sequence
from scripts.training_records import manifest_digest

@torch.inference_mode()
def main():
    p=argparse.ArgumentParser();p.add_argument('--camera',choices=['rml','diffuser'],required=True);p.add_argument('--epoch',type=int,default=25)
    p.add_argument('--policy',choices=['simultaneous','fixed_sequence'],default='simultaneous');a=p.parse_args()
    base=Path(f'results/quantile_search_epoch{a.epoch}_20261011')/a.camera
    out=base if a.policy=='simultaneous' else base/'fixed_sequence';out.mkdir(parents=True,exist_ok=True)
    if (out/'report.json').exists():print('Already complete');return
    torch.set_num_threads(2);torch.manual_seed(20261011)
    model,ck=load_model(a.camera,'conditioned',a.epoch);model.cuda().eval()
    data,caldir=paths(a.camera);cal=np.load(caldir/'pairs.npy',mmap_mode='r')
    baseline=json.loads((Path(f'results/corrected_demo_epoch{a.epoch}_20261011')/a.camera/'conditioned/report.json').read_text())
    assert baseline['manifest_sha256']==manifest_digest(data) and baseline['calibration_sha256']==manifest_digest(caldir)
    factors=baseline['factors']['rcps_hb'];qs=np.concatenate([LOWER_GRID,UPPER_GRID]);k=len(LOWER_GRID)
    def query(y,q):
        with torch.autocast('cuda',dtype=torch.bfloat16):z=model(y,torch.full((len(y),),float(q),device='cuda'))
        z=z.float()
        if not torch.isfinite(z).all():raise ValueError('Nonfinite quantile output')
        return z
    t=time.monotonic()
    losses=np.zeros((len(cal),len(qs)),dtype=np.float64);means=np.zeros_like(losses);anchors=np.zeros_like(losses)
    scanfile=base/'calibration_scan.npz'
    if scanfile.exists():
        saved=np.load(scanfile);assert np.array_equal(saved['qs'],qs)
        losses,means,anchors=saved['losses'],saved['means'],saved['anchors']
    else:
        for i in range(0,len(cal),4):
            b=torch.from_numpy(np.array(cal[i:i+4],copy=True)).cuda().float()/255;y,x=b[:,0],b[:,1];median=query(y,.5).clamp(0,1)
            for j,q in enumerate(qs):
                raw=query(y,q).clamp(0,1)
                bound=torch.minimum(raw,median) if j<k else torch.maximum(raw,median)
                missed=x<bound if j<k else x>bound
                losses[i:i+len(x),j]=missed.float().mean((1,2,3)).cpu().numpy()
                means[i:i+len(x),j]=bound.mean((1,2,3)).cpu().numpy()
                anchors[i:i+len(x),j]=(raw!=bound).float().mean((1,2,3)).cpu().numpy()
            if i%128==0:print(a.camera,'quantile calibration',i,'/',len(cal),flush=True)
        np.savez_compressed(scanfile,qs=qs,losses=losses,means=means,anchors=anchors)
    selector=select_pair if a.policy=='simultaneous' else select_fixed_sequence
    selected=selector(losses[:,:k],losses[:,k:],means[:,:k].mean(0),means[:,k:].mean(0))
    selected.update(lower_grid=LOWER_GRID.tolist(),upper_grid=UPPER_GRID.tolist(),
        lower_empirical_risks=losses[:,:k].mean(0).tolist(),upper_empirical_risks=losses[:,k:].mean(0).tolist(),
        lower_means=means[:,:k].mean(0).tolist(),upper_means=means[:,k:].mean(0).tolist(),
        median_anchoring_fraction=anchors.mean(0).tolist())
    write(out/'selection.json',selected);cal_seconds=time.monotonic()-t
    print('SELECTED',a.camera,json.dumps(selected),flush=True)
    test=Pairs('test',data);ids=[r['id'] for r in json.loads((data/'manifest.json').read_text())['test']]
    rows=[];arrays={z:[] for z in ['measurement','target','prediction','lower','upper']};t=time.monotonic()
    for i in range(0,len(test),4):
        b=torch.stack([test[j] for j in range(i,min(i+4,len(test)))]);y,x=b[:,0].cuda(),b[:,1].cuda()
        r=query(y,.5);pred=r.clamp(0,1);rawlo=query(y,selected['lower_q']);rawhi=query(y,selected['upper_q'])
        lower=torch.minimum(rawlo,r).clamp(0,1);upper=torch.maximum(rawhi,r).clamp(0,1)
        oldlo=query(y,.05);oldhi=query(y,.95)
        fixedlo=(r-factors['lower']*(r-oldlo).clamp_min(1e-6)).clamp(0,1)
        fixedhi=(r+factors['upper']*(oldhi-r).clamp_min(1e-6)).clamp(0,1)
        error=pred-x;psnr=-10*error.square().mean((1,2,3)).clamp_min(1e-12).log10()
        similarity=ssim(pred,x,data_range=1.,reduction='none')
        metrics={name:dict(coverage=((x>=lo)&(x<=hi)).float().mean((1,2,3)),width=(hi-lo).mean((1,2,3))) for name,lo,hi in [('searched',lower,upper),('scaled',fixedlo,fixedhi)]}
        for j in range(len(x)):
            row=dict(id=ids[i+j],psnr=float(psnr[j]),ssim=float(similarity[j]),mae=float(error[j].abs().mean()),
                native_crossing=float((rawlo[j]>rawhi[j]).float().mean()))
            for name,values in metrics.items():row.update({name+'_'+key:float(v[j]) for key,v in values.items()})
            rows.append(row)
            if i+j<50:
                for key,v in zip(arrays,[b[:,0],x,pred,lower,upper]):arrays[key].append(v[j].cpu().numpy())
        if i%512==0:print(a.camera,'test',i,'/',len(test),flush=True)
    np.savez_compressed(out/'examples.npz',**{z:np.stack(v) for z,v in arrays.items()})
    keys=[z for z in rows[0] if z!='id']
    def aggregate(rs):return {z:float(np.mean([r[z] for r in rs])) for z in keys}
    result=dict(camera=a.camera,epoch=a.epoch,model='conditioned',selection=selected,
        calibration_count=len(cal),test_count=len(test),demo_count=50,alpha=.1,delta=.05,
        manifest_sha256=manifest_digest(data),calibration_sha256=manifest_digest(caldir),
        calibration_seconds=cal_seconds,test_seconds=time.monotonic()-t,gpu=torch.cuda.get_device_name(),
        fixed_scale_factors=factors,aggregate=aggregate(rows),demo_aggregate=aggregate(rows[:50]),per_image=rows,
        endpoint_policy='Clipped quantile predictions anchored to the median: LB=min(Q(q_lower),Q(.5)), UB=max(Q(q_upper),Q(.5)); no interval multiplication. Global q pair per camera, spatially varying predicted bounds.',
        selection_policy=selected['policy'],search_policy=a.policy,
        limitation='Finite-grid search, not a continuous global optimum. Simultaneous search has an additional multiplicity penalty; fixed-sequence stops at the first failed tail test. Guarantees require independent calibration images and matching calibration/test distribution. Weights unchanged; median reconstruction unchanged.')
    write(out/'report.json',result);print('COMPLETE',a.camera,json.dumps(result['aggregate']),flush=True)

if __name__=='__main__':main()
