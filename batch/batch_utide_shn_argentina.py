#!/usr/bin/env python3
"""
UTide harmonic analysis for SHN Argentina stations.

Loads cached HW/LW data + metadata from annual_predictions/argentina/shn/parsed/,
cosine-interpolates to 15-min, runs UTide with CONSTIT_67, writes harmonics_utide_argentina.txt.
"""
import sys
sys.path.insert(0, '/home/oliver/py')

import os
import json
import re
import gc
import time
import pickle
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path

import utide
from generate_germany_harmonics_175 import (
    CONSTITUENTS_175,
    find_xtide_match,
    read_header_from_template,
)

PARSED_DIR = Path("/home/oliver/annual_predictions/argentina/shn/parsed")
CHECKPOINT_DIR = Path("/home/oliver/harmonics/utide/checkpoints_shn_ar")
OUTPUT_PATH = Path("/home/oliver/harmonics/utide/harmonics_utide_argentina.txt")
TEMPLATE_PATH = Path("/home/oliver/harmonics/utide/harmonics_utide_tidetables.txt")

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

# Station display-name corrections: map SHN code → canonical XTide-style name.
# SHN names use ALL-CAPS and abbreviations; we want Title Case + Spanish accents.
NAME_OVERRIDES = {
    'ATAL': 'Atalaya',
    'AGUI': 'Bahía Aguirre',
    'SUCE': 'Bahía Buen Suceso',
    'CROS': 'Bahía Crossley (Isla de los Estados)',
    'SANB': 'Bahía San Blas',
    'SSEB': 'Bahía San Sebastián',
    'THET': 'Bahía Thetis',
    'USHU': 'Ushuaia',
    'CBRE': 'Caleta Brent (Isla de los Estados)',
    'LAMI': 'Caleta La Misión',
    'CPAU': 'Caleta Paula',
    'SPAB': 'Caleta San Pablo',
    'BBLA': 'Canal Principal a Bahía Blanca (Par 12 a 16)',
    'PIND': 'Canal Punta Indio (Km 201.6)',
    'OYAR': 'Canal Punta Indio (Oyarvide - Km 133)',
    'PCOL': 'Cargadero de Punta Colorada',
    'EMAG': 'Estrecho de Magallanes (Boca Oriental)',
    'SROM': 'Fondeadero San Román (Golfo San José)',
    'MAGA': 'Isla Martín García',
    'ANUE': 'Islas de Año Nuevo (Isla Observatorio)',
    'MAJO': 'Mar de Ajó',
    'MHER': 'Monte Hermoso',
    'TURB': 'Muelle El Turbio (Puerto Río Gallegos)',
    'NORD': 'Pilote Norden',
    'PINA': 'Pinamar',
    'PARG': 'Puerto Argentino (Isla Soledad, Islas Malvinas)',
    'BELG': 'Puerto Belgrano',
    'COMO': 'Puerto Comodoro Rivadavia',
    'BSAS': 'Puerto de Buenos Aires (Muelle de Pescadores)',
    'PDES': 'Puerto Deseado',
    'IWHI': 'Puerto Ingeniero White',
    'LPLA': 'Puerto La Plata',
    'MADR': 'Puerto Madryn',
    'MARD': 'Puerto Mar del Plata',
    'QUEQ': 'Puerto Quequén',
    'RAWS': 'Puerto Rawson',
    'RIOG': 'Puerto Río Grande (Exterior)',
    'ROSA': 'Puerto Rosales',
    'SANT': 'Puerto San Antonio (Muelle de Ultramar)',
    'SJUA': 'Puerto San Juan del Salvamento (Isla de los Estados)',
    'SJUL': 'Puerto San Julián (Punta Peña)',
    'SELE': 'Puerto Santa Elena',
    'VANC': 'Puerto Vancouver (Isla de los Estados)',
    'LOYO': 'Punta Loyola (Muelle Presidente Illia)',
    'QUIL': 'Punta Quilla (Puerto Santa Cruz)',
    'RION': 'Río Negro (Punta Redonda)',
    'SCLE': 'San Clemente del Tuyú (Muelle)',
    'SANF': 'San Fernando',
    'STER': 'Santa Teresita',
    # Antarctic
    'SCOT': 'Bahía Scotia (Isla Laurie, Islas Orcadas del Sur)',
    'BROW': 'Base Brown (Bahía Paraíso)',
    'CAMA': 'Base Cámara (Caleta Menguante, Isla Media Luna)',
    'JUBA': 'Base Carlini (Caleta Potter, Isla 25 de Mayo)',
    'ESPE': 'Base Esperanza (Bahía Esperanza)',
    'BMAR': 'Base Marambio (Isla Marambio)',
    'MATZ': 'Base Matienzo (Nunatak Larsen)',
    'MELC': 'Base Melchior (Archipiélago Melchior)',
    'PRIM': 'Base Primavera (Caleta Cierva)',
    'CALD': 'Golfo Caldera (Islas Sandwich del Sur)',
    'ARTU': 'Puerto Arthur (Isla Amberes)',
    'CHAR': 'Puerto Charcot (Isla Booth)',
    'FOST': 'Puerto Foster (Isla Decepción)',
    'LOCK': 'Puerto Lockroy (Isla Wiencke)',
    'MIKK': 'Puerto Mikkelsen (Isla Trinidad)',
    'NEKO': 'Puerto Neko (Bahía Andvord)',
    'NENY': 'Puerto Sidders (Bahía Margarita)',
    'BALL': 'Refugio Ballvé (Caleta Ardley, Isla 25 de Mayo)',
    'GROU': 'Refugio Groussac (Isla Petermann)',
    'GURR': 'Refugio Gurruchaga (Caleta Armonía, Isla Nelson)',
}

# Stations that already exist in harmonics with good coverage — skip to keep originals.
# Set to None to NOT skip and let SHN replace them (after explicit user confirmation).
EXISTING_AR_STATIONS = {
    'Buenos Aires (Club de Pescadores), Argentina',
    'Dallmann, Argentina',
    'Esperanza (Hope Bay, Antarctica), Argentina',
    'Mar del Plata, Argentina',
    'Puerto Deseado, Argentina',
    'Puerto Madryn, Argentina',
    'Ushuaia, Argentina',
}


def local_to_utc(dt_local, tz_offset_h):
    """Convert Argentine local time (UTC-3) to UTC."""
    return dt_local - timedelta(hours=tz_offset_h)  # tz_offset_h is negative


def cosine_interpolate(hw_lw_utc, target_interval_min=15):
    """Cosine interpolation between consecutive HW/LW extremes."""
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


def analyze_station(code, name, lat, lon, tz_offset_h, entries_local):
    """Run UTide on one station."""
    ckpt = CHECKPOINT_DIR / f"{code}.pkl"
    if ckpt.exists():
        with open(ckpt, 'rb') as f:
            r = pickle.load(f)
        print(f"  ✓ Checkpoint (R²={r['r_squared']:.4f})")
        return r

    t0 = time.time()

    # Convert local → UTC, dedupe
    pts = [(local_to_utc(dt, tz_offset_h), h) for dt, h in entries_local]
    pts.sort(key=lambda x: x[0])
    cleaned = [pts[0]]
    for p in pts[1:]:
        if p[0] > cleaned[-1][0]:
            cleaned.append(p)
    pts = cleaned

    if len(pts) < 100:
        print(f"  ✗ {len(pts)} pts < 100, skip")
        return None

    # Detect cadence: hourly (op=2) vs HW/LW (op=1).
    # Hourly data has median spacing ~3600s; HW/LW has ~22000s.
    deltas = [(pts[i+1][0] - pts[i][0]).total_seconds() for i in range(min(100, len(pts) - 1))]
    median_dt = sorted(deltas)[len(deltas) // 2] if deltas else 3600
    is_hourly = median_dt < 1.5 * 3600  # within 1.5x hourly threshold

    if is_hourly:
        # Hourly already — feed directly to UTide
        datetimes_utc = np.array([t for t, _ in pts])
        levels = np.array([h for _, h in pts])
        n = len(datetimes_utc)
        yrs = n / (24 * 365.25)
        print(f"  {len(pts)} hourly pts → direct ({yrs:.2f}y)", end=' ', flush=True)
    else:
        datetimes_utc, levels = cosine_interpolate(pts)
        if datetimes_utc is None:
            print(f"  ✗ Interpolation failed")
            return None
        n = len(datetimes_utc)
        yrs = n / (4 * 24 * 365.25)
        print(f"  {len(pts)} HW/LW → {n} pts ({yrs:.2f}y)", end=' ', flush=True)

    try:
        coef = utide.solve(
            datetimes_utc, levels, lat=lat,
            nodal=True, trend=False, method='ols',
            conf_int='none', verbose=False, constit=CONSTIT_67,
        )
    except Exception as e:
        print(f" FEHLER: {e}")
        return None

    # Map to XTide 175 set
    from utide._ut_constants import ut_constants
    const_table = ut_constants['const']
    utide_all_names = [n.strip() for n in const_table.name]
    utide_results = {}
    for i, uname in enumerate(coef['name']):
        uname = uname.strip()
        amp = coef['A'][i]
        gph = coef['g'][i]
        if uname in utide_all_names:
            idx = utide_all_names.index(uname)
            uspeed = const_table.freq[idx] * 360.0
        else:
            continue
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

    duration = time.time() - t0

    result = {
        'code': code, 'name': name, 'lat': lat, 'lon': lon,
        'mean': float(coef['mean']),
        'constituents': constituents,
        'n_analyzed': n_analyzed,
        'r_squared': r2, 'rms_error': rms,
        'm2_amp': m2, 'n_obs': n,
        'n_hwlw': len(pts),
        'is_hourly': is_hourly,
        'start_time': datetimes_utc[0],
        'end_time': datetimes_utc[-1],
        'duration': duration,
    }

    with open(ckpt, 'wb') as f:
        pickle.dump(result, f)

    del coef, recon, datetimes_utc, levels, residuals
    gc.collect()

    print(f"R²={r2:.4f} RMS={rms:.3f}m M2={m2:.3f}m ({duration:.0f}s)")
    return result


def format_station_block(result):
    name = NAME_OVERRIDES.get(result['code'], result['name'].title())
    if not name.endswith(', Argentina'):
        full_name = f"{name}, Argentina"
    else:
        full_name = name
    lat = result['lat']
    lon = result['lon']

    L = []
    src_desc = "hourly tide predictions" if result.get('is_hourly') else "cosine-interpolated HW/LW data"
    L.append(f"# Harmonic constants derived from SHN Argentina tide predictions")
    L.append(f"# using UTide (v{utide.__version__}) with {src_desc}")
    if result.get('is_hourly'):
        L.append(f"# {result['n_hwlw']} hourly points")
    else:
        L.append(f"# {result['n_hwlw']} HW/LW points -> {result['n_obs']} interpolated points")
    L.append(f"# from {result['start_time'].strftime('%Y-%m-%d')} to {result['end_time'].strftime('%Y-%m-%d')}")
    L.append(f"# R^2 = {result['r_squared']:.4f}, RMS error = {result['rms_error']:.4f} m")
    L.append(f"# Constituents analyzed: {result['n_analyzed']}")
    L.append(f"#")
    L.append(f"# {full_name}")
    L.append(f"# BEGIN HOT COMMENTS")
    L.append(f"# country: Argentina")
    L.append(f"# source: Derived from SHN Argentina (Servicio de Hidrografía Naval) tide tables with UTide harmonic analysis")
    L.append(f"# station_id_context: SHN-{result['code']}")
    L.append(f"# date_imported: {datetime.now().strftime('%Y%m%d')}")
    L.append(f"# datum: Chart Datum")
    L.append(f"# confidence: 7")
    L.append(f"# shn_code: {result['code']}")
    L.append(f"# utide: pts={result['n_obs']} period={result['start_time'].strftime('%Y-%m-%d')}..{result['end_time'].strftime('%Y-%m-%d')} r2={result['r_squared']:.4f} rms={result['rms_error']:.4f}m const={result['n_analyzed']}")
    L.append(f"# !units: meters")
    L.append(f"# !longitude: {lon:.4f}")
    L.append(f"# !latitude: {lat:.4f}")
    L.append(full_name)
    L.append(f"+00:00 :UTC")
    L.append(f"{result['mean']:.4f} meters")
    for c in result['constituents']:
        if c.get('not_analyzed') or c['amplitude'] < 0.00005:
            L.append("x 0 0")
        else:
            L.append(f"{c['name']:15s} {c['amplitude']:.4f}  {c['phase']:.2f}")
    return '\n'.join(L)


def main():
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)

    files = sorted(PARSED_DIR.glob("*.json"))
    print(f"SHN Argentina UTide pipeline — {len(files)} station files")

    results = []
    skipped_existing = []
    errors = []

    for i, fp in enumerate(files):
        with open(fp, encoding='utf-8') as f:
            rec = json.load(f)
        code = rec['code']
        sname = rec['name']
        meta = rec['meta']
        lat = meta.get('lat')
        lon = meta.get('lon')
        tz = meta.get('tz_offset_h', -3)
        if lat is None or lon is None:
            print(f"[{i+1}/{len(files)}] {code} {sname}: no coords, skip")
            errors.append((code, 'no coords'))
            continue

        canonical = NAME_OVERRIDES.get(code, sname.title())
        full_name = canonical if canonical.endswith(', Argentina') else f"{canonical}, Argentina"
        if full_name in EXISTING_AR_STATIONS:
            print(f"[{i+1}/{len(files)}] {code} {full_name}: already exists, SKIP")
            skipped_existing.append(full_name)
            continue

        entries = [(datetime.fromisoformat(t), h) for t, h in rec['entries']]
        print(f"[{i+1}/{len(files)}] {code} {full_name} (lat={lat:.3f}, lon={lon:.3f})")
        r = analyze_station(code, sname, lat, lon, tz, entries)
        if r is not None:
            results.append(r)
        else:
            errors.append((code, 'analysis failed'))

        if (i + 1) % 10 == 0:
            gc.collect()

    print(f"\n{'='*70}")
    print(f"Stationen analysiert: {len(results)}")
    print(f"Skipped (already exist): {len(skipped_existing)}")
    print(f"Errors: {len(errors)}")
    print(f"{'='*70}\n")

    if not results:
        print("Keine Ergebnisse — Abbruch.")
        return

    # Write standalone harmonics file
    header = read_header_from_template(TEMPLATE_PATH)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, 'w', encoding='iso-8859-1') as f:
        f.write(header)
        f.write('\n')
        for r in results:
            f.write(format_station_block(r))
            f.write('\n')
    print(f"Wrote {OUTPUT_PATH} ({OUTPUT_PATH.stat().st_size / 1024:.0f} KB, {len(results)} stations)")

    # R² distribution
    r2s = sorted([r['r_squared'] for r in results], reverse=True)
    print(f"\nR² Quartiles: max={r2s[0]:.4f} Q3={r2s[len(r2s)//4]:.4f} median={r2s[len(r2s)//2]:.4f} Q1={r2s[3*len(r2s)//4]:.4f} min={r2s[-1]:.4f}")
    low = [(r['code'], r['name'], r['r_squared']) for r in results if r['r_squared'] < 0.90]
    if low:
        print(f"\n{len(low)} stations with R² < 0.90:")
        for c, n, r2 in low:
            print(f"  {c} {n}: R²={r2:.4f}")


if __name__ == "__main__":
    main()
