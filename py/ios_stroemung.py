#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""IOS-Stroemungsmessungen British Columbia (DFO Institute of Ocean Sciences) fitten (Oliver 14.11.2026).

Quelle: CIOOS Pacific ERDDAP (frei, "may be used and redistributed for free"):
  IOS_CUR_Moorings  (Stroemungsmesser, LCEWEL01/LCNSEL01 m/s bzw. LCSAEL01/LCDAEL01)
  IOS_ADCP_Moorings (ADCP, LCEWAP01/LCNSAP01 m/s je Tiefe, Gueteflag *_QC: 1 gut)
Auswahl (quellen/tidal_streams/Canada_IOS/einsaetze.csv, Vorlauf 14.11.): >= 25 Tage, <= 30 km vom naechsten Pegelsatz,
je 3-km-Ort ein Einsatz: der flachste Stroemungsmesser bis 60 m, sonst ADCP (Mittel der Zellen 5-25 m),
bei Gleichstand der laengste. ADCP: Zellen 5-25 m tief, nicht im obersten 12 % (Reflex). Stundenmittel mit Stempel = mittlere Zeit (C.stundenmittel).
Fit: ab 182,6 Tagen frei; darunter K2/P1 (und unter 27,6 Tagen N2) an den naechsten Pegel gekoppelt (K.fit).
Rohreihen (Stundenmittel u,v m/s) -> quellen/tidal_streams/Canada_IOS/roh/<datei>.csv; Ergebnis harmonics/help/ios_stroemung.csv
und Bloecke harmonics/help/ios_stroemung.txt (Namen = Dateiname, Benennung spaeter).

Usage: venv/bin/python py/ios_stroemung.py [--nur N]
"""
import csv
import datetime as dt
import math
import os
import sys
import time
import urllib.parse
import urllib.request

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cmems_stroemung_nachholen as C                               # noqa: E402
import stroemung_kopplung as K                                      # noqa: E402

ROOT = K.ROOT
D = os.path.join(ROOT, 'quellen/tidal_streams/Canada_IOS')
ERDDAP = 'https://data.cioospacific.ca/erddap/tabledap/'
FREI = ['M2', 'S2', 'N2', 'K2', 'K1', 'O1', 'P1', 'Q1', 'L2', 'NU2', 'MU2', '2N2', 'J1', 'OO1', 'M4', 'MS4', 'MN4',
        'M6', 'MK3', 'M3', '2MS6', 'MSF', 'MF', 'MM']


def auswahl():
    E = list(csv.DictReader(open(os.path.join(D, 'einsaetze.csv'))))
    for e in E:
        e['lat'], e['lon'], e['tage'], e['tief'] = float(e['lat']), float(e['lon']), int(e['tage']), int(e['tief'])
        e['pegel_km'] = float(e['pegel_km'])
    K_ = [e for e in E if e['tage'] >= 25 and e['pegel_km'] <= 30 and (e['ds'] == 'ADCP' or 0 <= e['tief'] <= 60)]
    cl = []
    for e in sorted(K_, key=lambda e: -e['tage']):
        for c in cl:
            if abs(c[0]['lat'] - e['lat']) < 0.03 and abs(c[0]['lon'] - e['lon']) < 0.045:
                c.append(e)
                break
        else:
            cl.append([e])
    wahl = []
    for c in cl:
        cur = sorted([e for e in c if e['ds'] == 'CUR_'], key=lambda e: (e['tief'], -e['tage']))
        wahl.append(cur[0] if cur else max(c, key=lambda e: e['tage']))
    return wahl


def holen(e):
    roh = os.path.join(D, 'roh', e['datei'] + '.csv')
    if os.path.exists(roh):
        df = pd.read_csv(roh, index_col=0, parse_dates=True)
        return df if len(df) else None
    os.makedirs(os.path.dirname(roh), exist_ok=True)
    f = urllib.parse.quote('"%s"' % e['datei'])
    if e['ds'] == 'CUR_':
        q = 'IOS_CUR_Moorings.csv?time,LCEWEL01,LCNSEL01,LCSAEL01,LCDAEL01&filename=' + f
    else:
        q = 'IOS_ADCP_Moorings.csv?time,depth,distance,LCEWAP01,LCNSAP01,LCEWAP01_QC&filename=' + f
        if e['tief'] > 0:                                          # nur Zellen um 5-25 m Tiefe holen (Geraetetiefe aus dem Namen)
            q += '&distance%%3E=%d&distance%%3C=%d' % (max(0, e['tief'] - 30), max(1, e['tief'] - 3))
    for v in range(4):
        try:
            x = pd.read_csv(urllib.request.urlopen(ERDDAP + q, timeout=600), skiprows=[1])
            break
        except Exception as ex:                                     # noqa: BLE001
            print('   Abruf', e['datei'], str(ex)[:60], flush=True)
            time.sleep(20 * (v + 1))
    else:
        return None
    x['time'] = pd.to_datetime(x['time'], utc=True).dt.tz_localize(None)
    if e['ds'] == 'CUR_':
        u, v_ = x['LCEWEL01'], x['LCNSEL01']
        if u.isna().all() and 'LCSAEL01' in x:                      # nur Betrag/Richtung (wohin)
            u = x['LCSAEL01'] * np.sin(np.radians(x['LCDAEL01']))
            v_ = x['LCSAEL01'] * np.cos(np.radians(x['LCDAEL01']))
        df = pd.DataFrame({'u': u.values, 'v': v_.values}, index=x['time'])
    else:
        # depth = Geraetetiefe, distance = Abstand der Zelle vom Geraet (aufwaerts): Zellentiefe 5-25 m, nicht in den
        # obersten 12 % (Oberflaechenreflex: cyp1 2016 zeigt dort 0,76 statt 0,05 m/s); QC 0 = ungeprueft, 1 = gut
        zt = x['depth'] - x['distance']
        x = x[(zt >= 5) & (zt <= 25) & (zt >= 0.12 * x['depth']) & (x['LCEWAP01_QC'].isna() | x['LCEWAP01_QC'].isin([0, 1]))]
        df = x.groupby('time')[['LCEWAP01', 'LCNSAP01']].mean().rename(columns={'LCEWAP01': 'u', 'LCNSAP01': 'v'})
    df = df[(df['u'].abs() < 6) & (df['v'].abs() < 6)].dropna().sort_index()
    df = C.stundenmittel(df) if len(df) else df
    df.to_csv(roh)
    return df if len(df) else None


def main(argv):
    W = auswahl()
    if '--nur' in argv:
        W = W[:int(argv[argv.index('--nur') + 1])]
    print(len(W), 'Einsaetze ausgewaehlt', flush=True)
    zeilen, bloecke = [], []
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(4) as ex:                              # 14.11.: ERDDAP langsam -> 4 Abrufe gleichzeitig
        geholt = list(ex.map(holen, W))
    for i, e in enumerate(W):
        df = geholt[i]
        if df is None or len(df) < 24 * 25:
            print('%3d %-45s zu kurz/leer' % (i, e['datei']), flush=True)
            continue
        tage = (df.index[-1] - df.index[0]).total_seconds() / 86400
        try:
            if tage >= 182.6:
                r = K.fit(df, FREI, {})
                kop = ''
            else:
                verh, pegel, km = K.verhaeltnisse(e['lat'], e['lon'])
                paare = K.noetig(df, FREI)
                kopplung = {b: (h, *verh[b]) for h, b in paare if b in verh}
                frei = [k for k in FREI if k not in kopplung and k not in ('MSF', 'MF', 'MM')]
                r = K.fit(df, frei, kopplung)
                kop = '%s an %s (%.0f km)' % ('/'.join(kopplung), pegel, km)
        except Exception as ex:                                     # noqa: BLE001
            print('%3d %-45s Fit-Fehler %s' % (i, e['datei'], str(ex)[:60]), flush=True)
            continue
        m2, s2, k1 = r['m2'], r['s2'], r['k1']
        print('%3d %-45s %4.0f T  r2 %.2f  M2 %.2f kn  S2 %.2f  K1 %.2f  Achse %3.0f  %s' % (
            i, e['datei'][:45], tage, r['r2'], m2, s2, k1, r['achse'], kop), flush=True)
        zeilen.append(dict(datei=e['datei'], ds=e['ds'], lat=e['lat'], lon=e['lon'], tief=e['tief'], tage=round(tage),
                           von=df.index[0].date(), bis=df.index[-1].date(), r2=round(r['r2'], 3), m2_kn=round(m2, 3),
                           s2_kn=round(s2, 3), k1_kn=round(k1, 3), v95_kn=round(r['smax'], 2), achse=round(r['achse']),
                           mittel_kn=round(r['mean'], 3), kopplung=kop, pegel_km=e['pegel_km']))
        bloecke.append((e, r, kop, tage))
    with open(os.path.join(ROOT, 'harmonics/help/ios_stroemung.csv'), 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=list(zeilen[0]))
        w.writeheader()
        w.writerows(zeilen)
    import pickle
    pickle.dump(bloecke, open(os.path.join(D, 'fits.pkl'), 'wb'))
    print(len(zeilen), 'gefittet ->', 'harmonics/help/ios_stroemung.csv')


if __name__ == '__main__':
    main(sys.argv[1:])
