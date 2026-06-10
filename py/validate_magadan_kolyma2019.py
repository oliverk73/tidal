#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Out-of-Sample-Validierung des Magadan-Fits gegen die offizielle
Kolymskoe-UGMS-Tabelle Februar 2019 (Bucht Nagaeva) von kolyma.ru.

Der Fit basiert auf Apr 2025 - Mai 2026 (Bucht Gertnera); Feb 2019 liegt
6 Jahre davor => echter Nodal-/OOS-Test. Nagaeva = Gertnera + 11 min.

Usage: python3 py/validate_magadan_kolyma2019.py /tmp/kolyma_feb2019.html
"""
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import utide

sys.path.insert(0, '/home/oliver/py')
sys.path.insert(0, '/home/oliver/batch')
from fit_magadan_rybalka import load_events, fit, STATIONS

HTML = Path(sys.argv[1] if len(sys.argv) > 1 else '/tmp/kolyma_feb2019.html')
UTC_OFF = timedelta(hours=11)
NAGAEVA_SHIFT_MIN = 11.0


def parse_kolyma():
    txt = HTML.read_bytes().decode('windows-1251')
    tb = next(t for t in re.findall(r'<table.*?</table>', txt, re.S) if 'Мв' in t)
    rows = re.findall(r'<tr[^>]*>(.*?)</tr>', tb, re.S)
    # 3 Spaltengruppen je (число, фаза, время, высота); Tage 1-10/11-20/21-28
    groups = [[], [], []]   # je Gruppe: Liste (день|None, фаза, h, m, height)
    for r in rows:
        cells = [re.sub(r'<[^>]+>', ' ', c).replace('\xa0', ' ').strip()
                 for c in re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', r, re.S)]
        if len(cells) != 12 or 'число' in cells[0]:
            continue
        for g in range(3):
            day_s, faza, tm, hgt = cells[4 * g:4 * g + 4]
            tmm = re.match(r'(\d{1,2})[.:](\d{2})', tm)
            hgm = re.match(r'(-?\d+(?:,\d+)?)', hgt)
            day = int(day_s) if day_s.strip().isdigit() else None
            if faza in ('Мв', 'Пв') and tmm and hgm:
                groups[g].append((day, faza, int(tmm.group(1)), int(tmm.group(2)),
                                  float(hgm.group(1).replace(',', '.'))))

    events = []
    for g, ev in enumerate(groups):
        # Tagesgrenzen: Zeit springt zurueck => neuer Tag; число-Marker validieren
        blocks = [[]]
        for e in ev:
            if blocks[-1] and (e[2], e[3]) < (blocks[-1][-1][2], blocks[-1][-1][3]):
                blocks.append([])
            blocks[-1].append(e)
        first_day = 1 + 10 * g
        expected = {0: 10, 1: 10, 2: 8}[g]
        assert len(blocks) == expected, f'Gruppe {g}: {len(blocks)} Bloecke != {expected}'
        # Marker-Konsistenz: jeder число-Marker muss im Block seines Tages liegen
        for bi, blk in enumerate(blocks):
            for e in blk:
                if e[0] is not None:
                    assert e[0] == first_day + bi, f'Marker {e[0]} in Block {first_day + bi}'
        for bi, blk in enumerate(blocks):
            day = first_day + bi
            for _, faza, hh, mi, h in blk:
                dt_loc = datetime(2019, 2, day, hh, mi)
                events.append((dt_loc - UTC_OFF, 'H' if faza == 'Пв' else 'L', h))
    events.sort()
    return events


def main():
    table = parse_kolyma()
    print(f'UGMS Feb 2019 (Nagaeva): {len(table)} Events geparst')
    bad = sum(1 for a, b in zip(table, table[1:]) if a[1] == b[1])
    print(f'Alternations-Verstoesse: {bad}')

    hw_lw = load_events()
    coef, r2, *_ = fit(list(hw_lw), STATIONS[1][1])

    # 1-min-Rekonstruktion Feb 2019 (UTC), Nagaeva = Gertnera(t - 11min)
    t0 = datetime(2019, 1, 31, 0, 0)
    times = np.array([t0 + timedelta(minutes=i) for i in range(31 * 24 * 60)])
    shift = np.array([t - timedelta(minutes=NAGAEVA_SHIFT_MIN) for t in times])
    h = utide.reconstruct(shift, coef, verbose=False)['h']

    # Extrema der Rekonstruktion
    ext = []
    for i in range(1, len(h) - 1):
        if h[i] >= h[i - 1] and h[i] > h[i + 1]:
            ext.append((times[i], 'H', h[i]))
        elif h[i] <= h[i - 1] and h[i] < h[i + 1]:
            ext.append((times[i], 'L', h[i]))

    dts, dhs = [], []
    for tdt, tty, th in table:
        cand = [(abs((edt - tdt).total_seconds()), edt, eh)
                for edt, ety, eh in ext if ety == tty]
        d, edt, eh = min(cand)
        if d > 3 * 3600:
            print('  kein Match:', tdt, tty, th)
            continue
        dts.append((edt - tdt).total_seconds() / 60.0)
        dhs.append(eh - th)
    import statistics
    print(f'n={len(dts)}  dt_med={statistics.median(dts):+.1f} min  '
          f'dt_mean={statistics.mean(dts):+.1f}  sigma={statistics.pstdev(dts):.1f} min')
    print(f'dh_med={statistics.median(dhs):+.3f} m  sigma_h={statistics.pstdev(dhs):.3f} m')
    big = [(t, round(d)) for (t, ty, hh), d in zip(table, dts) if abs(d) > 30]
    if big:
        print('Ausreisser >30min:', big[:10])


if __name__ == '__main__':
    main()
