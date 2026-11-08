#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Vergleicht die DWF-2025-Saetze mit den aktuellen CO-OPS-Konstanten (harcon).

Anlass: St. Michael (Norton Sound) stand im DWF-Satz genau 2 h neben der
Wirklichkeit, und NOAA fuehrt inzwischen eine Analyse von 2025.

Usage: python3 py/noaa_harcon_abgleich.py <puffer-verzeichnis> [ausgabe.csv]
"""
import concurrent.futures as cf
import csv
import json
import os
import re
import sys
import time
import urllib.request

DATEI = os.environ.get('DATEI', 'harmonics/classic/harmonics-dwf-20251228-free.txt')
URL = 'https://api.tidesandcurrents.noaa.gov/mdapi/prod/webapi/stations/%s/harcon.json?units=metric'
SPEED = {'M2': 28.984104, 'S2': 30.0, 'K1': 15.041069, 'O1': 13.943035}


def saetze():
    zeilen = open(DATEI, encoding='latin-1').read().split('\n')
    i, aus = 0, []
    sid, einheit = None, None
    while i < len(zeilen):
        z = zeilen[i]
        m = re.match(r'# noaa_station_id: (\S+)', z)
        if m:
            sid = m.group(1)
        m = re.match(r'# !units: (\S+)', z)
        if m:
            einheit = m.group(1)
        if z and not z.startswith('#') and i + 2 < len(zeilen) and re.match(r'[+-]\d\d:\d\d ', zeilen[i + 1]):
            k = {}
            j = i + 3
            while j < len(zeilen) and not zeilen[j].startswith('#') and zeilen[j].strip():
                t = zeilen[j].split()
                if len(t) == 3 and t[0] != 'x':
                    k[t[0]] = (float(t[1]), float(t[2]))
                j += 1
            aus.append({'name': z, 'sid': sid, 'einheit': einheit, 'mer': zeilen[i + 1].split()[0], 'k': k})
            sid, einheit = None, None
            i = j
            continue
        i += 1
    return aus


def harcon(sid, puffer):
    p = os.path.join(puffer, sid + '.json')
    if os.path.exists(p):
        return json.load(open(p))
    for versuch in range(3):
        try:
            d = json.load(urllib.request.urlopen(URL % sid, timeout=30))
            json.dump(d, open(p, 'w'))
            return d
        except Exception as e:
            fehler = e
            time.sleep(2)
    return {'fehler': str(fehler)}


def ph(x):
    return (x + 180) % 360 - 180


def main():
    puffer = sys.argv[1]
    aus = sys.argv[2] if len(sys.argv) > 2 else os.path.join(puffer, 'abgleich.csv')
    s = [x for x in saetze() if x['sid'] and x['k'] and ('Current' not in x['name'])]
    print(len(s), 'Saetze mit NOAA-Nummer')
    with cf.ThreadPoolExecutor(int(os.environ.get("PARALLEL", 4))) as ex:
        h = list(ex.map(lambda x: harcon(x['sid'], puffer), s))
    with open(aus, 'w', newline='', encoding='utf8') as f:
        w = csv.writer(f)
        w.writerow(['name', 'sid', 'mer', 'dM2_grad', 'dS2_grad', 'dK1_grad', 'dO1_grad', 'rM2', 'rK1', 'dt_h', 'analyse'])
        for x, d in zip(s, h):
            kk = {c['name']: c for c in d.get('HarmonicConstituents') or [] if c.get('amplitude')}
            if 'M2' not in kk and 'K1' not in kk:
                w.writerow([x['name'], x['sid'], x['mer'], '', '', '', '', '', '', '', d.get('fehler', 'keine')])
                continue
            mer = int(x['mer'][:3])
            fak = 0.3048 if x['einheit'] == 'feet' else 1.0
            dd, r = {}, {}
            for c in SPEED:
                if c in x['k'] and c in kk:
                    g = x['k'][c][1] - mer * SPEED[c]
                    dd[c] = ph(g - kk[c]['phase_GMT'])
                    r[c] = x['k'][c][0] * fak / kk[c]['amplitude']
            dt = [dd[c] / SPEED[c] for c in dd if ((x['k'][c][0] * fak) > 0.03)]
            dt = sorted(dt)[len(dt) // 2] if dt else ''
            kom = next(iter(kk.values())).get('comments') or ''
            w.writerow([x['name'], x['sid'], x['mer']] +
                       ['%.1f' % dd[c] if c in dd else '' for c in SPEED] +
                       ['%.2f' % r[c] if c in r else '' for c in ('M2', 'K1')] +
                       ['%.2f' % dt if dt != '' else '', kom[:90]])
    print('geschrieben', aus)


main()
