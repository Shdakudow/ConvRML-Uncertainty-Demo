/* Shared empirical-calibration controls and exact saved-array overlays. */
(() => {
  "use strict";
  const root = new URL("./", document.currentScript.src);
  const active =
    new URLSearchParams(location.search).get("calibration") !== "reference";
  const labels = {
    im2im: "Im2im",
    ensemble5: "Ensemble · 5",
    ensemble10: "Ensemble · 10",
    mc_005: "MC dropout",
    qutcc: "QUTCC",
  };
  let metadata, curves;

  async function init() {
    const response = await fetch(new URL("coverage90.json", root), {
      cache: "no-store",
    });
    if (!response.ok)
      throw Error("Calibration metadata HTTP " + response.status);
    metadata = await response.json();
    const curveResponse = await fetch(new URL("coverage90_curves.json", root), {
      cache: "no-store",
    });
    if (!curveResponse.ok)
      throw Error("Calibration curves HTTP " + curveResponse.status);
    curves = await curveResponse.json();
    const nav = document.querySelector("main > nav");
    const label = document.createElement("label");
    label.textContent = "Calibration ";
    const select = document.createElement("select");
    select.id = "calibrationMode";
    select.innerHTML =
      '<option value="tight90">Near 90%</option><option value="reference">Reference</option>';
    select.value = active ? "tight90" : "reference";
    select.onchange = () => {
      const url = new URL(location.href);
      url.searchParams.set("calibration", select.value);
      location.href = url.href;
    };
    label.append(select);
    nav.prepend(label);
    const status = document.createElement("p");
    status.id = "calibrationStatus";
    status.className = "muted context";
    status.setAttribute("role", "status");
    nav.after(status);
  }

  const entries = (group) => metadata?.groups?.[group] || {};
  function status(group, methods) {
    const count = methods.filter((method) => entries(group)[method]).length;
    const outside = methods.filter(
      (method) =>
        entries(group)[method] &&
        !entries(group)[method].calibration.within_tolerance,
    );
    const node = document.getElementById("calibrationStatus");
    node.textContent = active
      ? `Near 90% · empirical calibration · ${count}/${methods.length} models ready · actual test coverage shown below${outside.length ? " · Outside target band: " + outside.map((method) => labels[method]).join(", ") : ""}`
      : "Reference calibration · original results";
    node.title = active
      ? "Target: 90.0–90.1% on the calibration split. No RCPS confidence guarantee. Test coverage may vary. Missing models remain unavailable until inference finishes."
      : "Original RCPS-HB baseline and paper-style QUTCC results are preserved.";
  }

  async function unpack(entry, index) {
    const response = await fetch(
      `${entry.base}/example_${String(index).padStart(2, "0")}.bin.gz`,
    );
    if (!response.ok) throw Error("Near-90% array HTTP " + response.status);
    const buffer = await new Response(
      response.body.pipeThrough(new DecompressionStream("gzip")),
    ).arrayBuffer();
    const size = new DataView(buffer).getUint32(0, true);
    const header = JSON.parse(
      new TextDecoder().decode(new Uint8Array(buffer, 4, size)),
    );
    const output = { ...header };
    for (const descriptor of header.arrays) {
      const bytes = new Uint8Array(
        buffer,
        4 + size + descriptor.offset,
        descriptor.length,
      );
      if (descriptor.encoding === "uint8")
        output[descriptor.name] = Uint8Array.from(bytes);
      else {
        const count = bytes.length / 4,
          ordered = new Uint8Array(bytes.length);
        for (let b = 0; b < 4; b++)
          for (let i = 0; i < count; i++)
            ordered[4 * i + b] = bytes[b * count + i];
        output[descriptor.name] = new Float32Array(ordered.buffer);
      }
    }
    return output;
  }

  function checkPair(reference, replacement) {
    if (String(reference.id) !== String(replacement.id))
      throw Error("Calibration sample ID mismatch");
    for (const key of ["measurement", "target"]) {
      if (
        reference[key].length !== replacement[key].length ||
        !reference[key].every((v, i) => v === replacement[key][i])
      ) {
        throw Error("Calibration " + key + " mismatch");
      }
    }
  }

  function exp2Dataset(dataset, group) {
    status(group, ["im2im", "ensemble5", "mc_005", "qutcc"]);
    if (!active) return;
    const ready = entries(group);
    dataset.methods = [];
    dataset.aggregate = {};
    dataset.factors = {};
    for (const [method, entry] of Object.entries(ready)) {
      if (
        JSON.stringify(entry.ids.map(String)) !==
        JSON.stringify(dataset.ids.map(String))
      )
        throw Error("Calibration preview IDs do not match");
      const key = method === "qutcc" ? "paper_qutcc" : method;
      dataset.methods.push(key);
      dataset.aggregate[key] = entry.aggregate;
      dataset.epochs[key] = entry.epoch;
      dataset.factors[key] = entry.calibration.scales || null;
    }
    dataset.notes =
      "Frozen checkpoints; separate calibration split targets 90.0–90.1% after [0,1] clipping. Test coverage is measured independently. Empirical calibration, not an RCPS certificate.";
    dataset.calibrationMethod = "tight_empirical";
  }

  async function exp2Example(reference, index, group) {
    if (!active) return reference;
    const output = { ...reference, models: {} };
    await Promise.all(
      Object.entries(entries(group)).map(async ([method, entry]) => {
        const packed = await unpack(entry, index);
        checkPair(reference, packed);
        // The Exp2 receiveExample decoder consumes shuffled bytes. Encode these
        // exact floats in the same format, without float16/PNG conversion.
        const shuffle = (array) => {
          const raw = new Uint8Array(
              array.buffer,
              array.byteOffset,
              array.byteLength,
            ),
            bytes = new Uint8Array(raw.length),
            n = raw.length / 4;
          for (let i = 0; i < n; i++)
            for (let b = 0; b < 4; b++) bytes[b * n + i] = raw[4 * i + b];
          return bytes;
        };
        output.models[method === "qutcc" ? "paper_qutcc" : method] = {
          mean: shuffle(packed.prediction),
          lower: shuffle(packed.lower),
          upper: shuffle(packed.upper),
          metrics: packed.metrics,
        };
      }),
    );
    return output;
  }

  function exp2Summary() {
    const group = window.CAMERA,
      ready = entries(group);
    const body = document.getElementById("aggregateRows"),
      table = body.closest("table");
    table.tHead.innerHTML =
      "<tr><th>Model</th><th>PSNR (dB)</th><th>SSIM</th><th>Calibration coverage</th><th>Test coverage</th><th>Width</th></tr>";
    const before = table.closest(".table-wrap").previousElementSibling;
    before.textContent =
      "Full held-out test set; calibration coverage is measured on separate images.";
    before.previousElementSibling.textContent = "All 5,000 test images";
    body.innerHTML = ["im2im", "ensemble5", "mc_005", "qutcc"]
      .map((method) => {
        const entry = ready[method];
        if (!entry)
          return `<tr><td>${labels[method]}</td><td colspan="5">Inference pending</td></tr>`;
        const m = entry.metrics.clipped,
          cal = entry.calibration;
        return `<tr><td>${labels[method]} · epoch ${entry.epoch}</td><td>${m.psnr.toFixed(3)}</td><td>${m.ssim.toPrecision(5)}</td><td title="${cal.within_tolerance ? "Within requested band" : "Outside requested band; closest fit reported"}">${(100 * cal.calibration_coverage).toFixed(3)}%</td><td>${(100 * m.coverage).toFixed(3)}%</td><td>${m.width.toFixed(5)}</td></tr>`;
      })
      .join("");
  }

  function exp2Details() {
    const ready = entries(window.CAMERA);
    document.getElementById("qExplanation").textContent =
      "Near-90% empirical fit on 2,048 calibration images using clipped endpoints. QUTCC refines global q inputs; baselines fit independent lower/upper scales. Test data do not select the endpoints.";
    const rows = document.getElementById("factorRows");
    rows
      .closest("details")
      .querySelectorAll(":scope > p:not(#qExplanation)")
      .forEach((node) => (node.hidden = true));
    rows.innerHTML = ["im2im", "ensemble5", "mc_005", "qutcc"]
      .map((method) => {
        const e = ready[method],
          c = e?.calibration;
        return `<tr><td>${labels[method]}</td>${!c ? '<td colspan="2">Pending</td>' : method === "qutcc" ? `<td>q=${c.lower_q.toFixed(8)}</td><td>q=${c.upper_q.toFixed(8)}</td>` : `<td>${c.scales.lower.toFixed(6)}</td><td>${c.scales.upper.toFixed(6)}</td>`}</tr>`;
      })
      .join("");
    const download = document.createElement("p");
    download.innerHTML =
      '<a href="../coverage90.json">Download near-90% calibration and test metrics</a> · <a href="../coverage90_curves.json">Five-epoch curve data</a>';
    rows.closest("details").append(download);
    document
      .getElementById("ensembleDifferenceRows")
      .closest("details").hidden = true;
    document.querySelector('#ensembleSize option[value="10"]').disabled = true;
    document.getElementById("ensembleSize").closest("label").hidden = true;
    // The old correlation analyses use reference intervals and must not be
    // presented as analyses of the new uncertainty maps.
    for (const id of ["analysisStatus", "analysisPlots", "analysisFigures"]) {
      const node = document.getElementById(id);
      node.hidden = true;
      if (id === "analysisStatus") node.previousElementSibling.hidden = true;
      if (id === "analysisFigures") node.closest("details").hidden = true;
    }
    const plots = document.getElementById("intervalHistoryPlots");
    const details = plots.previousElementSibling.previousElementSibling;
    if (details.tagName === "DETAILS")
      details.querySelector("p").textContent =
        "Each saved checkpoint at epochs 5, 10, …, 50 is calibrated independently and evaluated on the same full test split. Queued milestones remain pending; infeasible calibration leaves a gap. Hover to compare exact values, including calibration coverage.";
    const accuracyDetails =
      document.getElementById("historyPlots").previousElementSibling
        .previousElementSibling;
    if (accuracyDetails.tagName === "DETAILS") {
      accuracyDetails.querySelector("p").textContent =
        "PSNR and SSIM use the same 5,000 held-out test images as the interval curves. MC dropout uses 30 stochastic passes; the ensemble uses five members. Every point comes from that epoch’s frozen checkpoint.";
      accuracyDetails.previousElementSibling.textContent =
        "Held-out reconstruction accuracy at each saved checkpoint. Hover for values.";
    }
  }

  function curveRows(group) {
    return Object.entries(curves?.groups?.[group] || {}).flatMap(
      ([method, rows]) => rows.map((row) => ({ method, ...row })),
    );
  }

  function curveStatus(group) {
    const rows = curveRows(group),
      complete = rows.filter((row) => row.status === "complete").length;
    const failed = rows.filter((row) => row.status === "failed").length;
    return `${complete}/${rows.length} calibrated milestones · ${rows.length - complete - failed} pending${failed ? " · " + failed + " calibration failures" : ""} · full held-out test set`;
  }

  function exp2Curves() {
    return curveRows(window.CAMERA)
      .filter((row) => row.status === "complete")
      .map((row) => ({
        method: row.method === "qutcc" ? "paper_qutcc" : row.method,
        epoch: row.epoch,
        metrics: row.metrics.clipped,
        calibration: row.calibration,
      }));
  }

  function rawDataset(data, study) {
    const group = "raw_" + study;
    status(group, ["qutcc", "im2im"]);
    if (!active) return data;
    const result = structuredClone(data);
    for (const method of ["qutcc", "im2im"]) {
      const entry = entries(group)[method],
        summary = result.studies[study][method];
      summary.metrics = entry?.metrics || null;
      summary.calibration = entry?.calibration || null;
      summary.example_count = 50;
      summary.example_metrics = entry?.per_image.map((row) => row.clipped);
      summary.epoch = entry?.epoch || (study === "clean" ? 50 : 30);
      summary.evaluations = (curves?.groups?.[group]?.[method] || []).map(
        (row) => ({ ...row }),
      );
      summary.history = summary.history.filter(
        (row) => row.epoch <= (study === "clean" ? 50 : 30),
      );
    }
    return result;
  }

  async function rawExample(reference, index, study) {
    if (!active) return reference;
    const output = { ...reference, models: {} };
    await Promise.all(
      Object.entries(entries("raw_" + study)).map(async ([method, entry]) => {
        const packed = await unpack(entry, index);
        checkPair(reference, packed);
        output.models[method] = packed;
      }),
    );
    return output;
  }

  window.Coverage90 = {
    active,
    init,
    entries,
    status,
    curveRows,
    curveStatus,
    exp2Dataset,
    exp2Example,
    exp2Summary,
    exp2Details,
    exp2Curves,
    rawDataset,
    rawExample,
  };
})();
