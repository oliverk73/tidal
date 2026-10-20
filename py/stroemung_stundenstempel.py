#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Stempelfehler der Stundenmittel in den Stroemungsfits beheben (Oliver 20.10.2026).

bodc_stroemung.reihe, cmems_stroemung_nachholen.reihe und die MDE-Einleseskripte mittelten mit
df.resample('1h').mean(): das Mittel einer Stunde bekommt den Stempel ihres Beginns. Bei
10-min-Werten liegt es 25 min spaeter, bei 1-min-Werten 29,5 min -- die Fits kamen um diese Zeit
zu frueh heraus. Gefunden am Druck der Anglian-ADCPs (MDE TCE-3952), der so 30 min vor den
Pegeln lag und mit richtigem Stempel auf 0-5 min passt.

Heilung ohne Neufit: die Zeitverschiebung d (Minuten) geht exakt in die Phasen ein,
kappa_neu = kappa + Speed * d / 60. d je Satz aus den Rohdaten (C.stempelfehler_min):
  BODC   bodc_ref bzw. "N deployments combined, BODC refs a..b" (Reihen im Bereich, < 1,5 km)
  CMEMS  nur Saetze aus cmems_stroemung_nachholen (Rohdatei in water_levels/CMEMS_currents_neu)
  MDE    beim Einlesen gemessen (MDE unten)
Saetze aus stuendlichen Quellen (d < 1 min) bleiben unberuehrt.
Usage: venv/bin/python py/stroemung_stundenstempel.py [--schreiben]
"""
import glob
import os
import re
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bodc_stroemung as B                                          # noqa: E402
import cmems_stroemung_nachholen as C                               # noqa: E402
import health_check as hc                                           # noqa: E402
import sicher_schreiben                                             # noqa: E402
import xtide_modell as X                                            # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATEI = os.path.join(ROOT, 'harmonics/utide/harmonics_utide_current_observations.txt')
NEU = os.path.join(ROOT, 'water_levels/CMEMS_currents_neu')
# MDE: Stempelfehler beim Einlesen der Rohdaten gemessen (Takt 1-10 min)
MDE = {'Needles (15 km SW': 29.21, 'Swanage (20 km SE': 32.50, 'Swanage (22 km SSE': 29.50,
       'Lundy (24 km N': 20.03, 'Ilfracombe (24 km WNW': 20.38, 'Dale (3 km E': 30.98,
       'Worthing (': 25.01, 'Brighton (': 24.99, 'Shoreham (': 25.00,
       'Skomer (96 km SW': 25.06, 'Padstow (71 km NW': 28.38}
NOTIZ = '# note: 20261020 phases +%.1f min: hourly means had been stamped at the start of the hour'


def bodc_delta(M, refs, min_h=B.MIN_STUNDEN):
    """-> (gewichtetes d, Anzahl Reihen) ueber die Reihen refs."""
    s = w = 0.0
    n = 0
    for ref in refs:
        m = M[ref]
        x = B.reihe(os.path.join(m['_dir'], 'b%07d.qxf' % int(ref)), float(m['Sea floor depth (m)'] or 'nan'), roh=True)
        if not x or not len(x[0]):
            continue
        t = x[0].index
        h = t.floor('1h').nunique()
        if h < min_h:
            continue
        s += C.stempelfehler_min(t) * h
        w += h
        n += 1
    return (s / w if w else None), n


def main(argv):
    namen, speeds, _, _ = X.kopf_lesen(DATEI)
    L = open(DATEI, encoding='iso-8859-1').read().split('\n')
    M = B.metadaten()
    neu = {re.sub(r'^.._TS_MO_|\.nc$', '', os.path.basename(p)): p for p in glob.glob(NEU + '/*.nc')}
    stationen = [k for k in range(len(L) - 1) if L[k] and not L[k].startswith('#') and hc.MERIDIAN.match(L[k + 1])]
    aenderungen = []
    vorher = 0
    for k in stationen:
        kopf = L[vorher:k]
        vorher = k
        text = '\n'.join(kopf)
        if '# note: 20261020 phases' in text:
            continue
        d, wie = None, ''
        g = re.search(r'(\d+) deployments combined, BODC refs (\d+)\.\.(\d+)', text)
        liste = re.search(r'deployments combined, BODC refs ([\d ]+)$', text, re.M)
        b = re.search(r'# bodc_ref: BODC(\d+)', text)
        c = re.search(r'# cmems_code: (\S+)', text)
        if g:
            la = float(re.search(r'# !latitude: (\S+)', text).group(1))
            lo = float(re.search(r'# !longitude: (\S+)', text).group(1))
            a, e = int(g.group(2)), int(g.group(3))
            refs = [r for r, m in M.items() if a <= int(r) <= e
                    and hc.km(dict(lat=la, lon=lo), dict(lat=float(m['Latitude A']), lon=float(m['Longitude A']))) < 1.5]
            d, n = bodc_delta(M, refs)
            wie = 'BODC %d/%s Reihen' % (n, g.group(1))
        elif liste:
            refs = [r for r in liste.group(1).split() if r in M]
            d, n = bodc_delta(M, refs, 0)
            wie = 'BODC %d Reihen' % n
        elif b and b.group(1) in M:
            d, n = bodc_delta(M, [b.group(1)], 0)
            wie = 'BODC %s' % b.group(1)
        elif c and c.group(1) in neu and 'institution:' in text:
            x = C.reihe(neu[c.group(1)], roh=True)
            d = C.stempelfehler_min(x[0].index) if x else None
            wie = 'CMEMS %s' % c.group(1)
        elif '# mde_id:' in text:
            d = next((v for p, v in MDE.items() if L[k].startswith(p)), None)
            wie = 'MDE'
            assert d is not None, L[k]
        if d is None or d < 1:
            continue
        aenderungen.append((k, d))
        print('%+5.1f min  %-22s %s' % (d, wie, L[k][:70]), flush=True)
    for k, d in reversed(aenderungen):
        j = k + 3
        while j < len(L) and L[j].strip() and not L[j].startswith('#'):
            f = L[j].split()
            if f[0] != 'x' and float(f[1]) > 0:
                L[j] = '%-15s %s  %.2f' % (f[0], f[1], (float(f[2]) + speeds[f[0]] * d / 60) % 360)
            j += 1
        L.insert(k, NOTIZ % d)
    print(len(aenderungen), 'Saetze verschoben')
    if '--schreiben' in argv:
        sicher_schreiben.schreiben(DATEI, '\n'.join(L))


if __name__ == '__main__':
    main(sys.argv[1:])
