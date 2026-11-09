#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Wetterbedingter Wasserstand fuer Ostsee, Mittelmeer und Schwarzes Meer aus Copernicus Marine (Oliver 6.11.2026).

Dort dominiert das Wetter den Wasserstand; NOAA STOFS deckt diese Meere kaum ab.
Quellen (copernicusmarine-Toolbox, Zugang ~/.copernicusmarine):
  Ostsee        cmems_mod_bal_phy_anfc_PT1H-i, sla (Anomalie, stuendlich, ~9 Tage Vorhersage)
  Mittelmeer    cmems_mod_med_phy-ssh_anfc_4.2km-2D_PT1H-m, zos (absolut) + Tagesmittel P1D des letzten Jahres
  Schwarzes M.  cmems_mod_blk_phy-ssh_anfc_2.5km_PT1H-m, zos + P1D
  Limfjord W    cmems_mod_nws_phy-ssh_anfc_1.5km-2D_PT1H-i, zos + Jahresmittel der Stundenwerte (9.11.2026)
Je 1x1-Grad-Ausschnitt mit unseren Stationen ein Abruf; je Station der naechste Wasserpunkt des Modells.
zos -> Anomalie: minus Mittel der Tagesmittel des letzten Jahres. Danach wie bei STOFS die Modellgezeit
(M2, S2, K1, O1, M4) ueber das Fenster angepasst und abgezogen.
Ergebnis: water_levels/cmems_ssh/aktuell.npz (schluessel 'datei|satz', t, z[m]). py/windstau.py liest es zuerst.
Kein automatischer Abruf (Oliver 6.11.2026: erst, wenn die Seite operativ ist).

Usage: venv/bin/python py/windstau_cmems.py [--meer=ostsee|mittelmeer|schwarz|limfjord]
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
ZIEL = os.path.join(ROOT, 'water_levels/cmems_ssh')
DATEI = os.path.join(ZIEL, 'aktuell.npz')
CLI = os.path.join(ROOT, 'venv/bin/copernicusmarine')
MEERE = {
    'ostsee': dict(ds='cmems_mod_bal_phy_anfc_PT1H-i', var='sla', mittel=None),
    'mittelmeer': dict(ds='cmems_mod_med_phy-ssh_anfc_4.2km-2D_PT1H-m', var='zos',
                       mittel='cmems_mod_med_phy-ssh_anfc_4.2km_P1D-m'),
    'schwarz': dict(ds='cmems_mod_blk_phy-ssh_anfc_2.5km_PT1H-m', var='zos', mittel='cmems_mod_blk_phy-ssh_anfc_2.5km_P1D-m'),
    # 9.11.2026: westlicher Limfjord liegt ausserhalb des Ostsee-Modells (ab 9,04 O, Wasser erst ab Aggersund), STOFS hat in
    # Daenemark keinen Punkt. Nordsee-Modell (AMM15, 1,5 km, mit Tide) loest Nissum Bredning auf; ohne Tagesmittel ->
    # Jahresmittel aus den Stundenwerten. Nur bis 10 km zum Modellpunkt (Lemvig 2, Struer 8 km); Thisted 16, Skive,
    # Nykoebing Mors, Roenbjerg ~30 km bleiben ohne Kurve (Windstau kippt im Fjord von Ende zu Ende).
    'limfjord': dict(ds='cmems_mod_nws_phy-ssh_anfc_1.5km-2D_PT1H-i', var='zos', mittel='selbst', max_km=10),
}
PERIODEN = (12.4206, 12.0, 23.9345, 25.8193, 6.2103)


def meer(la, lo):
    if 56.3 < la < 57.2 and 8.1 < lo < 9.3:
        return 'limfjord'
    if 40.5 < la < 47.2 and 27.3 < lo < 42:
        return 'schwarz'
    if 53.3 < la < 66 and 9.3 < lo < 30.5:
        return 'ostsee'
    if 30 < la < 46 and -5.8 < lo < 36.5 and not (la > 40.5 and lo > 27.3):
        return 'mittelmeer'
    return None


def stationen():
    """-> {meer: {(zelle_lat, zelle_lon): [(schluessel, lat, lon)]}} aus den Markerdaten (keine Stroeme)."""
    d = json.load(open(os.path.join(ROOT, 'static/js/leaflet_markers_data.json'), encoding='utf-8'))['stations']
    out = {}
    for r in d:
        if r[5] == 1 or r[3] == 'bore':
            continue
        m = meer(r[1], r[2])
        if m:
            key = f"{r[3][:-4]}.txt|{r[8]}"
            out.setdefault(m, {}).setdefault((math.floor(r[1]), math.floor(r[2])), []).append((key, r[1], r[2]))
    return out


def _subset(ds, var, zelle, t0, t1, ziel):
    la, lo = zelle
    cmd = [CLI, 'subset', '-i', ds, '-v', var, '-x', str(lo - 0.05), '-X', str(lo + 1.05), '-y', str(la - 0.05),
           '-Y', str(la + 1.05), '-t', t0, '-T', t1, '-o', os.path.dirname(ziel), '-f', os.path.basename(ziel),
           '--overwrite']
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    if r.returncode or not os.path.exists(ziel):
        raise RuntimeError((r.stderr or r.stdout)[-300:])


def _bereinigen(th, v):
    X = [np.ones_like(th)]
    for p in PERIODEN:
        w = 2 * math.pi / p
        X += [np.cos(w * th), np.sin(w * th)]
    X = np.column_stack(X)
    ok = np.isfinite(v)
    if ok.sum() < 48:
        return None
    b, *_ = np.linalg.lstsq(X[ok], v[ok], rcond=None)
    return v - X[:, 1:] @ b[1:]


def main(argv):
    import xarray as xr
    opt = dict(a[2:].split('=', 1) for a in argv if a.startswith('--'))
    os.makedirs(ZIEL, exist_ok=True)
    jetzt = dt.datetime.now(dt.timezone.utc)
    t0 = f'{jetzt - dt.timedelta(days=1):%Y-%m-%d}T00:00:00'
    t1 = f'{jetzt + dt.timedelta(days=11):%Y-%m-%d}T00:00:00'
    m0 = f'{jetzt - dt.timedelta(days=366):%Y-%m-%d}T00:00:00'
    tmp = tempfile.mkdtemp(prefix='cmems_')
    ergebnis = {}
    if os.path.exists(DATEI) and opt.get('meer'):         # nur ein Meer neu: die anderen behalten
        alt = np.load(DATEI, allow_pickle=True)
        ergebnis = {k: (alt['t'], alt['z'][:, i]) for i, k in enumerate(alt['schluessel'])}
    for name, cfg in MEERE.items():
        if opt.get('meer') and opt['meer'] != name:
            continue
        zellen = stationen().get(name, {})
        print(f'{name}: {len(zellen)} Ausschnitte, {sum(len(v) for v in zellen.values())} Stationen', flush=True)
        for n, (zelle, st) in enumerate(sorted(zellen.items())):
            f = os.path.join(tmp, f'{name}_{zelle[0]}_{zelle[1]}.nc')
            try:
                _subset(cfg['ds'], cfg['var'], zelle, t0, t1, f)
                d = xr.open_dataset(f)
                v = d[cfg['var']]
                if 'depth' in v.dims:
                    v = v.isel(depth=0)
                ts = (v.time.values.astype('datetime64[s]').astype('int64')).astype(float)
                arr = v.values                                        # (t, lat, lon)
                lats, lons = v.latitude.values, v.longitude.values
                mittel = None
                if cfg['mittel']:
                    fm = f[:-3] + '_mittel.nc'
                    _subset(cfg['ds'] if cfg['mittel'] == 'selbst' else cfg['mittel'], cfg['var'], zelle, m0, t0, fm)
                    mittel = np.nanmean(xr.open_dataset(fm)[cfg['var']].values, axis=0)
            except Exception as e:  # noqa: BLE001
                print(f'  {zelle} Fehler: {e}', flush=True)
                continue
            gueltig = np.isfinite(arr).sum(axis=0) > 0.8 * len(ts)
            jj, ii = np.nonzero(gueltig)
            if not len(jj):
                continue
            for key, la, lo in st:
                km = 111.2 * np.hypot(lats[jj] - la, (lons[ii] - lo) * math.cos(math.radians(la)))
                k = int(np.argmin(km))
                if km[k] > cfg.get('max_km', 15):
                    continue
                z = arr[:, jj[k], ii[k]].astype(float)
                if mittel is not None:
                    z = z - mittel[jj[k], ii[k]]
                z = _bereinigen((ts - ts[0]) / 3600.0, z)
                if z is not None:
                    ergebnis[key] = (ts, z)
            print(f'  {n + 1}/{len(zellen)} {zelle}: {len(st)} Stationen', flush=True)
    if not ergebnis:
        print('nichts geladen')
        return 1
    tg = sorted({tuple(t) for t, _ in ergebnis.values()}, key=len)[-1]
    tg = np.array(tg)
    sch = sorted(ergebnis)
    z = np.column_stack([np.interp(tg, *ergebnis[k], left=np.nan, right=np.nan) for k in sch]).astype('float32')
    np.savez_compressed(DATEI + '.teil.npz', schluessel=np.array(sch), t=tg, z=z, lauf=jetzt.isoformat()[:16])
    os.replace(DATEI + '.teil.npz', DATEI)
    print(f'{len(sch)} Stationen -> {DATEI}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
