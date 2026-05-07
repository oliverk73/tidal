
import re
import os

input_files = [
    "../harmonics/harmonics-dwf-20241229-free.txt",
    "../harmonics/harmonics-dwf-20100529-nonfree_mod.txt",
    "../harmonics/harmonics-dwf-20070318_no_us_no_dupes.txt",
    "../harmonics/harmonics-2004-06-14_no_us_no_dupes2.txt",
    "../harmonics/harmonics_old.txt",
    # Weitere Dateien bei Bedarf aktivieren
]

output_file = "../js/leaflet_markers.js"
marker_count = 1
marker_definitions = []

# Maximal 10 Farben (reihum verwendet)
icon_colors = [
    "red", "blue", "green", "orange", "yellow",
    "violet", "grey", "black", "gold", "pink"
]

# Icon-Vorlagen definieren
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

# Clustergruppe initialisieren
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
    source_file_label = os.path.basename(input_file)

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
            name_escaped = re.sub(r"[’']", r"\\'", name)
            safe_name = re.sub(r",", "", name)
            safe_name = re.sub(r"[^\w]", "_", safe_name)

            marker_var = f"marker{marker_count}"
            marker_count += 1

            popup = (
                f"<p><a href=\\\"tide_prediction_{safe_name}\\\">{name_escaped}</a><br>"
                f"<small>{source_file_label}</small></p>"
            )

            marker_code = (
                f"var {marker_var} = L.marker([{lat}, {lon}], {{icon: {icon_var}}});\n"
                f"{marker_var}.bindPopup('{popup}');\n"
                f"markers.addLayer({marker_var});"
            )
            marker_definitions.append(marker_code)

marker_definitions.append("map.addLayer(markers);")
marker_definitions.append("map.fitBounds(markers.getBounds());")

with open(output_file, "w", encoding="utf-8") as f:
    f.write(icon_definitions)
    f.write("\n".join(marker_definitions))

print(f"Total markers generated: {marker_count}")
