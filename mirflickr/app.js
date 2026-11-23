"use strict";
const METHODS = ["qutcc", "im2im"],
  NAMES = { qutcc: "QUTCC", im2im: "Im2im" },
  COLORS = { qutcc: "#63dbce", im2im: "#f2b76a" };
const $ = (s) => document.querySelector(s),
  fmt = (v, n = 5) => (Number.isFinite(v) ? v.toFixed(n) : "—"),
  pct = (v) => (Number.isFinite(v) ? (100 * v).toFixed(3) + "%" : "—");
let data, assets, index = 0, example = null, busy = false,
  point = { x: 240, y: 135 }, requestSerial = 0;
const CACHE = new Map();

function summary(method) {
  return data.studies.mirflickr[method];
}

function escapeHTML(v) {
  return String(v).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}

function renderImageMetrics() {
  $("#imageMetricRows").innerHTML = METHODS.map((method) => {
    const metrics = example?.models[method]?.metrics;
    if (!metrics)
      return `<tr><td>${NAMES[method]}</td><td colspan="6">Inference pending</td></tr>`;
    return `<tr><td>${NAMES[method]}</td><td>${summary(method).epoch}</td><td>${fmt(metrics.psnr, 3)}</td><td>${fmt(metrics.ssim)}</td><td>${pct(metrics.coverage)}</td><td>${fmt(metrics.width)}</td><td>${fmt(metrics.mae)}</td></tr>`;
  }).join("");
}

function stateURL() {
  const u = new URL(location.href);
  u.searchParams.set("example", index);
  history.replaceState(null, "", u);
  window.syncDemoNavigation?.();
}

function controls(disabled) {
  window.exampleBrowser?.setBusy(disabled);
  for (const id of ["example", "previous", "next", "random"])
    $("#" + id).disabled = disabled;
}

async function unpack(url) {
  const response = await fetch(url);
  if (!response.ok) throw Error(`HTTP ${response.status}`);
  const decompressed = new Response(response.body.pipeThrough(new DecompressionStream("gzip"))),
    buffer = await decompressed.arrayBuffer(),
    view = new DataView(buffer),
    length = view.getUint32(0, true);
  const header = JSON.parse(new TextDecoder().decode(new Uint8Array(buffer, 4, length))),
    start = 4 + length,
    arrays = {};
  for (const d of header.arrays) {
    const bytes = new Uint8Array(buffer, start + d.offset, d.length);
    if (d.encoding === "uint8") {
      arrays[d.name] = Uint8Array.from(bytes);
    } else {
      const size = bytes.length / 4, ordered = new Uint8Array(bytes.length);
      for (let byte = 0; byte < 4; byte++)
        for (let i = 0; i < size; i++)
          ordered[4 * i + byte] = bytes[byte * size + i];
      arrays[d.name] = new Float32Array(ordered.buffer);
    }
  }
  return { ...header, ...arrays };
}

function heat(v) {
  if (v < 0) return [255, 50, 150];
  const t = Math.min(1, Math.max(0, v)),
    stops = [[20,35,60],[34,95,157],[35,185,172],[243,203,85],[250,112,82]],
    i = Math.min(3, Math.floor(t * 4)), f = t * 4 - i;
  return stops[i].map((a, k) => Math.round(a + (stops[i+1][k] - a) * f));
}

function paint(canvas, kind, model) {
  const { width: w, height: h } = example, N = w * h;
  canvas.width = w; canvas.height = h;
  const ctx = canvas.getContext("2d"), img = ctx.createImageData(w, h);
  let arr;
  if (kind === "measurement" || kind === "target") arr = example[kind];
  else arr = example.models[model][kind];
  for (let i = 0; i < N; i++) {
    let rgb;
    if (kind === "error" || kind === "width") {
      let value = 0;
      const m = example.models[model];
      for (let c = 0; c < 3; c++) {
        const k = c * N + i;
        value += kind === "error"
          ? Math.abs(example.target[k] / 255 - m.prediction[k])
          : m.upper[k] - m.lower[k];
      }
      rgb = heat(value / 3);
    } else {
      rgb = [0,1,2].map((c) => Math.max(0, Math.min(255,
        arr[c * N + i] * (arr instanceof Uint8Array ? 1 : 255))));
    }
    for (let c = 0; c < 3; c++) img.data[4 * i + c] = rgb[c];
    img.data[4 * i + 3] = 255;
  }
  ctx.putImageData(img, 0, 0);
  if (kind !== "measurement") HeatmapPixels.drawCanvas(canvas, point.x + 0.5, point.y + 0.5);
  if (kind === "measurement") { canvas.onclick = null; return; }
  canvas.onclick = (e) => {
    const r = canvas.getBoundingClientRect();
    point = {
      x: Math.max(0, Math.min(w - 1, Math.floor(((e.clientX - r.left) / r.width) * w))),
      y: Math.max(0, Math.min(h - 1, Math.floor(((e.clientY - r.top) / r.height) * h))),
    };
    $("#pixelInspector").open = true;
    drawImages();
  };
}

function renderPixel() {
  if (!example) return;
  const N = example.width * example.height, p = point.y * example.width + point.x,
    ch = $("#channel").value, channels = ch === "rgb" ? [0,1,2] : [Number(ch)];
  const read = (a, byte = false) =>
    channels.reduce((sum, c) => sum + a[c * N + p] / (byte ? 255 : 1), 0) / channels.length;
  const target = read(example.target, true);
  $("#pixelTitle").textContent = `Selected pixel (${point.x}, ${point.y})`;
  $("#pixelTruth").textContent =
    `Ground truth: ${target.toFixed(6)} · ${ch === "rgb" ? "RGB average" : ["Red","Green","Blue"][Number(ch)]}`;
  $("#pixelRows").innerHTML = METHODS.map((method) => {
    const m = example.models[method];
    if (!m) return `<tr><td>${NAMES[method]}</td><td colspan="5">Inference pending</td></tr>`;
    const pred = read(m.prediction), lo = read(m.lower), hi = read(m.upper);
    const err = channels.reduce((s, c) => s + Math.abs(example.target[c*N+p]/255 - m.prediction[c*N+p]), 0) / channels.length;
    return `<tr><td>${NAMES[method]}</td>${[pred, lo, hi, err, hi - lo].map((v) => `<td>${v.toFixed(6)}</td>`).join("")}</tr>`;
  }).join("");
}

function drawImages() {
  if (!example) return;
  paint($("#measurement"), "measurement");
  paint($("#target"), "target");
  for (const c of document.querySelectorAll("#matrix canvas"))
    paint(c, c.dataset.kind, c.dataset.method);
  renderPixel();
}

function renderExample() {
  window.exampleBrowser?.update(index);
  let html = "";
  for (const method of METHODS) {
    const m = example.models[method];
    if (!m) {
      html += `<div class="model-header"><h3>${NAMES[method]}</h3><p>Inference pending.</p></div>`;
      continue;
    }
    html += `<div class="model-header"><h3 style="color:${COLORS[method]}">${NAMES[method]}</h3></div>`;
    for (const [kind, label] of [
      ["prediction", "Reconstruction"], ["error", "Error"], ["width", "Uncertainty"],
      ["lower", "Lower bound"], ["upper", "Upper bound"],
    ])
      html += `<figure class="${["lower","upper"].includes(kind) ? "bound-image" : ""}"><figcaption>${label}</figcaption><canvas class="image" data-kind="${kind}" data-method="${method}"></canvas></figure>`;
  }
  $("#matrix").innerHTML = html;
  renderImageMetrics();
  drawImages();
  const count = Math.min(...METHODS.map((m) => summary(m).example_count));
  $("#status").textContent = `${index + 1} / ${count} · ID ${example.id}`;
}

async function loadExample() {
  const serial = ++requestSerial;
  busy = true; controls(true);
  $("#status").textContent = "Loading…";
  const key = String(index);
  try {
    let item = CACHE.get(key);
    if (!item) {
      const loaded = await Promise.all(METHODS.map((m) =>
        unpack(`${assets.base}/${m}/example_${String(index).padStart(2, "0")}.bin.gz`)));
      const [a, b] = loaded;
      if (String(a.id) !== String(b.id) || a.target.length !== b.target.length)
        throw Error("Example pairing mismatch");
      const shape = a.arrays.find((d) => d.name === "target").shape;
      item = {
        id: a.id, width: shape[2], height: shape[1],
        measurement: a.measurement, target: a.target,
        models: Object.fromEntries(METHODS.map((m, i) => [m, loaded[i]])),
      };
      if (CACHE.size > 5) CACHE.delete(CACHE.keys().next().value);
      CACHE.set(key, item);
    }
    if (serial !== requestSerial) return;
    example = item;
    point.x = Math.min(point.x, item.width - 1);
    point.y = Math.min(point.y, item.height - 1);
    renderExample();
    stateURL();
  } catch (e) {
    if (serial === requestSerial)
      $("#status").textContent = "Could not load example: " + e.message;
    console.error(e);
  } finally {
    if (serial === requestSerial) { busy = false; controls(false); }
  }
}

function renderTables() {
  $("#aggregateRows").innerHTML = METHODS.map((method) => {
    const s = summary(method), m = s.metrics?.clipped;
    if (!m) return `<tr><td>${NAMES[method]}</td><td>${s.epoch}</td><td colspan="6">Inference pending</td></tr>`;
    return `<tr><td>${NAMES[method]}</td><td>${s.epoch}</td><td>${fmt(m.psnr, 3)}</td><td>${fmt(m.ssim)}</td><td>${pct(s.calibration?.calibration_coverage)}</td><td>${pct(m.coverage)}</td><td>${fmt(m.width)}</td><td>${fmt(m.lpips)}</td></tr>`;
  }).join("");

  $("#calibrationRows").innerHTML = METHODS.flatMap((method) =>
    summary(method).evaluations.map((e) => ({ method, ...e }))
  ).sort((a, b) => a.epoch - b.epoch || a.method.localeCompare(b.method))
   .map((e) => {
     if (e.status !== "complete")
       return `<tr><td>${e.epoch}</td><td>${NAMES[e.method]}</td><td colspan="5">Calibration pending</td></tr>`;
     const c = e.calibration, q = e.method === "qutcc";
     const param = q ? `q = ${fmt(c.lower_q, 6)} / ${fmt(c.upper_q, 6)}`
       : `λ mean = ${fmt(c.lambda_mean, 6)}, max = ${fmt(c.lambda_max, 6)}`;
     return `<tr><td>${e.epoch}</td><td>${NAMES[e.method]}</td><td>${q ? "Quantile search" : "K-RCPS"}</td><td>${escapeHTML(param)}</td><td>${pct(c.calibration_coverage)}</td><td>${pct(e.metrics.clipped.coverage)}</td><td>${fmt(e.metrics.clipped.width, 6)}</td></tr>`;
   }).join("");

  const count = Math.min(...METHODS.map((m) => summary(m).example_count));
  $("#provenance").hidden = count === 0;
  $("#provenance").textContent = `Images: epoch ${summary("qutcc").epoch} · ${count} examples`;
  const epochs = Math.max(...METHODS.flatMap((m) => summary(m).history.map((r) => r.epoch)), 0);
  $("#curveNote").textContent = epochs ? `Curves through epoch ${epochs}` : "";
  $("#settings").textContent =
    "QUTCC and Im2im trained from random initialization for 50 epochs. AdamW with cosine-decayed learning rate and weight decay.";
}

function makePlot(container, title, key, kind) {
  const plot = document.createElement("div");
  plot.className = "plot";
  const histories = {};
  for (const method of METHODS) {
    const s = summary(method);
    histories[method] = kind === "validation"
      ? s.history.map((r) => ({ epoch: r.epoch, value: r[key] }))
      : s.evaluations.map((r) => ({
          epoch: r.epoch, status: r.status,
          value: r.status === "complete" ? r.metrics.clipped[key] : null,
          calibrationCoverage: r.calibration?.calibration_coverage,
        }));
  }
  const values = METHODS.flatMap((m) =>
    histories[m].filter((r) => Number.isFinite(r.value)).map((r) => r.value));
  if (!values.length) {
    plot.innerHTML = `<h3>${title}</h3><p>Inference pending.</p>`;
    container.append(plot);
    return;
  }
  const epochs = [...new Set(METHODS.flatMap((m) => histories[m].map((r) => r.epoch)))].sort((a,b) => a-b),
    scale = key === "coverage" ? 100 : 1;
  let lo = Math.min(...values) * scale, hi = Math.max(...values) * scale;
  const pad = Math.max((hi - lo) * 0.12, key === "ssim" ? 0.001 : key === "coverage" ? 0.025 : 0.05);
  lo -= pad; hi += pad;
  const W = 700, H = 270, L = 64, R = 20, T = 18, B = 42,
    x = (e) => L + ((e - epochs[0]) / Math.max(1, epochs.at(-1) - epochs[0])) * (W - L - R),
    y = (v) => H - B - ((v - lo) / (hi - lo)) * (H - T - B);
  let svg = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${title}">`;
  for (let i = 0; i < 5; i++) {
    const v = lo + ((hi - lo) * i) / 4;
    svg += `<line x1="${L}" x2="${W-R}" y1="${y(v)}" y2="${y(v)}" stroke="#354357"/>` +
      `<text x="${L-8}" y="${y(v)+4}" fill="#bac7d6" font-size="12" text-anchor="end">${v.toFixed(key==="psnr"?2:3)}</text>`;
  }
  for (const e of epochs.filter((e) => epochs.length <= 12 || e % 5 === 0))
    svg += `<text x="${x(e)}" y="${H-18}" fill="#bac7d6" font-size="12" text-anchor="middle">${e}</text>`;
  for (const method of METHODS) {
    let d = "";
    for (const r of histories[method]) {
      if (!Number.isFinite(r.value)) { if (d) svg += `<path d="${d}" fill="none" stroke="${COLORS[method]}" stroke-width="1.5"/>`; d = ""; continue; }
      d += `${d ? "L" : "M"}${x(r.epoch)},${y(r.value * scale)}`;
      svg += `<circle cx="${x(r.epoch)}" cy="${y(r.value*scale)}" r="3" fill="${COLORS[method]}"/>`;
    }
    if (d) svg += `<path d="${d}" fill="none" stroke="${COLORS[method]}" stroke-width="1.5"/>`;
  }
  svg += '<line class="epoch-guide" hidden/>';
  for (let i = 0; i < epochs.length; i++) {
    const e = epochs[i],
      left = i ? (x(e) + x(epochs[i-1])) / 2 : L,
      right = i < epochs.length - 1 ? (x(e) + x(epochs[i+1])) / 2 : W - R;
    svg += `<rect class="epoch-hit" tabindex="0" role="button" aria-label="Epoch ${e}" data-epoch="${e}" x="${left}" y="${T}" width="${Math.max(1, right-left)}" height="${H-T-B}"/>`;
  }
  svg += "</svg>";
  plot.innerHTML = `<h3>${title}</h3><div class="legend">${METHODS.map((m) => `<span style="color:${COLORS[m]}">${NAMES[m]}</span>`).join("")}</div>${svg}<div class="tooltip" hidden></div>`;
  const tip = plot.querySelector(".tooltip"), guide = plot.querySelector(".epoch-guide");
  const show = (e) => {
    tip.hidden = false;
    tip.innerHTML = `<b>Epoch ${e}</b><table>${METHODS.map((m) => {
      const r = histories[m].find((r) => r.epoch === e), v = r?.value;
      return `<tr><td style="color:${COLORS[m]}">${NAMES[m]}</td><td>${Number.isFinite(v) ? (v*scale).toFixed(6) + (key==="coverage"?"%":"") : "—"}</td></tr>`;
    }).join("")}</table>`;
    guide.removeAttribute("hidden");
    for (const [k,v] of Object.entries({x1:x(e),x2:x(e),y1:T,y2:H-B})) guide.setAttribute(k,v);
  };
  for (const hit of plot.querySelectorAll(".epoch-hit")) {
    hit.onpointerenter = hit.onfocus = () => show(Number(hit.dataset.epoch));
  }
  plot.onpointerleave = () => { tip.hidden = true; guide.setAttribute("hidden", ""); };
  container.append(plot);
}

function renderCurves() {
  for (const id of ["historyPlots", "intervalPlots"]) $("#" + id).innerHTML = "";
  makePlot($("#historyPlots"), "Validation PSNR (dB)", "psnr", "validation");
  makePlot($("#historyPlots"), "Validation SSIM", "ssim", "validation");
  makePlot($("#intervalPlots"), "Mean interval width · test", "width", "test");
  makePlot($("#intervalPlots"), "Actual test coverage (%)", "coverage", "test");
}

function initializeExamples() {
  const count = Math.min(...METHODS.map((m) => summary(m).example_count));
  if (count === 0) {
    $("#status").textContent = "Inference pending — examples not yet available.";
    controls(true);
    renderTables();
    renderCurves();
    return;
  }
  index = Math.min(index, count - 1);
  $("#example").innerHTML = Array.from({length: count}, (_, i) =>
    `<option value="${i}">${i + 1}</option>`).join("");
  $("#example").value = index;
  renderTables();
  renderCurves();
  loadExample();
}

(async () => {
  try {
    [data, assets] = await Promise.all(
      ["data.json", "assets.json"].map(async (file) => {
        const r = await fetch(file, { cache: "no-store" });
        if (!r.ok) throw Error(file + " HTTP " + r.status);
        return r.json();
      })
    );
    const params = new URLSearchParams(location.search);
    index = Math.max(0, Number(params.get("example")) || 0);
    $("#example").onchange = () => { index = Number($("#example").value); loadExample(); };
    $("#next").onclick = () => { index = (index + 1) % $("#example").options.length; $("#example").value = index; loadExample(); };
    $("#previous").onclick = () => { index = (index + $("#example").options.length - 1) % $("#example").options.length; $("#example").value = index; loadExample(); };
    $("#random").onclick = () => { index = Math.floor(Math.random() * $("#example").options.length); $("#example").value = index; loadExample(); };
    $("#channel").onchange = renderPixel;
    $("#showBounds").onchange = () => $("#matrix").classList.toggle("show-bounds", $("#showBounds").checked);
    initializeExamples();
  } catch (e) {
    $("#status").textContent = "Could not load results: " + e.message;
    console.error(e);
  }
})();
