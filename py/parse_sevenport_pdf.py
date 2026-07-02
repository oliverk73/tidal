#!/usr/bin/env python3
# -*- coding: iso-8859-1 -*-
"""Parser fuer das 'seven port format' der Firth-of-Forth/Tay-Tidetafeln.

7 Haefen nebeneinander (feste x-Spalten), Zeitzone UT(GMT) ganzjaehrig.
Liefert pro Hafen eine Liste (datetime_utc, height_m) aus HW/LW-Eintraegen.

Spalten (Zeit-Token x0, Hoehen-Token sitzt direkt rechts):
  GRANGEMOUTH ~79  ROSYTH ~144  LEITH ~209  BURNTISLAND ~274
  METHIL ~340  DUNDEE ~405  RIVER TAY BAR ~470
"""
import re
from datetime import datetime
from pathlib import Path

import pdfplumber

PORTS = [
    ('Grangemouth', 79.0),
    ('Rosyth', 144.2),
    ('Leith', 209.5),
    ('Burntisland', 274.5),
    ('Methil', 339.8),
    ('Dundee', 405.1),
    ('River Tay Bar', 470.1),
]
MONTHS = {m: i for i, m in enumerate(
    ['JANUARY', 'FEBRUARY', 'MARCH', 'APRIL', 'MAY', 'JUNE', 'JULY',
     'AUGUST', 'SEPTEMBER', 'OCTOBER', 'NOVEMBER', 'DECEMBER'], 1)}

TIME_RE = re.compile(r'^\d{4}$')
HEIGHT_RE = re.compile(r'^\d{1,2}\.\d$')


def nearest_port(x0):
    """Index des Hafens, dessen Zeit-Spalte am naechsten an x0 liegt (<=20 px)."""
    best, bd = None, 1e9
    for i, (_, cx) in enumerate(PORTS):
        d = abs(x0 - cx)
        if d < bd:
            bd, best = d, i
    return best if bd <= 20 else None


def group_rows(words, ytol=2.5):
    """Woerter nach 'top' in Zeilen gruppieren."""
    rows = []
    for w in sorted(words, key=lambda w: (w['top'], w['x0'])):
        if rows and abs(w['top'] - rows[-1][0]) <= ytol:
            rows[-1][1].append(w)
        else:
            rows.append([w['top'], [w]])
    return [r[1] for r in rows]


def parse_page(page):
    """Gibt {port_name: [(datetime, height), ...]} fuer eine Seite."""
    words = page.extract_words(use_text_flow=False, keep_blank_chars=False)
    # Header: MONTH YEAR (top < 70)
    month = year = None
    for w in words:
        if w['top'] < 70:
            t = w['text'].upper()
            if t in MONTHS:
                month = MONTHS[t]
            elif re.fullmatch(r'20\d{2}', t):
                year = int(t)
    if month is None or year is None:
        return {}

    out = {name: [] for name, _ in PORTS}
    cur_day = None
    for row in group_rows(words):
        # Tagesnummer am linken/rechten Rand (Integer 1..31, x0<60 oder x0>525)
        for w in row:
            if (w['x0'] < 60 or w['x0'] > 525) and w['text'].isdigit():
                v = int(w['text'])
                if 1 <= v <= 31:
                    cur_day = v
        if cur_day is None:
            continue
        # Zeit/Hoehen-Token den Haefen zuordnen
        times = {}    # port_idx -> (x0, 'HHMM')
        heights = {}  # liste (x0, value)
        for w in row:
            txt = w['text']
            if TIME_RE.match(txt):
                pi = nearest_port(w['x0'])
                if pi is not None:
                    times[pi] = (w['x0'], txt)
            elif HEIGHT_RE.match(txt):
                heights.setdefault('h', []).append((w['x0'], float(txt)))
        # Hoehe = naechster Hoehen-Token rechts der Zeit (innerhalb ~35px)
        for pi, (tx, hhmm) in times.items():
            hh, mm = int(hhmm[:2]), int(hhmm[2:])
            if not (0 <= hh <= 23 and 0 <= mm <= 59):
                continue
            cand = [(abs(hx - (tx + 26)), hv) for hx, hv in heights.get('h', [])
                    if 5 < (hx - tx) < 40]
            if not cand:
                continue
            hgt = min(cand)[1]
            try:
                dt = datetime(year, month, cur_day, hh, mm)
            except ValueError:
                continue
            out[PORTS[pi][0]].append((dt, hgt))
    return out


def parse_pdf(path):
    merged = {name: [] for name, _ in PORTS}
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            for name, lst in parse_page(page).items():
                merged[name].extend(lst)
    return merged


def parse_many(paths):
    """Mehrere PDFs (Jahre) zusammenfuehren, dedup + sortiert."""
    all_p = {name: [] for name, _ in PORTS}
    for p in paths:
        for name, lst in parse_pdf(p).items():
            all_p[name].extend(lst)
    for name in all_p:
        seen = {}
        for dt, h in all_p[name]:
            seen[dt] = h  # spaetere Jahre/Dubletten ueberschreiben identische ts
        all_p[name] = sorted(seen.items())
    return all_p


if __name__ == '__main__':
    import sys
    files = sys.argv[1:] or [
        'tide_tables/UK/sevenPortFormat_24.pdf',
        'tide_tables/UK/sevenPortFormat_25.pdf',
        'tide_tables/UK/sevPortFormat_26.pdf',
    ]
    data = parse_many([Path(f) for f in files])
    for name, _ in PORTS:
        lst = data[name]
        if lst:
            print(f'{name:16s} {len(lst):5d} pts  {lst[0][0].date()}..{lst[-1][0].date()}'
                  f'  h[{min(h for _,h in lst):.1f}..{max(h for _,h in lst):.1f}]')
        else:
            print(f'{name:16s}     0 pts')
