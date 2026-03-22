/**
 * PrecipCanvasLayer — Leaflet Canvas overlay for precipitation rate grids.
 * Renders GFS PRATE binary data (uint16 LE, values in 0.01 mm/h) as a
 * color-interpolated overlay with classic radar color scale.
 *
 * Same architecture as WaveCanvasLayer for consistency.
 */

// --- Precipitation color scale: mm/h → [R, G, B, A] ---
// Classic radar scale: light blue → green → yellow → orange → red → purple
const PRECIP_COLORS = [
  [0.0,   0, 0, 0, 0],
  [0.1,   0, 0, 0, 0],
  [0.2,   120, 200, 255, 130],   // very light blue
  [0.5,   60, 150, 255, 150],    // light blue
  [1.0,   20, 100, 240, 165],    // blue
  [2.0,   40, 200, 40, 175],     // green
  [4.0,   200, 230, 0, 185],     // yellow-green
  [8.0,   255, 200, 0, 195],     // yellow-orange
  [16.0,  255, 120, 0, 210],     // orange
  [32.0,  230, 30, 30, 220],     // red
  [64.0,  170, 0, 120, 230],     // purple
  [100.0, 100, 0, 100, 240]      // dark purple
];

// LUT: 2048 entries, index = precipRate in 0.01mm/h / 5 → covers 0..102 mm/h
const PRECIP_LUT32 = new Uint32Array(2048);
(function buildPrecipLUT() {
  for (let i = 0; i < 2048; i++) {
    const mmh = i * 0.05; // mm/h
    let r = 0, g = 0, b = 0, a = 0;
    for (let j = 0; j < PRECIP_COLORS.length - 1; j++) {
      const s0 = PRECIP_COLORS[j], s1 = PRECIP_COLORS[j + 1];
      if (mmh >= s0[0] && mmh < s1[0]) {
        const t = (mmh - s0[0]) / (s1[0] - s0[0]);
        r = s0[1] + t * (s1[1] - s0[1]);
        g = s0[2] + t * (s1[2] - s0[2]);
        b = s0[3] + t * (s1[3] - s0[3]);
        a = s0[4] + t * (s1[4] - s0[4]);
        break;
      }
    }
    if (mmh >= PRECIP_COLORS[PRECIP_COLORS.length - 1][0]) {
      const s = PRECIP_COLORS[PRECIP_COLORS.length - 1];
      r = s[1]; g = s[2]; b = s[3]; a = s[4];
    }
    PRECIP_LUT32[i] = ((a & 0xFF) << 24) | ((b & 0xFF) << 16) | ((g & 0xFF) << 8) | (r & 0xFF);
  }
})();


class PrecipCanvasLayer {
  constructor(map) {
    this.map = map;
    this.meta = null;
    this.gridCache = {};
    this.canvas = null;
    this.currentFrame = 0;
    this.frames = [];
    this.animTimer = null;
    this.animDelay = 800;
    this.active = false;
    this._renderViewKey = '';
    this._frameRenderCache = {};
    this._onMoveEnd = () => {
      if (this.active) {
        this._renderViewKey = '';
        this._frameRenderCache = {};
        this.render();
      }
    };
  }

  async loadMeta(url) {
    const resp = await fetch(url + '?t=' + Date.now());
    this.meta = await resp.json();
    this.frames = this.meta.frames;
    this._cacheBust = this.meta.generated ? '?t=' + encodeURIComponent(this.meta.generated) : '';
    return this.meta;
  }

  async loadGrid(frameIdx) {
    if (this.gridCache[frameIdx]) return this.gridCache[frameIdx];
    const resp = await fetch('/static/precip/' + this.frames[frameIdx].file + (this._cacheBust || ''));
    const buf = await resp.arrayBuffer();
    this.gridCache[frameIdx] = new Uint16Array(buf);
    return this.gridCache[frameIdx];
  }

  async preloadAll() {
    await Promise.all(this.frames.map((_, i) => this.loadGrid(i)));
  }

  activate() {
    if (this.active) return;
    this.active = true;
    const canvas = L.DomUtil.create('canvas');
    canvas.style.position = 'absolute';
    canvas.style.pointerEvents = 'none';
    canvas.style.zIndex = '452';
    canvas.style.imageRendering = 'auto';
    this.canvas = canvas;
    this.map.getContainer().querySelector('.leaflet-overlay-pane').appendChild(canvas);
    this.map.on('moveend zoomend resize', this._onMoveEnd);
    this.showFrame(this.currentFrame);
  }

  deactivate() {
    this.active = false;
    this.stopAnim();
    this.map.off('moveend zoomend resize', this._onMoveEnd);
    if (this.canvas && this.canvas.parentNode) this.canvas.parentNode.removeChild(this.canvas);
    this.canvas = null;
    this._frameRenderCache = {};
  }

  async showFrame(idx) {
    if (!this.active || !this.frames.length) return;
    idx = ((idx % this.frames.length) + this.frames.length) % this.frames.length;
    this.currentFrame = idx;
    await this.loadGrid(idx);
    this._renderViewKey = '';
    this.render();
    this.updateUI();
  }

  render() {
    if (!this.canvas || !this.meta || !this.active) return;
    const grid = this.gridCache[this.currentFrame];
    if (!grid) return;

    const map = this.map;
    const size = map.getSize();
    const bounds = map.getBounds();
    const zoom = map.getZoom();

    const topLeft = map.containerPointToLayerPoint([0, 0]);
    const baseViewKey = zoom + '|' +
      bounds.getNorth().toFixed(4) + ',' + bounds.getWest().toFixed(4) + ',' +
      bounds.getSouth().toFixed(4) + ',' + bounds.getEast().toFixed(4) + '|' +
      size.x + 'x' + size.y;
    const frameKey = this.currentFrame + '|' + baseViewKey;

    if (frameKey === this._renderViewKey) return;
    this._renderViewKey = frameKey;

    // Check frame cache
    const cached = this._frameRenderCache[this.currentFrame];
    if (cached && cached.viewKey === baseViewKey) {
      const canvas = this.canvas;
      canvas.width = cached.rw;
      canvas.height = cached.rh;
      canvas.style.width = size.x + 'px';
      canvas.style.height = size.y + 'px';
      L.DomUtil.setPosition(canvas, topLeft);
      canvas.getContext('2d').putImageData(cached.imgData, 0, 0);
      return;
    }

    // Full render at half resolution
    const scale = zoom >= 5 ? 1.0 : 0.5;
    const rw = Math.ceil(size.x * scale);
    const rh = Math.ceil(size.y * scale);

    const canvas = this.canvas;
    canvas.width = rw;
    canvas.height = rh;
    canvas.style.width = size.x + 'px';
    canvas.style.height = size.y + 'px';
    L.DomUtil.setPosition(canvas, topLeft);

    const ctx = canvas.getContext('2d');
    const imgData = ctx.createImageData(rw, rh);
    const buf32 = new Uint32Array(imgData.data.buffer);

    const g = this.meta.grid;
    const gnx = g.nx, gny = g.ny;
    const la1 = g.la1, lo1 = g.lo1, dx = g.dx, dy = g.dy;

    const west = bounds.getWest();
    const lonSpan = bounds.getEast() - west;
    const invRw = lonSpan / rw;

    // Precompute lat → grid Y per row
    const rowGy = new Float32Array(rh);
    const rowValid = new Uint8Array(rh);
    for (let py = 0; py < rh; py++) {
      const lat = map.containerPointToLatLng([0, py / scale]).lat;
      if (lat > 90 || lat < -90) continue;
      const gy = (la1 - lat) / dy;
      if (gy < 0 || gy >= gny - 1) continue;
      rowGy[py] = gy;
      rowValid[py] = 1;
    }

    for (let py = 0; py < rh; py++) {
      if (!rowValid[py]) continue;
      const gy = rowGy[py];
      const gy0 = gy | 0;
      const gy1 = gy0 + 1 < gny ? gy0 + 1 : gy0;
      const fy = gy - gy0;
      const fy1 = 1 - fy;
      const row0 = gy0 * gnx;
      const row1 = gy1 * gnx;
      const rowOff = py * rw;

      for (let px = 0; px < rw; px++) {
        let lon = west + px * invRw;
        lon = ((lon % 360) + 360) % 360;

        const gx = (lon - lo1) / dx;
        if (gx < 0) continue;

        const gx0 = gx | 0;
        const gx1 = (gx0 + 1) % gnx;
        const fx = gx - gx0;
        const fx1 = 1 - fx;

        const val = grid[row0 + gx0] * fx1 * fy1 +
                    grid[row0 + gx1] * fx  * fy1 +
                    grid[row1 + gx0] * fx1 * fy +
                    grid[row1 + gx1] * fx  * fy;

        // val is in 0.01 mm/h, threshold: 0.2 mm/h = 20 units
        if (val < 20) continue;

        // LUT: index = val / 5 (since val is 0.01mm/h, and LUT covers 0.05mm/h per step)
        const lutIdx = Math.min(2047, (val / 5) | 0);
        const c = PRECIP_LUT32[lutIdx];
        if (c === 0) continue;
        buf32[rowOff + px] = c;
      }
    }

    ctx.putImageData(imgData, 0, 0);

    // Cache
    this._frameRenderCache[this.currentFrame] = {
      viewKey: baseViewKey, imgData: imgData, rw: rw, rh: rh
    };
  }

  // --- Animation ---
  playAnim() {
    if (this.animTimer) return;
    this.animTimer = true;
    this._lastAnimTime = 0;
    this._animRAF = requestAnimationFrame((t) => this._animStep(t));
  }

  _animStep(timestamp) {
    if (!this.animTimer) return;
    if (timestamp - this._lastAnimTime >= this.animDelay) {
      this._lastAnimTime = timestamp;
      this.showFrame(this.currentFrame + 1);
    }
    this._animRAF = requestAnimationFrame((t) => this._animStep(t));
  }

  stopAnim() {
    if (this._animRAF) cancelAnimationFrame(this._animRAF);
    this.animTimer = null;
    this._animRAF = null;
  }

  toggleAnim() {
    if (this.animTimer) { this.stopAnim(); } else { this.playAnim(); }
    this.updateUI();
  }

  formatDateTime(frameIdx) {
    if (!this.meta || !this.frames[frameIdx]) return '--';
    const frame = this.frames[frameIdx];
    const d = this.meta.date;
    const c = parseInt(this.meta.cycle);
    const base = new Date(Date.UTC(
      parseInt(d.slice(0, 4)), parseInt(d.slice(4, 6)) - 1, parseInt(d.slice(6, 8)), c
    ));
    base.setUTCHours(base.getUTCHours() + frame.hour);
    return base.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit' }) + ' ' +
           base.toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' }) +
           ' (+' + frame.hour + 'h)';
  }

  updateUI() {
    const playBtn = document.getElementById('pr-play-btn');
    if (playBtn) playBtn.textContent = this.animTimer ? '\u23F8' : '\u25B6';
    const tsEl = document.getElementById('pr-label');
    if (tsEl) tsEl.textContent = this.formatDateTime(this.currentFrame);
    const progEl = document.getElementById('pr-progress');
    if (progEl) progEl.value = this.currentFrame;
  }
}

window.PrecipCanvasLayer = PrecipCanvasLayer;
