"use strict";
// Inspect saved pixel values on demand without changing model data or inference.
document.addEventListener("click", event => {
  if (event.target instanceof HTMLCanvasElement) {
    const inspector = document.getElementById("pixelInspector");
    if (inspector) inspector.open = true;
  }
});
