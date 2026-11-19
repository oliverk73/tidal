#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SSW-RS: harmonischer Fit an allen Dreieckszellen + Eichung gegen Messsaetze (19.11.2026).

  fit JJJJMMTT JJJJMMTT   Kleinste Quadrate je Zelle (ua, va) -> UK_SSWRS/fit_<a>_<b>.npz
                          {k: komplexe Amplitude U, V in kn, c = a*e^{-ig}, Greenwich, mit Knotenfaktoren}
  fitjahr JJJJMMTT JJJJMMTT  dasselbe fuer lange Reihen (Normalgleichungen tageweise, 29 Tiden inkl. SA/SSA/K2/P1)
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


KS_JAHR = ['SA', 'SSA', 'MM', 'MSF', 'MF', 'Q1', 'O1', 'M1', 'P1', 'K1', 'J1', 'OO1', '2N2', 'MU2', 'N2', 'NU2', 'M2',
           'L2', 'T2', 'S2', 'K2', 'MN4', 'M4', 'MS4', 'MK4', 'S4', 'M6', 'MS6', 'M8']


def fit_jahr(a, b):
    """Wie fit(), aber tageweise Normalgleichungen aufsummiert (ein Jahr aller Zellen passt nicht in den Speicher)."""
    _n, sp, arg, fak = X.kopf_lesen(os.path.join(ROOT, 'harmonics/utide/harmonics_fes2022.txt'))
    ks = [k for k in KS_JAHR if k in sp]
    t0 = dt.datetime.strptime(a, '%Y%m%d').date()
    t1 = dt.datetime.strptime(b, '%Y%m%d').date()
    ATA = None
    n = 0
    for i in range((t1 - t0).days + 1):
        f = os.path.join(D, 'tage', (t0 + dt.timedelta(days=i)).strftime('%Y%m%d') + '.npz')
        if not os.path.exists(f):
            print('  fehlt', f)
            continue
        z = np.load(f)
        sek = np.round((MJD0 + z['zeit'].astype(float) * 86400.0) / 3600) * 3600
        Cm, Sm, _ = X.matrix(sek, ks, sp, arg, fak)
        A = np.column_stack([np.ones(len(sek))] + [c for j in range(len(ks)) for c in (Cm[:, j], Sm[:, j])])
        Y = {nm: np.nan_to_num((z[k] * z[k + '_skala'][0] + z[k + '_skala'][1]).astype(np.float64))
             for nm, k in (('U', 'ua'), ('V', 'va'))}
        if ATA is None:
            ATA = np.zeros((A.shape[1], A.shape[1]))
            ATY = {nm: np.zeros((A.shape[1], Y[nm].shape[1])) for nm in Y}
            YY = {nm: np.zeros(Y[nm].shape[1]) for nm in Y}
        ATA += A.T @ A
        for nm in Y:
            ATY[nm] += A.T @ Y[nm]
            YY[nm] += (Y[nm] ** 2).sum(axis=0)
        n += len(sek)
        if i % 30 == 0:
            print('  %s' % (t0 + dt.timedelta(days=i)), flush=True)
    Q = np.linalg.pinv(ATA)
    out, res = {}, {}
    for nm in ('U', 'V'):
        C = Q @ ATY[nm]
        rss = np.maximum(YY[nm] - (C * ATY[nm]).sum(axis=0), 0)
        res[nm] = np.sqrt(rss / n) * KN
        out[nm + '_z0'] = (C[0] * KN).astype(np.float32)
        for j, k in enumerate(ks):
            out['%s_%s' % (nm, k)] = ((C[1 + 2 * j] - 1j * C[2 + 2 * j]) * KN).astype(np.complex64)
    aus = os.path.join(D, 'fit_%s_%s.npz' % (a, b))
    np.savez_compressed(aus, ks=np.array(ks), rest_u=res['U'].astype(np.float32), rest_v=res['V'].astype(np.float32),
                        stunden=n, **out)
    print('%d Stunden -> %s' % (n, aus))


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
    vergleich = [k for k in ('M2', 'S2', 'N2', 'K2', 'K1', 'O1', 'P1', 'M4') if k in ks]
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


def saetze(fitdatei, pruefdatei, argv, schwelle=1.5, abstand_km=8.0):
    """Brennpunkte (Spring M2+S2 >= schwelle, kein Satz in abstand_km, je abstand_km der staerkste, nur GB/IE/IoM)
    -> Saetze in harmonics_utide_current_tables.txt. Zeit: Median-Versatz der Messsaetze bis 40 km (>= 5) wird
    herausgerechnet (SSW-RS lief im Januar-Test 6-18 min zu frueh). Ohne --schreiben nur Liste."""
    import json
    import health_check as H
    import strom_namen_vorort as SN
    from generate_germany_harmonics_175 import CONSTITUENTS_175
    from sicher_schreiben import schreiben
    from scipy.spatial import cKDTree
    _n, sp, arg, fak = X.kopf_lesen(os.path.join(ROOT, 'harmonics/utide/harmonics_fes2022.txt'))
    F = np.load(fitdatei)
    ks = [str(k) for k in F['ks']]
    g = np.load(os.path.join(D, 'gitter.npz'))
    la, lo = g['latc'].astype(float), ((g['lonc'].astype(float) + 180) % 360) - 180
    m2, ax = ellipse(F['U_M2'].astype(complex), F['V_M2'].astype(complex))
    s2, _ = ellipse(F['U_S2'].astype(complex), F['V_S2'].astype(complex))
    spring = m2 + s2
    x, y = lo * 111 * np.cos(np.radians(la)), la * 111
    R = [r for r in H.load_records() if r['current'] and r['lat'] is not None and 47 < r['lat'] < 63 and -14 < r['lon'] < 11]
    dS, _ = cKDTree(np.array([(r['lon'] * 111 * math.cos(math.radians(r['lat'])), r['lat'] * 111) for r in R])).query(np.column_stack([x, y]))
    alle = {r['name'] for r in H.load_records()}
    P = list(csv.DictReader(open(pruefdatei, encoding='utf-8')))
    L = json.load(open(SN.LM, encoding='utf-8'))
    L = [z for z in L if 48 < z[1] < 62 and -14 < z[2] < 3 and z[0] not in ('British Isles',)]   # GeoNames-Sammelpunkt in der Irischen See
    ERSETZ = {'East Float (North Wall Light 5 km S)': 'River Mersey (Pier Head)',     # East Float = Birkenhead-Dock
              'Pleaskin Head (Dunseverick Harbou)': 'Dunseverick (Pleaskin Head)'}    # GeoNames-Name abgeschnitten
    LAND = ('United Kingdom', 'Ireland', 'Isle of Man')
    kand = np.where((spring >= schwelle) & (dS >= abstand_km) & (la > 49.8) & (lo > -11) & (lo < 2.2))[0]
    kand = kand[np.argsort(-spring[kand])]
    raster, wahl = {}, []
    for i in kand:
        gx, gy = int(x[i] // abstand_km), int(y[i] // abstand_km)
        if any(math.hypot(x[i] - x[j], y[i] - y[j]) < abstand_km for a in (-1, 0, 1) for b in (-1, 0, 1)
               for j in raster.get((gx + a, gy + b), ())):
            continue
        raster.setdefault((gx, gy), []).append(i)
        wahl.append(i)
    bloecke, liste, heute = [], [], dt.date.today().strftime('%Y%m%d')
    vergeben, vorschau = set(), []
    for i in wahl:
        name = SN.vorschlag(la[i], lo[i], L)
        if name:
            name = re.sub(r'\s*\(historical\)', '', name)              # GeoNames 'North Wall Light (historical)'
        if not name:                                                  # naechste Landmarke bis 15 km
            nah = sorted((SN.km(la[i], lo[i], a, b), n, c, a, b, t) for n, a, b, c, t in L
                         if c in SN.PUNKT and abs(a - la[i]) < 0.2 and abs(b - lo[i]) < 0.4)
            if not nah or nah[0][0] > 15:
                print('  %.4f %.4f  %.1f kn  keine Landmarke bis 15 km' % (la[i], lo[i], spring[i]))
                continue
            d, n, c, a, b, t = nah[0]
            n = re.sub(r'\s*\(historical\)', '', n)
            n = re.sub(r'\s+(Lighthouse|Light Station|Light)$', '', n)
            name = '%s (%d km %s), %s Current' % (SN.latin1(n), max(1, round(d)), SN.richtung(la[i], lo[i], a, b), t)
        if not any(w in name for w in LAND):
            continue
        for a_, b_ in ERSETZ.items():
            name = name.replace(a_, b_)
        name = SN.auf_tcd_laenge(SN.latin1(name))                   # 'Hellabrick’s' -> ASCII-Apostroph
        if name in alle or name in vergeben:
            print('  %-60s Name schon vergeben' % name)
            continue
        vergeben.add(name)
        # Zeitversatz der Umgebung
        nb = [float(p['m2_zeit_min']) for p in P if km(la[i], lo[i], float(p['lat']), float(p['lon'])) <= 40]
        dtm = float(np.median(nb)) if len(nb) >= 5 else 0.0
        th = float(ax[i])
        sn, cs = math.sin(math.radians(th)), math.cos(math.radians(th))
        konst = {}
        for k in ks:
            c = complex(F['U_' + k][i]) * sn + complex(F['V_' + k][i]) * cs
            gph = (-math.degrees(cmath.phase(c)) - sp[k] * dtm / 60.0) % 360     # dtm < 0: Modell zu frueh -> spaeter legen
            konst[k] = (abs(c), gph)
        z0 = float(F['U_z0'][i]) * sn + float(F['V_z0'][i]) * cs
        rest = float(np.hypot(F['rest_u'][i], F['rest_v'][i]))
        print('%-62s %.4f %.4f  Spring %.2f kn  M2 %.2f  Achse %3.0f  Zeit %+.0f min (%d)  Rest %.2f' %
              (name, la[i], lo[i], spring[i], m2[i], th, -dtm, len(nb), rest))
        liste.append(('harmonics_utide_current_tables.txt', name))
        vorschau.append((name, '%.5f' % la[i], '%.5f' % lo[i], '%.2f' % spring[i], 'https://www.google.com/maps?q=%.5f,%.5f' % (la[i], lo[i])))
        B = ['# Harmonic constants derived from the Scottish Shelf Water Reanalysis Service (SSW-RS V3.02, FVCOM, NOC/Marine Directorate)',
             '# depth-mean ua/va at element %d (unstructured grid), hourly %s (py/sswrs.py, py/sswrs_fit.py)' % (i, os.path.basename(fitdatei)[4:-4]),
             '# Checked 19.11.2026 against measured current sets (median curve error ~10 %%, better than TPXO10 near coasts)',
             '# Time corrected by %+.0f min (median M2 offset of %d measured sets within 40 km)' % (-dtm, len(nb)),
             '# least squares, %d constituents, residual RMS %.2f kn' % (len(ks), rest),
             '# Major axis: %.1f deg true' % th, '#',
             '# BEGIN HOT COMMENTS', '# country: %s' % ('Ireland' if 'Ireland' in name and 'Northern' not in name else 'United Kingdom'),
             '# source: SSW-RS reanalysis model, harmonic fit', '# station_id_context: SSWRS-V3.02-ele%d' % i,
             '# institution: Scottish Government Marine Directorate / NOC', '# datum: n/a', '# station_type: current',
             '# major_axis_deg_true: %.1f' % th, '# confidence: 5',
             '# note: MODEL-DERIVED. Brennpunkt Spring %.1f kn, kein Satz in %d km, Oliver %s.' % (spring[i], abstand_km, heute),
             '# !units: knots', '# !longitude: %.5f' % lo[i], '# !latitude: %.5f' % la[i],
             name, '+00:00 :UTC', '%.4f knots' % z0]
        for k, _sp in CONSTITUENTS_175:
            c = konst.get(k)
            B.append('%-15s %.4f  %.2f' % (k, c[0], c[1]) if c and c[0] >= 0.00005 else 'x 0 0')
        bloecke.append('\n'.join(B))
    print('%d Brennpunkte, %d Saetze' % (len(wahl), len(bloecke)))
    with open(os.path.join(ROOT, 'harmonics/help/sswrs_vorschlag_%s.csv' % heute), 'w', newline='', encoding='utf-8') as fh:
        wr = csv.writer(fh)
        wr.writerow(['name', 'lat', 'lon', 'spring_kn', 'google_maps'])
        wr.writerows(vorschau)
    if '--schreiben' in argv and bloecke:
        STROM = os.path.join(ROOT, 'harmonics/utide/harmonics_utide_current_tables.txt')
        T = open(STROM, encoding='iso-8859-1').read().rstrip('\n')
        schreiben(STROM, T + '\n' + '\n'.join(bloecke) + '\n')
        nl = os.path.join(ROOT, 'harmonics/help/neu_pruefen_%s.csv' % heute)
        neu = not os.path.exists(nl)
        with open(nl, 'a', newline='', encoding='utf-8') as fh:
            wr = csv.writer(fh)
            if neu:
                wr.writerow(['datei', 'name'])
            wr.writerows(liste)
        print('->', os.path.relpath(STROM, ROOT), '+', os.path.relpath(nl, ROOT))


if __name__ == '__main__':
    if sys.argv[1:2] == ['saetze']:
        saetze(sys.argv[2], sys.argv[3], sys.argv[4:])
    elif sys.argv[1:2] == ['fit']:
        fit(sys.argv[2], sys.argv[3])
    elif sys.argv[1:2] == ['fitjahr']:
        fit_jahr(sys.argv[2], sys.argv[3])
    elif sys.argv[1:2] == ['pruefen']:
        pruefen(sys.argv[2])
    else:
        print(__doc__)
