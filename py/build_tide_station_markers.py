import os
import unicodedata

# Liste der Eingabedateien
input_files = [
    "harmonics/harmonics-dwf-20241229-free.txt",
    "harmonics/harmonics-dwf-20100529-nonfree.txt",
    "harmonics/harmonics-dwf-20070318_no_us_no_dupes.txt",
    "harmonics/harmonics-2004-06-14_no_us_no_dupes2.txt",
    "harmonics/harmonics_old_no_us_no_dupes3.txt",
    "harmonics/harmonics_pierre_lavergne_v10_add.txt",
]

output_file = "static/js/leaflet_markers.js"

def escape_js_string(s):
    return s.replace("\\", "\\\\").replace("'", "\\'").replace('"', '\\"')

def normalize_filename(s):
    nfkd_form = unicodedata.normalize("NFKD", s)
    return "".join([c for c in nfkd_form if not unicodedata.combining(c)]).replace(" ", "_").replace(",", "_")

def extract_blocks(lines):
    blocks = []
    current_block = []
    for line in lines:
        if line.strip() == "" or line.strip().startswith("#"):
            current_block.append(line)
        else:
            # Start Infobereich (3 Zeilen)
            current_block.append(line)  # Ortsname
            current_block.append(next(lines))  # UTC
            current_block.append(next(lines))  # Referenzhöhe

            # Constituents
            while True:
                try:
                    next_line = next(lines)
                except StopIteration:
                    break
                if next_line.strip().startswith("#") and next_line.strip() != "#":
                    break
                current_block.append(next_line)

            blocks.append(current_block)
            current_block = [next_line] if next_line.strip().startswith("#") else []

    return blocks

def main():
    total_markers = 0
    with open(output_file, "w", encoding="utf-8") as out:
        out.write("// Automatisch generiert\n")
        out.write("var markers = L.layerGroup();\n\n")

        for input_file in input_files:
            print(f"🔍 Verarbeite Datei: {input_file}")
            with open(input_file, "r", encoding="iso-8859-1") as f:
                lines = iter(f.readlines())

            blocks = extract_blocks(lines)

            for block in blocks:
                try:
                    comments = [line for line in block if line.strip().startswith("#")]
                    name_line = block[len(comments)].strip()
                    lat_line = next((line for line in comments if "!latitude" in line), None)
                    lon_line = next((line for line in comments if "!longitude" in line), None)

                    if not lat_line or not lon_line:
                        continue

                    lat = lat_line.split(":", 1)[1].strip()
                    lon = lon_line.split(":", 1)[1].strip()

                    station_display = name_line.split(" - READ")[0].strip()
                    station_js = escape_js_string(station_display)
                    station_file = normalize_filename(station_display)
                    source_file = os.path.basename(input_file)

                    popup_html = (
                        f"<b>{station_display}</b><br>"
                        f"<small><i>{source_file}</i></small><br>"
                        f"<a href='#' onclick=\"generateAndOpen('{station_js}', '{station_file}'); return false;\">🌊 Vorhersage anzeigen</a>"
                    )

                    marker_code = f"L.marker([{lat}, {lon}]).bindPopup('{popup_html}').addTo(markers);\n"
                    out.write(marker_code)
                    total_markers += 1
                except Exception as e:
                    print(f"⚠️ Fehler bei Block in Datei {input_file}: {e}")
                    continue

        out.write("\n// Ende\n")

    print(f"✅ Total markers generated: {total_markers}")

if __name__ == "__main__":
    main()
