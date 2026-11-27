"use strict";

let dcData, dcAssets, dcIndex = 0, dcExample = null, dcBusy = false,
  dcPoint = { x: 240, y: 150 }, dcRequestSerial = 0;
const DC_CACHE = new Map();
const DC_EXPORT_VERSION = {};

// Paint context: routes shared paint/rawMap/displayMap to the DC example and controls.
const DC_CTX = {
  get ex() { return dcExample; },
  get blurEl() { return document.getElementById("dc-blur"); },
  get inspectorEl() { return document.getElementById("dc-pixelInspector"); },
  get pt() { return dcPoint; },
  onPixelClick(canvas) {
    return (e) => {
      const { width: w, height: h } = dcExample;
      const r = canvas.getBoundingClientRect();
      dcPoint = {
        x: Math.max(0, Math.min(w - 1, Math.floor(((e.clientX - r.left) / r.width) * w))),
        y: Math.max(0, Math.min(h - 1, Math.floor(((e.clientY - r.top) / r.height) * h))),
      };
      document.getElementById("dc-pixelInspector").open = true;
      dcDrawImages();
    };
  },
};

function dcControls(disabled) {
  for (const id of ["dc-example", "dc-previous", "dc-next", "dc-random"])
    document.getElementById(id).disabled = disabled;
}

function dcDrawImages() {
  if (!dcExample) return;
  paint(document.getElementById("dc-measurement"), "measurement", null, DC_CTX);
  paint(document.getElementById("dc-target"), "target", null, DC_CTX);
  for (const c of document.querySelectorAll("#dc-matrix canvas"))
    paint(c, c.dataset.kind, c.dataset.method, DC_CTX);
  dcRenderPixel();
}

function dcRenderPixel() {
  if (!dcExample) return;
  const N = dcExample.width * dcExample.height, p = dcPoint.y * dcExample.width + dcPoint.x,
    ch = document.getElementById("dc-channel").value,
    channels = ch === "rgb" ? [0, 1, 2] : [Number(ch)];
  const read = (a, byte = false) =>
    channels.reduce((sum, c) => sum + a[c * N + p] / (byte ? 255 : 1), 0) / channels.length;
  const target = read(dcExample.target, true);
  document.getElementById("dc-pixelTitle").textContent = `Selected pixel (${dcPoint.x}, ${dcPoint.y})`;
  document.getElementById("dc-pixelTruth").textContent =
    `Ground truth: ${target.toFixed(6)} · ${ch === "rgb" ? "RGB average" : ["Red", "Green", "Blue"][Number(ch)]}`;
  document.getElementById("dc-pixelRows").innerHTML = dcData.models.map((method) => {
    const m = dcExample.models[method];
    const pred = read(m.prediction), lo = read(m.lower), hi = read(m.upper);
    const err = channels.reduce((s, c) => s + Math.abs(dcExample.target[c * N + p] / 255 - m.prediction[c * N + p]), 0) / channels.length;
    const width = method === "qutcc" && !document.getElementById("signedWidth").checked
      ? channels.reduce((sum, c) => sum + Math.abs(m.upper[c * N + p] - m.lower[c * N + p]), 0) / channels.length
      : hi - lo;
    return `<tr><td>${NAMES[method]}</td>${[pred, lo, hi, err, width].map((v) => `<td>${v.toFixed(6)}</td>`).join("")}</tr>`;
  }).join("");
}

function dcRenderExample() {
  const cols = [
    ["prediction", "Reconstruction"], ["error", "Absolute error"], ["width", "Uncertainty"],
    ["lower", "Lower bound (LB)"], ["upper", "Upper bound (UB)"],
  ];
  const isBound = (kind) => kind === "lower" || kind === "upper";
  let html = `<div class="method-row col-headers"><div class="method-label"></div>` +
    cols.map(([kind, label]) => `<div class="${isBound(kind) ? "bound-image" : ""}">${label}</div>`).join("") +
    `</div>`;
  for (const method of dcData.models) {
    const m = dcExample.models[method];
    let widthLabel = "";
    if (m) {
      const widths = rawMap(m, "width", dcExample);
      const mean = widths.reduce((s, v) => s + v, 0) / widths.length;
      widthLabel = `<small class="mean-width" title="Mean width across all pixels and RGB channels">Mean width ${mean.toFixed(4)}</small>`;
      const metrics = dcData.scenes[dcIndex].metrics?.[method];
      if (metrics) widthLabel +=
        `<small class="mean-width">SSIM ${metrics.ssim.toFixed(4)}</small>` +
        `<small class="mean-width">PSNR ${metrics.psnr.toFixed(2)} dB</small>` +
        `<small class="mean-width">LPIPS ${metrics.lpips.toFixed(4)}</small>`;
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
  document.getElementById("dc-matrix").innerHTML = html;
  dcDrawImages();
  document.getElementById("dc-status").textContent =
    `${dcIndex + 1} / ${dcData.scenes.length} · ${dcExample.id} · Im2im SSIM ${dcData.scenes[dcIndex].ssim.toFixed(3)}`;
}

async function dcLoadExample() {
  const serial = ++dcRequestSerial;
  dcBusy = true; dcControls(true);
  document.getElementById("dc-status").textContent = "Loading…";
  const key = String(dcIndex);
  try {
    let item = DC_CACHE.get(key);
    if (!item) {
      const loaded = await Promise.all(dcData.models.map((m) =>
        unpack(`${dcAssets.base}/${m}/example_${String(dcIndex).padStart(2, "0")}.bin.gz${DC_EXPORT_VERSION[m] ?? ""}`)));
      for (let i = 1; i < loaded.length; i++)
        if (String(loaded[i].id) !== String(loaded[0].id) || loaded[i].prediction.length !== loaded[0].target.length)
          throw Error("Example pairing mismatch");
      if (loaded[0].id !== dcData.scenes[dcIndex].id) throw Error("Scene ID differs from label");
      const shape = loaded[0].arrays.find((d) => d.name === "target").shape;
      item = {
        id: loaded[0].id, width: shape[2], height: shape[1],
        measurement: loaded[0].measurement, target: loaded[0].target,
        models: Object.fromEntries(dcData.models.map((m, i) => [m, loaded[i]])),
      };
      if (DC_CACHE.size > 5) DC_CACHE.delete(DC_CACHE.keys().next().value);
      DC_CACHE.set(key, item);
    }
    if (serial !== dcRequestSerial) return;
    dcExample = item;
    dcPoint.x = Math.min(dcPoint.x, item.width - 1);
    dcPoint.y = Math.min(dcPoint.y, item.height - 1);
    dcRenderExample();
    const u = new URL(location.href);
    u.searchParams.set("dc-example", dcIndex);
    history.replaceState(null, "", u);
  } catch (e) {
    if (serial === dcRequestSerial)
      document.getElementById("dc-status").textContent = "Could not load example: " + e.message;
    console.error(e);
  } finally {
    if (serial === dcRequestSerial) { dcBusy = false; dcControls(false); }
  }
}

(async function initDiffuserCam() {
  try {
    [dcData, dcAssets] = await Promise.all(
      ["data-dc.json", "assets-dc.json"].map(async (file) => {
        const r = await fetch(file, { cache: "no-store" });
        if (!r.ok) throw Error(file + " HTTP " + r.status);
        return r.json();
      })
    );
    const test = dcData.test;
    document.getElementById("dc-calibration-result").textContent =
      `Epoch ${dcData.checkpoint_epoch} · Test pixel coverage ${(100 * test.coverage).toFixed(2)}% across ${test.n_images.toLocaleString("en-US")} images.`;
    const params = new URLSearchParams(location.search);
    dcIndex = Math.max(0, Math.min(dcData.scenes.length - 1, Math.trunc(Number(params.get("dc-example"))) || 0));
    const dcSel = document.getElementById("dc-example");
    dcSel.innerHTML = Array.from({ length: dcData.scenes.length }, (_, i) =>
      `<option value="${i}">${dcData.scenes[i].objects}</option>`).join("");
    dcSel.value = dcIndex;
    dcSel.onchange = () => { dcIndex = Number(dcSel.value); dcLoadExample(); };
    document.getElementById("dc-next").onclick = () => { dcIndex = (dcIndex + 1) % dcData.scenes.length; dcSel.value = dcIndex; dcLoadExample(); };
    document.getElementById("dc-previous").onclick = () => { dcIndex = (dcIndex + dcData.scenes.length - 1) % dcData.scenes.length; dcSel.value = dcIndex; dcLoadExample(); };
    document.getElementById("dc-random").onclick = () => { dcIndex = Math.floor(Math.random() * dcData.scenes.length); dcSel.value = dcIndex; dcLoadExample(); };
    document.getElementById("dc-channel").onchange = dcRenderPixel;
    document.getElementById("dc-pixelInspector").ontoggle = dcDrawImages;
    document.getElementById("dc-blur").onchange = () => {
      if (dcExample)
        for (const c of document.querySelectorAll('#dc-matrix [data-kind="width"], #dc-matrix [data-kind="error"]'))
          paint(c, c.dataset.kind, c.dataset.method, DC_CTX);
    };
    document.getElementById("dc-showBounds").onclick = () => {
      const on = document.getElementById("dc-matrix").classList.toggle("show-bounds");
      document.getElementById("dc-showBounds").setAttribute("aria-expanded", on);
      document.getElementById("dc-showBounds").textContent = on ? "Hide bounds" : "Show bounds";
    };
    const loadOnOpen = () => {
      if (!dcExample && !dcBusy) dcLoadExample();
    };
    document.querySelector('[data-tab="tab-diffusercam"]').addEventListener("click", loadOnOpen);
    if (document.getElementById("tab-diffusercam").classList.contains("active")) loadOnOpen();
  } catch (e) {
    document.getElementById("dc-status").textContent = "Could not load DiffuserCam results: " + e.message;
    console.error(e);
  }
})();
