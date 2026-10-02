'use strict';
function renderLearningCurves(){
 const curves=window.LEARNING_CURVES,container=document.getElementById('learningPlots');if(!curves||!container)return;
 const camera=window.CAMERA||'rml',calibration=document.getElementById('curveCalibration').value;
 const rows=curves.rows.filter(r=>r.camera===camera&&r.calibration===calibration);
 const methods=[['fixed','Fixed head','#eac879'],['conditioned','Q-conditioned','#90edc0'],['ensemble','Deep ensemble','#90b9ff'],['mc','MC dropout','#de9bef']];
 document.getElementById('curveLegend').innerHTML=methods.map(([k,label,color])=>`<span style="color:${color}">● ${label}</span>`).join('');
 const epochs=[...new Set(rows.map(r=>r.epoch))].sort((a,b)=>a-b);
 document.getElementById('curveStatus').textContent=`${camera==='rml'?'RML':'DiffuserCam'} · ${calibration==='rcps'?'RCPS (α = 0.10, δ = 0.05)':'Empirical calibration (target 90%)'} · 5,000 test images per checkpoint · epochs ${epochs.join(', ')||'not yet available'}.`;
 const metrics=[['psnr','Reconstruction accuracy · PSNR ↑','dB'],['ssim','Reconstruction accuracy · SSIM ↑','SSIM'],['width','Mean interval width ↓','Normalized intensity'],['coverage','Test coverage','%']];
 container.innerHTML=metrics.map(([metric,title,unit])=>{
  if(!rows.length)return `<article class="plot"><h3>${title}</h3><p>No completed results for this calibration yet.</p></article>`;
  const value=r=>r.metrics[metric]*(metric==='coverage'?100:1),values=rows.map(value);
  let low,high;if(metric==='width'){low=0;high=Math.max(...values)*1.08}else if(metric==='coverage'){low=85;high=100}else{const min=Math.min(...values),max=Math.max(...values),pad=Math.max((max-min)*.12,metric==='ssim'?.002:.1);low=min-pad;high=max+pad}
  const x=e=>68+(e-5)/45*440,y=v=>230-(v-low)/(high-low)*175;
  const format=v=>metric==='ssim'||metric==='width'?v.toFixed(3):v.toFixed(1);
  let svg=`<svg viewBox="0 0 550 285" role="img" aria-label="${title} versus backbone training epoch for ${camera}"><text x="68" y="24" fill="#a4b4c4" font-size="12">${unit}</text>`;
  for(let j=0;j<=4;j++){const v=low+(high-low)*j/4;svg+=`<line x1="68" y1="${y(v)}" x2="508" y2="${y(v)}" stroke="#334152"/><text x="59" y="${y(v)+4}" fill="#a4b4c4" font-size="11" text-anchor="end">${format(v)}</text>`}
  for(let e=5;e<=50;e+=5)svg+=`<text x="${x(e)}" y="251" fill="#a4b4c4" font-size="11" text-anchor="middle">${e}</text>`;
  if(metric==='coverage')svg+=`<line x1="68" y1="${y(90)}" x2="508" y2="${y(90)}" stroke="#e6edf5" stroke-dasharray="5 5"/><text x="506" y="${y(90)-7}" fill="#e6edf5" font-size="10" text-anchor="end">90% target</text>`;
  for(const [key,label,color]of methods){const points=rows.filter(r=>r.method===key).sort((a,b)=>a.epoch-b.epoch);if(points.length>1)svg+=`<polyline points="${points.map(r=>`${x(r.epoch)},${y(value(r))}`).join(' ')}" fill="none" stroke="${color}" stroke-width="2"/>`;for(const r of points){const text=`${label}, epoch ${r.epoch}: ${metric==='ssim'?value(r).toPrecision(5):value(r).toFixed(metric==='width'?5:3)} ${unit}`;svg+=`<circle tabindex="0" cx="${x(r.epoch)}" cy="${y(value(r))}" r="4" fill="${color}" aria-label="${text}"><title>${text}</title></circle>`}}
  svg+='<text x="288" y="276" fill="#a4b4c4" font-size="12" text-anchor="middle">Backbone training epoch</text></svg>';
  return `<article class="plot"><h3>${title}</h3>${svg}</article>`;
 }).join('');
 document.getElementById('curveRows').innerHTML=[...rows].sort((a,b)=>a.epoch-b.epoch||a.method.localeCompare(b.method)).map(r=>`<tr><td>${r.epoch}</td><td>${methods.find(m=>m[0]===r.method)[1]}</td><td>${r.metrics.psnr.toFixed(3)}</td><td>${r.metrics.ssim.toPrecision(5)}</td><td>${r.metrics.width.toFixed(5)}</td><td>${(r.metrics.coverage*100).toFixed(2)}%</td></tr>`).join('');
 document.getElementById('curveCalibration').onchange=renderLearningCurves;
}
