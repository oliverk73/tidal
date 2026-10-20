#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Stroemungsfit mit gekoppelten Nachbartiden fuer Reihen unter einem halben Jahr (Oliver 20.10.2026).

In 1-6 Monaten lassen sich S2/K2 und K1/P1 nicht trennen (Rayleigh: 182,6 Tage), unter 27,6 Tagen
auch M2/N2 nicht. UTide 'auto' laesst K2 und P1 dann weg; S2 und K1 schlucken sie, und zwar je
nach Jahreszeit mit anderem Vorzeichen -- Inner Sound: S2 1,45 kn im Juni, 2,29 kn im Februar, mit
K2 gemeinsam 1,79 + 0,54 kn. Hier wird der fehlende Partner mit Amplitudenverhaeltnis und
Phasenabstand des naechsten Pegels an die Haupttide gekoppelt (wie py/stroemung_kurzfit.py) und
mit allen uebrigen Tiden des alten Satzes gemeinsam gefittet (eigene kleinste Quadrate, XTide-Modell).

Usage: als Modul -- verhaeltnisse(lat, lon), fit(df, frei, kopplung)
"""
from __future__ import annotations

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cmems_stroemung_nachholen as C                               # noqa: E402
import health_check as hc                                           # noqa: E402
import osm_land                                                     # noqa: E402
import xtide_modell as X                                            # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KOPF = X.kopf_lesen(os.path.join(ROOT, 'harmonics/utide/harmonics_utide_current_observations.txt'))
PAARE = [('S2', 'K2'), ('K1', 'P1'), ('M2', 'N2')]
# Pegelquellen fuer die Verhaeltnisse: Messfits, Tafelfits, TICON, Admiralty-Haupthaefen
PEGELDATEIEN = ('harmonics_utide_observations.txt', 'harmonics_utide_tidetables.txt', 'harmonics_ticon4_worldwide.txt',
                'harmonics_att_np202.txt', 'harmonics_att_np203.txt', 'harmonics_att_np207.txt', 'harmonics_att_np208.txt')
_PEGEL = None
_KOPF = {}


def _pegel():
    global _PEGEL
    if _PEGEL is None:
        _PEGEL = [r for r in hc.load_records() if not r['current'] and r['lat'] is not None
                  and os.path.basename(r['file']) in PEGELDATEIEN
                  and all(r['amp'].get(k, (0, 0))[0] > 0 for p in PAARE for k in p)]
    return _PEGEL


def verhaeltnisse(lat, lon, max_km=150.0):
    """-> ({partner: (ratio, phasenabstand_grad)}, pegelname, km) vom naechsten vollstaendigen Pegel."""
    r = min(_pegel(), key=lambda r: osm_land.km(lat, lon, r['lat'], r['lon']))
    km = osm_land.km(lat, lon, r['lat'], r['lon'])
    if km > max_km:
        return None, None, km
    pfad = os.path.join(ROOT, r['file'])
    if pfad not in _KOPF:
        _KOPF[pfad] = X.kopf_lesen(pfad)
    sp = _KOPF[pfad][1]
    _z0, w, _e, m = X.satz_lesen(pfad, r['name'])
    g = {k: (a, X.greenwich(kap, sp[k], m)) for k, (a, kap) in w.items()}
    return {b: (g[b][0] / g[a][0], (g[b][1] - g[a][1] + 180) % 360 - 180) for a, b in PAARE}, r['name'], km


def fit(df, frei, kopplung):
    """df u,v (m/s, Stundenmittel). frei: Tiden, die frei gefittet werden; kopplung: {partner: (haupt, ratio, grad)}.
    -> dict wie C.analyse (konst in Knoten, Greenwich-Phasen)."""
    namen, sp, arg, fak = KOPF
    u, v = df['u'].values, df['v'].values
    w_, V = np.linalg.eigh(np.cov(np.vstack([u, v])))
    a = V[:, np.argmax(w_)]
    achse = float(np.degrees(np.arctan2(a[0], a[1])) % 180)
    s = (u * np.sin(np.radians(achse)) + v * np.cos(np.radians(achse))) * C.MS_KN
    t = df.index.values.astype('datetime64[s]').astype(np.int64).astype(float)
    frei = [k for k in frei if k in sp and k not in kopplung]
    alle = frei + list(kopplung)
    Cm, Sm, _ = X.matrix(t, alle, sp, arg, fak)
    col = {k: j for j, k in enumerate(alle)}
    cols = [np.ones(len(t))]
    for k in frei:
        c, sn = Cm[:, col[k]].copy(), Sm[:, col[k]].copy()
        for b, (h, r_, d_) in kopplung.items():
            if h == k:                                 # Partner b = r * A cos(theta_b - kappa - delta)
                dr = np.radians(d_)
                c += r_ * (Cm[:, col[b]] * np.cos(dr) + Sm[:, col[b]] * np.sin(dr))
                sn += r_ * (Sm[:, col[b]] * np.cos(dr) - Cm[:, col[b]] * np.sin(dr))
        cols += [c, sn]
    M = np.vstack(cols).T
    x, *_ = np.linalg.lstsq(M, s, rcond=None)
    res = s - M @ x
    konst = {}
    for i, k in enumerate(frei):
        A, kap = float(np.hypot(x[1 + 2 * i], x[2 + 2 * i])), float(np.degrees(np.arctan2(x[2 + 2 * i], x[1 + 2 * i])) % 360)
        konst[k] = (A, kap)
    for b, (h, r_, d_) in kopplung.items():
        konst[b] = (konst[h][0] * r_, (konst[h][1] + d_) % 360)
    r2 = 1 - np.sum(res ** 2) / np.sum((s - s.mean()) ** 2)
    return dict(achse=achse, mean=float(x[0]), konst=konst, r2=float(r2), rms=float(np.sqrt(np.mean(res ** 2))), n=len(s),
                t0=df.index[0], t1=df.index[-1], m2=konst.get('M2', (0, 0))[0], k1=konst.get('K1', (0, 0))[0],
                s2=konst.get('S2', (0, 0))[0], smax=float(np.percentile(np.abs(s), 95)))


def noetig(df, frei):
    """Welche Partner koppeln? K2/P1 unter 182,6 Tagen, N2 unter 27,6 Tagen -- und nur, wenn sie nicht frei drin sind."""
    tage = (df.index[-1] - df.index[0]).total_seconds() / 86400
    p = []
    if tage < 182.6:
        p += [('S2', 'K2'), ('K1', 'P1')]
    if tage < 27.6:
        p += [('M2', 'N2')]
    return [(h, b) for h, b in p if b not in frei or tage < (27.6 if b == 'N2' else 182.6)]
