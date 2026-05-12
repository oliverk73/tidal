#!/usr/bin/env python3
"""
Parser for SEMAR Mexico annual tide-prediction PDFs (Tablas Numéricas).

Each PDF covers one year, one page per month, three day-columns per page
(days 1-10, 11-20, 21-31). Per day: 1-4 HW/LW events with HHMM, feet, meters.

We use pdfplumber word bounding boxes; the three columns sit at well-separated
x-ranges, so day assignment by closest HORA-column x-center is robust.

Each PDF footer line on the last page contains:
  HORA DEL MERIDIANO LOCAL NN° W
This determines the time-zone offset (Mexico uses 75°/90°/105°/120° W).
"""
import re
from datetime import datetime, timedelta
from pathlib import Path

import pdfplumber


MONTHS = {
    'ENERO': 1, 'FEBRERO': 2, 'MARZO': 3, 'ABRIL': 4,
    'MAYO': 5, 'JUNIO': 6, 'JULIO': 7, 'AGOSTO': 8,
    'SEPTIEMBRE': 9, 'OCTUBRE': 10, 'NOVIEMBRE': 11, 'DICIEMBRE': 12,
}

# X-center ranges for HORA column (one per day-column)
HORA_X_CENTERS = [99.0, 228.5, 358.0]
DIA_X_CENTERS = [55.0, 190.0, 320.0]
COL_TOL = 25.0  # x-tolerance in points

DEC_RE = re.compile(r'^-?\d+\.\d+$')
TIME_RE = re.compile(r'^\d{4}$')


def _cluster_rows(words, y_tol=3):
    sw = sorted(words, key=lambda w: w['top'])
    rows = []
    cur = []
    cur_y = None
    for w in sw:
        if cur_y is None or abs(w['top'] - cur_y) <= y_tol:
            cur.append(w)
            cur_y = w['top'] if cur_y is None else cur_y
        else:
            rows.append(sorted(cur, key=lambda x: x['x0']))
            cur = [w]
            cur_y = w['top']
    if cur:
        rows.append(sorted(cur, key=lambda x: x['x0']))
    return rows


def _which_col(x_center, centers, tol=COL_TOL):
    for i, c in enumerate(centers):
        if abs(x_center - c) <= tol:
            return i
    return -1


def parse_pdf(path):
    """Return dict {year, tz_offset_h, station_header, entries:[(datetime_local, height_m)]}."""
    entries = []
    year = None
    tz_offset_h = None
    station_header = None

    with pdfplumber.open(str(path)) as pdf:
        for page in pdf.pages:
            words = page.extract_words(x_tolerance=1)
            text = page.extract_text() or ''

            # Header parse
            for line in text.split('\n')[:3]:
                m = re.search(
                    r'ESTACI[ÓO]N\s+(.+?)\s+(' + '|'.join(MONTHS) + r')\s+(\d{4})',
                    line, re.IGNORECASE,
                )
                if m:
                    if station_header is None:
                        station_header = m.group(1).strip()
                    month_name = m.group(2).upper()
                    month = MONTHS[month_name]
                    year_pg = int(m.group(3))
                    if year is None:
                        year = year_pg
                    break
            else:
                continue

            # TZ from footer
            for line in text.split('\n'):
                m = re.search(r'MERIDIANO\s+LOCAL\s+(\d+)\s*[°º]?\s*W', line, re.IGNORECASE)
                if m and tz_offset_h is None:
                    tz_offset_h = -int(m.group(1)) // 15
                    break

            # Cluster rows
            rows = _cluster_rows(words)

            # Active days per column (set when we encounter a row with day numbers)
            day_in_col = [None, None, None]

            for row in rows:
                # Skip header rows
                texts = [w['text'] for w in row]
                if any(t in ('DÍA', 'HORA', 'PIES', 'METROS') for t in texts):
                    continue
                # Skip day-name rows (Lunes, Martes... — all alpha words)
                if all(not (TIME_RE.match(t) or DEC_RE.match(t) or t.isdigit())
                       for t in texts):
                    continue

                # Look for integer day numbers in DIA column ranges
                for w in row:
                    if w['text'].isdigit():
                        v = int(w['text'])
                        xc = (w['x0'] + w['x1']) / 2
                        col = _which_col(xc, DIA_X_CENTERS)
                        if col >= 0 and 1 <= v <= 31:
                            day_in_col[col] = v

                # Parse HORA + METROS pairs per column
                # For each column: find HHMM word at HORA-center, then nearest decimal at METROS-center on same row
                # Strategy: iterate words; if HHMM in HORA x-range → store; if decimal in METROS x-range → match to last unmatched HHMM in same column
                pending_hhmm = [None, None, None]
                for w in row:
                    xc = (w['x0'] + w['x1']) / 2
                    txt = w['text']
                    if TIME_RE.match(txt):
                        col = _which_col(xc, HORA_X_CENTERS)
                        if col >= 0:
                            hh = int(txt) // 100
                            mm = int(txt) % 100
                            if 0 <= hh <= 24 and 0 <= mm <= 59:
                                pending_hhmm[col] = (hh, mm)
                    elif DEC_RE.match(txt):
                        # METROS column center ~ HORA center + ~60
                        col = _which_col(xc, [c + 60 for c in HORA_X_CENTERS], tol=COL_TOL)
                        if col >= 0 and pending_hhmm[col] is not None and day_in_col[col] is not None:
                            try:
                                meters = float(txt)
                            except ValueError:
                                continue
                            hh, mm = pending_hhmm[col]
                            try:
                                dt = datetime(year_pg, month, day_in_col[col],
                                              hh % 24, mm)
                                if hh == 24:
                                    dt += timedelta(days=1)
                                entries.append((dt, meters))
                            except ValueError:
                                pass
                            # Consume so we don't re-match
                            pending_hhmm[col] = None

    if year is None or tz_offset_h is None:
        raise ValueError(f"Could not parse year or meridian from {path}")

    # Dedupe (same datetime can show up in multiple parses); keep last value
    seen = {}
    for dt, h in entries:
        seen[dt] = h
    entries = sorted(seen.items())

    return {
        'year': year,
        'tz_offset_h': tz_offset_h,
        'station_header': station_header or '',
        'entries': entries,
    }


if __name__ == '__main__':
    import sys
    p = Path(sys.argv[1])
    r = parse_pdf(p)
    print(f"{p.name}: year={r['year']}, TZ=UTC{r['tz_offset_h']:+d}, "
          f"station={r['station_header']!r}, {len(r['entries'])} events")
    for dt, h in r['entries'][:6]:
        print(f"  {dt}  {h:+.2f} m")
    print('  ...')
    for dt, h in r['entries'][-6:]:
        print(f"  {dt}  {h:+.2f} m")
