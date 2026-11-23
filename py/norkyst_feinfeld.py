#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""NorKyst800-Gezeitenstrom je Zelle fuer das Feinfeld (22.11.2026).

Bisher gab es von NorKyst nur Punktreihen (py/norkyst_strom.py). Hier: alle Wasserzellen mit Springstrom >= 0,5 kn
(springamplitude.npy vom 15.11.) plus 6 Zellen Saum, nordlich 57,9 N, als Bloecke 32x32 tageweise von THREDDS
(ubar/vbar, tiefengemittelt, mit angle nach Ost/Nord gedreht). Die Rohreihen werden NICHT gespeichert: der
harmonische Fit ist linear, c = (G'G)^-1 G'u, und G ist fuer alle Zellen gleich (gleiche Stunden). Je Tag werden nur
G'u, G'v, Summe u, Summe u^2 (fuer r2) aufaddiert -> Zwischenstand akku.npz, fortsetzbar.

Reihe < 6 Monate -> K2 an S2 (0,2723) und P1 an K1 (0,3309) gekoppelt (Gleichgewichtsverhaeltnis, gleiche Phase),
wie bei den kurzen Strom-Messreihen. Knotenfaktoren/Argumente aus dem FES2022-Kopf (xtide_modell.kopf_lesen), damit
die Konstanten genau wie die uebrigen Feinfeld-Quellen gelten (c = a e^{-ig}, Greenwich, m/s).

Server bittet um keine parallelen Sitzungen -> streng nacheinander.

  laden VON BIS     -> quellen/tidal_streams/Norway_NorKyst800/feinfeld_akku.npz
  fit               -> quellen/tidal_streams/Norway_NorKyst800/feinfeld_norkyst.npz (lat, lon, U_k, V_k, r2)
"""
import datetime as dt
import os
import sys
import time

import netCDF4 as nc
import numpy as np
from scipy import ndimage

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import xtide_modell as X                                            # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(ROOT, 'quellen/tidal_streams/Norway_NorKyst800')
AKKU = os.path.join(D, 'feinfeld_akku.npz')
AUS = os.path.join(D, 'feinfeld_norkyst.npz')
URL = 'https://thredds.met.no/thredds/dodsC/fou-hi/norkyst800m-1h/NorKyst-800m_ZDEPTHS_his.an.%s00.nc'
KS = ('M2', 'S2', 'N2', 'K2', 'K1', 'O1', 'P1', 'Q1', 'M4', 'MS4', 'MN4')       # wie strom_feinfeld
FREI = ['M2', 'S2', 'N2', 'K1', 'O1', 'Q1', 'M4', 'MS4', 'MN4', '2N2', 'MU2', 'L2', 'M6', 'MK3', 'M3', 'MSF']
KOPPEL = {'K2': ('S2', 0.2723), 'P1': ('K1', 0.3309)}
B = 32
_K = {}


def auswahl():
    g = np.load(os.path.join(D, 'gitter.npz'))
    a = np.load(os.path.join(D, 'springamplitude.npy'))
    wasser = ~g['mask']
    sel = (a >= 0.5) & wasser & (g['lat'] >= 57.9) & (g['lon'] < 31)
    sel = ndimage.binary_dilation(sel, iterations=6) & wasser
    # Laeufe: je Blockzeile zusammenhaengende Bloecke (Luecke <= 2 Bloecke) in EINER Abfrage
    J, I = sel.shape
    laeufe = []
    for j0 in range(0, J, B):
        bl = [i0 for i0 in range(0, I, B) if sel[j0:j0 + B, i0:i0 + B].any()]
        lauf = None
        for i0 in bl:
            if lauf and i0 - lauf[1] <= 2 * B:
                lauf[1] = i0 + B
            else:
                if lauf:
                    laeufe.append((j0, min(j0 + B, J), lauf[0], min(lauf[1], I)))
                lauf = [i0, i0 + B]
        if lauf:
            laeufe.append((j0, min(j0 + B, J), lauf[0], min(lauf[1], I)))
    return g, sel, laeufe


def _kopf():
    if not _K:
        _K.update(zip(('namen', 'speeds', 'arg', 'fak'),
                      X.kopf_lesen(os.path.join(ROOT, 'harmonics/utide/harmonics_fes2022.txt'))))
    return _K


def design(ts):
    """ts: Unix-Sekunden -> (nt, P) mit Spalten 1, je Tide cos/-sin (gekoppelte Tiden in ihrer Haupttide)."""
    K = _kopf()
    jahre = np.array([dt.datetime.fromtimestamp(float(t), dt.UTC).year for t in ts])
    G = np.zeros((len(ts), 1 + 2 * len(FREI)))
    G[:, 0] = 1
    for jahr in np.unique(jahre):
        m = jahre == jahr
        th = (ts[m] - dt.datetime(int(jahr), 1, 1, tzinfo=dt.UTC).timestamp()) / 3600.0
        for q, k in enumerate(FREI):
            teile = [(k, 1.0)] + [(kk, r) for kk, (h, r) in KOPPEL.items() if h == k]
            for kk, r in teile:
                E = np.radians(K['arg'][int(jahr)][kk] + K['speeds'][kk] * th)
                G[m, 1 + 2 * q] += r * K['fak'][int(jahr)][kk] * np.cos(E)
                G[m, 2 + 2 * q] -= r * K['fak'][int(jahr)][kk] * np.sin(E)
    return G


def laden(argv):
    von, bis = dt.date.fromisoformat(argv[0]), dt.date.fromisoformat(argv[1])
    g, sel, laeufe = auswahl()
    jj, ii = np.nonzero(sel)
    N, P = len(jj), 1 + 2 * len(FREI)
    ca, sa = np.cos(g['angle'][jj, ii]), np.sin(g['angle'][jj, ii])
    if os.path.exists(AKKU):
        A = dict(np.load(AKKU))
        assert A['GtU'].shape == (P, N)
        A['tage'] = list(A['tage'])
    else:
        A = dict(GtG=np.zeros((P, P)), GtU=np.zeros((P, N)), GtV=np.zeros((P, N)), su=np.zeros(N), sv=np.zeros(N),
                 suu=np.zeros(N), svv=np.zeros(N), nt=np.zeros(1), tage=[], schlecht=np.zeros(N, bool))
    print('%d Zellen, %d Abfragen je Variable und Tag' % (N, len(laeufe)), flush=True)
    # Zelle -> (Lauf, j-Index, i-Index) im Ausschnitt
    lauf_von = []
    for q, (J0, J1, I0, I1) in enumerate(laeufe):
        m = (jj >= J0) & (jj < J1) & (ii >= I0) & (ii < I1)
        lauf_von.append((np.nonzero(m)[0], jj[m] - J0, ii[m] - I0))
    tag = von
    while tag <= bis:
        if tag.isoformat() in A['tage']:
            tag += dt.timedelta(days=1)
            continue
        t0 = time.time()
        u = np.full((24, N), np.nan, np.float32)
        v = np.full((24, N), np.nan, np.float32)
        ok = False
        for versuch in range(5):
            try:
                ds = nc.Dataset(URL % tag.strftime('%Y%m%d'))
                ts = np.asarray(ds['time'][:], float)
                if len(ts) != 24:
                    raise RuntimeError('%d Stunden' % len(ts))
                for (J0, J1, I0, I1), (idx, a, b) in zip(laeufe, lauf_von):
                    U = np.ma.filled(ds['ubar'][:, J0:J1, I0:I1].astype(np.float32), np.nan)
                    V = np.ma.filled(ds['vbar'][:, J0:J1, I0:I1].astype(np.float32), np.nan)
                    u[:, idx], v[:, idx] = U[:, a, b], V[:, a, b]
                ds.close()
                ok = True
                break
            except Exception as e:                        # noqa: BLE001
                if 'not found' in str(e) or 'syntax error' in str(e):
                    break
                print('  Fehler %s: %s' % (tag, str(e)[:200]), flush=True)
                time.sleep(30 * (versuch + 1))
        if not ok:
            print('  %s fehlt' % tag, flush=True)
            tag += dt.timedelta(days=1)
            continue
        ost, nord = u * ca - v * sa, u * sa + v * ca
        luecke = ~np.isfinite(ost).all(0) | ~np.isfinite(nord).all(0)
        A['schlecht'] |= luecke
        ost, nord = np.nan_to_num(ost).astype(float), np.nan_to_num(nord).astype(float)
        G = design(ts)
        A['GtG'] += G.T @ G
        A['GtU'] += G.T @ ost
        A['GtV'] += G.T @ nord
        A['su'] += ost.sum(0)
        A['sv'] += nord.sum(0)
        A['suu'] += (ost ** 2).sum(0)
        A['svv'] += (nord ** 2).sum(0)
        A['nt'] += len(ts)
        A['tage'].append(tag.isoformat())
        tmp = AKKU + '.tmp.npz'
        np.savez(tmp, **{k: (np.array(w) if k == 'tage' else w) for k, w in A.items()})
        os.replace(tmp, AKKU)
        print('%s  %.0f s  Luecken %d' % (tag, time.time() - t0, int(luecke.sum())), flush=True)
        tag += dt.timedelta(days=1)


def fit():
    g, sel, _ = auswahl()
    jj, ii = np.nonzero(sel)
    A = np.load(AKKU)
    GtG, nt = A['GtG'], float(A['nt'][0])
    print('%d Tage, %d Stunden, %d Zellen (%d mit Luecken)' % (len(A['tage']), nt, len(jj), A['schlecht'].sum()))
    cu = np.linalg.solve(GtG, A['GtU'])
    cv = np.linalg.solve(GtG, A['GtV'])
    r2 = []
    for c, Gt, s, ss in ((cu, A['GtU'], A['su'], A['suu']), (cv, A['GtV'], A['sv'], A['svv'])):
        var = ss / nt - (s / nt) ** 2
        erkl = np.einsum('pn,pn->n', c, Gt) / nt - (s / nt) ** 2      # c'G'u = c'G'Gc (Normalgleichung)
        r2.append((erkl, var))
    r2 = (r2[0][0] + r2[1][0]) / np.maximum(r2[0][1] + r2[1][1], 1e-12)
    out = dict(lat=g['lat'][jj, ii].astype(np.float32), lon=g['lon'][jj, ii].astype(np.float32),
               r2=r2.astype(np.float32), ok=~A['schlecht'])
    for k in KS:
        h, r = KOPPEL.get(k, (k, 1.0))
        q = FREI.index(h)
        for nam, c in (('U_', cu), ('V_', cv)):
            out[nam + k] = (r * (c[1 + 2 * q] + 1j * c[2 + 2 * q])).astype(np.complex64)
    np.savez_compressed(AUS, **out)
    m2 = np.hypot(np.abs(out['U_M2']), np.abs(out['V_M2'])) / 0.514444
    print('M2 Betrag kn: Median %.2f, P95 %.2f, max %.2f; r2 Median %.3f, P5 %.3f'
          % (np.median(m2), np.percentile(m2, 95), m2.max(), np.median(r2), np.percentile(r2, 5)))


def laden_feinfeld():
    """-> [(name, lat, lon, {k: (U, V)})] fuer strom_feinfeld.bauen (nur Zellen ohne Luecken)."""
    if not os.path.exists(AUS):
        return []
    F = np.load(AUS)
    m = F['ok']
    return [('NorKyst', F['lat'][m].astype(float), F['lon'][m].astype(float),
             {k: (F['U_' + k][m], F['V_' + k][m]) for k in KS})]


if __name__ == '__main__':
    {'laden': lambda: laden(sys.argv[2:]), 'fit': fit}[sys.argv[1]]()
