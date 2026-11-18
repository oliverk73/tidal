#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Stromsaetze (Pfeile der Kartenebene) gegen TPXO10 an derselben Stelle (Oliver 18.11.2026, Schritt 3a).

Je Satz mit Richtung (py/strom_pfeile.index) wird die Vektorreihe w_s = u + i v (kn) ueber TAGE Tage im 30-min-Takt
mit der TPXO10-Reihe w_m der naechsten Wasserzelle (<= RAD Zellen) verglichen. Gesucht wird die Korrektur
    w_s(t) ~ a * w_m(t + tau)        a komplex: |a| = Staerkefaktor, arg(a) = Drehung (Grad, + = im Uhrzeigersinn)
ueber tau in -3 .. +3 h (10-min-Schritte). Ausgegeben werden Fehler vorher/nachher (RMS |w_s - w|/RMS |w_s|).
Diese (a, tau) sind die Bausteine fuer die Angleichung der Flaeche (Schritt 3b).

  venv/bin/python py/tpxo_pfeile_vergleich.py      -> harmonics/help/tpxo_pfeile_vergleich_<datum>.csv
"""
import cmath
import csv
import datetime as dt
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import strom_pfeile as SP                                           # noqa: E402
import tpxo_strom as TS                                             # noqa: E402
import tpxo_strom_karte as TK                                       # noqa: E402

ROOT = SP.E.ROOT
TAGE = 15
RAD = 6
KN = 1 / 0.514444
T0 = dt.datetime(2026, 11, 18, tzinfo=dt.timezone.utc)


def tpxo_reihe(i, j, t):
    """TPXO10-Vektor u + i v in kn an Zelle (i, j) zu Unix-Zeiten t (wie tpxo_strom_karte: f, V0+u des Jahres)."""
    kopf = TK._kopf()
    jahr = T0.year
    th = (t - T0.replace(month=1, day=1).timestamp()) / 3600.0
    u = np.zeros(len(t))
    v = np.zeros(len(t))
    for k in TK.KS:
        try:
            U, V = TS.strom(i, j, k)
        except Exception:  # noqa: BLE001
            continue
        f = kopf['fak'][jahr][k]
        E = np.radians(kopf['arg'][jahr][k] + kopf['speeds'][k] * th)
        u += f * (U * np.exp(1j * E)).real
        v += f * (V * np.exp(1j * E)).real
    return (u + 1j * v) * KN


def satz_reihe(r, t):
    lat, lon, rang, p, name, flut, ebbe, ell = r
    D = SP.TD.datei(p)
    if ell is not None:
        st, ri, _h, _n = SP.E.vektor(D, name, t, ell)
    else:
        v = D.wert(name, t)
        ri = np.where(v >= 0, flut, ebbe)
        st = np.abs(v)
    ri = np.radians(ri)
    return st * np.sin(ri) + 1j * st * np.cos(ri)                    # u (Ost) + i v (Nord)


def anpassen(ws, wm_fn, t):
    """-> (fehler_vorher, fehler_nachher, a, tau_min)"""
    n = math.sqrt(np.mean(np.abs(ws) ** 2)) or 1e-9
    w0 = wm_fn(t)
    vorher = math.sqrt(np.mean(np.abs(ws - w0) ** 2)) / n
    best = None
    for tau in range(-180, 181, 10):
        wm = wm_fn(t + tau * 60)
        den = np.vdot(wm, wm).real
        if den <= 0:
            continue
        a = np.vdot(wm, ws) / den                                       # min |ws - a wm|^2
        e = math.sqrt(np.mean(np.abs(ws - a * wm) ** 2)) / n
        if best is None or e < best[0]:
            best = (e, a, tau)
    if best is None:
        return vorher, float('nan'), complex('nan'), float('nan')
    return vorher, best[0], best[1], best[2]


def main():
    t = T0.timestamp() + np.arange(0, TAGE * 86400, 1800.0)
    aus = os.path.join(ROOT, 'harmonics/help/tpxo_pfeile_vergleich_%s.csv' % dt.date.today().strftime('%Y%m%d'))
    zeilen = []
    idx = SP.index()
    for n, r in enumerate(idx):
        lat, lon, rang, p, name = r[:5]
        z = TS.wasserzelle(lat, lon, RAD)
        if z is None:
            zeilen.append(dict(name=name, datei=os.path.basename(p), lat=lat, lon=lon, rang=rang, zelle_km='', tiefe='',
                               satz_kn='', tpxo_kn='', fehler_vorher='', fehler_nachher='', faktor='', drehung='',
                               versatz_min='', gradient=''))
            continue
        i, j, dk = z
        try:
            ws = satz_reihe(r, t)
        except Exception:  # noqa: BLE001
            continue
        cache = {}

        def wm_fn(tt, i=i, j=j):
            key = float(tt[0])
            if key not in cache:
                cache[key] = tpxo_reihe(i, j, tt)
            return cache[key]
        vor, nach, a, tau = anpassen(ws, wm_fn, t)
        zeilen.append(dict(
            name=name, datei=os.path.basename(p), lat=lat, lon=lon, rang=rang, zelle_km=round(dk, 1),
            tiefe=round(float(TS.hz()[i, j]), 1),
            satz_kn=round(float(np.max(np.abs(ws))), 2), tpxo_kn=round(float(np.max(np.abs(wm_fn(t)))), 2),
            fehler_vorher=round(100 * vor), fehler_nachher=round(100 * nach) if nach == nach else '',
            faktor=round(abs(a), 2) if a == a else '', drehung=round(-math.degrees(cmath.phase(a))) if a == a else '',
            versatz_min=tau, gradient=round(TS.gradient(i, j), 0)))
        if n % 500 == 0:
            print('%d/%d' % (n, len(idx)), flush=True)
    with open(aus, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=list(zeilen[0]))
        w.writeheader()
        w.writerows(zeilen)
    ok = [z for z in zeilen if z['fehler_vorher'] != '']
    print(aus, len(zeilen), 'Saetze,', len(ok), 'mit TPXO-Zelle')
    for rg in range(5):
        g = [z for z in ok if z['rang'] == rg]
        if not g:
            continue
        fv = np.median([z['fehler_vorher'] for z in g])
        fn = np.median([z['fehler_nachher'] for z in g if z['fehler_nachher'] != ''])
        fa = np.median([z['faktor'] for z in g if z['faktor'] != ''])
        ve = np.median([abs(z['versatz_min']) for z in g if z['versatz_min'] == z['versatz_min']])
        print('Rang %d: %4d Saetze  Fehler vorher %3.0f %% nachher %3.0f %%  Faktor %.2f  |Versatz| %3.0f min' % (rg, len(g), fv, fn, fa, ve))


if __name__ == '__main__':
    main()
