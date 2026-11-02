'use strict';
const $ = id => document.getElementById(id);
const methods = ['qutcc', 'im2im'];
const labels = {qutcc: 'QUTCC', im2im: 'Im2im'};
const colors = {qutcc: '#9ddfd2', im2im: '#f9ba77'};
let data, selected, requestToken = 0;
let pixelPoint = null;
let agreementData = null, agreementPanel = null, agreementCursor = null;
const pixelInspector = new HeatmapPixels.Inspector(document.querySelector('.video-grid'));
const number = value => Number(value).toFixed(5);
const videos = () => methods.map(method => $(method + 'Video'));
const showCumulative = () => $('cumulativeToggle').getAttribute('aria-pressed') === 'true';
const tracking = () => $('trackRankGap').checked;
const frameIndex = time => Math.max(0, Math.min(selected.frames - 1, Math.floor(time * selected.fps + 1e-6)));

// Use precomputed patch coordinates during playback: no per-frame map downloads.
function trackRegion(video, index) {
  if (!tracking() || !agreementData || !selected) return;
  const region = agreementData.videos[selected.id]?.rows[index]?.region;
  const wrapper = video.parentElement;
  if (!region) {
    wrapper.querySelector('.pixel-overlay')?.remove();
    if (video.id === 'qutccVideo') $('trackingStatus').textContent = `Frame ${index + 1} · No valid rank-gap patch`;
    return;
  }
  // HeatmapPixels supplies the same wrapper/alignment as manual pixel inspection.
  if (!wrapper.classList.contains('pixel-stage')) HeatmapPixels.mark(video, [], 480, 588);
  let overlay = video.parentElement.querySelector('.pixel-overlay');
  if (!overlay) {HeatmapPixels.mark(video, [], 480, 588); overlay = video.parentElement.querySelector('.pixel-overlay');}
  const key = `${selected.id}/${index}`;
  if (overlay.dataset.trackingKey === key) return;
  overlay.innerHTML = [24, 318].flatMap(offset => [['#fff', 5], ['#07111b', 3], ['#fff200', 1.5]].map(([color, thickness]) =>
    `<rect x="${region.x}" y="${region.y + offset}" width="${region.width}" height="${region.height}" fill="none" stroke="${color}" stroke-width="${thickness}" vector-effect="non-scaling-stroke"/>`)).join('');
  Object.assign(overlay.dataset, {trackingKey: key, frame: index + 1, x: region.x, y: region.y, width: region.width, height: region.height});
  if (video.id === 'qutccVideo') {
    $('trackingStatus').hidden = false;
    $('trackingStatus').textContent = `Frame ${index + 1} · Patch (${region.x}, ${region.y}) · ${region.width} × ${region.height} · Mean rank gap ${region.mean_rank_gap.toFixed(5)}`;
  }
}

function stopTracking() {
  $('trackRankGap').checked = false; $('trackingStatus').hidden = true;
  clearPixel();
}

function presentedFrame(video, time) {
  if (!selected || video.seeking) return;
  const index = frameIndex(video.paused ? video.currentTime : time);
  if (video.id === 'qutccVideo') setFrame(index);
  trackRegion(video, index);
}

// timeupdate alone can skip several of the 20 frames per second.
for (const video of videos()) {
  if ('requestVideoFrameCallback' in video) {
    const onFrame = (_, metadata) => {
      presentedFrame(video, metadata.mediaTime);
      video.requestVideoFrameCallback(onFrame);
    };
    video.requestVideoFrameCallback(onFrame);
  } else {
    video.addEventListener('timeupdate', () => presentedFrame(video, video.currentTime));
  }
  video.addEventListener('seeked', () => presentedFrame(video, video.currentTime));
}
function pause() { videos().forEach(video => video.pause()); }
function setFrame(index) {
  const bounded = Math.max(0, Math.min(selected.frames - 1, index));
  $('frame').value = bounded + 1;
  $('frameLabel').textContent = `${bounded + 1} / ${selected.frames}`;
  if (agreementCursor) agreementCursor(bounded);
  VideoIntensityPlot.setFrame(bounded);
}
function seekFrame(index) {
  pause();
  const bounded = Math.max(0, Math.min(selected.frames - 1, index));
  // Seek inside the frame interval; an exact boundary can decode its predecessor.
  videos().forEach(video => { video.currentTime = (bounded + .5) / selected.fps; });
  setFrame(bounded);
  if (tracking()) videos().forEach(video => trackRegion(video, bounded));
  if (pixelPoint) inspectFrame(bounded);
  showAgreementFrame(bounded);
}
function showAgreementFrame(index) {
  if (!agreementPanel || !agreementData) return;
  const row = agreementData.videos[selected.id]?.rows[index];
  if (!row) return;
  const point = tracking() && row.region ? {x: row.region.x + Math.floor(row.region.width / 2), y: row.region.y + Math.floor(row.region.height / 2)} : pixelPoint;
  agreementPanel.show({key: selected.id + '/' + (index + 1), title: `${selected.label} · Frame ${index + 1}`, row, point,
    paths: Object.fromEntries(methods.map(method => [method, `videos/${selected.id}/${method}/frame_${String(index + 1).padStart(4, '0')}.bin.gz`]))});
}
function drawAgreementPlot() {
  if (!agreementData || !selected) return;
  const info = agreementData.videos[selected.id], rows = info.rows, svg = $('agreementPlot');
  const overlap = UncertaintyAgreement.getMode() === 'overlap';
  const metric = overlap ? 'top10_iou' : 'spearman';
  const label = overlap ? 'Overlap of most uncertain 10% (IoU)' : 'Spearman correlation';
  const display = value => overlap ? UncertaintyAgreement.percent(value) : UncertaintyAgreement.format(value);
  const values = rows.map(row => row[metric]).filter(Number.isFinite);
  $('agreementMetric').value = UncertaintyAgreement.getMode();
  $('agreementLegend').textContent = label;
  $('agreementHelp').textContent = overlap ? 'One overlap score per frame. Shared selected pixels ÷ pixels selected by either model. Higher means more agreement about the most uncertain locations. Click the graph to inspect a frame.' : 'One Spearman coefficient per frame between the two uncertainty maps. Higher means more similar pixel rankings. Click the graph to inspect a frame.';
  $('agreementJumpTitle').textContent = overlap ? 'Lowest-overlap frames · separated by at least 20 frames' : 'Lowest-correlation frames · separated by at least 20 frames';
  $('agreementOverview').href = overlap ? 'agreement/overlap-overview.png' : 'agreement/overview.png';
  $('agreementExamples').hidden = overlap;
  let low = overlap ? 0 : -1, high = 1;
  if ($('agreementZoom').checked && values.length) {
    const minimum = Math.min(...values), maximum = Math.max(...values), margin = Math.max(.01, (maximum - minimum) * .15);
    low = Math.max(overlap ? 0 : -1, minimum - margin); high = Math.min(1, maximum + margin);
  }
  const X = index => 70 + index / Math.max(1, rows.length - 1) * 900;
  const Y = value => 275 - (value - low) / Math.max(.001, high - low) * 253;
  let markup = '';
  for (let tick = 0; tick <= 4; tick++) {
    const value = low + tick / 4 * (high - low), index = Math.round(tick / 4 * (rows.length - 1));
    const text = overlap ? `${(100 * value).toFixed(0)}%` : value.toFixed(2);
    markup += `<line x1="70" x2="970" y1="${Y(value)}" y2="${Y(value)}" stroke="#33455c"/><text x="61" y="${Y(value)+4}" text-anchor="end" fill="#bac7d6" font-size="12">${text}</text><text x="${X(index)}" y="298" text-anchor="middle" fill="#bac7d6" font-size="12">${index+1}</text>`;
  }
  let path = '', connected = false;
  rows.forEach((row, index) => {
    if (Number.isFinite(row[metric])) {path += `${connected?'L':'M'}${X(index)},${Y(row[metric])}`; connected = true;}
    else connected = false;
  });
  markup += `<path data-metric="${metric}" d="${path}" fill="none" stroke="#d7a3ff" stroke-width="1.4"/>`;
  markup += `<text x="520" y="325" text-anchor="middle" fill="#bac7d6" font-size="13">Frame</text><text transform="translate(16,148) rotate(-90)" text-anchor="middle" fill="#bac7d6" font-size="13">${overlap ? 'Top-10% overlap (IoU)' : 'Spearman ρ'}</text><line id="agreementCursor" y1="22" y2="275" stroke="#e5edf5" opacity=".6"/><rect id="agreementHit" x="70" y="22" width="900" height="253" fill="transparent"/>`;
  svg.innerHTML = markup;
  agreementCursor = index => {
    const cursor = $('agreementCursor'); cursor.setAttribute('x1', X(index)); cursor.setAttribute('x2', X(index));
    const row = rows[index];
    $('agreementValues').textContent = `Frame ${index+1} · ${overlap ? 'Overlap (IoU)' : 'Spearman ρ'} ${display(row[metric])}${overlap ? ` · ${row.top10_intersection.toLocaleString()} shared / ${row.top10_union.toLocaleString()} selected by either` : ''}`;
  };
  const frameAtPointer = event => {
    const point = new DOMPoint(event.clientX, event.clientY).matrixTransform(svg.getScreenCTM().inverse());
    return Math.max(0, Math.min(rows.length - 1, Math.round((point.x - 70) / 900 * (rows.length - 1))));
  };
  $('agreementHit').onpointermove = event => agreementCursor(frameAtPointer(event));
  $('agreementHit').onclick = event => seekFrame(frameAtPointer(event));
  const jumps = overlap ? info.low_overlap_frames : info.low_agreement_frames;
  $('agreementJumps').replaceChildren(...jumps.map(frame => {
    const button = document.createElement('button'); button.textContent = `Frame ${frame} · ${overlap ? 'IoU' : 'ρ'} ${display(rows[frame-1][metric])}`;
    button.onclick = () => {
      const region = rows[frame-1].region;
      if (!overlap && region) pixelPoint = {x: region.x + 15, y: region.y + 15};
      else clearPixel();
      seekFrame(frame - 1);
      (overlap ? $('videoDisagreement') : document.querySelector('.video-grid')).scrollIntoView({block: 'start'});
    };
    return button;
  }));
  $('agreementCSV').href = `agreement/${selected.id}.csv`;
  agreementCursor(Number($('frame').value) - 1);
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
  agreementCursor = null;
  pause(); requestToken++;
  selected = data.videos.find(video => video.id === $('videoSelect').value);
  const url = new URL(location.href); url.searchParams.set('video', selected.id); history.replaceState(null, '', url);
  methods.forEach(method => {
    const report = selected.models[method], video = $(method + 'Video');
    video.src = report.video; video.poster = report.poster; video.load();
    video.playbackRate = Number($('playbackSpeed').value);
    $(method + 'Download').href = report.video;
    $(method + 'Summary').textContent = `Mean width ${number(report.mean_interval_width)} · CV ${(report.coefficient_of_variation * 100).toFixed(2)}%`;
  });
  $('metricsRows').replaceChildren(...methods.map(method => {
    const report = selected.models[method], row = document.createElement('tr');
    [labels[method], number(report.mean_interval_width), number(report.std_interval_width), `${(report.coefficient_of_variation * 100).toFixed(2)}%`, number(report.minimum), number(report.maximum)].forEach(value => {const cell = document.createElement('td'); cell.textContent = value; row.append(cell);});
    return row;
  }));
  VideoIntensityPlot.select(selected.id);
  $('frame').max = selected.frames; setFrame(0);
  $('status').textContent = `${selected.frames} frames · ${selected.fps} fps playback`;
  $('csvDownload').href = selected.csv; $('figureDownload').href = selected.plot;
  $('plotValues').textContent = 'QUTCC: green · Im2im: orange'; drawPlot();
  drawAgreementPlot(); showAgreementFrame(0);
  if (tracking()) videos().forEach(video => trackRegion(video, 0));
  $('error').hidden = true;
}
$('play').addEventListener('click', async () => {
  clearPixel();
  agreementPanel?.suspend('Pause or select a frame to inspect the disagreement map.');
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
$('pause').addEventListener('click', () => {pause(); if (selected) showAgreementFrame(Math.min(selected.frames - 1, Math.floor($('qutccVideo').currentTime * selected.fps + 1e-6)));});
for (const video of videos()) video.addEventListener('click', event => {
  if (!selected || video.readyState < 2) return;
  const point = HeatmapPixels.pointAt(video, event, 480, 588);
  if (!point) return;
  const offset = point.y >= 318 ? 318 : point.y >= 24 && point.y < 294 ? 24 : null;
  if (offset === null) return;
  stopTracking();
  pixelPoint = {x: point.x, y: point.y - offset};
  seekFrame(Math.min(selected.frames - 1, Math.floor(video.currentTime * selected.fps + 1e-6)));
});
$('frame').addEventListener('input', () => seekFrame(Number($('frame').value) - 1));
$('trackRankGap').addEventListener('change', () => {
  clearPixel(); $('trackingStatus').hidden = !tracking();
  if (tracking()) videos().forEach(video => trackRegion(video, frameIndex(video.currentTime)));
  if (selected && $('qutccVideo').paused) showAgreementFrame(frameIndex($('qutccVideo').currentTime));
});
$('playbackSpeed').addEventListener('change', () => {
  videos().forEach(video => {video.playbackRate = Number($('playbackSpeed').value);});
});
$('qutccVideo').addEventListener('timeupdate', () => {if (!selected) return; const first = $('qutccVideo'), second = $('im2imVideo'); setFrame(frameIndex(first.currentTime)); if (!first.paused && Math.abs(second.currentTime - first.currentTime) > .15) second.currentTime = first.currentTime;});
$('qutccVideo').addEventListener('ended', () => {pause(); if (selected) showAgreementFrame(selected.frames - 1);});
$('agreementZoom').addEventListener('change', drawAgreementPlot);
$('agreementMetric').addEventListener('change', () => UncertaintyAgreement.setMode($('agreementMetric').value));
window.addEventListener('uncertaintycomparisonchange', () => {
  if (UncertaintyAgreement.getMode() === 'overlap') stopTracking();
  $('trackingControl').hidden = UncertaintyAgreement.getMode() === 'overlap';
  drawAgreementPlot();
});
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
  ['videoSelect', 'play', 'pause', 'frame', 'playbackSpeed'].forEach(id => {$(id).disabled = false;}); choose();
}).catch(error => {$('status').textContent = 'Unable to load videos'; $('error').hidden = false; $('error').textContent = String(error);});
UncertaintyAgreement.load().then(value => {
  agreementData = value;
  agreementPanel = new UncertaintyAgreement.Panel($('videoDisagreement'), point => {
    stopTracking();
    pixelPoint = point;
    seekFrame(Math.min(selected.frames - 1, Math.floor($('qutccVideo').currentTime * selected.fps + 1e-6)));
  }, [$('inspectRankGapTop')]);
  $('trackRankGap').disabled = false;
  if (selected) {
    drawAgreementPlot();
    if ($('qutccVideo').paused) showAgreementFrame(Number($('frame').value) - 1);
    else agreementPanel.suspend('Pause or select a frame to inspect the disagreement map.');
  }
}).catch(() => {$('agreementValues').textContent = 'Agreement analysis unavailable.'; $('videoDisagreement').hidden = true;});

VideoIntensityPlot.init({onSeek: index => seekFrame(index)});
