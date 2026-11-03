/* Plot recorded validation and independently evaluated checkpoint intervals. */
(() => {
  'use strict';
  const root = document.getElementById('learningCurves');
  if (!root) return;
  const conditions = document.getElementById('learningConditions');
  const methods = ['qutcc', 'im2im'];
  const palette = ['#b59aff', '#f58cc1', '#c3dc77', '#7ebcff', '#ffd36c', '#a9b4c4', '#ff8c8c', '#76d2df', '#8d9aff', '#d8b495'];
  const metrics = [
    {id: 'ssim', label: 'Validation SSIM', source: 'learning', bounds: [0, 1], decimals: 3},
    {id: 'psnr', label: 'Validation PSNR (dB)', source: 'learning', bounds: [0, 40], decimals: 1},
    {id: 'calibration_width', label: 'Calibration interval width', source: 'intervals', bounds: [0, 1], decimals: 3},
    {id: 'test_coverage', label: 'Test coverage (%)', source: 'intervals', bounds: [0, 1], decimals: 1, percent: true},
  ];
  const compact = matchMedia('(max-width: 720px)');
  const theme = getComputedStyle(document.documentElement);
  const axisColor = theme.getPropertyValue('--muted').trim();
  const gridColor = theme.getPropertyValue('--line').trim();
  let learning, intervals;

  function element(tag, text) {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    return node;
  }
  const selectedConditions = () => [...conditions.querySelectorAll('input:checked')].map(input => input.value);
  const value = (row, condition, metric) => condition === 'average' ? row.mean[metric] : row.conditions[condition][metric];
  const label = condition => condition === 'average' ? 'Average' : learning.conditions.find(item => item.id === condition).label;
  const color = (condition, method) => condition === 'average'
    ? (method === 'qutcc' ? '#9ddfd2' : '#f9ba77')
    : palette[learning.conditions.findIndex(item => item.id === condition)];
  const display = (v, metric) => metric.percent ? `${(100 * v).toFixed(2)}%` : `${v.toFixed(4)}${metric.id === 'psnr' ? ' dB' : ''}`;

  function plot(metric, selected) {
    const source = metric.source === 'learning' ? learning : intervals;
    const svg = document.getElementById('learning-' + metric.id);
    const rows = source ? methods.flatMap(method => source.methods[method].history) : [];
    const values = rows.flatMap(row => selected.map(condition => value(row, condition, metric.id)));
    let [low, high] = metric.bounds;
    if (values.length && document.getElementById('learningZoom').checked) {
      const minimum = Math.min(...values), maximum = Math.max(...values);
      const margin = Math.max((maximum - minimum) * .12, metric.id === 'psnr' ? .25 : .005);
      low = Math.max(metric.bounds[0], minimum - margin);
      high = metric.id === 'psnr' ? maximum + margin : Math.min(metric.bounds[1], maximum + margin);
    } else if (values.length && metric.id === 'psnr') {
      high = Math.max(40, Math.ceil(Math.max(...values) / 10) * 10);
    }
    if (metric.percent) {low = Math.min(low, .89); high = Math.max(high, .91);}

    // A smaller coordinate system keeps tick labels readable on a phone.
    const width = compact.matches ? 360 : 600, height = compact.matches ? 310 : 350;
    const left = 62, right = width - 20, top = 22, bottom = height - 65;
    const x = epoch => left + (epoch - 1) / 99 * (right - left);
    const y = v => bottom - (v - low) / Math.max(.000001, high - low) * (bottom - top);
    const tick = v => (v * (metric.percent ? 100 : 1)).toFixed(metric.decimals);
    svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
    let html = '';
    for (let i = 0; i <= 4; i++) {
      const v = low + i / 4 * (high - low);
      html += `<line x1="${left}" x2="${right}" y1="${y(v)}" y2="${y(v)}" stroke="${gridColor}"/><text x="${left - 9}" y="${y(v) + 4}" text-anchor="end" font-size="14" fill="${axisColor}">${tick(v)}</text>`;
    }
    for (const epoch of [1, 25, 50, 75, 100]) {
      html += `<text x="${x(epoch)}" y="${bottom + 23}" text-anchor="middle" font-size="14" fill="${axisColor}">${epoch}</text>`;
    }
    if (metric.percent && low <= .9 && high >= .9) {
      html += `<line class="coverage-reference" x1="${left}" x2="${right}" y1="${y(.9)}" y2="${y(.9)}" stroke="#eed49f" stroke-dasharray="3 5"/><text x="${right - 3}" y="${y(.9) - 5}" text-anchor="end" fill="#eed49f" font-size="12">90% reference</text>`;
    }
    for (const condition of selected) for (const method of methods) {
      const history = source?.methods[method].history || [];
      const stroke = color(condition, method);
      const dash = method === 'im2im' ? 'stroke-dasharray="7 4"' : '';
      const attributes = `data-condition="${condition}" data-model="${method}" fill="none" stroke="${stroke}" stroke-width="${condition === 'average' ? 2.5 : 1.8}" ${dash}`;
      if (metric.source === 'learning') {
        const points = history.map(row => `${x(row.epoch)},${y(value(row, condition, metric.id))}`).join(' ');
        html += `<polyline ${attributes} points="${points}"/>`;
      } else {
        // Never join across missing evaluations or invent intermediate values.
        const path = history.map((row, index) => `${index && row.epoch - history[index - 1].epoch === 10 ? 'L' : 'M'}${x(row.epoch)},${y(value(row, condition, metric.id))}`).join(' ');
        if (history.length) html += `<path ${attributes} d="${path}"/>`;
        for (const row of history) {
          html += `<circle data-epoch="${row.epoch}" data-condition="${condition}" data-model="${method}" cx="${x(row.epoch)}" cy="${y(value(row, condition, metric.id))}" r="3" fill="${stroke}"><title>${source.methods[method].label} · ${label(condition)} · epoch ${row.epoch}: ${display(value(row, condition, metric.id), metric)}${row.calibration_target_met ? '' : ' · calibration target not met'}</title></circle>`;
        }
      }
    }
    html += `<text x="${(left + right) / 2}" y="${height - 8}" text-anchor="middle" fill="${axisColor}" font-size="15">Training epoch</text><text transform="translate(16,${(top + bottom) / 2}) rotate(-90)" text-anchor="middle" fill="${axisColor}" font-size="14">${metric.label}</text><line id="learning-cursor-${metric.id}" x1="${right}" x2="${right}" y1="${top}" y2="${bottom}" stroke="#879aaa"/><rect class="learning-hit" x="${left}" y="${top}" width="${right - left}" height="${bottom - top}" fill="transparent"/>`;
    svg.innerHTML = html;
    document.getElementById('learning-scale-' + metric.id).textContent = `Scale: ${tick(low)}–${tick(high)}${metric.percent ? '%' : metric.id === 'psnr' ? ' dB' : ''} · epochs 1–100`;

    function show(epoch) {
      const output = document.getElementById('learning-values-' + metric.id);
      const available = [...new Set(rows.map(row => row.epoch))];
      const nearest = available.length ? available.reduce((best, current) => Math.abs(current - epoch) < Math.abs(best - epoch) ? current : best) : epoch;
      const cursor = svg.querySelector('line[id]');
      for (const key of ['x1', 'x2']) cursor.setAttribute(key, x(nearest));
      output.replaceChildren(element('strong', `Epoch ${nearest}`));
      if (!selected.length) {output.append(element('div', 'Select Average or a condition to show a curve.')); return;}
      if (!rows.length) {output.append(element('div', 'Checkpoint evaluations are running. Measured points will appear when verified.')); return;}
      for (const condition of selected) {
        const text = methods.map(method => {
          const row = source.methods[method].history.find(item => item.epoch === nearest);
          return `${source.methods[method].label}: ${row ? display(value(row, condition, metric.id), metric) : 'pending'}`;
        }).join(' · ');
        output.append(element('div', `${label(condition)} · ${text}`));
      }
      for (const method of methods) {
        const row = source.methods[method].history.find(item => item.epoch === nearest);
        if (row && !row.calibration_target_met && metric.source === 'intervals') output.append(element('div', `${source.methods[method].label}: calibration target not met at this epoch.`));
      }
    }
    svg.querySelector('rect').onpointermove = event => {
      const point = new DOMPoint(event.clientX, event.clientY).matrixTransform(svg.getScreenCTM().inverse());
      show(Math.max(1, Math.min(100, Math.round(1 + (point.x - left) / (right - left) * 99))));
    };
    show(100);
  }

  function draw() {for (const metric of metrics) plot(metric, selectedConditions());}

  async function start() {
    try {
      const response = await fetch('learning-data.json');
      if (!response.ok) throw Error(response.status);
      learning = await response.json();
      if (learning.schema !== 'exp4_learning_v1') throw Error('Unknown learning history');
      for (const item of [{id: 'average', label: 'Average'}, ...learning.conditions]) {
        const entry = element('label'), input = element('input');
        input.type = 'checkbox'; input.value = item.id; input.checked = item.id === 'average';
        input.addEventListener('change', draw);
        entry.append(input, document.createTextNode(item.label));
        if (item.id !== 'average') entry.style.setProperty('--condition-color', color(item.id, 'qutcc'));
        conditions.append(entry);
      }
      document.getElementById('learningStatus').textContent = '100 completed training epochs · generalized models · fixed validation panel of 100 scenes × 10 conditions. Exposure combines both gains.';
      document.getElementById('learningZoom').addEventListener('change', draw);
      compact.addEventListener('change', draw);
      draw();
      try {
        const intervalResponse = await fetch('interval-curves.json');
        if (!intervalResponse.ok) throw Error(intervalResponse.status);
        intervals = await intervalResponse.json();
        if (intervals.schema !== 'exp4_interval_curves_v1') throw Error('Unknown interval curves');
        document.getElementById('intervalStatus').textContent = `${intervals.completed} / ${intervals.expected} checkpoint evaluations complete. One calibration per model and epoch targets 90% on the shared calibration mixture. Category and test coverage can differ.`;
        draw();
      } catch (_) {document.getElementById('intervalStatus').textContent = 'Interval-curve data could not be loaded. Reload to retry.';}
    } catch (_) {document.getElementById('learningStatus').textContent = 'Learning curves could not be loaded. Reload to retry.';}
  }
  start();
})();
