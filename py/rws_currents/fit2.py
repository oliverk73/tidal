#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Qualitaetsgesteuerter RWS-Stroemungs-Fit.
- Einheit aus Datenmagnitude ableiten (Label 'm/s' unzuverlaessig).
- Flags raus (dir 9999, NaN), Ausreisser per physikalischem Cap + MAD.
- bestes sauberes Einzelfenster (laengste dichte ~Jahresspanne) statt Mehrjahres-Verkettung.
- principal-axis Projektion, UTide robust + constit='auto'.
- Rueckgabe inkl. R^2 -> Aufrufer entscheidet confidence/drop.
"""
import sys
import numpy as np, pandas as pd, utide
sys.path.insert(0, '/home/oliver/py')
from generate_germany_harmonics_175 import CONSTITUENTS_175, find_xtide_match

MS_TO_KNOTS = 1.94384449
PHYS_CAP_MS = 4.0   # Tidenstrom real selten >4 m/s


def load(path):
    df = pd.read_csv(path, parse_dates=['time'], index_col='time')
    df = df.dropna(subset=['speed', 'direction'])
    df = df[df['direction'].between(0, 360)]          # 9999.9-Flags raus
    df = df[~df.index.duplicated(keep='first')]
    df.index = df.index.tz_convert('UTC').tz_localize(None)
    return df.sort_index()


def infer_scale(speed_abs):
    """m/s zurueck. Wenn Median|.| gross -> cm/s -> /100."""
    med = np.median(speed_abs[speed_abs > 0]) if (speed_abs > 0).any() else 0
    return 0.01 if med > 10 else 1.0   # >10 => cm/s


def best_window(df, days=365, step=30):
    """Laengstes dichtes Fenster: gleitend, waehle Start mit meisten Punkten in [t,t+days]."""
    if len(df) == 0:
        return df
    t0, t1 = df.index[0], df.index[-1]
    span = (t1 - t0).days
    if span <= days:
        return df
    best, bestn = None, -1
    s = t0
    from datetime import timedelta
    while s <= t1 - timedelta(days=days):
        w = df.loc[s:s + timedelta(days=days)]
        if len(w) > bestn:
            bestn, best = len(w), w
        s += timedelta(days=step)
    return best


def to_scalar(df, scale):
    rad = np.deg2rad(df['direction'].values)
    sp = df['speed'].values * scale            # m/s
    u = sp * np.sin(rad); v = sp * np.cos(rad)
    # Ausreisser: physikalischer Cap + MAD auf Betrag
    mag = np.hypot(u, v)
    med = np.median(mag); mad = np.median(np.abs(mag - med)) + 1e-9
    keep = (mag < PHYS_CAP_MS) & (mag < med + 8 * 1.4826 * mad)
    return u[keep], v[keep], df.index.values[keep]


def principal_axis(u, v):
    cov = np.cov(np.vstack([u, v]))
    w, V = np.linalg.eigh(cov)
    a = V[:, np.argmax(w)]
    return float(np.rad2deg(np.arctan2(a[0], a[1])) % 180.0)


def fit(path, lat, name, code):
    df = load(path)
    if len(df) < 4380:
        return {'code': code, 'name': name, 'error': f'zu wenig Daten roh ({len(df)})'}
    scale = infer_scale(df['speed'].abs().values)
    w = best_window(df)
    u, v, times = to_scalar(w, scale)
    if len(times) < 4380:
        return {'code': code, 'name': name, 'error': f'zu wenig nach Filter ({len(times)})'}
    axis = principal_axis(u, v)
    rad = np.deg2rad(axis)
    scal = (u * np.sin(rad) + v * np.cos(rad)) * MS_TO_KNOTS   # knots
    tpy = pd.to_datetime(times).to_pydatetime()
    coef = utide.solve(tpy, scal, lat=lat, nodal=True, trend=False,
                       method='robust', conf_int='none', verbose=False, constit='auto')
    rec = utide.reconstruct(tpy, coef, verbose=False)['h']
    res = scal - rec
    sstot = np.sum((scal - scal.mean())**2)
    r2 = float(1 - np.sum(res**2)/sstot) if sstot > 0 else 0.0
    rms = float(np.sqrt(np.mean(res**2)))

    from utide._ut_constants import ut_constants
    table = ut_constants['const']; names = [n.strip() for n in table.name]
    cm = {}
    for i, un in enumerate(coef['name']):
        un = un.strip()
        if un not in names:
            continue
        xt, _ = find_xtide_match(un, table.freq[names.index(un)] * 360.0)
        if xt:
            cm[xt] = (float(coef['A'][i]), float(coef['g'][i]) % 360.0)
    m2 = cm.get('M2', (0,))[0]
    return {'code': code, 'name': name, 'lat': lat,
            'scale': scale, 'axis': axis, 'r2': r2, 'rms': rms, 'm2': m2,
            'mean': float(coef['mean']), 'n': len(times),
            't0': str(pd.to_datetime(times[0]).date()), 't1': str(pd.to_datetime(times[-1]).date()),
            'cm': cm}


if __name__ == '__main__':
    # Phase A: 3 kaputte aus vorhandenen CSVs
    import json
    meta = json.load(open('/home/oliver/currents/Netherlands/_stations.json'))
    CD = '/home/oliver/currents/Netherlands'
    for code in ['eemshaven.waddenzee', 'ijgeul.1', 'ijmuiden.stroommeetpaal.backup']:
        m = meta[code]
        r = fit(f'{CD}/{code}.csv', m['lat'], m['name'], code)
        if 'error' in r:
            print(f"{code:38s} FEHLER: {r['error']}")
        else:
            print(f"{r['name']:30s} R²={r['r2']:.3f} RMS={r['rms']:.3f}kn M2={r['m2']:.3f}kn "
                  f"axis={r['axis']:.0f}° scale={r['scale']} n={r['n']} [{r['t0']}..{r['t1']}]")
