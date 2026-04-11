#!/usr/bin/env python3
"""
UTide harmonic analysis for Bay of Fundy / Minas Basin / Cobequid Bay stations.
Uses HW/LW predictions from tides.gc.ca (CHS).
Cosine-interpolates HW/LW to 15-min time series, then runs UTide.

Times are in AST/ADT (America/Moncton or America/Halifax).
We convert to UTC before analysis.
"""
import sys
sys.path.insert(0, '/home/oliver/py')

import json
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import time as timer
import pickle
import gc
import utide

from generate_germany_harmonics_175 import (
    CONSTITUENTS_175,
    find_xtide_match,
    read_header_from_template,
)

DATA_DIRS = [
    Path("/home/oliver/water_levels/CHS_NB"),
    Path("/home/oliver/water_levels/CHS_NS"),
]
TEMPLATE_PATH = Path("/home/oliver/harmonics/classic/harmonics-dwf-20070318_mod.txt")
OUTPUT_PATH = Path("/home/oliver/harmonics/utide/harmonics_utide_canada_fundy.txt")
CHECKPOINT_DIR = Path("/home/oliver/harmonics/utide/checkpoints_canada_fundy")

# Bore stations — only tidal bore arrival times, not real water levels
BORE_STATIONS = {'moncton', 'maccan', 'river_hebert', 'truro', 'maitland'}

# Station ID → province mapping
# NB stations: 00150-00225
# NS stations: 00235-00312
PROVINCE_MAP = {
    '00150': ('New Brunswick', 'America/Moncton'),   # Cape Enrage
    '00160': ('New Brunswick', 'America/Moncton'),   # Grindstone Island
    '00170': ('New Brunswick', 'America/Moncton'),   # Hopewell Cape
    '00172': ('New Brunswick', 'America/Moncton'),   # Belliveau Village
    '00173': ('New Brunswick', 'America/Moncton'),   # Dover (Memramcook)
    '00190': ('New Brunswick', 'America/Moncton'),   # Pecks Point
    '00215': ('Nova Scotia', 'America/Halifax'),      # Joggins (NS side of bay)
    '00225': ('Nova Scotia', 'America/Halifax'),      # Cape Capstan (NS side)
    '00235': ('Nova Scotia', 'America/Halifax'),      # West Advocate
    '00240': ('Nova Scotia', 'America/Halifax'),      # Cape d'Or
    '00242': ('Nova Scotia', 'America/Halifax'),      # Spencers Island
    '00245': ('Nova Scotia', 'America/Halifax'),      # Port Greville
    '00247': ('Nova Scotia', 'America/Halifax'),      # Diligent River
    '00250': ('Nova Scotia', 'America/Halifax'),      # Cape Sharp
    '00290': ('Nova Scotia', 'America/Halifax'),      # Cape Blomidon
    '00300': ('Nova Scotia', 'America/Halifax'),      # Scots Bay
    '00305': ('Nova Scotia', 'America/Halifax'),      # Baxters Harbour
    '00312': ('Nova Scotia', 'America/Halifax'),      # Ile Haute
    '00236': ('Nova Scotia', 'America/Halifax'),      # Advocate
    '00255': ('Nova Scotia', 'America/Halifax'),      # Parrsboro
    '00260': ('Nova Scotia', 'America/Halifax'),      # Five Islands
    '00270': ('Nova Scotia', 'America/Halifax'),      # Burntcoat Head
    '00282': ('Nova Scotia', 'America/Halifax'),      # Hantsport
    '00315': ('Nova Scotia', 'America/Halifax'),      # Margaretsville
}

# 67 constituents (from predictions, not observations)
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
    """Interpolate HW/LW points to regular time series using half-cosine."""
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

        t0 = hw_times[j]
        t1 = hw_times[j + 1]
        h0 = hw_levels[j]
        h1 = hw_levels[j + 1]

        dt_total = (t1 - t0).total_seconds()
        if dt_total <= 0:
            levels[i] = h0
            continue

        dt = (t - t0).total_seconds()
        frac = dt / dt_total

        w = (1 - np.cos(np.pi * frac)) / 2
        levels[i] = h0 * (1 - w) + h1 * w

    return np.array(times), levels


def load_chs_json(json_path):
    """Load CHS HW/LW JSON and convert to UTC (datetime, height_m) tuples."""
    with open(json_path) as f:
        data = json.load(f)

    tz_name = data.get('timezone', 'America/Halifax')
    local_tz = ZoneInfo(tz_name)

    entries = []
    for e in data['entries']:
        date_str = e['date']
        time_str = e['time']
        height_m = e['height_m']

        try:
            dt_local = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
            dt_aware = dt_local.replace(tzinfo=local_tz)
            dt_utc = dt_aware.astimezone(ZoneInfo('UTC')).replace(tzinfo=None)
            entries.append((dt_utc, height_m))
        except (ValueError, TypeError):
            continue

    # Sort and remove duplicates
    entries.sort(key=lambda x: x[0])
    cleaned = [entries[0]] if entries else []
    for e in entries[1:]:
        if e[0] > cleaned[-1][0]:
            cleaned.append(e)

    return cleaned, data.get('lat'), data.get('lon'), data.get('name', ''), data.get('station_id', '')


def analyze_station(json_path):
    """Run UTide analysis for one CHS station."""
    checkpoint_file = CHECKPOINT_DIR / f"{json_path.stem}.pkl"

    if checkpoint_file.exists():
        with open(checkpoint_file, 'rb') as f:
            result = pickle.load(f)
        print(f"  Checkpoint (R²={result['r_squared']:.4f})")
        return result

    t0 = timer.time()

    hw_lw, lat, lon, name, station_id = load_chs_json(json_path)
    if not name:
        name = json_path.stem.replace('_', ' ')

    if len(hw_lw) < 100:
        print(f"  Zu wenig HW/LW ({len(hw_lw)})")
        return None

    total_hwlw = len(hw_lw)
    print(f"  {total_hwlw} HW/LW-Punkte, {name} (ID {station_id})")

    # Cosine interpolation
    print(f"  Interpoliere...", end='', flush=True)
    datetimes_utc, levels = cosine_interpolate(hw_lw)

    if datetimes_utc is None:
        print(" FEHLER")
        return None

    n_points = len(datetimes_utc)
    years_span = n_points / (4 * 24 * 365.25)
    print(f" {n_points} Punkte ({years_span:.1f}J)")

    print(f"  UTide ({n_points} Beob., lat={lat:.2f})...", end='', flush=True)

    try:
        coef = utide.solve(
            datetimes_utc, levels, lat=lat,
            nodal=True, trend=False, method='ols',
            conf_int='none', verbose=False, constit=CONSTIT_67,
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
            uid = utide_all_names.index(uname)
            utide_speed = const_table.freq[uid] * 360.0
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
    for cname, speed in CONSTITUENTS_175:
        if cname in utide_results:
            r = utide_results[cname]
            constituents.append({
                'name': cname, 'amplitude': r['amplitude'],
                'phase': r['phase'], 'speed': speed,
            })
            n_analyzed += 1
        else:
            constituents.append({
                'name': cname, 'amplitude': 0.0, 'phase': 0.0,
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

    duration = timer.time() - t0

    result = {
        'mean': coef['mean'],
        'constituents': constituents,
        'n_analyzed': n_analyzed,
        'r_squared': r_squared,
        'rms_error': rms_error,
        'm2_amp': m2_amp,
        'k1_amp': k1_amp,
        'n_obs': n_points,
        'n_hwlw': total_hwlw,
        'start_time': datetimes_utc[0],
        'end_time': datetimes_utc[-1],
        'name': name,
        'station_id': station_id,
        'lat': lat,
        'lon': lon,
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
    name = result['name']
    lat = result['lat']
    lon = result['lon']
    station_id = result.get('station_id', '')

    # Determine province from station ID
    province, tz_name = PROVINCE_MAP.get(station_id, ('Nova Scotia', 'America/Halifax'))

    # Special name fixes
    if name == 'Dover':
        name = 'Dover (Memramcook)'

    location = f"{name}, {province}, Canada"

    # Timezone: AST = UTC-4
    if tz_name == 'America/Moncton':
        tz_line = "-04:00 :America/Moncton"
    else:
        tz_line = "-04:00 :America/Halifax"

    lines = []
    lines.append(f"# Harmonic constants derived from CHS (tides.gc.ca) HW/LW predictions")
    lines.append(f"# using UTide (v{utide.__version__}) with cosine-interpolated HW/LW data")
    lines.append(f"# {result['n_hwlw']} HW/LW points -> {result['n_obs']} interpolated points")
    lines.append(f"# from {result['start_time'].strftime('%Y-%m-%d')} to {result['end_time'].strftime('%Y-%m-%d')}")
    lines.append(f"# R^2 = {result['r_squared']:.4f}, RMS error = {result['rms_error']:.4f} m")
    lines.append(f"# Constituents analyzed: {result['n_analyzed']}")
    lines.append(f"#")
    lines.append(f"# {location}")
    lines.append(f"# BEGIN HOT COMMENTS")
    lines.append(f"# country: Canada")
    lines.append(f"# province: {province}")
    lines.append(f"# source: Derived from CHS (tides.gc.ca) HW/LW predictions with UTide")
    lines.append(f"# station_id_context: CHS {station_id}")
    lines.append(f"# date_imported: {datetime.now().strftime('%Y%m%d')}")
    lines.append(f"# datum: approximate chart datum")
    lines.append(f"# confidence: 7")
    lines.append(f"# !units: meters")
    lines.append(f"# !longitude: {lon:.6f}")
    lines.append(f"# !latitude: {lat:.6f}")

    lines.append(f"{location}")
    lines.append(tz_line)
    lines.append(f"{result['mean']:.4f} meters")

    for c in result['constituents']:
        if c.get('not_analyzed') or c['amplitude'] < 0.00005:
            lines.append(f"x 0 0")
        else:
            lines.append(f"{c['name']:15s} {c['amplitude']:.4f}  {c['phase']:.2f}")

    return '\n'.join(lines)


def collect_json_files():
    """Collect all 5-year CHS JSON files, deduplicating by station ID."""
    seen_ids = set()
    files = []

    for data_dir in DATA_DIRS:
        for json_path in sorted(data_dir.glob("*.json")):
            # Skip small files (old 1-year downloads)
            if json_path.stat().st_size < 400000:
                continue

            # Skip bore stations
            stem_lower = json_path.stem.lower()
            if any(bore in stem_lower for bore in BORE_STATIONS):
                continue

            # Extract station ID from filename (e.g., Cape_Enrage_00150.json -> 00150)
            import re
            m = re.search(r'_(\d{5})$', json_path.stem)
            if not m:
                continue
            station_id = m.group(1)

            if station_id in seen_ids:
                continue
            seen_ids.add(station_id)

            files.append(json_path)

    return files


def main():
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)

    header = read_header_from_template(TEMPLATE_PATH)

    json_files = collect_json_files()

    if not json_files:
        print("Keine JSON-Dateien gefunden!")
        return

    print("=" * 70)
    print("UTide Harmonic Analysis -- Bay of Fundy / Minas Basin (CHS)")
    print("=" * 70)
    print(f"Stationen: {len(json_files)}")
    for f in json_files:
        print(f"  {f.name}")
    print()

    results = []
    for i, json_path in enumerate(json_files):
        print(f"[{i+1:3d}/{len(json_files)}] {json_path.stem}")
        result = analyze_station(json_path)
        if result:
            results.append(result)

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
        sid = r.get('station_id', '?')
        province, _ = PROVINCE_MAP.get(sid, ('?', '?'))
        print(f"  {r['name']:30s} {province:15s}  R²={r['r_squared']:.4f}  "
              f"M2={r['m2_amp']:.4f}m  K1={r['k1_amp']:.4f}m  "
              f"RMS={r['rms_error']:.4f}m")


if __name__ == '__main__':
    main()
