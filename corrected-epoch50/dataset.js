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
const app=document.createElement('script');app.src='app.js?v=ensemble20261015';document.body.append(app);
}catch(e){document.getElementById('status').textContent='Inference export is not yet published: '+e.message;}})();
