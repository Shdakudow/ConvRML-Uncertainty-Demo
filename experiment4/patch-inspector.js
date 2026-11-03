/* Linked display crops. Saved predictions, palettes, and metrics are unchanged. */
(() => {
  'use strict';
  const imageWidth = 480, imageHeight = 270;
  const initialRegion = () => ({x: 192, y: 87, width: 96, height: 96});
  const clamp = (value, low, high) => Math.max(low, Math.min(high, value));

  class PatchInspector {
    constructor(root, onChange) {
      this.root = root;
      this.onChange = onChange;
      this.enabled = false;
      this.region = initialRegion();
      this.button = document.getElementById('patchToggle');
      this.reference = document.getElementById('patchReference');
      this.stage = document.getElementById('patchReferenceStage');
      this.fields = [...root.querySelectorAll('[data-patch-field]')];
      this.button.addEventListener('click', () => {
        this.enabled = !this.enabled;
        this.update(true);
        if (this.enabled) root.scrollIntoView({block: 'start', behavior: 'smooth'});
      });
      for (const input of this.fields) input.addEventListener('change', () => {
        const proposed = Object.fromEntries(this.fields.map(field => [field.dataset.patchField, Number(field.value)]));
        this.region = this.constrain(proposed);
        this.update(true);
      });
      document.getElementById('patchSize').addEventListener('change', event => {
        const side = Number(event.target.value);
        if (!side) return;
        const {x, y, width, height} = this.region;
        this.region = this.constrain({x: x + (width - side) / 2, y: y + (height - side) / 2, width: side, height: side});
        this.update(true);
      });
      document.getElementById('patchReset').addEventListener('click', () => {
        this.region = initialRegion();
        this.update(true);
      });
      this.stage.addEventListener('keydown', event => {
        const direction = {ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1]}[event.key];
        if (!direction) return;
        event.preventDefault();
        const step = event.shiftKey ? 10 : 1;
        this.region = this.constrain({...this.region, x: this.region.x + step * direction[0], y: this.region.y + step * direction[1]});
        this.update(true);
      });
      document.addEventListener('pointerdown', event => this.beginSelection(event));
    }

    get value() {
      const {x, y, width, height} = this.region;
      return this.enabled ? [x, y, width, height].join(',') : null;
    }

    constrain(region) {
      const integer = (key, fallback) => Number.isFinite(region[key]) ? Math.round(region[key]) : fallback;
      const width = clamp(integer('width', 96), 8, imageWidth);
      const height = clamp(integer('height', 96), 8, imageHeight);
      return {x: clamp(integer('x', 192), 0, imageWidth - width), y: clamp(integer('y', 87), 0, imageHeight - height), width, height};
    }

    readURL(value) {
      const values = value?.split(',').map(Number);
      this.enabled = Boolean(values?.length === 4 && values.every(Number.isFinite));
      this.region = this.enabled ? this.constrain({x: values[0], y: values[1], width: values[2], height: values[3]}) : initialRegion();
    }

    setScene(scene) {
      this.scene = scene;
      if (this.reference.src !== scene.reference) this.reference.src = scene.reference;
      document.getElementById('patchScene').textContent = scene.title;
      this.update(false);
    }

    update(notify) {
      if (!this.scene) return;
      const {x, y, width, height} = this.region;
      this.root.hidden = !this.enabled;
      this.button.textContent = this.enabled ? 'Show full images' : 'Inspect a patch';
      this.button.setAttribute('aria-pressed', String(this.enabled));
      document.documentElement.classList.toggle('patch-active', this.enabled);
      for (const input of this.fields) {
        input.value = this.region[input.dataset.patchField];
        input.max = {x: imageWidth - width, y: imageHeight - height, width: imageWidth, height: imageHeight}[input.dataset.patchField];
      }
      document.getElementById('patchSize').value = width === height && [64, 96, 128].includes(width) ? String(width) : 'custom';
      document.getElementById('patchCoordinates').textContent = `Selected patch: x ${x}, y ${y} · ${width} × ${height} pixels · full scene 480 × 270`;
      const viewports = this.enabled ? this.scene.card.querySelectorAll('.patch-viewport') : document.querySelectorAll('#tab-panels .patch-viewport');
      for (const viewport of viewports) {
        const image = viewport.querySelector('img');
        viewport.classList.toggle('patch-cropped', this.enabled);
        if (this.enabled) {
          viewport.style.aspectRatio = `${width} / ${height}`;
          viewport.dataset.patch = this.value;
          Object.assign(image.style, {width: `${imageWidth / width * 100}%`, height: `${imageHeight / height * 100}%`, left: `${-x / width * 100}%`, top: `${-y / height * 100}%`});
        } else {
          viewport.style.removeProperty('aspect-ratio');
          delete viewport.dataset.patch;
          for (const key of ['width', 'height', 'left', 'top']) image.style.removeProperty(key);
        }
        viewport.querySelector('.patch-selection')?.remove();
      }
      this.drawSelection(this.stage, this.region);
      if (notify) this.onChange();
    }

    drawSelection(stage, region) {
      const namespace = 'http://www.w3.org/2000/svg';
      let overlay = stage.querySelector('.patch-selection');
      if (!overlay) {
        overlay = document.createElementNS(namespace, 'svg');
        overlay.classList.add('patch-selection');
        overlay.setAttribute('aria-hidden', 'true');
        overlay.innerHTML = '<rect class="patch-outline"/><rect class="patch-line"/>';
        stage.append(overlay);
      }
      const view = stage.classList.contains('patch-cropped') ? this.region : {x: 0, y: 0, width: imageWidth, height: imageHeight};
      overlay.setAttribute('viewBox', `${view.x} ${view.y} ${view.width} ${view.height}`);
      for (const rectangle of overlay.children) for (const key of ['x', 'y', 'width', 'height']) rectangle.setAttribute(key, region[key]);
    }

    beginSelection(event) {
      const stage = event.target.closest('.patch-viewport, #patchReferenceStage');
      if (!stage || !this.scene || event.button !== 0) return;
      if (stage !== this.stage && !this.scene.card.contains(stage)) return;
      // A touch drag scrolls normally until the user enables patch inspection.
      if (event.pointerType === 'touch' && !this.enabled) return;
      event.preventDefault();
      const image = stage.querySelector('img');
      if (!image.complete || !image.naturalWidth) return;
      const bounds = image.getBoundingClientRect();
      const point = e => ({x: clamp(Math.floor((e.clientX - bounds.left) / bounds.width * imageWidth), 0, imageWidth - 1), y: clamp(Math.floor((e.clientY - bounds.top) / bounds.height * imageHeight), 0, imageHeight - 1)});
      const start = point(event);
      let end = start;
      const proposed = () => this.constrain({x: Math.min(start.x, end.x), y: Math.min(start.y, end.y), width: Math.abs(end.x - start.x) + 1, height: Math.abs(end.y - start.y) + 1});
      const move = e => {
        if (e.pointerId !== event.pointerId) return;
        end = point(e);
        this.drawSelection(stage, proposed());
      };
      const clean = () => {
        document.removeEventListener('pointermove', move);
        document.removeEventListener('pointerup', finish);
        document.removeEventListener('pointercancel', cancel);
      };
      const cancel = () => {clean(); stage.querySelector('.patch-selection')?.remove(); this.drawSelection(this.stage, this.region);};
      const finish = e => {
        if (e.pointerId !== event.pointerId) return;
        end = point(e);
        clean();
        this.region = Math.abs(end.x - start.x) < 4 && Math.abs(end.y - start.y) < 4
          ? this.constrain({...this.region, x: end.x - this.region.width / 2, y: end.y - this.region.height / 2})
          : proposed();
        this.enabled = true;
        this.update(true);
      };
      document.addEventListener('pointermove', move);
      document.addEventListener('pointerup', finish);
      document.addEventListener('pointercancel', cancel);
      try {stage.setPointerCapture(event.pointerId);} catch (_) { /* Synthetic pointer events need no capture. */ }
    }
  }
  window.PatchInspector = PatchInspector;
})();
