'use strict';
const $ = id => document.getElementById(id);
const methods = ['qutcc', 'im2im'];
const labels = {qutcc: 'QUTCC', im2im: 'Im2im'};
const colors = {qutcc: '#9ddfd2', im2im: '#f9ba77'};
let data, selected, requestToken = 0;
let pixelPoint = null;
const pixelInspector = new HeatmapPixels.Inspector(document.querySelector('.video-grid'));
const number = value => Number(value).toFixed(5);
const videos = () => methods.map(method => $(method + 'Video'));
const showCumulative = () => $('cumulativeToggle').getAttribute('aria-pressed') === 'true';
function pause() { videos().forEach(video => video.pause()); }
function setFrame(index) {
  const bounded = Math.max(0, Math.min(selected.frames - 1, index));
  $('frame').value = bounded + 1;
  $('frameLabel').textContent = `${bounded + 1} / ${selected.frames}`;
}
function seekFrame(index) {
  pause();
  const bounded = Math.max(0, Math.min(selected.frames - 1, index));
  videos().forEach(video => { video.currentTime = bounded / selected.fps; });
  setFrame(bounded);
  if (pixelPoint) inspectFrame(bounded);
}
function inspectFrame(index) {
  for (const video of videos()) HeatmapPixels.mark(video, [
    {x: pixelPoint.x + .5, y: pixelPoint.y + 24.5},
    {x: pixelPoint.x + .5, y: pixelPoint.y + 318.5},
  ], 480, 588);
  pixelInspector.show({...pixelPoint, frame: index + 1, targets: methods.map(method => ({
    element: $(method + 'Video'),
    path: `videos/${selected.id}/${method}/frame_${String(index + 1).padStart(4, '0')}.bin.gz`,
  }))});
}
function clearPixel() {pixelPoint = null; pixelInspector.clear();}
function drawPlot() {
  const svg = $('widthPlot'), left = 70, right = 970, top = 22, bottom = 275;
  const values = methods.flatMap(method => selected.models[method].per_frame.map(row => row.mean_interval_width));
  let minimum = 0, maximum = data.width_plot_range[1];
  if ($('zoom').checked) {
    const low = Math.min(...values), high = Math.max(...values), margin = Math.max((high - low) * .15, .0001);
    minimum = Math.max(0, low - margin); maximum = Math.min(1, high + margin);
  }
  const x = index => left + index / Math.max(1, selected.frames - 1) * (right - left);
  const y = value => bottom - (value - minimum) / (maximum - minimum) * (bottom - top);
  const pieces = [];
  const ticks = $('zoom').checked ? 4 : 5;
  for (let tick = 0; tick <= ticks; tick++) {
    const value = minimum + tick / ticks * (maximum - minimum), position = y(value);
    pieces.push(`<line x1="${left}" y1="${position}" x2="${right}" y2="${position}" stroke="#33455c"/><text x="${left - 9}" y="${position + 4}" text-anchor="end" fill="#bac7d6" font-size="12">${value.toFixed($('zoom').checked ? 4 : 2)}</text>`);
    const index = Math.round(tick / ticks * (selected.frames - 1));
    pieces.push(`<text x="${x(index)}" y="${bottom + 23}" text-anchor="middle" fill="#bac7d6" font-size="12">${index + 1}</text>`);
  }
  methods.forEach(method => {
    const report = selected.models[method], points = report.per_frame.map((row, index) => `${x(index)},${y(row.mean_interval_width)}`).join(' ');
    const cumulative = report.per_frame.map((row, index) => `${x(index)},${y(row.cumulative_mean_interval_width)}`).join(' ');
    pieces.push(`<polyline data-model="${method}" data-series="frame" points="${points}" fill="none" stroke="${colors[method]}" stroke-width="1.1" opacity="${showCumulative() ? '.3' : '.85'}"/>`);
    if (showCumulative()) pieces.push(`<polyline data-model="${method}" data-series="cumulative" points="${cumulative}" fill="none" stroke="${colors[method]}" stroke-width="1.7"/>`);
  });
  pieces.push('<text x="520" y="325" text-anchor="middle" fill="#bac7d6" font-size="13">Frame</text><text transform="translate(16,148) rotate(-90)" text-anchor="middle" fill="#bac7d6" font-size="13">Mean interval width</text>');
  pieces.push('<line id="plotCursor" y1="22" y2="275" stroke="#e5edf5" opacity="0"/><rect id="plotHit" x="70" y="22" width="900" height="253" fill="transparent"/>');
  svg.innerHTML = pieces.join('');
  const frameAtPointer = event => {
    const point = new DOMPoint(event.clientX, event.clientY).matrixTransform(svg.getScreenCTM().inverse());
    return Math.max(0, Math.min(selected.frames - 1, Math.round((point.x - left) / (right - left) * (selected.frames - 1))));
  };
  const showFrame = index => {
    const cursor = $('plotCursor'); cursor.setAttribute('x1', x(index)); cursor.setAttribute('x2', x(index)); cursor.setAttribute('opacity', .7);
    $('plotValues').textContent = `Frame ${index + 1} · ` + methods.map(method => {const row = selected.models[method].per_frame[index]; return `${labels[method]}: ${number(row.mean_interval_width)}${showCumulative() ? ', cumulative '+number(row.cumulative_mean_interval_width) : ''}`;}).join(' · ');
  };
  $('plotHit').addEventListener('pointermove', event => showFrame(frameAtPointer(event)));
  $('plotHit').addEventListener('click', event => {
    const index = frameAtPointer(event);
    seekFrame(index);
    showFrame(index);
  });
}
function choose() {
  clearPixel();
  pause(); requestToken++;
  selected = data.videos.find(video => video.id === $('videoSelect').value);
  const url = new URL(location.href); url.searchParams.set('video', selected.id); history.replaceState(null, '', url);
  methods.forEach(method => {
    const report = selected.models[method], video = $(method + 'Video');
    video.src = report.video; video.poster = report.poster; video.load();
    $(method + 'Download').href = report.video;
    $(method + 'Summary').textContent = `Mean width ${number(report.mean_interval_width)} · CV ${(report.coefficient_of_variation * 100).toFixed(2)}%`;
  });
  $('metricsRows').replaceChildren(...methods.map(method => {
    const report = selected.models[method], row = document.createElement('tr');
    [labels[method], number(report.mean_interval_width), number(report.std_interval_width), `${(report.coefficient_of_variation * 100).toFixed(2)}%`, number(report.minimum), number(report.maximum)].forEach(value => {const cell = document.createElement('td'); cell.textContent = value; row.append(cell);});
    return row;
  }));
  $('frame').max = selected.frames; setFrame(0);
  $('status').textContent = `${selected.frames} frames · ${selected.fps} fps playback`;
  $('csvDownload').href = selected.csv; $('figureDownload').href = selected.plot;
  $('plotValues').textContent = 'QUTCC: green · Im2im: orange'; drawPlot();
  $('error').hidden = true;
}
$('play').addEventListener('click', async () => {
  clearPixel();
  const token = requestToken;
  try {
    const [first, second] = videos();
    if (first.ended) first.currentTime = second.currentTime = 0;
    else second.currentTime = first.currentTime;
    await Promise.all(videos().map(video => video.play()));
  } catch (error) {
    if (token === requestToken) {pause(); $('error').textContent = 'Video playback failed. Please reload or download the MP4.'; $('error').hidden = false;}
  }
});
$('pause').addEventListener('click', pause);
for (const video of videos()) video.addEventListener('click', event => {
  if (!selected || video.readyState < 2) return;
  const point = HeatmapPixels.pointAt(video, event, 480, 588);
  if (!point) return;
  const offset = point.y >= 318 ? 318 : point.y >= 24 && point.y < 294 ? 24 : null;
  if (offset === null) return;
  pixelPoint = {x: point.x, y: point.y - offset};
  seekFrame(Math.min(selected.frames - 1, Math.floor(video.currentTime * selected.fps + 1e-6)));
});
$('frame').addEventListener('input', () => seekFrame(Number($('frame').value) - 1));
$('qutccVideo').addEventListener('timeupdate', () => {if (!selected) return; const first = $('qutccVideo'), second = $('im2imVideo'); setFrame(Math.floor(first.currentTime * selected.fps)); if (!first.paused && Math.abs(second.currentTime - first.currentTime) > .15) second.currentTime = first.currentTime;});
$('qutccVideo').addEventListener('ended', pause);
$('zoom').addEventListener('change', drawPlot);
$('cumulativeToggle').addEventListener('click', () => {
  const next = !showCumulative(); $('cumulativeToggle').setAttribute('aria-pressed', String(next));
  $('cumulativeToggle').textContent = next ? 'Hide cumulative average' : 'Show cumulative average';
  $('curveHelp').textContent = next ? 'Faint thin lines: per-frame width. Solid overlays: cumulative average from frame 1 through the current frame.' : 'Thin lines show each frame’s mean width. Use the button to overlay the cumulative average through the current frame. Hover for exact values.';
  drawPlot();
});
$('videoSelect').addEventListener('change', choose);
fetch('data.json?v=20261030bluered', {cache: 'no-store'}).then(response => {if (!response.ok) throw new Error(response.status); return response.json();}).then(value => {
  data = value;
  for (const video of data.videos) {const option = document.createElement('option'); option.value = video.id; option.textContent = video.label; $('videoSelect').append(option);}
  const requested = new URLSearchParams(location.search).get('video');
  if (data.videos.some(video => video.id === requested)) $('videoSelect').value = requested;
  $('heatGradient').style.background = data.heatmap_gradient;
  data.notes.forEach(text => {const paragraph = document.createElement('p'); paragraph.textContent = text; $('protocol').append(paragraph);});
  ['videoSelect', 'play', 'pause', 'frame'].forEach(id => {$(id).disabled = false;}); choose();
}).catch(error => {$('status').textContent = 'Unable to load videos'; $('error').hidden = false; $('error').textContent = String(error);});
