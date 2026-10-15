#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ATT-Saetze um die Nebenkonstituenten des archivierten NOAA-Satzes gleicher Position ergaenzen.

Verfahren (Nordkorea 13.10.2026, Philippinen 14.10.2026): Admiralty hat nur M2/S2/K1/O1 (N2/K2/P1/Q1
inferiert), NOAA-Uebertragungen 20-40 Tiden. Die Hauptkonstituenten bleiben aus Admiralty; jede
Nebenkonstituente wird ueber die Hauptkonstituente ihrer Gruppe (M2, S2, K1, O1; Obertiden mit n-facher
Phase) auf den ATT-Satz umgerechnet. Schutz: nur wenn M2/S2/K1/O1 von ATT und NOAA innerhalb Faktor 1.5
liegen (Tandag: NOAA-M2 20x zu klein haette 3 m Fehler erzeugt).

  --test   misst an Orten, wo ATT und NOAA archiviert sind und ein Amtssatz am selben Ort steht, ob die
           Ergaenzung die Kurve naeher an den Amtssatz bringt (Philippinen: 10.2 -> 6.8 cm).

Usage: venv/bin/python py/att_anreichern.py <paare.json> [--test <region.csv>] [--schreiben]
       paare.json: [[ATT-Name, ATT-Datei-Kurzname, NOAA-Name], ...]
"""
import csv
import json
import os
import re
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import xtide_modell as X                                           # noqa: E402

W = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'harmonics') + '/'
ARCH_NOAA = W + 'backup/geloescht/harmonics_noaa_cptt.txt'
ARCH_ATT = W + 'backup/geloescht/harmonics_att_np203_scs.txt'
KOPF = W + 'att/harmonics_att_np203_scs.txt'          # Archivdateien haben keinen Kopf
HAUPT = ('M2', 'S2', 'K1', 'O1')


def bezug(c, speeds):
    w = speeds[c]
    if w < 5:
        return None
    if w < 20:
        return 'K1' if w >= 14.5 else 'O1'
    if w < 35:
        return 'S2' if c in ('S2', 'K2', 'T2', 'R2') else 'M2'
    return 'M2'


def passt(wa, wn):
    return all(k in wa and k in wn and wn[k][0] > 0 and 0.67 <= wa[k][0] / wn[k][0] <= 1.5 for k in HAUPT)


def ergaenzt(wa, ma, wn, mn, speeds):
    G = lambda g, c, m: g - speeds[c] * m                 # -> Greenwich
    neu = {c: wa[c] for c in HAUPT}
    for c, (a, g) in wn.items():
        if c in neu or c not in speeds:
            continue
        b = bezug(c, speeds)
        if not b or b not in wn or b not in wa:
            continue
        n = max(1, round(speeds[c] / speeds['M2'])) if b == 'M2' and speeds[c] > 35 else 1
        ra = (wa[b][0] / wn[b][0]) ** n
        dg = n * (G(wa[b][1], b, ma) - G(wn[b][1], b, mn))
        neu[c] = (a * ra, (G(g, c, mn) + dg + speeds[c] * ma) % 360)
    return neu


def main(argv):
    paare = json.load(open(argv[1]))
    namen, speeds, arg, fak = X.kopf_lesen(KOPF)
    t = np.arange(0, 60 * 86400, 600) + X.jahresbeginn(2026)
    G = lambda g, c, m: g - speeds[c] * m

    def kurve(w, m):
        return X.kurve(t, 0, {c: (a, G(g, c, m)) for c, (a, g) in w.items() if c in speeds}, namen, speeds, arg, fak)

    if '--test' in argv:
        R = list(csv.DictReader(open(argv[argv.index('--test') + 1])))
        ref = {}
        for r in R:
            m = re.search(r'Dublette zu (.*?) \[(.*?)\] ([\d.]+) km', r['befund'])
            if m:
                ref[(r['satz'], r['datei'])] = (m.group(1), m.group(2))
        erg = []
        for (n, d), (p, pf) in ref.items():
            if d != 'att_np203_scs' or not pf.startswith('utide'):
                continue
            noaa = [k for k, v in ref.items() if k[1] == 'noaa_cptt' and v[0] == n and v[1] == 'att_np203_scs']
            if not noaa:
                continue
            try:
                _, wa, _, ma = X.satz_lesen(ARCH_ATT, n)
                _, wn, _, mn = X.satz_lesen(ARCH_NOAA, noaa[0][0])
                _, wr, _, mr = X.satz_lesen(W + 'utide/harmonics_' + pf + '.txt', p)
            except KeyError:
                continue
            if not passt(wa, wn):
                continue
            hr = kurve(wr, mr)
            rms = lambda h: float(np.sqrt(np.mean(((h - h.mean()) - (hr - hr.mean())) ** 2)))
            erg.append((n, rms(kurve(wa, ma)), rms(kurve(ergaenzt(wa, ma, wn, mn, speeds), ma)), rms(kurve(wn, mn))))
        for e in erg:
            print('%-44s ATT %.3f  ATT+NOAA %.3f  NOAA %.3f' % (e[0][:44], *e[1:]))
        if erg:
            a = np.median(np.array([e[1:] for e in erg]), axis=0)
            print('Median ATT %.3f  ATT+NOAA %.3f  NOAA %.3f  (n=%d)' % (*a, len(erg)))
        return
    nach = {}
    for att, f, noaa in paare:
        nach.setdefault(W + 'att/harmonics_' + f + '.txt', []).append((att, noaa))
    stat, aus = [], []
    for T, lst in nach.items():
        L = open(T, encoding='latin-1', newline='').read().split('\n')
        for att, noaa in lst:
            _, wa, _, ma = X.satz_lesen(T, att)
            _, wn, _, mn = X.satz_lesen(ARCH_NOAA, noaa)
            if not passt(wa, wn):
                aus.append(att)
                continue
            neu = ergaenzt(wa, ma, wn, mn, speeds)
            h1, h2 = kurve(wa, ma), kurve(neu, ma)
            stat.append((float(np.sqrt(np.mean((h1 - h2) ** 2))), att))
            if '--schreiben' in argv:
                i = L.index(att)
                b = i + 3
                for j, c in enumerate(namen):
                    L[b + j] = ('%-15s %.4f  %.2f' % (c, neu[c][0], neu[c][1] % 360)) if c in neu and neu[c][0] >= 0.00005 else 'x 0 0'
                L[i:i] = ['# note: %s Nebenkonstituenten aus NOAA-Satz gleicher Position (cptt, archiviert) ueber M2/S2/K1/O1'
                          % __import__('datetime').date.today().strftime('%Y%m%d'),
                          '# note: auf diesen Satz umgerechnet; M2/S2/K1/O1 aus Admiralty unveraendert (Oliver).']
        if '--schreiben' in argv:
            open(T + '.tmp', 'w', encoding='latin-1', newline='').write('\n'.join(L))
            os.replace(T + '.tmp', T)
            print('geschrieben', os.path.basename(T), len(lst) - len([a for a in aus if a in dict(lst)]))
    stat.sort()
    if stat:
        print('%d ergaenzt, %d ausgelassen (NOAA passt nicht: %s); Kurvenaenderung RMS Median %.3f m, max %.3f m (%s)'
              % (len(stat), len(aus), ', '.join(a.split(',')[0] for a in aus[:12]), stat[len(stat) // 2][0], stat[-1][0], stat[-1][1]))


if __name__ == '__main__':
    main(sys.argv)
