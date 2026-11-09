// Anzeige von Uhrzeit und Wasserstand bzw. Stromgeschwindigkeit beim Ueberfahren der 7-Tage-Kurve
// (Maus oder Finger, 7.11.2026). Laedt die SVG inline; Werte stehen im Attribut data-kurve
// (py/tiden_grafik.py). Alte XTide-Grafiken ohne data-kurve bleiben unveraendert als Bild.
(function () {
  'use strict';
  var NS = 'http://www.w3.org/2000/svg';

  function el(name, attr, eltern) {
    var e = document.createElementNS(NS, name);
    for (var k in attr) e.setAttribute(k, attr[k]);
    if (eltern) eltern.appendChild(e);
    return e;
  }

  function formatierer(zone, abk) {
    var f0 = formatiererRoh(zone);
    if (!abk || !abk.length) return f0.voll;
    return function (t) {
      var k = abk[0][1];
      for (var i = 0; i < abk.length && abk[i][0] <= t; i++) k = abk[i][1];
      return f0.ohne(t) + ' ' + k;
    };
  }

  function formatiererRoh(zone) {
    var opt = {weekday: 'short', day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit', hour12: false};
    function mach(tz, mitZone) {
      var o = {timeZone: tz}; for (var k in opt) o[k] = opt[k];
      if (mitZone) o.timeZoneName = 'short';
      return new Intl.DateTimeFormat('en-GB', o);
    }
    var m = /^([+-])(\d\d):(\d\d)$/.exec(zone);
    if (m) {
      var off = (m[1] === '-' ? -1 : 1) * (60 * +m[2] + +m[3]) * 60000, u = mach('UTC', false);
      var g = function (t) { return u.format(new Date(t * 1000 + off)).replace(/,/g, ''); };
      return {ohne: g, voll: function (t) { return g(t) + ' UTC' + zone; }};
    }
    var a, b;
    try { a = mach(zone, false); b = mach(zone, true); } catch (e) { a = mach('UTC', false); b = mach('UTC', true); }
    return {ohne: function (t) { return a.format(new Date(t * 1000)).replace(/,/g, ''); },
            voll: function (t) { return b.format(new Date(t * 1000)).replace(/,/g, ''); }};
  }

  function einrichten(wrap, svg) {
    var K = JSON.parse(svg.getAttribute('data-kurve'));
    var zeitText = formatierer(K.zone, K.abk);
    var hoehe = 312;
    var y = function (v) { return K.ymax + (v - K.vmin) / (K.vmax - K.vmin) * (K.ymin - K.ymax); };

    var g = el('g', {'pointer-events': 'none', visibility: 'hidden', 'font-family': 'Liberation Sans, Arial, sans-serif'}, svg);
    var linie = el('line', {y1: 0, y2: hoehe, stroke: '#000', 'stroke-width': 1, 'stroke-dasharray': '3 3'}, g);
    var punkt = el('circle', {r: 5, fill: '#fff', stroke: '#000', 'stroke-width': 2}, g);
    var punktW = el('circle', {r: 4, fill: '#c62828', stroke: '#fff', 'stroke-width': 1.5}, g);
    var kasten = el('rect', {rx: 5, ry: 5, fill: 'rgba(255,255,255,0.95)', stroke: '#333', 'stroke-width': 1}, g);
    var z1 = el('text', {'font-size': 14, 'font-weight': 'bold', fill: '#000'}, g);
    var z2 = el('text', {'font-size': 14, fill: '#000'}, g);
    var z3 = el('text', {'font-size': 13, fill: '#c62828'}, g);

    function zahl(v) { return (Math.abs(v) < 0.005 ? 0 : v).toFixed(2); }

    function zeigen(x) {
      if (x < K.x0 || x > 3200) { g.setAttribute('visibility', 'hidden'); return; }
      var i = Math.max(0, Math.min(K.werte.length - 1, Math.round(x / K.dx)));
      var xi = i * K.dx, v = K.werte[i], t = K.t0 + i * K.dt;
      linie.setAttribute('x1', xi); linie.setAttribute('x2', xi);
      punkt.setAttribute('cx', xi); punkt.setAttribute('cy', y(v));
      z1.textContent = zeitText(t);
      if (K.strom) {
        var s = Math.abs(v);
        z2.textContent = s < 0.05 ? 'Slack ' + zahl(s) + ' ' + K.einheit
                                  : (v > 0 ? 'Flood ' : 'Ebb ') + zahl(s) + ' ' + K.einheit;
      } else {
        z2.textContent = 'Tide level ' + zahl(v) + ' ' + K.einheit;
      }
      var w = K.wetter ? K.wetter[i] : null;
      if (w !== null && w !== undefined) {
        z3.textContent = 'Sea level (with surge) ' + zahl(w) + ' ' + K.einheit;
        punktW.setAttribute('cx', xi); punktW.setAttribute('cy', y(w));
        punktW.setAttribute('visibility', 'inherit');
      } else {
        z3.textContent = '';
        punktW.setAttribute('visibility', 'hidden');
      }
      var b = 12 + Math.max(z1.getComputedTextLength(), z2.getComputedTextLength(),
                            z3.textContent ? z3.getComputedTextLength() : 0);
      var h = z3.textContent ? 62 : 44;
      // Kasten neben die Linie, an den Raendern des sichtbaren Ausschnitts nach innen
      var sicht = wrap.getBoundingClientRect(), r = svg.getBoundingClientRect(), s = r.width / 3200;
      var links = (sicht.left - r.left) / s, rechts = (sicht.right - r.left) / s;
      var kx = xi + 12;
      if (kx + b > rechts - 4) kx = xi - 12 - b;
      if (kx < links + 4) kx = Math.min(links + 4, rechts - b - 4);
      var ky = 42;
      kasten.setAttribute('x', kx); kasten.setAttribute('y', ky);
      kasten.setAttribute('width', b); kasten.setAttribute('height', h);
      [z1, z2, z3].forEach(function (z, n) { z.setAttribute('x', kx + 6); z.setAttribute('y', ky + 18 + 18 * n); });
      g.setAttribute('visibility', 'visible');
    }

    function xVon(ev) {
      var r = svg.getBoundingClientRect();
      return (ev.clientX - r.left) * 3200 / r.width;
    }

    // Finger: waagerecht wandern fuehrt die Anzeige, senkrecht scrollt die Seite.
    // Am Rand des sichtbaren Ausschnitts laeuft die Grafik mit.
    svg.style.touchAction = 'pan-y';
    var randLauf = null, letztesX = null;
    function randPruefen() {
      if (letztesX === null) { randLauf = null; return; }
      var sicht = wrap.getBoundingClientRect(), d = 0;
      if (letztesX > sicht.right - 40) d = 8; else if (letztesX < sicht.left + 40) d = -8;
      if (d) {
        wrap.scrollLeft += d;
        zeigen(xVon({clientX: letztesX}));
        randLauf = requestAnimationFrame(randPruefen);
      } else randLauf = null;
    }
    svg.addEventListener('pointermove', function (ev) {
      zeigen(xVon(ev));
      if (ev.pointerType !== 'mouse') {
        letztesX = ev.clientX;
        if (!randLauf) randLauf = requestAnimationFrame(randPruefen);
      }
    });
    svg.addEventListener('pointerdown', function (ev) { zeigen(xVon(ev)); });
    function ende(ev) {
      letztesX = null;
      if (ev.pointerType === 'mouse') g.setAttribute('visibility', 'hidden');
    }
    svg.addEventListener('pointerleave', ende);
    svg.addEventListener('pointerup', ende);
    svg.addEventListener('pointercancel', ende);
  }

  function laden(wrap) {
    var img = wrap.querySelector('img');
    if (!img || !window.fetch || !window.DOMParser || !window.Intl) return;
    fetch(img.getAttribute('src'), {cache: 'no-store'}).then(function (r) { return r.ok ? r.text() : null; })
      .then(function (txt) {
        if (!txt) return;
        var svg = new DOMParser().parseFromString(txt, 'image/svg+xml').documentElement;
        if (!svg || svg.nodeName.toLowerCase() !== 'svg' || !svg.getAttribute('data-kurve')) return;
        svg = document.importNode(svg, true);
        svg.setAttribute('role', 'img');
        svg.setAttribute('aria-label', img.getAttribute('alt') || '');
        svg.setAttribute('id', img.id);
        svg.style.display = 'block';
        svg.style.cursor = 'crosshair';
        wrap.replaceChild(svg, img);
        einrichten(wrap, svg);
      }).catch(function () {});
  }

  function start() {
    var w = document.querySelectorAll('.tide-svg-wrap');
    for (var i = 0; i < w.length; i++) laden(w[i]);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
  else start();
})();
