from flask import Flask, send_file, request
from datetime import datetime
import subprocess
import os
import unicodedata
import re

app = Flask(__name__)

def normalize_filename(name: str) -> str:
    # Unicode-Zerlegung, z. B. é → e
    name = unicodedata.normalize('NFKD', name)
    name = name.encode('ascii', 'ignore').decode('ascii')
    name = re.sub(r"[\s,]+", "_", name)
    return name

@app.route("/")
def index():
    return send_file("static/index.html")

@app.route("/generate/<station>")
def generate_tide_prediction(station):
    try:
        decoded_station = station  # z. B. "Fécamp, France"
        safe_station = normalize_filename(decoded_station)  # z. B. "Fecamp_France"

        os.makedirs("static/images", exist_ok=True)
        os.makedirs("static/predictions", exist_ok=True)

        svg_filename = f"tide_prediction_{safe_station}.svg"
        svg_path = os.path.join("static/images", svg_filename)

        current_date = datetime.now().strftime("%Y-%m-%d 00:00")

        cmd = [
            "tide",
            "-l", decoded_station,
            "-b", current_date,
            "-f", "v",
            "-m", "g",
            "-o", svg_path
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            return f"Fehler beim Ausführen von 'tide': {result.stderr}", 500

        with open("templates/tide_prediction_template.html", encoding="utf-8") as f:
            template = f.read()

        # Originalname (z. B. mit é) für die Überschrift
        html_output = template.replace("<!--Stationssname-->", safe_station)
        html_output = html_output.replace("<!--Originalname-->", decoded_station)

        html_filename = f"tide_prediction_{safe_station}.html"
        html_path = os.path.join("static/predictions", html_filename)

        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html_output)

        return "OK"

    except Exception as e:
        return f"Interner Serverfehler: {str(e)}", 500

if __name__ == "__main__":
    app.run(debug=True)