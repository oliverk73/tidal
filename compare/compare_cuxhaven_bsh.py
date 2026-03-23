#!/usr/bin/env python3
"""
Compare UTide-generated harmonics for Cuxhaven-Steubenhöft with BSH predictions.

Parses BSH VB2 format from DE__506P2026.txt (HW/NW times & heights in PNP/MEZ),
reconstructs tide from UTide coefficients for the same period,
finds predicted HW/NW, and compares timing and height differences.
"""
import numpy as np
from datetime import datetime, timedelta, timezone
import re
import zipfile
import json
import ijson
import utide
from pathlib import Path
from scipy.signal import argrelextrema


# ── Parse BSH predictions ──────────────────────────────────────────────

def parse_bsh_predictions(bsh_file):
    """Parse BSH VB2 lines into list of (datetime_utc, height_pnp, type)."""
    predictions = []
    with open(bsh_file, 'r', encoding='latin-1') as f:
        for line in f:
            if not line.startswith('VB2#'):
                continue
            parts = line.strip().split('#')
            # parts: ['VB2', 'DE__506P', ' ', 'H'/'N', 'Do', ' 1. 1.2026', ' 4:50', ' 6.67 ', ...]
            hw_nw = parts[3].strip()  # 'H' or 'N'
            date_str = parts[5].strip()   # '1. 1.2026'
            time_str = parts[6].strip()   # '4:50'
            height_str = parts[7].strip() # '6.67'

            # Parse date: "1. 1.2026" or "30.12.2026"
            date_str = re.sub(r'\s+', '', date_str)  # remove spaces
            day, month, year = date_str.split('.')
            day, month, year = int(day), int(month), int(year)

            hour, minute = map(int, time_str.split(':'))
            height = float(height_str)

            # BSH times are MEZ (CET = UTC+1)
            dt_mez = datetime(year, month, day, hour, minute)
            dt_utc = dt_mez - timedelta(hours=1)

            predictions.append({
                'datetime_utc': dt_utc,
                'datetime_mez': dt_mez,
                'height_pnp': height,
                'type': 'HW' if hw_nw == 'H' else 'NW'
            })

    return predictions


# ── Reconstruct tide from UTide coefficients ───────────────────────────

def reconstruct_tide_2026(zip_path):
    """
    Re-run UTide solve on the same data used for harmonics generation,
    then reconstruct a high-resolution time series for 2026.
    """
    from datetime import datetime, timedelta

    cutoff = datetime(2016, 2, 15)
    datetimes = []
    levels = []
    count = 0

    print("Parsing water level data (10 years, hourly)...")
    with zipfile.ZipFile(zip_path, 'r') as zf:
        for name in zf.namelist():
            if name.endswith('.json') and ':' not in name:
                with zf.open(name) as f:
                    for entry in ijson.items(f, 'item'):
                        count += 1
                        if count % 60 != 0:
                            continue
                        val = entry.get('value')
                        if val is None:
                            continue
                        ts = entry['timestamp']
                        ts_base = ts[:19]
                        if int(ts_base[:4]) < 2015:
                            continue
                        dt_local = datetime.strptime(ts_base, "%Y-%m-%dT%H:%M:%S")
                        if '+' in ts[19:]:
                            oh = int(ts[20:22])
                            dt_utc = dt_local - timedelta(hours=oh)
                        else:
                            dt_utc = dt_local - timedelta(hours=1)
                        if dt_utc < cutoff:
                            continue
                        datetimes.append(dt_utc)
                        levels.append(float(val) / 100.0)
                break

    print(f"  {len(datetimes)} observations parsed")

    dt_arr = np.array(datetimes)
    lv_arr = np.array(levels)

    print("Running UTide solve...")
    coef = utide.solve(
        dt_arr, lv_arr, lat=53.8678,
        nodal=True, trend=False, method='ols',
        conf_int='none', verbose=False, constit='auto',
    )
    print(f"  {len(coef['name'])} constituents")

    # Reconstruct at 6-minute resolution for all of 2026
    print("Reconstructing 2026 at 6-minute resolution...")
    start_2026 = datetime(2025, 12, 31, 23, 0)  # start a bit before
    end_2026 = datetime(2027, 1, 1, 1, 0)        # end a bit after
    n_points = int((end_2026 - start_2026).total_seconds() / 360) + 1  # 6-min intervals
    t_pred = np.array([start_2026 + timedelta(minutes=6*i) for i in range(n_points)])

    reconstruction = utide.reconstruct(t_pred, coef, verbose=False)
    h_pred = reconstruction['h']

    return t_pred, h_pred, coef


# ── Find HW/NW from reconstructed time series ─────────────────────────

def find_hw_nw(t_pred, h_pred, min_prominence=0.3):
    """Find high water and low water from time series using local extrema."""
    # Use wider window for semi-diurnal tides (~6h period, at 6-min resolution = ~60 points)
    order = 30  # ~3 hours on each side

    hw_indices = argrelextrema(h_pred, np.greater, order=order)[0]
    nw_indices = argrelextrema(h_pred, np.less, order=order)[0]

    results = []
    for idx in hw_indices:
        results.append({
            'datetime_utc': t_pred[idx],
            'height': h_pred[idx],
            'type': 'HW'
        })
    for idx in nw_indices:
        results.append({
            'datetime_utc': t_pred[idx],
            'height': h_pred[idx],
            'type': 'NW'
        })

    results.sort(key=lambda x: x['datetime_utc'])
    return results


# ── Match and compare ──────────────────────────────────────────────────

def match_predictions(bsh_preds, utide_preds, max_dt_hours=3):
    """Match BSH predictions with nearest UTide predictions of same type."""
    matches = []
    used_utide = set()

    for bsh in bsh_preds:
        best_match = None
        best_dt = timedelta(hours=max_dt_hours)

        for j, ut in enumerate(utide_preds):
            if j in used_utide:
                continue
            if ut['type'] != bsh['type']:
                continue
            dt = abs(ut['datetime_utc'] - bsh['datetime_utc'])
            if dt < best_dt:
                best_dt = dt
                best_match = (j, ut)

        if best_match is not None:
            j, ut = best_match
            used_utide.add(j)
            time_diff_min = (ut['datetime_utc'] - bsh['datetime_utc']).total_seconds() / 60
            height_diff = ut['height'] - bsh['height_pnp']
            matches.append({
                'bsh': bsh,
                'utide': ut,
                'time_diff_min': time_diff_min,
                'height_diff_m': height_diff,
            })

    return matches


# ── Main ───────────────────────────────────────────────────────────────

def main():
    bsh_file = Path("/home/oliver/harmonics/help/BSH/DE__506P2026.txt")
    zip_path = Path("/home/oliver/water_levels/Germany/pegelonline-cuxhavensteubenhft-W-20000101-20260123.zip")

    print("=" * 75)
    print("Comparison: UTide Harmonics vs BSH Predictions for Cuxhaven-Steubenhöft")
    print("=" * 75)

    # 1. Parse BSH predictions
    print(f"\n1. Parsing BSH predictions from {bsh_file.name}...")
    bsh_preds = parse_bsh_predictions(bsh_file)
    hw_count = sum(1 for p in bsh_preds if p['type'] == 'HW')
    nw_count = sum(1 for p in bsh_preds if p['type'] == 'NW')
    print(f"   {len(bsh_preds)} predictions: {hw_count} HW, {nw_count} NW")
    print(f"   Range: {bsh_preds[0]['datetime_mez'].strftime('%d.%m.%Y')} - {bsh_preds[-1]['datetime_mez'].strftime('%d.%m.%Y')}")

    # 2. Reconstruct tide from UTide
    print(f"\n2. Reconstructing tide from UTide harmonics...")
    t_pred, h_pred, coef = reconstruct_tide_2026(zip_path)
    print(f"   Reconstruction: {len(t_pred)} points, {t_pred[0]} to {t_pred[-1]}")

    # 3. Find HW/NW
    print(f"\n3. Finding HW/NW from reconstructed series...")
    utide_preds = find_hw_nw(t_pred, h_pred)
    ut_hw = sum(1 for p in utide_preds if p['type'] == 'HW')
    ut_nw = sum(1 for p in utide_preds if p['type'] == 'NW')
    print(f"   Found: {ut_hw} HW, {ut_nw} NW")

    # 4. Match and compare
    print(f"\n4. Matching predictions...")
    matches = match_predictions(bsh_preds, utide_preds)
    print(f"   Matched: {len(matches)} of {len(bsh_preds)} BSH predictions")

    # 5. Statistics
    hw_matches = [m for m in matches if m['bsh']['type'] == 'HW']
    nw_matches = [m for m in matches if m['bsh']['type'] == 'NW']

    def stats(match_list, label):
        if not match_list:
            return
        time_diffs = [m['time_diff_min'] for m in match_list]
        height_diffs = [m['height_diff_m'] for m in match_list]
        print(f"\n   {label} ({len(match_list)} events):")
        print(f"   {'':30s} {'Time (min)':>15s}  {'Height (m)':>15s}")
        print(f"   {'Mean diff':30s} {np.mean(time_diffs):>+15.1f}  {np.mean(height_diffs):>+15.3f}")
        print(f"   {'Median diff':30s} {np.median(time_diffs):>+15.1f}  {np.median(height_diffs):>+15.3f}")
        print(f"   {'Std dev':30s} {np.std(time_diffs):>15.1f}  {np.std(height_diffs):>15.3f}")
        print(f"   {'Mean absolute diff':30s} {np.mean(np.abs(time_diffs)):>15.1f}  {np.mean(np.abs(height_diffs)):>15.3f}")
        print(f"   {'Max absolute diff':30s} {np.max(np.abs(time_diffs)):>15.1f}  {np.max(np.abs(height_diffs)):>15.3f}")
        print(f"   {'Min absolute diff':30s} {np.min(np.abs(time_diffs)):>15.1f}  {np.min(np.abs(height_diffs)):>15.3f}")
        # Percentage within thresholds
        within_10min = sum(1 for t in time_diffs if abs(t) <= 10) / len(time_diffs) * 100
        within_20min = sum(1 for t in time_diffs if abs(t) <= 20) / len(time_diffs) * 100
        within_30min = sum(1 for t in time_diffs if abs(t) <= 30) / len(time_diffs) * 100
        within_10cm = sum(1 for h in height_diffs if abs(h) <= 0.10) / len(height_diffs) * 100
        within_20cm = sum(1 for h in height_diffs if abs(h) <= 0.20) / len(height_diffs) * 100
        within_30cm = sum(1 for h in height_diffs if abs(h) <= 0.30) / len(height_diffs) * 100
        print(f"   {'Within ±10 min / ±10 cm':30s} {within_10min:>14.1f}%  {within_10cm:>14.1f}%")
        print(f"   {'Within ±20 min / ±20 cm':30s} {within_20min:>14.1f}%  {within_20cm:>14.1f}%")
        print(f"   {'Within ±30 min / ±30 cm':30s} {within_30min:>14.1f}%  {within_30cm:>14.1f}%")

    print("\n" + "=" * 75)
    print("RESULTS: UTide vs BSH (positive = UTide later/higher than BSH)")
    print("=" * 75)
    stats(matches, "ALL (HW + NW)")
    stats(hw_matches, "HIGH WATER (HW)")
    stats(nw_matches, "LOW WATER (NW)")

    # 6. Sample comparison (first 20 events)
    print(f"\n{'=' * 75}")
    print("Sample: First 20 matched events (January 2026)")
    print(f"{'=' * 75}")
    print(f"  {'Type':4s} {'BSH Time (MEZ)':18s} {'BSH Ht':>7s} {'UTide Time (MEZ)':18s} {'UTide Ht':>8s} {'dT(min)':>8s} {'dH(m)':>7s}")
    print(f"  {'-'*4} {'-'*18} {'-'*7} {'-'*18} {'-'*8} {'-'*8} {'-'*7}")

    for m in matches[:20]:
        bsh = m['bsh']
        ut = m['utide']
        ut_mez = ut['datetime_utc'] + timedelta(hours=1)
        print(f"  {bsh['type']:4s} {bsh['datetime_mez'].strftime('%d.%m.%Y %H:%M'):18s} {bsh['height_pnp']:7.2f} "
              f"{ut_mez.strftime('%d.%m.%Y %H:%M'):18s} {ut['height']:8.2f} "
              f"{m['time_diff_min']:>+8.0f} {m['height_diff_m']:>+7.2f}")

    # 7. Monthly breakdown
    print(f"\n{'=' * 75}")
    print("Monthly summary (mean absolute differences)")
    print(f"{'=' * 75}")
    print(f"  {'Month':8s} {'N':>5s} {'|dT| HW':>10s} {'|dH| HW':>10s} {'|dT| NW':>10s} {'|dH| NW':>10s}")
    print(f"  {'-'*8} {'-'*5} {'-'*10} {'-'*10} {'-'*10} {'-'*10}")

    for month in range(1, 13):
        hw_m = [m for m in hw_matches if m['bsh']['datetime_mez'].month == month]
        nw_m = [m for m in nw_matches if m['bsh']['datetime_mez'].month == month]
        n = len(hw_m) + len(nw_m)
        if n == 0:
            continue
        hw_dt = np.mean(np.abs([m['time_diff_min'] for m in hw_m])) if hw_m else 0
        hw_dh = np.mean(np.abs([m['height_diff_m'] for m in hw_m])) if hw_m else 0
        nw_dt = np.mean(np.abs([m['time_diff_min'] for m in nw_m])) if nw_m else 0
        nw_dh = np.mean(np.abs([m['height_diff_m'] for m in nw_m])) if nw_m else 0
        month_name = datetime(2026, month, 1).strftime('%b')
        print(f"  {month_name:8s} {n:>5d} {hw_dt:>9.1f}m {hw_dh:>9.3f}m {nw_dt:>9.1f}m {nw_dh:>9.3f}m")


if __name__ == "__main__":
    main()
