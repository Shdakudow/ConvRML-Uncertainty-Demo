/* Recorded validation only; condition selection never changes the scene viewer. */
(() => {
  'use strict';
  const root = document.getElementById('learningCurves');
  const conditions = document.getElementById('learningConditions');
  const methods = ['qutcc','im2im'];
  const colors = ['#007b79','#a24c20','#6b5cbb','#a02d68','#658819','#176ab1','#b46c00','#68727d','#a93e3e','#4a8291'];
  let data;
  const create = (tag,text) => {const e=document.createElement(tag);if(text!==undefined)e.textContent=text;return e;};
  const active = () => [...conditions.querySelectorAll('input:checked')].map(e=>e.value);
  const value = (row,condition,metric) => condition === 'average' ? row.mean[metric] : row.conditions[condition][metric];
  function draw() {
    const selected = active();
    for (const metric of ['ssim','psnr']) {
      const svg=document.getElementById('learning-'+metric), rows=methods.flatMap(m=>data.methods[m].history);
      const values=rows.flatMap(row=>selected.map(condition=>value(row,condition,metric)));
      const minimum=values.length?Math.min(...values):0, maximum=values.length?Math.max(...values):1;
      const margin=Math.max((maximum-minimum)*.08,metric==='ssim'?.01:.25);
      const low=metric==='ssim'?Math.max(0,minimum-margin):minimum-margin, high=metric==='ssim'?Math.min(1,maximum+margin):maximum+margin;
      const x=epoch=>60+(epoch-1)/99*520, y=v=>275-(v-low)/Math.max(.00001,high-low)*250;
      let html='';
      for(let tick=0;tick<=4;tick++) {
        const v=low+tick/4*(high-low),epoch=Math.round(1+tick/4*99);
        html+=`<line x1="60" x2="580" y1="${y(v)}" y2="${y(v)}" stroke="#dce5eb"/><text x="50" y="${y(v)+4}" text-anchor="end" font-size="13" fill="#536779">${v.toFixed(metric==='ssim'?3:1)}</text><text x="${x(epoch)}" y="298" text-anchor="middle" font-size="13" fill="#536779">${epoch}</text>`;
      }
      for(const condition of selected)for(const method of methods) {
        const color=condition==='average'?(method==='qutcc'?'#17697c':'#a24c20'):colors[data.conditions.findIndex(c=>c.id===condition)];
        const path=data.methods[method].history.map(row=>`${x(row.epoch)},${y(value(row,condition,metric))}`).join(' ');
        html+=`<polyline data-condition="${condition}" data-model="${method}" points="${path}" fill="none" stroke="${color}" stroke-width="${condition==='average'?2.5:1.6}" ${method==='im2im'?'stroke-dasharray="7 4"':''}/>`;
      }
      html+=`<text x="320" y="326" text-anchor="middle" fill="#536779" font-size="14">Epoch</text><text transform="translate(17,150) rotate(-90)" text-anchor="middle" fill="#536779" font-size="14">Validation ${metric==='ssim'?'SSIM':'PSNR (dB)'}</text><line id="learning-cursor-${metric}" x1="60" x2="60" y1="25" y2="275" stroke="#879aaa"/><rect class="learning-hit" x="60" y="25" width="520" height="250" fill="transparent"/>`;
      svg.innerHTML=html;
      const show=epoch=>{
        svg.querySelector('line[id]').setAttribute('x1',x(epoch));svg.querySelector('line[id]').setAttribute('x2',x(epoch));
        const output=document.getElementById('learning-values-'+metric);
        output.replaceChildren(create('strong',`Epoch ${epoch}`));
        for(const condition of selected) {
          const name=condition==='average'?'Average':data.conditions.find(c=>c.id===condition).label;
          const line=create('div',name+' · '+methods.map(method=>`${data.methods[method].label}: ${value(data.methods[method].history[epoch-1],condition,metric).toFixed(4)}`).join(' · '));
          output.append(line);
        }
        if(!selected.length)output.append(create('div','Select Average or a condition to show a curve.'));
      };
      svg.querySelector('rect').onpointermove=event=>{const p=new DOMPoint(event.clientX,event.clientY).matrixTransform(svg.getScreenCTM().inverse());show(Math.max(1,Math.min(100,Math.round(1+(p.x-60)/520*99))));};
      show(100);
    }
  }
  async function start() {
    try {
      const response=await fetch('learning-data.json');if(!response.ok)throw Error(response.status);data=await response.json();
      if(data.schema!=='exp4_learning_v1')throw Error('Unknown learning history');
      for(const item of [{id:'average',label:'Average'},...data.conditions]) {
        const label=create('label'),input=create('input');input.type='checkbox';input.value=item.id;input.checked=item.id==='average';input.addEventListener('change',draw);
        label.append(input,document.createTextNode(item.label));if(item.id!=='average'){label.style.borderLeft='3px solid '+colors[data.conditions.findIndex(c=>c.id===item.id)];label.style.paddingLeft='6px';}conditions.append(label);
      }
      document.getElementById('learningStatus').textContent='100 completed epochs · generalized models · fixed 100-scene panel × 10 conditions. Average is shown initially. Solid = QUTCC; dashed = Im2im. Exposure combines both gains.';
      draw();
    } catch (_) {document.getElementById('learningStatus').textContent='Learning curves could not be loaded. Reload to retry.';}
  }
  if(root)start();
})();
