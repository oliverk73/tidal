#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Stromsaetze aus WebTide Upper Fundy (DFO/BIO, Finite Elemente, 74934 Knoten, 10 Tiden), Oliver 21.11.2026.

Quelle: quellen/tidal_streams/Canada_WebTide/flood/ (aus dem install4j-Paket WebTide_upper_fundy_data_0_7.sh, Webarchiv
2017; WebTide-Seiten des BIO seit 2026 offline). Je Knoten und Tide u/v-Amplitude (m/s) und Phase (Grad, Greenwich).
Probe 21.11.: Wasserstand M2 an 10 Pegeln 1-6 %, 0-5 Grad; Strom Minas Passage gegen FORCE-Messung x1,05 / -5 Grad.
Das grobe Scotia-Fundy-Maine-Netz taugt fuer Stroeme nicht (enge Durchfahrten 3-25 % der Messung) -> nicht genutzt.

Brennpunkte wie bei SSW-RS (py/sswrs_fit.py): Spring (M2 + S2 Hauptachse) >= SCHWELLE kn, kein Stromsatz in
ABSTAND km, je ABSTAND-km-Feld der staerkste Knoten, Knoten im Wasser (Tiefe > 0) und >= 150 m vor der OSM-Kueste.
Satz: Hauptachse der M2-Ellipse, jede Tide auf die Achse projiziert (Amplitude kn, Phase Greenwich), Z0 = 0.

Usage: venv/bin/python py/webtide_strom.py [--schreiben]
"""
import cmath
import csv
import datetime as dt
import math
import os
import re
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
W = os.path.join(ROOT, 'quellen/tidal_streams/Canada_WebTide/flood')
ZIEL = os.path.join(ROOT, 'harmonics/utide/harmonics_utide_current_tables.txt')
KS = ('M2', 'S2', 'N2', 'K2', 'K1', 'O1', 'L2', 'M4', 'NU2', '2N2')
KN = 1.943844
SCHWELLE, ABSTAND = 1.5, 8.0


def laden():
    nod = np.loadtxt(os.path.join(W, 'flood_ll.nod'))
    bat = np.loadtxt(os.path.join(W, 'flood.bat'))
    uv = {}
    for k in KS:
        v = np.loadtxt(os.path.join(W, '%s.barotropic.v2c' % k), skiprows=3)
        uv[k] = (v[:, 1] * np.exp(-1j * np.radians(v[:, 2])), v[:, 3] * np.exp(-1j * np.radians(v[:, 4])))
    return nod[:, 2], nod[:, 1], bat[:, 1], uv


def achse(U, V):
    """Hauptachse (Grad, 0-180) und Amplitude der Ellipse fuer komplexe u/v-Amplituden (Vektoren)."""
    th = np.radians(np.arange(0, 180, 1.0))
    c = np.abs(U[:, None] * np.sin(th)[None] + V[:, None] * np.cos(th)[None])
    j = np.argmax(c, axis=1)
    return np.degrees(th[j]), c[np.arange(len(U)), j]


def konstanten(uv, i, th):
    sn, cs = math.sin(math.radians(th)), math.cos(math.radians(th))
    out = {}
    for k in KS:
        c = complex(uv[k][0][i]) * sn + complex(uv[k][1][i]) * cs
        out[k] = (abs(c) * KN, (-math.degrees(cmath.phase(c))) % 360)
    return out


def rohreihe(text, name, la, lo):
    """Fuer strom_ellipsen_eigen (Kompass): u, v (m/s) stuendlich 2026 aus den 10 Tiden des naechsten Knotens."""
    import pandas as pd
    import xtide_modell as X
    m = re.search(r'WEBTIDE-UPPER-FUNDY-n(\d+)', text)
    if not m:
        return None
    i = int(m.group(1))
    _la, _lo, _b, uv = laden()
    namen, speeds, arg, fak = X.kopf_lesen(os.path.join(ROOT, 'harmonics/utide/harmonics_fes2022.txt'))
    t0 = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc).timestamp()
    ts = t0 + 3600.0 * np.arange(365 * 24)
    ks = [k for k in KS if k in speeds]
    C, S, _w = X.matrix(ts, ks, speeds, arg, fak)
    u = sum((C[:, j] * uv[k][0][i].real - S[:, j] * uv[k][0][i].imag) for j, k in enumerate(ks))
    v = sum((C[:, j] * uv[k][1][i].real - S[:, j] * uv[k][1][i].imag) for j, k in enumerate(ks))
    return pd.DataFrame({'u': u, 'v': v}, index=pd.to_datetime(ts, unit='s'))


def main(argv):
    import health_check as H
    import osm_land
    import strom_namen_vorort as SN
    from generate_germany_harmonics_175 import CONSTITUENTS_175
    from scipy.spatial import cKDTree
    la, lo, tief, uv = laden()
    th, m2 = achse(uv['M2'][0], uv['M2'][1])
    _t2, s2 = achse(uv['S2'][0], uv['S2'][1])
    spring = (m2 + s2) * KN
    R = [r for r in H.load_records() if r['current'] and r['lat'] is not None and 43 < r['lat'] < 47 and -68 < r['lon'] < -62]
    kx = lambda a, b: np.c_[a * 111.2, b * 111.2 * math.cos(math.radians(45.3))]   # noqa: E731
    dS, _ = cKDTree(kx(np.array([r['lat'] for r in R]), np.array([r['lon'] for r in R]))).query(kx(la, lo))
    kand = np.where((spring >= SCHWELLE) & (tief > 0) & (dS >= ABSTAND))[0]
    kand = kand[np.argsort(-spring[kand])]
    L = osm_land.Land([(la[i], lo[i]) for i in kand[:400]])
    wahl, raster = [], set()
    for i in kand:
        z = (int(la[i] * 111.2 // ABSTAND), int(lo[i] * 111.2 * 0.703 // ABSTAND))
        if z in raster or any(math.hypot((la[i] - la[j]) * 111.2, (lo[i] - lo[j]) * 78.2) < ABSTAND for j in wahl):
            continue
        if L.ist_land(la[i], lo[i]) or L.kueste_km(la[i], lo[i], rmax=2) < 0.15:
            continue
        raster.add(z)
        wahl.append(i)
    SN.landmarken([], punkte=[(float(la[i]), float(lo[i])) for i in wahl])
    import json
    Lg = json.load(open(SN.LM, encoding='utf-8'))
    Lg = [z for z in Lg if 43 < z[1] < 47.5 and -68 < z[2] < -62 and '(historical)' not in z[0]]
    alle = {r['name'] for r in H.load_records()}
    heute = dt.date.today().strftime('%Y%m%d')
    bloecke, namen = [], []
    for i in wahl:
        name = SN.vorschlag(float(la[i]), float(lo[i]), Lg)
        if not name:
            nah = sorted((SN.km(la[i], lo[i], a, b), n, a, b, t) for n, a, b, c, t in Lg if c in SN.PUNKT)
            d, n, a, b, t = nah[0]
            n = re.sub(r'\s+(Lighthouse|Light Station|Light)$', '', n)
            name = '%s (%d km %s), %s Current' % (SN.latin1(n), max(1, round(d)), SN.richtung(la[i], lo[i], a, b), t)
        name = SN.auf_tcd_laenge(SN.latin1(name))
        if 'Canada' not in name:
            name = name.replace(' Current', ', Canada Current') if not name.endswith('Canada Current') else name
        if name in alle or name in namen:
            print('  %-60s Name schon vergeben, uebersprungen' % name)
            continue
        k = konstanten(uv, i, float(th[i]))
        print('%-64s %.4f %.4f  Spring %.1f kn  M2 %.2f  Achse %3.0f' % (name[:64], la[i], lo[i], spring[i], k['M2'][0], th[i]))
        namen.append(name)
        B = ['# Harmonic constants from WebTide Upper Fundy (Fisheries and Oceans Canada, Bedford Institute of Oceanography),',
             '# finite element barotropic tidal model, node %d (depth %.0f m); constituents projected on the M2 major axis.' % (i, tief[i]),
             '# Checked 21.11.2026: water level M2 at 10 gauges within 1-6 %, current Minas Passage vs FORCE x1.05 / -5 deg.',
             '# Major axis: %.1f deg true' % th[i], '#', '# BEGIN HOT COMMENTS', '# country: Canada',
             '# source: WebTide Upper Fundy model (DFO/BIO), harmonic constants', '# station_id_context: WEBTIDE-UPPER-FUNDY-n%d' % i,
             '# institution: Fisheries and Oceans Canada', '# datum: n/a', '# station_type: current',
             '# major_axis_deg_true: %.1f' % th[i], '# confidence: 6',
             '# note: MODEL-DERIVED. Brennpunkt Spring %.1f kn, kein Satz in %d km, Oliver %s.' % (spring[i], ABSTAND, heute),
             '# !units: knots', '# !longitude: %.5f' % lo[i], '# !latitude: %.5f' % la[i], name, '+00:00 :UTC', '0.0000 knots']
        for c_, _sp in CONSTITUENTS_175:
            a_ = k.get(c_)
            B.append('%-15s %.4f  %.2f' % (c_, a_[0], a_[1]) if a_ and a_[0] >= 0.00005 else 'x 0 0')
        bloecke.append('\n'.join(B))
    print('%d Saetze' % len(bloecke))
    if '--schreiben' in argv and bloecke:
        from sicher_schreiben import schreiben
        T = open(ZIEL, encoding='iso-8859-1').read().rstrip('\n')
        schreiben(ZIEL, T + '\n' + '\n'.join(bloecke) + '\n')
        p = os.path.join(ROOT, 'harmonics/help/neu_pruefen_%s.csv' % heute)
        neu = not os.path.exists(p)
        with open(p, 'a', newline='', encoding='utf-8') as fh:
            w = csv.writer(fh)
            if neu:
                w.writerow(['datei', 'name'])
            for n in namen:
                w.writerow([os.path.basename(ZIEL), n])
        print('->', os.path.relpath(ZIEL, ROOT))


if __name__ == '__main__':
    main(sys.argv[1:])
