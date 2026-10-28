#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""NOAA-Buchsaetze in den USA (Table 2, harmonics_noaa_amtt) gegen NOAAs eigene HW/NW-Vorhersage am selben Ort (28.10.2026).

Die Table-2-Saetze sind unsere Uebertragung der Buchdifferenzen auf den Bezugsort. NOAA rechnet fuer dieselben Nebenorte
selbst HW/NW (CO-OPS, Typ S), dort mit eigenen Differenzen je Scheitel. Fuer jeden Buchsatz: CO-OPS-Station bis 2 km,
HW/NW 2026 (MLLW, GMT; Cache water_levels/NOAA_hilo), dann Zeitfehler (Median mit Vorzeichen, + = Satz zu spaet),
Hoehen-RMS nach Abzug des mittleren Versatzes und Hubverhaeltnis.
Hawaii/Puerto Rico/Pazifik sind seit 27.10. ohnehin Scheitelfits an diese Vorhersagen (py/noaa_hwnw_scheitelfit.py).

Kanada (--kanada): dieselbe Probe gegen die CHS-HW/NW Juli 2026 aus tide_tables/canada_chs (ohne neue Abfrage).

Usage: venv/bin/python py/noaa_buch_coops_probe.py [--kanada]   -> harmonics/help/noaa_buch_{coops,chs}_<datum>.csv
"""
import csv
import datetime as dt
import json
import math
import os
import re
import sys
import time
import urllib.request

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import health_check as H                                           # noqa: E402
import scheitelfit as SF                                           # noqa: E402
import xtide_modell as X                                           # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATEI = os.path.join(ROOT, 'harmonics/noaa/harmonics_noaa_amtt.txt')
CACHE = os.path.join(ROOT, 'water_levels/NOAA_hilo')
STATIONEN = 'https://api.tidesandcurrents.noaa.gov/mdapi/prod/webapi/stations.json?type=tidepredictions'
URL = ('https://api.tidesandcurrents.noaa.gov/api/prod/datagetter?product=predictions&station=%s&begin_date=20260101'
       '&end_date=20261231&datum=MLLW&time_zone=gmt&units=metric&interval=hilo&format=json')
US = ('Alaska', 'California', 'Oregon', 'Washington')
CHS = os.path.join(ROOT, 'tide_tables/canada_chs')                  # IWLS wlp-hilo, Juli 2026 (py/chs_referenz.py)


def stationen():
    pfad = os.path.join(CACHE, 'coops_stationen.json')
    if not os.path.exists(pfad):
        os.makedirs(CACHE, exist_ok=True)
        json.dump(json.load(urllib.request.urlopen(STATIONEN, timeout=180))['stations'], open(pfad, 'w'))
    return json.load(open(pfad))


def scheitel(sid):
    pfad = os.path.join(CACHE, '%s_2026.json' % sid)
    if not os.path.exists(pfad):
        for k in range(4):
            try:
                d = json.load(urllib.request.urlopen(URL % sid, timeout=180))
                json.dump(d.get('predictions', []), open(pfad, 'w'))
                break
            except Exception:                                          # noqa: BLE001 (504 der API)
                time.sleep(10 * (k + 1))
        time.sleep(0.5)
    if not os.path.exists(pfad):
        return np.array([]), np.array([])
    ev = sorted({(dt.datetime.strptime(x['t'], '%Y-%m-%d %H:%M').replace(tzinfo=dt.timezone.utc).timestamp(), float(x['v']))
                 for x in json.load(open(pfad)) if x.get('v') not in (None, '')})
    return np.array([a for a, _ in ev]), np.array([b for _, b in ev])


def chs_stationen():
    return [(s['code'], s['officialName'], 'CHS', s['latitude'], s['longitude']) for s in json.load(open(os.path.join(CHS, 'stationen.json')))
            if os.path.exists(os.path.join(CHS, '%s.json' % s['code']))]


def chs_scheitel(code):
    ev = sorted({(dt.datetime.strptime(x['eventDate'], '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=dt.timezone.utc).timestamp(), float(x['value']))
                 for x in json.load(open(os.path.join(CHS, '%s.json' % code))) if x.get('value') is not None})
    return np.array([a for a, _ in ev]), np.array([b for _, b in ev])


def main(argv):
    kopf = X.kopf_lesen(DATEI)
    namen, speeds, _, _ = kopf
    kanada = '--kanada' in argv
    S = chs_stationen() if kanada else [(s['id'], s['name'], s['type'], s['lat'], s['lng']) for s in stationen()]
    buch = [r for r in H.load_records() if 'harmonics_noaa_amtt' in r['file'] and not r['current'] and r['name'].endswith(('Canada',) if kanada else US)]
    zeilen = []
    for r in buch:
        kand = sorted((H.km(r, dict(lat=la, lon=lo)), sid, n, typ) for sid, n, typ, la, lo in S)
        km, sid, cname, typ = kand[0]
        if km > 2:
            zeilen.append(dict(name=r['name'], befund='keine Station', coops='%s %s (%.1f km)' % (sid, cname, km)))
            continue
        t, h = chs_scheitel(sid) if kanada else scheitel(sid)
        if len(t) < (100 if kanada else 300):
            zeilen.append(dict(name=r['name'], befund='keine Vorhersage', coops='%s %s' % (sid, cname)))
            continue
        z0, w, einheit, mer = X.satz_lesen(DATEI, r['name'])
        f = 0.3048 if einheit.startswith('f') else 1.0
        wg = {k: (a * f, X.greenwich(g, speeds[k], mer)) for k, (a, g) in w.items() if k in speeds}
        hm, h1, h2 = SF.hoehe_und_ableitungen(t, z0 * f, wg, kopf)
        d = np.where(h2 != 0, -h1 / np.where(h2 != 0, h2, 1), 0.0) * 60.0     # Modellscheitel - Tafelzeit (min)
        d = d[np.abs(d) < 180]
        off = float(np.mean(h - hm))
        rms = float(np.sqrt(np.mean((hm + off - h) ** 2)))
        hub = float(np.std(hm) / np.std(h))
        dtm = float(np.median(d))
        befund = 'falsch' if abs(dtm) >= 15 or rms >= 0.15 or abs(hub - 1) >= 0.15 else ('grenzwertig' if abs(dtm) >= 8 or rms >= 0.08 else 'ok')
        zeilen.append(dict(name=r['name'], befund=befund, coops='%s %s %s (%.1f km)' % (sid, typ, cname, km),
                           dt_min='%+.0f' % dtm, rms_cm='%.1f' % (rms * 100), hub='%.2f' % hub, scheitel=len(t)))
        print('%-11s %-44s %-34s dt %+4.0f min  RMS %4.1f cm  Hub %.2f' % (befund, r['name'][:44], ('%s %s' % (sid, cname))[:34], dtm, rms * 100, hub), flush=True)
    heute = dt.date.today().strftime('%Y%m%d')
    aus = os.path.join(ROOT, 'harmonics/help/noaa_buch_%s_%s.csv' % ('chs' if kanada else 'coops', heute))
    with open(aus, 'w', newline='', encoding='utf-8') as fh:
        wr = csv.DictWriter(fh, fieldnames=['befund', 'name', 'coops', 'dt_min', 'rms_cm', 'hub', 'scheitel'])
        wr.writeheader()
        wr.writerows(sorted(zeilen, key=lambda z: (z['befund'], z['name'])))
    import collections
    print(collections.Counter(z['befund'] for z in zeilen), '->', os.path.relpath(aus, ROOT))


if __name__ == '__main__':
    main(sys.argv[1:])
