#!/usr/bin/env python3
"""
UTide harmonic analysis for SEMAR Mexico tide-prediction PDFs.

Reads PDFs in ~/annual_predictions/mexico_semar/{slug}/{CODE}_{YY}.pdf,
parses HW/LW extremes (3 years per station: 2024-2026), cosine-interpolates
to 15-min, runs UTide with CONSTIT_67, writes
harmonics_utide_mexico_semar.txt for downstream merge into
harmonics_utide_tidetables.txt.

SEMAR PDFs declare their local meridian on every page footer
("HORA DEL MERIDIANO LOCAL NN° W"); the parser reads this and we convert
to UTC before passing data to UTide.
"""
import sys
import gc
import time
import pickle
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path

import utide

sys.path.insert(0, '/home/oliver/py')
from parse_semar_pdf import parse_pdf
from download_semar_mexico import STATIONS
from generate_germany_harmonics_175 import (
    CONSTITUENTS_175,
    find_xtide_match,
    read_header_from_template,
)

DATA_ROOT = Path('/home/oliver/annual_predictions/mexico_semar')
CHECKPOINT_DIR = Path('/home/oliver/harmonics/utide/checkpoints_semar_mx')
OUTPUT_PATH = Path('/home/oliver/harmonics/utide/harmonics_utide_mexico_semar.txt')
TEMPLATE_PATH = Path('/home/oliver/harmonics/utide/harmonics_utide_tidetables.txt')

R2_MIN = 0.50

CONSTIT_67 = [
    'K1', 'O1', 'P1', 'Q1', 'J1', 'OO1', '2Q1', 'RHO1',
    'NO1', 'CHI1', 'PI1', 'PHI1', 'PSI1', 'SIG1', 'THE1', 'SO1',
    'M2', 'S2', 'N2', 'K2', 'L2', '2N2', 'R2', 'T2',
    'LDA2', 'MU2', 'NU2', 'EPS2', 'ETA2',
    'MF', 'MSF', 'MM', 'SA', 'SSA', 'MSM',
    'M3', 'MK3', 'MO3', 'SK3', 'SO3',
    'M4', 'MN4', 'MS4', 'MK4', 'S4', 'SN4',
    'M6', '2MS6', '2MN6',
    'M8',
    'H1', 'H2', 'S1',
    'ALP1', 'BET1', 'TAU1', 'UPS1',
    '2SM2', 'OP2', 'MKS2', 'SKM2',
    'NO3',
    'N4', '3MS4',
    '2MK5', '2SK5',
    '2MK6', 'MSK6',
]


def cosine_interpolate(hw_lw_utc, target_interval_min=15):
    if len(hw_lw_utc) < 4:
        return None, None
    hw_lw_utc.sort(key=lambda x: x[0])
    t_start = hw_lw_utc[0][0]
    t_end = hw_lw_utc[-1][0]
    interval = timedelta(minutes=target_interval_min)
    times = []
    t = t_start
    while t <= t_end:
        times.append(t)
        t += interval
    if len(times) < 100:
        return None, None
    levels = np.zeros(len(times))
    hw_times = [e[0] for e in hw_lw_utc]
    hw_levels = [e[1] for e in hw_lw_utc]
    j = 0
    for i, t in enumerate(times):
        while j < len(hw_times) - 2 and hw_times[j + 1] <= t:
            j += 1
        if j >= len(hw_times) - 1:
            levels[i] = hw_levels[-1]
            continue
        t0 = hw_times[j]; t1 = hw_times[j + 1]
        h0 = hw_levels[j]; h1 = hw_levels[j + 1]
        dt_total = (t1 - t0).total_seconds()
        if dt_total <= 0:
            levels[i] = h0
            continue
        dt = (t - t0).total_seconds()
        frac = dt / dt_total
        w = (1 - np.cos(np.pi * frac)) / 2
        levels[i] = h0 * (1 - w) + h1 * w
    return np.array(times), levels


def analyze_station(station):
    slug = station['slug']
    name = station['name']
    ckpt = CHECKPOINT_DIR / f"{slug}.pkl"
    if ckpt.exists():
        return pickle.load(open(ckpt, 'rb'))

    pdfs = sorted((DATA_ROOT / slug).glob(f"{station['code']}_*.pdf"))
    if not pdfs:
        print(f"  {slug}: no PDFs")
        return None
    print(f"  {slug}: {len(pdfs)} PDFs", end=' ', flush=True)

    all_pts = []
    tz_offset_h = station['tz']
    for pdf in pdfs:
        try:
            r = parse_pdf(pdf)
            if r['tz_offset_h'] is not None:
                tz_offset_h = r['tz_offset_h']
            for dt_local, h in r['entries']:
                dt_utc = dt_local - timedelta(hours=tz_offset_h)
                all_pts.append((dt_utc, h))
        except Exception as e:
            print(f"\n    PDF parse fail {pdf.name}: {e}")
            continue

    if len(all_pts) < 200:
        print(f"only {len(all_pts)} pts → skip")
        return None

    all_pts.sort(key=lambda x: x[0])
    cleaned = [all_pts[0]]
    for p in all_pts[1:]:
        if p[0] > cleaned[-1][0]:
            cleaned.append(p)

    datetimes_utc, levels = cosine_interpolate(cleaned)
    if datetimes_utc is None:
        print("interp fail")
        return None

    t0 = time.time()
    try:
        coef = utide.solve(
            datetimes_utc, levels, lat=station['lat'],
            nodal=True, trend=False, method='ols',
            conf_int='none', verbose=False, constit=CONSTIT_67,
        )
    except Exception as e:
        print(f"UTide fail: {e}")
        return None

    from utide._ut_constants import ut_constants
    const_table = ut_constants['const']
    utide_all_names = [n.strip() for n in const_table.name]
    utide_results = {}
    for i, uname in enumerate(coef['name']):
        uname = uname.strip()
        amp = coef['A'][i]
        gph = coef['g'][i]
        if uname not in utide_all_names:
            continue
        idx = utide_all_names.index(uname)
        uspeed = const_table.freq[idx] * 360.0
        xt_name, xt_speed = find_xtide_match(uname, uspeed)
        if xt_name is None:
            continue
        utide_results[xt_name] = {'amplitude': amp, 'phase': gph % 360, 'speed': xt_speed}

    constituents = []
    n_analyzed = 0
    for cname, speed in CONSTITUENTS_175:
        if cname in utide_results:
            r = utide_results[cname]
            constituents.append({'name': cname, 'amplitude': r['amplitude'], 'phase': r['phase'], 'speed': speed})
            n_analyzed += 1
        else:
            constituents.append({'name': cname, 'amplitude': 0.0, 'phase': 0.0, 'speed': speed, 'not_analyzed': True})

    recon = utide.reconstruct(datetimes_utc, coef, verbose=False)
    residuals = levels - recon['h']
    ss_res = np.sum(residuals**2)
    ss_tot = np.sum((levels - np.mean(levels))**2)
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0
    rms = np.sqrt(np.mean(residuals**2))
    m2 = next((c['amplitude'] for c in constituents if c['name'] == 'M2'), 0)

    result = {
        'slug': slug,
        'name': name,
        'state': station['state'],
        'lat': station['lat'],
        'lon': station['lon'],
        'mean': float(coef['mean']),
        'constituents': constituents,
        'n_analyzed': n_analyzed,
        'r_squared': r2,
        'rms_error': rms,
        'm2_amp': m2,
        'n_obs': len(datetimes_utc),
        'n_hwlw': len(cleaned),
        'start_time': datetimes_utc[0],
        'end_time': datetimes_utc[-1],
        'tz_offset_h': tz_offset_h,
    }
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    pickle.dump(result, open(ckpt, 'wb'))
    del coef, recon, datetimes_utc, levels, residuals
    gc.collect()
    print(f"R²={r2:.4f} RMS={rms:.3f}m M2={m2:.3f}m {len(cleaned)}pts ({time.time()-t0:.0f}s)")
    return result


def format_station_block(result):
    name = result['name']
    state = result['state']
    full_name = f"{name}, {state}, Mexico"
    L = []
    L.append("# Harmonic constants derived from SEMAR Mexico tide predictions")
    L.append(f"# using UTide (v{utide.__version__}) with cosine-interpolated HW/LW data")
    L.append(f"# {result['n_hwlw']} HW/LW points -> {result['n_obs']} interpolated points")
    L.append(f"# from {result['start_time'].strftime('%Y-%m-%d')} to {result['end_time'].strftime('%Y-%m-%d')}")
    L.append(f"# R^2 = {result['r_squared']:.4f}, RMS error = {result['rms_error']:.4f} m")
    L.append(f"# Constituents analyzed: {result['n_analyzed']}")
    L.append("#")
    L.append(f"# {full_name}")
    L.append("# BEGIN HOT COMMENTS")
    L.append("# country: Mexico")
    L.append(f"# state: {state}")
    L.append("# source: SEMAR Mexico tide tables × UTide")
    L.append(f"# station_id_context: SEMAR-{result['slug']}")
    L.append(f"# date_imported: {datetime.now().strftime('%Y%m%d')}")
    L.append("# datum: NBM (Nivel de Bajamar Media, SEMAR Chart Datum)")
    L.append("# confidence: 7")
    L.append("# !units: meters")
    L.append(f"# !longitude: {result['lon']:.4f}")
    L.append(f"# !latitude: {result['lat']:.4f}")
    L.append(full_name)
    L.append("+00:00 :UTC")
    L.append(f"{result['mean']:.4f} meters")
    for c in result['constituents']:
        if c.get('not_analyzed') or c['amplitude'] < 0.00005:
            L.append("x 0 0")
        else:
            L.append(f"{c['name']:15s} {c['amplitude']:.4f}  {c['phase']:.2f}")
    return '\n'.join(L)


def main():
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"SEMAR Mexico UTide pipeline — {len(STATIONS)} stations")
    results = []
    rejected = []
    for i, s in enumerate(STATIONS):
        print(f"[{i+1}/{len(STATIONS)}] {s['name']} ({s['slug']}):", end=' ')
        r = analyze_station(s)
        if r is None:
            continue
        if r['r_squared'] < R2_MIN:
            rejected.append((f"{r['name']}, {r['state']}, Mexico", r['r_squared']))
            continue
        results.append(r)
        if (i + 1) % 5 == 0:
            gc.collect()

    if not results:
        print("Nothing produced.")
        return

    header = read_header_from_template(TEMPLATE_PATH)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, 'w', encoding='iso-8859-1') as f:
        f.write(header)
        f.write('\n')
        for r in results:
            f.write(format_station_block(r))
            f.write('\n')
    print(f"\nWrote {OUTPUT_PATH} ({OUTPUT_PATH.stat().st_size / 1024:.0f} KB, {len(results)} stations)")

    if rejected:
        print(f"\nRejected (R²<{R2_MIN}):")
        for n, r in rejected:
            print(f"  {n}: {r:.3f}")


if __name__ == '__main__':
    main()
