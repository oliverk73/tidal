import os
import re
import json
import hashlib
import tempfile
import unicodedata
import subprocess
import shutil
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import glob
from flask import Flask, render_template, render_template_string, abort, jsonify, url_for, request, send_from_directory
from urllib.parse import unquote
from timezonefinder import TimezoneFinder

# Module-level TimezoneFinder: ~50 MB shapefile data, but only one instance.
# Used to convert UTC times for stations whose harmonics meridian is +00:00
# (all UTide-derived stations). Lookup is ~1 ms per call.
_tzfinder = TimezoneFinder()

app = Flask(__name__)

# Compress text responses (HTML, JSON, JS, CSS, XML, SVG) with brotli/gzip.
# leaflet_markers.js (17.8 MB) drops to ~3 MB gzipped, ~2 MB brotli.
try:
    from flask_compress import Compress
    app.config["COMPRESS_MIMETYPES"] = [
        "text/html", "text/css", "text/xml", "text/plain",
        "text/javascript",  # Flask sends static .js as text/javascript
        "application/json", "application/javascript", "application/xml",
        "image/svg+xml",
    ]
    app.config["COMPRESS_MIN_SIZE"] = 500
    app.config["COMPRESS_LEVEL"] = 6
    Compress(app)
except ImportError:
    pass  # Compression optional; install via `pip install flask-compress`

# Direktories
PREDICTIONS_DIR = "static/predictions"  # generated HTML + SVG (täglich purgen)
IMAGES_DIR = "static/images"  # permanente Assets (Logos, Marker-Icons, Geo-Daten)
SVG_DIR = PREDICTIONS_DIR  # generated tide grafiks (gleicher Lifecycle wie HTML)
TEMPLATE_PATH = "templates/tide_prediction_template.html"
HARMONICS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "harmonics")
TCD_DIR = "/usr/share/xtide"
MARKERS_JS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "js", "leaflet_markers.js")


def find_txt_for_tcd(tcd_basename):
    """Map a TCD filename (e.g. harmonics-dwf-20070318_mod.tcd) to its .txt source."""
    stem = os.path.splitext(tcd_basename)[0]  # e.g. harmonics-dwf-20070318_mod
    for subdir in ["classic", "att", "utide", "ticon", "ihm", "literature"]:
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


def _fsync_path(path):
    """fsync a file's contents to physical disk (e.g. after shutil.copyfile,
    which leaves the new data only in the OS page cache)."""
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _fsync_dir(path):
    """fsync the directory containing *path* so a rename into it is durable.

    A rename (os.replace) is only recorded in the directory's metadata; without
    fsyncing the directory the rename can be lost on a hard crash even if the
    new file's data was already flushed.
    """
    d = os.path.dirname(os.path.abspath(path)) or "."
    dirfd = os.open(d, os.O_RDONLY)
    try:
        os.fsync(dirfd)
    finally:
        os.close(dirfd)


def _atomic_write_durable(path, data, encoding):
    """Write *data* to *path* atomically AND durably.

    *data* may be a string or a list of lines. Writes to a temp file in the
    same directory, fsyncs the file's contents to physical disk, atomically
    renames it over the target, then fsyncs the directory so the rename itself
    is on disk.

    WICHTIG: Ohne die fsyncs liegt der neue Inhalt nur im OS-Page-Cache und
    geht bei Stromausfall / hartem Absturz (WSL2 + Windows) verloren – obwohl
    der Aufruf erfolgreich zurueckkehrte und die App "gespeichert" meldete.
    """
    d = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding=encoding) as f:
            if isinstance(data, str):
                f.write(data)
            else:
                f.writelines(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    _fsync_dir(path)


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

    # Atomic + durable write (survives a hard crash / power loss)
    _atomic_write_durable(txt_path, lines, "iso-8859-1")
    return True


def rebuild_tcd(txt_path, tcd_basename):
    """Recompile a harmonics .txt file to .tcd and replace the deployed TCD cleanly.

    WICHTIG: build_tide_db HAENGT an eine existierende TCD an, statt sie zu
    ueberschreiben. Wuerde man es direkt auf die System-TCD aufrufen, waechst
    diese bei jedem Speichern (Dubletten/Bloat, z.B. 3200 -> 25000+ Records).
    Daher: in eine frische Temp-Datei bauen (build_tide_db legt sie neu an) und
    den Inhalt in-place ueber die deployte TCD kopieren. Das ueberschreibt nur
    den Dateiinhalt (die .tcd in TCD_DIR gehoeren dem App-User) und braucht kein
    Schreibrecht auf das root-eigene Verzeichnis und kein sudo.
    """
    tcd_path = os.path.join(TCD_DIR, tcd_basename)
    fd, tmp = tempfile.mkstemp(suffix=".tcd")
    os.close(fd)
    os.unlink(tmp)  # build_tide_db muss die Datei frisch anlegen (sonst Append)
    try:
        subprocess.run(["build_tide_db", tmp, txt_path], check=True)
        shutil.copyfile(tmp, tcd_path)  # Inhalt in-place ersetzen (kein Verzeichnis-Schreibrecht noetig)
        _fsync_path(tcd_path)  # neue TCD durable auf die Platte zwingen (sonst nur Page-Cache)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


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

    # Atomic + durable write (survives a hard crash / power loss)
    _atomic_write_durable(txt_path, lines, "iso-8859-1")
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

    _atomic_write_durable(MARKERS_JS, js_lines, "utf-8")
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

    # Atomic + durable write (survives a hard crash / power loss)
    _atomic_write_durable(txt_path, lines, "iso-8859-1")
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

    _atomic_write_durable(MARKERS_JS, content, "utf-8")


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
        _atomic_write_durable(MARKERS_JS, js_lines, "utf-8")


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

COUNTRY_BY_SOURCE = {
    'harmonics-dwf-20251228-free.tcd': 'USA',
}


def display_name_for(name, source_file):
    """Append country suffix for sources that lack it in the harmonics file
    (e.g. DWF-2025 US stations). Display-only — original name unchanged."""
    if not source_file:
        return name
    country = COUNTRY_BY_SOURCE.get(source_file)
    if country and not name.endswith(f", {country}"):
        return f"{name}, {country}"
    return name


def load_station_data():
    """Read station name → source/coords pairs from leaflet_markers_data.json.
    Returns (sources_dict, coords_dict)."""
    json_path = os.path.join("static", "js", "leaflet_markers_data.json")
    sources = {}
    coords = {}
    if not os.path.exists(json_path):
        return sources, coords
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)
    for s in data.get("stations", []):
        # Row format: [displayName, lat, lon, source, groupIdx, isCurrent,
        #              slug, needsSource, origName]
        lat, lon, source = s[1], s[2], s[3]
        orig_name = s[8] if len(s) > 8 else s[0]
        sources[orig_name] = source
        coords[orig_name] = (float(lat), float(lon))
    return sources, coords


_station_data, _station_coords = load_station_data()
# Display names (with USA suffix where applicable) for autocomplete/index
_station_names = [display_name_for(n, s) for n, s in _station_data.items()]

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

# Reverse lookup: slug → original station name (used for tide CLI)
# Slug is computed from the *display* name so URLs match what the user sees,
# but the lookup returns the original name to keep tide -l working.
_slug_to_station = {}
for _orig, _src in _station_data.items():
    _disp = display_name_for(_orig, _src)
    _slug_to_station[to_slug(_disp)] = _orig
    # Also accept the original-name slug as fallback (back-compat for old bookmarks)
    _slug_to_station.setdefault(to_slug(_orig), _orig)

# Station -> sea/ocean lookup (built by py/build_station_seas.py from IHO Sea Areas).
# Used in SEO copy when xtide's water_body comment is unavailable.
_STATION_SEAS = {}
_seas_path = os.path.join("harmonics", "help", "station_seas.json")
if os.path.exists(_seas_path):
    try:
        with open(_seas_path, encoding="utf-8") as f:
            _STATION_SEAS = json.load(f)
        print(f"🌊 Loaded {len(_STATION_SEAS)} station-to-sea mappings")
    except (OSError, json.JSONDecodeError) as e:
        print(f"⚠️ Could not load station_seas.json: {e}")

def _markers_version():
    """Cache-Buster: mtime der Marker-Dateien -> bricht Browser-Cache bei jedem Rebuild."""
    base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "js")
    v = 0
    for f in ("leaflet_markers_data.json", "leaflet_markers.js"):
        try:
            v = max(v, int(os.path.getmtime(os.path.join(base, f))))
        except OSError:
            pass
    return v


@app.route("/")
def index():
    return render_template("index.html", station_names=_station_names,
                           markers_version=_markers_version())


@app.route("/learn/")
def learn_hub():
    from py.learn_content import ARTICLES_BY_CATEGORY, CATEGORIES
    return render_template(
        "learn_hub.html",
        categories=CATEGORIES,
        articles_by_category=ARTICLES_BY_CATEGORY,
        station_names=_station_names,
    )


@app.route("/learn/<slug>/")
@app.route("/learn/<slug>")
def learn_article(slug):
    from py.learn_content import SLUG_INDEX
    article = SLUG_INDEX.get(slug)
    if not article:
        abort(404)
    related = [SLUG_INDEX[s] for s in article.get("related", []) if s in SLUG_INDEX]
    return render_template(
        "learn_article.html",
        article=article,
        related=related,
        station_names=_station_names,
    )


@app.route("/favicon.ico")
def favicon():
    return send_from_directory("static", "favicon.ico", mimetype="image/x-icon")


@app.route("/sw.js")
def service_worker():
    """Serve the Service Worker from site root so its scope is '/'.
    Browsers restrict SW scope to the path the file is served from;
    /static/sw.js could only control /static/* — not what we want."""
    resp = send_from_directory("static", "sw.js", mimetype="application/javascript")
    # The browser caches sw.js itself; force a max-age of 0 so updates
    # propagate on the next page load.
    resp.headers["Cache-Control"] = "no-cache, max-age=0"
    return resp


@app.route("/robots.txt")
def robots_txt():
    body = (
        "User-agent: *\n"
        "Allow: /\n"
        "Disallow: /generate/\n"
        "Disallow: /update_coordinates\n"
        "Disallow: /update_station_name\n"
        "Disallow: /delete_station\n"
        f"Sitemap: {request.url_root.rstrip('/')}/sitemap.xml\n"
    )
    return body, 200, {"Content-Type": "text/plain; charset=utf-8"}


_US_STATES = {
    "Alabama","Alaska","Arizona","Arkansas","California","Colorado","Connecticut",
    "Delaware","Florida","Georgia","Hawaii","Idaho","Illinois","Indiana","Iowa",
    "Kansas","Kentucky","Louisiana","Maine","Maryland","Massachusetts","Michigan",
    "Minnesota","Mississippi","Missouri","Montana","Nebraska","Nevada",
    "New Hampshire","New Jersey","New Mexico","New York","North Carolina",
    "North Dakota","Ohio","Oklahoma","Oregon","Pennsylvania","Rhode Island",
    "South Carolina","South Dakota","Tennessee","Texas","Utah","Vermont",
    "Virginia","Washington","West Virginia","Wisconsin","Wyoming",
    "Puerto Rico","Guam","American Samoa","U.S. Virgin Islands",
    "Northern Mariana Islands",
    "Maryland/Delaware",  # combined regions seen in DWF
}

# Curated list of countries / dependencies as they appear in our station names
_COUNTRIES = {
    "Albania","Algeria","Angola","Anguilla","Antigua and Barbuda","Argentina",
    "Aruba","Australia","Bahamas","Bahrain","Bangladesh","Barbados","Belgium",
    "Belize","Benin","Bermuda","Brazil","British Virgin Islands","Brunei",
    "Bulgaria","Cambodia","Cameroon","Canada","Cape Verde","Cayman Islands",
    "Chile","China","Colombia","Comoros","Cook Islands","Costa Rica",
    "Croatia","Cuba","Cyprus","Denmark","Djibouti","Dominica","Dominican Republic",
    "Ecuador","Egypt","El Salvador","Equatorial Guinea","Eritrea","Estonia",
    "Falkland Islands","Faroe Islands","Federated States of Micronesia","Fiji",
    "Finland","France","French Guiana","French Polynesia","Gabon","Gambia",
    "Germany","Ghana","Gibraltar","Greece","Greenland","Grenada","Guadeloupe",
    "Guam","Guatemala","Guernsey","Guinea","Guinea-Bissau","Guyana","Haiti",
    "Honduras","Hong Kong","Iceland","India","Indonesia","Iran","Iraq","Ireland",
    "Isle of Man","Israel","Italy","Ivory Coast","Jamaica","Japan","Jersey",
    "Jordan","Kazakhstan","Kenya","Kiribati","Kuwait","Laos","Latvia","Lebanon",
    "Liberia","Libya","Lithuania","Macau","Madagascar","Malaysia","Maldives",
    "Malta","Marshall Islands","Martinique","Mauritania","Mauritius","Mayotte",
    "Mexico","Monaco","Montenegro","Montserrat","Morocco","Mozambique","Myanmar",
    "Namibia","Nauru","Netherlands","Netherlands Antilles","New Caledonia",
    "New Zealand","Nicaragua","Nigeria","Niue","North Korea","Norway","Oman",
    "Pakistan","Palau","Palestine","Panama","Papua New Guinea","Paraguay","Peru",
    "Philippines","Pitcairn Islands","Poland","Portugal","Puerto Rico","Qatar",
    "Republic of the Congo","Reunion","Romania","Russia","Saint Barthelemy",
    "Saint Helena","Saint Kitts and Nevis","Saint Lucia","Saint Martin",
    "Saint Pierre and Miquelon","Saint Vincent and the Grenadines","Samoa",
    "Sao Tome and Principe","Saudi Arabia","Senegal","Serbia","Seychelles",
    "Sierra Leone","Singapore","Slovenia","Solomon Islands","Somalia",
    "South Africa","South Georgia","South Korea","Spain","Sri Lanka","Sudan",
    "Suriname","Sweden","Syria","Taiwan","Tanzania","Thailand","Togo","Tokelau",
    "Tonga","Trinidad and Tobago","Tunisia","Turkey","Turks and Caicos Islands",
    "Tuvalu","Ukraine","United Arab Emirates","United Kingdom","Uruguay","USA",
    "United States","Vanuatu","Venezuela","Vietnam","Wallis and Futuna",
    "Yemen","Zimbabwe",
    # Antarctic and special
    "Antarctica","Australian Antarctic Territory","British Antarctic Territory",
    "Channel Islands","Crozet Islands","Kerguelen Islands","Macquarie Island",
    "Tristan da Cunha","Tahiti","Wallis","Île Futuna",
}

_COUNTRY_ALIASES = {
    "United States": "USA",
    "México": "Mexico",
    "Moçambique": "Mozambique",
    "Brasil": "Brazil",
    "España": "Spain",
    "Türkiye": "Turkey",
    "Türkei": "Turkey",
    "Côte d'Ivoire": "Ivory Coast",
    "Kerguelen": "Kerguelen Islands",
    "Edinburgh of the Seven Seas": "Tristan da Cunha",
    "Tristan da Cunha Island": "Tristan da Cunha",
    "Tristan Da Cunha": "Tristan da Cunha",
    "Curaçao": "Curacao",
    "Curacao": "Curacao",
    "Îles Éparses": "French Scattered Islands",
    "Western Sahara": "Western Sahara",
    "Samoa Islands": "Samoa",
    "Wallis": "Wallis and Futuna",
    "Île Futuna": "Wallis and Futuna",
    "Greater Sunda Islands": "Indonesia",
    "Crozet Islands": "Crozet Islands",
    # Variants found in actual data
    "Hawaii": "USA",
    "Newfoundland Canada": "Canada",
    "Newfoundland  Canada": "Canada",
    "Okayama Japan": "Japan",
    "Réunion": "Reunion",
    "Saint-Pierre-et-Miquelon": "Saint Pierre and Miquelon",
    "Caribbean Netherlands": "Netherlands",
    "Bonaire": "Netherlands",
    "Ascension Island": "Saint Helena",
    "St. Helena": "Saint Helena",
    "F.S.M.": "Federated States of Micronesia",
    "Micronesia": "Federated States of Micronesia",
    "Confederated States of Micronesia": "Federated States of Micronesia",
    "Caroline Islands": "Federated States of Micronesia",
    "Torres Strait": "Australia",
    "Tuamotu Archipelago": "French Polynesia",
    "Tuamoto Atoll": "French Polynesia",  # typo in source
    "French Polyneisa": "French Polynesia",  # typo in source
    "Gambier Islands": "French Polynesia",
    "São Tomé and Príncipe": "Sao Tome and Principe",
    "Îles Anglo-Normandes": "Channel Islands",
    "Archipel Crozet": "Crozet Islands",
    "Tongatapu": "Tonga",
}
# Add the alias targets to _COUNTRIES (so they round-trip)
_COUNTRIES |= set(_COUNTRY_ALIASES.values())


def _country_for_name(name):
    """Heuristic: extract canonical country from station name.
    Walks comma-separated parts right-to-left, strips noise suffixes,
    also tries content inside parentheses (e.g. "Oahu (Hawaii)" → Hawaii)."""
    if not name:
        return None
    parts = [p.strip() for p in name.split(",")]
    for part in reversed(parts):
        # Strip noise suffixes:
        cleaned = part
        cleaned = re.sub(r"\s+\(expired [^)]+\)$", "", cleaned)
        cleaned = re.sub(r"\s+\(\d+\)$", "", cleaned)
        cleaned = re.sub(r"\s+Currents?$", "", cleaned)
        cleaned = cleaned.strip()
        # Direct match
        for cand in [cleaned] + re.findall(r"\(([^)]+)\)", cleaned) + [re.sub(r"\s*\([^)]*\)", "", cleaned).strip()]:
            cand = cand.strip()
            if not cand: continue
            if cand in _US_STATES:
                return "USA"
            if cand in _COUNTRY_ALIASES:
                return _COUNTRY_ALIASES[cand]
            if cand in _COUNTRIES:
                return cand
    return None


def _is_currents_station(name, source):
    """True if this is a tidal currents station (not heights)."""
    if source and "currents" in source.lower():
        return True
    if name and re.search(r"\bCurrents?\b", name):
        return True
    return False


# Subdivisions per country used as the middle breadcrumb tier.
# Match is exact against the second-to-last comma part (after trailing "(N)" cleanup).
_COUNTRY_SUBDIVISIONS = {
    "USA": _US_STATES,
    "United Kingdom": {"England", "Scotland", "Wales", "Northern Ireland"},
    "Canada": {
        "British Columbia", "Alberta", "Saskatchewan", "Manitoba", "Ontario",
        "Québec", "Quebec", "New Brunswick", "Nova Scotia",
        "Prince Edward Island", "Newfoundland", "Labrador",
        "Newfoundland and Labrador", "Yukon", "Northwest Territories",
        "Nunavut",
    },
    "Australia": {
        "Queensland", "Western Australia", "Northern Territory",
        "South Australia", "Victoria", "New South Wales", "Tasmania",
        "Australian Capital Territory",
    },
    "Mexico": {
        "Baja California", "Baja California Sur", "Baja California Norte",
        "Sonora", "Sinaloa", "Nayarit", "Jalisco", "Colima", "Michoacán",
        "Guerrero", "Oaxaca", "Chiapas", "Veracruz", "Tabasco", "Campeche",
        "Yucatan", "Yucatán", "Quintana Roo", "Tamaulipas",
    },
    "Brazil": {
        "Amapá", "Pará", "Maranhão", "Piauí", "Ceará", "Rio Grande do Norte",
        "Paraíba", "Pernambuco", "Alagoas", "Sergipe", "Bahia",
        "Espírito Santo", "Rio de Janeiro", "São Paulo", "Sao Paulo",
        "Paraná", "Santa Catarina", "Rio Grande do Sul",
    },
    "India": {
        "Gujarat", "Maharashtra", "Goa", "Karnataka", "Kerala", "Tamil Nadu",
        "Andhra Pradesh", "Odisha", "West Bengal", "Lakshadweep",
        "Andaman and Nicobar", "Andaman Islands", "Daman and Diu",
        "Puducherry",
    },
    "Japan": {
        "Hokkaido", "Aomori", "Iwate", "Miyagi", "Akita", "Yamagata",
        "Fukushima", "Ibaraki", "Tochigi", "Gunma", "Saitama", "Chiba",
        "Tokyo", "Kanagawa", "Niigata", "Toyama", "Ishikawa", "Fukui",
        "Yamanashi", "Nagano", "Gifu", "Shizuoka", "Aichi", "Mie",
        "Shiga", "Kyoto", "Osaka", "Hyogo", "Nara", "Wakayama",
        "Tottori", "Shimane", "Okayama", "Hiroshima", "Yamaguchi",
        "Tokushima", "Kagawa", "Ehime", "Kochi", "Fukuoka", "Saga",
        "Nagasaki", "Kumamoto", "Oita", "Miyazaki", "Kagoshima", "Okinawa",
    },
    "Indonesia": {
        "Java", "Sumatra", "Sulawesi", "Borneo", "Maluku", "Bali", "Lombok",
        "New Guinea", "Irian Jaya",
    },
    "Spain": {"Islas Canarias", "Baleares", "Ceuta", "Melilla"},
    "China": {"Hong Kong"},
    "Russia": {"Kuril Islands", "Sakhalin", "Kamchatka"},
}


def _breadcrumb_parts(name, is_current):
    """Split a station's display name into (country, state, station_short).

    Builds a clean hierarchy for breadcrumbs so the chain reads
    Country → State → Station instead of repeating the country in the
    final segment. Examples:
      "Harney Channel ..., Washington, USA"            → ("USA", "Washington", "Harney Channel ...")
      "Aberystwyth, Wales, United Kingdom"             → ("United Kingdom", "Wales", "Aberystwyth")
      "Admiralty Inlet, Washington Current"            → ("USA", "Washington", "Admiralty Inlet")
      "Active Pass, British Columbia, Canada Current"  → ("Canada", "British Columbia", "Active Pass")
      "Doha, Qatar"                                    → ("Qatar", None, "Doha")
    Returns (None, None, name) if the country cannot be identified."""
    if not name:
        return None, None, name
    work = name
    if is_current:
        m = re.search(r"\s+Currents?(\s*\([^)]*\))?\s*$", work)
        if m:
            work = work[:m.start()].rstrip()
    parts = [p.strip() for p in work.split(",") if p.strip()]
    if not parts:
        return None, None, name
    last = parts[-1]
    country = None
    state = None
    short_parts = parts
    if last in _US_STATES:
        country = "USA"
        state = last
        short_parts = parts[:-1]
    elif last in _COUNTRY_ALIASES:
        country = _COUNTRY_ALIASES[last]
        short_parts = parts[:-1]
    elif last in _COUNTRIES:
        country = last
        short_parts = parts[:-1]
    else:
        return None, None, work
    # Country-specific subdivision (state/province/region) in second-to-last
    if country and state is None and short_parts:
        subs = _COUNTRY_SUBDIVISIONS.get(country)
        if subs:
            cand = short_parts[-1]
            cand_clean = re.sub(r"\s*\([^)]*\)\s*$", "", cand).strip()
            if cand in subs:
                state = cand
                short_parts = short_parts[:-1]
            elif cand_clean and cand_clean in subs:
                state = cand_clean
                short_parts = short_parts[:-1]
    short = ", ".join(short_parts) if short_parts else work
    return country, state, short


# SEO intro/outro templates. Variation breaks duplicate-content signals across
# the ~12k prediction pages. {place} resolves to a phrase like "at <station> on
# the <water_body>" or "for <station> in <country>"; {station} is the bare name.
_SEO_INTROS_TIDE = [
    "Accurate tide predictions and tide charts {place} — high and low tide times for the next seven days. Useful for sailors, anglers, surfers and anyone planning coastal activities.",
    "Tide times {place}: predicted high water and low water for the coming week, with continuous tidal curves derived from harmonic analysis. Updated daily.",
    "Plan your day {place} with seven-day tide predictions. High tide, low tide and the full water-level curve for boating, fishing and beach trips alike.",
    "Seven-day high and low tide forecast {place}. Tide curves are referenced to chart datum and refreshed daily for navigation, watersports and harbour planning.",
    "{station} tide times — predicted high and low water for the next week. Astronomically derived water-level curve, useful for sailing, fishing and coastal exploration.",
]
_SEO_INTROS_CURRENT = [
    "Tidal current predictions {place} — flood and ebb times, slack water and peak velocities for the next seven days. Essential for navigation in straits, channels and tidal passages.",
    "Flood and ebb currents {place}: predicted slack-water times and peak velocities for the coming week. Useful for sailors, kayakers and dive-trip planning.",
    "{station} tidal currents — predicted flood, ebb and slack-water times across seven days, derived from harmonic analysis of measured flow.",
    "Plan your passage {place} with seven-day current predictions. Slack water, peak flood and peak ebb for safe navigation through tidal passes.",
    "Predicted tidal currents {place} for the next week — direction, peak speed and slack times, refreshed daily.",
]
_SEO_OUTROS_TIDE = [
    "Tide prediction relies on the gravitational interaction of Earth, Moon and Sun. Astronomical contributions are highly predictable, but real water levels can deviate from forecast due to wind, atmospheric pressure and storm surge. Treat these predictions as planning information, not as a substitute for official tide tables in commercial navigation.",
    "The forecast on this page is derived from harmonic analysis of historical observations or official tide tables. Astronomical tides repeat predictably for years; meteorological effects (wind, pressure, surge) can shift heights and timing. Always cross-check with official sources where safety-critical.",
    "Tides are driven mainly by lunar and solar gravity and follow predictable harmonic cycles. The seven-day forecast above is purely astronomical — actual conditions also depend on weather and on local hydrodynamics, which are not modelled here.",
    "These tide forecasts combine astronomical components — primarily lunar and solar — into a continuous water-level curve. Local effects such as prolonged offshore winds, low atmospheric pressure or river discharge can offset the forecast, so cross-check with on-site readings if conditions matter.",
    "Tidal predictions on this page are computed from harmonic constituents fitted to historical water-level data. Real-world deviations from the predicted curve are caused by meteorological forcing (wind, pressure) and by hydrodynamic effects in shallow or restricted basins.",
]
_SEO_OUTROS_CURRENT = [
    "Tidal current prediction follows the same astronomical principles as tide-height forecasting, applied to flow rather than elevation. Real currents can be modified by wind-driven flow, river discharge and density gradients, so values shown here should be treated as a planning baseline.",
    "Flood and ebb cycles repeat predictably with the moon and sun, but local current speeds also depend on wind, freshwater inflow and basin geometry. Use these forecasts for planning, not for safety-critical timing.",
    "These current predictions are derived from harmonic analysis of measured flow data. The forecast captures astronomical periodicity; actual flow can deviate due to wind stress, freshwater inflow and storm conditions.",
    "Tidal currents follow a predictable astronomical cycle, but real flow speeds and slack times can shift in response to weather. Treat these forecasts as planning information rather than instantaneous truth.",
    "Slack water, flood and ebb times above are astronomical predictions. In real conditions, prolonged wind or significant freshwater inflow can advance or delay timing and modify peak speeds.",
]


def _seo_paragraphs(station_short, country, is_current, water_body):
    """Pick deterministic intro + outro paragraphs for a prediction page.

    Selection is hashed on the station name + tide/current flag, so the same
    station always renders the same text (stable for caching/SEO) but the 12k+
    pages collectively show 5 distinct templates per type instead of one.
    """
    if not station_short:
        station_short = ""
    seed = (station_short + ("|c" if is_current else "|t")).encode("utf-8")
    h = hashlib.md5(seed).digest()
    intro_idx = int.from_bytes(h[0:4], "big")
    outro_idx = int.from_bytes(h[4:8], "big")

    if water_body:
        place = f"at {station_short} on the {water_body}" if station_short else f"on the {water_body}"
    elif country:
        place = f"for {station_short} in {country}" if station_short else f"in {country}"
    else:
        place = f"for {station_short}" if station_short else ""

    intros = _SEO_INTROS_CURRENT if is_current else _SEO_INTROS_TIDE
    outros = _SEO_OUTROS_CURRENT if is_current else _SEO_OUTROS_TIDE
    intro = intros[intro_idx % len(intros)].format(place=place, station=station_short)
    outro = outros[outro_idx % len(outros)].format(place=place, station=station_short)
    return intro, outro


_DATUM_EXPANSIONS = {
    "MSL":     "Mean Sea Level",
    "MLW":     "Mean Low Water",
    "MLLW":    "Mean Lower Low Water",
    "MHW":     "Mean High Water",
    "MHHW":    "Mean Higher High Water",
    "MLWS":    "Mean Low Water Springs",
    "MHWS":    "Mean High Water Springs",
    "MLWN":    "Mean Low Water Neaps",
    "MHWN":    "Mean High Water Neaps",
    "LWS":     "Low Water Springs",
    "HWS":     "High Water Springs",
    "LAT":     "Lowest Astronomical Tide",
    "HAT":     "Highest Astronomical Tide",
    "CD":      "Chart Datum",
    "ACD":     "Admiralty Chart Datum",
    "ZH":      "Zéro Hydrographique",
    "LLWLT":   "Lowest Low Water Lunar Tide",
    "ISLW":    "Indian Spring Low Water",
    "NHN":     "Normalhöhennull",
    "NN":      "Normal Null",
    "NGVD":    "National Geodetic Vertical Datum",
    "NAVD":    "North American Vertical Datum",
    "NAVD88":  "North American Vertical Datum 1988",
    "IGLD":    "International Great Lakes Datum",
    "IGLD85":  "International Great Lakes Datum 1985",
    "PMSL":    "Permanent Service for Mean Sea Level",
}


def _expand_datum(val):
    """Expand a datum abbreviation like 'MSL' to 'Mean Sea Level (MSL)'.

    Handles two forms:
      'MSL'             -> 'Mean Sea Level (MSL)'
      'ACD (approx.)'   -> 'Admiralty Chart Datum (ACD, approx.)'
    Unknown abbreviations and values with non-trivial extra content are
    returned unchanged."""
    if not val:
        return val
    v = val.strip()
    m = re.match(r"^([A-Za-z0-9]+)\s*\(([^)]+)\)\s*$", v)
    if m:
        abbr, qual = m.group(1), m.group(2).strip()
        full = _DATUM_EXPANSIONS.get(abbr)
        if full:
            return f"{full} ({abbr}, {qual})"
        return v
    if "(" in v:
        return v
    full = _DATUM_EXPANSIONS.get(v)
    return f"{full} ({v})" if full else val


_TIDAL_RANGE_PHRASINGS = [
    "The typical tidal range here is about {rng} {unit}.",
    "Mean tidal range at this location is around {rng} {unit}.",
    "Expect an average tidal range of roughly {rng} {unit}.",
    "The average difference between high and low water is approximately {rng} {unit}.",
]


def _tidal_range_sentence(tide_rows, station_short, is_current):
    """Mean tidal range derived from the 7-day prediction.

    Returns a short SEO sentence (deterministically phrased per station) or
    None if no usable data, or for tidal currents (range doesn't apply)."""
    if is_current:
        return None
    highs, lows, unit = [], [], None
    for r in tide_rows:
        if r.get("row_type") != "tide":
            continue
        m = re.match(r"^(-?\d+(?:\.\d+)?)\s+(\w+)", (r.get("value") or "").strip())
        if not m:
            continue
        val = float(m.group(1))
        if unit is None:
            unit = m.group(2)
        t = r.get("type", "")
        if "High Tide" in t:
            highs.append(val)
        elif "Low Tide" in t:
            lows.append(val)
    if len(highs) < 3 or len(lows) < 3:
        return None
    rng = (sum(highs) / len(highs)) - (sum(lows) / len(lows))
    if rng <= 0.05:
        return None
    unit_short = "m" if unit and unit.lower().startswith("meter") else (
        "ft" if unit and unit.lower() in {"foot", "feet"} else unit or "")
    rng_str = f"{rng:.1f}"
    seed = ((station_short or "") + "|range").encode("utf-8")
    idx = int.from_bytes(hashlib.md5(seed).digest()[:4], "big")
    return _TIDAL_RANGE_PHRASINGS[idx % len(_TIDAL_RANGE_PHRASINGS)].format(
        rng=rng_str, unit=unit_short)


def _build_faq_items(tide_rows, station_short, country, water_body, lat, lon, datum, is_current):
    """Build 3-4 datadriven FAQ items per page (rendered visibly + as JSON-LD).

    For tide stations: today's HW/LW times, typical range, location, methodology.
    For currents:      today's slack water, peak flood/ebb over week, location,
                       methodology.

    Returns a list of {"q": str, "a": str} dicts. Empty if station_short is
    missing or no usable data could be extracted."""
    items = []
    if not station_short:
        return items
    today_str = datetime.now().strftime("%Y-%m-%d")

    today_high, today_low, today_slack = [], [], []
    week_max_flood = None  # (abs_value, raw_value_str)
    week_max_ebb = None
    week_highs, week_lows = [], []
    unit = None
    last_date = None
    for r in tide_rows:
        d = r.get("date")
        if d:
            last_date = d
        if r.get("row_type") != "tide":
            continue
        t = r.get("type", "")
        time = r.get("time", "")
        value = (r.get("value") or "").strip()
        is_today = (last_date == today_str)
        m = re.match(r"^(-?\d+(?:\.\d+)?)\s+(\w+)", value)
        num = float(m.group(1)) if m else None
        if m and unit is None:
            unit = m.group(2)
        if "High Tide" in t:
            if is_today:
                today_high.append((time, value))
            if num is not None:
                week_highs.append(num)
        elif "Low Tide" in t:
            if is_today:
                today_low.append((time, value))
            if num is not None:
                week_lows.append(num)
        elif "Slack" in t:
            if is_today:
                # "Slack, Flood Begins" -> "flood beginning"
                begins = "flood beginning" if "Flood Begins" in t else (
                    "ebb beginning" if "Ebb Begins" in t else "slack water")
                today_slack.append((time, begins))
        elif "Max Flood" in t and num is not None:
            if week_max_flood is None or abs(num) > week_max_flood[0]:
                week_max_flood = (abs(num), value)
        elif "Max Ebb" in t and num is not None:
            if week_max_ebb is None or abs(num) > week_max_ebb[0]:
                week_max_ebb = (abs(num), value)

    if not is_current:
        # Q1: Today's tide times
        parts = []
        if today_high:
            parts.append("high tides at " + ", ".join(f"{t} ({v})" for t, v in today_high))
        if today_low:
            parts.append("low tides at " + ", ".join(f"{t} ({v})" for t, v in today_low))
        if parts:
            heights_clause = f", with heights above {datum}" if datum else ""
            items.append({
                "q": f"What are today's tide times at {station_short}?",
                "a": f"Today at {station_short}: {' and '.join(parts)}{heights_clause}.",
            })
        # Q2: Typical tidal range (data-derived)
        if len(week_highs) >= 3 and len(week_lows) >= 3:
            rng = (sum(week_highs)/len(week_highs)) - (sum(week_lows)/len(week_lows))
            if rng > 0.05:
                u = "m" if unit and unit.lower().startswith("meter") else (
                    "ft" if unit and unit.lower() in {"foot", "feet"} else (unit or ""))
                items.append({
                    "q": f"What is the typical tidal range at {station_short}?",
                    "a": (f"The typical tidal range at {station_short} is approximately "
                          f"{rng:.1f} {u}, calculated from the mean difference between "
                          f"high and low water in the seven-day forecast."),
                })
    else:
        # Currents Q1: Today's slack water times
        if today_slack:
            slack_str = ", ".join(f"{t} ({lbl})" for t, lbl in today_slack)
            items.append({
                "q": f"What are today's slack water times at {station_short}?",
                "a": f"Today at {station_short}: slack water at {slack_str}.",
            })
        # Currents Q2: Peak flood/ebb over the week
        peaks = []
        if week_max_flood:
            peaks.append(f"peak flood of {week_max_flood[1]}")
        if week_max_ebb:
            peaks.append(f"peak ebb of {week_max_ebb[1]}")
        if peaks:
            items.append({
                "q": f"What are the maximum current speeds at {station_short}?",
                "a": (f"Over the next seven days at {station_short}: "
                      + " and ".join(peaks) + "."),
            })

    # Q3 (common): Location
    if lat is not None and lon is not None:
        ns = "N" if lat >= 0 else "S"
        ew = "E" if lon >= 0 else "W"
        coord = f"{abs(lat):.4f}°{ns}, {abs(lon):.4f}°{ew}"
        loc = station_short + " is located"
        if country:
            loc += f" in {country}"
        if water_body:
            loc += f" on the {water_body}"
        loc += f" at coordinates {coord}."
        items.append({
            "q": f"Where is {station_short} located?",
            "a": loc,
        })

    # Q4 (common): Methodology
    if is_current:
        items.append({
            "q": "How are these tidal current predictions calculated?",
            "a": ("Predictions are derived from harmonic analysis of historical "
                  "current measurements, modelling the astronomical components "
                  "driven by lunar and solar gravity. Actual flow speeds can deviate "
                  "from the forecast due to wind, freshwater inflow and other local "
                  "hydrodynamic effects."),
        })
    else:
        items.append({
            "q": "How are these tide predictions calculated?",
            "a": ("Predictions are derived from harmonic analysis of historical "
                  "water-level observations or official tide tables, modelling the "
                  "astronomical components driven by lunar and solar gravity. "
                  "Actual water levels can deviate from the forecast due to wind, "
                  "atmospheric pressure and storm surge."),
        })

    return items


@app.route("/stations/")
def stations_index():
    """Crawler-friendly HTML list of all tide stations grouped by country.
    Provides internal linking from the JS-only map to all prediction pages.
    Currents stations are listed in a separate section."""
    by_country = {}
    currents_by_country = {}
    other_tides = []
    other_currents = []
    # Dedup by orig_name (not by slug): _slug_to_station holds both the
    # display-slug and a legacy orig-slug fallback for each DWF USA station,
    # so iterating its items would count those stations twice. The display
    # slug is inserted first, so picking the first slug we see per orig_name
    # gives us the canonical URL.
    seen_orig = set()
    for slug, orig_name in _slug_to_station.items():
        if orig_name in seen_orig:
            continue
        seen_orig.add(orig_name)
        src = _station_data.get(orig_name)
        disp = display_name_for(orig_name, src)
        country = _country_for_name(disp) or _country_for_name(orig_name)
        is_curr = _is_currents_station(orig_name, src)
        if is_curr:
            (currents_by_country.setdefault(country, []) if country else other_currents).append((disp, slug))
        else:
            (by_country.setdefault(country, []) if country else other_tides).append((disp, slug))
    for c in by_country:
        by_country[c].sort(key=lambda x: x[0].lower())
    for c in currents_by_country:
        currents_by_country[c].sort(key=lambda x: x[0].lower())
    other_tides.sort(key=lambda x: x[0].lower())
    other_currents.sort(key=lambda x: x[0].lower())

    countries = sorted(by_country.keys(), key=str.lower)
    curr_countries = sorted(currents_by_country.keys(), key=str.lower)
    n_tides = sum(len(v) for v in by_country.values()) + len(other_tides)
    n_currents = sum(len(v) for v in currents_by_country.values()) + len(other_currents)
    n_total = n_tides + n_currents
    base = request.url_root.rstrip("/")

    out = [
        '<!DOCTYPE html><html lang="en"><head>',
        '<meta charset="utf-8"/>',
        '<meta name="viewport" content="width=device-width, initial-scale=1.0"/>',
        f'<title>All stations ({n_total}) — Tide predictions &amp; forecasts</title>',
        f'<meta name="description" content="Index of {n_total} stations ({n_tides} tide + {n_currents} current) across {len(countries)} countries. High and low tide times, tide curves and forecasts."/>',
        f'<link rel="canonical" href="{base}/stations/"/>',
        '<link rel="manifest" href="/static/manifest.webmanifest"/>',
        '<meta name="theme-color" content="#169ca5"/>',
        '<script src="/static/js/pwa.js" defer></script>',
        '<style>body{font-family:sans-serif;max-width:1200px;margin:0 auto;padding:20px;color:#333;}',
        'h1{margin-bottom:0.3em;}h2{margin-top:1.5em;border-bottom:1px solid #ddd;padding-bottom:4px;}',
        'nav.toc{column-count:4;column-gap:18px;font-size:0.92em;margin:0.5em 0 1.5em;}',
        'nav.toc a{display:block;text-decoration:none;color:#0066cc;padding:1px 0;}',
        'ul.stations{column-count:3;column-gap:18px;list-style:none;padding:0;font-size:0.9em;}',
        'ul.stations li{break-inside:avoid;padding:1px 0;}',
        'ul.stations a{text-decoration:none;color:#0066cc;}',
        '.section-toggle{display:block;margin:2em 0 1em;padding:8px 14px;background:#f0f0f0;border-radius:4px;color:#333;text-decoration:none;font-weight:bold;}',
        '@media (max-width:700px){nav.toc{column-count:2;}ul.stations{column-count:1;}}',
        'a.back{display:inline-block;margin-bottom:1em;color:#0066cc;text-decoration:none;}',
        'nav.header-links{margin-bottom:1em;display:flex;gap:18px;flex-wrap:wrap;font-size:0.95em;}',
        'nav.header-links a{color:#0066cc;text-decoration:none;}',
        '.learn-cta{margin:1.5em 0;padding:14px 18px;background:#eaf6f7;border-left:4px solid #169ca5;border-radius:4px;font-size:0.95em;}',
        '.learn-cta a{color:#0066cc;text-decoration:none;font-weight:500;}',
        '</style></head><body>',
        '<nav class="header-links" aria-label="Site navigation">',
        '<a href="/">&larr; Back to interactive map</a>',
        '<a href="/learn/">Learn about tides &rarr;</a>',
        '</nav>',
        f'<h1>All stations ({n_total})</h1>',
        f'<p>Index of {n_total} stations &mdash; {n_tides} tide stations across {len(countries)} countries '
        f'plus <a href="#currents">{n_currents} tidal currents</a>, sorted alphabetically. '
        f'Click any station for high/low tide times, tide curves and forecasts.</p>',
        '<aside class="learn-cta">',
        '  <strong>New to tides?</strong> Read our short articles on '
        '  <a href="/learn/how-tides-work/">how tides work</a>, '
        '  <a href="/learn/how-predictions-are-made/">how predictions are made</a>, '
        '  <a href="/learn/largest-tidal-ranges/">the world&rsquo;s largest tidal ranges</a> '
        '  and <a href="/learn/strongest-currents/">strongest tidal currents</a> &mdash; or browse the full '
        '  <a href="/learn/">Learn hub</a>.',
        '</aside>',
        '<nav class="toc" aria-label="Countries (tides)"><strong>Tide stations by country:</strong>',
    ]
    for c in countries:
        anchor = "tides-" + re.sub(r"[^a-z0-9]+", "-", c.lower()).strip("-")
        out.append(f'<a href="#{anchor}">{c} ({len(by_country[c])})</a>')
    if other_tides:
        out.append(f'<a href="#tides-other">Other / unmapped ({len(other_tides)})</a>')
    out.append('</nav>')
    for c in countries:
        anchor = "tides-" + re.sub(r"[^a-z0-9]+", "-", c.lower()).strip("-")
        out.append(f'<h2 id="{anchor}">{c}</h2>')
        out.append('<ul class="stations">')
        for disp, slug in by_country[c]:
            out.append(f'<li><a href="/prediction/{slug}">{disp}</a></li>')
        out.append('</ul>')
    if other_tides:
        out.append('<h2 id="tides-other">Other / unmapped</h2>')
        out.append('<ul class="stations">')
        for disp, slug in other_tides:
            out.append(f'<li><a href="/prediction/{slug}">{disp}</a></li>')
        out.append('</ul>')

    # Currents section
    out.append(f'<h2 id="currents" style="margin-top:3em;">Tidal currents ({n_currents})</h2>')
    out.append('<nav class="toc" aria-label="Countries (currents)">')
    for c in curr_countries:
        anchor = "currents-" + re.sub(r"[^a-z0-9]+", "-", c.lower()).strip("-")
        out.append(f'<a href="#{anchor}">{c} ({len(currents_by_country[c])})</a>')
    if other_currents:
        out.append(f'<a href="#currents-other">Other / unmapped ({len(other_currents)})</a>')
    out.append('</nav>')
    for c in curr_countries:
        anchor = "currents-" + re.sub(r"[^a-z0-9]+", "-", c.lower()).strip("-")
        out.append(f'<h3 id="{anchor}">{c}</h3>')
        out.append('<ul class="stations">')
        for disp, slug in currents_by_country[c]:
            out.append(f'<li><a href="/prediction/{slug}">{disp}</a></li>')
        out.append('</ul>')
    if other_currents:
        out.append('<h3 id="currents-other">Other / unmapped</h3>')
        out.append('<ul class="stations">')
        for disp, slug in other_currents:
            out.append(f'<li><a href="/prediction/{slug}">{disp}</a></li>')
        out.append('</ul>')

    out.append('</body></html>')
    return "\n".join(out), 200, {"Content-Type": "text/html; charset=utf-8"}


@app.route("/sitemap.xml")
def sitemap_xml():
    base = request.url_root.rstrip("/")
    today = datetime.now().date().isoformat()
    parts = ['<?xml version="1.0" encoding="UTF-8"?>',
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    parts.append(f"<url><loc>{base}/</loc><lastmod>{today}</lastmod>"
                 f"<changefreq>daily</changefreq><priority>1.0</priority></url>")
    parts.append(f"<url><loc>{base}/stations/</loc><lastmod>{today}</lastmod>"
                 f"<changefreq>weekly</changefreq><priority>0.8</priority></url>")
    parts.append(f"<url><loc>{base}/widgets/</loc><lastmod>{today}</lastmod>"
                 f"<changefreq>monthly</changefreq><priority>0.6</priority></url>")
    # Learn articles (FAQ-style content pages)
    from py.learn_content import ARTICLES as _LEARN_ARTICLES
    parts.append(f"<url><loc>{base}/learn/</loc><lastmod>{today}</lastmod>"
                 f"<changefreq>monthly</changefreq><priority>0.7</priority></url>")
    for _a in _LEARN_ARTICLES:
        parts.append(f"<url><loc>{base}/learn/{_a['slug']}/</loc>"
                     f"<lastmod>{today}</lastmod><changefreq>monthly</changefreq>"
                     f"<priority>0.6</priority></url>")
    seen = set()
    for slug in _slug_to_station:
        if slug in seen:
            continue
        seen.add(slug)
        parts.append(f"<url><loc>{base}/prediction/{slug}</loc>"
                     f"<lastmod>{today}</lastmod><changefreq>daily</changefreq>"
                     f"<priority>0.7</priority></url>")
    parts.append("</urlset>")
    return "\n".join(parts), 200, {"Content-Type": "application/xml; charset=utf-8"}


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


_last_purge_date = None  # tracks date of last successful purge


# Pre-compute (slug, lat, lon, display_name) for nearest-station lookup.
# Built once at module load; query is O(N) per request (~11k entries → <10ms).
# Dedup: one entry per unique display_name (a station may have multiple slugs).
_station_index = []
_seen_disp_for_index = set()
for _orig, _src in _station_data.items():
    _coords = _station_coords.get(_orig)
    if not _coords:
        continue
    _disp = display_name_for(_orig, _src)
    if _disp in _seen_disp_for_index:
        continue
    _seen_disp_for_index.add(_disp)
    _slug = to_slug(_disp)
    _station_index.append((_slug, _coords[0], _coords[1], _disp))


def _nearest_stations(slug, lat, lon, k=8, max_km=300):
    """Return up to k nearest stations to (lat, lon), sorted by distance.
    Excludes the query station itself by slug. Filters to <= max_km
    (drops if 0 results within that radius — fall back to global k)."""
    import math
    rlat = math.radians(lat)
    cos_lat = math.cos(rlat)
    sin_lat = math.sin(rlat)
    out = []
    R = 6371.0  # km
    for s_slug, s_lat, s_lon, s_disp in _station_index:
        if s_slug == slug:
            continue
        # Haversine
        dlat = math.radians(s_lat - lat)
        dlon = math.radians(s_lon - lon)
        a = math.sin(dlat / 2) ** 2 + cos_lat * math.cos(math.radians(s_lat)) * math.sin(dlon / 2) ** 2
        if a >= 1: a = 1
        d = 2 * R * math.asin(math.sqrt(a))
        out.append((d, s_disp, s_slug))
    out.sort(key=lambda x: x[0])
    within = [(disp, slg, dist) for dist, disp, slg in out[:k] if dist <= max_km]
    if within:
        return within
    # Fall back: top-k regardless of distance (very remote stations)
    return [(disp, slg, dist) for dist, disp, slg in out[:k]]

def _purge_stale_predictions(force=False):
    """Delete prediction HTMLs and SVGs not modified today.
    Called lazily on first prediction request per day (cheap if already purged).
    Tide grafiks are date-anchored (start = today), so yesterday's are stale."""
    global _last_purge_date
    today = datetime.now().date()
    if not force and _last_purge_date == today:
        return 0
    n_purged = 0
    for d, pattern in [(PREDICTIONS_DIR, "tide_prediction_*.html"),
                       (SVG_DIR, "tide_prediction_*.svg")]:
        if not os.path.isdir(d):
            continue
        for f in glob.glob(os.path.join(d, pattern)):
            try:
                mtime_date = datetime.fromtimestamp(os.path.getmtime(f)).date()
                if mtime_date < today:
                    os.remove(f)
                    n_purged += 1
            except OSError:
                pass
    _last_purge_date = today
    if n_purged:
        print(f"🗑️ Purged {n_purged} stale prediction asset(s) from previous day(s)")
    return n_purged


def _generate_prediction(decoded_station, station_raw, source, svg_filename, html_filename, utc=False):
    """Generate SVG + HTML prediction files. Returns html_path."""
    svg_path = os.path.join(SVG_DIR, svg_filename)
    html_path = os.path.join(PREDICTIONS_DIR, html_filename)

    os.makedirs(PREDICTIONS_DIR, exist_ok=True)

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
    end_date = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d %H:%M")
    # xtide -m g ignoriert -e; Zeitspanne wird über -gw (pixels-per-hour fest) gesteuert.
    # gw=3200 deckt ~7 Tage ab (heute + 6.5 Tage) bei xtide-nativer Schrift­größe.
    cmd = [
        "tide",
        "-l", decoded_station,
        "-b", current_date,
        "-gw", "3200",
        "-f", "v",
        "-m", "g",
        "-o", svg_path,
        *tz_flag,
    ]

    print("➤ Aufruf von tide:")
    print(" ", " ".join(cmd))

    subprocess.run(cmd, capture_output=True, text=True, check=True, env=env)
    print("✅ tide wurde erfolgreich ausgeführt.")

    # Konvertierung der SVG-Kodierung + Inject <title> für Accessibility/SEO
    with open(svg_path, "rb") as f:
        svg_text = f.read().decode("iso-8859-1")
    is_curr_for_title = decoded_station.rstrip().endswith("Current")
    title_text = (
        f"Current prediction curve for {decoded_station}"
        if is_curr_for_title else
        f"Tide prediction curve for {decoded_station}"
    )
    # Escape XML special chars in title
    title_safe = (title_text.replace("&", "&amp;")
                              .replace("<", "&lt;")
                              .replace(">", "&gt;"))
    # Inject <title> as first child of <svg> (only if not already present)
    if "<title>" not in svg_text[:500]:
        svg_text = re.sub(
            r"(<svg[^>]*>)",
            r"\1<title>" + title_safe + r"</title>",
            svg_text, count=1,
        )
    with open(svg_path, "w", encoding="utf-8") as f:
        f.write(svg_text)
    print(f"✅ SVG-Datei konvertiert + Title injiziert: {svg_path}")

    # Zusätzlich: tide -l "Station" -m a → als Key-Value-Liste
    # Mehrzeilige Comments werden zusätzlich strukturiert ausgewertet (water_body etc.)
    meta_extras = {}
    try:
        meta_cmd = ["tide", "-l", decoded_station, "-m", "a", *tz_flag]
        meta_result = subprocess.run(meta_cmd, capture_output=True, text=True, check=True, env=env)
        meta_rows = []
        comment_lines = []
        last_key = None
        for line in meta_result.stdout.strip().splitlines():
            key = line[:14].strip()
            val = line[14:].strip()
            if key:
                if key == "Datum":
                    val = _expand_datum(val)
                meta_rows.append((key, val))
                last_key = key
                if key == "Comments" and val:
                    comment_lines.append(val)
            elif last_key == "Comments" and val:
                comment_lines.append(val)
        for c in comment_lines:
            m = re.match(r"^([a-z][a-z_]*)\s*:\s*(.+)$", c)
            if m:
                meta_extras[m.group(1)] = m.group(2).strip()
        meta_info = meta_rows
    except subprocess.CalledProcessError:
        meta_info = []

    # Textvorhersage: tide -l "Station" -b ... -e ... -f t -m p
    try:
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
                'row_type': row_type,
                # Keep full date (untrimmed) for later TZ shift; the visible
                # 'date' field is reset to '' for continuation rows.
                '_full_date': date_str,
            })
    except subprocess.CalledProcessError:
        tide_rows = []

    # If the user asked for "Local" but the station's harmonics are in UTC
    # (all UTide-derived stations have `Time zone: :UTC`), xtide can't do
    # the conversion for us — its -z flag toggles between station-meridian
    # time and UTC, and here they're the same. Do the shift in Python using
    # the IANA zone derived from the station's lat/lon.
    station_tz_raw = next((v for k, v in meta_info if k == "Time zone"), "")
    is_utc_station = station_tz_raw.strip().lstrip(':').upper() == "UTC"
    coords_for_tz = _station_coords.get(station_raw) or _station_coords.get(decoded_station)
    if (not utc) and is_utc_station and coords_for_tz and tide_rows:
        try:
            iana = _tzfinder.timezone_at(lat=coords_for_tz[0], lng=coords_for_tz[1])
            if iana:
                target_tz = ZoneInfo(iana)
                shifted = []
                prev_date = None
                for r in tide_rows:
                    dt_utc = datetime.strptime(
                        f"{r['_full_date']} {r['time']}", "%Y-%m-%d %H:%M"
                    ).replace(tzinfo=ZoneInfo("UTC"))
                    dt_loc = dt_utc.astimezone(target_tz)
                    full_date = dt_loc.strftime("%Y-%m-%d")
                    r['date'] = full_date if full_date != prev_date else ''
                    r['time'] = dt_loc.strftime("%H:%M")
                    r['_full_date'] = full_date
                    prev_date = full_date
                    shifted.append(r)
                # Re-sort after conversion (rows may now cross day boundaries
                # in either direction depending on UTC offset sign).
                shifted.sort(key=lambda r: (r['_full_date'], r['time']))
                prev_date = None
                for r in shifted:
                    full_date = r['_full_date']
                    r['date'] = full_date if full_date != prev_date else ''
                    prev_date = full_date
                tide_rows = shifted
        except Exception as e:
            print(f"⚠️ TZ conversion failed: {e}")

    for r in tide_rows:
        r.pop('_full_date', None)

    # HTML-Datei erzeugen
    is_current_station = decoded_station.rstrip().endswith('Current')
    with open(TEMPLATE_PATH, encoding="utf-8") as f:
        template = f.read()
    svg_url = f"/static/predictions/{svg_filename}"
    # Display name appends e.g. ", USA" for DWF-2025 stations (SEO + UX),
    # while decoded_station / station_raw stay clean for tide CLI lookups.
    display_station = display_name_for(decoded_station, source)
    coords = _station_coords.get(station_raw) or _station_coords.get(decoded_station)
    lat = coords[0] if coords else None
    lon = coords[1] if coords else None
    this_slug = to_slug(display_station)
    nearby = []
    if lat is not None and lon is not None:
        # Nearest other stations within 300 km (or top-8 if remote)
        try:
            nearby = _nearest_stations(this_slug, lat, lon, k=8, max_km=300)
        except Exception as e:
            print(f"⚠️ Nearby-stations error: {e}")
    bc_country, bc_state, bc_station = _breadcrumb_parts(display_station, is_current_station)
    # Prefer xtide's curated water_body; fall back to IHO Sea Areas lookup by slug.
    water_body = meta_extras.get("water_body") or _STATION_SEAS.get(this_slug)
    seo_intro, seo_outro = _seo_paragraphs(
        bc_station or display_station,
        bc_country,
        is_current_station,
        water_body,
    )
    seo_range = _tidal_range_sentence(tide_rows, bc_station or display_station, is_current_station)
    _datum_value = next((v for k, v in meta_info if k == "Datum"), None)
    faq_items = _build_faq_items(
        tide_rows,
        bc_station or display_station,
        bc_country,
        water_body,
        lat, lon,
        _datum_value,
        is_current_station,
    )
    html = render_template_string(template,
                                  station=display_station,
                                  original_name=display_station,
                                  svg_url=svg_url,
                                  meta_info=meta_info,
                                  tide_rows=tide_rows,
                                  is_current=is_current_station,
                                  station_names=_station_names,
                                  utc=utc,
                                  src=source,
                                  latitude=lat,
                                  longitude=lon,
                                  nearby=nearby,
                                  bc_country=bc_country,
                                  bc_state=bc_state,
                                  bc_station=bc_station,
                                  seo_intro=seo_intro,
                                  seo_outro=seo_outro,
                                  seo_range=seo_range,
                                  faq_items=faq_items,
                                  water_body=water_body)
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"✅ HTML-Seite erzeugt: {html_path}")
    return html_path


@app.route("/prediction/<slug>")
def show_prediction(slug):
    """Serve a prediction page, regenerating if stale (not from today)."""
    try:
        # Daily housekeeping: drop yesterday's cached HTMLs and SVGs.
        # Cheap (no-op) after first request of the day.
        _purge_stale_predictions()

        source = request.args.get('source')
        utc = request.args.get('utc') == '1'

        # Resolve slug to original station name
        station_name = _slug_to_station.get(slug)
        if not station_name:
            return "Station nicht gefunden.", 404
        # Source fallback: if URL didn't include ?source=, pick it from
        # the marker file. Needed so display_name_for can append ", USA"
        # (for DWF-2025 stations) on the prediction page.
        if not source:
            source = _station_data.get(station_name)

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

# ──────────────────────────────────────────────────────────────────────
# Embeddable tide widget (script + iframe), see /widgets/ for docs
# ──────────────────────────────────────────────────────────────────────

_widget_cache = {}        # (slug, days) → payload dict; cleared on date change
_widget_cache_date = None
_widget_meta_cache = {}   # (station, source) → {"tz": ..., "datum": ...}

_WIDGET_EVENT_KINDS = {
    'High Tide': 'high',
    'Low Tide': 'low',
    'Max Flood': 'flood',
    'Max Ebb': 'ebb',
    'Min Flood': 'flood',
    'Min Ebb': 'ebb',
    'Slack, Flood Begins': 'slack',
    'Slack, Ebb Begins': 'slack',
}


def _widget_env_for_source(source):
    if source:
        tcd_path = os.path.join('/usr/share/xtide', source)
        if os.path.exists(tcd_path):
            env = os.environ.copy()
            env['HFILE_PATH'] = tcd_path
            return env
    return None


def _widget_station_meta(station_name, source, env):
    """Time zone + datum from `tide -m a`, cached per process."""
    key = (station_name, source)
    cached = _widget_meta_cache.get(key)
    if cached is not None:
        return cached
    meta = {"tz": "", "datum": ""}
    try:
        result = subprocess.run(["tide", "-l", station_name, "-m", "a"],
                                capture_output=True, text=True, check=True, env=env)
        for line in result.stdout.splitlines():
            k, v = line[:14].strip(), line[14:].strip()
            if k == "Time zone":
                meta["tz"] = v
            elif k == "Datum":
                meta["datum"] = _expand_datum(v)
    except subprocess.CalledProcessError:
        pass
    _widget_meta_cache[key] = meta
    return meta


def _widget_resolve_slug(q):
    """Accept a slug or a full station name; return (slug, station_name) or (None, None)."""
    q = unquote(q or "").strip()
    if not q:
        return None, None
    station = _slug_to_station.get(q)
    if station:
        return q, station
    slug = to_slug(q)
    station = _slug_to_station.get(slug)
    if station:
        return slug, station
    return None, None


def _widget_tide_data(slug, station_name, days, units='m'):
    """Tide events for the widget: {station, days:[{date, events:[...]}], ...}.
    Cached per (slug, days, units) until midnight (server time)."""
    global _widget_cache_date
    today = datetime.now().date()
    if _widget_cache_date != today:
        _widget_cache.clear()
        _widget_cache_date = today
    cache_key = (slug, days, units)
    if cache_key in _widget_cache:
        return _widget_cache[cache_key]

    source = _station_data.get(station_name)
    env = _widget_env_for_source(source)
    meta = _widget_station_meta(station_name, source, env)

    # Begin one day early and end one day late: a UTC→local shift (up to
    # ±14 h) moves events across day boundaries in either direction.
    begin = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d 00:00")
    end = (datetime.now() + timedelta(days=days + 1)).strftime("%Y-%m-%d %H:%M")
    cmd = [
        "tide", "-l", station_name,
        "-b", begin, "-e", end,
        "-f", "t", "-m", "p",
        "-df", "%Y-%m-%d", "-tf", "%H:%M",
        "-em", "pSsMm",  # suppress sun/moon events
        "-u", "ft" if units == 'ft' else "m",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True, env=env)

    events = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}\s", line):
            continue
        parts = line.split(None, 2)
        if len(parts) < 3:
            continue
        date_str, time_str, rest = parts[0], parts[1], parts[2].strip()
        val_parts = rest.rsplit('  ', 1)
        if len(val_parts) == 2:
            value, ev_type = val_parts[0].strip(), val_parts[1].strip()
        else:
            value, ev_type = '', rest
        kind = _WIDGET_EVENT_KINDS.get(ev_type)
        if not kind:
            continue  # astro or unknown event
        height, unit = None, ''
        m = re.match(r"^(-?\d+(?:\.\d+)?)\s*(\S+)", value)
        if m:
            height = float(m.group(1))
            unit = m.group(2)
        events.append({"date": date_str, "time": time_str, "type": ev_type,
                       "kind": kind, "height": height, "unit": unit})

    # UTide-derived stations carry `Time zone: :UTC`; shift to local station
    # time in Python (same approach as _generate_prediction).
    is_utc_station = meta["tz"].strip().lstrip(':').upper() == "UTC"
    coords = _station_coords.get(station_name)
    today_str = today.isoformat()
    if is_utc_station and coords and events:
        try:
            iana = _tzfinder.timezone_at(lat=coords[0], lng=coords[1])
            if iana:
                target_tz = ZoneInfo(iana)
                for ev in events:
                    dt_utc = datetime.strptime(
                        f"{ev['date']} {ev['time']}", "%Y-%m-%d %H:%M"
                    ).replace(tzinfo=ZoneInfo("UTC"))
                    dt_loc = dt_utc.astimezone(target_tz)
                    ev['date'] = dt_loc.strftime("%Y-%m-%d")
                    ev['time'] = dt_loc.strftime("%H:%M")
                events.sort(key=lambda e: (e['date'], e['time']))
                # "Today" from the station's perspective, not the server's
                today_str = datetime.now(target_tz).date().isoformat()
        except Exception as e:
            print(f"⚠️ Widget-TZ-Konvertierung fehlgeschlagen: {e}")

    # Group by date; drop anything before today, cap at `days` distinct dates
    day_list = []
    for ev in events:
        if ev['date'] < today_str:
            continue
        if day_list and day_list[-1]['date'] == ev['date']:
            day_list[-1]['events'].append(ev)
        elif len(day_list) < days:
            day_list.append({'date': ev['date'], 'events': [ev]})
        else:
            break
    for d in day_list:
        for ev in d['events']:
            ev.pop('date', None)

    display = display_name_for(station_name, source)
    data = {
        "station": display,
        "slug": slug,
        "url": f"/prediction/{slug}",
        "lat": coords[0] if coords else None,
        "lon": coords[1] if coords else None,
        "datum": meta["datum"],
        "is_current": station_name.rstrip().endswith("Current"),
        "days": day_list,
    }
    _widget_cache[cache_key] = data
    return data


def _widget_days_param():
    try:
        days = int(request.args.get('days', 3))
    except (TypeError, ValueError):
        days = 3
    return max(1, min(days, 3))


def _widget_units_param():
    units = (request.args.get('units') or 'm').strip().lower()
    return 'ft' if units in ('ft', 'feet') else 'm'


def _cors_json(payload, status=200):
    resp = jsonify(payload)
    resp.status_code = status
    resp.headers['Access-Control-Allow-Origin'] = '*'
    resp.headers['Cache-Control'] = 'public, max-age=900'
    return resp


@app.route("/api/widget/tides")
def api_widget_tides():
    slug, station_name = _widget_resolve_slug(request.args.get('station'))
    if not slug:
        return _cors_json({"error": "Station not found"}, 404)
    days = _widget_days_param()
    units = _widget_units_param()
    try:
        return _cors_json(_widget_tide_data(slug, station_name, days, units))
    except subprocess.CalledProcessError as e:
        print(f"❌ Widget: tide-Aufruf fehlgeschlagen für {station_name}: {e.stderr}")
        return _cors_json({"error": "Prediction failed"}, 500)


@app.route("/api/widget/nearest")
def api_widget_nearest():
    try:
        lat = float(request.args.get('lat'))
        lon = float(request.args.get('lon'))
    except (TypeError, ValueError):
        return _cors_json({"error": "lat and lon are required"}, 400)
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return _cors_json({"error": "lat/lon out of range"}, 400)
    best = None
    import math
    cos_lat = math.cos(math.radians(lat))
    for s_slug, s_lat, s_lon, s_disp in _station_index:
        if s_disp.rstrip().endswith("Current"):
            continue
        dlat = math.radians(s_lat - lat)
        dlon = math.radians(s_lon - lon)
        a = math.sin(dlat / 2) ** 2 + cos_lat * math.cos(math.radians(s_lat)) * math.sin(dlon / 2) ** 2
        d = 2 * 6371.0 * math.asin(math.sqrt(min(a, 1)))
        if best is None or d < best[0]:
            best = (d, s_slug, s_disp)
    if not best:
        return _cors_json({"error": "No stations available"}, 404)
    return _cors_json({"slug": best[1], "station": best[2],
                       "distance_km": round(best[0], 1)})


@app.route("/api/widget/resolve")
def api_widget_resolve():
    slug, station_name = _widget_resolve_slug(request.args.get('station'))
    if not slug:
        return _cors_json({"error": "Station not found"}, 404)
    source = _station_data.get(station_name)
    return _cors_json({"slug": slug,
                       "station": display_name_for(station_name, source)})


@app.route("/widget.js")
def widget_js():
    resp = send_from_directory("static/js", "tide-widget.js",
                               mimetype="application/javascript")
    resp.headers['Access-Control-Allow-Origin'] = '*'
    resp.headers['Cache-Control'] = 'public, max-age=86400'
    return resp


@app.route("/widget/<slug>")
def widget_frame(slug):
    resolved_slug, station_name = _widget_resolve_slug(slug)
    if not resolved_slug:
        return "Station not found.", 404
    days = _widget_days_param()
    theme = request.args.get('theme', 'light')
    if theme not in ('light', 'dark', 'auto'):
        theme = 'light'
    units = _widget_units_param()
    return render_template("widget_frame.html", slug=resolved_slug,
                           days=days, theme=theme, units=units)


@app.route("/widgets/")
@app.route("/widgets")
def widgets_page():
    return render_template("widgets.html", station_names=_station_names)


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
    # Startup housekeeping: drop any stale tide HTMLs/SVGs from previous days
    _purge_stale_predictions(force=True)
    app.run(debug=True)
