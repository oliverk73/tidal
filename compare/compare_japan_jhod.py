#!/usr/bin/env python3
"""
Compare XTide/TICON4 tide predictions for Japan against official JHOD
(Japan Hydrographic and Oceanographic Department) 10-minute predictions.

Downloads JHOD prediction files, generates XTide predictions, and compares
HW/LW timing and height differences.
"""
import os
import re
import subprocess
import zipfile
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path

DATA_DIR = Path("/home/oliver/water_levels/Japan_JHOD")
COMPARE_YEAR = 2026
COMPARE_MONTH = 1  # January

# JHOD station code → XTide station name mapping per source
# XTide uses Nihon-shiki romanization (Kagosima, Isigaki, etc.)
# Classic 2004 has only smaller ports, TICON4 has major stations
STATIONS = [
    {'jhod': '0114', 'name': 'Nemuro',    'z0_cm': 87,
     'xtide': {'TICON4': 'Nemuro, Hokkaido, Japan'}},
    {'jhod': '0124', 'name': 'Wakkanai',  'z0_cm': 18,
     'xtide': {'TICON4': 'Wakkanai, Hokkaido, Japan'}},
    {'jhod': '0145', 'name': 'Hakodate',  'z0_cm': 57,
     'xtide': {'TICON4': 'Hakodate, Hokkaido, Japan'}},
    {'jhod': '1314', 'name': 'Tokyo',     'z0_cm': 120,
     'xtide': {'TICON4': 'Harumi (Tokyo), Tokyo, Japan',
               'Classic 2004': 'Haneda, Tokyo, Japan'}},
    {'jhod': '1403', 'name': 'Yokohama',  'z0_cm': 115,
     'xtide': {'TICON4': 'Yokohama Sin-Yamasita, Kanagawa, Japan'}},
    {'jhod': '2317', 'name': 'Nagoya',    'z0_cm': 140,
     'xtide': {'TICON4': 'Nagoya, Aichi, Japan'}},
    {'jhod': '2706', 'name': 'Osaka',     'z0_cm': 95,
     'xtide': {'TICON4': 'Osaka, Osaka, Japan'}},
    {'jhod': '2807', 'name': 'Kobe',      'z0_cm': 95,
     'xtide': {'TICON4': 'Kobe, Hyogo, Japan'}},
    {'jhod': '4259', 'name': 'Nagasaki',  'z0_cm': 164,
     'xtide': {'TICON4': 'Matugae, Nagasaki, Japan',
               'Classic 2004': 'Nagasaki Megami, Nagasaki, Japan'}},
    {'jhod': '4610', 'name': 'Kagoshima', 'z0_cm': 155,
     'xtide': {'TICON4': 'Kagosima, Kagosima, Japan'}},
    {'jhod': '4705', 'name': 'Naha',      'z0_cm': 118,
     'xtide': {'TICON4': 'Naha, Okinawa, Japan'}},
    {'jhod': '4715', 'name': 'Ishigaki',  'z0_cm': 107,
     'xtide': {'TICON4': 'Isigaki, Okinawa, Japan'}},
]

# Sources to compare against
SOURCES = [
    {
        'name': 'TICON4',
        'tcd': '/usr/share/xtide/harmonics_ticon4_worldwide.tcd',
    },
    {
        'name': 'Classic 2004',
        'tcd': '/usr/share/xtide/harmonics-2004-06-14_mod.tcd',
    },
]


def download_jhod(jhod_code, year):
    """Download and extract JHOD prediction files."""
    zip_file = DATA_DIR / f"prediction{jhod_code}_{year}.zip"
    extract_dir = DATA_DIR / f"prediction{jhod_code}_{year}"

    if not zip_file.exists():
        url = f"https://www1.kaiho.mlit.go.jp/TIDE/gauge/tidedata/prediction/prediction{jhod_code}_{year}.zip"
        os.system(f'wget -q "{url}" -O "{zip_file}"')

    if not extract_dir.exists() and zip_file.exists():
        try:
            with zipfile.ZipFile(zip_file) as zf:
                zf.extractall(extract_dir)
        except zipfile.BadZipFile:
            print(f"  ✗ Ungültige ZIP-Datei für {jhod_code}")
            return False
    return extract_dir.exists()


def load_jhod_predictions(jhod_code, year, month):
    """Load 10-minute JHOD predictions for a specific month."""
    extract_dir = DATA_DIR / f"prediction{jhod_code}_{year}"
    fname = f"prediction{jhod_code}_{year}{month:02d}.txt"
    filepath = extract_dir / fname

    if not filepath.exists():
        return None, None

    times = []
    levels = []

    with open(filepath, 'rb') as f:
        lines = f.readlines()

    for line in lines[1:]:  # Skip header
        line = line.decode('shift-jis', errors='replace').strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) < 147:  # year + month + day + 144 values
            continue

        try:
            y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
            if m != month:
                continue
            values = [int(v) for v in parts[3:147]]  # 144 values

            # JHOD data is in JST (UTC+9), convert to UTC
            base = datetime(y, m, d) - timedelta(hours=9)
            for i, v in enumerate(values):
                t = base + timedelta(minutes=i * 10)
                times.append(t)
                levels.append(v / 100.0)  # cm → m
        except (ValueError, IndexError):
            continue

    if not times:
        return None, None
    return np.array(times), np.array(levels)


def generate_xtide_predictions(station_name, tcd_path, year, month,
                               interval_min=10):
    """Generate XTide predictions using the tide command."""
    # Calculate date range
    start = datetime(year, month, 1)
    if month == 12:
        end = datetime(year + 1, 1, 1)
    else:
        end = datetime(year, month + 1, 1)
    end -= timedelta(minutes=interval_min)

    begin_str = start.strftime('%Y-%m-%d %H:%M')
    end_str = end.strftime('%Y-%m-%d %H:%M')

    # Use raw output with HFILE_PATH to restrict to one TCD
    env = os.environ.copy()
    env['HFILE_PATH'] = tcd_path

    cmd = [
        'tide', '-l', station_name,
        '-b', begin_str,
        '-e', end_str,
        '-s', f'00:{interval_min:02d}',
        '-m', 'r',
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True,
                                timeout=30, env=env)
        if 'Error' in result.stderr or 'Error' in result.stdout:
            return None, None
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None, None

    times = []
    levels = []
    for line in result.stdout.strip().split('\n'):
        if not line.strip():
            continue
        parts = line.strip().split()
        if len(parts) >= 2:
            try:
                timestamp = int(parts[0])
                level = float(parts[1])
                dt = datetime.utcfromtimestamp(timestamp)
                times.append(dt)
                levels.append(level)
            except (ValueError, IndexError):
                continue

    if not times:
        return None, None
    return np.array(times), np.array(levels)


def find_hw_lw(times, levels, min_prominence=0.03):
    """Find high water and low water events from a time series.
    Uses a window of ±3 samples (30 min for 10-min data) to avoid
    noise-induced false extrema, plus prominence filter."""
    w = 3  # window half-size
    events = []
    for i in range(w, len(levels) - w):
        is_max = all(levels[i] >= levels[i+j] for j in range(-w, w+1) if j != 0)
        is_min = all(levels[i] <= levels[i+j] for j in range(-w, w+1) if j != 0)
        if is_max:
            events.append({'time': times[i], 'level': levels[i], 'type': 'HW'})
        elif is_min:
            events.append({'time': times[i], 'level': levels[i], 'type': 'LW'})

    # Filter by prominence: remove events where the range to the nearest
    # opposite event is below min_prominence
    if len(events) < 2:
        return events
    filtered = [events[0]]
    for i in range(1, len(events)):
        if events[i]['type'] != filtered[-1]['type']:
            filtered.append(events[i])
        else:
            # Same type consecutive: keep the more extreme one
            if events[i]['type'] == 'HW':
                if events[i]['level'] > filtered[-1]['level']:
                    filtered[-1] = events[i]
            else:
                if events[i]['level'] < filtered[-1]['level']:
                    filtered[-1] = events[i]

    # Remove pairs with tiny range
    final = []
    for i, ev in enumerate(filtered):
        if i > 0:
            rng = abs(ev['level'] - filtered[i-1]['level'])
            if rng < min_prominence:
                continue
        final.append(ev)

    return final


def match_events(ref_events, pred_events, max_dt_hours=3):
    """Match reference and predicted HW/LW events."""
    matches = []
    used_pred = set()

    for ref in ref_events:
        best_dt = None
        best_pred = None
        best_idx = None

        for j, pred in enumerate(pred_events):
            if j in used_pred or pred['type'] != ref['type']:
                continue
            dt_hours = abs((pred['time'] - ref['time']).total_seconds()) / 3600
            if dt_hours < max_dt_hours:
                if best_dt is None or dt_hours < best_dt:
                    best_dt = dt_hours
                    best_pred = pred
                    best_idx = j

        if best_pred is not None:
            used_pred.add(best_idx)
            dt_min = (best_pred['time'] - ref['time']).total_seconds() / 60
            dh = best_pred['level'] - ref['level']
            matches.append({
                'ref_time': ref['time'],
                'ref_level': ref['level'],
                'pred_time': best_pred['time'],
                'pred_level': best_pred['level'],
                'type': ref['type'],
                'dt_min': dt_min,
                'dh_m': dh,
            })

    return matches


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 90)
    print("Vergleich: XTide Japan vs. JHOD offizielle Vorhersagen (10-Min-Auflösung)")
    print(f"Zeitraum: {COMPARE_YEAR}-{COMPARE_MONTH:02d}")
    print("=" * 90)

    for source in SOURCES:
        tcd_path = source['tcd']
        source_name = source['name']

        if not Path(tcd_path).exists():
            print(f"\n⚠ TCD nicht gefunden: {tcd_path}")
            continue

        print(f"\n{'▓' * 90}")
        print(f"  Quelle: {source_name}")
        print(f"  TCD: {tcd_path}")
        print(f"{'▓' * 90}")

        summary = []

        for station in STATIONS:
            jhod_code = station['jhod']
            display_name = station['name']
            z0_cm = station['z0_cm']

            # Get source-specific XTide name
            xtide_name = station['xtide'].get(source_name)
            if xtide_name is None:
                continue

            print(f"\n{'━' * 90}")
            print(f"  {display_name} (JHOD {jhod_code} → {xtide_name})")
            print(f"{'━' * 90}")

            # 1. Download and load JHOD predictions
            if not download_jhod(jhod_code, COMPARE_YEAR):
                print(f"  ✗ JHOD-Download fehlgeschlagen")
                continue

            ref_times, ref_levels = load_jhod_predictions(
                jhod_code, COMPARE_YEAR, COMPARE_MONTH)
            if ref_times is None:
                print(f"  ✗ Keine JHOD-Daten")
                continue

            print(f"  JHOD: {len(ref_times)} Datenpunkte, "
                  f"Range: {ref_levels.min():.2f}m - {ref_levels.max():.2f}m")

            # 2. Generate XTide predictions
            pred_times, pred_levels = generate_xtide_predictions(
                xtide_name, tcd_path, COMPARE_YEAR, COMPARE_MONTH)

            if pred_times is None or len(pred_times) < 100:
                print(f"  ✗ XTide-Vorhersage fehlgeschlagen für '{xtide_name}'")
                continue

            print(f"  XTide: {len(pred_times)} Datenpunkte, "
                  f"Range: {pred_levels.min():.2f}m - {pred_levels.max():.2f}m")

            # 3. Datum alignment: JHOD uses CDL, XTide uses MLLW
            # Both should be relative to local datum, no adjustment needed
            # for HW/LW height comparison (dH shows systematic offset = datum diff)

            # 4. Find HW/LW events
            ref_events = find_hw_lw(ref_times, ref_levels)
            pred_events = find_hw_lw(pred_times, pred_levels)

            print(f"  JHOD HW/LW: {len(ref_events)} "
                  f"({sum(1 for e in ref_events if e['type']=='HW')} HW, "
                  f"{sum(1 for e in ref_events if e['type']=='LW')} LW)")
            print(f"  XTide HW/LW: {len(pred_events)} "
                  f"({sum(1 for e in pred_events if e['type']=='HW')} HW, "
                  f"{sum(1 for e in pred_events if e['type']=='LW')} LW)")

            if not ref_events or not pred_events:
                print(f"  ✗ Keine HW/LW-Extrema gefunden")
                continue

            # 5. Match and compare
            matches = match_events(ref_events, pred_events)
            hw_matches = [m for m in matches if m['type'] == 'HW']
            lw_matches = [m for m in matches if m['type'] == 'LW']

            print(f"\n  Matches: {len(matches)} "
                  f"({len(hw_matches)} HW, {len(lw_matches)} LW)")

            if not matches:
                print(f"  ✗ Keine Übereinstimmungen")
                continue

            # Statistics
            for label, subset in [('HW', hw_matches), ('LW', lw_matches),
                                   ('Gesamt', matches)]:
                if not subset:
                    continue
                dt_vals = [m['dt_min'] for m in subset]
                dh_vals = [m['dh_m'] for m in subset]

                print(f"\n  {label}:")
                print(f"    Zeit:  Mittel={np.mean(dt_vals):+.1f}min, "
                      f"Std={np.std(dt_vals):.1f}min, "
                      f"|Mittel|={np.mean(np.abs(dt_vals)):.1f}min")
                print(f"    Höhe:  Mittel={np.mean(dh_vals)*100:+.1f}cm, "
                      f"Std={np.std(dh_vals)*100:.1f}cm, "
                      f"|Mittel|={np.mean(np.abs(dh_vals))*100:.1f}cm")

            dt_all = [m['dt_min'] for m in matches]
            dh_all = [m['dh_m'] for m in matches]

            summary.append({
                'name': display_name,
                'n': len(matches),
                'dt_abs': np.mean(np.abs(dt_all)),
                'dt_std': np.std(dt_all),
                'dh_abs': np.mean(np.abs(dh_all)) * 100,
                'dh_std': np.std(dh_all) * 100,
                'dt_mean': np.mean(dt_all),
                'dh_mean': np.mean(dh_all) * 100,
            })

        # Overall summary
        if summary:
            print(f"\n\n{'=' * 90}")
            print(f"ZUSAMMENFASSUNG — {source_name}")
            print(f"{'=' * 90}")
            print(f"{'Station':<15s} {'N':>4s} {'|dT|':>7s} {'dT±':>7s} "
                  f"{'dT_bias':>8s} {'|dH|':>7s} {'dH±':>7s} {'dH_bias':>8s}")
            print(f"{'─'*15} {'─'*4} {'─'*7} {'─'*7} {'─'*8} "
                  f"{'─'*7} {'─'*7} {'─'*8}")

            for s in summary:
                print(f"{s['name']:<15s} {s['n']:>4d} "
                      f"{s['dt_abs']:>6.1f}m {s['dt_std']:>6.1f}m "
                      f"{s['dt_mean']:>+7.1f}m "
                      f"{s['dh_abs']:>5.1f}cm {s['dh_std']:>5.1f}cm "
                      f"{s['dh_mean']:>+6.1f}cm")

            avg_dt = np.mean([s['dt_abs'] for s in summary])
            avg_dh = np.mean([s['dh_abs'] for s in summary])
            print(f"\n{'Durchschnitt':<15s} {'':>4s} "
                  f"{avg_dt:>6.1f}m {'':>7s} {'':>8s} "
                  f"{avg_dh:>5.1f}cm")
            print(f"\n  Bewertung: |dT| < 10min = gut, "
                  f"10-20min = akzeptabel, > 20min = schlecht")
            print(f"             |dH| < 10cm = gut, "
                  f"10-20cm = akzeptabel, > 20cm = schlecht")


if __name__ == '__main__':
    main()
