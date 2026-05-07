import re
import os
import unicodedata

def normalize_filename(name: str) -> str:
    name = unicodedata.normalize('NFKD', name)
    name = name.encode('ascii', 'ignore').decode('ascii')
    name = re.sub(r"[\s,]+", "_", name)
    return name

input_files = [
    "harmonics/harmonics-dwf-20241229-free.txt",
    "harmonics/harmonics-dwf-20100529-nonfree_mod.txt",
    "harmonics/harmonics-dwf-20070318_no_us_no_dupes.txt",
    "harmonics/harmonics-2004-06-14_no_us_no_dupes2.txt",
    "harmonics/harmonics_old_no_us_no_dupes3.txt",
    "harmonics/harmonics_pierre_lavergne_v10_add.txt",

]

output_file = "static/js/leaflet_markers.js"
os.makedirs(os.path.dirname(output_file), exist_ok=True)

marker_count = 1
marker_definitions = []

# Helper-Funktion für JSON-Redirect in die Ausgabe aufnehmen
helper_js = """
// ==== BEGIN helper: JSON-Redirect for tide generation ====
function generateAndOpen(el) {
  const n = el.dataset.name;
  fetch('/generate/' + encodeURIComponent(n))
    .then(r => r.ok ? r.json() : Promise.reject(r))
    .then(({ url }) => { window.location.href = url; })
    .catch(err => {
      console.error('Generate failed', err);
      alert('❌ Fehler beim Erzeugen der Vorhersage.');
    });
  return false;
}
// ==== END helper ====
"""

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

marker_definitions.append("var markers = L.markerClusterGroup({ chunkedLoading: true });")

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

            marker_var = f"marker{marker_count}"
            marker_count += 1

            source_file = os.path.basename(input_file)

            name_escaped = name.replace('"', '\\"')

            popup_html = (
                f"<b>{name}</b><br>"
                f"<a href=\\\"#\\\" data-name=\\\"{name_escaped}\\\" onclick=\\\"return generateAndOpen(this)\\\">"
                f"🌊 Vorhersage anzeigen</a><br>"
                f"📄 Aus Datei: {source_file}"
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
    f.write(helper_js)
    f.write("\n".join(marker_definitions))

print(f"✅ Total markers generated: {marker_count - 1}")