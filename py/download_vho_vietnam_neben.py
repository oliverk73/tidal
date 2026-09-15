#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Stuendliche VHO-Vorhersagen fuer die 32 Stationen, die download_vho_vietnam.py nicht kennt.

Das Portal thuydacvietnam.org.vn fuehrt 49 Stationen (DIZI1..DIZI49). Die 17 Hauptstationen haben
Vorhersagen 2022..2026; die uebrigen 32 nur 2022..2024 (15.09.2026 geprueft, fuer 2025/26
"Khong tim thay du bao thuy trieu"). Geladen wird ein volles Jahr (2024), eine Anfrage je Sekunde,
ehrlicher User-Agent. Tages-Cache je Station (resume-faehig), Format wie download_vho_vietnam.py.

Usage: python3 py/download_vho_vietnam_neben.py [--jahr 2024]
"""
from __future__ import annotations

import json
import re
import ssl
import sys
import time
import urllib.request
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from download_vho_vietnam import parse_day  # noqa: E402

BASE = 'https://thuydacvietnam.org.vn/thuy-trieu'
OUTDIR = Path(__file__).resolve().parent.parent / 'water_levels' / 'VN_vho'
UA = 'oliver-weather-tides/1.0 (private tide research; oliver.k73@gmail.com)'
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

# (DIZI-Nummer, slug, Name laut Portal)
STATIONS = [
    (1, 'dao-chang-tay', 'Dao Tran'), (2, 'van-hoa', 'Van Hoa'), (3, 'cua-ong', 'Cua Ong'),
    (5, 'vinh-cat-ba', 'Vinh Cat Ba'), (6, 'hai-phong', 'Hai Phong'), (8, 'bach-long-vy', 'Bach Long Vy'),
    (9, 'cua-ba-lat', 'Cua Ba Lat'), (10, 'van-ly', 'Van Ly'), (11, 'lach-truong', 'Lach Truong'),
    (12, 'hon-me', 'Hon Me'), (13, 'lach-quen', 'Lach Quen'), (16, 'cua-nhat-le', 'Cua Nhat Le'),
    (17, 'cua-tung', 'Cua Tung'), (19, 'chan-may', 'Chan May'), (21, 'cu-lao-cham', 'Cu Lao Cham'),
    (22, 'vung-dung-quat', 'Vung Dung Quat'), (24, 'vung-ro', 'Vung Ro'), (25, 'nha-trang', 'Nha Trang'),
    (27, 'dao-phu-quy', 'Dao Phu Quy'), (30, 'con-dao', 'Dao Con Son (Con Dao)'), (32, 'hon-khoai', 'Hon Khoai'),
    (38, 'phan-vinh', 'Phan Vinh'), (39, 'toc-tan', 'Toc Tan'), (40, 'tien-nu', 'Tien Nu'), (41, 'nui-le', 'Nui Le'),
    (42, 'da-dong', 'Da Dong'), (43, 'da-tay', 'Da Tay'), (44, 'da-lat', 'Da Lat'), (46, 'thuyen-chai', 'Thuyen Chai'),
    (47, 'an-bang', 'An Bang'), (48, 'phuc-tan', 'Phuc Tan'), (49, 'ba-ke', 'Ba Ke'),
]

_cookie = None


def _get(url):
    global _cookie
    for _ in range(3):
        headers = {'User-Agent': UA}
        if _cookie:
            headers['Cookie'] = _cookie
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30, context=CTX) as r:
            html = r.read().decode('utf-8', errors='replace')
        m = re.search(r'document\.cookie="(D1N=[a-f0-9]+)"', html)
        if m:
            _cookie = m.group(1)
            time.sleep(1)
            continue
        return html
    raise RuntimeError('Anti-Bot-Cookie wird nicht akzeptiert')


def main(argv):
    jahr = int(argv[argv.index('--jahr') + 1]) if '--jahr' in argv else 2024
    d0, d1 = date(jahr, 1, 1), date(jahr, 12, 31)
    OUTDIR.mkdir(exist_ok=True)
    t0 = time.time()
    for k, (nr, slug, name) in enumerate(STATIONS, 1):
        out = OUTDIR / f'{slug}_{d0.isoformat()}_{d1.isoformat()}.json'
        cache = json.loads(out.read_text()) if out.exists() else {}
        d, n = d0, 0
        while d <= d1:
            key = d.isoformat()
            if key not in cache:
                url = f'{BASE}/{slug}-DNP280101983DIZI{nr}/{d:%Y%m%d}.html'
                try:
                    html = _get(url)
                except Exception:
                    time.sleep(10)
                    try:
                        html = _get(url)
                    except Exception:
                        d += timedelta(days=1)
                        continue
                rec = parse_day(html)
                if rec and '_meta' not in cache and rec.get('lat') is not None:
                    cache['_meta'] = {'name': name, 'dizi': nr, 'lat': rec['lat'], 'lon': rec['lon'],
                                      'datum': 'chart datum (Kartennull)', 'tz': 'UTC+7',
                                      'source': 'thuydacvietnam.org.vn (VHO Navy)'}
                if rec:
                    rec.pop('lat', None)
                    rec.pop('lon', None)
                cache[key] = rec
                n += 1
                if n % 30 == 0:
                    out.write_text(json.dumps(cache))
                time.sleep(1.0)
            d += timedelta(days=1)
        out.write_text(json.dumps(cache))
        ok = sum(1 for kk, v in cache.items() if v and not kk.startswith('_'))
        print(f'[{k}/{len(STATIONS)} {(time.time() - t0) / 60:6.1f} min] {name}: {ok} Tage mit Daten', flush=True)
    print('FERTIG', flush=True)


if __name__ == '__main__':
    main(sys.argv[1:])
