#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sucht verschriebene Phasen in den Altsaetzen (harmonics-2004/1997).

Island 1.11.2026: einzelne Phasen tragen Tippfehler (319.70 statt 31.97), der Rest des Satzes ist
gut. Die Tiden eines Satzes stehen in festem Abstand zueinander: K2~S2, P1~K1, S2-M2, M2-N2 und
K1-O1 wie bei den sechs naechsten Nachbarn. Fuer jede Tide entsteht so eine Erwartung aus dem
eigenen Satz; zweiter Zeuge ist FES (harmonics/help/fes_pruefung_bestand.csv).

Klasse A: eine einzige Ziffer oder ein Komma aendern trifft beide Zeugen auf <5 Grad.
Klasse B: Tide liegt >30 Grad neben beiden Zeugen, ohne solche Aenderung.

Usage: python3 py/phasenprobe.py      -> harmonics/help/phasenprobe_20261101.csv
"""
from __future__ import annotations

import csv
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import health_check as hc                                           # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUS = os.path.join(ROOT, 'harmonics/help/phasenprobe_20261101.csv')
QUELLEN = ('harmonics-2004-06-14_mod.txt', 'harmonics-1997-05-25_mod.txt')
TAKT = {'M2': 28.984, 'S2': 30.0, 'K1': 15.041, 'O1': 13.943}
# Tide -> Bezugstiden, deren Abstand gilt
PAARE = {'M2': ['S2', 'N2'], 'S2': ['M2', 'K2'], 'K2': ['S2'], 'N2': ['M2'], 'K1': ['O1', 'P1'], 'P1': ['K1'], 'O1': ['K1']}
d = lambda a, b: (a - b + 180) % 360 - 180


def varianten(p):
    """Alle Werte, die eine Ziffer oder ein Komma von p entfernt sind."""
    s = f'{p:06.2f}'
    ziff = s.replace('.', '')
    out = set()
    for i, c in enumerate(ziff):
        for n in '0123456789':
            if n != c:
                out.add(float(ziff[:i] + n + ziff[i + 1:]) / 100)
    for q in (float(ziff) / 10, float(ziff) / 1000):      # 319.70 <- 31.97, 31.97 <- 319.7
        out.add(q)
    return {x for x in out if x < 360}


def main():
    recs = [r for r in hc.load_records() if not r['current'] and r['lat'] is not None and 'M2' in r['amp'] and 'S2' in r['amp']]
    la = np.radians([r['lat'] for r in recs])
    lo = np.radians([r['lon'] for r in recs])
    fes = {}
    for z in csv.DictReader(open(os.path.join(ROOT, 'harmonics/help/fes_pruefung_bestand.csv'), encoding='utf-8')):
        fes[(os.path.basename(z['datei']), z['name'])] = z
    aus = []
    for i, r in enumerate(recs):
        f = os.path.basename(r['file'])
        if f not in QUELLEN:
            continue
        fak = 0.3048 if r['units'].startswith('f') else 1.0
        w = r['amp']
        if w['M2'][0] * fak < 0.05:
            continue
        c = np.sin(la[i]) * np.sin(la) + np.cos(la[i]) * np.cos(la) * np.cos(lo - lo[i])
        nb = [recs[j] for j in np.argsort(-c)[1:7] if c[j] > math.cos(300 / 6371)]
        fz = fes.get((f, r['name']), {})
        for t, bezug in PAARE.items():
            if t not in w or w[t][0] * fak < 0.015:
                continue
            p = w[t][1]
            erw = []
            for b in bezug:
                if b not in w:
                    continue
                abst = [d(n['amp'][t][1], n['amp'][b][1]) for n in nb if t in n['amp'] and b in n['amp']]
                if len(abst) >= 3 or b in ('K2', 'P1') or t in ('K2', 'P1'):
                    m = float(np.median(abst)) if abst else 0.0
                    erw.append((w[b][1] + m) % 360)
            if not erw:
                continue
            fw = fz.get(t.lower() + '_min', '')
            fphase = (p - float(fw) * TAKT[t] / 60) % 360 if fw not in ('', None) and t in TAKT else None
            nah = min(abs(d(p, e)) for e in erw)
            if nah < 30:
                continue
            if fphase is not None and abs(d(p, fphase)) < 25:
                continue
            ziel = [e for e in erw] + ([fphase] if fphase is not None else [])
            treffer = [v for v in varianten(p) if all(abs(d(v, e)) < 5 for e in (erw[:1] + ([fphase] if fphase is not None else [])))]
            aus.append(dict(klasse='A' if treffer and fphase is not None else 'A?' if treffer else 'B', datei=f, name=r['name'],
                            lat=r['lat'], lon=r['lon'], tide=t, amp_m=round(w[t][0] * fak, 3), phase=p,
                            erwartet=' '.join(f'{e:.1f}' for e in erw), fes='' if fphase is None else f'{fphase:.1f}',
                            aenderung=' '.join(f'{v:.2f}' for v in sorted(treffer)),
                            nachbarn=len(nb)))
    aus.sort(key=lambda x: (x['klasse'], x['name']))
    with open(AUS, 'w', encoding='utf-8', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=list(aus[0]))
        w.writeheader()
        w.writerows(aus)
    print(len(aus), {k: sum(1 for x in aus if x['klasse'] == k) for k in ('A', 'A?', 'B')})


if __name__ == '__main__':
    main()
