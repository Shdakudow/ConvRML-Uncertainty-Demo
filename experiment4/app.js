/* Browse verified results by category. Images are loaded for the active tab only. */
(() => {
  "use strict";
  const arms = [
    "qutcc_clean50",
    "qutcc_general100",
    "im2im_clean50",
    "im2im_general100",
  ];
  const labels = {
    qutcc_clean50: "QUTCC · clean · 50 epochs",
    qutcc_general100: "QUTCC · generalized · 100 epochs",
    im2im_clean50: "Im2im · clean · 50 epochs",
    im2im_general100: "Im2im · generalized · 100 epochs",
  };
  const metrics = [
    ["psnr", "PSNR (dB)"],
    ["ssim", "SSIM"],
    ["mae", "MAE"],
    ["coverage", "Coverage"],
    ["width", "Width"],
    ["crossing", "Crossing"],
  ];
  const tabLabels = {
    clean: "Clean",
    gaussian: "Gaussian",
    poisson: "Poisson",
    poisson_gaussian: "Poisson + Gaussian",
    exposure_050: "Half exposure",
    exposure_150: "Higher exposure",
    dead_pixels: "Dead pixels",
    fixed_pattern: "Uneven pixel response",
    gaussian_blur: "Blur",
    resolution: "Resolution",
    jpeg: "JPEG",
  };
  let data, errorData,
    index = 0,
    activeTab = "overview";
  let patchInspector;
  const cards = new Map();
  const buttons = new Map();
  const el = (tag, text, className) => {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    if (className) node.className = className;
    return node;
  };
  const asset = (path) => new URL(path, new URL(data.base, location.href)).href;
  function updateToolbarOffset() {
    const height = document.querySelector(".workspace-toolbar").getBoundingClientRect().height;
    document.documentElement.style.setProperty("--toolbar-height", `${height + 14}px`);
  }
  const number = (key, value) => {
    if (!Number.isFinite(value)) return "—";
    return key === "coverage" || key === "crossing"
      ? `${(100 * value).toFixed(2)}%`
      : value.toFixed(key === "psnr" ? 2 : 4);
  };

  function figure(label, kind, arm) {
    const node = el(
      "figure",
      undefined,
      kind === "target" ? "target-reference" : "",
    );
    node.append(el("figcaption", label));
    const image = el("img");
    image.alt = label;
    image.width = 480;
    image.height = 270;
    image.loading = "lazy";
    image.decoding = "async";
    image.dataset.kind = kind;
    if (arm) image.dataset.arm = arm;
    image.addEventListener("error", () => {
      image.alt = `${label} · image unavailable`;
    });
    if (["target", "prediction", "error", "width"].includes(kind)) {
      const viewport = el("div", undefined, "patch-viewport");
      viewport.append(image);
      node.append(viewport);
    } else node.append(image);
    return node;
  }

  function pairs(kind = "prediction") {
    const grid = el("div", undefined, `model-grid${kind === "width" ? " maps" : kind === "error" ? " errors" : " reconstructions"}`);
    for (const method of ["qutcc", "im2im"]) {
      const pair = el("div", undefined, "pair");
      pair.append(el("h3", method === "qutcc" ? "QUTCC" : "Im2im"));
      const images = el("div", undefined, "pair-images");
      images.append(
        figure(
          "Clean-trained · 50 epochs",
          kind,
          `${method}_clean50`,
        ),
      );
      images.append(
        figure(
          "Generalized · 100 epochs",
          kind,
          `${method}_general100`,
        ),
      );
      pair.append(images);
      grid.append(pair);
    }
    return grid;
  }

  function table(condition, mean, sceneIndex = index) {
    const wrapper = el("div", undefined, "table-scroll");
    const t = el("table");
    t.setAttribute(
      "aria-label",
      `${condition.title}: ${mean ? "all test scenes" : data.ids[sceneIndex]} metrics`,
    );
    const head = el("thead"),
      tr = el("tr");
    tr.append(el("th", "Model"));
    for (const [, label] of metrics) tr.append(el("th", label));
    head.append(tr);
    t.append(head);
    const body = el("tbody");
    for (const arm of arms) {
      const row = el("tr");
      row.append(el("th", labels[arm]));
      const results = data.results[condition.id].arms[arm];
      const values = mean ? results.mean : results.examples[sceneIndex];
      for (const [key] of metrics)
        row.append(el("td", number(key, values[key])));
      body.append(row);
    }
    t.append(body);
    wrapper.append(t);
    return wrapper;
  }

  function appendUncertainty(card) {
    const section = el("section", undefined, "uncertainty-section");
    section.append(el("h3", "Uncertainty maps", "map-title"), pairs("width"));
    const legend = el("div", undefined, "legend");
    legend.append(
      el("span", "Narrow 0"),
      el("span", undefined, "gradient"),
      el("span", "Wide 1"),
      el("span", "Pink = crossed bounds", "pink"),
    );
    section.append(
      legend,
      el(
        "p",
        "Mean RGB interval width; the same color scale is used for every model and scene.",
        "caption",
      ),
    );
    section.append(el("div", undefined, "scene-metrics"));
    card.append(section);
  }

  function renderMetrics(card, condition) {
    const content = card.querySelector(".scene-metrics");
    content.replaceChildren();
    content.append(
      el("h4", `Full-scene metrics · ${data.ids[index]}`, "table-title"),
      table(condition, false),
    );
    content.append(
      el("h4", "Mean across all 2,000 test scenes", "table-title"),
      table(condition, true),
    );
    content.append(
      el("h4", "Calibration on the shared 3,000-scene mixture", "table-title"),
    );
    const list = el("ul", undefined, "calibration");
    for (const arm of arms) {
      const fit = data.calibration[arm];
      const failed = fit.status !== "fitted" || !fit.target_met;
      const text = `${labels[arm]}: ${(100 * fit.calibration_coverage).toFixed(2)}% overall coverage${failed ? ` · ${fit.failure || "90% target not met"}` : ""}.`;
      list.append(el("li", text, failed ? "failed" : ""));
    }
    content.append(list);
  }

  function imageUrl(kind, condition, sceneIndex, arm) {
    const stem = String(sceneIndex).padStart(3, "0");
    let path;
    if (kind === "original" || kind === "target")
      path = `images/shared/${stem}-${kind}.png`;
    else if (kind === "input")
      path = condition.id === "clean"
        ? `images/shared/${stem}-original.png`
        : `images/${condition.id}/${stem}-input.png`;
    else path = `images/${condition.id}/${arm}/${stem}-${kind}.png`;
    return kind === "error"
      ? new URL(`errors/${condition.id}/${arm}/${stem}.png`, new URL(errorData.base, location.href)).href
      : asset(path);
  }

  function loadImages(card, condition, sceneIndex = index) {
    for (const image of card.querySelectorAll("img")) {
      const url = imageUrl(image.dataset.kind, condition, sceneIndex, image.dataset.arm);
      if (image.src !== url) image.src = url;
    }
  }

  function appendErrors(card) {
    const legend = el("div", undefined, "legend");
    legend.append(el("span", "Low error 0"), el("span", undefined, "gradient"), el("span", "High error 1"));
    card.append(
      el("h3", "Absolute reconstruction error", "error-title"),
      pairs("error"),
      legend,
      el("p", "Mean RGB |reconstruction − ground truth|, computed before display quantization. The same 0–1 scale is used for every model and condition.", "caption"),
    );
  }

  function buildCard(condition) {
    const card = el("section", undefined, "condition");
    card.id = `panel-${condition.id}`;
    card.append(
      el("h2", condition.title),
      el("p", condition.description, "explanation"),
    );
    const clean = condition.id === "clean";
    const inputs = el("div", undefined, `inputs${clean ? " two-inputs" : ""}`);
    inputs.append(figure("Original sensor input", "original"));
    if (!clean) inputs.append(figure("Modified sensor input", "input"));
    inputs.append(figure("Ground truth · reference", "target"));
    card.append(inputs, el("code", condition.formula, "formula"), pairs());
    appendErrors(card);
    appendUncertainty(card);
    return card;
  }

  function overviewTable() {
    const t = el("table", undefined, "overview-table");
    t.setAttribute("aria-label", "Mean test metrics by input category");
    const head = el("thead"),
      tr = el("tr");
    tr.append(el("th", "Input category"));
    for (const arm of arms) tr.append(el("th", labels[arm]));
    head.append(tr);
    t.append(head);
    const body = el("tbody");
    const key = document.getElementById("overview-metric").value;
    for (const condition of data.conditions) {
      const row = el("tr"),
        label = el("th");
      const button = el("button", condition.title, "condition-link");
      button.type = "button";
      button.addEventListener("click", () => {
        selectTab(condition.id, true);
        document
          .getElementById("tab-panels")
          .scrollIntoView({ block: "start" });
      });
      label.append(button);
      row.append(label);
      for (const arm of arms)
        row.append(
          el("td", number(key, data.results[condition.id].arms[arm].mean[key])),
        );
      body.append(row);
    }
    t.append(body);
    document.getElementById("overview-table").replaceChildren(t);
  }

  function buildOverview() {
    const card = el("section", undefined, "condition overview");
    card.id = "panel-overview";
    card.append(
      el("h2", "Overview"),
      el(
        "p",
        "Clean input preview and results across every input category.",
        "explanation",
      ),
    );
    const inputs = el("div", undefined, "inputs two-inputs");
    inputs.append(
      figure("Original sensor input", "original"),
      figure("Ground truth · reference", "target"),
    );
    card.append(inputs, pairs());
    appendErrors(card);
    appendUncertainty(card);
    card.append(document.getElementById("learningCurves"));
    const heading = el("div", undefined, "overview-heading");
    const title = el("div");
    title.append(
      el("h3", "Across input categories"),
      el("p", "Mean across all 2,000 test scenes per category.", "caption"),
    );
    const label = el("label", "Metric");
    const select = el("select");
    select.id = "overview-metric";
    select.setAttribute("aria-label", "Overview metric");
    for (const [key, text] of metrics) {
      const option = el("option", text);
      option.value = key;
      option.selected = key === "ssim";
      select.append(option);
    }
    select.addEventListener("change", overviewTable);
    label.append(select);
    heading.append(title, label);
    const table = el("div", undefined, "table-scroll");
    table.id = "overview-table";
    card.append(heading, table);
    return card;
  }

  function updateURL(push = false) {
    const url = new URL(location.href);
    url.searchParams.set("example", String(index));
    url.searchParams.set("condition", activeTab);
    for (const key of ["view", "batchSize", "batchKind"]) url.searchParams.delete(key);
    if (patchInspector?.value) url.searchParams.set("patch", patchInspector.value);
    else url.searchParams.delete("patch");
    url.hash = "";
    if (url.href !== location.href)
      history[push ? "pushState" : "replaceState"](null, "", url);
    window.syncDemoNavigation?.();
  }

  function render() {
    document.getElementById("scene").value = String(index);
    document.getElementById("counter").textContent =
      `${index + 1} / ${data.ids.length}`;
    document.getElementById("previous").disabled = index === 0;
    document.getElementById("next").disabled = index === data.ids.length - 1;
    for (const [id, card] of cards) {
      const selected = id === activeTab;
      card.hidden = !selected;
      const button = buttons.get(id);
      button.setAttribute("aria-selected", String(selected));
      button.tabIndex = selected ? 0 : -1;
    }
    updateToolbarOffset();
    const condition =
      data.conditions.find((item) => item.id === activeTab) ||
      data.conditions.find((item) => item.id === "clean");
    const card = cards.get(activeTab);
    loadImages(card, condition);
    renderMetrics(card, condition);
    patchInspector.setScene({card, reference: imageUrl("target", condition, index), title: `${condition.title} · ${data.ids[index]}`});
  }

  function selectTab(id, push = false) {
    if (!cards.has(id)) id = "overview";
    activeTab = id;
    render();
    buttons.get(id).scrollIntoView({ block: "nearest", inline: "nearest" });
    updateURL(push);
  }

  function readURL() {
    const url = new URL(location.href);
    index = Math.max(
      0,
      Math.min(
        data.ids.length - 1,
        Number.parseInt(url.searchParams.get("example"), 10) || 0,
      ),
    );
    const candidate =
      url.searchParams.get("condition") || url.hash.slice(1) || "overview";
    activeTab = cards.has(candidate) ? candidate : "overview";
    patchInspector.readURL(url.searchParams.get("patch"));
  }

  function addTab(id, label, card) {
    const button = el("button", label);
    button.type = "button";
    button.id = `tab-${id}`;
    button.dataset.category = id;
    button.setAttribute("role", "tab");
    button.setAttribute("aria-controls", card.id);
    button.addEventListener("click", () => selectTab(id, id !== activeTab));
    button.addEventListener("keydown", (event) => {
      const ids = [...buttons.keys()];
      let next = ids.indexOf(id);
      if (event.key === "ArrowRight") next = (next + 1) % ids.length;
      else if (event.key === "ArrowLeft")
        next = (next + ids.length - 1) % ids.length;
      else if (event.key === "Home") next = 0;
      else if (event.key === "End") next = ids.length - 1;
      else return;
      event.preventDefault();
      selectTab(ids[next], true);
      buttons.get(ids[next]).focus({ preventScroll: true });
    });
    card.setAttribute("role", "tabpanel");
    card.setAttribute("aria-labelledby", button.id);
    card.tabIndex = 0;
    card.hidden = true;
    cards.set(id, card);
    buttons.set(id, button);
    document.getElementById("category-tabs").append(button);
    document.getElementById("tab-panels").append(card);
  }

  async function start() {
    const response = await fetch("data.json");
    if (!response.ok)
      throw new Error(`Results could not be loaded (${response.status})`);
    data = await response.json();
    // Keep the stored condition ID and scientific results intact.
    const pixelResponse = data.conditions.find(condition => condition.id === "fixed_pattern");
    pixelResponse.title = "Uneven pixel response";
    pixelResponse.description = "Make some pixels slightly more or less sensitive, with small brightness offsets.";
    const errorResponse = await fetch("error-maps.json");
    if (!errorResponse.ok) throw new Error("Absolute-error maps could not be loaded");
    errorData = await errorResponse.json();
    if (errorData.schema !== "exp4_error_maps_v1" || JSON.stringify(errorData.ids) !== JSON.stringify(data.ids))
      throw new Error("Absolute-error export does not match these test scenes");
    if (
      data.schema !== "experiment4-v1" ||
      !data.ids.length ||
      !data.conditions.some((condition) => condition.id === "clean")
    )
      throw new Error("Incomplete experiment data");
    const scenes = document.getElementById("scene");
    patchInspector = new PatchInspector(document.getElementById("patchInspector"), () => updateURL());
    data.ids.forEach((id, i) => {
      const option = el("option", `${i + 1} · ${id}`);
      option.value = String(i);
      scenes.append(option);
    });
    addTab("overview", "Overview", buildOverview());
    for (const condition of data.conditions)
      addTab(
        condition.id,
        tabLabels[condition.id] || condition.title,
        buildCard(condition),
      );
    overviewTable();
    scenes.addEventListener("change", () => {
      index = Number(scenes.value);
      render();
      updateURL();
    });
    document.getElementById("previous").addEventListener("click", () => {
      if (index > 0) {
        index--;
        render();
        updateURL();
      }
    });
    document.getElementById("next").addEventListener("click", () => {
      if (index < data.ids.length - 1) {
        index++;
        render();
        updateURL();
      }
    });
    window.addEventListener("popstate", () => {
      readURL();
      render();
    });
    window.addEventListener("hashchange", () => {
      readURL();
      selectTab(location.hash.slice(1));
    });
    readURL();
    document.getElementById("status").hidden = true;
    document.getElementById("experiment").hidden = false;
    selectTab(activeTab);
    if ("ResizeObserver" in window) new ResizeObserver(updateToolbarOffset).observe(document.querySelector(".workspace-toolbar"));
  }
  start().catch((error) => {
    document.getElementById("status").textContent = error.message;
  });
})();
