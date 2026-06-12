#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Puducherry-Port-Monats-Tidetafeln (port.py.gov.in, tideinfoDDMMYYYY.pdf) -> UTide-Block.

Layout: 1 Seite/Monat, Textzeilen 'DD/MM/YYYY HHMM H.HH HHMM H.HH ...' (bis 4
Events/Tag, '--' = leer), Zeiten IST, Hoehen m (Kartennull angenommen).

Usage: python3 py/fit_puducherry_tides.py DIR 'Name' LAT LON CONF
"""
from __future__ import annotations
import glob
import re
import sys
from datetime import datetime, timedelta

import numpy as np
import pdfplumber
import utide

sys.path.insert(0, '/home/oliver/py')
sys.path.insert(0, '/home/oliver/batch')
from generate_germany_harmonics_175 import CONSTITUENTS_175, find_xtide_match
from batch_utide_uk_tidetimes import CONSTIT_67

IST = timedelta(hours=5, minutes=30)


def parse_pdf(path):
    events = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            txt = page.extract_text() or ''
            for line in txt.splitlines():
                m = re.match(r'\s*(\d{1,2})/(\d{1,2})/(\d{4})\s+(.*)', line)
                if not m:
                    continue
                d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
                rest = m.group(4)
                for tm, ht in re.findall(r'(\d{4})\s+(-?\d{1,2}\.\d{1,2})', rest):
                    hh, mi = int(tm[:2]), int(tm[2:])
                    if hh > 23 or mi > 59 or float(ht) > 14:
                        continue
                    try:
                        events.append((datetime(y, mo, d, hh, mi) - IST, float(ht)))
                    except ValueError:
                        pass
    return events


def main():
    d, name, lat, lon, conf = sys.argv[1], sys.argv[2], \
        float(sys.argv[3]), float(sys.argv[4]), sys.argv[5]
    events = []
    for p in sorted(glob.glob(d + '/tideinfo*.pdf')):
        ev = parse_pdf(p)
        print(f'# {p.split("/")[-1]}: {len(ev)} Events', file=sys.stderr, flush=True)
        events += ev
    events.sort(key=lambda e: e[0])
    events = [e for i, e in enumerate(events) if i == 0 or e[0] > events[i - 1][0]]
    print(f'# gesamt {len(events)} Events', file=sys.stderr)

    dts, lv = [], []
    for (t0, v0), (t1, v1) in zip(events, events[1:]):
        gap = (t1 - t0).total_seconds() / 3600.0
        if not (2.0 < gap < 10.5) or abs(v1 - v0) < 0.2:
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
    keep = np.abs(resid) < max(0.3, 3.5 * float(resid.std()))
    coef = utide.solve(dts[keep], lv[keep], **kw)
    rec = utide.reconstruct(dts[keep], coef, verbose=False)
    resid = lv[keep] - rec['h']
    r2 = 1 - float(np.sum(resid ** 2)) / float(np.sum((lv[keep] - lv[keep].mean()) ** 2))
    rms = float(np.sqrt(np.mean(resid ** 2)))
    print(f'# r2={r2:.4f} rms={rms:.4f} drop={int((~keep).sum())}', file=sys.stderr)

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
    L = [
        "#", f"# {name}", "# BEGIN HOT COMMENTS", "# country: India",
        "# source: Puducherry Port monthly tide tables (port.py.gov.in) with UTide",
        f"# date_imported: {datetime.now():%Y%m%d}",
        "# datum: chart datum (assumed, per port tide table)",
        f"# confidence: {conf}",
        f"# utide: pts={len(events)} hwlw period={events[0][0]:%Y-%m-%d}..{events[-1][0]:%Y-%m-%d} r2={r2:.4f} rms={rms:.4f}m const={sum(1 for cn, _ in CONSTITUENTS_175 if cn in cm)}",
        "# !units: meters", f"# !longitude: {lon:.4f}", f"# !latitude: {lat:.4f}",
        name, '+00:00 :Asia/Kolkata', f"{z0:.4f} meters",
    ]
    for cn, _sp in CONSTITUENTS_175:
        if cn in cm and cm[cn][0] >= 0.00005:
            L.append(f"{cn:15s} {cm[cn][0]:.4f}  {cm[cn][1]:.2f}")
        else:
            L.append("x 0 0")
    print('\n'.join(L))


if __name__ == '__main__':
    main()
