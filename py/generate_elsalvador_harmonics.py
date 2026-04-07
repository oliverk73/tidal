#!/usr/bin/env python3
"""
Generate Harmonic Constants for El Salvador tide stations using UTide.
Sources: UHSLC (Acajutla) + IOC SLSMF (La Libertad, La Union).

Note on IOC radar data: La Libertad and La Union have radar sensors with values
in the 5-8m range (water level above a low datum). Correlation with Acajutla
confirms higher values = higher water (NOT inverted). Column-aware parser needed
to extract 'rad' column specifically (bat/prs columns also present).

Outputs 175 XTide-compatible constituents.
"""
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
import pandas as pd
import re
import time
import utide
try:
    import requests
except ImportError:
    import urllib.request
    requests = None

# ── Station definitions ──────────────────────────────────────────────
UHSLC_STATIONS = [
    {'uhslc_id': 82, 'name': 'Acajutla', 'lat': 13.5738, 'lon': -89.8381, 'water': 'Pacific Ocean'},
]

IOC_STATIONS = [
    {'ioc_code': 'lalb', 'name': 'La Libertad', 'lat': 13.4851, 'lon': -89.3190, 'water': 'Pacific Ocean',
     'start': datetime(2016, 10, 1), 'end': datetime(2026, 4, 6), 'sensor': 'rad'},
    {'ioc_code': 'laun', 'name': 'La Union', 'lat': 13.3333, 'lon': -87.8181, 'water': 'Gulf of Fonseca',
     'start': datetime(2018, 1, 1), 'end': datetime(2026, 4, 6), 'sensor': 'rad'},
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


# ── IOC data download (column-aware) ────────────────────────────────
def fetch_ioc_data(code, endtime, period=7, sensor='rad'):
    """Fetch IOC data, extracting only the specified sensor column.

    IOC HTML uses <td class=field> for column headers (not <th>).
    We find the column index by matching sensor name in the header row.
    """
    url = (f"https://www.ioc-sealevelmonitoring.org/bgraph.php"
           f"?code={code}&output=tab&period={period}&endtime={endtime}")
    if requests:
        resp = requests.get(url, timeout=30)
        html = resp.text
    else:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=30) as resp:
            html = resp.read().decode('utf-8')

    # Parse all rows (header + data are all <tr>...<td>...</td>...</tr>)
    all_rows = re.findall(r'<tr>(.*?)</tr>', html, re.DOTALL)

    # Find the header row (contains 'class=field' or 'Time')
    sensor_col = None
    for row_html in all_rows:
        cells = re.findall(r'<td[^>]*>(.*?)</td>', row_html, re.DOTALL)
        if not cells:
            continue
        # Check if this is a header row
        cell_texts = [c.strip() for c in cells]
        if any('Time' in c for c in cell_texts):
            # Found header row — find sensor column
            for i, c in enumerate(cell_texts):
                c_lower = c.lower()
                if c_lower.startswith(sensor + '(') or c_lower == sensor:
                    sensor_col = i
                    break
            break

    if sensor_col is None:
        return []

    # Parse data rows
    result = []
    for row_html in all_rows:
        cells = re.findall(r'<td[^>]*>(.*?)</td>', row_html, re.DOTALL)
        if len(cells) <= sensor_col:
            continue
        time_str = cells[0].strip()
        if not re.match(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}', time_str):
            continue
        val_str = cells[sensor_col].strip()
        # Skip empty, &nbsp;, or non-numeric values
        if not val_str or val_str == '&nbsp;' or not re.match(r'^-?[\d.]+$', val_str):
            continue
        result.append((time_str, float(val_str)))

    return result


def download_ioc_data(code, start_date, end_date, csv_path, sensor='rad'):
    if csv_path.exists():
        df = pd.read_csv(csv_path)
        print(f"  CSV exists: {len(df)} rows")
        return csv_path

    all_data = {}
    current_end = end_date
    chunk_days = 7
    total_chunks = int((end_date - start_date).days / chunk_days) + 2

    print(f"  Downloading ~{total_chunks} chunks (sensor={sensor})...")
    chunk_num = 0

    while current_end > start_date:
        chunk_num += 1
        endtime_str = current_end.strftime('%Y-%m-%d')
        if chunk_num % 10 == 1:
            print(f"  [{chunk_num}/{total_chunks}] {endtime_str}...", flush=True)

        try:
            rows = fetch_ioc_data(code, endtime_str, period=chunk_days, sensor=sensor)
            for ts, val in rows:
                if ts not in all_data:
                    all_data[ts] = val
        except Exception as e:
            print(f"  [{chunk_num}] ERROR: {e}")

        current_end -= timedelta(days=chunk_days)
        time.sleep(0.5)

    if not all_data:
        print("  NO DATA!")
        return None

    sorted_times = sorted(all_data.keys())
    df = pd.DataFrame({'time': sorted_times, 'waterlevel_m': [all_data[t] for t in sorted_times]})
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(csv_path, index=False)
    print(f"  Saved {len(df)} points: {sorted_times[0]} to {sorted_times[-1]}")
    return csv_path


# ── UHSLC data download ────────────────────────────────────────────
def download_uhslc_data(uhslc_id, csv_path):
    if csv_path.exists():
        df = pd.read_csv(csv_path, skiprows=[1])
        print(f"  CSV exists: {len(df)} rows")
        return csv_path

    url = (f"https://uhslc.soest.hawaii.edu/erddap/tabledap/global_hourly_fast.csv"
           f"?time,sea_level&uhslc_id={uhslc_id}&orderBy(%22time%22)")
    print(f"  Downloading UHSLC #{uhslc_id}...", flush=True)

    if requests:
        resp = requests.get(url, timeout=120)
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        with open(csv_path, 'w') as f:
            f.write(resp.text)
    else:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = resp.read().decode('utf-8')
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        with open(csv_path, 'w') as f:
            f.write(data)

    df = pd.read_csv(csv_path, skiprows=[1])
    print(f"  Downloaded {len(df)} rows")
    return csv_path


# ── Data loading ─────────────────────────────────────────────────────
def load_uhslc_csv(csv_path, max_years=10.0):
    df = pd.read_csv(csv_path, skiprows=[1])
    times = pd.to_datetime(df['time'], utc=True)
    levels = df['sea_level'].values / 1000.0
    valid = ~np.isnan(levels)
    times = times[valid].reset_index(drop=True)
    levels = levels[valid]
    max_obs = int(max_years * 365.25 * 24)
    if len(times) > max_obs:
        times = times.iloc[-max_obs:]
        levels = levels[-max_obs:]
    dt_list = [pd.Timestamp(t).to_pydatetime().replace(tzinfo=None) for t in times]
    n_obs = len(dt_list)
    if n_obs < 2000:
        return None
    first, last = dt_list[0], dt_list[-1]
    years = (last - first).total_seconds() / (365.25 * 86400)
    return {'datetimes_utc': np.array(dt_list), 'levels': np.array(levels),
            'start_time': first, 'end_time': last, 'n_obs': n_obs, 'years': years}


def load_ioc_csv(csv_path, invert=False):
    df = pd.read_csv(csv_path)
    df['time'] = pd.to_datetime(df['time'], utc=True)
    df = df.dropna(subset=['waterlevel_m'])
    if invert:
        df['waterlevel_m'] = -df['waterlevel_m']
    v = df['waterlevel_m']
    df = df[(v > v.mean() - 20) & (v < v.mean() + 20)].copy()
    for _ in range(2):
        v = df['waterlevel_m']
        mu, sigma = v.mean(), v.std()
        df = df[(v > mu - 4*sigma) & (v < mu + 4*sigma)].copy()
    n_before = len(pd.read_csv(csv_path))
    n_after = len(df)
    if n_before > n_after:
        print(f"  Outliers removed: {n_before - n_after} ({100*(n_before-n_after)/n_before:.1f}%)")
    df = df.set_index('time')
    df = df.resample('1h').mean().dropna()
    df = df.reset_index()
    times = df['time']
    levels = df['waterlevel_m'].values
    dt_list = [pd.Timestamp(t).to_pydatetime().replace(tzinfo=None) for t in times]
    n_obs = len(dt_list)
    if n_obs < 2000:
        print(f"  Only {n_obs} hourly obs - insufficient")
        return None
    first, last = dt_list[0], dt_list[-1]
    years = (last - first).total_seconds() / (365.25 * 86400)
    print(f"  Resampled to hourly: {n_obs} obs")
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


def format_station_block(station, results, data, source_type='UHSLC'):
    name = station['name']
    full_name = f"{name}, El Salvador"
    lines = []
    if source_type == 'UHSLC':
        src_line = f"# source: Derived from UHSLC hourly data (ID={station['uhslc_id']}) with UTide harmonic analysis"
        sid_line = f"# station_id_context: UHSLC-{station['uhslc_id']}"
    else:
        src_line = f"# source: Derived from IOC SLSMF data (code={station['ioc_code']}) with UTide harmonic analysis"
        sid_line = f"# station_id_context: IOC-{station['ioc_code']}"
    lines.append(f"# Harmonic constants derived from {'UHSLC' if source_type == 'UHSLC' else 'IOC SLSMF'} sea level data")
    lines.append(f"# using UTide (v{utide.__version__}) with {data['n_obs']} observations")
    lines.append(f"# from {data['start_time'].strftime('%Y-%m-%d')} to {data['end_time'].strftime('%Y-%m-%d')}")
    lines.append(f"# R^2 = {results['r_squared']:.4f}, RMS error = {results['rms_error']:.4f} m")
    lines.append(f"# Constituents analyzed: {results['n_analyzed']}")
    lines.append(f"#")
    lines.append(f"# {full_name}")
    lines.append(f"# BEGIN HOT COMMENTS")
    lines.append(f"# country: El Salvador")
    lines.append(f"# water body: {station['water']}")
    lines.append(f"# {src_line[2:]}")
    lines.append(f"# {sid_line[2:]}")
    lines.append(f"# date_imported: {datetime.now().strftime('%Y%m%d')}")
    lines.append(f"# datum: Mean Sea Level")
    lines.append(f"# confidence: 7")
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
    uhslc_dir = Path('/home/oliver/water_levels/ElSalvador_UHSLC')
    ioc_dir = Path('/home/oliver/water_levels/ElSalvador_IOC')
    template_path = Path('/home/oliver/harmonics/utide/harmonics_utide_canada_all.txt')
    output_path = Path('/home/oliver/harmonics/utide/harmonics_utide_elsalvador.txt')

    print("=" * 70)
    print("Generate El Salvador Harmonics with UTide")
    print("=" * 70)

    header = read_header_from_template(template_path)
    station_blocks = []
    processed = 0
    failed = 0

    # ── UHSLC Stations ──
    print(f"\n{'='*40}")
    print("UHSLC Stations")
    print(f"{'='*40}")

    for station in UHSLC_STATIONS:
        uid = station['uhslc_id']
        name = station['name']
        print(f"\n[UHSLC-{uid}] {name}...")

        csv_path = uhslc_dir / f'uhslc_{uid}.csv'
        download_uhslc_data(uid, csv_path)

        data = load_uhslc_csv(csv_path)
        if data is None:
            print("  Insufficient data")
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
        print(f" OK (R²={results['r_squared']:.3f}, M2={m2:.3f}m, K1={k1:.3f}m, constit={results['n_analyzed']})")

        block = format_station_block(station, results, data, source_type='UHSLC')
        station_blocks.append(block)
        processed += 1

    # ── IOC Stations ──
    print(f"\n{'='*40}")
    print("IOC Stations")
    print(f"{'='*40}")

    for station in IOC_STATIONS:
        code = station['ioc_code']
        name = station['name']
        sensor = station.get('sensor', 'rad')
        invert = station.get('invert', False)
        print(f"\n[IOC-{code}] {name}{'  (inverted radar)' if invert else ''}...")

        csv_path = ioc_dir / f'{code}_ioc.csv'
        result = download_ioc_data(code, station['start'], station['end'], csv_path, sensor=sensor)
        if result is None:
            failed += 1
            continue

        data = load_ioc_csv(csv_path, invert=invert)
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
        print(f" OK (R²={results['r_squared']:.3f}, M2={m2:.3f}m, K1={k1:.3f}m, constit={results['n_analyzed']})")

        block = format_station_block(station, results, data, source_type='IOC')
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
