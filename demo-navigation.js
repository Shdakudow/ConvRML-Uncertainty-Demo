/* Shared experiment order; preserve the current scene when changing pages. */
(() => {
  const root = new URL("./", document.currentScript.src);
  const routes = {
    legacy: "./",
    current: "corrected-epoch50/",
    raw: "raw-diffusercam/",
    captures: "named-captures/",
    videos: "videos-plot/",
    exp4: "experiment4/",
    brightness: "test-image-intensified-1/",
    earlier: "corrected-latest/",
  };
  const navigation = [
    ["legacy", "Exp 1"],
    ["current", "Exp 2"],
    ["raw", "Exp 3"],
    ["captures", "Named pictures"],
    ["videos", "Video plot"],
    ["exp4", "Exp 4"],
  ];
  function sync() {
    const nav = document
      .querySelector('header nav [data-demo-route="legacy"]')
      ?.closest("nav");
    if (nav) {
      for (const [route, label] of navigation) {
        let link = nav.querySelector(`[data-demo-route="${route}"]`);
        if (!link) {
          link = document.createElement("a");
          link.dataset.demoRoute = route;
        }
        link.textContent = label;
        if (new URL(routes[route], root).pathname === location.pathname)
          link.setAttribute("aria-current", "page");
        else link.removeAttribute("aria-current");
        nav.append(link);
      }
    }
    const state = new URLSearchParams(location.search);
    const camera =
      state.get("camera") || document.getElementById("camera")?.value;
    if (camera === "rml" || camera === "diffuser") state.set("camera", camera);
    for (const link of document.querySelectorAll("[data-demo-route]")) {
      const target = new URL(routes[link.dataset.demoRoute], root);
      for (const key of [
        "camera",
        "ensemble",
        "example",
        "gain",
        "study",
        "capture",
        "bounds",
      ]) {
        if (state.has(key)) target.searchParams.set(key, state.get(key));
      }
      link.href = target.href;
    }
  }
  window.syncDemoNavigation = sync;
  document.addEventListener("DOMContentLoaded", sync);
  document.addEventListener(
    "click",
    (event) => {
      if (event.target.closest("[data-demo-route]")) sync();
    },
    true,
  );
  window.addEventListener("pageshow", sync);
  window.addEventListener("popstate", sync);
})();
