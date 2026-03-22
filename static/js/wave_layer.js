/**
 * WaveCanvasLayer — Leaflet Canvas overlay for wave height + direction grids.
 * Renders GFS-Wave binary data as a smooth color-interpolated overlay
 * with directional arrows showing wave propagation.
 *
 * Performance optimizations:
 * - Adaptive render scale (half-res at low zoom, full at high zoom)
 * - Precomputed lat array (one Leaflet call per row, not per pixel)
 * - Uint32Array single-write per pixel via 2048-entry color LUT
 * - 3601-entry sin/cos LUT for direction interpolation (no trig in loop)
 * - Batched arrow path rendering (single stroke + single fill call)
 * - Per-frame ImageData cache for instant frame switching during animation
 * - requestAnimationFrame for smooth playback
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

// Color LUT: index = wave height in cm / 5 → 0..2047 covers 0..102m
const WAVE_LUT32 = new Uint32Array(2048);
(function buildColorLUT() {
  for (let i = 0; i < 2048; i++) {
    const hm = i * 0.05;
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
    WAVE_LUT32[i] = ((a & 0xFF) << 24) | ((b & 0xFF) << 16) | ((g & 0xFF) << 8) | (r & 0xFF);
  }
})();

// Direction sin/cos LUT: 3601 entries for 0..360.0° in 0.1° steps
// Eliminates all trig calls from the arrow render loop
const DIR_SIN = new Float32Array(3601);
const DIR_COS = new Float32Array(3601);
(function buildDirLUT() {
  const toRad = Math.PI / 1800;
  for (let i = 0; i <= 3600; i++) {
    DIR_SIN[i] = Math.sin(i * toRad);
    DIR_COS[i] = Math.cos(i * toRad);
  }
})();


class WaveCanvasLayer {
  constructor(map) {
    this.map = map;
    this.meta = null;
    this.gridCache = {};
    this.dirCache = {};
    this.canvas = null;
    this.arrowCanvas = null;
    this.currentFrame = 0;
    this.frames = [];
    this.animTimer = null;
    this.animDelay = 800;
    this.active = false;
    this.hasDirection = false;
    this._renderViewKey = '';
    // Per-frame render cache: viewKey → { heightImgData, arrowImgData }
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
    this.hasDirection = !!this.meta.hasDirection;
    this._cacheBust = this.meta.generated ? '?t=' + encodeURIComponent(this.meta.generated) : '';
    return this.meta;
  }

  _heightFile(frameIdx) {
    const f = this.frames[frameIdx];
    return f.height || f.file;
  }

  async loadGrid(frameIdx) {
    if (this.gridCache[frameIdx]) return this.gridCache[frameIdx];
    const resp = await fetch('/static/waves/' + this._heightFile(frameIdx) + (this._cacheBust || ''));
    const buf = await resp.arrayBuffer();
    this.gridCache[frameIdx] = new Uint16Array(buf);
    return this.gridCache[frameIdx];
  }

  async loadDir(frameIdx) {
    if (this.dirCache[frameIdx]) return this.dirCache[frameIdx];
    const f = this.frames[frameIdx];
    if (!f.direction) return null;
    const resp = await fetch('/static/waves/' + f.direction + (this._cacheBust || ''));
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

    const canvas = L.DomUtil.create('canvas');
    canvas.style.position = 'absolute';
    canvas.style.pointerEvents = 'none';
    canvas.style.zIndex = '450';
    canvas.style.imageRendering = 'auto';
    this.canvas = canvas;

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
    if (this.canvas && this.canvas.parentNode) this.canvas.parentNode.removeChild(this.canvas);
    if (this.arrowCanvas && this.arrowCanvas.parentNode) this.arrowCanvas.parentNode.removeChild(this.arrowCanvas);
    this.canvas = null;
    this.arrowCanvas = null;
    this._frameRenderCache = {};
  }

  async showFrame(idx) {
    if (!this.active || !this.frames.length) return;
    idx = ((idx % this.frames.length) + this.frames.length) % this.frames.length;
    this.currentFrame = idx;
    await this.loadGrid(idx);
    if (this.hasDirection) await this.loadDir(idx);
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

    // Position canvases
    const topLeft = map.containerPointToLayerPoint([0, 0]);

    // Check frame render cache (same viewport → just blit cached ImageData)
    const baseViewKey = zoom + '|' +
      bounds.getNorth().toFixed(4) + ',' + bounds.getWest().toFixed(4) + ',' +
      bounds.getSouth().toFixed(4) + ',' + bounds.getEast().toFixed(4) + '|' +
      size.x + 'x' + size.y;
    const frameKey = this.currentFrame + '|' + baseViewKey;

    if (frameKey === this._renderViewKey) return;
    this._renderViewKey = frameKey;

    const cached = this._frameRenderCache[this.currentFrame];
    if (cached && cached.viewKey === baseViewKey) {
      // Instant blit from cache
      const canvas = this.canvas;
      canvas.width = cached.hw;
      canvas.height = cached.hh;
      canvas.style.width = size.x + 'px';
      canvas.style.height = size.y + 'px';
      L.DomUtil.setPosition(canvas, topLeft);
      canvas.getContext('2d').putImageData(cached.heightImg, 0, 0);

      if (cached.arrowImg && this.arrowCanvas) {
        const ac = this.arrowCanvas;
        ac.width = size.x;
        ac.height = size.y;
        ac.style.width = size.x + 'px';
        ac.style.height = size.y + 'px';
        L.DomUtil.setPosition(ac, topLeft);
        ac.getContext('2d').putImageData(cached.arrowImg, 0, 0);
      }
      return;
    }

    // Full render
    const heightImg = this._renderHeight(grid, size, bounds, zoom, topLeft);
    const arrowImg = this._renderArrows(grid, size, bounds, zoom, topLeft);

    // Cache for animation reuse
    const scale = zoom >= 5 ? 1.0 : 0.5;
    this._frameRenderCache[this.currentFrame] = {
      viewKey: baseViewKey,
      heightImg: heightImg,
      hw: Math.ceil(size.x * scale),
      hh: Math.ceil(size.y * scale),
      arrowImg: arrowImg
    };
  }

  _renderHeight(grid, size, bounds, zoom, topLeft) {
    const map = this.map;
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
    const gnx = g.nx;
    const gny = g.ny;
    const la1 = g.la1, lo1 = g.lo1, dx = g.dx, dy = g.dy;

    const west = bounds.getWest();
    const lonSpan = bounds.getEast() - west;
    const invRw = lonSpan / rw;

    // Precompute lat → grid Y for each render row (avoids Leaflet call in inner loop)
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

        if (val < 30) continue;

        const lutIdx = Math.min(2047, (val / 5) | 0);
        const color32 = WAVE_LUT32[lutIdx];
        if (color32 === 0) continue;

        buf32[rowOff + px] = color32;
      }
    }

    ctx.putImageData(imgData, 0, 0);
    return imgData;
  }

  _renderArrows(grid, size, bounds, zoom, topLeft) {
    const dirGrid = this.dirCache[this.currentFrame];
    if (!dirGrid || !this.arrowCanvas) return null;

    const map = this.map;
    const canvas = this.arrowCanvas;
    canvas.width = size.x;
    canvas.height = size.y;
    canvas.style.width = size.x + 'px';
    canvas.style.height = size.y + 'px';
    L.DomUtil.setPosition(canvas, topLeft);

    const ctx = canvas.getContext('2d');

    const g = this.meta.grid;
    const gnx = g.nx;
    const gny = g.ny;
    const la1 = g.la1, lo1 = g.lo1, dx = g.dx, dy = g.dy;

    const west = bounds.getWest();
    const lonSpan = bounds.getEast() - west;

    const spacing = Math.max(30, Math.min(60, 200 / Math.pow(2, zoom - 4)));
    const arrowLen = spacing * 0.35;
    const headAngle = 0.45;
    const cosHA = Math.cos(headAngle);
    const sinHA = Math.sin(headAngle);

    // Batch all shafts into one path, all heads into another
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.85)';
    ctx.fillStyle = 'rgba(255, 255, 255, 0.85)';
    ctx.lineWidth = 1.5;

    // Shaft path
    ctx.beginPath();
    // Collect arrowhead vertices for a second batched path
    const heads = [];

    for (let py = spacing * 0.5; py < size.y; py += spacing) {
      const lat = map.containerPointToLatLng([0, py]).lat;
      if (lat > 90 || lat < -90) continue;

      const gy = (la1 - lat) / dy;
      if (gy < 0 || gy >= gny - 1) continue;
      const gy0 = gy | 0;
      const gy1 = gy0 + 1 < gny ? gy0 + 1 : gy0;
      const fy = gy - gy0;
      const fy1 = 1 - fy;
      const row0 = gy0 * gnx;
      const row1 = gy1 * gnx;

      for (let px = spacing * 0.5; px < size.x; px += spacing) {
        let lon = west + (px / size.x) * lonSpan;
        lon = ((lon % 360) + 360) % 360;

        const gx = (lon - lo1) / dx;
        if (gx < 0) continue;
        const gx0 = gx | 0;
        const gx1 = (gx0 + 1) % gnx;
        const fx = gx - gx0;
        const fx1 = 1 - fx;

        const hVal = grid[row0 + gx0] * fx1 * fy1 +
                     grid[row0 + gx1] * fx  * fy1 +
                     grid[row1 + gx0] * fx1 * fy +
                     grid[row1 + gx1] * fx  * fy;
        if (hVal < 30) continue;

        // Direction interpolation via LUT (no trig in loop)
        const d00 = Math.min(dirGrid[row0 + gx0], 3600);
        const d01 = Math.min(dirGrid[row0 + gx1], 3600);
        const d10 = Math.min(dirGrid[row1 + gx0], 3600);
        const d11 = Math.min(dirGrid[row1 + gx1], 3600);

        const sinD = DIR_SIN[d00] * fx1 * fy1 +
                     DIR_SIN[d01] * fx  * fy1 +
                     DIR_SIN[d10] * fx1 * fy +
                     DIR_SIN[d11] * fx  * fy;
        const cosD = DIR_COS[d00] * fx1 * fy1 +
                     DIR_COS[d01] * fx  * fy1 +
                     DIR_COS[d10] * fx1 * fy +
                     DIR_COS[d11] * fx  * fy;

        // atan2 is unavoidable for the final angle, but only once per arrow
        const dirRad = Math.atan2(sinD, cosD) + Math.PI;

        const scaleFactor = Math.min(1.0, Math.max(0.4, hVal / 400));
        const len = arrowLen * scaleFactor;

        const adx = Math.sin(dirRad) * len;
        const ady = -Math.cos(dirRad) * len;

        const x0 = px - adx * 0.5;
        const y0 = py - ady * 0.5;
        const x1 = px + adx * 0.5;
        const y1 = py + ady * 0.5;

        // Shaft
        ctx.moveTo(x0, y0);
        ctx.lineTo(x1, y1);

        // Arrowhead vertices (precompute with rotation matrix instead of atan2+cos+sin)
        const headLen = len * 0.35;
        // Normalize direction vector
        const invLen = 1.0 / (len || 1);
        const ux = adx * invLen;
        const uy = ady * invLen;
        // Rotate ±headAngle using precomputed cos/sin of headAngle
        // Left wing: rotate (ux, uy) by -headAngle
        const lx = ux * cosHA + uy * sinHA;
        const ly = -ux * sinHA + uy * cosHA;
        // Right wing: rotate (ux, uy) by +headAngle
        const rx = ux * cosHA - uy * sinHA;
        const ry = ux * sinHA + uy * cosHA;

        heads.push(
          x1, y1,
          x1 - lx * headLen, y1 - ly * headLen,
          x1 - rx * headLen, y1 - ry * headLen
        );
      }
    }
    ctx.stroke();

    // Batch-render all arrowheads
    ctx.beginPath();
    for (let i = 0; i < heads.length; i += 6) {
      ctx.moveTo(heads[i], heads[i + 1]);
      ctx.lineTo(heads[i + 2], heads[i + 3]);
      ctx.lineTo(heads[i + 4], heads[i + 5]);
      ctx.closePath();
    }
    ctx.fill();

    // Capture for cache
    return ctx.getImageData(0, 0, size.x, size.y);
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
