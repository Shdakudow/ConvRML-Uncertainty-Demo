'use strict';
window.CAMERA=new URLSearchParams(location.search).get('camera')==='diffuser'?'diffuser':'rml';
(async()=>{try{
const config=await (await fetch('assets.json',{cache:'no-store'})).json();
window.DATA_PATH=config.base+'/data/'+window.CAMERA;
const response=await fetch(window.DATA_PATH+'/protocol.json');if(!response.ok)throw Error('HTTP '+response.status);
window.DATASET=await response.json();
const curvesResponse=await fetch('ensemble_curves.json',{cache:'no-store'});
if(curvesResponse.ok){const curves=await curvesResponse.json();DATASET.history.ensemble10=curves.cameras[window.CAMERA]||[];}
else DATASET.history.ensemble10=[];
for(const [file,key] of [['ensemble5_curves.json','ensemble5Curves'],['ensemble_comparison.json','ensembleComparison'],['interval_curves.json','intervalCurves']]){const res=await fetch(file,{cache:'no-store'});if(res.ok)window[key]=await res.json();}
DATASET.history.ensemble5=window.ensemble5Curves?.cameras[window.CAMERA]||[];
if(window.CAMERA==='diffuser'){
 const result=await fetch('normalized_qutcc_results.json',{cache:'no-store'});
 if(!result.ok)throw Error('Normalized QUTCC results HTTP '+result.status);
 window.paperStyleQutcc=await result.json();
 DATASET.history.paper_qutcc=window.paperStyleQutcc.validation;
}
const app=document.createElement('script');app.src='app.js?v=inlinecurves20261019';document.body.append(app);
}catch(e){document.getElementById('status').textContent='Inference export is not yet published: '+e.message;}})();
