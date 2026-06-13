#!/usr/bin/env python3
"""UTide harmonic analysis for Dutch RWS tidal currents.

For each station the (speed, direction) time series is converted to
complex velocity u+iv, projected onto the principal flood/ebb axis
(via PCA) to obtain a signed scalar speed, and analyzed with UTide.
The result is written in XTide harmonics format with units=knots and
station_type=current.
"""
import sys, os, json, glob, time, pickle, gc
sys.path.insert(0, '/home/oliver/py')
from pathlib import Path
import numpy as np
import pandas as pd
import utide

from generate_germany_harmonics_175 import (
    CONSTITUENTS_175, find_xtide_match, read_header_from_template,
)

CSV_DIR       = Path('/home/oliver/currents/Netherlands')
META_PATH     = CSV_DIR / '_stations.json'
TEMPLATE_PATH = Path('/home/oliver/harmonics/utide/harmonics_utide_canada_all.txt')
OUTPUT_PATH   = Path('/home/oliver/harmonics/utide/harmonics_utide_netherlands_currents.txt')
CHECKPOINT    = Path('/home/oliver/harmonics/utide/checkpoints_nl_currents')

CONSTIT_67 = [
    'K1','O1','P1','Q1','J1','OO1','2Q1','RHO1','NO1','CHI1','PI1','PHI1',
    'PSI1','SIG1','THE1','SO1','M2','S2','N2','K2','L2','2N2','R2','T2',
    'LDA2','MU2','NU2','EPS2','ETA2','MF','MSF','MM','SA','SSA','MSM',
    'M3','MK3','MO3','SK3','SO3','M4','MN4','MS4','MK4','S4','SN4',
    'M6','2MS6','2MN6','M8','H1','H2','S1','ALP1','BET1','TAU1','UPS1',
    '2SM2','OP2','MKS2','SKM2','NO3','N4','3MS4','2MK5','2SK5','2MK6','MSK6',
]

MS_TO_KNOTS = 1.94384449


def load_csv(path):
    df = pd.read_csv(path, parse_dates=['time'], index_col='time')
    df = df[(df['speed'].abs() < 100) & df['direction'].between(0, 360)]
    df = df.dropna()
    df = df[~df.index.duplicated(keep='first')]
    df.index = df.index.tz_convert('UTC').tz_localize(None)
    df = df.sort_index()
    return df


def to_uv(df):
    rad = np.deg2rad(df['direction'].values)
    u = df['speed'].values * np.sin(rad)
    v = df['speed'].values * np.cos(rad)
    return u, v


def principal_axis(u, v):
    """Return angle (deg, 0=N) of major flood/ebb axis via PCA."""
    cov = np.cov(np.vstack([u, v]))
    w, V = np.linalg.eigh(cov)
    a = V[:, np.argmax(w)]
    return float(np.rad2deg(np.arctan2(a[0], a[1])) % 180.0)


def project(u, v, axis_deg):
    rad = np.deg2rad(axis_deg)
    return u * np.sin(rad) + v * np.cos(rad)


def analyze(code, meta, csv_path):
    ck = CHECKPOINT / f'{code.replace("/","_").replace(" ","_")}.pkl'
    if ck.exists():
        with open(ck, 'rb') as f: r = pickle.load(f)
        print(f"  Checkpoint R²={r['r_squared']:.4f}")
        return r

    t0 = time.time()
    df = load_csv(csv_path)
    if len(df) < 4380:  # < ~1 month of 10-min data
        print(f"  zu wenig Daten ({len(df)})"); return None

    u, v = to_uv(df)
    axis = principal_axis(u, v)
    scal = project(u, v, axis) * MS_TO_KNOTS  # knots
    times = df.index.to_pydatetime()

    print(f"  {len(df)} Punkte, Hauptachse {axis:.1f}°, |v|max={np.abs(scal).max():.2f}kn")

    try:
        # constit='auto' (Rayleigh): feste CONSTIT_67-Liste über die kurzen
        # ~140-Tage-RWS-Records erzeugte nicht trennbare, sich aufhebende
        # Diurnal-Paare (S1/K1/P1/PSI1/PI1/PHI1) -> OOW-Divergenz. Siehe
        # SHOA-Chile-Bug. Auto wählt nur Rayleigh-auflösbare Konstituenten.
        coef = utide.solve(times, scal, lat=meta['lat'],
                           nodal=True, trend=False, method='ols',
                           conf_int='none', verbose=False, constit='auto')
    except Exception as e:
        print(f"  UTide FEHLER: {e}"); return None

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

    constituents = []
    n_an = 0
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
    print(f"  R²={r_sq:.4f} RMS={rms:.4f}kn M2={m2:.4f}kn K1={k1:.4f}kn ({result['duration']:.0f}s)")
    return result


def fmt_block(r):
    name = r['name']
    L = []
    L.append(f"# Harmonic constants derived from RWS current measurements")
    L.append(f"# (UTide v{utide.__version__}, principal-axis projection)")
    L.append(f"# {r['n_obs']} 10-min samples")
    L.append(f"# from {r['start_time'].strftime('%Y-%m-%d')} to {r['end_time'].strftime('%Y-%m-%d')}")
    L.append(f"# R^2 = {r['r_squared']:.4f}, RMS error = {r['rms_error']:.4f} knots")
    L.append(f"# Constituents analyzed: {r['n_analyzed']}")
    L.append(f"# Major axis: {r['axis_deg']:.1f} deg true")
    L.append(f"#")
    L.append(f"# {name}, Netherlands Current")
    L.append(f"# BEGIN HOT COMMENTS")
    L.append(f"# country: Netherlands")
    L.append(f"# source: Rijkswaterstaat Waterinfo (DDL/ddlpy), UTide analysis")
    L.append(f"# station_id_context: RWS-{r['code']}")
    L.append(f"# datum: n/a")
    L.append(f"# station_type: current")
    L.append(f"# major_axis_deg_true: {r['axis_deg']:.1f}")
    L.append(f"# confidence: 8")
    L.append(f"# !units: knots")
    L.append(f"# !longitude: {r['lon']:.6f}")
    L.append(f"# !latitude: {r['lat']:.6f}")
    L.append(f"{name}, Netherlands Current")
    L.append(f"+00:00 :UTC")
    L.append(f"{r['mean']:.4f} knots")
    for c in r['constituents']:
        if c.get('not_analyzed') or c['amplitude'] < 0.00005:
            L.append("x 0 0")
        else:
            L.append(f"{c['name']:15s} {c['amplitude']:.4f}  {c['phase']:.2f}")
    return '\n'.join(L)


def main():
    CHECKPOINT.mkdir(parents=True, exist_ok=True)
    with open(META_PATH) as f: meta = json.load(f)

    csvs = sorted(glob.glob(str(CSV_DIR / '*.csv')))
    csvs = [c for c in csvs if not c.endswith('_stations.json')]
    print(f"RWS Currents — {len(csvs)} CSVs\n")

    results, errors = [], []
    for i, p in enumerate(csvs):
        safe = os.path.basename(p)[:-4]
        code = next((c for c in meta if c.replace('/','_').replace(' ','_').replace('\\','_')==safe), None)
        if code is None:
            print(f"[{i+1}/{len(csvs)}] {safe} — kein Metadaten-Match"); errors.append(safe); continue
        m = meta[code]
        print(f"[{i+1}/{len(csvs)}] {code} | {m['name']} ({m['lat']:.4f},{m['lon']:.4f})")
        try:
            r = analyze(code, m, p)
        except Exception as e:
            print(f"  AUSNAHME: {e}"); r = None
        if r: results.append(r)
        else: errors.append(safe)

    if results:
        h = read_header_from_template(TEMPLATE_PATH)
        with open(OUTPUT_PATH, 'w', encoding='iso-8859-1') as f:
            f.write(h); f.write('\n')
            for r in results:
                f.write(fmt_block(r)); f.write('\n')
        print(f"\nGeschrieben: {OUTPUT_PATH.name} ({len(results)} Stationen)")
        for r in sorted(results, key=lambda x:-x['m2_amp']):
            print(f"  {r['name']:<40s} R²={r['r_squared']:.4f} M2={r['m2_amp']:.3f}kn axis={r['axis_deg']:5.1f}°")

    if errors:
        print(f"\n{len(errors)} ohne Ergebnis: {', '.join(errors[:10])}{'...' if len(errors)>10 else ''}")


if __name__ == '__main__':
    main()
