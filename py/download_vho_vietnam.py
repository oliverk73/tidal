#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Stuendliche Tidenvorhersagen vom VHO-Navy-Portal Vietnam laden.

VHO = Uy ban Thuy dac Viet Nam (Vietnam Hydrographic Office, Marine),
Online-Version der amtlichen "Bang thuy trieu". Pro Tagesseite:
24 Stundenwerte (m ueber Kartennull) + bis 4 HW/LW (NL=Nuoc lon/HW,
NR=Nuoc rong/NW). Zeitzone UTC+7 (Indochina). Verfuegbar 2022-01 bis
~2026-02 (spaetere Tage liefern leere Tabellen -> None im Cache).

URL: https://thuydacvietnam.org.vn/thuy-trieu/<slug>/<YYYYMMDD>.html
Anti-Bot: erste Antwort ist JS mit document.cookie="D1N=<hash>" ->
Cookie extrahieren und mitschicken.

Tages-Cache pro Station (crash-sicher, resume-faehig), 3 Worker.
Usage: python3 py/download_vho_vietnam.py [--test]
"""
import json
import re
import ssl
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path

BASE = 'https://thuydacvietnam.org.vn/thuy-trieu'
OUTDIR = Path('/home/oliver/water_levels/VN_vho')
D0, D1 = date(2022, 1, 1), date(2026, 6, 30)
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

STATIONS = [
    ('hong-gai-DNP280101983DIZI4', 'Hong Gai'),
    ('hon-dau-DNP280101983DIZI7', 'Hon Dau'),
    ('cua-hoi-DNP280101983DIZI14', 'Cua Hoi'),
    ('cua-gianh-DNP280101983DIZI15', 'Cua Gianh'),
    ('cua-viet-DNP280101983DIZI18', 'Cua Viet'),
    ('da-nang-DNP280101983DIZI20', 'Da Nang'),
    ('quy-nhon-DNP280101983DIZI23', 'Quy Nhon'),
    ('cam-ranh-DNP280101983DIZI26', 'Cam Ranh'),
    ('vung-tau-DNP280101983DIZI28', 'Vung Tau'),
    ('sai-gon-DNP280101983DIZI29', 'Sai Gon'),
    ('ha-tien-DNP280101983DIZI31', 'Ha Tien'),
    ('phu-quoc-DNP280101983DIZI33', 'Phu Quoc'),
    ('cong-pong-xom-DNP280101983DIZI34', 'Kompong Som'),
    ('hoang-sa-DNP280101983DIZI35', 'Hoang Sa'),
    ('song-tu-tay-DNP280101983DIZI36', 'Song Tu Tay'),
    ('nam-yet-DNP280101983DIZI37', 'Nam Yet'),
    ('truong-sa-DNP280101983DIZI45', 'Truong Sa'),
]

_cookie = None


def _get(url):
    global _cookie
    for attempt in range(2):
        headers = {'User-Agent': 'Mozilla/5.0'}
        if _cookie:
            headers['Cookie'] = _cookie
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=30, context=CTX) as r:
            html = r.read().decode('utf-8', errors='replace')
        m = re.search(r'document\.cookie="(D1N=[a-f0-9]+)"', html)
        if m:
            _cookie = m.group(1)
            continue
        return html
    raise RuntimeError('Anti-Bot-Cookie wird nicht akzeptiert')


def parse_day(html):
    """24 Stundenwerte + HW/LW aus Tagesseite; None wenn keine Daten."""
    tables = re.findall(r'<table.*?</table>', html, re.S)
    hourly, extrema, lat, lon = None, [], None, None
    for t in tables:
        txt = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', t)).strip()
        if 'Vĩ độ' in txt:
            m = re.search(r"Vĩ độ:\s*(\d+)[o°]\s*(\d+)&#39;?([NS]).*?"
                          r"Kinh độ:\s*(\d+)[o°]\s*(\d+)&#39;?([EW])", txt)
            if m:
                lat = (int(m.group(1)) + int(m.group(2)) / 60) * (1 if m.group(3) == 'N' else -1)
                lon = (int(m.group(4)) + int(m.group(5)) / 60) * (1 if m.group(6) == 'E' else -1)
        elif 'MỰC NƯỚC TỪNG GIỜ' in txt:
            nums = re.findall(r'\d+\.\d+', txt.split('Độ cao', 1)[-1])
            if len(nums) == 24:
                hourly = [float(x) for x in nums]
        elif 'NL1' in txt and 'Giờ,phút' in txt:
            tail = txt.rsplit('Độ cao', 1)[-1]
            for hh, mm, ht in re.findall(r'(\d{1,2})\s+(\d{2})\s+(\d+\.\d+)', tail):
                extrema.append({'time': f'{int(hh):02d}:{mm}', 'height_m': float(ht)})
    if hourly is None:
        return None
    return {'hourly_m': hourly, 'extrema': extrema, 'lat': lat, 'lon': lon}


def download_station(st):
    slug, name = st
    out = OUTDIR / f'{slug.split("-DNP")[0]}_{D0.isoformat()}_{D1.isoformat()}.json'
    cache = json.loads(out.read_text()) if out.exists() else {}
    n_days = (D1 - D0).days + 1
    if sum(1 for k in cache if not k.startswith('_')) >= n_days:
        return name, 'cache', sum(1 for k, v in cache.items() if v and not k.startswith('_'))
    d = D0
    n_req = 0
    while d <= D1:
        key = d.isoformat()
        if key not in cache:
            url = f'{BASE}/{slug}/{d.strftime("%Y%m%d")}.html'
            try:
                html = _get(url)
            except Exception:
                time.sleep(5)
                try:
                    html = _get(url)
                except Exception:
                    d += timedelta(days=1)
                    continue
            rec = parse_day(html)
            if rec and '_meta' not in cache and rec.get('lat') is not None:
                cache['_meta'] = {'name': name, 'lat': rec['lat'], 'lon': rec['lon'],
                                  'datum': 'chart datum (Kartennull)', 'tz': 'UTC+7',
                                  'source': 'thuydacvietnam.org.vn (VHO Navy)'}
            if rec:
                rec.pop('lat', None)
                rec.pop('lon', None)
            cache[key] = rec
            n_req += 1
            if n_req % 60 == 0:
                out.write_text(json.dumps(cache))
            time.sleep(0.15)
        d += timedelta(days=1)
    out.write_text(json.dumps(cache))
    ok = sum(1 for k, v in cache.items() if v and not k.startswith('_'))
    return name, 'neu', ok


def main():
    OUTDIR.mkdir(exist_ok=True)
    if '--test' in sys.argv:
        for slug, name in STATIONS[:2]:
            html = _get(f'{BASE}/{slug}/20240315.html')
            rec = parse_day(html)
            print(name, json.dumps(rec, ensure_ascii=False)[:300])
        return
    n_days = (D1 - D0).days + 1
    print(f'{len(STATIONS)} Stationen, {n_days} Tage/Station ({D0}..{D1})', flush=True)
    t0 = time.time()
    done = 0
    with ThreadPoolExecutor(max_workers=3) as ex:
        for name, how, ok in ex.map(download_station, STATIONS):
            done += 1
            el = (time.time() - t0) / 60
            print(f'[{done}/{len(STATIONS)} {el:6.1f}min] {name} {how} ({ok} Tage ok)', flush=True)
    print('BATCH FERTIG', flush=True)


if __name__ == '__main__':
    main()
