#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Gezeitenstrom-Konstanten je Zelle aus den Stundenatlanten SHOM-2D und BSH fuer das Feinfeld (22.11.2026).

Beide Atlanten geben je Ort ein Stundenbild um das HW eines Bezugshafens fuer zwei Tidenstaerken (SHOM: Koeffizient
45/95 nach dem Brester Hub; BSH: Nipp/Spring nach dem Hub Helgoland). Die Atlasregel baut daraus eine Jahresreihe
(shom_atlas_stroemung.reihe, hafenatlas_stroeme.reihe_sn), die bisher Punkt fuer Punkt mit UTide gefittet wurde.

Die Reihe ist LINEAR in den Atlaswerten: u(t) = sum_j W[t, j] * Atlas[j] (j = Stunde x Tidenstaerke). Ebenso ist der
harmonische Fit linear: c = (G'G)^-1 G' u. Also c = M @ Atlas mit M = (G'G)^-1 G' W -- M einmal je Atlas/Bezugshafen,
dann alle Zellen in einer Matrixmultiplikation. Gleiche Regel wie die Einzelsaetze, gleiche Zeiten.

Ausgabe quellen/tidal_streams/feinfeld_atlanten.npz: je Atlas lat, lon, U_k/V_k (komplex, m/s, c = a e^{-ig},
Greenwich, Knotenfaktoren aus dem FES2022-Kopf wie tpxo_strom_karte), r2 (Anteil der Atlasreihe, den die Tiden
erklaeren). Feinere SHOM-Gitter als 250 m (Rade/Port de Brest) fallen weg: die Kartenebene rastert hoechstens 460 m.

Usage: venv/bin/python py/feinfeld_atlanten.py
"""
import datetime as dt
import glob
import math
import os
import sys

import numpy as np
from scipy import sparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shom_atlas_stroemung as S                                    # noqa: E402
import xtide_modell as X                                            # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUS = os.path.join(ROOT, 'quellen/tidal_streams/feinfeld_atlanten.npz')
KS = ('M2', 'S2', 'N2', 'K2', 'K1', 'O1', 'P1', 'Q1', 'M4', 'MS4', 'MN4')       # wie strom_feinfeld
FIT = list(KS) + ['2N2', 'MU2', 'NU2', 'L2', 'T2', 'LDA2', 'EPS2', 'MSN2', 'MK4', 'S4', 'SN4', 'M6', '2MS6', '2MN6',
                  'MSN6', 'M8', 'MSF', 'MM']
JAHR = 2026
RAND_KM = {'562': 10.0}        # abgeschnittener Randstreifen je SHOM-Atlas (km), sonst 3 km


def _nummer(pfad):
    import re
    m = re.search(r'-(5\d\d)-', os.path.basename(pfad))
    return m.group(1) if m else ''
KN = 0.514444


def _zeiten():
    t0 = dt.datetime(JAHR, 1, 1, tzinfo=dt.timezone.utc).timestamp()
    return t0, np.arange(t0, t0 + 365 * 86400, 600.0)


def _design():
    namen, speeds, arg, fak = X.kopf_lesen(os.path.join(ROOT, 'harmonics/utide/harmonics_fes2022.txt'))
    ks = [k for k in FIT if k in speeds]
    t0, ts = _zeiten()
    th = (ts - t0) / 3600.0
    sp = [np.ones_like(th)]
    for k in ks:
        E = np.radians(arg[JAHR][k] + speeds[k] * th)
        sp += [fak[JAHR][k] * np.cos(E), -fak[JAHR][k] * np.sin(E)]
    return ks, np.array(sp).T                                   # (nt, 1 + 2K)


_G = {}


def operator(tau, w, raster):
    """tau (nt) Zeit zum Bezugsereignis in Rasterwerten, w (nt) Gewicht des zweiten Bildes -> (ks, M), M: (1+2K, 2R).
    Spalten 0..R-1 = erstes Bild (Nipp/Koeff. 45), R..2R-1 = zweites (Spring/95)."""
    if not _G:
        ks, G = _design()
        _G.update(ks=ks, G=G, GtG=G.T @ G)
    G = _G['G']
    R = len(raster)
    tau = np.clip(tau, raster[0], raster[-1])
    i = np.clip(np.searchsorted(raster, tau, side='right') - 1, 0, R - 2)
    f = (tau - raster[i]) / (raster[i + 1] - raster[i])
    nt = len(tau)
    zeilen = np.repeat(np.arange(nt), 4)
    spalten = np.c_[i, i + 1, R + i, R + i + 1].ravel()
    werte = np.c_[(1 - f) * (1 - w), f * (1 - w), (1 - f) * w, f * w].ravel()
    W = sparse.csr_matrix((werte, (zeilen, spalten)), shape=(nt, 2 * R))
    GtW = (W.T @ G).T                                           # (1+2K, 2R)
    return _G['ks'], np.linalg.solve(_G['GtG'], GtW), W


def anwenden(ks, M, W, A):
    """A: (2R, n) Atlaswerte einer Komponente -> {k: komplex (n)}, Reihen-Varianz, Rest-Varianz.
    Varianzen ueber quadratische Formen (W'W, G'G klein), ohne die Reihe je Zelle zu bilden."""
    c = M @ A
    out = {k: (c[1 + 2 * j] + 1j * c[2 + 2 * j]).astype(np.complex64) for j, k in enumerate(ks) if k in KS}
    nt = W.shape[0]
    if _G.get('W') is not W:
        _G['W'], _G['Q'] = W, (np.asarray((W.T @ W).todense()), np.asarray(W.sum(0)).ravel() / nt)
    Q = _G['Q']
    qq = np.einsum('in,ij,jn->n', A, Q[0], A) / nt                # mittleres Quadrat der Reihe
    m = Q[1] @ A
    var = qq - m ** 2
    rest = qq - np.einsum('in,ij,jn->n', c, _G['GtG'], c) / nt
    return out, var, np.maximum(rest, 0)


def shom():
    tb, kb = S.koeffizient(JAHR)
    t0, ts = _zeiten()
    teile = []
    for f in sorted(glob.glob(os.path.join(ROOT, 'quellen/tidal_streams/SHOM_atlas/*/*/*.nc'))):
        if '-100M-' in f or '-30M-' in f:
            continue
        a = S.Atlas(f)
        pfad = S._hafen_finden(S.HAFEN[a.port][1])
        t = np.arange(t0 - 86400, t0 + 366 * 86400, 120.0)
        h = S.gezeit(pfad, S.HAFEN[a.port][1], t)
        tp, _ = S.scheitel(t, h, not a.bm)
        kp = np.interp(tp, tb, kb)
        k = np.clip(np.searchsorted(tp, ts), 1, len(tp) - 1)
        k -= (ts - tp[k - 1]) < (tp[k] - ts)
        tau = (ts - tp[k]) / 60.0
        w = (kp[k] - a.coeff[0]) / (a.coeff[1] - a.coeff[0])
        ks, M, W = operator(tau, w, a.tau)
        U = np.ma.filled(a.d['U'][:, :, 0].astype(float), np.nan)        # (2, R, ny, nx)
        V = np.ma.filled(a.d['V'][:, :, 0].astype(float), np.nan)
        R = U.shape[1]
        U = U.reshape(2 * R, -1)
        V = V.reshape(2 * R, -1)
        ok = np.isfinite(U).all(0) & np.isfinite(V).all(0) & (U > -999).all(0) & (V > -999).all(0)
        LA, LO = np.meshgrid(a.lat, a.lon, indexing='ij')
        # Offener Modellrand: Randzellen weichen stark ab (Golfe normand-breton 562 bei 49,6 N / 3,5 W: Querstrom
        # 0,62 kn/162 Grad gegen 0,2 kn/195 Grad bei SSW-RS, Manche- und Abers-Atlas; P90 der Vektorabweichung zu
        # SSW-RS 123 % in 0-2 km, 59 % in 10-20 km, 37 % ab 20 km) -> Randstreifen weg, dort uebernimmt der Nachbar.
        km_rand = np.minimum.reduce([(LA - a.lat.min()) * 111.2, (a.lat.max() - LA) * 111.2,
                                     (LO - a.lon.min()) * 111.2 * np.cos(np.radians(LA)),
                                     (a.lon.max() - LO) * 111.2 * np.cos(np.radians(LA))]).ravel()
        if '-250M-' not in f:      # 250-m-Gitter liegen im 500-m-Gitter desselben Laufs, dessen Rand ist der Rand
            ok &= km_rand >= RAND_KM.get(_nummer(f), 3.0)
        res = _stuecke(ks, M, W, U[:, ok], V[:, ok])
        name = 'SHOM-' + os.path.basename(f).split('_R11')[1][6:].rsplit('-', 1)[0]
        teile.append((name, LA.ravel()[ok], LO.ravel()[ok], res))
        print('%-28s %-11s %6d Zellen  r2 Median %.3f  M2 max %.2f m/s' % (
            name, a.port, ok.sum(), np.median(res['r2']), np.abs(res['U']['M2']).max()), flush=True)
    return teile


def _stuecke(ks, M, W, U, V, block=4000):
    out = {'U': {k: [] for k in KS}, 'V': {k: [] for k in KS}, 'r2': []}
    for s in range(0, U.shape[1], block):
        cu, vu, ru = anwenden(ks, M, W, U[:, s:s + block])
        cv, vv, rv = anwenden(ks, M, W, V[:, s:s + block])
        for k in KS:
            z = np.zeros(cu[next(iter(cu))].shape, np.complex64)
            out['U'][k].append(cu.get(k, z))
            out['V'][k].append(cv.get(k, z))
        out['r2'].append(1 - (ru + rv) / np.maximum(vu + vv, 1e-12))
    return {'U': {k: np.concatenate(v) for k, v in out['U'].items()},
            'V': {k: np.concatenate(v) for k, v in out['V'].items()}, 'r2': np.concatenate(out['r2'])}


def bsh():
    import bsh_gezeitenstrom as B
    _z0, w_, _e, _m = X.satz_lesen(B.HAFEN[1], B.HAFEN[0])
    hs, hn = 2 * (w_['M2'][0] + w_['S2'][0]), 2 * (w_['M2'][0] - w_['S2'][0])
    t0, ts = _zeiten()
    t = np.arange(t0 - 86400, t0 + 367 * 86400, 120.0)
    h = S.gezeit(B.HAFEN[1], B.HAFEN[0], t)
    thw, hhw = S.scheitel(t, h, True)
    tnw, hnw = S.scheitel(t, h, False)
    hub = hhw - np.interp(thw, tnw, hnw)
    k = np.clip(np.searchsorted(thw, ts), 1, len(thw) - 1)
    k -= (ts - thw[k - 1]) < (thw[k] - ts)
    tau = (ts - thw[k]) / 3600.0
    w = np.clip((hub[k] - hn) / (hs - hn), -0.5, 1.5)
    ks, M, W = operator(tau, w, np.array(B.STUNDEN, float))
    teile = []
    for teil, (lon, lat, Sp, Ni) in B.laden().items():
        def vec(A):
            r = np.radians(A[..., 1])
            return A[..., 0] * np.sin(r) * KN, A[..., 0] * np.cos(r) * KN
        su, sv = vec(Sp)
        nu, nv = vec(Ni)
        U = np.concatenate([nu, su])                             # (26, n): erst Nipp, dann Spring
        V = np.concatenate([nv, sv])
        ok = np.isfinite(U).all(0) & np.isfinite(V).all(0)
        # Westliche Ostsee/Belte (oestlich der Landbruecke Juetland-Holstein) raus: kaum Gezeit, Bezug HW Helgoland
        # traegt nicht; an Lillebaelt/Storebaelt/Hatter Barn/Spodsbjerg schlechter als TPXO (22.11.2026)
        ok &= ~((lon > 9.6) & (lat > 54.2))
        res = _stuecke(ks, M, W, U[:, ok], V[:, ok])
        teile.append(('BSH-' + teil, lat[ok], lon[ok], res))
        print('%-28s %-11s %6d Zellen  r2 Median %.3f  M2 max %.2f m/s' % (
            'BSH-' + teil, 'Helgoland', ok.sum(), np.median(res['r2']), np.abs(res['U']['M2']).max()), flush=True)
    return teile


def probe(teile):
    """Gegenprobe an den Einzelsaetzen, die aus denselben Atlanten per UTide entstanden: Feld (naechste Zelle) gegen
    Satz, M2-Vektor entlang der Satzachse."""
    import cmath
    import health_check as H
    _n, speeds, _a, _f = X.kopf_lesen(os.path.join(ROOT, 'harmonics/utide/harmonics_fes2022.txt'))
    R = [r for r in H.load_records() if r['current'] and r['lat'] is not None and 'current_tables' in r['file']]
    for name, la, lo, res in teile:
        q = 'SHOM' if name.startswith('SHOM') else 'BSH'
        e = []
        for r in R:
            txt = r.get('source') or ''
            if q not in txt and not (q == 'SHOM' and 'Shom' in txt) and not (q == 'BSH' and 'BSH' in txt):
                continue
            d = 111.2 * np.hypot(la - r['lat'], (lo - r['lon']) * math.cos(math.radians(r['lat'])))
            i = int(np.argmin(d))
            if d[i] > 0.3:
                continue
            _z, w, _e, mer = X.satz_lesen(r['file'], r['name'])
            if 'M2' not in w:
                continue
            ax = r.get('axis')
            s = cmath.rect(w['M2'][0] * KN, -math.radians(X.greenwich(w['M2'][1], speeds['M2'], mer)))
            if ax is None:
                continue
            a = res['U']['M2'][i] * math.sin(math.radians(ax)) + res['V']['M2'][i] * math.cos(math.radians(ax))
            e.append(100 * abs(a - s) / abs(s))
        if e:
            print('  Probe %-24s %3d Saetze: M2-Vektorfehler Median %.1f %%, max %.0f %%' % (name, len(e), np.median(e), max(e)))


def shom3d():
    """SHOM "Courants de maree 3D" Loire (Saint-Nazaire, bis Quiberon/Morbihan) und Fromveur (Brest), Oberflaeche
    (23.11.2026). Gleiche Atlasregel wie shom(); Leser py/shom_3d_stroemung.Atlas3D. Der 2D-Atlas 565 hat dort nur
    2 km und im Golfe du Morbihan keine Zelle."""
    import shom_3d_stroemung as S3
    tb, kb = S.koeffizient(JAHR)
    t0, ts = _zeiten()
    teile = []
    for nm in ('loire', 'fromveur'):
        a = S3.Atlas3D(nm)
        pfad = S._hafen_finden(S.HAFEN[a.port][1])
        t = np.arange(t0 - 86400, t0 + 366 * 86400, 120.0)
        h = S.gezeit(pfad, S.HAFEN[a.port][1], t)
        tp, _ = S.scheitel(t, h, not a.bm)
        kp = np.interp(tp, tb, kb)
        k = np.clip(np.searchsorted(tp, ts), 1, len(tp) - 1)
        k -= (ts - tp[k - 1]) < (tp[k] - ts)
        tau = (ts - tp[k]) / 60.0
        w = (kp[k] - a.coeff[0]) / (a.coeff[1] - a.coeff[0])
        ks, M, W = operator(tau, w, a.tau)
        R = len(a.tau)
        U = a.U.transpose(1, 2, 0).reshape(2 * R, -1)               # (n, 2, R) -> (2R, n), erst ME dann VE
        V = a.V.transpose(1, 2, 0).reshape(2 * R, -1)
        ok = np.isfinite(U).all(0) & np.isfinite(V).all(0)
        res = _stuecke(ks, M, W, U[:, ok], V[:, ok])
        name = 'SHOM3D-' + nm.upper()
        teile.append((name, a.lat[ok], a.lon[ok], res))
        print('%-28s %-11s %6d Zellen  r2 Median %.3f  M2 max %.2f m/s' % (
            name, a.port, ok.sum(), np.median(res['r2']), np.abs(res['U']['M2']).max()), flush=True)
    return teile


def main():
    teile = shom() + bsh() + shom3d()
    out = {}
    for q, (name, la, lo, res) in enumerate(teile):
        out['n%d' % q] = np.array(name)
        out['lat%d' % q] = la.astype(np.float32)
        out['lon%d' % q] = lo.astype(np.float32)
        out['r2_%d' % q] = res['r2'].astype(np.float32)
        for k in KS:
            out['U_%s_%d' % (k, q)] = res['U'][k]
            out['V_%s_%d' % (k, q)] = res['V'][k]
    out['anzahl'] = np.array(len(teile))
    np.savez(AUS, **out)
    print('->', AUS, '%.0f MB' % (os.path.getsize(AUS) / 1e6))
    return teile


def laden():
    """-> [(name, lat, lon, {k: (U, V)})] fuer strom_feinfeld.bauen."""
    F = np.load(AUS)
    return [(str(F['n%d' % q]), F['lat%d' % q].astype(float), F['lon%d' % q].astype(float),
             {k: (F['U_%s_%d' % (k, q)], F['V_%s_%d' % (k, q)]) for k in KS}) for q in range(int(F['anzahl']))]


if __name__ == '__main__':
    main()
