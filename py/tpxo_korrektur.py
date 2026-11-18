#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TPXO10-Stromflaeche an guten Stromsaetzen angleichen (Oliver 18.11.2026, Schritt 3b).

Anker: Saetze aus harmonics/help/tpxo_pfeile_vergleich_<datum>.csv (py/tpxo_pfeile_vergleich.py) mit
  Rang <= 2 (Messfit, NOAA/Ellipse, Tafel/Atlas), TPXO-Zelle <= 3 km, Fehler nach Korrektur <= 30 %,
  Gewinn >= 15 Prozentpunkte, Faktor 0,33 .. 3, |Drehung| <= 60 Grad.
Je Anker: w_satz(t) ~ a * w_tpxo(t + tau)  (a komplex: Faktor + Drehung, w = u + i v).

Flaeche: Gewichte g_i = exp(-(d_i/R)^2) (bis 3 R), S = sum g_i,
  tau(x)   = sum g_i tau_i   / max(S, 1)
  log a(x) = sum g_i log a_i / max(S, 1)
Am Anker volle Korrektur, nach aussen weich auf null. Mehrere Anker mitteln sich.

  venv/bin/python py/tpxo_korrektur.py bauen      -> tide_models/tpxo_korrektur.json
  venv/bin/python py/tpxo_korrektur.py pruefen    Gegenprobe: jeder Satz nur mit den Ankern ohne sich selbst
"""
import cmath
import csv
import glob
import json
import math
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATEI = os.path.join(ROOT, 'tide_models/tpxo_korrektur.json')
R_KM = 6.0
_cache = {'mtime': None, 'a': None}


def _csv():
    return sorted(glob.glob(os.path.join(ROOT, 'harmonics/help/tpxo_pfeile_vergleich_*.csv')))[-1]


def _anker_aus_zeile(r):
    f = lambda k: float(r[k])  # noqa: E731
    try:
        if int(r['rang']) > 2 or f('zelle_km') > 3 or f('fehler_nachher') > 30:
            return None
        if f('fehler_vorher') - f('fehler_nachher') < 15:
            return None
        fa, dr = f('faktor'), f('drehung')
        if not (0.33 <= fa <= 3) or abs((dr + 180) % 360 - 180) > 60:
            return None
    except (ValueError, KeyError):
        return None
    # a = faktor * e^{-i drehung}: Drehung im Uhrzeigersinn (Kompass) = negative komplexe Phase
    la = complex(math.log(fa), -math.radians((dr + 180) % 360 - 180))
    return dict(name=r['name'], lat=f('lat'), lon=f('lon'), tau=f('versatz_min'), la_re=la.real, la_im=la.imag,
                vorher=f('fehler_vorher'), nachher=f('fehler_nachher'))


def bauen():
    A = [a for a in (_anker_aus_zeile(r) for r in csv.DictReader(open(_csv(), encoding='utf-8'))) if a]
    json.dump({'r_km': R_KM, 'quelle': os.path.basename(_csv()), 'anker': A}, open(DATEI, 'w', encoding='utf-8'),
              ensure_ascii=False, indent=0)
    print(len(A), 'Anker ->', DATEI)


def anker():
    if not os.path.exists(DATEI):
        return []
    m = os.path.getmtime(DATEI)
    if _cache['mtime'] != m:
        _cache['a'] = json.load(open(DATEI, encoding='utf-8'))['anker']
        _cache['mtime'] = m
    return _cache['a']


def gitter(lat, lon, ohne=None):
    """lat (ny,), lon (nx,) Grad -> (tau_min (ny,nx), log_a komplex (ny,nx)) oder None, wenn kein Anker wirkt."""
    A = anker()
    if not A:
        return None
    lat = np.asarray(lat, float)
    lon = np.asarray(lon, float)
    s, n = lat.min(), lat.max()
    rad = 3 * R_KM / 111.0
    sel = [a for a in A if s - rad <= a['lat'] <= n + rad and a['name'] != ohne]
    if not sel:
        return None
    S = np.zeros((len(lat), len(lon)))
    T = np.zeros_like(S)
    L = np.zeros(S.shape, complex)
    for a in sel:
        dlo = ((lon - a['lon'] + 180) % 360) - 180
        ci = np.nonzero(np.abs(dlo) <= rad / max(0.1, math.cos(math.radians(a['lat']))))[0]
        ri = np.nonzero(np.abs(lat - a['lat']) <= rad)[0]
        if not len(ci) or not len(ri):
            continue
        dy = (lat[ri, None] - a['lat']) * 111.0
        dx = dlo[None, ci] * 111.0 * math.cos(math.radians(a['lat']))
        g = np.exp(-(dx ** 2 + dy ** 2) / R_KM ** 2)
        sub = np.ix_(ri, ci)
        S[sub] += g
        T[sub] += g * a['tau']
        L[sub] += g * complex(a['la_re'], a['la_im'])
    if not S.any():
        return None
    d = np.maximum(S, 1.0)
    return T / d, L / d


def punkt(lat, lon, ohne=None):
    r = gitter(np.array([lat]), np.array([lon]), ohne)
    if r is None:
        return 0.0, 0j
    return float(r[0][0, 0]), complex(r[1][0, 0])


def pruefen():
    """Gegenprobe: Saetze (Rang <= 2, Zelle <= 3 km) im Wirkbereich eines ANDEREN Ankers, Fehler vorher/nachher."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import tpxo_pfeile_vergleich as V
    idx = {x[4]: x for x in V.SP.index()}
    t = V.T0.timestamp() + np.arange(0, V.TAGE * 86400, 1800.0)
    zeilen = [r for r in csv.DictReader(open(_csv(), encoding='utf-8'))
              if r['fehler_vorher'] and r['zelle_km'] and int(r['rang']) <= 2 and float(r['zelle_km']) <= 3]
    erg = []
    for r in zeilen:
        x = idx.get(r['name'])
        if not x:
            continue
        tau, la = punkt(x[0], x[1], ohne=r['name'])
        if tau == 0 and la == 0:
            continue
        z = V.TS.wasserzelle(x[0], x[1], V.RAD)
        ws = V.satz_reihe(x, t)
        n = math.sqrt(np.mean(np.abs(ws) ** 2)) or 1e-9
        w0 = V.tpxo_reihe(z[0], z[1], t)
        w1 = cmath.exp(la) * V.tpxo_reihe(z[0], z[1], t + tau * 60)
        erg.append((r['name'], 100 * math.sqrt(np.mean(np.abs(ws - w0) ** 2)) / n,
                    100 * math.sqrt(np.mean(np.abs(ws - w1) ** 2)) / n, abs(la), tau))
    if not erg:
        print('keine Saetze im Wirkbereich anderer Anker')
        return
    v = np.array([e[1] for e in erg])
    w = np.array([e[2] for e in erg])
    print('%d Saetze im Wirkbereich anderer Anker: Fehler Median %.0f -> %.0f %%, besser %d, schlechter %d (>5 Punkte: %d/%d)'
          % (len(erg), np.median(v), np.median(w), (w < v).sum(), (w > v).sum(), (w < v - 5).sum(), (w > v + 5).sum()))
    for e in sorted(erg, key=lambda e: e[2] - e[1])[-8:]:
        print('  schlechter: %-60s %3.0f -> %3.0f %%' % (e[0][:60], e[1], e[2]))
    return erg


if __name__ == '__main__':
    {'bauen': bauen, 'pruefen': pruefen}[sys.argv[1]]()
