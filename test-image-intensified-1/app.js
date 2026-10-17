'use strict';
const $=id=>document.getElementById(id);
const specs=[['im2im','Im2im','#91d9cd'],['ensemble5','Ensemble · 5','#ffcc80'],['ensemble10','Ensemble · 10','#c4a5ff'],['mc_005','MC dropout','#72b7ff']];
let report=null,selected=4,camera=new URLSearchParams(location.search).get('camera')==='diffuser'?'diffuser':'rml';
$('camera').value=camera;$('camera').onchange=e=>{location.search='?camera='+e.target.value};
const pct=x=>(x>=0?'+':'')+x.toFixed(2)+'%';
function draw(){
 const row=report.rows[selected],base='data/'+camera+'/';
 $('results').hidden=false;$('status').textContent=`Test image 1 · scene ${report.image_id} · epoch 50 · measurement gain ${row.gain}× · ${(100*row.saturated_fraction).toFixed(2)}% of input channel values at the upper limit`;
 $('gains').innerHTML=report.rows.map((r,i)=>`<button data-index="${i}" aria-pressed="${i===selected}">${r.gain}×${r.gain===1?' · original':''}</button>`).join('');
 for(const button of $('gains').querySelectorAll('button'))button.onclick=()=>{selected=Number(button.dataset.index);draw()};
 $('difficulty').textContent=`${row.difficulty} · Average reconstruction MAE ${row.average_mae.toFixed(6)} (${pct(100*(row.relative_mae-1))} versus original).`;
 $('difficulty').classList.toggle('hard',row.difficulty==='Harder than original');
 $('original').src=base+'original-measurement.png';$('measurement').src=base+`measurement-${selected}.png`;$('truth').src=base+'ground-truth.png';$('measurementLabel').textContent=`${row.label} measurement · ${row.gain}×`;
 $('scale').textContent=`Shared map scale: 0 → ${report.heatmap_max.toFixed(6)} normalized intensity`;
 let html='<div></div>'+specs.map(([k,n])=>`<div class="head"><b>${n}</b><small>Epoch 50</small><span class="badge">${row.gain===1?'Reference':row.models[k].harder?'Harder for this model':'No >10% error increase'}</span></div>`).join('');
 for(const [key,label] of [['prediction','Reconstruction'],['error','|GT − prediction|'],['width','Uncertainty: UB − LB']])html+=`<div class="row-label">${label}</div>`+specs.map(([k,n])=>`<img src="${base}${k}-${selected}-${key}.png" alt="${n}, ${label}, gain ${row.gain}">`).join('');
 $('matrix').innerHTML=html;
 $('metrics').innerHTML=specs.map(([k,n])=>{const v=row.models[k];return `<tr><td>${n}</td><td>${v.psnr.toFixed(4)}</td><td>${v.ssim.toFixed(6)}</td><td>${v.mae.toFixed(6)}</td><td>${v.width.toFixed(6)}</td><td>${(100*v.coverage).toFixed(3)}%</td><td>${pct(v.mae_change_percent)}</td><td>${pct(v.width_change_percent)}</td></tr>`}).join('');
 $('allValues').innerHTML=report.rows.map(r=>specs.map(([k,n])=>{const v=r.models[k];return `<tr><td>${r.gain}×</td><td>${n}</td><td>${v.mae.toFixed(6)}</td><td>${v.width.toFixed(6)}</td><td>${(100*v.coverage).toFixed(3)}%</td><td>${v.ssim.toFixed(6)}</td></tr>`}).join('')).join('');
 $('charts').innerHTML=['mae','width','coverage'].map(metric=>{
  const factor=metric==='coverage'?100:1,values=report.rows.flatMap(r=>specs.map(([k])=>r.models[k][metric]*factor));
  const mn=Math.min(...values),mx=Math.max(...values),pad=Math.max((mx-mn)*.15,metric==='coverage'?.1:.0001),lo=Math.max(0,mn-pad),hi=mx+pad;
  const X=g=>55+(g-.5)*270,Y=v=>175-(v-lo)/(hi-lo)*135,title={mae:'Reconstruction MAE',width:'Mean interval width',coverage:'Actual coverage (%)'}[metric];
  return `<div class="chart"><h3>${title}</h3><svg viewBox="0 0 350 220" aria-label="${title} versus gain" role="img"><path d="M55 35V175H330" fill="none" stroke="#a4b4c4"/>${[lo,(lo+hi)/2,hi].map(v=>`<text x="0" y="${Y(v)}" fill="#a4b4c4" font-size="10">${v.toFixed(metric==='coverage'?1:4)}</text>`).join('')}${report.rows.map(r=>`<text x="${X(r.gain)-10}" y="195" fill="#a4b4c4" font-size="10">${r.gain}×</text>`).join('')}${specs.map(([k,n,c])=>`<polyline points="${report.rows.map(r=>`${X(r.gain)},${Y(r.models[k][metric]*factor)}`).join(' ')}" fill="none" stroke="${c}" stroke-width="2"/>${report.rows.map(r=>`<circle cx="${X(r.gain)}" cy="${Y(r.models[k][metric]*factor)}" r="4" fill="${c}"><title>${n}, ${r.gain}×: ${(r.models[k][metric]*factor).toFixed(6)}</title></circle>`).join('')}`).join('')}<text x="120" y="215" fill="#a4b4c4" font-size="10">Measurement brightness gain</text></svg>${specs.map(([,n,c])=>`<span class="legend" style="color:${c}">${n}</span>`).join('')}</div>`;
 }).join('');
}
(async()=>{try{const response=await fetch('data/'+camera+'/report.json',{cache:'no-store'});if(!response.ok)throw Error('pending');report=await response.json();draw()}catch(e){$('status').textContent='Brightness inference is pending for this camera. Results will appear here after publication.';$('difficulty').textContent='No difficulty label is assigned until reconstruction errors have been measured.'}})();
