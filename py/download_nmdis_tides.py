#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Stuendliche Tidenvorhersagen vom NMDIS-Datenportal (mds.nmdis.org.cn) laden.

NMDIS = National Marine Data and Information Service (国家海洋信息中心),
Herausgeber der offiziellen chinesischen Tidetafeln. Der Endpunkt liefert
pro Tag 24 Stundenwerte (a0..a23, cm ueber Tidenull) + HW/LW-Zeiten,
Zeitzone laut Feld timearea = "-0800" (Beijing, UTC+8),
benchmark z.B. "在平均海面下91cm" (Tidenull 91 cm unter Mittelwasser).

API: POST https://mds.nmdis.org.cn/service/rdata/front/knowledge/chaoxidata/list
     {"serchdate": "YYYY-MM-DD", "sitecode": "T020"}
Stationsliste: GET .../knowledge/site/list?areaId=<id> (Gebiete via area/list).
Verfuegbar (Stand 2026-06): ca. 2019 bis Ende Juli 2026.

Usage: python3 py/download_nmdis_tides.py T020 2024-07-01 2026-06-30
"""
import json
import sys
import time
import urllib.request
import ssl
from datetime import date, timedelta
from pathlib import Path

API = 'https://mds.nmdis.org.cn/service/rdata/front/knowledge/chaoxidata/list'
OUTDIR = Path('/home/oliver/water_levels/CN_nmdis')
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE


def fetch_day(sitecode, d):
    body = json.dumps({'serchdate': d.isoformat(), 'sitecode': sitecode}).encode()
    req = urllib.request.Request(API, data=body, headers={
        'Content-Type': 'application/json',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
    with urllib.request.urlopen(req, timeout=30, context=CTX) as r:
        return json.loads(r.read())


def main():
    sitecode, d0, d1 = sys.argv[1], date.fromisoformat(sys.argv[2]), date.fromisoformat(sys.argv[3])
    OUTDIR.mkdir(parents=True, exist_ok=True)
    out = OUTDIR / f'{sitecode}_{d0.isoformat()}_{d1.isoformat()}.json'
    cache = {}
    if out.exists():
        cache = json.loads(out.read_text())
        print(f'{len(cache)} Tage aus Cache {out.name}')

    d = d0
    n_req = 0
    meta = None
    while d <= d1:
        key = d.isoformat()
        if key not in cache:
            try:
                resp = fetch_day(sitecode, d)
            except Exception as e:
                print(f'{key}: FEHLER {e} - 5s Pause, retry')
                time.sleep(5)
                try:
                    resp = fetch_day(sitecode, d)
                except Exception as e2:
                    print(f'{key}: erneut FEHLER {e2} - skip')
                    d += timedelta(days=1)
                    continue
            data = resp.get('data') or []
            if data:
                rec = data[0]
                fd = rec['filedata']
                cache[key] = {
                    'hourly_cm': [fd.get(f'a{i}') for i in range(24)],
                    'benchmark': rec.get('benchmark'),
                    'timearea': rec.get('timearea'),
                    'title': rec.get('title'),
                    'coordinate': rec.get('coordinate'),
                }
                if meta is None:
                    meta = cache[key]
                    print('Meta:', meta['title'], meta['coordinate'], meta['benchmark'], meta['timearea'])
            else:
                cache[key] = None
            n_req += 1
            if n_req % 50 == 0:
                out.write_text(json.dumps(cache))
                print(f'{key}: {n_req} Requests, zwischengespeichert')
            time.sleep(0.12)
        d += timedelta(days=1)

    out.write_text(json.dumps(cache))
    ok = sum(1 for v in cache.values() if v)
    print(f'Fertig: {ok}/{len(cache)} Tage mit Daten -> {out}')


if __name__ == '__main__':
    main()
