/**
 * WaveCanvasLayer — Leaflet Canvas overlay for wave height + direction grids.
 * Renders GFS-Wave binary data as a smooth color-interpolated overlay
 * with directional arrows showing wave propagation.
 *
 * Performance optimizations:
 * - Render at half resolution, CSS-upscale (4x fewer pixels)
 * - Precomputed Mercator projection (no per-pixel Leaflet API calls)
 * - Uint32Array single-write per pixel
 * - 2048-entry LUT for instant color lookup (0.05m precision)
 * - Frame render cache (skip re-render if viewport unchanged)
 * - Direction arrows drawn at fixed pixel intervals
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
    this.gridCache = {};    // height grids
    this.dirCache = {};     // direction grids
    this.canvas = null;
    this.arrowCanvas = null;
    this.currentFrame = 0;
    this.frames = [];
    this.animTimer = null;
    this.animDelay = 1000;
    this.active = false;
    this.hasDirection = false;
    this._renderViewKey = '';
    this._onMoveEnd = () => { if (this.active) this._renderViewKey = ''; this.render(); };
  }

  async loadMeta(url) {
    const resp = await fetch(url);
    this.meta = await resp.json();
    this.frames = this.meta.frames;
    this.hasDirection = !!this.meta.hasDirection;
    return this.meta;
  }

  _heightFile(frameIdx) {
    const f = this.frames[frameIdx];
    return f.height || f.file; // support old ("file") and new ("height") format
  }

  async loadGrid(frameIdx) {
    if (this.gridCache[frameIdx]) return this.gridCache[frameIdx];
    const resp = await fetch('/static/waves/' + this._heightFile(frameIdx));
    const buf = await resp.arrayBuffer();
    this.gridCache[frameIdx] = new Uint16Array(buf);
    return this.gridCache[frameIdx];
  }

  async loadDir(frameIdx) {
    if (this.dirCache[frameIdx]) return this.dirCache[frameIdx];
    const f = this.frames[frameIdx];
    if (!f.direction) return null;
    const resp = await fetch('/static/waves/' + f.direction);
    const buf = await resp.arrayBuffer();
    this.dirCache[frameIdx] = new Uint16Array(buf);
    return this.dirCache[frameIdx];
  }

  async preloadAll() {
    const promises = this.frames.map((_, i) => this.loadGrid(i));
    if (this.hasDirection) {
      this.frames.forEach((f, i) => {
        if (f.direction) promises.push(this.loadDir(i));
      });
    }
    await Promise.all(promises);
  }

  activate() {
    if (this.active) return;
    this.active = true;

    // Height color canvas
    const canvas = L.DomUtil.create('canvas');
    canvas.style.position = 'absolute';
    canvas.style.pointerEvents = 'none';
    canvas.style.zIndex = '450';
    canvas.style.imageRendering = 'auto';
    this.canvas = canvas;

    // Arrow overlay canvas (full resolution for crisp arrows)
    const arrowCanvas = L.DomUtil.create('canvas');
    arrowCanvas.style.position = 'absolute';
    arrowCanvas.style.pointerEvents = 'none';
    arrowCanvas.style.zIndex = '451';
    this.arrowCanvas = arrowCanvas;

    const pane = this.map.getContainer().querySelector('.leaflet-overlay-pane');
    pane.appendChild(canvas);
    pane.appendChild(arrowCanvas);

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
    if (this.arrowCanvas && this.arrowCanvas.parentNode) {
      this.arrowCanvas.parentNode.removeChild(this.arrowCanvas);
    }
    this.canvas = null;
    this.arrowCanvas = null;
  }

  async showFrame(idx) {
    if (!this.active || !this.frames.length) return;
    idx = ((idx % this.frames.length) + this.frames.length) % this.frames.length;
    this.currentFrame = idx;
    this._renderViewKey = '';
    await this.loadGrid(idx);
    if (this.hasDirection) await this.loadDir(idx);
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

    const viewKey = this.currentFrame + '|' + zoom + '|' +
      bounds.getNorth().toFixed(4) + ',' + bounds.getWest().toFixed(4) + ',' +
      bounds.getSouth().toFixed(4) + ',' + bounds.getEast().toFixed(4) + '|' +
      size.x + 'x' + size.y;
    if (viewKey === this._renderViewKey) return;
    this._renderViewKey = viewKey;

    this._renderHeight(grid, size, bounds, zoom);
    this._renderArrows(grid, size, bounds, zoom);
  }

  _renderHeight(grid, size, bounds, zoom) {
    const map = this.map;
    const scale = 0.5;
    const rw = Math.ceil(size.x * scale);
    const rh = Math.ceil(size.y * scale);

    const canvas = this.canvas;
    canvas.width = rw;
    canvas.height = rh;
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

    const west = bounds.getWest();
    const east = bounds.getEast();
    const lonSpan = east - west;

    for (let py = 0; py < rh; py++) {
      const containerY = py / scale;
      const lat = map.containerPointToLatLng([0, containerY]).lat;
      if (lat > 90 || lat < -90) continue;

      const gy = (g.la1 - lat) / g.dy;
      if (gy < 0 || gy >= gny - 1) continue;

      const gy0 = gy | 0;
      const gy1 = gy0 + 1 < gny ? gy0 + 1 : gy0;
      const fy = gy - gy0;
      const fy1 = 1 - fy;

      const row0 = gy0 * gnx;
      const row1 = gy1 * gnx;
      const rowOff = py * rw;

      for (let px = 0; px < rw; px++) {
        let lon = west + (px / rw) * lonSpan;
        lon = ((lon % 360) + 360) % 360;

        const gx = (lon - g.lo1) / g.dx;
        if (gx < 0) continue;

        const gx0 = gx | 0;
        const gx1 = (gx0 + 1) % gnx;
        const fx = gx - gx0;
        const fx1 = 1 - fx;

        const val = grid[row0 + gx0] * fx1 * fy1 +
                    grid[row0 + gx1] * fx  * fy1 +
                    grid[row1 + gx0] * fx1 * fy +
                    grid[row1 + gx1] * fx  * fy;

        if (val < 30) continue;

        const lutIdx = Math.min(2047, (val / 5) | 0);
        const color32 = WAVE_LUT32[lutIdx];
        if (color32 === 0) continue;

        buf32[rowOff + px] = color32;
      }
    }

    ctx.putImageData(imgData, 0, 0);
  }

  _renderArrows(grid, size, bounds, zoom) {
    const dirGrid = this.dirCache[this.currentFrame];
    if (!dirGrid || !this.arrowCanvas) return;

    const map = this.map;
    const canvas = this.arrowCanvas;
    canvas.width = size.x;
    canvas.height = size.y;
    canvas.style.width = size.x + 'px';
    canvas.style.height = size.y + 'px';

    const topLeft = map.containerPointToLayerPoint([0, 0]);
    L.DomUtil.setPosition(canvas, topLeft);

    const ctx = canvas.getContext('2d');
    ctx.clearRect(0, 0, size.x, size.y);

    const g = this.meta.grid;
    const gnx = g.nx;
    const gny = g.ny;

    const west = bounds.getWest();
    const east = bounds.getEast();
    const lonSpan = east - west;

    // Arrow spacing adapts to zoom: closer at higher zoom
    const spacing = Math.max(30, Math.min(60, 200 / Math.pow(2, zoom - 4)));
    const arrowLen = spacing * 0.35;

    ctx.strokeStyle = 'rgba(255, 255, 255, 0.85)';
    ctx.fillStyle = 'rgba(255, 255, 255, 0.85)';
    ctx.lineWidth = 1.5;

    for (let py = spacing / 2; py < size.y; py += spacing) {
      const lat = map.containerPointToLatLng([0, py]).lat;
      if (lat > 90 || lat < -90) continue;

      const gy = (g.la1 - lat) / g.dy;
      if (gy < 0 || gy >= gny - 1) continue;
      const gy0 = gy | 0;
      const gy1 = gy0 + 1 < gny ? gy0 + 1 : gy0;
      const fy = gy - gy0;
      const fy1 = 1 - fy;
      const row0 = gy0 * gnx;
      const row1 = gy1 * gnx;

      for (let px = spacing / 2; px < size.x; px += spacing) {
        let lon = west + (px / size.x) * lonSpan;
        lon = ((lon % 360) + 360) % 360;

        const gx = (lon - g.lo1) / g.dx;
        if (gx < 0) continue;
        const gx0 = gx | 0;
        const gx1 = (gx0 + 1) % gnx;
        const fx = gx - gx0;
        const fx1 = 1 - fx;

        // Check wave height at this point (skip if too small)
        const hVal = grid[row0 + gx0] * fx1 * fy1 +
                     grid[row0 + gx1] * fx  * fy1 +
                     grid[row1 + gx0] * fx1 * fy +
                     grid[row1 + gx1] * fx  * fy;
        if (hVal < 30) continue; // < 0.3m — no arrow

        // Bilinear interpolation of direction (in 0.1° units)
        const d00 = dirGrid[row0 + gx0];
        const d01 = dirGrid[row0 + gx1];
        const d10 = dirGrid[row1 + gx0];
        const d11 = dirGrid[row1 + gx1];

        // Handle angle wraparound (e.g., 350° vs 10°)
        // Convert to sin/cos, interpolate, convert back
        const toRad = Math.PI / 1800; // 0.1° units → radians
        const sinD = Math.sin(d00 * toRad) * fx1 * fy1 +
                     Math.sin(d01 * toRad) * fx  * fy1 +
                     Math.sin(d10 * toRad) * fx1 * fy +
                     Math.sin(d11 * toRad) * fx  * fy;
        const cosD = Math.cos(d00 * toRad) * fx1 * fy1 +
                     Math.cos(d01 * toRad) * fx  * fy1 +
                     Math.cos(d10 * toRad) * fx1 * fy +
                     Math.cos(d11 * toRad) * fx  * fy;

        // Direction the waves are coming FROM (meteorological convention)
        // We want to show where waves travel TO, so add 180°
        const dirRad = Math.atan2(sinD, cosD) + Math.PI;

        // Scale arrow by wave height (0.3m→small, 8m+→full)
        const hMeters = hVal / 100;
        const scaleFactor = Math.min(1.0, Math.max(0.4, hMeters / 4));
        const len = arrowLen * scaleFactor;

        // Arrow direction: dirRad is compass bearing (0=N, clockwise)
        // On screen: dx = sin(bearing), dy = -cos(bearing)
        const dx = Math.sin(dirRad) * len;
        const dy = -Math.cos(dirRad) * len;

        // Draw arrow shaft
        const x0 = px - dx * 0.5;
        const y0 = py - dy * 0.5;
        const x1 = px + dx * 0.5;
        const y1 = py + dy * 0.5;

        ctx.beginPath();
        ctx.moveTo(x0, y0);
        ctx.lineTo(x1, y1);
        ctx.stroke();

        // Draw arrowhead
        const headLen = len * 0.35;
        const headAngle = 0.45;
        const angle = Math.atan2(dy, dx);
        ctx.beginPath();
        ctx.moveTo(x1, y1);
        ctx.lineTo(
          x1 - headLen * Math.cos(angle - headAngle),
          y1 - headLen * Math.sin(angle - headAngle)
        );
        ctx.lineTo(
          x1 - headLen * Math.cos(angle + headAngle),
          y1 - headLen * Math.sin(angle + headAngle)
        );
        ctx.closePath();
        ctx.fill();
      }
    }
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
