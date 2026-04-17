#!/usr/bin/env python3
"""UTide harmonics for all European CMEMS current stations (country-agnostic).

Processes every currents/<Country>/ directory that has no existing
harmonics_utide_<country>_currents.txt. Skips Germany/Netherlands/Belgium/Canada
(already done) and _unclassified.

Writes one harmonics_utide_<country>_currents.txt per country.
"""
import sys, os, json, glob, time, pickle, argparse
sys.path.insert(0, '/home/oliver/py')
from pathlib import Path
import numpy as np
import pandas as pd
import utide

from generate_germany_harmonics_175 import (
    CONSTITUENTS_175, find_xtide_match, read_header_from_template,
)

CURRENTS_ROOT = Path('/home/oliver/currents')
HARMONICS_DIR = Path('/home/oliver/harmonics/utide')
TEMPLATE_PATH = HARMONICS_DIR / 'harmonics_utide_canada_all.txt'
CHECKPOINT_ROOT = HARMONICS_DIR / 'checkpoints_eu_currents'

SKIP_DIRS = {
    'cmems_raw', '_unclassified',
    'Germany', 'Netherlands', 'Belgium',
    'Canada_CHS_measured', 'Canada_CHS_predicted',
}

# Country-dir -> nice label for harmonics header / station line
COUNTRY_LABEL = {
    'Denmark': 'Denmark',
    'France_Atlantic': 'France',
    'France_Channel': 'France',
    'France_Med': 'France',
    'Ireland': 'Ireland',
    'Norway': 'Norway',
    'Portugal': 'Portugal',
    'Portugal_Offshore': 'Portugal',
    'Spain_Atlantic': 'Spain',
    'Spain_Med': 'Spain',
    'UK': 'United Kingdom',
    'Australia_IMOS': 'Australia',
}

CONSTIT_67 = [
    'K1','O1','P1','Q1','J1','OO1','2Q1','RHO1','NO1','CHI1','PI1','PHI1',
    'PSI1','SIG1','THE1','SO1','M2','S2','N2','K2','L2','2N2','R2','T2',
    'LDA2','MU2','NU2','EPS2','ETA2','MF','MSF','MM','SA','SSA','MSM',
    'M3','MK3','MO3','SK3','SO3','M4','MN4','MS4','MK4','S4','SN4',
    'M6','2MS6','2MN6','M8','H1','H2','S1','ALP1','BET1','TAU1','UPS1',
    '2SM2','OP2','MKS2','SKM2','NO3','N4','3MS4','2MK5','2SK5','2MK6','MSK6',
]

MS_TO_KNOTS = 1.94384449
MIN_POINTS = 4380   # ~6 months hourly


def load_csv(path):
    df = pd.read_csv(path)
    df['time'] = pd.to_datetime(df['time'], errors='coerce', utc=True)
    df = df.dropna(subset=['time'])
    df.index = df['time'].dt.tz_convert('UTC').dt.tz_localize(None)
    df = df.drop(columns=['time'])
    df = df[(df['speed'].abs() < 15) & df['direction'].between(0, 360)]
    df = df.dropna()
    df = df[~df.index.duplicated(keep='first')]
    return df.sort_index()


def to_uv(df):
    rad = np.deg2rad(df['direction'].values)
    u = df['speed'].values * np.sin(rad)
    v = df['speed'].values * np.cos(rad)
    return u, v


def principal_axis(u, v):
    cov = np.cov(np.vstack([u, v]))
    w, V = np.linalg.eigh(cov)
    a = V[:, np.argmax(w)]
    return float(np.rad2deg(np.arctan2(a[0], a[1])) % 180.0)


def project(u, v, axis_deg):
    rad = np.deg2rad(axis_deg)
    return u * np.sin(rad) + v * np.cos(rad)


def analyze(code, meta, csv_path, checkpoint_dir):
    ck = checkpoint_dir / f'{code}.pkl'
    if ck.exists():
        with open(ck, 'rb') as f: r = pickle.load(f)
        print(f"    checkpoint R²={r['r_squared']:.4f}")
        return r

    t0 = time.time()
    df = load_csv(csv_path)
    if len(df) < MIN_POINTS:
        print(f"    too little data ({len(df)})"); return None

    u, v = to_uv(df)
    axis = principal_axis(u, v)
    scal = project(u, v, axis) * MS_TO_KNOTS
    times = df.index.to_pydatetime()

    print(f"    {len(df)} pts, axis {axis:.1f}°, |v|max={np.abs(scal).max():.2f}kn")

    try:
        coef = utide.solve(times, scal, lat=meta['lat'],
                           nodal=True, trend=False, method='ols',
                           conf_int='none', verbose=False, constit=CONSTIT_67)
    except Exception as e:
        print(f"    UTide error: {e}"); return None

    from utide._ut_constants import ut_constants
    table = ut_constants['const']
    names = [n.strip() for n in table.name]

    mapped = {}
    for i, uname in enumerate(coef['name']):
        uname = uname.strip()
        if uname not in names: continue
        idx = names.index(uname)
        speed = table.freq[idx] * 360.0
        xt_name, xt_speed = find_xtide_match(uname, speed)
        if xt_name is None: continue
        mapped[xt_name] = (float(coef['A'][i]), float(coef['g'][i]) % 360, xt_speed)

    constituents, n_an = [], 0
    for cname, sp in CONSTITUENTS_175:
        if cname in mapped:
            a, g, _ = mapped[cname]
            constituents.append({'name':cname,'amplitude':a,'phase':g,'speed':sp})
            n_an += 1
        else:
            constituents.append({'name':cname,'amplitude':0.0,'phase':0.0,
                                 'speed':sp,'not_analyzed':True})

    rec = utide.reconstruct(times, coef, verbose=False)
    res = scal - rec['h']
    ss_tot = np.sum((scal - scal.mean())**2)
    r_sq = 1 - np.sum(res**2)/ss_tot if ss_tot>0 else 0
    rms = float(np.sqrt(np.mean(res**2)))

    m2 = next((c['amplitude'] for c in constituents if c['name']=='M2'), 0)
    k1 = next((c['amplitude'] for c in constituents if c['name']=='K1'), 0)

    result = {
        'code': code, 'name': meta['name'], 'lat': meta['lat'], 'lon': meta['lon'],
        'mean': float(coef['mean']), 'axis_deg': axis, 'constituents': constituents,
        'n_analyzed': n_an, 'r_squared': float(r_sq), 'rms_error': rms,
        'm2_amp': float(m2), 'k1_amp': float(k1),
        'n_obs': len(df), 'start_time': df.index[0], 'end_time': df.index[-1],
        'duration': time.time()-t0,
    }
    with open(ck,'wb') as f: pickle.dump(result, f)
    print(f"    R²={r_sq:.4f} RMS={rms:.4f}kn M2={m2:.4f}kn K1={k1:.4f}kn ({result['duration']:.0f}s)")
    return result


def fmt_block(r, country_label):
    name = r['name']
    L = []
    L.append(f"# Harmonic constants derived from CMEMS in-situ currents")
    L.append(f"# (UTide v{utide.__version__}, principal-axis projection)")
    L.append(f"# {r['n_obs']} samples")
    L.append(f"# from {r['start_time'].strftime('%Y-%m-%d')} to {r['end_time'].strftime('%Y-%m-%d')}")
    L.append(f"# R^2 = {r['r_squared']:.4f}, RMS error = {r['rms_error']:.4f} knots")
    L.append(f"# Constituents analyzed: {r['n_analyzed']}")
    L.append(f"# Major axis: {r['axis_deg']:.1f} deg true")
    L.append(f"#")
    L.append(f"# {name}, {country_label} Current")
    L.append(f"# BEGIN HOT COMMENTS")
    L.append(f"# country: {country_label}")
    L.append(f"# source: CMEMS in-situ, UTide analysis")
    L.append(f"# station_id_context: CMEMS-{r['code']}")
    L.append(f"# datum: n/a")
    L.append(f"# station_type: current")
    L.append(f"# major_axis_deg_true: {r['axis_deg']:.1f}")
    conf = 8 if r['r_squared'] > 0.7 else 5
    L.append(f"# confidence: {conf}")
    L.append(f"# !units: knots")
    L.append(f"# !longitude: {r['lon']:.6f}")
    L.append(f"# !latitude: {r['lat']:.6f}")
    L.append(f"{name}, {country_label} Current")
    L.append(f"+00:00 :UTC")
    L.append(f"{r['mean']:.4f} knots")
    for c in r['constituents']:
        if c.get('not_analyzed') or c['amplitude'] < 0.00005:
            L.append("x 0 0")
        else:
            L.append(f"{c['name']:15s} {c['amplitude']:.4f}  {c['phase']:.2f}")
    return '\n'.join(L)


def country_output_stem(country_dir):
    # France_Atlantic -> france_atlantic, UK -> uk
    return country_dir.lower()


def process_country(country_dir, force=False):
    csv_dir = CURRENTS_ROOT / country_dir
    meta_path = csv_dir / '_stations.json'
    if not meta_path.exists():
        print(f"[{country_dir}] no _stations.json, skip")
        return 0

    stem = country_output_stem(country_dir)
    out_path = HARMONICS_DIR / f'harmonics_utide_{stem}_currents.txt'
    if out_path.exists() and not force:
        print(f"[{country_dir}] {out_path.name} exists, skip (--force to rebuild)")
        return 0

    ck_dir = CHECKPOINT_ROOT / country_dir
    ck_dir.mkdir(parents=True, exist_ok=True)

    with open(meta_path) as f: meta = json.load(f)
    csvs = sorted(glob.glob(str(csv_dir / '*.csv')))
    if not csvs:
        print(f"[{country_dir}] no CSVs"); return 0

    label = COUNTRY_LABEL.get(country_dir, country_dir.replace('_', ' '))
    print(f"\n=== {country_dir} ({label}) — {len(csvs)} CSVs ===")

    results, errors = [], []
    for i, p in enumerate(csvs):
        code = os.path.basename(p)[:-4]
        if code not in meta:
            print(f"  [{i+1}/{len(csvs)}] {code} — no meta"); errors.append(code); continue
        m = meta[code]
        print(f"  [{i+1}/{len(csvs)}] {code} | {m['name']} ({m['lat']:.3f},{m['lon']:.3f})")
        try:
            r = analyze(code, m, p, ck_dir)
        except Exception as e:
            print(f"    EXCEPTION: {e}"); r = None
        if r: results.append(r)
        else: errors.append(code)

    if results:
        h = read_header_from_template(TEMPLATE_PATH)
        with open(out_path, 'w', encoding='iso-8859-1') as f:
            f.write(h); f.write('\n')
            for r in results:
                f.write(fmt_block(r, label)); f.write('\n')
        print(f"  -> {out_path.name} ({len(results)} stations)")
    if errors:
        print(f"  {len(errors)} without result: {errors}")
    return len(results)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--country', help='process only this country dir')
    ap.add_argument('--force', action='store_true', help='rebuild even if output exists')
    args = ap.parse_args()

    CHECKPOINT_ROOT.mkdir(parents=True, exist_ok=True)

    if args.country:
        dirs = [args.country]
    else:
        dirs = sorted(d.name for d in CURRENTS_ROOT.iterdir()
                      if d.is_dir() and d.name not in SKIP_DIRS)

    total = 0
    for d in dirs:
        total += process_country(d, force=args.force)
    print(f"\nTotal stations analyzed: {total}")


if __name__ == '__main__':
    main()
