"use strict";

(() => {
  const $ = id => document.getElementById(id);
  const models = ["qutcc", "im2im"];
  let data;
  let current = 0;
  let renderVersion = 0;
  const pixelInspector = new HeatmapPixels.Inspector($("viewer"));

  function saveLocation() {
    const url = new URL(location.href);
    url.searchParams.set("capture", data.examples[current].id);
    if ($("boundsToggle").checked) url.searchParams.set("bounds", "1");
    else url.searchParams.delete("bounds");
    history.replaceState(null, "", url);
    window.syncDemoNavigation?.();
  }

  function showError(message) {
    $("error").textContent = message;
    $("error").hidden = false;
    $("status").textContent = "Could not load images";
  }

  async function render(index, updateLocation = true) {
    pixelInspector.clear();
    const version = ++renderVersion;
    current = (index + data.count) % data.count;
    const example = data.examples[current];
    $("imageSelect").value = example.id;
    $("captureTitle").textContent = example.name;
    $("measurementName").textContent = example.name;
    $("status").textContent = "Loading…";
    $("viewer").setAttribute("aria-busy", "true");
    $("error").hidden = true;
    const images = [];
    function assign(id, source, alt) {
      const image = $(id);
      image.alt = alt;
      image.src = source;
      images.push(image.decode());
    }
    assign("measurement", example.measurement, `Sensor12 measurement: ${example.name}`);
    for (const model of models) {
      const value = example.models[model];
      const label = data.models[model].label;
      assign(model + "Prediction", value.images.reconstruction, `${label} reconstruction: ${example.name}`);
      assign(model + "Width", value.images.uncertainty + "?v=20261030bluered", `${label} calibrated interval width: ${example.name}`);
      assign(model + "Lower", value.images.lower_bound, `${label} lower bound: ${example.name}`);
      assign(model + "Upper", value.images.upper_bound, `${label} upper bound: ${example.name}`);
      $(model + "Bounds").hidden = !$("boundsToggle").checked;
      $(model + "Metrics").textContent = `Mean interval width: ${value.metrics.mean_interval_width.toFixed(5)}`;
      $(model + "Download").href = value.images.reconstruction;
      $(model + "Download").download = `${example.id}_${model}_exp3_sensor12.png`;
    }
    if (updateLocation) saveLocation();
    try {
      await Promise.all(images);
      if (version !== renderVersion) return;
      $("viewer").setAttribute("aria-busy", "false");
      $("status").textContent = `${current + 1} / ${data.count}`;
    } catch (_) {
      if (version === renderVersion) showError("An image did not load. Select another image or reload this page to retry.");
    }
  }

  function readLocation() {
    const params = new URLSearchParams(location.search);
    const index = data.examples.findIndex(example => example.id === params.get("capture"));
    $("boundsToggle").checked = params.get("bounds") === "1";
    return Math.max(0, index);
  }

  async function start() {
    try {
      const response = await fetch("data.json?v=20261030bluered", { cache: "no-store" });
      if (!response.ok) throw new Error("Capture manifest unavailable");
      data = await response.json();
      if (data.experiment !== 3 || data.epoch !== 50 || data.count !== 10 || Object.keys(data.models).sort().join() !== "im2im,qutcc") throw new Error("Unexpected capture data");
      for (const example of data.examples) {
        const option = document.createElement("option");
        option.value = example.id;
        option.textContent = example.name;
        $("imageSelect").append(option);
      }
      for (const example of data.examples) {
        const row = document.createElement("tr");
        const values = [example.name, ...models.map(model =>
          example.models[model].metrics.mean_interval_width.toFixed(5))];
        for (const value of values) {
          const cell = document.createElement("td");
          cell.textContent = value;
          row.append(cell);
        }
        $("widthRows").append(row);
      }
      $("widthAverage").innerHTML = `<tr><th>Mean across all ten captures</th>${models.map(model =>
        `<th>${data.mean_interval_width[model].toFixed(5)}</th>`
      ).join("")}</tr>`;
      $("heatGradient").style.background = data.heatmap.gradient;
      $("heatRange").textContent = `0 – ${data.heatmap.max.toFixed(3)}`;
      const q = data.models.qutcc.calibration;
      const scales = data.models.im2im.calibration.scales;
      $("calibrationSettings").textContent = `QUTCC: qL = ${q.lower_q.toFixed(7)}, qU = ${q.upper_q.toFixed(7)}. Im2im: lower scale ${scales.lower.toFixed(6)}, upper scale ${scales.upper.toFixed(6)}.`;
      $("heatmapSettings").textContent = `Heatmaps share a 0–${data.heatmap.max.toFixed(5)} scale (${data.heatmap.saturation}). Higher values saturate. Magenta marks a location with at least one crossed RGB interval; bounds are not silently reordered.`;
      $("imageSelect").disabled = false;
      $("previous").disabled = false;
      $("next").disabled = false;
      $("imageSelect").addEventListener("change", event => render(data.examples.findIndex(example => example.id === event.target.value)));
      $("previous").addEventListener("click", () => render(current - 1));
      $("next").addEventListener("click", () => render(current + 1));
      $("boundsToggle").addEventListener("change", () => {
        for (const model of models) $(model + "Bounds").hidden = !$("boundsToggle").checked;
        saveLocation();
      });
      for (const image of $("viewer").querySelectorAll("img")) image.addEventListener("click", event => {
        if ($("viewer").getAttribute("aria-busy") === "true") return;
        const point = HeatmapPixels.pointAt(image, event, 480, 270);
        if (!point) return;
        for (const other of $("viewer").querySelectorAll("img")) HeatmapPixels.mark(other, [{x: point.x + .5, y: point.y + .5}], 480, 270);
        pixelInspector.show({...point, targets: models.map(model => ({
          element: $(model + "Width"),
          path: `captures/${data.examples[current].id}/${model}.bin.gz`,
        }))});
      });
      document.addEventListener("keydown", event => {
        if (event.target.closest?.("input, select, textarea") || event.ctrlKey || event.altKey || event.metaKey) return;
        if (event.key === "ArrowRight" || event.key === "ArrowLeft") {
          event.preventDefault();
          render(current + (event.key === "ArrowRight" ? 1 : -1));
        }
      });
      window.addEventListener("popstate", () => render(readLocation(), false));
      await render(readLocation());
    } catch (_) {
      showError("The named captures could not be loaded. Please reload this page to retry.");
    }
  }
  start();
})();
