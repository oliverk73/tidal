/**
 * Pressure (GFS PRMSL) for the map, Oliver 13.11.2026 (model: windy.app type=prmsl&iso=1).
 *
 *  PressureLayer   — colour field (exclusive overlay like waves/wind), semi-transparent with coastlines on top.
 *  PressureOverlay — isobars (every 4 hPa, labels, H/L centres) and weather fronts (cold/warm/stationary),
 *                    independent overlay that can be switched on over ANY layer (like the seamarks).
 *
 * Data (py/download_pressure_forecast.py, static/pressure/):
 *   pressure_meta.json      grid + frames
 *   pressure_f{NNN}.bin     uint16 LE, 0.1 hPa, row 0 = 90°N, column 0 = 0°E
 *   pressure_f{NNN}.json    {isobaren, labels, zentren, fronten}; fronts from py/fronten.py (thermal front parameter
 *                           of 850 hPa theta-e, type from the wind across the front) — an objective model analysis.
 */

// --- Colour scale: hPa → [R, G, B, A] (low = violet/blue, normal = green/yellow, high = orange/red) ---
const PRESSURE_COLORS = [
  [950, 92, 40, 140, 125],
  [970, 60, 70, 180, 120],
  [985, 50, 130, 200, 115],
  [1000, 70, 175, 170, 110],
  [1010, 120, 190, 110, 105],
  [1016, 205, 200, 95, 105],
  [1024, 230, 160, 70, 110],
  [1035, 210, 95, 60, 120],
  [1050, 150, 40, 50, 130],
];
const PRESSURE_LUT32 = new Uint32Array(1201);       // 940.0 .. 1060.0 hPa in 0.1 hPa
(function buildPressureLUT() {
  for (let i = 0; i < PRESSURE_LUT32.length; i++) {
    const h = 940 + i / 10;
    let c = PRESSURE_COLORS[0];
    let r = c[1], g = c[2], b = c[3], a = c[4];
    if (h >= PRESSURE_COLORS[PRESSURE_COLORS.length - 1][0]) {
      c = PRESSURE_COLORS[PRESSURE_COLORS.length - 1]; r = c[1]; g = c[2]; b = c[3]; a = c[4];
    } else {
      for (let j = 0; j < PRESSURE_COLORS.length - 1; j++) {
        const s0 = PRESSURE_COLORS[j], s1 = PRESSURE_COLORS[j + 1];
        if (h >= s0[0] && h < s1[0]) {
          const t = (h - s0[0]) / (s1[0] - s0[0]);
          r = s0[1] + t * (s1[1] - s0[1]); g = s0[2] + t * (s1[2] - s0[2]);
          b = s0[3] + t * (s1[3] - s0[3]); a = s0[4] + t * (s1[4] - s0[4]);
          break;
        }
      }
    }
    PRESSURE_LUT32[i] = ((a & 0xFF) << 24) | ((b & 0xFF) << 16) | ((g & 0xFF) << 8) | (r & 0xFF);
  }
})();

// Shared data store (both layers use the same frames)
const PressureData = {
  meta: null, frames: [], grid: {}, iso: {}, _bust: '',
  async loadMeta() {
    if (this.meta && Date.now() - this._t < 10 * 60 * 1000) return this.meta;
    const r = await fetch('/static/pressure/pressure_meta.json?t=' + Date.now());
    this.meta = await r.json(); this._t = Date.now();
    this.frames = this.meta.frames; this.grid = {}; this.iso = {};
    this._bust = '?t=' + encodeURIComponent(this.meta.generated || Date.now());
    return this.meta;
  },
  async loadGrid(i) {
    if (!this.grid[i]) {
      const r = await fetch('/static/pressure/' + this.frames[i].file + this._bust);
      this.grid[i] = new Uint16Array(await r.arrayBuffer());
    }
    return this.grid[i];
  },
  async loadIso(i) {
    if (!this.iso[i]) {
      const r = await fetch('/static/pressure/' + this.frames[i].iso + this._bust);
      this.iso[i] = await r.json();
    }
    return this.iso[i];
  },
  frameTime(i) {
    const d = this.meta.date, c = parseInt(this.meta.cycle);
    const t = new Date(Date.UTC(+d.slice(0, 4), +d.slice(4, 6) - 1, +d.slice(6, 8), c));
    t.setUTCHours(t.getUTCHours() + this.frames[i].hour);
    return t;
  },
  nowFrame() {
    let best = 0, bd = Infinity;
    for (let i = 0; i < this.frames.length; i++) {
      const dd = Math.abs(this.frameTime(i) - Date.now());
      if (dd < bd) { bd = dd; best = i; }
    }
    return best;
  },
  label(i) {
    if (!this.meta || !this.frames[i]) return '--';
    const t = this.frameTime(i);
    return t.toLocaleDateString(undefined, { day: '2-digit', month: '2-digit' }) + ' ' +
           t.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' }) + ' (+' + this.frames[i].hour + 'h)';
  },
};

class PressureLayer {
  constructor(map) {
    this.map = map;
    this.currentFrame = 0;
    this.active = false;
    this.canvas = null;
    this.coast = null;
    this.animTimer = null;
    this.animDelay = 900;
    this.onFrame = null;                     // callback(idx) -> keeps the isobar/front overlay in step
    this._onMoveEnd = () => { if (this.active) this.render(); };
  }
  get frames() { return PressureData.frames; }
  async loadMeta() { return PressureData.loadMeta(); }

  activate() {
    if (this.active) return;
    this.active = true;
    const c = L.DomUtil.create('canvas');
    c.style.position = 'absolute'; c.style.pointerEvents = 'none'; c.style.zIndex = '450';
    this.canvas = c;
    this.map.getContainer().querySelector('.leaflet-overlay-pane').appendChild(c);
    this._coastlines();
    this.map.on('moveend zoomend resize', this._onMoveEnd);
    this.showFrame(PressureData.nowFrame());
  }

  async _coastlines() {
    if (!this.map.getPane('pressureCoast')) {
      const p = this.map.createPane('pressureCoast');
      p.style.zIndex = '452'; p.style.pointerEvents = 'none';
    }
    if (!this.coast) {
      const gj = await (await fetch('/static/ne_50m_land.geojson')).json();
      this.coast = L.geoJSON(gj, { pane: 'pressureCoast', interactive: false,
        style: { color: '#3b3b3b', weight: 0.9, opacity: 0.85, fill: false } });
    }
    if (this.active) this.coast.addTo(this.map);
  }

  deactivate() {
    this.active = false;
    this.stopAnim();
    this.map.off('moveend zoomend resize', this._onMoveEnd);
    if (this.canvas && this.canvas.parentNode) this.canvas.parentNode.removeChild(this.canvas);
    this.canvas = null;
    if (this.coast) this.map.removeLayer(this.coast);
  }

  async showFrame(idx, vonOverlay) {
    if (!this.active || !this.frames.length) return;
    idx = ((idx % this.frames.length) + this.frames.length) % this.frames.length;
    this.currentFrame = idx;
    await PressureData.loadGrid(idx);
    if (!this.active || idx !== this.currentFrame) return;
    this.render();
    this.updateUI();
    if (this.onFrame && !vonOverlay) this.onFrame(idx);
    PressureData.loadGrid((idx + 1) % this.frames.length);
  }

  render() {
    if (!this.canvas || !PressureData.meta) return;
    const grid = PressureData.grid[this.currentFrame];
    if (!grid) return;
    const map = this.map, size = map.getSize(), zoom = map.getZoom();
    const scale = zoom >= 6 ? 1.0 : 0.5;
    const rw = Math.ceil(size.x * scale), rh = Math.ceil(size.y * scale);
    const c = this.canvas;
    c.width = rw; c.height = rh;
    c.style.width = size.x + 'px'; c.style.height = size.y + 'px';
    L.DomUtil.setPosition(c, map.containerPointToLayerPoint([0, 0]));
    const ctx = c.getContext('2d');
    const img = ctx.createImageData(rw, rh);
    const buf = new Uint32Array(img.data.buffer);
    const g = PressureData.meta.grid, nx = g.nx, ny = g.ny;
    const colX = new Float32Array(rw);
    for (let x = 0; x < rw; x++) {
      const lon = map.containerPointToLatLng([x / scale, 0]).lng;
      colX[x] = ((((lon - g.lo1) % 360) + 360) % 360) / g.dx;
    }
    for (let y = 0; y < rh; y++) {
      const lat = map.containerPointToLatLng([0, y / scale]).lat;
      const gy = (g.la1 - lat) / g.dy;
      if (gy < 0 || gy > ny - 1) continue;
      const i0 = Math.floor(gy), i1 = Math.min(ny - 1, i0 + 1), fy = gy - i0;
      const r0 = i0 * nx, r1 = i1 * nx, o = y * rw;
      for (let x = 0; x < rw; x++) {
        const gx = colX[x];
        const j0 = Math.floor(gx) % nx, j1 = (j0 + 1) % nx, fx = gx - Math.floor(gx);
        const v = (grid[r0 + j0] * (1 - fx) + grid[r0 + j1] * fx) * (1 - fy) +
                  (grid[r1 + j0] * (1 - fx) + grid[r1 + j1] * fx) * fy;      // 0.1 hPa
        let k = Math.round(v - 9400);
        if (k < 0) k = 0; else if (k > 1200) k = 1200;
        buf[o + x] = PRESSURE_LUT32[k];
      }
    }
    ctx.putImageData(img, 0, 0);
  }

  playAnim() {
    if (this.animTimer) return;
    this.animTimer = setInterval(() => this.showFrame(this.currentFrame + 1), this.animDelay);
    this.updateUI();
  }
  stopAnim() {
    if (this.animTimer) { clearInterval(this.animTimer); this.animTimer = null; }
    this.updateUI();
  }
  toggleAnim() { this.animTimer ? this.stopAnim() : this.playAnim(); }

  updateUI() {
    const b = document.getElementById('ps-play-btn'); if (b) b.textContent = this.animTimer ? '⏸' : '▶';
    const l = document.getElementById('ps-label'); if (l) l.textContent = PressureData.label(this.currentFrame);
    const p = document.getElementById('ps-progress'); if (p) p.value = this.currentFrame;
  }
}

class PressureOverlay {
  constructor(map) {
    this.map = map;
    this.currentFrame = 0;
    this.showIsobars = false;
    this.showFronts = false;
    this.onFrame = null;                     // callback(idx) -> keeps the pressure colour layer in step
    if (!map.getPane('isobars')) {
      const p = map.createPane('isobars');
      p.style.zIndex = '455';
      p.style.pointerEvents = 'none';
    }
    this.renderer = L.canvas({ pane: 'isobars', padding: 0.5 });
    this.lines = L.layerGroup();
    this.labels = L.layerGroup();
    this.frontCanvas = null;
    this._onMove = () => { if (this.active) { this._drawLabels(); this._drawFronts(); } };
  }
  get active() { return this.showIsobars || this.showFronts; }
  get frames() { return PressureData.frames; }

  async set(isobars, fronts) {
    const vorher = this.active;
    this.showIsobars = isobars; this.showFronts = fronts;
    if (this.active && !vorher) {
      await PressureData.loadMeta();
      this.lines.addTo(this.map); this.labels.addTo(this.map);
      const fc = L.DomUtil.create('canvas');
      fc.style.position = 'absolute'; fc.style.pointerEvents = 'none'; fc.style.zIndex = '456';
      this.frontCanvas = fc;
      this.map.getPane('isobars').appendChild(fc);
      this.map.on('moveend zoomend resize', this._onMove);
      this.currentFrame = PressureData.nowFrame();
    }
    if (!this.active) {
      this.map.off('moveend zoomend resize', this._onMove);
      this.lines.clearLayers(); this.labels.clearLayers();
      this.map.removeLayer(this.lines); this.map.removeLayer(this.labels);
      if (this.frontCanvas && this.frontCanvas.parentNode) this.frontCanvas.parentNode.removeChild(this.frontCanvas);
      this.frontCanvas = null;
      return;
    }
    await this.showFrame(this.currentFrame, true);
  }

  async showFrame(idx, vonLayer) {
    if (!this.active || !this.frames.length) return;
    idx = ((idx % this.frames.length) + this.frames.length) % this.frames.length;
    this.currentFrame = idx;
    await PressureData.loadIso(idx);
    if (!this.active || idx !== this.currentFrame) return;
    this._drawIsobars(); this._drawLabels(); this._drawFronts();
    this.updateUI();
    if (this.onFrame && !vonLayer) this.onFrame(idx);
    PressureData.loadIso((idx + 1) % this.frames.length);
  }

  _drawIsobars() {
    this.lines.clearLayers();
    const d = PressureData.iso[this.currentFrame];
    if (!d || !this.showIsobars) return;
    for (const iso of d.isobaren) {
      const haupt = iso.hpa % 20 === 0;
      const style = { renderer: this.renderer, color: 'rgba(40,40,40,0.75)', weight: haupt ? 1.5 : 0.8,
                      opacity: 1, interactive: false, smoothFactor: 1.5 };
      for (const off of [-360, 0, 360]) {
        for (const seg of iso.linien) L.polyline(seg.map(p => [p[1], p[0] + off]), style).addTo(this.lines);
      }
    }
  }

  _drawLabels() {
    this.labels.clearLayers();
    const d = PressureData.iso[this.currentFrame];
    if (!d || !this.showIsobars) return;
    const b = this.map.getBounds().pad(0.05), zoom = this.map.getZoom();
    const gesetzt = [];
    const frei = (pt, abst) => gesetzt.every(q => Math.abs(q.x - pt.x) + Math.abs(q.y - pt.y) > abst);
    for (const off of [-360, 0, 360]) {
      for (const [lon, lat, art, hpa] of d.zentren) {
        const ll = L.latLng(lat, lon + off);
        if (!b.contains(ll)) continue;
        const pt = this.map.latLngToContainerPoint(ll);
        if (!frei(pt, 60)) continue;
        gesetzt.push(pt);
        const farbe = art === 'H' ? '#c0392b' : '#1f4e9c';
        L.marker(ll, { interactive: false, keyboard: false, icon: L.divIcon({ className: 'ps-zentrum',
          html: '<div style="font:bold 22px sans-serif;color:' + farbe + ';text-shadow:0 0 3px #fff,0 0 3px #fff;line-height:22px;text-align:center">' + art +
                '<div style="font:bold 11px sans-serif">' + hpa + '</div></div>', iconSize: [40, 36], iconAnchor: [20, 18] }) }).addTo(this.labels);
      }
    }
    if (zoom < 2) return;
    for (const off of [-360, 0, 360]) {
      for (const [lon, lat, hpa] of d.labels) {
        const ll = L.latLng(lat, lon + off);
        if (!b.contains(ll)) continue;
        const pt = this.map.latLngToContainerPoint(ll);
        if (!frei(pt, 70)) continue;
        gesetzt.push(pt);
        L.marker(ll, { interactive: false, keyboard: false, icon: L.divIcon({ className: 'ps-label',
          html: '<span style="font:600 10px sans-serif;color:#222;background:rgba(255,255,255,0.75);padding:0 2px;border-radius:2px">' + hpa + '</span>',
          iconSize: [30, 12], iconAnchor: [15, 6] }) }).addTo(this.labels);
      }
    }
  }

  _drawFronts() {
    const c = this.frontCanvas;
    if (!c) return;
    const map = this.map, size = map.getSize();
    c.width = size.x; c.height = size.y;
    c.style.width = size.x + 'px'; c.style.height = size.y + 'px';
    L.DomUtil.setPosition(c, map.containerPointToLayerPoint([0, 0]));
    const ctx = c.getContext('2d');
    ctx.clearRect(0, 0, size.x, size.y);
    const d = PressureData.iso[this.currentFrame];
    if (!d || !d.fronten || !this.showFronts) return;
    const FARBE = { kalt: '#1f5fd1', warm: '#d62828', stationaer: '#8a4fbf' };
    const ABST = 34, GR = 7;                                 // px between symbols, symbol size
    for (const off of [-360, 0, 360]) {
      for (const f of d.fronten) {
        const pts = f.linie.map(p => map.latLngToContainerPoint([p[1], p[0] + off]));
        if (pts.every(p => p.x < -50 || p.x > size.x + 50 || p.y < -50 || p.y > size.y + 50)) continue;
        ctx.strokeStyle = FARBE[f.typ]; ctx.fillStyle = FARBE[f.typ];
        ctx.lineWidth = f.typ === 'stationaer' ? 1.4 : 2.4;
        ctx.setLineDash(f.typ === 'stationaer' ? [6, 5] : []);
        ctx.beginPath();
        pts.forEach((p, i) => (i ? ctx.lineTo(p.x, p.y) : ctx.moveTo(p.x, p.y)));
        ctx.stroke();
        ctx.setLineDash([]);
        if (f.typ === 'stationaer') continue;
        // symbols: cold front triangles toward the warm side, warm front semicircles toward the cold side
        let rest = ABST / 2;
        for (let i = 0; i < pts.length - 1; i++) {
          const a = pts[i], b = pts[i + 1];
          const dx = b.x - a.x, dy = b.y - a.y, len = Math.hypot(dx, dy);
          if (len < 1e-6) continue;
          const tx = dx / len, ty = dy / len;
          const w = (f.warm[i] || 0) * Math.PI / 180;
          const wx = Math.sin(w), wy = -Math.cos(w);          // warm side in screen coords (north up)
          let nx = -ty, ny = tx;
          const zurWarm = nx * wx + ny * wy >= 0 ? 1 : -1;
          const seite = f.typ === 'kalt' ? zurWarm : -zurWarm;
          nx *= seite; ny *= seite;
          let s = rest;
          while (s < len) {
            const cx = a.x + tx * s, cy = a.y + ty * s;
            ctx.beginPath();
            if (f.typ === 'kalt') {
              ctx.moveTo(cx - tx * GR, cy - ty * GR);
              ctx.lineTo(cx + tx * GR, cy + ty * GR);
              ctx.lineTo(cx + nx * GR * 1.3, cy + ny * GR * 1.3);
            } else {
              const ang = Math.atan2(ny, nx);
              ctx.arc(cx, cy, GR, ang - Math.PI / 2, ang + Math.PI / 2);
            }
            ctx.closePath(); ctx.fill();
            s += ABST;
          }
          rest = s - len;
        }
      }
    }
  }

  updateUI() {
    const l = document.getElementById('po-label'); if (l) l.textContent = PressureData.label(this.currentFrame);
    const p = document.getElementById('po-progress'); if (p) { p.max = this.frames.length - 1; p.value = this.currentFrame; }
  }
}

window.PressureLayer = PressureLayer;
window.PressureOverlay = PressureOverlay;
window.PressureData = PressureData;
