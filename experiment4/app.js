/* Display only completed, verified results. Uncertainty is loaded on expansion. */
(() => {
  'use strict';
  const arms = ['qutcc_clean50','qutcc_general100','im2im_clean50','im2im_general100'];
  const labels = {qutcc_clean50:'QUTCC · clean · 50 epochs',qutcc_general100:'QUTCC · generalized · 100 epochs',im2im_clean50:'Im2im · clean · 50 epochs',im2im_general100:'Im2im · generalized · 100 epochs'};
  const metrics = [['psnr','PSNR (dB)'],['ssim','SSIM'],['mae','MAE'],['coverage','Coverage'],['width','Width'],['crossing','Crossing']];
  let data, errorData, index = 0;
  const cards = new Map();
  const el = (tag, text, className) => {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    if (className) node.className = className;
    return node;
  };
  const asset = path => new URL(path, new URL(data.base, location.href)).href;
  const number = (key, value) => {
    if (!Number.isFinite(value)) return '—';
    return key === 'coverage' || key === 'crossing' ? `${(100*value).toFixed(2)}%` : value.toFixed(key === 'psnr' ? 2 : 4);
  };
  function figure(label, kind, arm) {
    const node = el('figure');
    node.append(el('figcaption', label));
    const image = el('img');
    image.alt = label;
    image.width = 480; image.height = 270; image.loading = 'lazy'; image.decoding = 'async';
    image.dataset.kind = kind;
    if (arm) image.dataset.arm = arm;
    image.addEventListener('error', () => { image.alt = `${label} · image unavailable`; });
    node.append(image);
    return node;
  }
  function pairs(kind = 'prediction') {
    const grid = el('div', undefined, `model-grid${kind === 'width' ? ' maps' : kind === 'error' ? ' errors' : ''}`);
    for (const method of ['qutcc','im2im']) {
      const pair = el('div', undefined, 'pair');
      pair.append(el('h3', method === 'qutcc' ? 'QUTCC' : 'Im2im'));
      const images = el('div', undefined, 'pair-images');
      images.append(figure('Clean-trained · 50 epochs', kind, `${method}_clean50`));
      images.append(figure('Generalized · 100 epochs', kind, `${method}_general100`));
      pair.append(images); grid.append(pair);
    }
    return grid;
  }
  function table(condition, mean) {
    const wrapper = el('div', undefined, 'table-scroll');
    const t = el('table');
    t.setAttribute('aria-label', `${condition.title}: ${mean ? 'all test scenes' : 'selected scene'} metrics`);
    const head = el('thead'), tr = el('tr');
    tr.append(el('th','Model'));
    for (const [, label] of metrics) tr.append(el('th',label));
    head.append(tr); t.append(head);
    const body = el('tbody');
    for (const arm of arms) {
      const row = el('tr'); row.append(el('th', labels[arm]));
      const results = data.results[condition.id].arms[arm];
      const values = mean ? results.mean : results.examples[index];
      for (const [key] of metrics) row.append(el('td', number(key, values[key])));
      body.append(row);
    }
    t.append(body); wrapper.append(t); return wrapper;
  }
  function fillDetails(card, condition) {
    const details = card.querySelector('details');
    if (!details.open) return;
    const content = details.querySelector('.detail-content'); content.replaceChildren();
    content.append(pairs('width'));
    const legend = el('div', undefined, 'legend');
    legend.append(el('span','Narrow 0'), el('span',undefined,'gradient'), el('span','Wide 1'), el('span','Pink = crossed bounds','pink'));
    content.append(legend, el('p','Mean RGB interval width; the same color scale is used for every model and scene.','caption'));
    content.append(el('h4',`Selected scene · ${data.ids[index]}`,'table-title'), table(condition,false));
    content.append(el('h4','Mean across all 2,000 test scenes','table-title'), table(condition,true));
    content.append(el('h4','Calibration on the shared 3,000-scene mixture','table-title'));
    const list = el('ul',undefined,'calibration');
    for (const arm of arms) {
      const fit = data.calibration[arm];
      const failed = fit.status !== 'fitted' || !fit.target_met;
      const text = `${labels[arm]}: ${(100*fit.calibration_coverage).toFixed(2)}% overall coverage${failed ? ` · ${fit.failure || '90% target not met'}` : ''}.`;
      list.append(el('li',text,failed ? 'failed' : ''));
    }
    content.append(list);
    loadImages(card, condition, true);
  }
  function loadImages(card, condition, includeWidth = false) {
    const stem = String(index).padStart(3,'0');
    for (const image of card.querySelectorAll('img')) {
      const kind = image.dataset.kind;
      if (kind === 'width' && !includeWidth) continue;
      let path;
      if (kind === 'original' || kind === 'target') path = `images/shared/${stem}-${kind}.png`;
      else if (kind === 'input') path = condition.id === 'clean' ? `images/shared/${stem}-original.png` : `images/${condition.id}/${stem}-input.png`;
      else path = `images/${condition.id}/${image.dataset.arm}/${stem}-${kind}.png`;
      if (kind === 'error') {
        path = `errors/${condition.id}/${image.dataset.arm}/${stem}.png`;
        image.src = new URL(path, new URL(errorData.base, location.href)).href;
      } else image.src = asset(path);
    }
  }
  function buildCard(condition) {
    const card = el('section',undefined,`condition${condition.id === 'clean' ? ' reference' : ''}`);
    card.id = condition.id;
    card.append(el('h2',condition.title), el('p',condition.description,'explanation'));
    const inputs = el('div',undefined,'inputs');
    inputs.append(figure('Original sensor input','original'),figure(condition.id === 'clean' ? 'Unchanged input' : 'Modified sensor input','input'),figure('Target scene','target'));
    card.append(inputs, el('code',condition.formula,'formula'), pairs());
    card.append(el('h3','Absolute reconstruction error','error-title'), pairs('error'));
    const errorLegend = el('div', undefined, 'legend');
    errorLegend.append(el('span','Low error 0'), el('span',undefined,'gradient'), el('span','High error 1'));
    card.append(errorLegend, el('p','Mean RGB |reconstruction − ground truth|, computed before display quantization. The same 0–1 scale is used for every model and condition.','caption'));
    const details = el('details'), summary = el('summary');
    summary.append(el('span','⬇️','arrow'),document.createTextNode('Uncertainty maps and metrics'));
    details.append(summary,el('div',undefined,'detail-content'));
    details.addEventListener('toggle', () => fillDetails(card,condition));
    card.append(details); cards.set(condition.id,card); return card;
  }
  function render() {
    document.getElementById('scene').value = String(index);
    document.getElementById('counter').textContent = `${index+1} / ${data.ids.length}`;
    document.getElementById('previous').disabled = index === 0;
    document.getElementById('next').disabled = index === data.ids.length-1;
    for (const condition of data.conditions) {
      const card = cards.get(condition.id);
      loadImages(card,condition);
      fillDetails(card,condition);
    }
    const url = new URL(location.href); url.searchParams.set('example',String(index));
    history.replaceState(null,'',url);
  }
  async function start() {
    const response = await fetch('data.json');
    if (!response.ok) throw new Error(`Results could not be loaded (${response.status})`);
    data = await response.json();
    const errorResponse = await fetch('error-maps.json');
    if (!errorResponse.ok) throw new Error('Absolute-error maps could not be loaded');
    errorData = await errorResponse.json();
    if (errorData.schema !== 'exp4_error_maps_v1' || JSON.stringify(errorData.ids) !== JSON.stringify(data.ids)) throw new Error('Absolute-error export does not match these test scenes');
    if (data.schema !== 'experiment4-v1' || data.ids.length !== 50 || data.conditions.length !== 11) throw new Error('Incomplete experiment data');
    index = Math.max(0,Math.min(data.ids.length-1,Number.parseInt(new URLSearchParams(location.search).get('example'),10) || 0));
    const scenes = document.getElementById('scene'), conditions = document.getElementById('condition');
    data.ids.forEach((id,i) => { const option = el('option',`${i+1} · ${id}`); option.value = String(i); scenes.append(option); });
    for (const condition of data.conditions) {
      const option = el('option',condition.title); option.value = condition.id; conditions.append(option);
      document.getElementById('conditions').append(buildCard(condition));
    }
    scenes.addEventListener('change', () => { index=Number(scenes.value); render(); });
    document.getElementById('previous').addEventListener('click', () => { if(index>0){index--;render();} });
    document.getElementById('next').addEventListener('click', () => { if(index<data.ids.length-1){index++;render();} });
    conditions.addEventListener('change', () => document.getElementById(conditions.value).scrollIntoView({behavior:'smooth'}));
    document.getElementById('status').hidden = true;
    document.getElementById('experiment').hidden = false;
    render();
  }
  start().catch(error => { document.getElementById('status').textContent = error.message; });
})();
