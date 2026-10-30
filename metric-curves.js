/* Matched fixed-200 LPIPS and unsmoothed uncertainty/error correlations. */
(() => {
  'use strict';
  const root=new URL('./',document.currentScript.src);
  const raw=location.pathname.includes('/raw-diffusercam/');
  const group=raw?'raw_clean':new URLSearchParams(location.search).get('camera')==='diffuser'?'diffuser':'rml';
  const specs=raw?[['qutcc','QUTCC','#63dbce'],['im2im','Im2im','#f2b76a']]:[['im2im','Im2im','#91d9cd'],['ensemble5','Ensemble · 5','#ffcc80'],['mc_005','MC dropout','#72b7ff'],['qutcc','QUTCC','#ff8f70']];
  async function mount() {
    const anchor=document.getElementById(raw?'intervalPlots':'historyPlots');if(!anchor)return;
    const section=document.createElement('section');section.id='metrics200Section';
    section.innerHTML='<h2>LPIPS &amp; uncertainty–error correlation versus epoch</h2><p class="analysis-scope">The same fixed 200 held-out test images at every epoch. Correlations are computed within each image between mean RGB interval width and absolute error, then averaged across images.</p><p id="metrics200Status">Loading fixed-200 evaluations…</p><div id="metrics200Plots" class="learning-plots plots"></div><p><a href="'+new URL('metric_curves200.json',root)+'" download>Download fixed-200 curve data</a></p>';
    anchor.after(section);
    let data;
    try {const response=await fetch(new URL('metric_curves200.json',root),{cache:'no-store'});if(!response.ok)throw new Error(response.status);data=await response.json();}
    catch(error){document.getElementById('metrics200Status').textContent='Fixed-200 evaluations are being prepared.';return;}
    const groups=data.groups[group]||{};
    const measured=specs.reduce((n,[key])=>n+(groups[key]||[]).filter(row=>row.status==='complete').length,0);
    const estimated=specs.reduce((n,[key])=>n+(groups[key]||[]).filter(row=>row.status==='estimated').length,0);
    document.getElementById('metrics200Status').textContent=`${measured} measured milestones${estimated?' · '+estimated+' interpolated estimate (epoch-20 calibration failed)':''} · 200 images per measured point. Hollow diamonds are estimates; they are not successful calibration results.`;
    const target=document.getElementById('metrics200Plots');
    for(const [metric,title] of [['lpips','Mean LPIPS ↓'],['spearman','Mean Spearman ρ ↑'],['pearson','Mean Pearson r ↑']]) {
      const series=specs.map(([key,name,color])=>({key,name,color,rows:(groups[key]||[]).filter(row=>Number.isFinite(row.metrics?.[metric]))}));
      const values=series.flatMap(s=>s.rows.map(r=>r.metrics[metric]));
      const plot=document.createElement('div');plot.className='plot';
      if(!values.length){plot.innerHTML='<h3>'+title+'</h3><p>Evaluation pending.</p>';target.append(plot);continue;}
      const minimum=Math.min(...values),maximum=Math.max(...values),pad=Math.max((maximum-minimum)*.15,.005);
      const lo=Math.max(metric==='lpips'?0:-1,minimum-pad),hi=metric==='lpips'?maximum+pad:Math.min(1,maximum+pad);
      const X=e=>60+(e-5)/45*600,Y=v=>225-(v-lo)/Math.max(hi-lo,.001)*200;
      let svg='<svg viewBox="0 0 700 270" role="img" aria-label="'+title+' versus training epoch">';
      for(let i=0;i<=4;i++){const value=lo+(hi-lo)*i/4;svg+=`<line x1="60" x2="660" y1="${Y(value)}" y2="${Y(value)}" stroke="#33455c"/><text x="52" y="${Y(value)+4}" fill="#bac7d6" font-size="12" text-anchor="end">${value.toFixed(3)}</text>`;}
      for(let epoch=5;epoch<=50;epoch+=5)svg+=`<text x="${X(epoch)}" y="247" fill="#bac7d6" font-size="12" text-anchor="middle">${epoch}</text>`;
      for(const s of series){
        for(let i=0;i<s.rows.length;i++){
          const row=s.rows[i],x=X(row.epoch),y=Y(row.metrics[metric]),prior=s.rows[i-1];
          if(prior&&row.epoch-prior.epoch===5)svg+=`<path d="M${X(prior.epoch)},${Y(prior.metrics[metric])}L${x},${y}" fill="none" stroke="${s.color}" stroke-width="1.6"/>`;
          const text=`${s.name}, epoch ${row.epoch}: ${row.metrics[metric].toFixed(6)}${row.status==='estimated'?' · Interpolated estimate, not measured':''}`;
          svg+=row.status==='estimated'?`<path data-estimated="true" d="M${x},${y-5}l5,5 -5,5 -5,-5 Z" fill="#101722" stroke="${s.color}" stroke-width="2"><title>${text}</title></path>`:`<circle cx="${x}" cy="${y}" r="3.5" fill="${s.color}"><title>${text}</title></circle>`;
        }
      }
      for(let epoch=5;epoch<=50;epoch+=5)svg+=`<rect class="metric-epoch-hit" data-epoch="${epoch}" x="${X(epoch)-25}" y="20" width="50" height="205" fill="transparent" tabindex="0" aria-label="Compare epoch ${epoch}"/>`;
      svg+='<text x="350" y="268" fill="#bac7d6" text-anchor="middle" font-size="12">Training epoch · same 200 test images</text></svg>';
      plot.innerHTML='<h3>'+title+'</h3><div class="legend">'+series.map(s=>`<span style="color:${s.color};margin-right:16px">${s.name}</span>`).join('')+'</div>'+svg+'<div class="metric-curve-tooltip" hidden></div>';
      const tip=plot.querySelector('.metric-curve-tooltip');
      for(const hit of plot.querySelectorAll('.metric-epoch-hit'))hit.onpointerenter=hit.onfocus=()=>{
        const epoch=Number(hit.dataset.epoch);tip.hidden=false;
        tip.innerHTML='<b>Epoch '+epoch+' · 200-image averages</b><table>'+series.map(s=>{const row=s.rows.find(r=>r.epoch===epoch);return `<tr><td style="color:${s.color}">${s.name}</td><td>${row?row.metrics[metric].toFixed(6)+(row.status==='estimated'?' · Interpolated (15/25)':''):'Pending'}</td></tr>`;}).join('')+'</table>';
      };
      plot.onpointerleave=()=>{tip.hidden=true;};target.append(plot);
    }
  }
  document.addEventListener('DOMContentLoaded',mount);
})();
