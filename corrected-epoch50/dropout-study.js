/* Saved epoch-50 rate sweep; independent of the main four-model viewer. */
(async function dropoutRateStudy() {
  'use strict';
  const host = document.getElementById('dropoutRateStudy');
  const camera = new URLSearchParams(location.search).get('camera') === 'diffuser' ? 'diffuser' : 'rml';
  const colors = {30: '#73c6ff', 60: '#f5bb65', 100: '#98dc98'};
  const label = {ssim: 'SSIM ↑', psnr: 'PSNR (dB) ↑', mae: 'Absolute error ↓'};
  const format = (key, value) => Number(value).toFixed(key === 'mae' ? 6 : 5);
  const image = (src, alt) => `<img src="dropout-study/${src}?v=20261030scale01" alt="${alt}" width="256" height="256">`;
  try {
    const response = await fetch('dropout-study/data.json', {cache: 'no-store'});
    if (!response.ok) throw Error(`HTTP ${response.status}`);
    const data = await response.json();
    const study = data.cameras[camera];
    host.innerHTML = `
      <h2>MC dropout · rate comparison</h2>
      <p>Epoch 50 · 5,000 validation images · <b>Best tested SSIM: p = 0.05.</b></p>
      <p class="muted">30 / 60 / 100 stochastic passes · hover for values · focused axes.</p>
      <div class="dropout-legend">${Object.keys(colors).map(n => `<span style="color:${colors[n]}">● ${n} passes</span>`).join('')}</div>
      <div class="dropout-plots"></div>
      <label>Exact validation values · passes <select id="dropoutPasses"><option>30</option><option>60</option><option selected>100</option></select></label>
      <div class="table-wrap"><table><thead><tr><th>Dropout p</th><th>SSIM ↑</th><th>PSNR (dB) ↑</th><th>MAE ↓</th></tr></thead><tbody id="dropoutRateValues"></tbody></table></div>
      <details><summary>Protocol &amp; source results</summary><p>${data.trend_protocol}</p><p>Training uses dropout in 36 encoder and 12 decoder sites, with MSE reconstruction loss. Timing is omitted because runs used different GPU models. The main four-model demo retains its 30-pass MC inference.</p><p>${study.rates.map(r => `<a href="dropout-study/sources/${camera}_${r.arm}.json">p = ${r.dropout_probability} source JSON</a>`).join(' · ')} · <a href="dropout-study/data.json">All plot data</a> · <a href="dropout-study/validation_trend.csv">CSV</a></p></details>
      <h3>Matched test examples · p = 0.05 and 0.10</h3>
      <p class="muted">Eight test examples · 30 passes · saved p = 0.05 and 0.10 predictions.</p>
      <div class="dropout-controls"><button id="dropoutPrevious" type="button">← Previous</button><label>Example <select id="dropoutExample"></select></label><button id="dropoutNext" type="button">Next →</button><label><input id="dropoutMaps" type="checkbox"> Show error &amp; uncertainty</label></div>
      <p id="dropoutExampleName" class="muted"></p>
      <div id="dropoutExampleImages" class="dropout-examples"></div>
      <div id="dropoutExampleMaps" hidden></div>
      <p class="muted" id="dropoutMapLegend" hidden>Error = mean RGB |GT − prediction|. Uncertainty = mean RGB (UB − LB), using each model’s saved RCPS bounds. Shared map scale for both rates and all eight examples: 0–${study.map_max.toFixed(5)}; brighter means larger. Values above the limit saturate.</p>`;

    // SVG points support both pointer hover and keyboard focus, with a shared tooltip.
    const plotArea = host.querySelector('.dropout-plots');
    for (const key of Object.keys(label)) {
      const all = study.rates.flatMap(r => Object.values(r.results).map(v => v[key]));
      const min = Math.min(...all), max = Math.max(...all), pad = Math.max((max - min) * .16, 1e-7);
      const low = min - pad, high = max + pad;
      const x = p => 64 + (p - .05) / .15 * 245;
      const y = v => 195 - (v - low) / (high - low) * 160;
      let svg = `<svg viewBox="0 0 350 240" role="img" aria-label="Validation ${label[key]} versus dropout probability"><title>${label[key]} versus dropout probability, epoch 50</title>`;
      for (let i = 0; i < 5; i++) {
        const value = low + (high - low) * i / 4;
        svg += `<line x1="64" x2="309" y1="${y(value)}" y2="${y(value)}" stroke="#334152"/><text x="59" y="${y(value)+4}" text-anchor="end">${value.toFixed(key === 'mae' ? 4 : key === 'psnr' ? 2 : 3)}</text>`;
      }
      for (const passes of [30, 60, 100]) {
        svg += `<polyline fill="none" stroke="${colors[passes]}" stroke-width="2" points="${study.rates.map(r => `${x(r.dropout_probability)},${y(r.results[passes][key])}`).join(' ')}"/>`;
        for (const r of study.rates) {
          svg += `<circle tabindex="0" data-p="${r.dropout_probability}" data-metric="${key}" cx="${x(r.dropout_probability)}" cy="${y(r.results[passes][key])}" r="4" fill="${colors[passes]}" aria-label="p ${r.dropout_probability}, ${passes} passes: ${format(key, r.results[passes][key])}"><title>p=${r.dropout_probability}, ${passes} passes: ${format(key, r.results[passes][key])}</title></circle>`;
        }
      }
      for (const r of study.rates) svg += `<text x="${x(r.dropout_probability)}" y="216" text-anchor="middle">${r.dropout_probability.toFixed(2)}</text>`;
      svg += '<text x="185" y="236" text-anchor="middle">Dropout probability p</text></svg>';
      const panel = document.createElement('figure');
      panel.innerHTML = `<figcaption>${label[key]}</figcaption>${svg}<div class="dropout-tooltip" role="status">Hover a point to compare pass counts.</div>`;
      plotArea.append(panel);
      const tooltip = panel.querySelector('.dropout-tooltip');
      const show = event => {
        const r = study.rates.find(r => r.dropout_probability === Number(event.target.dataset.p));
        tooltip.textContent = `p=${r.dropout_probability} · ` + [30,60,100].map(n => `${n} passes: ${format(key, r.results[n][key])}`).join(' · ');
      };
      panel.querySelectorAll('circle').forEach(circle => {circle.addEventListener('mouseenter', show); circle.addEventListener('focus', show);});
    }
    function values() {
      const passes = host.querySelector('#dropoutPasses').value;
      host.querySelector('#dropoutRateValues').innerHTML = study.rates.map(r => `<tr${r.dropout_probability === study.selected_p ? ' class="dropout-best"' : ''}><td>${r.dropout_probability.toFixed(2)}${r.dropout_probability === study.selected_p ? ' · selected' : ''}</td>${['ssim','psnr','mae'].map(k => `<td>${format(k,r.results[passes][k])}</td>`).join('')}</tr>`).join('');
    }
    host.querySelector('#dropoutPasses').addEventListener('change', values);
    values();
    const select = host.querySelector('#dropoutExample');
    study.examples.forEach((e, i) => select.add(new Option(`${i+1} · ${e.id}`, i)));
    function renderExample() {
      const e = study.examples[Number(select.value)];
      host.querySelector('#dropoutExampleName').textContent = `Test image ${e.id}`;
      const tile = (src, title, subtitle='') => `<figure>${image(src,title)}<figcaption>${title}${subtitle ? `<small>${subtitle}</small>` : ''}</figcaption></figure>`;
      host.querySelector('#dropoutExampleImages').innerHTML = tile(e.measurement, 'Measurement') + tile(e.target, 'Ground truth') + ['mc_005','mc_010'].map(arm => {
        const m = e.models[arm];
        return tile(m.prediction, `p = ${arm === 'mc_005' ? '0.05' : '0.10'}`, `SSIM ${m.metrics.ssim.toFixed(5)} · PSNR ${m.metrics.psnr.toFixed(3)} dB`);
      }).join('');
      host.querySelector('#dropoutExampleMaps').innerHTML = ['error','width'].map(key => `<div class="dropout-map-row">${['mc_005','mc_010'].map(arm => tile(e.models[arm][key], `p = ${arm === 'mc_005' ? '0.05' : '0.10'} · ${key === 'error' ? 'Absolute error' : 'Uncertainty'}`)).join('')}</div>`).join('');
    }
    select.addEventListener('change', renderExample);
    for (const [id, step] of [['dropoutPrevious',-1], ['dropoutNext',1]]) host.querySelector('#'+id).addEventListener('click', () => {select.value = (Number(select.value)+step+study.examples.length)%study.examples.length; renderExample();});
    host.querySelector('#dropoutMaps').addEventListener('change', event => {for (const id of ['dropoutExampleMaps','dropoutMapLegend']) host.querySelector('#'+id).hidden = !event.target.checked;});
    renderExample();
    host.dataset.ready = 'true';
  } catch (error) {
    host.textContent = `Dropout-rate comparison could not load: ${error.message}`;
    host.dataset.error = 'true';
  }
})();
