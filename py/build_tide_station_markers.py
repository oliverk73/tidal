import os
import re
import unicodedata
import html
import json

input_files = [
    "harmonics/harmonics-dwf-20241229-free.txt",
    "harmonics/harmonics-dwf-20100529-nonfree.txt",
    "harmonics/harmonics-dwf-20070318_no_us_no_dupes.txt",
    "harmonics/harmonics-2004-06-14_no_us_no_dupes2.txt",
    "harmonics/harmonics_old_no_us_no_dupes3.txt",
    "harmonics/harmonics_pierre_lavergne_v10_add.txt",
    # Weitere Dateien bei Bedarf ergänzen
]

output_dir = "static/js"
output_file = os.path.join(output_dir, "leaflet_markers.js")
marker_count = 0

umlaut_map = {
    "ä": "ae", "ö": "oe", "ü": "ue",
    "Ä": "Ae", "Ö": "Oe", "Ü": "Ue",
    "ß": "ss"
}

def normalize_filename(name: str) -> str:
    for umlaut, replacement in umlaut_map.items():
        name = name.replace(umlaut, replacement)
    name = unicodedata.normalize("NFKD", name)
    name = "".join(c for c in name if not unicodedata.combining(c))
    name = name.encode("ascii", "ignore").decode("ascii")
    name = re.sub(r"[ ,]+", "_", name)
    name = re.sub(r"_+", "_", name)
    return name.strip("_")

def escape_js_string(s: str) -> str:
    return s.replace("\\", "\\\\").replace("'", "\\'")

def parse_block(block, source_file):
    global marker_count
    lat = lon = name = None

    for line in block:
        if line.startswith("# !latitude:"):
            lat = line.split(":", 1)[1].strip()
        elif line.startswith("# !longitude:"):
            lon = line.split(":", 1)[1].strip()
        elif not line.startswith("#") and name is None:
            name = line.strip()

    if lat and lon and name:
        safe_name = normalize_filename(name)
        js_original = escape_js_string(name)
        js_safe = escape_js_string(safe_name)

        popup_html = (
            f"<b>{html.escape(name)}</b><br>"
            f"<small>📂 {os.path.basename(source_file)}</small><br>"
            f"<a href='#' onclick=\"generateAndOpen('{js_original}', '{js_safe}')\">🌊 Vorhersage anzeigen</a>"
        )

        marker_code = (
            f"var marker{marker_count} = L.marker([{lat}, {lon}]).addTo(markers);\n"
            f"marker{marker_count}.bindPopup({json.dumps(popup_html)});\n"
        )
        marker_count += 1
        return marker_code
    return None

def main():
    os.makedirs(output_dir, exist_ok=True)
    all_markers = ["// Automatisch generiert", "var markers = L.layerGroup();\n"]

    for input_file in input_files:
        print(f"🔍 Verarbeite Datei: {input_file}")
        with open(input_file, "r", encoding="iso-8859-1") as f:
            lines = f.readlines()

        block = []
        for line in lines:
            if line.startswith("# BEGIN HOT COMMENTS"):
                if block:
                    marker = parse_block(block, input_file)
                    if marker:
                        all_markers.append(marker)
                block = [line]
            else:
                block.append(line)

        if block:
            marker = parse_block(block, input_file)
            if marker:
                all_markers.append(marker)

    all_markers.append("// Ende")

    with open(output_file, "w", encoding="utf-8") as f:
        f.write("\n".join(all_markers))

    print(f"✅ Total markers generated: {marker_count}")

if __name__ == "__main__":
    main()
