#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""NOAA NCEI Global Ocean Currents Database (GOCD, eingestellt 04/2025, Dateien weiter unter
https://www.ncei.noaa.gov/data/oceans/ncei/gocd/) -> Stromfits (Oliver 14.11.2026).

Inventare gocd_cmetr_inv.csv (Stroemungsmesser) und gocd_madcp_inv.csv (verankerte ADCP) -> quellen/tidal_streams/NCEI_GOCD/kandidaten.csv
(Vorlauf 14.11.: >= 25 Tage, <= 30 km vom naechsten Pegelsatz, Stroemungsmesser bis 60 m). Hier: nur Reihen > 5 km vom
naechsten Stromsatz, je 3-km-Ort eine: flachster Stroemungsmesser, sonst ADCP (Zellen 5-25 m, nicht in den obersten 12 %
der Wassertiefe), bei Gleichstand die laengste. GOCD-3.0-NetCDF: u/v m/s, time Tage seit 1900, Flags 1/2 = gut.
Stundenmittel mittig gestempelt, Fit wie py/ios_stroemung.py. Dateien -> quellen/tidal_streams/NCEI_GOCD/nc/, fits.pkl, help/gocd_stroemung.csv.

Usage: venv/bin/python py/gocd_stroemung.py
"""
import csv
import os
import pickle
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import netCDF4 as nc
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cmems_stroemung_nachholen as C                               # noqa: E402
import stroemung_kopplung as K                                      # noqa: E402
from ios_stroemung import FREI                                      # noqa: E402

ROOT = K.ROOT
D = os.path.join(ROOT, 'quellen/tidal_streams/NCEI_GOCD')
URL = 'https://www.ncei.noaa.gov/data/oceans/ncei/gocd/'


def auswahl():
    E = list(csv.DictReader(open(os.path.join(D, 'kandidaten.csv'))))
    for e in E:
        for k in ('lat', 'lon', 'tief', 'boden', 'pegel_km', 'strom_km'):
            e[k] = float(e[k])
        e['tage'] = int(e['tage'])
    E = [e for e in E if e['strom_km'] > 5]
    cl = []
    for e in sorted(E, key=lambda e: -e['tage']):
        for c in cl:
            if abs(c[0]['lat'] - e['lat']) < 0.03 and abs(c[0]['lon'] - e['lon']) < 0.045:
                c.append(e)
                break
        else:
            cl.append([e])
    wahl = []
    for c in cl:
        cur = sorted([e for e in c if e['typ'] == 'cmetr'], key=lambda e: (e['tief'], -e['tage']))
        wahl.append(cur[0] if cur else max(c, key=lambda e: e['tage']))
    return wahl


def laden(e):
    f = os.path.join(D, 'nc', os.path.basename(e['url']))
    if os.path.exists(f):
        return f
    os.makedirs(os.path.dirname(f), exist_ok=True)
    for v in range(4):
        try:
            rq = urllib.request.Request(URL + e['url'], headers={'User-Agent': 'weather-tides/1.0'})
            open(f + '.tmp', 'wb').write(urllib.request.urlopen(rq, timeout=600).read())
            os.rename(f + '.tmp', f)
            return f
        except Exception as ex:                                     # noqa: BLE001
            print('   Abruf', e['url'], str(ex)[:60], flush=True)
            time.sleep(20 * (v + 1))
    return None


def reihe(f):
    """-> (DataFrame u,v m/s Stundenmittel, Tiefe m, lat, lon) oder None."""
    d = nc.Dataset(f)
    t = pd.to_datetime(np.ma.filled(d['time'][:], np.nan).astype(float), unit='D', origin='1900-01-01').round('1s')
    u, v = np.ma.filled(d['u'][:], np.nan).astype(float), np.ma.filled(d['v'][:], np.nan).astype(float)
    qu = np.ma.filled(d['u_quality_flag'][:], 9)
    u = np.where(np.isin(qu, (1, 2)), u, np.nan)
    v = np.where(np.isin(np.ma.filled(d['v_quality_flag'][:], 9), (1, 2)), v, np.nan)
    tiefe = np.ma.filled(d['depth'][:], np.nan).astype(float)
    boden = float(np.ma.filled(d['seafloor_depth'][:], np.nan)) if 'seafloor_depth' in d.variables else float('nan')
    if u.ndim == 2:                                                 # ADCP: Zellen 5-25 m, nicht im obersten 12 % (Reflex)
        ok = (tiefe >= 5) & (tiefe <= 25) & (~np.isfinite(boden) | (tiefe >= 0.12 * boden))
        if not ok.any():
            gut = np.where((tiefe >= 5) & (tiefe <= 60) & (~np.isfinite(boden) | (tiefe >= 0.12 * boden)))[0]
            if not len(gut):
                return None
            ok = np.zeros_like(ok)
            ok[gut[np.argmin(tiefe[gut])]] = True
        u, v = np.nanmean(u[:, ok], axis=1), np.nanmean(v[:, ok], axis=1)
        z = float(np.nanmean(tiefe[ok]))
    else:
        z = float(tiefe)
    df = pd.DataFrame({'u': u, 'v': v}, index=t).dropna()
    df = df[(df['u'].abs() < 6) & (df['v'].abs() < 6)].sort_index()
    if len(df) < 24 * 25:
        return None
    return C.stundenmittel(df), z, float(d['latitude'][:]), float(d['longitude'][:])


def main():
    W = auswahl()
    print(len(W), 'Orte', flush=True)
    with ThreadPoolExecutor(4) as ex:
        dateien = list(ex.map(laden, W))
    zeilen, fits = [], []
    for i, (e, f) in enumerate(zip(W, dateien)):
        x = reihe(f) if f else None
        if not x or len(x[0]) < 24 * 25:
            print('%3d %-40s keine brauchbare Reihe' % (i, os.path.basename(e['url'])), flush=True)
            continue
        df, z, lat, lon = x
        tage = (df.index[-1] - df.index[0]).total_seconds() / 86400
        try:
            if tage >= 182.6:
                r, kop = K.fit(df, FREI, {}), ''
            else:
                verh, pegel, km = K.verhaeltnisse(lat, lon)
                kopplung = {b: (h, *verh[b]) for h, b in K.noetig(df, FREI) if b in verh}
                r = K.fit(df, [k for k in FREI if k not in kopplung and k not in ('MSF', 'MF', 'MM')], kopplung)
                kop = '%s an %s (%.0f km)' % ('/'.join(kopplung), pegel, km)
        except Exception as ex:                                     # noqa: BLE001
            print('%3d %-40s Fit-Fehler %s' % (i, os.path.basename(e['url']), str(ex)[:60]), flush=True)
            continue
        print('%3d %-40s %4.0f T %3.0f m  r2 %.2f  M2 %.2f kn  S2 %.2f  K1 %.2f' % (
            i, os.path.basename(e['url'])[:40], tage, z, r['r2'], r['m2'], r['s2'], r['k1']), flush=True)
        e2 = dict(e, datei=os.path.basename(e['url']), tief=z, lat=lat, lon=lon)
        zeilen.append(dict(datei=e2['datei'], typ=e['typ'], geraet=e['gerät'], lat=lat, lon=lon, tief=round(z), tage=round(tage),
                           von=df.index[0].date(), bis=df.index[-1].date(), r2=round(r['r2'], 3), m2_kn=round(r['m2'], 3),
                           s2_kn=round(r['s2'], 3), k1_kn=round(r['k1'], 3), achse=round(r['achse']), kopplung=kop))
        fits.append((e2, r, kop, tage))
    with open(os.path.join(ROOT, 'harmonics/help/gocd_stroemung.csv'), 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=list(zeilen[0]))
        w.writeheader()
        w.writerows(zeilen)
    pickle.dump(fits, open(os.path.join(D, 'fits.pkl'), 'wb'))
    print(len(zeilen), 'gefittet')


if __name__ == '__main__':
    main()
