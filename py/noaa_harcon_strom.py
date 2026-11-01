#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Wie noaa_harcon_abgleich.py, fuer die DWF-Stroeme: Kennung STATION_BIN, Hauptachse in cm/s.

Usage: python3 py/noaa_harcon_strom.py <puffer-verzeichnis> <ausgabe.csv>
"""
import concurrent.futures as cf
import csv
import json
import os
import re
import sys
import time
import urllib.request

DATEI = 'harmonics/classic/harmonics-dwf-20251228-free.txt'
URL = 'https://api.tidesandcurrents.noaa.gov/mdapi/prod/webapi/stations/%s/harcon.json?units=metric&bin=%s'
SPEED = {'M2': 28.984104, 'S2': 30.0, 'K1': 15.041069, 'O1': 13.943035}


def saetze():
    z = open(DATEI, encoding='latin-1').read().split('\n')
    aus, sid, einheit = [], None, None
    i = 0
    while i < len(z):
        l = z[i]
        m = re.match(r'# noaa_station_id: (\S+)', l)
        if m:
            sid = m.group(1)
        m = re.match(r'# !units: (\S+)', l)
        if m:
            einheit = m.group(1)
        if l and not l.startswith('#') and l != 'x 0 0' and i + 2 < len(z) and re.match(r'[+-]\d\d:\d\d ', z[i + 1]):
            k = {}
            for t in (x.split() for x in z[i + 3:i + 179]):
                if len(t) == 3 and t[0] != 'x':
                    k[t[0]] = (float(t[1]), float(t[2]))
            if einheit and einheit.startswith('knot') and sid:
                aus.append(dict(name=l, sid=sid, mer=z[i + 1].split()[0], k=k))
            sid, einheit = None, None
            i += 179
            continue
        i += 1
    return aus


def harcon(sid, puffer):
    st, _, b = sid.partition('_')
    p = os.path.join(puffer, sid + '.json')
    if os.path.exists(p):
        return json.load(open(p))
    fehler = None
    for _ in range(3):
        try:
            d = json.load(urllib.request.urlopen(URL % (st, b or '1'), timeout=40))
            json.dump(d, open(p, 'w'))
            return d
        except Exception as e:
            fehler = e
            if '400' in str(e):
                break
            time.sleep(3)
    return {'fehler': str(fehler)}


def ph(x):
    return (x + 180) % 360 - 180


def main():
    puffer, aus = sys.argv[1:3]
    s = saetze()
    print(len(s), 'Stromsaetze', sum('Current' not in x['name'] for x in s), 'ohne Current im Namen', flush=True)
    with cf.ThreadPoolExecutor(4) as ex:
        h = list(ex.map(lambda x: harcon(x['sid'], puffer), s))
    with open(aus, 'w', newline='', encoding='utf8') as f:
        w = csv.writer(f)
        w.writerow(['name', 'sid', 'dM2', 'dS2', 'dK1', 'dO1', 'rM2', 'rK1', 'kn_M2', 'kn_NOAA', 'hinweis'])
        for x, d in zip(s, h):
            kk = {c['constituentName']: c for c in d.get('HarmonicConstituents') or [] if c.get('majorAmplitude')}
            if not kk:
                w.writerow([x['name'], x['sid'], '', '', '', '', '', '', '', '', d.get('fehler', 'keine')])
                continue
            mer = int(x['mer'][:3])
            dd, r = {}, {}
            for c in SPEED:
                if c in x['k'] and c in kk:
                    dd[c] = ph(x['k'][c][1] - mer * SPEED[c] - kk[c]['majorPhaseGMT'])
                    r[c] = x['k'][c][0] * 51.444 / kk[c]['majorAmplitude']
            w.writerow([x['name'], x['sid']] + ['%.1f' % dd[c] if c in dd else '' for c in SPEED] +
                       ['%.2f' % r[c] if c in r else '' for c in ('M2', 'K1')] +
                       ['%.3f' % x['k']['M2'][0] if 'M2' in x['k'] else '',
                        '%.3f' % (kk['M2']['majorAmplitude'] / 51.444) if 'M2' in kk else '', ''])
    print('fertig', flush=True)


main()
