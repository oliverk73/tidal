#!/usr/bin/env python3
"""Rebuild JMA tide station CSV with romanized names from the JMA list page."""
import re
import csv
import pykakasi
from pathlib import Path
import requests

URL = "https://www.data.jma.go.jp/kaiyou/db/tide/suisan/station.php"
OUT = Path("/tmp/jma_stations_romanized_final.csv")

# Common place-name overrides: long-vowel 'ou'→'o', 'uu'→'u', standard spellings.
# Kanji that pykakasi maps to a Japanese given name instead of the local place
# reading must be listed here explicitly (e.g. 日明 → Akira vs Hiagari).
OVERRIDES = {
    '東京': 'Tokyo', '大阪': 'Osaka', '京都': 'Kyoto', '神戸': 'Kobe',
    '横浜': 'Yokohama', '名古屋': 'Nagoya', '福岡': 'Fukuoka',
    '札幌': 'Sapporo', '仙台': 'Sendai', '広島': 'Hiroshima',
    '那覇': 'Naha', '鹿児島': 'Kagoshima', '長崎': 'Nagasaki',
    '大阪': 'Osaka', '神戸': 'Kobe', '小樽': 'Otaru',
    '日明': 'Hiagari',
    '苅田': 'Kanda',
}


def romanize(jp):
    if jp in OVERRIDES:
        return OVERRIDES[jp]
    kks = pykakasi.kakasi()
    r = kks.convert(jp)
    s = ''.join(x['hepburn'] for x in r)
    # common long-vowel normalisation for place names
    s = s.replace('oo', 'o').replace('ou', 'o').replace('uu', 'u')
    return s.capitalize()


def parse_coord(s):
    # "45゜24'"  => degrees+minutes
    m = re.match(r"(\d+)\D+(\d+)", s)
    if not m:
        return None
    deg, mn = int(m.group(1)), int(m.group(2))
    return deg + mn / 60.0


def main():
    html = requests.get(URL, headers={'User-Agent': 'Mozilla/5.0'}, timeout=60).text
    rows = re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.DOTALL)

    kks = pykakasi.kakasi()
    stations = []
    for r in rows:
        cells = re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', r, re.DOTALL)
        cells = [re.sub(r'<[^>]+>', '', c).strip() for c in cells]
        if len(cells) < 5:
            continue
        if not re.match(r'^[A-Z0-9]{2}$', cells[1]):
            continue
        code = cells[1]
        name_jp = cells[2]
        lat = parse_coord(cells[3])
        lon = parse_coord(cells[4])
        if lat is None or lon is None:
            continue
        name_rom = romanize(name_jp)
        stations.append({'code': code, 'name_jp': name_jp,
                         'romanized': name_rom, 'lat': lat, 'lon': lon})

    with open(OUT, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=['code', 'name_jp', 'romanized', 'lat', 'lon'])
        w.writeheader()
        for s in stations:
            w.writerow(s)
    print(f"{len(stations)} stations -> {OUT}")


if __name__ == '__main__':
    main()
