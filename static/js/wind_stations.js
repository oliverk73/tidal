// Wind stations used to verify the wind models at surf and sailing spots (py/thermik_pruefung.py,
// Oliver 24.11.2026). Fills the "Wind Stations" menu (dropdown + show/hide) and puts a marker per station.
// Data: /static/wind_stations/wind_stations.json (written by py/thermik_pruefung.py).
(function () {
  'use strict';

  // Weather stations for the map search (static/js/suche.js, Oliver 25.11.2026):
  // entries {name, detail, keys, kind, badge, lat, lon, show()}.
  var WS = window.weatherSearch = window.weatherSearch || { list: [] };

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

  // header count of the "Wind Stations" box: spot stations + every station of the official/national layers
  var WS_COUNT = { spots: 0, net: 0 };
  function showCount() {
    var el = document.getElementById('wind-stations-count');
    if (el) el.textContent = '(' + (WS_COUNT.spots + WS_COUNT.net).toLocaleString('en-US') + ')';
  }
  function build(map, data) {
    var body = document.getElementById('wind-stations-body');
    var count = document.getElementById('wind-stations-count');
    var stations = data.stations || [];
    WS_COUNT.spots = stations.length;
    showCount();

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

    var showSpot = function (name) {
      var m = byName[name];
      if (!m) return;
      if (!map.hasLayer(layer)) { cb.checked = true; layer.addTo(map); localStorage.setItem('windStationsOn', '1'); }
      map.flyTo(m.getLatLng(), Math.max(map.getZoom(), 10), { duration: 1.2 });
      map.once('moveend', function () { m.openPopup(); });
    };
    document.getElementById('wst-select').addEventListener('change', function () { showSpot(this.value); });
    stations.forEach(function (s) {
      WS.list.push({ name: s.name, detail: (s.spot ? 'Spot: ' + s.spot + ' · ' : '') + s.source + ' ' + s.id,
        keys: [s.name, s.spot || '', s.id || ''].join(' '), kind: 'spot', badge: 'Wind spot', lat: s.lat, lon: s.lon,
        show: function () { showSpot(s.name); } });
    });
    buildPioupiou(map, body);
    buildNet(map, body);
  }

  // ---- Official station network: METAR airports (NOAA AWC) + WMO synoptic stations (OSCAR/Surface), Oliver 25.11.2026.
  // Data: /static/wind_stations/stationsnetz.json (py/stationsnetz.py), rows [lat, lon, name, icao, wmo, elev_m, type, wdqms],
  // type 1 = METAR, 2 = SYNOP, 3 = both.
  var NET_COL = { 1: '#1f78b4', 2: '#2e8b3a', 3: '#7a3db8', 4: '#e07b00' };
  // national networks with an open archive (type 4): name + where the data come from
  var NAT = {
    dwd: ['DWD, 10-min wind', 'https://opendata.dwd.de/climate_environment/CDC/observations_germany/climate/10_minutes/wind/'],
    dwd_synop: ['DWD, hourly wind (SYNOP)', 'https://opendata.dwd.de/climate_environment/CDC/observations_germany/climate/hourly/wind_synop/'],
    meteofrance: ['Météo-France', 'https://meteo.data.gouv.fr/'],
    knmi: ['KNMI (Netherlands)', 'https://dataplatform.knmi.nl/dataset/10-minute-in-situ-meteorological-observations-1-0'],
    dmi: ['DMI, 10-min', 'https://opendatadocs.dmi.govcloud.dk/'],
    coops: ['NOAA CO-OPS (tide gauge met sensor)', 'https://tidesandcurrents.noaa.gov/stationhome.html?id={id}'],
    geosphere: ['GeoSphere Austria, 10-min', 'https://data.hub.geosphere.at/dataset/klima-v2-10min'],
    meteoschweiz: ['MeteoSwiss SwissMetNet, 10-min', 'https://www.meteoswiss.admin.ch/services-and-publications/applications/measurement-values-and-measuring-networks.html'],
    smhi: ['SMHI, hourly', 'https://www.smhi.se/data/meteorologi/ladda-ner-meteorologiska-observationer'],
    rws: ['Rijkswaterstaat, 10-min', 'https://waterinfo.rws.nl/'],
    pioupiou: ['Pioupiou / OpenWindMap', 'https://www.openwindmap.org/PP{id}'],
    meteireann: ['Met Éireann, hourly', 'https://www.met.ie/climate/available-data/historical-data'],
    // 26.11.2026 (py/netze_kataloge.py)
    ndbc: ['NOAA NDBC (buoy / coastal station)', 'https://www.ndbc.noaa.gov/station_page.php?station={id}'],
    aemet: ['AEMET, hourly (Spain)', 'https://opendata.aemet.es/'],
    fmi: ['FMI, 10-min (Finland)', 'https://en.ilmatieteenlaitos.fi/open-data'],
    imgw: ['IMGW-PIB, 10-min (Poland)', 'https://danepubliczne.imgw.pl/'],
    lhmt: ['LHMT, hourly (Lithuania)', 'https://api.meteo.lt/'],
    ee: ['Keskkonnaagentuur, hourly (Estonia)', 'https://www.ilmateenistus.ee/ilm/ilmavaatlused/vaatlusandmed/'],
    meteocat: ['Meteocat XEMA, 30-min (Catalonia)', 'https://www.meteo.cat/observacions/xema/dades?codi={id}'],
    socib: ['SOCIB (Balearic Islands)', 'https://apps.socib.es/data-catalog/'],
    lombardia: ['ARPA Lombardia, 10-min', 'https://www.arpalombardia.it/temi-ambientali/meteo-e-clima/form-richiesta-dati/'],
    suedtirol: ['Landeswetterdienst Südtirol, 10-min', 'https://wetter.provinz.bz.it/'],
    frost: ['MET Norway (Frost)', 'https://seklima.met.no/'],
    ispra_rmn: ['ISPRA Rete Mareografica Nazionale (tide gauge with weather sensors)', 'https://www.mareografico.it/',
      'Data: ISPRA, please cite <a href="https://doi.org/10.83182/ispra-rmn" target="_blank" rel="noopener">doi:10.83182/ispra-rmn</a>'],
    puertos: ['Puertos del Estado (PORTUS: port weather station, tide gauge or buoy)', 'https://portus.puertos.es/'],
    lvgmc: ['LVĢMC, hourly (Latvia)', 'https://videscentrs.lvgmc.lv/karte'],
    ipma: ['IPMA Portugal, hourly', 'https://www.ipma.pt/en/otempo/obs.superficie/'],
    vedur: ['Icelandic Met Office (Veðurstofa)', 'https://en.vedur.is/weather/observations/areas/'],
    midas: ['UK Met Office (MIDAS Open archive, no live data)', 'https://data.ceda.ac.uk/badc/ukmo-midas-open/data/uk-mean-wind-obs/dataset-version-202607/{path}',
      'Archive updated yearly (Open Government Licence); current wind: nearby METAR/SYNOP stations'],
    dwd_strasse: ['DWD road weather station (roadside, wind usually reduced)', 'https://opendata.dwd.de/weather/weather_reports/road_weather_stations/'],
    dwd_poi: ['DWD, current hourly report', 'https://opendata.dwd.de/weather/weather_reports/poi/'],
    arpav: ['ARPA Veneto', 'https://www.arpa.veneto.it/dati-ambientali/dati-in-diretta/meteo-idro-nivo/variabili_meteo'],
    arpal: ['ARPAL Liguria (OMIRL)', 'https://omirl.regione.liguria.it/'],
    arpae: ['ARPAE Emilia-Romagna', 'https://dati.arpae.it/dataset/dati-dalle-stazioni-meteo-locali-della-rete-idrometeorologica-regionale'],
    venezia: ['Comune di Venezia, tide centre (CPSM)', 'https://www.comune.venezia.it/content/dati-dalle-stazioni-rilevamento'],
    snpa_mare: ['Rete Mareografica SNPA (regional agency)', '{agency}'],
    meteotrentino: ['Meteotrentino (all weather stations, wind not at every one)', 'https://www.meteotrentino.it/#!/content?menuItemDesktop=111']
  };
  // networks whose current reading the popup fetches on click, one station at a time (/api/station_live, py/station_live.py)
  var NAT_LIVE = { pioupiou: 1, ndbc: 1, coops: 1, fmi: 1, imgw: 1, lhmt: 1, ee: 1, meteocat: 1, lombardia: 1, suedtirol: 1,
    meteotrentino: 1, ispra_rmn: 1, venezia: 1, puertos: 1, dwd_poi: 1, dwd_strasse: 1, ipma: 1, vedur: 1, lvgmc: 1, meteofrance: 1, knmi: 1, arpav: 1, arpal: 1, arpae: 1, aemet: 1, dwd: 1, dmi: 1, geosphere: 1, meteoschweiz: 1, smhi: 1, frost: 1 };
  function loadNatLive(popupEl, s) {
    var el = popupEl && popupEl.querySelector('.nat-live');
    if (!el) return;
    fetch('/api/station_live?netz=' + encodeURIComponent(s[8]) + '&id=' + encodeURIComponent(s[9]))
      .then(function (r) { return r.json(); })
      .then(function (j) {
        if (j.fehler) { el.textContent = 'No current wind: ' + j.fehler; return; }
        var age = (Date.now() - Date.parse(j.zeit)) / 60000;
        var c = j.kn == null ? '#777' : ppColour(j.kn);
        el.innerHTML = '<span style="font-size:16px;font-weight:bold;color:' + (age > 180 ? '#888' : c) + ';">' +
          (j.kn == null ? '–' : j.kn.toFixed(0)) + ' kn</span>' +
          (j.boe_kn != null ? ' &nbsp;gusts ' + j.boe_kn.toFixed(0) + ' kn' : '') +
          (j.richtung != null ? ' · from ' + ppCompass(j.richtung) + ' (' + Math.round(j.richtung) + '°)' : '') +
          '<div style="color:#777;">' + ppAgeText(age) + ' (' + new Date(j.zeit).toLocaleString([], { hour: '2-digit', minute: '2-digit', day: '2-digit', month: '2-digit' }) + ')' +
          (j.hinweis ? ' · ' + esc(j.hinweis) : '') + '</div>';
      })
      .catch(function (e) { el.textContent = 'Current wind could not be loaded: ' + e.message; });
  }
  var POI = {};          // WMO numbers with a DWD current-report file (stationsnetz.json "poi")
  var WDQMS_TXT = { o: 'reports arrive regularly', p: 'reports arrive partly', n: 'no reports received', u: 'reception not assessed by WMO' };
  function netPopup(s) {
    if (s[6] === 4) {
      var nn = NAT[s[8]] || [s[8], ''];
      var url = nn[1] === '{agency}' ? (s[9].indexOf('fvg-') === 0 ? 'https://www.meteo.fvg.it/monitor-mare.php?ln' :
        s[9].indexOf('arpae-') === 0 ? 'https://www.arpae.it/it/temi-ambientali/mare/dati-e-indicatori/rete-di-monitoraggio-meteo-marina' :
        'https://www.snpambiente.it/dati/clima-e-meteo/') : nn[1].replace('{path}', s[9].split('/').map(encodeURIComponent).join('/'))
        .replace('{id}', encodeURIComponent(s[9]));
      return '<div style="font-family:sans-serif;font-size:12.5px;min-width:220px;max-width:340px;">' +
        '<div style="font-weight:bold;font-size:14px;">' + esc(s[2]) + '</div>' +
        '<div style="color:#555;margin-bottom:3px;">' + esc(nn[0]) + (s[5] != null ? ' · ' + esc(s[5]) + ' m' : '') + '</div>' +
        '<div>ID <b>' + esc(s[9]) + '</b>' + (url ? ' · <a href="' + esc(url) + '" target="_blank" rel="noopener">data source</a>' : '') + '</div>' +
        '<div style="color:#777;font-size:11.5px;margin-top:2px;">' + s[0].toFixed(4) + ', ' + s[1].toFixed(4) + '</div>' +
        (NAT_LIVE[s[8]] ? '<div class="nat-live" style="margin-top:6px;color:#777;font-size:11.5px;">Loading current wind…</div>' : '') +
        (nn[2] ? '<div style="color:#777;font-size:11px;margin-top:3px;">' + nn[2] + '</div>' : '') +
        '<div style="color:#777;font-size:11px;margin-top:3px;">Open wind measurements of a national or regional network.</div></div>';
    }
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
      (s[3] ? '<div class="net-metar" style="margin-top:6px;color:#777;font-size:11.5px;">Loading METAR…</div>' :
        POI[s[4]] ? '<div class="nat-live" style="margin-top:6px;color:#777;font-size:11.5px;">Loading current wind (DWD)…</div>' : '') + '</div>';
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
        // The canvas must not swallow clicks (it would block every tide/current marker below it): the pane ignores
        // pointer events, clicks and hover near a dot are resolved by hand in pick() below.
        if (!map.getPane('netPane')) {
          map.createPane('netPane');
          map.getPane('netPane').style.zIndex = 620;
          map.getPane('netPane').style.pointerEvents = 'none';
        }
        (d.poi || []).forEach(function (w) { POI[w] = 1; });
        var renderer = L.canvas({ padding: 0.3, pane: 'netPane' });
        var layers = { metar: L.layerGroup(), synop: L.layerGroup(), both: L.layerGroup(), nat: L.layerGroup() };
        var n = { 1: 0, 2: 0, 3: 0, 4: 0 };
        d.stationen.forEach(function (s) {
          n[s[6]]++;
          var m = L.circleMarker([s[0], s[1]], { renderer: renderer, pane: 'netPane', interactive: false, radius: s[6] === 1 || s[6] === 3 ? 6 : 5,
            weight: 1.5, color: '#fff', fillColor: s[6] === 2 && s[7] === 'n' ? '#9a9a9a' : NET_COL[s[6]], fillOpacity: 0.95 });
          m.addTo(s[6] === 1 ? layers.metar : s[6] === 2 ? layers.synop : s[6] === 4 ? layers.nat : layers.both);
        });
        // nearest visible station within 8 px of a map point (clicks on tide/current markers never reach the map)
        var shown = function (s) { return map.hasLayer(s[6] === 1 ? layers.metar : s[6] === 2 ? layers.synop : s[6] === 4 ? layers.nat : layers.both); };
        var pick = function (pt) {
          var best = null, bd = 64, b = map.getBounds().pad(0.05);
          for (var i = 0; i < d.stationen.length; i++) {
            var s = d.stationen[i];
            if (!b.contains([s[0], s[1]]) || !shown(s)) continue;
            var q = map.latLngToContainerPoint([s[0], s[1]]), dd = (q.x - pt.x) * (q.x - pt.x) + (q.y - pt.y) * (q.y - pt.y);
            if (dd < bd) { bd = dd; best = s; }
          }
          return best;
        };
        var anyShown = function () { return Object.keys(layers).some(function (k) { return map.hasLayer(layers[k]); }); };
        map.on('click', function (e) {
          if (!anyShown()) return;
          var s = pick(e.containerPoint);
          if (!s) return;
          var p = L.popup({ maxWidth: 380, offset: [0, -4] }).setLatLng([s[0], s[1]]).setContent(netPopup(s)).openOn(map);
          if (s[3]) loadMetar(p.getElement(), s[3]);
          if (s[6] === 4) loadNatLive(p.getElement(), s);
          else if (!s[3] && POI[s[4]]) loadNatLive(p.getElement(), [0, 0, '', '', '', 0, 4, '', 'dwd_poi', s[4]]);
        });
        var tip = L.tooltip({ direction: 'top', offset: [0, -6] }), tipFor = null, last = 0;
        map.on('mousemove', function (e) {
          var now = Date.now();
          if (now - last < 80) return;
          last = now;
          var s = anyShown() ? pick(e.containerPoint) : null;
          if (s === tipFor) return;
          tipFor = s;
          map.getContainer().style.cursor = s ? 'pointer' : '';
          if (!s) { map.closeTooltip(tip); return; }
          tip.setLatLng([s[0], s[1]]).setContent(esc(s[2]) + (s[3] ? ' (' + esc(s[3]) + ')' : s[4] ? ' (' + esc(s[4]) + ')' :
            s[6] === 4 ? ' (' + esc((NAT[s[8]] || [s[8]])[0].split(',')[0]) + ')' : ''));
          map.openTooltip(tip);
        });
        var dot = function (c) { return '<span style="display:inline-block;width:9px;height:9px;border-radius:50%;background:' + c + ';margin:0 5px 0 2px;"></span>'; };
        box.innerHTML =
          '<div style="font-weight:bold;font-size:12.5px;margin-bottom:2px;">Official stations</div>' +
          '<label style="display:flex;align-items:center;cursor:pointer;min-height:26px;font-size:12.5px;">' +
            '<input type="checkbox" id="net-metar" style="margin-right:6px;width:16px;height:16px;">' + dot(NET_COL[1]) + 'Airports with METAR (' + (n[1] + n[3]) + ')</label>' +
          '<label style="display:flex;align-items:center;cursor:pointer;min-height:26px;font-size:12.5px;">' +
            '<input type="checkbox" id="net-synop" style="margin-right:6px;width:16px;height:16px;">' + dot(NET_COL[2]) + 'WMO synoptic stations (' + (n[2] + n[3]) + ')</label>' +
          '<label style="display:flex;align-items:center;cursor:pointer;min-height:26px;font-size:12.5px;">' +
            '<input type="checkbox" id="net-nat" style="margin-right:6px;width:16px;height:16px;">' + dot(NET_COL[4]) + 'National & regional networks, open data (' + n[4] + ')</label>' +
          '<div style="font-size:11px;color:#666;line-height:1.5;">' + dot(NET_COL[3]) + 'both (' + n[3] + ').' + dot('#9a9a9a') + 'WMO receives no reports. ' +
            'Sources: NOAA Aviation Weather Center, WMO OSCAR/Surface (' + esc(d.stand) + '); national/regional: ' +
            esc(Object.keys(NAT).filter(function (k) { return d.stationen.some(function (s) { return s[8] === k; }); })
              .map(function (k) { return NAT[k][0].split(',')[0].split(' (')[0]; })
              .filter(function (v, i, a) { return a.indexOf(v) === i; }).join(', ')) + '.</div>';
        WS_COUNT.net = d.stationen.length;
        showCount();
        var cbM = document.getElementById('net-metar'), cbS = document.getElementById('net-synop'), cbN = document.getElementById('net-nat');
        var get = function (k) { try { return localStorage.getItem(k) === '1'; } catch (e) { return false; } };
        cbM.checked = get('netMetarOn'); cbS.checked = get('netSynopOn'); cbN.checked = get('netNatOn');
        var update = function () {
          var show = { metar: cbM.checked, synop: cbS.checked, both: cbM.checked || cbS.checked, nat: cbN.checked };
          Object.keys(layers).forEach(function (k) {
            if (show[k] && !map.hasLayer(layers[k])) layers[k].addTo(map);
            if (!show[k] && map.hasLayer(layers[k])) map.removeLayer(layers[k]);
          });
          try { localStorage.setItem('netMetarOn', cbM.checked ? '1' : '0'); localStorage.setItem('netSynopOn', cbS.checked ? '1' : '0'); localStorage.setItem('netNatOn', cbN.checked ? '1' : '0'); } catch (e) { /* ignore */ }
        };
        cbM.addEventListener('change', update); cbS.addEventListener('change', update); cbN.addEventListener('change', update);
        update();
        var openNet = function (s) {
          var cbx = s[6] === 1 || s[6] === 3 ? cbM : s[6] === 2 ? cbS : cbN;
          if (!cbx.checked) { cbx.checked = true; update(); }
          map.closePopup();
          map.flyTo([s[0], s[1]], Math.max(map.getZoom(), 11), { duration: 1.2 });
          map.once('moveend', function () {
            var p = L.popup({ maxWidth: 380, offset: [0, -4] }).setLatLng([s[0], s[1]]).setContent(netPopup(s)).openOn(map);
            if (s[3]) loadMetar(p.getElement(), s[3]);
          if (s[6] === 4) loadNatLive(p.getElement(), s);
          else if (!s[3] && POI[s[4]]) loadNatLive(p.getElement(), [0, 0, '', '', '', 0, 4, '', 'dwd_poi', s[4]]);
          });
        };
        d.stationen.forEach(function (s) {
          var badge = s[6] === 1 ? 'METAR' : s[6] === 2 ? 'SYNOP' : s[6] === 3 ? 'METAR+SYNOP' :
            (NAT[s[8]] || [s[8]])[0].split(',')[0];
          var ids = s[6] === 4 ? s[9] : [s[3], s[4]].filter(Boolean).join(' · ');
          WS.list.push({ name: s[2], detail: ids ? (s[6] === 4 ? 'ID ' : '') + ids : '', keys: [s[2], s[3], s[4], s[9] || ''].join(' '),
            kind: s[6] === 4 ? 'nat' : 'net', badge: badge, lat: s[0], lon: s[1], show: function () { openNet(s); } });
        });
      })
      .catch(function (e) {
        box.innerHTML = '<span style="color:#a00;font-size:12px;">Official stations could not be loaded.</span>';
        console.error('station network:', e);
      });
  }

  // ---- Pioupiou / OpenWindMap live sensors (Oliver 26.11.2026). /api/pioupiou_live (app.py, km/h -> kn, 2 min cache),
  // rows [id, name, lat, lon, time_utc, heading_from_deg, avg_kn, min_kn, max_kn, on]; popup loads 24 h via /api/pioupiou_history.
  var PP_SCALE = [[5, '#8fbcd9'], [10, '#3fa34d'], [15, '#d9c21a'], [20, '#ee7d14'], [25, '#d7301f'], [1e9, '#8e2a9c']];
  var PP_STALE_MIN = 60;      // older measurements: grey dot; older than a day: not shown
  function ppColour(v) {
    for (var i = 0; i < PP_SCALE.length; i++) if (v < PP_SCALE[i][0]) return PP_SCALE[i][1];
    return PP_SCALE[PP_SCALE.length - 1][1];
  }
  function ppAgeMin(s) { return s[4] ? (Date.now() - Date.parse(s[4])) / 60000 : Infinity; }
  function ppCompass(d) {
    return ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE', 'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW'][Math.round(d / 22.5) % 16];
  }
  function ppAgeText(min) {
    if (!isFinite(min)) return 'no measurement';
    if (min < 1) return 'just now';
    if (min < 90) return Math.round(min) + ' min ago';
    if (min < 48 * 60) return Math.round(min / 60) + ' h ago';
    return Math.round(min / 1440) + ' days ago';
  }
  function ppIcon(s) {
    var age = ppAgeMin(s);
    if (age > PP_STALE_MIN || s[6] == null || s[5] == null) {
      return L.divIcon({ className: '', iconSize: [10, 10], iconAnchor: [5, 5],
        html: '<div style="width:8px;height:8px;border-radius:50%;background:#a5a5a5;border:1px solid #fff;"></div>' });
    }
    // heading = direction the wind comes FROM; the arrow points where it blows to
    var c = ppColour(s[6]), rot = (s[5] + 180) % 360;
    return L.divIcon({ className: '', iconSize: [26, 26], iconAnchor: [13, 13],
      html: '<svg width="26" height="26" viewBox="-13 -13 26 26" style="overflow:visible;display:block;">' +
        '<g transform="rotate(' + rot + ')"><path d="M0,-11 L6,3 L1.6,1.2 L1.6,10 L-1.6,10 L-1.6,1.2 L-6,3 Z" fill="' + c +
        '" stroke="#222" stroke-width="1.1" stroke-linejoin="round"/></g></svg>' });
  }
  function ppPopup(s) {
    var age = ppAgeMin(s), stale = age > PP_STALE_MIN;
    var wind = s[6] == null ? 'no wind reading' :
      '<span style="font-size:18px;font-weight:bold;color:' + (stale ? '#888' : ppColour(s[6])) + ';">' + s[6].toFixed(0) + ' kn</span>' +
      ' &nbsp;gusts ' + (s[8] != null ? s[8].toFixed(0) : '–') + ', min ' + (s[7] != null ? s[7].toFixed(0) : '–') + ' kn' +
      (s[5] != null ? '<br>from ' + ppCompass(s[5]) + ' (' + Math.round(s[5]) + '°)' : '');
    return '<div style="font-family:sans-serif;font-size:12.5px;min-width:250px;max-width:340px;">' +
      '<div style="font-weight:bold;font-size:14px;">' + esc(s[1]) + '</div>' +
      '<div style="color:#555;margin-bottom:4px;">Pioupiou ' + esc(s[0]) + ' · ' + ppAgeText(age) + (s[9] ? '' : ' · sensor off') + '</div>' +
      '<div>' + wind + '</div>' +
      '<div class="pp-hist" style="margin-top:6px;color:#777;font-size:11.5px;">Loading last 24 h…</div>' +
      '<div style="margin-top:4px;font-size:11px;color:#777;"><a href="https://www.openwindmap.org/PP' + encodeURIComponent(s[0]) +
        '" target="_blank" rel="noopener">OpenWindMap</a> · © contributors of the OpenWindMap wind network. ' +
        'Low-cost sensors, often read 2–5 kn low.</div></div>';
  }
  function ppHistory(popupEl, id) {
    var el = popupEl && popupEl.querySelector('.pp-hist');
    if (!el) return;
    fetch('/api/pioupiou_history?id=' + encodeURIComponent(id))
      .then(function (r) { return r.json().then(function (j) { if (!r.ok) throw new Error(j.error || r.status); return j; }); })
      .then(function (j) {
        var d = (j.daten || []).filter(function (z) { return z[2] != null; });
        if (d.length < 2) { el.textContent = 'No measurements in the last 24 h.'; return; }
        var W = 300, H = 90, L0 = 22, B = 14, t1 = Date.now(), t0 = t1 - 864e5;
        var top = Math.max(10, Math.ceil(Math.max.apply(null, d.map(function (z) { return z[3] || z[2]; })) / 5) * 5);
        var x = function (t) { return L0 + (Date.parse(t) - t0) / 864e5 * (W - L0 - 2); };
        var y = function (v) { return H - B - v / top * (H - B - 4); };
        var band = d.map(function (z) { return x(z[0]).toFixed(1) + ',' + y(z[3] != null ? z[3] : z[2]).toFixed(1); }).concat(
          d.slice().reverse().map(function (z) { return x(z[0]).toFixed(1) + ',' + y(z[1] != null ? z[1] : z[2]).toFixed(1); }));
        var line = d.map(function (z) { return x(z[0]).toFixed(1) + ',' + y(z[2]).toFixed(1); }).join(' ');
        var grid = '';
        for (var v = 0; v <= top; v += top > 30 ? 10 : 5) {
          grid += '<line x1="' + L0 + '" x2="' + W + '" y1="' + y(v) + '" y2="' + y(v) + '" stroke="#e4e4e4"/>' +
            '<text x="' + (L0 - 3) + '" y="' + (y(v) + 3) + '" text-anchor="end" font-size="9" fill="#888">' + v + '</text>';
        }
        // local-time hour marks every 6 h
        var hrs = '', d0 = new Date(t0); d0.setMinutes(0, 0, 0);
        for (var t = d0.getTime() + 3600e3; t < t1; t += 3600e3) {
          var h = new Date(t).getHours();
          if (h % 6) continue;
          var xx = L0 + (t - t0) / 864e5 * (W - L0 - 2);
          hrs += '<line x1="' + xx + '" x2="' + xx + '" y1="4" y2="' + (H - B) + '" stroke="#eee"/>' +
            '<text x="' + xx + '" y="' + (H - 3) + '" text-anchor="middle" font-size="9" fill="#888">' + (h < 10 ? '0' : '') + h + ':00</text>';
        }
        el.innerHTML = '<div style="color:#555;margin-bottom:2px;">Last 24 h, kn (line = mean, band = min–gust, local time)</div>' +
          '<svg width="' + W + '" height="' + H + '" style="display:block;">' + grid + hrs +
          '<polygon points="' + band.join(' ') + '" fill="#3f8fd2" fill-opacity="0.18"/>' +
          '<polyline points="' + line + '" fill="none" stroke="#1f5fa0" stroke-width="1.5"/></svg>';
      })
      .catch(function (e) { el.textContent = 'History could not be loaded: ' + e.message; });
  }
  function buildPioupiou(map, body) {
    var box = document.createElement('div');
    box.style.cssText = 'margin-top:8px;padding-top:6px;border-top:1px solid #ccc;max-width:290px;';
    var legend = PP_SCALE.map(function (c, i) {
      var lo = i ? PP_SCALE[i - 1][0] : 0;
      return '<span style="display:inline-block;width:10px;height:10px;background:' + c[1] + ';margin:0 2px 0 4px;vertical-align:-1px;"></span>' +
        (c[0] > 1e8 ? lo + '+' : lo + '–' + c[0]);
    }).join('');
    box.innerHTML =
      '<div style="font-weight:bold;font-size:12.5px;margin-bottom:2px;">Live wind sensors</div>' +
      '<label style="display:flex;align-items:center;cursor:pointer;min-height:26px;font-size:12.5px;">' +
        '<input type="checkbox" id="pp-toggle" style="margin-right:6px;width:16px;height:16px;">Pioupiou / OpenWindMap <span id="pp-count" style="color:#777;margin-left:4px;"></span></label>' +
      '<div style="font-size:11px;color:#666;line-height:1.5;">Arrow = where the wind blows, colour = mean wind (kn):<br>' + legend +
        '<br><span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:#a5a5a5;margin:0 3px 0 4px;"></span>no reading in the last hour. ' +
        'Updates every 2 min. Wind data © contributors of the ' +
        '<a href="https://openwindmap.org" target="_blank" rel="noopener">OpenWindMap</a> wind network.</div>';
    body.appendChild(box);
    if (!map.getPane('ppPane')) { map.createPane('ppPane'); map.getPane('ppPane').style.zIndex = 625; }
    var layer = L.layerGroup(), markers = {}, timer = null;
    var cb = box.querySelector('#pp-toggle'), count = box.querySelector('#pp-count');
    var load = function () {
      fetch('/api/pioupiou_live')
        .then(function (r) { return r.json().then(function (j) { if (!r.ok) throw new Error(j.error || r.status); return j; }); })
        .then(function (d) {
          var live = 0, seen = {};
          d.stationen.forEach(function (s) {
            if (ppAgeMin(s) > 1440) return;
            if (ppAgeMin(s) <= PP_STALE_MIN) live++;
            seen[s[0]] = 1;
            var m = markers[s[0]];
            if (!m) {
              m = markers[s[0]] = L.marker([s[2], s[3]], { pane: 'ppPane', icon: ppIcon(s), riseOnHover: true });
              m.bindPopup('', { maxWidth: 360 });
              m.on('popupopen', function (e) { e.popup.setContent(ppPopup(m.pp)); ppHistory(e.popup.getElement(), m.pp[0]); });
              m.addTo(layer);
            } else {
              m.setLatLng([s[2], s[3]]).setIcon(ppIcon(s));
            }
            m.pp = s;
            m.unbindTooltip().bindTooltip(esc(s[1]) + (s[6] != null && ppAgeMin(s) <= PP_STALE_MIN ? ' · ' + s[6].toFixed(0) + ' kn' : ''), { direction: 'top', offset: [0, -10] });
          });
          Object.keys(markers).forEach(function (k) { if (!seen[k]) { layer.removeLayer(markers[k]); delete markers[k]; } });
          count.textContent = '(' + live + ' live)';
        })
        .catch(function (e) { count.textContent = '(not available)'; console.error('pioupiou:', e); });
    };
    var set = function (on) {
      if (on) {
        layer.addTo(map); load();
        if (!timer) timer = setInterval(function () { if (!document.hidden) load(); }, 120000);
      } else {
        map.removeLayer(layer);
        if (timer) { clearInterval(timer); timer = null; }
      }
      try { localStorage.setItem('ppLiveOn', on ? '1' : '0'); } catch (e) { /* ignore */ }
    };
    try { cb.checked = localStorage.getItem('ppLiveOn') === '1'; } catch (e) { cb.checked = false; }
    cb.addEventListener('change', function () { set(this.checked); });
    if (cb.checked) set(true);
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
