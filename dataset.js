'use strict';
window.CAMERA=new URLSearchParams(location.search).get('camera')==='diffuser'?'diffuser':'rml';
window.DATA_PATH='data/'+window.CAMERA;
const manifest=document.createElement('script');manifest.src=window.DATA_PATH+'/manifest.js?v=20261011b';manifest.onload=async()=>{window.exampleCategories=await (await fetch('example-categories.json',{cache:'no-store'})).json();const app=document.createElement('script');app.src='app.js?v=20261030scale01';document.body.append(app)};manifest.onerror=()=>{document.getElementById('status').textContent='Could not load this dataset. Please refresh or try the other camera.'};document.body.append(manifest);
