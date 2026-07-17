#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Indische Hafen-Tidetafeln im Admiralty-Layout (Wayback) -> UTide -> Block.

Layout (Dighi, Karaikal): 4 Monatsgruppen/Seite, je Monat 2 Tagesspalten
(1-15 links, 16-31 rechts), je Tag 3-4 Zeilen 'HHMM H.hh', IST ("TIME ZONE
-0530" = invertierte SoI-Konvention), Hoehen m ueber Kartennull.
Dighi-Falle: Zeit-Tokens zersplittert ('133' '4') -> Rekonstruktion ueber
Hoehen-Anker (x-Cluster der H.hh-Tokens) + Digit-Fenster links davon.
Tageszuordnung: y-Gap-Blocksegmentierung je Spalte (Tage sequentiell),
Tagesnummern-Tokens nur als Pin-Verifikation (SoI-Lektion).

Usage: python3 py/fit_att_layout_india.py dighi|karaikal > block.txt
"""
from __future__ import annotations
import glob
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

UTC_OFF = timedelta(hours=5, minutes=30)
MONTHS_L = ['january', 'february', 'march', 'april', 'may', 'june', 'july',
            'august', 'september', 'october', 'november', 'december']
MON3 = {m[:3]: i + 1 for i, m in enumerate(MONTHS_L)}

PORTS = {
    'dighi': dict(
        dir='/home/oliver/weather/tide_tables/india_dighi',
        files=['dighi_2013.pdf', 'dighi_2019.pdf', 'dighi_2020b.pdf'],
        name='Dighi Port (Rajpuri Creek), Maharashtra, India',
        lat=18.2667, lon=72.9667, state='Maharashtra',
        source='# source: Dighi Port annual tide tables with UTide',
        notes=['# note: Source: dighiport.in via web.archive.org, annual tables 2013, 2019,',
               "# note: 2020 (Admiralty layout, 'TIME ZONE -0530' = IST), m above chart datum.",
               '# note: Header position: LAT 18 16 N LONG 72 58 E (Rajpuri Creek entrance).'],
    ),
    'karaikal': dict(
        dir='/home/oliver/weather/tide_tables/india_karaikal',
        files=['karaikal_jan2012.pdf', 'karaikal_2016.pdf', 'karaikal_2019.pdf',
               'karaikal_2021.pdf'],
        name='Karaikal Port, Puducherry, India',
        lat=10.9167, lon=79.8500, state='Puducherry',
        gap_h=26, confidence=6,
        source='# source: Karaikal Port (KPPL) annual tide tables with UTide',
        notes=['# note: Source: karaikalport.com via web.archive.org, annual tables 2012,',
               '# note: 2016, 2019, 2021 (Admiralty layout, IST), m above chart datum.',
               '# note: Header position: LAT 10 55 N LONG 79 51 E.'],
    ),
}


def char_rows(page, drop_big_digits=True):
    """page.chars -> Zeilen [(top, [token,...])], Token=(x0, text).
    Zeichenweise gerenderte PDFs (Dighi 2019/2020) machen extract_words
    unbrauchbar -> Zeilen aus chars: top-Cluster (2pt), Tokens per x-Gap.
    drop_big_digits: fette Tagesnummern verwerfen (ueberlappen bei Dighi
    die Zeit-Digits; Dhamra braucht sie als Spaltenanker -> False)."""
    rows = {}
    for c in page.chars:
        if c['text'].strip() == '':
            continue
        if drop_big_digits and c['size'] > 9.5 and c['text'].isdigit():
            continue    # fette Tagesnummern ueberlappen die Zeit-Digits
        key = None
        for k in (round(c['top']), round(c['top']) - 1, round(c['top']) + 1):
            if k in rows:
                key = k
                break
        if key is None:
            key = round(c['top'])
            rows[key] = []
        rows[key].append(c)
    out = []
    for top in sorted(rows):
        cs = sorted(rows[top], key=lambda c: c['x0'])
        toks = [[cs[0]]]
        for c in cs[1:]:
            if c['x0'] - toks[-1][-1]['x1'] > 2.0:
                toks.append([])
            toks[-1].append(c)
        out.append((top, [(t[0]['x0'], ''.join(c['text'] for c in t)) for t in toks]))
    return out


def parse_pdf(path):
    """-> Liste (datetime_utc, hoehe). Layout siehe Modul-Doc."""
    import calendar
    events = []
    with pdfplumber.open(path) as pdf:
        for pgno, page in enumerate(pdf.pages):
            txt = page.extract_text() or ''
            if not txt.strip():
                print(f'# {os.path.basename(path)} S.{pgno+1}: leer/Scan -> skip',
                      file=sys.stderr)
                continue
            year_g = re.search(r'YEAR\s+(\d{4})', txt)
            if not year_g:
                year_g = re.search(r'\b(20[0-2]\d)\b', txt[:200])
            if not year_g:
                m = re.search(r'(20[0-2]\d)', os.path.basename(path))
                year_g = m
            rows = char_rows(page)
            # Monatsanker: 'JANUARY' (Jahr aus Header) oder 'Jan-16'
            mon_anchors = []  # (x0, month, year)
            for top, toks in rows[:10]:
                for x, t in toks:
                    m = re.match(r'^([A-Z][a-z]{2})-(\d{2})$', t)
                    if t.lower() in MONTHS_L and year_g:
                        mon_anchors.append((x, MONTHS_L.index(t.lower()) + 1,
                                            int(year_g.group(1))))
                    elif m and m.group(1).lower() in MON3:
                        mon_anchors.append((x, MON3[m.group(1).lower()],
                                            2000 + int(m.group(2))))
                    elif t.upper() == t and t.lower() in MON3 and year_g:
                        mon_anchors.append((x, MON3[t.lower()],
                                            int(year_g.group(1))))
            mon_anchors.sort()
            if len(mon_anchors) != 4:
                print(f'# {os.path.basename(path)} S.{pgno+1}: {len(mon_anchors)} '
                      f'Monatsanker != 4 -> skip', file=sys.stderr)
                continue
            # Event-Paare (Zeit, Hoehe) einsammeln: Token HHMM + H.hh direkt rechts
            pairs = []  # (top, x_time, 'HHMM', hoehe)
            for top, toks in rows:
                for i, (x, t) in enumerate(toks):
                    if not re.match(r'^\d{4}$', t):
                        continue
                    for x2, t2 in toks[i + 1:]:
                        if x2 - x > 45:
                            break
                        if re.match(r'^-?\d\.\d{2}$', t2):
                            pairs.append((top, x, t, float(t2)))
                            break
            # Spaltenanker: x-Cluster der Zeit-Tokens -> 8 Spalten
            xs = sorted(p[1] for p in pairs)
            clusters = [[xs[0]]]
            for x in xs[1:]:
                if x - clusters[-1][-1] > 12:
                    clusters.append([])
                clusters[-1].append(x)
            anchors = sorted(float(np.median(c)) for c in clusters if len(c) > 25)
            if len(anchors) != 8:
                print(f'# {os.path.basename(path)} S.{pgno+1}: {len(anchors)} Spaltenanker '
                      f'!= 8: {[round(a) for a in anchors]} -> skip', file=sys.stderr)
                continue
            colev = {}
            for top, x, tstr, hgt in pairs:
                dists = [abs(x - a) for a in anchors]
                ai = int(np.argmin(dists))
                if dists[ai] > 12:
                    continue
                colev.setdefault(ai, []).append((top, tstr, hgt))
            # Tagessegmentierung: Zeitruecksprung = neuer Tag
            for ai, evs in sorted(colev.items()):
                month, year = mon_anchors[ai // 2][1:]
                sc = ai % 2
                ndays = calendar.monthrange(year, month)[1]
                evs.sort()
                blocks = [[evs[0]]]
                for e in evs[1:]:
                    if int(e[1]) <= int(blocks[-1][-1][1]):
                        blocks.append([])
                    blocks[-1].append(e)
                expect = 15 if sc == 0 else ndays - 15
                if len(blocks) != expect:
                    print(f'# {os.path.basename(path)} {year}-{month:02d} sub{sc}: '
                          f'{len(blocks)} Tagesbloecke != {expect} -> Monat verworfen',
                          file=sys.stderr)
                    continue
                bad = [b for b in blocks if not 2 <= len(b) <= 4]
                if bad:
                    print(f'# {os.path.basename(path)} {year}-{month:02d} sub{sc}: '
                          f'{len(bad)} Tage mit !=2-4 Events', file=sys.stderr)
                for bi, blk in enumerate(blocks):
                    day = bi + 1 + (0 if sc == 0 else 15)
                    for _, tstr, hgt in blk:
                        hh, mi = int(tstr[:2]), int(tstr[2:])
                        if hh > 23 or mi > 59:
                            print(f'# {os.path.basename(path)}: Zeit kaputt '
                                  f'{year}-{month:02d}-{day} {tstr}', file=sys.stderr)
                            continue
                        events.append((datetime(year, month, day, hh, mi) - UTC_OFF, hgt))
    return events


def main():
    port = PORTS[sys.argv[1]]
    events = []
    for f in port['files']:
        ev = parse_pdf(os.path.join(port['dir'], f))
        print(f'# {f}: {len(ev)} Events', file=sys.stderr)
        events.extend(ev)
    events.sort(key=lambda e: e[0])
    ev = [events[0]]
    for e in events[1:]:
        if e[0] > ev[-1][0]:
            ev.append(e)
    print(f'# {len(ev)} Events {ev[0][0]:%Y-%m-%d}..{ev[-1][0]:%Y-%m-%d}', file=sys.stderr)
    ev = drop_alternation_breakers(ev)
    t, v = interp_segments(ev, gap_h=port.get('gap_h', 16))
    coef = utide.solve(t, v, lat=port['lat'], nodal=True, trend=False, method='ols',
                       conf_int='none', verbose=False, constit=CONSTIT_67)
    rec = utide.reconstruct(t, coef, verbose=False)
    resid = v - rec['h']
    r2 = 1 - float(np.sum(resid ** 2)) / float(np.sum((v - v.mean()) ** 2))
    rms = float(np.sqrt(np.mean(resid ** 2)))
    for yr in sorted({e[0].year for e in ev}):
        ey = [e for e in ev if e[0].year == yr]
        ty = np.array([e[0] for e in ey])
        vy = np.array([e[1] for e in ey])
        ry = utide.reconstruct(ty, coef, verbose=False)
        d = vy - ry['h']
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
    m2, s2, k1, o1 = (cm.get(c, (0, 0)) for c in ('M2', 'S2', 'K1', 'O1'))
    print(f'# Z0={z0:.3f} M2={m2[0]:.3f}@{m2[1]:.0f} S2={s2[0]:.3f}@{s2[1]:.0f} '
          f'K1={k1[0]:.3f}@{k1[1]:.0f} O1={o1[0]:.3f}@{o1[1]:.0f}', file=sys.stderr)
    n_ana = sum(1 for cn, _ in CONSTITUENTS_175 if cn in cm)
    yrs = '+'.join(str(y) for y in sorted({e[0].year for e in ev}))
    L = (["#", f"# {port['name']}", "# BEGIN HOT COMMENTS", "# country: India",
          f"# state: {port['state']}", port['source']]
         + port['notes'] +
         [f"# date_imported: {datetime.now():%Y%m%d}",
          "# datum: chart datum (port tide table)",
          f"# confidence: {port.get('confidence', 7)}",
          f"# utide: events={len(ev)} hwlw period={yrs} r2={r2:.4f} rms={rms:.4f}m const={n_ana}",
          "# !units: meters", f"# !longitude: {port['lon']:.4f}",
          f"# !latitude: {port['lat']:.4f}",
          port['name'], '+00:00 :Asia/Kolkata', f"{z0:.4f} meters"])
    for cn, _sp in CONSTITUENTS_175:
        if cn in cm and cm[cn][0] >= 0.00005:
            L.append(f"{cn:15s} {cm[cn][0]:.4f}  {cm[cn][1]:.2f}")
        else:
            L.append("x 0 0")
    print('\n'.join(L))


if __name__ == '__main__':
    main()
