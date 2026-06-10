#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Batch-Download aller geplanten NMDIS-China-Stationen (P1 -> P2 -> P3).

Liest water_levels/CN_nmdis/batch_plan.json (py/plan_nmdis_batch.py),
laedt je Station 1 Jahr Stundenwerte (2025-07-01..2026-06-30) ueber
fetch_day() aus download_nmdis_tides. 3 parallele Worker (moderat fuer
Behoerden-API), Tages-Cache pro Station (crash-sicher, resume-faehig).

Usage: python3 py/batch_download_nmdis.py [--prios P1,P2,P3]
"""
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, '/home/oliver/py')
from download_nmdis_tides import fetch_day, OUTDIR

PLAN = Path('/home/oliver/water_levels/CN_nmdis/batch_plan.json')
D0, D1 = date(2025, 7, 1), date(2026, 6, 30)
PRIOS = ('P1', 'P2', 'P3')


def download_station(st):
    code = st['code']
    out = OUTDIR / f'{code}_{D0.isoformat()}_{D1.isoformat()}.json'
    cache = json.loads(out.read_text()) if out.exists() else {}
    n_days = (D1 - D0).days + 1
    if len(cache) >= n_days:
        return code, 'cache', sum(1 for v in cache.values() if v)
    d = D0
    n_req = 0
    while d <= D1:
        key = d.isoformat()
        if key not in cache:
            try:
                resp = fetch_day(code, d)
            except Exception:
                time.sleep(5)
                try:
                    resp = fetch_day(code, d)
                except Exception:
                    d += timedelta(days=1)
                    continue
            data = resp.get('data') or []
            if data:
                rec = data[0]
                fd = rec['filedata']
                cache[key] = {'hourly_cm': [fd.get(f'a{i}') for i in range(24)],
                              'benchmark': rec.get('benchmark'),
                              'timearea': rec.get('timearea'),
                              'title': rec.get('title'),
                              'coordinate': rec.get('coordinate')}
            else:
                cache[key] = None
            n_req += 1
            if n_req % 60 == 0:
                out.write_text(json.dumps(cache))
            time.sleep(0.1)
        d += timedelta(days=1)
    out.write_text(json.dumps(cache))
    ok = sum(1 for v in cache.values() if v)
    return code, 'neu', ok


def main():
    prios = PRIOS
    if '--prios' in sys.argv:
        prios = tuple(sys.argv[sys.argv.index('--prios') + 1].split(','))
    plan = [s for s in json.loads(PLAN.read_text()) if s['prio'] in prios]
    print(f'{len(plan)} Stationen ({",".join(prios)}), {(D1-D0).days+1} Tage/Station', flush=True)
    t0 = time.time()
    done = 0
    with ThreadPoolExecutor(max_workers=3) as ex:
        for code, how, ok in ex.map(download_station, plan):
            done += 1
            el = (time.time() - t0) / 60
            print(f'[{done}/{len(plan)} {el:5.1f}min] {code} {how} ({ok} Tage ok)', flush=True)
    print('BATCH FERTIG', flush=True)


if __name__ == '__main__':
    main()
