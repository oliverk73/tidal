#!/usr/bin/env python3
"""
UTide-Fit für cabaigne.net Sfax HW/LW-Daten.

Pipeline:
  1. HTM-Files parsen (Tunisia local time, UTC+1, kein DST)
  2. → UTC umrechnen
  3. Cosinus-Interpolation auf 15-min Raster
  4. UTide solve (CONSTIT_67)
  5. Map auf XTide-Namen, R²/RMS berechnen
  6. Block schreiben + Prediction-Sample für TCD-Vergleich exportieren
"""
from __future__ import annotations
import sys, numpy as np, pickle
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, '/home/oliver/py')
sys.path.insert(0, '/home/oliver/batch')

import utide
from parse_cabaigne_tunisia import parse_station
from generate_germany_harmonics_175 import CONSTITUENTS_175, find_xtide_match
from batch_utide_bom_australia import CONSTIT_67, cosine_interpolate  # type: ignore


# Tunisia: UTC+1 year-round, no DST
TZ_OFFSET = timedelta(hours=1)

STATION = {
    'name': 'Sfax',
    'country': 'Tunisia',
    'lat': 34.7276,
    'lon': 10.7742,
}


def local_to_utc(dt_local: datetime) -> datetime:
    return dt_local - TZ_OFFSET


def main():
    out_dir = Path('/tmp/cabaigne_sfax')
    out_dir.mkdir(exist_ok=True)
    in_dir = Path('/home/oliver/annual_predictions/Tunisia')

    print(f"Parsing Sfax HTM files...")
    events = parse_station(in_dir, 'Sfax')
    print(f"\nTotal: {len(events)} HW/LW events")

    # Convert to UTC
    entries_utc = [(local_to_utc(dt), h) for dt, h, _ in events]
    entries_utc.sort(key=lambda x: x[0])
    # Deduplicate monotonic
    cleaned = [entries_utc[0]]
    for e in entries_utc[1:]:
        if e[0] > cleaned[-1][0]:
            cleaned.append(e)
    entries_utc = cleaned
    print(f"After dedup: {len(entries_utc)} events")
    print(f"From {entries_utc[0][0]} to {entries_utc[-1][0]} (UTC)")

    # Cosine interpolation to 15-min grid
    datetimes_utc, levels = cosine_interpolate(entries_utc, target_interval_min=15)
    print(f"Interpolated: {len(datetimes_utc)} 15-min points")

    # UTide fit
    print(f"Running UTide (lat={STATION['lat']:.4f})...")
    coef = utide.solve(
        datetimes_utc, levels, lat=STATION['lat'],
        nodal=True, trend=False, method='ols',
        conf_int='none', verbose=False, constit=CONSTIT_67,
    )

    recon = utide.reconstruct(datetimes_utc, coef, verbose=False)
    residuals = levels - recon['h']
    ss_res = np.sum(residuals**2)
    ss_tot = np.sum((levels - np.mean(levels))**2)
    r2 = 1 - ss_res/ss_tot if ss_tot > 0 else 0
    rms = np.sqrt(np.mean(residuals**2))
    print(f"R²={r2:.4f}  RMS={rms:.4f} m  mean={float(coef['mean']):.4f} m")

    # Map to XTide 175 constituents
    from utide._ut_constants import ut_constants
    const_table = ut_constants['const']
    utide_names = [n.strip() for n in const_table.name]

    utide_results = {}
    for i, uname in enumerate(coef['name']):
        uname = uname.strip()
        A = coef['A'][i]; g = coef['g'][i]
        if uname not in utide_names:
            continue
        idx = utide_names.index(uname)
        speed = const_table.freq[idx] * 360.0
        xt_name, xt_speed = find_xtide_match(uname, speed)
        if xt_name is None:
            continue
        utide_results[xt_name] = {'amplitude': A, 'phase': g % 360, 'speed': xt_speed}

    # Print key constituents
    print("\nKey constituents (UTide cabaigne fit):")
    for c in ['M2','S2','N2','K2','K1','O1','P1','Q1','M4','MS4']:
        if c in utide_results:
            r = utide_results[c]
            print(f"  {c:6s}  A={r['amplitude']:.4f} m  g={r['phase']:7.2f}°")
        else:
            print(f"  {c:6s}  --")

    # Save result for downstream comparison
    out = {
        'station': STATION,
        'mean': float(coef['mean']),
        'r_squared': float(r2),
        'rms': float(rms),
        'n_hwlw': len(entries_utc),
        'n_points': len(datetimes_utc),
        'start_utc': entries_utc[0][0],
        'end_utc': entries_utc[-1][0],
        'utide_results': utide_results,
        'coef': coef,
    }
    with open(out_dir / 'sfax_fit.pkl', 'wb') as f:
        pickle.dump(out, f)
    print(f"\nSaved → {out_dir/'sfax_fit.pkl'}")


if __name__ == '__main__':
    main()
