#!/usr/bin/env python3
"""
Generate Harmonic Constants from UHSLC hourly water level data for Mexico.
Uses UTide for harmonic analysis with equilibrium arguments and node factors.
Outputs 175 tidal constituents compatible with XTide format.

Phase convention:
  UTide outputs Greenwich phase lag (g).
  XTide with +00:00 meridian stores Greenwich phase directly.
"""
import numpy as np
from datetime import datetime
import os
from pathlib import Path
import pandas as pd
import utide

# Meridian: UTC (+00:00) -> no phase conversion needed
TIME_MERIDIAN_DEGREES = 0

# 175 Constituents with speeds in degrees per solar hour (XTide order)
CONSTITUENTS_175 = [
    ('J1', 15.5854433), ('K1', 15.0410686), ('K2', 30.0821373), ('L2', 29.5284789),
    ('M1', 14.4966939), ('M2', 28.9841042), ('M3', 43.4761563), ('M4', 57.9682084),
    ('M6', 86.9523126), ('M8', 115.9364169), ('N2', 28.4397295), ('2N2', 27.8953548),
    ('O1', 13.9430356), ('OO1', 16.1391017), ('P1', 14.9589314), ('Q1', 13.3986609),
    ('2Q1', 12.8542862), ('R2', 30.0410667), ('S1', 15.0000000), ('S2', 30.0000000),
    ('S4', 60.0000000), ('S6', 90.0000000), ('T2', 29.9589333), ('LDA2', 29.4556253),
    ('MU2', 27.9682084), ('NU2', 28.5125831), ('RHO1', 13.4715145), ('MK3', 44.0251729),
    ('2MK3', 42.9271398), ('MN4', 57.4238337), ('MS4', 58.9841042), ('2SM2', 31.0158958),
    ('MF', 1.0980331), ('MSF', 1.0158958), ('MM', 0.5443747), ('SA', 0.0410686),
    ('SSA', 0.0821373), ('SA-IOS', 0.0410667), ('MF-IOS', 1.0980331), ('S1-IOS', 15.0000020),
    ('OO1-IOS', 16.1391017), ('R2-IOS', 30.0410667), ('A7', 1.6424078), ('2MK5', 73.0092771),
    ('2MK6', 88.0503457), ('2MN2', 29.5284789), ('2MN6', 86.4079379), ('2MS6', 87.9682084),
    ('2NM6', 85.8635632), ('2SK5', 75.0410686), ('2SM6', 88.9841042), ('3MK7', 101.9933813),
    ('3MN8', 115.3920422), ('3MS2', 26.9523126), ('3MS4', 56.9523126), ('3MS8', 116.9523126),
    ('ALP1', 12.3827651), ('BET1', 14.4145567), ('CHI1', 14.5695476), ('H1', 28.9430375),
    ('H2', 29.0251709), ('KJ2', 30.6265120), ('ETA2', 30.6265120), ('KQ1', 16.6834764),
    ('UPS1', 16.6834764), ('M10', 144.9205211), ('M12', 173.9046253), ('MK4', 59.0662415),
    ('MKS2', 29.0662415), ('MNS2', 27.4238337), ('EPS2', 27.4238337), ('MO3', 42.9271398),
    ('MP1', 14.0251729), ('TAU1', 14.0251729), ('MPS2', 28.9430356), ('MSK6', 89.0662415),
    ('MSM', 0.4715211), ('MSN2', 30.5443747), ('MSN6', 87.4238337), ('NLK2', 27.8860711),
    ('NO1', 14.4966939), ('OP2', 28.9019669), ('OQ2', 27.3509801), ('PHI1', 15.1232059),
    ('KP1', 15.1232059), ('PI1', 14.9178647), ('TK1', 14.9178647), ('PSI1', 15.0821353),
    ('RP1', 15.0821353), ('S3', 45.0000000), ('SIG1', 12.9271398), ('SK3', 45.0410686),
    ('SK4', 60.0821373), ('SN4', 58.4397295), ('SNK6', 88.5218668), ('SO1', 16.0569644),
    ('SO3', 43.9430356), ('THE1', 15.5125897), ('2PO1', 15.9748271), ('2NS2', 26.8794590),
    ('MLN2S2', 26.9523126), ('2ML2S2', 27.4966873), ('SKM2', 31.0980331), ('2MS2K2', 27.8039339),
    ('MKL2S2', 28.5947204), ('M2(KS)2', 29.1483788), ('2SN(MK)2', 29.3734880), ('2KM(SN)2', 30.7086493),
    ('NO3', 42.3827651), ('2MLS4', 57.4966873), ('ML4', 58.5125831), ('N4', 56.8794590),
    ('SL4', 59.5284789), ('MNO5', 71.3668693), ('2MO5', 71.9112440), ('MSK5', 74.0251729),
    ('3KM5', 74.1073101), ('2MP5', 72.9271398), ('3MP5', 71.9933813), ('MNK5', 72.4649024),
    ('2NMLS6', 85.3920422), ('MSL6', 88.5125831), ('2ML6', 87.4966873), ('2MNLS6', 85.9364169),
    ('3MLS6', 86.4807916), ('2MNO7', 100.3509735), ('2NMK7', 100.9046319), ('2MSO7', 101.9112440),
    ('MSKO7', 103.0092771), ('2MSN8', 116.4079379), ('2(MS)8', 117.9682084), ('2(MN)8', 114.8476675),
    ('2MSL8', 117.4966873), ('4MLS8', 115.4648958), ('3ML8', 116.4807916), ('3MK8', 117.0344499),
    ('2MSK8', 118.0503457), ('2M2NK9', 129.8887361), ('3MNK9', 130.4331108), ('4MK9', 130.9774855),
    ('3MSK9', 131.9933813), ('4MN10', 144.3761464), ('3MNS10', 145.3920422), ('4MS10', 145.9364169),
    ('3MSL10', 146.4807916), ('3M2S10', 146.9523126), ('4MSK11', 160.9774855), ('4MNS12', 174.3761464),
    ('5MS12', 174.9205211), ('4MSL12', 175.4648958), ('4M2S12', 175.9364169), ('M1C', 14.4920521),
    ('3MKS2', 26.8701754), ('OQ2-HORN', 27.3416965), ('MSK2', 28.9019669), ('MSP2', 29.0251729),
    ('2MP3', 43.0092771), ('4MS4', 55.9364169), ('2MNS4', 56.4079379), ('2MSK4', 57.8860711),
    ('3MN4', 58.5125831), ('2MSN4', 59.5284789), ('3MK5', 71.9112440), ('3MO5', 73.0092771),
    ('3MNS6', 85.3920422), ('4MS6', 85.9364169), ('2MNU6', 86.4807916), ('3MSK6', 86.8701754),
    ('MKNU6', 87.5788246), ('3MSN6', 88.5125831), ('M7', 101.4490066), ('2MNK8', 116.4900752),
    ('2(MS)N10', 146.4079379), ('MNUS2', 27.4966873), ('2MK2', 27.8860711),
]

# Explicit name mapping: UTide name -> XTide name
UTIDE_TO_XTIDE_NAME = {
    'SA':   'SA-IOS',
    'S1':   'S1-IOS',
    'ETA2': 'ETA2',
    'NO1':  'NO1',
    'TAU1': 'TAU1',
    'EPS2': 'EPS2',
}

# Build speed-based lookup
XTIDE_BY_SPEED = {}
for name, speed in CONSTITUENTS_175:
    key = round(speed * 1000)
    if key not in XTIDE_BY_SPEED:
        XTIDE_BY_SPEED[key] = []
    XTIDE_BY_SPEED[key].append((name, speed))


# Station metadata (must match download_uhslc_mexico.py)
STATIONS = [
    {'uhslc_id': 317, 'name': 'Ensenada',           'lat': 31.850, 'lon': -116.633, 'state': 'Baja California',     'water': 'Pacific Ocean'},
    {'uhslc_id': 308, 'name': 'San Quintin',         'lat': 30.483, 'lon': -115.983, 'state': 'Baja California',     'water': 'Pacific Ocean'},
    {'uhslc_id':  36, 'name': 'Isla Guadalupe',      'lat': 28.883, 'lon': -118.300, 'state': 'Baja California',     'water': 'Pacific Ocean'},
    {'uhslc_id': 305, 'name': 'Isla de Cedros',      'lat': 28.100, 'lon': -115.183, 'state': 'Baja California',     'water': 'Pacific Ocean'},
    {'uhslc_id':  34, 'name': 'Cabo San Lucas',      'lat': 22.880, 'lon': -109.908, 'state': 'Baja California Sur', 'water': 'Pacific Ocean'},
    {'uhslc_id':  90, 'name': 'Isla Socorro',         'lat': 18.733, 'lon': -111.017, 'state': 'Colima',             'water': 'Pacific Ocean'},
    {'uhslc_id': 307, 'name': 'San Felipe',          'lat': 31.018, 'lon': -114.818, 'state': 'Baja California',     'water': 'Gulf of California'},
    {'uhslc_id': 310, 'name': 'Bahia de los Angeles','lat': 28.958, 'lon': -113.550, 'state': 'Baja California',     'water': 'Gulf of California'},
    {'uhslc_id': 319, 'name': 'Loreto',              'lat': 26.017, 'lon': -111.367, 'state': 'Baja California Sur', 'water': 'Gulf of California'},
    {'uhslc_id': 674, 'name': 'San Carlos',          'lat': 24.790, 'lon': -112.120, 'state': 'Baja California Sur', 'water': 'Gulf of California'},
    {'uhslc_id': 671, 'name': 'La Paz',              'lat': 24.162, 'lon': -110.345, 'state': 'Baja California Sur', 'water': 'Gulf of California'},
    {'uhslc_id': 676, 'name': 'Topolobampo',         'lat': 25.600, 'lon': -109.048, 'state': 'Sinaloa',            'water': 'Gulf of California'},
    {'uhslc_id': 677, 'name': 'Yavaros',             'lat': 26.703, 'lon': -109.513, 'state': 'Sonora',             'water': 'Gulf of California'},
    {'uhslc_id': 397, 'name': 'Guaymas',             'lat': 27.933, 'lon': -110.900, 'state': 'Sonora',             'water': 'Gulf of California'},
    {'uhslc_id': 673, 'name': 'Mazatlan',            'lat': 23.198, 'lon': -106.422, 'state': 'Sinaloa',            'water': 'Pacific Ocean'},
    {'uhslc_id': 393, 'name': 'Puerto Vallarta',     'lat': 20.615, 'lon': -105.245, 'state': 'Jalisco',            'water': 'Pacific Ocean'},
    {'uhslc_id': 395, 'name': 'Manzanillo',          'lat': 19.050, 'lon': -104.333, 'state': 'Colima',             'water': 'Pacific Ocean'},
    {'uhslc_id': 687, 'name': 'Zihuatanejo',         'lat': 17.637, 'lon': -101.558, 'state': 'Guerrero',           'water': 'Pacific Ocean'},
    {'uhslc_id': 316, 'name': 'Acapulco',            'lat': 16.840, 'lon':  -99.912, 'state': 'Guerrero',           'water': 'Pacific Ocean'},
    {'uhslc_id': 672, 'name': 'Puerto Angel',        'lat': 15.657, 'lon':  -96.493, 'state': 'Oaxaca',             'water': 'Pacific Ocean'},
    {'uhslc_id': 394, 'name': 'Salina Cruz',         'lat': 16.160, 'lon':  -95.203, 'state': 'Oaxaca',             'water': 'Pacific Ocean'},
    {'uhslc_id': 318, 'name': 'Puerto Madero',       'lat': 14.717, 'lon':  -92.433, 'state': 'Chiapas',            'water': 'Pacific Ocean'},
    {'uhslc_id': 277, 'name': 'Madero (Tampico)',    'lat': 22.262, 'lon':  -97.795, 'state': 'Tamaulipas',         'water': 'Gulf of Mexico'},
    {'uhslc_id': 250, 'name': 'Veracruz',            'lat': 19.200, 'lon':  -96.133, 'state': 'Veracruz',           'water': 'Gulf of Mexico'},
    {'uhslc_id': 779, 'name': 'Ciudad del Carmen',   'lat': 18.533, 'lon':  -91.833, 'state': 'Campeche',           'water': 'Gulf of Mexico'},
    {'uhslc_id': 861, 'name': 'Celestun',            'lat': 20.858, 'lon':  -90.403, 'state': 'Yucatan',            'water': 'Gulf of Mexico'},
    {'uhslc_id': 721, 'name': 'Progreso',            'lat': 21.283, 'lon':  -89.667, 'state': 'Yucatan',            'water': 'Gulf of Mexico'},
    {'uhslc_id': 862, 'name': 'Telchac',             'lat': 21.340, 'lon':  -89.308, 'state': 'Yucatan',            'water': 'Gulf of Mexico'},
    {'uhslc_id': 860, 'name': 'Puerto Morelos',      'lat': 20.868, 'lon':  -86.867, 'state': 'Quintana Roo',       'water': 'Caribbean Sea'},
]


def find_xtide_match(utide_name, utide_speed):
    """Find matching XTide constituent by name or speed."""
    mapped_name = UTIDE_TO_XTIDE_NAME.get(utide_name, utide_name)

    for xt_name, xt_speed in CONSTITUENTS_175:
        if xt_name == mapped_name:
            return xt_name, xt_speed

    key = round(utide_speed * 1000)
    for delta in [0, -1, 1]:
        candidates = XTIDE_BY_SPEED.get(key + delta, [])
        for xt_name, xt_speed in candidates:
            if abs(xt_speed - utide_speed) < 0.002:
                return xt_name, xt_speed

    return None, None


def load_csv_water_levels(csv_path, max_years=10.0):
    """Load water level data from UHSLC CSV file.
    Limits to max_years (default ~1 nodal cycle) using the most recent data.
    Returns UTC datetimes and levels in meters."""
    df = pd.read_csv(csv_path)

    # Parse timestamps to datetime
    times = pd.to_datetime(df['time'], utc=True)
    levels = df['waterlevel_m'].values

    # Remove NaN
    valid = ~np.isnan(levels)
    times = times[valid].reset_index(drop=True)
    levels = levels[valid]

    # Limit to max_years of most recent data to keep memory manageable
    max_obs = int(max_years * 365.25 * 24)
    if len(times) > max_obs:
        times = times.iloc[-max_obs:]
        levels = levels[-max_obs:]

    # Convert to Python datetime objects (UTide needs this)
    dt_list = [pd.Timestamp(t).to_pydatetime().replace(tzinfo=None) for t in times]

    n_obs = len(dt_list)
    if n_obs < 2000:
        return None

    first = dt_list[0]
    last = dt_list[-1]
    years = (last - first).total_seconds() / (365.25 * 86400)

    return {
        'datetimes_utc': np.array(dt_list),
        'levels': np.array(levels),
        'start_time': first,
        'end_time': last,
        'n_obs': n_obs,
        'years': years,
    }


def harmonic_analysis_utide(datetimes_utc, levels, lat):
    """Perform harmonic analysis using UTide. Returns 175-constituent results."""
    try:
        coef = utide.solve(
            datetimes_utc,
            levels,
            lat=lat,
            nodal=True,
            trend=False,
            method='ols',
            conf_int='linear',
            verbose=False,
            constit='auto',
        )
    except Exception as e:
        print(f" UTide error: {e}", end='')
        return None

    # Map UTide results to XTide 175-constituent format
    from utide._ut_constants import ut_constants
    const_table = ut_constants['const']
    utide_names = [n.strip() for n in const_table.name]

    utide_results = {}
    for i, uname in enumerate(coef['name']):
        uname = uname.strip()
        amplitude = coef['A'][i]
        greenwich_phase = coef['g'][i]
        snr = coef['SNR'][i] if 'SNR' in coef else 999

        if uname in utide_names:
            idx = utide_names.index(uname)
            utide_speed = const_table.freq[idx] * 360.0
        else:
            continue

        xt_name, xt_speed = find_xtide_match(uname, utide_speed)
        if xt_name is None:
            continue

        # Store Greenwich phase directly (meridian +00:00)
        utide_results[xt_name] = {
            'amplitude': amplitude,
            'phase': greenwich_phase % 360,
            'snr': snr
        }

    # Build full 175-constituent result
    results = {'mean': coef['mean'], 'constituents': []}

    for name, speed in CONSTITUENTS_175:
        if name in utide_results:
            r = utide_results[name]
            results['constituents'].append({
                'name': name,
                'amplitude': r['amplitude'],
                'phase': r['phase'],
                'speed': speed,
                'snr': r['snr']
            })
        else:
            results['constituents'].append({
                'name': name,
                'amplitude': 0.0,
                'phase': 0.0,
                'speed': speed,
                'not_analyzed': True
            })

    # Goodness of fit
    try:
        reconstruction = utide.reconstruct(datetimes_utc, coef, verbose=False)
        h_predicted = reconstruction['h']
        residuals = levels - h_predicted
        ss_res = np.sum(residuals**2)
        ss_tot = np.sum((levels - np.mean(levels))**2)
        results['r_squared'] = 1 - ss_res / ss_tot if ss_tot > 0 else 0
        results['rms_error'] = np.sqrt(np.mean(residuals**2))
    except:
        results['r_squared'] = 0
        results['rms_error'] = 0

    results['n_analyzed'] = sum(1 for c in results['constituents'] if not c.get('not_analyzed'))

    return results


def format_station_block(station, results, data):
    """Format a single station block in XTide harmonics format."""
    name = station['name']
    state = station['state']
    lat = station['lat']
    lon = station['lon']
    water = station['water']
    full_name = f"{name}, {state}, Mexico"

    lines = []
    lines.append(f"# Harmonic constants derived from UHSLC sea level data")
    lines.append(f"# using UTide (v{utide.__version__}) with {data['n_obs']} observations")
    lines.append(f"# from {data['start_time'].strftime('%Y-%m-%d')} to {data['end_time'].strftime('%Y-%m-%d')}")
    lines.append(f"# R^2 = {results['r_squared']:.4f}, RMS error = {results['rms_error']:.4f} m")
    lines.append(f"# Constituents analyzed: {results['n_analyzed']}")
    lines.append(f"#")
    lines.append(f"# {full_name}")
    lines.append(f"# BEGIN HOT COMMENTS")
    lines.append(f"# country: Mexico")
    lines.append(f"# state: {state}")
    lines.append(f"# source: Derived from UHSLC data with UTide harmonic analysis")
    lines.append(f"# station_id_context: UHSLC-{station['uhslc_id']}")
    lines.append(f"# date_imported: {datetime.now().strftime('%Y%m%d')}")
    lines.append(f"# datum: Mean Sea Level")
    lines.append(f"# confidence: 8")
    lines.append(f"# !units: meters")
    lines.append(f"# !longitude: {lon:.6f}")
    lines.append(f"# !latitude: {lat:.6f}")

    lines.append(full_name)
    lines.append(f"+00:00 :UTC")
    lines.append(f"{results['mean']:.4f} meters")

    for c in results['constituents']:
        if c.get('not_analyzed') or c['amplitude'] < 0.00005:
            lines.append(f"x 0 0")
        else:
            lines.append(f"{c['name']:15s} {c['amplitude']:.4f}  {c['phase']:.2f}")

    return '\n'.join(lines)


def read_header_from_template(template_path):
    """Read header from template file up to (but not including) first station block."""
    with open(template_path, 'r', encoding='latin-1') as f:
        lines = f.readlines()

    header_lines = []
    end_count = 0
    after_second_end = False

    for line in lines:
        stripped = line.strip()

        if stripped == '*END*':
            end_count += 1
            header_lines.append(line.rstrip())
            if end_count >= 2:
                after_second_end = True
            continue

        if after_second_end:
            if any(kw in stripped for kw in [
                'derived by', 'derived from', 'BEGIN HOT COMMENTS',
                'observations from', 'minut data',
            ]):
                break
            if stripped and not stripped.startswith('#'):
                break

        header_lines.append(line.rstrip())

    return '\n'.join(header_lines)


def main():
    data_dir = Path('/home/oliver/water_levels/Mexico_UHSLC')
    template_path = Path('/home/oliver/harmonics/utide/harmonics_utide_canada_all.txt')
    output_path = Path(f'/home/oliver/harmonics/utide/harmonics_utide_mexico.txt')

    print("=" * 70)
    print("Generate Mexico Harmonics with UTide")
    print("=" * 70)

    # Read header from template
    print(f"\nReading header from {template_path.name}...")
    header = read_header_from_template(template_path)

    # Build lookup for CSV files
    csv_files = {int(f.name.split('_')[0]): f for f in data_dir.glob('*.csv')}
    print(f"Found {len(csv_files)} CSV files")

    print(f"\nProcessing {len(STATIONS)} stations...\n")

    station_blocks = []
    processed = 0
    failed = 0
    skipped = 0

    for i, station in enumerate(STATIONS):
        sid = station['uhslc_id']
        name = station['name']

        print(f"[{i+1}/{len(STATIONS)}] {name} (UHSLC {sid})...", end='', flush=True)

        if sid not in csv_files:
            print(" NO DATA FILE")
            failed += 1
            continue

        data = load_csv_water_levels(str(csv_files[sid]))
        if data is None:
            print(" INSUFFICIENT DATA")
            failed += 1
            continue

        print(f" {data['n_obs']} obs ({data['years']:.1f}y)...", end='', flush=True)

        results = harmonic_analysis_utide(data['datetimes_utc'], data['levels'], station['lat'])
        if results is None:
            print(" ANALYSIS FAILED")
            failed += 1
            continue

        block = format_station_block(station, results, data)
        station_blocks.append(block)

        # Find M2 amplitude for summary
        m2_amp = 0
        for c in results['constituents']:
            if c['name'] == 'M2':
                m2_amp = c['amplitude']
                break

        print(f" OK (R²={results['r_squared']:.3f}, M2={m2_amp:.3f}m, constit={results['n_analyzed']})")
        processed += 1

    print(f"\n{'='*70}")
    print(f"Processed: {processed}, Failed: {failed}")

    if not station_blocks:
        print("No stations processed, nothing to write.")
        return

    print(f"\nWriting output to {output_path}...")
    with open(output_path, 'w', encoding='latin-1') as f:
        f.write(header)
        f.write('\n')
        for block in station_blocks:
            f.write(block)
            f.write('\n')

    print(f"Done! Created {output_path}")
    print(f"Total stations: {len(station_blocks)}")


if __name__ == "__main__":
    main()
