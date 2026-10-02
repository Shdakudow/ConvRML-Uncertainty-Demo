'use strict';
window.CAMERA=new URLSearchParams(location.search).get('camera')==='diffuser'?'diffuser':'rml';
window.DATA_PATH='data/'+window.CAMERA;
const manifest=document.createElement('script');manifest.src=window.DATA_PATH+'/manifest.js';manifest.onload=()=>{const app=document.createElement('script');app.src='app.js';document.body.append(app)};manifest.onerror=()=>{document.getElementById('status').textContent='Could not load this dataset. Please refresh or try the other camera.'};document.body.append(manifest);
