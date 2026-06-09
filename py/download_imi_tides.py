#!/usr/bin/env python3
"""
Marine-Institute-Tidenpegel-Downloader (Irisches National Tide Gauge Network).

ERDDAP-Archiv erddap.marine.ie, Dataset IrishNationalTideGaugeNetwork. Liefert
5-min-Wasserstand bereits relativ zu LAT (= Chart Datum!) -> kein Datum-Shift
noetig. Mehrjahres-Archiv direkt abrufbar (kein Akkumulieren).

Variable Water_Level_LAT, QC_Flag (0 = ok). Pro Jahr gechunkt.
Liest harmonics/help/imi_new_stations.json (noch fehlende Pegel).

Aufruf:  python3 py/download_imi_tides.py [--years N]
"""
from __future__ import annotations
import sys, json, csv, io, urllib.request, urllib.parse
from pathlib import Path
from datetime import datetime

IMI_DIR = Path('/home/oliver/water_levels/imi')
STATIONS = Path('/home/oliver/harmonics/help/imi_new_stations.json')
BASE = ('https://erddap.marine.ie/erddap/tabledap/IrishNationalTideGaugeNetwork.csv'
        '?time,Water_Level_LAT,QC_Flag&station_id=%22{sid}%22'
        '&time%3E={fr}-01-01&time%3C={to}-01-01')
END_YEAR = 2026
DEFAULT_YEARS = 9


def safe(sid):
    return sid.replace(' ', '_').replace('-', '').replace('/', '_')


def fetch_year(sid, year, timeout=120):
    url = BASE.format(sid=urllib.parse.quote(sid), fr=year, to=year + 1)
    with urllib.request.urlopen(url, timeout=timeout) as r:
        text = r.read().decode('utf-8', 'replace')
    out = {}
    rd = csv.reader(io.StringIO(text))
    next(rd, None); next(rd, None)             # header + units
    for row in rd:
        if len(row) >= 2 and row[1] not in ('', 'NaN'):
            q = row[2] if len(row) > 2 else '0'
            if q in ('0', '', '1'):            # 0/1 = ok
                try:
                    out[row[0]] = float(row[1])
                except ValueError:
                    pass
    return out


def main():
    args = sys.argv[1:]
    years = DEFAULT_YEARS
    if '--years' in args:
        i = args.index('--years'); years = int(args[i + 1])
    IMI_DIR.mkdir(parents=True, exist_ok=True)
    stations = json.loads(STATIONS.read_text())
    yr0 = END_YEAR - years + 1
    print(f"{len(stations)} IMI-Pegel, Jahre {yr0}..{END_YEAR}")
    for st in stations:
        sid = st['station_id']
        store = {}
        for year in range(yr0, END_YEAR + 1):
            try:
                store.update(fetch_year(sid, year))
            except Exception as e:
                print(f"  {sid[:24]:24s} {year}: {type(e).__name__}")
        merged = dict(sorted(store.items()))
        (IMI_DIR / f'{safe(sid)}.json').write_text(json.dumps(merged))
        sp = (list(merged)[0][:10], list(merged)[-1][:10]) if merged else ('-', '-')
        print(f"  {sid[:26]:26s} {len(merged):7d} Pkt  [{sp[0]}..{sp[1]}]  -> {st['name'].split(',')[0]}")
    print("Fertig.")


if __name__ == '__main__':
    main()
