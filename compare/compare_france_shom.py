#!/usr/bin/env python3
"""
Compare French tide station predictions from multiple harmonics sources
against SHOM observations (water level measurements).

Sources compared:
1. UTide France (harmonics_utide_france.tcd) — 93-constituent UTide analysis from SHOM observations
2. TICON4 (harmonics_ticon4_worldwide_edited.tcd) — TICON4 worldwide database
3. Pierre Lavergne v10 (harmonics_pierre_lavergne_v10.tcd) — Classic XTide harmonics

Reference: SHOM REFMAR observations (10-min validated water levels)
"""

import subprocess
import re
import os
import sys
import math
import numpy as np
from datetime import datetime, timedelta
from scipy.signal import find_peaks

# Harmonics sources to compare
SOURCES = {
    'UTide': '/usr/share/xtide/harmonics_utide_france.tcd',
    'TICON4': '/usr/share/xtide/harmonics_ticon4_worldwide_edited.tcd',
    'PLv10': '/home/oliver/harmonics/classic/harmonics_pierre_lavergne_v10.tcd',
}

NPZ_DIR = '/home/oliver/water_levels/France_SHOM/npz/'

# Comparison period: use January 2025 (recent data, most stations have it)
COMP_START = np.datetime64('2025-01-01')
COMP_END = np.datetime64('2025-01-31')


def haversine(lat1, lon1, lat2, lon2):
    """Distance in km between two points."""
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))


def get_xtide_stations(tcd_path):
    """Get French tide stations from TCD file with coordinates."""
    env = os.environ.copy()
    env['HFILE_PATH'] = tcd_path
    result = subprocess.run(['tide', '-m', 'l'], capture_output=True, text=True, env=env, timeout=30)

    stations = []
    for line in result.stdout.strip().split('\n'):
        if not line.strip() or 'Location list' in line:
            continue
        # Extract name and coordinates
        m = re.match(r'^(.+?)\s+(Ref|Sub)\s+([\d.]+)°\s+([NS]),\s*([\d.]+)°\s+([EW])', line.strip())
        if m:
            name = m.group(1).strip()
            lat = float(m.group(3)) * (1 if m.group(4) == 'N' else -1)
            lon = float(m.group(5)) * (1 if m.group(6) == 'E' else -1)
            if ', France' in name and 'Current' not in name:
                stations.append({'name': name, 'lat': lat, 'lon': lon})
    return stations


def load_npz_stations():
    """Load all SHOM NPZ observation stations."""
    import glob
    stations = []
    for f in sorted(glob.glob(NPZ_DIR + '*.npz')):
        d = np.load(f, allow_pickle=True)
        name = str(d['name'])
        lat = float(d['latitude'])
        lon = float(d['longitude'])
        times = d['datetimes_utc']

        # Check if station has data in our comparison period
        if times[-1] < COMP_START or times[0] > COMP_END:
            continue

        stations.append({
            'name': name,
            'lat': lat,
            'lon': lon,
            'file': f,
        })
    return stations


def extract_hw_nw_from_observations(npz_file, start, end):
    """Extract HW/NW events from 10-min water level observations."""
    d = np.load(npz_file, allow_pickle=True)
    times = d['datetimes_utc']
    levels = d['levels_m']

    # Select comparison period
    mask = (times >= start) & (times <= end)
    t = times[mask]
    l = levels[mask]

    if len(l) < 100:
        return []

    # Remove NaN
    valid = ~np.isnan(l)
    t = t[valid]
    l = l[valid]

    if len(l) < 100:
        return []

    # Find peaks (HW) and troughs (NW)
    # Distance: at least 4 hours (24 samples at 10min) between events
    hw_idx, _ = find_peaks(l, distance=24, prominence=0.1)
    nw_idx, _ = find_peaks(-l, distance=24, prominence=0.1)

    events = []
    for i in hw_idx:
        events.append({
            'datetime_utc': t[i],
            'height': l[i],
            'type': 'HW',
        })
    for i in nw_idx:
        events.append({
            'datetime_utc': t[i],
            'height': l[i],
            'type': 'NW',
        })

    return sorted(events, key=lambda x: x['datetime_utc'])


def get_xtide_predictions(station_name, tcd_path, start_dt, end_dt):
    """Get HW/NW predictions from XTide in UTC."""
    env = os.environ.copy()
    env['HFILE_PATH'] = tcd_path

    # Try getting predictions
    result = subprocess.run(
        ['tide', '-l', station_name,
         '-b', start_dt.strftime('%Y-%m-%d 00:00'),
         '-e', end_dt.strftime('%Y-%m-%d 00:00'),
         '-m', 'p', '-em', 'pSsMm'],
        capture_output=True, text=True, env=env, timeout=30,
    )

    if result.returncode != 0:
        return None

    # First, determine the timezone offset from the output
    events = []
    for line in result.stdout.strip().split('\n'):
        line = line.strip()
        if not line or line.startswith('Indexing') or '°' in line:
            continue

        # Format: "2025-01-01  2:27 AM CET   6.45 meters  High Tide"
        # or:     "2025-01-01 11:09 AM CET  -2.60 meters  Low Tide" (negative heights)
        m = re.match(
            r'(\d{4}-\d{2}-\d{2})\s+(\d{1,2}:\d{2}\s+[AP]M)\s+(\S+)\s+(-?[\d.]+)\s+meters\s+(High|Low)\s+Tide',
            line
        )
        if m:
            date_str = m.group(1)
            time_str = m.group(2)
            tz_str = m.group(3)
            height = float(m.group(4))
            tide_type = 'HW' if m.group(5) == 'High' else 'NW'

            dt_local = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %I:%M %p")

            # Convert to UTC based on timezone abbreviation
            tz_offsets = {
                'UTC': 0, 'WET': 0, 'GMT': 0,
                'CET': 1, 'MET': 1,
                'CEST': 2, 'MEST': 2,
                'WEST': 1, 'BST': 1,
                'HST': -10, 'AST': -4, 'EST': -5,
                'NCT': 11, 'WFT': 12, 'TAHT': -10,
                'SRT': -3, 'FET': 3,
                ':UTC': 0,
            }
            offset_hours = tz_offsets.get(tz_str, 1)  # Default CET
            dt_utc = dt_local - timedelta(hours=offset_hours)

            events.append({
                'datetime_utc': np.datetime64(dt_utc),
                'height': height,
                'type': tide_type,
            })

    return events if events else None


def adjust_datum(pred_events, obs_events):
    """Adjust prediction datum to match observations by shifting mean level."""
    if not pred_events or not obs_events:
        return pred_events

    # Check if there's a significant datum offset (>1m)
    pred_hw = [e['height'] for e in pred_events if e['type'] == 'HW']
    obs_hw = [e['height'] for e in obs_events if e['type'] == 'HW']

    if not pred_hw or not obs_hw:
        return pred_events

    offset = np.mean(obs_hw) - np.mean(pred_hw)

    if abs(offset) > 1.0:
        # Significant datum difference — adjust predictions
        adjusted = []
        for e in pred_events:
            e_adj = e.copy()
            e_adj['height'] = e['height'] + offset
            adjusted.append(e_adj)
        return adjusted

    return pred_events


def match_hw_nw(obs_events, pred_events, max_hours=3):
    """Match observed HW/NW with predicted HW/NW."""
    matches = []
    used = set()

    for obs in obs_events:
        best = None
        best_dt = np.timedelta64(max_hours, 'h')

        for j, pred in enumerate(pred_events):
            if j in used or pred['type'] != obs['type']:
                continue
            dt = abs(pred['datetime_utc'] - obs['datetime_utc'])
            if dt < best_dt:
                best_dt = dt
                best = (j, pred)

        if best is not None:
            j, pred = best
            used.add(j)
            time_diff_min = (pred['datetime_utc'] - obs['datetime_utc']) / np.timedelta64(1, 'm')
            height_diff = pred['height'] - obs['height']
            matches.append({
                'obs': obs, 'pred': pred,
                'time_diff_min': float(time_diff_min),
                'height_diff_m': float(height_diff),
            })

    return matches


def match_xtide_to_npz(xtide_stations, npz_stations, max_km=4):
    """Match XTide stations to NPZ observation stations by coordinates."""
    matches = []
    for xt in xtide_stations:
        best = None
        best_dist = max_km

        for npz in npz_stations:
            dist = haversine(xt['lat'], xt['lon'], npz['lat'], npz['lon'])
            if dist < best_dist:
                best_dist = dist
                best = npz

        if best is not None:
            matches.append({
                'xtide_name': xt['name'],
                'npz_name': best['name'],
                'npz_file': best['file'],
                'distance_km': best_dist,
            })

    return matches


def main():
    print("=" * 100)
    print("Vergleich: XTide-Harmonics vs SHOM-Beobachtungen — Januar 2025")
    print("=" * 100)

    # Load NPZ observation stations
    npz_stations = load_npz_stations()
    print(f"SHOM-Beobachtungsstationen mit Daten im Zeitraum: {len(npz_stations)}")

    # For each source, find stations, match to NPZ, compare
    all_results = {}  # source -> list of results
    all_matches_info = {}  # source -> {npz_name: xtide_name}

    # First pass: find which NPZ stations can be matched across sources
    for source_name, tcd_path in SOURCES.items():
        xt_stations = get_xtide_stations(tcd_path)
        matches = match_xtide_to_npz(xt_stations, npz_stations)
        all_matches_info[source_name] = {m['npz_name']: m for m in matches}
        print(f"\n{source_name}: {len(xt_stations)} frz. Stationen, {len(matches)} mit SHOM-Beobachtungen matched")

    # Extract observations once per NPZ station
    print("\n--- Lade Beobachtungsdaten und vergleiche ---")
    obs_cache = {}

    start_dt = datetime(2025, 1, 1)
    end_dt = datetime(2025, 1, 31)

    for source_name, tcd_path in SOURCES.items():
        source_results = []

        for npz_name, match_info in sorted(all_matches_info[source_name].items()):
            xtide_name = match_info['xtide_name']
            npz_file = match_info['npz_file']

            # Get observations (cached)
            if npz_name not in obs_cache:
                obs_events = extract_hw_nw_from_observations(npz_file, COMP_START, COMP_END)
                obs_cache[npz_name] = obs_events

            obs_events = obs_cache[npz_name]
            if not obs_events:
                continue

            # Get XTide predictions
            pred_events = get_xtide_predictions(xtide_name, tcd_path, start_dt, end_dt + timedelta(days=1))
            if not pred_events:
                continue

            # Adjust datum if needed (e.g., TICON4 uses MSL, SHOM uses LAT/ZH)
            pred_events = adjust_datum(pred_events, obs_events)

            # Match and compare
            matches = match_hw_nw(obs_events, pred_events)
            if not matches:
                continue

            hw_matches = [m for m in matches if m['obs']['type'] == 'HW']
            nw_matches = [m for m in matches if m['obs']['type'] == 'NW']

            result = {
                'npz_name': npz_name,
                'xtide_name': xtide_name,
                'source': source_name,
                'n_matches': len(matches),
                'n_hw': len(hw_matches),
                'n_nw': len(nw_matches),
                'hw_dt_mean': np.mean(np.abs([m['time_diff_min'] for m in hw_matches])) if hw_matches else 0,
                'hw_dh_mean': np.mean(np.abs([m['height_diff_m'] for m in hw_matches])) if hw_matches else 0,
                'nw_dt_mean': np.mean(np.abs([m['time_diff_min'] for m in nw_matches])) if nw_matches else 0,
                'nw_dh_mean': np.mean(np.abs([m['height_diff_m'] for m in nw_matches])) if nw_matches else 0,
                'hw_dt_bias': np.mean([m['time_diff_min'] for m in hw_matches]) if hw_matches else 0,
                'nw_dt_bias': np.mean([m['time_diff_min'] for m in nw_matches]) if nw_matches else 0,
                'hw_dh_bias': np.mean([m['height_diff_m'] for m in hw_matches]) if hw_matches else 0,
                'nw_dh_bias': np.mean([m['height_diff_m'] for m in nw_matches]) if nw_matches else 0,
            }
            source_results.append(result)
            print(f"  {source_name:6s} | {npz_name[:35]:<35s} {len(matches):>3d} Events: "
                  f"HW |dT|={result['hw_dt_mean']:.0f}min |dH|={result['hw_dh_mean']:.2f}m, "
                  f"NW |dT|={result['nw_dt_mean']:.0f}min |dH|={result['nw_dh_mean']:.2f}m")

        all_results[source_name] = source_results

    # === SUMMARY PER SOURCE ===
    print(f"\n\n{'='*100}")
    print("ZUSAMMENFASSUNG PRO QUELLE")
    print(f"{'='*100}")

    for source_name in SOURCES:
        src = all_results[source_name]
        if not src:
            print(f"\n  {source_name}: Keine Ergebnisse")
            continue

        print(f"\n  === {source_name} ({len(src)} Stationen) ===")
        print(f"  {'Station':<40s} {'N':>4s} {'|dT|HW':>7s} {'|dH|HW':>7s} {'|dT|NW':>7s} {'|dH|NW':>7s}")
        print(f"  {'─'*40} {'─'*4} {'─'*7} {'─'*7} {'─'*7} {'─'*7}")

        for r in sorted(src, key=lambda x: x['hw_dh_mean'] + x['nw_dh_mean']):
            print(f"  {r['npz_name'][:40]:<40s} {r['n_matches']:>4d} "
                  f"{r['hw_dt_mean']:>6.0f}m {r['hw_dh_mean']:>6.2f}m "
                  f"{r['nw_dt_mean']:>6.0f}m {r['nw_dh_mean']:>6.2f}m")

        n_total = sum(r['n_matches'] for r in src)
        avg_hw_dt = np.mean([r['hw_dt_mean'] for r in src])
        avg_hw_dh = np.mean([r['hw_dh_mean'] for r in src])
        avg_nw_dt = np.mean([r['nw_dt_mean'] for r in src])
        avg_nw_dh = np.mean([r['nw_dh_mean'] for r in src])
        print(f"  {'─'*40} {'─'*4} {'─'*7} {'─'*7} {'─'*7} {'─'*7}")
        print(f"  {'DURCHSCHNITT':<40s} {n_total:>4d} "
              f"{avg_hw_dt:>6.0f}m {avg_hw_dh:>6.2f}m "
              f"{avg_nw_dt:>6.0f}m {avg_nw_dh:>6.2f}m")

    # === DIRECT COMPARISON (common stations) ===
    # Find NPZ stations present in all sources
    common_npz = set.intersection(*[set(r['npz_name'] for r in all_results[s]) for s in SOURCES if all_results[s]])

    if common_npz:
        print(f"\n\n{'='*100}")
        print(f"DIREKTVERGLEICH: {len(common_npz)} Stationen in allen {len(SOURCES)} Quellen")
        print(f"{'='*100}")

        src_names = list(SOURCES.keys())
        header = f"  {'Station':<35s}"
        for s in src_names:
            header += f" │ {s:>6s}|dH| {s:>6s}|dT|"
        print(header)
        sep = f"  {'─'*35}"
        for s in src_names:
            sep += f"─┼─{'─'*8}{'─'*9}"
        print(sep)

        for npz_name in sorted(common_npz):
            line = f"  {npz_name[:35]:<35s}"
            for s in src_names:
                r = [x for x in all_results[s] if x['npz_name'] == npz_name]
                if r:
                    r = r[0]
                    avg_dh = (r['hw_dh_mean'] + r['nw_dh_mean']) / 2
                    avg_dt = (r['hw_dt_mean'] + r['nw_dt_mean']) / 2
                    line += f" │ {avg_dh:>7.2f}m {avg_dt:>7.0f}min"
                else:
                    line += f" │ {'---':>8s} {'---':>8s}"
            print(line)

        # Averages
        print(sep)
        avg_line = f"  {'DURCHSCHNITT':<35s}"
        for s in src_names:
            common_r = [x for x in all_results[s] if x['npz_name'] in common_npz]
            if common_r:
                avg_dh = np.mean([(r['hw_dh_mean'] + r['nw_dh_mean']) / 2 for r in common_r])
                avg_dt = np.mean([(r['hw_dt_mean'] + r['nw_dt_mean']) / 2 for r in common_r])
                avg_line += f" │ {avg_dh:>7.2f}m {avg_dt:>7.0f}min"
            else:
                avg_line += f" │ {'---':>8s} {'---':>8s}"
        print(avg_line)

    # === RANKING ===
    print(f"\n\n{'='*100}")
    print("RANKING DER QUELLEN")
    print(f"{'='*100}")

    ranking = []
    for source_name in SOURCES:
        if common_npz:
            common_r = [x for x in all_results[source_name] if x['npz_name'] in common_npz]
        else:
            common_r = all_results[source_name]

        if common_r:
            avg_dh = np.mean([(r['hw_dh_mean'] + r['nw_dh_mean']) / 2 for r in common_r])
            avg_dt = np.mean([(r['hw_dt_mean'] + r['nw_dt_mean']) / 2 for r in common_r])
            hw_bias = np.mean([r['hw_dh_bias'] for r in common_r])
            nw_bias = np.mean([r['nw_dh_bias'] for r in common_r])
            hw_dt_bias = np.mean([r['hw_dt_bias'] for r in common_r])
            nw_dt_bias = np.mean([r['nw_dt_bias'] for r in common_r])
            ranking.append((source_name, avg_dh, avg_dt, hw_bias, nw_bias, hw_dt_bias, nw_dt_bias, len(common_r)))

    for source, avg_dh, avg_dt, hw_bias, nw_bias, hw_dt_bias, nw_dt_bias, n in sorted(ranking, key=lambda x: x[1]):
        print(f"\n  {source}:")
        print(f"    Mittl. |dH|: {avg_dh:.3f}m   Mittl. |dT|: {avg_dt:.0f}min")
        print(f"    HW-Höhen-Bias: {hw_bias:+.3f}m   NW-Höhen-Bias: {nw_bias:+.3f}m")
        print(f"    HW-Zeit-Bias:  {hw_dt_bias:+.0f}min     NW-Zeit-Bias:  {nw_dt_bias:+.0f}min")
        print(f"    Stationen: {n}")


if __name__ == '__main__':
    main()
