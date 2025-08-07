import os
import re
import unicodedata
import subprocess
from datetime import datetime
from flask import Flask, send_file, abort, render_template_string
from urllib.parse import unquote

app = Flask(__name__)

def normalize_filename(name: str) -> str:
    name = unicodedata.normalize('NFKD', name)
    name = name.encode('ascii', 'ignore').decode('ascii')
    name = re.sub(r"[\s,]+", "_", name)
    return name

# Optional: normalisierte Namen laden
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

        print("➤ Angeforderte Station:", decoded_station)
        print("➤ Normalisierter Dateiname:", safe_station)

        html_path = f"static/predictions/tide_prediction_{safe_station}.html"
        svg_path = f"static/images/tide_prediction_{safe_station}.svg"
        svg_url = f"/static/images/tide_prediction_{safe_station}.svg"

        os.makedirs("static/predictions", exist_ok=True)
        os.makedirs("static/images", exist_ok=True)

        # 💡 Zeitstempel im Format: YYYY-MM-DD 00:00
        current_date = datetime.now().strftime("%Y-%m-%d 00:00")

        # ❗ SVG-Datei ggf. löschen, um doppelte XML-Blöcke zu vermeiden
        if os.path.exists(svg_path):
            os.remove(svg_path)
            print(f"🗑️ Vorhandene Datei gelöscht: {svg_path}")

        cmd = [
            "tide",
            "-l", decoded_station,
            "-b", current_date,
            "-f", "v",
            "-m", "g",
            "-o", svg_path
        ]

        print("➤ Aufruf von tide:\n", " ".join(cmd))

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            print("✅ tide wurde erfolgreich ausgeführt.")
        except subprocess.CalledProcessError as e:
            print("❌ Fehler beim Aufruf von tide:")
            print(e.stderr)
            return abort(500)

        if not os.path.exists(svg_path):
            print("❌ SVG-Datei wurde nicht erzeugt:", svg_path)
            return abort(500)
        else:
            print("✅ SVG-Datei erzeugt:", svg_path)

        # Template laden und HTML generieren
        template_path = "templates/tide_prediction_template.html"
        with open(template_path, encoding="utf-8") as tf:
            template = tf.read()

        html = render_template_string(
            template,
            station=decoded_station,
            original_name=station,
            svg_url=f"/static/images/tide_prediction_{safe_station}.svg"
        )

        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html)

        print("✅ HTML-Datei geschrieben:", html_path)
        return "", 200

    except Exception as e:
        print(f"❌ Unerwarteter Fehler:\n{e}")
        return abort(500)

if __name__ == "__main__":
    app.run(debug=True)
