import os
import unicodedata

INPUT_FILES = [
    "harmonics/harmonics-dwf-20241229-free.txt",
    "harmonics/harmonics-dwf-20100529-nonfree_mod.txt",
    "harmonics/harmonics-dwf-20070318_no_us_no_dupes.txt",
    "harmonics/harmonics-2004-06-14_no_us_no_dupes2.txt",
    "harmonics/harmonics_old_no_us_no_dupes3.txt",
    "harmonics/harmonics_pierre_lavergne_v10_add.txt",
]

NORMALIZATION_FILE = "normalized_station_names.txt"
OUTPUT_FILE = "static/js/leaflet_markers.js"
LOG_FILE = "marker_generation_log.txt"

log_entries = []

def log(msg):
    print(msg)
    log_entries.append(msg)

def escape_js_string(s):
    return s.replace("\\", "\\\\").replace("'", "\\\\'")

def load_normalized_names(filepath):
    norm = {}
    if not os.path.exists(filepath):
        return norm
    with open(filepath, encoding="utf-8") as f:
        for line in f:
            if " → " in line:
                orig, normed = line.strip().split(" → ", 1)
                norm[orig] = normed
    return norm

def normalize_filename(name):
    nfkd_form = unicodedata.normalize('NFKD', name)
    only_ascii = "".join(c for c in nfkd_form if not unicodedata.combining(c))
    return only_ascii.replace(" ", "_")

def parse_blocks_from_file(file_path):
    with open(file_path, encoding="iso-8859-1") as f:
        lines = f.readlines()

    blocks = []
    current_block = []

    for line in lines:
        if line.startswith("#") and line.strip() == "#":
            if current_block:
                blocks.append(current_block)
                current_block = []
        else:
            current_block.append(line.rstrip())

    if current_block:
        blocks.append(current_block)

    return blocks

def extract_station_info(block):
    comments = [line for line in block if line.startswith("#")]
    content = [line for line in block if not line.startswith("#")]

    try:
        name = content[0].strip()
        lat_line = next((l for l in comments if "!latitude:" in l), "")
        lon_line = next((l for l in comments if "!longitude:" in l), "")
        lat = float(lat_line.split(":")[1].strip()) if lat_line else None
        lon = float(lon_line.split(":")[1].strip()) if lon_line else None
        return name, lat, lon
    except Exception:
        return None, None, None

def main():
    normalized = load_normalized_names(NORMALIZATION_FILE)
    all_markers = []
    total_blocks = 0
    skipped_blocks = 0

    for input_file in INPUT_FILES:
        log(f"🔍 Verarbeite Datei: {input_file}")
        blocks = parse_blocks_from_file(input_file)
        total_blocks += len(blocks)

        for block in blocks:
            name, lat, lon = extract_station_info(block)
            if not name or lat is None or lon is None:
                log(f"⚠️  Ungültiger Block übersprungen in Datei: {input_file}")
                log(f"   Name: {name} | Lat: {lat} | Lon: {lon}")
                log(f"   Blockinhalt (erste Zeilen):")
                for line in block[:5]:
                    log(f"     {line}")
                skipped_blocks += 1
                continue

            safe_name = normalized.get(name, normalize_filename(name))
            js_name = escape_js_string(name)

            popup_html = (
                f"<b>{name}</b><br>"
                f"<small><i>{input_file}</i></small><br>"
                f"<a href='#' onclick=\\\"generateAndOpen('{js_name}', '{safe_name}'); return false;\\\">🌊 Vorhersage anzeigen</a>"
            )

            marker_code = f'L.marker([{lat}, {lon}]).bindPopup("{popup_html}").addTo(markers);'
            all_markers.append(marker_code)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("// Automatisch generiert – bitte nicht manuell bearbeiten!\\n")
        f.write("var markers = L.markerClusterGroup();\\n")
        f.write("\\n".join(all_markers))
        f.write("\\nmap.addLayer(markers);\\n")

    log(f"✅ Total markers generated: {len(all_markers)}")
    log(f"📦 Gesamtblöcke verarbeitet: {total_blocks}")
    log(f"🚫 Übersprungene Blöcke: {skipped_blocks}")

    with open(LOG_FILE, "w", encoding="utf-8") as log_f:
        log_f.write("\\n".join(log_entries))

if __name__ == "__main__":
    main()
