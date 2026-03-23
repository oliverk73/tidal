/**
 * SSTCanvasLayer — Leaflet Canvas overlay for sea surface temperature.
 * Renders NOAA OISST binary data as a smooth color-interpolated overlay.
 *
 * Binary format: uint16 LE, value = (T_celsius + 50) * 100
 *   → 0 = no data (land), 5000 = 0°C, 7500 = 25°C
 *
 * Same architecture as PrecipCanvasLayer for consistency.
 */

// --- SST color scale: °C → [R, G, B, A] ---
const SST_COLORS = [
  [-2.0,  200, 220, 255, 180],  // ice: very light blue
  [ 0.0,  140, 170, 230, 180],  // near-freezing: light steel blue
  [ 4.0,   60, 100, 200, 175],  // cold: blue
  [ 8.0,   30, 140, 210, 170],  // cool: medium blue
  [12.0,    0, 180, 200, 168],  // mild: teal
  [16.0,   30, 195, 145, 165],  // warm-mild: sea green
  [20.0,  100, 210,  80, 163],  // warm: yellow-green
  [24.0,  200, 215,  30, 165],  // warm: yellow
  [27.0,  240, 170,  10, 170],  // tropical: orange-yellow
  [29.0,  240, 110,  20, 178],  // hot: orange
  [31.0,  210,  40,  30, 185],  // very hot: red
  [34.0,  160,  20,  80, 190]   // extreme: dark magenta
];

// LUT: 4000 entries, index = (value - 4800) → covers -2°C to +38°C
// value = (T+50)*100, so T=-2 → 4800, T=38 → 8800
const SST_LUT_OFFSET = 4800;  // value for -2°C
const SST_LUT_SIZE = 4001;    // -2°C to +38°C in 0.01°C steps
const SST_LUT32 = new Uint32Array(SST_LUT_SIZE);
(function buildSSTLUT() {
  for (let i = 0; i < SST_LUT_SIZE; i++) {
    const tc = -2.0 + i * 0.01; // °C
    let r = 0, g = 0, b = 0, a = 0;
    if (tc < SST_COLORS[0][0]) {
      const s = SST_COLORS[0];
      r = s[1]; g = s[2]; b = s[3]; a = s[4];
    } else {
      for (let j = 0; j < SST_COLORS.length - 1; j++) {
        const s0 = SST_COLORS[j], s1 = SST_COLORS[j + 1];
        if (tc >= s0[0] && tc < s1[0]) {
          const t = (tc - s0[0]) / (s1[0] - s0[0]);
          r = s0[1] + t * (s1[1] - s0[1]);
          g = s0[2] + t * (s1[2] - s0[2]);
          b = s0[3] + t * (s1[3] - s0[3]);
          a = s0[4] + t * (s1[4] - s0[4]);
          break;
        }
      }
      if (tc >= SST_COLORS[SST_COLORS.length - 1][0]) {
        const s = SST_COLORS[SST_COLORS.length - 1];
        r = s[1]; g = s[2]; b = s[3]; a = s[4];
      }
    }
    SST_LUT32[i] = ((a & 0xFF) << 24) | ((b & 0xFF) << 16) | ((g & 0xFF) << 8) | (r & 0xFF);
  }
})();


class SSTCanvasLayer {
  constructor(map) {
    this.map = map;
    this.meta = null;
    this.grid = null;
    this.canvas = null;
    this.active = false;
    this._renderViewKey = '';
    this._cachedImgData = null;
    this._cachedViewKey = '';
    this._onMoveEnd = () => {
      if (this.active) {
        this._renderViewKey = '';
        this._cachedImgData = null;
        this.render();
      }
    };
  }

  async loadMeta(url) {
    const resp = await fetch(url + '?t=' + Date.now());
    this.meta = await resp.json();
    this._cacheBust = this.meta.generated ? '?t=' + encodeURIComponent(this.meta.generated) : '';
    return this.meta;
  }

  async loadGrid() {
    if (this.grid) return this.grid;
    const resp = await fetch('/static/sst/' + this.meta.file + (this._cacheBust || ''));
    const buf = await resp.arrayBuffer();
    this.grid = new Uint16Array(buf);
    return this.grid;
  }

  activate() {
    if (this.active) return;
    this.active = true;
    const canvas = L.DomUtil.create('canvas');
    canvas.style.position = 'absolute';
    canvas.style.pointerEvents = 'none';
    canvas.style.zIndex = '449';
    canvas.style.imageRendering = 'auto';
    this.canvas = canvas;
    this.map.getContainer().querySelector('.leaflet-overlay-pane').appendChild(canvas);
    this.map.on('moveend zoomend resize', this._onMoveEnd);
    this.render();
  }

  deactivate() {
    this.active = false;
    this.map.off('moveend zoomend resize', this._onMoveEnd);
    if (this.canvas && this.canvas.parentNode) this.canvas.parentNode.removeChild(this.canvas);
    this.canvas = null;
    this._cachedImgData = null;
  }

  render() {
    if (!this.canvas || !this.meta || !this.active || !this.grid) return;

    const map = this.map;
    const size = map.getSize();
    const bounds = map.getBounds();
    const zoom = map.getZoom();

    const topLeft = map.containerPointToLayerPoint([0, 0]);
    const viewKey = zoom + '|' +
      bounds.getNorth().toFixed(4) + ',' + bounds.getWest().toFixed(4) + ',' +
      bounds.getSouth().toFixed(4) + ',' + bounds.getEast().toFixed(4) + '|' +
      size.x + 'x' + size.y;

    if (viewKey === this._renderViewKey) return;
    this._renderViewKey = viewKey;

    // Check cache
    if (this._cachedImgData && this._cachedViewKey === viewKey) {
      const canvas = this.canvas;
      canvas.width = this._cachedImgData.rw;
      canvas.height = this._cachedImgData.rh;
      canvas.style.width = size.x + 'px';
      canvas.style.height = size.y + 'px';
      L.DomUtil.setPosition(canvas, topLeft);
      canvas.getContext('2d').putImageData(this._cachedImgData.imgData, 0, 0);
      return;
    }

    // Render at half resolution for performance at low zoom
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
    const grid = this.grid;

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

        // Check if any corner is land (value 0) — skip to avoid interpolation artifacts
        const v00 = grid[row0 + gx0];
        const v01 = grid[row0 + gx1];
        const v10 = grid[row1 + gx0];
        const v11 = grid[row1 + gx1];
        if (v00 === 0 || v01 === 0 || v10 === 0 || v11 === 0) continue;

        const val = v00 * fx1 * fy1 +
                    v01 * fx  * fy1 +
                    v10 * fx1 * fy +
                    v11 * fx  * fy;

        // LUT index: val - offset (4800 = -2°C)
        const lutIdx = Math.round(val) - SST_LUT_OFFSET;
        if (lutIdx < 0 || lutIdx >= SST_LUT_SIZE) continue;
        const c = SST_LUT32[lutIdx];
        if (c === 0) continue;
        buf32[rowOff + px] = c;
      }
    }

    ctx.putImageData(imgData, 0, 0);

    // Cache
    this._cachedImgData = { viewKey: viewKey, imgData: imgData, rw: rw, rh: rh };
    this._cachedViewKey = viewKey;
  }

  getDateLabel() {
    if (!this.meta) return '--';
    return 'NOAA OISST ' + this.meta.date;
  }
}

window.SSTCanvasLayer = SSTCanvasLayer;
