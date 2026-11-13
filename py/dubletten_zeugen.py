#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Namensdubletten nach Zeugen statt nach Rang entscheiden (Oliver 13.11.2026: "du hast einfach nach Rang entschieden?").

Regel (Notiz landesquelle-nicht-unfehlbar): erst unabhaengige Messsaetze in der Naehe, dann Modelle, Rang zuletzt.
Fuer jedes Paar (behaltener Satz im Bestand, archivierter Satz in harmonics/backup/geloescht/) mit > MIN_PCT Abstand:
  Zeugen  = Messsaetze (utide_observations, ticon, current_observations) bis ZEUGE_KM, nicht gleichen Namens;
            Kurvenfehler (M2 S2 N2 K1 O1, wie FES-Pruefung) gegen die bis zu 3 naechsten, Median.
  Modelle = FES2022 am Ort (Gezeiten) bzw. TPXO10-Strom (Stroeme, Hauptachse des Satzes) -- nur wenn keine Zeugen.
Ergebnis je Paar: welcher Satz naeher an den Zeugen liegt; "tauschen", wenn der archivierte um > 2 Prozentpunkte besser ist.

Usage: venv/bin/python py/dubletten_zeugen.py harmonics/help/dubletten_namen_20261113_loeschen.csv
"""
import cmath
import csv
import math
import os
import re
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import health_check as H                                           # noqa: E402
import xtide_modell as X                                           # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
K = ('M2', 'S2', 'N2', 'K1', 'O1')
ZEUGE_KM, MIN_PCT = 30.0, 5.0
MESS = re.compile(r'utide_observations|ticon|current_observations')


def archiv_satz(datei, name):
    """letzter archivierter Block dieses Namens -> z-dict (Greenwich, komplex, m bzw. kn), lat, lon"""
    p = os.path.join(ROOT, 'harmonics/backup/geloescht', os.path.basename(datei))
    L = open(p, encoding='iso-8859-1').read().split('\n')
    i = max(k for k, x in enumerate(L) if x == name)
    kopf = '\n'.join(L[max(0, i - 40):i])
    la = float(re.findall(r'!latitude: (\S+)', kopf)[-1])
    lo = float(re.findall(r'!longitude: (\S+)', kopf)[-1])
    mer = L[i + 1].split()[0]
    vz = -1.0 if mer[0] == '-' else 1.0
    hh, mm = mer.lstrip('+-').split(':')
    meridian = vz * (int(hh) + int(mm) / 60.0)
    f = 0.3048 if L[i + 2].split()[1].startswith('f') else 1.0
    _n, speeds, _a, _f = X.kopf_lesen(os.path.join(ROOT, datei))
    z = {}
    j = i + 3
    while j < len(L) and L[j].strip() and not L[j].startswith('#'):
        t = L[j].split()
        if t[0] in K:
            z[t[0]] = cmath.rect(float(t[1]) * f, -math.radians(X.greenwich(float(t[2]), speeds[t[0]], meridian)))
        j += 1
    return z, la, lo


def fehler(za, zb):
    ks = [k for k in K if k in za and k in zb]
    tot = max(0.05, sum(abs(zb[k]) for k in ks))
    return min(100 * math.sqrt(sum(abs(za[k] - v * zb[k]) ** 2 for k in ks) / 2) / tot for v in (1, -1))


def main(argv):
    R = H.load_records()
    beh = {r['name']: r for r in R}
    zeugen = [r for r in R if r['lat'] is not None and MESS.search(os.path.basename(r['file']))]
    for z in csv.DictReader(open(argv[0], encoding='utf-8')):
        name = z['name']
        k = beh.get(name)
        if not k:
            print('%-50s behaltener Satz nicht mehr im Bestand' % name[:50])
            continue
        za, la, lo = archiv_satz(z['datei'], name)
        zk = {c: k['z'][c] for c in K if c in k['z']}
        abst = fehler(za, zk)
        if abst < MIN_PCT:
            continue
        nah = sorted((r for r in zeugen if r['name'] != name and r['current'] == k['current']),
                     key=lambda r: H.km(k, r))[:3]
        nah = [r for r in nah if H.km(k, r) <= ZEUGE_KM]
        stufe = 'Messung'
        if not nah:                          # Stufe 2: unabhaengige Tafelsaetze anderer Herkunft (keine Uebertragung, kein FES)
            stufe = 'Tafel'
            fam = {os.path.basename(k['file'])[:20], os.path.basename(z['datei'])[:20]}
            nah = sorted((r for r in R if r['lat'] is not None and r['name'] != name and r['current'] == k['current']
                          and not re.search(r'secondary|fes2022|noaa_(amtt|cptt|censam|eutt|carib|pacif)|transfer', os.path.basename(r['file']))
                          and os.path.basename(r['file'])[:20] not in fam), key=lambda r: H.km(k, r))[:3]
            nah = [r for r in nah if H.km(k, r) <= 25.0]
        if nah:
            ek = float(np.median([fehler(zk, r['z']) for r in nah]))
            ea = float(np.median([fehler(za, r['z']) for r in nah]))
            quelle = stufe + ': ' + ', '.join('%s %.0f km' % (r['name'].split(',')[0][:22], H.km(k, r)) for r in nah)
        elif not k['current']:               # Stufe 3: FES und TPXO10, nur wenn beide einig (< 10 %)
            import tpxo as TP
            from luecken_fes_welt import sample as smp
            import netCDF4 as nc
            from fes_ersatz_inseln import stem, FES_DIR
            fv = {}
            for c in K:
                a_, g_ = smp(nc.Dataset(os.path.join(FES_DIR, '%s_fes2022.nc' % stem(c))), k['lat'], k['lon'])
                if a_:
                    fv[c] = cmath.rect(a_, -math.radians(g_))
            w, _d = TP.konstanten('10', k['lat'], k['lon'])
            tv = {c: cmath.rect(w[c][0], -math.radians(w[c][1])) for c in K if w and c in w}
            einig = fehler(fv, tv) if fv and tv else 999
            if einig < 10:
                ek, ea = fehler(zk, fv), fehler(za, fv)
                quelle = 'Modelle (FES/TPXO10 einig %.0f %%)' % einig
            else:
                ek = ea = float('nan')
                quelle = 'keine Zeugen, Modelle uneins (%.0f %%)' % einig
        else:
            ek = ea = float('nan')
            quelle = 'keine Zeugen'
        urteil = 'tauschen' if ea + 2 < ek else ('bleibt' if ek + 2 < ea else 'gleich')
        print('%-46s %5.1f %% | behalten %-22s %5.1f %% | archiviert %-22s %5.1f %% | %-8s | %s' % (
            name[:46], abst, os.path.basename(k['file'])[9:31], ek, os.path.basename(z['datei'])[9:31], ea, urteil, quelle[:90]))


if __name__ == '__main__':
    main(sys.argv[1:])
