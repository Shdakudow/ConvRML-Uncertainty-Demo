/* Current-image tables and column-wise comparisons for Experiments 2 and 3. */
(() => {
  'use strict';
  const format = value => Number.isFinite(value) ? value.toFixed(5) : 'Unavailable';
  function highlight(table) {
    if (!table?.tHead) return;
    const headers = [...table.tHead.rows[0].cells];
    headers.forEach((header, index) => {
      const label = header.textContent.toLowerCase();
      const direction = /coverage/.test(label) ? 'coverage' : /psnr|ssim|pearson|spearman/.test(label) ? 'max' : /lpips|mae|error|width/.test(label) ? 'min' : null;
      if (!direction) return;
      const cells = [...table.tBodies[0].rows].map(row => row.cells[index]).filter(Boolean);
      cells.forEach(cell => cell.classList.remove('metric-best'));
      const valid = cells.map(cell => ({cell, value: parseFloat(cell.textContent)})).filter(item => Number.isFinite(item.value));
      if (valid.length < 2) return;
      const score = value => direction === 'coverage' ? -Math.abs(value - 90) : direction === 'min' ? -value : value;
      const best = Math.max(...valid.map(item => score(item.value)));
      valid.filter(item => Math.abs(score(item.value) - best) < 0.000005).forEach(({cell}) => {
        cell.classList.add('metric-best');
        cell.title = direction === 'coverage' ? 'Closest to 90% coverage in this comparison' : /width/.test(label) ? 'Smallest interval width; compare coverage separately' : `Best ${header.textContent.trim()} in this column`;
      });
    });
  }
  function renderImage(rows) {
    let section = document.getElementById('selectedImageMetrics');
    if (!section) {
      section = document.createElement('section'); section.id = 'selectedImageMetrics'; section.className = 'selected-image-metrics';
      section.innerHTML = '<h2>This image · metrics</h2><div class="table-wrap"><table><thead><tr><th>Model</th><th>PSNR ↑</th><th>SSIM ↑</th><th>Coverage</th><th>Width ↓</th><th>MAE ↓</th><th>LPIPS ↓</th><th>Pearson r ↑</th><th>Spearman ρ ↑</th></tr></thead><tbody></tbody></table></div>';
      document.getElementById('matrix').after(section);
    }
    const body = section.querySelector('tbody'); body.replaceChildren();
    rows.forEach(({label, metrics}) => {
      const row = document.createElement('tr');
      [label, format(metrics.psnr), format(metrics.ssim), Number.isFinite(metrics.coverage) ? (100 * metrics.coverage).toFixed(3) + '%' : 'Unavailable', ...['width','mae','lpips','pearson','spearman'].map(key => format(metrics[key]))].forEach(value => {const cell = document.createElement('td');cell.textContent=value;row.append(cell);});
      body.append(row);
    });
    highlight(section.querySelector('table'));
    const cards = [...document.querySelectorAll('#matrix .metrics')];
    if (cards[0]?.previousElementSibling?.classList.contains('row-label')) cards[0].previousElementSibling.classList.add('legacy-image-metrics');
    cards.forEach(card => card.classList.add('legacy-image-metrics'));
  }
  function mount() {
    const rawTable = document.getElementById('imageMetrics');
    if (rawTable && !rawTable.closest('.selected-image-metrics')) {
      const wrapper = rawTable.closest('.table-wrap'), title = wrapper.previousElementSibling;
      const section = document.createElement('section');section.className='selected-image-metrics';wrapper.before(section);
      if (title?.textContent.includes('This image')) section.append(title);
      section.append(wrapper);
    }
    for (const id of ['imageMetricRows','aggregateRows']) {
      const body=document.getElementById(id);if(!body)continue;
      const table=body.closest('table');highlight(table);
      new MutationObserver(() => highlight(table)).observe(body,{childList:true,subtree:true});
    }
    const note=document.createElement('p');note.className='metric-ranking-note';note.textContent='Colored cells mark column-best values; coverage is ranked by closeness to 90%. Width alone does not establish better uncertainty.';
    document.getElementById('aggregateRows')?.closest('.table-wrap')?.after(note);
  }
  window.ExperimentUI={renderImage,highlight};
  document.addEventListener('DOMContentLoaded',mount);
})();
