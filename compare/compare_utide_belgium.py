#!/usr/bin/env python3
"""
Compare UTide harmonics (harmonics_utide_belgium.txt) against official
astronomical tide predictions from waterinfo.be (KIWIS API).

Downloads HW/LW predictions for coastal stations, generates UTide predictions
from our harmonics, and compares timing and height differences.
"""

import numpy as np
import requests
import time
from datetime import datetime, timedelta
from pathlib import Path
import utide

# Stations with known Astro.HWLW ts_ids from waterinfo.be
STATIONS = {
    'Oostende': {
        'ts_id_hwlw': '0484307010',
        'ts_id_astro10': '0484305010',
        'code': '04OST-1069',
        'lat': 51.23,
        'lon': 2.93,
    },
    'Nieuwpoort': {
        'ts_id_hwlw': '0488663010',
        'ts_id_astro10': '0488661010',
        'code': '04NPT-1069',
        'lat': 51.15,
        'lon': 2.72,
    },
    'Zeebrugge': {
        'ts_id_hwlw': '0488659010',
        'ts_id_astro10': '0488657010',
        'code': '04ZLD-1069',
        'lat': 51.35,
        'lon': 3.18,
    },
    'Antwerpen': {
        'ts_id_hwlw': '0484033010',
        'ts_id_astro10': '04112650010',
        'code': '04zes21a-1066',
        'lat': 51.23,
        'lon': 4.40,
    },
}

KIWIS_BASE = 'https://waterinfo.vlaanderen.be/tsmpub/KiWIS/KiWIS'
HARMONICS_FILE = Path("/home/oliver/harmonics/utide/harmonics_utide_belgium.txt")
CHECKPOINT_DIR = Path("/home/oliver/harmonics/utide/checkpoints_belgium")

# Comparison period
COMPARE_START = '2026-01-01'
COMPARE_END = '2026-01-31'


def fetch_hwlw(ts_id, start, end):
    """Fetch HW/LW predictions from waterinfo.be."""
    params = {
        'service': 'kisters',
        'type': 'queryServices',
        'request': 'getTimeseriesValues',
        'datasource': 0,
        'format': 'json',
        'ts_id': ts_id,
        'from': start,
        'to': end,
        'metadata': 'false',
    }
    resp = requests.get(KIWIS_BASE, params=params, timeout=60)
    resp.raise_for_status()
    data = resp.json()

    events = []
    if data and len(data) > 0:
        from dateutil import parser as dateparser
        from datetime import timezone
        for row in data[0].get('data', []):
            if row[1] is not None:
                ts_str = row[0]
                dt = dateparser.parse(ts_str)
                # Convert to UTC (waterinfo returns CET/CEST with tz offset)
                dt_utc = dt.astimezone(timezone.utc).replace(tzinfo=None)
                events.append({
                    'time_str': ts_str,
                    'time_utc': dt_utc,
                    'level_m': float(row[1]),
                })
    return events


def fetch_astro_timeseries(ts_id, start, end):
    """Fetch 10-min astronomical predictions from waterinfo.be."""
    params = {
        'service': 'kisters',
        'type': 'queryServices',
        'request': 'getTimeseriesValues',
        'datasource': 0,
        'format': 'json',
        'ts_id': ts_id,
        'from': start,
        'to': end,
        'metadata': 'false',
    }
    resp = requests.get(KIWIS_BASE, params=params, timeout=60)
    resp.raise_for_status()
    data = resp.json()

    times = []
    levels = []
    if data and len(data) > 0:
        from dateutil import parser as dateparser
        from datetime import timezone
        for row in data[0].get('data', []):
            if row[1] is not None:
                dt = dateparser.parse(row[0])
                dt_utc = dt.astimezone(timezone.utc).replace(tzinfo=None)
                times.append(dt_utc)
                levels.append(float(row[1]))
    return np.array(times), np.array(levels)


def load_checkpoint(station_code):
    """Load UTide checkpoint for a station."""
    import pickle
    pkl = CHECKPOINT_DIR / f"{station_code}.pkl"
    if not pkl.exists():
        return None
    with open(pkl, 'rb') as f:
        return pickle.load(f)


def predict_utide(coef, start, end, interval_min=10):
    """Generate UTide predictions for a time range."""
    dt_start = datetime.strptime(start, '%Y-%m-%d')
    dt_end = datetime.strptime(end, '%Y-%m-%d') + timedelta(days=1)

    n_steps = int((dt_end - dt_start).total_seconds() / (interval_min * 60))
    times = np.array([dt_start + timedelta(minutes=i * interval_min) for i in range(n_steps)])

    recon = utide.reconstruct(times, coef, verbose=False)
    return times, recon['h']


def find_hw_lw(times, levels):
    """Find high water and low water events from a time series."""
    events = []
    for i in range(1, len(levels) - 1):
        if levels[i] > levels[i-1] and levels[i] > levels[i+1]:
            events.append({'time': times[i], 'level': levels[i], 'type': 'HW'})
        elif levels[i] < levels[i-1] and levels[i] < levels[i+1]:
            events.append({'time': times[i], 'level': levels[i], 'type': 'LW'})
    return events


def classify_hwlw(events):
    """Classify HWLW events as HW or LW based on alternating pattern."""
    if len(events) < 2:
        return events
    # Determine if first event is HW or LW
    for e in events:
        if 'type' not in e:
            # Guess from level
            avg = np.mean([ev['level_m'] for ev in events])
            e['type'] = 'HW' if e['level_m'] > avg else 'LW'
    return events


def match_events(ref_events, pred_events, max_dt_hours=3):
    """Match reference and predicted HW/LW events."""
    matches = []
    used_pred = set()

    for ref in ref_events:
        best_dt = None
        best_pred = None
        best_idx = None

        for j, pred in enumerate(pred_events):
            if j in used_pred:
                continue
            dt_hours = abs((pred['time'] - ref['time_utc']).total_seconds()) / 3600
            if dt_hours < max_dt_hours:
                if best_dt is None or dt_hours < best_dt:
                    best_dt = dt_hours
                    best_pred = pred
                    best_idx = j

        if best_pred is not None:
            used_pred.add(best_idx)
            dt_min = (best_pred['time'] - ref['time_utc']).total_seconds() / 60
            dh = best_pred['level'] - ref['level_m']
            matches.append({
                'ref_time': ref['time_utc'],
                'ref_level': ref['level_m'],
                'pred_time': best_pred['time'],
                'pred_level': best_pred['level'],
                'type': best_pred['type'],
                'dt_min': dt_min,
                'dh_m': dh,
            })

    return matches


def main():
    print("=" * 80)
    print("Vergleich: UTide Belgium vs. Offizielle Vorhersagen (waterinfo.be)")
    print(f"Zeitraum: {COMPARE_START} bis {COMPARE_END}")
    print("=" * 80)

    for name, info in STATIONS.items():
        print(f"\n{'━' * 80}")
        print(f"  {name} ({info['code']})")
        print(f"{'━' * 80}")

        # 1. Load UTide checkpoint
        result = load_checkpoint(info['code'])
        if result is None:
            print(f"  ✗ Kein UTide-Checkpoint für {info['code']}")
            continue

        coef = result['coef']
        print(f"  UTide: R²={result['r_squared']:.4f}, "
              f"M2={result.get('m2_amp', 0):.4f}m")

        # 2. Generate UTide predictions
        print(f"  Generiere UTide-Vorhersage...", end='', flush=True)
        pred_times, pred_levels = predict_utide(coef, COMPARE_START, COMPARE_END)
        pred_events = find_hw_lw(pred_times, pred_levels)
        print(f" {len(pred_events)} HW/LW-Ereignisse")

        # 3. Fetch official HWLW predictions
        print(f"  Lade offizielle Vorhersagen (Astro.HWLW)...", end='', flush=True)
        try:
            ref_events = fetch_hwlw(info['ts_id_hwlw'], COMPARE_START, COMPARE_END)
            print(f" {len(ref_events)} Ereignisse")
        except Exception as e:
            print(f" FEHLER: {e}")
            # Try 10-min astro series instead
            print(f"  Versuche Astro.10...", end='', flush=True)
            try:
                ref_times, ref_levels = fetch_astro_timeseries(
                    info['ts_id_astro10'], COMPARE_START, COMPARE_END)
                if len(ref_times) > 0:
                    ref_hw_lw = find_hw_lw(ref_times, ref_levels)
                    ref_events = [{'time_utc': e['time'], 'level_m': e['level'],
                                   'type': e['type']} for e in ref_hw_lw]
                    print(f" {len(ref_events)} HW/LW aus Astro.10")
                else:
                    print(f" keine Daten")
                    continue
            except Exception as e2:
                print(f" FEHLER: {e2}")
                continue

        if not ref_events:
            print(f"  ✗ Keine offiziellen Vorhersagen verfügbar")
            continue

        # Classify official events
        avg_level = np.mean([e['level_m'] for e in ref_events])
        for e in ref_events:
            if 'type' not in e:
                e['type'] = 'HW' if e['level_m'] > avg_level else 'LW'

        # 4. Match and compare
        matches = match_events(ref_events, pred_events)

        if not matches:
            print(f"  ✗ Keine Übereinstimmungen gefunden")
            continue

        hw_matches = [m for m in matches if m['type'] == 'HW']
        lw_matches = [m for m in matches if m['type'] == 'LW']

        print(f"\n  Ergebnis: {len(matches)} Matches "
              f"({len(hw_matches)} HW, {len(lw_matches)} LW)")

        # Statistics
        for label, subset in [('HW', hw_matches), ('LW', lw_matches), ('Gesamt', matches)]:
            if not subset:
                continue
            dt_vals = [m['dt_min'] for m in subset]
            dh_vals = [m['dh_m'] for m in subset]

            print(f"\n  {label}:")
            print(f"    Zeit-Diff:  Mittel={np.mean(dt_vals):+.1f}min, "
                  f"Std={np.std(dt_vals):.1f}min, "
                  f"|Mittel|={np.mean(np.abs(dt_vals)):.1f}min")
            print(f"    Höhe-Diff:  Mittel={np.mean(dh_vals):+.3f}m, "
                  f"Std={np.std(dh_vals):.3f}m, "
                  f"|Mittel|={np.mean(np.abs(dh_vals)):.3f}m")

        # Show first few matches
        print(f"\n  Erste 10 Vergleiche:")
        print(f"  {'Typ':>3s}  {'Offiziell':>16s}  {'UTide':>16s}  {'dT(min)':>8s}  {'dH(m)':>8s}")
        print(f"  {'─'*3}  {'─'*16}  {'─'*16}  {'─'*8}  {'─'*8}")
        for m in matches[:10]:
            ref_str = m['ref_time'].strftime('%d.%m. %H:%M')
            pred_str = m['pred_time'].strftime('%d.%m. %H:%M')
            print(f"  {m['type']:>3s}  {ref_str:>16s}  {pred_str:>16s}  "
                  f"{m['dt_min']:>+7.0f}  {m['dh_m']:>+7.3f}")

        time.sleep(2)  # Rate limit


if __name__ == '__main__':
    main()
