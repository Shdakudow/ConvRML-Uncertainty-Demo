/* One spatial brightness/width coefficient per frame, computed before encoding. */
window.VideoIntensityPlot = (() => {
  'use strict';
  const methods = ['qutcc', 'im2im'];
  const names = {qutcc: 'QUTCC', im2im: 'Im2im'};
  const colors = {qutcc: '#9ddfd2', im2im: '#f9ba77'};
  const get = id => document.getElementById(id);
  const format = value => Number.isFinite(value) ? value.toFixed(4) : 'undefined';
  let data, selectedId, current = 0, onSeek, frameCount = 0;
  const metric = () => get('intensityMetric').value;
  const rows = method => data?.videos[selectedId]?.models[method].rows;
  let plotWidth = 1000, left = 80, right = 970;
  const x = index => left + (right - left) * index / Math.max(1, frameCount - 1);
  const y = value => 275 - (value + 1) * 126.5;

  function showFrame(index) {
    if (!data?.videos[selectedId]) return;
    const bounded = Math.max(0, Math.min(frameCount - 1, index));
    const cursor = get('intensityCursor');
    if (cursor) {
      cursor.setAttribute('x1', x(bounded));
      cursor.setAttribute('x2', x(bounded));
    }
    const label = metric() === 'spearman' ? 'Spearman ρ' : 'Pearson r';
    const values = methods.map(method => `${names[method]} ${format(rows(method)[bounded][metric()])}`);
    const valid = rows('qutcc')[bounded].valid_pixels;
    const total = rows('qutcc')[bounded].total_pixels;
    get('intensityValues').textContent = `Frame ${bounded + 1} · ${label}: ${values.join(' · ')} · ${valid.toLocaleString()} / ${total.toLocaleString()} valid pixels`;
  }

  function draw() {
    const video = data?.videos[selectedId];
    if (!video) return;
    frameCount = video.frames;
    const svg = get('intensityPlot');
    const small = window.innerWidth <= 650;
    plotWidth = small ? 600 : 1000;
    left = small ? 65 : 80;
    right = plotWidth - (small ? 20 : 30);
    const tickFont = small ? 16 : 12;
    const axisFont = small ? 17 : 13;
    svg.setAttribute('viewBox', `0 0 ${plotWidth} 330`);
    let markup = '';
    for (let tick = 0; tick <= 4; tick++) {
      const value = -1 + tick / 2;
      const frame = Math.round(tick * (frameCount - 1) / 4);
      markup += `<line x1="${left}" x2="${right}" y1="${y(value)}" y2="${y(value)}" stroke="${value === 0 ? '#9aadc2' : '#33455c'}"${value === 0 ? ' stroke-dasharray="5 5"' : ''}/>`;
      markup += `<text x="${left - 10}" y="${y(value) + 4}" text-anchor="end" fill="#bac7d6" font-size="${tickFont}">${value.toFixed(1)}</text>`;
      markup += `<text x="${x(frame)}" y="298" text-anchor="middle" fill="#bac7d6" font-size="${tickFont}">${frame + 1}</text>`;
    }
    for (const method of methods) {
      let path = '', connected = false;
      rows(method).forEach((row, index) => {
        const value = row[metric()];
        if (Number.isFinite(value)) {
          path += `${connected ? 'L' : 'M'}${x(index)},${y(value)}`;
          connected = true;
        } else connected = false;
      });
      markup += `<path data-model="${method}" d="${path}" fill="none" stroke="${colors[method]}" stroke-width="1.5"/>`;
    }
    const label = metric() === 'spearman' ? 'Spearman ρ' : 'Pearson r';
    markup += `<text x="${(left + right) / 2}" y="325" text-anchor="middle" fill="#bac7d6" font-size="${axisFont}">Frame</text><text transform="translate(20,148) rotate(-90)" text-anchor="middle" fill="#bac7d6" font-size="${axisFont}">${label} · brightness vs width</text>`;
    markup += `<line id="intensityCursor" y1="22" y2="275" stroke="#e5edf5" opacity=".6"/><rect id="intensityHit" x="${left}" y="22" width="${right - left}" height="253" fill="transparent"/>`;
    svg.innerHTML = markup;
    const indexAt = event => {
      const point = new DOMPoint(event.clientX, event.clientY).matrixTransform(svg.getScreenCTM().inverse());
      return Math.max(0, Math.min(frameCount - 1, Math.round((point.x - left) / (right - left) * (frameCount - 1))));
    };
    get('intensityHit').onpointermove = event => showFrame(indexAt(event));
    get('intensityHit').onclick = event => onSeek(indexAt(event));
    svg.onpointerleave = () => showFrame(current);
    svg.onkeydown = event => {
      if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return;
      event.preventDefault();
      onSeek(Math.max(0, Math.min(frameCount - 1, current + (event.key === 'ArrowRight' ? 1 : -1))));
    };
    get('intensityCSV').href = `intensity/${selectedId}.csv`;
    get('intensityPNG').href = `intensity/${selectedId}.png`;
    get('intensityMetric').disabled = false;
    showFrame(current);
  }

  function init(options) {
    onSeek = options.onSeek;
    get('intensityMetric').addEventListener('change', draw);
    window.addEventListener('resize', draw);
    fetch('intensity/data.json?v=20261102', {cache: 'no-store'})
      .then(response => {if (!response.ok) throw new Error(response.status); return response.json();})
      .then(value => {
        if (value.schema !== 'video_intensity_correlation_v1') throw new Error('Unknown correlation data');
        data = value;
        draw();
      })
      .catch(() => {get('intensityValues').textContent = 'Brightness–uncertainty analysis unavailable. Reload to retry.';});
  }
  function select(id) {selectedId = id; current = 0; draw();}
  function setFrame(index) {current = index; showFrame(index);}
  return {init, select, setFrame};
})();
