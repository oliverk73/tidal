#!/usr/bin/env python3
"""Download tidal-current forecast (조류예보) from KHOA OceanGrid Open API.

Quelle: Korea Hydrographic and Oceanographic Agency (KHOA), Badanuri OceanGrid.
API:    https://www.khoa.go.kr/oceangrid/khoa/takepart/openapi/openApiFcTidalCurrent.do

Voraussetzung: kostenloser ServiceKey von
    https://www.khoa.go.kr/oceangrid/khoa/takepart/openapi/openApiKey.do
    (oder data.go.kr Datensatz 15156024 -> "활용신청").
Key in Umgebungsvariable KHOA_KEY ablegen:
    export KHOA_KEY='....'

Strategie (analog zu den vorhandenen current_tables/Vorhersage-Stationen):
  1. Forecast-Punkt-Liste ziehen (ObsCode + Koordinaten).
  2. Pro Punkt mehrere Tage Vorhersage (Speed cm/s + Richtung deg) holen
     -> sauberes, lückenloses Zeitreihen-Material für UTide-Strömungs-Fit.
  3. Roh-JSON je Punkt/Tag speichern; Fit erfolgt in fit_khoa_currents.py.

Die genauen JSON-Feldnamen werden beim ersten echten Response verifiziert
(--probe schreibt eine Beispielantwort nach stdout, bevor wir den Parser fixieren).
"""
import os
import sys
import json
import time
import argparse
import requests

KEY = os.environ.get('KHOA_KEY', '').strip()
BASE = 'https://www.khoa.go.kr/api/oceangrid'
FC_URL = f'{BASE}/fcTidalCurrent/search.do'          # 조류예보 (Vorhersage)
# Metadaten-/Listen-Endpunkte (Feldnamen beim ersten Lauf verifizieren):
LIST_CANDIDATES = [
    f'{BASE}/fcTidalCurrent/search.do',              # manche KHOA-APIs liefern bei leerem ObsCode die Liste
]

OUT_DIR = '/home/oliver/water_levels/Korea_currents'
HEADERS = {'User-Agent': 'Mozilla/5.0 (tide-research; scientific comparison of tide models)'}


def _get(url, params):
    params = dict(params)
    params['ServiceKey'] = KEY
    params.setdefault('ResultType', 'json')
    r = requests.get(url, params=params, headers=HEADERS, timeout=40)
    r.raise_for_status()
    txt = r.text
    try:
        return r.json()
    except ValueError:
        # KHOA liefert bei Fehlern eine HTML-Fehlerseite statt JSON
        raise RuntimeError(f'Keine JSON-Antwort (Key gültig?). Anfang:\n{txt[:300]}')


def probe(obscode, date):
    """Eine Beispielantwort holen und roh ausgeben -> Feldnamen verifizieren."""
    data = _get(FC_URL, {'ObsCode': obscode, 'Date': date})
    print(json.dumps(data, ensure_ascii=False, indent=2)[:4000])


def fetch_point(obscode, date):
    return _get(FC_URL, {'ObsCode': obscode, 'Date': date})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--probe', nargs=2, metavar=('OBSCODE', 'YYYYMMDD'),
                    help='Eine Beispielantwort ausgeben (Feldnamen prüfen)')
    ap.add_argument('--codes', help='Komma-Liste von ObsCodes')
    ap.add_argument('--codes-file', help='JSON/Textdatei mit ObsCodes')
    ap.add_argument('--days', type=int, default=40,
                    help='Anzahl Tage ab --start (Default 40 -> reicht für M2/S2/K1/O1)')
    ap.add_argument('--start', default='20260101', help='Startdatum YYYYMMDD')
    args = ap.parse_args()

    if not KEY:
        sys.exit('FEHLER: KHOA_KEY nicht gesetzt. export KHOA_KEY=... '
                 '(Registrierung: https://www.khoa.go.kr/oceangrid/khoa/takepart/openapi/openApiKey.do)')

    if args.probe:
        probe(*args.probe)
        return

    os.makedirs(OUT_DIR, exist_ok=True)

    codes = []
    if args.codes:
        codes = [c.strip() for c in args.codes.split(',') if c.strip()]
    elif args.codes_file:
        with open(args.codes_file) as f:
            raw = f.read()
        try:
            obj = json.loads(raw)
            codes = list(obj.keys()) if isinstance(obj, dict) else list(obj)
        except json.JSONDecodeError:
            codes = [l.strip() for l in raw.splitlines() if l.strip()]
    else:
        sys.exit('Keine ObsCodes übergeben (--codes / --codes-file).')

    from datetime import datetime, timedelta
    start = datetime.strptime(args.start, '%Y%m%d')

    for code in codes:
        cdir = os.path.join(OUT_DIR, code)
        os.makedirs(cdir, exist_ok=True)
        got = 0
        for d in range(args.days):
            day = (start + timedelta(days=d)).strftime('%Y%m%d')
            out = os.path.join(cdir, f'{day}.json')
            if os.path.exists(out):
                got += 1
                continue
            try:
                data = fetch_point(code, day)
            except Exception as e:
                print(f'  {code} {day}: {e}')
                time.sleep(1.0)
                continue
            with open(out, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False)
            got += 1
            time.sleep(0.25)
        print(f'{code}: {got}/{args.days} Tage gespeichert -> {cdir}')


if __name__ == '__main__':
    main()
