import re
import os
import glob
import unicodedata
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
    """Parse station list directly from a harmonics TXT file."""
    stations = []
    with open(txt_path, 'r', encoding='iso-8859-1') as f:
        lines = f.readlines()

    lat = lon = None
    for line in lines:
        line = line.rstrip()
        if line.startswith('# !latitude:'):
            lat = float(line.split(':', 1)[1].strip())
        elif line.startswith('# !longitude:'):
            lon = float(line.split(':', 1)[1].strip())
        elif not line.startswith('#') and line.strip() and lat is not None and lon is not None:
            stations.append((line.strip(), lat, lon))
            lat = lon = None
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
    for name, lat, lon in stations:
        if name not in seen:
            seen.add(name)
            all_stations.append((name, lat, lon, basename))
            count += 1
    print(f"  {basename}: {count} neue Stationen ({len(stations)} in TXT)")

print(f"Gesamt: {len(all_stations)} Stationen (nach Deduplizierung)")

output_file = os.path.join(PROJECT_ROOT, "static", "js", "leaflet_markers.js")
os.makedirs(os.path.dirname(output_file), exist_ok=True)

icon_definition = """
var tideIcon = new L.Icon({
  iconUrl: '/static/images/marker-icon-blue.png',
  shadowUrl: '/static/images/marker-shadow.png',
  iconSize: [25, 41],
  iconAnchor: [12, 41],
  popupAnchor: [1, -34],
  shadowSize: [41, 41]
});
"""

lines = ["var stationCoords = {};"]
lines.append("var stationSources = {};")
lines.append("var markers = L.markerClusterGroup();")

for i, (name, lat, lon, source_file) in enumerate(all_stations, 1):
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

    marker_var = f"m{i}"
    coord_key = name.replace("\\", "\\\\").replace("'", "\\'")
    lines.append(f"stationCoords['{coord_key}'] = [{lat}, {lon}];")
    lines.append(f"stationSources['{coord_key}'] = '{source_file}';")
    lines.append(
        f'var {marker_var} = L.marker([{lat}, {lon}], {{icon: tideIcon}});'
    )
    lines.append(f'{marker_var}.bindPopup("{popup_html}");')
    lines.append(f"markers.addLayer({marker_var});")

lines.append("""document.addEventListener('DOMContentLoaded', function() {
  map.addLayer(markers);
  if (!localStorage.getItem('mapView')) {
    map.fitBounds(markers.getBounds());
  }
});""")

with open(output_file, "w", encoding="utf-8") as f:
    f.write(icon_definition)
    f.write("\n".join(lines))

print(f"Fertig: {len(all_stations)} Marker in {output_file}")
