#!/usr/bin/env python3
"""
Generate Harmonic Constants from German Pegelonline water level measurements.
Uses UTide for harmonic analysis with LAT/SKN reference level.
Reads SKN offsets from BSH E-Format files.
Outputs 175 tidal constituents compatible with XTide format.

Based on generate_germany_harmonics_175.py with LAT support.
"""
import numpy as np
from datetime import datetime, timedelta
import os
import re
import json
import zipfile
import gc
import logging
from pathlib import Path
import pandas as pd
import utide

# Setup logging
LOG_FILE = Path("/home/oliver/harmonics/utide/harmonics_generation.log")
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, mode='w', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

# Directories
WATER_LEVELS_DIR = Path("/home/oliver/water_levels/Germany")
BSH_DIR = Path("/home/oliver/harmonics/help/BSH")
ODS_FILE = Path("/home/oliver/harmonics/help/tide_stations_pegelonline.ods")
TEMPLATE_PATH = Path("/home/oliver/harmonics/classic/harmonics-dwf-20070318_no_us_no_dupes.txt")
OUTPUT_PATH = Path("/home/oliver/harmonics/utide/harmonics_germany_lat_2026-01-31.txt")

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

# Build speed-based lookup for XTide constituents
XTIDE_BY_SPEED = {}
for name, speed in CONSTITUENTS_175:
    key = round(speed * 1000)
    if key not in XTIDE_BY_SPEED:
        XTIDE_BY_SPEED[key] = []
    XTIDE_BY_SPEED[key].append((name, speed))

# Complete ZIP key mapping for all stations
ZIP_MAPPING = {
    # A
    'Altengamme': 'altengamme',
    # B
    'Bake Z': 'bakez',
    'Belum (Oste)': 'belum',
    'Borkum (Fischerbalje)': 'borkumfischerbalje',
    'Borkum (Südstrand)': 'borkumsdstrand',
    'Breitenberg (Stör)': 'breitenberg',
    'Bremen (Wilhelm-Kaisen-Brücke, Weser)': 'grosseweserbrcke',
    'Bremen-Borgfeld (Wümme)': 'borgfeld',
    'Bremen-Wasserhorst (Lesum)': 'wasserhorst',
    'Bremen-Weserwehr (Unterpegel)': 'weserwehruw',
    'Bremerhaven (Alter Leuchtturm)': 'bhvalterleuchtturm',
    'Bremervörde (Oste)': 'bremervrdeuw',
    'Brokdorf (Elbe)': 'brokdorf',
    'Brunsbüttel (Elbe)': 'brunsbttelmpm',
    'Büsum (Schleuse)': 'büsum',
    'Buttelerhörne (Hunte)': 'buttelerhrne',
    'Buxtehude (Este)': 'buxtehude',
    # C
    'Cranz (Este-Sperrwerk)': 'cranz',
    'Cuxhaven-Steubenhöft (Elbe)': 'cuxhavensteubenhft',
    # D
    'Dreyschloot (Leda)': 'dreyschloot',
    'Dukegat': 'dukegat',
    'Dwarsgat (Unterfeuer)': 'dwarsgat',
    # E
    'Eider-Sperrwerk (Außenpegel)': 'eidersperrwerkap',
    'Elsfleth Ohrt (Hunte)': 'elsflethohrt',
    'Elsmhorn Hafen (Krückau)': 'elmshornhafen',
    'Emden (Ems, Große Seeschleuse)': 'emdenneueseeschleuse',
    'Emshörn': 'emshrn',
    # F
    'Fahrenholz (Ilmenau)': 'fahrenholzup',
    'Friedrichstadt (Eider Strassenbrücke)': 'friedrichstadtstrassenbrcke',
    # G
    'Geesthacht (Elbe, Wehr, Unterpegel)': 'geesthacht',
    'Glückstadt (Elbe)': 'glckstadt',
    'Grauerort (Reede)': 'grauerortreede',
    'Grönhude (Stör)': 'grnhude',
    # H
    'Hamburg (St. Pauli)': 'stpauli',  # May not exist
    'Hechthausen': 'hechthausen',
    'Helgoland (Binnenhafen)': 'helgolandbinnenhafen',
    'Herbrum (Ems, Hafendamm)': 'herbrumhafendamm',
    'Hetlingen (Elbe)': 'hetlingen',
    'Hollersiel': 'hollersiel',
    'Hooksielplate': 'hooksielplate',
    'Horneburg (Lühe)': 'horneburg',
    'Hörnum (Sylt, Hafen)': 'hörnum',
    'Huntebrück (Hunte)': 'huntebrck',
    'Husum (Schleuse)': 'husum',
    # I
    'Ilmenau (Speerwerk Außenpegel)': 'ilmenausperrwerkap',
    'Itzehoe (Stör Hafen)': 'itzehoehafen',
    # J
    'Jade-Weser-Port': 'jadeweserport',
    # K
    'Knock (Ems)': 'knock',
    'Kollmar (Elbe)': 'kollmar',
    'Krautsand (Elbe, Reede)': 'krautsandreede',
    'Krückau-Sperrwerk (Außenpegel)': 'krckausperrwerkap',
    'Krückau-Sperrwerk (Binnenpegel)': 'krckausperrwerkbp',
    # L
    'Langeoog (Hafeneinfahrt)': 'langeoog',
    'Leda-Sperrwerk (Unterpegel)': 'ledasperrwerkup',
    'Leerort (Ems)': 'leerort',
    'Leuchtturm Alte Weser': 'leuchtturmalteweser',
    'List auf Sylt (Hafen)': 'listaufsylt',
    'Lühort (Lühe)': 'lhort',
    'Lüneburg (Ilmenau)': 'lne',
    # M
    'Mittelgrund': 'mittelgrund',
    # N
    'Niederblockland (Wümme)': 'niederblockland',
    'Nordenham (Weser, Unterfeuer)': 'nordenham',
    'Norderney (Riffgat)': 'norderneyriffgat',
    'Nordfeld (Eider, Oberwasser)': 'nordfeldoberwasser',
    # O
    'Oldenburg-Drielake (Hunte)': 'oldenburgdrielake',
    'Oslebshausen (Weser)': 'oslebshausen',
    'Osterriff (Elbe)': 'osteriffmpm',
    'Otterndorf (Elbe)': 'otterndorfmpm',
    'Over (Elbe)': 'over',
    # P
    'Papenburg (Ems)': 'papenburg',
    'Pellworm (Anleger)': 'pellwormanleger',
    'Pinnau-Sperrwerk (Außenpegel)': 'pinnausperrwerkap',
    'Pinnau-Sperrwerk (Binnenpegel)': 'pinnausperrwerkbp',
    'Pogum (Ems)': 'pogum',
    # R
    'Rechtenfleth (Weser)': 'rechtenfleth',
    'Reithörne (Hunte)': 'reithrne',
    'Rhede (Ems)': 'rhede',
    'Ritterhude (Hamme)': 'ritterhude',
    'Robbensüdsteert / Solthörn': 'robbensdsteert',
    # S
    'Scharhörn (Bake C)': 'scharhörn',
    'Scharhörnriff (Bake A)': 'bakea',
    'Schillig': 'schillig',
    'Schulau (Elbe)': 'schulau',
    'Spiekeroog (Alter Anleger)': 'spiekeroog',
    'Stadersand (Elbe)': 'stadersand',
    'Stör-Sperrwerk (Außenpegel)': 'störsperrwerkap',
    # T
    'Terborg (Ems)': 'terborg',
    'Tönning (Eider)': 'tönning',
    # U
    'Uetersen (Pinnau)': 'uetersen',
    # W
    'Wangerooge (Hafen)': 'wangeroogewest',
    'Wangerooge (Langes Riff, Nord)': 'wangeroogenord',
    'Wangerooge (Ost)': 'wangeroogeost',
    'Weener (Ems)': 'weener',
    'Wilhelmshaven (Alter Vorhafen)': 'whvaltervorhafen',
    'Wilhelmshaven (Neuer Vorhafen)': 'whvneuervorhafen',
    'Wittdün (Amrum Hafen)': 'wittdün',
    'Wittorf (Ilmenau Oberpegel)': 'wittorfop',
    # Z
    'Zehnerloch': 'zehnerloch',
    'Zollenspieker (Elbe)': 'zollenspieker',
}


def extract_bsh_info(bsh_file):
    """Extract station info and SKN offset from BSH E-Format file."""
    info = {}
    try:
        with open(bsh_file, 'r', encoding='latin-1') as f:
            for line in f:
                if line.startswith('A04#GT-Name'):
                    match = re.search(r'A04#.*?:#(.+?)#', line)
                    if match:
                        info['bsh_name'] = match.group(1).strip()
                elif line.startswith('A08#Position'):
                    # A08#Position   :#53°52'04''N   8°43'03''E WGS84#
                    match = re.search(r"(\d+).(\d+)'(\d+)''([NS])\s+(\d+).(\d+)'(\d+)''([EW])", line)
                    if match:
                        lat_d, lat_m, lat_s, lat_dir = match.groups()[:4]
                        lon_d, lon_m, lon_s, lon_dir = match.groups()[4:]
                        lat = float(lat_d) + float(lat_m)/60 + float(lat_s)/3600
                        lon = float(lon_d) + float(lon_m)/60 + float(lon_s)/3600
                        if lat_dir == 'S': lat = -lat
                        if lon_dir == 'W': lon = -lon
                        info['lat'] = lat
                        info['lon'] = lon
                elif line.startswith('D01#PNP'):
                    match = re.search(r'D01#.*?#\s*([\d.-]+)\s*#', line)
                    if match:
                        info['pnp_nhn'] = float(match.group(1))
                elif line.startswith('D02#SKN'):
                    match = re.search(r'D02#.*?#\s*([\d.-]+)\s*#', line)
                    if match:
                        info['skn_nhn'] = float(match.group(1))
                elif line.startswith('D03#SKN'):
                    match = re.search(r'D03#.*?#\s*([\d.-]+)\s*#', line)
                    if match:
                        info['skn_pnp'] = float(match.group(1))
                elif line.startswith('G01#MHW'):
                    match = re.search(r'G01#.*?#\s*([\d.-]+)\s*#', line)
                    if match:
                        info['mhw_pnp'] = float(match.group(1))
                elif line.startswith('G02#MNW'):
                    match = re.search(r'G02#.*?#\s*([\d.-]+)\s*#', line)
                    if match:
                        info['mnw_pnp'] = float(match.group(1))
    except Exception as e:
        print(f"  Error reading BSH file: {e}")
    return info


def find_xtide_match(utide_name, utide_speed):
    """Find matching XTide constituent by name or speed."""
    # Name mapping for known differences
    name_map = {
        'SA': 'SA-IOS',
        'S1': 'S1-IOS',
    }
    mapped_name = name_map.get(utide_name, utide_name)

    # Try exact name match
    for xt_name, xt_speed in CONSTITUENTS_175:
        if xt_name == mapped_name:
            return xt_name, xt_speed

    # Try speed match
    key = round(utide_speed * 1000)
    for delta in [0, -1, 1]:
        candidates = XTIDE_BY_SPEED.get(key + delta, [])
        for xt_name, xt_speed in candidates:
            if abs(xt_speed - utide_speed) < 0.002:
                return xt_name, xt_speed

    return None, None


def parse_pegelonline_zip(zip_path, sample_interval_minutes=60, use_last_n_years=10):
    """
    Parse water level data from Pegelonline ZIP file.
    Uses last N years of data (default 10 years for good harmonic analysis).
    Memory-efficient: uses deque to only keep last N years as we stream.
    Returns UTC datetime array and levels in meters (PNP reference).
    """
    import ijson  # Streaming JSON parser
    from collections import deque

    # Use deque with max length to automatically discard old samples
    max_samples = use_last_n_years * 365 * 24  # ~87600 for 10 years
    datetimes_utc = deque(maxlen=max_samples)
    levels = deque(maxlen=max_samples)
    count = 0

    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            for name in zf.namelist():
                if name.endswith(':Zone.Identifier'):
                    continue
                with zf.open(name) as f:
                    parser = ijson.items(f, 'item')
                    for entry in parser:
                        # Only process every Nth entry (hourly from minutely)
                        if count % sample_interval_minutes == 0:
                            value = entry.get('value')
                            if value is not None:
                                ts_str = entry['timestamp']
                                # Skip entries with epoch timestamp (indicates missing data)
                                if ts_str.startswith('1970-'):
                                    count += 1
                                    continue
                                try:
                                    ts_base = ts_str[:19]
                                    dt_local = datetime.strptime(ts_base, "%Y-%m-%dT%H:%M:%S")

                                    # Parse UTC offset
                                    if '+' in ts_str[19:]:
                                        offset_str = ts_str[19:].lstrip('+')
                                        offset_parts = offset_str.split(':')
                                        offset_hours = int(offset_parts[0])
                                        utc_offset = timedelta(hours=offset_hours)
                                    else:
                                        utc_offset = timedelta(hours=1)

                                    dt_utc = dt_local - utc_offset
                                    level = float(value) / 100.0
                                    datetimes_utc.append(dt_utc)
                                    levels.append(level)
                                except:
                                    pass
                        count += 1
                break
    except Exception as e:
        print(f"  Error: {e}")
        return None

    if len(datetimes_utc) < 2000:
        print(f"  Only {len(datetimes_utc)} observations")
        return None

    # Convert deque to list for numpy conversion
    dt_list = list(datetimes_utc)
    lv_list = list(levels)

    return {
        'datetimes_utc': np.array(dt_list),
        'levels': np.array(lv_list),
        'start_time': dt_list[0],
        'end_time': dt_list[-1],
        'n_obs': len(dt_list)
    }


def harmonic_analysis_utide(datetimes_utc, levels, lat):
    """Run UTide harmonic analysis and map to XTide 175 constituents."""
    # UTide accepts datetime objects directly - no conversion needed

    # Explicit constituent list for reliable analysis
    # Standard tidal constituents that should be resolvable with multi-year data
    # (Only constituents that exist in UTide's database)
    UTIDE_CONSTITUENTS = [
        'M2', 'S2', 'N2', 'K1', 'O1', 'K2', 'P1', 'Q1',  # Main 8
        'M4', 'MS4', 'MN4', 'M6', 'S4', 'M8',            # Shallow water
        'MU2', 'NU2', 'L2', '2N2', 'T2',                 # Semi-diurnal
        'J1', 'OO1', '2Q1', 'RHO1',                      # Diurnal
        'MK3', 'MO3', 'SK3', 'SO3',                      # Terdiurnal
        '2MK5', '2SK5', '2MK6', '2MS6', '2SM6', 'MSK6',  # Higher harmonics
        '3MK7', 'M3',                                    # Other
        'SA', 'SSA', 'MM', 'MF', 'MSF',                  # Long period
        'LDA2', 'EPS2', 'MKS2',                          # Additional
        'ALP1', 'CHI1', 'PHI1', 'PI1', 'PSI1',           # Minor diurnals
        'THE1', 'SIG1', 'TAU1', 'NO1', 'SO1', 'UPS1',    # Minor diurnals
        'H1', 'H2', 'MSN2', 'OQ2',                       # Additional
    ]

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
            constit=UTIDE_CONSTITUENTS,
        )
    except Exception as e:
        print(f"  UTide error: {e}")
        return None

    # Map UTide results to XTide format
    utide_results = {}
    for i, uname in enumerate(coef['name']):
        uname = uname.strip()
        amplitude = coef['A'][i]
        greenwich_phase = coef['g'][i]
        snr = coef['SNR'][i] if 'SNR' in coef else 999

        # Get UTide speed
        from utide._ut_constants import ut_constants
        const_table = ut_constants['const']
        utide_names = [n.strip() for n in const_table.name]
        if uname in utide_names:
            idx = utide_names.index(uname)
            utide_speed = const_table.freq[idx] * 360.0
        else:
            continue

        # Find matching XTide constituent
        xt_name, xt_speed = find_xtide_match(uname, utide_speed)
        if xt_name is None:
            continue

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


def format_station_block(station_name, lat, lon, water, results, data, bsh_info, skn_offset):
    """Format station block in XTide harmonics format with LAT reference."""
    mean_pnp = results['mean']
    mean_lat = mean_pnp - skn_offset

    lines = []
    lines.append(f"# Harmonic constants derived from Pegelonline water level data")
    lines.append(f"# using UTide (v{utide.__version__}) with {data['n_obs']} observations")
    lines.append(f"# Period: {data['start_time'].strftime('%Y-%m-%d')} to {data['end_time'].strftime('%Y-%m-%d')}")
    years = (data['end_time'] - data['start_time']).days / 365.25
    lines.append(f"# Duration: {years:.1f} years")
    lines.append(f"# R² = {results['r_squared']:.4f}, RMS error = {results['rms_error']:.4f} m")
    lines.append(f"# Constituents analyzed: {results['n_analyzed']}")
    lines.append(f"#")
    lines.append(f"# Reference Level Conversion (SKN = LAT):")
    if 'pnp_nhn' in bsh_info:
        lines.append(f"#   PNP unter NHN: {bsh_info['pnp_nhn']:.2f} m")
    if 'skn_nhn' in bsh_info:
        lines.append(f"#   SKN unter NHN: {bsh_info['skn_nhn']:.2f} m")
    lines.append(f"#   SKN über PNP:  {skn_offset:.2f} m")
    lines.append(f"#   Mean (PNP): {mean_pnp:.4f} m")
    lines.append(f"#   Mean (LAT): {mean_lat:.4f} m")
    if 'mhw_pnp' in bsh_info:
        lines.append(f"#   BSH MHW: {bsh_info['mhw_pnp']:.2f} m (PNP) -> {bsh_info['mhw_pnp'] - skn_offset:.2f} m (LAT)")
    if 'mnw_pnp' in bsh_info:
        lines.append(f"#   BSH MNW: {bsh_info['mnw_pnp']:.2f} m (PNP) -> {bsh_info['mnw_pnp'] - skn_offset:.2f} m (LAT)")
    lines.append(f"#")
    lines.append(f"# {station_name}")
    lines.append(f"# Water body: {water}")
    lines.append(f"# BEGIN HOT COMMENTS")
    lines.append(f"# country: Germany")
    lines.append(f"# source: Derived from Pegelonline data with UTide harmonic analysis")
    lines.append(f"# restriction: Non-commercial use only")
    lines.append(f"# date_imported: {datetime.now().strftime('%Y%m%d')}")
    lines.append(f"# datum: LAT (Lowest Astronomical Tide / SKN)")
    lines.append(f"# confidence: 8")
    lines.append(f"# !units: meters")
    lines.append(f"# !longitude: {lon:.4f}")
    lines.append(f"# !latitude: {lat:.4f}")

    lines.append(f"{station_name}, Germany")
    lines.append(f"+00:00 :Europe/Berlin")
    lines.append(f"{mean_lat:.4f} meters")

    for c in results['constituents']:
        if c.get('not_analyzed') or c['amplitude'] < 0.00005:
            lines.append(f"x 0 0")
        else:
            lines.append(f"{c['name']:15s} {c['amplitude']:.4f}  {c['phase']:.2f}")

    return '\n'.join(lines)


def read_header_from_template(template_path):
    """Read header from template file."""
    with open(template_path, 'r', encoding='latin-1') as f:
        lines = f.readlines()

    header_lines = []
    end_count = 0

    for line in lines:
        stripped = line.strip()
        if stripped == '*END*':
            end_count += 1
            header_lines.append(line.rstrip())
            continue

        if end_count >= 2:
            if stripped and not stripped.startswith('#'):
                break
            header_lines.append(line.rstrip())
        else:
            header_lines.append(line.rstrip())

    return '\n'.join(header_lines)


def main():
    print("=" * 70)
    print("Generate Germany Harmonics with LAT Reference")
    print("=" * 70)

    # Read station list from ODS
    print(f"\nReading station list from {ODS_FILE.name}...")
    df = pd.read_excel(ODS_FILE, engine='odf')

    # Process ALL stations with BSH files
    df_with_bsh = df[df['Datei'].notna()]
    stations_df = df_with_bsh[['Station', 'Latitude', 'Longitude', 'Datei']]
    print(f"Processing {len(stations_df)} stations with BSH files")

    # Read header from template
    print(f"\nReading header from {TEMPLATE_PATH.name}...")
    header = read_header_from_template(TEMPLATE_PATH)

    # Build ZIP lookup
    zip_files = list(WATER_LEVELS_DIR.glob("pegelonline-*.zip"))
    zip_files = [f for f in zip_files if 'Zone.Identifier' not in str(f)]

    # Also check parent directory for new files
    zip_files_parent = list(Path("/home/oliver/water_levels").glob("pegelonline-*.zip"))
    zip_files_parent = [f for f in zip_files_parent if 'Zone.Identifier' not in str(f)]
    zip_files.extend(zip_files_parent)

    zip_lookup = {}
    for zf in zip_files:
        parts = zf.stem.split('-')
        if len(parts) >= 2:
            zip_lookup[parts[1].lower()] = zf

    print(f"Found {len(zip_lookup)} water level files")

    # Process stations
    print("\n" + "=" * 70)
    print("Processing Stations")
    print("=" * 70)

    station_blocks = []
    processed = 0
    failed = 0

    # Track errors for summary
    errors = {
        'no_bsh_file': [],
        'bsh_not_found': [],
        'no_skn_offset': [],
        'no_coordinates': [],
        'no_zip_file': [],
        'data_load_failed': [],
        'utide_failed': [],
    }
    successful = []

    logging.info(f"Starting processing of {len(stations_df)} stations")

    for idx, (i, row) in enumerate(stations_df.iterrows()):
        station_name = row['Station'].replace(', Germany', '').strip()
        # Ensure lat/lon are floats (ODS sometimes stores as strings)
        try:
            lat = float(row['Latitude'])
            lon = float(row['Longitude'])
        except (ValueError, TypeError):
            lat = None
            lon = None
        bsh_file = row['Datei']

        print(f"\n[{idx+1}/{len(stations_df)}] {station_name}")

        # Check for BSH file
        if pd.isna(bsh_file):
            msg = f"No BSH file specified"
            print(f"  ⚠ {msg}")
            logging.warning(f"{station_name}: {msg}")
            errors['no_bsh_file'].append(station_name)
            failed += 1
            continue

        bsh_path = BSH_DIR / bsh_file
        if not bsh_path.exists():
            msg = f"BSH file not found: {bsh_file}"
            print(f"  ⚠ {msg}")
            logging.warning(f"{station_name}: {msg}")
            errors['bsh_not_found'].append(station_name)
            failed += 1
            continue

        # Extract BSH info
        bsh_info = extract_bsh_info(bsh_path)
        skn_offset = bsh_info.get('skn_pnp')
        if skn_offset is None:
            msg = f"No SKN offset (D03) in BSH file"
            print(f"  ⚠ {msg}")
            logging.warning(f"{station_name}: {msg}")
            errors['no_skn_offset'].append(station_name)
            failed += 1
            continue

        # Use BSH coordinates if ODS has NaN
        if pd.isna(lat) or pd.isna(lon):
            if 'lat' in bsh_info and 'lon' in bsh_info:
                lat = bsh_info['lat']
                lon = bsh_info['lon']
                print(f"  Using BSH coordinates: {lat:.4f}, {lon:.4f}")
            else:
                msg = f"No coordinates in ODS or BSH file"
                print(f"  ⚠ {msg}")
                logging.warning(f"{station_name}: {msg}")
                errors['no_coordinates'].append(station_name)
                failed += 1
                continue

        print(f"  BSH: SKN über PNP = {skn_offset:.2f} m")

        # Find ZIP file
        zip_key = ZIP_MAPPING.get(station_name)
        if zip_key and zip_key.lower() in zip_lookup:
            zip_file = zip_lookup[zip_key.lower()]
        else:
            # Try fuzzy match
            norm_name = station_name.lower().replace('ä','a').replace('ö','o').replace('ü','u').replace('ß','ss')
            norm_name = re.sub(r'[^a-z0-9]', '', norm_name)
            zip_file = None
            for key, zf in zip_lookup.items():
                if key in norm_name or norm_name in key:
                    zip_file = zf
                    break

        if zip_file is None:
            msg = f"No ZIP file found (tried key: {zip_key})"
            print(f"  ⚠ {msg}")
            logging.warning(f"{station_name}: {msg}")
            errors['no_zip_file'].append(station_name)
            failed += 1
            continue

        print(f"  ZIP: {zip_file.name}")

        # Load water level data
        data = parse_pegelonline_zip(zip_file, sample_interval_minutes=60)
        if data is None:
            msg = f"Failed to load water level data from {zip_file.name}"
            print(f"  ⚠ {msg}")
            logging.warning(f"{station_name}: {msg}")
            errors['data_load_failed'].append(station_name)
            failed += 1
            continue

        years = (data['end_time'] - data['start_time']).days / 365.25
        print(f"  Data: {data['n_obs']} obs, {years:.1f} years ({data['start_time'].year}-{data['end_time'].year})")

        # Run UTide analysis
        results = harmonic_analysis_utide(data['datetimes_utc'], data['levels'], lat)
        if results is None:
            msg = f"UTide harmonic analysis failed"
            print(f"  ⚠ {msg}")
            logging.warning(f"{station_name}: {msg}")
            errors['utide_failed'].append(station_name)
            failed += 1
            continue

        # Find M2 amplitude
        m2_amp = 0
        for c in results['constituents']:
            if c['name'] == 'M2':
                m2_amp = c['amplitude']
                break

        mean_lat = results['mean'] - skn_offset
        print(f"  UTide: R²={results['r_squared']:.3f}, M2={m2_amp:.3f}m, {results['n_analyzed']} constituents")
        print(f"  Mean: {results['mean']:.3f}m (PNP) -> {mean_lat:.3f}m (LAT)")

        # Determine water body from station name
        water = "German Bight"
        if "Elbe" in station_name or "Hamburg" in station_name:
            water = "Elbe"
        elif "Weser" in station_name or "Bremen" in station_name:
            water = "Weser"
        elif "Ems" in station_name or "Emden" in station_name:
            water = "Ems"
        elif "Oste" in station_name:
            water = "Oste"
        elif "Stör" in station_name:
            water = "Stör"
        elif "Eider" in station_name:
            water = "Eider"
        elif "Hunte" in station_name:
            water = "Hunte"
        elif "Ilmenau" in station_name:
            water = "Ilmenau"

        # Format block
        block = format_station_block(station_name, lat, lon, water, results, data, bsh_info, skn_offset)
        station_blocks.append(block)
        processed += 1
        successful.append({
            'name': station_name,
            'r_squared': results['r_squared'],
            'm2_amp': m2_amp,
            'mean_lat': mean_lat,
            'n_obs': data['n_obs'],
            'years': years
        })
        logging.info(f"{station_name}: OK (R²={results['r_squared']:.3f}, M2={m2_amp:.3f}m)")
        print(f"  ✓ OK")

        # Free memory
        del data, results
        gc.collect()

    # Write output
    print(f"\n{'='*70}")
    print(f"Processed: {processed}, Failed: {failed}")

    print(f"\nWriting output to {OUTPUT_PATH}...")
    with open(OUTPUT_PATH, 'w', encoding='latin-1') as f:
        f.write(header)
        f.write('\n')
        for block in station_blocks:
            f.write(block)
            f.write('\n')

    print(f"Done! Created {OUTPUT_PATH}")
    print(f"Total stations: {len(station_blocks)}")


if __name__ == "__main__":
    main()
