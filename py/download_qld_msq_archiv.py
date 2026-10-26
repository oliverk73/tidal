#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MSQ-Archivreihen ("<Pegel> tide gauge -- archived interval recordings") vom QLD-Datenportal.

Oliver 22.10.2026: "Gibt es hier brauchbare Tidendaten: data.qld.gov.au/dataset/?tags=tides" -> 64 gemessene
Reihen; 16 hatte schon py/download_qld_australia.py. Die CSV-Downloads sperrt eine AWS-WAF-Abfrage (202, leer),
die CKAN-datastore_search-API liefert dieselben Zeilen (Date dd/mm/yyyy, Time, Ind, Reading).

Zeit: Portal liefert AEST (UTC+10, ohne Sommerzeit) -> hier gleich nach UTC umgerechnet
(Falle von 13.09.2026, siehe messreihe_qualitaet._lies_npz). Reading -99 u. a. Fehlwerte verworfen, Ind mitgeschrieben.
Je Datensatz die Jahrgaenge ab JAHR_AB, bei reinen Altreihen alle.

Usage: venv/bin/python py/download_qld_msq_archiv.py [dataset-name-teil ...] [--alt] [--ab JAHR] [--ziel DIR]
       -> water_levels/Australia_QLD/msq/<dataset-name>.csv (time_utc, waterlevel_m, ind)
       --alt: nur die 16 Datensaetze aus py/download_qld_australia.py (dort nur 2023-2025), fuer lange Fits
       (26.10.2026, Ziel water_levels/Australia_QLD/msq_lang)
"""
import csv
import datetime as dt
import os
import re
import sys
import time

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ZIEL = os.path.join(ROOT, 'water_levels/Australia_QLD/msq')
API = 'https://www.data.qld.gov.au/api/3/action'
JAHR_AB = 2015
# Datensaetze, die py/download_qld_australia.py schon holt (npz/)
ALT = {'1e96cbe0-771b-48d9-82cc-329607d3abba', '1e874768-43ed-4d82-8a2f-bb689c4eefd4',
       'bc6ef33d-b3be-4e3f-ae4c-adb0601461a8', 'd99c2929-e42c-49f0-8249-f4f20eb311f8',
       '95ba8f5b-cdc2-4409-a701-fb9a38ac5017', 'a9ad661a-82ca-4d0d-9a1c-37a25bc1dfcc',
       'cc83963c-dc50-4047-9d49-a1d5ef59c7c3', '863abfda-ec9b-4408-b896-458cbf5a3388',
       'aed24280-fbd4-49da-b2dc-6e87b6b256ba', '179c7cc5-26a7-4f57-9e1e-3ec2ed5dd4de',
       '94174433-ac3e-474a-a03e-9c87f320c38c', '43c33f0c-cd08-4281-b13e-a108101fc1cb',
       '4a8b4b86-95dc-426c-a33f-02fdc8e58f8d', '1b540272-464e-456e-b3d9-806dbd5538b4',
       '5473e4a2-a5ab-4d9c-906a-efdc0e099617', '43f307f6-522b-4507-a970-c074efceeca9'}
S = requests.Session()
S.headers['User-Agent'] = 'Mozilla/5.0 (X11; Linux x86_64)'


def api(action, **params):
    for versuch in range(5):
        try:
            r = S.get('%s/%s' % (API, action), params=params, timeout=120)
            if r.status_code == 404:                                # Jahrgang nicht im Datastore (nur CSV hinter der WAF)
                break
            r.raise_for_status()
            return r.json()['result']
        except Exception as e:                                      # noqa: BLE001
            print('      Wiederholung %d: %s' % (versuch + 1, e), flush=True)
            time.sleep(5 * (versuch + 1))
    raise RuntimeError('%s %s' % (action, params))


def datensaetze(alt=False):
    res = api('package_search', q='title:"archived interval recordings"', rows=200)['results']
    return [p for p in res if (p['id'] in ALT) == alt]


def jahr(r):
    m = re.search(r'(?<!\d)(19\d\d|20\d\d)(?!\d)', r.get('name', '') + ' ' + r.get('url', ''))
    return int(m.group(1)) if m else 0


def zeilen(rid):
    off = 0
    while True:
        res = api('datastore_search', resource_id=rid, limit=32000, offset=off)
        rec = res['records']
        if not rec:
            return
        yield from rec
        off += len(rec)
        if off >= res.get('total', 0):
            return
        time.sleep(0.2)


def main(argv):
    ab = int(argv[argv.index('--ab') + 1]) if '--ab' in argv else JAHR_AB
    ziel = argv[argv.index('--ziel') + 1] if '--ziel' in argv else ZIEL
    wert = {argv[i + 1] for i, a in enumerate(argv) if a in ('--ab', '--ziel')}
    namen = [a for a in argv if not a.startswith('--') and a not in wert]
    os.makedirs(ziel, exist_ok=True)
    for p in sorted(datensaetze('--alt' in argv), key=lambda p: p['name']):
        if namen and not any(a in p['name'] for a in namen):
            continue
        pfad = os.path.join(ziel, p['name'] + '.csv')
        if os.path.exists(pfad):
            print('%s: vorhanden' % p['name'])
            continue
        res = [r for r in p['resources'] if r.get('datastore_active') or r.get('format', '').lower() == 'csv']
        neu = [r for r in res if jahr(r) >= ab]
        res = neu or res
        print('%s: %d Jahrgaenge %s' % (p['name'], len(res), sorted(jahr(r) for r in res)), flush=True)
        werte = {}
        for r in res:
            n = 0
            try:
                for z in zeilen(r['id']):
                    try:
                        v = float(z.get('Reading', ''))
                        t = dt.datetime.strptime('%s %s' % (z['Date'].strip(), z['Time'].strip()), '%d/%m/%Y %H:%M')
                    except (ValueError, KeyError, AttributeError):
                        continue
                    if not -10 < v < 20:
                        continue
                    werte[t - dt.timedelta(hours=10)] = (v, (z.get('Ind') or '').strip())
                    n += 1
            except RuntimeError as e:
                print('   FEHLER %s: %s' % (r.get('name'), e))
            print('   %s: %d' % (r.get('name', r['id'])[:70], n), flush=True)
        if not werte:
            continue
        tmp = '%s.%d.tmp' % (pfad, os.getpid())
        with open(tmp, 'w', newline='') as f:
            w = csv.writer(f)
            w.writerow(['time_utc', 'waterlevel_m', 'ind'])
            for t in sorted(werte):
                w.writerow([t.strftime('%Y-%m-%d %H:%M'), '%.3f' % werte[t][0], werte[t][1]])
        os.replace(tmp, pfad)
        print('   -> %d Werte %s..%s' % (len(werte), min(werte).date(), max(werte).date()), flush=True)


if __name__ == '__main__':
    main(sys.argv[1:])
