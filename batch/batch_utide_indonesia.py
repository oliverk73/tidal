#!/usr/bin/env python3
"""
UTide harmonic analysis for Indonesian tide stations using UHSLC hourly data.
Uses last 19 years (full nodal cycle) where available.
"""
import sys
sys.path.insert(0, '/home/oliver/py')

import numpy as np
import pandas as pd
from datetime import datetime
from pathlib import Path
import time
import pickle
import gc
import utide

from generate_germany_harmonics_175 import (
    CONSTITUENTS_175,
    find_xtide_match,
    read_header_from_template,
)

CSV_DIR = Path("/home/oliver/water_levels/Indonesia_UHSLC")
TEMPLATE_PATH = Path("/home/oliver/harmonics/classic/harmonics-dwf-20070318_mod.txt")
OUTPUT_PATH = Path("/home/oliver/harmonics/utide/harmonics_utide_indonesia.txt")
CHECKPOINT_DIR = Path("/home/oliver/harmonics/utide/checkpoints_indonesia")

USE_LAST_N_YEARS = 19

STATIONS = {
    33:  {'name': 'Bitung',          'lat':  1.438, 'lon': 125.190, 'tz': 'Asia/Makassar'},
    107: {'name': 'Padang',          'lat': -1.000, 'lon': 100.367, 'tz': 'Asia/Jakarta'},
    122: {'name': 'Sibolga',         'lat':  1.750, 'lon':  98.767, 'tz': 'Asia/Jakarta'},
    123: {'name': 'Sabang',          'lat':  5.833, 'lon':  95.333, 'tz': 'Asia/Jakarta'},
    125: {'name': 'Prigi',           'lat': -8.283, 'lon': 111.733, 'tz': 'Asia/Jakarta'},
    133: {'name': 'Ambon',           'lat': -3.700, 'lon': 128.200, 'tz': 'Asia/Jayapura'},
    160: {'name': 'Surabaya',        'lat': -7.208, 'lon': 112.725, 'tz': 'Asia/Jakarta'},
    161: {'name': 'Jakarta',         'lat': -6.117, 'lon': 106.850, 'tz': 'Asia/Jakarta'},
    162: {'name': 'Cilacap',         'lat': -7.752, 'lon': 109.017, 'tz': 'Asia/Jakarta'},
    163: {'name': 'Benoa',           'lat': -8.745, 'lon': 115.210, 'tz': 'Asia/Makassar'},
    416: {'name': 'Tanjung Lesung',  'lat': -6.483, 'lon': 105.667, 'tz': 'Asia/Jakarta'},
    417: {'name': 'Sadeng',          'lat': -8.500, 'lon': 110.783, 'tz': 'Asia/Jakarta'},
    418: {'name': 'Waikelo',         'lat': -9.400, 'lon': 119.233, 'tz': 'Asia/Makassar'},
    419: {'name': 'Lembar',          'lat': -8.732, 'lon': 116.072, 'tz': 'Asia/Makassar'},
    420: {'name': 'Saumlaki',        'lat': -7.982, 'lon': 131.290, 'tz': 'Asia/Jayapura'},
    913: {'name': 'Telukdalam',      'lat':  0.555, 'lon':  97.822, 'tz': 'Asia/Jakarta'},
    914: {'name': 'Meulaboh',        'lat':  5.128, 'lon':  96.132, 'tz': 'Asia/Jakarta'},
}

# Island/region names for output
ISLAND_NAMES = {
    33:  'Sulawesi',
    107: 'Sumatra',
    122: 'Sumatra',
    123: 'Pulau Weh',
    125: 'Java',
    133: 'Maluku',
    160: 'Java',
    161: 'Java',
    162: 'Java',
    163: 'Bali',
    416: 'Java',
    417: 'Java',
    418: 'Sumba',
    419: 'Lombok',
    420: 'Yamdena',
    913: 'Nias',
    914: 'Sumatra',
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

    if use_last_n_years is not None and len(df) > 0:
        cutoff = df.index[-1] - pd.Timedelta(days=use_last_n_years * 365.25)
        df = df[df.index >= cutoff]

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
        with open(checkpoint_file, 'rb') as f:
            result = pickle.load(f)
        print(f"  Checkpoint (R²={result['r_squared']:.4f})")
        return result

    t0 = time.time()
    datetimes_utc, levels = load_csv(csv_path, use_last_n_years=USE_LAST_N_YEARS)

    if datetimes_utc is None or len(datetimes_utc) < 2000:
        n = 0 if datetimes_utc is None else len(datetimes_utc)
        print(f"  Zu wenig Daten ({n} Werte)")
        return None

    lat = meta['lat']
    years = len(datetimes_utc) / (24 * 365.25)
    print(f"  UTide solve ({len(datetimes_utc)} Beob., {years:.1f} Jahre, lat={lat:.2f})...",
          end='', flush=True)

    try:
        coef = utide.solve(
            datetimes_utc, levels, lat=lat,
            nodal=True, trend=False, method='ols',
            conf_int='none', verbose=False, constit=CONSTIT_93,
        )
    except Exception as e:
        print(f" FEHLER: {e}")
        return None

    print(" OK", flush=True)

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
    }

    with open(checkpoint_file, 'wb') as f:
        pickle.dump(result, f)

    del coef, recon, datetimes_utc, levels, residuals
    gc.collect()

    print(f"  R²={r_squared:.4f}, RMS={rms_error:.4f}m, M2={m2_amp:.4f}m, "
          f"K1={k1_amp:.4f}m ({duration:.0f}s)")

    return result


def format_station_block(result):
    """Format a single station block in XTide harmonics format."""
    meta = result['station_meta']
    name = meta['name']
    lat = meta['lat']
    lon = meta['lon']
    uhslc_id = result['uhslc_id']
    island = ISLAND_NAMES.get(uhslc_id, '')

    location = f"{name}, {island}, Indonesia" if island else f"{name}, Indonesia"

    lines = []
    lines.append(f"# Harmonic constants derived from UHSLC hourly sea level data")
    lines.append(f"# using UTide (v{utide.__version__}) with {result['n_obs']} observations")
    lines.append(f"# from {result['start_time'].strftime('%Y-%m-%d')} to {result['end_time'].strftime('%Y-%m-%d')}")
    lines.append(f"# R^2 = {result['r_squared']:.4f}, RMS error = {result['rms_error']:.4f} m")
    lines.append(f"# Constituents analyzed: {result['n_analyzed']}")
    lines.append(f"#")
    lines.append(f"# {location}")
    lines.append(f"# BEGIN HOT COMMENTS")
    lines.append(f"# country: Indonesia")
    lines.append(f"# source: Derived from UHSLC hourly data with UTide harmonic analysis")
    lines.append(f"# station_id_context: UHSLC-{uhslc_id}")
    lines.append(f"# date_imported: {datetime.now().strftime('%Y%m%d')}")
    lines.append(f"# datum: station datum")
    lines.append(f"# confidence: 8")
    lines.append(f"# !units: meters")
    lines.append(f"# !longitude: {lon:.6f}")
    lines.append(f"# !latitude: {lat:.6f}")

    lines.append(f"{location}")
    lines.append(f"+00:00 :{meta.get('tz', 'UTC')}")
    lines.append(f"{result['mean']:.4f} meters")

    for c in result['constituents']:
        if c.get('not_analyzed') or c['amplitude'] < 0.00005:
            lines.append(f"x 0 0")
        else:
            lines.append(f"{c['name']:15s} {c['amplitude']:.4f}  {c['phase']:.2f}")

    return '\n'.join(lines)


def main():
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)

    header = read_header_from_template(TEMPLATE_PATH)

    print("=" * 70)
    print("UTide Harmonic Analysis -- Indonesia (UHSLC)")
    print("=" * 70)
    print(f"Eingabe:  {CSV_DIR}")
    print(f"Ausgabe:  {OUTPUT_PATH}")
    print(f"Stationen: {len(STATIONS)}")
    print(f"Letzte {USE_LAST_N_YEARS} Jahre")
    print()

    results = []
    for uhslc_id, meta in sorted(STATIONS.items()):
        csv_files = list(CSV_DIR.glob(f"{uhslc_id}_*.csv"))
        if not csv_files:
            print(f"[{uhslc_id}] {meta['name']}: KEINE CSV gefunden")
            continue

        csv_path = csv_files[0]
        print(f"[{uhslc_id}] {meta['name']}:")
        result = analyze_station(csv_path, meta, uhslc_id)
        if result:
            results.append(result)
        else:
            print(f"  UEBERSPRUNGEN")

        gc.collect()
        print()

    if not results:
        print("Keine Ergebnisse!")
        return

    blocks = [format_station_block(r) for r in results]
    output = header + '\n' + '\n'.join(blocks) + '\n'
    OUTPUT_PATH.write_text(output, encoding='iso-8859-1')

    print(f"{'='*70}")
    print(f"Ergebnis: {len(results)} Stationen -> {OUTPUT_PATH}")
    print()
    for r in results:
        m = r['station_meta']
        print(f"  {m['name']:20s}  R²={r['r_squared']:.4f}  "
              f"M2={r['m2_amp']:.4f}m  K1={r['k1_amp']:.4f}m  "
              f"RMS={r['rms_error']:.4f}m  {r['n_obs']} Beob.")


if __name__ == '__main__':
    main()
