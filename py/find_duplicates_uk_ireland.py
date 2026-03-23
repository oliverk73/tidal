#!/usr/bin/env python3
"""
Find duplicate stations between UK BODC and Ireland harmonics files.
Compares by geographic proximity (within 5km) and fuzzy name matching.
"""

import re
import math
from collections import defaultdict

# Files to analyze
FILES = {
    'UK_BODC': '/home/oliver/harmonics/utide/harmonics_utide_uk_bodc.txt',
    'Ireland': '/home/oliver/harmonics/utide/harmonics_utide_ireland.txt',
}

# Constituent names in order (we need to know which index is M2)
CONSTITUENT_ORDER = []


def haversine_km(lat1, lon1, lat2, lon2):
    """Calculate distance in km between two points."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return R * 2 * math.asin(math.sqrt(a))


def levenshtein(s1, s2):
    """Simple Levenshtein distance."""
    if len(s1) < len(s2):
        return levenshtein(s2, s1)
    if len(s2) == 0:
        return len(s1)
    prev = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        curr = [i + 1]
        for j, c2 in enumerate(s2):
            curr.append(min(prev[j+1]+1, curr[j]+1, prev[j]+(c1 != c2)))
        prev = curr
    return prev[-1]


def normalize_name(name):
    """Normalize station name for comparison."""
    # Remove country/region suffixes after last comma-separated part
    # Keep core station name
    n = name.strip().lower()
    # Remove common suffixes
    n = re.sub(r',\s*(united kingdom|ireland|northern ireland|england|scotland|wales|channel islands|denmark|isle of man).*$', '', n, flags=re.IGNORECASE)
    n = re.sub(r'\s+', ' ', n).strip()
    return n


def fuzzy_match(name1, name2, threshold=0.65):
    """Check if two names are similar enough to be duplicates."""
    n1 = normalize_name(name1)
    n2 = normalize_name(name2)

    # Exact match after normalization
    if n1 == n2:
        return True, 1.0

    # One contained in the other
    if n1 in n2 or n2 in n1:
        return True, 0.9

    # Levenshtein similarity
    max_len = max(len(n1), len(n2))
    if max_len == 0:
        return False, 0.0
    dist = levenshtein(n1, n2)
    similarity = 1.0 - dist / max_len

    return similarity >= threshold, similarity


def parse_stations(filepath, source_name):
    """Parse all stations from an XTide harmonics file."""
    stations = []

    with open(filepath, 'r', encoding='iso-8859-1') as f:
        content = f.read()

    lines = content.split('\n')

    # Find constituent order from header
    global CONSTITUENT_ORDER
    if not CONSTITUENT_ORDER:
        in_speeds = False
        for line in lines:
            if line.strip().startswith('# Constituent speeds'):
                in_speeds = True
                continue
            if in_speeds and not line.startswith('#') and line.strip():
                parts = line.strip().split()
                if len(parts) == 2:
                    try:
                        float(parts[1])
                        CONSTITUENT_ORDER.append(parts[0])
                    except ValueError:
                        break
                else:
                    break

    # Find the start of harmonic constants section (after second *END*)
    end_count = 0
    start_idx = 0
    for i, line in enumerate(lines):
        if line.strip() == '*END*':
            end_count += 1
            if end_count == 2:
                start_idx = i + 1
                break

    # Parse station blocks
    # Each station block starts with a comment block (# ...) followed by:
    # Line 1: Station name
    # Line 2: time meridian tzfile
    # Line 3: DATUM units
    # Lines 4-178: constituent data (175 lines)

    i = start_idx
    while i < len(lines):
        # Skip comment lines
        while i < len(lines) and (lines[i].startswith('#') or lines[i].strip() == ''):
            # Extract metadata from comments
            i += 1

        if i >= len(lines):
            break

        # Station name line
        station_name = lines[i].strip()
        if not station_name or station_name.startswith('#'):
            i += 1
            continue

        # Look back for coordinate comments
        lat = None
        lon = None
        r2 = None
        rms = None
        n_obs = None
        confidence = None

        j = i - 1
        while j >= 0 and (lines[j].startswith('#') or lines[j].strip() == ''):
            line = lines[j].strip()
            if '!latitude:' in line:
                try:
                    lat = float(line.split('!latitude:')[1].strip())
                except:
                    pass
            if '!longitude:' in line:
                try:
                    lon = float(line.split('!longitude:')[1].strip())
                except:
                    pass
            if 'R^2' in line:
                m = re.search(r'R\^2\s*=\s*([\d.]+)', line)
                if m:
                    r2 = float(m.group(1))
                m = re.search(r'RMS error\s*=\s*([\d.]+)', line)
                if m:
                    rms = float(m.group(1))
            if 'observations' in line:
                m = re.search(r'with\s+([\d]+)\s+observations', line)
                if m:
                    n_obs = int(m.group(1))
            if 'confidence:' in line:
                m = re.search(r'confidence:\s*(\d+)', line)
                if m:
                    confidence = int(m.group(1))
            j -= 1

        i += 1  # Skip name line

        if i >= len(lines):
            break

        # Time meridian line
        tz_line = lines[i].strip()
        i += 1

        if i >= len(lines):
            break

        # Datum line
        datum_line = lines[i].strip()
        i += 1

        # Parse 175 constituent lines
        constituents = {}
        non_zero_count = 0
        m2_amplitude = 0.0

        for c_idx in range(175):
            if i >= len(lines):
                break
            line = lines[i].strip()
            i += 1

            if not line:
                continue

            # Handle "x 0 0" placeholder lines
            if line.startswith('x '):
                parts = line.split()
                if len(parts) == 3:
                    try:
                        amp = float(parts[1])
                        phase = float(parts[2])
                        if amp > 0:
                            non_zero_count += 1
                        continue
                    except:
                        pass

            parts = line.split()
            if len(parts) >= 3:
                name = parts[0]
                try:
                    amp = float(parts[1])
                    phase = float(parts[2])
                    constituents[name] = (amp, phase)
                    if amp > 0:
                        non_zero_count += 1
                    if name == 'M2':
                        m2_amplitude = amp
                except ValueError:
                    pass

        stations.append({
            'name': station_name,
            'lat': lat,
            'lon': lon,
            'non_zero': non_zero_count,
            'm2_amp': m2_amplitude,
            'r2': r2,
            'rms': rms,
            'n_obs': n_obs,
            'confidence': confidence,
            'source': source_name,
            'constituents': constituents,
        })

    return stations


def find_duplicates(all_stations, distance_threshold_km=5.0, name_threshold=0.65):
    """Find duplicate station clusters."""
    duplicates = []
    n = len(all_stations)
    matched = set()

    for i in range(n):
        if i in matched:
            continue
        cluster = [i]
        for j in range(i+1, n):
            if j in matched:
                continue

            s1 = all_stations[i]
            s2 = all_stations[j]

            # Check geographic proximity
            geo_match = False
            dist = None
            if s1['lat'] is not None and s2['lat'] is not None:
                dist = haversine_km(s1['lat'], s1['lon'], s2['lat'], s2['lon'])
                geo_match = dist < distance_threshold_km

            # Check name similarity
            name_match, similarity = fuzzy_match(s1['name'], s2['name'])

            if geo_match or (name_match and (dist is None or dist < 50)):
                cluster.append(j)
                matched.add(j)

        if len(cluster) > 1:
            matched.add(i)
            duplicates.append(cluster)

    return duplicates


def quality_score(station):
    """Calculate a quality score for a station. Higher is better."""
    score = 0
    score += station['non_zero'] * 2  # More non-zero constituents = better
    score += station['m2_amp'] * 10   # Higher M2 = more tidal signal
    if station['r2'] is not None:
        score += station['r2'] * 100  # Higher R^2 = better fit
    if station['n_obs'] is not None:
        score += min(station['n_obs'] / 10000, 50)  # More observations, capped
    if station['confidence'] is not None:
        score += station['confidence'] * 5
    return score


def main():
    all_stations = []

    for source_name, filepath in FILES.items():
        print(f"Parsing {source_name}: {filepath}")
        stations = parse_stations(filepath, source_name)
        print(f"  Found {len(stations)} stations")
        all_stations.extend(stations)

    print(f"\nTotal stations: {len(all_stations)}")
    print()

    # List all stations per file
    for source in FILES:
        src_stations = [s for s in all_stations if s['source'] == source]
        print(f"--- {source} ({len(src_stations)} stations) ---")
        for s in sorted(src_stations, key=lambda x: x['name']):
            r2_str = f"{s['r2']:.4f}" if s['r2'] else 'N/A'
            lat_str = f"{s['lat']:8.4f}" if s['lat'] is not None else '     N/A'
            lon_str = f"{s['lon']:9.4f}" if s['lon'] is not None else '      N/A'
            print(f"  {s['name']:<60s}  lat={lat_str}  lon={lon_str}  "
                  f"nonzero={s['non_zero']:3d}  M2={s['m2_amp']:.4f}  "
                  f"R2={r2_str:>6s}  "
                  f"conf={s['confidence']}")
        print()

    # Find duplicates
    print("=" * 120)
    print("DUPLICATE ANALYSIS (within 5km distance OR similar names)")
    print("=" * 120)

    duplicates = find_duplicates(all_stations)

    if not duplicates:
        print("\nNo duplicates found!")
        return

    print(f"\nFound {len(duplicates)} duplicate clusters:\n")

    for idx, cluster in enumerate(duplicates, 1):
        stations_in_cluster = [all_stations[i] for i in cluster]

        print(f"{'='*100}")
        print(f"DUPLICATE CLUSTER #{idx}")
        print(f"{'='*100}")

        # Calculate distances between all pairs
        for ci, si in enumerate(stations_in_cluster):
            for cj, sj in enumerate(stations_in_cluster):
                if ci < cj and si['lat'] and sj['lat']:
                    dist = haversine_km(si['lat'], si['lon'], sj['lat'], sj['lon'])
                    _, sim = fuzzy_match(si['name'], sj['name'])
                    print(f"  Distance: {dist:.2f} km | Name similarity: {sim:.2f}")

        print()

        # Sort by quality score (best first)
        scored = [(s, quality_score(s)) for s in stations_in_cluster]
        scored.sort(key=lambda x: -x[1])

        for rank, (s, score) in enumerate(scored):
            label = ">>> KEEP <<<" if rank == 0 else "    DELETE  "
            print(f"  {label}  [{s['source']}]")
            print(f"    Name:          {s['name']}")
            print(f"    Coordinates:   {s['lat']:.6f}, {s['lon']:.6f}")
            print(f"    Non-zero:      {s['non_zero']}")
            print(f"    M2 amplitude:  {s['m2_amp']:.4f} m")
            print(f"    R^2:           {s['r2']}")
            print(f"    RMS error:     {s['rms']}")
            print(f"    Observations:  {s['n_obs']}")
            print(f"    Confidence:    {s['confidence']}")
            print(f"    Quality score: {score:.1f}")
            print()

        # Compare M2 amplitudes
        if len(scored) == 2:
            s1, sc1 = scored[0]
            s2, sc2 = scored[1]
            m2_diff = abs(s1['m2_amp'] - s2['m2_amp'])
            if max(s1['m2_amp'], s2['m2_amp']) > 0:
                m2_pct = m2_diff / max(s1['m2_amp'], s2['m2_amp']) * 100
            else:
                m2_pct = 0
            print(f"  M2 difference: {m2_diff:.4f} m ({m2_pct:.1f}%)")
            print(f"  Quality score difference: {sc1 - sc2:.1f}")

            # Recommendation detail
            reasons = []
            if s1['non_zero'] > s2['non_zero']:
                reasons.append(f"more non-zero constituents ({s1['non_zero']} vs {s2['non_zero']})")
            elif s1['non_zero'] < s2['non_zero']:
                reasons.append(f"fewer non-zero constituents ({s1['non_zero']} vs {s2['non_zero']}), but better overall")

            if s1['r2'] and s2['r2']:
                if s1['r2'] > s2['r2']:
                    reasons.append(f"higher R^2 ({s1['r2']} vs {s2['r2']})")

            if s1['n_obs'] and s2['n_obs']:
                if s1['n_obs'] > s2['n_obs']:
                    reasons.append(f"more observations ({s1['n_obs']} vs {s2['n_obs']})")

            if reasons:
                print(f"  Reason to keep [{s1['source']}] {s1['name']}: {'; '.join(reasons)}")

        print()

    # Summary
    print("=" * 120)
    print("SUMMARY: Stations to DELETE")
    print("=" * 120)
    for idx, cluster in enumerate(duplicates, 1):
        stations_in_cluster = [all_stations[i] for i in cluster]
        scored = [(s, quality_score(s)) for s in stations_in_cluster]
        scored.sort(key=lambda x: -x[1])

        for rank, (s, score) in enumerate(scored):
            if rank > 0:
                print(f"  DELETE from [{s['source']}]: {s['name']} "
                      f"(lat={s['lat']:.4f}, lon={s['lon']:.4f}, M2={s['m2_amp']:.4f})")


if __name__ == '__main__':
    main()
