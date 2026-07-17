#!/usr/bin/env python3
"""
Parser für Port-of-Mostyn Tidenkalender-PDFs (UKHO-Format, EasyTide PortID 0464).

Layout pro Datenseite: 2 Monate nebeneinander, je 2 Tag-Halbspalten →
4 Zeit/Höhe-Spalten. Tagesnummern stehen in eigenen x-Bändern. Mondphasen
(A/B/C/D) und Wochentage (W/TH/F/...) sind reine Buchstaben → werden ignoriert.

WICHTIG (Zeitzone): Laut Notizseite sind die Zeiten lokale Uhrzeit inklusive
British Summer Time (mit den im PDF genannten DST-Daten). Der Seitenkopf "GMT"
ist irreführend. Wir geben die Zeiten daher als Europe/London Wall-Clock zurück;
die UTC-Umrechnung (DST-aware) macht das Fit-Skript.

Datum: Mostyn Chart Datum = 4.5 m unter ODN (Newlyn). Höhen in Metern.
"""
from __future__ import annotations
import re
from datetime import datetime
from pathlib import Path

import pdfplumber

MONTHS = {
    'January': 1, 'February': 2, 'March': 3, 'April': 4, 'May': 5, 'June': 6,
    'July': 7, 'August': 8, 'September': 9, 'October': 10, 'November': 11,
    'December': 12,
}

RE_TIME = re.compile(r'^\d{4}$')
RE_HEIGHT = re.compile(r'^\d{1,2}\.\d$')
RE_DAY = re.compile(r'^\d{1,2}$')


def _cluster_centers(xs, tol=15.0):
    """1-D Clustering der Spalten-x-Positionen → sortierte Zentren."""
    xs = sorted(xs)
    clusters = []
    for x in xs:
        if clusters and x - clusters[-1][-1] <= tol:
            clusters[-1].append(x)
        else:
            clusters.append([x])
    return [sum(c) / len(c) for c in clusters]


def parse_page(page):
    """Eine Datenseite → Liste (datetime_local_naive, height_m)."""
    words = page.extract_words(use_text_flow=False, keep_blank_chars=False)

    # Jahr aus Header
    year = None
    for i, w in enumerate(words):
        if w['text'] == 'Year' and i + 2 < len(words):
            m = re.match(r'^(\d{4})$', words[i + 2]['text'])
            if m:
                year = int(m.group(1))
    if year is None:
        for w in words:
            m = re.match(r'^(20\d{2})$', w['text'])
            if m:
                year = int(m.group(1)); break

    # Monatstitel: linker (kleinstes x) = Monat A (Spalten 0,1),
    # rechter = Monat B (Spalten 2,3)
    month_titles = sorted(
        [(w['x0'], MONTHS[w['text']]) for w in words if w['text'] in MONTHS],
        key=lambda t: t[0],
    )
    if len(month_titles) < 2:
        return []
    month_a = month_titles[0][1]
    month_b = month_titles[1][1]

    # Höhen-Tokens (Dezimalzahlen) sind in jeder Zeile vorhanden und sauber →
    # als Anker für die 4 Spalten nutzen. Die zugehörige Zeit steht ~46px links;
    # ältere PDFs zerlegen Zeiten in Fragmente ("1"+"525"), daher Ziffern-Concat.
    height_words = [w for w in words if RE_HEIGHT.match(w['text'])]
    if not height_words:
        return []
    height_cols = _cluster_centers([w['x0'] for w in height_words])
    if len(height_cols) != 4:
        return []

    def nearest_col(x, centers, tol=25.0):
        best, bd = None, 1e9
        for j, c in enumerate(centers):
            d = abs(x - c)
            if d < bd:
                bd, best = d, j
        return best if bd <= tol else None

    digit_words = [w for w in words if w['text'].isdigit()]

    # Tagesnummern: integer 1-31, ~78px links der zugehörigen Höhenspalte.
    # (Zeit liegt ~46px links der Höhe → klar abgegrenzt.)
    def day_column(x0):
        for j, c in enumerate(height_cols):
            if 60 <= (c - x0) <= 98:
                return j
        return None

    day_words = []   # (top, day_value, col)
    for w in digit_words:
        if len(w['text']) <= 2 and 1 <= int(w['text']) <= 31:
            col = day_column(w['x0'])
            if col is not None:
                day_words.append((w['top'], int(w['text']), col))

    # Pro Spalte: sortierte Liste (top, day_value)
    col_days = {0: [], 1: [], 2: [], 3: []}
    for top, dval, col in day_words:
        col_days[col].append((top, dval))
    for col in col_days:
        col_days[col].sort()

    def active_day(col, top):
        days = col_days.get(col, [])
        cur = None
        for dtop, dval in days:
            if dtop <= top + 2:   # kleine Toleranz
                cur = dval
            else:
                break
        return cur

    # Spalte → (Monat)
    col_month = {0: month_a, 1: month_a, 2: month_b, 3: month_b}

    results = []
    for hw in height_words:
        col = nearest_col(hw['x0'], height_cols, tol=25.0)
        if col is None:
            continue
        # Zeit = Ziffernfragmente derselben Zeile, 5..60px links der Höhe
        frags = [w for w in digit_words
                 if abs(w['top'] - hw['top']) <= 2.5 and 5 <= (hw['x0'] - w['x0']) <= 60]
        frags.sort(key=lambda w: w['x0'])
        tstr = ''.join(w['text'] for w in frags)
        if len(tstr) != 4:
            continue
        hh, mm = int(tstr[:2]), int(tstr[2:])
        if hh > 23 or mm > 59:
            continue
        day = active_day(col, hw['top'])
        if day is None:
            continue
        month = col_month[col]
        try:
            dt = datetime(year, month, day, hh, mm)
        except ValueError:
            continue
        results.append((dt, float(hw['text'])))

    return results


def parse_pdf(path: Path):
    out = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            txt = page.extract_text() or ''
            if 'Time' not in txt:   # Notizseite o.ä.
                continue
            out.extend(parse_page(page))
    # dedup + sort
    seen = set()
    cleaned = []
    for dt, h in sorted(out):
        key = (dt, round(h, 2))
        if key in seen:
            continue
        seen.add(key)
        cleaned.append((dt, h))
    return cleaned


if __name__ == '__main__':
    import sys
    d = Path('/home/oliver/weather/tide_tables/mostyn')
    files = sorted(d.glob('*.pdf'))
    if len(sys.argv) > 1:
        files = [Path(sys.argv[1])]
    for f in files:
        ev = parse_pdf(f)
        if ev:
            hh = [h for _, h in ev]
            print(f"{f.name:40s} {len(ev):5d} events  "
                  f"{ev[0][0].date()}..{ev[-1][0].date()}  "
                  f"h_min={min(hh):.1f} h_max={max(hh):.1f}")
        else:
            print(f"{f.name:40s} 0 events")
