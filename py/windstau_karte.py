#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Kartenebene Windstau (Oliver 7.11.2026): wetterbedingter Wasserstand fuer Ostsee, Mittelmeer und
Schwarzes Meer als Rasterbilder fuer die Karte (static/js/windstau_layer.js).

Quellen und Bereinigung wie py/windstau_cmems.py, aber fuer das ganze Meer:
  Ostsee        cmems_mod_bal_phy_anfc_PT1H-i, sla (Anomalie)
  Mittelmeer    cmems_mod_med_phy-ssh_anfc_4.2km-2D_PT1H-m, zos minus Mittel der letzten 12 Monatsmittel (P1M)
  Schwarzes M.  cmems_mod_blk_phy-ssh_anfc_2.5km_PT1H-m, zos minus Mittel der letzten 12 Monatsmittel (P1M)
Raster vergroebert (Blockmittel) auf ~0,05-0,08 Grad, dann je Zelle Modellgezeit (M2, S2, K1, O1, M4) ueber das
ganze Fenster (-1 Tag bis Vorhersageende) angepasst und abgezogen. Bilder alle 3 h ab jetzt-3 h.

Ausgabe: static/windstau/ws_fNNN.bin (int16 mm, -32768 = Land; je Bild die Raster der Meere hintereinander)
         static/windstau/windstau_meta.json (Raster, Bilder, Zeiten).
Download je Lauf ~1 GB, Dauer ~10-20 min. Kein automatischer Abruf (Oliver 6.11.2026: erst, wenn die Seite
operativ ist).

Usage: venv/bin/python py/windstau_karte.py [--meer=ostsee|mittelmeer|schwarz|nordsee] [--behalten]
       nordsee: aus water_levels/nws_ssh/aktuell.npz (py/windstau_nws.py --vorhersage), kein eigener Download
       --behalten: heruntergeladene NetCDF-Dateien in water_levels/cmems_ssh/karte/ liegen lassen und wiederverwenden
"""
from __future__ import annotations

import datetime as dt
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLI = os.path.join(ROOT, 'venv/bin/copernicusmarine')
ROH = os.path.join(ROOT, 'water_levels/cmems_ssh/karte')
ZIEL = os.path.join(ROOT, 'static/windstau')
MEERE = {
    'ostsee': dict(ds='cmems_mod_bal_phy_anfc_PT1H-i', var='sla', mittel=None,
                   box=(9.0, 30.3, 53.0, 66.0), aufl=(0.083, 0.05), name='Baltic Sea'),
    'mittelmeer': dict(ds='cmems_mod_med_phy-ssh_anfc_4.2km-2D_PT1H-m', var='zos',
                       mittel='cmems_mod_med_phy-ssh_anfc_4.2km_P1M-m',
                       box=(-6.0, 36.3, 30.1, 46.0), aufl=(0.083, 0.083), name='Mediterranean Sea'),
    'schwarz': dict(ds='cmems_mod_blk_phy-ssh_anfc_2.5km_PT1H-m', var='zos',
                    mittel='cmems_mod_blk_phy-ssh_anfc_2.5km_P1M-m',
                    box=(27.2, 42.0, 40.5, 47.4), aufl=(0.05, 0.05), name='Black Sea'),
}
PERIODEN = (12.4206, 12.0, 23.9345, 25.8193, 6.2103)
SCHRITT_H = 3
LEER = -32768


def _subset(ds, var, box, t0, t1, ziel):
    x0, x1, y0, y1 = box
    cmd = [CLI, 'subset', '-i', ds, '-v', var, '-x', str(x0), '-X', str(x1), '-y', str(y0), '-Y', str(y1),
           '-t', t0, '-T', t1, '-o', os.path.dirname(ziel), '-f', os.path.basename(ziel), '--overwrite']
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
    if r.returncode or not os.path.exists(ziel):
        raise RuntimeError((r.stderr or r.stdout)[-400:])


def _frisch(f, alter=6 * 3600):
    """--behalten: Download wiederverwenden, solange er juenger ist als alter Sekunden."""
    import time
    return os.path.exists(f) and time.time() - os.path.getmtime(f) < alter


def _vergroebern(v, aufl):
    """xarray-DataArray (t, lat, lon) -> Blockmittel auf ~aufl=(dlon, dlat) Grad; Zellen mit etwas Wasser gelten."""
    dlon = float(abs(v.longitude.values[1] - v.longitude.values[0]))
    dlat = float(abs(v.latitude.values[1] - v.latitude.values[0]))
    fx, fy = max(1, round(aufl[0] / dlon)), max(1, round(aufl[1] / dlat))
    if fx > 1 or fy > 1:
        v = v.coarsen(longitude=fx, latitude=fy, boundary='trim').mean(skipna=True)
    return v


def _gezeit_ab(ts_h, arr):
    """arr (t, n) -> arr minus angepasster Gezeit; Spalten mit Luecken bleiben NaN, wo Daten fehlen."""
    X = [np.ones_like(ts_h)]
    for p in PERIODEN:
        w = 2 * math.pi / p
        X += [np.cos(w * ts_h), np.sin(w * ts_h)]
    X = np.column_stack(X)
    voll = np.isfinite(arr).all(axis=0)
    out = np.full_like(arr, np.nan)
    if voll.any():
        b, *_ = np.linalg.lstsq(X, arr[:, voll], rcond=None)
        out[:, voll] = arr[:, voll] - X[:, 1:] @ b[1:]
    return out


def meer_laden(name, cfg, t0, t1, m0, m1, ordner):
    import xarray as xr
    f = os.path.join(ordner, f'{name}.nc')
    if not _frisch(f):
        print(f'{name}: lade {cfg["ds"]} {t0} .. {t1}', flush=True)
        _subset(cfg['ds'], cfg['var'], cfg['box'], t0, t1, f)
    v = xr.open_dataset(f)[cfg['var']]
    if 'depth' in v.dims:
        v = v.isel(depth=0)
    v = v.sortby('latitude', ascending=False)
    v = _vergroebern(v, cfg['aufl']).load()
    arr = v.values.astype('float32')                                   # (t, ny, nx)
    ts = v.time.values.astype('datetime64[s]').astype('int64').astype(float)
    if cfg['mittel']:
        fm = os.path.join(ordner, f'{name}_mittel.nc')
        if not _frisch(fm, 20 * 86400):
            print(f'{name}: lade Monatsmittel {m0} .. {m1}', flush=True)
            _subset(cfg['mittel'], cfg['var'], cfg['box'], m0, m1, fm)
        vm = xr.open_dataset(fm)[cfg['var']]
        if 'depth' in vm.dims:
            vm = vm.isel(depth=0)
        vm = _vergroebern(vm.sortby('latitude', ascending=False), cfg['aufl']).load()
        with np.errstate(all='ignore'):
            import warnings
            warnings.simplefilter('ignore', RuntimeWarning)
            mittel = np.nanmean(vm.values, axis=0)
        if mittel.shape != arr.shape[1:]:
            raise RuntimeError(f'Mittel {mittel.shape} passt nicht zu {arr.shape[1:]}')
        arr = arr - mittel[None]
    if name == 'mittelmeer':                                         # Atlantikteil des Modells weglassen
        la2, lo2 = np.meshgrid(v.latitude.values, v.longitude.values, indexing='ij')
        arr[:, (lo2 < -5.6) | ((la2 > 42) & (lo2 < 0))] = np.nan
    ny, nx = arr.shape[1:]
    z = _gezeit_ab((ts - ts[0]) / 3600.0, arr.reshape(len(ts), -1)).reshape(arr.shape)
    lats, lons = v.latitude.values, v.longitude.values
    gitter = dict(name=cfg['name'], nx=int(nx), ny=int(ny), la1=float(lats[0]), lo1=float(lons[0]),
                  dy=float(abs(lats[1] - lats[0])), dx=float(abs(lons[1] - lons[0])))
    wasser = int(np.isfinite(z).any(axis=0).sum())
    print(f'{name}: {nx}x{ny} Zellen ({wasser} Wasser), {len(ts)} Stunden, '
          f'Spanne {np.nanmin(z):+.2f} .. {np.nanmax(z):+.2f} m', flush=True)
    return gitter, ts, z


NWS_AKTUELL = os.path.join(ROOT, 'water_levels/nws_ssh/aktuell.npz')
NWS_MT = os.path.join(ROOT, 'water_levels/nws_ssh/modelltide.npz')
NWS_MASKE = os.path.join(ROOT, 'water_levels/nws_ssh/karte_maske.npz')
NWS_RADIUS_KM = 60.0


def nordsee_laden():
    """Nordsee/Aermelkanal/Britische Inseln/Biskaya (9.11.2026): kein Raster-Download -- das Modell rechnet die Tide mit,
    die Modelltide kennen wir nur an Punkten (py/windstau_nws.py: Pegel + virtuelle Punkte auf See). Das Bild ist eine
    Abstandsgewichtung (1/(d^2 + 5 km^2), Radius 60 km) dieser Punktreihen; Land und Ostsee/Limfjord (eigene Raster)
    bleiben leer."""
    from scipy.spatial import cKDTree
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import windstau_nws as W
    A = np.load(NWS_AKTUELL, allow_pickle=True)
    M = np.load(NWS_MT, allow_pickle=True)
    pos = {k: p for k, p in zip(M['schluessel'], M['punkt'])}
    keys = [k for k in A['schluessel'] if k in pos]
    sp = [list(A['schluessel']).index(k) for k in keys]
    pla = np.array([pos[k][0] for k in keys], float)
    plo = np.array([pos[k][1] for k in keys], float)
    ts = A['t'].astype(float)
    werte = A['z'][:, sp].astype(float)                                   # (t, n)
    dx, dy = 0.1, 0.06
    lo1, lo2 = math.floor((plo.min() - 0.5) * 10) / 10, math.ceil((plo.max() + 0.5) * 10) / 10
    la1, la2 = math.ceil((pla.max() + 0.5) / dy) * dy, math.floor((pla.min() - 0.5) / dy) * dy
    lons = np.arange(lo1, lo2 + dx / 2, dx)
    lats = np.arange(la1, la2 - dy / 2, -dy)
    LA, LO = np.meshgrid(lats, lons, indexing='ij')
    lat0 = math.radians(54.0)
    if os.path.exists(NWS_MASKE) and np.load(NWS_MASKE)['form'].tolist() == [len(lats), len(lons), lo1, la1]:
        wasser = np.load(NWS_MASKE)['wasser']
    else:
        import osm_land
        zellen = [(la, lo) for la, lo in zip(LA.ravel(), LO.ravel())]
        baum = cKDTree(np.column_stack([plo * 111.2 * math.cos(lat0), pla * 111.2]))
        d, _ = baum.query(np.column_stack([LO.ravel() * 111.2 * math.cos(lat0), LA.ravel() * 111.2]))
        nah = d <= NWS_RADIUS_KM
        kand = [z for z, n in zip(zellen, nah) if n and W.gebiet(*z)]
        L = osm_land.Land(kand)
        land = {z for z in kand if L.ist_land(*z)}
        wasser = np.array([n and W.gebiet(*z) and z not in land for z, n in zip(zellen, nah)]).reshape(LA.shape)
        np.savez_compressed(NWS_MASKE, wasser=wasser, form=np.array([len(lats), len(lons), lo1, la1]))
    # Gewichte Zelle -> Punkte
    cx = LO[wasser] * 111.2 * np.cos(np.radians(LA[wasser]))
    cy = LA[wasser] * 111.2
    px = plo * 111.2 * np.cos(np.radians(pla))
    py = pla * 111.2
    baum = cKDTree(np.column_stack([px, py]))
    nachbarn = baum.query_ball_point(np.column_stack([cx, cy]), NWS_RADIUS_KM)
    from scipy.sparse import csr_matrix
    zeilen, spalten, gew = [], [], []
    for i, nb in enumerate(nachbarn):
        for j in nb:
            d2 = (cx[i] - px[j]) ** 2 + (cy[i] - py[j]) ** 2
            zeilen.append(i)
            spalten.append(j)
            gew.append(1.0 / (d2 + 25.0))
    Wm = csr_matrix((gew, (zeilen, spalten)), shape=(len(cx), len(keys)))
    ok = np.isfinite(werte)
    zaehler = Wm @ np.where(ok, werte, 0.0).T                            # (zellen, t)
    nenner = Wm @ ok.T.astype(float)
    with np.errstate(all='ignore'):
        feld = zaehler / nenner
    z = np.full((len(ts), len(lats), len(lons)), np.nan, dtype='float32')
    z[:, wasser] = feld.T
    gitter = dict(name='North Sea / Atlantic shelf', nx=int(len(lons)), ny=int(len(lats)), la1=float(lats[0]),
                  lo1=float(lons[0]), dy=dy, dx=dx)
    print(f'nordsee: {len(lons)}x{len(lats)} Zellen ({int(wasser.sum())} Wasser), {len(keys)} Punkte, {len(ts)} Stunden, '
          f'Spanne {np.nanmin(z):+.2f} .. {np.nanmax(z):+.2f} m', flush=True)
    return gitter, ts, z


def main(argv):
    opt = dict((a[2:].split('=', 1) + [''])[:2] for a in argv if a.startswith('--'))
    jetzt = dt.datetime.now(dt.timezone.utc)
    t0 = f'{jetzt - dt.timedelta(days=1):%Y-%m-%d}T00:00:00'
    t1 = f'{jetzt + dt.timedelta(days=11):%Y-%m-%d}T00:00:00'
    erster = jetzt.replace(day=1)
    m1 = f'{erster - dt.timedelta(days=1):%Y-%m-%d}T00:00:00'
    m0 = f'{(erster - dt.timedelta(days=370)).replace(day=1):%Y-%m-%d}T00:00:00'
    if 'behalten' in opt:
        ordner = ROH
        os.makedirs(ordner, exist_ok=True)
    else:
        ordner = tempfile.mkdtemp(prefix='windstau_karte_')
    teile = []
    for name, cfg in MEERE.items():
        if opt.get('meer') and opt['meer'] != name:
            continue
        try:
            teile.append(meer_laden(name, cfg, t0, t1, m0, m1, ordner))
        except Exception as e:  # noqa: BLE001
            print(f'{name}: Fehler {e}', flush=True)
    if (not opt.get('meer') or opt['meer'] == 'nordsee') and os.path.exists(NWS_AKTUELL):
        try:
            teile.append(nordsee_laden())
        except Exception as e:  # noqa: BLE001
            print(f'nordsee: Fehler {e!r}', flush=True)
    if not teile:
        print('nichts geladen')
        return 1

    # Bildzeiten: alle 3 h ab der letzten vollen 3-h-Marke vor jetzt-3 h bis zum spaetesten Ende
    start = (int(jetzt.timestamp()) - 3 * 3600) // (SCHRITT_H * 3600) * SCHRITT_H * 3600
    ende = max(ts[-1] for _, ts, _ in teile)
    zeiten = list(range(start, int(ende) + 1, SCHRITT_H * 3600))
    neu = ZIEL + '.neu'
    shutil.rmtree(neu, ignore_errors=True)
    os.makedirs(neu)
    gitter, off = [], 0
    for g, _, _ in teile:
        gitter.append(dict(g, offset=off))
        off += g['nx'] * g['ny']
    bilder = []
    for k, t in enumerate(zeiten):
        stueck = []
        for (g, ts, z) in teile:
            i = np.searchsorted(ts, t)
            if i < len(ts) and ts[i] == t:
                f = z[i]
            else:
                f = np.full(z.shape[1:], np.nan, dtype='float32')       # Meer hat hier keine Vorhersage mehr
            mm = np.where(np.isfinite(f), np.clip(np.round(f * 1000), -32000, 32000), LEER).astype('<i2')
            stueck.append(mm.ravel())
        datei = f'ws_f{k:03d}.bin'
        np.concatenate(stueck).tofile(os.path.join(neu, datei))
        bilder.append(dict(file=datei, t=int(t),
                           label=dt.datetime.fromtimestamp(t, dt.timezone.utc).strftime('%d.%m. %H:%M UTC')))
    meta = dict(source='Copernicus Marine Service (BAL/MED/BLK/NWS analysis & forecast), detided',
                generated=jetzt.isoformat(timespec='seconds'), schritt_h=SCHRITT_H, grids=gitter, frames=bilder,
                ende={g['name']: int(ts[-1]) for g, ts, _ in teile})
    json.dump(meta, open(os.path.join(neu, 'windstau_meta.json'), 'w'), indent=1)
    alt = ZIEL + '.alt'
    shutil.rmtree(alt, ignore_errors=True)
    if os.path.exists(ZIEL):
        os.replace(ZIEL, alt)
    os.replace(neu, ZIEL)
    shutil.rmtree(alt, ignore_errors=True)
    if 'behalten' not in opt:
        shutil.rmtree(ordner, ignore_errors=True)
    groesse = sum(os.path.getsize(os.path.join(ZIEL, b['file'])) for b in bilder)
    print(f'{len(bilder)} Bilder ({groesse / 1e6:.1f} MB) -> {ZIEL}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
