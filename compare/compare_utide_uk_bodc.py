#!/usr/bin/env python3
"""
Compare UTide harmonics (harmonics_utide_uk_bodc.txt) against official
tide predictions extracted from BODC residual data.

Official predicted tide = observed level - residual.
Compares HW/LW timing and height differences for January 2024.
"""

import re
import numpy as np
import pickle
import time
from datetime import datetime, timedelta
from pathlib import Path
import utide

DATA_DIR = Path("/home/oliver/water_levels/UK/bodc_sea_level_2007-2026_values_and_residuals_acd")
CHECKPOINT_DIR = Path("/home/oliver/harmonics/utide/checkpoints_uk_bodc")

# Compare period: use 2024 data (most recent full year)
COMPARE_YEAR = 2024
COMPARE_MONTH = 1  # January


def load_bodc_predictions(code, year, month):
    """Extract official predicted tide from BODC data (observed - residual)."""
    fname = f"{year}{code}.txt"
    filepath = DATA_DIR / fname
    if not filepath.exists():
        return None, None

    times = []
    predictions = []

    with open(filepath) as f:
        for line in f:
            # Match data lines: cycle) date time value[M/N/T] residual[M/N/T]
            m = re.match(
                r'\s*\d+\)\s+(\d{4}/\d{2}/\d{2}\s+\d{2}:\d{2}:\d{2})\s+'
                r'([\d.]+)[MNTS ]?\s+([\d.-]+)', line)
            if m:
                try:
                    dt = datetime.strptime(m.group(1), '%Y/%m/%d %H:%M:%S')
                    if dt.month != month:
                        continue
                    obs = float(m.group(2))
                    res = float(m.group(3))
                    predicted = obs - res
                    times.append(dt)
                    predictions.append(predicted)
                except (ValueError, IndexError):
                    pass

    if not times:
        return None, None
    return np.array(times), np.array(predictions)


def predict_utide(coef, start, end, interval_min=15):
    """Generate UTide predictions for a time range."""
    dt_start = datetime.strptime(start, '%Y-%m-%d')
    dt_end = datetime.strptime(end, '%Y-%m-%d') + timedelta(days=1)

    n_steps = int((dt_end - dt_start).total_seconds() / (interval_min * 60))
    times = np.array([dt_start + timedelta(minutes=i * interval_min)
                      for i in range(n_steps)])

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
    print("Vergleich: UTide UK BODC vs. Offizielle Vorhersagen (aus BODC Residuals)")
    print(f"Zeitraum: {COMPARE_YEAR}-{COMPARE_MONTH:02d}")
    print("=" * 80)

    # Discover stations from checkpoints
    all_results = []
    for pkl_file in sorted(CHECKPOINT_DIR.glob("*.pkl")):
        code = pkl_file.stem
        with open(pkl_file, 'rb') as f:
            result = pickle.load(f)
        all_results.append((code, result))

    print(f"\n{len(all_results)} Stationen mit UTide-Checkpoints\n")

    summary = []

    for code, result in all_results:
        station = result['station']
        name = station['name']
        coef = result['coef']

        print(f"\n{'━' * 80}")
        print(f"  {name} ({code})")
        print(f"{'━' * 80}")

        # 1. Load official predictions from BODC residuals
        start_str = f"{COMPARE_YEAR}-{COMPARE_MONTH:02d}-01"
        end_day = 31 if COMPARE_MONTH in [1, 3, 5, 7, 8, 10, 12] else 30
        if COMPARE_MONTH == 2:
            end_day = 29 if COMPARE_YEAR % 4 == 0 else 28
        end_str = f"{COMPARE_YEAR}-{COMPARE_MONTH:02d}-{end_day}"

        ref_times, ref_levels = load_bodc_predictions(code, COMPARE_YEAR, COMPARE_MONTH)
        if ref_times is None:
            print(f"  ✗ Keine BODC-Daten für {COMPARE_YEAR}")
            continue

        print(f"  BODC: {len(ref_times)} Datenpunkte")

        # Find HW/LW in official predictions
        ref_events = find_hw_lw(ref_times, ref_levels)
        print(f"  Offizielle HW/LW: {len(ref_events)}")

        if not ref_events:
            print(f"  ✗ Keine HW/LW in offiziellen Daten gefunden")
            continue

        # 2. Generate UTide predictions
        pred_times, pred_levels = predict_utide(coef, start_str, end_str,
                                                 interval_min=15)
        pred_events = find_hw_lw(pred_times, pred_levels)
        print(f"  UTide HW/LW: {len(pred_events)}")

        # 3. Match and compare
        matches = match_events(ref_events, pred_events)

        if not matches:
            print(f"  ✗ Keine Übereinstimmungen")
            continue

        hw_matches = [m for m in matches if m['type'] == 'HW']
        lw_matches = [m for m in matches if m['type'] == 'LW']

        print(f"\n  Matches: {len(matches)} ({len(hw_matches)} HW, {len(lw_matches)} LW)")

        # Statistics
        for label, subset in [('HW', hw_matches), ('LW', lw_matches),
                               ('Gesamt', matches)]:
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

        # Summary entry
        dt_all = [m['dt_min'] for m in matches]
        dh_all = [m['dh_m'] for m in matches]
        summary.append({
            'name': name,
            'code': code,
            'n_matches': len(matches),
            'dt_mean': np.mean(np.abs(dt_all)),
            'dh_mean': np.mean(np.abs(dh_all)),
            'r_squared': result['r_squared'],
        })

        # First few matches
        print(f"\n  Erste 5 Vergleiche:")
        print(f"  {'Typ':>3s}  {'Offiziell':>16s}  {'UTide':>16s}  "
              f"{'dT(min)':>8s}  {'dH(m)':>8s}")
        print(f"  {'─'*3}  {'─'*16}  {'─'*16}  {'─'*8}  {'─'*8}")
        for m in matches[:5]:
            ref_str = m['ref_time'].strftime('%d.%m. %H:%M')
            pred_str = m['pred_time'].strftime('%d.%m. %H:%M')
            print(f"  {m['type']:>3s}  {ref_str:>16s}  {pred_str:>16s}  "
                  f"{m['dt_min']:>+7.0f}  {m['dh_m']:>+7.3f}")

    # Overall summary
    if summary:
        print(f"\n\n{'=' * 80}")
        print("ZUSAMMENFASSUNG")
        print(f"{'=' * 80}")
        print(f"{'Station':<30s} {'R²':>6s}  {'|dT|':>6s}  {'|dH|':>6s}  {'N':>4s}")
        print(f"{'─'*30} {'─'*6}  {'─'*6}  {'─'*6}  {'─'*4}")
        for s in sorted(summary, key=lambda x: x['dt_mean']):
            print(f"{s['name']:<30s} {s['r_squared']:>5.4f}  "
                  f"{s['dt_mean']:>5.1f}m  {s['dh_mean']:>5.3f}m  {s['n_matches']:>4d}")

        avg_dt = np.mean([s['dt_mean'] for s in summary])
        avg_dh = np.mean([s['dh_mean'] for s in summary])
        print(f"\nDurchschnitt: |dT|={avg_dt:.1f}min, |dH|={avg_dh:.3f}m")


if __name__ == '__main__':
    main()
