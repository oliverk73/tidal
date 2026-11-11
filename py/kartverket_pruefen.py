#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Norwegische Tidensaetze gegen Kartverket-Punktvorhersagen pruefen (Oliver 11.11.2026: "Ja").

Kartverket (vannstand.kartverket.no tideapi, locationdata) rechnet jeden Kuestenpunkt vom naechsten festen Pegel
(Faktor + Zeitversatz). Je Satz in Norwegen/Svalbard: 2026 stuendlich an der Satzposition abrufen (Cache unter
water_levels/Norway_Kartverket_punkte/), den Satz dagegen rechnen.
Mass: RMS nach Abzug beider Mittel, bester Zeitversatz (-90..90 min, 5-min-Schritt), Hubverhaeltnis (Std Satz/KV),
Z0-Differenz (Mittel Satz - Mittel KV, beide auf Kartennull). Messsaetze (Kartverket-Fits, TICON) laufen als Kontrolle mit.
Schreibt nichts ausser harmonics/help/kartverket_pruefung.csv.

Usage: venv/bin/python py/kartverket_pruefen.py
"""
import csv
import json
import os
import re
import sys
import time
import urllib.request

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import health_check as H                                           # noqa: E402
import rtn_thailand_pruefen as P                                   # noqa: E402
import scheitelfit as SF                                           # noqa: E402
import xtide_modell as X                                           # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KOPF = os.path.join(ROOT, 'harmonics/utide/harmonics_utide_tidetables.txt')
CACHE = os.path.join(ROOT, 'water_levels/Norway_Kartverket_punkte')
AUS = os.path.join(ROOT, 'harmonics/help/kartverket_pruefung.csv')
API = 'https://vannstand.kartverket.no/tideapi.php'


def kopfzeilen(pfad, zeile):
    """Hot-Comment-Felder des Satzes (rueckwaerts bis zur Leerzeile '#')."""
    z = X._datei(pfad) if hasattr(X, '_datei') else open(pfad, encoding='iso-8859-1').read().split('\n')
    d = {}
    k = zeile - 2
    while k >= 0 and z[k].startswith('#') and z[k].strip() != '#':
        m = re.match(r'# !?(\w+): ?(.*)', z[k])
        if m:
            d.setdefault(m.group(1), m.group(2))
        k -= 1
    return d


def abruf(la, lo):
    os.makedirs(CACHE, exist_ok=True)
    f = os.path.join(CACHE, '%.4f_%.4f.json' % (la, lo))
    if os.path.exists(f):
        return json.load(open(f))
    u = ('%s?tide_request=locationdata&lat=%.6f&lon=%.6f&fromtime=2026-01-01T00:00&totime=2027-01-01T00:00'
         '&datatype=pre&refcode=cd&lang=en&interval=60&dst=0&tzone=0' % (API, la, lo))
    for versuch in range(3):
        try:
            x = urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': 'weather-tides/1.0'}),
                                       timeout=300).read().decode()
            break
        except Exception as e:                                      # noqa: BLE001
            print('   Abruf-Fehler', e)
            time.sleep(20)
    else:
        return None
    m = re.search(r'<location ([^>]*)/>', x)
    a = dict(re.findall(r'(\w+)="([^"]*)"', m.group(1))) if m else {}
    fehler = re.search(r'<error>([^<]*)', x)
    pts = re.findall(r'value="(-?[\d.]+)" time="([^"]+)" flag="pre"', x)
    d = dict(name=a.get('name', ''), code=a.get('code', ''), faktor=a.get('factor', ''), delay=a.get('delay', ''),
             fehler=fehler.group(1) if fehler else '',
             t=[b for a, b in pts], h=[float(a) / 100 for a, b in pts])
    json.dump(d, open(f, 'w'))
    return d


def ohne_jahresgang(d):
    """Gleitendes 30-Tage-Mittel abziehen: Kartverket rechnet SA/SSA ein, FES und ATT-Buchsaetze nicht."""
    k = 720
    lp = np.convolve(np.pad(d, k // 2, mode='edge'), np.ones(k) / k, mode='same')[k // 2:k // 2 + len(d)]
    return d - lp


def main(argv):
    kopf = X.kopf_lesen(KOPF)
    namen, speeds, arg, fak = kopf
    recs = [r for r in H.load_records() if not r['current'] and r['lat'] is not None
            and (r['name'].endswith('Norway') or 'Svalbard' in r['name'] or 'Jan Mayen' in r['name'])]
    print(len(recs), 'Saetze')
    zeilen = []
    for i, r in enumerate(sorted(recs, key=lambda r: (r['lat'], r['lon']))):
        kv = abruf(r['lat'], r['lon'])
        meta = kopfzeilen(os.path.join(ROOT, r['file']), r['line'])
        quelle = meta.get('source', '')[:70]
        if not kv or len(kv['h']) < 1000:
            print('%3d %-50s keine KV-Daten %s' % (i, r['name'][:50], kv and kv['fehler']))
            zeilen.append(dict(name=r['name'], datei=os.path.basename(r['file']), quelle=quelle, lat=r['lat'], lon=r['lon'],
                               kv_bezug='', kv_faktor='', kv_delay='', rms_cm='', versatz_min='', hub='', z0_diff_cm='', notiz='keine KV-Daten'))
            continue
        import datetime as dt
        t = np.array([dt.datetime.fromisoformat(s.replace('Z', '+00:00')).timestamp() for s in kv['t']])
        h = np.array(kv['h'])
        try:
            z0, w = P.satz_werte(dict(file=os.path.join(ROOT, r['file']), name=r['name']), speeds)
        except Exception as e:                                       # noqa: BLE001
            print('%3d %-50s Satz unlesbar %s' % (i, r['name'][:50], e))
            continue
        best = None
        for v in range(-90, 91, 5):
            p = SF.hoehe_und_ableitungen(t + v * 60, z0, w, kopf)[0]
            d = ohne_jahresgang(h - p)
            rr = float(np.sqrt(np.mean(d ** 2)))
            if best is None or rr < best[0]:
                best = (rr, v, p)
        p0 = SF.hoehe_und_ableitungen(t, z0, w, kopf)[0]
        rms0 = float(np.sqrt(np.mean(ohne_jahresgang(h - p0) ** 2)))
        rms_jg = float(np.sqrt(np.mean(((h - h.mean()) - (p0 - p0.mean())) ** 2)))
        rr, v, p = best
        hub = float(p.std() / h.std())
        dz = float(p.mean() - h.mean())
        print('%3d %-50s %-28s RMS %5.1f (%5.1f bei 0) %+4d min Hub %.2f dZ %+5.1f  [%s x %s %s min] %s' % (
            i, r['name'][:50], quelle[:28], 100 * rr, 100 * rms0, v, hub, 100 * dz, kv['code'], kv['faktor'], kv.get('delay'), kv['name'][:20]))
        zeilen.append(dict(name=r['name'], datei=os.path.basename(r['file']), quelle=quelle, lat=r['lat'], lon=r['lon'],
                           kv_bezug=kv['code'], kv_faktor=kv['faktor'], kv_delay=kv.get('delay', ''), rms_cm='%.1f' % (100 * rms0), versatz_min=v,
                           hub='%.2f' % hub, z0_diff_cm='%.1f' % (100 * dz), notiz='RMS bei bestem Versatz %.1f, mit Jahresgang %.1f' % (100 * rr, 100 * rms_jg)))
    with open(AUS, 'w', newline='', encoding='utf-8') as fh:
        wr = csv.DictWriter(fh, fieldnames=list(zeilen[0]))
        wr.writeheader()
        wr.writerows(zeilen)
    print('->', os.path.relpath(AUS, ROOT))


if __name__ == '__main__':
    main(sys.argv[1:])
