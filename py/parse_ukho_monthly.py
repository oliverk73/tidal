#!/usr/bin/env python3
"""
Parser für UKHO-Hafenbooklets im "Monats-Layout" (1 Monat pro Seite, eine Zeile
pro Tag): wie ABP-Häfen (Barrow, Fleetwood, …) und Harwich Haven.

Zeilenformat:  <day> <weekday> [moon]  HW-AM  HW-PM  LW-AM  LW-PM
mit Zeit als zwei 2-stellige Tokens ("09 10" = 09:10, 24h) gefolgt von Höhe.
Einzelne Spalten können leer sein. Für UTide brauchen wir nur (datetime, Höhe)-
Paare — die HW/LW/AM/PM-Spaltenzuordnung ist egal, da die Zeit 24h-eindeutig ist.

Gibt naive lokale Datetimes + Höhen (m) zurück (Zeitzone macht der Aufrufer).
"""
from __future__ import annotations
import re
from datetime import datetime
from pathlib import Path

import pdfplumber

MONTHS = {m: i for i, m in enumerate(
    ['JANUARY', 'FEBRUARY', 'MARCH', 'APRIL', 'MAY', 'JUNE', 'JULY', 'AUGUST',
     'SEPTEMBER', 'OCTOBER', 'NOVEMBER', 'DECEMBER'], start=1)}

RE_INT2 = re.compile(r'^\d{1,2}$')
RE_HEIGHT = re.compile(r'^-?\d{1,2}\.\d{1,2}$')


def _page_month_year(text):
    mu = text.upper()
    month = year = None
    for name, num in MONTHS.items():
        if name in mu:
            month = num; break
    m = re.search(r'(20\d{2})', text)
    if m:
        year = int(m.group(1))
    return month, year


def parse_page(page):
    text = page.extract_text() or ''
    month, year = _page_month_year(text)
    if not month or not year:
        return []
    words = page.extract_words(use_text_flow=False, keep_blank_chars=False)
    int_words = [w for w in words if RE_INT2.match(w['text'])]
    height_words = [w for w in words if RE_HEIGHT.match(w['text'])]

    # Tag-Nummern: int 1-31 in der linken Datumsspalte (x < 140)
    day_rows = [(w['top'], int(w['text'])) for w in words
                if RE_INT2.match(w['text']) and w['x0'] < 140 and 1 <= int(w['text']) <= 31]

    out = []
    for top, day in day_rows:
        # Höhen dieser Zeile; HH/MM stehen ~50/37px links der Höhe (spaltenfest)
        row_h = [h for h in height_words if abs(h['top'] - top) <= 5]
        seen_evt = set()
        for h in row_h:
            hx = h['x0']
            hh = [w for w in int_words if abs(w['top'] - top) <= 5
                  and 42 <= (hx - w['x0']) <= 60]
            mm = [w for w in int_words if abs(w['top'] - top) <= 5
                  and 28 <= (hx - w['x0']) <= 45]
            if not hh or not mm:
                continue
            H = int(min(hh, key=lambda w: abs((hx - w['x0']) - 50))['text'])
            M = int(min(mm, key=lambda w: abs((hx - w['x0']) - 37))['text'])
            if H > 23 or M > 59:
                continue
            key = (H, M)
            if key in seen_evt:   # Doppel-Render derselben Spalte
                continue
            seen_evt.add(key)
            try:
                out.append((datetime(year, month, day, H, M), float(h['text'])))
            except ValueError:
                pass
    return out


def parse_pdf(path: Path):
    out = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            out.extend(parse_page(page))
    seen, cleaned = set(), []
    for dt, h in sorted(out):
        k = (dt, round(h, 2))
        if k in seen:
            continue
        seen.add(k); cleaned.append((dt, h))
    return cleaned


if __name__ == '__main__':
    import sys
    from collections import Counter
    for f in sys.argv[1:]:
        ev = parse_pdf(Path(f))
        if ev:
            hh = [h for _, h in ev]
            dist = Counter(Counter(d.date() for d, _ in ev).values())
            print(f"{Path(f).name:30s} {len(ev):5d} ev {ev[0][0].date()}..{ev[-1][0].date()} "
                  f"h={min(hh):.2f}-{max(hh):.2f} /Tag={dict(sorted(dist.items()))}")
        else:
            print(f"{Path(f).name}: 0")
