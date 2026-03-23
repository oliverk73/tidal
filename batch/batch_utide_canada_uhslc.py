#!/usr/bin/env python3
"""
UTide harmonic analysis for Canadian tide stations using UHSLC hourly data.
Uses last 19 years (full nodal cycle) where available.
Compares with CHS official predictions for validation.
"""
import sys
sys.path.insert(0, '/home/oliver/py')

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
import time
import pickle
import requests
import utide

from generate_germany_harmonics_175 import (
    CONSTITUENTS_175,
    find_xtide_match,
    read_header_from_template,
)

CSV_DIR = Path("/home/oliver/water_levels/Canada_UHSLC")
TEMPLATE_PATH = Path("/home/oliver/harmonics/classic/harmonics-dwf-20070318_no_us_no_dupes.txt")
OUTPUT_PATH = Path("/home/oliver/harmonics/utide/harmonics_utide_canada_uhslc.txt")
CHECKPOINT_DIR = Path("/home/oliver/harmonics/utide/checkpoints_ca_uhslc")

API_BASE = 'https://api-sine.dfo-mpo.gc.ca/api/v1'

USE_LAST_N_YEARS = 19

# Station metadata: uhslc_id, CHS code (for API comparison), timezone
STATIONS = {
    275: {'name': 'Halifax', 'lat': 44.667, 'lon': -63.583, 'tz': 'America/Halifax', 'province': 'Nova Scotia', 'chs_code': '00490'},
    540: {'name': 'Prince Rupert', 'lat': 54.317, 'lon': -130.323, 'tz': 'America/Vancouver', 'province': 'British Columbia', 'chs_code': '09354'},
    542: {'name': 'Tofino', 'lat': 49.153, 'lon': -125.913, 'tz': 'America/Vancouver', 'province': 'British Columbia', 'chs_code': '08615'},
    543: {'name': 'Victoria', 'lat': 48.425, 'lon': -123.370, 'tz': 'America/Vancouver', 'province': 'British Columbia', 'chs_code': '07120'},
    276: {'name': "St. John's", 'lat': 47.567, 'lon': -52.700, 'tz': 'America/St_Johns', 'province': 'Newfoundland', 'chs_code': '00905'},
    274: {'name': 'Churchill', 'lat': 58.783, 'lon': -94.183, 'tz': 'America/Winnipeg', 'province': 'Manitoba', 'chs_code': '05010'},
    833: {'name': 'Nain', 'lat': 56.550, 'lon': -61.683, 'tz': 'America/Goose_Bay', 'province': 'Newfoundland', 'chs_code': '01430'},
    273: {'name': 'Port-aux-Basques', 'lat': 47.567, 'lon': -59.133, 'tz': 'America/St_Johns', 'province': 'Newfoundland', 'chs_code': '02200'},
    541: {'name': 'Bamfield', 'lat': 48.833, 'lon': -125.133, 'tz': 'America/Vancouver', 'province': 'British Columbia', 'chs_code': '08545'},
    836: {'name': 'Alert', 'lat': 82.492, 'lon': -62.317, 'tz': 'America/Iqaluit', 'province': 'Nunavut', 'chs_code': '03765'},
}

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


def load_csv(csv_path, use_last_n_years=19):
    """Load UHSLC CSV (time, waterlevel_m) and return arrays."""
    df = pd.read_csv(csv_path, parse_dates=['time'], index_col='time')
    df = df.dropna(subset=['waterlevel_m'])

    if len(df) == 0:
        return None, None

    # Use last N years
    if use_last_n_years is not None and len(df) > 0:
        cutoff = df.index[-1] - pd.Timedelta(days=use_last_n_years * 365.25)
        df = df[df.index >= cutoff]

    # Timestamps are UTC (UHSLC data)
    if df.index.tz is not None:
        datetimes_utc = df.index.tz_convert('UTC').tz_localize(None).to_pydatetime()
    else:
        datetimes_utc = df.index.to_pydatetime()

    levels_m = df['waterlevel_m'].values.astype(np.float64)
    return np.array(datetimes_utc), levels_m


def analyze_station(csv_path, meta, uhslc_id):
    """Run UTide analysis for one station."""
    key = str(uhslc_id)
    checkpoint_file = CHECKPOINT_DIR / f"{key}.pkl"

    if checkpoint_file.exists():
        print(f"  ✓ Checkpoint vorhanden, lade...")
        with open(checkpoint_file, 'rb') as f:
            return pickle.load(f)

    t0 = time.time()
    datetimes_utc, levels = load_csv(csv_path, use_last_n_years=USE_LAST_N_YEARS)

    if datetimes_utc is None or len(datetimes_utc) < 2000:
        n = 0 if datetimes_utc is None else len(datetimes_utc)
        print(f"  ✗ Zu wenig Daten ({n} Werte)")
        return None

    lat = meta['lat']
    years = len(datetimes_utc) / (24 * 365.25)
    print(f"  UTide solve ({len(datetimes_utc)} Beob., {years:.1f} Jahre, lat={lat:.2f})...",
          end='', flush=True)

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

    m2_amp = next((c['amplitude'] for c in constituents if c['name'] == 'M2'), 0)
    k1_amp = next((c['amplitude'] for c in constituents if c['name'] == 'K1'), 0)

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
        'uhslc_id': uhslc_id,
        'duration': duration,
        'coef': coef,
    }

    with open(checkpoint_file, 'wb') as f:
        pickle.dump(result, f)

    return result


def format_station_block(result):
    """Format a single station block in XTide harmonics format."""
    meta = result['station_meta']
    name = meta['name']
    lat = meta['lat']
    lon = meta['lon']
    province = meta.get('province', 'Canada')

    lines = []
    lines.append(f"# Harmonic constants derived from UHSLC hourly sea level data")
    lines.append(f"# using UTide (v{utide.__version__}) with {result['n_obs']} observations")
    lines.append(f"# from {result['start_time'].strftime('%Y-%m-%d')} to {result['end_time'].strftime('%Y-%m-%d')}")
    lines.append(f"# R^2 = {result['r_squared']:.4f}, RMS error = {result['rms_error']:.4f} m")
    lines.append(f"# Constituents analyzed: {result['n_analyzed']}")
    lines.append(f"#")
    lines.append(f"# {name}")
    lines.append(f"# BEGIN HOT COMMENTS")
    lines.append(f"# country: Canada")
    lines.append(f"# source: Derived from UHSLC hourly data with UTide harmonic analysis")
    lines.append(f"# station_id_context: UHSLC-{result['uhslc_id']}")
    lines.append(f"# date_imported: {datetime.now().strftime('%Y%m%d')}")
    lines.append(f"# datum: station datum")
    lines.append(f"# confidence: 8")
    lines.append(f"# !units: meters")
    lines.append(f"# !longitude: {lon:.6f}")
    lines.append(f"# !latitude: {lat:.6f}")

    lines.append(f"{name}, {province}, Canada")
    lines.append(f"+00:00 :{meta.get('tz', 'UTC')}")
    lines.append(f"{result['mean']:.4f} meters")

    for c in result['constituents']:
        if c.get('not_analyzed') or c['amplitude'] < 0.00005:
            lines.append(f"x 0 0")
        else:
            lines.append(f"{c['name']:15s} {c['amplitude']:.4f}  {c['phase']:.2f}")

    return '\n'.join(lines)


def compare_with_chs(result):
    """Compare UTide predictions with CHS official predictions for Jan 2025."""
    meta = result['station_meta']
    coef = result['coef']
    chs_code = meta.get('chs_code', '')

    if not chs_code:
        return None

    print(f"  Vergleich mit CHS-Vorhersagen (Januar 2025)...")

    # Generate UTide predictions
    pred_start = datetime(2025, 1, 1)
    pred_end = datetime(2025, 1, 31, 23, 45)
    pred_times = pd.date_range(pred_start, pred_end, freq='15min')
    pred_dt = pred_times.to_pydatetime()

    recon = utide.reconstruct(np.array(pred_dt), coef, verbose=False)
    utide_df = pd.DataFrame({
        'time': pred_times,
        'utide_m': recon['h'],
    }).set_index('time')

    # Get CHS station ID
    try:
        resp = requests.get(f'{API_BASE}/stations', params={'code': chs_code}, timeout=15)
        station_info = resp.json()
        if not station_info:
            print(f"    CHS Station {chs_code} nicht gefunden")
            return None
        station_id = station_info[0]['id']
    except Exception as e:
        print(f"    CHS API Fehler: {e}")
        return None

    # Download CHS predictions week by week
    chs_rows = []
    for week_start in pd.date_range('2025-01-01', '2025-01-29', freq='7D'):
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
        'uhslc_id': result['uhslc_id'],
        'mean_diff_cm': mean_diff * 100,
        'rms_cm': rms * 100,
        'max_abs_cm': max_abs * 100,
        'r2': r2,
        'n_points': len(merged),
    }


def main():
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("UTide Harmonic Analysis — UHSLC Hourly Data (Canada)")
    print(f"Letzte {USE_LAST_N_YEARS} Jahre (voller Nodalzyklus)")
    print("=" * 70)

    csv_files = sorted(CSV_DIR.glob("*.csv"))
    print(f"CSV-Dateien: {len(csv_files)}")
    for f in csv_files:
        print(f"  {f.name}: {f.stat().st_size / (1024*1024):.1f} MB")
    print()

    results = []
    comparisons = []

    for uhslc_id, meta in STATIONS.items():
        csv_match = [f for f in csv_files if f.name.startswith(str(uhslc_id))]
        if not csv_match:
            print(f"  ✗ {meta['name']}: Keine CSV-Datei")
            continue

        csv_path = csv_match[0]
        print(f"\n{'─'*70}")
        print(f"  {meta['name']} (UHSLC {uhslc_id}) — {meta.get('province', '')}")

        result = analyze_station(csv_path, meta, uhslc_id)
        if result is None:
            continue

        results.append(result)
        print(f"  R² = {result['r_squared']:.4f}, RMS = {result['rms_error']:.4f} m")
        print(f"  M2 = {result['m2_amp']:.4f} m, K1 = {result['k1_amp']:.4f} m")
        print(f"  Konstituenten: {result['n_analyzed']}, Dauer: {result['duration']:.1f}s")

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
        print("VERGLEICH: UTide (UHSLC 19J) vs. CHS-Vorhersagen (Jan 2025)")
        print(f"{'='*70}")
        print(f"{'Station':<25s} {'RMS':>7s} {'MaxAbs':>7s} {'Bias':>7s} {'R²':>7s}")
        print(f"{'─'*25} {'─'*7} {'─'*7} {'─'*7} {'─'*7}")
        for c in comparisons:
            print(f"{c['station']:<25s} {c['rms_cm']:>6.2f}  {c['max_abs_cm']:>6.2f}  {c['mean_diff_cm']:>+6.2f}  {c['r2']:>6.4f}")

        rms_all = [c['rms_cm'] for c in comparisons]
        print(f"\nDurchschnittlicher RMS-Fehler: {np.mean(rms_all):.2f} cm")

    # Compare with previous 7-year results if available
    prev_checkpoint = Path("/home/oliver/harmonics/utide/checkpoints_ca")
    if prev_checkpoint.exists() and comparisons:
        print(f"\n\n{'='*70}")
        print("VERGLEICH: 19 Jahre (UHSLC) vs. 7 Jahre (CHS IWLS)")
        print(f"{'='*70}")
        print(f"{'Station':<25s} {'RMS 19J':>8s} {'RMS 7J':>8s} {'Verbesserung':>13s}")
        print(f"{'─'*25} {'─'*8} {'─'*8} {'─'*13}")
        for comp in comparisons:
            name = comp['station']
            rms_19 = comp['rms_cm']
            # Try to find matching 7-year result
            for code, meta in [('07120', 'Victoria'), ('00065', 'Saint John'),
                              ('02985', 'Rimouski'), ('05010', 'Churchill')]:
                prev_file = prev_checkpoint / f"{code}.pkl"
                # Match by name similarity
            print(f"{name:<25s} {rms_19:>7.2f}  {'n/a':>8s} {'':>13s}")


if __name__ == '__main__':
    main()
