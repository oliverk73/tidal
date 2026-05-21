"""Build marker data for the Leaflet map.

Output:
  static/js/leaflet_markers_data.json  — columnar marker data (groups + stations)
  static/js/leaflet_markers.js         — small loader (fetch JSON, build markers
                                          chunked via requestIdleCallback)

The big-payload split is a SEO/perf win: the browser parses JSON ~10x faster
than equivalent JS code, and the loader spreads marker creation across idle
slots so the main thread stays responsive.
"""

import json
import re
import os
import glob
import unicodedata
from collections import OrderedDict, Counter

TCD_DIR = "/usr/share/xtide"
HARMONICS_DIRS = [
    "harmonics/classic",
    "harmonics/ihm",
    "harmonics/utide",
    "harmonics/ticon",
]


TRANSLITERATION = {
    'ä': 'ae', 'ö': 'oe', 'ü': 'ue', 'ß': 'ss',
    'Ä': 'Ae', 'Ö': 'Oe', 'Ü': 'Ue',
    'ø': 'oe', 'Ø': 'Oe', 'å': 'aa', 'Å': 'Aa', 'æ': 'ae', 'Æ': 'Ae',
    'ł': 'l', 'Ł': 'L',
    'ð': 'd', 'Ð': 'D', 'þ': 'th', 'Þ': 'Th',
}


def normalize_filename(name: str) -> str:
    for char, repl in TRANSLITERATION.items():
        name = name.replace(char, repl)
    name = unicodedata.normalize('NFKD', name)
    name = name.encode('ascii', 'ignore').decode('ascii')
    name = re.sub(r"['\\\\/]", "", name)
    name = re.sub(r"[\s,]+", "_", name)
    return name.lower()


def to_slug(name: str) -> str:
    """Convert station name to SEO-friendly slug: 'Douala, Cameroon' → 'douala-cameroon'."""
    slug = name
    for char, repl in TRANSLITERATION.items():
        slug = slug.replace(char, repl)
    slug = unicodedata.normalize('NFKD', slug)
    slug = slug.encode('ascii', 'ignore').decode('ascii')
    slug = re.sub(r"['\\\\/]", "", slug)
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", slug)
    slug = slug.strip("-").lower()
    return slug


def get_stations_from_txt(txt_path):
    """Parse station list directly from a harmonics TXT file.
    Returns list of (name, lat, lon, is_current) tuples."""
    stations = []
    with open(txt_path, 'r', encoding='iso-8859-1') as f:
        lines = f.readlines()

    lat = lon = None
    units = None
    for line in lines:
        line = line.rstrip()
        if line.startswith('# !latitude:'):
            lat = float(line.split(':', 1)[1].strip())
        elif line.startswith('# !longitude:'):
            lon = float(line.split(':', 1)[1].strip())
        elif line.startswith('# !units:'):
            units = line.split(':', 1)[1].strip().lower()
        elif not line.startswith('#') and line.strip() and lat is not None and lon is not None:
            is_current = (units == 'knots' or units == 'knots^2')
            stations.append((line.strip(), lat, lon, is_current))
            lat = lon = None
            units = None
    return stations


def find_txt_for_tcd(tcd_basename):
    txt_name = tcd_basename.replace('.tcd', '.txt')
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for hdir in HARMONICS_DIRS:
        txt_path = os.path.join(project_root, hdir, txt_name)
        if os.path.exists(txt_path):
            return txt_path
    return None


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SUPERSEDED_TCDS = {
    'harmonics_utide_currents.tcd',  # split into current_observations + current_tables
}

tcd_files = sorted(glob.glob(os.path.join(TCD_DIR, "*.tcd")))
print(f"Gefunden: {len(tcd_files)} TCD-Dateien in {TCD_DIR}")

all_stations = []
for tcd_file in tcd_files:
    basename = os.path.basename(tcd_file)
    if basename in SUPERSEDED_TCDS:
        continue
    txt_path = find_txt_for_tcd(basename)
    if not txt_path:
        print(f"  {basename}: ÜBERSPRUNGEN (keine TXT-Datei gefunden)")
        continue
    stations = get_stations_from_txt(txt_path)
    for name, lat, lon, is_current in stations:
        all_stations.append((name, lat, lon, basename, is_current))
    print(f"  {basename}: {len(stations)} Stationen")

# Names appearing in multiple TCD files need source suffix in URLs
name_counter = Counter(name for name, _, _, _, _ in all_stations)
duplicate_names = {name for name, count in name_counter.items() if count > 1}

slug_to_names = {}
for name, _, _, _, _ in all_stations:
    slug = to_slug(name)
    slug_to_names.setdefault(slug, set()).add(name)
duplicate_slugs = {slug for slug, names in slug_to_names.items() if len(names) > 1}
for slug in duplicate_slugs:
    duplicate_names.update(slug_to_names[slug])
slug_counter = Counter(to_slug(name) for name, _, _, _, _ in all_stations)
for name, _, _, _, _ in all_stations:
    if slug_counter[to_slug(name)] > 1:
        duplicate_names.add(name)

print(f"Gesamt: {len(all_stations)} Stationen ({len(duplicate_names)} Namen mehrfach/Slug-Kollisionen)")

SOURCE_GROUPS = OrderedDict([
    ('DWF 2025',        {'color': '#2196F3', 'files': ['harmonics-dwf-20251228-free.tcd']}),
    ('DWF 2010',        {'color': '#607D8B', 'files': ['harmonics-dwf-20100529-nonfree_mod.tcd']}),
    ('DWF 2007',        {'color': '#795548', 'files': ['harmonics-dwf-20070318_mod.tcd']}),
    ('Classic 2004',    {'color': '#4CAF50', 'files': ['harmonics-2004-06-14_mod.tcd']}),
    ('Classic 1997',    {'color': '#9C27B0', 'files': ['harmonics-1997-05-25_mod.tcd']}),
    ('TICON4',          {'color': '#FF9800', 'files': ['harmonics_ticon4_worldwide.tcd']}),
    ('Lavergne',        {'color': '#E91E63', 'files': ['harmonics-pierre-lavergne-v10_mod.tcd',
                                                        'harmonics-pierre-lavergne-v9-europe_mod.tcd']}),
    ('UTide TC',        {'color': '#F44336', 'files': [
                            'harmonics_utide_tidetables.tcd',
                            'harmonics_utide_current_tables.tcd',
                            'harmonics_utide_australia_bom.tcd',
                            'harmonics_utide_brazil_dhn.tcd',
                            'harmonics_utide_canada_bc.tcd',
                            'harmonics_utide_canada_nb.tcd',
                            'harmonics_utide_canada_nl.tcd',
                            'harmonics_utide_canada_mb.tcd',
                            'harmonics_utide_canada_nt.tcd',
                            'harmonics_utide_canada_nu.tcd',
                            'harmonics_utide_canada_on.tcd',
                            'harmonics_utide_canada_qc.tcd',
                            'harmonics_utide_canada_yt.tcd',
                            'harmonics_utide_pei.tcd',
                            'harmonics_utide_taiwan_cwa.tcd',
                            'harmonics_utide_hongkong_hko.tcd',
                            'harmonics_utide_spain_ihm.tcd',
                            'harmonics_utide_canada_ns.tcd',
                            'harmonics_utide_korea.tcd',
                            'harmonics_utide_philippines_namria.tcd',
                            'harmonics_utide_uk_tidetimes.tcd',
                            'harmonics_utide_thailand.tcd',
                            'harmonics_utide_canada_currents_predicted.tcd',
                            ]}),
    ('SHOM',            {'color': '#3F51B5', 'files': ['harmonics_utide_shom.tcd']}),
    ('UTide SL',        {'color': '#E57373', 'files': [
                            'harmonics_utide_observations.tcd',
                            'harmonics_utide_current_observations.tcd',
                            'harmonics_utide_germany_z0corrected.tcd',
                            'harmonics_utide_germany_currents.tcd',
                            'harmonics_utide_netherlands.tcd',
                            'harmonics_utide_netherlands_currents.tcd',
                            'harmonics_utide_france.tcd',
                            'harmonics_utide_belgium.tcd',
                            'harmonics_utide_australia_imos_currents.tcd',
                            'harmonics_utide_south_africa_saeon_currents.tcd',
                            'harmonics_utide_belgium_currents.tcd',
                            'harmonics_utide_denmark_currents.tcd',
                            'harmonics_utide_france_atlantic_currents.tcd',
                            'harmonics_utide_france_channel_currents.tcd',
                            'harmonics_utide_france_med_currents.tcd',
                            'harmonics_utide_ireland_currents.tcd',
                            'harmonics_utide_norway_currents.tcd',
                            'harmonics_utide_portugal_currents.tcd',
                            'harmonics_utide_portugal_offshore_currents.tcd',
                            'harmonics_utide_spain_atlantic_currents.tcd',
                            'harmonics_utide_spain_med_currents.tcd',
                            'harmonics_utide_uk_currents.tcd',
                            'harmonics_utide_canada_currents_measured.tcd',
                            'harmonics_utide_canada_all.tcd',
                            'harmonics_utide_uk_bodc.tcd',
                            'harmonics_utide_uk_cmems.tcd',
                            'harmonics_utide_ireland.tcd',
                            'harmonics_utide_uk_ireland.tcd',
                            'harmonics_utide_denmark.tcd',
                            'harmonics_utide_australia.tcd',
                            'harmonics_utide_australia_qld.tcd',
                            'harmonics_utide_australia_uhslc.tcd',
                            'harmonics_utide_portugal.tcd',
                            'harmonics_utide_norway.tcd',
                            'harmonics_utide_india.tcd',
                            'harmonics_utide_chile.tcd',
                            'harmonics_utide_mexico.tcd',
                            'harmonics_utide_new_zealand.tcd',
                            'harmonics_utide_south_africa.tcd',
                            'harmonics_utide_brazil.tcd',
                            'harmonics_utide_argentina.tcd',
                            'harmonics_utide_colombia.tcd',
                            'harmonics_utide_peru.tcd',
                            'harmonics_utide_jordan.tcd',
                            'harmonics_utide_panama.tcd',
                            'harmonics_utide_nicaragua.tcd',
                            'harmonics_utide_elsalvador.tcd',
                            'harmonics_utide_caribbean.tcd',
                            'harmonics_utide_caribbean_uhslc.tcd',
                            'harmonics_utide_bd_mm_mg_mz.tcd',
                            'harmonics_utide_tz_ke.tcd',
                            'harmonics_utide_png.tcd',
                            'harmonics_utide_pakistan.tcd',
                            'harmonics_utide_russia.tcd',
                            'harmonics_utide_egypt.tcd',
                            'harmonics_utide_abc.tcd',
                            'harmonics_utide_antigua.tcd',
                            'harmonics_utide_barbados.tcd',
                            'harmonics_utide_bvi.tcd',
                            'harmonics_utide_cayman.tcd',
                            'harmonics_utide_montserrat.tcd',
                            'harmonics_utide_stkitts.tcd',
                            'harmonics_utide_stvincent.tcd',
                            'harmonics_utide_indonesia.tcd',
                            'harmonics_utide_philippines.tcd',
                            'harmonics_utide_vietnam.tcd',
                            'harmonics_utide_sudan.tcd',
                            'harmonics_utide_oman.tcd',
                            'harmonics_utide_iran.tcd',
                            'harmonics_utide_japan.tcd',
                            'harmonics_utide_cameroon_angola.tcd',
                            'harmonics_utide_trinidad_tobago.tcd',
                            'harmonics_utide_venezuela.tcd',
                            'harmonics_utide_westafrica.tcd',
                            ]}),
    ('Puertos',         {'color': '#00BCD4', 'files': ['harmonics_puertos_spain.tcd']}),
])

# Group order: predefined + Sonstige fallback
GROUP_NAMES = list(SOURCE_GROUPS.keys()) + ['Sonstige']
GROUP_COLOR = {g: SOURCE_GROUPS[g]['color'] for g in SOURCE_GROUPS}
GROUP_COLOR['Sonstige'] = '#999999'
GROUP_INDEX = {g: i for i, g in enumerate(GROUP_NAMES)}


def get_group_for_source(source_file):
    for group_name, info in SOURCE_GROUPS.items():
        if source_file in info['files']:
            return group_name
    if source_file.startswith('harmonics_utide_'):
        return 'UTide SL'
    return 'Sonstige'


COUNTRY_BY_SOURCE = {
    'harmonics-dwf-20251228-free.tcd': 'USA',
}


def display_name_for(name, source_file):
    """Append country suffix for sources that lack it."""
    country = COUNTRY_BY_SOURCE.get(source_file)
    if country and not name.endswith(f", {country}"):
        return f"{name}, {country}"
    return name


# Build columnar JSON payload
station_rows = []
for name, lat, lon, source_file, is_current in all_stations:
    display_name_raw = display_name_for(name, source_file)
    slug = to_slug(display_name_raw)
    needs_source = name in duplicate_names
    group_name = get_group_for_source(source_file)
    group_idx = GROUP_INDEX[group_name]
    # Round coords to ~5m precision (5 decimals) — saves bytes vs full precision
    station_rows.append([
        display_name_raw,
        round(lat, 5),
        round(lon, 5),
        source_file,
        group_idx,
        1 if is_current else 0,
        slug,
        1 if needs_source else 0,
        name,  # original name (key for stationCoords/stationSources globals)
    ])

payload = {
    "version": 1,
    "groups": [{"name": g, "color": GROUP_COLOR[g]} for g in GROUP_NAMES],
    "stations": station_rows,
}

json_path = os.path.join(PROJECT_ROOT, "static", "js", "leaflet_markers_data.json")
os.makedirs(os.path.dirname(json_path), exist_ok=True)
with open(json_path, "w", encoding="utf-8") as f:
    json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))

# Loader JS (small, static — does the heavy lifting client-side, chunked)
LOADER_JS = r"""// Auto-generated by py/build_tide_station_markers.py — do not edit by hand.
// Loads marker data from /static/js/leaflet_markers_data.json and builds
// markers in idle-time batches so the main thread stays responsive.
(function () {
  var DATA_URL = '/static/js/leaflet_markers_data.json';
  var BATCH_SIZE = 500;

  function start() {
    fetch(DATA_URL)
      .then(function (r) { return r.json(); })
      .then(buildAll)
      .catch(function (err) { console.error('Marker load failed:', err); });
  }

  function tideSvg(color) {
    return '<svg width="18" height="18" viewBox="0 0 18 18" xmlns="http://www.w3.org/2000/svg">' +
      '<line x1="9" y1="2" x2="9" y2="16" stroke="' + color + '" stroke-width="3" stroke-linecap="round"/>' +
      '<polyline points="5,5 9,2 13,5" fill="none" stroke="' + color + '" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>' +
      '<polyline points="5,13 9,16 13,13" fill="none" stroke="' + color + '" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>' +
      '</svg>';
  }
  function currentSvg(color) {
    return '<svg width="18" height="18" viewBox="0 0 18 18" xmlns="http://www.w3.org/2000/svg">' +
      '<line x1="2" y1="9" x2="16" y2="9" stroke="' + color + '" stroke-width="3" stroke-linecap="round"/>' +
      '<polyline points="5,5 2,9 5,13" fill="none" stroke="' + color + '" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>' +
      '<polyline points="13,5 16,9 13,13" fill="none" stroke="' + color + '" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>' +
      '</svg>';
  }
  function makeIcon(html) {
    return L.divIcon({ html: html, className: '', iconSize: [18, 18], iconAnchor: [9, 9], popupAnchor: [0, -9] });
  }

  function popupContent(layer) {
    var d = layer.options.sd;
    return '<b>' + d.n + '</b><br>' +
      '<a href="' + d.u + '">🌊 Show prediction</a><br>' +
      '<a href="#" onclick="enableDrag(this); return false;">📍 Correct position</a> ' +
      '<a href="#" onclick="setCoordinatesManual(this); return false;">📍 Enter coordinates</a><br>' +
      '<a href="#" onclick="renameStation(this); return false;">✏️ Rename</a> ' +
      '<a href="#" onclick="deleteStation(this); return false;">🗑️ Delete</a><br>' +
      '<small>📄 ' + d.s + '</small>';
  }

  function buildAll(data) {
    var groups = data.groups;
    var stations = data.stations;

    // Pre-build one icon per (groupIdx, isCurrent). Shared by all markers.
    var tideIcons = [], currentIcons = [];
    for (var gi = 0; gi < groups.length; gi++) {
      tideIcons.push(makeIcon(tideSvg(groups[gi].color)));
      currentIcons.push(makeIcon(currentSvg(groups[gi].color)));
    }

    // Globals expected by templates/index.html and other scripts.
    window.stationCoords = {};
    window.stationSources = {};
    window.grp_all_tide = L.markerClusterGroup();
    window.grp_all_current = L.markerClusterGroup();
    window.markers = L.featureGroup();
    // Per-group marker arrays (used by the layer control toggle).
    var srcMarkers = []; // srcMarkers[groupIdx] = { tide: [], current: [] }
    var tideCounts = [], currentCounts = [];
    for (var i = 0; i < groups.length; i++) {
      srcMarkers.push({ tide: [], current: [] });
      tideCounts.push(0);
      currentCounts.push(0);
    }

    var idx = 0;
    var total = stations.length;

    function step(deadline) {
      var end = Math.min(idx + BATCH_SIZE, total);
      for (; idx < end; idx++) {
        var s = stations[idx];
        // [displayName, lat, lon, source, groupIdx, isCurrent, slug, needsSource, origName]
        var displayName = s[0], lat = s[1], lon = s[2], source = s[3];
        var gi = s[4], isCurrent = s[5] === 1, slug = s[6], needsSource = s[7] === 1, origName = s[8];

        var url = needsSource
          ? '/prediction/' + slug + '?source=' + source
          : '/prediction/' + slug;

        var icon = isCurrent ? currentIcons[gi] : tideIcons[gi];
        var m = L.marker([lat, lon], {
          icon: icon,
          title: displayName,
          alt: displayName,
          keyboard: true,
          sd: { n: displayName, u: url, s: source }
        });
        m.bindPopup(popupContent);

        if (isCurrent) {
          window.grp_all_current.addLayer(m);
          srcMarkers[gi].current.push(m);
          currentCounts[gi]++;
        } else {
          window.grp_all_tide.addLayer(m);
          srcMarkers[gi].tide.push(m);
          tideCounts[gi]++;
        }
        window.stationCoords[origName] = [lat, lon];
        window.stationSources[origName] = source;
      }

      if (idx < total) {
        scheduleNext(step);
      } else {
        finalize(groups, srcMarkers, tideCounts, currentCounts);
      }
    }

    scheduleNext(step);
  }

  function scheduleNext(fn) {
    if (window.requestIdleCallback) {
      requestIdleCallback(fn, { timeout: 500 });
    } else {
      setTimeout(fn, 0);
    }
  }

  function finalize(groups, srcMarkers, tideCounts, currentCounts) {
    if (typeof map === 'undefined') {
      // Map not yet initialized — defer.
      setTimeout(function () { finalize(groups, srcMarkers, tideCounts, currentCounts); }, 50);
      return;
    }

    map.addLayer(grp_all_tide);
    markers.addLayer(grp_all_tide);
    map.addLayer(grp_all_current);
    markers.addLayer(grp_all_current);

    var tideTotal = 0, currentTotal = 0;
    for (var i = 0; i < groups.length; i++) {
      tideTotal += tideCounts[i];
      currentTotal += currentCounts[i];
    }

    var tideGroups = [], currentGroups = [];
    for (var j = 0; j < groups.length; j++) {
      if (tideCounts[j] > 0) {
        tideGroups.push({
          name: groups[j].name, count: tideCounts[j], color: groups[j].color,
          markers: srcMarkers[j].tide, cluster: grp_all_tide
        });
      }
      if (currentCounts[j] > 0) {
        currentGroups.push({
          name: groups[j].name, count: currentCounts[j], color: groups[j].color,
          markers: srcMarkers[j].current, cluster: grp_all_current
        });
      }
    }

    addStationControl(tideGroups, currentGroups, tideTotal, currentTotal);

    if (!localStorage.getItem('mapView')) {
      try { map.fitBounds(markers.getBounds()); } catch (e) { /* empty */ }
    }
  }

  function addStationControl(tideGroups, currentGroups, tideTotal, currentTotal) {
    var tideHeaderSvg = '<svg width="16" height="16" viewBox="0 0 18 18" style="vertical-align:middle;margin-right:4px;"><line x1="9" y1="2" x2="9" y2="16" stroke="#333" stroke-width="3" stroke-linecap="round"/><polyline points="5,5 9,2 13,5" fill="none" stroke="#333" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><polyline points="5,13 9,16 13,13" fill="none" stroke="#333" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/></svg>';
    var currentHeaderSvg = '<svg width="16" height="16" viewBox="0 0 18 18" style="vertical-align:middle;margin-right:4px;"><line x1="2" y1="9" x2="16" y2="9" stroke="#333" stroke-width="3" stroke-linecap="round"/><polyline points="5,5 2,9 5,13" fill="none" stroke="#333" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><polyline points="13,5 16,9 13,13" fill="none" stroke="#333" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/></svg>';

    var StationControl = L.Control.extend({
      options: { position: 'bottomright' },
      onAdd: function () {
        var div = L.DomUtil.create('div', 'leaflet-bar');
        div.style.cssText = 'background:rgba(255,255,255,0.25);backdrop-filter:blur(4px);-webkit-backdrop-filter:blur(4px);padding:8px 10px;font-size:13px;font-family:sans-serif;cursor:default;border-radius:6px;box-shadow:0 2px 6px rgba(0,0,0,.2);max-height:60vh;overflow-y:auto;';
        L.DomEvent.disableClickPropagation(div);
        L.DomEvent.disableScrollPropagation(div);

        function dot(color) {
          return '<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:' + color + ';margin-right:5px;vertical-align:middle;border:1px solid #fff;"></span>';
        }

        function buildSection(masterLabel, masterSvg, groups, idPrefix) {
          // min-height + padding give a >=36px tap target on mobile without
          // visually enlarging the checkbox; aria-label provides an
          // accessible name for screen readers.
          var html = '<label style="display:flex;align-items:center;cursor:pointer;font-weight:bold;margin-bottom:2px;min-height:32px;padding:2px 0;">' +
            '<input type="checkbox" data-master="' + idPrefix + '" checked aria-label="Toggle all ' + idPrefix + ' stations" style="margin-right:6px;width:18px;height:18px;">' +
            masterSvg + ' ' + masterLabel + '</label>';
          for (var i = 0; i < groups.length; i++) {
            var g = groups[i];
            var groupLabel = g.name + ' (' + g.count + ')';
            html += '<label style="display:flex;align-items:center;cursor:pointer;margin-left:22px;margin-bottom:1px;min-height:32px;padding:2px 0;">' +
              '<input type="checkbox" data-group="' + idPrefix + '-' + i + '" checked aria-label="Toggle ' + groupLabel + '" style="margin-right:5px;width:18px;height:18px;">' +
              dot(g.color) + groupLabel + '</label>';
          }
          return html;
        }

        var html = buildSection('Tides (' + tideTotal + ')', tideHeaderSvg, tideGroups, 'tide');
        html += '<div style="border-top:1px solid rgba(0,0,0,0.15);margin:5px 0;"></div>';
        html += buildSection('Currents (' + currentTotal + ')', currentHeaderSvg, currentGroups, 'current');
        div.innerHTML = html;

        function toggleGroup(g, on) {
          var arr = g.markers, cl = g.cluster;
          for (var j = 0; j < arr.length; j++) {
            if (on) cl.addLayer(arr[j]);
            else cl.removeLayer(arr[j]);
          }
        }

        function setupMaster(idPrefix, groups) {
          var master = div.querySelector('[data-master="' + idPrefix + '"]');
          var subs = [];
          for (var i = 0; i < groups.length; i++) {
            subs.push(div.querySelector('[data-group="' + idPrefix + '-' + i + '"]'));
          }
          master.addEventListener('change', function () {
            var on = this.checked;
            for (var i = 0; i < groups.length; i++) {
              subs[i].checked = on;
              toggleGroup(groups[i], on);
            }
          });
          for (var i = 0; i < groups.length; i++) {
            (function (idx) {
              subs[idx].addEventListener('change', function () {
                toggleGroup(groups[idx], this.checked);
                var allOn = true, allOff = true;
                for (var j = 0; j < subs.length; j++) {
                  if (subs[j].checked) allOff = false;
                  else allOn = false;
                }
                master.checked = allOn;
                master.indeterminate = !allOn && !allOff;
              });
            })(i);
          }
        }

        setupMaster('tide', tideGroups);
        setupMaster('current', currentGroups);

        return div;
      }
    });
    new StationControl().addTo(map);
  }

  // Entry point — wait until the map is set up, then start.
  if (typeof map !== 'undefined') {
    start();
  } else if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start);
  } else {
    start();
  }
})();
"""

loader_path = os.path.join(PROJECT_ROOT, "static", "js", "leaflet_markers.js")
with open(loader_path, "w", encoding="utf-8") as f:
    f.write(LOADER_JS)

json_size = os.path.getsize(json_path)
loader_size = os.path.getsize(loader_path)
print(f"Fertig:")
print(f"  {len(all_stations)} Stationen")
print(f"  {json_path}  ({json_size/1024:.1f} KiB)")
print(f"  {loader_path}  ({loader_size/1024:.1f} KiB)")
