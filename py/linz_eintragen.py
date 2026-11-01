#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Uebernimmt LINZ-Harmonische (Release 2025) in den Bestand (1.11.2026, Oliver).

Phasen stehen in Zone +12: G = g - speed*12 (M2 +12,2 Grad); damit treffen die TICON- und Messsaetze
auf unter 2 Grad. Ersetzt wird nur, was kein Mess- oder TICON-Satz ist und abweicht (M2 >=3 Grad, S2 >=5,
K1 >=15, Hub >=5 %). Name, Position und Region bleiben vom alten Satz, der ins Archiv geht.
Lizenz CC BY 4.0, Quelle wird im Satz genannt.

Usage: python3 py/linz_eintragen.py [--schreiben]
"""
from __future__ import annotations

import csv
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import health_check as hc                                           # noqa: E402
import linz_harm as L                                               # noqa: E402
import xtide_modell as X                                            # noqa: E402

ROOT = L.ROOT
ZIEL = os.path.join(ROOT, 'harmonics/utide/harmonics_utide_observations.txt')
LISTE = os.path.join(ROOT, 'harmonics/help/linz_20261101_loeschen.csv')
GUT = ('harmonics_utide_observations.txt', 'harmonics_ticon4_worldwide.txt')
NAMEN_NEU = {}      # Kopf 210 Dargaville nennt 3656 S statt 3556 S: von Hand dem Bestandssatz zugeordnet
d = lambda a, b: (a - b + 180) % 360 - 180


def norm(s):
    return re.sub(r'[^a-z]', '', s.lower())


def main():
    namen, speeds, _a, _f = X.kopf_lesen(ZIEL)
    R = [r for r in hc.load_records() if not r['current'] and r['lat'] is not None and 'M2' in r['amp'] and 'S2' in r['amp']
         and -48 < r['lat'] < -34 and 165 < r['lon'] < 179]
    neu, weg, gemeldet = [], [], []
    for s in L.saetze():
        G = {t: (a, (g - speeds[t] * 12) % 360) for t, (a, g) in s['werte'].items() if t in speeds}
        v = {'lat': s['lat'], 'lon': s['lon']}
        um = sorted((r for r in R if hc.km(v, r) <= 6), key=lambda r: hc.km(v, r))
        tr = [r for r in um if norm(s['name'])[:6] in norm(r['name'])]
        r = tr[0] if tr else (um[0] if um and hc.km(v, um[0]) <= 2 else None)
        if s['id'] == '076':     # Messsatz steht als "Pot Taranaki" im Bestand, Dublette wird getrennt archiviert
            continue
        if r is None:
            if s['id'] in NAMEN_NEU:
                neu.append((s, G, NAMEN_NEU[s['id']], s['lat'], s['lon'], []))
            else:
                gemeldet.append((s['name'], 'kein Partner'))
            continue
        if any(os.path.basename(q['file']) in GUT for q in tr or um[:1]):
            continue
        z, w, _e, m = X.satz_lesen(os.path.join(ROOT, r['file']), r['name'])
        kl = X.kopf_lesen(os.path.join(ROOT, r['file']))[1]
        g = lambda t: (w[t][1] - kl[t] * m) % 360
        dm, ds = d(g('M2'), G['M2'][1]), d(g('S2'), G['S2'][1])
        dk = d(g('K1'), G['K1'][1]) if 'K1' in w else 0
        hub = w['M2'][0] * r['scale'] / G['M2'][0]
        if abs(dm) >= 3 or abs(ds) >= 5 or abs(dk) >= 15 or abs(hub - 1) >= 0.05:
            t = open(os.path.join(ROOT, r['file']), encoding='iso-8859-1').read().split('\n')
            k = t.index(r['name'])
            j = k
            while not t[j].startswith('# BEGIN'):
                j -= 1
            hot = [x for x in t[j:k] if re.match(r'# (region|province|state|admin1_quelle):', x)]
            neu.append((s, G, r['name'], r['lat'], r['lon'], hot))
            weg.append((r['file'], r['name'], f"LINZ-Analyse {s['zeitraum']} ersetzt: M2 {dm:+.0f} Grad, S2 {ds:+.0f}, K1 {dk:+.0f}, Hub x{hub:.2f}. 1.11.2026"))
        print(f"{s['name'][:20]:20s} {r['name'][:32]:32s} {os.path.basename(r['file'])[:24]:24s} dM {dm:+5.0f} dS {ds:+5.0f} dK {dk:+5.0f} x{hub:.2f} {'ERSETZT' if weg and weg[-1][1] == r['name'] else ''}")
    print(len(neu), 'neu', len(weg), 'archiviert', gemeldet)
    fehlt = sorted({t for s in L.saetze() for t in s['werte'] if t not in speeds})
    print('nicht im Kopf:', fehlt)
    if '--schreiben' not in sys.argv:
        return
    with open(LISTE, 'w', encoding='utf-8', newline='') as fh:
        w = csv.writer(fh)
        w.writerow(['datei', 'name', 'fehler_prozent', 'begruendung'])
        for a, b, c in weg:
            w.writerow([a, b, '-', c])
    z = []
    for s, G, name, la, lo, hot in neu:
        z += ['# BEGIN HOT COMMENTS', '# country: New Zealand', '# source: LINZ Tide Constituents 2025 (CC BY 4.0), harmonic analysis of hourly gauge data',
              f"# station_id_context: LINZ-{s['id']}", '# date_imported: 20261101', '# datum: Chart Datum (LINZ Z0 above CD)', '# confidence: 9',
              f"# note: LINZ Analyse {s['zeitraum']}, Stunde; Phasen von Zone +12 auf Greenwich umgerechnet.", *hot,
              '# !units: meters', f'# !longitude: {lo:.4f}', f'# !latitude: {la:.4f}', name, '+00:00 :Pacific/Auckland', f"{s['z0']:.4f} meters"]
        for q in namen:
            if q in G and G[q][0] >= 0.0005:
                z.append(f'{q:<16}{G[q][0]:.4f}  {G[q][1]:.2f}')
            else:
                z.append('x 0 0')
    t = open(ZIEL, encoding='iso-8859-1').read()
    for x in z:
        x.encode('iso-8859-1')
    open(ZIEL, 'w', encoding='iso-8859-1').write(t.rstrip('\n') + '\n' + '\n'.join(z) + '\n')


if __name__ == '__main__':
    main()
