// Wind stations used to verify the wind models at surf and sailing spots (py/thermik_pruefung.py,
// Oliver 24.11.2026). Fills the "Wind Stations" menu (dropdown + show/hide) and puts a marker per station.
// Data: /static/wind_stations/wind_stations.json (written by py/thermik_pruefung.py).
(function () {
  'use strict';

  var REGIONS = [
    ['Alps & lakes', function (s) { return /Zurich|Vienna/.test(s.tz) || /See|Lago|Garda|Comer|Silvaplana|Reschen|Bodensee|Chiemsee|Müritz|Iseosee|Achensee/.test(s.spot || s.name); }],
    ['Europe', function (s) { return s.tz.indexOf('Europe/') === 0; }],
    ['Atlantic & Africa', function (s) { return /^(Atlantic|Africa|Indian)\//.test(s.tz); }],
    ['Americas', function (s) { return s.tz.indexOf('America/') === 0; }],
    ['Australia', function (s) { return s.tz.indexOf('Australia/') === 0; }],
    ['Other', function () { return true; }]
  ];

  // Colour = mean error of our per-spot correction (kn): how well the wind can be forecast there.
  var CLASSES = [
    [1.5, '#1a9850', '< 1.5 kn'],
    [2.0, '#91cf60', '1.5–2 kn'],
    [2.5, '#fdae61', '2–2.5 kn'],
    [99,  '#d73027', '> 2.5 kn']
  ];
  function colour(mae) {
    for (var i = 0; i < CLASSES.length; i++) if (mae < CLASSES[i][0]) return CLASSES[i][1];
    return CLASSES[CLASSES.length - 1][1];
  }

  function esc(t) {
    return String(t == null ? '' : t).replace(/[&<>"]/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c];
    });
  }
  function kn(v, sign) {
    if (v == null || isNaN(v)) return '–';
    return (sign && v > 0 ? '+' : '') + v.toFixed(1) + ' kn';
  }

  function icon(s) {
    var c = colour(s.corr_mae);
    var svg = '<svg width="20" height="20" viewBox="0 0 20 20">' +
      '<rect x="4" y="4" width="12" height="12" transform="rotate(45 10 10)" fill="' + c + '" stroke="#fff" stroke-width="1.8"/>' +
      '<path d="M6.5 8.5h5.5a1.6 1.6 0 1 0-1.6-1.6M6.5 11.5h7a1.6 1.6 0 1 1-1.6 1.6" fill="none" stroke="#fff" stroke-width="1.3" stroke-linecap="round"/>' +
      '</svg>';
    return L.divIcon({ className: 'wind-station-icon', html: svg, iconSize: [20, 20], iconAnchor: [10, 10], popupAnchor: [0, -9] });
  }

  function popup(s, meta) {
    var src = s.link
      ? '<a href="' + esc(s.link) + '" target="_blank" rel="noopener">' + esc(s.source) + ' ' + esc(s.id) + '</a>'
      : esc(s.source) + ' ' + esc(s.id);
    var num = function (v, sign) { return (v == null || isNaN(v)) ? '–' : (sign && v > 0 ? '+' : '') + v.toFixed(1); };
    var row = function (label, mae, bias) {
      return '<tr><td style="padding:1px 8px 1px 0;white-space:nowrap;">' + label + '</td><td style="text-align:right;padding:1px 6px;">' +
        num(mae) + '</td><td style="text-align:right;padding:1px 0 1px 6px;color:#555;">' + (bias == null ? '' : num(bias, true)) + '</td></tr>';
    };
    var models = (s.models || []).map(function (m) {
      return '<tr><td style="padding:0 8px 0 0;white-space:nowrap;">' + esc(m.m) + '</td><td style="text-align:right;padding:0 6px;">' + m.mae.toFixed(2) +
        '</td><td style="text-align:right;padding:0 6px;">' + (m.bias > 0 ? '+' : '') + m.bias.toFixed(1) +
        '</td><td style="text-align:right;padding:0 6px;">' + (isNaN(m.r) ? '' : m.r.toFixed(2)) +
        '</td><td style="text-align:right;padding:0 0 0 6px;">' + m.corr_mae.toFixed(2) + '</td></tr>';
    }).join('');
    return '<div style="font-family:sans-serif;font-size:12.5px;min-width:260px;max-width:340px;">' +
      '<div style="font-weight:bold;font-size:14px;margin-bottom:2px;">' + esc(s.name) + '</div>' +
      (s.spot ? '<div style="margin-bottom:2px;">Spot: <b>' + esc(s.spot) + '</b></div>' : '') +
      '<div style="color:#555;">' + src + (s.note ? ' · ' + esc(s.note) : '') + '</div>' +
      '<div style="color:#777;font-size:11.5px;margin-bottom:6px;">' + s.lat.toFixed(4) + ', ' + s.lon.toFixed(4) + '</div>' +
      '<div style="margin-bottom:4px;">Measured ' + esc(meta.period) + ', ' + esc(meta.hours) + ': mean <b>' + kn(s.mean_kn) +
        '</b>, ' + s.hours12 + ' h ≥ 12 kn</div>' +
      '<table style="border-collapse:collapse;font-size:12.5px;">' +
        '<tr style="color:#777;font-size:11px;"><td>Forecast</td><td style="text-align:right;padding:0 6px;white-space:nowrap;">error kn</td><td style="text-align:right;padding:0 0 0 6px;white-space:nowrap;">bias kn</td></tr>' +
        row('Open-Meteo best match', s.best_match_mae, s.best_match_bias) +
        (s.best_model ? row('Best model: ' + esc(s.best_model), s.best_model_mae, s.best_model_bias) : '') +
        row('<b>Spot correction</b>', s.corr_mae, null) +
      '</table>' +
      '<div style="color:#555;margin-top:2px;">Spot correction detects ' + Math.round(s.corr_pod12 * 100) + ' % of the hours ≥ 12 kn (' +
        Math.round(s.corr_far12 * 100) + ' % false alarms).</div>' +
      (s.lag_h ? '<div style="color:#a60;margin-top:3px;">Time offset model ↔ station: ' + (s.lag_h > 0 ? '+' : '') + s.lag_h + ' h</div>' : '') +
      '<div class="wst-fc" style="margin-top:6px;color:#777;font-size:11.5px;">Loading forecast…</div>' +
      '<details style="margin-top:5px;"><summary style="cursor:pointer;color:#246;">All models (' + (s.models || []).length + ')</summary>' +
        '<table style="border-collapse:collapse;font-size:11.5px;margin-top:3px;">' +
        '<tr style="color:#777;"><td>Model</td><td style="text-align:right;padding:0 6px;">error</td><td style="text-align:right;padding:0 6px;">bias</td><td style="text-align:right;padding:0 6px;">r</td><td style="text-align:right;padding-left:6px;">corrected</td></tr>' +
        models + '</table>' +
        '<div style="color:#777;font-size:11px;margin-top:3px;">Error = mean absolute error of the wind speed, bias = forecast − measured (kn). ' +
        'Corrected = with the learned per-spot correction (cross-validated by month).</div>' +
      '</details></div>';
  }

  // Live forecast with the per-spot correction (/api/wind_spot_forecast, py/thermik_korrektur.py)
  function windCell(v, strong) {
    if (v == null) return '<td style="text-align:center;color:#bbb;padding:1px 2px;">·</td>';
    var bg = v >= 20 ? '#7b3294' : v >= 15 ? '#d7301f' : v >= 12 ? '#fc8d59' : v >= 8 ? '#fdd49e' : 'transparent';
    var fg = v >= 15 ? '#fff' : '#222';
    return '<td style="text-align:center;padding:1px 2px;background:' + bg + ';color:' + fg + ';' + (strong ? 'font-weight:bold;' : '') + '">' + Math.round(v) + '</td>';
  }
  function renderForecast(el, f) {
    var days = {}, order = [];
    (f.stunden || []).forEach(function (h) {
      var d = h.t.slice(0, 10);
      if (!days[d]) { days[d] = {}; order.push(d); }
      days[d][parseInt(h.t.slice(11, 13), 10)] = h;
    });
    var hours = []; for (var i = 9; i <= 19; i++) hours.push(i);
    var anyCorr = (f.stunden || []).some(function (h) { return h.korr != null; });
    var wd = ['Su', 'Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa'];
    var head = '<tr style="color:#777;"><td></td>' + hours.map(function (h) { return '<td style="text-align:center;padding:0 2px;">' + h + '</td>'; }).join('') + '</tr>';
    var rows = order.map(function (d) {
      var dt = new Date(d + 'T12:00:00');
      var label = wd[dt.getDay()] + ' ' + d.slice(8, 10) + '.';
      var r1 = '<tr><td style="padding-right:4px;white-space:nowrap;">' + label + '</td>' + hours.map(function (h) {
        var x = days[d][h]; return windCell(x ? (anyCorr ? x.korr : x.best_match) : null, anyCorr);
      }).join('') + '</tr>';
      var r2 = anyCorr ? '<tr style="color:#888;font-size:10px;"><td style="text-align:right;padding-right:4px;">bm</td>' + hours.map(function (h) {
        var x = days[d][h]; return '<td style="text-align:center;">' + (x && x.best_match != null ? Math.round(x.best_match) : '') + '</td>';
      }).join('') + '</tr>' : '';
      return r1 + r2;
    }).join('');
    el.style.color = '#222';
    el.innerHTML = '<div style="font-weight:bold;margin-bottom:2px;">' + (anyCorr ? 'Forecast with spot correction (kn)' : 'Forecast, Open-Meteo best match (kn)') + '</div>' +
      '<table style="border-collapse:collapse;font-size:11px;">' + head + rows + '</table>' +
      '<div style="color:#777;font-size:10.5px;margin-top:2px;">' + (anyCorr
        ? 'Top row: corrected (local time), bm = Open-Meteo best match. Learned from ' + esc((f.lernjahre || []).join(', ')) +
          ' at short lead time; days 3–7 use fewer models and are less certain.'
        : 'The spot correction is only learned for May–September (thermal season) and is not applied now.') + '</div>';
  }
  function loadForecast(popupEl, name) {
    var el = popupEl && popupEl.querySelector('.wst-fc');
    if (!el || el.getAttribute('data-done')) return;
    el.setAttribute('data-done', '1');
    fetch('/api/wind_spot_forecast?name=' + encodeURIComponent(name))
      .then(function (r) { return r.json().then(function (j) { if (!r.ok) throw new Error(j.error || r.status); return j; }); })
      .then(function (f) { renderForecast(el, f); })
      .catch(function (e) { el.removeAttribute('data-done'); el.textContent = 'No live forecast: ' + e.message; });
  }

  function build(map, data) {
    var body = document.getElementById('wind-stations-body');
    var count = document.getElementById('wind-stations-count');
    var stations = data.stations || [];
    if (count) count.textContent = '(' + stations.length + ')';

    var layer = L.layerGroup();
    var byName = {};
    stations.forEach(function (s) {
      var m = L.marker([s.lat, s.lon], { icon: icon(s), title: s.name, riseOnHover: true, zIndexOffset: 500 });
      m.bindPopup(popup(s, data), { maxWidth: 380 });
      m.on('popupopen', function (e) { loadForecast(e.popup.getElement(), s.name); });
      m.addTo(layer);
      byName[s.name] = m;
    });

    var groups = REGIONS.map(function (r) { return { label: r[0], test: r[1], items: [] }; });
    stations.forEach(function (s) {
      for (var i = 0; i < groups.length; i++) if (groups[i].test(s)) { groups[i].items.push(s); break; }
    });
    groups.forEach(function (g) { g.items.sort(function (a, b) { return (a.spot || a.name).localeCompare(b.spot || b.name); }); });
    var options = '<option value="">Choose a station…</option>' + groups.filter(function (g) { return g.items.length; }).map(function (g) {
      return '<optgroup label="' + esc(g.label) + '">' + g.items.map(function (s) {
        return '<option value="' + esc(s.name) + '">' + esc(s.spot ? s.spot + ' (' + s.name + ')' : s.name) + ' – ' + s.corr_mae.toFixed(1) + ' kn</option>';
      }).join('') + '</optgroup>';
    }).join('');

    var legend = CLASSES.map(function (c) {
      return '<span style="white-space:nowrap;margin-right:8px;"><span style="display:inline-block;width:9px;height:9px;background:' + c[1] +
        ';transform:rotate(45deg);margin-right:4px;border:1px solid #fff;"></span>' + c[2] + '</span>';
    }).join(' ');

    body.innerHTML =
      '<label style="display:flex;align-items:center;cursor:pointer;font-weight:bold;min-height:30px;">' +
        '<input type="checkbox" id="wst-toggle" style="margin-right:6px;width:18px;height:18px;">Show on map</label>' +
      '<select id="wst-select" style="width:100%;max-width:290px;margin:4px 0 6px;padding:4px;font-size:13px;border-radius:4px;border:1px solid #bbb;background:rgba(255,255,255,0.85);">' +
        options + '</select>' +
      '<div style="font-size:11.5px;color:#444;max-width:290px;line-height:1.5;">Colour = forecast error after spot correction:<br>' + legend + '</div>' +
      '<div style="font-size:11px;color:#666;max-width:290px;margin-top:4px;">Stations used to check the wind models at surf and sailing spots (' +
        esc(data.period) + ', ' + esc(data.hours) + ').</div>';

    var cb = document.getElementById('wst-toggle');
    var on = localStorage.getItem('windStationsOn');
    cb.checked = (on === null) ? true : on === '1';
    if (cb.checked) layer.addTo(map);
    cb.addEventListener('change', function () {
      if (this.checked) layer.addTo(map); else map.removeLayer(layer);
      localStorage.setItem('windStationsOn', this.checked ? '1' : '0');
    });

    document.getElementById('wst-select').addEventListener('change', function () {
      var m = byName[this.value];
      if (!m) return;
      if (!map.hasLayer(layer)) { cb.checked = true; layer.addTo(map); localStorage.setItem('windStationsOn', '1'); }
      map.flyTo(m.getLatLng(), Math.max(map.getZoom(), 10), { duration: 1.2 });
      map.once('moveend', function () { m.openPopup(); });
    });
    buildNet(map, body);
  }

  // ---- Official station network: METAR airports (NOAA AWC) + WMO synoptic stations (OSCAR/Surface), Oliver 25.11.2026.
  // Data: /static/wind_stations/stationsnetz.json (py/stationsnetz.py), rows [lat, lon, name, icao, wmo, elev_m, type, wdqms],
  // type 1 = METAR, 2 = SYNOP, 3 = both.
  var NET_COL = { 1: '#1f78b4', 2: '#2e8b3a', 3: '#7a3db8' };
  var WDQMS_TXT = { o: 'reports arrive regularly', p: 'reports arrive partly', n: 'no reports received', u: 'reception not assessed by WMO' };
  function netPopup(s) {
    var lines = [];
    if (s[3]) lines.push('ICAO <b>' + esc(s[3]) + '</b> · <a href="https://aviationweather.gov/data/metar/?ids=' + encodeURIComponent(s[3]) +
      '&hours=24" target="_blank" rel="noopener">METAR history (NOAA AWC)</a>');
    if (s[4]) lines.push('WMO <b>' + esc(s[4]) + '</b> · <a href="https://oscar.wmo.int/surface/#/search/station/stationReportDetails/0-20000-0-' +
      encodeURIComponent(s[4]) + '" target="_blank" rel="noopener">WMO OSCAR</a>' + (s[7] ? ' · SYNOP ' + esc(WDQMS_TXT[s[7]] || '') : ''));
    var typ = s[6] === 3 ? 'Airport with METAR + synoptic station' : s[6] === 1 ? 'Airport with METAR' : 'Synoptic station (WMO)';
    return '<div style="font-family:sans-serif;font-size:12.5px;min-width:240px;max-width:360px;">' +
      '<div style="font-weight:bold;font-size:14px;">' + esc(s[2]) + '</div>' +
      '<div style="color:#555;margin-bottom:3px;">' + typ + (s[5] != null && s[5] !== 9999 ? ' · ' + esc(s[5]) + ' m' : '') + '</div>' +
      lines.map(function (l) { return '<div>' + l + '</div>'; }).join('') +
      '<div style="color:#777;font-size:11.5px;margin-top:2px;">' + s[0].toFixed(4) + ', ' + s[1].toFixed(4) + '</div>' +
      (s[3] ? '<div class="net-metar" style="margin-top:6px;color:#777;font-size:11.5px;">Loading METAR…</div>' : '') + '</div>';
  }
  function loadMetar(popupEl, icao) {
    var el = popupEl && popupEl.querySelector('.net-metar');
    if (!el) return;
    fetch('/api/metar?id=' + encodeURIComponent(icao))
      .then(function (r) { return r.json().then(function (j) { if (!r.ok) throw new Error(j.error || r.status); return j; }); })
      .then(function (j) {
        var m = j.metars || [];
        if (!m.length) { el.textContent = 'No METAR in the last 6 hours.'; return; }
        var w = m[0], wind = '';
        if (w.wspd != null) wind = (w.wdir === 'VRB' ? 'variable' : (w.wdir != null ? w.wdir + '°' : '')) + ' ' + w.wspd + ' kn' + (w.wgst ? ', gusts ' + w.wgst + ' kn' : '');
        el.style.color = '#222';
        el.innerHTML = (wind ? '<div>Latest wind: <b>' + esc(wind) + '</b></div>' : '') +
          '<div style="font-family:monospace;font-size:11px;white-space:pre-wrap;margin-top:3px;">' +
          m.slice(0, 6).map(function (x) { return esc(x.rawOb); }).join('\n') + '</div>' +
          '<div style="color:#777;font-size:10.5px;margin-top:2px;">Source: NOAA Aviation Weather Center</div>';
      })
      .catch(function (e) { el.textContent = 'METAR could not be loaded: ' + e.message; });
  }
  function buildNet(map, body) {
    var box = document.createElement('div');
    box.style.cssText = 'margin-top:8px;padding-top:6px;border-top:1px solid #ccc;max-width:290px;';
    box.innerHTML = '<div style="font-size:11.5px;color:#666;">Loading official stations…</div>';
    body.appendChild(box);
    fetch('/static/wind_stations/stationsnetz.json', { cache: 'no-cache' })
      .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
      .then(function (d) {
        // own pane above the tide/current markers (markerPane 600), otherwise coastal stations hide under tide gauges
        if (!map.getPane('netPane')) { map.createPane('netPane'); map.getPane('netPane').style.zIndex = 620; }
        var renderer = L.canvas({ padding: 0.3, pane: 'netPane' });
        var layers = { metar: L.layerGroup(), synop: L.layerGroup(), both: L.layerGroup() };
        var n = { 1: 0, 2: 0, 3: 0 };
        d.stationen.forEach(function (s) {
          n[s[6]]++;
          var m = L.circleMarker([s[0], s[1]], { renderer: renderer, pane: 'netPane', radius: s[6] === 2 ? 5 : 6, weight: 1.5, color: '#fff',
            fillColor: s[6] === 2 && s[7] === 'n' ? '#9a9a9a' : NET_COL[s[6]], fillOpacity: 0.95 });
          m.bindTooltip(s[2] + (s[3] ? ' (' + s[3] + ')' : s[4] ? ' (' + s[4] + ')' : ''), { direction: 'top', offset: [0, -3] });
          m.bindPopup(function () { return netPopup(s); }, { maxWidth: 380 });
          if (s[3]) m.on('popupopen', function (e) { loadMetar(e.popup.getElement(), s[3]); });
          m.addTo(s[6] === 1 ? layers.metar : s[6] === 2 ? layers.synop : layers.both);
        });
        var dot = function (c) { return '<span style="display:inline-block;width:9px;height:9px;border-radius:50%;background:' + c + ';margin:0 5px 0 2px;"></span>'; };
        box.innerHTML =
          '<div style="font-weight:bold;font-size:12.5px;margin-bottom:2px;">Official stations</div>' +
          '<label style="display:flex;align-items:center;cursor:pointer;min-height:26px;font-size:12.5px;">' +
            '<input type="checkbox" id="net-metar" style="margin-right:6px;width:16px;height:16px;">' + dot(NET_COL[1]) + 'Airports with METAR (' + (n[1] + n[3]) + ')</label>' +
          '<label style="display:flex;align-items:center;cursor:pointer;min-height:26px;font-size:12.5px;">' +
            '<input type="checkbox" id="net-synop" style="margin-right:6px;width:16px;height:16px;">' + dot(NET_COL[2]) + 'WMO synoptic stations (' + (n[2] + n[3]) + ')</label>' +
          '<div style="font-size:11px;color:#666;line-height:1.5;">' + dot(NET_COL[3]) + 'both (' + n[3] + ').' + dot('#9a9a9a') + 'WMO receives no reports. ' +
            'Sources: NOAA Aviation Weather Center, WMO OSCAR/Surface (' + esc(d.stand) + ').</div>';
        var cbM = document.getElementById('net-metar'), cbS = document.getElementById('net-synop');
        var get = function (k) { try { return localStorage.getItem(k) === '1'; } catch (e) { return false; } };
        cbM.checked = get('netMetarOn'); cbS.checked = get('netSynopOn');
        var update = function () {
          var show = { metar: cbM.checked, synop: cbS.checked, both: cbM.checked || cbS.checked };
          Object.keys(layers).forEach(function (k) {
            if (show[k] && !map.hasLayer(layers[k])) layers[k].addTo(map);
            if (!show[k] && map.hasLayer(layers[k])) map.removeLayer(layers[k]);
          });
          try { localStorage.setItem('netMetarOn', cbM.checked ? '1' : '0'); localStorage.setItem('netSynopOn', cbS.checked ? '1' : '0'); } catch (e) { /* ignore */ }
        };
        cbM.addEventListener('change', update); cbS.addEventListener('change', update);
        update();
      })
      .catch(function (e) {
        box.innerHTML = '<span style="color:#a00;font-size:12px;">Official stations could not be loaded.</span>';
        console.error('station network:', e);
      });
  }

  function start() {
    var map = window.map;
    var body = document.getElementById('wind-stations-body');
    if (!map || !body) { setTimeout(start, 300); return; }
    fetch('/static/wind_stations/wind_stations.json', { cache: 'no-cache' })
      .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
      .then(function (d) { build(map, d); })
      .catch(function (e) {
        body.innerHTML = '<span style="color:#a00;">Wind stations could not be loaded.</span>';
        console.error('wind stations:', e);
      });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
  else start();
})();
