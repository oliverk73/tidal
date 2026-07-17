#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Royal-Thai-Navy-Tidetafel-PDF (Stundenwerte) -> UTide -> Harmonics-Block.

Quelle: hydro.navy.mi.th 'waterlaveltable', je Station ein Jahres-PDF
(<CODE>2026.pdf, LLW-Variante): 12 Monatsseiten (Index 13..24), Tageszeilen
mit 24 Stundenwerten (m ueber LLW, Ortszeit UTC+7).

Usage: python3 py/fit_rtn_thailand_pdf.py CODE 'Name, Province, Thailand'
Beispiel: python3 py/fit_rtn_thailand_pdf.py MT 'Map Ta Phut, Rayong, Thailand'
Block -> stdout, Diagnose -> stderr.
"""
from __future__ import annotations
import re
import sys
import warnings
from datetime import datetime, timedelta

import numpy as np
import pdfplumber
import utide

warnings.filterwarnings('ignore')
sys.path.insert(0, '/home/oliver/py')
sys.path.insert(0, '/home/oliver/batch')
from generate_germany_harmonics_175 import CONSTITUENTS_175, find_xtide_match
from batch_utide_uk_tidetimes import CONSTIT_67

PDF_DIR = '/home/oliver/weather/tide_tables/thailand'
UTC_OFF = timedelta(hours=7)
MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July',
          'August', 'September', 'October', 'November', 'December']


def parse_pdf(code, year=2026):
    path = f'{PDF_DIR}/{code}{year}.pdf'
    t, v = [], []
    meta = {}
    with pdfplumber.open(path) as pdf:
        for pg in range(13, min(25, len(pdf.pages))):
            txt = pdf.pages[pg].extract_text() or ''
            lines = txt.split('\n')
            month = None
            for l in lines[:6]:
                m = re.search(r"(\d+)\s*[้']?\s*(\d+)'\s*(\d+)\"\s*\S*\s*\(?N", l)
                if m and 'lat' not in meta:
                    meta['lat'] = int(m.group(1)) + int(m.group(2)) / 60 + int(m.group(3)) / 3600
                m = re.search(r"(\d+)\s*[้']?\s*(\d+)'\s*(\d+)\"\s*\S*\s*\(?E", l)
                if m and 'lon' not in meta:
                    meta['lon'] = int(m.group(1)) + int(m.group(2)) / 60 + int(m.group(3)) / 3600
                for i, mo in enumerate(MONTHS):
                    if mo in l and str(year) in l:
                        month = i + 1
            if month is None:
                continue
            for l in lines:
                parts = l.split()
                if len(parts) == 25 and parts[0].isdigit():
                    day = int(parts[0])
                    if not 1 <= day <= 31:
                        continue
                    try:
                        vals = [float(x) for x in parts[1:]]
                    except ValueError:
                        continue
                    base = datetime(year, month, day)
                    for h, x in enumerate(vals):
                        t.append(base + timedelta(hours=h) - UTC_OFF)
                        v.append(x)
    return np.array(t), np.array(v), meta


def main():
    code, name = sys.argv[1], sys.argv[2]
    t, v, meta = parse_pdf(code)
    print(f'# {code}: {len(t)} Punkte {t[0]}..{t[-1]} lat={meta.get("lat"):.4f} '
          f'lon={meta.get("lon"):.4f} min={v.min():.2f} max={v.max():.2f}', file=sys.stderr)
    assert len(t) >= 8000, 'zu wenige Punkte geparst'

    coef = utide.solve(t, v, lat=meta['lat'], nodal=True, trend=False,
                       method='ols', conf_int='none', verbose=False,
                       constit=CONSTIT_67)
    rec = utide.reconstruct(t, coef, verbose=False)
    resid = v - rec['h']
    r2 = 1 - float(np.sum(resid ** 2)) / float(np.sum((v - v.mean()) ** 2))
    rms = float(np.sqrt(np.mean(resid ** 2)))

    from utide._ut_constants import ut_constants
    table = ut_constants['const']
    unames = [n.strip() for n in table.name]
    cm = {}
    for i, u in enumerate(coef['name']):
        u = u.strip()
        if u not in unames:
            continue
        xt, _ = find_xtide_match(u, table.freq[unames.index(u)] * 360.0)
        if xt:
            cm[xt] = (float(coef['A'][i]), float(coef['g'][i]) % 360.0)
    z0 = float(coef['mean'])
    m2, k1, o1 = (cm.get(c, (0, 0)) for c in ('M2', 'K1', 'O1'))
    print(f'# r2={r2:.4f} rms={rms:.4f} Z0={z0:.2f} M2={m2[0]:.2f}@{m2[1]:.0f} '
          f'K1={k1[0]:.2f}@{k1[1]:.0f} O1={o1[0]:.2f}@{o1[1]:.0f}', file=sys.stderr)

    n_ana = sum(1 for cn, _ in CONSTITUENTS_175 if cn in cm)
    province = name.split(',')[1].strip() if name.count(',') >= 2 else ''
    L = [
        "#", f"# {name}", "# 8760 hourly predictions (1 year)",
        "# BEGIN HOT COMMENTS", "# country: Thailand",
        f"# province: {province}",
        "# source: Derived from Royal Thai Navy hourly tide predictions with UTide",
        f"# rtn_pdf: {code}2026 (hydro.navy.mi.th)",
        f"# date_imported: {datetime.now():%Y%m%d}",
        "# datum: LLW",
        "# confidence: 8",
        f"# utide: period=2025-12-31..2026-12-31 r2={r2:.4f} rms={rms:.4f}m const={n_ana}",
        "# !units: meters",
        f"# !longitude: {meta['lon']:.4f}", f"# !latitude: {meta['lat']:.4f}",
        name, '+00:00 :Asia/Bangkok', f"{z0:.4f} meters",
    ]
    for cn, _sp in CONSTITUENTS_175:
        if cn in cm and cm[cn][0] >= 0.00005:
            L.append(f"{cn:15s} {cm[cn][0]:.4f}  {cm[cn][1]:.2f}")
        else:
            L.append("x 0 0")
    print('\n'.join(L))


if __name__ == '__main__':
    main()
