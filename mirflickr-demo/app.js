"use strict";
const METHODS = ["qutcc", "im2im", "deepensemble", "mcdropout"],
  NAMES = { qutcc: "QUTCC", im2im: "Im2im", deepensemble: "Deep ensemble", mcdropout: "MC dropout" },
  COLORS = { qutcc: "#63dbce", im2im: "#f2b76a", deepensemble: "#a78bfa", mcdropout: "#f87171" };
const $ = (s) => document.querySelector(s);
let data, assets, index = 0, example = null, busy = false,
  point = { x: 240, y: 135 }, requestSerial = 0;
const CACHE = new Map();
const exportVersion = { mcdropout: "?v=mc-grid-44", deepensemble: "?v=ensemble-grid-49" };

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
  const t = Math.min(1, Math.max(0, v)),
    stops = [[20,35,60],[34,95,157],[35,185,172],[243,203,85],[250,112,82]],
    i = Math.min(3, Math.floor(t * 4)), f = t * 4 - i;
  return stops[i].map((a, k) => Math.round(a + (stops[i + 1][k] - a) * f));
}

// Applies a separable Gaussian blur to a scalar map. Kernel radius is 3σ; boundary pixels are replicated.
function smoothMap(values, sigma, width, height) {
  const radius = Math.max(1, Math.round(3 * sigma));
  const weights = Array.from({length: 2 * radius + 1}, (_, i) => Math.exp(-((i - radius) ** 2) / (2 * sigma ** 2)));
  const sum = weights.reduce((a, b) => a + b, 0);
  const horizontal = new Float32Array(values.length);
  const result = new Float32Array(values.length);
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      let total = 0;
      for (let dx = -radius; dx <= radius; dx++) {
        const xx = Math.max(0, Math.min(width - 1, x + dx));
        total += weights[dx + radius] * values[y * width + xx];
      }
      horizontal[y * width + x] = total / sum;
    }
  }
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      let total = 0;
      for (let dy = -radius; dy <= radius; dy++) {
        const yy = Math.max(0, Math.min(height - 1, y + dy));
        total += weights[dy + radius] * horizontal[yy * width + x];
      }
      result[y * width + x] = total / sum;
    }
  }
  return result;
}

function widthKey(model, kind, ex) {
  ex ??= example;
  return kind === "width" && model === ex.models.qutcc && !$("#signedWidth").checked
    ? "absoluteWidth" : kind;
}

function rawMap(model, kind, ex) {
  ex ??= example;
  kind = widthKey(model, kind, ex);
  if (model[kind]) return model[kind];
  const {width, height, target} = ex;
  const count = width * height;
  const values = new Float32Array(count);
  for (let i = 0; i < values.length; i++) {
    for (let c = 0; c < 3; c++) {
      const k = c * count + i;
      values[i] += (kind === "error" ? Math.abs(target[k] / 255 - model.prediction[k])
        : kind === "absoluteWidth" ? Math.abs(model.upper[k] - model.lower[k])
        : model.upper[k] - model.lower[k]) / 3;
    }
  }
  model[kind] = values;
  return values;
}

function displayMap(model, kind, ex, blurEl) {
  ex ??= example;
  const raw = rawMap(model, kind, ex);
  const sigma = Number((blurEl ?? $("#blur")).value);
  if (!sigma) return raw;
  model.smoothed ??= {};
  model.smoothed[sigma] ??= {};
  return model.smoothed[sigma][widthKey(model, kind, ex)] ??= smoothMap(raw, sigma, ex.width, ex.height);
}

function paint(canvas, kind, model, pctx) {
  const ex = pctx?.ex ?? example;
  const blurEl = pctx?.blurEl ?? null;
  const inspectorEl = pctx?.inspectorEl ?? $("#pixelInspector");
  const pt = pctx?.pt ?? point;
  const { width: w, height: h } = ex, N = w * h;
  canvas.width = w; canvas.height = h;
  const ctx = canvas.getContext("2d"), img = ctx.createImageData(w, h);
  let arr;
  if (kind === "measurement" || kind === "target") arr = ex[kind];
  else if (kind === "error" || kind === "width") {
    arr = displayMap(ex.models[model], kind, ex, blurEl);
  }
  else arr = ex.models[model][kind];
  const markCrossing = kind === "width" && model === "qutcc" && $("#signedWidth").checked;
  const qModel = ex.models.qutcc;
  for (let i = 0; i < N; i++) {
    let rgb;
    if (kind === "error" || kind === "width") {
      rgb = heat(arr[i]);
      if (markCrossing && (qModel.lower[i] > qModel.upper[i] ||
          qModel.lower[N+i] > qModel.upper[N+i] || qModel.lower[2*N+i] > qModel.upper[2*N+i]))
        rgb = [227,32,201];
    } else {
      rgb = [0, 1, 2].map((c) => Math.max(0, Math.min(255,
        arr[c * N + i] * (arr instanceof Uint8Array ? 1 : 255))));
    }
    for (let c = 0; c < 3; c++) img.data[4 * i + c] = rgb[c];
    img.data[4 * i + 3] = 255;
  }
  ctx.putImageData(img, 0, 0);
  if (kind !== "measurement" && inspectorEl.open) HeatmapPixels.drawCanvas(canvas, pt.x + 0.5, pt.y + 0.5);
  if (kind === "measurement") { canvas.onclick = null; return; }
  if (pctx?.onPixelClick) {
    canvas.onclick = pctx.onPixelClick(canvas);
  } else {
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
}

function renderPixel() {
  if (!example) return;
  const N = example.width * example.height, p = point.y * example.width + point.x,
    ch = $("#channel").value, channels = ch === "rgb" ? [0, 1, 2] : [Number(ch)];
  const read = (a, byte = false) =>
    channels.reduce((sum, c) => sum + a[c * N + p] / (byte ? 255 : 1), 0) / channels.length;
  const target = read(example.target, true);
  $("#pixelTitle").textContent = `Selected pixel (${point.x}, ${point.y})`;
  $("#pixelTruth").textContent =
    `Ground truth: ${target.toFixed(6)} · ${ch === "rgb" ? "RGB average" : ["Red", "Green", "Blue"][Number(ch)]}`;
  $("#pixelSpread").textContent = "MC dropout SD across 50 passes (RGB mean): " + example.models.mcdropout.spread[p].toFixed(6);
  $("#pixelRows").innerHTML = METHODS.map((method) => {
    const m = example.models[method];
    if (!m) return `<tr><td>${NAMES[method]}</td><td colspan="5">Inference pending</td></tr>`;
    const pred = read(m.prediction), lo = read(m.lower), hi = read(m.upper);
    const err = channels.reduce((s, c) => s + Math.abs(example.target[c * N + p] / 255 - m.prediction[c * N + p]), 0) / channels.length;
    const width = method === "qutcc" && !$("#signedWidth").checked
      ? channels.reduce((sum, c) => sum + Math.abs(m.upper[c*N+p] - m.lower[c*N+p]), 0) / channels.length
      : hi - lo;
    return `<tr><td>${NAMES[method]}</td>${[pred, lo, hi, err, width].map((v) => `<td>${v.toFixed(6)}</td>`).join("")}</tr>`;
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
  const cols = [
    ["prediction", "Reconstruction"], ["error", "Absolute error"], ["width", "Uncertainty"],
    ["lower", "Lower bound (LB)"], ["upper", "Upper bound (UB)"],
  ];
  const isBound = (kind) => kind === "lower" || kind === "upper";
  let html = `<div class="method-row col-headers"><div class="method-label"></div>` +
    cols.map(([kind, label]) => `<div class="${isBound(kind) ? "bound-image" : ""}">${label}</div>`).join("") +
    `</div>`;
  for (const method of METHODS) {
    const m = example.models[method];
    let widthLabel = "";
    if (m) {
      const widths = rawMap(m, "width");
      const mean = widths.reduce((sum, width) => sum + width, 0) / widths.length;
      widthLabel = `<small class="mean-width" title="Mean width across all pixels and RGB channels">Mean width ${mean.toFixed(4)}</small>`;
      const { ssim, psnr, lpips } = data.scenes[index].metrics[method];
      widthLabel += `<small class="mean-width">SSIM ${ssim.toFixed(4)}</small>
        <small class="mean-width">PSNR ${psnr.toFixed(2)} dB</small>
        <small class="mean-width">LPIPS ${lpips.toFixed(4)}</small>`;
    }
    const nameDiv = `<div class="method-label" style="color:${COLORS[method]}">${NAMES[method]}${widthLabel}</div>`;
    if (!m) {
      html += `<div class="method-row">${nameDiv}<p class="pending-method">Inference pending.</p></div>`;
      continue;
    }
    const figures = cols.map(([kind, label]) => {
      const dropoutBound = method === "mcdropout" && isBound(kind);
      return `<figure class="${isBound(kind) ? "bound-image" : ""}"><figcaption class="panel-title${dropoutBound ? " dropout-bound" : ""}">${label}</figcaption><canvas class="image" aria-label="${NAMES[method]} ${label}" data-kind="${kind}" data-method="${method}"></canvas></figure>`;
    }).join("");
    html += `<div class="method-row">${nameDiv}${figures}</div>`;
  }
  $("#matrix").innerHTML = html;
  drawImages();
  $("#status").textContent = `${index + 1} / ${data.scenes.length} · ${example.id} · Im2im SSIM ${data.scenes[index].ssim.toFixed(3)}`;
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
        unpack(`${assets.base}/${m}/example_${String(index).padStart(2, "0")}.bin.gz${exportVersion[m] ?? ""}`)));
      for (let i = 1; i < loaded.length; i++)
        if (String(loaded[i].id) !== String(loaded[0].id) || loaded[i].prediction.length !== loaded[0].target.length)
          throw Error("Example pairing mismatch");
      if (loaded[0].id !== data.scenes[index].id) throw Error("Scene ID differs from label");
      const shape = loaded[0].arrays.find((d) => d.name === "target").shape;
      item = {
        id: loaded[0].id, width: shape[2], height: shape[1],
        measurement: loaded[0].measurement, target: loaded[0].target,
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
    const u = new URL(location.href);
    u.searchParams.set("example", index);
    history.replaceState(null, "", u);
  } catch (e) {
    if (serial === requestSerial)
      $("#status").textContent = "Could not load example: " + e.message;
    console.error(e);
  } finally {
    if (serial === requestSerial) { busy = false; controls(false); }
  }
}

function initWGTPictures() {
  const rows = [["qutcc", "im2im"], ["deepensemble", "mcdropout"]];
  $("#wgt-grid").innerHTML = rows.map(pair =>
    `<div class="wgt-row">${pair.map(method => `
      <div class="wgt-method">
        <div class="wgt-method-header">
          <span class="wgt-method-name" style="color:${COLORS[method]}">${NAMES[method]}</span>
          <span class="wgt-avg-width">(avg width: N/A)</span>
        </div>
        <div class="wgt-pair">
          <figure><figcaption>Reconstruction</figcaption><canvas data-kind="prediction" data-method="${method}" width="480" height="270"></canvas></figure>
          <figure><figcaption>Uncertainty</figcaption><canvas data-kind="width" data-method="${method}" width="480" height="270"></canvas></figure>
          <figure class="bound-figure"><figcaption>Upper bound (UB)</figcaption><canvas data-kind="upper" data-method="${method}" width="480" height="270"></canvas></figure>
          <figure class="bound-figure"><figcaption>Lower bound (LB)</figcaption><canvas data-kind="lower" data-method="${method}" width="480" height="270"></canvas></figure>
        </div>
      </div>`).join("")}</div>`
  ).join("");
}

function initVideoLayout() {
  const rows = [["qutcc", "im2im"], ["deepensemble", "mcdropout"]];
  $("#vid-layout").innerHTML =
    `<section class="wgt-input-section">
      <figure><figcaption>Camera input</figcaption><canvas id="vid-measurement" width="480" height="270"></canvas></figure>
    </section>
    <div class="vid-scrubber">
      <input type="range" id="vid-frame" min="0" max="0" value="0" disabled>
      <span id="vid-frame-label">– / –</span>
    </div>
    <div class="wgt-grid">` +
    rows.map(pair =>
      `<div class="wgt-row">${pair.map(method => `
        <div class="wgt-method">
          <div class="wgt-method-header">
            <span class="wgt-method-name" style="color:${COLORS[method]}">${NAMES[method]}</span>
            <span class="wgt-avg-width">(avg width: N/A)</span>
          </div>
          <div class="wgt-pair">
            <figure><figcaption>Reconstruction</figcaption><canvas data-kind="prediction" data-method="${method}" width="480" height="270"></canvas></figure>
            <figure><figcaption>Uncertainty</figcaption><canvas data-kind="width" data-method="${method}" width="480" height="270"></canvas></figure>
            <figure class="bound-figure"><figcaption>Upper bound (UB)</figcaption><canvas data-kind="upper" data-method="${method}" width="480" height="270"></canvas></figure>
            <figure class="bound-figure"><figcaption>Lower bound (LB)</figcaption><canvas data-kind="lower" data-method="${method}" width="480" height="270"></canvas></figure>
          </div>
        </div>`).join("")}</div>`
    ).join("") +
    `</div>`;
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
    index = Math.max(0, Math.min(data.scenes.length - 1, Math.trunc(Number(params.get("example"))) || 0));
    $("#example").innerHTML = Array.from({ length: data.scenes.length }, (_, i) =>
      `<option value="${i}">${data.scenes[i].objects}</option>`).join("");
    $("#example").value = index;
    $("#example").onchange = () => { index = Number($("#example").value); loadExample(); };
    $("#next").onclick = () => { index = (index + 1) % data.scenes.length; $("#example").value = index; loadExample(); };
    $("#previous").onclick = () => { index = (index + data.scenes.length - 1) % data.scenes.length; $("#example").value = index; loadExample(); };
    $("#random").onclick = () => { index = Math.floor(Math.random() * data.scenes.length); $("#example").value = index; loadExample(); };
    $("#channel").onchange = renderPixel;
    $("#pixelInspector").ontoggle = drawImages;
    $("#blur").onchange = () => {
      if (example)
        for (const canvas of document.querySelectorAll('#matrix [data-kind="width"], #matrix [data-kind="error"]'))
          paint(canvas, canvas.dataset.kind, canvas.dataset.method);
    };
    $("#showBounds").onclick = () => { const on = $("#matrix").classList.toggle("show-bounds"); $("#showBounds").setAttribute("aria-expanded", on); $("#showBounds").textContent = on ? "Hide bounds" : "Show bounds"; };

    function rememberTab(key, value) {
      const url = new URL(location.href);
      url.searchParams.set(key, value);
      history.replaceState(history.state, "", url);
    }

    // Page tab switching
    document.querySelectorAll(".page-tab").forEach(btn => {
      btn.onclick = () => {
        document.querySelectorAll(".page-tab").forEach(b => b.classList.remove("active"));
        document.querySelectorAll(".tab-panel").forEach(p => p.classList.remove("active"));
        btn.classList.add("active");
        document.getElementById(btn.dataset.tab).classList.add("active");
        rememberTab("tab", btn.dataset.tab);
      };
    });

    // Subtab switching
    document.querySelectorAll(".subtab").forEach(btn => {
      btn.onclick = () => {
        const c = btn.closest(".subtab-container");
        c.querySelectorAll(".subtab").forEach(b => b.classList.remove("active"));
        c.querySelectorAll(".subtab-panel").forEach(p => p.classList.remove("active"));
        btn.classList.add("active");
        document.getElementById(btn.dataset.subtab).classList.add("active");
        rememberTab("subtab", btn.dataset.subtab);
      };
    });

    // W/o GT toggle buttons
    $("#wgt-show-bounds").onclick = () => {
      const on = $("#wgt-grid").classList.toggle("show-bounds");
      $("#wgt-show-bounds").textContent = on ? "Hide UB / LB" : "Show UB / LB";
      $("#wgt-show-bounds").setAttribute("aria-expanded", on);
    };
    $("#vid-show-bounds").onclick = () => {
      const on = $("#vid-layout").classList.toggle("show-bounds");
      $("#vid-show-bounds").textContent = on ? "Hide UB / LB" : "Show UB / LB";
      $("#vid-show-bounds").setAttribute("aria-expanded", on);
    };

    initWGTPictures();
    initVideoLayout();
    initUnpaired();
    $("#signedWidth").addEventListener("change", () => {
      const formula = $("#signedWidth").checked ? "upper − lower" : "|upper − lower|";
      $("#widthFormula").textContent = formula;
      const dcFormula = document.getElementById("dc-widthFormula");
      if (dcFormula) dcFormula.textContent = formula;
      if (example) renderExample();
    });
    for (const key of ["subtab", "tab"]) {
      const saved = params.get(key);
      if (saved) Array.from(document.querySelectorAll(`[data-${key}]`))
        .find(button => button.dataset[key] === saved)?.click();
    }
    loadExample();
  } catch (e) {
    $("#status").textContent = "Could not load results: " + e.message;
    console.error(e);
  }
})();
