/* Click inspection uses numerical sidecars, never colors from PNG/MP4 pixels. */
(() => {
  'use strict';
  const root = new URL('./', document.currentScript.src);
  const cache = new Map();
  let configuration;
  const selectionStrokes = [['#ffffff', 6], ['#07111b', 4], ['#fff200', 2]];

  function selectionBox(x, y, width, height, scale) {
    const size = Math.min(24 / (scale || 1), width, height);
    return {x: Math.max(0, Math.min(width - size, x - size / 2)),
      y: Math.max(0, Math.min(height - size, y - size / 2)), size};
  }

  function drawCanvas(canvas, x, y) {
    const rect = canvas.getBoundingClientRect();
    const scale = Math.min(rect.width / canvas.width, rect.height / canvas.height) || 1;
    const box = selectionBox(x, y, canvas.width, canvas.height, scale);
    const context = canvas.getContext('2d');
    context.save();
    for (const [color, thickness] of selectionStrokes) {
      context.strokeStyle = color; context.lineWidth = thickness / scale;
      context.strokeRect(box.x, box.y, box.size, box.size);
    }
    context.restore();
    canvas.dataset.selectionBox = 'true';
  }

  async function loadMap(path) {
    if (!configuration) configuration = fetch(new URL('pixel_maps.json', root), {cache: 'no-store'})
      .then(response => {if (!response.ok) throw Error(response.status); return response.json();})
      .catch(error => {configuration = null; throw error;});
    const config = await configuration;
    const url = new URL(path, new URL(config.base.replace(/\/$/, '') + '/', root)).href;
    if (cache.has(url)) return cache.get(url);
    const pending = (async () => {
      const response = await fetch(url);
      if (!response.ok) throw Error(response.status);
      const buffer = await new Response(response.body.pipeThrough(new DecompressionStream('gzip'))).arrayBuffer();
      const headerSize = new DataView(buffer).getUint32(0, true);
      const header = JSON.parse(new TextDecoder().decode(new Uint8Array(buffer, 4, headerSize)));
      if (header.version !== 1 || header.encoding !== 'float32-shuffled-le') throw Error('Unexpected pixel map');
      const count = header.width * header.height;
      if (buffer.byteLength !== 4 + headerSize + 4 * count + Math.ceil(count / 8)) throw Error('Incomplete pixel map');
      const shuffled = new Uint8Array(buffer, 4 + headerSize, 4 * count), ordered = new Uint8Array(4 * count);
      for (let byte = 0; byte < 4; byte++) for (let index = 0; index < count; index++) ordered[4 * index + byte] = shuffled[byte * count + index];
      return {...header, assetBase: config.base, values: new DataView(ordered.buffer), crossing: new Uint8Array(buffer, 4 + headerSize + 4 * count)};
    })();
    cache.set(url, pending);
    pending.catch(() => {if (cache.get(url) === pending) cache.delete(url);});
    if (cache.size > 8) cache.delete(cache.keys().next().value);
    return pending;
  }

  function pointAt(element, event, width, height) {
    const rect = element.getBoundingClientRect();
    const scale = Math.min(rect.width / width, rect.height / height);
    const x = (event.clientX - rect.left - (rect.width - width * scale) / 2) / scale;
    const y = (event.clientY - rect.top - (rect.height - height * scale) / 2) / scale;
    return x >= 0 && x < width && y >= 0 && y < height ? {x: Math.floor(x), y: Math.floor(y)} : null;
  }

  function stage(element) {
    if (!element.parentElement.classList.contains('pixel-stage')) {
      const wrapper = document.createElement('div'); wrapper.className = 'pixel-stage';
      element.before(wrapper); wrapper.append(element);
    }
    return element.parentElement;
  }

  function mark(element, points, width, height) {
    const wrapper = stage(element);
    wrapper.querySelector('.pixel-overlay')?.remove();
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('viewBox', `0 0 ${width} ${height}`); svg.classList.add('pixel-overlay');
    svg.setAttribute('aria-hidden', 'true');
    const rect = element.getBoundingClientRect();
    const scale = Math.min(rect.width / width, rect.height / height) || 1;
    svg.innerHTML = points.map(({x, y}) => {
      const box = selectionBox(x, y, width, height, scale);
      const attributes = `x="${box.x}" y="${box.y}" width="${box.size}" height="${box.size}" fill="none" vector-effect="non-scaling-stroke"`;
      return selectionStrokes.map(([color, thickness]) => `<rect ${attributes} stroke="${color}" stroke-width="${thickness}"/>`).join('');
    }).join('');
    wrapper.append(svg);
  }

  function label(element, text) {
    const wrapper = stage(element);
    let output = wrapper.querySelector('.pixel-readout');
    if (!output) {output = document.createElement('output'); output.className = 'pixel-readout'; output.setAttribute('aria-live', 'polite'); wrapper.append(output);}
    for (const key of ['value', 'x', 'y', 'frame', 'crossed']) delete output.dataset[key];
    output.textContent = text;
    return output;
  }

  class Inspector {
    constructor(container) {this.container = container; this.version = 0;}
    clear() {
      this.version++;
      this.container.querySelectorAll('.pixel-overlay,.pixel-readout').forEach(node => node.remove());
    }
    async show({x, y, frame, targets}) {
      const version = ++this.version;
      const prefix = `${frame ? 'Frame '+frame+' · ' : ''}(${x}, ${y}) · `;
      targets.forEach(target => label(target.element, prefix + 'Loading…'));
      await Promise.all(targets.map(async target => {
        try {
          const map = await loadMap(target.path);
          if (version !== this.version) return;
          if (x >= map.width || y >= map.height) throw Error('Pixel outside map');
          const index = y * map.width + x, value = map.values.getFloat32(4 * index, true);
          const crossed = Boolean(map.crossing[index >> 3] & (1 << (7 - (index & 7))));
          const output = label(target.element, prefix + `Width ${value.toFixed(6)}${crossed ? ' · Crossed bounds' : ''}`);
          Object.assign(output.dataset, {value, x, y, frame: frame || '', crossed});
        } catch (_) {
          if (version === this.version) label(target.element, prefix + 'Unavailable. Click to retry.');
        }
      }));
    }
  }
  window.HeatmapPixels = {Inspector, pointAt, mark, drawCanvas, loadMap};
})();
