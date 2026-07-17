#!/usr/bin/env python3
"""
UTide harmonic analysis for SHOA Chile tide predictions.

Parses SHOA tide-prediction HTML files from annual_predictions/chile/,
cosine-interpolates HW/LW extremes to 15-min, runs UTide with CONSTIT_67,
appends results to harmonics_utide_tidetables.txt.

SHOA times are always in UTC-4 for mainland Chile + Magallanes + Antártica
(SHOA does not apply DST in its tide tables — confirmed in HTML header text).
"""
import sys
sys.path.insert(0, '/home/oliver/py')

import gc
import re
import time
import pickle
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path

import utide
from bs4 import BeautifulSoup

from generate_germany_harmonics_175 import (
    CONSTITUENTS_175,
    find_xtide_match,
    read_header_from_template,
)

SHOA_DIR = Path("/home/oliver/weather/tide_tables/chile")
CHECKPOINT_DIR = Path("/home/oliver/harmonics/utide/checkpoints_shoa_cl")
OUTPUT_PATH = Path("/home/oliver/harmonics/utide/harmonics_utide_chile_shoa.txt")
TEMPLATE_PATH = Path("/home/oliver/harmonics/utide/harmonics_utide_tidetables.txt")

TZ_OFFSET_H = -4  # SHOA mainland Chile always UTC-4 (no DST in tide tables)

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

# Station catalog: code → (display name, lat, lon).
# We start with Constitución; the same pipeline can be extended to other SHOA
# stations as more month-HTMLs are saved into SHOA_DIR.
STATIONS = {
    'constitucion': {
        'name': 'Constitución',
        'lat': -35.35573,   # SHOA reference (35°19'52" S)
        'lon': -72.45703,   # SHOA reference (72°24'30" W)
    },
    'puerto_natales': {
        'name': 'Puerto Natales',
        'lat': -51.72913,   # SHOA Magallanes (~51°43.8' S)
        'lon': -72.51567,   # ~72°30.6' W
    },
    'mejillones_del_sur': {
        'name': 'Mejillones del Sur',
        'lat': -23.09771,   # Bahía Mejillones del Sur, Antofagasta
        'lon': -70.45066,
        'tz': 'America/Santiago',
    },
    'quintero': {
        'name': 'Quintero',
        'lat': -32.77549,   # Bahía de Quintero, Valparaíso
        'lon': -71.52543,
        'tz': 'America/Santiago',
    },
    'bahia_cumberland_isla_robinson_crusoe': {
        'name': 'Bahía Cumberland (Isla Robinson Crusoe)',
        'lat': -33.63602,   # Juan Fernández, San Juan Bautista
        'lon': -78.82988,
        'tz': 'America/Santiago',
    },
    'valdivia_rio_calle_calle': {
        'name': 'Valdivia (Río Calle-Calle)',
        'lat': -39.81467,   # Río Calle-Calle, Los Ríos
        'lon': -73.24895,
        'tz': 'America/Santiago',
    },
    'corral': {
        'name': 'Corral',
        'lat': -39.886595,  # IOC corr
        'lon': -73.42748,
        'tz': 'America/Santiago',
    },
    'chacao': {
        'name': 'Puerto Chacao',
        'lat': -41.828840,  # Oliver-Vorgabe (kein IOC-Pegel in Chacao)
        'lon': -73.515259,
        'tz': 'America/Santiago',
    },
    'inglesa': {
        'name': 'Angostura Inglesa, Canal Messier',
        'lat': -48.980571,  # Oliver-Vorgabe (kein IOC-Pegel), Región Aysén
        'lon': -74.421297,
        'tz': 'America/Santiago',
    },
    'delgada': {
        'name': 'Punta Delgada, Estrecho de Magallanes',
        'lat': -52.456936,  # Oliver-Vorgabe (kein IOC-Pegel), Primera Angostura
        'lon': -69.545627,
        'tz': 'America/Punta_Arenas',  # Magallanes UTC-3
    },
    'meteoro': {
        'name': 'Caleta Meteoro, Estrecho de Magallanes',
        'lat': -52.9666,   # IOC cmet
        'lon': -74.0667,
        'tz': 'America/Punta_Arenas',
    },
    'percy': {
        'name': 'Caleta Percy, Bahía Gente Grande',
        'lat': -52.9,      # IOC
        'lon': -70.266667,
        'tz': 'America/Punta_Arenas',
    },
}


def parse_shoa_html(path):
    """Extract (datetime_local, height, kind) from one SHOA HTML.

    kind = 'P' (Pleamar/high) or 'B' (Bajamar/low). Returns list sorted by time.
    """
    with open(path, 'rb') as fp:
        html = fp.read().decode('utf-8')
    soup = BeautifulSoup(html, 'html.parser')
    entries = []
    for table in soup.find_all('table'):
        for row in table.find_all('tr'):
            cells = [c.get_text(strip=True) for c in row.find_all(['td', 'th'])]
            if not cells or len(cells) < 3:
                continue
            # Date column is dd/mm/yyyy
            m = re.match(r'^(\d{2})/(\d{2})/(\d{4})$', cells[0])
            if not m:
                continue
            dd, mm, yyyy = int(m.group(1)), int(m.group(2)), int(m.group(3))
            # Remaining columns are pairs: HH:MM, "h.hh K" where K in {P, B}
            for i in range(1, len(cells) - 1, 2):
                t_str = cells[i]
                v_str = cells[i + 1]
                if not t_str or not v_str:
                    continue
                tm = re.match(r'^(\d{2}):(\d{2})$', t_str)
                vm = re.match(r'^(-?\d+(?:\.\d+)?)\s*([PB])$', v_str)
                if not (tm and vm):
                    continue
                hh, mn = int(tm.group(1)), int(tm.group(2))
                height = float(vm.group(1))
                kind = vm.group(2)
                dt = datetime(yyyy, mm, dd, hh, mn)
                entries.append((dt, height, kind))
    entries.sort(key=lambda e: e[0])
    return entries


def local_to_utc(dt_local):
    """SHOA local (UTC-4) → UTC. tz_offset_h is negative for west of GMT."""
    return dt_local - timedelta(hours=TZ_OFFSET_H)


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


def analyze_station(code, name, lat, lon, entries_local):
    """Run UTide on cosine-interpolated SHOA HW/LW data."""
    ckpt = CHECKPOINT_DIR / f"{code}.pkl"
    if ckpt.exists():
        with open(ckpt, 'rb') as f:
            r = pickle.load(f)
        print(f"  ✓ Checkpoint (R²={r['r_squared']:.4f})")
        return r

    t0 = time.time()

    pts = [(local_to_utc(dt), h) for dt, h, _ in entries_local]
    pts.sort(key=lambda x: x[0])
    cleaned = [pts[0]]
    for p in pts[1:]:
        if p[0] > cleaned[-1][0]:
            cleaned.append(p)
    pts = cleaned

    if len(pts) < 100:
        print(f"  ✗ {len(pts)} pts < 100, skip")
        return None

    datetimes_utc, levels = cosine_interpolate(pts)
    if datetimes_utc is None:
        print(f"  ✗ Interpolation failed")
        return None
    n = len(datetimes_utc)
    yrs = n / (4 * 24 * 365.25)
    print(f"  {len(pts)} HW/LW → {n} pts ({yrs:.2f}y)", end=' ', flush=True)

    try:
        # constit='auto' (Rayleigh-Kriterium): NICHT die feste CONSTIT_67-Liste
        # erzwingen. Über kurze Records (~90 Tage SHOA-Kalender) sind eng
        # benachbarte Diurnal-Linien (S1/K1/P1/PSI1/PI1/PHI1) nicht trennbar;
        # erzwungen liefert OLS sich aufhebende Riesen-Amplituden, die im
        # Fit-Fenster passen, aber außerhalb katastrophal divergieren.
        coef = utide.solve(
            datetimes_utc, levels, lat=lat,
            nodal=True, trend=False, method='ols',
            conf_int='none', verbose=False, constit='auto',
        )
    except Exception as e:
        print(f" FEHLER: {e}")
        return None

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
        'start_time': datetimes_utc[0],
        'end_time': datetimes_utc[-1],
        'duration': duration,
    }

    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    with open(ckpt, 'wb') as f:
        pickle.dump(result, f)

    del coef, recon, datetimes_utc, levels, residuals
    gc.collect()

    print(f"R²={r2:.4f} RMS={rms:.3f}m M2={m2:.3f}m ({duration:.0f}s)")
    return result


def format_station_block(result):
    name = result['name']
    full_name = f"{name}, Chile"
    L = []
    L.append("# Harmonic constants derived from SHOA Chile tide predictions")
    L.append(f"# using UTide (v{utide.__version__}) with cosine-interpolated HW/LW data")
    L.append(f"# {result['n_hwlw']} HW/LW points -> {result['n_obs']} interpolated points")
    L.append(f"# from {result['start_time'].strftime('%Y-%m-%d')} to {result['end_time'].strftime('%Y-%m-%d')}")
    L.append(f"# R^2 = {result['r_squared']:.4f}, RMS error = {result['rms_error']:.4f} m")
    L.append(f"# Constituents analyzed: {result['n_analyzed']}")
    L.append("#")
    L.append(f"# {full_name}")
    L.append("# BEGIN HOT COMMENTS")
    L.append("# country: Chile")
    L.append("# source: SHOA Chile tide tables × UTide")
    L.append(f"# station_id_context: SHOA-{result['code']}")
    L.append(f"# date_imported: {datetime.now().strftime('%Y%m%d')}")
    L.append("# datum: Plano de Reducción (Chart Datum SHOA)")
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

    results = []
    for code, meta in STATIONS.items():
        # Find all matching HTML files (case-insensitive on station code)
        pattern = f"*_{code}_*.htm"
        files = sorted(SHOA_DIR.glob(pattern))
        # Also try Title-Case (SHOA filename mixes cases)
        files += sorted(SHOA_DIR.glob(f"*_{code.capitalize()}_*.htm"))
        # Dedupe preserving order
        seen = set()
        files = [f for f in files if not (f in seen or seen.add(f))]
        if not files:
            print(f"{code}: NO HTML files found in {SHOA_DIR}")
            continue
        print(f"\n{code} ({meta['name']}): {len(files)} HTML files")
        for fp in files:
            print(f"  {fp.name}")

        all_entries = []
        for fp in files:
            entries = parse_shoa_html(fp)
            print(f"    {fp.name}: {len(entries)} HW/LW")
            all_entries.extend(entries)

        # Sort + dedupe by timestamp
        all_entries.sort(key=lambda e: e[0])
        deduped = []
        seen_times = set()
        for e in all_entries:
            if e[0] not in seen_times:
                deduped.append(e)
                seen_times.add(e[0])

        print(f"  Total: {len(deduped)} HW/LW after dedup")

        r = analyze_station(code, meta['name'], meta['lat'], meta['lon'], deduped)
        if r:
            results.append(r)

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
    for r in results:
        print(f"  {r['name']}: R²={r['r_squared']:.4f}, M2={r['m2_amp']:.3f} m, {r['n_hwlw']} pts")


if __name__ == '__main__':
    main()
