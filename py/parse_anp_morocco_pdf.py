#!/usr/bin/env python3
"""
Parser for the Moroccan ANP / Direction Générale de la Météorologie
annual tide-prediction PDFs (Annuaire des Marées – Ports du Maroc).

URL pattern:
  https://extranet.marocmeteo.ma/ftp/catalogues/anp/marees/maree_<Port>.pdf

Each PDF: 1 title page + 12 monthly pages.
Each monthly page is a table with 4 time/height column-pairs per row:
  HW1 (Pleins mer, La première)  – x≈116 / 174
  HW2 (Pleins mer, La deuxième)  – x≈226 / 284
  LW1 (Basse  mer, La première)  – x≈336 / 393
  LW2 (Basse  mer, La deuxième)  – x≈445 / 503
Day column at x≈68. Times in HH:MM, UTC+1. Heights in meters
(reference: Bassin Marin Inférieur, BMI ≈ chart datum).

Header on each monthly page contains the port name and coordinates,
title page contains "ANNUAIRE DES MAREES YYYY".

Public API:
  parse_pdf(path) -> dict {year, tz_offset_h, station_header, lat, lon, entries}
  entries = [(datetime_local, height_m), ...] (HW and LW mixed, sorted by time)
"""
from __future__ import annotations
import re
from datetime import datetime, timedelta
from pathlib import Path

import pdfplumber


MONTHS_FR = {
    'Janvier': 1, 'Février': 2, 'Mars': 3, 'Avril': 4,
    'Mai': 5, 'Juin': 6, 'Juillet': 7, 'Août': 8,
    'Septembre': 9, 'Octobre': 10, 'Novembre': 11, 'Décembre': 12,
}

# Default column centers (used for Sidi Ifni / Apr-Dec template).
# Some PDFs use a different layout; column positions are auto-detected
# per page from the HH:MM and decimal-number token x-distribution.
TIME_X = [127.6, 237.5, 347.0, 456.5]
HEIGHT_X = [182.8, 292.3, 401.8, 511.3]
COL_TOL = 10.0
DAY_X = 71.0
ROW_Y_TOL = 3.0

TIME_RE = re.compile(r'^([01]?\d|2[0-4]):([0-5]\d)$')
HEIGHT_RE = re.compile(r'^-?\d+([.,]\d+)?$')


def _which_col(x_center, centers, tol=COL_TOL):
    for i, c in enumerate(centers):
        if abs(x_center - c) <= tol:
            return i
    return -1


def _detect_columns(words, expected=4, cluster_tol=15.0):
    """Cluster word x-centers and return the `expected` densest cluster centers,
    or None if the data is too sparse / clusters don't separate cleanly."""
    if len(words) < expected * 5:
        return None
    xs = sorted((w['x0'] + w['x1']) / 2 for w in words)
    clusters = [[xs[0]]]
    for x in xs[1:]:
        if x - clusters[-1][-1] <= cluster_tol:
            clusters[-1].append(x)
        else:
            clusters.append([x])
    # Sort clusters by population, keep top `expected`
    clusters.sort(key=len, reverse=True)
    top = clusters[:expected]
    if len(top) < expected:
        return None
    centers = sorted(sum(c) / len(c) for c in top)
    return centers


def _cluster_rows(words):
    sw = sorted(words, key=lambda w: w['top'])
    rows = []
    cur = []
    cur_y = None
    for w in sw:
        if cur_y is None or abs(w['top'] - cur_y) <= ROW_Y_TOL:
            cur.append(w)
            cur_y = w['top'] if cur_y is None else cur_y
        else:
            rows.append(sorted(cur, key=lambda x: x['x0']))
            cur = [w]
            cur_y = w['top']
    if cur:
        rows.append(sorted(cur, key=lambda x: x['x0']))
    return rows


def _parse_coords(line):
    """Match "(29° 33' N , 10° 04' W)" → (lat_deg, lon_deg)."""
    m = re.search(
        r'\(\s*(\d+)°\s*(\d+)\'?\s*([NS])\s*,\s*(\d+)°\s*(\d+)\'?\s*([EW])\s*\)',
        line)
    if not m:
        return None
    lat = int(m.group(1)) + int(m.group(2)) / 60.0
    if m.group(3) == 'S':
        lat = -lat
    lon = int(m.group(4)) + int(m.group(5)) / 60.0
    if m.group(6) == 'W':
        lon = -lon
    return (lat, lon)


def parse_pdf(path):
    """Return dict {year, tz_offset_h, station_header, lat, lon, entries}."""
    entries = []
    year = None
    station_header = None
    lat = lon = None

    with pdfplumber.open(str(path)) as pdf:
        # Title page
        title_text = pdf.pages[0].extract_text() or ''
        m = re.search(r'ANNUAIRE DES MAREES\s+(\d{4})', title_text, re.I)
        if m:
            year = int(m.group(1))
        m = re.search(r'PORT DE\s+([A-ZÀÂÉÈÊËÎÏÔÛÜÇ \-]+?)\s*$',
                      title_text, re.I | re.M)
        if m:
            station_header = m.group(1).strip().title()

        for page in pdf.pages[1:]:
            text = page.extract_text() or ''
            words = page.extract_words(x_tolerance=1)

            # Month header
            month = None
            page_year = year
            for line in text.split('\n')[:6]:
                for mname, midx in MONTHS_FR.items():
                    if mname in line:
                        month = midx
                        m = re.search(r'(\d{4})\s*$', line.strip())
                        if m:
                            page_year = int(m.group(1))
                        break
                if month is not None:
                    break
            if month is None:
                continue

            # Coordinates (any line of page)
            if lat is None:
                for line in text.split('\n'):
                    c = _parse_coords(line)
                    if c:
                        lat, lon = c
                        break

            # Auto-detect column centers from the page's own token distribution.
            page_times = [w for w in words if TIME_RE.match(w['text'])]
            page_heights = [w for w in words
                            if HEIGHT_RE.match(w['text'])
                            and ',' in w['text'] + '.' or '.' in w['text']]
            time_x = _detect_columns(page_times, expected=4) or TIME_X
            height_x = _detect_columns(page_heights, expected=4) or HEIGHT_X
            # Day column = leftmost integer column on data rows
            page_days = [w for w in words
                         if w['text'].isdigit() and 1 <= int(w['text']) <= 31]
            day_xs = sorted((w['x0'] + w['x1']) / 2 for w in page_days)
            day_x = day_xs[0] if day_xs else DAY_X

            rows = _cluster_rows(words)
            for row in rows:
                # Find day number at the page's day-column x
                day = None
                for w in row:
                    xc = (w['x0'] + w['x1']) / 2
                    if abs(xc - day_x) <= COL_TOL and w['text'].isdigit():
                        v = int(w['text'])
                        if 1 <= v <= 31:
                            day = v
                            break
                if day is None:
                    continue

                # Collect times and heights per column
                times = [None, None, None, None]
                heights = [None, None, None, None]
                for w in row:
                    xc = (w['x0'] + w['x1']) / 2
                    txt = w['text']
                    mt = TIME_RE.match(txt)
                    if mt:
                        col = _which_col(xc, time_x)
                        if col >= 0:
                            times[col] = (int(mt.group(1)), int(mt.group(2)))
                        continue
                    if HEIGHT_RE.match(txt):
                        col = _which_col(xc, height_x)
                        if col >= 0:
                            try:
                                heights[col] = float(txt.replace(',', '.'))
                            except ValueError:
                                pass

                for col in range(4):
                    if times[col] is None or heights[col] is None:
                        continue
                    hh, mm = times[col]
                    try:
                        if hh == 24:
                            dt = datetime(page_year, month, day, 0, mm) \
                                + timedelta(days=1)
                        else:
                            dt = datetime(page_year, month, day, hh, mm)
                    except ValueError:
                        continue
                    entries.append((dt, heights[col]))

    if year is None:
        raise ValueError(f"Could not parse year from {path}")

    seen = {}
    for dt, h in entries:
        seen[dt] = h
    entries = sorted(seen.items())

    return {
        'year': year,
        'tz_offset_h': 1,  # Morocco uses UTC+1 year-round (since 2018)
        'station_header': station_header or '',
        'lat': lat,
        'lon': lon,
        'entries': entries,
    }


if __name__ == '__main__':
    import sys
    p = Path(sys.argv[1])
    r = parse_pdf(p)
    print(f"{p.name}: year={r['year']}, TZ=UTC+{r['tz_offset_h']}, "
          f"station={r['station_header']!r}, lat={r['lat']}, lon={r['lon']}, "
          f"{len(r['entries'])} events")
    for dt, h in r['entries'][:6]:
        print(f"  {dt}  {h:+.2f} m")
    print('  ...')
    for dt, h in r['entries'][-6:]:
        print(f"  {dt}  {h:+.2f} m")
