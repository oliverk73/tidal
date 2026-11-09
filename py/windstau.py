#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Windstau-Vorhersage (Oliver 6.11.2026): erwarteter Wasserstand = astronomische Vorhersage + Windstau.

Quelle: NOAA STOFS-2D-Global, Stationsausgabe stofs_2d_glo.tHHz.points.swl.nc (nicht-tidaler Wasserstand,
6 min, 7,5 Tage, 1687 Punkte, fast alle in den USA; ~20 IOC-Pegel in Europa). Vier Laeufe am Tag; der neueste
verfuegbare wird alle 6 h geholt (systemd --user: windstau.timer) -> water_levels/stofs/aktuell.npz.

Bereinigung: das grobe Modell trifft die Gezeiten in Buchten/Fluessen nicht; die Differenz schwingt mit der
Tide mit (Anchorage M2 0,24 m). Je Punkt werden M2, S2(~), K1, O1, M4 ueber das Vorhersagefenster angepasst und
abgezogen (ein 25-h-Mittel wuerde Sturmspitzen halbieren). Mittel/Anomalie bleibt erhalten.
Zuordnung: NOAA-Nummer im Punktnamen = noaa_station_id des Satzes, sonst naechster Punkt bis 5 km.

Usage: venv/bin/python py/windstau.py [laden]
"""
from __future__ import annotations

import datetime as dt
import math
import os
import re
import sys
import tempfile
import urllib.request

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ZIEL = os.path.join(ROOT, 'water_levels/stofs')
DATEI = os.path.join(ZIEL, 'aktuell.npz')
URL = 'https://nomads.ncep.noaa.gov/pub/data/nccf/com/stofs/prod/stofs_2d_glo.{d}/stofs_2d_glo.t{h:02d}z.points.swl.nc'
PERIODEN = (12.4206, 12.0, 23.9345, 25.8193, 6.2103)     # M2, S2, K1, O1, M4 (h)
MAX_KM = 5.0
MAX_LECK = 0.12   # m: halbtaegiger Gezeitenrest im Rohwert; darueber trifft das Modell die Tide nicht (Anchorage 0,24:
                  # STOFS -0,66 m gegen gemessen +0,21 m) -> kein Windstau anzeigen. Boston/Philadelphia/Galveston ~0,1 m genau.


def laden():
    """Neuesten verfuegbaren Lauf holen und als npz ablegen. -> Laufzeit (UTC) oder None."""
    import netCDF4 as nc
    os.makedirs(ZIEL, exist_ok=True)
    jetzt = dt.datetime.now(dt.timezone.utc)
    for tage in (0, 1):
        tag = jetzt - dt.timedelta(days=tage)
        for h in (18, 12, 6, 0):
            lauf = tag.replace(hour=h, minute=0, second=0, microsecond=0)
            if lauf > jetzt - dt.timedelta(hours=4):          # Lauf braucht ~4 h bis zur Veroeffentlichung
                continue
            if os.path.exists(DATEI) and str(np.load(DATEI)['lauf']) >= lauf.isoformat():
                return None                                      # schon aktuell
            tmp = os.path.join(tempfile.mkdtemp(prefix='stofs_'), 'swl.nc')
            try:
                req = urllib.request.Request(URL.format(d=f'{tag:%Y%m%d}', h=h), headers={'User-Agent': 'tiden-pruefung/1.0'})
                with urllib.request.urlopen(req, timeout=300) as r, open(tmp, 'wb') as f:
                    f.write(r.read())
            except Exception:  # noqa: BLE001 -- dieser Lauf noch nicht da
                continue
            d = nc.Dataset(tmp)
            namen = np.array([b''.join(x).decode(errors='ignore').strip() for x in d.variables['station_name'][:].data])
            t = nc.num2date(d.variables['time'][:], d.variables['time'].units, only_use_cftime_datetimes=False)
            ts = np.array([x.replace(tzinfo=dt.timezone.utc).timestamp() for x in t])
            z = np.ma.filled(d.variables['zeta'][:].astype('float32'), np.nan)
            lon = np.asarray(d.variables['x'][:], float)
            lon = np.where(lon > 180, lon - 360, lon)
            lat = np.asarray(d.variables['y'][:], float)
            z, leck = bereinigen(ts, z)
            np.savez_compressed(DATEI + '.teil.npz', namen=namen, t=ts, z=np.nan_to_num(z, nan=-99).astype('float32'),
                                lat=lat, lon=lon, leck=leck, lauf=lauf.isoformat())
            os.replace(DATEI + '.teil.npz', DATEI)
            return lauf
    return None


def bereinigen(ts, z):
    """Gezeitenreste (Modelltide - harmonische Tide) je Punkt abziehen; Mittel bleibt. -> (z, leck_m2)"""
    th = (ts - ts[0]) / 3600.0
    X = [np.ones_like(th)]
    for p in PERIODEN:
        w = 2 * math.pi / p
        X += [np.cos(w * th), np.sin(w * th)]
    X = np.column_stack(X)
    out = z.copy()
    leck = np.full(z.shape[1], np.nan)
    for i in range(z.shape[1]):
        v = z[:, i]
        ok = np.isfinite(v)
        if ok.sum() < 100:
            out[:, i] = np.nan
            continue
        b, *_ = np.linalg.lstsq(X[ok], v[ok], rcond=None)
        out[:, i] = v - X[:, 1:] @ b[1:]
        leck[i] = float(np.std(X[:, 1:] @ b[1:]) * math.sqrt(2))   # Amplitude des ganzen Gezeitenrests (M2/S2 in 7,5 d
                                                                     # nicht trennbar, daher nicht M2 allein)
    return out, leck


_CACHE = {}


def _daten():
    if not os.path.exists(DATEI):
        return None
    m = os.path.getmtime(DATEI)
    if _CACHE.get('m') != m:
        d = np.load(DATEI)
        _CACHE.update(m=m, d={k: d[k] for k in d.files})
    return _CACHE['d']


def fuer(lat, lon, noaa_id=None):
    """-> dict(t, z [m], lauf, punkt, km) fuer den passenden STOFS-Punkt oder None."""
    d = _daten()
    if d is None:
        return None
    i = None
    if noaa_id:
        treffer = [j for j, n in enumerate(d['namen']) if re.search(rf'\b{re.escape(noaa_id)}\b', str(n))]
        if treffer:
            i = treffer[0]
    km = 111.2 * np.hypot(d['lat'] - lat, (d['lon'] - lon) * math.cos(math.radians(lat)))
    if i is None:
        j = int(np.nanargmin(km))
        if km[j] > MAX_KM:
            return None
        i = j
    z = d['z'][:, i].astype(float)
    z[z < -90] = np.nan
    if not np.isfinite(z).any() or not (d['leck'][i] <= MAX_LECK):
        return None
    return dict(t=d['t'], z=z, lauf=str(d['lauf']), punkt=str(d['namen'][i]), km=float(km[i]))


CMEMS = os.path.join(ROOT, 'water_levels/cmems_ssh/aktuell.npz')
NWS = os.path.join(ROOT, 'water_levels/nws_ssh/aktuell.npz')       # py/windstau_nws.py (9.11.2026, Modelltide abgezogen)
_CM = {}


def _copernicus(pfad, key):
    if not os.path.exists(pfad):
        return None
    m = os.path.getmtime(pfad)
    c = _CM.get(pfad)
    if not c or c['m'] != m:
        d = np.load(pfad, allow_pickle=True)
        c = _CM[pfad] = dict(m=m, idx={k: i for i, k in enumerate(d['schluessel'])}, t=d['t'], z=d['z'], lauf=str(d['lauf']))
    i = c['idx'].get(key)
    if i is None:
        return None
    z = c['z'][:, i].astype(float)
    if np.isfinite(z).sum() <= 24:
        return None
    return dict(t=c['t'], z=z, lauf=c['lauf'], punkt='Copernicus Marine', km=0.0, quelle='cmems')


def fuer_satz(datei, satz, lat, lon, noaa_id=None):
    """Copernicus (Ostsee/Mittelmeer/Schwarzes Meer/Limfjord, dann Nordsee/Atlantik) fuer genau diesen Satz, sonst STOFS."""
    key = f'{os.path.basename(datei)}|{satz}'
    for pfad in (CMEMS, NWS):
        r = _copernicus(pfad, key)
        if r:
            return r
    r = fuer(lat, lon, noaa_id)
    if r:
        r['quelle'] = 'stofs'
    return r


def main(argv):
    lauf = laden()
    print('STOFS:', lauf.isoformat() if lauf else 'unveraendert/kein neuer Lauf', '->', DATEI)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
