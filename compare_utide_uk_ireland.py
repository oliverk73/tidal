#!/usr/bin/env python3
"""
Compare UTide UK/Ireland harmonics against NOC/NTSLF tidal predictions.

For UK stations (Lerwick, Newlyn, Stornoway): uses NOC storm surge API
which provides observed and predicted (astronomical) data.

For Irish stations: uses Marine Institute Ireland API.
"""

import numpy as np
import requests
import pickle
from datetime import datetime, timedelta
from pathlib import Path
import utide

CHECKPOINT_DIR = Path("/home/oliver/harmonics_working/checkpoints_uk_ie")

STATIONS = {
    293: {'name': 'Lerwick', 'lat': 60.154, 'noc_id': 'lerwick'},
    294: {'name': 'Newlyn', 'lat': 50.103, 'noc_id': 'newlyn'},
    295: {'name': 'Stornoway', 'lat': 58.207, 'noc_id': 'stornoway'},
    834: {'name': 'Malin Head', 'lat': 55.367, 'mi_id': 'MalinHead'},
    835: {'name': 'Castletownbere', 'lat': 51.650, 'mi_id': 'Castletownbere'},
}

# NOC Storm Surge API for UK (returns predicted astronomical tide)
NOC_BASE = "https://www.ntslf.org/tides/predictions"


def fetch_noc_predictions(noc_id, year, month):
    """Fetch tidal predictions from NOC/NTSLF for a UK station."""
    # Try NTSLF tide prediction download
    url = f"https://www.ntslf.org/tides/hilo/{noc_id}"
    params = {
        'year': year,
        'format': 'csv',
    }
    try:
        resp = requests.get(url, params=params, timeout=60)
        if resp.status_code == 200 and resp.text.strip():
            return parse_ntslf_hilo(resp.text, year, month)
    except Exception:
        pass

    # Fallback: try the gauge data API
    start = f"{year}-{month:02d}-01T00:00:00Z"
    if month == 12:
        end = f"{year+1}-01-01T00:00:00Z"
    else:
        end = f"{year}-{month+1:02d}-01T00:00:00Z"

    url = f"https://www.ntslf.org/api/v1/stations/{noc_id}/data"
    params = {'start': start, 'end': end, 'type': 'predicted'}
    try:
        resp = requests.get(url, params=params, timeout=60)
        if resp.status_code == 200:
            data = resp.json()
            if data:
                times = []
                levels = []
                for entry in data:
                    dt = datetime.fromisoformat(entry['time'].replace('Z', '+00:00'))
                    dt_utc = dt.replace(tzinfo=None)
                    times.append(dt_utc)
                    levels.append(float(entry['value']))
                return np.array(times), np.array(levels)
    except Exception:
        pass

    return None, None


def parse_ntslf_hilo(text, year, month):
    """Parse NTSLF HW/LW CSV format."""
    import csv
    from io import StringIO
    events = []
    reader = csv.reader(StringIO(text))
    for row in reader:
        if len(row) >= 4:
            try:
                dt = datetime.strptime(row[0].strip(), '%Y-%m-%d %H:%M')
                if dt.month != month:
                    continue
                level = float(row[1])
                hw_lw = row[2].strip().upper()
                events.append({
                    'time': dt,
                    'level': level,
                    'type': 'HW' if 'H' in hw_lw else 'LW',
                })
            except (ValueError, IndexError):
                continue
    return events


def predict_utide(coef, start, end, interval_min=15):
    """Generate UTide predictions."""
    dt_start = datetime.strptime(start, '%Y-%m-%d')
    dt_end = datetime.strptime(end, '%Y-%m-%d') + timedelta(days=1)
    n_steps = int((dt_end - dt_start).total_seconds() / (interval_min * 60))
    times = np.array([dt_start + timedelta(minutes=i * interval_min)
                      for i in range(n_steps)])
    recon = utide.reconstruct(times, coef, verbose=False)
    return times, recon['h']


def find_hw_lw(times, levels):
    """Find HW/LW from time series."""
    events = []
    for i in range(1, len(levels) - 1):
        if levels[i] > levels[i-1] and levels[i] > levels[i+1]:
            events.append({'time': times[i], 'level': levels[i], 'type': 'HW'})
        elif levels[i] < levels[i-1] and levels[i] < levels[i+1]:
            events.append({'time': times[i], 'level': levels[i], 'type': 'LW'})
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
                'type': best_pred['type'],
                'dt_min': dt_min,
                'dh_m': dh,
            })
    return matches


def main():
    print("=" * 80)
    print("Vergleich: UTide UK/Ireland vs. Offizielle Vorhersagen (NOC/MI)")
    print("Zeitraum: 2024-01")
    print("=" * 80)

    for sid, info in STATIONS.items():
        print(f"\n{'━' * 80}")
        print(f"  {info['name']} (UHSLC {sid})")
        print(f"{'━' * 80}")

        pkl = CHECKPOINT_DIR / f"{sid}.pkl"
        if not pkl.exists():
            print(f"  ✗ Kein Checkpoint")
            continue

        with open(pkl, 'rb') as f:
            result = pickle.load(f)

        coef = result['coef']
        print(f"  UTide R²={result['r_squared']:.4f}")

        # Try to fetch official predictions
        if 'noc_id' in info:
            print(f"  Lade NOC-Vorhersagen...", end='', flush=True)
            ref_result = fetch_noc_predictions(info['noc_id'], 2024, 1)
            if isinstance(ref_result, list):
                # Got HW/LW events directly
                ref_events = ref_result
                print(f" {len(ref_events)} HW/LW")
            elif ref_result[0] is not None:
                ref_times, ref_levels = ref_result
                ref_events = find_hw_lw(ref_times, ref_levels)
                print(f" {len(ref_events)} HW/LW aus Zeitreihe")
            else:
                print(f" keine Daten verfügbar")
                # Fall back: use BODC data if available
                import re
                bodc_codes = {'Lerwick': 'LER', 'Newlyn': 'NEW', 'Stornoway': 'STO'}
                bodc_code = bodc_codes.get(info['name'])
                if bodc_code:
                    bodc_pkl = Path(f"/home/oliver/harmonics_working/checkpoints_uk_bodc/{bodc_code}.pkl")
                    if bodc_pkl.exists():
                        print(f"  → BODC-Vergleich bereits in compare_utide_uk_bodc.py")
                continue
        else:
            print(f"  Keine API für irische Stationen verfügbar, überspringe")
            continue

        if not ref_events:
            print(f"  ✗ Keine HW/LW gefunden")
            continue

        # Generate UTide predictions
        pred_times, pred_levels = predict_utide(coef, '2024-01-01', '2024-01-31',
                                                 interval_min=15)
        pred_events = find_hw_lw(pred_times, pred_levels)
        print(f"  UTide HW/LW: {len(pred_events)}")

        # Match
        matches = match_events(ref_events, pred_events)
        if not matches:
            print(f"  ✗ Keine Übereinstimmungen")
            continue

        hw = [m for m in matches if m['type'] == 'HW']
        lw = [m for m in matches if m['type'] == 'LW']
        print(f"\n  Matches: {len(matches)} ({len(hw)} HW, {len(lw)} LW)")

        for label, subset in [('HW', hw), ('LW', lw), ('Gesamt', matches)]:
            if not subset:
                continue
            dt_vals = [m['dt_min'] for m in subset]
            dh_vals = [m['dh_m'] for m in subset]
            print(f"\n  {label}:")
            print(f"    Zeit-Diff:  Mittel={np.mean(dt_vals):+.1f}min, "
                  f"|Mittel|={np.mean(np.abs(dt_vals)):.1f}min")
            print(f"    Höhe-Diff:  Mittel={np.mean(dh_vals):+.3f}m, "
                  f"|Mittel|={np.mean(np.abs(dh_vals)):.3f}m")


if __name__ == '__main__':
    main()
