import os
import re
import unicodedata
import subprocess
from datetime import datetime
from flask import Flask, render_template_string, send_file, abort
from urllib.parse import unquote

app = Flask(__name__)

# Direktories
PREDICTIONS_DIR = "static/predictions"
IMAGES_DIR = "static/images"
TEMPLATE_PATH = "templates/tide_prediction_template.html"

# Unicode-Normalisierung + ASCII + Ersetzung für Dateinamen
def normalize_filename(name: str) -> str:
    name = unicodedata.normalize('NFKD', name)
    name = name.encode('ascii', 'ignore').decode('ascii')
    name = re.sub(r"[\s,]+", "_", name)
    return name

# Optional: Mapping aus Datei laden
normalized = {}
if os.path.exists("normalized_station_names.txt"):
    with open("normalized_station_names.txt", encoding="utf-8") as f:
        for line in f:
            if " → " in line:
                orig, norm = line.strip().split(" → ", 1)
                normalized[orig] = norm

@app.route("/")
def index():
    return send_file("static/index.html")

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

        # HTML-Datei erzeugen
        with open(TEMPLATE_PATH, encoding="utf-8") as f:
            template = f.read()
        svg_url = f"/static/images/{svg_filename}"
        html = render_template_string(template,
                                      station=decoded_station,
                                      original_name=station,
                                      svg_url=svg_url)
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"✅ HTML-Seite erzeugt: {html_path}")

        return "OK"

    except subprocess.CalledProcessError as e:
        print("❌ Fehler beim Aufruf von tide:")
        print(e.stderr)
        return "Fehler beim Erzeugen der Vorhersage.", 500
    except Exception as e:
        print(f"❌ Unerwarteter Fehler: {e}")
        return "Interner Fehler", 500

if __name__ == "__main__":
    app.run(debug=True)
