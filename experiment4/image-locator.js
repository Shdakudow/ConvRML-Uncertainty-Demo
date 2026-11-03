/* Mark a common image coordinate without changing image size or content. */
(() => {
  'use strict';
  const width = 480, height = 270;

  class ImageLocator {
    constructor(root) {
      this.root = root;
      this.point = null;
      root.addEventListener('click', event => {
        const image = event.target.closest('img[data-kind]');
        if (!image?.closest('.image-locator-stage') || !this.card?.contains(image)) return;
        this.point = HeatmapPixels.pointAt(image, event, width, height);
        this.draw();
      });
      window.addEventListener('resize', () => this.draw());
      document.addEventListener('keydown', event => {
        if (event.key !== 'Escape') return;
        this.point = null;
        root.querySelectorAll('.image-locator-marker').forEach(marker => marker.remove());
      });
    }

    setScene(card) {
      this.card = card;
      this.draw();
    }

    draw() {
      if (!this.card) return;
      for (const stage of this.card.querySelectorAll('.image-locator-stage')) {
        stage.querySelector('.image-locator-marker')?.remove();
        if (!this.point) continue;
        HeatmapPixels.mark(stage.querySelector('img'), [{x: this.point.x + .5, y: this.point.y + .5}], width, height);
        const marker = stage.querySelector('.pixel-overlay');
        marker.classList.add('image-locator-marker');
        marker.dataset.point = `${this.point.x},${this.point.y}`;
      }
    }
  }
  window.ImageLocator = ImageLocator;
})();
