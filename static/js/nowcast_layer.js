/**
 * NowcastCanvasLayer — Leaflet Canvas overlay for PySTEPS radar nowcast grids.
 * Supports MULTIPLE REGIONS simultaneously (e.g. Europe + USA on one layer).
 * Renders binary uint16 LE data (values in 0.01 mm/h) with radar color scale.
 * Shows coverage rectangles on the map when active.
 */

const NOWCAST_COLORS = [
  [0.0,   0, 0, 0, 0],
  [0.1,   0, 0, 0, 0],
  [0.2,   120, 200, 255, 130],
  [0.5,   60, 150, 255, 150],
  [1.0,   20, 100, 240, 165],
  [2.0,   40, 200, 40, 175],
  [4.0,   200, 230, 0, 185],
  [8.0,   255, 200, 0, 195],
  [16.0,  255, 120, 0, 210],
  [32.0,  230, 30, 30, 220],
  [64.0,  170, 0, 120, 230],
  [100.0, 100, 0, 100, 240]
];

const NOWCAST_LUT32 = new Uint32Array(2048);
(function buildNowcastLUT() {
  for (let i = 0; i < 2048; i++) {
    const mmh = i * 0.05;
    let r = 0, g = 0, b = 0, a = 0;
    for (let j = 0; j < NOWCAST_COLORS.length - 1; j++) {
      const s0 = NOWCAST_COLORS[j], s1 = NOWCAST_COLORS[j + 1];
      if (mmh >= s0[0] && mmh < s1[0]) {
        const t = (mmh - s0[0]) / (s1[0] - s0[0]);
        r = s0[1] + t * (s1[1] - s0[1]);
        g = s0[2] + t * (s1[2] - s0[2]);
        b = s0[3] + t * (s1[3] - s0[3]);
        a = s0[4] + t * (s1[4] - s0[4]);
        break;
      }
    }
    if (mmh >= NOWCAST_COLORS[NOWCAST_COLORS.length - 1][0]) {
      const s = NOWCAST_COLORS[NOWCAST_COLORS.length - 1];
      r = s[1]; g = s[2]; b = s[3]; a = s[4];
    }
    NOWCAST_LUT32[i] = ((a & 0xFF) << 24) | ((b & 0xFF) << 16) | ((g & 0xFF) << 8) | (r & 0xFF);
  }
})();


class NowcastCanvasLayer {
  constructor(map) {
    this.map = map;
    this.regions = [];        // array of { meta, gridCache, baseUrl }
    this.canvas = null;
    this.currentFrame = 0;
    this.nFrames = 0;
    this.animTimer = null;
    this.animDelay = 800;
    this.active = false;
    this._renderViewKey = '';
    this._frameRenderCache = {};
    this._coverageRects = [];
    this._onMoveEnd = () => {
      if (this.active) {
        this._renderViewKey = '';
        this._frameRenderCache = {};
        this.render();
      }
    };
  }

  async addRegion(metaUrl) {
    const baseUrl = metaUrl.replace(/[^/]*$/, '');
    const resp = await fetch(metaUrl + '?t=' + Date.now());
    const meta = await resp.json();
    const cacheBust = meta.generated ? '?t=' + encodeURIComponent(meta.generated) : '';

    const region = { meta: meta, gridCache: {}, baseUrl: baseUrl, cacheBust: cacheBust };

    // Preload all grids
    const promises = meta.frames.map(async (frame, i) => {
      const r = await fetch(baseUrl + frame.file + cacheBust);
      const buf = await r.arrayBuffer();
      region.gridCache[i] = new Uint16Array(buf);
    });
    await Promise.all(promises);

    this.regions.push(region);

    // Use the frame count from the first region (all regions should have same count)
    if (this.nFrames === 0) this.nFrames = meta.frames.length;

    return region;
  }

  clearRegions() {
    this.regions = [];
    this.nFrames = 0;
    this._frameRenderCache = {};
  }

  activate() {
    if (this.active) return;
    this.active = true;
    const canvas = L.DomUtil.create('canvas');
    canvas.style.position = 'absolute';
    canvas.style.pointerEvents = 'none';
    canvas.style.zIndex = '453';
    canvas.style.imageRendering = 'auto';
    this.canvas = canvas;
    this.map.getContainer().querySelector('.leaflet-overlay-pane').appendChild(canvas);
    this.map.on('moveend zoomend resize', this._onMoveEnd);

    // Coverage rectangles disabled — visual clutter with many regions.
    // Enable via showCoverageBoxes() if needed for debugging.

    // Start at "now" frame
    const r0 = this.regions[0];
    if (r0) {
      const nowIdx = r0.meta.frames.findIndex(function (f) { return f.offset_min === 0; });
      this.showFrame(nowIdx >= 0 ? nowIdx : 0);
    }
  }

  deactivate() {
    this.active = false;
    this.stopAnim();
    this.map.off('moveend zoomend resize', this._onMoveEnd);
    if (this.canvas && this.canvas.parentNode) this.canvas.parentNode.removeChild(this.canvas);
    this.canvas = null;
    this._frameRenderCache = {};
    this._hideCoverage();
  }

  // Optional debugging helper — call showCoverageBoxes() from console to see them.
  showCoverageBoxes() {
    this._hideCoverage();
    for (var i = 0; i < this.regions.length; i++) {
      var g = this.regions[i].meta.grid;
      var desc = this.regions[i].meta.description || this.regions[i].meta.region || '';
      var rect = L.rectangle(
        [[g.la2, g.lo1], [g.la1, g.lo2]],
        { color: '#4488cc', weight: 1.5, fillOpacity: 0.03, dashArray: '6,4', interactive: false }
      );
      rect.bindTooltip('Nowcast: ' + desc, { sticky: true, opacity: 0.8 });
      rect.addTo(this.map);
      this._coverageRects.push(rect);
    }
  }

  _hideCoverage() {
    for (var i = 0; i < this._coverageRects.length; i++) {
      this.map.removeLayer(this._coverageRects[i]);
    }
    this._coverageRects = [];
  }

  async showFrame(idx) {
    if (!this.active || this.nFrames === 0) return;
    idx = ((idx % this.nFrames) + this.nFrames) % this.nFrames;
    this.currentFrame = idx;
    this._renderViewKey = '';
    this.render();
    this.updateUI();
  }

  _renderRegion(buf32, rw, rh, region, scale, bounds, map) {
    var grid = region.gridCache[this.currentFrame];
    if (!grid) return;

    var g = region.meta.grid;
    var gnx = g.nx, gny = g.ny;
    var la1 = g.la1, lo1 = g.lo1, lo2 = g.lo2, dx = g.dx, dy = g.dy;

    var west = bounds.getWest();
    var lonSpan = bounds.getEast() - west;
    var invRw = lonSpan / rw;

    // Precompute lat → grid Y
    var rowGy = new Float32Array(rh);
    var rowValid = new Uint8Array(rh);
    for (var py = 0; py < rh; py++) {
      var lat = map.containerPointToLatLng([0, py / scale]).lat;
      if (lat > 90 || lat < -90) continue;
      var gy = (la1 - lat) / dy;
      if (gy < 0 || gy >= gny - 1) continue;
      rowGy[py] = gy;
      rowValid[py] = 1;
    }

    for (var py = 0; py < rh; py++) {
      if (!rowValid[py]) continue;
      var gy = rowGy[py];
      var gy0 = gy | 0;
      var gy1 = gy0 + 1 < gny ? gy0 + 1 : gy0;
      var fy = gy - gy0;
      var fy1 = 1 - fy;
      var row0 = gy0 * gnx;
      var row1 = gy1 * gnx;
      var rowOff = py * rw;

      for (var px = 0; px < rw; px++) {
        var lon = west + px * invRw;
        if (lon < lo1 || lon > lo2) continue;

        var gx = (lon - lo1) / dx;
        if (gx < 0 || gx >= gnx - 1) continue;

        var gx0 = gx | 0;
        var gx1 = gx0 + 1;
        var fx = gx - gx0;
        var fx1 = 1 - fx;

        var val = grid[row0 + gx0] * fx1 * fy1 +
                  grid[row0 + gx1] * fx  * fy1 +
                  grid[row1 + gx0] * fx1 * fy +
                  grid[row1 + gx1] * fx  * fy;

        if (val < 20) continue;

        var lutIdx = Math.min(2047, (val / 5) | 0);
        var c = NOWCAST_LUT32[lutIdx];
        if (c === 0) continue;
        // Only overwrite if new value is stronger (max compositing)
        if (buf32[rowOff + px] === 0 || val > 20) {
          buf32[rowOff + px] = c;
        }
      }
    }
  }

  render() {
    if (!this.canvas || !this.active || this.regions.length === 0) return;

    var map = this.map;
    var size = map.getSize();
    var bounds = map.getBounds();
    var zoom = map.getZoom();
    var topLeft = map.containerPointToLayerPoint([0, 0]);

    var baseViewKey = zoom + '|' +
      bounds.getNorth().toFixed(4) + ',' + bounds.getWest().toFixed(4) + ',' +
      bounds.getSouth().toFixed(4) + ',' + bounds.getEast().toFixed(4) + '|' +
      size.x + 'x' + size.y;
    var frameKey = this.currentFrame + '|' + baseViewKey;

    if (frameKey === this._renderViewKey) return;
    this._renderViewKey = frameKey;

    var cached = this._frameRenderCache[this.currentFrame];
    if (cached && cached.viewKey === baseViewKey) {
      var canvas = this.canvas;
      canvas.width = cached.rw;
      canvas.height = cached.rh;
      canvas.style.width = size.x + 'px';
      canvas.style.height = size.y + 'px';
      L.DomUtil.setPosition(canvas, topLeft);
      canvas.getContext('2d').putImageData(cached.imgData, 0, 0);
      return;
    }

    var scale = zoom >= 5 ? 1.0 : 0.5;
    var rw = Math.ceil(size.x * scale);
    var rh = Math.ceil(size.y * scale);

    var canvas = this.canvas;
    canvas.width = rw;
    canvas.height = rh;
    canvas.style.width = size.x + 'px';
    canvas.style.height = size.y + 'px';
    L.DomUtil.setPosition(canvas, topLeft);

    var ctx = canvas.getContext('2d');
    var imgData = ctx.createImageData(rw, rh);
    var buf32 = new Uint32Array(imgData.data.buffer);

    // Render all regions onto the same buffer
    for (var i = 0; i < this.regions.length; i++) {
      this._renderRegion(buf32, rw, rh, this.regions[i], scale, bounds, map);
    }

    ctx.putImageData(imgData, 0, 0);
    this._frameRenderCache[this.currentFrame] = {
      viewKey: baseViewKey, imgData: imgData, rw: rw, rh: rh
    };
  }

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
    var r0 = this.regions[0];
    if (!r0 || !r0.meta.frames[frameIdx]) return '--';
    var frame = r0.meta.frames[frameIdx];
    var d = new Date(frame.time);
    var dateStr = d.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit' });
    var timeStr = d.toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' });
    var offset = frame.offset_min;
    var tag = '';
    if (offset > 0) tag = ' (Forecast +' + offset + 'min)';
    else if (offset < 0) tag = ' (' + offset + 'min)';
    else tag = ' (jetzt)';
    return dateStr + ' ' + timeStr + tag;
  }

  getFrameType(frameIdx) {
    var r0 = this.regions[0];
    if (!r0 || !r0.meta.frames[frameIdx]) return 'observed';
    return r0.meta.frames[frameIdx].type;
  }

  updateUI() {
    var playBtn = document.getElementById('nf-play-btn');
    if (playBtn) playBtn.textContent = this.animTimer ? '\u23F8' : '\u25B6';
    var tsEl = document.getElementById('nf-label');
    if (tsEl) {
      tsEl.textContent = this.formatDateTime(this.currentFrame);
      tsEl.style.color = this.getFrameType(this.currentFrame) === 'forecast' ? '#e07000' : '#333';
    }
    var progEl = document.getElementById('nf-progress');
    if (progEl) progEl.value = this.currentFrame;
  }
}

window.NowcastCanvasLayer = NowcastCanvasLayer;
