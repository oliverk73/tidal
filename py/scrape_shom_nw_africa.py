#!/usr/bin/env python3
"""
Scrape SHOM tide predictions for NW Africa (20 Morocco + Sfax Tunisia),
run UTide harmonic analysis, write XTide-compatible harmonics files.

SHOM API (undocumented, reverse-engineered from maree.shom.fr Ember app):
  GET https://services.data.shom.fr/b2q8lrcdl4s04cbabsj4nhcb/hdm/spm/wl
      ?harborName=<CST>&duration=<days>&date=YYYY-MM-DD&utc=0&nbWaterLevels=288
  Referer header required. Max duration=60 for /wl.
"""
import csv
import json
import time
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import utide

# ── Stations ─────────────────────────────────────────────────────────
STATIONS = [
    # Morocco — Atlantic coast (north → south)
    {'cst': 'KSAR_ES_SRHIR',  'name': 'Ksar es Sghir',        'country': 'Morocco', 'lat': 35.8420, 'lon':  -5.5705, 'water': 'Strait of Gibraltar'},
    {'cst': 'TANGER_MED',     'name': 'Tanger Med',           'country': 'Morocco', 'lat': 35.9000, 'lon':  -5.4833, 'water': 'Strait of Gibraltar'},
    {'cst': 'TANGER',         'name': 'Tanger',               'country': 'Morocco', 'lat': 35.7833, 'lon':  -5.8000, 'water': 'Strait of Gibraltar'},
    {'cst': 'MEHDIA',         'name': 'Mehdia',               'country': 'Morocco', 'lat': 34.2667, 'lon':  -6.6667, 'water': 'Atlantic Ocean'},
    {'cst': 'RABAT',          'name': 'Rabat',                'country': 'Morocco', 'lat': 34.0333, 'lon':  -6.8333, 'water': 'Atlantic Ocean'},
    {'cst': 'MOHAMMEDIA',     'name': 'Mohammedia',           'country': 'Morocco', 'lat': 33.7167, 'lon':  -7.4000, 'water': 'Atlantic Ocean'},
    {'cst': 'CASABLANCA',     'name': 'Casablanca',           'country': 'Morocco', 'lat': 33.6067, 'lon':  -7.6100, 'water': 'Atlantic Ocean'},
    {'cst': 'MAZAGAN',        'name': 'El Jadida (Mazagan)',  'country': 'Morocco', 'lat': 33.2667, 'lon':  -8.5000, 'water': 'Atlantic Ocean'},
    {'cst': 'JORF_LASFAR',    'name': 'Jorf Lasfar',          'country': 'Morocco', 'lat': 33.1333, 'lon':  -8.6333, 'water': 'Atlantic Ocean'},
    {'cst': 'SAFI',           'name': 'Safi',                 'country': 'Morocco', 'lat': 32.3083, 'lon':  -9.2500, 'water': 'Atlantic Ocean'},
    {'cst': 'SAFI_SUD',       'name': 'Nouveau Port de Safi', 'country': 'Morocco', 'lat': 32.1715, 'lon':  -9.2683, 'water': 'Atlantic Ocean'},
    {'cst': 'ESSAOUIRA',      'name': 'Essaouira (Mogador)',  'country': 'Morocco', 'lat': 31.5057, 'lon':  -9.7750, 'water': 'Atlantic Ocean'},
    {'cst': 'AGADIR',         'name': 'Agadir',               'country': 'Morocco', 'lat': 30.4233, 'lon':  -9.6417, 'water': 'Atlantic Ocean'},
    {'cst': 'TAMAJARUSH',     'name': 'Tamajarush',           'country': 'Morocco', 'lat': 29.5500, 'lon': -10.0667, 'water': 'Atlantic Ocean'},
    {'cst': 'TAN-TAN',        'name': 'Tan-Tan',              'country': 'Morocco', 'lat': 28.5000, 'lon': -11.3500, 'water': 'Atlantic Ocean'},
    {'cst': 'TARFAYA',        'name': 'Tarfaya',              'country': 'Morocco', 'lat': 27.9419, 'lon': -12.9355, 'water': 'Atlantic Ocean'},
    {'cst': 'LAAYOUNE',       'name': 'Laayoune',             'country': 'Morocco', 'lat': 27.1000, 'lon': -13.4167, 'water': 'Atlantic Ocean'},
    {'cst': 'BOUJDOUR',       'name': 'Boujdour',             'country': 'Morocco', 'lat': 26.1167, 'lon': -14.5000, 'water': 'Atlantic Ocean'},
    {'cst': 'DAKHLA',         'name': 'Dakhla',               'country': 'Morocco', 'lat': 23.6615, 'lon': -15.9410, 'water': 'Atlantic Ocean'},
    {'cst': 'EL_MHIREZ',      'name': 'El Mhirez',            'country': 'Morocco', 'lat': 22.1895, 'lon': -16.7598, 'water': 'Atlantic Ocean'},
    # Tunisia — Gulf of Gabes
    {'cst': 'SFAX',           'name': 'Sfax',                 'country': 'Tunisia', 'lat': 34.7333, 'lon':  10.7667, 'water': 'Gulf of Gabès (Mediterranean)'},
]

# ── Scraping ─────────────────────────────────────────────────────────
SHOM_WL_URL = 'https://services.data.shom.fr/b2q8lrcdl4s04cbabsj4nhcb/hdm/spm/wl'
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (compatible; harmonics-research/1.0)',
    'Referer': 'https://maree.shom.fr/',
}
START_DATE = datetime(2025, 4, 20)
BLOCK_DAYS = 60
NUM_BLOCKS = 6  # 6 × 60 = 360 days (SHOM API rejects end-dates >7d in future)
CSV_DIR = Path('/home/oliver/harmonics/help/shom_raw')
CSV_DIR.mkdir(parents=True, exist_ok=True)


def scrape_station(cst, session):
    """Download 1 year of 5-min water level data. Returns (datetimes[], levels_m[])."""
    all_samples = []  # list of (datetime, float_m)
    for i in range(NUM_BLOCKS):
        block_start = START_DATE + timedelta(days=i * BLOCK_DAYS)
        params = {
            'harborName': cst,
            'duration': BLOCK_DAYS,
            'date': block_start.strftime('%Y-%m-%d'),
            'utc': 0,
            'nbWaterLevels': 288,
        }
        for attempt in range(3):
            try:
                r = session.get(SHOM_WL_URL, params=params, headers=HEADERS, timeout=30)
                r.raise_for_status()
                data = r.json()
                break
            except Exception as e:
                if attempt == 2:
                    raise
                print(f'    retry {attempt+1} after error: {e}')
                time.sleep(5)
        for date_str, samples in data.items():
            base = datetime.strptime(date_str, '%Y-%m-%d')
            for tstr, level in samples:
                h, m, s = map(int, tstr.split(':'))
                all_samples.append((base.replace(hour=h, minute=m, second=s), float(level)))
        time.sleep(2.5)
    # Deduplicate on time (API may repeat day at block boundaries)
    seen = {}
    for dt, lv in all_samples:
        seen[dt] = lv
    sorted_items = sorted(seen.items())
    return np.array([dt for dt, _ in sorted_items]), np.array([lv for _, lv in sorted_items])


def save_csv(cst, times, levels):
    path = CSV_DIR / f'{cst}.csv'
    with open(path, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['datetime_utc', 'level_m'])
        for t, lv in zip(times, levels):
            w.writerow([t.strftime('%Y-%m-%d %H:%M:%S'), f'{lv:.3f}'])
    return path


def load_csv(cst):
    path = CSV_DIR / f'{cst}.csv'
    if not path.exists():
        return None, None
    df = pd.read_csv(path, parse_dates=['datetime_utc'])
    return df['datetime_utc'].values.astype('datetime64[s]').astype('O'), df['level_m'].values


# ── UTide analysis (adapted from generate_portugal_harmonics.py) ─────
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
UTIDE_TO_XTIDE_NAME = {'SA': 'SA-IOS', 'S1': 'S1-IOS'}
XTIDE_BY_SPEED = {}
for n, sp in CONSTITUENTS_175:
    XTIDE_BY_SPEED.setdefault(round(sp * 1000), []).append((n, sp))


def find_xtide_match(utide_name, utide_speed):
    mapped = UTIDE_TO_XTIDE_NAME.get(utide_name, utide_name)
    for xn, xsp in CONSTITUENTS_175:
        if xn == mapped:
            return xn, xsp
    key = round(utide_speed * 1000)
    for delta in (0, -1, 1):
        for xn, xsp in XTIDE_BY_SPEED.get(key + delta, []):
            if abs(xsp - utide_speed) < 0.002:
                return xn, xsp
    return None, None


def harmonic_analysis(times, levels, lat):
    try:
        coef = utide.solve(times, levels, lat=lat, nodal=True, trend=False,
                           method='ols', conf_int='linear', verbose=False, constit='auto')
    except Exception as e:
        print(f'    UTide error: {e}')
        return None
    from utide._ut_constants import ut_constants
    ct = ut_constants['const']
    names = [n.strip() for n in ct.name]
    out = {}
    for i, un in enumerate(coef['name']):
        un = un.strip()
        if un not in names:
            continue
        uspeed = ct.freq[names.index(un)] * 360.0
        xn, _ = find_xtide_match(un, uspeed)
        if xn is None:
            continue
        out[xn] = {'amp': coef['A'][i], 'phase': coef['g'][i] % 360}
    result = {'mean': coef['mean'], 'constituents': []}
    for n, sp in CONSTITUENTS_175:
        if n in out:
            result['constituents'].append({'name': n, 'amp': out[n]['amp'],
                                           'phase': out[n]['phase'], 'speed': sp})
        else:
            result['constituents'].append({'name': n, 'amp': 0.0, 'phase': 0.0,
                                           'speed': sp, 'missing': True})
    try:
        rec = utide.reconstruct(times, coef, verbose=False)
        res = levels - rec['h']
        ss_res = np.sum(res ** 2)
        ss_tot = np.sum((levels - np.mean(levels)) ** 2)
        result['r2'] = 1 - ss_res / ss_tot if ss_tot > 0 else 0
        result['rms'] = float(np.sqrt(np.mean(res ** 2)))
    except Exception:
        result['r2'], result['rms'] = 0, 0
    result['n_analyzed'] = sum(1 for c in result['constituents'] if not c.get('missing'))
    return result


def format_station_block(st, results, n_obs, start, end):
    name_line = f"{st['name']}, {st['country']}"
    lines = [
        f"# Harmonic constants derived from SHOM tide predictions",
        f"# using UTide (v{utide.__version__}) with {n_obs} observations",
        f"# from {start.strftime('%Y-%m-%d')} to {end.strftime('%Y-%m-%d')}",
        f"# R^2 = {results['r2']:.4f}, RMS error = {results['rms']:.4f} m",
        f"# Constituents analyzed: {results['n_analyzed']}",
        f"#",
        f"# {name_line}",
        f"# BEGIN HOT COMMENTS",
        f"# country: {st['country']}",
        f"# water body: {st['water']}",
        f"# source: Derived from SHOM tide predictions with UTide harmonic analysis",
        f"# station_id_context: SHOM-{st['cst']}",
        f"# date_imported: {datetime.now().strftime('%Y%m%d')}",
        f"# datum: Mean Sea Level",
        f"# confidence: 6",
        f"# !units: meters",
        f"# !longitude: {st['lon']:.4f}",
        f"# !latitude: {st['lat']:.4f}",
        name_line,
        "+00:00 :UTC",
        f"{results['mean']:.4f} meters",
    ]
    for c in results['constituents']:
        if c.get('missing') or c['amp'] < 0.00005:
            lines.append("x 0 0")
        else:
            lines.append(f"{c['name']:15s} {c['amp']:.4f}  {c['phase']:.2f}")
    return '\n'.join(lines)


def read_header(template_path):
    with open(template_path, 'r', encoding='latin-1') as f:
        return f.read().rstrip() + '\n'


# ── Main ─────────────────────────────────────────────────────────────
def main():
    template = Path('/home/oliver/harmonics/template/harmonics_template.txt')
    out_ma = Path('/home/oliver/harmonics/utide/harmonics_utide_morocco_shom.txt')
    out_tn = Path('/home/oliver/harmonics/utide/harmonics_utide_tunisia_shom.txt')

    session = requests.Session()
    header = read_header(template)
    blocks = {'Morocco': [], 'Tunisia': []}

    for st in STATIONS:
        print(f"\n[{st['cst']}] {st['name']} ({st['country']})", flush=True)
        # Step 1: scrape (if not cached)
        csv_path = CSV_DIR / f"{st['cst']}.csv"
        if csv_path.exists():
            times, levels = load_csv(st['cst'])
            print(f"  cached: {len(times)} samples", flush=True)
        else:
            try:
                times, levels = scrape_station(st['cst'], session)
            except Exception as e:
                print(f"  SCRAPE FAILED: {e}", flush=True)
                continue
            save_csv(st['cst'], times, levels)
            print(f"  scraped: {len(times)} samples → {csv_path.name}", flush=True)
        if len(times) < 2000:
            print(f"  insufficient samples, skipping", flush=True)
            continue
        # Step 2: UTide
        print(f"  running UTide…", end='', flush=True)
        res = harmonic_analysis(times, levels, st['lat'])
        if res is None:
            print(" FAILED")
            continue
        m2 = next((c['amp'] for c in res['constituents'] if c['name'] == 'M2'), 0)
        print(f" OK (R²={res['r2']:.3f}, M2={m2:.3f}m, constit={res['n_analyzed']})")
        # Step 3: format block
        block = format_station_block(st, res, len(times), times[0], times[-1])
        blocks[st['country']].append(block)

    # Step 4: write harmonics files
    for country, path in [('Morocco', out_ma), ('Tunisia', out_tn)]:
        bs = blocks[country]
        if not bs:
            continue
        with open(path, 'w', encoding='latin-1') as f:
            f.write(header)
            for b in bs:
                f.write(b + '\n')
        print(f"\nWrote {len(bs)} station(s) → {path}")


if __name__ == '__main__':
    main()
