import re
import os
import glob
import subprocess
import unicodedata

TCD_DIR = "/usr/share/xtide"


def normalize_filename(name: str) -> str:
    name = unicodedata.normalize('NFKD', name)
    name = name.encode('ascii', 'ignore').decode('ascii')
    name = re.sub(r"['\\\\/]", "", name)
    name = re.sub(r"[\s,]+", "_", name)
    return name


def get_stations_from_tcd(tcd_path):
    """Parse station list from a single TCD file via tide command."""
    env = os.environ.copy()
    env["HFILE_PATH"] = tcd_path
    result = subprocess.run(
        ["tide", "-m", "l", "-tw", "200"],
        capture_output=True, text=True, env=env
    )
    output = result.stdout or result.stderr
    stations = []
    pattern = re.compile(
        r'^(.+?)\s{2,}(Ref|Sub)\s+([\d.]+)°\s*([NS]),\s*([\d.]+)°\s*([EW])$'
    )
    for line in output.splitlines():
        if line.startswith("Indexing ") or line.startswith("Location list") or not line.strip():
            continue
        m = pattern.match(line)
        if not m:
            continue
        name, stype, lat, ns, lon, ew = m.groups()
        lat = float(lat) * (1 if ns == 'N' else -1)
        lon = float(lon) * (1 if ew == 'E' else -1)
        stations.append((name.strip(), stype, lat, lon))
    return stations


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

tcd_files = sorted(glob.glob(os.path.join(TCD_DIR, "*.tcd")))
print(f"Gefunden: {len(tcd_files)} TCD-Dateien in {TCD_DIR}")

all_stations = []
seen_names = set()
seen_coords = set()
for tcd_file in tcd_files:
    basename = os.path.basename(tcd_file)
    stations = get_stations_from_tcd(tcd_file)
    added = 0
    for s in stations:
        coord_key = (round(s[2], 4), round(s[3], 4))
        if s[0] not in seen_names and coord_key not in seen_coords:
            seen_names.add(s[0])
            seen_coords.add(coord_key)
            all_stations.append((*s, basename))
            added += 1
    print(f"  {basename}: {len(stations)} Stationen ({len(stations) - added} Duplikate übersprungen)")

print(f"Gesamt: {len(all_stations)} Stationen")

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
lines.append("var markers = L.markerClusterGroup();")

for i, (name, stype, lat, lon, source_file) in enumerate(all_stations, 1):
    safe_name = normalize_filename(name)
    display_name = name.replace('"', '&quot;')
    js_name = name.replace("\\", "\\\\").replace("'", "\\x27").replace('"', "\\x22")

    popup_html = (
        f"<b>{display_name}</b><br>"
        f"<a href=\\\"#\\\" onclick=\\\""
        f"fetch('/generate/' + encodeURIComponent('{js_name}')).then(r => {{"
        f"  if (r.ok) window.location.href = '/static/predictions/tide_prediction_{safe_name}.html';"
        f"  else alert('Fehler beim Erzeugen der Vorhersage.');"
        f"}}); return false;\\\">🌊 Vorhersage anzeigen</a><br>"
        f"📄 Aus Datei: {source_file}"
    )

    marker_var = f"m{i}"
    # Add to stationCoords lookup for search-to-map zoom
    coord_key = name.replace("\\", "\\\\").replace("'", "\\'")
    lines.append(f"stationCoords['{coord_key}'] = [{lat}, {lon}];")
    lines.append(
        f'var {marker_var} = L.marker([{lat}, {lon}], {{icon: tideIcon}});'
    )
    lines.append(f'{marker_var}.bindPopup("{popup_html}");')
    lines.append(f"markers.addLayer({marker_var});")

lines.append("map.addLayer(markers);")
lines.append("""
if (!localStorage.getItem('mapView')) {
  map.fitBounds(markers.getBounds());
}
""")

with open(output_file, "w", encoding="utf-8") as f:
    f.write(icon_definition)
    f.write("\n".join(lines))

print(f"Fertig: {len(all_stations)} Marker in {output_file}")
