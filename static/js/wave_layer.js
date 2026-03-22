/**
 * WaveCanvasLayer — Leaflet Canvas overlay for scalar wave height grids.
 * Renders GFS-Wave binary data (uint16 LE, values in cm) as a smooth
 * color-interpolated overlay, similar to Windy.com's wave layer.
 *
 * Performance optimizations:
 * - Render at half resolution, CSS-upscale (4x fewer pixels)
 * - Precomputed Mercator projection (no per-pixel Leaflet API calls)
 * - Uint32Array single-write per pixel
 * - 2048-entry LUT for instant color lookup (0.05m precision)
 * - Frame render cache (skip re-render if viewport unchanged)
 */

// --- Color scale: wave height (m) → [R, G, B, A] ---
const WAVE_COLORS = [
  [0.0,  0, 0, 0, 0],
  [0.3,  0, 0, 0, 0],
  [0.5,  10, 40, 160, 150],
  [1.0,  0, 120, 210, 170],
  [1.5,  0, 190, 170, 180],
  [2.0,  60, 200, 60, 185],
  [3.0,  210, 210, 0, 195],
  [4.0,  235, 150, 0, 205],
  [6.0,  210, 40, 30, 215],
  [8.0,  150, 0, 80, 225],
  [15.0, 120, 0, 120, 235]
];

// Build a 2048-entry LUT: index = wave height in cm / 5 → 0..2047 covers 0..102m
// Stored as packed ABGR uint32 for direct pixel write
const WAVE_LUT32 = new Uint32Array(2048);
(function buildLUT() {
  for (let i = 0; i < 2048; i++) {
    const hm = i * 0.05; // height in meters
    let r = 0, g = 0, b = 0, a = 0;
    for (let j = 0; j < WAVE_COLORS.length - 1; j++) {
      const s0 = WAVE_COLORS[j], s1 = WAVE_COLORS[j + 1];
      if (hm >= s0[0] && hm < s1[0]) {
        const t = (hm - s0[0]) / (s1[0] - s0[0]);
        r = s0[1] + t * (s1[1] - s0[1]);
        g = s0[2] + t * (s1[2] - s0[2]);
        b = s0[3] + t * (s1[3] - s0[3]);
        a = s0[4] + t * (s1[4] - s0[4]);
        break;
      }
    }
    if (hm >= WAVE_COLORS[WAVE_COLORS.length - 1][0]) {
      const s = WAVE_COLORS[WAVE_COLORS.length - 1];
      r = s[1]; g = s[2]; b = s[3]; a = s[4];
    }
    // Pack as ABGR for little-endian Uint32Array on ImageData
    WAVE_LUT32[i] = ((a & 0xFF) << 24) | ((b & 0xFF) << 16) | ((g & 0xFF) << 8) | (r & 0xFF);
  }
})();


class WaveCanvasLayer {
  constructor(map) {
    this.map = map;
    this.meta = null;
    this.gridCache = {};
    this.canvas = null;
    this.currentFrame = 0;
    this.frames = [];
    this.animTimer = null;
    this.animDelay = 1000;
    this.active = false;
    this._renderViewKey = '';  // cache key: frame+bounds+zoom
    this._onMoveEnd = () => { if (this.active) this._renderViewKey = ''; this.render(); };
  }

  async loadMeta(url) {
    const resp = await fetch(url);
    this.meta = await resp.json();
    this.frames = this.meta.frames;
    return this.meta;
  }

  async loadGrid(frameIdx) {
    if (this.gridCache[frameIdx]) return this.gridCache[frameIdx];
    const resp = await fetch('/static/waves/' + this.frames[frameIdx].file);
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
    canvas.style.zIndex = '450';
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
    if (this.canvas && this.canvas.parentNode) {
      this.canvas.parentNode.removeChild(this.canvas);
    }
    this.canvas = null;
  }

  async showFrame(idx) {
    if (!this.active || !this.frames.length) return;
    idx = ((idx % this.frames.length) + this.frames.length) % this.frames.length;
    this.currentFrame = idx;
    this._renderViewKey = ''; // invalidate cache
    await this.loadGrid(idx);
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

    // Cache check: skip render if nothing changed
    const viewKey = this.currentFrame + '|' + zoom + '|' +
      bounds.getNorth().toFixed(4) + ',' + bounds.getWest().toFixed(4) + ',' +
      bounds.getSouth().toFixed(4) + ',' + bounds.getEast().toFixed(4) + '|' +
      size.x + 'x' + size.y;
    if (viewKey === this._renderViewKey) return;
    this._renderViewKey = viewKey;

    // Render at half resolution for performance
    const scale = 0.5;
    const rw = Math.ceil(size.x * scale);
    const rh = Math.ceil(size.y * scale);

    const canvas = this.canvas;
    canvas.width = rw;
    canvas.height = rh;
    // CSS scales it back up to full map size
    canvas.style.width = size.x + 'px';
    canvas.style.height = size.y + 'px';

    const topLeft = map.containerPointToLayerPoint([0, 0]);
    L.DomUtil.setPosition(canvas, topLeft);

    const ctx = canvas.getContext('2d');
    const imgData = ctx.createImageData(rw, rh);
    const buf32 = new Uint32Array(imgData.data.buffer);

    const g = this.meta.grid;
    const gnx = g.nx;
    const gny = g.ny;

    // Precompute projection: map pixel → lat/lon using only corner points
    // Mercator Y is non-linear, so we compute lat per row via Leaflet's projection
    // but lon is linear per row (big win: only 1 Leaflet call per row instead of per pixel)
    const west = bounds.getWest();
    const east = bounds.getEast();
    const lonSpan = east - west;

    for (let py = 0; py < rh; py++) {
      // Convert render-pixel Y to container Y, then to lat
      const containerY = py / scale;
      const lat = map.containerPointToLatLng([0, containerY]).lat;
      if (lat > 90 || lat < -90) continue;

      // Grid Y index (float)
      const gy = (g.la1 - lat) / g.dy;
      if (gy < 0 || gy >= gny - 1) continue;

      const gy0 = gy | 0; // floor
      const gy1 = gy0 + 1 < gny ? gy0 + 1 : gy0;
      const fy = gy - gy0;
      const fy1 = 1 - fy;

      // Row offsets in grid
      const row0 = gy0 * gnx;
      const row1 = gy1 * gnx;

      // Lon is linear across the row
      const rowOff = py * rw;

      for (let px = 0; px < rw; px++) {
        // Linear lon interpolation
        let lon = west + (px / rw) * lonSpan;
        // Normalize to 0-360
        lon = ((lon % 360) + 360) % 360;

        // Grid X index
        const gx = (lon - g.lo1) / g.dx;
        if (gx < 0) continue;

        const gx0 = gx | 0;
        const gx1 = (gx0 + 1) % gnx;
        const fx = gx - gx0;
        const fx1 = 1 - fx;

        // Bilinear interpolation
        const val = grid[row0 + gx0] * fx1 * fy1 +
                    grid[row0 + gx1] * fx  * fy1 +
                    grid[row1 + gx0] * fx1 * fy +
                    grid[row1 + gx1] * fx  * fy;

        if (val < 30) continue; // < 0.3m skip

        // LUT index: val is in cm, LUT step = 5cm → index = val/5
        const lutIdx = Math.min(2047, (val / 5) | 0);
        const color32 = WAVE_LUT32[lutIdx];
        if (color32 === 0) continue;

        buf32[rowOff + px] = color32;
      }
    }

    ctx.putImageData(imgData, 0, 0);
  }

  // --- Animation ---
  playAnim() {
    if (this.animTimer) return;
    this.animTimer = true;
    this._animStep();
  }

  _animStep() {
    if (!this.animTimer) return;
    this.showFrame(this.currentFrame + 1).then(() => {
      if (this.animTimer) {
        this.animTimer = setTimeout(() => this._animStep(), this.animDelay);
      }
    });
  }

  stopAnim() {
    if (this.animTimer && this.animTimer !== true) {
      clearTimeout(this.animTimer);
    }
    this.animTimer = null;
  }

  toggleAnim() {
    if (this.animTimer) {
      this.stopAnim();
    } else {
      this.playAnim();
    }
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
    const playBtn = document.getElementById('wv-play-btn');
    if (playBtn) playBtn.textContent = this.animTimer ? '\u23F8' : '\u25B6';

    const tsEl = document.getElementById('wv-label');
    if (tsEl) tsEl.textContent = this.formatDateTime(this.currentFrame);

    const progEl = document.getElementById('wv-progress');
    if (progEl) progEl.value = this.currentFrame;
  }
}

window.WaveCanvasLayer = WaveCanvasLayer;
