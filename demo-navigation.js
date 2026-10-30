/* Preserve view state when moving between experiment pages. */
(()=>{
 const script=document.currentScript,root=new URL('./',script.src);
 const routes={current:'corrected-epoch50/',brightness:'test-image-intensified-1/',earlier:'corrected-latest/',legacy:'./',raw:'raw-diffusercam/',captures:'named-captures/',videos:'videos-plot/'};
 function sync(){
  const nav=document.querySelector('[data-demo-route="legacy"]')?.closest('nav');
  if(nav&&!nav.querySelector('[data-demo-route="captures"]')){
   const link=document.createElement('a');link.dataset.demoRoute='captures';link.textContent='Named captures';nav.append(link);
  }
  if(nav&&!nav.querySelector('[data-demo-route="videos"]')){
   const link=document.createElement('a');link.dataset.demoRoute='videos';link.textContent='Videos plot';nav.append(link);
  }
  const state=new URLSearchParams(location.search);
  const camera=state.get('camera')||document.getElementById('camera')?.value;
  if(camera==='rml'||camera==='diffuser')state.set('camera',camera);
  for(const a of document.querySelectorAll('[data-demo-route]')){
   const target=new URL(routes[a.dataset.demoRoute],root);
   for(const key of ['camera','ensemble','example','gain','study','capture','bounds'])if(state.has(key))target.searchParams.set(key,state.get(key));
   a.href=target.href;
  }
 }
 window.syncDemoNavigation=sync;
 document.addEventListener('DOMContentLoaded',sync);
 document.addEventListener('click',e=>{if(e.target.closest('[data-demo-route]'))sync()},true);
 window.addEventListener('pageshow',sync);
 window.addEventListener('popstate',sync);
})();
