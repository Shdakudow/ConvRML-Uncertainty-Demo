/* Preserve view state when moving between experiment pages. */
(()=>{
 const script=document.currentScript,root=new URL('./',script.src);
 const routes={current:'corrected-epoch50/',brightness:'test-image-intensified-1/',earlier:'corrected-latest/',legacy:'./',raw:'raw-diffusercam/'};
 function sync(){
  const state=new URLSearchParams(location.search);
  const camera=state.get('camera')||document.getElementById('camera')?.value;
  if(camera==='rml'||camera==='diffuser')state.set('camera',camera);
  for(const a of document.querySelectorAll('[data-demo-route]')){
   const target=new URL(routes[a.dataset.demoRoute],root);
   for(const key of ['camera','ensemble','example','gain','study'])if(state.has(key))target.searchParams.set(key,state.get(key));
   a.href=target.href;
  }
 }
 window.syncDemoNavigation=sync;
 document.addEventListener('DOMContentLoaded',sync);
 document.addEventListener('click',e=>{if(e.target.closest('[data-demo-route]'))sync()},true);
 window.addEventListener('pageshow',sync);
 window.addEventListener('popstate',sync);
})();
