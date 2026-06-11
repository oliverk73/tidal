#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""NCHMF-10-Tage-Tidenbulletins aus dem Wayback-Archiv nachladen.

Quellen (CDX, collapse=urlkey):
  thoitietvietnam.gov.vn//upload/haivan/Y/M/D/dbqg-tthv-YYYYMMDD_0930.pdf (2021-12..2022)
  kttv.gov.vn//upload/haivan/...                                          (2024..2026)
Eingabe: Liste 'timestamp original_url' (eine Zeile je Capture).
Lokaler Name: dbqg-tthv-<datum>_0930.pdf — vorhandene Dateien (>10KB)
werden uebersprungen (resume-faehig), je Bulletin-Datum nur 1 Download.

Usage: python3 py/download_nchmf_wayback.py /tmp/nchmf_all.txt
"""
import re
import sys
import time
import urllib.request
from pathlib import Path

DIR = Path('/home/oliver/water_levels/VN_nchmf')
UA = {'User-Agent': 'Mozilla/5.0 (tide-research; contact oliver.k73@gmail.com)'}


def main():
    lines = Path(sys.argv[1]).read_text().split('\n')
    by_date = {}
    for ln in lines:
        parts = ln.split()
        if len(parts) != 2:
            continue
        ts, url = parts
        m = re.search(r'dbqg-tthv-(\d{8})', url)
        if m:
            by_date.setdefault(m.group(1), []).append((ts, url))

    todo = []
    for date, caps in sorted(by_date.items()):
        out = DIR / f'dbqg-tthv-{date}_0930.pdf'
        if out.exists() and out.stat().st_size > 10240:
            continue
        todo.append((date, caps, out))
    print(f'{len(by_date)} Bulletin-Tage im Index, {len(todo)} fehlen', flush=True)

    ok = fail = 0
    for i, (date, caps, out) in enumerate(todo, 1):
        got = False
        for ts, url in caps:
            wb = f'http://web.archive.org/web/{ts}id_/{url}'
            for attempt in range(3):
                try:
                    req = urllib.request.Request(wb, headers=UA)
                    data = urllib.request.urlopen(req, timeout=90).read()
                    if data[:4] == b'%PDF' and len(data) > 10240:
                        out.write_bytes(data)
                        got = True
                    break
                except Exception as e:
                    code = getattr(e, 'code', None)
                    if code == 429 or 'too many' in str(e).lower():
                        time.sleep(60)
                        continue
                    time.sleep(10)
                    break
            if got:
                break
        ok += got
        fail += not got
        print(f'[{i}/{len(todo)}] {date} {"ok" if got else "FEHLT"}', flush=True)
        time.sleep(3)
    print(f'fertig: {ok} geladen, {fail} fehlgeschlagen', flush=True)


if __name__ == '__main__':
    main()
