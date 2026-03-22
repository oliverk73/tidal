import re
import os
import glob
import unicodedata

def normalize_filename(name: str) -> str:
    name = unicodedata.normalize('NFKD', name)
    name = name.encode('ascii', 'ignore').decode('ascii')
    name = re.sub(r"[\s,]+", "_", name)
    return name

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

HARMONICS_DIRS = [
    os.path.join(PROJECT_ROOT, "harmonics"),
]

EXCLUDE_PATTERNS = [
    "*template*",
    "*restored_check*",
    "*bak*",
]

def find_harmonics_files():
    """Scan directories for valid XTide harmonics .txt files."""
    files = []
    for d in HARMONICS_DIRS:
        if not os.path.isdir(d):
            continue
        for path in sorted(glob.glob(os.path.join(d, "*.txt"))):
            basename = os.path.basename(path)
            if any(glob.fnmatch.fnmatch(basename, pat) for pat in EXCLUDE_PATTERNS):
                continue
            try:
                with open(path, "r", encoding="iso-8859-1") as f:
                    head = f.read(4096)
                if "WITHOUT ANY WARRANTY" in head:
                    files.append(path)
            except (OSError, UnicodeDecodeError):
                continue
    return files

input_files = find_harmonics_files()
print(f"Gefunden: {len(input_files)} Harmonics-Dateien")
for f in input_files:
    print(f"  {f}")

output_file = os.path.join(PROJECT_ROOT, "static", "js", "leaflet_markers.js")
os.makedirs(os.path.dirname(output_file), exist_ok=True)

marker_count = 1
marker_definitions = []

icon_colors = [
    "red", "blue", "green", "orange", "yellow",
    "violet", "grey", "black", "gold", "pink"
]

icon_definitions = ""
icon_template = """
var icon_{idx} = new L.Icon({{
  iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-{color}.png',
  shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
  iconSize: [25, 41],
  iconAnchor: [12, 41],
  popupAnchor: [1, -34],
  shadowSize: [41, 41]
}});
"""

marker_definitions.append("var markers = L.markerClusterGroup();")

for file_index, input_file in enumerate(input_files):
    try:
        with open(input_file, "r", encoding="iso-8859-1") as f:
            lines = f.readlines()
    except FileNotFoundError:
        continue

    color = icon_colors[file_index % len(icon_colors)]
    icon_var = f"icon_{file_index + 1}"
    icon_definitions += icon_template.format(idx=file_index + 1, color=color)

    inside_block = False
    lat = lon = name = None

    for i in range(len(lines)):
        line = lines[i].strip()

        if not inside_block:
            if "WITHOUT ANY WARRANTY" in line:
                inside_block = True
            continue

        if line.startswith("# BEGIN HOT COMMENTS"):
            lat = lon = name = None
            for j in range(i, i + 15):
                lat_match = re.search(r"#\s*!latitude:\s*([-+]?[0-9]*\.?[0-9]+)", lines[j])
                lon_match = re.search(r"#\s*!longitude:\s*([-+]?[0-9]*\.?[0-9]+)", lines[j])
                if lat_match:
                    lat = lat_match.group(1)
                if lon_match:
                    lon = lon_match.group(1)
                if lat and lon:
                    break
            continue

        if lat and lon and not line.startswith("#") and name is None:
            name = line.strip().replace(" - READ flaterco.com/pol.html", "")
            name_escaped = name.replace('"', '\\"')
            safe_name = normalize_filename(name)

            js_name = name.replace("\\", "\\\\").replace("'", "\\'")
            
            marker_var = f"marker{marker_count}"
            marker_count += 1

            source_file = os.path.basename(input_file)

            popup_html = (
                f"<b>{name}</b><br>"
                f"<a href='#' onclick=\\\""
                f"fetch('/generate/' + encodeURIComponent('{js_name}')).then(r => {{"
                f"  if (r.ok) window.location.href = '/static/predictions/tide_prediction_{safe_name}.html';"
                f"  else alert('❌ Fehler beim Erzeugen der Vorhersage.');"
                f"}}); return false;\\\">🌊 Vorhersage anzeigen</a><br>"
                f"📄 Aus Datei: {source_file}"
            )
            
            marker_code = (
                f"var {marker_var} = L.marker([{lat}, {lon}], {{icon: {icon_var}}});\n"
                f'{marker_var}.bindPopup("{popup_html}");\n'
                f"markers.addLayer({marker_var});"
            )


            marker_definitions.append(marker_code)

marker_definitions.append("map.addLayer(markers);")
# marker_definitions.append("map.fitBounds(markers.getBounds());")

marker_definitions.append("""
if (!localStorage.getItem('mapView')) {
  map.fitBounds(markers.getBounds());
}
""")

with open(output_file, "w", encoding="utf-8") as f:
    f.write(icon_definitions)
    f.write("\n".join(marker_definitions))

print(f"✅ Total markers generated: {marker_count - 1}")