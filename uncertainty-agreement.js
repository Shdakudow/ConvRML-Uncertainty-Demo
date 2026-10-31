/* Inter-model agreement: no ground truth, reconstruction error, or calibration fit. */
(() => {
  'use strict';
  const root = new URL('./', document.currentScript.src);
  const palette = [[20,35,60],[34,95,157],[35,185,172],[243,203,85],[250,112,82]];
  const format = value => Number.isFinite(value) ? value.toFixed(5) : 'Undefined';
  let metadata;

  function load() {
    if (!metadata) metadata = Promise.all(['uncertainty_agreement.json','pixel_maps.json'].map(async name => {
      const response = await fetch(new URL(name, root), {cache: 'no-store'});
      if (!response.ok) throw Error(response.status);
      return response.json();
    })).then(([agreement, pixels]) => {
      if (agreement.pixel_asset_base !== pixels.base) throw Error('Agreement/pixel export mismatch');
      return agreement;
    }).catch(error => {metadata = null; throw error;});
    return metadata;
  }

  function percentileRanks(values, valid) {
    const sorted = [...valid].sort((a, b) => values[a] - values[b]);
    const result = new Float32Array(values.length); result.fill(NaN);
    for (let start = 0; start < sorted.length;) {
      let end = start + 1;
      while (end < sorted.length && values[sorted[end]] === values[sorted[start]]) end++;
      const rank = (start + end - 1) / (2 * Math.max(1, sorted.length - 1));
      for (let index = start; index < end; index++) result[sorted[index]] = rank;
      start = end;
    }
    return result;
  }

  function differences(q, i) {
    if (q.width !== i.width || q.height !== i.height) throw Error('Map shape mismatch');
    const count = q.width * q.height, a = new Float32Array(count), b = new Float32Array(count);
    const widthGap = new Float32Array(count); widthGap.fill(NaN);
    const valid = [];
    let minA = Infinity, maxA = -Infinity, minB = Infinity, maxB = -Infinity;
    for (let p = 0; p < count; p++) {
      a[p] = q.values.getFloat32(p * 4, true); b[p] = i.values.getFloat32(p * 4, true);
      const crossed = (q.crossing[p >> 3] | i.crossing[p >> 3]) & (1 << (7 - (p & 7)));
      if (!crossed && Number.isFinite(a[p]) && Number.isFinite(b[p])) {
        valid.push(p); widthGap[p] = Math.abs(a[p] - b[p]);
        minA = Math.min(minA, a[p]); maxA = Math.max(maxA, a[p]); minB = Math.min(minB, b[p]); maxB = Math.max(maxB, b[p]);
      }
    }
    const rankGap = new Float32Array(count); rankGap.fill(NaN);
    if (valid.length >= 2 && minA < maxA && minB < maxB) {
      const rankA = percentileRanks(a, valid), rankB = percentileRanks(b, valid);
      for (const p of valid) rankGap[p] = Math.abs(rankA[p] - rankB[p]);
    }
    return {widthGap, rankGap, validCount: valid.length, width: q.width, height: q.height};
  }

  class Panel {
    constructor(container, onPick, extraRegionButtons = []) {
      this.container = container; this.onPick = onPick; this.version = 0;
      container.innerHTML = '<h2>Where uncertainty maps disagree</h2><p class="agreement-title"></p><div class="agreement-layout"><figure><canvas class="agreement-map" width="480" height="270" aria-label="Difference between the two uncertainty maps"></canvas><figcaption class="agreement-map-label"></figcaption><div class="map-key"><span class="gradient"></span><span>0 → 1</span><span>Magenta: excluded crossed bounds</span></div><output class="agreement-pixel"></output></figure><div><div class="agreement-controls"><label>Difference <select class="agreement-mode"><option value="rank">Spatial uncertainty ranking</option><option value="width">Absolute interval width</option></select></label><button class="agreement-region" disabled>Inspect largest rank gap</button></div><div class="table-wrap"><table><thead><tr><th>Pearson r</th><th>Spearman ρ</th><th>Mean |width gap|</th></tr></thead><tbody class="agreement-metrics"></tbody></table></div><p class="agreement-status hint" role="status"></p><p class="hint">Agreement between models, not reconstruction accuracy. Click the map to inspect both models at that pixel.</p></div></div>';
      this.canvas = container.querySelector('canvas');
      this.mode = container.querySelector('select');
      this.status = container.querySelector('.agreement-status');
      this.regionButton = container.querySelector('.agreement-region');
      this.regionButtons = [this.regionButton, ...extraRegionButtons];
      this.mode.onchange = () => this.draw();
      this.canvas.onclick = event => {
        if (this.container.getAttribute('aria-busy') === 'true' || !this.maps) return;
        const point = HeatmapPixels.pointAt(this.canvas, event, this.maps.width, this.maps.height);
        if (point) this.pick(point);
      };
      const inspectRegion = () => {
        const region = this.row?.region;
        if (region) this.pick({x: region.x + Math.floor(region.width / 2), y: region.y + Math.floor(region.height / 2)});
      };
      for (const button of this.regionButtons) {
        button.onclick = inspectRegion;
        button.title = 'Select the center of the 30 × 30 patch with the largest mean absolute percentile-rank difference';
      }
    }

    enableRegionButtons(enabled) {for (const button of this.regionButtons) button.disabled = !enabled;}

    pick(point) {this.point = point; this.draw(); this.onPick(point);}

    suspend(message) {
      this.version++; this.container.hidden = false; this.container.setAttribute('aria-busy', 'true');
      this.status.textContent = message; this.enableRegionButtons(false);
      this.container.querySelector('.agreement-title').textContent = '';
      this.container.querySelector('.agreement-metrics').replaceChildren();
      this.container.querySelector('.agreement-pixel').textContent = '';
    }

    async show({key, title, paths, row, point = null}) {
      const version = ++this.version;
      this.container.hidden = false; this.row = row; this.point = point;
      this.container.querySelector('.agreement-title').textContent = title;
      this.container.querySelector('.agreement-metrics').innerHTML = '<tr>'+[row.pearson,row.spearman,row.mean_absolute_width_gap].map(value => '<td>'+format(value)+'</td>').join('')+'</tr>';
      if (this.loadedKey !== key || !this.maps) {
        this.container.setAttribute('aria-busy', 'true'); this.enableRegionButtons(false);
        this.status.textContent = 'Loading numerical width maps…';
        try {
          const [agreement, q, i] = await Promise.all([load(), HeatmapPixels.loadMap(paths.qutcc), HeatmapPixels.loadMap(paths.im2im)]);
          if (version !== this.version) return;
          if (q.assetBase !== agreement.pixel_asset_base || i.assetBase !== agreement.pixel_asset_base) throw Error('Pixel export changed');
          this.maps = differences(q, i);
          if (this.maps.validCount !== row.valid_pixels) throw Error('Agreement mask changed');
          this.loadedKey = key;
        } catch (_) {
          if (version === this.version) {this.status.textContent = 'Disagreement maps unavailable. Select the frame or image again to retry.'; this.maps = null;}
          return;
        }
      }
      if (version !== this.version) return;
      this.container.setAttribute('aria-busy', 'false'); this.enableRegionButtons(Boolean(row.region));
      this.status.textContent = `${row.valid_pixels.toLocaleString()} jointly valid pixels · lower correlation means less spatial agreement.`;
      this.draw();
    }

    draw() {
      if (!this.maps) return;
      const rank = this.mode.value === 'rank', values = rank ? this.maps.rankGap : this.maps.widthGap;
      const context = this.canvas.getContext('2d'), image = context.createImageData(this.maps.width, this.maps.height);
      for (let p = 0; p < values.length; p++) {
        const value = values[p];
        let rgb = [227,32,201];
        if (Number.isFinite(value)) {
          const t = Math.min(1, Math.max(0, value)) * 4, k = Math.min(3, Math.floor(t)), weight = t - k;
          rgb = palette[k].map((a, c) => Math.round(a * (1 - weight) + palette[k+1][c] * weight));
        }
        for (let c = 0; c < 3; c++) image.data[4*p+c] = rgb[c];
        image.data[4*p+3] = 255;
      }
      context.putImageData(image, 0, 0);
      this.container.querySelector('.agreement-map-label').textContent = rank ? 'Difference in uncertainty percentile rank · 0–1' : '|QUTCC width − Im2im width| · normalized intensity';
      const output = this.container.querySelector('.agreement-pixel'); output.textContent = '';
      if (this.point) {
        HeatmapPixels.drawCanvas(this.canvas, this.point.x + .5, this.point.y + .5);
        const p = this.point.y * this.maps.width + this.point.x;
        output.textContent = `(${this.point.x}, ${this.point.y}) · rank gap ${format(this.maps.rankGap[p])} · width gap ${format(this.maps.widthGap[p])}`;
      }
    }
  }
  window.UncertaintyAgreement = {load, Panel, differences, format};
})();
