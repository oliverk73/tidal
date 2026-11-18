#!/usr/bin/env python3
"""Parse the 2024 Porto do Forno PDF using word positions.
Row-based approach: group words by y-position, then assign to 8 sub-columns."""

import re
import fitz
from datetime import datetime
from collections import defaultdict


def parse_2024_pdf(filename, year=2024):
    """Parse PDF with 4 months per page, 8 sub-columns."""
    doc = fitz.open(filename)

    page_months = [
        [1, 2, 3, 4],
        [5, 6, 7, 8],
        [9, 10, 11, 12],
    ]

    entries = []

    for page_idx, page in enumerate(doc):
        months = page_months[page_idx]
        words = page.get_text('words')

        # Find the 8 HORA x-positions (anchors for sub-columns)
        hora_words = [w for w in words if w[4] == 'HORA' and w[1] < 110]
        hora_xs = sorted(set(w[0] for w in hora_words))

        # Find day-number x-positions (should also be 8)
        day_words = [(w[0], w[1], w[4]) for w in words
                     if w[1] > 95 and w[1] < 170 and re.match(r'^\d{1,2}$', w[4])
                     and 1 <= int(w[4]) <= 31]
        day_xs = sorted(set(round(w[0], 0) for w in day_words))[:8]  # 8 unique x positions

        if len(day_xs) != 8:
            print(f"  Warning page {page_idx}: {len(day_xs)} day x-positions: {day_xs}")

        # Each sub-column has: day_x, then time and height nearby
        # Sub-columns 0,1 → months[0]; 2,3 → months[1]; etc.
        # Assign each sub-column an x-center
        sub_col_centers = day_xs

        def closest_subcol(x):
            """Find the sub-column index closest to x."""
            min_dist = 999
            best = 0
            for ci, cx in enumerate(sub_col_centers):
                dist = abs(x - cx)
                if dist < min_dist:
                    min_dist = dist
                    best = ci
            return best

        # Pass 1: Find all day numbers with their (subcol, y) positions
        data_words = [(w[0], w[1], w[4]) for w in words if w[1] > 95]
        data_words = [(x, y, t) for x, y, t in data_words
                      if t not in ('v', 'c', '&', '*', 'z', 'DG6-63', 'Original')]

        # Collect day assignments: for each subcol, list of (y_pos, day_number)
        day_assignments = defaultdict(list)  # subcol -> [(y, day)]
        for x, y, text in data_words:
            if re.match(r'^\d{1,2}$', text):
                val = int(text)
                if 1 <= val <= 31:
                    ci = closest_subcol(x)
                    day_assignments[ci].append((y, val))

        # Sort each subcol's days by y
        for ci in day_assignments:
            day_assignments[ci].sort()

        def get_day_for_subcol(ci, y):
            """Find the active day for subcol ci at y position."""
            best_day = None
            for dy, dval in day_assignments[ci]:
                if dy <= y + 3:  # day number can be slightly below first time
                    best_day = dval
                else:
                    break
            return best_day

        # Pass 2: Find time-height pairs and assign to days
        # Group by y with tolerance
        rows = defaultdict(list)
        for x, y, t in data_words:
            y_key = round(y / 2) * 2
            rows[y_key].append((x, y, t))

        for y_key in sorted(rows.keys()):
            row = sorted(rows[y_key], key=lambda w: w[0])

            i = 0
            while i < len(row):
                x, y, text = row[i]
                if re.match(r'^\d{4}$', text):
                    hour = int(text[:2])
                    minute = int(text[2:])
                    if i + 1 < len(row):
                        x2, y2, text2 = row[i + 1]
                        if re.match(r'^-?\d+\.\d+$', text2) and abs(x2 - x) < 30:
                            height = float(text2)
                            ci = closest_subcol(x)
                            month = months[ci // 2]
                            day = get_day_for_subcol(ci, y)

                            if day and hour < 24:
                                try:
                                    dt = datetime(year, month, day, hour, minute)
                                    entries.append((dt, height))
                                except ValueError:
                                    pass
                            i += 2
                            continue
                i += 1

    return entries


if __name__ == '__main__':
    entries = parse_2024_pdf('/home/oliver/weather/tide_tables/brazil/40_-_porto_do_forno_2024_ok.pdf')
    entries.sort(key=lambda e: e[0])

    # Remove duplicates
    seen = set()
    unique = []
    for dt, h in entries:
        if dt not in seen:
            seen.add(dt)
            unique.append((dt, h))
    entries = unique

    print(f"Total entries: {len(entries)}")
    if entries:
        print(f"First: {entries[0]}")
        print(f"Last:  {entries[-1]}")

    from collections import Counter
    month_counts = Counter(e[0].month for e in entries)
    for m in range(1, 13):
        print(f"  Month {m:2d}: {month_counts.get(m, 0)} entries")

    print("\nJanuar 1-3:")
    for dt, h in entries:
        if dt.month == 1 and dt.day <= 3:
            print(f"  {dt.strftime('%d.%m %H:%M')}  {h}m")

    # Verify: Jan 1, 2024 was Monday
    import calendar
    dow = calendar.day_name[datetime(2024, 1, 1).weekday()]
    print(f"\nJan 1, 2024 = {dow}")

    # Expected for Jan 1: 0000 0.2, 0556 1.0, 1204 0.5, 1734 1.0
    print("Expected Jan 1: 00:00/0.2  05:56/1.0  12:04/0.5  17:34/1.0")
