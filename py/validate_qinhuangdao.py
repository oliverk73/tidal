#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Validierung des Qinhuangdao-Fits gegen die NMEFC-30-Tage-Vorhersage
(oceanguide.org.cn, 国家海洋预报中心 — unabhängige zweite Behörde neben NMDIS).

NMEFC: Zeiten Beijing-Zeit (UTC+8), Höhen cm. Das Feld cxdatum
"在平均海面下" beschreibt das Tidenull (unter MSL) — die Höhen sind
bereits relativ zum selben Tidenull wie NMDIS (empirisch: Offset 0.91
ergab dh_med exakt -0.910 m, ohne Offset ~0).

Usage: python3 py/validate_qinhuangdao.py  (nach TCD-Deploy)
"""
import csv
import json
import os
import re
import statistics
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

REF = Path('/home/oliver/water_levels/CN_nmdis/oceanguide_qinhuangdao_30d_20260610.json')
STATION = 'Qinhuangdao, Hebei, China'
MSL_OFFSET = 0.0    # NMEFC nutzt dasselbe Tidenull wie NMDIS (s. Docstring)


def load_ref():
    d = json.loads(REF.read_text())
    events, seen = [], set()
    year = 2026
    for row in d['obj']:
        m = re.match(r'(\d{2})月(\d{2})日', row['posttime'])
        mon, day = int(m.group(1)), int(m.group(2))
        if (mon, day) in seen:        # API liefert manche Tage doppelt (2. defekt)
            continue
        seen.add((mon, day))
        for pre, kind in [('ht', 'H'), ('lt', 'L')]:
            for idx in '12':
                t, v = row.get(f'{pre}time{idx}', ''), row.get(f'{pre}value{idx}', '')
                if not t or not v or not re.match(r'^\d{1,2}:\d{2}$', t):
                    continue
                hh, mi = map(int, t.split(':'))
                dt_utc = datetime(year, mon, day, hh, mi) - timedelta(hours=8)
                events.append((dt_utc, kind, float(v) / 100.0 + MSL_OFFSET))
    events.sort()
    return events


def xtide_events(b, e):
    env = os.environ.copy()
    r = subprocess.run(['tide', '-l', STATION, '-b', b, '-e', e,
                        '-f', 'c', '-m', 'p', '-em', 'pSsMm', '-z'],
                       capture_output=True, text=True, env=env)
    out = []
    for p in csv.reader(r.stdout.splitlines()):
        if len(p) >= 5 and 'Tide' in p[4]:
            t = p[2].replace(' UTC', '').strip()
            try:
                dt = datetime.strptime(p[1] + ' ' + t, '%Y-%m-%d %I:%M %p')
            except ValueError:
                continue
            out.append((dt, 'H' if 'High' in p[4] else 'L', float(p[3].split()[0])))
    return out


def main():
    ref = load_ref()
    print(f'NMEFC-Referenz: {len(ref)} HW/LW-Events '
          f'{ref[0][0]:%Y-%m-%d}..{ref[-1][0]:%Y-%m-%d} (UTC)')
    mine = xtide_events('2026-06-10 00:00', '2026-07-12 00:00')
    print(f'XTide: {len(mine)} Events')
    dts, dhs = [], []
    for rdt, rty, rh in ref:
        cand = [(abs((mdt - rdt).total_seconds()), mdt, mh)
                for mdt, mty, mh in mine if mty == rty]
        if not cand:
            continue
        d, mdt, mh = min(cand)
        if d > 3 * 3600:
            print('  kein Match:', rdt, rty)
            continue
        dts.append((mdt - rdt).total_seconds() / 60.0)
        dhs.append(mh - rh)
    print(f'n={len(dts)}  dt_med={statistics.median(dts):+.1f} min  '
          f'sigma={statistics.pstdev(dts):.1f} min')
    print(f'dh_med={statistics.median(dhs):+.3f} m  sigma_h={statistics.pstdev(dhs):.3f} m')
    big = [(rdt.strftime("%m-%d %H:%M"), round(d)) for (rdt, _, _), d in zip(ref, dts) if abs(d) > 45]
    if big:
        print('Ausreisser >45min:', big[:12])


if __name__ == '__main__':
    main()
