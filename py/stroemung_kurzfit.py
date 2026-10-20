#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Kurzreihen-Fit (14-25 Tage): M2+N2, S2+K2, K1+P1 gekoppelt mit Verhaeltnis/Phasenabstand vom Pegel."""
import sys, numpy as np, pandas as pd
sys.path.insert(0, '/home/oliver/weather/py')
import xtide_modell as X, cmems_stroemung_nachholen as C
KOPF = X.kopf_lesen('/home/oliver/weather/harmonics/utide/harmonics_utide_current_observations.txt')
GRUPPEN = [('M2', 'N2'), ('S2', 'K2'), ('K1', 'P1')]
FREI = ['O1', 'M4', 'MS4', 'M6', '2MS6']


def pegel_verhaeltnisse(pfad, name):
    namen, sp, _, _ = X.kopf_lesen(pfad)
    z0, w, e, m = X.satz_lesen(pfad, name)
    g = {k: (a, X.greenwich(kap, sp[k], m)) for k, (a, kap) in w.items()}
    return {b: (g[b][0] / g[a][0], (g[b][1] - g[a][1] + 180) % 360 - 180) for a, b in GRUPPEN}


def fit(df, ratio):
    """df: u, v in m/s (stuendlich). ratio: {N2: (r, delta_grad), K2: ..., P1: ...}. -> r wie C.analyse."""
    namen, sp, arg, fak = KOPF
    u, v = df['u'].values, df['v'].values
    w_, V = np.linalg.eigh(np.cov(np.vstack([u, v])))
    a = V[:, np.argmax(w_)]
    achse = float(np.degrees(np.arctan2(a[0], a[1])) % 180)
    s = (u * np.sin(np.radians(achse)) + v * np.cos(np.radians(achse))) * C.MS_KN
    t = (df.index.values.astype('datetime64[s]').astype(np.int64)).astype(float)
    alle = [x for g in GRUPPEN for x in g] + FREI
    Cm, Sm, _ = X.matrix(t, alle, sp, arg, fak)
    col = {k: j for j, k in enumerate(alle)}
    cols = [np.ones(len(t))]
    for a_, b_ in GRUPPEN:
        r_, d_ = ratio[b_]; dr = np.radians(d_)
        # Term A cos(theta - kappa); b_: r A cos(theta_b - kappa - delta)
        cb = Cm[:, col[b_]] * np.cos(dr) + Sm[:, col[b_]] * np.sin(dr)
        sb = Sm[:, col[b_]] * np.cos(dr) - Cm[:, col[b_]] * np.sin(dr)
        cols += [Cm[:, col[a_]] + r_ * cb, Sm[:, col[a_]] + r_ * sb]
    for k in FREI:
        cols += [Cm[:, col[k]], Sm[:, col[k]]]
    M = np.vstack(cols).T
    x, *_ = np.linalg.lstsq(M, s, rcond=None)
    res = s - M @ x
    konst = {}
    i = 1
    for a_, b_ in GRUPPEN:
        A = np.hypot(x[i], x[i + 1]); kap = np.degrees(np.arctan2(x[i + 1], x[i])) % 360
        konst[a_] = (float(A), float(kap)); r_, d_ = ratio[b_]
        konst[b_] = (float(A * r_), float((kap + d_) % 360)); i += 2
    for k in FREI:
        konst[k] = (float(np.hypot(x[i], x[i + 1])), float(np.degrees(np.arctan2(x[i + 1], x[i])) % 360)); i += 2
    r2 = 1 - np.sum(res ** 2) / np.sum((s - s.mean()) ** 2)
    return dict(achse=achse, mean=float(x[0]), konst=konst, r2=float(r2), rms=float(np.sqrt(np.mean(res ** 2))), n=len(s),
                t0=df.index[0], t1=df.index[-1], m2=konst['M2'][0], k1=konst['K1'][0], s2=konst['S2'][0],
                smax=float(np.percentile(np.abs(s), 95)))
