/**
 * TideCanvasLayer — Leaflet Canvas overlay for FES2022 tide height forecasts.
 * Renders signed int16 binary grids (mm) as a diverging color overlay.
 *
 * Binary format: int16 LE, value = tide_height_meters * 1000
 *   → +1500 = +1.5m, -800 = -0.8m, -32768 = no data (land)
 *
 * Color scale: diverging blue (low tide) → white (0) → red/brown (high tide)
 */

// --- Tide color scale: meters → [R, G, B, A] ---
const TIDE_COLORS = [
  [-8.0,  20,  20,  80, 200],   // extreme low: very dark blue
  [-4.0,  30,  50, 160, 195],   // very low: dark blue
  [-2.0,  40, 100, 200, 185],   // low: blue
  [-1.0,  80, 160, 220, 175],   // moderately low: light blue
  [-0.5, 140, 200, 235, 165],   // slightly low: pale blue
  [ 0.0, 220, 225, 230, 155],   // mean level: near white / light grey
  [ 0.5, 235, 195, 140, 165],   // slightly high: warm cream
  [ 1.0, 220, 155,  80, 175],   // moderately high: orange
  [ 2.0, 200, 100,  40, 185],   // high: dark orange
  [ 4.0, 170,  40,  30, 195],   // very high: red-brown
  [ 8.0, 100,  15,  15, 200],   // extreme high: dark red
];

// LUT: 16001 entries covering -8.000m to +8.000m in 1mm steps
// index = value_mm + 8000
const TIDE_LUT_OFFSET = 8000;  // index for 0m
const TIDE_LUT_SIZE = 16001;
const TIDE_LUT32 = new Uint32Array(TIDE_LUT_SIZE);
const TIDE_NO_DATA = -32768;

(function buildTideLUT() {
  for (let i = 0; i < TIDE_LUT_SIZE; i++) {
    const hm = (i - TIDE_LUT_OFFSET) / 1000.0; // meters
    let r = 0, g = 0, b = 0, a = 0;

    if (hm <= TIDE_COLORS[0][0]) {
      const s = TIDE_COLORS[0];
      r = s[1]; g = s[2]; b = s[3]; a = s[4];
    } else if (hm >= TIDE_COLORS[TIDE_COLORS.length - 1][0]) {
      const s = TIDE_COLORS[TIDE_COLORS.length - 1];
      r = s[1]; g = s[2]; b = s[3]; a = s[4];
    } else {
      for (let j = 0; j < TIDE_COLORS.length - 1; j++) {
        const s0 = TIDE_COLORS[j], s1 = TIDE_COLORS[j + 1];
        if (hm >= s0[0] && hm < s1[0]) {
          const t = (hm - s0[0]) / (s1[0] - s0[0]);
          r = s0[1] + t * (s1[1] - s0[1]);
          g = s0[2] + t * (s1[2] - s0[2]);
          b = s0[3] + t * (s1[3] - s0[3]);
          a = s0[4] + t * (s1[4] - s0[4]);
          break;
        }
      }
    }
    TIDE_LUT32[i] = ((a & 0xFF) << 24) | ((b & 0xFF) << 16) | ((g & 0xFF) << 8) | (r & 0xFF);
  }
})();


class TideCanvasLayer {
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
    this._landMask = null;
    this._landPane = null;
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
    const f = this.frames[frameIdx];
    const resp = await fetch('/static/tides/' + f.file + (this._cacheBust || ''));
    const buf = await resp.arrayBuffer();
    this.gridCache[frameIdx] = new Int16Array(buf);
    return this.gridCache[frameIdx];
  }

  async preloadAll() {
    await Promise.all(this.frames.map((_, i) => this.loadGrid(i)));
  }

  async _loadLandMask() {
    if (this._landMask) return;
    const resp = await fetch('/static/ne_10m_land.geojson');
    const geojson = await resp.json();

    // Create a pane above the tide canvas (zIndex 451) but below markers
    if (!this.map.getPane('tideLandMask')) {
      this._landPane = this.map.createPane('tideLandMask');
      this._landPane.style.zIndex = '451';
      this._landPane.style.pointerEvents = 'none';
    } else {
      this._landPane = this.map.getPane('tideLandMask');
    }

    this._landMask = L.geoJSON(geojson, {
      pane: 'tideLandMask',
      style: {
        fillColor: '#f2efe9',  // matches CARTO light land color
        fillOpacity: 1.0,
        stroke: false,
      },
      interactive: false,
    });
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

    const pane = this.map.getContainer().querySelector('.leaflet-overlay-pane');
    pane.appendChild(canvas);

    // Show land mask
    this._loadLandMask().then(() => {
      if (this.active && this._landMask) {
        this._landMask.addTo(this.map);
      }
    });

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

    // Hide land mask
    if (this._landMask && this.map.hasLayer(this._landMask)) {
      this.map.removeLayer(this._landMask);
    }
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

    const cached = this._frameRenderCache[this.currentFrame];
    if (cached && cached.viewKey === baseViewKey) {
      const canvas = this.canvas;
      canvas.width = cached.cw;
      canvas.height = cached.ch;
      canvas.style.width = size.x + 'px';
      canvas.style.height = size.y + 'px';
      L.DomUtil.setPosition(canvas, topLeft);
      canvas.getContext('2d').putImageData(cached.imgData, 0, 0);
      return;
    }

    const imgData = this._renderGrid(grid, size, bounds, zoom, topLeft);
    const scale = zoom >= 5 ? 1.0 : 0.5;
    this._frameRenderCache[this.currentFrame] = {
      viewKey: baseViewKey,
      imgData: imgData,
      cw: Math.ceil(size.x * scale),
      ch: Math.ceil(size.y * scale),
    };
  }

  _renderGrid(grid, size, bounds, zoom, topLeft) {
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
    // Handle grids that start at negative longitude (e.g. -180)
    const lo2 = g.lo2;

    const west = bounds.getWest();
    const lonSpan = bounds.getEast() - west;
    const invRw = lonSpan / rw;

    // Precompute lat → grid Y
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
        // Normalize to grid longitude range
        if (lon < lo1) lon += 360;
        if (lon > lo2 + dx) continue;

        const gx = (lon - lo1) / dx;
        if (gx < 0) continue;

        const gx0 = gx | 0;
        if (gx0 >= gnx - 1) continue;
        const gx1 = gx0 + 1;
        const fx = gx - gx0;
        const fx1 = 1 - fx;

        // Check for no-data in any corner (land masking)
        const v00 = grid[row0 + gx0];
        const v01 = grid[row0 + gx1];
        const v10 = grid[row1 + gx0];
        const v11 = grid[row1 + gx1];

        if (v00 === TIDE_NO_DATA || v01 === TIDE_NO_DATA ||
            v10 === TIDE_NO_DATA || v11 === TIDE_NO_DATA) continue;

        const val = v00 * fx1 * fy1 +
                    v01 * fx  * fy1 +
                    v10 * fx1 * fy +
                    v11 * fx  * fy;

        // LUT index: val is in mm, offset by 8000
        const lutIdx = Math.round(val) + TIDE_LUT_OFFSET;
        if (lutIdx < 0 || lutIdx >= TIDE_LUT_SIZE) continue;

        const color32 = TIDE_LUT32[lutIdx];
        if (color32 === 0) continue;

        buf32[rowOff + px] = color32;
      }
    }

    ctx.putImageData(imgData, 0, 0);
    return imgData;
  }

  // --- Animation ---
  toggleAnim() {
    if (this.animTimer) {
      this.stopAnim();
    } else {
      this.startAnim();
    }
  }

  startAnim() {
    if (this.animTimer) return;
    const step = () => {
      this.showFrame(this.currentFrame + 1);
      this.animTimer = setTimeout(step, this.animDelay);
    };
    this.animTimer = setTimeout(step, this.animDelay);
    this.updateUI();
  }

  stopAnim() {
    if (this.animTimer) {
      clearTimeout(this.animTimer);
      this.animTimer = null;
    }
    this.updateUI();
  }

  updateUI() {
    const playBtn = document.getElementById('td-play');
    if (playBtn) playBtn.textContent = this.animTimer ? '\u23F8' : '\u25B6';

    const label = document.getElementById('td-time');
    if (label && this.frames[this.currentFrame]) {
      label.textContent = this.frames[this.currentFrame].label;
    }

    const range = document.getElementById('td-range');
    if (range) {
      range.max = this.frames.length - 1;
      range.value = this.currentFrame;
    }
  }
}
