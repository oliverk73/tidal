import os
import re
import json
import tempfile
import unicodedata
import subprocess
from datetime import datetime, timedelta
import glob
from flask import Flask, render_template, render_template_string, abort, jsonify, url_for, request, send_from_directory
from urllib.parse import unquote

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

@app.route("/")
def index():
    return render_template("index.html", station_names=_station_names)

@app.route("/favicon.ico")
def favicon():
    return send_from_directory("static", "favicon.ico", mimetype="image/x-icon")


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


@app.route("/stations/")
def stations_index():
    """Crawler-friendly HTML list of all tide stations grouped by country.
    Provides internal linking from the JS-only map to all prediction pages.
    Currents stations are listed in a separate section."""
    by_country = {}
    currents_by_country = {}
    other_tides = []
    other_currents = []
    seen_slugs = set()
    for slug, orig_name in _slug_to_station.items():
        if slug in seen_slugs:
            continue
        seen_slugs.add(slug)
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
    base = request.url_root.rstrip("/")

    out = [
        '<!DOCTYPE html><html lang="en"><head>',
        '<meta charset="utf-8"/>',
        '<meta name="viewport" content="width=device-width, initial-scale=1.0"/>',
        f'<title>All tide stations ({n_tides}) — Tide predictions &amp; forecasts</title>',
        f'<meta name="description" content="Index of {n_tides} tide stations across {len(countries)} countries plus {n_currents} current stations. High and low tide times, tide curves and forecasts."/>',
        f'<link rel="canonical" href="{base}/stations/"/>',
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
        '</style></head><body>',
        '<a class="back" href="/">&larr; Back to interactive map</a>',
        f'<h1>Tide stations ({n_tides})</h1>',
        f'<p>Index of {n_tides} tide stations across {len(countries)} countries, sorted alphabetically. '
        f'Click any station for high/low tide times, tide curves and forecasts. '
        f'<a href="#currents">Tidal currents ({n_currents})</a> are listed below.</p>',
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
    svg_url = f"/static/predictions/{svg_filename}"
    # Display name appends e.g. ", USA" for DWF-2025 stations (SEO + UX),
    # while decoded_station / station_raw stay clean for tide CLI lookups.
    display_station = display_name_for(decoded_station, source)
    coords = _station_coords.get(station_raw) or _station_coords.get(decoded_station)
    lat = coords[0] if coords else None
    lon = coords[1] if coords else None
    nearby = []
    if lat is not None and lon is not None:
        # Nearest other stations within 300 km (or top-8 if remote)
        try:
            this_slug = to_slug(display_station)
            nearby = _nearest_stations(this_slug, lat, lon, k=8, max_km=300)
        except Exception as e:
            print(f"⚠️ Nearby-stations error: {e}")
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
                                  nearby=nearby)
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
