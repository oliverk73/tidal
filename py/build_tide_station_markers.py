import re
import os
import glob
import unicodedata
from collections import OrderedDict, Counter
from urllib.parse import quote

TCD_DIR = "/usr/share/xtide"
HARMONICS_DIRS = [
    "harmonics/classic",
    "harmonics/ihm",
    "harmonics/utide",
    "harmonics/ticon",
]


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


def normalize_filename(name: str) -> str:
    for char, repl in TRANSLITERATION.items():
        name = name.replace(char, repl)
    name = unicodedata.normalize('NFKD', name)
    name = name.encode('ascii', 'ignore').decode('ascii')
    name = re.sub(r"['\\\\/]", "", name)
    name = re.sub(r"[\s,]+", "_", name)
    return name.lower()


def to_slug(name: str) -> str:
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


def get_stations_from_txt(txt_path):
    """Parse station list directly from a harmonics TXT file.
    Returns list of (name, lat, lon, is_current) tuples."""
    stations = []
    with open(txt_path, 'r', encoding='iso-8859-1') as f:
        lines = f.readlines()

    lat = lon = None
    units = None
    for line in lines:
        line = line.rstrip()
        if line.startswith('# !latitude:'):
            lat = float(line.split(':', 1)[1].strip())
        elif line.startswith('# !longitude:'):
            lon = float(line.split(':', 1)[1].strip())
        elif line.startswith('# !units:'):
            units = line.split(':', 1)[1].strip().lower()
        elif not line.startswith('#') and line.strip() and lat is not None and lon is not None:
            is_current = (units == 'knots' or units == 'knots^2')
            stations.append((line.strip(), lat, lon, is_current))
            lat = lon = None
            units = None
    return stations


def source_key(tcd_basename):
    """Short key from TCD filename for URL/filename disambiguation."""
    key = tcd_basename.replace('.tcd', '')
    key = re.sub(r'^harmonics[-_]', '', key)
    key = key.replace('_mod', '')
    return key


def find_txt_for_tcd(tcd_basename):
    """Find the TXT source file for a given TCD basename."""
    txt_name = tcd_basename.replace('.tcd', '.txt')
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for hdir in HARMONICS_DIRS:
        txt_path = os.path.join(project_root, hdir, txt_name)
        if os.path.exists(txt_path):
            return txt_path
    return None


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

tcd_files = sorted(glob.glob(os.path.join(TCD_DIR, "*.tcd")))
print(f"Gefunden: {len(tcd_files)} TCD-Dateien in {TCD_DIR}")

all_stations = []
for tcd_file in tcd_files:
    basename = os.path.basename(tcd_file)
    txt_path = find_txt_for_tcd(basename)
    if not txt_path:
        print(f"  {basename}: ÜBERSPRUNGEN (keine TXT-Datei gefunden)")
        continue
    stations = get_stations_from_txt(txt_path)
    for name, lat, lon, is_current in stations:
        all_stations.append((name, lat, lon, basename, is_current))
    print(f"  {basename}: {len(stations)} Stationen")

# Names appearing in multiple TCD files need source suffix in URLs
name_counter = Counter(name for name, _, _, _, _ in all_stations)
duplicate_names = {name for name, count in name_counter.items() if count > 1}

# Also detect slug collisions: different names that produce the same URL slug
slug_to_names = {}
for name, _, _, _, _ in all_stations:
    slug = to_slug(name)
    if slug not in slug_to_names:
        slug_to_names[slug] = set()
    slug_to_names[slug].add(name)
duplicate_slugs = {slug for slug, names in slug_to_names.items() if len(names) > 1}
# Add all names with colliding slugs to duplicate_names
for slug in duplicate_slugs:
    duplicate_names.update(slug_to_names[slug])
# Also add names that appear multiple times (same slug from same name in different TCDs)
slug_counter = Counter(to_slug(name) for name, _, _, _, _ in all_stations)
for name, _, _, _, _ in all_stations:
    if slug_counter[to_slug(name)] > 1:
        duplicate_names.add(name)

print(f"Gesamt: {len(all_stations)} Stationen ({len(duplicate_names)} Namen mehrfach/Slug-Kollisionen)")

output_file = os.path.join(PROJECT_ROOT, "static", "js", "leaflet_markers.js")
os.makedirs(os.path.dirname(output_file), exist_ok=True)

SOURCE_GROUPS = OrderedDict([
    ('DWF 2025',        {'color': '#2196F3', 'files': ['harmonics-dwf-20251228-free.tcd']}),
    ('DWF 2010',        {'color': '#607D8B', 'files': ['harmonics-dwf-20100529-nonfree.tcd']}),
    ('DWF 2007',        {'color': '#795548', 'files': ['harmonics-dwf-20070318_mod.tcd']}),
    ('Classic 2004',    {'color': '#4CAF50', 'files': ['harmonics-2004-06-14_mod.tcd']}),
    ('Classic 1997',    {'color': '#9C27B0', 'files': ['harmonics-1997-05-25_mod.tcd']}),
    ('TICON4',          {'color': '#FF9800', 'files': ['harmonics_ticon4_worldwide.tcd']}),
    ('Lavergne',        {'color': '#E91E63', 'files': ['harmonics-pierre-lavergne-v10_mod.tcd',
                                                        'harmonics-pierre-lavergne-v9-europe_mod.tcd']}),
    ('UTide TC',        {'color': '#F44336', 'files': [
                            'harmonics_utide_australia_bom.tcd',
                            'harmonics_utide_brazil_dhn.tcd',
                            'harmonics_utide_canada_bc.tcd',
                            'harmonics_utide_canada_nb.tcd',
                            'harmonics_utide_canada_nl.tcd',
                            'harmonics_utide_canada_qc.tcd',
                            'harmonics_utide_pei.tcd',
                            'harmonics_utide_taiwan_cwa.tcd',
                            'harmonics_utide_hongkong_hko.tcd',
                            'harmonics_utide_spain_ihm.tcd',
                            'harmonics_utide_canada_ns.tcd',
                            'harmonics_utide_korea.tcd',
                            'harmonics_utide_philippines_namria.tcd',
                            'harmonics_utide_uk_tidetimes.tcd',
                            'harmonics_utide_thailand.tcd',
                            ]}),
    ('UTide SL',        {'color': '#E57373', 'files': [
                            'harmonics_utide_germany_z0corrected.tcd',
                            'harmonics_utide_netherlands.tcd',
                            'harmonics_utide_france.tcd',
                            'harmonics_utide_belgium.tcd',
                            'harmonics_utide_canada_all.tcd',
                            'harmonics_utide_uk_bodc.tcd',
                            'harmonics_utide_uk_cmems.tcd',
                            'harmonics_utide_ireland.tcd',
                            'harmonics_utide_uk_ireland.tcd',
                            'harmonics_utide_denmark.tcd',
                            'harmonics_utide_australia.tcd',
                            'harmonics_utide_australia_qld.tcd',
                            'harmonics_utide_australia_uhslc.tcd',
                            'harmonics_utide_portugal.tcd',
                            'harmonics_utide_norway.tcd',
                            'harmonics_utide_india.tcd',
                            'harmonics_utide_chile.tcd',
                            'harmonics_utide_mexico.tcd',
                            'harmonics_utide_new_zealand.tcd',
                            'harmonics_utide_south_africa.tcd',
                            'harmonics_utide_brazil.tcd',
                            'harmonics_utide_argentina.tcd',
                            'harmonics_utide_colombia.tcd',
                            'harmonics_utide_peru.tcd',
                            'harmonics_utide_morocco.tcd',
                            'harmonics_utide_jordan.tcd',
                            'harmonics_utide_panama.tcd',
                            'harmonics_utide_nicaragua.tcd',
                            'harmonics_utide_elsalvador.tcd',
                            'harmonics_utide_caribbean.tcd',
                            'harmonics_utide_abc.tcd',
                            'harmonics_utide_antigua.tcd',
                            'harmonics_utide_barbados.tcd',
                            'harmonics_utide_bvi.tcd',
                            'harmonics_utide_cayman.tcd',
                            'harmonics_utide_montserrat.tcd',
                            'harmonics_utide_stkitts.tcd',
                            'harmonics_utide_stvincent.tcd',
                            'harmonics_utide_indonesia.tcd',
                            'harmonics_utide_philippines.tcd',
                            'harmonics_utide_vietnam.tcd',
                            'harmonics_utide_sudan.tcd',
                            ]}),
    ('Puertos',         {'color': '#00BCD4', 'files': ['harmonics_puertos_spain.tcd']}),
])

def get_group_for_source(source_file):
    for group_name, info in SOURCE_GROUPS.items():
        if source_file in info['files']:
            return group_name, info['color']
    return 'Sonstige', '#999999'

icon_definition = ""

lines = ["var stationCoords = {};"]
lines.append("var stationSources = {};")
# Single cluster group for all tide markers and one for all current markers
# This ensures overlapping stations from different sources get spiderfied together
group_names = list(SOURCE_GROUPS.keys()) + ['Sonstige']
group_colors = {g: SOURCE_GROUPS[g]['color'] for g in SOURCE_GROUPS}
group_colors['Sonstige'] = '#999999'
lines.append("var grp_all_tide = L.markerClusterGroup();")
lines.append("var grp_all_current = L.markerClusterGroup();")
# Arrays of markers per source group for layer control toggling
for g in group_names:
    var_name = re.sub(r'[^a-zA-Z0-9]', '_', g)
    lines.append(f"var src_{var_name}_tide = [];")
    lines.append(f"var src_{var_name}_current = [];")
lines.append("var markers = L.featureGroup();")  # master group for fitBounds

group_tide_counts = {}
group_current_counts = {}
tide_count = 0
current_count = 0
for i, (name, lat, lon, source_file, is_current) in enumerate(all_stations, 1):
    safe_name = normalize_filename(name)
    display_name = name.replace('"', '&quot;')
    uri_name = quote(name, safe='')

    # For duplicate station names: add source suffix to filename and pass source in URL
    slug = to_slug(name)
    if name in duplicate_names:
        skey = source_key(source_file)
        safe_name_full = safe_name + '__' + skey
        prediction_url = f'/prediction/{slug}?source={source_file}'
    else:
        safe_name_full = safe_name
        prediction_url = f'/prediction/{slug}'

    popup_html = (
        f"<b>{display_name}</b><br>"
        f"<a href=\\\"{prediction_url}\\\">🌊 Vorhersage anzeigen</a><br>"
        f"<a href=\\\"#\\\" onclick=\\\"enableDrag(this); return false;\\\">📍 Position korrigieren</a> "
        f"<a href=\\\"#\\\" onclick=\\\"setCoordinatesManual(this); return false;\\\">📍 Koordinaten eingeben</a><br>"
        f"<a href=\\\"#\\\" onclick=\\\"renameStation(this); return false;\\\">✏️ Name ändern</a> "
        f"<a href=\\\"#\\\" onclick=\\\"deleteStation(this); return false;\\\">🗑️ Löschen</a><br>"
        f"<small>📄 {source_file}</small>"
    )

    group_name, color = get_group_for_source(source_file)
    src_var_name = re.sub(r'[^a-zA-Z0-9]', '_', group_name)
    marker_var = f"m{i}"
    coord_key = name.replace("\\", "\\\\").replace("'", "\\'")
    lines.append(f"stationCoords['{coord_key}'] = [{lat}, {lon}];")
    lines.append(f"stationSources['{coord_key}'] = '{source_file}';")
    sz = 18
    sw = 3  # stroke width
    if is_current:
        current_count += 1
        group_current_counts[group_name] = group_current_counts.get(group_name, 0) + 1
        grp_var = "grp_all_current"
        # horizontal double arrow ↔
        svg = (f'<svg width="{sz}" height="{sz}" viewBox="0 0 {sz} {sz}" xmlns="http://www.w3.org/2000/svg">'
               f'<line x1="2" y1="{sz//2}" x2="{sz-2}" y2="{sz//2}" stroke="{color}" stroke-width="{sw}" stroke-linecap="round"/>'
               f'<polyline points="5,{sz//2-4} 2,{sz//2} 5,{sz//2+4}" fill="none" stroke="{color}" stroke-width="{sw}" stroke-linecap="round" stroke-linejoin="round"/>'
               f'<polyline points="{sz-5},{sz//2-4} {sz-2},{sz//2} {sz-5},{sz//2+4}" fill="none" stroke="{color}" stroke-width="{sw}" stroke-linecap="round" stroke-linejoin="round"/>'
               f'</svg>')
        lines.append(
            f'var {marker_var} = L.marker([{lat}, {lon}], {{icon: L.divIcon({{html:\'{svg}\', className:"", iconSize:[{sz},{sz}], iconAnchor:[{sz//2},{sz//2}], popupAnchor:[0,-{sz//2}]}})}});'
        )
    else:
        tide_count += 1
        group_tide_counts[group_name] = group_tide_counts.get(group_name, 0) + 1
        grp_var = "grp_all_tide"
        # vertical double arrow ↕
        svg = (f'<svg width="{sz}" height="{sz}" viewBox="0 0 {sz} {sz}" xmlns="http://www.w3.org/2000/svg">'
               f'<line x1="{sz//2}" y1="2" x2="{sz//2}" y2="{sz-2}" stroke="{color}" stroke-width="{sw}" stroke-linecap="round"/>'
               f'<polyline points="{sz//2-4},5 {sz//2},2 {sz//2+4},5" fill="none" stroke="{color}" stroke-width="{sw}" stroke-linecap="round" stroke-linejoin="round"/>'
               f'<polyline points="{sz//2-4},{sz-5} {sz//2},{sz-2} {sz//2+4},{sz-5}" fill="none" stroke="{color}" stroke-width="{sw}" stroke-linecap="round" stroke-linejoin="round"/>'
               f'</svg>')
        lines.append(
            f'var {marker_var} = L.marker([{lat}, {lon}], {{icon: L.divIcon({{html:\'{svg}\', className:"", iconSize:[{sz},{sz}], iconAnchor:[{sz//2},{sz//2}], popupAnchor:[0,-{sz//2}]}})}});'
        )
    lines.append(f'{marker_var}.bindPopup("{popup_html}");')
    lines.append(f"{grp_var}.addLayer({marker_var});")
    src_type = "current" if is_current else "tide"
    lines.append(f"src_{src_var_name}_{src_type}.push({marker_var});")

# Build the DOMContentLoaded block with hierarchical layer control
ctrl_lines = ["document.addEventListener('DOMContentLoaded', function() {"]

# Add the two cluster groups to map
ctrl_lines.append("  map.addLayer(grp_all_tide);")
ctrl_lines.append("  markers.addLayer(grp_all_tide);")
ctrl_lines.append("  map.addLayer(grp_all_current);")
ctrl_lines.append("  markers.addLayer(grp_all_current);")

# Collect group info for tide and current sections
tide_groups_js = []
for g in group_names:
    tc = group_tide_counts.get(g, 0)
    if tc == 0:
        continue
    var_name = re.sub(r'[^a-zA-Z0-9]', '_', g)
    color = group_colors[g]
    tide_groups_js.append(f"{{name:'{g}',count:{tc},color:'{color}',markers:src_{var_name}_tide,cluster:grp_all_tide}}")

current_groups_js = []
for g in group_names:
    cc = group_current_counts.get(g, 0)
    if cc == 0:
        continue
    var_name = re.sub(r'[^a-zA-Z0-9]', '_', g)
    color = group_colors[g]
    current_groups_js.append(f"{{name:'{g}',count:{cc},color:'{color}',markers:src_{var_name}_current,cluster:grp_all_current}}")

tide_svg = '<svg width="16" height="16" viewBox="0 0 18 18" style="vertical-align:middle;margin-right:4px;"><line x1="9" y1="2" x2="9" y2="16" stroke="#333" stroke-width="3" stroke-linecap="round"/><polyline points="5,5 9,2 13,5" fill="none" stroke="#333" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><polyline points="5,13 9,16 13,13" fill="none" stroke="#333" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/></svg>'
current_svg = '<svg width="16" height="16" viewBox="0 0 18 18" style="vertical-align:middle;margin-right:4px;"><line x1="2" y1="9" x2="16" y2="9" stroke="#333" stroke-width="3" stroke-linecap="round"/><polyline points="5,5 2,9 5,13" fill="none" stroke="#333" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><polyline points="13,5 16,9 13,13" fill="none" stroke="#333" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/></svg>'

ctrl_lines.append(f"""
  var tideGroups = [{','.join(tide_groups_js)}];
  var currentGroups = [{','.join(current_groups_js)}];

  var StationControl = L.Control.extend({{
    options: {{ position: 'bottomright' }},
    onAdd: function() {{
      var div = L.DomUtil.create('div', 'leaflet-bar');
      div.style.cssText = 'background:rgba(255,255,255,0.25);backdrop-filter:blur(4px);-webkit-backdrop-filter:blur(4px);padding:8px 10px;font-size:13px;font-family:sans-serif;cursor:default;border-radius:6px;box-shadow:0 2px 6px rgba(0,0,0,.2);max-height:60vh;overflow-y:auto;';
      L.DomEvent.disableClickPropagation(div);
      L.DomEvent.disableScrollPropagation(div);

      function dot(color) {{
        return '<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:'+color+';margin-right:5px;vertical-align:middle;border:1px solid #fff;"></span>';
      }}

      function buildSection(masterLabel, masterSvg, groups, idPrefix) {{
        var html = '<label style="display:flex;align-items:center;cursor:pointer;font-weight:bold;margin-bottom:2px;">' +
          '<input type="checkbox" data-master="'+idPrefix+'" checked style="margin-right:6px;">' +
          masterSvg + ' ' + masterLabel + '</label>';
        for (var i = 0; i < groups.length; i++) {{
          var g = groups[i];
          html += '<label style="display:flex;align-items:center;cursor:pointer;margin-left:22px;margin-bottom:1px;">' +
            '<input type="checkbox" data-group="'+idPrefix+'-'+i+'" checked style="margin-right:5px;">' +
            dot(g.color) + g.name + ' (' + g.count + ')</label>';
        }}
        return html;
      }}

      var html = buildSection('Tides ({tide_count})', '{tide_svg}', tideGroups, 'tide');
      html += '<div style="border-top:1px solid rgba(0,0,0,0.15);margin:5px 0;"></div>';
      html += buildSection('Currents ({current_count})', '{current_svg}', currentGroups, 'current');
      div.innerHTML = html;

      function toggleGroup(g, on) {{
        var arr = g.markers, cl = g.cluster;
        for (var j = 0; j < arr.length; j++) {{
          if (on) cl.addLayer(arr[j]);
          else cl.removeLayer(arr[j]);
        }}
      }}

      // Master toggle handler
      function setupMaster(idPrefix, groups) {{
        var master = div.querySelector('[data-master="'+idPrefix+'"]');
        var subs = [];
        for (var i = 0; i < groups.length; i++) {{
          subs.push(div.querySelector('[data-group="'+idPrefix+'-'+i+'"]'));
        }}
        master.addEventListener('change', function() {{
          var on = this.checked;
          for (var i = 0; i < groups.length; i++) {{
            subs[i].checked = on;
            toggleGroup(groups[i], on);
          }}
        }});
        for (var i = 0; i < groups.length; i++) {{
          (function(idx) {{
            subs[idx].addEventListener('change', function() {{
              toggleGroup(groups[idx], this.checked);
              // Update master checkbox state
              var allOn = true, allOff = true;
              for (var j = 0; j < subs.length; j++) {{
                if (subs[j].checked) allOff = false;
                else allOn = false;
              }}
              master.checked = allOn;
              master.indeterminate = !allOn && !allOff;
            }});
          }})(i);
        }}
      }}

      setupMaster('tide', tideGroups);
      setupMaster('current', currentGroups);

      return div;
    }}
  }});
  new StationControl().addTo(map);
""")
ctrl_lines.append("  if (!localStorage.getItem('mapView')) {")
ctrl_lines.append("    map.fitBounds(markers.getBounds());")
ctrl_lines.append("  }")
ctrl_lines.append("});")
lines.append("\n".join(ctrl_lines))

with open(output_file, "w", encoding="utf-8") as f:
    f.write(icon_definition)
    f.write("\n".join(lines))

print(f"Fertig: {len(all_stations)} Marker in {output_file}")
