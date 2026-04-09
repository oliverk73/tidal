#!/usr/bin/env python3
"""
UTide harmonic analysis for Spanish IHM (Instituto Hidrográfico de la Marina)
tide stations. Downloads HW/NW predictions from IHM open API (2022-2027),
cosine-interpolates to 15-min time series, then runs UTide.

Only processes stations NOT already covered by existing harmonics.
"""
import sys
sys.path.insert(0, '/home/oliver/py')

import os
import json
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
import time
import pickle
import gc
import urllib.request

import utide
from generate_germany_harmonics_175 import (
    CONSTITUENTS_175,
    find_xtide_match,
    read_header_from_template,
)

OUTPUT_PATH = Path("/home/oliver/harmonics/utide/harmonics_utide_spain_ihm.txt")
TEMPLATE_PATH = Path("/home/oliver/harmonics/utide/harmonics_utide_australia_bom.txt")
CHECKPOINT_DIR = Path("/home/oliver/harmonics/utide/checkpoints_spain_ihm")
CACHE_DIR = Path("/tmp/ihm_tides")

API_BASE = "https://ideihm.covam.es/api-ihm/getmarea"
YEARS = [2022, 2023, 2024, 2025, 2026, 2027]

# All IHM stations NOT already in Puertos del Estado (high-quality 175-constituent harmonics).
# Includes: Lisboa (Portugal), Tánger (Morocco), and stations overlapping with
# Classic 1997 or TICON4 (lower quality → improvement).
STATIONS = [
    # Galicia (NW Spain)
    ('71', 'A Guarda',                              41.8983, -8.8767, 'España'),
    ('30', 'Baiona',                                42.1183, -8.8450, 'España'),
    ('22', 'Camariñas',                             43.1267, -9.1817, 'España'),
    ('16', 'Cariño',                                43.7367, -7.8650, 'España'),
    ('17', 'Cedeira',                               43.6567, -8.0717, 'España'),
    ('15', 'Cillero, Ría de Viveiro',               43.6783, -7.5983, 'España'),
    ('23', 'Fisterra',                              42.9083, -9.2583, 'España'),
    ('12', 'Foz',                                   43.5650, -7.2550, 'España'),
    ('21', 'Malpica',                               43.3233, -8.8083, 'España'),
    ('28', 'Marín, Ría de Pontevedra',              42.4100, -8.6900, 'España'),
    ('24', 'Portosín, Ría de Muros y Noia',         42.7633, -8.9483, 'España'),
    ('11', 'Ribadeo',                               43.5333, -7.0367, 'España'),
    ('19', 'Sada Fontán, Ría de Betanzos',          43.3617, -8.2467, 'España'),
    ('14', 'San Cibrao',                            43.7083, -7.4617, 'España'),
    ('25', 'Santa Uxía de Ribeíra, Ría de Arousa',  42.5633, -8.9883, 'España'),
    ('27', 'Sanxenxo, Ría de Pontevedra',           42.3967, -8.8050, 'España'),
    # Asturias / Cantabria / Basque Country
    ('7',  'Avilés',                                43.5917, -5.9300, 'España'),
    ('72', 'Bermeo',                                43.4207, -2.7128, 'España'),
    ('13', 'Burela',                                43.6567, -7.3483, 'España'),
    ('8',  'Cudillero',                             43.5667, -6.1500, 'España'),
    ('4',  'Llanes',                                43.4200, -4.7483, 'España'),
    ('9',  'Navia',                                 43.5417, -6.7250, 'España'),
    ('5',  'Ribadesella',                           43.4617, -5.0600, 'España'),
    ('10', 'Tapia',                                 43.5717, -6.9450, 'España'),
    # Andalusia (Atlantic coast)
    ('32', 'Ayamonte',                              37.2117, -7.4050, 'España'),
    ('47', 'Barbate',                               36.1850, -5.9333, 'España'),
    ('42', 'Cádiz',                                 36.5400, -6.2867, 'España'),
    ('51', 'Ceuta',                                 35.8917, -5.3150, 'España'),
    ('39', 'Chipiona',                              36.7467, -6.4283, 'España'),
    ('46', 'Conil',                                 36.2950, -6.1367, 'España'),
    ('41', 'El Puerto de Santa María',              36.5983, -6.2217, 'España'),
    ('44', 'Gallineras',                            36.4383, -6.2050, 'España'),
    ('33', 'Marina de Isla Canela',                 37.1883, -7.3400, 'España'),
    ('34', 'Isla Cristina',                         37.2050, -7.3250, 'España'),
    ('43', 'La Carraca',                            36.4967, -6.1833, 'España'),
    ('35', 'Punta Umbría',                          37.1800, -6.9567, 'España'),
    ('40', 'Rota',                                  36.6150, -6.3300, 'España'),
    ('45', 'Sancti Petri',                          36.3950, -6.2083, 'España'),
    ('50', 'Sotogrande',                            36.2833, -5.2833, 'España'),
    # Canary Islands
    ('64', 'Granadilla, Tenerife, Islas Canarias',          28.0883, -16.4917, 'España'),
    ('63', 'Los Cristianos, Tenerife, Islas Canarias',      28.0483, -16.7183, 'España'),
    ('61', 'Los Gigantes, Tenerife, Islas Canarias',        28.2483, -16.8417, 'España'),
    ('55', 'Morro Jable, Fuerteventura, Islas Canarias',    28.0500, -14.3600, 'España'),
    ('58', 'Pasito Blanco, Gran Canaria, Islas Canarias',   27.7467, -15.6217, 'España'),
    ('62', 'Puerto de la Cruz, Tenerife, Islas Canarias',   28.4183, -16.5500, 'España'),
    ('59', 'Puerto de las Nieves, Gran Canaria, Islas Canarias', 28.1000, -15.7117, 'España'),
    # Portugal / Morocco (from same IHM API)
    ('31', 'Lisboa',                                38.7117, -9.1233, 'Portugal'),
    ('52', 'Tánger',                                35.7883, -5.8033, 'Morocco'),
]

# UTide constituents
CONSTIT_66 = [
    'M2', 'S2', 'N2', 'K2', 'K1', 'O1', 'P1', 'Q1',
    'MU2', 'NU2', 'L2', 'T2', '2N2', 'LDA2', 'R2',
    'J1', 'OO1', '2Q1', 'RHO1', 'SIG1', 'CHI1', 'PHI1', 'THE1', 'PSI1',
    'PI1', 'S1',
    'MF', 'MSF', 'MM', 'SA', 'SSA', 'MSM',
    'M3', 'MK3', 'MO3', 'SK3', 'SO3',
    'M4', 'MN4', 'MS4', 'MK4', 'S4', 'SN4',
    'M6', '2MS6', '2MN6',
    'M8',
    'H1', 'H2',
    'ALP1', 'BET1', 'TAU1', 'UPS1',
    '2SM2', 'OP2', 'MKS2', 'SKM2',
    'NO3',
    'N4', '3MS4',
    '2MK5', '2SK5',
    '2MK6', 'MSK6',
]


def download_station_data(station_id):
    """Download all months of HW/NW data for one station from IHM API."""
    all_entries = []
    for year in YEARS:
        for month in range(1, 13):
            cache_file = CACHE_DIR / f"{station_id}_{year}{month:02d}.json"
            if cache_file.exists():
                with open(cache_file) as f:
                    data = json.load(f)
            else:
                url = f"{API_BASE}?request=gettide&id={station_id}&format=json&month={year}{month:02d}"
                try:
                    req = urllib.request.Request(url)
                    with urllib.request.urlopen(req, timeout=30) as resp:
                        data = json.loads(resp.read())
                    with open(cache_file, 'w') as f:
                        json.dump(data, f)
                    time.sleep(0.2)  # be polite
                except Exception as e:
                    print(f"    Fehler {year}-{month:02d}: {e}")
                    continue

            mareas = data.get('mareas', {}).get('datos', {}).get('marea', [])
            for m in mareas:
                try:
                    dt_str = f"{m['fecha']}T{m['hora']}"
                    dt_local = datetime.strptime(dt_str, '%Y-%m-%dT%H:%M')
                    # IHM times are in UTC+1 (CET) for mainland Spain
                    # Canary Islands are UTC+0
                    height_m = float(m['altura'])
                    all_entries.append((dt_local, height_m))
                except (ValueError, KeyError):
                    continue

    return all_entries


def cosine_interpolate(hw_lw, target_interval_min=15):
    """Interpolate HW/NW points to regular time series using half-cosine."""
    if len(hw_lw) < 4:
        return None, None

    hw_lw.sort(key=lambda x: x[0])

    t_start = hw_lw[0][0]
    t_end = hw_lw[-1][0]
    interval = timedelta(minutes=target_interval_min)

    times = []
    t = t_start
    while t <= t_end:
        times.append(t)
        t += interval

    if len(times) < 100:
        return None, None

    levels = np.zeros(len(times))
    hw_times = [e[0] for e in hw_lw]
    hw_levels = [e[1] for e in hw_lw]

    j = 0
    for i, t in enumerate(times):
        while j < len(hw_times) - 2 and hw_times[j + 1] <= t:
            j += 1
        if j >= len(hw_times) - 1:
            levels[i] = hw_levels[-1]
            continue

        t0, t1 = hw_times[j], hw_times[j + 1]
        h0, h1 = hw_levels[j], hw_levels[j + 1]
        dt_total = (t1 - t0).total_seconds()
        if dt_total <= 0:
            levels[i] = h0
            continue

        dt = (t - t0).total_seconds()
        frac = dt / dt_total
        w = (1 - np.cos(np.pi * frac)) / 2
        levels[i] = h0 * (1 - w) + h1 * w

    return np.array(times), levels


def analyze_station(sid, name, lat, lon, entries):
    """Run UTide analysis for one IHM station."""
    checkpoint_file = CHECKPOINT_DIR / f"{sid}.pkl"
    if checkpoint_file.exists():
        with open(checkpoint_file, 'rb') as f:
            result = pickle.load(f)
        print(f"  Checkpoint (R2={result['r_squared']:.4f})")
        return result

    t0 = time.time()

    if len(entries) < 100:
        print(f"  Zu wenig Daten ({len(entries)} HW/NW)")
        return None

    # Sort and deduplicate
    entries.sort(key=lambda x: x[0])
    cleaned = [entries[0]]
    for entry in entries[1:]:
        if entry[0] > cleaned[-1][0]:
            cleaned.append(entry)
    entries = cleaned
    total_hwlw = len(entries)

    # Cosine interpolation
    print(f"  {total_hwlw} HW/NW, interpoliere...", end='', flush=True)
    datetimes, levels = cosine_interpolate(entries)

    if datetimes is None:
        print(" FEHLER")
        return None

    n_points = len(datetimes)
    years_span = n_points / (4 * 24 * 365.25)
    print(f" {n_points} Punkte ({years_span:.1f}J)")

    # UTide
    print(f"  UTide (lat={lat:.2f})...", end='', flush=True)
    try:
        coef = utide.solve(
            datetimes, levels, lat=lat,
            nodal=True, trend=False, method='ols',
            conf_int='none', verbose=False, constit=CONSTIT_66,
        )
    except Exception as e:
        print(f" FEHLER: {e}")
        return None
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

    # R2
    recon = utide.reconstruct(datetimes, coef, verbose=False)
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
        'n_obs': n_points,
        'n_hwlw': total_hwlw,
        'start_time': datetimes[0],
        'end_time': datetimes[-1],
        'station_id': sid,
        'name': name,
        'lat': lat,
        'lon': lon,
        'duration': duration,
    }

    with open(checkpoint_file, 'wb') as f:
        pickle.dump(result, f)

    del coef, recon, datetimes, levels, residuals
    gc.collect()

    print(f"  R2={r_squared:.4f}, RMS={rms_error:.4f}m, M2={m2_amp:.4f}m, "
          f"K1={k1_amp:.4f}m ({duration:.0f}s)")
    return result


def format_station_block(result):
    """Format a single station block in XTide harmonics format."""
    name = result['name']
    lat = result['lat']
    lon = result['lon']
    sid = result['station_id']
    country = result.get('country', 'España')

    lines = []
    lines.append(f"# Harmonic constants derived from IHM tide predictions")
    lines.append(f"# using UTide (v{utide.__version__}) with cosine-interpolated HW/NW data")
    lines.append(f"# {result['n_hwlw']} HW/NW points -> {result['n_obs']} interpolated points")
    lines.append(f"# from {result['start_time'].strftime('%Y-%m-%d')} to {result['end_time'].strftime('%Y-%m-%d')}")
    lines.append(f"# R^2 = {result['r_squared']:.4f}, RMS error = {result['rms_error']:.4f} m")
    lines.append(f"# Constituents analyzed: {result['n_analyzed']}")
    lines.append(f"#")
    lines.append(f"# {name}, {country}")
    lines.append(f"# BEGIN HOT COMMENTS")
    lines.append(f"# country: {country}")
    lines.append(f"# source: IHM tide predictions, UTide analysis")
    lines.append(f"# station_id_context: IHM-{sid}")
    lines.append(f"# date_imported: {datetime.now().strftime('%Y%m%d')}")
    lines.append(f"# datum: Chart Datum")
    lines.append(f"# confidence: 8")
    lines.append(f"# !units: meters")
    lines.append(f"# !longitude: {lon:.6f}")
    lines.append(f"# !latitude: {lat:.6f}")

    lines.append(f"{name}, {country}")
    lines.append(f"+00:00 :UTC")
    lines.append(f"{result['mean']:.4f} meters")

    for c in result['constituents']:
        if c.get('not_analyzed') or c['amplitude'] < 0.00005:
            lines.append(f"x 0 0")
        else:
            lines.append(f"{c['name']:15s} {c['amplitude']:.4f}  {c['phase']:.2f}")

    return '\n'.join(lines)


def main():
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("UTide Harmonic Analysis - IHM Spain Tide Predictions")
    print("=" * 70)
    print(f"Stationen: {len(STATIONS)}, Jahre: {YEARS[0]}-{YEARS[-1]}")
    print()

    results = []
    errors = []

    for i, (sid, name, lat, lon, country_name) in enumerate(STATIONS):
        print(f"\n[{i+1}/{len(STATIONS)}] {sid} | {name} ({lat:.4f}, {lon:.4f}) [{country_name}]")

        entries = download_station_data(sid)
        print(f"  {len(entries)} HW/NW aus {len(YEARS)} Jahren")

        if len(entries) < 100:
            print(f"  Zu wenig Daten, ueberspringe")
            errors.append((name, "zu wenig Daten"))
            continue

        result = analyze_station(sid, name, lat, lon, entries)
        if result is not None:
            result['country'] = country_name
            results.append(result)
        else:
            errors.append((name, "Analyse fehlgeschlagen"))

        if (i + 1) % 10 == 0:
            gc.collect()

    # Write harmonics file
    if results:
        header = read_header_from_template(TEMPLATE_PATH)

        print(f"\n{'='*70}")
        print(f"Schreibe Harmonics-Datei: {OUTPUT_PATH.name}")
        with open(OUTPUT_PATH, 'w', encoding='iso-8859-1') as f:
            f.write(header)
            f.write('\n')
            for result in results:
                block = format_station_block(result)
                f.write(block)
                f.write('\n')
        print(f"  {len(results)} Stationen, {OUTPUT_PATH.stat().st_size / 1024:.0f} KB")

    # Summary
    print(f"\n{'='*70}")
    print("ZUSAMMENFASSUNG")
    print(f"{'='*70}")
    print(f"{'Station':<40s} {'ID':>3s} {'HW/NW':>6s} {'R2':>7s} {'RMS':>7s} "
          f"{'M2':>7s} {'K1':>7s}")
    print(f"{'_'*40} {'_'*3} {'_'*6} {'_'*7} {'_'*7} {'_'*7} {'_'*7}")

    for r in results:
        print(f"{r['name']:<40s} {r['station_id']:>3s} {r['n_hwlw']:>6d} "
              f"{r['r_squared']:>7.4f} {r['rms_error']:>7.4f} "
              f"{r['m2_amp']:>7.4f} {r['k1_amp']:>7.4f}")

    if errors:
        print(f"\nFehler ({len(errors)}):")
        for name, err in errors:
            print(f"  {name}: {err}")

    print(f"\nGesamt: {len(results)} Stationen")
    if results:
        avg_r2 = np.mean([r['r_squared'] for r in results])
        print(f"Durchschnittliches R2: {avg_r2:.4f}")


if __name__ == '__main__':
    main()
