#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SSW-RS: harmonischer Fit an allen Dreieckszellen + Eichung gegen Messsaetze (19.11.2026).

  fit JJJJMMTT JJJJMMTT   Kleinste Quadrate je Zelle (ua, va) -> UK_SSWRS/fit_<a>_<b>.npz
                          {k: komplexe Amplitude U, V in kn, c = a*e^{-ig}, Greenwich, mit Knotenfaktoren}
  pruefen <fitdatei>      gegen die Messsaetze im Gebiet (current_observations, Hauptachse im Kopf):
                          Kurvenfehler wie fes2014_strom.kurve (Vorzeichen frei + Vorzeichen), Faktor/Zeit M2,
                          dazu TPXO10 an derselben Stelle -> harmonics/help/sswrs_pruefung_<datum>.csv
"""
import cmath
import csv
import datetime as dt
import glob
import math
import os
import re
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import xtide_modell as X                                              # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(ROOT, 'quellen/tidal_streams/UK_SSWRS')
KS_MONAT = ['M2', 'S2', 'N2', 'K1', 'O1', 'M4', 'MS4', 'M6', 'Q1', 'MN4', '2N2', 'L2']
KN = 1.0 / 0.514444
MJD0 = dt.datetime(1858, 11, 17, tzinfo=dt.timezone.utc).timestamp()


def reihe(a, b):
    t0 = dt.datetime.strptime(a, '%Y%m%d').date()
    t1 = dt.datetime.strptime(b, '%Y%m%d').date()
    sek, U, V = [], [], []
    for i in range((t1 - t0).days + 1):
        f = os.path.join(D, 'tage', (t0 + dt.timedelta(days=i)).strftime('%Y%m%d') + '.npz')
        if not os.path.exists(f):
            print('  fehlt', f)
            continue
        z = np.load(f)
        sek.append(MJD0 + z['zeit'].astype(float) * 86400.0)
        U.append((z['ua'] * z['ua_skala'][0] + z['ua_skala'][1]).astype(np.float32))
        V.append((z['va'] * z['va_skala'][0] + z['va_skala'][1]).astype(np.float32))
    return np.concatenate(sek), np.concatenate(U), np.concatenate(V)


def fit(a, b):
    _n, sp, arg, fak = X.kopf_lesen(os.path.join(ROOT, 'harmonics/utide/harmonics_fes2022.txt'))
    sek, U, V = reihe(a, b)
    sek = np.round(sek / 3600) * 3600          # Zeit ist float32-Tage (~5 min ungenau), Ausgabe stuendlich
    print('%d Stunden, %s .. %s' % (len(sek), dt.datetime.fromtimestamp(sek[0], dt.timezone.utc),
                                    dt.datetime.fromtimestamp(sek[-1], dt.timezone.utc)), flush=True)
    ks = [k for k in KS_MONAT if k in sp]
    Cm, Sm, _ = X.matrix(sek, ks, sp, arg, fak)
    A = np.column_stack([np.ones(len(sek))] + [c for j in range(len(ks)) for c in (Cm[:, j], Sm[:, j])])
    P = np.linalg.pinv(A).astype(np.float32)
    out = {}
    res = {}
    for nm, Y in (('U', U), ('V', V)):
        Y = np.nan_to_num(Y)
        C = P @ Y                                                     # (1+2k) x Zellen
        res[nm] = np.sqrt(np.mean((Y - A.astype(np.float32) @ C) ** 2, axis=0)) * KN
        out[nm + '_z0'] = C[0] * KN
        for j, k in enumerate(ks):
            out['%s_%s' % (nm, k)] = ((C[1 + 2 * j] - 1j * C[2 + 2 * j]) * KN).astype(np.complex64)
    aus = os.path.join(D, 'fit_%s_%s.npz' % (a, b))
    np.savez_compressed(aus, ks=np.array(ks), rest_u=res['U'], rest_v=res['V'], **out)
    print('->', aus)


def ellipse(Uc, Vc):
    wp, wm = (Uc + 1j * Vc) / 2, (Uc - 1j * Vc) / 2
    sema = np.abs(wp) + np.abs(wm)
    ach = (90 - np.degrees((np.angle(wp) + np.angle(np.conj(wm))) / 2)) % 180
    return sema, ach


def km(a, b, c, d):
    return 6371 * np.hypot(np.radians(c - a), np.radians(((d - b + 180) % 360) - 180) * np.cos(np.radians(a)))


def pruefen(fitdatei):
    import health_check as H
    import tpxo_strom as T
    from scipy.spatial import cKDTree
    F = np.load(fitdatei)
    ks = [str(k) for k in F['ks']]
    g = np.load(os.path.join(D, 'gitter.npz'))
    la, lo = g['latc'].astype(float), ((g['lonc'].astype(float) + 180) % 360) - 180
    baum = cKDTree(np.column_stack([la, lo * np.cos(np.radians(57))]))
    _n, sp, arg, fak = X.kopf_lesen(os.path.join(ROOT, 'harmonics/utide/harmonics_fes2022.txt'))
    vergleich = [k for k in ('M2', 'S2', 'N2', 'K1', 'O1', 'M4') if k in ks]
    R = [r for r in H.load_records() if r['current'] and r['lat'] is not None and 'current_observations' in r['file']
         and 48.5 < r['lat'] < 61.5 and -12 < r['lon'] < 9]
    zeilen = []
    texte = {}
    for r in R:
        p = r['file'] if r['file'].startswith('/') else os.path.join(ROOT, r['file'])
        if p not in texte:
            texte[p] = open(p, encoding='iso-8859-1').read().split('\n')
        L = texte[p]
        i = L.index(r['name'])
        a = i
        while a > 0 and L[a - 1].startswith('#'):
            a -= 1
        kopf = '\n'.join(L[a:i])
        m = re.findall(r'major_axis_deg_true: ([\d.]+)', kopf)
        if not m:
            continue
        ax = float(m[-1])
        d, j = baum.query([r['lat'], r['lon'] * math.cos(math.radians(57))])
        dk = float(km(r['lat'], r['lon'], la[j], lo[j]))
        if dk > 3:
            continue
        _z0, w, _e, mer = X.satz_lesen(p, r['name'])
        s = {k: cmath.rect(w[k][0], -math.radians(X.greenwich(w[k][1], sp[k], mer))) for k in vergleich if k in w and w[k][0] > 0}
        if 'M2' not in s or abs(s['M2']) < 0.2:
            continue
        sn, cs = math.sin(math.radians(ax)), math.cos(math.radians(ax))
        pm = {k: complex(F['U_' + k][j]) * sn + complex(F['V_' + k][j]) * cs for k in s}
        tot = sum(abs(v) for v in s.values())
        fe = [100 * math.sqrt(sum(abs(pm[k] - vz * s[k]) ** 2 for k in s) / 2) / max(0.1, tot) for vz in (1, -1)]
        vz = 1 if fe[0] <= fe[1] else -1
        tz = T.wasserzelle(r['lat'], r['lon'])
        ft = None
        if tz:
            pt = T.projektion(tz[0], tz[1], ax, list(s))
            ft = min(100 * math.sqrt(sum(abs(pt[k] - v * s[k]) ** 2 for k in s) / 2) / max(0.1, tot) for v in (1, -1))
        dphi = math.degrees(cmath.phase(pm['M2'] / (vz * s['M2'])))
        zeilen.append(dict(name=r['name'], lat=r['lat'], lon=r['lon'], zelle_km=round(dk, 2), m2_mess=round(abs(s['M2']), 2),
                           sswrs_pct=round(min(fe), 1), vorzeichen=vz, tpxo_pct=round(ft, 1) if ft is not None else '',
                           m2_faktor=round(abs(pm['M2']) / abs(s['M2']), 2), m2_zeit_min=round(-dphi / 28.984 * 60)))
    aus = os.path.join(ROOT, 'harmonics/help/sswrs_pruefung_%s.csv' % dt.date.today().strftime('%Y%m%d'))
    with open(aus, 'w', newline='', encoding='utf-8') as fh:
        wr = csv.DictWriter(fh, fieldnames=list(zeilen[0]))
        wr.writeheader()
        wr.writerows(zeilen)
    e = np.array([z['sswrs_pct'] for z in zeilen])
    t = np.array([z['tpxo_pct'] for z in zeilen if z['tpxo_pct'] != ''])
    f = np.array([z['m2_faktor'] for z in zeilen])
    zt = np.array([z['m2_zeit_min'] for z in zeilen])
    print('%d Messsaetze (Zelle <= 3 km, M2 >= 0,2 kn): SSW-RS Median %.1f %% (P75 %.1f), TPXO10 Median %.1f %%; '
          'M2-Faktor Median %.2f, Zeit Median %+.0f min, Vorzeichen -1: %d'
          % (len(e), np.median(e), np.percentile(e, 75), np.median(t), np.median(f), np.median(zt),
             sum(z['vorzeichen'] == -1 for z in zeilen)))
    print('->', aus)


if __name__ == '__main__':
    if sys.argv[1:2] == ['fit']:
        fit(sys.argv[2], sys.argv[3])
    elif sys.argv[1:2] == ['pruefen']:
        pruefen(sys.argv[2])
    else:
        print(__doc__)
