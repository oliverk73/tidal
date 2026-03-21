#!/usr/bin/env python3
"""
Compare UTide harmonic predictions with RWS astronomical water levels.
Picks a few representative stations, generates predictions from checkpoints,
downloads RWS data for the same period, and compares.
"""
import sys
sys.path.insert(0, '/home/oliver/py')

import numpy as np
import pandas as pd
import pickle
import datetime
import ddlpy
import utide
from pathlib import Path

CHECKPOINT_DIR = Path("/home/oliver/harmonics_working/checkpoints_nl")
CSV_DIR = Path("/home/oliver/water_levels/Netherlands")

# Comparison period: January 2026 (recent, full month)
COMPARE_START = datetime.datetime(2026, 1, 1)
COMPARE_END = datetime.datetime(2026, 1, 31, 23, 59)

# Representative stations: coast, estuary, inland
TEST_STATIONS = [
    'hoekvanholland',
    'vlissingen',
    'delfzijl',
    'denhelder.marsdiep',
    'harlingen.waddenzee',
    'scheveningen',
]


def load_checkpoint_and_predict(key, start, end):
    """Load UTide checkpoint and generate predictions for given period."""
    checkpoint_file = CHECKPOINT_DIR / f"{key}.pkl"
    if not checkpoint_file.exists():
        return None, None

    with open(checkpoint_file, 'rb') as f:
        result = pickle.load(f)

    # Reconstruct UTide coefficients from checkpoint
    # We need to re-run utide.solve to get coef object, but we can also
    # rebuild predictions from the stored constituents directly.
    # Easier: load the original CSV, run utide.solve on it, then reconstruct.

    csv_path = CSV_DIR / f"{key}.csv"
    if not csv_path.exists():
        return None, None

    # Load CSV for utide.solve
    df = pd.read_csv(csv_path, parse_dates=['time'], index_col='time')
    df = df.dropna(subset=['waterlevel_cm_NAP'])

    if df.index.tz is not None:
        datetimes_utc = df.index.tz_convert('UTC').tz_localize(None).to_pydatetime()
    else:
        datetimes_utc = (df.index - pd.Timedelta(hours=1)).to_pydatetime()

    levels_m = df['waterlevel_cm_NAP'].values / 100.0

    lat = result['station_meta']['lat']

    print(f"    UTide solve ({len(datetimes_utc)} obs)...", end='', flush=True)
    coef = utide.solve(
        np.array(datetimes_utc), levels_m.astype(np.float64), lat=lat,
        nodal=True, trend=False, method='ols',
        conf_int='none', verbose=False,
        constit=[
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
        ],
    )
    print(" OK", flush=True)

    # Generate predictions for comparison period
    pred_times = pd.date_range(start, end, freq='10min')
    pred_dt = pred_times.to_pydatetime()

    print(f"    Reconstruct ({len(pred_dt)} timesteps)...", end='', flush=True)
    recon = utide.reconstruct(np.array(pred_dt), coef, verbose=False)
    print(" OK", flush=True)

    pred_df = pd.DataFrame({
        'time': pred_times,
        'utide_m': recon['h'],
    }).set_index('time')

    return pred_df, result['station_meta']


def download_rws_data(station_code, start, end):
    """Download astronomical water level from RWS for comparison period."""
    print(f"    RWS download...", end='', flush=True)

    locations = ddlpy.locations()
    sel = locations[
        (locations['Grootheid.Code'] == 'WATHTE') &
        (locations['Hoedanigheid.Code'] == 'NAP') &
        (locations['ProcesType'] == 'astronomisch') &
        (locations['Groepering.Code'] == '')
    ]

    if station_code not in sel.index:
        # Try partial match
        matches = [idx for idx in sel.index if station_code in idx]
        if matches:
            station_code = matches[0]
        else:
            print(f" station not found!")
            return None

    station = sel.loc[station_code]

    measurements = ddlpy.measurements(station, start_date=start, end_date=end)

    if measurements is None or len(measurements) == 0:
        print(" KEINE DATEN")
        return None

    # Extract water level
    rws_df = pd.DataFrame({
        'time': measurements.index,
        'rws_cm': measurements['Meetwaarde.Waarde_Numeriek'].values,
    })
    rws_df['time'] = pd.to_datetime(rws_df['time'], utc=True).dt.tz_convert(None)
    rws_df['rws_m'] = rws_df['rws_cm'] / 100.0
    rws_df = rws_df.set_index('time')

    print(f" {len(rws_df)} Werte", flush=True)
    return rws_df


def compare(utide_df, rws_df, station_name):
    """Compare UTide predictions with RWS data."""
    # Merge on time index
    merged = utide_df.join(rws_df[['rws_m']], how='inner')
    merged = merged.dropna()

    if len(merged) == 0:
        print(f"    KEINE überlappenden Daten!")
        return

    diff = merged['utide_m'] - merged['rws_m']

    # Statistics
    mean_diff = diff.mean()
    std_diff = diff.std()
    rms = np.sqrt(np.mean(diff**2))
    max_abs = diff.abs().max()
    r2 = 1 - np.sum(diff**2) / np.sum((merged['rws_m'] - merged['rws_m'].mean())**2)

    # HW/NW comparison: find high and low water times in RWS data
    rws_series = merged['rws_m']
    utide_series = merged['utide_m']

    print(f"\n    {'─'*55}")
    print(f"    Station: {station_name}")
    print(f"    Zeitraum: {merged.index[0].strftime('%d.%m.%Y')} – {merged.index[-1].strftime('%d.%m.%Y')}")
    print(f"    Datenpunkte: {len(merged)}")
    print(f"    {'─'*55}")
    print(f"    Mittlere Abweichung:    {mean_diff*100:>+7.2f} cm")
    print(f"    Std. Abweichung:        {std_diff*100:>7.2f} cm")
    print(f"    RMS-Fehler:             {rms*100:>7.2f} cm")
    print(f"    Max. |Abweichung|:      {max_abs*100:>7.2f} cm")
    print(f"    R²:                     {r2:>7.4f}")

    # Show a few sample values
    print(f"\n    Stichprobe (alle 12h):")
    print(f"    {'Zeit':>20s}  {'RWS':>8s}  {'UTide':>8s}  {'Diff':>8s}")
    sample = merged.iloc[::72]  # every 12 hours (72 * 10min)
    for t, row in list(sample.iterrows())[:10]:
        d = row['utide_m'] - row['rws_m']
        print(f"    {t.strftime('%d.%m. %H:%M'):>20s}  {row['rws_m']*100:>7.1f}  {row['utide_m']*100:>7.1f}  {d*100:>+7.1f} cm")

    return {
        'station': station_name,
        'mean_diff_cm': mean_diff * 100,
        'std_diff_cm': std_diff * 100,
        'rms_cm': rms * 100,
        'max_abs_cm': max_abs * 100,
        'r2': r2,
        'n_points': len(merged),
    }


def main():
    print("=" * 65)
    print("Vergleich UTide-Vorhersagen vs. RWS astronomische Wasserstände")
    print("=" * 65)
    print(f"Zeitraum: {COMPARE_START.strftime('%d.%m.%Y')} – {COMPARE_END.strftime('%d.%m.%Y')}")
    print()

    results = []

    for key in TEST_STATIONS:
        print(f"\n{'─'*65}")
        print(f"  Station: {key}")

        # 1. Generate UTide predictions
        utide_df, meta = load_checkpoint_and_predict(key, COMPARE_START, COMPARE_END)
        if utide_df is None:
            print(f"    Checkpoint nicht gefunden, überspringe.")
            continue

        # 2. Download RWS data
        code = meta.get('code', key)
        rws_df = download_rws_data(code, COMPARE_START, COMPARE_END)
        if rws_df is None:
            continue

        # 3. Compare
        r = compare(utide_df, rws_df, meta['name'])
        if r:
            results.append(r)

    # Summary
    if results:
        print(f"\n\n{'='*65}")
        print(f"ZUSAMMENFASSUNG")
        print(f"{'='*65}")
        print(f"{'Station':<40s} {'RMS':>7s} {'MaxAbs':>7s} {'R²':>7s}")
        print(f"{'─'*40} {'─'*7} {'─'*7} {'─'*7}")
        for r in results:
            print(f"{r['station']:<40s} {r['rms_cm']:>6.2f}  {r['max_abs_cm']:>6.2f}  {r['r2']:>6.4f}")

        rms_all = [r['rms_cm'] for r in results]
        print(f"\nDurchschnittlicher RMS-Fehler: {np.mean(rms_all):.2f} cm")


if __name__ == '__main__':
    main()
