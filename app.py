import os
import re
import unicodedata
import subprocess
from datetime import datetime
import glob
from flask import Flask, render_template, render_template_string, abort, jsonify, url_for, request
from urllib.parse import unquote

app = Flask(__name__)

# Direktories
PREDICTIONS_DIR = "static/predictions"
IMAGES_DIR = "static/images"
TEMPLATE_PATH = "templates/tide_prediction_template.html"
HARMONICS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "harmonics")
TCD_DIR = "/usr/share/xtide"
MARKERS_JS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "js", "leaflet_markers.js")


def find_txt_for_tcd(tcd_basename):
    """Map a TCD filename (e.g. harmonics-dwf-20070318_mod.tcd) to its .txt source."""
    stem = os.path.splitext(tcd_basename)[0]  # e.g. harmonics-dwf-20070318_mod
    for subdir in ["classic", "utide", "ticon", "ihm"]:
        txt_path = os.path.join(HARMONICS_DIR, subdir, stem + ".txt")
        if os.path.exists(txt_path):
            return txt_path
    return None


def update_coords_in_txt(txt_path, station_name, new_lat, new_lon):
    """Update latitude/longitude for a station in a harmonics .txt file (ISO-8859-1)."""
    with open(txt_path, "r", encoding="iso-8859-1") as f:
        lines = f.readlines()

    # Find the station name line, then look backwards for # !latitude: and # !longitude:
    found = False
    for i, line in enumerate(lines):
        stripped = line.rstrip("\n").rstrip("\r")
        if stripped == station_name:
            # Search backwards for the coordinate comments
            for j in range(i - 1, max(i - 20, -1), -1):
                if lines[j].startswith("# !latitude:"):
                    lines[j] = f"# !latitude: {new_lat:.4f}\n"
                elif lines[j].startswith("# !longitude:"):
                    lines[j] = f"# !longitude: {new_lon:.4f}\n"
            found = True
            break

    if not found:
        return False

    with open(txt_path, "w", encoding="iso-8859-1") as f:
        f.writelines(lines)
    return True


def rebuild_tcd(txt_path, tcd_basename):
    """Recompile a harmonics .txt file to .tcd."""
    tcd_path = os.path.join(TCD_DIR, tcd_basename)
    subprocess.run(["build_tide_db", tcd_path, txt_path], check=True)


def update_markers_js(station_name, new_lat, new_lon):
    """Update coordinates for a station directly in leaflet_markers.js."""
    with open(MARKERS_JS, "r", encoding="utf-8") as f:
        content = f.read()

    # Escape station name for use in regex
    escaped = re.escape(station_name)

    # Update stationCoords['Name'] = [lat, lon];
    content = re.sub(
        rf"(stationCoords\['{escaped}'\] = \[)[^\]]+(\];)",
        rf"\g<1>{new_lat}, {new_lon}\2",
        content
    )
    # Update L.marker([lat, lon], ...) — match the line that has the station popup right after
    # The marker line is always directly before the bindPopup line containing the station name
    content = re.sub(
        rf"(var m\d+ = L\.marker\()(\[[^\]]+\])(.*\n[^\n]*{escaped})",
        rf"\g<1>[{new_lat}, {new_lon}]\3",
        content
    )

    with open(MARKERS_JS, "w", encoding="utf-8") as f:
        f.write(content)


# Unicode-Normalisierung + ASCII + Ersetzung für Dateinamen
def normalize_filename(name: str) -> str:
    name = unicodedata.normalize('NFKD', name)
    name = name.encode('ascii', 'ignore').decode('ascii')
    name = re.sub(r"['\\\\/]", "", name)
    name = re.sub(r"[\s,]+", "_", name)
    return name

# Optional: Mapping aus Datei laden
normalized = {}
if os.path.exists("normalized_station_names.txt"):
    with open("normalized_station_names.txt", encoding="utf-8") as f:
        for line in f:
            if " = " in line:
                orig, norm = line.strip().split(" = ", 1)
                normalized[orig] = norm

def load_station_names():
    """Extract station names from the generated leaflet_markers.js file."""
    markers_path = os.path.join("static", "js", "leaflet_markers.js")
    names = []
    if os.path.exists(markers_path):
        with open(markers_path, encoding="utf-8") as f:
            for line in f:
                m = re.search(r'<b>([^<]+)</b>', line)
                if m:
                    names.append(m.group(1))
    return names

_station_names = load_station_names()

@app.route("/")
def index():
    return render_template("index.html", station_names=_station_names)

@app.route("/generate/<station>")
def generate_tide_prediction(station):
    try:
        decoded_station = unquote(station)
        safe_station = normalized.get(decoded_station, normalize_filename(decoded_station))

        print(f"➤ Angeforderte Station: {decoded_station}")
        print(f"➤ Normalisierter Dateiname: {safe_station}")

        svg_filename = f"tide_prediction_{safe_station}.svg"
        html_filename = f"tide_prediction_{safe_station}.html"
        svg_path = os.path.join(IMAGES_DIR, svg_filename)
        html_path = os.path.join(PREDICTIONS_DIR, html_filename)

        os.makedirs(PREDICTIONS_DIR, exist_ok=True)
        os.makedirs(IMAGES_DIR, exist_ok=True)

        if os.path.exists(svg_path):
            os.remove(svg_path)
            print(f"🗑️ Alte SVG-Datei gelöscht: {svg_path}")

        current_date = datetime.now().strftime("%Y-%m-%d 00:00")
        cmd = [
            "tide",
            "-l", decoded_station,
            "-b", current_date,
            "-f", "v",
            "-m", "g",
            "-o", svg_path
        ]

        print("➤ Aufruf von tide:")
        print(" ", " ".join(cmd))

        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        print("✅ tide wurde erfolgreich ausgeführt.")

        # Konvertierung der SVG-Kodierung
        with open(svg_path, "rb") as f:
            raw = f.read()
        with open(svg_path, "w", encoding="utf-8") as f:
            f.write(raw.decode("iso-8859-1"))
        print(f"✅ SVG-Datei konvertiert: {svg_path}")

        # Zusätzlich: tide -l "Station" -m a
        try:
            meta_cmd = ["tide", "-l", decoded_station, "-m", "a"]
            meta_result = subprocess.run(meta_cmd, capture_output=True, text=True, check=True)
            meta_info = meta_result.stdout.strip()
        except subprocess.CalledProcessError as e:
            meta_info = f"❌ Fehler bei 'tide -m a': {e.stderr.strip()}"

        # HTML-Datei erzeugen
        with open(TEMPLATE_PATH, encoding="utf-8") as f:
            template = f.read()
        svg_url = f"/static/images/{svg_filename}"
        html = render_template_string(template,
                                      station=decoded_station,
                                      original_name=station,
                                      svg_url=svg_url,
                                      meta_info=meta_info,
                                      station_names=_station_names)
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"✅ HTML-Seite erzeugt: {html_path}")

        # Final-URL als JSON an den Client zurückgeben
        rel_path = os.path.join("predictions", html_filename)
        final_url = url_for('static', filename=rel_path)
        return jsonify(url=final_url)

    except subprocess.CalledProcessError as e:
        print("❌ Fehler beim Aufruf von tide:")
        print(e.stderr)
        return "Fehler beim Erzeugen der Vorhersage.", 500
    except Exception as e:
        print(f"❌ Unerwarteter Fehler: {e}")
        return "Interner Fehler", 500

@app.route("/update_coordinates", methods=["POST"])
def update_coordinates():
    try:
        data = request.get_json()
        station = data.get("station")
        new_lat = float(data.get("lat"))
        new_lon = float(data.get("lon"))
        tcd_file = data.get("source")

        if not station or not tcd_file:
            return jsonify(error="station und source sind Pflichtfelder"), 400

        # Quelldatei finden
        txt_path = find_txt_for_tcd(tcd_file)
        if not txt_path:
            return jsonify(error=f"Keine .txt-Datei gefunden für {tcd_file}"), 404

        # Koordinaten in .txt aktualisieren
        if not update_coords_in_txt(txt_path, station, new_lat, new_lon):
            return jsonify(error=f"Station '{station}' nicht in {txt_path} gefunden"), 404

        # TCD neu kompilieren
        rebuild_tcd(txt_path, tcd_file)

        # Marker-JS aktualisieren
        update_markers_js(station, new_lat, new_lon)

        print(f"✅ Koordinaten aktualisiert: {station} → {new_lat:.4f}, {new_lon:.4f} (in {txt_path})")
        return jsonify(ok=True, lat=new_lat, lon=new_lon)

    except Exception as e:
        print(f"❌ Fehler beim Aktualisieren der Koordinaten: {e}")
        return jsonify(error=str(e)), 500


if __name__ == "__main__":
    app.run(debug=True)
