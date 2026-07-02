#!/usr/bin/env python3
"""
Generischer Parser für UKHO-Hafen-Tidenkalender-PDFs (Standard-Layout, wie es
Port of Mostyn, Montrose Port, Harwich Haven u.v.a. veröffentlichen).

Layout pro Datenseite: 2 Monate nebeneinander, je 2 Tag-Halbspalten →
4 Zeit/Höhe-Spalten. Tagesnummern stehen in eigenen x-Bändern. Mondphasen
(A/B/C/D) und Wochentage (W/TH/F/...) sind reine Buchstaben → werden ignoriert.
Höhen mit 1 oder 2 Nachkommastellen (8.6 oder 4.53).

Gibt naive lokale Datetimes + Höhen (m) zurück; die Zeitzonen-Behandlung
(UTC vs. Europe/London-BST) übernimmt das aufrufende Fit-Skript — die meisten
UKHO-Hafenbooklets sind GMT/UTC ganzjährig, Mostyn ist die BST-Ausnahme.
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
RE_HEIGHT = re.compile(r'^\d{1,2}\.\d{1,2}$')
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

    # Monatstitel (links→rechts). N Monate pro Seite → 2N Spalten
    # (je Monat 2 Tag-Halbspalten). col_month[j] = months[j//2].
    month_titles = sorted(
        [(w['x0'], MONTHS[w['text'].capitalize()]) for w in words
         if w['text'].capitalize() in MONTHS],
        key=lambda t: t[0],
    )
    if len(month_titles) < 2:
        return []
    months = [m for _, m in month_titles]

    # Höhen-Tokens (Dezimalzahlen) als Spalten-Anker.
    height_words = [w for w in words if RE_HEIGHT.match(w['text'])]
    if not height_words:
        return []
    height_cols = _cluster_centers([w['x0'] for w in height_words])
    if len(height_cols) != 2 * len(months):
        return []
    colsp = (height_cols[-1] - height_cols[0]) / (len(height_cols) - 1)
    col_month = {j: months[j // 2] for j in range(len(height_cols))}

    def nearest_col(x, tol):
        best, bd = None, 1e9
        for j, c in enumerate(height_cols):
            d = abs(x - c)
            if d < bd:
                bd, best = d, j
        return best if bd <= tol else None

    digit_words = [w for w in words if w['text'].isdigit()]

    def row_digits(col, top):
        """Ziffern-Tokens dieser Spalte+Zeile (links der Höhe, innerhalb colsp)."""
        c = height_cols[col]
        toks = [w for w in digit_words if abs(w['top'] - top) <= 2.5
                and (c - colsp + 2) < w['x0'] < (c - 2)]
        return sorted(toks, key=lambda w: w['x0'])

    def split_time_day(toks):
        """Rechte Tokens, die zusammen 4 Ziffern ergeben = Zeit; ein verbleibendes
        1-2-stelliges Token links davon = Tagesnummer."""
        digs = [t['text'] for t in toks]
        # von rechts 4 Ziffern als Zeit sammeln
        acc, i = '', len(digs)
        while i > 0 and len(acc) < 4:
            i -= 1
            acc = digs[i] + acc
        if len(acc) != 4:
            return None, None
        tstr = acc
        day = None
        if i - 1 >= 0 and len(digs[i - 1]) <= 2:
            v = int(digs[i - 1])
            if 1 <= v <= 31:
                day = v
        return tstr, day

    # Tagesnummern pro Spalte sammeln (für active_day-Tracking)
    col_days = {j: [] for j in range(len(height_cols))}
    for hw in height_words:
        col = nearest_col(hw['x0'], tol=colsp * 0.45)
        if col is None:
            continue
        _, day = split_time_day(row_digits(col, hw['top']))
        if day is not None:
            col_days[col].append((hw['top'], day))
    for col in col_days:
        col_days[col].sort()

    def active_day(col, top):
        cur = None
        for dtop, dval in col_days[col]:
            if dtop <= top + 2:
                cur = dval
            else:
                break
        return cur

    results = []
    for hw in height_words:
        col = nearest_col(hw['x0'], tol=colsp * 0.45)
        if col is None:
            continue
        tstr, _ = split_time_day(row_digits(col, hw['top']))
        if tstr is None:
            continue
        hh, mm = int(tstr[:2]), int(tstr[2:])
        if hh > 23 or mm > 59:
            continue
        day = active_day(col, hw['top'])
        if day is None:
            continue
        try:
            dt = datetime(year, col_month[col], day, hh, mm)
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
    d = Path('/home/oliver/tide_tables/mostyn')
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
