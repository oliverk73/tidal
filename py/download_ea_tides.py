#!/usr/bin/env python3
"""
EA-Tidenpegel-Harvester (Environment Agency, England).

Holt die 15-min-Wasserstandsmessungen der "check-for-flooding"-CSV
(https://check-for-flooding.service.gov.uk/station-csv/<RLOIid>) und
AKKUMULIERT sie pro Station (das CSV liefert nur ein rollierendes ~5-Tage-
Fenster). Regelmaessig laufen lassen (Kadenz <=4 Tage, damit die Fenster
ueberlappen, sonst Luecken) -> nach ~19 Tagen brauchbarer M2/S2/N2-Fit,
nach ~6-12 Monaten Vollsatz. Messdaten = Goldstandard (UTide SL), klar
besser als die cosinus-interpolierten tidetimes-Vorhersagen (vgl.
[[project_cco_measured_tides]]).

Stationsliste: water_levels/ea/ea_station_map.json (RLOIid -> unsere Station;
erzeugt durch Koordinaten-Match EA-Tidenpegel <3km, sortiert nach Fit-Guete).
Speicher: water_levels/ea/rloi<id>.json  (dedup nach ISO-Zeitstempel, sortiert).
Datum der EA-Werte = lokales Station Datum (mASD) -> Z0 spaeter relabeln.

Aufruf:  python3 py/download_ea_tides.py            # alle gemappten Stationen
         python3 py/download_ea_tides.py 5051 3146  # nur diese RLOIids
"""
from __future__ import annotations
import sys, json, csv, io, time, urllib.request
from pathlib import Path
from datetime import datetime

EA_DIR = Path('/home/oliver/water_levels/ea')        # akkumulierte Messreihen (gitignored)
STATIONS = Path('/home/oliver/harmonics/help/ea_tidal_stations.json')  # ALLE 110 EA-Tidenpegel
MAP = Path('/home/oliver/harmonics/help/ea_station_map.json')  # Match zu unseren Stationen (getrackt)
CSV_URL = 'https://check-for-flooding.service.gov.uk/station-csv/{rloi}'
HEADERS = {'User-Agent': 'Mozilla/5.0 (tidal-harmonics-research)',
           'Referer': 'https://check-for-flooding.service.gov.uk/'}


def fetch_csv(rloi, timeout=30):
    req = urllib.request.Request(CSV_URL.format(rloi=rloi), headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode('utf-8', 'replace')


def parse_csv(text):
    """-> dict {iso_timestamp: height_m}. CSV: 'Timestamp (UTC),Height (m)'."""
    out = {}
    rd = csv.reader(io.StringIO(text))
    header = next(rd, None)
    if not header or 'Timestamp' not in header[0]:
        return out
    for row in rd:
        if len(row) < 2:
            continue
        ts, h = row[0].strip(), row[1].strip()
        try:
            datetime.strptime(ts, '%Y-%m-%dT%H:%M:%SZ')
            out[ts] = float(h)
        except ValueError:
            continue
    return out


def accumulate(rloi, new_points):
    fp = EA_DIR / f'rloi{rloi}.json'
    store = {}
    if fp.exists():
        try:
            store = json.loads(fp.read_text())
        except Exception:
            store = {}
    before = len(store)
    store.update(new_points)                       # dedup: gleicher Zeitstempel ueberschreibt
    merged = dict(sorted(store.items()))            # chronologisch
    fp.write_text(json.dumps(merged))
    added = len(merged) - before
    span = (list(merged)[0][:10], list(merged)[-1][:10]) if merged else ('-', '-')
    return added, len(merged), span


def _rloi(m):
    r = m['rloi']
    return str(r[0] if isinstance(r, list) else r)


def main():
    rlois = [a for a in sys.argv[1:] if a.isdigit()]
    stations = json.loads(STATIONS.read_text())          # alle 110 EA-Tidenpegel
    # Annotation: welche unserer Stationen haengt an welchem Pegel?
    our = {}
    if MAP.exists():
        for m in json.loads(MAP.read_text()):
            r = _rloi(m)
            our.setdefault(r, m['our_name'].split(',')[0])
    for s in stations:
        s['rloi'] = str(s['rloi'])
        s['our_name'] = our.get(s['rloi'], '-')
    if rlois:
        targets = [s for s in stations if s['rloi'] in rlois]
    else:
        targets = stations
    print(f"{len(targets)} EA-Pegel zu holen ...")
    log = []
    for m in targets:
        rloi = m['rloi']
        label = str(m.get('label', ''))[:24]
        try:
            pts = parse_csv(fetch_csv(rloi))
            if not pts:
                print(f"  RLOI {rloi:>6} {label:24s}  0 Punkte (leer/Format?)")
                log.append((rloi, 0, 0)); continue
            added, total, span = accumulate(rloi, pts)
            print(f"  RLOI {rloi:>6} {label:24s}  +{added:4d} -> {total:6d} Pkt  [{span[0]}..{span[1]}]  ({m['our_name']})")
            log.append((rloi, added, total))
        except Exception as e:
            print(f"  RLOI {rloi:>6} {label:24s}  FEHLER: {e}")
            log.append((rloi, -1, -1))
        time.sleep(0.3)
    ok = sum(1 for _, a, _ in log if a >= 0)
    EA_DIR.joinpath('harvest_progress.json').write_text(json.dumps({
        'last_run_utc': datetime.utcnow().isoformat(), 'stations': len(targets), 'ok': ok}, indent=1))
    print(f"Fertig: {ok}/{len(targets)} ok.")


if __name__ == '__main__':
    main()
