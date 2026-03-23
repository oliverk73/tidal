import os
import re
import unicodedata

input_files = [
    "harmonics/harmonics-dwf-20241229-free.txt",
    "harmonics/harmonics-dwf-20100529-nonfree.txt",
    "harmonics/harmonics-dwf-20070318_no_us_no_dupes.txt",
    "harmonics/harmonics-2004-06-14_no_us_no_dupes2.txt",
    "harmonics/harmonics_old_no_us_no_dupes3.txt",
    "harmonics/harmonics_pierre_lavergne_v10_add.txt",
]


output_dir = "static/js"
output_file = os.path.join(output_dir, "leaflet_markers.js")

lat_lon_pattern = re.compile(r"# LatLon:\s*([-+]?[0-9.]+),\s*([-+]?[0-9.]+)")

# → z. B. Fécamp, France → Fecamp_France
def normalize_filename(name: str) -> str:
    name = unicodedata.normalize("NFKD", name)
    umlaut_map = {
        "ä": "ae", "ö": "oe", "ü": "ue",
        "Ä": "Ae", "Ö": "Oe", "Ü": "Ue",
        "ß": "ss",
    }
    for src, repl in umlaut_map.items():
        name = name.replace(src, repl)
    name = "".join(c for c in name if not unicodedata.combining(c))
    name = re.sub(r"[ ,]+", "_", name)
    name = name.encode("ascii", "ignore").decode("ascii")
    return name

def escape_js_string(s: str) -> str:
    return s.replace("\\", "\\\\").replace("\"", "\\\"").replace("'", "\\'")

def main():
    os.makedirs(output_dir, exist_ok=True)
    marker_lines = ["// Automatisch generiert", "var markers = L.layerGroup();\n"]
    marker_count = 0

    for input_file in input_files:
        with open(input_file, "r", encoding="iso-8859-1") as f:
            lines = f.readlines()

        current_name = None

        for i, line in enumerate(lines):
            line = line.strip()

            if line.startswith("# Location:"):
                current_name = line.split(":", 1)[1].strip()

            elif line.startswith("# LatLon:") and current_name:
                match = lat_lon_pattern.match(line)
                if not match:
                    continue

                lat, lon = match.groups()
                safe_name = normalize_filename(current_name)
                js_original = escape_js_string(current_name)
                js_safe = escape_js_string(safe_name)

                popup_html = (
                    f"<b>{js_original}</b><br>"
                    f"<a href='#' onclick=\\\"generateAndOpen('{js_original}', '{js_safe}')\\\">🌊 Vorhersage anzeigen</a>"
                )

                marker_code = (
                    f"var marker{marker_count} = L.marker([{lat}, {lon}]).addTo(markers);\n"
                    f"marker{marker_count}.bindPopup(\"{popup_html}\");\n"
                )

                marker_lines.append(marker_code)
                marker_count += 1
                current_name = None

        print(f"📄 Fertig mit Datei: {input_file}")

    marker_lines.append("// Ende")

    with open(output_file, "w", encoding="utf-8") as f:
        f.write("\n".join(marker_lines))

    print(f"✅ Total markers generated: {marker_count}")

if __name__ == "__main__":
    main()