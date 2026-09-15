/**
 * WindCanvasLayer — Leaflet Canvas overlay for GFS 10 m wind forecasts.
 * Renders a color-interpolated wind speed field plus continuously animated
 * particles that flow with the wind (windy.com style).
 *
 * Same architecture as WaveCanvasLayer / PrecipCanvasLayer:
 * - binary grids per forecast frame (static/wind/wind_f{NNN}.bin, see
 *   py/download_wind_forecast.py): int16 LE, u block then v block, 0.01 m/s
 * - adaptive render scale, precomputed lat rows, Uint32 color LUT
 * - per-frame ImageData cache for instant frame switching during playback
 *
 * Particles do not sample the grid per particle: on every view/frame change a
 * screen-space velocity field (one cell per FIELD_STEP px) is built once, the
 * particle loop then only does a bilinear lookup in that field.
 */

// --- Color scale: wind speed (kn) → [R, G, B, A] ---
const WIND_COLORS = [
  [0,   98, 113, 183, 150],
  [4,   57, 97, 159, 160],
  [8,   74, 148, 169, 170],
  [12,  77, 141, 123, 175],
  [16,  83, 165, 83, 180],
  [20,  53, 159, 53, 185],
  [24,  167, 157, 81, 190],
  [28,  159, 127, 58, 195],
  [34,  161, 108, 92, 200],
  [40,  129, 58, 78, 205],
  [48,  175, 80, 136, 210],
  [56,  117, 74, 147, 215],
  [64,  109, 97, 163, 220]
];

const MS_TO_KN = 1.943844;

// Color LUT: index = wind speed in 0.1 kn → 0..1023 covers 0..102 kn
const WIND_LUT32 = new Uint32Array(1024);
(function buildWindLUT() {
  const last = WIND_COLORS[WIND_COLORS.length - 1];
  for (let i = 0; i < 1024; i++) {
    const kn = i * 0.1;
    let c = last.slice(1);
    for (let j = 0; j < WIND_COLORS.length - 1; j++) {
      const s0 = WIND_COLORS[j], s1 = WIND_COLORS[j + 1];
      if (kn >= s0[0] && kn < s1[0]) {
        const t = (kn - s0[0]) / (s1[0] - s0[0]);
        c = [1, 2, 3, 4].map(k => s0[k] + t * (s1[k] - s0[k]));
        break;
      }
    }
    WIND_LUT32[i] = ((c[3] & 0xFF) << 24) | ((c[2] & 0xFF) << 16) | ((c[1] & 0xFF) << 8) | (c[0] & 0xFF);
  }
})();

const WIND_FIELD_STEP = 4;          // px per cell of the screen-space velocity field
const WIND_COMPASS = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE',
                      'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW'];


class WindCanvasLayer {
  constructor(map) {
    this.map = map;
    this.meta = null;
    this.gridCache = {};             // frameIdx → { u: Int16Array, v: Int16Array, speed: Uint16Array (0.1 kn) }
    this.canvas = null;
    this.particleCanvas = null;
    this.currentFrame = 0;
    this.frames = [];
    this.animTimer = null;
    this.animDelay = 800;
    this.active = false;
    this.velocityScale = 0.12;       // screen px per tick per m/s
    this._particles = [];
    this._particleRAF = null;
    this._field = null;
    this._renderViewKey = '';
    this._frameRenderCache = {};
    this._onMoveStart = () => {
      if (!this.active) return;
      this._stopParticles();
      if (this.particleCanvas) this.particleCanvas.style.opacity = '0';
    };
    this._onMoveEnd = () => {
      if (!this.active) return;
      this._renderViewKey = '';
      this._frameRenderCache = {};
      this.render();
      this._resetParticles();
      this._startParticles();
    };
    this._onPointer = (e) => this._updateReadout(e.latlng);
  }

  async loadMeta(url) {
    const resp = await fetch(url + '?t=' + Date.now());
    this.meta = await resp.json();
    this.frames = this.meta.frames;
    this.gridCache = {};
    this._frameRenderCache = {};
    this._cacheBust = this.meta.generated ? '?t=' + encodeURIComponent(this.meta.generated) : '';
    return this.meta;
  }

  async loadGrid(frameIdx) {
    if (this.gridCache[frameIdx]) return this.gridCache[frameIdx];
    const resp = await fetch('/static/wind/' + this.frames[frameIdx].file + (this._cacheBust || ''));
    const buf = await resp.arrayBuffer();
    const n = this.meta.grid.nx * this.meta.grid.ny;
    const u = new Int16Array(buf, 0, n);
    const v = new Int16Array(buf, n * 2, n);
    const speed = new Uint16Array(n);
    for (let i = 0; i < n; i++) {
      speed[i] = Math.min(1023, Math.sqrt(u[i] * u[i] + v[i] * v[i]) * 0.01 * MS_TO_KN * 10);
    }
    this.gridCache[frameIdx] = { u: u, v: v, speed: speed };
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

    const particleCanvas = L.DomUtil.create('canvas');
    particleCanvas.style.position = 'absolute';
    particleCanvas.style.pointerEvents = 'none';
    particleCanvas.style.zIndex = '452';
    particleCanvas.style.transition = 'opacity 0.15s ease-out';
    this.particleCanvas = particleCanvas;

    const pane = this.map.getContainer().querySelector('.leaflet-overlay-pane');
    pane.appendChild(canvas);
    pane.appendChild(particleCanvas);

    this.map.on('movestart zoomstart', this._onMoveStart);
    this.map.on('moveend zoomend resize', this._onMoveEnd);
    this.map.on('mousemove click', this._onPointer);
    this.showFrame(this.currentFrame);
  }

  deactivate() {
    this.active = false;
    this.stopAnim();
    this._stopParticles();
    this.map.off('movestart zoomstart', this._onMoveStart);
    this.map.off('moveend zoomend resize', this._onMoveEnd);
    this.map.off('mousemove click', this._onPointer);
    if (this.canvas && this.canvas.parentNode) this.canvas.parentNode.removeChild(this.canvas);
    if (this.particleCanvas && this.particleCanvas.parentNode) this.particleCanvas.parentNode.removeChild(this.particleCanvas);
    this.canvas = null;
    this.particleCanvas = null;
    this._field = null;
    this._particles = [];
    this._frameRenderCache = {};
    this._renderViewKey = '';
  }

  async showFrame(idx) {
    if (!this.active || !this.frames.length) return;
    idx = ((idx % this.frames.length) + this.frames.length) % this.frames.length;
    this.currentFrame = idx;
    await this.loadGrid(idx);
    if (!this.active || this.currentFrame !== idx) return;
    this._renderViewKey = '';
    this.render();
    // Particles keep their positions across frames; only the field changes.
    if (!this._particles.length) this._resetParticles();
    else this._buildField();
    this._startParticles();
    this.updateUI();
  }

  // --- Bilinear u/v sample (m/s) at a lat/lon, null outside the grid ---
  _sampleUV(data, lat, lonRaw) {
    const g = this.meta.grid;
    const gy = (g.la1 - lat) / g.dy;
    if (!(gy >= 0 && gy < g.ny - 1)) return null;
    const lon = ((lonRaw % 360) + 360) % 360;
    const gx = (lon - g.lo1) / g.dx;
    if (gx < 0) return null;
    const gy0 = gy | 0, fy = gy - gy0, fy1 = 1 - fy;
    const gx0 = gx | 0, gx1 = (gx0 + 1) % g.nx, fx = gx - gx0, fx1 = 1 - fx;
    const r0 = gy0 * g.nx, r1 = r0 + g.nx;
    const w00 = fx1 * fy1, w01 = fx * fy1, w10 = fx1 * fy, w11 = fx * fy;
    const u = data.u, v = data.v;
    return [
      (u[r0 + gx0] * w00 + u[r0 + gx1] * w01 + u[r1 + gx0] * w10 + u[r1 + gx1] * w11) * 0.01,
      (v[r0 + gx0] * w00 + v[r0 + gx1] * w01 + v[r1 + gx0] * w10 + v[r1 + gx1] * w11) * 0.01
    ];
  }

  render() {
    if (!this.canvas || !this.meta || !this.active) return;
    const data = this.gridCache[this.currentFrame];
    if (!data) return;

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

    // Instant blit from cache (same viewport, frame already rendered)
    const cached = this._frameRenderCache[this.currentFrame];
    if (cached && cached.viewKey === baseViewKey) {
      ctx.putImageData(cached.imgData, 0, 0);
      return;
    }

    const imgData = ctx.createImageData(rw, rh);
    const buf32 = new Uint32Array(imgData.data.buffer);
    const grid = data.speed;

    const g = this.meta.grid;
    const gnx = g.nx, gny = g.ny;
    const la1 = g.la1, lo1 = g.lo1, dx = g.dx, dy = g.dy;
    const west = bounds.getWest();
    const invRw = (bounds.getEast() - west) / rw;

    for (let py = 0; py < rh; py++) {
      const lat = map.containerPointToLatLng([0, py / scale]).lat;
      if (lat > 90 || lat < -90) continue;
      const gy = (la1 - lat) / dy;
      if (gy < 0 || gy >= gny - 1) continue;
      const gy0 = gy | 0;
      const fy = gy - gy0;
      const fy1 = 1 - fy;
      const row0 = gy0 * gnx;
      const row1 = row0 + gnx;
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
        const val = grid[row0 + gx0] * fx1 * fy1 + grid[row0 + gx1] * fx * fy1 +
                    grid[row1 + gx0] * fx1 * fy  + grid[row1 + gx1] * fx * fy;
        buf32[rowOff + px] = WIND_LUT32[val | 0];
      }
    }

    ctx.putImageData(imgData, 0, 0);
    this._frameRenderCache[this.currentFrame] = { viewKey: baseViewKey, imgData: imgData };
  }

  // --- Particle animation ---
  _buildField() {
    const data = this.gridCache[this.currentFrame];
    if (!data || !this.meta || !this.particleCanvas) { this._field = null; return; }
    const map = this.map;
    const size = map.getSize();
    const bounds = map.getBounds();
    const west = bounds.getWest();
    const lonSpan = bounds.getEast() - west;
    const fw = Math.ceil(size.x / WIND_FIELD_STEP) + 2;
    const fh = Math.ceil(size.y / WIND_FIELD_STEP) + 2;
    const fu = new Float32Array(fw * fh);
    const fv = new Float32Array(fw * fh);
    const ok = new Uint8Array(fw * fh);
    const k = this.velocityScale;

    for (let j = 0; j < fh; j++) {
      const y = j * WIND_FIELD_STEP;
      const lat = map.containerPointToLatLng([0, y]).lat;
      if (lat > 85 || lat < -85) continue;
      for (let i = 0; i < fw; i++) {
        const uv = this._sampleUV(data, lat, west + (i * WIND_FIELD_STEP / size.x) * lonSpan);
        if (!uv) continue;
        const idx = j * fw + i;
        fu[idx] = uv[0] * k;
        fv[idx] = -uv[1] * k;          // north-positive v → screen y grows downward
        ok[idx] = 1;
      }
    }
    this._field = { fw: fw, fh: fh, u: fu, v: fv, ok: ok };
  }

  _resetParticles() {
    if (!this.particleCanvas || !this.active) return;
    const size = this.map.getSize();
    const pc = this.particleCanvas;
    pc.width = size.x;
    pc.height = size.y;
    pc.style.width = size.x + 'px';
    pc.style.height = size.y + 'px';
    pc.style.opacity = '1';
    L.DomUtil.setPosition(pc, this.map.containerPointToLayerPoint([0, 0]));

    this._buildField();
    const count = Math.round(Math.min(5000, Math.max(800, size.x * size.y / 300)));
    this._particles = [];
    for (let i = 0; i < count; i++) this._particles.push(this._spawnParticle(size, true));
  }

  _spawnParticle(size, randomAge) {
    return {
      x: Math.random() * size.x,
      y: Math.random() * size.y,
      age: randomAge ? Math.floor(Math.random() * 80) : 0,
      maxAge: 50 + Math.floor(Math.random() * 50)
    };
  }

  _startParticles() {
    if (this._particleRAF || !this.active) return;
    this._particleLastTime = 0;
    const step = (timestamp) => {
      if (!this._particleRAF) return;
      if (timestamp - this._particleLastTime >= 30) {
        this._particleLastTime = timestamp;
        this._tickParticles();
      }
      this._particleRAF = requestAnimationFrame(step);
    };
    this._particleRAF = requestAnimationFrame(step);
  }

  _stopParticles() {
    if (this._particleRAF) cancelAnimationFrame(this._particleRAF);
    this._particleRAF = null;
    if (this.particleCanvas) {
      this.particleCanvas.getContext('2d').clearRect(0, 0, this.particleCanvas.width, this.particleCanvas.height);
    }
  }

  _tickParticles() {
    const pc = this.particleCanvas;
    const f = this._field;
    if (!pc || !f || !this.active) return;
    const w = pc.width, h = pc.height;
    if (w === 0 || h === 0) return;
    const ctx = pc.getContext('2d');

    // Fade existing trails
    ctx.globalCompositeOperation = 'destination-in';
    ctx.fillStyle = 'rgba(0, 0, 0, 0.92)';
    ctx.fillRect(0, 0, w, h);
    ctx.globalCompositeOperation = 'source-over';

    const size = { x: w, y: h };
    const inv = 1 / WIND_FIELD_STEP;
    const fw = f.fw, fu = f.u, fv = f.v, ok = f.ok;
    const particles = this._particles;

    ctx.beginPath();
    for (let i = 0; i < particles.length; i++) {
      const p = particles[i];
      if (++p.age >= p.maxAge || p.x < 0 || p.x >= w || p.y < 0 || p.y >= h) {
        particles[i] = this._spawnParticle(size, false);
        continue;
      }
      const cx = p.x * inv, cy = p.y * inv;
      const i0 = cx | 0, j0 = cy | 0;
      const a = j0 * fw + i0, b = a + 1, c = a + fw, d = c + 1;
      if (!(ok[a] && ok[b] && ok[c] && ok[d])) {
        particles[i] = this._spawnParticle(size, false);
        continue;
      }
      const tx = cx - i0, ty = cy - j0, tx1 = 1 - tx, ty1 = 1 - ty;
      const du = (fu[a] * tx1 + fu[b] * tx) * ty1 + (fu[c] * tx1 + fu[d] * tx) * ty;
      const dv = (fv[a] * tx1 + fv[b] * tx) * ty1 + (fv[c] * tx1 + fv[d] * tx) * ty;
      ctx.moveTo(p.x, p.y);
      p.x += du;
      p.y += dv;
      ctx.lineTo(p.x, p.y);
    }
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.85)';
    ctx.lineWidth = 1.2;
    ctx.stroke();
  }

  // --- Value readout under the pointer ---
  _updateReadout(latlng) {
    const el = document.getElementById('wd-readout');
    const data = this.gridCache[this.currentFrame];
    if (!el || !data || !this.meta) return;
    const uv = this._sampleUV(data, latlng.lat, latlng.lng);
    if (!uv) { el.textContent = ''; return; }
    const kn = Math.hypot(uv[0], uv[1]) * MS_TO_KN;
    const from = (Math.atan2(-uv[0], -uv[1]) * 180 / Math.PI + 360) % 360;
    el.textContent = kn.toFixed(0) + ' kn (' + (kn / MS_TO_KN).toFixed(1) + ' m/s) from ' +
      WIND_COMPASS[Math.round(from / 22.5) % 16] + ' ' + Math.round(from) + '°';
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
    const playBtn = document.getElementById('wd-play-btn');
    if (playBtn) playBtn.textContent = this.animTimer ? '⏸' : '▶';
    const tsEl = document.getElementById('wd-label');
    if (tsEl) tsEl.textContent = this.formatDateTime(this.currentFrame);
    const progEl = document.getElementById('wd-progress');
    if (progEl) progEl.value = this.currentFrame;
  }
}

window.WindCanvasLayer = WindCanvasLayer;
