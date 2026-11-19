#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Stroemungssaetze aus den SHOM-Produkten "Courants de maree 3D" (Fromveur, Estuaire de la Loire), Oliver 19.11.2026.

Licence Ouverte 2.0 (Etalab). ASCII-Dateien je Schicht/Bedingung/Zeitschritt: Geschwindigkeit (m/s) und
Richtung (wohin, Grad rechtweisend) an Punkten eines unstrukturierten Gitters, Koeffizient 45 (ME) und 95 (VE),
Zeit relativ zur PM des Bezugshafens (Fromveur: Brest, 15 min, -6h30..+6h30; Loire: Saint-Nazaire, 1 h, -6..+6).
Trockenfallende Punkte fehlen in einzelnen Dateien -> nur Punkte mit allen Zeitschritten.
Umrechnung wie py/shom_atlas_stroemung.py (Atlas-Regel -> synthetisches Jahr -> UTide), Oberflaeche wie die
2D-Atlanten. Brennpunkte: VE-Maximum >= SCHWELLE kn, kein Stromsatz in ABSTAND km, je ABSTAND km der staerkste,
Landmarke naeher als KUESTE_KM (offene See deckt der 2D-Atlas), R2 >= R2_MIN.
Abgleich 19.11.: Fromveur M2 5,26 kn/34,6 Grad gegen 2D-Atlas 5,30/34,4; Loire-Produkt gegen Atlas 565 2-8 Grad, <= 10 %.

Usage: venv/bin/python py/shom_3d_stroemung.py [fromveur|loire ...] [--schreiben]
"""
from __future__ import annotations

import csv
import datetime as dt
import glob
import math
import os
import re
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shom_atlas_stroemung as A                                    # noqa: E402

ROOT = A.ROOT
D = os.path.join(ROOT, 'quellen/tidal_streams/SHOM_3D')
SCHWELLE, ABSTAND, KUESTE_KM, R2_MIN = 1.5, 3.0, 3.5, 0.9
FEIN_M = 250          # Gitterabstand < 250 m: Modell dort verfeinert (Aestuar, Engstelle) -> auch ohne nahe Landmarke
BINNEN = [(47.53, 47.66, -2.95, -2.65)]   # Golfe du Morbihan: Binnengewaesser, GeoNames-Landmarken duenn
MS_KN = 1.0 / 0.514444
A.HAFEN.setdefault('SAINT-NAZAIRE', (A.OBS, 'Saint-Nazaire, France'))

PRODUKT = {
    'fromveur': dict(ordner='FROMVEUR_PACK', port='BREST', lambert=False, titel='Courants de maree 3D - Fromveur (2014)',
                     muster='FROMVEUR3D_0_pl10_ms_*data%s.txt'),
    'loire': dict(ordner='C3D_LOIRE', port='SAINT-NAZAIRE', lambert=True, titel='Courants de maree 3D - Estuaire de la Loire (2014)',
                  muster='LOIRE_0_pl13_ms_*data%s.txt'),
}


def _tau(datei):
    m = re.search(r'_(-?)(\d+)h(\d+)mindata', datei)
    if m:
        return (-1 if m.group(1) else 1) * (int(m.group(2)) * 60 + int(m.group(3)))
    m = re.search(r'_ms_(\d+)data', datei)
    return (int(m.group(1)) - 7) * 60                     # 01 = PM-6h ... 13 = PM+6h


class Atlas3D:
    """Gleiche Schnittstelle wie shom_atlas_stroemung.Atlas (port, bm, coeff, tau, zyklus)."""

    def __init__(self, name):
        p = PRODUKT[name]
        self.name, self.p, self.port, self.bm, self.coeff = name, p, p['port'], False, [45, 95]
        werte = {}
        for ci, bed in enumerate(('ME', 'VE')):
            for f in glob.glob(os.path.join(D, p['ordner'], 'ASCII', bed, 'SURFACE', p['muster'] % bed)):
                t = _tau(f)
                a = np.loadtxt(f, skiprows=1)
                for x, y, vit, rich, _h in a:
                    werte.setdefault((round(x, 5), round(y, 5)), {})[(ci, t)] = (vit, rich)
        taus = sorted({t for v in werte.values() for _c, t in v})
        self.tau = np.array(taus, float)
        voll = [k for k, v in werte.items() if len(v) == 2 * len(taus)]
        xy = np.array(voll)
        if p['lambert']:
            import pyproj
            lo, la = pyproj.Transformer.from_crs(2154, 4326, always_xy=True).transform(xy[:, 0], xy[:, 1])
        else:
            lo, la = xy[:, 0], xy[:, 1]
        self.lat, self.lon = np.asarray(la, float), np.asarray(lo, float)
        n = len(voll)
        self.U = np.zeros((n, 2, len(taus)))
        self.V = np.zeros((n, 2, len(taus)))
        for i, k in enumerate(voll):
            for (ci, t), (vit, rich) in werte[k].items():
                j = taus.index(t)
                self.U[i, ci, j] = vit * math.sin(math.radians(rich))
                self.V[i, ci, j] = vit * math.cos(math.radians(rich))
        from scipy.spatial import cKDTree
        xy_km = np.c_[self.lon * 111 * np.cos(np.radians(self.lat)), self.lat * 111]
        self.fein = cKDTree(xy_km).query(xy_km, k=2)[0][:, 1] * 1000 < FEIN_M
        self.vmax = np.hypot(self.U[:, 1], self.V[:, 1]).max(axis=1) * MS_KN
        print('%s: %d Punkte (von %d), %d Zeitschritte %+d..%+d min' % (name, n, len(werte), len(taus), taus[0], taus[-1]))

    def zyklus(self, i, _i=None):
        return self.U[i], self.V[i]


def block(at, i, r):
    p = at.p
    L = ['# Harmonic constants derived from the Shom product "%s", surface layer, model output' % p['titel'],
         '# Atlas rule: minutes from HW %s, coefficients 45/95 interpolated (Brest coefficient), one synthetic year 2026'
         % A.HAFEN[at.port][1].split(',')[0].split(' (')[0],
         '# no time correction (2D Shom atlases checked +3 min against UK ADCPs)',
         '# Shom, Courants de maree 3D, diffusion.shom.fr (Licence Ouverte 2.0)',
         '# (UTide, principal-axis projection), %d 10-minute samples, surface' % r['n'],
         '# R^2 = %.4f, RMS error = %.4f knots' % (r['r2'], r['rms']),
         '# Major axis: %.1f deg true' % r['achse'], '#',
         '# BEGIN HOT COMMENTS', '# country: France',
         '# source: Shom 3D tidal current product %s (model), UTide analysis' % at.name.capitalize(),
         '# station_id_context: SHOM-C3D-%s-%d' % (at.name.upper(), i), '# institution: Shom', '# datum: n/a',
         '# station_type: current', '# major_axis_deg_true: %.1f' % r['achse'], '# confidence: 5',
         '# time_correction_min: 0',
         '# note: MODEL-DERIVED. Brennpunkt Spring (VE 95) %.1f kn, kein Satz in %.0f km, Oliver %s.'
         % (at.vmax[i], ABSTAND, dt.date.today().strftime('%Y%m%d')),
         '# !units: knots', '# !longitude: %.5f' % at.lon[i], '# !latitude: %.5f' % at.lat[i]]
    return L


def main(argv):
    import health_check as H
    import strom_namen_vorort as SN
    import json
    from generate_germany_harmonics_175 import CONSTITUENTS_175
    from sicher_schreiben import schreiben
    schreib = '--schreiben' in argv
    namen = [a for a in argv if a in PRODUKT] or list(PRODUKT)
    REC = H.load_records()
    S = [(r['lat'], r['lon']) for r in REC if r['current'] and r['lat'] is not None and 46 < r['lat'] < 49.5 and -6 < r['lon'] < 0]
    alle = {r['name'] for r in REC}
    ORTE = json.load(open(SN.ORTE, encoding='utf-8'))
    L = [z for z in json.load(open(SN.LM, encoding='utf-8')) if 46 < z[1] < 49.5 and -6 < z[2] < 0]
    bloecke, liste, vorschau, vergeben = [], [], [], set()
    for nm in namen:
        at = Atlas3D(nm)
        kand = [i for i in np.argsort(-at.vmax) if at.vmax[i] >= SCHWELLE]
        wahl = []
        for i in kand:
            if any(SN.km(at.lat[i], at.lon[i], a, b) < ABSTAND for a, b in S):
                continue
            if any(SN.km(at.lat[i], at.lon[i], at.lat[j], at.lon[j]) < ABSTAND for j in wahl):
                continue
            wahl.append(i)
        print('%s: %d Kandidaten >= %.1f kn, %d Brennpunkte' % (nm, len(kand), SCHWELLE, len(wahl)))
        SN.landmarken([], punkte=[(float(at.lat[i]), float(at.lon[i])) for i in wahl])   # Landmarken um die Brennpunkte
        L = [z for z in json.load(open(SN.LM, encoding='utf-8')) if 46 < z[1] < 49.5 and -6 < z[2] < 0]
        for i in wahl:
            la, lo = float(at.lat[i]), float(at.lon[i])
            name = SN.vorschlag(la, lo, L)
            if name:
                name = re.sub(r'\s*\(historical\)', '', name)
            else:
                nah = sorted((SN.km(la, lo, a, b), n, a, b, t) for n, a, b, c, t in L
                             if c in SN.PUNKT and abs(a - la) < 0.1 and abs(b - lo) < 0.15)
                innen = at.fein[i] or any(a <= la <= b and c <= lo <= d for a, b, c, d in BINNEN)
                if not nah or (nah[0][0] >= KUESTE_KM and not innen):   # offene See: 2D-Atlas/FES reichen
                    print('  %.4f %.4f %.1f kn keine Landmarke' % (la, lo, at.vmax[i]))
                    continue
                d, n, a, b, t = nah[0]
                if d >= KUESTE_KM:                                  # Binnen/Aestuar: naechster Ort statt ferner Landmarke
                    oo = [(SN.km(la, lo, oa, ob), on, oa, ob, e) for on, oa, ob, e in ORTE
                          if abs(oa - la) < 0.1 and abs(ob - lo) < 0.15]
                    oo = [x for x in oo if x[0] < min(d, 4.0)]
                    if oo:                                          # der groesste Ort bis 4 km (bekannt, bei Maps zu finden)
                        d, n, a, b, _e = max(oo, key=lambda x: (x[4], -x[0]))
                n = re.sub(r'\s+(Lighthouse|Light Station|Light|\(historical\))$', '', n)
                name = '%s (%d km %s), %s Current' % (SN.latin1(n), max(1, round(d)), SN.richtung(la, lo, a, b), t)
            name = SN.auf_tcd_laenge(SN.latin1(name))
            if not name or name in alle or name in vergeben:
                print('  %s: Name fehlt/vergeben' % name)
                continue
            vergeben.add(name)
            df = A.reihe(at, i, None)
            r = A.C.analyse(df, la, A.KONST)
            if r['r2'] < R2_MIN:                                  # Drehstrom/Kehrwasser: Achsprojektion taugt nicht
                print('  %s: R2 %.2f, entfaellt' % (name, r['r2']))
                vergeben.discard(name)
                continue
            print('%-62s %.4f %.4f  VE %.2f kn  M2 %.2f  Achse %3.0f  R2 %.3f' % (name, la, lo, at.vmax[i], r['m2'], r['achse'], r['r2']))
            vorschau.append((name, '%.5f' % la, '%.5f' % lo, '%.2f' % at.vmax[i], 'https://www.google.com/maps?q=%.5f,%.5f' % (la, lo)))
            B = block(at, i, r) + [name, '+00:00 :UTC', '%.4f knots' % r['mean']]
            for k, _sp in CONSTITUENTS_175:
                c = r['konst'].get(k)
                B.append('%-15s %.4f  %.2f' % (k, c[0], c[1]) if c and c[0] >= 0.00005 else 'x 0 0')
            bloecke.append('\n'.join(B))
            liste.append(('harmonics_utide_current_tables.txt', name))
    heute = dt.date.today().strftime('%Y%m%d')
    with open(os.path.join(ROOT, 'harmonics/help/shom3d_vorschlag_%s.csv' % heute), 'w', newline='', encoding='utf-8') as fh:
        w = csv.writer(fh)
        w.writerow(['name', 'lat', 'lon', 'spring_kn', 'google_maps'])
        w.writerows(vorschau)
    print('%d Saetze' % len(bloecke))
    if schreib and bloecke:
        STROM = os.path.join(ROOT, 'harmonics/utide/harmonics_utide_current_tables.txt')
        T = open(STROM, encoding='iso-8859-1').read().rstrip('\n')
        schreiben(STROM, T + '\n' + '\n'.join(bloecke) + '\n')
        nl = os.path.join(ROOT, 'harmonics/help/neu_pruefen_%s.csv' % heute)
        neu = not os.path.exists(nl)
        with open(nl, 'a', newline='', encoding='utf-8') as fh:
            w = csv.writer(fh)
            if neu:
                w.writerow(['datei', 'name'])
            w.writerows(liste)
        print('->', STROM)


if __name__ == '__main__':
    main(sys.argv[1:])
