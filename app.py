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


def _find_station_line(lines, station_name, expected_lat=None, expected_lon=None):
    """Return index of the name line matching station_name.

    Without expected_lat/lon: returns the first match (legacy behavior).
    With expected_lat/lon: returns the name-match whose # !latitude: /
    # !longitude: comments are closest to the expected coordinates. This
    disambiguates duplicate names even when marker coords were rounded or
    perturbed by the cluster layer.
    """
    candidates = []
    for i, line in enumerate(lines):
        if line.rstrip() != station_name:
            continue
        if expected_lat is None or expected_lon is None:
            return i
        lat = lon = None
        for j in range(i - 1, max(i - 30, -1), -1):
            s = lines[j]
            if lat is None and s.startswith("# !latitude:"):
                try: lat = float(s.split(":", 1)[1].strip())
                except ValueError: pass
            elif lon is None and s.startswith("# !longitude:"):
                try: lon = float(s.split(":", 1)[1].strip())
                except ValueError: pass
            if lat is not None and lon is not None:
                break
        if lat is not None and lon is not None:
            d2 = (lat - expected_lat) ** 2 + (lon - expected_lon) ** 2
            candidates.append((d2, i))
    if not candidates:
        return None
    candidates.sort()
    return candidates[0][1]


def update_coords_in_txt(txt_path, station_name, new_lat, new_lon,
                         expected_lat=None, expected_lon=None):
    """Update latitude/longitude for a station in a harmonics .txt file (ISO-8859-1)."""
    with open(txt_path, "r", encoding="iso-8859-1") as f:
        lines = f.readlines()

    i = _find_station_line(lines, station_name, expected_lat, expected_lon)
    if i is None:
        return False
    for j in range(i - 1, max(i - 30, -1), -1):
        if lines[j].startswith("# !latitude:"):
            lines[j] = f"# !latitude: {new_lat:.4f}\n"
        elif lines[j].startswith("# !longitude:"):
            lines[j] = f"# !longitude: {new_lon:.4f}\n"

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


def delete_station_from_txt(txt_path, station_name,
                            expected_lat=None, expected_lon=None):
    """Delete a station and its entire data block from a harmonics .txt file."""
    num_constituents = get_num_constituents(txt_path)
    if num_constituents is None:
        return False

    with open(txt_path, "r", encoding="iso-8859-1") as f:
        lines = f.readlines()

    name_idx = _find_station_line(lines, station_name, expected_lat, expected_lon)
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
    """Remove a station from leaflet_markers.js and decrement group counts.

    The generator writes 6 lines per station:
      stationCoords['Name'] = ...;
      stationSources['Name'] = ...;
      var mN = L.marker(...);
      mN.bindPopup("<b>Name</b>...");
      grp_all_tide.addLayer(mN);         (or grp_all_current)
      src_<Group>_tide.push(mN);         (or _current)
    """
    with open(MARKERS_JS, "r", encoding="utf-8") as f:
        js_lines = f.readlines()

    coord_key = station_name.replace("\\", "\\\\").replace("'", "\\'")
    display_name = station_name.replace('"', '&quot;')

    indices_to_remove = set()
    # Per src_var count: tide/current station deletions attributed to each group
    deletions_per_src = {}
    for i, line in enumerate(js_lines):
        if f"stationCoords['{coord_key}']" in line:
            indices_to_remove.add(i)
        elif f"stationSources['{coord_key}']" in line:
            indices_to_remove.add(i)
        elif f"<b>{display_name}</b>" in line:
            indices_to_remove.add(i)
            if i > 0:
                indices_to_remove.add(i - 1)  # var mN = L.marker(...)
            if i + 1 < len(js_lines):
                indices_to_remove.add(i + 1)  # grp_all_*.addLayer(mN)
            if i + 2 < len(js_lines):
                indices_to_remove.add(i + 2)  # src_*.push(mN)
                m = re.match(r"(src_\w+_(?:tide|current))\.push\(",
                             js_lines[i + 2].strip())
                if m:
                    deletions_per_src[m.group(1)] = \
                        deletions_per_src.get(m.group(1), 0) + 1

    if not indices_to_remove:
        return False

    js_lines = [ln for idx, ln in enumerate(js_lines)
                if idx not in indices_to_remove]

    # Decrement group counts in tideGroups/currentGroups and the header totals
    tide_deletions = sum(n for s, n in deletions_per_src.items()
                         if s.endswith("_tide"))
    current_deletions = sum(n for s, n in deletions_per_src.items()
                            if s.endswith("_current"))

    for src_var, n in deletions_per_src.items():
        count_pattern = re.compile(
            r"(count:)(\d+)([^}]*?markers:" + re.escape(src_var) + r"\b)"
        )
        for idx, line in enumerate(js_lines):
            if f"markers:{src_var}," in line:
                js_lines[idx] = count_pattern.sub(
                    lambda m: f"{m.group(1)}{int(m.group(2)) - n}{m.group(3)}",
                    line,
                    count=1,
                )
                break

    for header, n in (("Tides", tide_deletions), ("Currents", current_deletions)):
        if n == 0:
            continue
        header_pattern = re.compile(rf"buildSection\('{header} \((\d+)\)")
        for idx, line in enumerate(js_lines):
            m = header_pattern.search(line)
            if m:
                js_lines[idx] = line.replace(
                    f"{header} ({m.group(1)})",
                    f"{header} ({int(m.group(1)) - n})",
                    1,
                )
                break

    with open(MARKERS_JS, "w", encoding="utf-8") as f:
        f.writelines(js_lines)
    return True


def rename_station_in_txt(txt_path, old_name, new_name,
                          expected_lat=None, expected_lon=None):
    """Rename a station in a harmonics .txt file (ISO-8859-1)."""
    with open(txt_path, "r", encoding="iso-8859-1") as f:
        lines = f.readlines()

    i = _find_station_line(lines, old_name, expected_lat, expected_lon)
    if i is None:
        return False
    lines[i] = new_name + "\n"

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
    """Update coordinates for a station directly in leaflet_markers.js.

    Generator writes 6 lines per station; we update line N (stationCoords)
    and line N+2 (var mX = L.marker([lat, lon], ...)). Strictly line-based
    so a regex can never accidentally cross station boundaries.
    """
    with open(MARKERS_JS, "r", encoding="utf-8") as f:
        js_lines = f.readlines()

    coord_key = station_name.replace("\\", "\\\\").replace("'", "\\'")
    needle = f"stationCoords['{coord_key}'] = ["

    updated = False
    for i, line in enumerate(js_lines):
        if not line.startswith(needle):
            continue
        js_lines[i] = f"{needle}{new_lat}, {new_lon}];\n"
        if i + 2 < len(js_lines):
            js_lines[i + 2] = re.sub(
                r"(L\.marker\()\[[^\]]+\]",
                rf"\g<1>[{new_lat}, {new_lon}]",
                js_lines[i + 2],
                count=1,
            )
        updated = True

    if updated:
        with open(MARKERS_JS, "w", encoding="utf-8") as f:
            f.writelines(js_lines)


TRANSLITERATION = {
    # German
    'ä': 'ae', 'ö': 'oe', 'ü': 'ue', 'ß': 'ss',
    'Ä': 'Ae', 'Ö': 'Oe', 'Ü': 'Ue',
    # Scandinavian
    'ø': 'oe', 'Ø': 'Oe', 'å': 'aa', 'Å': 'Aa', 'æ': 'ae', 'Æ': 'Ae',
    # Polish
    'ł': 'l', 'Ł': 'L',
    # Icelandic
    'ð': 'd', 'Ð': 'D', 'þ': 'th', 'Þ': 'Th',
}


# Unicode-Normalisierung + Transliteration + ASCII für Dateinamen/URLs
def normalize_filename(name: str) -> str:
    for char, repl in TRANSLITERATION.items():
        name = name.replace(char, repl)
    name = unicodedata.normalize('NFKD', name)
    name = name.encode('ascii', 'ignore').decode('ascii')
    name = re.sub(r"['\\\\/]", "", name)
    name = re.sub(r"[\s,]+", "_", name)
    return name.lower()

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

def to_slug(name):
    """Convert station name to SEO-friendly slug: 'Douala, Cameroon' → 'douala-cameroon'."""
    slug = name
    for char, repl in TRANSLITERATION.items():
        slug = slug.replace(char, repl)
    slug = unicodedata.normalize('NFKD', slug)
    slug = slug.encode('ascii', 'ignore').decode('ascii')
    slug = re.sub(r"['\\\\/]", "", slug)
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", slug)
    slug = slug.strip("-").lower()
    return slug

# Reverse lookup: slug → original station name
_slug_to_station = {}
for _name in _station_names:
    _slug_to_station[to_slug(_name)] = _name

@app.route("/")
def index():
    return render_template("index.html", station_names=_station_names)

@app.route("/favicon.ico")
def favicon():
    return send_from_directory("static", "favicon.ico", mimetype="image/x-icon")

def _resolve_station(station, source=None, utc=False):
    """Decode station name and compute safe filenames + source suffix."""
    decoded_station = unquote(station)
    safe_station = normalized.get(decoded_station, normalize_filename(decoded_station))
    if source:
        skey = source.replace('.tcd', '')
        skey = re.sub(r'^harmonics[-_]', '', skey)
        skey = skey.replace('_mod', '')
        safe_station = safe_station + '__' + skey
    if utc:
        safe_station = safe_station + '__utc'
    svg_filename = f"tide_prediction_{safe_station}.svg"
    html_filename = f"tide_prediction_{safe_station}.html"
    return decoded_station, safe_station, svg_filename, html_filename


def _is_fresh_today(filepath):
    """Check if file exists and was last modified today."""
    if not os.path.exists(filepath):
        return False
    mtime = datetime.fromtimestamp(os.path.getmtime(filepath))
    return mtime.date() == datetime.now().date()


def _generate_prediction(decoded_station, station_raw, source, svg_filename, html_filename, utc=False):
    """Generate SVG + HTML prediction files. Returns html_path."""
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

    tz_flag = ["-z"] if utc else []
    current_date = datetime.now().strftime("%Y-%m-%d 00:00")
    cmd = [
        "tide",
        "-l", decoded_station,
        "-b", current_date,
        "-f", "v",
        "-m", "g",
        "-o", svg_path,
        *tz_flag,
    ]

    print("➤ Aufruf von tide:")
    print(" ", " ".join(cmd))

    subprocess.run(cmd, capture_output=True, text=True, check=True, env=env)
    print("✅ tide wurde erfolgreich ausgeführt.")

    # Konvertierung der SVG-Kodierung
    with open(svg_path, "rb") as f:
        raw = f.read()
    with open(svg_path, "w", encoding="utf-8") as f:
        f.write(raw.decode("iso-8859-1"))
    print(f"✅ SVG-Datei konvertiert: {svg_path}")

    # Zusätzlich: tide -l "Station" -m a → als Key-Value-Liste
    try:
        meta_cmd = ["tide", "-l", decoded_station, "-m", "a", *tz_flag]
        meta_result = subprocess.run(meta_cmd, capture_output=True, text=True, check=True, env=env)
        meta_rows = []
        for line in meta_result.stdout.strip().splitlines():
            key = line[:14].strip()
            val = line[14:].strip()
            if key:
                meta_rows.append((key, val))
        meta_info = meta_rows
    except subprocess.CalledProcessError:
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
            "-em", "x",
            *tz_flag,
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
            is_current = ('Max Flood' in rest or 'Max Ebb' in rest or
                          'Min Flood' in rest or 'Min Ebb' in rest or
                          'Slack, Flood Begins' in rest or 'Slack, Ebb Begins' in rest)
            is_sun = rest in ('Sunrise', 'Sunset')
            is_moon = rest in ('Moonrise', 'Moonset', 'New Moon',
                               'First Quarter', 'Full Moon', 'Last Quarter')
            # Show date only on first row of each day
            show_date = date_str != last_date
            last_date = date_str
            # Parse tide/current value and type
            if is_tide or is_current:
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
            row_type = 'tide' if (is_tide or is_current) else 'astro'
            icons = {
                'High Tide': '\u25b2',              # ▲
                'Low Tide': '\u25bc',               # ▼
                'Max Flood': '\u27a1',              # ➡
                'Max Ebb': '\u2b05',                # ⬅
                'Min Flood': '\u27a1',              # ➡
                'Min Ebb': '\u2b05',                # ⬅
                'Slack, Flood Begins': '\u23f8',    # ⏸
                'Slack, Ebb Begins': '\u23f8',      # ⏸
                'Sunrise': '\u2600',                # ☀
                'Sunset': '\u25cb',                 # ○
                'Moonrise': '\u263d',               # ☽
                'Moonset': '\u263e',                # ☾
                'New Moon': '\u25cf',               # ●
                'First Quarter': '\u25d0',          # ◐
                'Full Moon': '\u25cb',              # ○
                'Last Quarter': '\u25d1',           # ◑
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
    except subprocess.CalledProcessError:
        tide_rows = []

    # HTML-Datei erzeugen
    is_current_station = decoded_station.rstrip().endswith('Current')
    with open(TEMPLATE_PATH, encoding="utf-8") as f:
        template = f.read()
    svg_url = f"/static/images/{svg_filename}"
    html = render_template_string(template,
                                  station=decoded_station,
                                  original_name=station_raw,
                                  svg_url=svg_url,
                                  meta_info=meta_info,
                                  tide_rows=tide_rows,
                                  is_current=is_current_station,
                                  station_names=_station_names,
                                  utc=utc,
                                  src=source)
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"✅ HTML-Seite erzeugt: {html_path}")
    return html_path


@app.route("/prediction/<slug>")
def show_prediction(slug):
    """Serve a prediction page, regenerating if stale (not from today)."""
    try:
        source = request.args.get('source')
        utc = request.args.get('utc') == '1'

        # Resolve slug to original station name
        station_name = _slug_to_station.get(slug)
        if not station_name:
            return "Station nicht gefunden.", 404

        decoded_station, safe_station, svg_filename, html_filename = _resolve_station(station_name, source, utc)
        html_path = os.path.join(PREDICTIONS_DIR, html_filename)

        if not _is_fresh_today(html_path):
            print(f"➤ Prediction veraltet oder nicht vorhanden: {decoded_station}")
            _generate_prediction(decoded_station, station_name, source, svg_filename, html_filename, utc=utc)
        else:
            print(f"➤ Prediction aktuell (Cache-Hit): {decoded_station}")

        with open(html_path, encoding="utf-8") as f:
            return f.read()

    except subprocess.CalledProcessError as e:
        print("❌ Fehler beim Aufruf von tide:")
        print(e.stderr)
        return "Fehler beim Erzeugen der Vorhersage.", 500
    except Exception as e:
        print(f"❌ Unerwarteter Fehler: {e}")
        return "Interner Fehler", 500


@app.route("/generate/<station>")
def generate_tide_prediction(station):
    try:
        source = request.args.get('source')
        utc = request.args.get('utc') == '1'
        decoded_station, safe_station, svg_filename, html_filename = _resolve_station(station, source, utc)

        print(f"➤ Angeforderte Station: {decoded_station}")
        print(f"➤ Normalisierter Dateiname: {safe_station}")
        if source:
            print(f"➤ Quelle: {source}")

        html_path = os.path.join(PREDICTIONS_DIR, html_filename)

        if not _is_fresh_today(html_path):
            _generate_prediction(decoded_station, station, source, svg_filename, html_filename, utc=utc)
        else:
            print(f"➤ Prediction aktuell (Cache-Hit): {decoded_station}")

        # URL zur dynamischen Route zurückgeben
        params = []
        if source: params.append(f"source={source}")
        if utc: params.append("utc=1")
        query = ("?" + "&".join(params)) if params else ""
        slug = to_slug(decoded_station)
        final_url = f"/prediction/{slug}{query}"
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
        old_lat = data.get("old_lat")
        old_lon = data.get("old_lon")
        old_lat = float(old_lat) if old_lat is not None else None
        old_lon = float(old_lon) if old_lon is not None else None

        if not station or not tcd_file:
            return jsonify(error="station und source sind Pflichtfelder"), 400

        # Quelldatei finden
        txt_path = find_txt_for_tcd(tcd_file)
        if not txt_path:
            return jsonify(error=f"Keine .txt-Datei gefunden für {tcd_file}"), 404

        print(f"DEBUG /update_coordinates: station={station!r} old=({old_lat},{old_lon}) new=({new_lat},{new_lon}) file={tcd_file}")
        # Koordinaten in .txt aktualisieren
        if not update_coords_in_txt(txt_path, station, new_lat, new_lon,
                                    expected_lat=old_lat, expected_lon=old_lon):
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
        old_lat = data.get("old_lat")
        old_lon = data.get("old_lon")
        old_lat = float(old_lat) if old_lat is not None else None
        old_lon = float(old_lon) if old_lon is not None else None

        if not old_name or not new_name or not tcd_file:
            return jsonify(error="old_name, new_name und source sind Pflichtfelder"), 400

        if old_name == new_name:
            return jsonify(error="Name ist unverändert"), 400

        # Quelldatei finden
        txt_path = find_txt_for_tcd(tcd_file)
        if not txt_path:
            return jsonify(error=f"Keine .txt-Datei gefunden für {tcd_file}"), 404

        print(f"DEBUG /update_station_name: old_name={old_name!r} new_name={new_name!r} old=({old_lat},{old_lon}) file={tcd_file}")
        # Name in .txt aktualisieren
        if not rename_station_in_txt(txt_path, old_name, new_name,
                                     expected_lat=old_lat, expected_lon=old_lon):
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
        old_lat = data.get("old_lat")
        old_lon = data.get("old_lon")
        old_lat = float(old_lat) if old_lat is not None else None
        old_lon = float(old_lon) if old_lon is not None else None

        if not station or not tcd_file:
            return jsonify(error="station und source sind Pflichtfelder"), 400

        # Quelldatei finden
        txt_path = find_txt_for_tcd(tcd_file)
        if not txt_path:
            return jsonify(error=f"Keine .txt-Datei gefunden für {tcd_file}"), 404

        # Station aus .txt löschen
        if not delete_station_from_txt(txt_path, station,
                                       expected_lat=old_lat, expected_lon=old_lon):
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
