/**
 * PressureLayer — sea-level pressure (GFS PRMSL) as a colour field with isobars, H/L centres and labels.
 * Oliver 13.11.2026 (model: windy.app type=prmsl&iso=1).
 *
 * Data (py/download_pressure_forecast.py, static/pressure/):
 *   pressure_meta.json      grid + frames
 *   pressure_f{NNN}.bin     uint16 LE, 0.1 hPa, row 0 = 90°N, column 0 = 0°E
 *   pressure_f{NNN}.json    {isobaren:[{hpa, linien:[[[lon,lat],..],..]}], labels:[[lon,lat,hpa]], zentren:[[lon,lat,'H'|'L',hpa]]}
 * Isobars every 4 hPa, longitudes -180..180; drawn three times (-360, 0, +360) so they follow the map when panned
 * across the date line.
 */

// --- Colour scale: hPa → [R, G, B, A] (low = violet/blue, normal = green/yellow, high = orange/red) ---
const PRESSURE_COLORS = [
  [950, 92, 40, 140, 170],
  [970, 60, 70, 180, 165],
  [985, 50, 130, 200, 160],
  [1000, 70, 175, 170, 155],
  [1010, 120, 190, 110, 150],
  [1016, 205, 200, 95, 150],
  [1024, 230, 160, 70, 160],
  [1035, 210, 95, 60, 170],
  [1050, 150, 40, 50, 180],
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

class PressureLayer {
  constructor(map) {
    this.map = map;
    this.meta = null;
    this.frames = [];
    this.gridCache = {};
    this.isoCache = {};
    this.currentFrame = 0;
    this.active = false;
    this.canvas = null;
    this.animTimer = null;
    this.animDelay = 900;
    if (!map.getPane('isobars')) {
      const p = map.createPane('isobars');
      p.style.zIndex = '455';
      p.style.pointerEvents = 'none';
    }
    this.renderer = L.canvas({ pane: 'isobars', padding: 0.5 });
    this.lines = L.layerGroup();
    this.labels = L.layerGroup();
    this._onMoveEnd = () => { if (this.active) { this.render(); this._drawLabels(); } };
  }

  async loadMeta() {
    const resp = await fetch('/static/pressure/pressure_meta.json?t=' + Date.now());
    this.meta = await resp.json();
    this.frames = this.meta.frames;
    this._cacheBust = '?t=' + encodeURIComponent(this.meta.generated || Date.now());
    this.gridCache = {}; this.isoCache = {};
    return this.meta;
  }

  async loadGrid(i) {
    if (!this.gridCache[i]) {
      const r = await fetch('/static/pressure/' + this.frames[i].file + this._cacheBust);
      this.gridCache[i] = new Uint16Array(await r.arrayBuffer());
    }
    return this.gridCache[i];
  }

  async loadIso(i) {
    if (!this.isoCache[i]) {
      const r = await fetch('/static/pressure/' + this.frames[i].iso + this._cacheBust);
      this.isoCache[i] = await r.json();
    }
    return this.isoCache[i];
  }

  activate() {
    if (this.active) return;
    this.active = true;
    const c = L.DomUtil.create('canvas');
    c.style.position = 'absolute'; c.style.pointerEvents = 'none'; c.style.zIndex = '450';
    this.canvas = c;
    this.map.getContainer().querySelector('.leaflet-overlay-pane').appendChild(c);
    this.lines.addTo(this.map);
    this.labels.addTo(this.map);
    this.map.on('moveend zoomend resize', this._onMoveEnd);
    this.showFrame(this.currentFrame);
  }

  deactivate() {
    this.active = false;
    this.stopAnim();
    this.map.off('moveend zoomend resize', this._onMoveEnd);
    if (this.canvas && this.canvas.parentNode) this.canvas.parentNode.removeChild(this.canvas);
    this.canvas = null;
    this.lines.clearLayers(); this.labels.clearLayers();
    this.map.removeLayer(this.lines); this.map.removeLayer(this.labels);
  }

  async showFrame(idx) {
    if (!this.active || !this.frames.length) return;
    idx = ((idx % this.frames.length) + this.frames.length) % this.frames.length;
    this.currentFrame = idx;
    await Promise.all([this.loadGrid(idx), this.loadIso(idx)]);
    if (!this.active || idx !== this.currentFrame) return;
    this.render();
    this._drawIsobars();
    this._drawLabels();
    this.updateUI();
    // prefetch next frame
    const n = (idx + 1) % this.frames.length;
    this.loadGrid(n); this.loadIso(n);
  }

  render() {
    if (!this.canvas || !this.meta) return;
    const grid = this.gridCache[this.currentFrame];
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
    const g = this.meta.grid, nx = g.nx, ny = g.ny;
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

  _drawIsobars() {
    this.lines.clearLayers();
    const d = this.isoCache[this.currentFrame];
    if (!d) return;
    for (const iso of d.isobaren) {
      const haupt = iso.hpa % 20 === 0;                      // every 20 hPa a bit stronger
      const style = { renderer: this.renderer, color: 'rgba(255,255,255,0.85)', weight: haupt ? 1.6 : 0.9,
                      opacity: 1, interactive: false, smoothFactor: 1.5 };
      for (const off of [-360, 0, 360]) {
        for (const seg of iso.linien) {
          L.polyline(seg.map(p => [p[1], p[0] + off]), style).addTo(this.lines);
        }
      }
    }
  }

  _drawLabels() {
    this.labels.clearLayers();
    const d = this.isoCache[this.currentFrame];
    if (!d) return;
    const b = this.map.getBounds().pad(0.05), zoom = this.map.getZoom();
    const minAbst = 70;                                       // px between isobar labels
    const gesetzt = [];
    const frei = (pt) => gesetzt.every(q => Math.abs(q.x - pt.x) + Math.abs(q.y - pt.y) > minAbst);
    // centres first (larger, take priority)
    for (const off of [-360, 0, 360]) {
      for (const [lon, lat, art, hpa] of d.zentren) {
        const ll = L.latLng(lat, lon + off);
        if (!b.contains(ll)) continue;
        const pt = this.map.latLngToContainerPoint(ll);
        if (!frei(pt)) continue;
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
        if (!frei(pt)) continue;
        gesetzt.push(pt);
        L.marker(ll, { interactive: false, keyboard: false, icon: L.divIcon({ className: 'ps-label',
          html: '<span style="font:600 10px sans-serif;color:#222;background:rgba(255,255,255,0.75);padding:0 2px;border-radius:2px">' + hpa + '</span>',
          iconSize: [30, 12], iconAnchor: [15, 6] }) }).addTo(this.labels);
      }
    }
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

  formatDateTime(i) {
    if (!this.meta || !this.frames[i]) return '--';
    const d = this.meta.date, c = parseInt(this.meta.cycle);
    const t = new Date(Date.UTC(+d.slice(0, 4), +d.slice(4, 6) - 1, +d.slice(6, 8), c));
    t.setUTCHours(t.getUTCHours() + this.frames[i].hour);
    return t.toLocaleDateString(undefined, { day: '2-digit', month: '2-digit' }) + ' ' +
           t.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' }) + ' (+' + this.frames[i].hour + 'h)';
  }

  updateUI() {
    const b = document.getElementById('ps-play-btn'); if (b) b.textContent = this.animTimer ? '⏸' : '▶';
    const l = document.getElementById('ps-label'); if (l) l.textContent = this.formatDateTime(this.currentFrame);
    const p = document.getElementById('ps-progress'); if (p) p.value = this.currentFrame;
  }
}

window.PressureLayer = PressureLayer;
