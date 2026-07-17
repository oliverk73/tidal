#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Dhamra-Port-Monatstidetafeln (Wayback) -> UTide -> Harmonics-Block.

Quelle: dhamraport.com (alte DPCL-Site via web.archive.org), Bildschirm-
Kalender "Tides-DHAMRA (4475A) Harmonic station (UKHO)": je Monat 1 Seite,
Wochenzeilen mit Tagesnummern-Zeile, dann 1 Zeiten-Zeile (HH:MM, oft
verklebt '04:3009:51') + 1 Hoehen-Zeile (cm) darunter, x-buendig.
(Time Zone: -0530) = IST invertiert. 6 Monate: Jan-Mae 2011 + Sep-Nov 2016.

Usage: python3 py/fit_dhamra_tides.py > block.txt
"""
from __future__ import annotations
import os
import re
import sys
from datetime import datetime, timedelta

import numpy as np
import pdfplumber
import utide

sys.path.insert(0, '/home/oliver/py')
sys.path.insert(0, '/home/oliver/batch')
from generate_germany_harmonics_175 import CONSTITUENTS_175, find_xtide_match
from fit_krishnapatnam_tides import drop_alternation_breakers, interp_segments
from batch_utide_uk_tidetimes import CONSTIT_67
from fit_att_layout_india import char_rows

DIR = '/home/oliver/weather/tide_tables/india_dhamra'
FILES = ['dhamra_2011.pdf', 'dhamra_cont107.pdf', 'dhamra_cont111.pdf', 'dhamra_cont112.pdf']
UTC_OFF = timedelta(hours=5, minutes=30)
MONTHS_L = ['january', 'february', 'march', 'april', 'may', 'june', 'july',
            'august', 'september', 'october', 'november', 'december']
LAT, LON = 20.8000, 86.9000
NAME = 'Dhamra Port, Odisha, India'


def parse_page(page, fname):
    txt = page.extract_text() or ''
    m = re.search(r'(January|February|March|April|May|June|July|August|September|'
                  r'October|November|December)\s+(\d{4})', txt)
    if not m:
        return []
    month, year = MONTHS_L.index(m.group(1).lower()) + 1, int(m.group(2))
    rows = char_rows(page, drop_big_digits=False)
    # Tagesnummern-Zeilen: nur Ints 1-31, aufsteigend, >=2 Tokens (oder Tag "1"-Zeile)
    day_lines = []   # (top, [(x, day)])
    other = []       # (top, tokens)
    for top, toks in rows:
        ints = [(x, int(t)) for x, t in toks if re.match(r'^\d{1,2}$', t) and 1 <= int(t) <= 31]
        nonints = [t for _, t in toks if not re.match(r'^\d{1,2}$', t)]
        vals = [d for _, d in ints]
        if ints and not nonints and vals == sorted(vals) and \
                (len(ints) > 1 or vals == [1]):
            day_lines.append((top, ints))
        else:
            other.append((top, toks))
    events = []
    for top, toks in other:
        # Zeiten-Zeile: Tokens mit HH:MM-Mustern
        tps = []   # (x, 'HH:MM')
        for x, t in toks:
            if t.startswith(('SR:', 'SS:')) or 'cm' in t:
                continue
            for mt in re.finditer(r'\d{2}:\d{2}', t):
                tps.append((x + mt.start() * 3.3, mt.group(0)))
        if not tps:
            continue
        # zugehoerige Wochenzeile: letzte day_line OBERHALB
        cands = [dl for dl in day_lines if dl[0] < top]
        if not cands:
            continue
        _, anchors = max(cands, key=lambda dl: dl[0])
        # Hoehen-Zeile direkt darunter suchen (naechste Zeile mit \d{1,3}-Tokens)
        hrow = None
        for top2, toks2 in other:
            if top < top2 <= top + 14:
                hs = [(x, int(t)) for x, t in toks2 if re.match(r'^-?\d{1,3}$', t)]
                if len(hs) >= len(tps) * 0.7:
                    hrow = hs
                    break
        if hrow is None:
            continue
        # Zeit->Hoehe ueber x-Naehe; Tag: Gruppen per Zeitruecksprung, der
        # Reihe nach auf die Wochen-Anker (Tagesnummern) verteilt
        tps.sort()
        rowev = []
        for xt, tstr in tps:
            dists = [(abs(xh - xt), h) for xh, h in hrow]
            dmin, hgt = min(dists)
            if dmin > 12:
                print(f'# {fname}: keine Hoehe fuer {tstr} (d={dmin:.0f})', file=sys.stderr)
                continue
            rowev.append((xt, tstr, hgt))
        if not rowev:
            continue
        groups = [[rowev[0]]]
        for e in rowev[1:]:
            if int(e[1].replace(':', '')) <= int(groups[-1][-1][1].replace(':', '')):
                groups.append([])
            groups[-1].append(e)
        if len(groups) != len(anchors):
            print(f'# {fname} {year}-{month:02d} Woche@y{top}: {len(groups)} Gruppen '
                  f'!= {len(anchors)} Tage -> Zeile verworfen', file=sys.stderr)
            continue
        for (_, day), grp in zip(anchors, groups):
            for _, tstr, hgt in grp:
                hh, mi = int(tstr[:2]), int(tstr[3:])
                if hh > 23 or mi > 59:
                    continue
                events.append((datetime(year, month, day, hh, mi) - UTC_OFF, hgt / 100.0))
    return events


def main():
    events = []
    for f in FILES:
        with pdfplumber.open(os.path.join(DIR, f)) as pdf:
            n0 = len(events)
            for page in pdf.pages:
                events.extend(parse_page(page, f))
            print(f'# {f}: {len(events) - n0} Events', file=sys.stderr)
    events.sort(key=lambda e: e[0])
    ev = [events[0]]
    for e in events[1:]:
        if e[0] > ev[-1][0]:
            ev.append(e)
    print(f'# {len(ev)} Events {ev[0][0]:%Y-%m-%d}..{ev[-1][0]:%Y-%m-%d}', file=sys.stderr)
    ev = drop_alternation_breakers(ev)
    t, v = interp_segments(ev)
    coef = utide.solve(t, v, lat=LAT, nodal=True, trend=False, method='ols',
                       conf_int='none', verbose=False, constit=CONSTIT_67)
    rec = utide.reconstruct(t, coef, verbose=False)
    resid = v - rec['h']
    r2 = 1 - float(np.sum(resid ** 2)) / float(np.sum((v - v.mean()) ** 2))
    rms = float(np.sqrt(np.mean(resid ** 2)))
    for yr in sorted({e[0].year for e in ev}):
        ey = [e for e in ev if e[0].year == yr]
        ty = np.array([e[0] for e in ey])
        vy = np.array([e[1] for e in ey])
        d = vy - utide.reconstruct(ty, coef, verbose=False)['h']
        print(f'# {yr}: {len(ey)} Events, bias={d.mean():+.3f} rms={np.sqrt((d**2).mean()):.3f}',
              file=sys.stderr)
    print(f'# GESAMT r2={r2:.4f} rms={rms:.4f}', file=sys.stderr)

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
    m2, s2, k1, o1, n2 = (cm.get(c, (0, 0)) for c in ('M2', 'S2', 'K1', 'O1', 'N2'))
    print(f'# Z0={z0:.3f} M2={m2[0]:.3f}@{m2[1]:.0f} S2={s2[0]:.3f}@{s2[1]:.0f} '
          f'N2={n2[0]:.3f}@{n2[1]:.0f} K1={k1[0]:.3f}@{k1[1]:.0f} O1={o1[0]:.3f}@{o1[1]:.0f}',
          file=sys.stderr)
    n_ana = sum(1 for cn, _ in CONSTITUENTS_175 if cn in cm)
    L = [
        "#", f"# {NAME}", "# BEGIN HOT COMMENTS", "# country: India",
        "# state: Odisha",
        "# source: Dhamra Port monthly tide tables (UKHO station 4475A) with UTide",
        "# note: Source: dhamraport.com via web.archive.org, 6 monthly calendar",
        "# note: sheets (Jan-Mar 2011, Sep-Nov 2016), 'Tides-DHAMRA (4475A) Harmonic",
        "# note: station (UKHO)', heights cm above CD, IST. Port entrance/river mouth;",
        "# note: Shortt's Island (SoI, 11 km offshore) exists as separate station.",
        f"# date_imported: {datetime.now():%Y%m%d}",
        "# datum: chart datum (port tide table)",
        "# confidence: 5",
        f"# utide: events={len(ev)} hwlw period=2011x3m+2016x3m r2={r2:.4f} rms={rms:.4f}m const={n_ana}",
        "# !units: meters", f"# !longitude: {LON:.4f}", f"# !latitude: {LAT:.4f}",
        NAME, '+00:00 :Asia/Kolkata', f"{z0:.4f} meters",
    ]
    for cn, _sp in CONSTITUENTS_175:
        if cn in cm and cm[cn][0] >= 0.00005:
            L.append(f"{cn:15s} {cm[cn][0]:.4f}  {cm[cn][1]:.2f}")
        else:
            L.append("x 0 0")
    print('\n'.join(L))


if __name__ == '__main__':
    main()
