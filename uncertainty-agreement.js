/* Compare frozen uncertainty maps on jointly finite, uncrossed spatial pixels. */
(() => {
  'use strict';
  const root = new URL('./', document.currentScript.src);
  const palette = [[20,35,60],[34,95,157],[35,185,172],[243,203,85],[250,112,82]];
  const overlapColors = [[16,23,34],[0,190,255],[255,112,0],[240,240,240]];
  const format = value => Number.isFinite(value) ? value.toFixed(5) : 'Undefined';
  const percent = value => Number.isFinite(value) ? `${(100 * value).toFixed(2)}%` : 'Undefined';
  let metadata, comparison = 'overlap';

  function getMode() {return comparison;}
  function setMode(value) {
    if (!['spearman', 'overlap'].includes(value)) throw Error('Unknown comparison');
    if (value === comparison) return;
    comparison = value;
    window.dispatchEvent(new CustomEvent('uncertaintycomparisonchange', {detail: {mode: value}}));
  }

  function load() {
    if (!metadata) metadata = Promise.all(['uncertainty_agreement.json','pixel_maps.json'].map(async name => {
      const response = await fetch(new URL(name, root), {cache: 'no-store'});
      if (!response.ok) throw Error(response.status);
      return response.json();
    })).then(([agreement, pixels]) => {
      if (agreement.protocol !== 'intermodel_rgb_width_agreement_v2' || agreement.pixel_asset_base !== pixels.base) throw Error('Agreement/pixel export mismatch');
      return agreement;
    }).catch(error => {metadata = null; throw error;});
    return metadata;
  }

  function ranked(values, valid) {
    const sorted = [...valid].sort((a, b) => values[a] - values[b]);
    const ranks = new Float32Array(values.length); ranks.fill(NaN);
    for (let start = 0; start < sorted.length;) {
      let end = start + 1;
      while (end < sorted.length && values[sorted[end]] === values[sorted[start]]) end++;
      const rank = (start + end - 1) / (2 * Math.max(1, sorted.length - 1));
      for (let index = start; index < end; index++) ranks[sorted[index]] = rank;
      start = end;
    }
    const position = .9 * (sorted.length - 1), low = Math.floor(position), high = Math.ceil(position);
    const lower = values[sorted[low]], upper = values[sorted[high]];
    return {ranks, cutoff: lower + (upper - lower) * (position - low), constant: values[sorted[0]] === values[sorted.at(-1)]};
  }

  function differences(q, i) {
    if (q.width !== i.width || q.height !== i.height) throw Error('Map shape mismatch');
    const count = q.width * q.height, a = new Float32Array(count), b = new Float32Array(count);
    const widthGap = new Float32Array(count); widthGap.fill(NaN);
    const rankGap = new Float32Array(count); rankGap.fill(NaN);
    const overlapClasses = new Uint8Array(count); overlapClasses.fill(255);
    const valid = [];
    for (let p = 0; p < count; p++) {
      a[p] = q.values.getFloat32(p * 4, true); b[p] = i.values.getFloat32(p * 4, true);
      const crossed = (q.crossing[p >> 3] | i.crossing[p >> 3]) & (1 << (7 - (p & 7)));
      if (!crossed && Number.isFinite(a[p]) && Number.isFinite(b[p])) {
        valid.push(p); widthGap[p] = Math.abs(a[p] - b[p]); overlapClasses[p] = 0;
      }
    }
    const top10 = {top10_iou: null, top10_intersection: 0, top10_union: 0, top10_qutcc_count: 0, top10_im2im_count: 0, top10_threshold_qutcc: null, top10_threshold_im2im: null, top10_valid_pixels: valid.length, top10_reason: null};
    if (valid.length < 2) top10.top10_reason = 'Fewer than two jointly valid pixels';
    else {
      const first = ranked(a, valid), second = ranked(b, valid);
      if (first.constant || second.constant) top10.top10_reason = 'A constant map has no distinct most-uncertain pixels';
      else {
        top10.top10_threshold_qutcc = first.cutoff; top10.top10_threshold_im2im = second.cutoff;
        for (const p of valid) {
          rankGap[p] = Math.abs(first.ranks[p] - second.ranks[p]);
          const code = (a[p] >= first.cutoff ? 1 : 0) | (b[p] >= second.cutoff ? 2 : 0);
          overlapClasses[p] = code;
          if (code & 1) top10.top10_qutcc_count++;
          if (code & 2) top10.top10_im2im_count++;
          if (code === 3) top10.top10_intersection++;
          if (code) top10.top10_union++;
        }
        top10.top10_iou = top10.top10_intersection / top10.top10_union;
      }
    }
    return {widthGap, rankGap, overlapClasses, top10, validCount: valid.length, width: q.width, height: q.height};
  }

  class Panel {
    constructor(container, onPick, extraRegionButtons = []) {
      this.container = container; this.onPick = onPick; this.version = 0;
      container.innerHTML = `
        <h2 class="agreement-heading">Most uncertain 10% of pixels</h2><p class="agreement-title"></p>
        <div class="agreement-layout"><figure>
          <canvas class="agreement-map" width="480" height="270" aria-label="Spatial comparison of the two uncertainty maps"></canvas>
          <video class="agreement-playback" playsinline muted preload="metadata" hidden aria-label="Spatial uncertainty comparison during playback"></video>
          <figcaption class="agreement-map-label"></figcaption>
          <div class="map-key agreement-rank-key"><span class="gradient"></span><span>0 → 1</span><span>Magenta: excluded crossed bounds</span></div>
          <div class="agreement-overlap-key"><span class="both">Both in top 10%</span><span class="q-only">QUTCC top 10% only</span><span class="i-only">Im2im top 10% only</span><span class="neither">Neither in top 10%</span><span class="excluded">Excluded</span></div>
          <output class="agreement-pixel"></output>
        </figure><div>
          <div class="agreement-controls">
            <label>Comparison <select class="agreement-comparison"><option value="spearman">Spearman correlation</option><option value="overlap">Overlap · most uncertain 10% of pixels</option></select></label>
            <label class="agreement-difference-control">Difference <select class="agreement-mode"><option value="rank">Spatial uncertainty ranking</option><option value="width">Absolute interval width</option></select></label>
            <button class="agreement-region" disabled>Inspect largest rank gap</button>
          </div>
          <div class="table-wrap"><table><thead class="agreement-metric-head"></thead><tbody class="agreement-metrics"></tbody></table></div>
          <p class="agreement-status hint" role="status"></p>
          <p class="agreement-explanation hint"></p>
          <p class="hint">Agreement between models, not reconstruction accuracy. Click the map to inspect both models at that pixel.</p>
        </div></div>`;
      this.canvas = container.querySelector('canvas');
      this.playbackVideo = container.querySelector('.agreement-playback');
      this.playing = false;
      this.mode = container.querySelector('.agreement-mode');
      this.comparison = container.querySelector('.agreement-comparison');
      this.status = container.querySelector('.agreement-status');
      this.regionButton = container.querySelector('.agreement-region');
      this.regionButtons = [this.regionButton, ...extraRegionButtons];
      this.mode.onchange = () => {
        this.draw();
        window.dispatchEvent(new CustomEvent('uncertaintydifferencechange', {detail: {container: this.container}}));
      };
      this.comparison.onchange = () => setMode(this.comparison.value);
      window.addEventListener('uncertaintycomparisonchange', () => this.renderComparison());
      this.canvas.onclick = event => {
        if (this.container.getAttribute('aria-busy') === 'true' || !this.maps) return;
        const point = HeatmapPixels.pointAt(this.canvas, event, this.maps.width, this.maps.height);
        if (point) this.pick(point);
      };
      for (const button of this.regionButtons) {
        button.onclick = () => {
          const region = this.row?.region;
          if (region && getMode() === 'spearman') this.pick({x: region.x + Math.floor(region.width / 2), y: region.y + Math.floor(region.height / 2)});
        };
        button.title = 'Select the center of the 30 × 30 patch with the largest mean absolute percentile-rank difference';
      }
      this.renderComparison();
    }

    enableRegionButtons(enabled) {
      for (const button of this.regionButtons) {
        button.hidden = getMode() === 'overlap';
        button.disabled = !enabled || getMode() === 'overlap' || this.playing;
      }
    }

    renderComparison() {
      const overlap = getMode() === 'overlap';
      const live = this.playing && Boolean(this.playbackVideo.getAttribute('src'));
      this.canvas.hidden = this.playing;
      this.playbackVideo.hidden = !live;
      if (this.playing) this.container.setAttribute('aria-busy', live ? 'false' : 'true');
      this.comparison.value = getMode();
      this.container.querySelector('.agreement-heading').textContent = overlap ? 'Most uncertain 10% of pixels' : 'Where uncertainty maps disagree';
      this.container.querySelector('.agreement-difference-control').hidden = overlap;
      this.container.querySelector('.agreement-rank-key').hidden = overlap;
      this.container.querySelector('.agreement-overlap-key').hidden = !overlap;
      const headings = overlap ? ['Overlap (IoU)', 'Shared pixels', 'QUTCC selected', 'Im2im selected'] : ['Spearman ρ', 'Pearson r', 'Mean |width gap|'];
      this.container.querySelector('.agreement-metric-head').innerHTML = '<tr>'+headings.map(label => '<th>'+label+'</th>').join('')+'</tr>';
      const values = this.row ? (overlap ? [percent(this.row.top10_iou), this.row.top10_intersection.toLocaleString(), this.row.top10_qutcc_count.toLocaleString(), this.row.top10_im2im_count.toLocaleString()] : [format(this.row.spearman), format(this.row.pearson), format(this.row.mean_absolute_width_gap)]) : [];
      this.container.querySelector('.agreement-metrics').innerHTML = values.length ? '<tr>'+values.map(value => '<td>'+value+'</td>').join('')+'</tr>' : '';
      this.container.querySelector('.agreement-explanation').textContent = overlap ? 'Select values at or above each map’s 90th percentile. Overlap = shared pixels ÷ pixels selected by either model. 0% means no overlap; 100% means the same locations. Cutoff ties stay together, so the selected count can exceed 10%. Constant maps are undefined. Whole frame; no foreground mask is applied.' : 'Rank differences compare relative uncertainty ordering. Large rank changes can occur even when both widths are small.';
      if (live) this.container.querySelector('.agreement-map-label').textContent = overlap ? 'Moving top-10% selections · white = shared by both models' : this.mode.value === 'rank' ? 'Moving absolute percentile-rank difference · 0–1; Spearman is reported below' : 'Moving absolute interval-width difference · 0–1';
      this.enableRegionButtons(Boolean(this.row?.region) && this.container.getAttribute('aria-busy') !== 'true');
      if (this.row && this.container.getAttribute('aria-busy') !== 'true') this.status.textContent = `${this.row.valid_pixels.toLocaleString()} jointly valid pixels · ${overlap ? (this.row.top10_reason || 'higher overlap means the models select more of the same locations.') : 'lower correlation means less spatial agreement.'}`;
      if (this.playing && !live) this.status.textContent = 'Pause or select a frame to inspect the rank-difference map.';
      this.draw();
    }

    setPlaybackSource(source) {
      if (source) {
        this.playbackVideo.src = source.video;
        this.playbackVideo.poster = source.poster;
      } else {
        this.playbackVideo.removeAttribute('src');
        this.playbackVideo.removeAttribute('poster');
      }
      this.playbackVideo.load();
    }

    setPlaying(value) {
      this.version++;
      this.playing = value;
      this.container.setAttribute('aria-busy', 'true');
      this.renderComparison();
    }

    updatePlaybackFrame(row, title) {
      if (!this.playing) return;
      this.row = row;
      this.container.querySelector('.agreement-title').textContent = title;
      this.renderComparison();
    }

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
      if (this.loadedKey !== key || !this.maps) {
        this.container.setAttribute('aria-busy', 'true'); this.enableRegionButtons(false);
        this.status.textContent = 'Loading numerical width maps…';
        this.renderComparison();
        try {
          const [agreement, q, i] = await Promise.all([load(), HeatmapPixels.loadMap(paths.qutcc), HeatmapPixels.loadMap(paths.im2im)]);
          if (version !== this.version) return;
          if (q.assetBase !== agreement.pixel_asset_base || i.assetBase !== agreement.pixel_asset_base) throw Error('Pixel export changed');
          const maps = differences(q, i);
          if (maps.validCount !== row.valid_pixels) throw Error('Agreement mask changed');
          for (const key of ['top10_intersection','top10_union','top10_qutcc_count','top10_im2im_count']) if (maps.top10[key] !== row[key]) throw Error('Overlap mask changed');
          this.maps = maps; this.loadedKey = key;
        } catch (_) {
          if (version === this.version) {this.status.textContent = 'Comparison maps unavailable. Select the frame or image again to retry.'; this.maps = null;}
          return;
        }
      }
      if (version !== this.version) return;
      this.container.setAttribute('aria-busy', 'false');
      this.renderComparison();
    }

    draw() {
      if (!this.maps || this.playing || this.container.getAttribute('aria-busy') === 'true') return;
      const overlap = getMode() === 'overlap', rank = this.mode.value === 'rank';
      const values = rank ? this.maps.rankGap : this.maps.widthGap;
      const context = this.canvas.getContext('2d'), image = context.createImageData(this.maps.width, this.maps.height);
      for (let p = 0; p < values.length; p++) {
        let rgb = [227,32,201];
        if (overlap) rgb = overlapColors[this.maps.overlapClasses[p]] || rgb;
        else if (Number.isFinite(values[p])) {
          const t = Math.min(1, Math.max(0, values[p])) * 4, k = Math.min(3, Math.floor(t)), weight = t - k;
          rgb = palette[k].map((a, c) => Math.round(a * (1 - weight) + palette[k+1][c] * weight));
        }
        for (let c = 0; c < 3; c++) image.data[4*p+c] = rgb[c];
        image.data[4*p+3] = 255;
      }
      context.putImageData(image, 0, 0);
      this.container.querySelector('.agreement-map-label').textContent = overlap ? 'All selected high-uncertainty locations · white = shared by both models' : rank ? 'Difference in uncertainty percentile rank · 0–1' : '|QUTCC width − Im2im width| · normalized intensity';
      const output = this.container.querySelector('.agreement-pixel'); output.textContent = '';
      if (this.point) {
        HeatmapPixels.drawCanvas(this.canvas, this.point.x + .5, this.point.y + .5);
        const p = this.point.y * this.maps.width + this.point.x;
        const selected = ['neither in top 10%','QUTCC top 10% only','Im2im top 10% only','both in top 10%'][this.maps.overlapClasses[p]] || 'excluded pixel';
        output.textContent = `(${this.point.x}, ${this.point.y}) · ${overlap ? selected : `rank gap ${format(this.maps.rankGap[p])}`} · width gap ${format(this.maps.widthGap[p])}`;
      }
    }
  }
  window.UncertaintyAgreement = {load, Panel, differences, format, percent, getMode, setMode};
})();
