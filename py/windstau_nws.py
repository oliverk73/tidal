#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Windstau fuer Nordsee, Aermelkanal, Britische Inseln und Biskaya aus dem Copernicus-Nordseemodell (Oliver 9.11.2026).

Das Modell (NWSHELF_ANALYSISFORECAST_PHY_004_013, AMM15 1,5 km) rechnet die Tide mit. Der Abzug von nur 5 Tiden
(windstau_cmems.py) reicht hier nicht: N2 ist in 10 Tagen nicht von M2 zu trennen, Flachwassertiden sind gross.
Deshalb einmalig je Pegel ein Jahr Stundenwerte am naechsten Modellpunkt holen und die MODELLTIDE fitten
(Mittel + Sa/Ssa + ~60 Tiden, feste Frequenzen, absolute Zeit). Windstau = Modell-Vorhersage - Modelltide - Mittel.
Kein Automatismus: alles von Hand.

  --modelltide [name ...]   Jahr laden + fitten (einmalig; ~3 MB und ~7 s je Pegel)  -> water_levels/nws_ssh/modelltide.npz
  --vorhersage              Vorhersagefenster je 1-Grad-Ausschnitt laden, Windstau rechnen -> water_levels/nws_ssh/aktuell.npz
Usage: venv/bin/python py/windstau_nws.py --modelltide|--vorhersage [name ...]
"""
from __future__ import annotations

import datetime as dt
import json
import math
import os
import subprocess
import sys
import tempfile

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ZIEL = os.path.join(ROOT, 'water_levels/nws_ssh')
MT = os.path.join(ZIEL, 'modelltide.npz')
DATEI = os.path.join(ZIEL, 'aktuell.npz')
CLI = os.path.join(ROOT, 'venv/bin/copernicusmarine')
DS = 'cmems_mod_nws_phy-ssh_anfc_1.5km-2D_PT1H-i'
# Tiden fuer den Modelltide-Fit (Grad/h); Sa/Ssa fuer den Jahresgang des Mittelwassers
TIDEN = {
    'Sa': 0.0410686, 'Ssa': 0.0821373, 'Mm': 0.5443747, 'Mf': 1.0980331, 'Q1': 13.3986609, 'O1': 13.9430356,
    'M1': 14.4920521, 'P1': 14.9589314, 'S1': 15.0, 'K1': 15.0410686, 'J1': 15.5854433, 'OO1': 16.1391017,
    '2N2': 27.8953548, 'MU2': 27.9682084, 'N2': 28.4397295, 'NU2': 28.5125831, 'M2': 28.9841042, 'LDA2': 29.4556253,
    'L2': 29.5284789, 'T2': 29.9589333, 'S2': 30.0, 'K2': 30.0821373, '2SM2': 31.0158958, 'MO3': 42.9271398,
    'M3': 43.4761563, 'MK3': 44.0251729, 'MN4': 57.4238337, 'M4': 57.9682084, 'MS4': 58.9841042, 'MK4': 59.0662415,
    'S4': 60.0, '2MN6': 86.4079380, 'M6': 86.9523127, 'MSN6': 87.4238337, '2MS6': 87.9682084, '2MK6': 88.0503457,
    '2SM6': 88.9841042, 'M8': 115.9364166, 'MNS2': 27.4966873, 'MSN2': 30.5443747, '3MS4': 56.9523127,
    'N4': 56.8794590, '2MK5': 73.0092604, 'M5': 72.4602502, '3MK7': 101.9933085,
}
EPOCHE = dt.datetime(2020, 1, 1, tzinfo=dt.timezone.utc).timestamp()


def gebiet(la, lo):
    """NWS-Gebiet ohne die Teile, die windstau_cmems.py schon abdeckt (Ostsee ab 9,3 O, Limfjord)."""
    if not (46.0 <= la <= 62.7 and -19.8 <= lo <= 12.9):
        return False
    if la > 53.3 and lo > 9.3:
        return False
    if 56.3 < la < 57.2 and 8.1 < lo < 9.3:
        return False
    return True


def stationen(nur=None):
    d = json.load(open(os.path.join(ROOT, 'static/js/leaflet_markers_data.json'), encoding='utf-8'))['stations']
    out = []
    for r in d:
        if r[5] == 1 or r[3] == 'bore' or not gebiet(r[1], r[2]):
            continue
        if nur and r[8] not in nur:
            continue
        out.append((f"{r[3][:-4]}.txt|{r[8]}", r[1], r[2]))
    return out


def _subset(x0, x1, y0, y1, t0, t1, ziel, service=None):
    cmd = [CLI, 'subset', '-i', DS, '-v', 'zos', '-x', str(x0), '-X', str(x1), '-y', str(y0), '-Y', str(y1), '-t', t0,
           '-T', t1, '-o', os.path.dirname(ziel), '-f', os.path.basename(ziel), '--overwrite']
    if service:
        cmd += ['-s', service]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    if r.returncode or not os.path.exists(ziel):
        raise RuntimeError((r.stderr or r.stdout)[-300:])


def _naechster(f, la, lo):
    """-> (zeiten_s, werte, lat, lon) des naechsten Modellpunkts mit Daten."""
    import xarray as xr
    d = xr.open_dataset(f)
    v = d['zos'].values
    if v.ndim == 4:
        v = v[:, 0]
    ts = d.time.values.astype('datetime64[s]').astype('int64').astype(float)
    lats, lons = d.latitude.values, d.longitude.values
    gut = np.isfinite(v).sum(axis=0) > 0.8 * len(ts)
    jj, ii = np.nonzero(gut)
    if not len(jj):
        return None
    km = 111.2 * np.hypot(lats[jj] - la, (lons[ii] - lo) * math.cos(math.radians(la)))
    k = int(np.argmin(km))
    return ts, v[:, jj[k], ii[k]].astype(float), float(lats[jj[k]]), float(lons[ii[k]]), float(km[k])


def _matrix(ts):
    th = (ts - EPOCHE) / 3600.0
    sp = np.radians(np.array(list(TIDEN.values())))
    return np.column_stack([np.ones_like(th)] + [f(np.outer(th, sp)) for f in (np.cos, np.sin)])


def modelltide(argv):
    import time
    nur = [a for a in argv if not a.startswith('--')]
    st = stationen(nur)
    os.makedirs(ZIEL, exist_ok=True)
    alt = dict(np.load(MT, allow_pickle=True)) if os.path.exists(MT) else {}
    erg = {k: (alt['koef'][i], alt['punkt'][i]) for i, k in enumerate(alt.get('schluessel', []))}
    jetzt = dt.datetime.now(dt.timezone.utc)
    t0 = f'{jetzt - dt.timedelta(days=366):%Y-%m-%d}T00:00:00'
    t1 = f'{jetzt - dt.timedelta(days=1):%Y-%m-%d}T00:00:00'
    tmp = tempfile.mkdtemp(prefix='nws_')
    print(len(st), 'Pegel,', sum(1 for k, _, _ in st if k in erg), 'schon fertig', flush=True)
    for n, (key, la, lo) in enumerate(st):
        if key in erg and not nur:
            continue
        f = os.path.join(tmp, 'p.nc')
        a = time.time()
        try:
            _subset(lo - 0.04, lo + 0.04, la - 0.025, la + 0.025, t0, t1, f, 'arco-time-series')
            r = _naechster(f, la, lo)
        except Exception as e:  # noqa: BLE001
            print('  %s: %s' % (key, str(e)[-120:]), flush=True)
            continue
        if not r or r[4] > 5:
            print('  %s: kein Modellwasser bis 5 km' % key, flush=True)
            continue
        ts, z, pla, plo, km = r
        ok = np.isfinite(z)
        X = _matrix(ts[ok])
        b, *_ = np.linalg.lstsq(X, z[ok], rcond=None)
        rest = z[ok] - X @ b
        erg[key] = (b.astype('float32'), np.array([pla, plo, km], 'float32'))
        print('%4d/%d %-60s %.1f km  Tide-RMS %.2f m  Rest %.3f m  %.0f s' % (
            n + 1, len(st), key[:60], km, np.std(X @ b), np.std(rest), time.time() - a), flush=True)
        if n % 20 == 0:
            _mt_speichern(erg)
    _mt_speichern(erg)


def _mt_speichern(erg):
    k = sorted(erg)
    np.savez_compressed(MT + '.teil.npz', schluessel=np.array(k), koef=np.array([erg[x][0] for x in k]),
                        punkt=np.array([erg[x][1] for x in k]), tiden=np.array(list(TIDEN)))
    os.replace(MT + '.teil.npz', MT)


def vorhersage(argv):
    nur = [a for a in argv if not a.startswith('--')]
    M = dict(np.load(MT, allow_pickle=True))
    idx = {k: i for i, k in enumerate(M['schluessel'])}
    st = [s for s in stationen(nur) if s[0] in idx]
    jetzt = dt.datetime.now(dt.timezone.utc)
    t0 = f'{jetzt - dt.timedelta(days=2):%Y-%m-%d}T00:00:00'
    t1 = f'{jetzt + dt.timedelta(days=11):%Y-%m-%d}T00:00:00'
    zellen = {}
    for key, la, lo in st:
        p = M['punkt'][idx[key]]
        zellen.setdefault((math.floor(p[0]), math.floor(p[1])), []).append((key, float(p[0]), float(p[1])))
    tmp = tempfile.mkdtemp(prefix='nws_')
    ergebnis = {}
    for n, (z, pts) in enumerate(sorted(zellen.items())):
        f = os.path.join(tmp, 'z.nc')
        try:
            # Zeitreihen-Ablage: 1-Grad-Ausschnitt ~9 s / 6,5 MB; die Raum-Ablage laedt immer ~180 MB (gemessen 9.11.2026).
            # Ausschnitt eng um die Modellpunkte der Pegel dieser Zelle.
            la_, lo_ = [p_[1] for p_ in pts], [p_[2] for p_ in pts]
            _subset(min(lo_) - 0.03, max(lo_) + 0.03, min(la_) - 0.02, max(la_) + 0.02, t0, t1, f, 'arco-time-series')
            import xarray as xr
            d = xr.open_dataset(f)
            v = d['zos'].values
            ts = d.time.values.astype('datetime64[s]').astype('int64').astype(float)
            lats, lons = d.latitude.values, d.longitude.values
        except Exception as e:  # noqa: BLE001
            print('  Zelle %s: %s' % (z, str(e)[-120:]), flush=True)
            continue
        X = _matrix(ts)
        for key, pla, plo in pts:
            j, i = int(np.argmin(np.abs(lats - pla))), int(np.argmin(np.abs(lons - plo)))
            w = v[:, j, i].astype(float)
            if np.isfinite(w).sum() < 24:
                continue
            ergebnis[key] = (ts, w - X @ M['koef'][idx[key]].astype(float))
        print('  %d/%d %s: %d Pegel' % (n + 1, len(zellen), z, len(pts)), flush=True)
    if not ergebnis:
        print('nichts geladen')
        return 1
    tg = sorted({tuple(t) for t, _ in ergebnis.values()}, key=len)[-1]
    tg = np.array(tg)
    sch = sorted(ergebnis)
    zz = np.column_stack([np.interp(tg, *ergebnis[k], left=np.nan, right=np.nan) for k in sch]).astype('float32')
    np.savez_compressed(DATEI + '.teil.npz', schluessel=np.array(sch), t=tg, z=zz, lauf=jetzt.isoformat()[:16])
    os.replace(DATEI + '.teil.npz', DATEI)
    print(len(sch), 'Pegel ->', os.path.relpath(DATEI, ROOT))
    return 0


def pruefen(argv):
    """Modell-Windstau der letzten 30 Tage gegen gemessenen Windstau (Messung - eigene Vorhersage) am Echtzeitpegel."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import pegel_echtzeit as P
    import tiden_dienst as TD
    nur = [a for a in argv if not a.startswith('--')]
    M = dict(np.load(MT, allow_pickle=True))
    idx = {k: i for i, k in enumerate(M['schluessel'])}
    jetzt = dt.datetime.now(dt.timezone.utc)
    t0 = f'{jetzt - dt.timedelta(days=31):%Y-%m-%d}T00:00:00'
    t1 = f'{jetzt - dt.timedelta(days=1):%Y-%m-%d}T00:00:00'
    tmp = tempfile.mkdtemp(prefix='nws_')
    for key, la, lo in stationen(nur):
        if key not in idx:
            continue
        datei, name = key.split('|', 1)
        D, name = TD.finden(name, datei.replace('.txt', '.tcd'))
        s = D.saetze[name]
        zu = P.zuordnen(la, lo, s.hot)
        if not zu:
            print(key, 'kein Pegel')
            continue
        to, zo = P.messwerte(zu[0])
        pla, plo = M['punkt'][idx[key]][:2]
        f = os.path.join(tmp, 'p.nc')
        _subset(plo - 0.01, plo + 0.01, pla - 0.01, pla + 0.01, t0, t1, f, 'arco-time-series')
        r = _naechster(f, pla, plo)
        tm, zm = r[0], r[1]
        stau_m = zm - _matrix(tm) @ M['koef'][idx[key]].astype(float)
        # gemessener Windstau: Messung - eigene Vorhersage, auf volle Stunden (Mittel +-30 min)
        res = zo - np.asarray(D.wert(name, to), float)
        h = np.round(to / 3600) * 3600
        uh, inv = np.unique(h, return_inverse=True)
        rh = np.bincount(inv, weights=res) / np.bincount(inv)
        gem = dict(zip(uh, rh))
        paar = np.array([(gem[t], v) for t, v in zip(tm, stau_m) if t in gem and np.isfinite(v)])
        if len(paar) < 200:
            print(key, 'zu wenig Ueberlappung', len(paar))
            continue
        g, m = paar[:, 0] - np.median(paar[:, 0]), paar[:, 1] - np.median(paar[:, 1])
        print('%-55s %s %4d h | r %.2f | RMS gemessen %.2f  Modell %.2f  Differenz %.2f m | Spitzen gem. %+.2f/%+.2f Modell %+.2f/%+.2f' % (
            name[:55], zu[0]['id'][:8], len(g), np.corrcoef(g, m)[0, 1], g.std(), m.std(), (g - m).std(),
            g.min(), g.max(), m.min(), m.max()), flush=True)


def main(argv):
    if '--pruefen' in argv:
        pruefen(argv)
        return 0
    if '--modelltide' in argv:
        modelltide(argv)
        return 0
    if '--vorhersage' in argv:
        return vorhersage(argv)
    print(__doc__)
    return 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
