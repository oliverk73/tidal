import re
import os
import glob
import unicodedata
from collections import OrderedDict
from urllib.parse import quote

TCD_DIR = "/usr/share/xtide"
HARMONICS_DIRS = [
    "harmonics/classic",
    "harmonics/ihm",
    "harmonics/utide",
    "harmonics/ticon",
]


def normalize_filename(name: str) -> str:
    name = unicodedata.normalize('NFKD', name)
    name = name.encode('ascii', 'ignore').decode('ascii')
    name = re.sub(r"['\\\\/]", "", name)
    name = re.sub(r"[\s,]+", "_", name)
    return name


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
    """Find the TXT source file for a given TCD basename."""
    txt_name = tcd_basename.replace('.tcd', '.txt')
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for hdir in HARMONICS_DIRS:
        txt_path = os.path.join(project_root, hdir, txt_name)
        if os.path.exists(txt_path):
            return txt_path
    return None


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

tcd_files = sorted(glob.glob(os.path.join(TCD_DIR, "*.tcd")))
print(f"Gefunden: {len(tcd_files)} TCD-Dateien in {TCD_DIR}")

all_stations = []
seen = set()
for tcd_file in tcd_files:
    basename = os.path.basename(tcd_file)
    txt_path = find_txt_for_tcd(basename)
    if not txt_path:
        print(f"  {basename}: ÜBERSPRUNGEN (keine TXT-Datei gefunden)")
        continue
    stations = get_stations_from_txt(txt_path)
    count = 0
    for name, lat, lon, is_current in stations:
        if name not in seen:
            seen.add(name)
            all_stations.append((name, lat, lon, basename, is_current))
            count += 1
    print(f"  {basename}: {count} neue Stationen ({len(stations)} in TXT)")

print(f"Gesamt: {len(all_stations)} Stationen (nach Deduplizierung)")

output_file = os.path.join(PROJECT_ROOT, "static", "js", "leaflet_markers.js")
os.makedirs(os.path.dirname(output_file), exist_ok=True)

SOURCE_GROUPS = OrderedDict([
    ('DWF 2025',        {'color': '#2196F3', 'files': ['harmonics-dwf-20251228-free.tcd']}),
    ('DWF 2010',        {'color': '#607D8B', 'files': ['harmonics-dwf-20100529-nonfree.tcd']}),
    ('DWF 2007',        {'color': '#795548', 'files': ['harmonics-dwf-20070318_mod.tcd']}),
    ('Classic 2004',    {'color': '#4CAF50', 'files': ['harmonics-2004-06-14_mod.tcd']}),
    ('Classic 1997',    {'color': '#9C27B0', 'files': ['harmonics-1997-05-25_mod.tcd']}),
    ('TICON4',          {'color': '#FF9800', 'files': ['harmonics_ticon4_worldwide.tcd']}),
    ('Lavergne',        {'color': '#E91E63', 'files': ['harmonics-pierre-lavergne-v10_mod.tcd',
                                                        'harmonics-pierre-lavergne-v9-europe_mod.tcd']}),
    ('UTide',           {'color': '#F44336', 'files': [
                            'harmonics_utide_germany_z0corrected.tcd',
                            'harmonics_utide_netherlands.tcd',
                            'harmonics_utide_france.tcd',
                            'harmonics_utide_belgium.tcd',
                            'harmonics_utide_canada_all.tcd',
                            'harmonics_utide_uk_bodc.tcd',
                            'harmonics_utide_ireland.tcd',
                            'harmonics_utide_uk_ireland.tcd',
                            'harmonics_utide_denmark.tcd',
                            'harmonics_utide_australia.tcd',
                            'harmonics_utide_australia_qld.tcd',
                            'harmonics_utide_australia_uhslc.tcd']}),
    ('Puertos',         {'color': '#00BCD4', 'files': ['harmonics_puertos_spain.tcd']}),
])

def get_group_for_source(source_file):
    for group_name, info in SOURCE_GROUPS.items():
        if source_file in info['files']:
            return group_name, info['color']
    return 'Sonstige', '#999999'

icon_definition = ""

lines = ["var stationCoords = {};"]
lines.append("var stationSources = {};")
# Create a cluster group per source group
group_names = list(SOURCE_GROUPS.keys()) + ['Sonstige']
group_colors = {g: SOURCE_GROUPS[g]['color'] for g in SOURCE_GROUPS}
group_colors['Sonstige'] = '#999999'
for g in group_names:
    var_name = re.sub(r'[^a-zA-Z0-9]', '_', g)
    lines.append(f"var grp_{var_name} = L.markerClusterGroup();")
lines.append("var markers = L.featureGroup();")  # master group for fitBounds
lines.append("var allTideMarkers = [];")
lines.append("var allCurrentMarkers = [];")

group_counts = {}
tide_count = 0
current_count = 0
for i, (name, lat, lon, source_file, is_current) in enumerate(all_stations, 1):
    safe_name = normalize_filename(name)
    display_name = name.replace('"', '&quot;')
    uri_name = quote(name, safe='')

    popup_html = (
        f"<b>{display_name}</b><br>"
        f"<a href=\\\"#\\\" onclick=\\\""
        f"fetch('/generate/{uri_name}').then(r => {{"
        f"  if (r.ok) window.location.href = '/static/predictions/tide_prediction_{safe_name}.html';"
        f"  else alert('Fehler beim Erzeugen der Vorhersage.');"
        f"}}); return false;\\\">🌊 Vorhersage anzeigen</a><br>"
        f"<a href=\\\"#\\\" onclick=\\\"enableDrag(this); return false;\\\">📍 Position korrigieren</a> "
        f"<a href=\\\"#\\\" onclick=\\\"renameStation(this); return false;\\\">✏️ Name ändern</a> "
        f"<a href=\\\"#\\\" onclick=\\\"deleteStation(this); return false;\\\">🗑️ Löschen</a><br>"
        f"<small>📄 {source_file}</small>"
    )

    group_name, color = get_group_for_source(source_file)
    group_counts[group_name] = group_counts.get(group_name, 0) + 1
    grp_var = "grp_" + re.sub(r'[^a-zA-Z0-9]', '_', group_name)
    marker_var = f"m{i}"
    coord_key = name.replace("\\", "\\\\").replace("'", "\\'")
    lines.append(f"stationCoords['{coord_key}'] = [{lat}, {lon}];")
    lines.append(f"stationSources['{coord_key}'] = '{source_file}';")
    sz = 18
    sw = 3  # stroke width
    if is_current:
        current_count += 1
        # horizontal double arrow ↔
        svg = (f'<svg width="{sz}" height="{sz}" viewBox="0 0 {sz} {sz}" xmlns="http://www.w3.org/2000/svg">'
               f'<line x1="2" y1="{sz//2}" x2="{sz-2}" y2="{sz//2}" stroke="{color}" stroke-width="{sw}" stroke-linecap="round"/>'
               f'<polyline points="5,{sz//2-4} 2,{sz//2} 5,{sz//2+4}" fill="none" stroke="{color}" stroke-width="{sw}" stroke-linecap="round" stroke-linejoin="round"/>'
               f'<polyline points="{sz-5},{sz//2-4} {sz-2},{sz//2} {sz-5},{sz//2+4}" fill="none" stroke="{color}" stroke-width="{sw}" stroke-linecap="round" stroke-linejoin="round"/>'
               f'</svg>')
        lines.append(
            f'var {marker_var} = L.marker([{lat}, {lon}], {{icon: L.divIcon({{html:\'{svg}\', className:"", iconSize:[{sz},{sz}], iconAnchor:[{sz//2},{sz//2}], popupAnchor:[0,-{sz//2}]}})}});'
        )
        lines.append(f"allCurrentMarkers.push({marker_var});")
    else:
        tide_count += 1
        # vertical double arrow ↕
        svg = (f'<svg width="{sz}" height="{sz}" viewBox="0 0 {sz} {sz}" xmlns="http://www.w3.org/2000/svg">'
               f'<line x1="{sz//2}" y1="2" x2="{sz//2}" y2="{sz-2}" stroke="{color}" stroke-width="{sw}" stroke-linecap="round"/>'
               f'<polyline points="{sz//2-4},5 {sz//2},2 {sz//2+4},5" fill="none" stroke="{color}" stroke-width="{sw}" stroke-linecap="round" stroke-linejoin="round"/>'
               f'<polyline points="{sz//2-4},{sz-5} {sz//2},{sz-2} {sz//2+4},{sz-5}" fill="none" stroke="{color}" stroke-width="{sw}" stroke-linecap="round" stroke-linejoin="round"/>'
               f'</svg>')
        lines.append(
            f'var {marker_var} = L.marker([{lat}, {lon}], {{icon: L.divIcon({{html:\'{svg}\', className:"", iconSize:[{sz},{sz}], iconAnchor:[{sz//2},{sz//2}], popupAnchor:[0,-{sz//2}]}})}});'
        )
        lines.append(f"allTideMarkers.push({marker_var});")
    lines.append(f'{marker_var}.bindPopup("{popup_html}");')
    lines.append(f"{grp_var}.addLayer({marker_var});")

# Build the DOMContentLoaded block with layer control
ctrl_lines = ["document.addEventListener('DOMContentLoaded', function() {"]
ctrl_lines.append("  var overlays = {};")
for g in group_names:
    count = group_counts.get(g, 0)
    if count == 0:
        continue
    var_name = re.sub(r'[^a-zA-Z0-9]', '_', g)
    color = group_colors[g]
    ctrl_lines.append(
        f'  overlays[\'<span style="display:inline-block;width:12px;height:12px;'
        f'border-radius:50%;background:{color};margin-right:6px;vertical-align:middle;'
        f'border:1px solid #fff;"></span>{g} ({count})\'] = grp_{var_name};'
    )
    ctrl_lines.append(f"  map.addLayer(grp_{var_name});")
    ctrl_lines.append(f"  markers.addLayer(grp_{var_name});")
ctrl_lines.append("  L.control.layers(null, overlays, {position:'bottomright', collapsed:false}).addTo(map);")
# Master toggle control for tide/current
ctrl_lines.append(f"""
  var tidesVisible = true;
  var currentsVisible = true;
  var MasterToggle = L.Control.extend({{
    options: {{ position: 'bottomright' }},
    onAdd: function() {{
      var div = L.DomUtil.create('div', 'leaflet-bar');
      div.style.cssText = 'background:rgba(255,255,255,0.25);backdrop-filter:blur(4px);-webkit-backdrop-filter:blur(4px);padding:8px 10px;font-size:13px;font-family:sans-serif;cursor:default;border-radius:6px;box-shadow:0 2px 6px rgba(0,0,0,.2);';
      div.innerHTML =
        '<label style="display:flex;align-items:center;cursor:pointer;margin-bottom:4px;font-weight:bold;">' +
        '<input type="checkbox" id="toggle-tides" checked style="margin-right:6px;">' +
        '<svg width="16" height="16" viewBox="0 0 18 18" style="vertical-align:middle;margin-right:4px;"><line x1="9" y1="2" x2="9" y2="16" stroke="#333" stroke-width="3" stroke-linecap="round"/><polyline points="5,5 9,2 13,5" fill="none" stroke="#333" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><polyline points="5,13 9,16 13,13" fill="none" stroke="#333" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/></svg>' +
        ' Tides ({tide_count})</label>' +
        '<label style="display:flex;align-items:center;cursor:pointer;font-weight:bold;">' +
        '<input type="checkbox" id="toggle-currents" checked style="margin-right:6px;">' +
        '<svg width="16" height="16" viewBox="0 0 18 18" style="vertical-align:middle;margin-right:4px;"><line x1="2" y1="9" x2="16" y2="9" stroke="#333" stroke-width="3" stroke-linecap="round"/><polyline points="5,5 2,9 5,13" fill="none" stroke="#333" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><polyline points="13,5 16,9 13,13" fill="none" stroke="#333" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/></svg>' +
        ' Currents ({current_count})</label>';
      L.DomEvent.disableClickPropagation(div);
      div.querySelector('#toggle-tides').addEventListener('change', function() {{
        tidesVisible = this.checked;
        allTideMarkers.forEach(function(m) {{
          if (tidesVisible) m.setStyle ? m.setStyle({{opacity:1,fillOpacity:0.85}}) : (m._icon && (m._icon.style.display=''));
          else m.setStyle ? m.setStyle({{opacity:0,fillOpacity:0}}) : (m._icon && (m._icon.style.display='none'));
        }});
      }});
      div.querySelector('#toggle-currents').addEventListener('change', function() {{
        currentsVisible = this.checked;
        allCurrentMarkers.forEach(function(m) {{
          if (currentsVisible) {{ if(m._icon) m._icon.style.display=''; }}
          else {{ if(m._icon) m._icon.style.display='none'; }}
        }});
      }});
      return div;
    }}
  }});
  new MasterToggle().addTo(map);
""")
ctrl_lines.append("  if (!localStorage.getItem('mapView')) {")
ctrl_lines.append("    map.fitBounds(markers.getBounds());")
ctrl_lines.append("  }")
ctrl_lines.append("});")
lines.append("\n".join(ctrl_lines))

with open(output_file, "w", encoding="utf-8") as f:
    f.write(icon_definition)
    f.write("\n".join(lines))

print(f"Fertig: {len(all_stations)} Marker in {output_file}")
