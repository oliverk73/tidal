#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Adani-Ports-Tidetafel-PDF (Kalenderlayout) -> UTide -> Harmonics-Block.

Quelle: amtliche Jahres-Tidetafel des Hafenbetreibers (z.B. Mundra MMPT),
Kalenderlayout: Datumszeile 'DD/Mon' je Woche, darunter 3-5 Event-Zeilen
'H0050 6.01' / 'L0610 2.66' (H/L + HHMM, Hoehe m ueber Kartennull, UTC+5:30).
Spaltenzuordnung ueber Wort-x-Koordinaten (extract_words), da extract_text
die Tagesspalten vermischt.

Usage: python3 py/fit_adani_tide_pdf.py PDF JAHR 'Name, Region, Land' LAT LON > block.txt
Beispiel: python3 py/fit_adani_tide_pdf.py water_levels/mundra_tide_table_2026.pdf \
          2026 'Mundra, Gujarat, India' 22.738 69.701 > /tmp/mundra_block.txt
"""
from __future__ import annotations
import re
import sys
from datetime import datetime, timedelta

import numpy as np
import pdfplumber
import utide

sys.path.insert(0, '/home/oliver/py')
sys.path.insert(0, '/home/oliver/batch')
from generate_germany_harmonics_175 import CONSTITUENTS_175, find_xtide_match
from batch_utide_uk_tidetimes import cosine_interpolate, CONSTIT_67

MONTHS = {m: i + 1 for i, m in enumerate(
    ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'])}
UTC_OFF = timedelta(hours=5, minutes=30)


def parse_pdf(path, year):
    events = []
    blocks = []  # (top, [(x, day, month)]) — seitenuebergreifend (Wochenbloecke
    # laufen ueber Seitenumbrueche, Events oben auf der Folgeseite gehoeren
    # zur letzten Datumszeile der Vorseite)
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            words = page.extract_words()
            # Zeilen nach y gruppieren
            lines = {}
            for w in words:
                lines.setdefault(round(w['top'] / 3), []).append(w)
            for top in sorted(lines):
                ws = sorted(lines[top], key=lambda w: w['x0'])
                dates = [(w['x0'], int(m.group(1)), MONTHS[m.group(2)])
                         for w in ws if (m := re.match(r'^(\d{2})/([A-Z][a-z]{2})$', w['text']))]
                if dates:
                    blocks.append((top, dates))
                    continue
                for i, w in enumerate(ws):
                    m = re.match(r'^([HL])(\d{2})(\d{2})$', w['text'])
                    if not m or i + 1 >= len(ws):
                        continue
                    mh = re.match(r'^(-?\d+\.\d{1,2})$', ws[i + 1]['text'])
                    if not mh or not blocks:
                        continue
                    _, anchors = blocks[-1]
                    x, d, mo = min(anchors, key=lambda a: abs(a[0] - w['x0']))
                    hh, mi = int(m.group(2)), int(m.group(3))
                    dt = datetime(year, mo, d, hh, mi) - UTC_OFF
                    events.append((dt, float(mh.group(1))))
    events.sort(key=lambda e: e[0])
    out = [events[0]]
    for e in events[1:]:
        if e[0] > out[-1][0]:
            out.append(e)
    return out


def main():
    pdf, year, name, lat, lon = sys.argv[1], int(sys.argv[2]), sys.argv[3], \
        float(sys.argv[4]), float(sys.argv[5])
    ev = parse_pdf(pdf, year)
    print(f'# {len(ev)} HW/LW-Events {ev[0][0]:%Y-%m-%d}..{ev[-1][0]:%Y-%m-%d}', file=sys.stderr)
    gaps = [(a[0], b[0]) for a, b in zip(ev, ev[1:])
            if (b[0] - a[0]).total_seconds() > 16 * 3600]
    for g in gaps:
        print(f'# LUECKE {g[0]} .. {g[1]}', file=sys.stderr)
    t, v = cosine_interpolate(list(ev))
    t, v = np.array(t), np.array(v)
    coef = utide.solve(t, v, lat=lat, nodal=True, trend=False, method='ols',
                       conf_int='none', verbose=False, constit=CONSTIT_67)
    rec = utide.reconstruct(t, coef, verbose=False)
    resid = v - rec['h']
    r2 = 1 - float(np.sum(resid ** 2)) / float(np.sum((v - v.mean()) ** 2))
    rms = float(np.sqrt(np.mean(resid ** 2)))
    print(f'# r2={r2:.4f} rms={rms:.4f}', file=sys.stderr)

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
    n_ana = sum(1 for cn, _ in CONSTITUENTS_175 if cn in cm)
    L = [
        "#", f"# {name}", "# BEGIN HOT COMMENTS", f"# country: {name.rsplit(',', 1)[-1].strip()}",
        "# source: Adani Ports official annual tide table (PDF) with UTide",
        f"# date_imported: {datetime.now():%Y%m%d}",
        "# datum: chart datum (port tide table)",
        "# confidence: 7",
        f"# utide: pts={len(ev)} hwlw period={ev[0][0]:%Y-%m-%d}..{ev[-1][0]:%Y-%m-%d} r2={r2:.4f} rms={rms:.4f}m const={n_ana}",
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
