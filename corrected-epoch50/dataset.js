'use strict';
window.CAMERA=new URLSearchParams(location.search).get('camera')==='diffuser'?'diffuser':'rml';
(async()=>{try{
const config=await (await fetch('assets.json',{cache:'no-store'})).json();
window.DATA_PATH=config.base+'/data/'+window.CAMERA;
const response=await fetch(window.DATA_PATH+'/protocol.json');if(!response.ok)throw Error('HTTP '+response.status);
window.DATASET=await response.json();
const app=document.createElement('script');app.src='app.js?v=epoch5020261015';document.body.append(app);
}catch(e){document.getElementById('status').textContent='Inference export is not yet published: '+e.message;}})();
