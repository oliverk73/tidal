#!/usr/bin/env python3
"""
Plausibility check for TICON4 stations against all other harmonics sources.

Checks:
1. Phase: M2 phase vs nearest same-name or close non-TICON4 station
   - Flag ~29° (1h CET/timezone error)
   - Flag large phase diff only for very close neighbours (<50km)
2. Amplitude: M2 amplitude ratio vs close neighbour
3. Coordinates: lat/lon sanity, distance to nearest same-name station
4. Timezone vs longitude consistency
5. Z0 comparison only when datums match
6. Missing/zero M2
"""

import math
import os
import re
import sys
from collections import defaultdict

HARMONICS_DIRS = [
    "/home/oliver/harmonics/classic",
    "/home/oliver/harmonics/ihm",
    "/home/oliver/harmonics/utide",
    "/home/oliver/harmonics/ticon",
]

M2_SPEED = 28.984104  # degrees per hour


def parse_harmonics_file(txt_path):
    """Parse a harmonics .txt file. Returns list of station dicts."""
    stations = []
    with open(txt_path, 'r', encoding='iso-8859-1') as f:
        lines = f.readlines()

    # Find number of constituents from header
    num_constituents = None
    header_end = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped == '# Number of constituents':
            for j in range(i + 1, min(i + 5, len(lines))):
                if not lines[j].startswith('#'):
                    num_constituents = int(lines[j].strip())
                    break
        if stripped == '*END*':
            header_end = i + 1
            break

    # Parse stations
    lat = lon = None
    source_id = datum = country = units = None
    basename = os.path.basename(txt_path)

    i = header_end
    while i < len(lines):
        line = lines[i].rstrip()

        if line.startswith('# !latitude:'):
            try:
                lat = float(line.split(':', 1)[1].strip())
            except ValueError:
                lat = None
        elif line.startswith('# !longitude:'):
            try:
                lon = float(line.split(':', 1)[1].strip())
            except ValueError:
                lon = None
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
            tz_offset_hours = parse_tz_offset(tz_line)
            z0_line = lines[i + 2].strip() if i + 2 < len(lines) else '0'
            z0, z0_units = parse_z0(z0_line)

            constituents = {}
            if num_constituents:
                for ci in range(num_constituents):
                    cline = lines[i + 3 + ci].strip() if i + 3 + ci < len(lines) else 'x 0 0'
                    if cline.startswith('x '):
                        continue
                    parts = cline.split()
                    if len(parts) >= 3:
                        try:
                            constituents[parts[0]] = (float(parts[1]), float(parts[2]))
                        except ValueError:
                            pass
                i += 3 + num_constituents
            else:
                ci = i + 3
                while ci < len(lines):
                    cline = lines[ci].strip()
                    if cline.startswith('#') or cline == '':
                        break
                    if not cline.startswith('x '):
                        parts = cline.split()
                        if len(parts) >= 3:
                            try:
                                constituents[parts[0]] = (float(parts[1]), float(parts[2]))
                            except ValueError:
                                pass
                    ci += 1
                i = ci

            is_current = (units in ('knots', 'knots^2'))
            stations.append({
                'name': name,
                'lat': lat,
                'lon': lon,
                'tz_offset': tz_offset_hours,
                'z0': z0,
                'z0_units': z0_units,
                'constituents': constituents,
                'source_id': source_id or '',
                'datum': datum or '',
                'country': country or '',
                'source_file': basename,
                'is_current': is_current,
            })
            lat = lon = None
            source_id = datum = country = units = None
            continue
        i += 1

    return stations


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
        val = float(parts[0])
        unit = parts[1] if len(parts) > 1 else 'meters'
        return val, unit
    except (ValueError, IndexError):
        return 0.0, 'meters'


def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) ** 2)
    return R * 2 * math.asin(min(1.0, math.sqrt(a)))


def phase_diff(p1, p2):
    """Signed phase difference, range -180..+180."""
    d = (p1 - p2) % 360
    return d - 360 if d > 180 else d


def m2_amplitude_meters(station):
    m2 = station['constituents'].get('M2')
    if not m2:
        return None
    amp = m2[0]
    if station['z0_units'] == 'feet':
        amp *= 0.3048
    return amp


def m2_phase_at_greenwich(station):
    """Convert M2 phase to UTC-referenced phase."""
    m2 = station['constituents'].get('M2')
    if not m2:
        return None
    return (m2[1] + M2_SPEED * station['tz_offset']) % 360


def z0_meters(station):
    if station['z0_units'] == 'feet':
        return station['z0'] * 0.3048
    return station['z0']


def normalize_name(name):
    """Normalize station name for fuzzy matching."""
    n = name.lower()
    # Remove country/region suffixes for matching
    n = re.sub(r',\s*(france|spain|germany|netherlands|australia|canada|'
               r'japan|new zealand|united kingdom|ireland|italy|'
               r'norway|sweden|denmark|portugal|belgium|china|'
               r'french polynesia|south africa|india|sri lanka|'
               r'thailand|indonesia|malaysia|philippines|bangladesh|'
               r'mexico|chile|peru|colombia|argentina|brazil|'
               r'tonga|samoa|fiji|kiribati|tuvalu|tokelau|vanuatu|'
               r'solomon islands|marshall islands|micronesia|palau|'
               r'papua new guinea|bahamas|bermuda|senegal|gambia|'
               r'hong kong|singapore|taiwan|south korea|'
               r'croatia|greece|turkey|poland|finland|estonia|'
               r'bulgaria|russia|iceland|scotland|wales|england)$', '', n)
    # Remove common suffixes
    n = re.sub(r'\s*\(.*?\)', '', n)  # parenthetical
    n = re.sub(r',\s*(south australia|western australia|new south wales|'
               r'queensland|victoria|tasmania|northern territory|'
               r'nunavut|british columbia|nova scotia|newfoundland|'
               r'hokkaido|honshu|kyushu|shikoku)$', '', n)
    n = n.strip().strip(',').strip()
    return n


def find_best_neighbour(ts, other_stations, max_dist_km=500):
    """Find best matching non-TICON4 station: prefer same name, then closest with M2."""
    ts_norm = normalize_name(ts['name'])
    ts_m2 = ts['constituents'].get('M2')

    best_name_match = None
    best_name_dist = float('inf')
    best_close = None
    best_close_dist = float('inf')

    for os_ in other_stations:
        if os_['is_current'] != ts['is_current']:
            continue
        if 'M2' not in os_['constituents']:
            continue

        d = haversine_km(ts['lat'], ts['lon'], os_['lat'], os_['lon'])

        # Same-name match (strongest signal)
        os_norm = normalize_name(os_['name'])
        if ts_norm == os_norm or ts_norm.startswith(os_norm) or os_norm.startswith(ts_norm):
            if d < best_name_dist:
                best_name_dist = d
                best_name_match = os_

        # Closest station
        if d < best_close_dist:
            best_close_dist = d
            best_close = os_

    # Prefer name match if within 100km, otherwise closest
    if best_name_match and best_name_dist < 100:
        return best_name_match, best_name_dist
    if best_close and best_close_dist < max_dist_km:
        return best_close, best_close_dist
    return None, None


def datum_compatible(d1, d2):
    """Check if two datums are likely the same reference."""
    if not d1 or not d2:
        return False
    d1 = d1.lower().strip()
    d2 = d2.lower().strip()
    if d1 == d2:
        return True
    # Normalize common datum names
    msl_names = {'msl', 'mean sea level', 'msl (mean sea level)'}
    cd_names = {'cd', 'chart datum', 'chart datum (cd)', 'lat',
                'lowest astronomical tide', 'lowest astronomical tide (lat)',
                'zero hydrographique', 'zh'}
    if d1 in msl_names and d2 in msl_names:
        return True
    if d1 in cd_names and d2 in cd_names:
        return True
    return False


def main():
    import glob as globmod

    all_files = []
    for hdir in HARMONICS_DIRS:
        for f in sorted(globmod.glob(os.path.join(hdir, '*.txt'))):
            if 'backup' not in f:
                all_files.append(f)

    print(f"Parsing {len(all_files)} harmonics files...")

    ticon_stations = []
    other_stations = []

    for fpath in all_files:
        basename = os.path.basename(fpath)
        try:
            stations = parse_harmonics_file(fpath)
        except Exception as e:
            print(f"  ERROR parsing {basename}: {e}")
            continue

        is_ticon = 'ticon' in basename.lower()
        for s in stations:
            if is_ticon:
                ticon_stations.append(s)
            else:
                other_stations.append(s)
        print(f"  {basename}: {len(stations):4d} stations ({'TICON4' if is_ticon else 'other'})")

    print(f"\nTotal: {len(ticon_stations)} TICON4, {len(other_stations)} other stations")

    # Filter other stations to non-current with M2
    other_with_m2 = [s for s in other_stations if 'M2' in s['constituents'] and not s['is_current']]
    print(f"Reference stations with M2 (non-current): {len(other_with_m2)}")

    # Run checks
    issues_by_type = defaultdict(list)
    stations_ok = 0
    no_neighbour = 0

    for ts in ticon_stations:
        station_issues = []
        src_suffix = ts['source_id'].split('-')[-1] if ts['source_id'] else '?'

        # --- Check: Missing or zero M2 ---
        m2 = ts['constituents'].get('M2')
        if not m2 or m2[0] == 0:
            station_issues.append(('MISSING_M2', 'No M2 constituent or amplitude=0', None, None))

        # --- Check: Coordinates at (0,0) ---
        if abs(ts['lat']) < 0.01 and abs(ts['lon']) < 0.01:
            station_issues.append(('COORDS_ZERO', 'Coordinates at (0, 0)', None, None))

        if abs(ts['lat']) > 90:
            station_issues.append(('COORDS_INVALID', f'Latitude {ts["lat"]} out of range', None, None))

        # --- Check: Timezone vs longitude ---
        expected_tz = round(ts['lon'] / 15.0)
        tz_diff = abs(ts['tz_offset'] - expected_tz)
        # Only flag if TZ is non-zero and discrepancy is huge (>5h)
        # Many legitimate exceptions: China +8 for all, France overseas +1, etc.
        if ts['tz_offset'] != 0 and tz_diff > 5:
            station_issues.append(('TZ_LONGITUDE_MISMATCH',
                f'TZ {ts["tz_offset"]:+.0f}h but longitude {ts["lon"]:.1f}° '
                f'suggests ~{expected_tz:+.0f}h (diff {tz_diff:.0f}h)',
                None, None))

        # --- Find best reference station ---
        if m2 and m2[0] > 0 and not ts['is_current']:
            neighbour, dist = find_best_neighbour(ts, other_with_m2)

            if neighbour and dist is not None:
                ts_m2_utc = m2_phase_at_greenwich(ts)
                nb_m2_utc = m2_phase_at_greenwich(neighbour)
                ts_m2_amp = m2_amplitude_meters(ts)
                nb_m2_amp = m2_amplitude_meters(neighbour)

                nb_info = f'{neighbour["name"]} [{neighbour["source_file"]}] ({dist:.0f}km)'

                # --- Phase check ---
                if ts_m2_utc is not None and nb_m2_utc is not None:
                    pdiff = phase_diff(ts_m2_utc, nb_m2_utc)

                    # 1h offset: flag for all distances up to 200km
                    if 24 <= abs(pdiff) <= 34 and dist < 200:
                        station_issues.append(('PHASE_1H_OFFSET',
                            f'M2 phase diff {pdiff:+.1f}° vs {nb_info}',
                            neighbour, dist))

                    # Large phase diff: only flag for very close stations (<30km)
                    # and exclude microtidal areas where phases are unreliable
                    elif abs(pdiff) > 45 and dist < 30 and ts_m2_amp > 0.05 and nb_m2_amp > 0.05:
                        station_issues.append(('PHASE_LARGE_DIFF',
                            f'M2 phase diff {pdiff:+.1f}° vs {nb_info}',
                            neighbour, dist))

                # --- Amplitude check (only for close stations, <50km) ---
                if ts_m2_amp and nb_m2_amp and nb_m2_amp > 0.01 and dist < 50:
                    ratio = ts_m2_amp / nb_m2_amp
                    if ratio > 5.0 or ratio < 0.2:
                        station_issues.append(('AMP_RATIO_EXTREME',
                            f'M2 amp ratio {ratio:.2f}x vs {nb_info} '
                            f'[{ts_m2_amp:.4f}m vs {nb_m2_amp:.4f}m]',
                            neighbour, dist))

                # --- Z0 check (only if datums match and close) ---
                if dist < 30:
                    ts_z0 = z0_meters(ts)
                    nb_z0 = z0_meters(neighbour)
                    z0_d = abs(ts_z0 - nb_z0)

                    if datum_compatible(ts['datum'], neighbour['datum']):
                        if z0_d > 1.0:
                            station_issues.append(('Z0_SAME_DATUM',
                                f'Z0 diff {z0_d:.2f}m vs {nb_info} '
                                f'[{ts_z0:.2f}m vs {nb_z0:.2f}m, '
                                f'datums: {ts["datum"]} / {neighbour["datum"]}]',
                                neighbour, dist))

                # --- Coordinate check: same name but far apart ---
                ts_norm = normalize_name(ts['name'])
                nb_norm = normalize_name(neighbour['name'])
                if (ts_norm == nb_norm or ts_norm.startswith(nb_norm) or
                        nb_norm.startswith(ts_norm)):
                    if dist > 50:
                        station_issues.append(('COORDS_NAME_FAR',
                            f'Same name but {dist:.0f}km from {nb_info}',
                            neighbour, dist))
            else:
                no_neighbour += 1

        if station_issues:
            for itype, msg, nb, dist in station_issues:
                issues_by_type[itype].append((ts, msg))
        else:
            stations_ok += 1

    # Print results
    print(f"\n{'='*80}")
    print(f"TICON4 PLAUSIBILITY CHECK RESULTS")
    print(f"{'='*80}")
    print(f"Checked: {len(ticon_stations)} TICON4 stations")
    print(f"OK (no issues): {stations_ok}")
    print(f"No reference neighbour found: {no_neighbour}")

    total_issues = sum(len(v) for v in issues_by_type.values())
    stations_with_issues = len(set(ts['name'] + ts['source_id']
                                   for entries in issues_by_type.values()
                                   for ts, _ in entries))
    print(f"Stations with issues: {stations_with_issues}")
    print(f"Total issue count: {total_issues}")

    type_order = [
        'MISSING_M2', 'COORDS_ZERO', 'COORDS_INVALID',
        'TZ_LONGITUDE_MISMATCH', 'COORDS_NAME_FAR',
        'PHASE_1H_OFFSET', 'PHASE_LARGE_DIFF',
        'AMP_RATIO_EXTREME', 'Z0_SAME_DATUM',
    ]

    for itype in type_order:
        entries = issues_by_type.get(itype, [])
        if not entries:
            continue

        print(f"\n{'='*80}")
        print(f"  {itype} ({len(entries)} stations)")
        print(f"{'='*80}")

        # Sort by source, then name
        entries.sort(key=lambda x: (
            x[0].get('source_id', '').split('-')[-1],
            x[0]['name']))

        for ts, msg in entries:
            src_suffix = ts['source_id'].split('-')[-1] if ts['source_id'] else '?'
            print(f"\n  [{src_suffix:12s}] {ts['name']}")
            print(f"    {msg}")
            print(f"    Coords: {ts['lat']:.4f}, {ts['lon']:.4f}  "
                  f"TZ: {ts['tz_offset']:+.0f}h  Country: {ts['country']}  "
                  f"Datum: {ts['datum']}")

    # --- PHASE_1H_OFFSET analysis by source ---
    phase_1h = issues_by_type.get('PHASE_1H_OFFSET', [])
    if phase_1h:
        print(f"\n{'='*80}")
        print(f"  PHASE_1H_OFFSET — ANALYSIS BY DATA SOURCE")
        print(f"{'='*80}")
        by_src = defaultdict(lambda: {'positive': 0, 'negative': 0, 'stations': []})
        for ts, msg in phase_1h:
            src = ts['source_id'].split('-')[-1] if ts['source_id'] else '?'
            # Parse the phase diff from the message
            m = re.search(r'([+-]\d+\.\d+)°', msg)
            if m:
                pdiff = float(m.group(1))
                if pdiff > 0:
                    by_src[src]['positive'] += 1
                else:
                    by_src[src]['negative'] += 1
                by_src[src]['stations'].append((ts['name'], pdiff))

        for src in sorted(by_src.keys()):
            info = by_src[src]
            total = info['positive'] + info['negative']
            direction = 'POSITIVE' if info['positive'] > info['negative'] else 'NEGATIVE'
            dominant = max(info['positive'], info['negative'])
            print(f"\n  {src}: {total} stations ({info['positive']}×positive, {info['negative']}×negative) "
                  f"→ {direction} bias ({dominant}/{total})")
            # Show if this is a systematic issue (>80% same direction)
            if dominant / total > 0.8:
                avg = sum(pd for _, pd in info['stations']) / len(info['stations'])
                print(f"    ⚠ SYSTEMATIC: avg {avg:+.1f}° ≈ {abs(avg)/M2_SPEED*60:+.0f} min")
                print(f"    Suggests: timezone meridian off by ~1h")
            for name, pd in sorted(info['stations'], key=lambda x: x[0]):
                print(f"    {pd:+6.1f}°  {name}")

    # --- Summary by source ---
    print(f"\n{'='*80}")
    print(f"  SUMMARY BY DATA SOURCE")
    print(f"{'='*80}")

    source_stats = defaultdict(lambda: {'total': 0, 'ok': 0, 'issues': defaultdict(int)})
    for ts in ticon_stations:
        src = ts['source_id'].split('-')[-1] if ts['source_id'] else '?'
        source_stats[src]['total'] += 1

    # Count OK stations per source
    issue_station_keys = set()
    for itype, entries in issues_by_type.items():
        for ts, _ in entries:
            src = ts['source_id'].split('-')[-1] if ts['source_id'] else '?'
            key = ts['name'] + '|' + ts['source_id']
            source_stats[src]['issues'][itype] += 1
            issue_station_keys.add((src, key))

    for src in sorted(source_stats.keys(), key=lambda x: -source_stats[x]['total']):
        ss = source_stats[src]
        n_with_issues = len([k for s, k in issue_station_keys if s == src])
        n_ok = ss['total'] - n_with_issues
        print(f"\n  {src:15s}: {ss['total']:3d} total, {n_ok:3d} OK, {n_with_issues:3d} with issues")
        for itype in type_order:
            cnt = ss['issues'].get(itype, 0)
            if cnt > 0:
                print(f"    {itype:25s}: {cnt:3d}")


if __name__ == '__main__':
    main()
