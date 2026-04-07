#!/usr/bin/env python3
"""
Generate Harmonic Constants for Norway using UTide.
Source: Kartverket (Norwegian Mapping Authority) tide gauge API.
31 stations, hourly observations, freely available (CC BY 4.0).
Outputs 175 XTide-compatible constituents.
"""
import numpy as np
from datetime import datetime
from pathlib import Path
import pandas as pd
import utide
import re
import time
import xml.etree.ElementTree as ET
try:
    import requests
except ImportError:
    import urllib.request
    requests = None

# All 31 Kartverket stations with coordinates and earliest known data year
STATIONS = [
    {'code': 'AES', 'name': 'Ålesund',        'lat': 62.4694, 'lon': 6.1519,  'start': 2006, 'water': 'Norwegian Sea'},
    {'code': 'ANX', 'name': 'Andenes',         'lat': 69.3261, 'lon': 16.1348, 'start': 2006, 'water': 'Norwegian Sea'},
    {'code': 'BGO', 'name': 'Bergen',           'lat': 60.3980, 'lon': 5.3205,  'start': 2003, 'water': 'North Sea'},
    {'code': 'BOO', 'name': 'Bodø',             'lat': 67.2923, 'lon': 14.3998, 'start': 2006, 'water': 'Norwegian Sea'},
    {'code': 'BOH', 'name': 'Bøfjorden',        'lat': 61.1359, 'lon': 5.3397,  'start': 2023, 'water': 'Norwegian Sea'},
    {'code': 'BRJ', 'name': 'Bruravik',         'lat': 60.4921, 'lon': 6.8939,  'start': 2023, 'water': 'Hardangerfjorden'},
    {'code': 'HFT', 'name': 'Hammerfest',       'lat': 70.6648, 'lon': 23.6787, 'start': 2006, 'water': 'Barents Sea'},
    {'code': 'HAR', 'name': 'Harstad',          'lat': 68.8013, 'lon': 16.5482, 'start': 2006, 'water': 'Norwegian Sea'},
    {'code': 'HEI', 'name': 'Heimsjøen',        'lat': 63.4252, 'lon': 9.1015,  'start': 2006, 'water': 'Norwegian Sea'},
    {'code': 'HRO', 'name': 'Helgeroa',         'lat': 58.9952, 'lon': 9.8564,  'start': 2006, 'water': 'Skagerrak'},
    {'code': 'HVG', 'name': 'Honningsvåg',      'lat': 70.9803, 'lon': 25.9727, 'start': 2006, 'water': 'Barents Sea'},
    {'code': 'KAB', 'name': 'Kabelvåg',         'lat': 68.2126, 'lon': 14.4821, 'start': 2006, 'water': 'Norwegian Sea'},
    {'code': 'KSU', 'name': 'Kristiansund',     'lat': 63.1139, 'lon': 7.7361,  'start': 2006, 'water': 'Norwegian Sea'},
    {'code': 'LEH', 'name': 'Leirvik',          'lat': 59.7664, 'lon': 5.5037,  'start': 2022, 'water': 'North Sea'},
    {'code': 'MSU', 'name': 'Mausund',          'lat': 63.8693, 'lon': 8.6652,  'start': 2010, 'water': 'Norwegian Sea'},
    {'code': 'MAY', 'name': 'Måløy',            'lat': 61.9338, 'lon': 5.1133,  'start': 2006, 'water': 'Norwegian Sea'},
    {'code': 'NVK', 'name': 'Narvik',           'lat': 68.4283, 'lon': 17.4258, 'start': 2006, 'water': 'Ofotfjorden'},
    {'code': 'NYA', 'name': 'Ny-Ålesund',       'lat': 78.9285, 'lon': 11.9380, 'start': 2006, 'water': 'Arctic Ocean'},
    {'code': 'OSC', 'name': 'Oscarsborg',       'lat': 59.6781, 'lon': 10.6049, 'start': 2006, 'water': 'Oslofjorden'},
    {'code': 'OSL', 'name': 'Oslo',             'lat': 59.9086, 'lon': 10.7345, 'start': 2006, 'water': 'Oslofjorden'},
    {'code': 'RVK', 'name': 'Rørvik',           'lat': 64.8595, 'lon': 11.2301, 'start': 2006, 'water': 'Norwegian Sea'},
    {'code': 'SBG', 'name': 'Sandnes',          'lat': 58.8682, 'lon': 5.7466,  'start': 2021, 'water': 'North Sea'},
    {'code': 'SIE', 'name': 'Sirevaag',         'lat': 58.5052, 'lon': 5.7916,  'start': 2022, 'water': 'North Sea'},
    {'code': 'SOY', 'name': 'Solumstrand',      'lat': 59.7106, 'lon': 10.2730, 'start': 2023, 'water': 'Drammensfjorden'},
    {'code': 'SVG', 'name': 'Stavanger',        'lat': 58.9743, 'lon': 5.7301,  'start': 2006, 'water': 'North Sea'},
    {'code': 'TRG', 'name': 'Tregde',           'lat': 58.0064, 'lon': 7.5548,  'start': 2006, 'water': 'Skagerrak'},
    {'code': 'TOS', 'name': 'Tromsø',           'lat': 69.6461, 'lon': 18.9548, 'start': 2006, 'water': 'Norwegian Sea'},
    {'code': 'TRD', 'name': 'Trondheim',        'lat': 63.4365, 'lon': 10.3917, 'start': 2006, 'water': 'Trondheimsfjorden'},
    {'code': 'TAZ', 'name': 'Træna',            'lat': 66.4966, 'lon': 12.0886, 'start': 2023, 'water': 'Norwegian Sea'},
    {'code': 'VAW', 'name': 'Vardø',            'lat': 70.3750, 'lon': 31.1040, 'start': 2006, 'water': 'Barents Sea'},
    {'code': 'VIK', 'name': 'Viker',            'lat': 59.0360, 'lon': 10.9498, 'start': 2006, 'water': 'Skagerrak'},
]

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

UTIDE_TO_XTIDE_NAME = {
    'SA': 'SA-IOS', 'S1': 'S1-IOS', 'ETA2': 'ETA2',
    'NO1': 'NO1', 'TAU1': 'TAU1', 'EPS2': 'EPS2',
}

XTIDE_BY_SPEED = {}
for name, speed in CONSTITUENTS_175:
    key = round(speed * 1000)
    if key not in XTIDE_BY_SPEED:
        XTIDE_BY_SPEED[key] = []
    XTIDE_BY_SPEED[key].append((name, speed))


def find_xtide_match(utide_name, utide_speed):
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


def fetch_kartverket_year(lat, lon, year):
    """Fetch one year of hourly observations from Kartverket API. Returns list of (time_str, value_cm)."""
    url = (f"https://vannstand.kartverket.no/tideapi.php"
           f"?lat={lat}&lon={lon}"
           f"&fromtime={year}-01-01T00:00&totime={year+1}-01-01T00:00"
           f"&datatype=OBS&refcode=cd&interval=60&tzone=utc&dst=0&lang=en"
           f"&tide_request=locationdata")

    for attempt in range(3):
        try:
            if requests:
                resp = requests.get(url, timeout=120)
                xml_text = resp.text
            else:
                req = urllib.request.Request(url)
                with urllib.request.urlopen(req, timeout=120) as resp:
                    xml_text = resp.read().decode('utf-8')
            break
        except Exception as e:
            if attempt < 2:
                time.sleep(3)
                continue
            print(f"    Download error {year}: {e}")
            return []

    results = []
    try:
        root = ET.fromstring(xml_text)
        for wl in root.iter('waterlevel'):
            val = wl.get('value')
            t = wl.get('time')
            flag = wl.get('flag', '')
            if val and t and flag == 'obs':
                results.append((t, float(val)))
    except ET.ParseError as e:
        # Fallback: regex parse
        for m in re.finditer(r'<waterlevel\s+value="([^"]+)"\s+time="([^"]+)"\s+flag="obs"', xml_text):
            results.append((m.group(2), float(m.group(1))))

    return results


def download_kartverket_data(station, csv_path):
    """Download all available years for a station and save as CSV."""
    if csv_path.exists():
        df = pd.read_csv(csv_path)
        print(f"  CSV exists: {len(df)} rows")
        return csv_path

    lat, lon = station['lat'], station['lon']
    start_year = station['start']
    end_year = 2026  # current year

    all_data = []
    for year in range(start_year, end_year):
        print(f"    {year}...", end='', flush=True)
        rows = fetch_kartverket_year(lat, lon, year)
        print(f" {len(rows)}", end='', flush=True)
        all_data.extend(rows)
        time.sleep(0.5)  # Be polite to the API

    print(f"  Total: {len(all_data)}")

    if not all_data:
        return None

    csv_path.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(all_data, columns=['time', 'waterlevel_cm'])
    df.to_csv(csv_path, index=False)
    return csv_path


def load_kartverket_csv(csv_path, max_years=10.0):
    """Load Kartverket CSV (cm values) and return data dict for UTide."""
    df = pd.read_csv(csv_path)
    # Parse time - Kartverket uses ISO format with timezone
    df['time'] = pd.to_datetime(df['time'], utc=True)
    # Convert cm to meters
    df['waterlevel_m'] = df['waterlevel_cm'] / 100.0

    # Remove obvious outliers
    mean_val = df['waterlevel_m'].mean()
    std_val = df['waterlevel_m'].std()
    df = df[(df['waterlevel_m'] > mean_val - 5*std_val) &
            (df['waterlevel_m'] < mean_val + 5*std_val)].copy()

    # Remove duplicates (keep first)
    df = df.drop_duplicates(subset='time', keep='first')
    df = df.sort_values('time').reset_index(drop=True)

    # Limit to max_years from end
    max_obs = int(max_years * 365.25 * 24)
    if len(df) > max_obs:
        df = df.iloc[-max_obs:]

    n_obs = len(df)
    if n_obs < 2000:
        print(f"  Only {n_obs} obs - insufficient")
        return None

    dt_list = [t.to_pydatetime().replace(tzinfo=None) for t in df['time']]
    levels = df['waterlevel_m'].values

    first, last = dt_list[0], dt_list[-1]
    years = (last - first).total_seconds() / (365.25 * 86400)

    return {'datetimes_utc': np.array(dt_list), 'levels': np.array(levels),
            'start_time': first, 'end_time': last, 'n_obs': n_obs, 'years': years}


def harmonic_analysis_utide(datetimes_utc, levels, lat):
    try:
        coef = utide.solve(
            datetimes_utc, levels, lat=lat,
            nodal=True, trend=False, method='ols',
            conf_int='linear', verbose=False, constit='auto',
        )
    except Exception as e:
        print(f"  UTide error: {e}")
        return None

    from utide._ut_constants import ut_constants
    const_table = ut_constants['const']
    utide_names = [n.strip() for n in const_table.name]

    utide_results = {}
    for i, uname in enumerate(coef['name']):
        uname = uname.strip()
        if uname in utide_names:
            idx = utide_names.index(uname)
            utide_speed = const_table.freq[idx] * 360.0
        else:
            continue
        xt_name, xt_speed = find_xtide_match(uname, utide_speed)
        if xt_name is None:
            continue
        utide_results[xt_name] = {
            'amplitude': coef['A'][i],
            'phase': coef['g'][i] % 360,
            'snr': coef['SNR'][i] if 'SNR' in coef else 999
        }

    results = {'mean': coef['mean'], 'constituents': []}
    for name, speed in CONSTITUENTS_175:
        if name in utide_results:
            r = utide_results[name]
            results['constituents'].append({
                'name': name, 'amplitude': r['amplitude'],
                'phase': r['phase'], 'speed': speed, 'snr': r['snr']
            })
        else:
            results['constituents'].append({
                'name': name, 'amplitude': 0.0, 'phase': 0.0,
                'speed': speed, 'not_analyzed': True
            })

    try:
        reconstruction = utide.reconstruct(datetimes_utc, coef, verbose=False)
        residuals = levels - reconstruction['h']
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
    name = station['name']
    full_name = f"{name}, Norway"
    lines = []
    lines.append(f"# Harmonic constants derived from Kartverket sea level observations")
    lines.append(f"# using UTide (v{utide.__version__}) with {data['n_obs']} observations")
    lines.append(f"# from {data['start_time'].strftime('%Y-%m-%d')} to {data['end_time'].strftime('%Y-%m-%d')}")
    lines.append(f"# R^2 = {results['r_squared']:.4f}, RMS error = {results['rms_error']:.4f} m")
    lines.append(f"# Constituents analyzed: {results['n_analyzed']}")
    lines.append(f"#")
    lines.append(f"# {full_name}")
    lines.append(f"# BEGIN HOT COMMENTS")
    lines.append(f"# country: Norway")
    lines.append(f"# water body: {station['water']}")
    lines.append(f"# source: Derived from Kartverket hourly observations (station {station['code']}) with UTide harmonic analysis")
    lines.append(f"# station_id_context: Kartverket-{station['code']}")
    lines.append(f"# date_imported: {datetime.now().strftime('%Y%m%d')}")
    lines.append(f"# datum: Chart Datum")
    lines.append(f"# confidence: 8")
    lines.append(f"# !units: meters")
    lines.append(f"# !longitude: {station['lon']:.6f}")
    lines.append(f"# !latitude: {station['lat']:.6f}")
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
    data_dir = Path('/home/oliver/water_levels/Norway_Kartverket')
    template_path = Path('/home/oliver/harmonics/utide/harmonics_utide_canada_all.txt')
    output_path = Path('/home/oliver/harmonics/utide/harmonics_utide_norway.txt')

    print("=" * 70)
    print("Generate Norway Harmonics with UTide (Kartverket)")
    print(f"Stations: {len(STATIONS)}")
    print("=" * 70)

    header = read_header_from_template(template_path)
    station_blocks = []
    processed = 0
    failed = 0

    for station in STATIONS:
        code = station['code']
        name = station['name']
        print(f"\n[{code}] {name} (from {station['start']})...")

        csv_path = data_dir / f'kartverket_{code}.csv'
        result = download_kartverket_data(station, csv_path)
        if result is None:
            print(f"  No data available!")
            failed += 1
            continue

        data = load_kartverket_csv(csv_path)
        if data is None:
            failed += 1
            continue

        print(f"  {data['n_obs']} obs ({data['years']:.1f}y) from {data['start_time'].strftime('%Y-%m-%d')} to {data['end_time'].strftime('%Y-%m-%d')}")
        print(f"  Running UTide...", end='', flush=True)

        results = harmonic_analysis_utide(data['datetimes_utc'], data['levels'], station['lat'])
        if results is None:
            print(" FAILED")
            failed += 1
            continue

        m2 = next((c['amplitude'] for c in results['constituents'] if c['name'] == 'M2'), 0)
        k1 = next((c['amplitude'] for c in results['constituents'] if c['name'] == 'K1'), 0)
        s2 = next((c['amplitude'] for c in results['constituents'] if c['name'] == 'S2'), 0)
        print(f" OK (R²={results['r_squared']:.3f}, M2={m2:.3f}m, S2={s2:.3f}m, K1={k1:.3f}m, constit={results['n_analyzed']})")

        block = format_station_block(station, results, data)
        station_blocks.append(block)
        processed += 1

    print(f"\n{'='*70}")
    print(f"Processed: {processed}, Failed: {failed}")

    if not station_blocks:
        print("No stations processed!")
        return

    print(f"\nWriting {len(station_blocks)} stations to {output_path}...")
    with open(output_path, 'w', encoding='latin-1') as f:
        f.write(header)
        f.write('\n')
        for block in station_blocks:
            f.write(block)
            f.write('\n')

    print(f"Done! {output_path}")


if __name__ == "__main__":
    main()
