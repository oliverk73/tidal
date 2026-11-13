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
            Ergebnis Suedengland 13.11.: Achse 3 Grad, Staerke x1,05, Modell ~14 min frueh; geeicht offene See ~15 %,
            an Kaps/Buchten 40-90 %. Dort unterscheiden sich die Nachbarzellen (<= 2,5 km) um 18-52 %, an guten
            Punkten um hoechstens 13 % -> GRADIENT_MAX als Ausschluss.

  luecken:  venv/bin/python py/nws_strom.py luecken [--schreiben]
            Punkt 5 km (sonst 8 km) seewaerts vor jedem Pegelort der englischen Sued-/Suedwestkueste ohne Stromsatz in LUECKE_KM;
            nur wenn alle Zellen ringsum nass und der Nachbarzellen-Unterschied <= GRADIENT_MAX. Eichung: Zeitversatz
            und Staerke-Median der 3 naechsten guten Messsaetze. Schreibt harmonics_utide_current_tables.txt.
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
GRADIENT_MAX, LUECKE_KM, ABSTAND_KM, EICH_N = 12.0, 12.0, (5.0, 8.0), 3
STROM = os.path.join(ROOT, 'harmonics/utide/harmonics_utide_current_tables.txt')
SUED = (49.85, 51.0, -6.6, 1.0)   # englische Sued-/Suedwestkueste mit Scilly
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


def m2_vektor(ts, u, v):
    w = math.radians(28.9841042) * ts / 3600.0
    A = np.column_stack([np.ones_like(ts), np.cos(w), np.sin(w)])
    bu, *_ = np.linalg.lstsq(A, u, rcond=None)
    bv, *_ = np.linalg.lstsq(A, v, rcond=None)
    return np.array([bu[1], bu[2], bv[1], bv[2]])


def gradient(la, lo):
    """-> (max. M2-Unterschied der Nachbarzellen bis 2,5 km in %, Anteil nasser Zellen) an der naechsten Zelle."""
    import xarray as xr
    zelle(la, lo)
    d = xr.open_dataset(os.path.join(CACHE, '%.4f_%.4f.nc' % (la, lo)))
    u, v = d['ubar'].values, d['vbar'].values
    ts = d.time.values.astype('datetime64[s]').astype('int64').astype(float)
    lats, lons = d.latitude.values, d.longitude.values
    ok = np.isfinite(u).sum(axis=0) > 0.8 * len(ts)
    jj, ii = np.nonzero(ok)
    km = 111.2 * np.hypot(lats[jj] - la, (lons[ii] - lo) * math.cos(math.radians(la)))
    k = int(np.argmin(km))
    j0, i0 = jj[k], ii[k]
    c = m2_vektor(ts, u[:, j0, i0], v[:, j0, i0])
    n = np.linalg.norm(c)
    g = [np.linalg.norm(m2_vektor(ts, u[:, j, i], v[:, j, i]) - c) / n for j, i in zip(jj, ii)
         if 0 < 111.2 * math.hypot(lats[j] - lats[j0], (lons[i] - lons[i0]) * math.cos(math.radians(la))) <= 2.5]
    return 100 * max(g) if g else 999.0, ok.sum() / ok.size


def eichpunkte():
    """Gute Messsaetze im Suedgebiet: (record, dt_min, faktor) -- nur mit kleinem Modellgradient."""
    namen, speeds, arg, fak = X.kopf_lesen(ZIEL)
    out = []
    for r in H.load_records():
        if not (r['current'] and r['lat'] is not None and 'current_observations' in r['file']):
            continue
        if not (SUED[0] - 0.5 <= r['lat'] <= SUED[1] + 0.5 and SUED[2] - 0.5 <= r['lon'] <= SUED[3] + 1.0):
            continue
        T = open(r['file'], encoding='iso-8859-1').read().split('\n')
        i = T.index(r['name'])
        kopf = '\n'.join(T[max(0, i - 40):i])
        m = re.findall(r'major_axis_deg_true: ([\d.]+)', kopf) or re.findall(r'Major axis: ([\d.]+)', kopf)
        z = zelle(r['lat'], r['lon']) if m else None
        if not z:
            continue
        gr, nass = gradient(r['lat'], r['lon'])
        if gr > GRADIENT_MAX or nass < 1.0:
            continue
        ax = float(m[-1])
        ts, u, v = z[0], z[1] * KN, z[2] * KN
        ok = np.isfinite(u)
        ts, u, v = ts[ok], u[ok], v[ok]
        _z0, w, _e, mer = X.satz_lesen(r['file'], r['name'])
        wg = {c: (a, X.greenwich(g, speeds[c], mer)) for c, (a, g) in w.items() if c in speeds}
        ref = X.kurve(ts, 0.0, wg, namen, speeds, arg, fak)
        p = gezeit(ts, u * math.sin(math.radians(ax)) + v * math.cos(math.radians(ax)))
        am, gm = m2(ts, p)
        ar, gr_ = m2(ts, ref - ref.mean())
        out.append((r, ((gm - gr_ + 180) % 360 - 180) / 28.9841042 * 60, am / ar))
    return out


RICHTUNG = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE', 'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW']


def luecken(argv):
    import pandas as pd
    import cmems_stroemung_nachholen as C
    import osm_land
    from generate_germany_harmonics_175 import CONSTITUENTS_175
    from sicher_schreiben import schreiben
    alle = H.load_records()
    strom = [r for r in alle if r['current'] and r['lat'] is not None]
    orte = [r for r in alle if not r['current'] and r['lat'] is not None and 'England' in r['name']
            and SUED[0] <= r['lat'] <= SUED[1] and SUED[2] <= r['lon'] <= SUED[3]]
    E = eichpunkte()
    print('%d Pegelorte, %d Eichpunkte (Gradient <= %.0f %%)' % (len(orte), len(E), GRADIENT_MAX), flush=True)
    L = osm_land.Land([(r['lat'], r['lon']) for r in orte])
    neu, bloecke = [], []
    heute = dt.date.today().strftime('%Y%m%d')
    for r in sorted(orte, key=lambda r: r['name']):
        ort = r['name'].split(',')[0].split(' (')[0]
        treffer = None
        for abst in ABSTAND_KM:
            best = None
            for az in range(0, 360, 10):
                q = (r['lat'] + abst / 111.2 * math.cos(math.radians(az)),
                     r['lon'] + abst / (111.2 * math.cos(math.radians(r['lat']))) * math.sin(math.radians(az)))
                if L.ist_land(*q):
                    continue
                kk = L.kueste_km(*q, rmax=10)
                if best is None or kk > best[0]:
                    best = (kk, q, az)
            if not best or best[0] < 2.0:
                continue
            kk, (la, lo), az = best
            if any(H.km({'lat': la, 'lon': lo}, s_) < LUECKE_KM for s_ in strom + [{'lat': a_, 'lon': b_} for a_, b_, *_ in neu]):
                break                                     # Luecke schon zu: weiter draussen erst recht
            try:
                z = zelle(la, lo)
            except RuntimeError as e:
                print('  %s: %s' % (ort, e))
                continue
            if not z:
                continue
            gr, nass = gradient(la, lo)
            if gr > GRADIENT_MAX or nass < 1.0:
                print('  %-24s %4.1f km  %.4f %.4f  Gradient %3.0f %%, nass %3.0f %% -> nicht' % (ort, abst, la, lo, gr, 100 * nass))
                continue
            treffer = (la, lo, az, z, gr)
            break
        if not treffer:
            continue
        la, lo, az, z, gr = treffer
        nah = sorted(E, key=lambda x: H.km({'lat': la, 'lon': lo}, x[0]))[:EICH_N]
        dtm = float(np.median([x[1] for x in nah]))
        fk = float(np.median([x[2] for x in nah]))
        ts, u, v, pla, plo, km = z
        ok = np.isfinite(u) & np.isfinite(v)
        # Modell ist dtm Minuten frueh (dtm < 0): wahre Zeit = Modellzeit - dtm
        idx = pd.to_datetime(ts[ok] - dtm * 60, unit='s')
        df = pd.DataFrame({'u': u[ok] / fk, 'v': v[ok] / fk}, index=idx)
        a = C.analyse(df, pla, C.KONST)
        richt = RICHTUNG[int(((az + 11.25) % 360) // 22.5)]
        name = '%s (%d km %s), England, United Kingdom Current' % (ort, round(H.km(r, {'lat': pla, 'lon': plo})), richt)
        refn = ', '.join('%s (%+.0f min, x%.2f)' % (x[0]['name'].split(' Current')[0][:40], x[1], x[2]) for x in nah)
        print('%-62s %.4f %.4f  Gradient %3.0f %%  Achse %3.0f  M2 %.2f kn  Eichung %+.0f min x%.2f' % (
            name, pla, plo, gr, a['achse'], a['m2'], dtm, fk), flush=True)
        neu.append((pla, plo, name))
        B = ['# Harmonic constants derived from the Copernicus NW-Shelf model (AMM15 1.5 km, %s), depth-mean ubar/vbar, model output' % DS,
             '# Calibrated at the %d nearest measured current sets: time %+.0f min, strength /%.2f (py/nws_strom.py)' % (len(nah), -dtm, fk),
             '# Calibration sets: %s' % refn[:180],
             '# E.U. Copernicus Marine Service Information, NWSHELF_ANALYSISFORECAST_PHY_004_013, doi 10.48670/moi-00054',
             '# (UTide v0.3.1, principal-axis projection)',
             '# %d hourly samples, depth mean' % a['n'],
             '# from %s to %s' % (a['t0'].strftime('%Y-%m-%d'), a['t1'].strftime('%Y-%m-%d')),
             '# R^2 = %.4f, RMS error = %.4f knots' % (a['r2'], a['rms']),
             '# Major axis: %.1f deg true' % a['achse'], '#',
             '# BEGIN HOT COMMENTS', '# country: United Kingdom',
             '# source: Copernicus NW-Shelf model (AMM15), calibrated, UTide analysis',
             '# station_id_context: CMEMS-NWS-AMM15', '# institution: Met Office / Copernicus Marine',
             '# datum: n/a', '# station_type: current', '# major_axis_deg_true: %.1f' % a['achse'], '# confidence: 5',
             '# note: MODEL-DERIVED. Luecke offene See, Nachbarzellen-Unterschied %.0f %% (Grenze %.0f %%), Oliver %s.' % (gr, GRADIENT_MAX, heute),
             '# time_correction_min: %+.0f' % -dtm,
             '# utide: period=%s..%s const=%d' % (a['t0'].strftime('%Y-%m-%d'), a['t1'].strftime('%Y-%m-%d'), len(a['konst'])),
             '# !units: knots', '# !longitude: %.4f' % plo, '# !latitude: %.4f' % pla,
             name, '+00:00 :UTC', '%.4f knots' % a['mean']]
        for k, _sp in CONSTITUENTS_175:
            c = a['konst'].get(k)
            B.append('%-15s %.4f  %.2f' % (k, c[0], c[1]) if c and c[0] >= 0.00005 else 'x 0 0')
        bloecke.append('\n'.join(B))
    print('%d neue Saetze' % len(bloecke))
    if '--schreiben' in argv and bloecke:
        T = open(STROM, encoding='iso-8859-1').read().rstrip('\n')
        schreiben(STROM, T + '\n' + '\n'.join(bloecke) + '\n')
        print('->', os.path.relpath(STROM, ROOT))


if __name__ == '__main__':
    if sys.argv[1:2] == ['pruefen']:
        pruefen(sys.argv[2:])
    elif sys.argv[1:2] == ['luecken']:
        luecken(sys.argv[2:])
    else:
        print(__doc__)
