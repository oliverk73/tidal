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
  var MODE = { stb: 'starboard tack', bb: 'port tack', motor: 'engine', warten: 'waiting for the tide', nacht: 'night in harbour' };

  window.initRoutePlanner = function (map, body) {
    var state = { start: null, ziel: null, pick: null, layer: null, req: 0 };
    var inp = 'style="width:100%;box-sizing:border-box;padding:3px 4px;font-size:12px;"';
    var num = 'style="width:52px;padding:2px 3px;font-size:12px;"';
    body.innerHTML =
      '<div style="display:flex;flex-direction:column;gap:6px;width:250px;font-size:12px;">' +
        '<label>Boat (ORC, type to search)<input id="rp-boot-such" list="rp-boot-liste" autocomplete="off" placeholder="e.g. Bavaria 37, Hanse 370 …" ' + inp + '></label>' +
        '<datalist id="rp-boot-liste"></datalist>' +
        '<div id="rp-boot-info" style="color:#777;font-size:11px;margin-top:-3px;"></div>' +
        '<label title="Fills the options below for a cruising crew (reduced performance, no spinnaker, engine, conservative limits) or a racing crew (full ORC polar, spinnaker, no engine, quick tacks). All values can still be changed under Options.">Sailing style<select id="rp-stil" ' + inp + '><option value="toern">Cruising</option><option value="regatta">Racing</option></select></label>' +
        '<label id="rp-nospi-zeile" title="Uses the ORC non-spinnaker certificate of the class; where there is none, the spinnaker polar reduced by the median ratio of 800 classes with both certificates (about ±3 %)"><input type="checkbox" id="rp-nospi" checked> No spinnaker</label>' +
        '<label>Departure<input type="datetime-local" id="rp-zeit" ' + inp + '></label>' +
        '<label title="Sail only between dawn and dusk (civil twilight). At night the boat stays in a marina, harbour or anchorage (OpenStreetMap) or at the start, and continues at dawn. Longer passages become multi-day trips."><input type="checkbox" id="rp-nacht"> Avoid sailing at night (overnight in harbour)</label>' +
        '<label id="rp-tagh-zeile" style="padding-left:18px;display:none;" title="Each day ends in a harbour after at most this many hours under way (counted from dawn; empty = until dusk)">max. hours under way per day <input id="rp-tagh" type="number" min="2" max="24" step="1" placeholder="–" ' + num + '></label>' +
        '<div style="display:flex;gap:6px;">' +
          '<button id="rp-start-btn" style="flex:1;cursor:pointer;">Set start</button>' +
          '<button id="rp-ziel-btn" style="flex:1;cursor:pointer;">Set destination</button>' +
        '</div>' +
        '<div id="rp-punkte" style="color:#555;">Click a button, then click on the map.</div>' +
        '<details><summary style="cursor:pointer;">Options</summary>' +
          '<div style="display:grid;grid-template-columns:1fr auto;gap:3px 6px;margin-top:4px;align-items:center;">' +
            '<span title="ORC polars assume a racing crew with a clean bottom and new sails; cruising boats typically reach 80–90 %">Performance (% of ORC polar)</span><input id="rp-leistung" type="number" min="40" max="110" step="5" value="85" ' + num + '>' +
            '<span title="A cruising crew reefs earlier than the racing crew of the ORC polar: from this true wind speed, 1.5 % less speed per knot upwind to beam reach (at most 15 %). Estimate. 0 = off">Reef from (kn true wind)</span><input id="rp-reffen" type="number" min="0" max="40" step="1" value="18" ' + num + '>' +
            '<span>Max. wind (kn)</span><input id="rp-maxwind" type="number" min="5" max="60" value="25" ' + num + '>' +
            '<span>Max. wave height (m)</span><input id="rp-maxwelle" type="number" min="0.5" max="10" step="0.5" value="2.5" ' + num + '>' +
            '<span>Tack/gybe costs (s)</span><input id="rp-wende" type="number" min="0" max="600" step="10" value="60" ' + num + '>' +
            '<label style="grid-column:1/3;"><input type="checkbox" id="rp-motor" checked> Engine when sailing is slower than</label>' +
            '<span style="padding-left:18px;">sailing speed (kn)</span><input id="rp-motorunter" type="number" min="0" max="10" step="0.5" value="3" ' + num + '>' +
            '<span style="padding-left:18px;">engine speed (kn)</span><input id="rp-motorkn" type="number" min="2" max="12" step="0.5" value="5.5" ' + num + '>' +
            '<label style="grid-column:1/3;"><input type="checkbox" id="rp-ozean" checked> Include ocean current (Copernicus)</label>' +
            '<label style="grid-column:1/3;"><input type="checkbox" id="rp-tiefe" checked> Avoid shallow water (EMODnet, Europe)</label>' +
            '<span style="padding-left:18px;">under-keel reserve (m)</span><input id="rp-reserve" type="number" min="0" max="5" step="0.1" value="0.5" ' + num + '>' +
            '<label style="grid-column:1/3;padding-left:18px;"><input type="checkbox" id="rp-tide" checked> Use tide height (pass flats at high water, wait if needed)</label>' +
            '<label style="grid-column:1/3;padding-left:18px;"><input type="checkbox" id="rp-windstau" checked> Include storm surge forecast in the tide height</label>' +
            '<label style="grid-column:1/3;"><input type="checkbox" id="rp-vtg" checked> Obey traffic separation schemes (OpenSeaMap)</label>' +
            '<label style="grid-column:1/3;"><input type="checkbox" id="rp-sperr" checked> Avoid no-entry areas (OpenSeaMap)</label>' +
          '</div>' +
        '</details>' +
        '<div style="display:flex;gap:6px;">' +
          '<button id="rp-go" style="flex:2;cursor:pointer;font-weight:bold;" disabled>Compute route</button>' +
          '<button id="rp-clear" style="flex:1;cursor:pointer;">Clear</button>' +
        '</div>' +
        '<div id="rp-status" style="color:#555;"></div>' +
        '<div id="rp-ergebnis"></div>' +
        '<div style="font-size:11px;color:#777;">Planning aid only. Depth from EMODnet (Europe only) with predicted tide and storm surge; traffic separation schemes and no-entry areas from OpenSeaMap. Check charts, notices to mariners and the harbours chosen for the night.</div>' +
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
        : b[4] + ' ORC certificate' + (b[4] > 1 ? 's' : '') + (b[3] === 1 ? ', non-spinnaker polar available' : ', no spinnaker: derived from the spinnaker polar');
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
      bootInfo();
      letzteArt = null; vorgaben(b);
    });
    $('rp-boot-such').addEventListener('input', bootInfo);
    // Vorgaben je Bootsart und Stil (22.11.2026: Segeltoern / Regatta). Jollen: kein Motor, kurze Wende, niedrigere
    // Wind-/Wellengrenze. Gesetzt bei Stilwechsel und beim Wechsel Yacht <-> Jolle; danach frei aenderbar.
    var VORGABE = {
      yacht: { toern: { motor: true, wende: 60, maxwind: 25, maxwelle: 2.5, leistung: 85, nospi: true, reffen: 18 },
               regatta: { motor: false, wende: 30, maxwind: 35, maxwelle: 4.0, leistung: 100, nospi: false, reffen: 0 } },
      jolle: { toern: { motor: false, wende: 20, maxwind: 18, maxwelle: 1.0, leistung: 85, nospi: true, reffen: 12 },
               regatta: { motor: false, wende: 15, maxwind: 25, maxwelle: 1.5, leistung: 100, nospi: false, reffen: 0 } }
    }, letzteArt = null;
    try { var st = localStorage.getItem('rpStil'); if (st === 'regatta' || st === 'toern') $('rp-stil').value = st; } catch (e) {}
    function anwenden(art) {
      var stil = $('rp-stil').value, v = VORGABE[art][stil];
      $('rp-motor').checked = v.motor; $('rp-wende').value = v.wende; $('rp-maxwind').value = v.maxwind;
      $('rp-maxwelle').value = v.maxwelle; $('rp-leistung').value = v.leistung; $('rp-reffen').value = v.reffen;
      if (!$('rp-nospi').disabled) $('rp-nospi').checked = v.nospi;
      if (stil === 'regatta') { $('rp-nacht').checked = false; $('rp-tagh-zeile').style.display = 'none'; }
    }
    function vorgaben(b) {
      var art = b && b[5] ? 'jolle' : 'yacht';
      if (art === letzteArt) return;
      letzteArt = art;
      anwenden(art);
    }
    $('rp-stil').addEventListener('change', function () {
      try { localStorage.setItem('rpStil', this.value); } catch (e) {}
      anwenden(letzteArt || 'yacht');
    });
    $('rp-nacht').addEventListener('change', function () { $('rp-tagh-zeile').style.display = this.checked ? '' : 'none'; });
    $('rp-boot-such').addEventListener('change', function () {
      var b = bootNamen[this.value];
      if (b) { try { localStorage.setItem('rpBoot', b[0]); } catch (e) {} }
      bootInfo();
      vorgaben(b);
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
        state[art] = L.marker(latlng, { draggable: true, icon: icon(art === 'start' ? '#2a8c4a' : '#c0392b', art === 'start' ? 'S' : 'F'), zIndexOffset: 1000 }).addTo(map);
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
        var farbe = p.modus === 'motor' ? '#e67e22' : (p.nacht ? '#1b2f6b' : '#1f6fd1');
        var tip = '<b>' + hhmm(p.t) + '</b> ' + MODE[p.modus] + '<br>COG ' + p.kurs_kg + '° · SOG ' + p.sog.toFixed(1) + ' kn' +
          '<br>Wind ' + p.tws.toFixed(0) + ' kn from ' + p.twd + '° (TWA ' + p.twa + '°)' +
          '<br>Current ' + p.strom.toFixed(1) + ' kn to ' + p.strom_ri + '° · Waves ' + p.hs.toFixed(1) + ' m' +
          (p.tiefe != null ? '<br>Depth ' + p.tiefe.toFixed(1) + ' m (tide ' + p.tide.toFixed(1) + ' m above LAT)' : '');
        if (p.modus === 'nacht') {
          L.marker([p.la, p.lo], { icon: L.divIcon({ className: '', html: '<div style="width:20px;height:20px;border-radius:50%;background:#1b2f6b;color:#fff;font-size:13px;line-height:20px;text-align:center;border:2px solid #fff;box-shadow:0 0 3px #000;">☾</div>', iconSize: [24, 24], iconAnchor: [12, 12] }) })
            .bindTooltip('<b>Night ' + dayHHMM(p.t) + ' – ' + dayHHMM(P[i + 1].t) + '</b><br>' + (p.liege === 'start' ? 'at the start' : p.liege), { sticky: true }).addTo(g);
          continue;
        }
        if (p.modus === 'warten') {
          L.circleMarker([p.la, p.lo], { radius: 7, color: '#8e44ad', weight: 2, fillColor: '#fff', fillOpacity: 1 })
            .bindTooltip('<b>' + hhmm(p.t) + '–' + hhmm(P[i + 1].t) + '</b> waiting for the tide (not enough water ahead)', { sticky: true }).addTo(g);
          continue;
        }
        L.polyline([[p.la, p.lo], [P[i + 1].la, P[i + 1].lo]], { color: farbe, weight: 4, opacity: 0.9 }).bindTooltip(tip, { sticky: true }).addTo(g);
      }
      // volle Stunden markieren
      var naechste = Math.ceil(P[0].t / 3600) * 3600;
      for (var k = 0; k < P.length - 1; k++) {
        while (naechste <= P[k + 1].t) {
          if (naechste >= P[k].t && P[k].modus !== 'nacht' && P[k].modus !== 'warten') {
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

      var mehrtag = r.dauer_h > 18;
      function zeit(t) { return mehrtag ? new Date(t * 1000).toLocaleDateString(undefined, { weekday: 'short' }) + ' ' + hhmm(t) : hhmm(t); }
      var zeilen = r.abschnitte.map(function (a) {
        var p = P[a.von];
        if (a.modus === 'nacht') {
          return '<tr style="background:rgba(27,47,107,.15);"><td>' + zeit(p.t) + ' ☾</td><td colspan="6"><b>Night ' + (a.liege === 'start' ? 'at the start' : 'in ' + a.liege) + '</b>, continue ' + dayHHMM(a.bis_t) + '</td></tr>';
        }
        return '<tr' + (a.nacht ? ' style="background:rgba(40,40,90,.12);" title="in darkness (after civil twilight)"' : '') + '><td>' + zeit(p.t) + (a.nacht ? ' ☾' : '') + '</td><td>' + (p.modus === 'warten' ? 'wait' : (p.modus === 'motor' ? 'engine' : (p.modus === 'stb' ? 'stbd' : 'port'))) + '</td><td>' + a.kurs_kg + '°</td><td>' +
          a.sm.toFixed(1) + '</td><td>' + a.sog.toFixed(1) + '</td><td>' + a.tws.toFixed(0) + '/' + a.twa + '°</td><td>' + a.strom.toFixed(1) + '</td></tr>';
      }).join('');
      $('rp-ergebnis').innerHTML =
        '<div style="background:rgba(255,255,255,.6);border-radius:4px;padding:5px 6px;">' +
          (r.abfahrt && r.abfahrt - r.start.t > 600 ? 'Departure ' + dayHHMM(r.abfahrt) + ' (at dawn)<br>' : '') +
          '<b>Arrival ' + dayHHMM(r.ziel.t) + '</b><br>' + (r.liege_h ? 'under way ' + dur(r.fahrt_h) + ' + ' + r.naechte.length + (r.naechte.length === 1 ? ' night' : ' nights') + ' in harbour (' +
            r.naechte.map(function (x) { return x.name === 'start' ? 'start' : x.name; }).join(', ') + ') · ' : dur(r.dauer_h) + ' · ') + + r.strecke_sm + ' nm (direct ' + r.luftlinie_sm + ' nm) · Ø ' + r.sog_mittel + ' kn SOG<br>' +
          r.wenden + ' tacks · ' + r.halsen + ' gybes · engine ' + dur(r.motor_h) + (r.warten_h ? ' · <span style="color:#8e44ad;">waiting for the tide ' + dur(r.warten_h) + '</span>' : '') +
          (r.nacht_h ? ' · ☾ ' + dur(r.nacht_h) + ' in darkness' : '') + '<br>' +
          '<span style="color:#777;">' + r.boot.name + (r.boot.variante === 'nospi' ? ' without spinnaker' : ' with spinnaker') + ' (ORC: ' + r.boot.yacht + ', draft ' + (r.boot.tiefgang || '?') + ' m) · depth: ' + r.quellen.tiefe + (r.quellen.windstau && r.quellen.windstau !== 'off' ? ' · storm surge: ' + r.quellen.windstau : '') + ' · TSS: ' + r.quellen.vtg + ' · computed in ' + r.rechenzeit.gesamt_s + ' s</span>' +
          ((r.hinweise && r.hinweise.length) ? '<br><span style="color:#777;font-size:10px;">' + r.hinweise.join('<br>') + '</span>' : '') +
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
        max_wind: $('rp-maxwind').value, reffen_ab: $('rp-reffen').value || 0, max_welle: $('rp-maxwelle').value, wendezeit_s: $('rp-wende').value,
        motor: $('rp-motor').checked ? 1 : 0, motor_unter: $('rp-motorunter').value, motor_kn: $('rp-motorkn').value,
        ozean: $('rp-ozean').checked ? 1 : 0, tiefe: $('rp-tiefe').checked ? 1 : 0, tide: $('rp-tide').checked ? 1 : 0, windstau: $('rp-windstau').checked ? 1 : 0, nacht_meiden: $('rp-nacht').checked ? 1 : 0, max_tag_h: $('rp-nacht').checked ? ($('rp-tagh').value || '') : '', vtg: $('rp-vtg').checked ? 1 : 0, sperr: $('rp-sperr').checked ? 1 : 0, reserve_m: $('rp-reserve').value
      };
      var url = '/api/route?' + Object.keys(q).map(function (k) { return k + '=' + encodeURIComponent(q[k]); }).join('&');
      var nr = ++state.req;
      $('rp-go').disabled = true;
      $('rp-status').textContent = 'Computing (wind, waves, currents; usually 5–30 s, multi-day trips up to ~2 min)…';
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
