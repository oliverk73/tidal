#!/usr/bin/env python3
"""
Prüft die 49 noch ungeprüften TICON4-Länder (aus ticon4_country_status.md)
auf Meridian-/Phasen-/Koordinaten-Fehler.

Strategie:
  1. Parse alle Harmonics-Dateien (TICON4 + UTide + Classic + SHOM)
  2. Filter auf TICON4-Stationen in ungeprüften Ländern
  3. Für jede Station:
       - Erwartetes Meridian aus source_id ableiten (memory: project_ticon4_meridian_phase)
       - Quer-Vergleich mit nächster Nicht-TICON4-Station (bevorzugt UTide/Classic)
       - M2-Phase auf UTC umrechnen (phase_utc = phase + speed * tz_offset)
       - Flag: 1h-Offset (24-34°), 180°-Inversion (>150°), große Abweichung (>45° innerhalb 30km)
       - Amplitudencheck (Ratio <0.2 oder >5)
       - Koordinaten/TZ-Plausibilität

Output: harmonics/help/ticon4_unchecked_check.csv + Konsole
"""
import math
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

# Länder aus ticon4_country_status.md → "Nicht geprüft"
UNCHECKED_COUNTRIES = {
    'Angola', 'Antarctica', 'Bahamas', 'Bahrain', 'Bangladesh',
    'Cape Verde', 'China', 'Cook Islands', 'Curaçao', 'Curacao',
    'Djibouti', 'Ghana', 'Grenada', 'Haiti', 'Hong Kong', 'India',
    'Indonesia', 'Iran', 'Ivory Coast', "Cote d'Ivoire", 'Kenya',
    'Madagascar', 'Malaysia', 'Maldives', 'Mauritania', 'Mauritius',
    'Mozambique', 'Myanmar', 'Namibia', 'Nauru', 'Nigeria', 'Niue',
    'Oman', 'Pakistan', 'Papua New Guinea', 'Philippines',
    'Rep. du Congo', 'Republic of the Congo', 'Senegal', 'Seychelles',
    'Singapore', 'Solomon Islands', 'Sri Lanka', 'St. Helena',
    'Saint Helena', 'Taiwan', 'Tanzania', 'Thailand', 'Tonga',
    'Vanuatu', 'Vietnam', 'Yemen',
}

# Meridian-Konvention nach Datenquelle (aus memory/project_ticon4_meridian_phase)
GREENWICH_SOURCES = {  # → erwarteter Meridian +00:00
    'uhslc_rq', 'uhslc_fd', 'meds', 'jodc_pahb', 'jodc_jma',
    'jodc_giaj', 'jodc_jcg', 'refmar', 'nhs', 'bodc', 'cco', 'icg',
}
LOCAL_OFFSET_SOURCES = {  # → lokaler Meridian (Offset in Phasen)
    'wsv', 'rws_hist', 'rws', 'dmi', 'bom', 'ttw', 'unam_hist',
    'uz', 'noc', 'smhi', 'ispra', 'ieo', 'da_mm',
}
# 'cmems' und 'eseas' sind länderabhängig — separat behandeln

M2_SPEED = 28.984104

HARMONICS_DIRS = [
    "/home/oliver/harmonics/classic",
    "/home/oliver/harmonics/ihm",
    "/home/oliver/harmonics/utide",
    "/home/oliver/harmonics/ticon",
]
OUTPUT_CSV = "/home/oliver/harmonics/help/ticon4_unchecked_check.csv"


def parse_tz_offset(tz_line):
    try:
        parts = tz_line.split()
        if parts:
            tz_str = parts[0]
            sign = 1 if tz_str[0] == '+' else -1
            h, m = tz_str[1:].split(':')
            return sign * (int(h) + int(m) / 60.0)
    except (ValueError, IndexError):
        pass
    return 0.0


def parse_z0(z0_line):
    parts = z0_line.split()
    try:
        return float(parts[0]), (parts[1] if len(parts) > 1 else 'meters')
    except (ValueError, IndexError):
        return 0.0, 'meters'


def parse_harmonics_file(txt_path):
    stations = []
    with open(txt_path, 'r', encoding='iso-8859-1') as f:
        lines = f.readlines()

    num_constituents = None
    header_end = 0
    for i, line in enumerate(lines):
        s = line.strip()
        if s == '# Number of constituents':
            for j in range(i + 1, min(i + 5, len(lines))):
                if not lines[j].startswith('#'):
                    num_constituents = int(lines[j].strip())
                    break
        if s == '*END*':
            header_end = i + 1
            break

    basename = os.path.basename(txt_path)
    lat = lon = None
    source_id = datum = country = units = None

    i = header_end
    while i < len(lines):
        line = lines[i].rstrip()
        if line.startswith('# !latitude:'):
            try: lat = float(line.split(':', 1)[1].strip())
            except ValueError: lat = None
        elif line.startswith('# !longitude:'):
            try: lon = float(line.split(':', 1)[1].strip())
            except ValueError: lon = None
        elif line.startswith('# !units:'):
            units = line.split(':', 1)[1].strip().lower()
        elif line.startswith('# station_id_context:'):
            source_id = line.split(':', 1)[1].strip()
        elif line.startswith('# datum:'):
            datum = line.split(':', 1)[1].strip()
        elif line.startswith('# country:'):
            country = line.split(':', 1)[1].strip()
        elif not line.startswith('#') and line.strip() and lat is not None and lon is not None:
            name = line.strip()
            tz_line = lines[i + 1].strip() if i + 1 < len(lines) else ''
            tz_offset = parse_tz_offset(tz_line)
            z0_line = lines[i + 2].strip() if i + 2 < len(lines) else '0'
            z0, z0_units = parse_z0(z0_line)

            constituents = {}
            if num_constituents:
                for ci in range(num_constituents):
                    idx = i + 3 + ci
                    if idx >= len(lines): break
                    cline = lines[idx].strip()
                    if cline.startswith('x '): continue
                    parts = cline.split()
                    if len(parts) >= 3:
                        try: constituents[parts[0]] = (float(parts[1]), float(parts[2]))
                        except ValueError: pass
                i += 3 + num_constituents
            else:
                ci = i + 3
                while ci < len(lines):
                    cline = lines[ci].strip()
                    if cline.startswith('#') or cline == '': break
                    if not cline.startswith('x '):
                        parts = cline.split()
                        if len(parts) >= 3:
                            try: constituents[parts[0]] = (float(parts[1]), float(parts[2]))
                            except ValueError: pass
                    ci += 1
                i = ci

            is_current = (units in ('knots', 'knots^2'))
            stations.append({
                'name': name, 'lat': lat, 'lon': lon,
                'tz_offset': tz_offset, 'z0': z0, 'z0_units': z0_units,
                'constituents': constituents, 'source_id': source_id or '',
                'datum': datum or '', 'country': country or '',
                'source_file': basename, 'is_current': is_current,
            })
            lat = lon = None
            source_id = datum = country = units = None
            continue
        i += 1
    return stations


def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) ** 2)
    return R * 2 * math.asin(min(1.0, math.sqrt(a)))


def phase_diff_signed(p1, p2):
    d = (p1 - p2) % 360
    return d - 360 if d > 180 else d


def m2_phase_utc(st):
    m2 = st['constituents'].get('M2')
    if not m2: return None
    return (m2[1] + M2_SPEED * st['tz_offset']) % 360


def m2_amp_meters(st):
    m2 = st['constituents'].get('M2')
    if not m2: return None
    amp = m2[0]
    if st['z0_units'] == 'feet':
        amp *= 0.3048
    return amp


def source_suffix(source_id):
    return source_id.split('-')[-1] if source_id else '?'


def expected_meridian(source_id, country, tz_offset):
    """Erwartetes Meridian basierend auf source_id und Land.
       Return: (expected_tz, reason, confidence)
         confidence: 'hoch', 'mittel', 'niedrig'
    """
    src = source_suffix(source_id)
    if src in GREENWICH_SOURCES:
        return 0.0, f'{src} → Greenwich', 'hoch'
    if src in LOCAL_OFFSET_SOURCES:
        return tz_offset, f'{src} → lokaler Meridian', 'hoch'
    if src == 'cmems':
        # länderabhängig — verwende aktuellen tz_offset als "plausibel"
        return tz_offset, f'cmems ({country}) → lokaler Meridian angenommen', 'mittel'
    if src == 'eseas':
        return tz_offset, f'eseas → lokaler Meridian angenommen', 'niedrig'
    return tz_offset, f'unbekannte Quelle ({src})', 'niedrig'


def find_best_neighbour(ts, others, max_dist_km=300):
    """Nächste Nicht-TICON4-Station mit M2, bevorzugt UTide/Classic."""
    best = None
    best_dist = float('inf')
    preferred_prefix = ('harmonics_utide_', 'harmonics-1997', 'harmonics-2004',
                        'harmonics-dwf-', 'harmonics-pierre')
    for other in others:
        if other['is_current'] != ts['is_current']: continue
        if 'M2' not in other['constituents']: continue
        d = haversine_km(ts['lat'], ts['lon'], other['lat'], other['lon'])
        if d > max_dist_km: continue
        # Prefer UTide/Classic over CMEMS etc.
        pref = 0 if other['source_file'].startswith(preferred_prefix) else 1
        score = pref * 10000 + d  # UTide within 300km beats non-UTide at any dist
        if best is None or score < best['score']:
            best = {'station': other, 'dist': d, 'score': score}
            best_dist = d
    if best:
        return best['station'], best['dist']
    return None, None


def main():
    import glob as globmod
    import csv

    all_files = []
    for hdir in HARMONICS_DIRS:
        for f in sorted(globmod.glob(os.path.join(hdir, '*.txt'))):
            if 'backup' not in f and 'original_uncorrected' not in f:
                all_files.append(f)
    print(f"Parsing {len(all_files)} Dateien...")

    ticon_stations = []
    other_stations = []
    for fp in all_files:
        try:
            stations = parse_harmonics_file(fp)
        except Exception as e:
            print(f"  FEHLER beim Parsen {os.path.basename(fp)}: {e}")
            continue
        is_ticon = 'ticon' in os.path.basename(fp).lower()
        for s in stations:
            if is_ticon:
                ticon_stations.append(s)
            else:
                other_stations.append(s)

    print(f"  {len(ticon_stations)} TICON4-Stationen")
    print(f"  {len(other_stations)} Referenz-Stationen")

    # Filter auf ungeprüfte Länder
    unchecked = [s for s in ticon_stations if s['country'] in UNCHECKED_COUNTRIES]
    print(f"\n{len(unchecked)} TICON4-Stationen in {len(set(s['country'] for s in unchecked))} ungeprüften Ländern")

    # Sort by country then name
    unchecked.sort(key=lambda s: (s['country'], s['name']))

    results = []
    issues_by_country = defaultdict(list)

    for ts in unchecked:
        issues = []
        src = source_suffix(ts['source_id'])

        # Meridian-Check
        exp_tz, reason, conf = expected_meridian(ts['source_id'], ts['country'], ts['tz_offset'])
        mer_mismatch = abs(ts['tz_offset'] - exp_tz) > 0.01

        # Koordinaten-Plausibilität
        coord_tz_mismatch = False
        if ts['tz_offset'] != 0:
            expected_from_lon = ts['lon'] / 15.0
            tz_diff_h = abs(ts['tz_offset'] - expected_from_lon)
            if tz_diff_h > 4.5:
                issues.append(('TZ_LON_MISMATCH',
                    f'TZ {ts["tz_offset"]:+.1f}h vs lon {ts["lon"]:.1f}° → erwartet ~{expected_from_lon:+.1f}h'))

        # Cross-Vergleich
        nb, dist = find_best_neighbour(ts, other_stations)
        phase_note = ''
        amp_note = ''
        nb_info = ''
        if nb and dist is not None:
            nb_info = f'{nb["name"]} [{nb["source_file"]}] {dist:.0f}km'
            ts_p = m2_phase_utc(ts)
            nb_p = m2_phase_utc(nb)
            ts_a = m2_amp_meters(ts)
            nb_a = m2_amp_meters(nb)

            if ts_p is not None and nb_p is not None:
                pdiff = phase_diff_signed(ts_p, nb_p)
                phase_note = f'ΔΦ={pdiff:+.1f}°'

                # 1h-Offset: 24-34° (M2 speed * 1h)
                if 24 <= abs(pdiff) <= 34 and dist < 200:
                    issues.append(('PHASE_1H_OFFSET',
                        f'{phase_note} vs {nb_info} → 1h-Fehler?'))

                # 180°-Inversion: pdiff nahe ±180
                elif abs(abs(pdiff) - 180) < 25 and dist < 100:
                    issues.append(('PHASE_INVERTED',
                        f'{phase_note} vs {nb_info} → 180°-Inversion?'))

                # Große Abweichung auf kurzer Distanz
                elif abs(pdiff) > 45 and dist < 30 and ts_a and nb_a and ts_a > 0.05 and nb_a > 0.05:
                    issues.append(('PHASE_LARGE_DIFF',
                        f'{phase_note} vs {nb_info}'))

            if ts_a and nb_a and nb_a > 0.01 and dist < 50:
                ratio = ts_a / nb_a
                if ratio > 5.0 or ratio < 0.2:
                    issues.append(('AMP_RATIO_EXTREME',
                        f'M2 Amp-Ratio {ratio:.2f}x vs {nb_info} [{ts_a:.3f}m vs {nb_a:.3f}m]'))
                amp_note = f'M2={ts_a:.3f}m (nb={nb_a:.3f}m)'

        if mer_mismatch:
            issues.append(('MERIDIAN',
                f'Meridian {ts["tz_offset"]:+.1f}h, erwartet {exp_tz:+.1f}h ({reason}, {conf})'))

        status = 'OK' if not issues else 'ISSUE'
        results.append({
            'country': ts['country'],
            'name': ts['name'],
            'source': src,
            'lat': ts['lat'], 'lon': ts['lon'],
            'tz_offset': ts['tz_offset'],
            'expected_tz': exp_tz,
            'reason': reason,
            'nb_info': nb_info,
            'phase_note': phase_note,
            'amp_note': amp_note,
            'issues': '; '.join(f'{t}: {m}' for t, m in issues),
            'status': status,
        })
        if issues:
            for t, m in issues:
                issues_by_country[ts['country']].append((ts['name'], src, t, m))

    # Konsolenausgabe pro Land
    print("\n" + "="*90)
    print("ERGEBNISSE PRO LAND")
    print("="*90)
    for country in sorted(set(s['country'] for s in unchecked)):
        country_results = [r for r in results if r['country'] == country]
        n_total = len(country_results)
        n_issues = sum(1 for r in country_results if r['status'] == 'ISSUE')
        print(f"\n── {country} ({n_total} Stationen, {n_issues} mit Auffälligkeiten) ──")
        for r in country_results:
            tag = '⚠' if r['status'] == 'ISSUE' else ' '
            print(f"  {tag} {r['name']:40s} [{r['source']:12s}] {r['phase_note']}")
            if r['status'] == 'ISSUE':
                for ttype, msg in [x.split(': ', 1) for x in r['issues'].split('; ')]:
                    print(f"      {ttype}: {msg}")

    # Zusammenfassung
    print("\n" + "="*90)
    print("ZUSAMMENFASSUNG")
    print("="*90)
    total_issues = sum(1 for r in results if r['status'] == 'ISSUE')
    by_type = defaultdict(int)
    for r in results:
        if r['status'] == 'ISSUE':
            for entry in r['issues'].split('; '):
                t = entry.split(':', 1)[0]
                by_type[t] += 1
    print(f"  Stationen geprüft: {len(results)}")
    print(f"  Mit Auffälligkeiten: {total_issues}")
    print(f"  Typen:")
    for t in sorted(by_type.keys()):
        print(f"    {t}: {by_type[t]}")

    # CSV
    with open(OUTPUT_CSV, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=list(results[0].keys()), delimiter=';')
        w.writeheader()
        w.writerows(results)
    print(f"\nCSV: {OUTPUT_CSV}")


if __name__ == '__main__':
    main()
