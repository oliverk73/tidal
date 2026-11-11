#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Pegel der thailaendischen Marine (Hydrographic Dept., SDA-Messnetz) laden (Oliver 11.11.2026).

Karte http://203.147.59.19:3001/map zeigt nur Grafiken; dahinter liegt eine offene API:
  GET  http://203.147.59.19:3002/api/map/search                     -> Stationen, Sensoren, Position, letzter Wert
  POST http://203.147.59.19:3002/api/stations/<station>/graph/<sensor>
       {"from": "YYYY-MM-DD HH:MM", "to": ..., "pattern": "15m"|"1h", "offset": false}
       -> data[].name / dataPoints[{label, y}] (Ortszeit ICT = UTC+7; letzter Wert 14:49 bei 08:01 UTC)
Daten ab etwa Dezember 2025. Der Server ist sehr langsam (11.11.2026: 1 Tag 15m ~30 s, 7 Tage 15m ~115 s, 1h langsamer
als 15m, 14 Tage > 10 min) -> nur Stichprobenwochen (WOCHEN) in 15m; reicht fuer Satzpruefung und Fit (Spanne 10 Monate).
Ablage: water_levels/Thailand_RTN/<station_id>_<sensor_id>.json ({serienname: [[label, y], ...]}), vorhandene
Wochen werden nicht neu geladen.

Usage: python3 py/download_rtn_thailand.py [ID ...]
"""
import datetime as dt
import json
import os
import sys
import time
import urllib.request

API = 'http://203.147.59.19:3002/api'
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ZIEL = os.path.join(ROOT, 'water_levels', 'Thailand_RTN')
WOCHEN = [dt.date(2026, 1, 5), dt.date(2026, 3, 2), dt.date(2026, 5, 4), dt.date(2026, 7, 6), dt.date(2026, 9, 7),
          dt.date(2026, 10, 26)]


def holen(url, daten=None, versuche=3):
    for i in range(versuche):
        try:
            req = urllib.request.Request(url, data=json.dumps(daten).encode() if daten else None,
                                         headers={'Content-Type': 'application/json', 'User-Agent': 'weather-tides/1.0'})
            with urllib.request.urlopen(req, timeout=400) as r:
                return json.load(r)
        except Exception as e:                                       # noqa: BLE001
            print('   Fehler (%s), Versuch %d' % (e, i + 1), flush=True)
            time.sleep(20)
    return None


def main(argv):
    nur = {int(a) for a in argv if a.isdigit()}
    os.makedirs(ZIEL, exist_ok=True)
    m = holen(API + '/map/search')['data']
    json.dump(m, open(os.path.join(ZIEL, 'stationen.json'), 'w'), ensure_ascii=False, indent=0)
    paare = sorted({(x['station_id'], x['sensor_id']) for x in m if 'ระดับน้ำ' in x['parameter_disp_name']})
    for st, se in paare:
        if nur and st not in nur:
            continue
        pfad = os.path.join(ZIEL, '%d_%d.json' % (st, se))
        alt = json.load(open(pfad)) if os.path.exists(pfad) else {'_wochen': []}
        name = next(x['station_name'] for x in m if x['station_id'] == st)
        print(st, se, name, flush=True)
        for w in WOCHEN:
            k = '15m ' + w.isoformat()
            if k in alt['_wochen']:
                continue
            r = holen('%s/stations/%d/graph/%d' % (API, st, se),
                      {'from': '%s 00:00' % w, 'to': '%s 00:00' % (w + dt.timedelta(days=7)), 'pattern': '15m', 'offset': False})
            if r and r.get('status'):
                for s in r['data']:
                    if 'ระดับน้ำ' not in s['name']:
                        continue                                     # Batteriespannung weglassen
                    reihe = dict(alt.get(s['name'], []))
                    reihe.update({p['label']: p['y'] for p in s['dataPoints']})
                    alt[s['name']] = sorted(reihe.items())
                alt['_wochen'].append(k)
                print('   %s %s' % (k, sum(len(s['dataPoints']) for s in r['data'])), flush=True)
                json.dump(alt, open(pfad, 'w'), ensure_ascii=False)
            time.sleep(3)


if __name__ == '__main__':
    main(sys.argv[1:])
