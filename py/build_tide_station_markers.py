import re
import os
import html
import json

input_files = [
    "harmonics/harmonics-dwf-20241229-free.txt",
    "harmonics/harmonics-dwf-20100529-nonfree.txt",
    "harmonics/harmonics-dwf-20070318_no_us_no_dupes.txt",
    "harmonics/harmonics-2004-06-14_no_us_no_dupes2.txt",
    "harmonics/harmonics_old_no_us_no_dupes3.txt",
    "harmonics/harmonics_pierre_lavergne_v10_add.txt",
]

output_file = "static/js/leaflet_markers.js"
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
            name_html = html.escape(name)
            name_js = json.dumps(name)
            safe_name = re.sub(r"[\s,]+", "_", name)
            safe_js = json.dumps(safe_name)

            marker_var = f"marker{marker_count}"
            marker_count += 1

            popup_raw_html = (
                f"<b>{name_html}</b><br>"
                f"<small style='color:gray;'>📂 {os.path.basename(input_file)}</small><br>"
                f"<a href='#' onclick='generateAndOpen({name_js}, {safe_js}); return false;'>🌊 Vorhersage anzeigen</a>"
            )

            popup_html = json.dumps(popup_raw_html)

            marker_code = (
                f"var {marker_var} = L.marker([{lat}, {lon}], {{icon: {icon_var}}});\n"
                f"{marker_var}.bindPopup({popup_html});\n"
                f"markers.addLayer({marker_var});"
            )

            marker_definitions.append(marker_code)

marker_definitions.append("map.addLayer(markers);")
marker_definitions.append("map.fitBounds(markers.getBounds());")

helper_function = """
function generateAndOpen(stationName, safeName) {
    const encoded = encodeURIComponent(stationName);
    fetch(`/generate/` + encoded).then(r => {
        if (r.ok) window.location.href = `/static/predictions/tide_prediction_` + safeName + `.html`;
        else alert("❌ Fehler beim Erzeugen der Vorhersage.");
    });
}
"""

with open(output_file, "w", encoding="utf-8") as f:
    f.write(icon_definitions)
    f.write("\n".join(marker_definitions))
    f.write("\n")
    f.write(helper_function)

print(f"✅ Total markers generated: {marker_count - 1}")