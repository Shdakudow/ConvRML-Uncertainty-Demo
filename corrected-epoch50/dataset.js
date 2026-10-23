"use strict";
window.CAMERA =
  new URLSearchParams(location.search).get("camera") === "diffuser"
    ? "diffuser"
    : "rml";
(async () => {
  try {
    await window.Coverage90.init();
    const config = await (
      await fetch("assets.json", { cache: "no-store" })
    ).json();
    window.DATA_PATH = config.base + "/data/" + window.CAMERA;
    const response = await fetch(window.DATA_PATH + "/protocol.json");
    if (!response.ok) throw Error("HTTP " + response.status);
    window.DATASET = await response.json();
    const curvesResponse = await fetch("ensemble_curves.json", {
      cache: "no-store",
    });
    if (curvesResponse.ok) {
      const curves = await curvesResponse.json();
      DATASET.history.ensemble10 = curves.cameras[window.CAMERA] || [];
    } else DATASET.history.ensemble10 = [];
    for (const [file, key] of [
      ["ensemble5_curves.json", "ensemble5Curves"],
      ["ensemble_comparison.json", "ensembleComparison"],
      ["interval_curves.json", "intervalCurves"],
    ]) {
      const res = await fetch(file, { cache: "no-store" });
      if (res.ok) window[key] = await res.json();
    }
    DATASET.history.ensemble5 =
      window.ensemble5Curves?.cameras[window.CAMERA] || [];
    if (window.CAMERA === "diffuser") {
      const result = await fetch("normalized_qutcc_results.json", {
        cache: "no-store",
      });
      if (!result.ok)
        throw Error("Normalized QUTCC results HTTP " + result.status);
      window.paperStyleQutcc = await result.json();
      DATASET.history.paper_qutcc = window.paperStyleQutcc.validation;
    }
    const overlayResponse = await fetch("paper_qutcc_assets.json", {
      cache: "no-store",
    });
    if (overlayResponse.ok) {
      const overlays = await overlayResponse.json();
      window.paperQutccAssets = overlays.cameras[window.CAMERA];
      if (window.paperQutccAssets) {
        const q = window.paperQutccAssets;
        if (
          q.epoch !== 50 ||
          JSON.stringify(q.ids) !== JSON.stringify(DATASET.ids)
        )
          throw Error("QUTCC sample IDs or epoch do not match");
        DATASET.methods = DATASET.methods
          .filter((k) => k !== "adaptive_qutcc")
          .concat("paper_qutcc");
        DATASET.epochs.paper_qutcc = 50;
        DATASET.aggregate.paper_qutcc = q.aggregate;
        DATASET.history.paper_qutcc = q.validation_history;
        window.paperStyleQutcc = window.paperStyleQutcc || {
          validation: q.validation_history,
          evaluations: q.evaluations,
        };
      }
    }
    const metricResponse = await fetch("analysis_metrics.json", {
      cache: "no-store",
    });
    if (metricResponse.ok) window.analysisMetrics = await metricResponse.json();
    window.exampleCategories = await (
      await fetch("../example-categories.json", { cache: "no-store" })
    ).json();
    window.Coverage90.exp2Dataset(DATASET, window.CAMERA);
    const app = document.createElement("script");
    app.src = "app.js?v=20261023milestones";
    document.body.append(app);
  } catch (e) {
    document.getElementById("status").textContent =
      "Inference export is not yet published: " + e.message;
  }
})();
