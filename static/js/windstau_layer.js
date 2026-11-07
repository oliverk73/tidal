/**
 * SurgeCanvasLayer — Kartenebene "Weather effect on sea level" (7.11.2026).
 * Daten: py/windstau_karte.py -> static/windstau/ (Copernicus Marine, Ostsee/Mittelmeer/Schwarzes Meer,
 * Modellgezeit abgezogen). Je Bild int16 mm, mehrere Raster hintereinander (meta.grids[].offset).
 * Baut auf TideCanvasLayer (tide_layer.js) auf: gleiche Leinwand, Landmaske, Animation.
 */

const SURGE_COLORS = [
  [-1.00,  20,  40, 120, 210],
  [-0.60,  30,  80, 190, 200],
  [-0.30,  80, 150, 230, 185],
  [-0.10, 170, 210, 245, 140],
  [ 0.00, 240, 240, 240,  90],
  [ 0.10, 250, 215, 160, 140],
  [ 0.30, 245, 160,  70, 185],
  [ 0.60, 220,  70,  40, 200],
  [ 1.00, 130,  10,  40, 210],
];
const SURGE_LUT_OFFSET = 2000;          // Index fuer 0 mm; -2,000 .. +2,000 m in mm-Schritten
const SURGE_LUT_SIZE = 4001;
const SURGE_LUT32 = new Uint32Array(SURGE_LUT_SIZE);
const SURGE_NO_DATA = -32768;

(function buildSurgeLUT() {
  const C = SURGE_COLORS, n = C.length;
  for (let i = 0; i < SURGE_LUT_SIZE; i++) {
    const v = (i - SURGE_LUT_OFFSET) / 1000.0;
    let c;
    if (v <= C[0][0]) c = C[0].slice(1);
    else if (v >= C[n - 1][0]) c = C[n - 1].slice(1);
    else {
      for (let j = 0; j < n - 1; j++) {
        if (v >= C[j][0] && v < C[j + 1][0]) {
          const t = (v - C[j][0]) / (C[j + 1][0] - C[j][0]);
          c = [1, 2, 3, 4].map(k => C[j][k] + t * (C[j + 1][k] - C[j][k]));
          break;
        }
      }
    }
    SURGE_LUT32[i] = ((c[3] & 0xFF) << 24) | ((c[2] & 0xFF) << 16) | ((c[1] & 0xFF) << 8) | (c[0] & 0xFF);
  }
})();

function surgeLegendHtml() {
  const stops = SURGE_COLORS.map(c => `rgba(${c[1]},${c[2]},${c[3]},${Math.min(1, c[4] / 200)}) ${((c[0] + 1) / 2 * 100).toFixed(0)}%`);
  return '<div style="width:180px;height:10px;border-radius:3px;background:linear-gradient(90deg,' + stops.join(',') + ');"></div>' +
         '<div style="display:flex;justify-content:space-between;width:180px;font-size:11px;color:#444;">' +
         '<span>−1 m</span><span>0</span><span>+1 m</span></div>';
}

class SurgeCanvasLayer extends TideCanvasLayer {
  constructor(map) {
    super(map);
    this._onMouse = (e) => this._zeigeWert(e.latlng);
  }

  async loadMeta(url) {
    const resp = await fetch(url + '?t=' + Date.now());
    if (!resp.ok) throw new Error('no surge data');
    this.meta = await resp.json();
    this.frames = this.meta.frames;
    this._cacheBust = this.meta.generated ? '?t=' + encodeURIComponent(this.meta.generated) : '';
    this.gridCache = {};
    this._frameRenderCache = {};
    // mit dem Bild beginnen, das jetzt am naechsten liegt
    const jetzt = Date.now() / 1000;
    let best = 0;
    this.frames.forEach((f, i) => { if (Math.abs(f.t - jetzt) < Math.abs(this.frames[best].t - jetzt)) best = i; });
    this.currentFrame = best;
    return this.meta;
  }

  async loadGrid(frameIdx) {
    if (this.gridCache[frameIdx]) return this.gridCache[frameIdx];
    const f = this.frames[frameIdx];
    const resp = await fetch('/static/windstau/' + f.file + (this._cacheBust || ''));
    const buf = await resp.arrayBuffer();
    this.gridCache[frameIdx] = new Int16Array(buf);
    return this.gridCache[frameIdx];
  }

  // nur das erste Bild sofort, die anderen beim Abspielen (je ~0,5 MB)
  async preloadAll() {
    await this.loadGrid(this.currentFrame);
  }

  async showFrame(idx) {
    await super.showFrame(idx);
    const n = this.frames.length;
    if (n) this.loadGrid((this.currentFrame + 1) % n).catch(() => {});
    if (this._letzteLatLng) this._zeigeWert(this._letzteLatLng);
  }

  activate() {
    super.activate();
    this.map.on('mousemove click', this._onMouse);
  }

  deactivate() {
    this.map.off('mousemove click', this._onMouse);
    super.deactivate();
  }

  // Wert an einer Position (m) oder null
  wertBei(lat, lon) {
    const grid = this.gridCache[this.currentFrame];
    if (!grid || !this.meta) return null;
    for (const g of this.meta.grids) {
      const gy = (g.la1 - lat) / g.dy, gx = (lon - g.lo1) / g.dx;
      if (gy < 0 || gx < 0 || gy > g.ny - 1 || gx > g.nx - 1) continue;
      const v = grid[g.offset + Math.round(gy) * g.nx + Math.round(gx)];
      if (v === SURGE_NO_DATA) continue;
      return v / 1000;
    }
    return null;
  }

  _zeigeWert(ll) {
    this._letzteLatLng = ll;
    const el = document.getElementById('ws-wert');
    if (!el) return;
    const v = this.wertBei(ll.lat, ll.lng);
    el.textContent = v === null ? '' : 'Here: ' + (v >= 0 ? '+' : '−') + Math.abs(v).toFixed(2) + ' m';
  }

  _renderGrid(grid, size, bounds, zoom, topLeft) {
    const map = this.map;
    const scale = zoom >= 5 ? 1.0 : 0.5;
    const rw = Math.ceil(size.x * scale), rh = Math.ceil(size.y * scale);
    const canvas = this.canvas;
    canvas.width = rw; canvas.height = rh;
    canvas.style.width = size.x + 'px'; canvas.style.height = size.y + 'px';
    L.DomUtil.setPosition(canvas, topLeft);
    const ctx = canvas.getContext('2d');
    const imgData = ctx.createImageData(rw, rh);
    const buf32 = new Uint32Array(imgData.data.buffer);
    const west = bounds.getWest(), invRw = (bounds.getEast() - west) / rw;
    const lats = new Float64Array(rh);
    for (let py = 0; py < rh; py++) lats[py] = map.containerPointToLatLng([0, py / scale]).lat;

    for (const g of this.meta.grids) {
      const la2 = g.la1 - (g.ny - 1) * g.dy, lo2 = g.lo1 + (g.nx - 1) * g.dx;
      const pxA = Math.max(0, Math.floor((g.lo1 - west) / invRw)), pxB = Math.min(rw - 1, Math.ceil((lo2 - west) / invRw));
      if (pxA > pxB) continue;
      for (let py = 0; py < rh; py++) {
        const lat = lats[py];
        if (lat > g.la1 || lat < la2) continue;
        const gy = (g.la1 - lat) / g.dy, gy0 = gy | 0, gy1 = Math.min(gy0 + 1, g.ny - 1);
        const fy = gy - gy0, fy1 = 1 - fy;
        const r0 = g.offset + gy0 * g.nx, r1 = g.offset + gy1 * g.nx, rowOff = py * rw;
        for (let px = pxA; px <= pxB; px++) {
          const gx = (west + px * invRw - g.lo1) / g.dx;
          if (gx < 0 || gx > g.nx - 1) continue;
          const gx0 = gx | 0, gx1 = Math.min(gx0 + 1, g.nx - 1), fx = gx - gx0, fx1 = 1 - fx;
          // Kuestenzellen: fehlende Ecken weglassen und mit den vorhandenen gewichten
          let s = 0, w = 0, v;
          v = grid[r0 + gx0]; if (v !== SURGE_NO_DATA) { s += v * fx1 * fy1; w += fx1 * fy1; }
          v = grid[r0 + gx1]; if (v !== SURGE_NO_DATA) { s += v * fx * fy1; w += fx * fy1; }
          v = grid[r1 + gx0]; if (v !== SURGE_NO_DATA) { s += v * fx1 * fy; w += fx1 * fy; }
          v = grid[r1 + gx1]; if (v !== SURGE_NO_DATA) { s += v * fx * fy; w += fx * fy; }
          if (w < 0.25) continue;
          let i = Math.round(s / w) + SURGE_LUT_OFFSET;
          if (i < 0) i = 0; else if (i >= SURGE_LUT_SIZE) i = SURGE_LUT_SIZE - 1;
          buf32[rowOff + px] = SURGE_LUT32[i];
        }
      }
    }
    ctx.putImageData(imgData, 0, 0);
    return imgData;
  }

  updateUI() {
    const playBtn = document.getElementById('ws-play');
    if (playBtn) playBtn.textContent = this.animTimer ? '⏸' : '▶';
    const f = this.frames[this.currentFrame];
    const label = document.getElementById('ws-time');
    if (label && f) {
      label.textContent = new Date(f.t * 1000).toLocaleString(undefined,
        {weekday: 'short', day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit'});
      label.title = f.label;
    }
    const range = document.getElementById('ws-range');
    if (range) { range.max = this.frames.length - 1; range.value = this.currentFrame; }
  }
}
