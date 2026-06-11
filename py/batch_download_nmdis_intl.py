#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Batch-Download der internationalen NMDIS-Stationen (Luecken + Classic-Upgrades).

Wie batch_download_nmdis.py, aber ueber water_levels/CN_nmdis/intl_plan.json
(erzeugt aus sites_international_full.json, klass GAP/OLD). Gleicher
Tages-Cache (crash-sicher, resume-faehig), gleiche Dateinamen T###_D0_D1.json.

Usage: python3 py/batch_download_nmdis_intl.py
"""
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, '/home/oliver/py')
from download_nmdis_tides import fetch_day, OUTDIR

PLAN = Path('/home/oliver/water_levels/CN_nmdis/intl_plan.json')
D0, D1 = date(2025, 7, 1), date(2026, 6, 30)


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
        d += timedelta(days=1)
    out.write_text(json.dumps(cache))
    return code, 'neu', sum(1 for v in cache.values() if v)


def main():
    plan = json.loads(PLAN.read_text())
    t0 = time.time()
    print(f'{len(plan)} internationale Stationen, {(D1-D0).days+1} Tage/Station', flush=True)
    with ThreadPoolExecutor(max_workers=3) as ex:
        for i, (code, how, n_ok) in enumerate(ex.map(download_station, plan), 1):
            print(f'[{i}/{len(plan)} {(time.time()-t0)/60:5.1f}min] {code} {how} ({n_ok} Tage ok)', flush=True)


if __name__ == '__main__':
    main()
