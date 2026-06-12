#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Refit der 24 indischen Survey-of-India-Stationen in harmonics_utide_tidetables.txt.

Ersetzt die schwachen 2-Monats-Fits (date_imported 20260413, r2 0.88-0.96)
durch 22-Monats-Fits aus water_levels/IN_soi/months/ (Aug 2022, Feb-Dez 2024,
Feb-Aug 2025, Jan+Mai-Jul 2026). Name, Koordinaten und # state: bleiben
unveraendert (Oliver pflegt Koordinaten z.T. manuell); Phasen neu als
Greenwich mit '+00:00 :Asia/Kolkata' (Konvention der juengeren Importe;
Altbloecke hatten +05:30 mit Lokalphasen).

Validierung je Station: Out-of-sample Juli 2026 (Fit ohne Juli, Extrema gegen
Tafel: dt-sigma, dh-sigma).

Usage: python3 py/refit_soi_stations.py [--write]
"""
from __future__ import annotations
import io
import contextlib
import os
import re
import sys
import tempfile
from datetime import datetime, timedelta

import numpy as np
import utide

sys.path.insert(0, '/home/oliver/py')
sys.path.insert(0, '/home/oliver/batch')
from fit_soi_tide_pdf import collect_events
from generate_germany_harmonics_175 import CONSTITUENTS_175, find_xtide_match
from batch_utide_uk_tidetimes import CONSTIT_67

HFILE = '/home/oliver/harmonics/utide/harmonics_utide_tidetables.txt'

STATIONS = [
    ('KANDLA|DEENDAYAL', 'Kandla, Gujarat, India'),
    ('NAVLAKHI', 'Navlakhi, Gujarat, India'),
    ('OKHA', 'Okha, Gujarat, India'),
    ('PIPAVAV', 'Pipavav (Port), Gujarat, India'),
    # Porbandar: Kartennull-Sprung +0,2 m zwischen Ausgabe 2024 und 2025
    # -> nur aktuelle Datum-Aera (ab 2025) verwenden
    ('PORBANDAR', 'Porbandar, Gujarat, India', 2025),
    ('VERAVAL', 'Veraval, Gujarat, India'),
    ('VADINAR', 'Vadinar, Gujarat, India'),
    ('BEYPORE', 'Beypore, Kerala, India'),
    ('KARWAR', 'Karwar, Karnataka, India'),
    ('MANGALORE', 'Mangaluru, Karnataka, India'),
    ('PAMBAN', 'Pamban Pass, Tamil Nadu, India'),
    ('TUTICORIN|CHIDAMBARANAR', 'Thoothukudi, Tamil Nadu, India'),
    ('NAGAPATTINAM|NAGAPPATTINAM', 'Nagapattinam, Tamil Nadu, India'),
    ('ENNORE|KAMARAJAR|KAMRAJAR', 'Ennore, Tamil Nadu, India'),
    ('KAKINADA', 'Kakinada, Andhra Pradesh, India'),
    ('CHANDBALI', 'Chandbali (Dhamra River), Odisha, India'),
    ("SHORTT", "Shortt's Island, Odisha, India"),
    ('SAGAR', 'Sagar Island, West Bengal, India'),
    ('DIAMOND HARBOUR', 'Diamond Harbour, West Bengal, India'),
    ('GARDEN REACH', 'Kolkata (Garden Reach Khidderpore), West Bengal, India'),
    ('GANGRA', 'Gangra, West Bengal, India'),
    ('HALDIA', 'Haldia, West Bengal, India'),
    ('MAYAPUR', 'Mayapur, West Bengal, India'),
]


def fit_events(events, lat):
    dts, lv = [], []
    for (t0, v0), (t1, v1) in zip(events, events[1:]):
        gap = (t1 - t0).total_seconds() / 3600.0
        if not (2.0 < gap < 10.5) or abs(v1 - v0) < 0.25:
            continue
        n = max(2, int(gap * 4))
        for i in range(n + 1):
            f = i / n
            dts.append(t0 + (t1 - t0) * f)
            lv.append((v0 + v1) / 2 + (v0 - v1) / 2 * np.cos(np.pi * f))
    dts, lv = np.array(dts), np.array(lv)
    kw = dict(lat=lat, nodal=True, trend=False, method='ols', conf_int='none',
              verbose=False, constit=CONSTIT_67)
    coef = utide.solve(dts, lv, **kw)
    resid = lv - utide.reconstruct(dts, coef, verbose=False)['h']
    keep = np.abs(resid) < max(0.5, 3.5 * resid.std())
    coef = utide.solve(dts[keep], lv[keep], **kw)
    rec = utide.reconstruct(dts[keep], coef, verbose=False)
    resid = lv[keep] - rec['h']
    r2 = 1 - float(np.sum(resid ** 2)) / float(np.sum((lv[keep] - lv[keep].mean()) ** 2))
    rms = float(np.sqrt(np.mean(resid ** 2)))
    return coef, r2, rms


def oos_july(events, lat):
    train = [e for e in events if not (e[0].year == 2026 and e[0].month == 7)]
    test = [e for e in events if e[0].year == 2026 and e[0].month == 7]
    if len(test) < 50:
        return None
    coef, _, _ = fit_events(train, lat)
    t0 = test[0][0] - timedelta(hours=6)
    t1 = test[-1][0] + timedelta(hours=6)
    grid = np.array([t0 + timedelta(minutes=2 * i)
                     for i in range(int((t1 - t0).total_seconds() / 120) + 1)])
    h = utide.reconstruct(grid, coef, verbose=False)['h']
    ext = [(grid[i], h[i]) for i in range(1, len(h) - 1)
           if (h[i] - h[i - 1]) * (h[i + 1] - h[i]) <= 0]
    dt_err, dh_err = [], []
    for te, he in test:
        cands = [((tg - te).total_seconds(), hg) for tg, hg in ext
                 if abs((tg - te).total_seconds()) < 3 * 3600]
        if not cands:
            continue
        sec, hg = min(cands, key=lambda c: abs(c[0]))
        dt_err.append(sec / 60.0)
        dh_err.append(hg - he)
    if not dt_err:
        return None
    return (np.mean(dt_err), np.std(dt_err), np.mean(dh_err), np.std(dh_err),
            len(dt_err), len(test))


def make_block(name, lat, lon, state, coef, r2, rms, events, conf):
    from utide._ut_constants import ut_constants
    table = ut_constants['const']
    unames = [n.strip() for n in table.name]
    cm = {}
    for i, u in enumerate(coef['name']):
        u = u.strip()
        if u in unames:
            xt, _ = find_xtide_match(u, table.freq[unames.index(u)] * 360.0)
            if xt:
                cm[xt] = (float(coef['A'][i]), float(coef['g'][i]) % 360.0)
    z0 = float(coef['mean'])
    months = len({(e[0].year, e[0].month) for e in events})
    L = ["#", f"# {name}", "# BEGIN HOT COMMENTS", "# country: India"]
    if state:
        L.append(f"# state: {state}")
    L += [
        "# source: Survey of India monthly tide tables (surveyofindia.gov.in) with UTide",
        f"# date_imported: {datetime.now():%Y%m%d}",
        "# datum: chart datum (per Survey of India tide tables)",
        f"# confidence: {conf}",
        f"# utide: pts={len(events)} hwlw months={months} period={events[0][0]:%Y-%m-%d}..{events[-1][0]:%Y-%m-%d} r2={r2:.4f} rms={rms:.4f}m const={sum(1 for cn, _ in CONSTITUENTS_175 if cn in cm)}",
        "# !units: meters", f"# !longitude: {lon}", f"# !latitude: {lat}",
        name, '+00:00 :Asia/Kolkata', f"{z0:.4f} meters",
    ]
    for cn, _sp in CONSTITUENTS_175:
        if cn in cm and cm[cn][0] >= 0.00005:
            L.append(f"{cn:15s} {cm[cn][0]:.4f}  {cm[cn][1]:.2f}")
        else:
            L.append("x 0 0")
    return '\n'.join(L)


def find_block(text, name):
    i = text.find('\n' + name + '\n')
    if i < 0:
        raise ValueError(f'Station nicht gefunden: {name}')
    start = text.rfind('\n#\n', 0, i)
    if start < 0:
        raise ValueError(f'Blockanfang fehlt: {name}')
    start += 1  # hinter dem fuehrenden \n
    j = text.find('\n#\n', i)
    end = j + 1 if j > 0 else len(text)
    return start, end


def main():
    write = '--write' in sys.argv
    text = open(HFILE, encoding='iso-8859-1').read()
    n_before = text.count('# !units:')
    results = []
    for entry in STATIONS:
        alias, name = entry[0], entry[1]
        min_year = entry[2] if len(entry) > 2 else None
        start, end = find_block(text, name)
        old = text[start:end]
        m_lat = re.search(r'# !latitude: ([-\d.]+)', old)
        m_lon = re.search(r'# !longitude: ([-\d.]+)', old)
        m_state = re.search(r'# state: (.+)', old)
        m_old = re.search(r'# utide: (.*)', old)
        lat, lon = m_lat.group(1), m_lon.group(1)
        state = m_state.group(1).strip() if m_state else None
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            events = collect_events(alias)
        warn = [l for l in buf.getvalue().splitlines() if 'WARNUNG' in l or 'FEHLER' in l]
        if min_year:
            events = [e for e in events if e[0].year >= min_year]
        if len(events) < 1000:
            print(f'!! {name}: nur {len(events)} Events - UEBERSPRUNGEN')
            continue
        coef, r2, rms = fit_events(events, float(lat))
        oos = oos_july(events, float(lat))
        conf = 7 if (r2 > 0.97 and oos and abs(oos[0]) < 10 and oos[1] < 15) else 6
        blk = make_block(name, lat, lon, state, coef, r2, rms, events, conf)
        results.append((name, len(events), r2, rms, oos, conf, warn))
        if write:
            text = text[:start] + blk + '\n' + text[end:]
        o = f'dt={oos[0]:+.1f}±{oos[1]:.1f}min dh={oos[2]:+.3f}±{oos[3]:.3f}m n={oos[4]}/{oos[5]}' if oos else 'OOS n/a'
        print(f'{name[:44]:46s} ev={len(events):4d} r2={r2:.4f} rms={rms:.3f} conf={conf} {o}'
              + (f'  {len(warn)} Warnungen' if warn else ''))
        for w in warn[:3]:
            print('    ', w)
    if write:
        n_after = text.count('# !units:')
        print(f'Stationen vorher={n_before} nachher={n_after}')
        assert n_after == n_before, 'STATIONSZAHL GEAENDERT!'
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(HFILE))
        with os.fdopen(fd, 'w', encoding='iso-8859-1') as f:
            f.write(text)
        os.replace(tmp, HFILE)
        print('geschrieben:', HFILE)


if __name__ == '__main__':
    main()
