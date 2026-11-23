/*
 * TideFlowLayer – eigene Kartenebene für den Gezeitenstrom (TPXO10), Oliver 18.11.2026.
 *
 * Ersetzt leaflet-velocity für tc-toggle: dort löschte jedes setData() alle Partikel (Flackern alle 1,2 s),
 * und schwache Gezeitenströme waren auf der Skala bis 2,5 m/s kaum zu sehen.
 *
 * - Farbfläche nach Stromstärke (Knoten) unter den Partikeln
 * - Partikel bleiben beim Zeitwechsel erhalten; die Zeit läuft stufenlos, zwischen den
 *   30-min-Feldern vom Server (/api/tidal_current) wird linear interpoliert
 * - Partikelgeschwindigkeit in Bildpunkten unabhängig vom Zoom, schwache Ströme etwas angehoben
 *
 * Feldformat wie leaflet-velocity: [{header:{nx,ny,lo1,la1,dx,dy}, data:[u…]}, {…, data:[v…]}] in m/s.
 */
(function () {
  'use strict';

  var KN = 1.943844;
  // Farbskala in Knoten, passend zur Legende (0 … 5+ kn)
  var STOPS = [
    [0.0, [170, 220, 240, 0]],
    [0.2, [170, 220, 240, 90]],
    [0.5, [90, 170, 220, 150]],
    [1.0, [60, 180, 120, 175]],
    [1.5, [150, 200, 50, 185]],
    [2.0, [245, 200, 40, 195]],
    [3.0, [240, 130, 30, 205]],
    [4.0, [220, 50, 40, 215]],
    [5.0, [160, 20, 100, 225]]
  ];
  var LUT = (function () {               // 0 … 6 kn in 0,02-kn-Schritten
    var n = 301, out = new Uint8ClampedArray(n * 4);
    for (var i = 0; i < n; i++) {
      var s = i * 0.02, k = 0;
      while (k < STOPS.length - 2 && s > STOPS[k + 1][0]) k++;
      var a = STOPS[k], b = STOPS[k + 1];
      var f = Math.max(0, Math.min(1, (s - a[0]) / (b[0] - a[0])));
      for (var c = 0; c < 4; c++) out[i * 4 + c] = a[1][c] + f * (b[1][c] - a[1][c]);
    }
    return out;
  })();

  var CELL = 4;            // Bildpunkte je Rasterzelle für Farbfläche und Partikel-Nachschlagen
  var MAX_AGE = 90;        // Partikel-Lebensdauer in Bildern
  var FADE = 0.93;         // Spurenlänge (Deckkraft, die je Bild erhalten bleibt)

  function Frame(data) {
    var h = data[0].header;
    this.nx = h.nx; this.ny = h.ny; this.lo1 = h.lo1; this.la1 = h.la1; this.dx = h.dx; this.dy = h.dy;
    var n = h.nx * h.ny;
    this.u = new Float32Array(n); this.v = new Float32Array(n);
    var U = data[0].data, V = data[1].data;
    for (var i = 0; i < n; i++) {
      this.u[i] = U[i] === null ? NaN : U[i];
      this.v[i] = V[i] === null ? NaN : V[i];
    }
    // 21.11.2026: drittes Feld 'filled' (1 = bis an die OSM-Küste aus dem nächsten Modellwert geschätzt)
    this.f = data[2] ? Float32Array.from(data[2].data) : null;
  }
  // bilinear; NaN wenn eine Ecke Land ist (Küste bleibt scharf)
  Frame.prototype.at = function (lat, lon, out) {
    var x = ((lon - this.lo1) % 360 + 360) % 360 / this.dx;
    var y = (this.la1 - lat) / this.dy;
    var i = Math.floor(x), j = Math.floor(y);
    if (i < 0 || j < 0 || i >= this.nx - 1 || j >= this.ny - 1) { out[0] = NaN; return; }
    var fx = x - i, fy = y - j, nx = this.nx, k = j * nx + i;
    var u00 = this.u[k], u10 = this.u[k + 1], u01 = this.u[k + nx], u11 = this.u[k + nx + 1];
    var v00 = this.v[k], v10 = this.v[k + 1], v01 = this.v[k + nx], v11 = this.v[k + nx + 1];
    // fehlende Ecken durch vorhandene ersetzen, damit das Wasser bis an die Küste reicht
    var su = 0, sv = 0, sw = 0;
    var w = [(1 - fx) * (1 - fy), fx * (1 - fy), (1 - fx) * fy, fx * fy];
    var us = [u00, u10, u01, u11], vs = [v00, v10, v01, v11];
    var fs = this.f ? [this.f[k], this.f[k + 1], this.f[k + nx], this.f[k + nx + 1]] : null, sf = 0;
    for (var q = 0; q < 4; q++) if (us[q] === us[q]) {
      su += w[q] * us[q]; sv += w[q] * vs[q]; sw += w[q]; if (fs) sf += w[q] * fs[q];
    }
    if (sw < 0.3) { out[0] = NaN; return; }
    out[0] = su / sw; out[1] = sv / sw; out[2] = sf / sw;
  };

  var TideFlowLayer = L.Layer.extend({
    options: { pane: 'overlayPane' },

    initialize: function (opts) {
      L.setOptions(this, opts);
      this._fetch = opts.fetchFrame;       // async (t) -> leaflet-velocity-Liste
      this._step = opts.stepSeconds || 1800;
      this._frames = {};                   // t -> Frame (für den aktuellen Ausschnitt)
      this._pending = {};
      this._t = opts.time;                 // aktuelle Zeit (Unix-s), stufenlos
      this._grid = null;                   // Bildschirmraster (u, v in px/Bild, Knoten)
      this._gridT = null;
      this._particles = [];
      this._raf = null;
    },

    onAdd: function (map) {
      this._map = map;
      var size = map.getSize();
      this._bg = L.DomUtil.create('canvas', 'tideflow-bg leaflet-zoom-hide');
      this._fg = L.DomUtil.create('canvas', 'tideflow-fg leaflet-zoom-hide');
      this._ar = L.DomUtil.create('canvas', 'tideflow-ar leaflet-zoom-hide');
      // Satzpfeile in eigenem Pane ÜBER der Landmaske (ocLandMask, z 401, Natural Earth 10 m): die deckt Mündungen
      // und Flüsse zu (Loire bei Paimboeuf), Pfeile dort waren nur sichtbar, wenn sie ins offene Wasser zeigten (23.11.2026)
      var arPane = map.getPane('tideArrows') || map.createPane('tideArrows');
      arPane.style.zIndex = '450'; arPane.style.pointerEvents = 'none';     // unter den Markern (600)
      [this._bg, this._fg, this._ar].forEach(function (c) {
        c.style.position = 'absolute'; c.style.pointerEvents = 'none';
        (c === this._ar ? arPane : this.getPane()).appendChild(c);
      }, this);
      map.on('movestart', this._onMoveStart, this);
      map.on('moveend', this._onMoveEnd, this);
      map.on('resize', this._onMoveEnd, this);
      map.on('mousemove', this._onMouse, this);
      map.on('click', this._onClick, this);
      map.on('mouseout', this._hideReadout, this);
      this._readout = L.DomUtil.create('div', 'tideflow-readout', map.getContainer());
      this._readout.style.cssText = 'position:absolute;left:10px;bottom:28px;z-index:800;background:rgba(255,255,255,.85);' +
        'padding:3px 8px;border-radius:4px;font:12px sans-serif;pointer-events:none;display:none;';
      this._onMoveEnd();
      this._loop();
    },

    onRemove: function (map) {
      if (this._raf) cancelAnimationFrame(this._raf);
      this._raf = null;
      map.off('movestart', this._onMoveStart, this);
      map.off('moveend', this._onMoveEnd, this);
      map.off('resize', this._onMoveEnd, this);
      map.off('mousemove', this._onMouse, this);
      map.off('click', this._onClick, this);
      map.off('mouseout', this._hideReadout, this);
      map.getContainer().style.cursor = '';
      L.DomUtil.remove(this._bg); L.DomUtil.remove(this._fg); L.DomUtil.remove(this._ar); L.DomUtil.remove(this._readout);
    },

    // --- Zeit ---
    setTime: function (t) { this._t = t; this._gridT = null; },
    getTime: function () { return this._t; },
    // true, wenn die beiden Felder um t geladen sind (für die Wiedergabe: sonst warten)
    ready: function (t) {
      var a = Math.floor(t / this._step) * this._step;
      this._need(a); this._need(a + this._step);
      return !!(this._frames[a] && this._frames[a + this._step]);
    },
    prefetch: function (t) { var a = Math.floor(t / this._step) * this._step; this._need(a + 2 * this._step); },
    clearCache: function () { this._frames = {}; this._pending = {}; this._gridT = null; },

    _need: function (t) {
      var self = this;
      if (this._frames[t] || this._pending[t]) return;
      var gen = this._gen;
      this._pending[t] = this._fetch(t).then(function (d) {
        if (gen !== self._gen) return;
        self._frames[t] = new Frame(d);
        delete self._pending[t];
        self._gridT = null;
        // höchstens 8 Felder behalten
        var ks = Object.keys(self._frames).map(Number).sort(function (a, b) { return Math.abs(a - self._t) - Math.abs(b - self._t); });
        ks.slice(8).forEach(function (k) { delete self._frames[k]; });
      }).catch(function (e) { delete self._pending[t]; console.error('Tide flow:', e); });
    },

    // --- Karte ---
    _onMoveStart: function () {
      this._moving = true;
      this._bg.style.display = 'none'; this._fg.style.display = 'none'; this._ar.style.display = 'none';
    },
    _onMoveEnd: function () {
      var map = this._map, size = map.getSize();
      var tl = map.containerPointToLayerPoint([0, 0]);
      [this._bg, this._fg, this._ar].forEach(function (c) {
        c.width = size.x; c.height = size.y;
        L.DomUtil.setPosition(c, tl);
        c.style.display = '';
      });
      this._moving = false;
      this._gen = (this._gen || 0) + 1;
      // alte Felder bleiben nutzbar (sie tragen ihre eigenen Koordinaten), neue werden geholt
      this._oldFrames = this._frames;
      this._frames = {}; this._pending = {};
      this._gridT = null;
      this._particles = [];
      this.ready(this._t);
      this._loadArrows();
    },

    // --- Pfeile an den Strömungssätzen (Harmonics, /api/current_arrows) ---
    _loadArrows: function () {
      var self = this, gen = this._gen;
      this._arT = null;
      if (!this.options.fetchArrows) return;
      this.options.fetchArrows().then(function (d) {
        if (gen !== self._gen) return;
        self._arrows = d; self._arT = null;
      }).catch(function (e) { console.error('Current arrows:', e); });
    },
    _arrowAt: function (a, t) {
      var x = (t - this._arrows.t0) / this._arrows.dt, i = Math.floor(x);
      if (i < 0 || i >= a.u.length - 1) { i = Math.max(0, Math.min(a.u.length - 1, i)); return [a.u[i], a.v[i]]; }
      var f = x - i;
      return [a.u[i] + f * (a.u[i + 1] - a.u[i]), a.v[i] + f * (a.v[i + 1] - a.v[i])];
    },
    _drawArrows: function () {
      var ctx = this._ar.getContext('2d'), map = this._map;
      ctx.clearRect(0, 0, this._ar.width, this._ar.height);
      this._arT = this._t;
      if (!this._arrows) return;
      var z = map.getZoom(), label = z >= 8;
      this._arHit = [];
      ctx.lineCap = 'round'; ctx.lineJoin = 'round';
      ctx.font = 'bold 11px sans-serif'; ctx.textBaseline = 'middle';
      for (var i = 0; i < this._arrows.pfeile.length; i++) {
        var a = this._arrows.pfeile[i];
        var pt = map.latLngToContainerPoint([a.la, a.lo]);
        if (pt.x < -30 || pt.y < -30 || pt.x > this._ar.width + 30 || pt.y > this._ar.height + 30) continue;
        var uv = this._arrowAt(a, this._t), kn = Math.sqrt(uv[0] * uv[0] + uv[1] * uv[1]);
        var li = Math.min(300, Math.round(kn / 0.02)) * 4;
        var col = 'rgb(' + LUT[li] + ',' + LUT[li + 1] + ',' + LUT[li + 2] + ')';
        var hit = [pt.x, pt.y, a, kn, uv, null];
        this._arHit.push(hit);
        // Standort-Punkt (auch bei Stauwasser sichtbar)
        ctx.beginPath(); ctx.arc(pt.x, pt.y, 3, 0, 2 * Math.PI);
        ctx.fillStyle = '#fff'; ctx.fill(); ctx.lineWidth = 1.5; ctx.strokeStyle = '#223'; ctx.stroke();
        if (kn < 0.05) continue;
        var len = 10 + 14 * Math.sqrt(Math.min(kn, 6));
        var dx = uv[0] / kn, dy = -uv[1] / kn;
        var ex = pt.x + dx * len, ey = pt.y + dy * len;
        hit[5] = [ex, ey];
        var hx = -dy, hy = dx, hl = 6;
        var path = new Path2D();
        path.moveTo(pt.x, pt.y); path.lineTo(ex, ey);
        path.moveTo(ex - dx * hl + hx * hl * 0.6, ey - dy * hl + hy * hl * 0.6);
        path.lineTo(ex, ey);
        path.lineTo(ex - dx * hl - hx * hl * 0.6, ey - dy * hl - hy * hl * 0.6);
        ctx.strokeStyle = '#223'; ctx.lineWidth = 5; ctx.stroke(path);
        ctx.strokeStyle = col; ctx.lineWidth = 2.8; ctx.stroke(path);
        if (label) {
          var txt = kn.toFixed(1), tx = ex + dx * 9 - 8, ty = ey + dy * 9;
          ctx.lineWidth = 3; ctx.strokeStyle = 'rgba(255,255,255,.9)'; ctx.strokeText(txt, tx, ty);
          ctx.fillStyle = '#223'; ctx.fillText(txt, tx, ty);
        }
      }
    },

    // Felder um t (aktuelle oder, solange die neuen fehlen, die alten)
    _pair: function (t) {
      var a = Math.floor(t / this._step) * this._step, b = a + this._step;
      var f = (t - a) / this._step;
      var A = this._frames[a], B = this._frames[b];
      if (!A || !B) {
        var o = this._oldFrames || {};
        A = A || o[a]; B = B || o[b];
      }
      if (A && !B) { B = A; f = 0; }
      if (B && !A) { A = B; f = 1; }
      return A ? [A, B, f] : null;
    },

    // Feld einmal je Ausschnitt auf das Bildschirmraster abtasten (m/s, NaN = Land)
    _sample: function (F) {
      if (F._view === this._gen && F._su) return F;
      var map = this._map, size = map.getSize();
      var gw = Math.ceil(size.x / CELL) + 1, gh = Math.ceil(size.y / CELL) + 1;
      if (!this._ll || this._llGen !== this._gen) {
        this._ll = new Float64Array(gw * gh * 2); this._llGen = this._gen;
        for (var y = 0; y < gh; y++) for (var x = 0; x < gw; x++) {
          var ll = map.containerPointToLatLng([x * CELL, y * CELL]);
          this._ll[(y * gw + x) * 2] = ll.lat; this._ll[(y * gw + x) * 2 + 1] = ll.lng;
        }
      }
      var su = new Float32Array(gw * gh), sv = new Float32Array(gw * gh), sf = new Float32Array(gw * gh), o = [0, 0, 0];
      for (var k = 0; k < gw * gh; k++) {
        o[2] = 0;
        F.at(this._ll[k * 2], this._ll[k * 2 + 1], o);
        su[k] = o[0]; sv[k] = o[0] === o[0] ? o[1] : NaN; sf[k] = o[2] || 0;
      }
      F._su = su; F._sv = sv; F._sf = sf; F._view = this._gen; F._gw = gw; F._gh = gh;
      return F;
    },

    _buildGrid: function () {
      var p = this._pair(this._t);
      if (!p) return false;
      var A = this._sample(p[0]), B = this._sample(p[1]), f = p[2];
      var gw = A._gw, gh = A._gh, n = gw * gh;
      var u = new Float32Array(n), v = new Float32Array(n), knA = new Float32Array(n);
      var tmp = this._tmp || (this._tmp = document.createElement('canvas'));
      if (tmp.width !== gw || tmp.height !== gh) { tmp.width = gw; tmp.height = gh; }
      var tctx = tmp.getContext('2d'), img = tctx.createImageData(gw, gh), d = img.data;
      for (var k = 0; k < n; k++) {
        var ua = A._su[k], va = A._sv[k];
        if (ua !== ua) { u[k] = NaN; continue; }
        var ub = B._su[k];
        if (ub === ub && f > 0) { ua += f * (ub - ua); va += f * (B._sv[k] - va); }
        var kn = Math.sqrt(ua * ua + va * va) * KN;
        knA[k] = kn;
        // Bildschirmbewegung unabhängig vom Zoom, schwache Ströme angehoben (kn^0,4): 1 kn ≈ 1,1 px je Bild
        var px = kn > 0 ? 1.1 * Math.pow(kn, 0.4) / kn : 0;
        u[k] = ua * KN * px; v[k] = -va * KN * px;
        var li = Math.min(300, Math.round(kn / 0.02)) * 4;
        // aufgefüllter Küstenstreifen (geschätzt) halb so deckend
        d[k * 4] = LUT[li]; d[k * 4 + 1] = LUT[li + 1]; d[k * 4 + 2] = LUT[li + 2]; d[k * 4 + 3] = LUT[li + 3] * (1 - 0.5 * A._sf[k]);
      }
      this._grid = { u: u, v: v, w: gw, h: gh, kn: knA };
      this._gridT = this._t;
      tctx.putImageData(img, 0, 0);
      var ctx = this._bg.getContext('2d');
      ctx.clearRect(0, 0, this._bg.width, this._bg.height);
      ctx.imageSmoothingEnabled = true;
      ctx.drawImage(tmp, 0, 0, gw * CELL, gh * CELL);
      return true;
    },

    _vel: function (x, y, out) {
      var g = this._grid, gx = x / CELL, gy = y / CELL;
      var i = Math.floor(gx), j = Math.floor(gy);
      if (i < 0 || j < 0 || i >= g.w - 1 || j >= g.h - 1) { out[0] = NaN; return; }
      var k = j * g.w + i;
      out[0] = g.u[k]; out[1] = g.v[k]; out[2] = g.kn[k];
    },

    _spawn: function (pt) {
      var g = this._grid, tries = 0, o = [0, 0, 0];
      while (tries++ < 40) {                 // nur dort, wo Strom läuft (> 0,02 kn)
        var x = Math.random() * (g.w - 1) * CELL, y = Math.random() * (g.h - 1) * CELL;
        this._vel(x, y, o);
        if (o[0] === o[0] && o[2] > 0.02) { pt.x = x; pt.y = y; pt.age = Math.floor(Math.random() * MAX_AGE); return; }
      }
      pt.x = -1; pt.age = MAX_AGE;
    },

    _loop: function () {
      var self = this;
      this._raf = requestAnimationFrame(function () { self._loop(); });
      if (this._moving) return;
      if (this._arT !== this._t) this._drawArrows();
      if (this._gridT !== this._t || !this._grid) {
        if (!this._buildGrid()) return;
      }
      var g = this._grid, ctx = this._fg.getContext('2d');
      var want = Math.min(6000, Math.round(g.w * g.h * CELL * CELL / (this._map.getZoom() <= 4 ? 450 : 350)));
      while (this._particles.length < want) { var q = {}; this._spawn(q); this._particles.push(q); }
      if (this._particles.length > want) this._particles.length = want;

      // Spuren ausblenden
      ctx.globalCompositeOperation = 'destination-in';
      ctx.fillStyle = 'rgba(0,0,0,' + FADE + ')';
      ctx.fillRect(0, 0, this._fg.width, this._fg.height);
      ctx.globalCompositeOperation = 'source-over';

      // Linienstärke nach Zoom: weit draußen dünn
      var z = this._map.getZoom();
      ctx.lineWidth = z <= 3 ? 0.6 : z <= 5 ? 0.8 : z <= 7 ? 1.1 : 1.4;
      ctx.lineCap = 'round';
      // drei Durchgänge nach Stärke: schwacher Strom blass, starker kräftig
      var paths = [new Path2D(), new Path2D(), new Path2D()], o = [0, 0, 0];
      for (var i = 0; i < this._particles.length; i++) {
        var p = this._particles[i];
        if (p.age++ >= MAX_AGE || p.x < 0) { this._spawn(p); continue; }
        this._vel(p.x, p.y, o);
        if (o[0] !== o[0]) { p.age = MAX_AGE; continue; }
        var nx = p.x + o[0], ny = p.y + o[1];
        var q = o[2] < 0.25 ? 0 : o[2] < 1 ? 1 : 2;
        paths[q].moveTo(p.x, p.y); paths[q].lineTo(nx, ny);
        p.x = nx; p.y = ny;
      }
      var alpha = [0.5, 0.7, 0.9];
      for (var j = 0; j < 3; j++) { ctx.strokeStyle = 'rgba(25,35,45,' + alpha[j] + ')'; ctx.stroke(paths[j]); }
    },

    // --- Wertanzeige unter der Maus ---
    // Pfeil unter dem Mauszeiger (Standortpunkt oder Pfeilschaft, 10 px), sonst null
    _arrowHit: function (cp) {
      var hit = null;
      (this._arHit || []).forEach(function (h) {
        var d = (h[0] - cp.x) * (h[0] - cp.x) + (h[1] - cp.y) * (h[1] - cp.y);
        if (h[5]) {                                  // Abstand zum Schaft
          var ax = h[5][0] - h[0], ay = h[5][1] - h[1], l2 = ax * ax + ay * ay;
          var q = l2 ? Math.max(0, Math.min(1, ((cp.x - h[0]) * ax + (cp.y - h[1]) * ay) / l2)) : 0;
          var qx = h[0] + q * ax - cp.x, qy = h[1] + q * ay - cp.y;
          d = Math.min(d, qx * qx + qy * qy);
        }
        if (d < 100 && (!hit || d < hit[0])) hit = [d, h];
      });
      return hit && hit[1];
    },
    // 19.11.2026 (Oliver): Klick auf einen Pfeil oeffnet ein Popup wie bei den Stationsmarkern, von dort zur Detailseite
    _onClick: function (e) {
      var h = this._arrowHit(e.containerPoint);
      if (!h) return;
      L.DomEvent.stop(e.originalEvent);
      var a = h[2], esc = function (x) { return String(x).replace(/[&<>"']/g, function (c) { return '&#' + c.charCodeAt(0) + ';'; }); };
      var dirA = (Math.atan2(h[4][0], h[4][1]) * 180 / Math.PI + 360) % 360;
      var html = '<b>' + esc(a.n) + '</b><br>' +
        (a.url ? '<a href="' + esc(a.url) + '">🌊 Show prediction</a><br>' : '') +
        '<small>Now: ' + h[3].toFixed(1) + ' kn towards ' + Math.round(dirA) + '°</small><br>' +
        '<small>📄 ' + esc(a.f) + '</small><br>' +
        '<small>📌 <span style="user-select:all">' + a.la.toFixed(4) + ', ' + a.lo.toFixed(4) + '</span></small>';
      L.popup({ offset: [0, -4] }).setLatLng([a.la, a.lo]).setContent(html).openOn(this._map);
    },
    _onMouse: function (e) {
      var h = this._arrowHit(e.containerPoint);
      this._map.getContainer().style.cursor = h ? 'pointer' : '';
      if (h) {
        var dirA = (Math.atan2(h[4][0], h[4][1]) * 180 / Math.PI + 360) % 360;
        this._readout.textContent = h[2].n.replace(/ Current$/, '') + ': ' + h[3].toFixed(1) + ' kn towards ' + Math.round(dirA) + '° (station)' +
          ' – click for details';
        this._readout.style.display = 'block';
        return;
      }
      var p = this._pair(this._t), a = [0, 0], b = [0, 0];
      if (!p) return this._hideReadout();
      p[0].at(e.latlng.lat, e.latlng.lng, a);
      if (a[0] !== a[0]) return this._hideReadout();
      if (p[2] > 0) { p[1].at(e.latlng.lat, e.latlng.lng, b); if (b[0] === b[0]) { a[0] += p[2] * (b[0] - a[0]); a[1] += p[2] * (b[1] - a[1]); } }
      var kn = Math.sqrt(a[0] * a[0] + a[1] * a[1]) * KN;
      var dir = (Math.atan2(a[0], a[1]) * 180 / Math.PI + 360) % 360;
      this._readout.textContent = 'Tidal current: ' + kn.toFixed(1) + ' kn towards ' + Math.round(dir) + '° (model)';
      this._readout.style.display = 'block';
    },
    _hideReadout: function () { if (this._readout) this._readout.style.display = 'none'; }
  });

  window.TideFlowLayer = TideFlowLayer;
})();
