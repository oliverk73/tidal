#!/usr/bin/env python3
"""
Batch UTide harmonic analysis for Canadian tide stations (CHS).
Reads CSV files from water_levels/Canada/, runs UTide with 93 constituents,
maps to 175 XTide constituents, outputs XTide-compatible harmonics file.
Also compares predictions with CHS API predictions for validation.
"""
import sys
sys.path.insert(0, '/home/oliver/py')

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
import time
import pickle
import json
import requests
import utide

from generate_germany_harmonics_175 import (
    CONSTITUENTS_175,
    UTIDE_TO_XTIDE_NAME,
    find_xtide_match,
    read_header_from_template,
)

CSV_DIR = Path("/home/oliver/water_levels/Canada")
TEMPLATE_PATH = Path("/home/oliver/harmonics/classic/harmonics-dwf-20070318_no_us_no_dupes.txt")
OUTPUT_PATH = Path("/home/oliver/harmonics/utide/harmonics_utide_canada.txt")
CHECKPOINT_DIR = Path("/home/oliver/harmonics/utide/checkpoints_ca")

API_BASE = 'https://api-sine.dfo-mpo.gc.ca/api/v1'

# Station metadata
STATIONS = {
    '07120': {'name': 'Victoria Harbour', 'lat': 48.4244, 'lon': -123.3708, 'tz': 'America/Vancouver', 'province': 'British Columbia'},
    '00490': {'name': 'Halifax', 'lat': 44.6591, 'lon': -63.5834, 'tz': 'America/Halifax', 'province': 'Nova Scotia'},
    '00065': {'name': 'Saint John', 'lat': 45.2546, 'lon': -66.0600, 'tz': 'America/Moncton', 'province': 'New Brunswick'},
    '02985': {'name': 'Rimouski', 'lat': 48.4783, 'lon': -68.5137, 'tz': 'America/Montreal', 'province': 'Quebec'},
    '05010': {'name': 'Churchill', 'lat': 58.7734, 'lon': -94.1919, 'tz': 'America/Winnipeg', 'province': 'Manitoba'},
}

# 93 constituents (same as German/Dutch analysis)
CONSTIT_93 = [
    'J1', 'K1', 'O1', 'OO1', 'P1', 'Q1', '2Q1', 'RHO1', 'ALP1', 'BET1',
    'CHI1', 'NO1', 'PHI1', 'PI1', 'PSI1', 'SIG1', 'SO1', 'THE1', '2PO1',
    'TAU1', 'UPS1',
    'K2', 'L2', 'M2', 'N2', '2N2', 'R2', 'S2', 'T2', 'LDA2', 'MU2',
    'NU2', 'EPS2', 'ETA2', '2SM2', '2NS2', 'SKM2', 'OP2', 'MKS2', 'MSN2',
    'OQ2',
    'MF', 'MSF', 'MM', 'SA', 'SSA', 'MSM',
    'M3', 'MK3', 'MO3', 'SK3', 'SO3', 'NO3',
    'M4', 'MN4', 'MS4', 'MK4', 'S4', 'SN4', 'N4', 'SL4', '3MS4',
    '2MK5', '2SK5', '2MO5', 'MNO5', 'MSK5', '3KM5', '2MP5', '3MP5', 'MNK5',
    'M6', '2MN6', '2MS6', '2MK6', '2NM6', '2SM6', 'MSK6', 'MSN6', 'S6',
    'M7', '3MK7',
    'M8', '3MN8', '3MS8', '3MK8',
    '4MK9', 'M10', 'M12',
    'H1', 'H2', 'S1',
]


def load_csv(csv_path):
    """Load CHS CSV and return datetime + meters arrays."""
    df = pd.read_csv(csv_path, parse_dates=['time'], index_col='time')
    df = df.dropna(subset=['waterlevel_m'])

    if len(df) == 0:
        return None, None

    # Timestamps are already UTC
    if df.index.tz is not None:
        datetimes_utc = df.index.tz_convert('UTC').tz_localize(None).to_pydatetime()
    else:
        datetimes_utc = df.index.to_pydatetime()

    levels_m = df['waterlevel_m'].values.astype(np.float64)
    return np.array(datetimes_utc), levels_m


def analyze_station(csv_path, meta, code):
    """Run UTide analysis for one station."""
    checkpoint_file = CHECKPOINT_DIR / f"{code}.pkl"

    if checkpoint_file.exists():
        print(f"  ✓ Checkpoint vorhanden, lade...")
        with open(checkpoint_file, 'rb') as f:
            return pickle.load(f)

    t0 = time.time()
    datetimes_utc, levels = load_csv(csv_path)

    if datetimes_utc is None or len(datetimes_utc) < 2000:
        n = 0 if datetimes_utc is None else len(datetimes_utc)
        print(f"  ✗ Zu wenig Daten ({n} Werte)")
        return None

    lat = meta['lat']
    print(f"  UTide solve ({len(datetimes_utc)} Beobachtungen, lat={lat:.2f})...", end='', flush=True)

    coef = utide.solve(
        datetimes_utc, levels, lat=lat,
        nodal=True, trend=False, method='ols',
        conf_int='none', verbose=False, constit=CONSTIT_93,
    )
    print(" OK", flush=True)

    # Map to XTide 175 constituents
    from utide._ut_constants import ut_constants
    const_table = ut_constants['const']
    utide_all_names = [n.strip() for n in const_table.name]

    utide_results = {}
    for i, uname in enumerate(coef['name']):
        uname = uname.strip()
        amplitude = coef['A'][i]
        greenwich_phase = coef['g'][i]

        if uname in utide_all_names:
            idx = utide_all_names.index(uname)
            utide_speed = const_table.freq[idx] * 360.0
        else:
            continue

        xt_name, xt_speed = find_xtide_match(uname, utide_speed)
        if xt_name is None:
            continue

        utide_results[xt_name] = {
            'amplitude': amplitude,
            'phase': greenwich_phase % 360,
            'speed': xt_speed,
        }

    constituents = []
    n_analyzed = 0
    for name, speed in CONSTITUENTS_175:
        if name in utide_results:
            r = utide_results[name]
            constituents.append({
                'name': name, 'amplitude': r['amplitude'],
                'phase': r['phase'], 'speed': speed,
            })
            n_analyzed += 1
        else:
            constituents.append({
                'name': name, 'amplitude': 0.0, 'phase': 0.0,
                'speed': speed, 'not_analyzed': True,
            })

    # R² via reconstruction
    recon = utide.reconstruct(datetimes_utc, coef, verbose=False)
    residuals = levels - recon['h']
    ss_res = np.sum(residuals**2)
    ss_tot = np.sum((levels - np.mean(levels))**2)
    r_squared = 1 - ss_res / ss_tot if ss_tot > 0 else 0
    rms_error = np.sqrt(np.mean(residuals**2))

    m2_amp = 0
    k1_amp = 0
    for c in constituents:
        if c['name'] == 'M2':
            m2_amp = c['amplitude']
        if c['name'] == 'K1':
            k1_amp = c['amplitude']

    duration = time.time() - t0

    result = {
        'mean': coef['mean'],
        'constituents': constituents,
        'n_analyzed': n_analyzed,
        'r_squared': r_squared,
        'rms_error': rms_error,
        'm2_amp': m2_amp,
        'k1_amp': k1_amp,
        'n_obs': len(datetimes_utc),
        'start_time': datetimes_utc[0],
        'end_time': datetimes_utc[-1],
        'station_meta': meta,
        'code': code,
        'duration': duration,
        'coef': coef,  # Keep for prediction comparison
    }

    with open(checkpoint_file, 'wb') as f:
        pickle.dump(result, f)

    return result


def format_station_block(result):
    """Format a single station block in XTide harmonics format."""
    meta = result['station_meta']
    station_name = meta['name']
    lat = meta['lat']
    lon = meta['lon']
    province = meta.get('province', 'Canada')

    lines = []
    lines.append(f"# Harmonic constants derived from CHS water level observations")
    lines.append(f"# using UTide (v{utide.__version__}) with {result['n_obs']} observations")
    lines.append(f"# from {result['start_time'].strftime('%Y-%m-%d')} to {result['end_time'].strftime('%Y-%m-%d')}")
    lines.append(f"# R^2 = {result['r_squared']:.4f}, RMS error = {result['rms_error']:.4f} m")
    lines.append(f"# Constituents analyzed: {result['n_analyzed']}")
    lines.append(f"#")
    lines.append(f"# {station_name}")
    lines.append(f"# BEGIN HOT COMMENTS")
    lines.append(f"# country: Canada")
    lines.append(f"# source: Derived from CHS IWLS water level observations with UTide")
    lines.append(f"# station_id_context: CHS")
    lines.append(f"# date_imported: {datetime.now().strftime('%Y%m%d')}")
    lines.append(f"# datum: Chart Datum")
    lines.append(f"# confidence: 7")
    lines.append(f"# !units: meters")
    lines.append(f"# !longitude: {lon:.6f}")
    lines.append(f"# !latitude: {lat:.6f}")

    lines.append(f"{station_name}, {province}, Canada")
    lines.append(f"+00:00 :{meta.get('tz', 'UTC')}")
    lines.append(f"{result['mean']:.4f} meters")

    for c in result['constituents']:
        if c.get('not_analyzed') or c['amplitude'] < 0.00005:
            lines.append(f"x 0 0")
        else:
            lines.append(f"{c['name']:15s} {c['amplitude']:.4f}  {c['phase']:.2f}")

    return '\n'.join(lines)


def compare_with_chs(result):
    """Compare UTide predictions with CHS official predictions for Jan 2026."""
    code = result['code']
    meta = result['station_meta']
    coef = result['coef']

    print(f"\n  Vergleich mit CHS-Vorhersagen (Januar 2026)...")

    # Generate UTide predictions for January 2026
    pred_start = datetime(2026, 1, 1)
    pred_end = datetime(2026, 1, 31, 23, 45)
    pred_times = pd.date_range(pred_start, pred_end, freq='15min')
    pred_dt = pred_times.to_pydatetime()

    recon = utide.reconstruct(np.array(pred_dt), coef, verbose=False)
    utide_df = pd.DataFrame({
        'time': pred_times,
        'utide_m': recon['h'],
    }).set_index('time')

    # Download CHS predictions (wlp) for same period, week by week
    station_info = requests.get(f'{API_BASE}/stations', params={'code': code}, timeout=15).json()
    if not station_info:
        print("    Station nicht in API gefunden")
        return None
    station_id = station_info[0]['id']

    chs_rows = []
    for week_start in pd.date_range('2026-01-01', '2026-01-29', freq='7D'):
        week_end = week_start + timedelta(days=6, hours=23, minutes=59)
        if week_end > pred_end:
            week_end = pred_end

        try:
            resp = requests.get(
                f'{API_BASE}/stations/{station_id}/data',
                params={
                    'time-series-code': 'wlp',
                    'from': week_start.strftime('%Y-%m-%dT%H:%M:%SZ'),
                    'to': week_end.strftime('%Y-%m-%dT%H:%M:%SZ'),
                    'resolution': 'FIFTEEN_MINUTES',
                },
                timeout=30,
            )
            if resp.status_code == 200:
                for d in resp.json():
                    chs_rows.append((d['eventDate'], d['value']))
            time.sleep(2.5)
        except Exception as e:
            print(f"    API-Fehler: {e}")

    if not chs_rows:
        print("    Keine CHS-Vorhersagen verfügbar")
        return None

    chs_df = pd.DataFrame(chs_rows, columns=['time', 'chs_m'])
    chs_df['time'] = pd.to_datetime(chs_df['time'], utc=True).dt.tz_localize(None)
    chs_df = chs_df.set_index('time')

    # Merge
    merged = utide_df.join(chs_df, how='inner').dropna()
    if len(merged) == 0:
        print("    Keine überlappenden Daten")
        return None

    diff = merged['utide_m'] - merged['chs_m']
    mean_diff = diff.mean()
    rms = np.sqrt(np.mean(diff**2))
    max_abs = diff.abs().max()
    r2 = 1 - np.sum(diff**2) / np.sum((merged['chs_m'] - merged['chs_m'].mean())**2)

    print(f"    Datenpunkte:          {len(merged)}")
    print(f"    Mittlere Abweichung:  {mean_diff*100:+.2f} cm")
    print(f"    RMS-Fehler:           {rms*100:.2f} cm")
    print(f"    Max |Abweichung|:     {max_abs*100:.2f} cm")
    print(f"    R²:                   {r2:.4f}")

    return {
        'station': meta['name'],
        'code': code,
        'mean_diff_cm': mean_diff * 100,
        'rms_cm': rms * 100,
        'max_abs_cm': max_abs * 100,
        'r2': r2,
        'n_points': len(merged),
    }


def main():
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("UTide Harmonic Analysis — Canadian Tide Stations (CHS)")
    print("=" * 70)

    # Find CSV files
    csv_files = sorted(CSV_DIR.glob("*.csv"))
    print(f"CSV-Dateien gefunden: {len(csv_files)}")
    for f in csv_files:
        size_mb = f.stat().st_size / (1024*1024)
        print(f"  {f.name}: {size_mb:.1f} MB")
    print()

    results = []
    comparisons = []

    for code, meta in STATIONS.items():
        # Find matching CSV
        csv_match = [f for f in csv_files if f.name.startswith(code)]
        if not csv_match:
            print(f"  ✗ {meta['name']}: Keine CSV-Datei gefunden")
            continue

        csv_path = csv_match[0]
        print(f"\n{'─'*70}")
        print(f"  {meta['name']} ({code}) — {meta.get('province', '')}")
        print(f"  CSV: {csv_path.name}")

        result = analyze_station(csv_path, meta, code)
        if result is None:
            continue

        results.append(result)
        print(f"  R² = {result['r_squared']:.4f}, RMS = {result['rms_error']:.4f} m")
        print(f"  M2 = {result['m2_amp']:.4f} m, K1 = {result['k1_amp']:.4f} m")
        print(f"  Konstituenten: {result['n_analyzed']}, Dauer: {result['duration']:.1f}s")

        # Compare with CHS predictions
        comp = compare_with_chs(result)
        if comp:
            comparisons.append(comp)

    # Write harmonics file
    if results:
        header = read_header_from_template(TEMPLATE_PATH)
        print(f"\n\nSchreibe Harmonics-Datei: {OUTPUT_PATH.name}")
        with open(OUTPUT_PATH, 'w', encoding='iso-8859-1') as f:
            f.write(header)
            f.write('\n')
            for result in results:
                block = format_station_block(result)
                f.write(block)
                f.write('\n')
        print(f"  {len(results)} Stationen, {OUTPUT_PATH.stat().st_size / 1024:.0f} KB")

    # Summary
    if comparisons:
        print(f"\n\n{'='*70}")
        print("ZUSAMMENFASSUNG: UTide vs. CHS-Vorhersagen (Januar 2026)")
        print(f"{'='*70}")
        print(f"{'Station':<25s} {'RMS':>7s} {'MaxAbs':>7s} {'Bias':>7s} {'R²':>7s}")
        print(f"{'─'*25} {'─'*7} {'─'*7} {'─'*7} {'─'*7}")
        for c in comparisons:
            print(f"{c['station']:<25s} {c['rms_cm']:>6.2f}  {c['max_abs_cm']:>6.2f}  {c['mean_diff_cm']:>+6.2f}  {c['r2']:>6.4f}")

        rms_all = [c['rms_cm'] for c in comparisons]
        print(f"\nDurchschnittlicher RMS-Fehler: {np.mean(rms_all):.2f} cm")


if __name__ == '__main__':
    main()
