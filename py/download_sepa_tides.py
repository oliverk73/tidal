#!/usr/bin/env python3
"""
SEPA-Tidenpegel-Downloader (Scottish Environment Protection Agency).

SEPA betreibt 22 Tidenpegel mit 15-min-Messreihen ueber JAHRZEHNTE, abrufbar
ueber die KiWIS-Archiv-API (timeseries.sepa.org.uk). Anders als EA (rollierendes
5-Tage-Fenster) liefert KiWIS das volle Archiv direkt -> sofort fit-bar.

API:  getTimeseriesValues&ts_id=<id>&from=<date>&to=<date>&format=json
      -> data = [[ISO-Timestamp, value_m, quality], ...], 15-min, Datum vermutl.
      lokales Pegeldatum (Z0 spaeter relabeln). Quality 100/120 = ok.

Pro Station per Jahr gechunkt (gegen Timeouts/Groesse), akkumuliert in
water_levels/sepa/ts<id>.json  {iso: value}.

Aufruf:  python3 py/download_sepa_tides.py [--years N] [ts_id ...]
"""
from __future__ import annotations
import sys, json, urllib.request
from pathlib import Path
from datetime import datetime

SEPA_DIR = Path('/home/oliver/water_levels/sepa')
STATIONS = Path('/home/oliver/harmonics/help/sepa_tidal_stations.json')
API = ('https://timeseries.sepa.org.uk/KiWIS/KiWIS?service=kisters&type=queryServices'
       '&request=getTimeseriesValues&datasource=0&format=json'
       '&ts_id={ts}&from={fr}-01-01&to={fr}-12-31&returnfields=Timestamp,Value,Quality%20Code')
END_YEAR = 2026          # bis einschliesslich
DEFAULT_YEARS = 8        # so viele Jahre rueckwaerts (<= 1 Nodalzyklus ~19y)


def fetch_year(ts, year, timeout=90):
    url = API.format(ts=ts, fr=year)
    with urllib.request.urlopen(url, timeout=timeout) as r:
        d = json.loads(r.read().decode('utf-8', 'replace'))
    obj = d[0] if isinstance(d, list) and d else {}
    out = {}
    for row in obj.get('data', []):
        # alle gueltigen Werte akzeptieren; SEPA-Quality-Codes variieren (50/100/120/...),
        # nur echte Fehl-/Missing-Marker ausschliessen.
        if len(row) >= 2 and row[1] is not None and row[1] > -100:
            out[row[0]] = float(row[1])
    return out


def main():
    args = sys.argv[1:]
    years = DEFAULT_YEARS
    if '--years' in args:
        i = args.index('--years'); years = int(args[i + 1]); del args[i:i + 2]
    only = [a for a in args if a.isdigit()]
    SEPA_DIR.mkdir(parents=True, exist_ok=True)
    stations = json.loads(STATIONS.read_text())
    if only:
        stations = [s for s in stations if s['ts_id'] in only]
    yr_start = END_YEAR - years + 1
    print(f"{len(stations)} SEPA-Pegel, Jahre {yr_start}..{END_YEAR}")
    for s in stations:
        ts = s['ts_id']
        fp = SEPA_DIR / f'ts{ts}.json'
        store = json.loads(fp.read_text()) if fp.exists() else {}
        before = len(store)
        cov_from = int(s.get('cov_from', '2000')[:4] or 2000)
        for year in range(max(yr_start, cov_from), END_YEAR + 1):
            try:
                store.update(fetch_year(ts, year))
            except Exception as e:
                print(f"  {s['sepa_name'][:22]:22s} {year}: FEHLER {e}")
        merged = dict(sorted(store.items()))
        fp.write_text(json.dumps(merged))
        sp = (list(merged)[0][:10], list(merged)[-1][:10]) if merged else ('-', '-')
        print(f"  ts{ts} {s['sepa_name'][:22]:22s} {len(merged):7d} Pkt (+{len(merged)-before})  [{sp[0]}..{sp[1]}]  -> {s['match_type']} {s.get('match_name') or ''}".rstrip())
    print("Fertig.")


if __name__ == '__main__':
    main()
