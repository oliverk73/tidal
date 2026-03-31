import os
import re
import tempfile
import unicodedata
import subprocess
from datetime import datetime, timedelta
import glob
from flask import Flask, render_template, render_template_string, abort, jsonify, url_for, request, send_from_directory
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

    # Atomic write: temp file + rename to prevent truncation
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(txt_path), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="iso-8859-1") as f:
            f.writelines(lines)
        os.replace(tmp, txt_path)
    except:
        os.unlink(tmp)
        raise
    return True


def rebuild_tcd(txt_path, tcd_basename):
    """Recompile a harmonics .txt file to .tcd."""
    tcd_path = os.path.join(TCD_DIR, tcd_basename)
    subprocess.run(["build_tide_db", tcd_path, txt_path], check=True)


def get_num_constituents(txt_path):
    """Read the number of constituents from the harmonics file header."""
    with open(txt_path, "r", encoding="iso-8859-1") as f:
        prev_line = ""
        for line in f:
            if prev_line.strip() == "# Number of constituents":
                return int(line.strip())
            prev_line = line
    return None


def delete_station_from_txt(txt_path, station_name):
    """Delete a station and its entire data block from a harmonics .txt file."""
    num_constituents = get_num_constituents(txt_path)
    if num_constituents is None:
        return False

    with open(txt_path, "r", encoding="iso-8859-1") as f:
        lines = f.readlines()

    # Find the station name line
    name_idx = None
    for i, line in enumerate(lines):
        if line.rstrip("\n").rstrip("\r") == station_name:
            name_idx = i
            break

    if name_idx is None:
        return False

    # Block end: name line + 2 info lines + N constituent lines
    block_end = name_idx + 3 + num_constituents

    # Block start: scan backwards over comment lines (#) and blank lines
    block_start = name_idx
    for j in range(name_idx - 1, -1, -1):
        stripped = lines[j].strip()
        if stripped == "" or stripped.startswith("#"):
            block_start = j
        else:
            break

    # Delete the block
    del lines[block_start:block_end]

    # Atomic write: temp file + rename to prevent truncation
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(txt_path), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="iso-8859-1") as f:
            f.writelines(lines)
        os.replace(tmp, txt_path)
    except:
        os.unlink(tmp)
        raise
    return True


def delete_station_from_markers_js(station_name):
    """Remove a station from leaflet_markers.js."""
    with open(MARKERS_JS, "r", encoding="utf-8") as f:
        js_lines = f.readlines()

    coord_key = station_name.replace("\\", "\\\\").replace("'", "\\'")

    # Find and remove the 5 lines belonging to this station:
    # stationCoords['Name'] = ...;
    # stationSources['Name'] = ...;
    # var mN = L.marker(...);
    # mN.bindPopup("...");
    # markers.addLayer(mN);
    indices_to_remove = set()
    for i, line in enumerate(js_lines):
        if f"stationCoords['{coord_key}']" in line:
            indices_to_remove.add(i)
        elif f"stationSources['{coord_key}']" in line:
            indices_to_remove.add(i)
        elif f"<b>{station_name.replace(chr(34), '&quot;')}</b>" in line:
            # This is the bindPopup line — also remove the marker and addLayer lines
            indices_to_remove.add(i)
            # The L.marker line is directly before
            if i > 0:
                indices_to_remove.add(i - 1)
            # The markers.addLayer line is directly after
            if i + 1 < len(js_lines):
                indices_to_remove.add(i + 1)

    if not indices_to_remove:
        return False

    js_lines = [line for i, line in enumerate(js_lines) if i not in indices_to_remove]

    with open(MARKERS_JS, "w", encoding="utf-8") as f:
        f.writelines(js_lines)
    return True


def rename_station_in_txt(txt_path, old_name, new_name):
    """Rename a station in a harmonics .txt file (ISO-8859-1)."""
    with open(txt_path, "r", encoding="iso-8859-1") as f:
        lines = f.readlines()

    found = False
    for i, line in enumerate(lines):
        stripped = line.rstrip("\n").rstrip("\r")
        if stripped == old_name:
            lines[i] = new_name + "\n"
            found = True
            break

    if not found:
        return False

    # Atomic write: temp file + rename to prevent truncation
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(txt_path), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="iso-8859-1") as f:
            f.writelines(lines)
        os.replace(tmp, txt_path)
    except:
        os.unlink(tmp)
        raise
    return True


def rename_station_in_markers_js(old_name, new_name):
    """Rename a station in leaflet_markers.js — update all references."""
    with open(MARKERS_JS, "r", encoding="utf-8") as f:
        content = f.read()

    old_escaped = re.escape(old_name)
    new_display = new_name.replace('"', '&quot;')
    new_js = new_name.replace("\\", "\\\\").replace("'", "\\x27").replace('"', "\\x22")
    new_coord_key = new_name.replace("\\", "\\\\").replace("'", "\\'")
    old_coord_key = old_name.replace("\\", "\\\\").replace("'", "\\'")
    old_safe = normalize_filename(old_name)
    new_safe = normalize_filename(new_name)

    # stationCoords['Old'] → stationCoords['New']
    content = content.replace(
        f"stationCoords['{old_coord_key}']",
        f"stationCoords['{new_coord_key}']"
    )
    # stationSources['Old'] → stationSources['New']
    content = content.replace(
        f"stationSources['{old_coord_key}']",
        f"stationSources['{new_coord_key}']"
    )
    # Popup: <b>Old</b> → <b>New</b>
    content = content.replace(
        f"<b>{old_name.replace(chr(34), '&quot;')}</b>",
        f"<b>{new_display}</b>"
    )
    # Popup: encodeURIComponent('Old') → encodeURIComponent('New')
    old_js = old_name.replace("\\", "\\\\").replace("'", "\\x27").replace('"', "\\x22")
    content = content.replace(
        f"encodeURIComponent('{old_js}')",
        f"encodeURIComponent('{new_js}')"
    )
    # Popup: tide_prediction_OldSafe.html → tide_prediction_NewSafe.html
    content = content.replace(
        f"tide_prediction_{old_safe}.html",
        f"tide_prediction_{new_safe}.html"
    )

    with open(MARKERS_JS, "w", encoding="utf-8") as f:
        f.write(content)


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

@app.route("/favicon.ico")
def favicon():
    return send_from_directory("static", "favicon.ico", mimetype="image/x-icon")

@app.route("/generate/<station>")
def generate_tide_prediction(station):
    try:
        decoded_station = unquote(station)
        source = request.args.get('source')
        safe_station = normalized.get(decoded_station, normalize_filename(decoded_station))

        # Add source suffix for disambiguation when source is specified
        if source:
            skey = source.replace('.tcd', '')
            skey = re.sub(r'^harmonics[-_]', '', skey)
            skey = skey.replace('_mod', '')
            safe_station = safe_station + '__' + skey

        print(f"➤ Angeforderte Station: {decoded_station}")
        print(f"➤ Normalisierter Dateiname: {safe_station}")
        if source:
            print(f"➤ Quelle: {source}")

        svg_filename = f"tide_prediction_{safe_station}.svg"
        html_filename = f"tide_prediction_{safe_station}.html"
        svg_path = os.path.join(IMAGES_DIR, svg_filename)
        html_path = os.path.join(PREDICTIONS_DIR, html_filename)

        os.makedirs(PREDICTIONS_DIR, exist_ok=True)
        os.makedirs(IMAGES_DIR, exist_ok=True)

        if os.path.exists(svg_path):
            os.remove(svg_path)
            print(f"🗑️ Alte SVG-Datei gelöscht: {svg_path}")

        # Set HFILE_PATH to specific TCD file if source is specified
        env = None
        if source:
            tcd_path = os.path.join('/usr/share/xtide', source)
            if os.path.exists(tcd_path):
                env = os.environ.copy()
                env['HFILE_PATH'] = tcd_path

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

        result = subprocess.run(cmd, capture_output=True, text=True, check=True, env=env)
        print("✅ tide wurde erfolgreich ausgeführt.")

        # Konvertierung der SVG-Kodierung
        with open(svg_path, "rb") as f:
            raw = f.read()
        with open(svg_path, "w", encoding="utf-8") as f:
            f.write(raw.decode("iso-8859-1"))
        print(f"✅ SVG-Datei konvertiert: {svg_path}")

        # Zusätzlich: tide -l "Station" -m a → als Key-Value-Liste
        try:
            meta_cmd = ["tide", "-l", decoded_station, "-m", "a"]
            meta_result = subprocess.run(meta_cmd, capture_output=True, text=True, check=True, env=env)
            meta_rows = []
            for line in meta_result.stdout.strip().splitlines():
                key = line[:14].strip()
                val = line[14:].strip()
                if key:
                    meta_rows.append((key, val))
            meta_info = meta_rows
        except subprocess.CalledProcessError as e:
            meta_info = []

        # Textvorhersage: tide -l "Station" -b ... -e ... -f t -m p
        try:
            end_date = (datetime.now() + timedelta(days=5)).strftime("%Y-%m-%d %H:%M")
            text_cmd = [
                "tide", "-l", decoded_station,
                "-b", current_date,
                "-e", end_date,
                "-f", "t",
                "-m", "p",
                "-df", "%Y-%m-%d",
                "-tf", "%H:%M",
                "-em", "x"
            ]
            text_result = subprocess.run(text_cmd, capture_output=True, text=True, check=True, env=env)
            tide_rows = []
            last_date = None
            for line in text_result.stdout.strip().splitlines()[2:]:  # skip header
                line = line.strip()
                if not line:
                    continue
                # Format: "2026-03-30 05:43   2.08 meters  Low Tide"
                # or:     "2026-03-30 05:56   Moonset"
                parts = line.split(None, 2)
                if len(parts) < 3:
                    continue
                date_str = parts[0]
                time_str = parts[1]
                rest = parts[2].strip()
                # Determine event type
                is_tide = 'High Tide' in rest or 'Low Tide' in rest
                is_sun = rest in ('Sunrise', 'Sunset')
                is_moon = rest in ('Moonrise', 'Moonset', 'New Moon',
                                   'First Quarter', 'Full Moon', 'Last Quarter')
                # Show date only on first row of each day
                show_date = date_str != last_date
                last_date = date_str
                # Parse tide value and type
                if is_tide:
                    val_parts = rest.rsplit('  ', 1)
                    if len(val_parts) == 2:
                        value = val_parts[0].strip()
                        tide_type = val_parts[1].strip()
                    else:
                        value = ''
                        tide_type = rest
                else:
                    value = ''
                    tide_type = rest
                row_type = 'tide' if is_tide else 'astro'
                icons = {
                    'High Tide': '\u25b2',      # ▲
                    'Low Tide': '\u25bc',        # ▼
                    'Sunrise': '\u2600',         # ☀
                    'Sunset': '\u25cb',          # ○
                    'Moonrise': '\u263d',        # ☽
                    'Moonset': '\u263e',         # ☾
                    'New Moon': '\u25cf',        # ●
                    'First Quarter': '\u25d0',   # ◐
                    'Full Moon': '\u25cb',       # ○
                    'Last Quarter': '\u25d1',    # ◑
                }
                icon = icons.get(tide_type, '')
                tide_rows.append({
                    'date': date_str if show_date else '',
                    'time': time_str,
                    'value': value,
                    'type': tide_type,
                    'icon': icon,
                    'row_type': row_type
                })
        except subprocess.CalledProcessError as e:
            tide_rows = []

        # HTML-Datei erzeugen
        with open(TEMPLATE_PATH, encoding="utf-8") as f:
            template = f.read()
        svg_url = f"/static/images/{svg_filename}"
        html = render_template_string(template,
                                      station=decoded_station,
                                      original_name=station,
                                      svg_url=svg_url,
                                      meta_info=meta_info,
                                      tide_rows=tide_rows,
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


@app.route("/update_station_name", methods=["POST"])
def update_station_name():
    try:
        data = request.get_json()
        old_name = data.get("old_name")
        new_name = data.get("new_name", "").strip()
        tcd_file = data.get("source")

        if not old_name or not new_name or not tcd_file:
            return jsonify(error="old_name, new_name und source sind Pflichtfelder"), 400

        if old_name == new_name:
            return jsonify(error="Name ist unverändert"), 400

        # Quelldatei finden
        txt_path = find_txt_for_tcd(tcd_file)
        if not txt_path:
            return jsonify(error=f"Keine .txt-Datei gefunden für {tcd_file}"), 404

        # Name in .txt aktualisieren
        if not rename_station_in_txt(txt_path, old_name, new_name):
            return jsonify(error=f"Station '{old_name}' nicht in {txt_path} gefunden"), 404

        # TCD neu kompilieren
        rebuild_tcd(txt_path, tcd_file)

        # Marker-JS aktualisieren
        rename_station_in_markers_js(old_name, new_name)

        print(f"✅ Station umbenannt: '{old_name}' → '{new_name}' (in {txt_path})")
        return jsonify(ok=True, new_name=new_name)

    except Exception as e:
        print(f"❌ Fehler beim Umbenennen: {e}")
        return jsonify(error=str(e)), 500


@app.route("/delete_station", methods=["POST"])
def delete_station():
    try:
        data = request.get_json()
        station = data.get("station")
        tcd_file = data.get("source")

        if not station or not tcd_file:
            return jsonify(error="station und source sind Pflichtfelder"), 400

        # Quelldatei finden
        txt_path = find_txt_for_tcd(tcd_file)
        if not txt_path:
            return jsonify(error=f"Keine .txt-Datei gefunden für {tcd_file}"), 404

        # Station aus .txt löschen
        if not delete_station_from_txt(txt_path, station):
            return jsonify(error=f"Station '{station}' nicht in {txt_path} gefunden"), 404

        # TCD neu kompilieren
        rebuild_tcd(txt_path, tcd_file)

        # Marker aus JS entfernen
        delete_station_from_markers_js(station)

        print(f"🗑️ Station gelöscht: '{station}' (aus {txt_path})")
        return jsonify(ok=True)

    except Exception as e:
        print(f"❌ Fehler beim Löschen: {e}")
        return jsonify(error=str(e)), 500


if __name__ == "__main__":
    app.run(debug=True)
