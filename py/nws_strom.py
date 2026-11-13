#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Gezeitenstroeme aus dem Copernicus-Nordseemodell (AMM15, 1,5 km, NWSHELF_ANALYSISFORECAST_PHY_004_013).

Anlass 13.11.2026: Vor einem Kauf der Admiralty-Stromatlanten (NP337 Solent u. a.) pruefen, ob das freie Modell die
Luecken an der englischen Suedkueste fuellen kann (Solent 3, Portsmouth 0, Plymouth 0, Portland 1 Satz).

Daten: cmems_mod_nws_phy-cur_anfc_1.5km-3D_PT1H-i, ubar/vbar (tiefengemittelt, stuendlich, Zeitreihen-Ablage
-s arco-time-series: ~5 s und 0,4 MB je Punkt und Jahr). Naechste nasse Modellzelle bis MAX_KM.

  pruefen:  venv/bin/python py/nws_strom.py pruefen [lat0 lat1 lon0 lon1]
            Modell gegen alle gemessenen Stroeme (harmonics_utide_current_observations.txt) im Gebiet:
            Projektion auf die Hauptachse des Messsatzes, Vergleich der Vorhersagekurven ueber das Modelljahr
            (Kurvenfehler %, Staerke-Faktor, Zeitversatz aus M2, Richtungsfehler der Modell-Hauptachse).
"""
import cmath
import datetime as dt
import math
import os
import re
import subprocess
import sys
import tempfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import health_check as H                                           # noqa: E402
import xtide_modell as X                                           # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLI = os.path.join(ROOT, 'venv/bin/copernicusmarine')
DS = 'cmems_mod_nws_phy-cur_anfc_1.5km-3D_PT1H-i'
CACHE = os.path.join(ROOT, 'currents/nws_cur')
T0, T1 = '2025-11-01T00:00:00', '2026-11-01T00:00:00'
MAX_KM, KN = 3.0, 1.0 / 0.514444
ZIEL = os.path.join(ROOT, 'harmonics/utide/harmonics_fes2022.txt')     # nur fuer den Kopf (Speeds, Argumente)


def zelle(la, lo):
    """-> (zeiten_s, u, v, lat, lon, km) der naechsten nassen Modellzelle (m/s)."""
    import xarray as xr
    os.makedirs(CACHE, exist_ok=True)
    f = os.path.join(CACHE, '%.4f_%.4f.nc' % (la, lo))
    if not os.path.exists(f):
        cmd = [CLI, 'subset', '-i', DS, '-v', 'ubar', '-v', 'vbar', '-x', str(lo - 0.05), '-X', str(lo + 0.05),
               '-y', str(la - 0.03), '-Y', str(la + 0.03), '-z', '0', '-Z', '1', '-t', T0, '-T', T1,
               '-s', 'arco-time-series', '-o', os.path.dirname(f), '-f', os.path.basename(f), '--overwrite']
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=1200)
        if r.returncode or not os.path.exists(f):
            raise RuntimeError((r.stderr or r.stdout)[-300:])
    d = xr.open_dataset(f)
    u, v = d['ubar'].values, d['vbar'].values
    ts = d.time.values.astype('datetime64[s]').astype('int64').astype(float)
    lats, lons = d.latitude.values, d.longitude.values
    gut = np.isfinite(u).sum(axis=0) > 0.8 * len(ts)
    jj, ii = np.nonzero(gut)
    if not len(jj):
        return None
    km = 111.2 * np.hypot(lats[jj] - la, (lons[ii] - lo) * math.cos(math.radians(la)))
    k = int(np.argmin(km))
    if km[k] > MAX_KM:
        return None
    return ts, u[:, jj[k], ii[k]], v[:, jj[k], ii[k]], float(lats[jj[k]]), float(lons[ii[k]]), float(km[k])


def hauptachse(u, v):
    """Richtung (Grad rechtweisend, 0-180) der groessten Varianz."""
    c = np.cov(np.vstack([u, v]))
    w, e = np.linalg.eigh(c)
    ex, ny = e[:, -1]
    return math.degrees(math.atan2(ex, ny)) % 180


def m2(ts, x):
    """Amplitude und Phase (Grad) von M2 per Kleinste Quadrate (nur fuer Differenzen)."""
    w = math.radians(28.9841042) * ts / 3600.0
    w2 = math.radians(30.0) * ts / 3600.0
    A = np.column_stack([np.ones_like(ts), np.cos(w), np.sin(w), np.cos(w2), np.sin(w2)])
    b, *_ = np.linalg.lstsq(A, x, rcond=None)
    return math.hypot(b[1], b[2]), math.degrees(math.atan2(b[2], b[1]))


def gezeit(ts, x):
    """Gezeitenanteil einer Stundenreihe (Kleinste Quadrate mit den Tiden aus windstau_nws, ohne Mittel)."""
    from windstau_nws import _matrix
    A = _matrix(ts)
    b, *_ = np.linalg.lstsq(A, x, rcond=None)
    return A[:, 1:] @ b[1:]


def pruefen(argv):
    box = [float(a) for a in argv[:4]] if len(argv) >= 4 else [49.6, 51.3, -6.6, 1.6]
    namen, speeds, arg, fak = X.kopf_lesen(ZIEL)
    R = [r for r in H.load_records() if r['current'] and r['lat'] is not None and 'current_observations' in r['file']
         and box[0] <= r['lat'] <= box[1] and box[2] <= r['lon'] <= box[3]]
    print('%d Messsaetze' % len(R))
    erg = []
    for r in R:
        T = open(r['file'], encoding='iso-8859-1').read().split('\n')
        i = T.index(r['name'])
        kopf = '\n'.join(T[max(0, i - 40):i])
        m = re.findall(r'major_axis_deg_true: ([\d.]+)', kopf) or re.findall(r'Major axis: ([\d.]+)', kopf)
        if not m:
            print('  %s: keine Hauptachse im Kopf' % r['name'])
            continue
        ax = float(m[-1])
        try:
            z = zelle(r['lat'], r['lon'])
        except RuntimeError as e:
            print('  %s: %s' % (r['name'], e))
            continue
        if not z:
            print('  %-60s keine Modellzelle in %.0f km' % (r['name'][:60], MAX_KM))
            continue
        ts, u, v, pla, plo, km = z
        ok = np.isfinite(u) & np.isfinite(v)
        ts, u, v = ts[ok], u[ok] * KN, v[ok] * KN
        z0, w, einheit, mer = X.satz_lesen(r['file'], r['name'])
        wg = {c: (a, X.greenwich(g, speeds[c], mer)) for c, (a, g) in w.items() if c in speeds}
        ref = X.kurve(ts, 0.0, wg, namen, speeds, arg, fak)
        ref -= ref.mean()
        p = u * math.sin(math.radians(ax)) + v * math.cos(math.radians(ax))
        p = gezeit(ts, p)                                  # nur der Gezeitenanteil (Wind-/Staustrom raus)
        fehler = 100 * np.sqrt(np.mean((p - ref) ** 2)) / np.sqrt(np.mean(ref ** 2))
        am, gm = m2(ts, p)
        ar, gr = m2(ts, ref)
        dt_min = ((gm - gr + 180) % 360 - 180) / 28.9841042 * 60       # >0: Modell spaeter
        dax = (hauptachse(u, v) - ax + 90) % 180 - 90
        erg.append((fehler, am / ar, dt_min, dax))
        print('%-62s %4.1f km  Kurve %5.1f %%  Staerke x%.2f  Zeit %+4.0f min  Achse %+4.0f Grad  (M2 Messung %.2f kn)' % (
            r['name'][:62], km, fehler, am / ar, dt_min, dax, ar), flush=True)
    if erg:
        e = np.array(erg)
        print('Median: Kurve %.1f %%, Staerke x%.2f, Zeit %+.0f min, |Achse| %.0f Grad (n=%d)' % (
            np.median(e[:, 0]), np.median(e[:, 1]), np.median(e[:, 2]), np.median(abs(e[:, 3])), len(e)))


if __name__ == '__main__':
    if sys.argv[1:2] == ['pruefen']:
        pruefen(sys.argv[2:])
    else:
        print(__doc__)
