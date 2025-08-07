import os
import re
import unicodedata
from flask import Flask, send_file, abort, render_template_string
from urllib.parse import unquote

app = Flask(__name__)

# -- 1. Funktion für sichere Dateinamen (wie im Marker-Skript) --
def normalize_filename(name: str) -> str:
    name = unicodedata.normalize('NFKD', name)
    name = name.encode('ascii', 'ignore').decode('ascii')
    name = re.sub(r"[\s,]+", "_", name)
    return name

# -- 2. Optional: Normalisierte Namen aus Datei laden --
normalized = {}
if os.path.exists("normalized_station_names.txt"):
    with open("normalized_station_names.txt", encoding="utf-8") as f:
        for line in f:
            if " → " in line:
                orig, norm = line.strip().split(" → ", 1)
                normalized[orig] = norm

# -- 3. Indexseite --
@app.route("/")
def index():
    return send_file("static/index.html")

# -- 4. Vorhersageerzeugung --
@app.route("/generate/<station>")
def generate_tide_prediction(station):
    try:
        decoded_station = unquote(station)
        safe_station = normalized.get(decoded_station, normalize_filename(decoded_station))

        output_path = f"static/predictions/tide_prediction_{safe_station}.html"
        print(f"🌀 Generiere Vorhersage für: {decoded_station} → {output_path}")

        if not os.path.exists("static/predictions"):
            os.makedirs("static/predictions")

        # -- Template laden und anwenden --
        template_path = "templates/tide_prediction_template.html"
        with open(template_path, encoding="utf-8") as tf:
            template = tf.read()

        html = render_template_string(template, station=decoded_station)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html)

        return "", 200

    except Exception as e:
        print(f"❌ Fehler bei Erzeugung: {e}")
        return abort(500)

# -- 5. Lokalen Server starten (bei Aufruf per python3 app.py) --
if __name__ == "__main__":
    app.run(debug=True)

