#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""BODC-Stroemungsmesserreihen fitten (Oliver 19.10.2026).

Liest alle Lieferungen currents/BODC/RN-*/ (QXF = NetCDF; Datum AADYAA01 = Tage seit
1760-01-01, AAFDZZ01 = Tagesbruchteil; Flag ' ' = gut). Position, Tiefe und Projekt aus
bodc_series_metadata_summary.csv. Stroemung als Geschwindigkeit/Richtung (LCSAEL01 cm/s,
LCDAEL01 wohin) oder als Komponenten (LCEWAP01/LCNSAP01 o. ae.).
Achtung: Die NetCDF-Fassungen der Lieferung zaehlen in Julianischen Tagen, xarray macht daraus
den julianischen Kalender (13 Tage falsch) -- deshalb hier nur QXF.

Fit wie py/cmems_stroemung_nachholen.analyse (Hauptachse, UTide in Knoten); Reihen ab 25 Tagen.
Schreibt harmonics/help/bodc_stroemung_<datum>.csv und ..._<datum>.txt (Bloecke, Name = BODC-Nr.).
Usage: venv/bin/python py/bodc_stroemung.py
"""
import csv
import datetime as dt
import glob
import math
import os
import sys
from datetime import date

import netCDF4
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cmems_stroemung_nachholen as C                               # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EPOCHE = dt.datetime(1760, 1, 1)
MIN_STUNDEN = 600


def metadaten():
    out = {}
    for f in glob.glob(os.path.join(ROOT, 'currents/BODC/RN-*/bodc_series_metadata_summary.csv')):
        L = open(f, encoding='latin-1').read().split('\n')
        i = next(k for k, l in enumerate(L) if l.startswith('BODC reference'))
        for r in csv.DictReader(L[i:]):
            if r.get('BODC reference'):
                r['_dir'] = os.path.dirname(f)
                out[r['BODC reference'].strip()] = r
    return out


def reihe(pfad, boden=float('nan')):
    """-> (DataFrame u,v m/s stuendlich, Tiefe der gewaehlten Ebene) oder None."""
    d = netCDF4.Dataset(pfad)
    v = d.variables
    if 'AADYAA01' not in v or 'ALATGP01' in v:          # Profile ohne Zeit / Schiffs-ADCP in Fahrt
        return None
    tage = np.asarray(v['AADYAA01'][:], float) + np.asarray(v['AAFDZZ01'][:], float)
    t = pd.to_datetime(EPOCHE) + pd.to_timedelta(np.round(tage * 86400), unit='s')

    def wert(n):
        x = np.ma.filled(np.ma.asarray(v[n][:], float), np.nan)
        if 'F' + n in v:
            fl = np.asarray(v['F' + n][:]).astype('S1')
            x = np.where(fl == b' ', x, np.nan)
        return x
    if 'LCSAEL01' in v and 'LCDAEL01' in v:
        s, r = wert('LCSAEL01') / 100, wert('LCDAEL01')
        u, w = s * np.sin(np.radians(r)), s * np.cos(np.radians(r))
    else:
        ue = next((n for n in v if n.startswith('LCEW')), None)
        un = next((n for n in v if n.startswith('LCNS')), None)
        if not ue or not un:
            return None
        u, w = wert(ue) / 100, wert(un) / 100
    tiefe = float('nan')
    if u.ndim == 2:                                      # ADCP: flachste Ebene mit >= 80 % der besten Abdeckung
        n = np.isfinite(u).sum(axis=0)
        if n.max() == 0:
            return None
        if 'HBINAA01' in v:                              # Hoehe ueber Grund (Liverpool Bay): Tiefe = Wassertiefe - Hoehe
            hab = np.asarray(v['HBINAA01'][:], float)
            wt = np.nanmedian(wert('ASLVMWHA')) if 'ASLVMWHA' in v else boden
            dep = np.tile((wt if math.isfinite(wt) else 1000) - hab, (u.shape[0], 1))
        else:
            dep = wert('DBINAA01') if 'DBINAA01' in v else np.tile(np.arange(u.shape[1], dtype=float), (u.shape[0], 1))
        if dep.ndim == 1:
            dep = np.tile(dep, (u.shape[0], 1)) if dep.shape[0] == u.shape[1] else np.tile(dep[:, None], (1, u.shape[1]))
        kand = [j for j in range(u.shape[1]) if n[j] >= 0.8 * n.max()]
        if 'HBINAA01' in v:                              # Reichweite: ferne Zellen messen fast nichts (Dover 1 MHz)
            sp = np.nanmedian(np.hypot(u, w), axis=0)
            kand = [j for j in kand if sp[j] >= 0.8 * np.nanmax(sp[kand])]
        tiefen = [np.nanmedian(dep[:, j]) if np.isfinite(dep[:, j]).any() else np.inf for j in kand]
        j = kand[int(np.argmin(np.abs(tiefen)))]
        u, w, tiefe = u[:, j], w[:, j], tiefen[int(np.argmin(np.abs(tiefen)))]
    df = pd.DataFrame({'u': u, 'v': w}, index=t).dropna()
    df = df[(df['u'].abs() < 5) & (df['v'].abs() < 5)]
    return df.resample('1h').mean().dropna(), tiefe


def main():
    M = metadaten()
    tag = date.today().strftime('%Y%m%d')
    zeilen, bloecke = [], []
    for ref, m in sorted(M.items(), key=lambda x: int(x[0])):
        pfad = os.path.join(m['_dir'], 'b%07d.qxf' % int(ref))
        if not os.path.exists(pfad):
            continue
        try:
            x = reihe(pfad, float(m['Sea floor depth (m)'] or 'nan'))
            df, adcp_tiefe = x if x else (None, None)
        except Exception as e:                                       # noqa: BLE001
            print('  Fehler', ref, str(e)[:60])
            continue
        if df is None or len(df) < MIN_STUNDEN:
            continue
        lat, lon = float(m['Latitude A']), float(m['Longitude A'])
        try:
            r = C.analyse(df, lat, None if len(df) >= 8766 else 'auto')
        except Exception as e:                                       # noqa: BLE001
            print('  UTide', ref, str(e)[:60])
            continue
        tiefe = adcp_tiefe if adcp_tiefe is not None and math.isfinite(adcp_tiefe) else float(m['Series depth minimum (m)'] or 'nan')
        boden = float(m['Sea floor depth (m)'] or 'nan')
        k = dict(code='BODC%s' % ref, inst=m.get('Organisation', '')[:60] or 'BODC')
        b = C.block(k, r, lat, lon, tiefe).replace('# source: CMEMS in-situ, UTide analysis',
                                                     '# source: BODC current meter, UTide analysis')
        b = b.replace('# Harmonic constants derived from CMEMS in-situ', '# Harmonic constants derived from BODC current meter')
        b = b.replace('station_id_context: CMEMS-BODC', 'station_id_context: BODC-').replace('cmems_code:', 'bodc_ref:')
        bloecke.append(b)
        zeilen.append(dict(ref=ref, projekt=m.get('Project', '')[:30], lat=lat, lon=lon, tiefe=tiefe, boden=boden,
                           von=r['t0'].date(), bis=r['t1'].date(), stunden=r['n'], r2=round(r['r2'], 3),
                           m2_kn=round(r['m2'], 3), s2_kn=round(r['s2'], 3), k1_kn=round(r['k1'], 3),
                           v95_kn=round(r['smax'], 2), achse=round(r['achse'])))
    with open(os.path.join(ROOT, 'harmonics/help/bodc_stroemung_%s.txt' % tag), 'w', encoding='iso-8859-1') as fh:
        fh.write('\n'.join(bloecke) + '\n')
    with open(os.path.join(ROOT, 'harmonics/help/bodc_stroemung_%s.csv' % tag), 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=list(zeilen[0]))
        w.writeheader()
        w.writerows(zeilen)
    print(len(zeilen), 'Reihen gefittet von', len(M))


if __name__ == '__main__':
    main()
