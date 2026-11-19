#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Lueckensaetze Australien aus dem AUSTEn-Modell (CSIRO COMPAS, barotrop, unstrukturiert), Oliver 19.11.2026.

Quelle: CSIRO_tidal_const_v12.nc, "AusTEN National Tidal model data", doi 10.25919/q8dw-c732, CC BY-SA 4.0
(Hemer, Herzfeld, Griffin, Trenham 2021). Tiefengemittelte Stromellipsen (t_tide, 364 Tage 2017) fuer
13 Tiden je Gitterzelle, dazu 95-%-Fehler. Ablage quellen/tidal_streams/Australia_AusTEn/.

Eichung 19.11. gegen die 95 Strommesser derselben Studie (52 mit Zelle <= 3 km, >= 0,1 m/s):
Vektorfehler (M2 S2 N2 K1 O1) Median 32 % gegen FES2014 56 %, an 38/52 besser. M2 ~ x1,08; Zeit im
Median +24 min, aber eine einheitliche Korrektur senkt den Fehler nicht (-15 min: 31 %) -> unkorrigiert.

Brennpunkte: Spring (Halbachsen M2+S2) >= 1,5 kn, kein Stromsatz in 8 km, je 8 km der staerkste, Fehler der
M2-Halbachse <= 30 %, Landmarke bis 15 km. Komponente entlang der M2-Hauptachse.

Usage: venv/bin/python py/austen_strom.py [--schreiben]
"""
import csv
import datetime as dt
import json
import math
import os
import re
import sys

import netCDF4
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATEI = os.path.join(ROOT, 'quellen/tidal_streams/Australia_AusTEn/CSIRO_tidal_const_v12.nc')
SCHWELLE, ABSTAND, FEHLER_MAX, LM_KM = 1.5, 8.0, 0.30, 15.0
MS_KN = 1.0 / 0.514444
STAAT = {'Western Australia', 'Northern Territory', 'Queensland', 'New South Wales', 'Victoria', 'Tasmania', 'South Australia'}


def main(argv):
    import health_check as H
    import strom_namen_vorort as SN
    from generate_germany_harmonics_175 import CONSTITUENTS_175
    from sicher_schreiben import schreiben
    from scipy.spatial import cKDTree
    A = netCDF4.Dataset(DATEI)
    ks = [''.join(c.decode() if isinstance(c, bytes) else str(c) for c in x).strip() for x in A['constituent_name'][:]]
    mj, mn, inc, ph, err = [A[v][:].filled(np.nan).astype(float) for v in ('u_maj', 'u_min', 'u_inc', 'u_pha', 'u_maj_err')]
    la, lo = A['Mesh2_face_y'][:].astype(float), A['Mesh2_face_x'][:].astype(float)
    iM2, iS2 = ks.index('M2'), ks.index('S2')
    spring = (mj[:, iM2] + mj[:, iS2]) * MS_KN
    ok = np.isfinite(spring) & (spring >= SCHWELLE) & (err[:, iM2] <= FEHLER_MAX * mj[:, iM2])
    x, y = lo * 111 * np.cos(np.radians(la)), la * 111
    R = [r for r in H.load_records() if r['current'] and r['lat'] is not None and -50 < r['lat'] < -5 and 105 < r['lon'] < 160]
    dS, _ = cKDTree(np.array([(r['lon'] * 111 * math.cos(math.radians(r['lat'])), r['lat'] * 111) for r in R])).query(np.c_[x, y])
    kand = np.where(ok & (dS >= ABSTAND))[0]
    kand = kand[np.argsort(-spring[kand])]
    raster, wahl = {}, []
    for i in kand:
        gx, gy = int(x[i] // ABSTAND), int(y[i] // ABSTAND)
        if any(math.hypot(x[i] - x[j], y[i] - y[j]) < ABSTAND for a in (-1, 0, 1) for b in (-1, 0, 1) for j in raster.get((gx + a, gy + b), ())):
            continue
        raster.setdefault((gx, gy), []).append(i)
        wahl.append(i)
    print('%d Zellen >= %.1f kn (Fehler ok), %d ohne Satz in %.0f km, %d Brennpunkte' % (ok.sum(), SCHWELLE, len(kand), ABSTAND, len(wahl)))
    SN.landmarken([], punkte=[(float(la[i]), float(lo[i])) for i in wahl])
    L = [z for z in json.load(open(SN.LM, encoding='utf-8')) if -50 < z[1] < -5 and 105 < z[2] < 160]
    alle = {r['name'] for r in H.load_records()}
    heute = dt.date.today().strftime('%Y%m%d')
    bloecke, liste, vorschau, vergeben = [], [], [], set()
    for i in wahl:
        name = SN.vorschlag(la[i], lo[i], L)
        if name:
            name = re.sub(r'\s*\(historical\)', '', name)
        else:
            nah = sorted((SN.km(la[i], lo[i], a, b), n, a, b, t) for n, a, b, c, t in L
                         if c in SN.PUNKT and abs(a - la[i]) < 0.2 and abs(b - lo[i]) < 0.3)
            if not nah or nah[0][0] > LM_KM:
                continue
            d, n, a, b, t = nah[0]
            n = re.sub(r'\s*\(historical\)', '', n)
            n = re.sub(r'\s+(Lighthouse|Light Station|Light)$', '', n)
            name = '%s (%d km %s), %s Current' % (SN.latin1(n), max(1, round(d)), SN.richtung(la[i], lo[i], a, b), t)
        if 'Australia' not in name:
            continue
        name = SN.auf_tcd_laenge(SN.latin1(name))
        if not name or name in alle or name in vergeben:
            print('  %s: Name fehlt/vergeben' % name)
            continue
        vergeben.add(name)
        psi = inc[i, iM2]                                    # M2-Hauptachse, CCW von Ost
        achse = (90.0 - psi) % 360
        konst = {}
        for j, k in enumerate(ks):
            q = math.radians(psi - inc[i, j])
            z = np.exp(-1j * math.radians(ph[i, j])) * (mj[i, j] * math.cos(q) - 1j * mn[i, j] * math.sin(q))
            konst[k] = (abs(z) * MS_KN, (-math.degrees(np.angle(z))) % 360)
        print('%-66s %.4f %.4f  Spring %.2f kn  M2 %.2f  Achse %3.0f  Fehler M2 %2.0f %%' %
              (name, la[i], lo[i], spring[i], konst['M2'][0], achse, 100 * err[i, iM2] / mj[i, iM2]))
        liste.append(('harmonics_utide_current_tables.txt', name))
        vorschau.append((name, '%.5f' % la[i], '%.5f' % lo[i], '%.2f' % spring[i], 'https://www.google.com/maps?q=%.5f,%.5f' % (la[i], lo[i])))
        staat = next((s for s in STAAT if s in name), '')
        B = ['# Harmonic constants from the AUSTEn national tidal model (CSIRO COMPAS, unstructured barotropic, 2017 run)',
             '# CSIRO_tidal_const_v12.nc face %d, depth-mean ellipses (t_tide, 364 days), projected on the M2 major axis' % i,
             '# AUSTEn National Tidal model data, doi:10.25919/q8dw-c732, CC BY-SA 4.0 (Hemer, Herzfeld, Griffin, Trenham)',
             '# Checked 19.11.2026 against 52 AUSTEn current meters: median vector error 32 % (FES2014 56 %), no time correction',
             '# M2 major-axis 95 %% error %.0f %%, model depth %.0f m' % (100 * err[i, iM2] / mj[i, iM2], float(A['Mesh2_depth'][i])),
             '# Major axis: %.1f deg true' % achse, '#',
             '# BEGIN HOT COMMENTS', '# country: Australia', '# source: AUSTEn tidal model (CSIRO), ellipse constants',
             '# station_id_context: AUSTEN-v12-face%d' % i, '# institution: CSIRO', '# datum: n/a', '# station_type: current',
             '# major_axis_deg_true: %.1f' % achse, '# confidence: 5',
             '# note: MODEL-DERIVED. Brennpunkt Spring %.1f kn, kein Satz in %.0f km, Oliver %s.' % (spring[i], ABSTAND, heute),
             '# !units: knots', '# !longitude: %.5f' % lo[i], '# !latitude: %.5f' % la[i],
             name, '+00:00 :UTC', '0.0000 knots']
        for k, _sp in CONSTITUENTS_175:
            c = konst.get(k)
            B.append('%-15s %.4f  %.2f' % (k, c[0], c[1]) if c and c[0] >= 0.00005 else 'x 0 0')
        bloecke.append('\n'.join(B))
    with open(os.path.join(ROOT, 'harmonics/help/austen_vorschlag_%s.csv' % heute), 'w', newline='', encoding='utf-8') as fh:
        w = csv.writer(fh)
        w.writerow(['name', 'lat', 'lon', 'spring_kn', 'google_maps'])
        w.writerows(vorschau)
    print('%d Saetze' % len(bloecke))
    if '--schreiben' in argv and bloecke:
        STROM = os.path.join(ROOT, 'harmonics/utide/harmonics_utide_current_tables.txt')
        T = open(STROM, encoding='iso-8859-1').read().rstrip('\n')
        schreiben(STROM, T + '\n' + '\n'.join(bloecke) + '\n')
        nl = os.path.join(ROOT, 'harmonics/help/neu_pruefen_%s.csv' % heute)
        with open(nl, 'a', newline='', encoding='utf-8') as fh:
            csv.writer(fh).writerows(liste)
        print('->', STROM)


if __name__ == '__main__':
    main(sys.argv[1:])
