#!/usr/bin/env python3
"""
Column-aware parser for CICESE Mexico monthly tide-prediction PDFs.

The PDF lays out each week as 7 day-columns. Each column may contain
1-4 HW/LW events depending on local tide regime (diurnal vs semidiurnal).
Plain text extraction loses column info; we use pdfplumber's word
bounding boxes to assign each value to its day.

Layout per page:
  Header rows (station, month, coords).
  For each weekly block:
    - day-numbers row (1-7 day integers at fixed column x-centers)
    - reference labels row(s): "<PMS_val> PMS", "<NMM_val> NMM", "0 BMI"
    - times row: HHMM integers at x positions matching the day columns
    - heights row: signed integers (cm) aligned to times row

We cluster words into rows by y-coordinate, find day-header rows, then
the next two non-label rows below are times and heights.
"""
import re
from datetime import datetime, timedelta
from pathlib import Path

import pdfplumber


MONTH_NAMES = {
    'enero': 1, 'febrero': 2, 'marzo': 3, 'abril': 4,
    'mayo': 5, 'junio': 6, 'julio': 7, 'agosto': 8,
    'septiembre': 9, 'octubre': 10, 'noviembre': 11, 'diciembre': 12,
}


def cluster_rows(words, y_tol=4):
    """Group words into rows by y-coordinate; return list of rows (sorted)."""
    sorted_words = sorted(words, key=lambda w: w['top'])
    rows = []
    cur_row = []
    cur_y = None
    for w in sorted_words:
        if cur_y is None or abs(w['top'] - cur_y) <= y_tol:
            cur_row.append(w)
            cur_y = w['top'] if cur_y is None else cur_y
        else:
            rows.append(sorted(cur_row, key=lambda x: x['x0']))
            cur_row = [w]
            cur_y = w['top']
    if cur_row:
        rows.append(sorted(cur_row, key=lambda x: x['x0']))
    return rows


def _is_int(s):
    return bool(re.match(r'^-?\d+$', s))


def parse_pdf(path):
    """Parse one CICESE PDF, returning dict with year/month/tz/entries."""
    with pdfplumber.open(path) as pdf:
        page = pdf.pages[0]
        # x_tolerance=1 is much tighter than the default 3 — needed because
        # CICESE PDFs render adjacent column values close enough that the
        # default sometimes merges them (e.g. "1808 2211" → "18082211" or
        # "750 1057" → "7501057").
        words = page.extract_words(x_tolerance=1)
        # Also grab text-extracted lines for header info
        text = page.extract_text()
    text_lines = [l.rstrip() for l in text.split('\n')]

    # Month/year from header
    year = month = None
    for line in text_lines[:10]:
        m = re.search(r'\b(ENERO|FEBRERO|MARZO|ABRIL|MAYO|JUNIO|JULIO|AGOSTO|SEPTIEMBRE|OCTUBRE|NOVIEMBRE|DICIEMBRE)\s+(\d{4})', line, re.IGNORECASE)
        if m:
            month = MONTH_NAMES[m.group(1).lower()]
            year = int(m.group(2))
            break
    if month is None or year is None:
        raise ValueError(f"Could not parse month/year from {path}")

    # TZ offset
    tz_offset_h = -6
    for line in text_lines:
        m = re.search(r'Meridiano:\s*(\d+)\s*W', line)
        if m:
            tz_offset_h = -int(m.group(1)) // 15
            break

    rows = cluster_rows(words)

    entries = []
    seen_days = set()

    # Find day-header rows: rows whose word texts form 1-7 consecutive 1-31
    # integers. Day numbers appear at fixed x-centers — we record them.
    i = 0
    DATA_X_MIN = 110
    while i < len(rows):
        row = rows[i]
        # A real day-header row has ONLY day numbers (1-31) in the data
        # area — no out-of-range integers like coordinates or heights.
        # The reference value (e.g. "400" for PMS) sits at x < DATA_X_MIN
        # and is excluded.
        data_ints = [w for w in row if _is_int(w['text']) and w['x0'] >= DATA_X_MIN]
        if not data_ints or len(data_ints) > 7:
            i += 1
            continue
        vals_all = [int(w['text']) for w in data_ints]
        # ALL data integers must be in 1-31 day range, otherwise it's
        # almost certainly a heights/coords row.
        if not all(1 <= v <= 31 for v in vals_all):
            i += 1
            continue
        vals = vals_all
        if not all(vals[k+1] == vals[k] + 1 for k in range(len(vals) - 1)):
            i += 1
            continue
        if any(d in seen_days for d in vals):
            i += 1
            continue
        # Single-day header (last day of month): require next non-label
        # row(s) to look like a valid times row — otherwise it's a
        # one-off label/footer integer that happened to land in [1,31].
        # Multi-day headers are already discriminating enough.
        day_x = {int(w['text']): (w['x0'] + w['x1']) / 2 for w in data_ints}
        n_days = len(vals)

        # Find times row: scan forward past reference-label rows. A row is
        # a label row if it contains any of the strings PMS/NMM/BMI as a
        # word, or only contains words in the leftmost reference column
        # (x < 150). The day columns start ~x=115 for the leftmost day.
        DATA_X_MIN = 110  # tokens to the left of this are reference/footer
        times_row = heights_row = None
        j = i + 1
        scanned = 0
        while j < len(rows) and scanned < 12:
            r = rows[j]
            # Skip rows containing label words
            if any(w['text'] in ('PMS', 'NMM', 'BMI') for w in r):
                j += 1
                scanned += 1
                continue
            # Keep only integer words in data columns
            data_ints = [w for w in r if _is_int(w['text']) and w['x0'] >= DATA_X_MIN]
            if len(data_ints) >= n_days:
                # HHMM plausibility on all values
                ok = all(
                    0 <= int(w['text']) <= 2400 and (int(w['text']) % 100) < 60
                    for w in data_ints
                )
                if ok:
                    times_row = data_ints
                    j += 1
                    # Heights row: next row with ≥ n_days integers in data columns
                    while j < len(rows):
                        r2 = rows[j]
                        if any(w['text'] in ('PMS', 'NMM', 'BMI') for w in r2):
                            j += 1
                            continue
                        h_ints = [w for w in r2 if _is_int(w['text']) and w['x0'] >= DATA_X_MIN]
                        if len(h_ints) >= n_days:
                            heights_row = h_ints
                            j += 1
                            break
                        j += 1
                    break
            j += 1
            scanned += 1

        if not (times_row and heights_row):
            i = j
            continue

        seen_days.update(vals)

        # Assign each times entry to a day by nearest x-center
        day_xs_sorted = sorted(day_x.items(), key=lambda kv: kv[1])
        day_list = [d for d, _ in day_xs_sorted]
        day_centers = [x for _, x in day_xs_sorted]

        def day_for_x(x):
            # find closest column center
            best = day_list[0]
            best_dx = abs(x - day_centers[0])
            for d, c in zip(day_list, day_centers):
                dx = abs(x - c)
                if dx < best_dx:
                    best = d
                    best_dx = dx
            return best

        # Pair times with heights by INDEX in their rows (both sorted by x)
        for idx, t_word in enumerate(times_row):
            if idx >= len(heights_row):
                break
            h_word = heights_row[idx]
            try:
                t_val = int(t_word['text'])
                h_cm = int(h_word['text'])
            except ValueError:
                continue
            hh, mm = divmod(t_val, 100)
            if not (0 <= hh <= 24 and 0 <= mm <= 59):
                continue
            # Sanity filter: physical heights are typically -300 to +800 cm
            # (Bay-of-Fundy extreme is ~1700 cm; Mexico stations max ~750).
            # Values outside this range are almost always a column-merge
            # artifact where a time (HHMM) ended up in the heights slot.
            if h_cm < -500 or h_cm > 1000:
                continue
            t_x = (t_word['x0'] + t_word['x1']) / 2
            day = day_for_x(t_x)
            try:
                dt = datetime(year, month, day, hh % 24, mm)
                if hh == 24:
                    dt += timedelta(days=1)
            except ValueError:
                continue
            entries.append((dt, h_cm / 100.0))

        i = j

    # Dedupe (same datetime can appear from row re-reads) and sort
    seen = {}
    for dt, h in entries:
        seen[dt] = h
    entries = sorted(seen.items())

    return {
        'year': year,
        'month': month,
        'tz_offset_h': tz_offset_h,
        'entries': entries,
    }


if __name__ == '__main__':
    import sys
    p = Path(sys.argv[1])
    r = parse_pdf(p)
    print(f"{p.name}: {r['year']}-{r['month']:02d}, TZ=UTC{r['tz_offset_h']:+d}, {len(r['entries'])} events")
    for dt, h in r['entries'][:8]:
        print(f"  {dt}  {h:+.2f} m")
    print('  ...')
    for dt, h in r['entries'][-8:]:
        print(f"  {dt}  {h:+.2f} m")
