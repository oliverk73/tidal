/*
 * Route Planner – schnellste Segelroute für Tagestörns (py/segel_router.py, /api/route), Oliver 20.11.2026.
 * Füllt die Sektion "Route Planner" im Kartenmenü: Boot, Startzeit, Start/Ziel per Klick (Marker verschiebbar),
 * Optionen; zeigt die Route (Segeln blau, Motor orange) mit Stundenpunkten und eine Abschnittstabelle.
 */
(function () {
  'use strict';

  function el(html) { var d = document.createElement('div'); d.innerHTML = html.trim(); return d.firstChild; }
  function pad(n) { return (n < 10 ? '0' : '') + n; }
  function localInput(d) {
    return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate()) + 'T' + pad(d.getHours()) + ':' + pad(d.getMinutes());
  }
  function hhmm(t) { var d = new Date(t * 1000); return pad(d.getHours()) + ':' + pad(d.getMinutes()); }
  function dayHHMM(t) {
    return new Date(t * 1000).toLocaleString(undefined, { weekday: 'short', day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
  }
  function dur(h) { var m = Math.round(h * 60); return Math.floor(m / 60) + ' h ' + pad(m % 60) + ' min'; }
  var MODE = { stb: 'starboard tack', bb: 'port tack', motor: 'engine' };

  window.initRoutePlanner = function (map, body) {
    var state = { start: null, ziel: null, pick: null, layer: null, req: 0 };
    var inp = 'style="width:100%;box-sizing:border-box;padding:3px 4px;font-size:12px;"';
    var num = 'style="width:52px;padding:2px 3px;font-size:12px;"';
    body.innerHTML =
      '<div style="display:flex;flex-direction:column;gap:6px;width:250px;font-size:12px;">' +
        '<label>Boat (ORC, type to search)<input id="rp-boot-such" list="rp-boot-liste" autocomplete="off" placeholder="e.g. Bavaria 37, Hanse 370 …" ' + inp + '></label>' +
        '<datalist id="rp-boot-liste"></datalist>' +
        '<div id="rp-boot-info" style="color:#777;font-size:11px;margin-top:-3px;"></div>' +
        '<label id="rp-nospi-zeile"><input type="checkbox" id="rp-nospi" checked> No spinnaker (ORC non-spinnaker polar)</label>' +
        '<label>Departure<input type="datetime-local" id="rp-zeit" ' + inp + '></label>' +
        '<div style="display:flex;gap:6px;">' +
          '<button id="rp-start-btn" style="flex:1;cursor:pointer;">Set start</button>' +
          '<button id="rp-ziel-btn" style="flex:1;cursor:pointer;">Set destination</button>' +
        '</div>' +
        '<div id="rp-punkte" style="color:#555;">Click a button, then click on the map.</div>' +
        '<details><summary style="cursor:pointer;">Options</summary>' +
          '<div style="display:grid;grid-template-columns:1fr auto;gap:3px 6px;margin-top:4px;align-items:center;">' +
            '<span title="ORC polars assume a racing crew">Performance (% of ORC polar)</span><input id="rp-leistung" type="number" min="40" max="110" step="5" value="85" ' + num + '>' +
            '<span>Max. wind (kn)</span><input id="rp-maxwind" type="number" min="5" max="60" value="25" ' + num + '>' +
            '<span>Max. wave height (m)</span><input id="rp-maxwelle" type="number" min="0.5" max="10" step="0.5" value="2.5" ' + num + '>' +
            '<span>Tack/gybe costs (s)</span><input id="rp-wende" type="number" min="0" max="600" step="10" value="60" ' + num + '>' +
            '<label style="grid-column:1/3;"><input type="checkbox" id="rp-motor" checked> Engine when sailing is slower than</label>' +
            '<span style="padding-left:18px;">sailing speed (kn)</span><input id="rp-motorunter" type="number" min="0" max="10" step="0.5" value="3" ' + num + '>' +
            '<span style="padding-left:18px;">engine speed (kn)</span><input id="rp-motorkn" type="number" min="2" max="12" step="0.5" value="5.5" ' + num + '>' +
            '<label style="grid-column:1/3;"><input type="checkbox" id="rp-ozean" checked> Include ocean current (Copernicus)</label>' +
            '<label style="grid-column:1/3;"><input type="checkbox" id="rp-tiefe" checked> Avoid shallow water (EMODnet, Europe)</label>' +
            '<span style="padding-left:18px;">under-keel reserve (m)</span><input id="rp-reserve" type="number" min="0" max="5" step="0.1" value="0.5" ' + num + '>' +
          '</div>' +
        '</details>' +
        '<div style="display:flex;gap:6px;">' +
          '<button id="rp-go" style="flex:2;cursor:pointer;font-weight:bold;" disabled>Compute route</button>' +
          '<button id="rp-clear" style="flex:1;cursor:pointer;">Clear</button>' +
        '</div>' +
        '<div id="rp-status" style="color:#555;"></div>' +
        '<div id="rp-ergebnis"></div>' +
        '<div style="font-size:11px;color:#777;">Planning aid only. Shallow water is avoided as at chart datum (EMODnet, Europe only; flats are never crossed). Traffic separation schemes and restricted areas are not considered.</div>' +
      '</div>';
    var $ = function (id) { return document.getElementById(id); };

    var t = new Date(Date.now() + 30 * 60000); t.setMinutes(t.getMinutes() < 30 ? 30 : 60, 0, 0);
    $('rp-zeit').value = localInput(t);

    // ~2700 ORC-Klassen + Jollen (21.11.2026): [id, Name, LOA m, Non-Spinnaker vorhanden, Anzahl Zertifikate, Jolle]
    var boote = {}, bootNamen = {};
    function bootLabel(b) { return b[1] + ' (' + b[2].toFixed(1) + ' m)'; }
    function bootInfo() {
      var b = bootNamen[$('rp-boot-such').value];
      if (!b) { $('rp-boot-info').textContent = 'Unknown boat – choose one from the list'; return; }
      $('rp-boot-info').textContent = b[5] ? ('Dinghy: VPP polar calibrated to the class handicap (Portsmouth/Yardstick), about ±10 %' + (b[3] ? ', with and without spinnaker' : ', no spinnaker'))
        : b[4] + ' ORC certificate' + (b[4] > 1 ? 's' : '') + (b[3] ? ', non-spinnaker polar available' : ', no non-spinnaker polar (spinnaker polar is used)');
      $('rp-nospi').disabled = !b[3];
      $('rp-nospi-zeile').style.opacity = b[3] ? 1 : 0.5;
    }
    fetch('/api/route_boats').then(function (r) { return r.json(); }).then(function (d) {
      var html = [];
      d.boote.forEach(function (b) { boote[b[0]] = b; bootNamen[bootLabel(b)] = b; html.push('<option value="' + bootLabel(b).replace(/"/g, '&quot;') + '">'); });
      $('rp-boot-liste').innerHTML = html.join('');
      var gespeichert = null;
      try { gespeichert = localStorage.getItem('rpBoot'); } catch (e) {}
      var b = boote[gespeichert] || boote[d.standard];
      if (b) $('rp-boot-such').value = bootLabel(b);
      letzteArt = 'yacht'; vorgaben(b);
      bootInfo();
    });
    $('rp-boot-such').addEventListener('input', bootInfo);
    // Jollen: kein Motor, kurze Wende, niedrigere Wind-/Wellengrenze; beim Wechsel zurueck die Yacht-Vorgaben
    var JOLLE = { motor: false, wende: 20, maxwind: 20, maxwelle: 1.0, leistung: 95 },
        YACHT = { motor: true, wende: 60, maxwind: 25, maxwelle: 2.5, leistung: 85 }, letzteArt = null;
    function vorgaben(b) {
      var art = b && b[5] ? 'jolle' : 'yacht';
      if (art === letzteArt) return;
      var v = art === 'jolle' ? JOLLE : YACHT;
      if (letzteArt !== null) {
        $('rp-motor').checked = v.motor; $('rp-wende').value = v.wende; $('rp-maxwind').value = v.maxwind;
        $('rp-maxwelle').value = v.maxwelle; $('rp-leistung').value = v.leistung;
      }
      letzteArt = art;
    }
    $('rp-boot-such').addEventListener('change', function () {
      var b = bootNamen[this.value];
      if (b) { try { localStorage.setItem('rpBoot', b[0]); } catch (e) {} }
      vorgaben(b);
      bootInfo();
    });

    function icon(farbe, txt) {
      return L.divIcon({ className: '', iconSize: [22, 22], iconAnchor: [11, 11],
        html: '<div style="width:22px;height:22px;border-radius:50%;background:' + farbe + ';color:#fff;font:bold 12px/22px sans-serif;text-align:center;border:2px solid #fff;box-shadow:0 1px 4px rgba(0,0,0,.5);">' + txt + '</div>' });
    }
    function punktText() {
      var f = function (m) { var p = m.getLatLng(); return p.lat.toFixed(4) + ', ' + p.lng.toFixed(4); };
      $('rp-punkte').innerHTML = (state.start ? 'Start: ' + f(state.start) : 'Start: –') + '<br>' +
        (state.ziel ? 'Destination: ' + f(state.ziel) : 'Destination: –');
      $('rp-go').disabled = !(state.start && state.ziel);
    }
    function setze(art, latlng) {
      if (state[art]) { state[art].setLatLng(latlng); }
      else {
        state[art] = L.marker(latlng, { draggable: true, icon: icon(art === 'start' ? '#2a8c4a' : '#c0392b', art === 'start' ? 'A' : 'B'), zIndexOffset: 1000 }).addTo(map);
        state[art].on('dragend', punktText);
      }
      punktText();
    }
    function waehle(art) {
      state.pick = art;
      map.getContainer().style.cursor = 'crosshair';
      $('rp-punkte').textContent = 'Click on the map to set the ' + (art === 'start' ? 'start' : 'destination') + '.';
    }
    $('rp-start-btn').addEventListener('click', function () { waehle('start'); });
    $('rp-ziel-btn').addEventListener('click', function () { waehle('ziel'); });
    map.on('click', function (e) {
      if (!state.pick) return;
      setze(state.pick, e.latlng);
      state.pick = null;
      map.getContainer().style.cursor = '';
    });

    function loeschen() {
      if (state.layer) { map.removeLayer(state.layer); state.layer = null; }
      $('rp-ergebnis').innerHTML = '';
      $('rp-status').textContent = '';
    }
    $('rp-clear').addEventListener('click', function () {
      loeschen();
      ['start', 'ziel'].forEach(function (a) { if (state[a]) { map.removeLayer(state[a]); state[a] = null; } });
      punktText();
    });

    function zeichne(r) {
      loeschen();
      var g = L.featureGroup();
      var P = r.punkte;
      // Zubringer von der Eingabe zum Gitterpunkt (gestrichelt)
      L.polyline([[r.start.la, r.start.lo], [P[0].la, P[0].lo]], { color: '#555', weight: 2, dashArray: '4 4' }).addTo(g);
      L.polyline([[P[P.length - 1].la, P[P.length - 1].lo], [r.ziel.la, r.ziel.lo]], { color: '#555', weight: 2, dashArray: '4 4' }).addTo(g);
      for (var i = 0; i < P.length - 1; i++) {
        var p = P[i];
        var farbe = p.modus === 'motor' ? '#e67e22' : '#1f6fd1';
        var tip = '<b>' + hhmm(p.t) + '</b> ' + MODE[p.modus] + '<br>COG ' + p.kurs_kg + '° · SOG ' + p.sog.toFixed(1) + ' kn' +
          '<br>Wind ' + p.tws.toFixed(0) + ' kn from ' + p.twd + '° (TWA ' + p.twa + '°)' +
          '<br>Current ' + p.strom.toFixed(1) + ' kn to ' + p.strom_ri + '° · Waves ' + p.hs.toFixed(1) + ' m';
        L.polyline([[p.la, p.lo], [P[i + 1].la, P[i + 1].lo]], { color: farbe, weight: 4, opacity: 0.9 }).bindTooltip(tip, { sticky: true }).addTo(g);
      }
      // volle Stunden markieren
      var naechste = Math.ceil(P[0].t / 3600) * 3600;
      for (var k = 0; k < P.length - 1; k++) {
        while (naechste <= P[k + 1].t) {
          if (naechste >= P[k].t) {
            var f = (naechste - P[k].t) / Math.max(1, P[k + 1].t - P[k].t);
            var la = P[k].la + f * (P[k + 1].la - P[k].la), lo = P[k].lo + f * (P[k + 1].lo - P[k].lo);
            L.circleMarker([la, lo], { radius: 4, color: '#fff', weight: 1.5, fillColor: '#123', fillOpacity: 1 })
              .bindTooltip(hhmm(naechste), { permanent: map.getZoom() >= 10, direction: 'right', className: 'rp-zeit' }).addTo(g);
          }
          naechste += 3600;
        }
      }
      g.addTo(map);
      state.layer = g;

      var zeilen = r.abschnitte.map(function (a) {
        var p = P[a.von];
        return '<tr><td>' + hhmm(p.t) + '</td><td>' + (p.modus === 'motor' ? 'engine' : (p.modus === 'stb' ? 'stbd' : 'port')) + '</td><td>' + a.kurs_kg + '°</td><td>' +
          a.sm.toFixed(1) + '</td><td>' + a.sog.toFixed(1) + '</td><td>' + a.tws.toFixed(0) + '/' + a.twa + '°</td><td>' + a.strom.toFixed(1) + '</td></tr>';
      }).join('');
      $('rp-ergebnis').innerHTML =
        '<div style="background:rgba(255,255,255,.6);border-radius:4px;padding:5px 6px;">' +
          '<b>Arrival ' + dayHHMM(r.ziel.t) + '</b><br>' + dur(r.dauer_h) + ' · ' + r.strecke_sm + ' nm (direct ' + r.luftlinie_sm + ' nm) · Ø ' + r.sog_mittel + ' kn SOG<br>' +
          r.wenden + ' tacks · ' + r.halsen + ' gybes · engine ' + dur(r.motor_h) + '<br>' +
          '<span style="color:#777;">' + r.boot.name + (r.boot.variante === 'nospi' ? ' without spinnaker' : ' with spinnaker') + ' (ORC: ' + r.boot.yacht + ', draft ' + (r.boot.tiefgang || '?') + ' m) · depth: ' + r.quellen.tiefe + ' · computed in ' + r.rechenzeit.gesamt_s + ' s</span>' +
          ((r.start.verschoben || r.ziel.verschoben) ? '<br><span style="color:#a60;">' +
            (r.start.verschoben ? 'Start ' + r.start.verschoben + ' km' : '') + (r.start.verschoben && r.ziel.verschoben ? ', ' : '') +
            (r.ziel.verschoben ? 'destination ' + r.ziel.verschoben + ' km' : '') +
            ' from the computed route (dashed): on land, or behind a channel too narrow/shallow for the depth grid – follow the buoyed channel.</span>' : '') +
        '</div>' +
        '<div style="max-height:30vh;overflow-y:auto;margin-top:4px;">' +
          '<table style="width:100%;border-collapse:collapse;font-size:11px;" class="rp-tab">' +
          '<tr style="text-align:left;"><th>Time</th><th>Mode</th><th>COG</th><th>nm</th><th>SOG</th><th title="mean true wind speed / true wind angle">Wind/TWA</th><th title="strongest current on the leg (kn)">Curr.</th></tr>' + zeilen + '</table>' +
        '</div>';
    }

    $('rp-go').addEventListener('click', function () {
      if (!state.start || !state.ziel) return;
      var a = state.start.getLatLng(), b = state.ziel.getLatLng();
      var t0 = Math.round(new Date($('rp-zeit').value).getTime() / 1000);
      var q = {
        start: a.lat.toFixed(5) + ',' + a.lng.toFixed(5), ziel: b.lat.toFixed(5) + ',' + b.lng.toFixed(5), t: t0,
        boot: (bootNamen[$('rp-boot-such').value] || [''])[0], ohne_spi: $('rp-nospi').checked ? 1 : 0, leistung: (parseFloat($('rp-leistung').value) / 100).toFixed(2),
        max_wind: $('rp-maxwind').value, max_welle: $('rp-maxwelle').value, wendezeit_s: $('rp-wende').value,
        motor: $('rp-motor').checked ? 1 : 0, motor_unter: $('rp-motorunter').value, motor_kn: $('rp-motorkn').value,
        ozean: $('rp-ozean').checked ? 1 : 0, tiefe: $('rp-tiefe').checked ? 1 : 0, reserve_m: $('rp-reserve').value
      };
      var url = '/api/route?' + Object.keys(q).map(function (k) { return k + '=' + encodeURIComponent(q[k]); }).join('&');
      var nr = ++state.req;
      $('rp-go').disabled = true;
      $('rp-status').textContent = 'Computing (wind, waves, currents; usually 5–30 s)…';
      fetch(url).then(function (r) { return r.json(); }).then(function (r) {
        if (nr !== state.req) return;
        $('rp-go').disabled = false;
        if (r.error) { $('rp-status').textContent = 'Error: ' + r.error; return; }
        $('rp-status').textContent = '';
        zeichne(r);
      }).catch(function (e) {
        if (nr !== state.req) return;
        $('rp-go').disabled = false;
        $('rp-status').textContent = 'Error: ' + e;
      });
    });
    punktText();
  };
})();
