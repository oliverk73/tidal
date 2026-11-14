#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Arctic Tidal Current Atlas (Baumann et al. 2020, Sci. Data 7:275; NSF Arctic Data Center doi:10.18739/A26M3340D)
-> Stromsaetze (Oliver 14.11.2026).

429 Verankerungsreihen 1998-2018 mit T_TIDE-Analyse je Tiefe; jede Datei enthaelt die stuendliche Gezeitenvorhersage
u_tide_pred/v_tide_pred (cm/s, aus der Gesamtreihen-Analyse). Auswahl (List_of_records.txt): Schelf und Engstellen
(Wassertiefe <= 600 m, ohne Tiefseebecken eeb/mb/pole/web), je Verankerung die laengste Reihe (bei Gleichstand das
flachere Geraet). Genommen wird die flachste Tiefe ab 4 m mit >= 80 % gueltigen Werten; Fit wie py/ios_stroemung.py
(Hauptachse, XTide-Konstanten in Knoten; unter 182,6 Tagen K2/P1 an den naechsten Pegel gekoppelt).
Dateien -> currents/Arctic_tidal_atlas/nc/, Ergebnis harmonics/help/arktis_stromatlas.csv + fits.pkl.

Usage: venv/bin/python py/arktis_stromatlas.py
"""
import csv
import datetime as dt
import json
import os
import pickle
import sys
import time
import urllib.request

import netCDF4 as nc
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import stroemung_kopplung as K                                      # noqa: E402
import xtide_modell as X                                            # noqa: E402
from ios_stroemung import FREI                                      # noqa: E402

ROOT = K.ROOT
D = os.path.join(ROOT, 'currents/Arctic_tidal_atlas')
OBJ = 'https://arcticdata.io/metacat/d1/mn/v2/object/'
TIEFSEE = ('eeb', 'mb', 'pole', 'web')
HAUPT = ('M2', 'S2', 'N2', 'K2', 'K1', 'O1', 'P1', 'Q1')


def auswahl():
    Z = [l.split() for l in open(os.path.join(D, 'List_of_records.txt')) if l[:1].strip().isdigit()]
    best = {}
    for z in Z:
        try:
            bot = float(z[12])
        except ValueError:
            continue
        if z[3] in TIEFSEE or bot > 600:
            continue
        t0, t1 = dt.date(*map(int, z[4:7])), dt.date(*map(int, z[7:10]))
        e = dict(datei=z[1], mooring=z[2], region=z[3], lat=float(z[10]), lon=float(z[11]), boden=bot,
                 geraet=z[13], tage=(t1 - t0).days, quelle=z[15] if len(z) > 15 else '')
        k = (z[3], z[2].split('_')[0])
        if k not in best or (e['tage'], -len(e['datei'])) > (best[k]['tage'], -len(best[k]['datei'])):
            best[k] = e
    return list(best.values())


def laden(e, ids):
    f = os.path.join(D, 'nc', e['datei'].replace('-', '_') + '.nc')
    if os.path.exists(f):
        return f
    os.makedirs(os.path.dirname(f), exist_ok=True)
    name = os.path.basename(f)
    if name not in ids:
        print('   keine Datei', name)
        return None
    for v in range(3):
        try:
            urllib.request.urlretrieve(OBJ + ids[name], f + '.tmp')
            os.rename(f + '.tmp', f)
            return f
        except Exception as ex:                                     # noqa: BLE001
            print('   Abruf', name, str(ex)[:60], flush=True)
            time.sleep(20)
    return None


def reihe(f):
    d = nc.Dataset(f)
    t = d['time'][:].astype(float)                                 # Tage seit 0000-01-01 (MATLAB datenum)
    zeit = pd.to_datetime(t - 719529, unit='D').round('1min')
    U, V = np.ma.filled(d['u_tide_pred'][:], np.nan), np.ma.filled(d['v_tide_pred'][:], np.nan)
    p = np.ma.filled(d['pressure'][:], np.nan)
    # ab 4 m: Dinkum Sands (7 m Wassertiefe) zeigte in der 0-m-Zelle K1 3,9 kn (Eis/Oberflaechenreflex)
    ok = [j for j in np.argsort(p) if np.isfinite(p[j]) and p[j] >= 4 and np.isfinite(U[:, j]).mean() >= 0.8]
    if not ok:
        return None, None, None
    j = ok[0]
    # 14.11.: u_tide_pred enthaelt nur die SNR-signifikanten Tiden (Davis C1: O1/P1 fehlen, Tabelle O1 0,08 kn).
    # Deshalb aus den Ellipsen der Gesamtanalyse (FR) neu synthetisieren: Haupttiden immer, sonst Amplitude >= 2x Fehler.
    con = [''.join(c.decode() if isinstance(c, bytes) else c for c in x).strip().upper()
           for x in np.ma.filled(d['all_con'][:], b' ').T]
    g = {k: np.ma.filled(d[k + '_FR'][:], np.nan)[:, j] for k in ('maj_amp', 'maj_amp_err', 'min_amp', 'ori', 'phase')}
    namen, sp, arg, fak = K.KOPF
    sek = zeit.values.astype('datetime64[s]').astype(np.int64).astype(float)
    nutz = [i for i, c in enumerate(con) if c in sp and np.isfinite(g['maj_amp'][i])
            and (c in HAUPT or g['maj_amp'][i] >= 2 * g['maj_amp_err'][i])]
    Cm, Sm, _ = X.matrix(sek, [con[i] for i in nutz], sp, arg, fak)
    U_, V_ = np.zeros(len(sek)), np.zeros(len(sek))
    for s_, i in enumerate(nutz):
        sema, semi, inc, pha = g['maj_amp'][i], np.nan_to_num(g['min_amp'][i]), g['ori'][i], g['phase'][i]
        wp = (sema + semi) / 2 * np.exp(1j * np.radians(inc - pha))
        wm = (sema - semi) / 2 * np.exp(1j * np.radians(inc + pha))
        for ziel, ca in ((U_, wp + np.conj(wm)), (V_, -1j * (wp - np.conj(wm)))):
            A_, ph = abs(ca), -np.angle(ca)                         # Greenwich-Phase = -arg
            ziel += A_ * (Cm[:, s_] * np.cos(ph) + Sm[:, s_] * np.sin(ph))
    U[:, j], V[:, j] = np.where(np.isfinite(U[:, j]), U_, np.nan), np.where(np.isfinite(V[:, j]), V_, np.nan)
    df = pd.DataFrame({'u': U[:, j] / 100, 'v': V[:, j] / 100}, index=zeit).dropna()
    return df, float(p[j]), float(d['latitude'][:]), float(d['longitude'][:])


def main():
    ids = {x['fileName']: x['id'] for x in json.load(open(os.path.join(D, 'dateien.json')))['response']['docs'] if 'fileName' in x}
    W = auswahl()
    print(len(W), 'Verankerungen', flush=True)
    zeilen, fits = [], []
    for i, e in enumerate(sorted(W, key=lambda e: (e['region'], e['mooring']))):
        f = laden(e, ids)
        if not f:
            continue
        x = reihe(f)
        if x[0] is None or len(x[0]) < 24 * 25:
            print('%3d %-34s keine brauchbare Tiefe' % (i, e['datei']))
            continue
        df, tiefe, lat, lon = x
        tage = (df.index[-1] - df.index[0]).total_seconds() / 86400
        if tage >= 182.6:
            r, kop = K.fit(df, FREI, {}), ''
        else:
            verh, pegel, km = K.verhaeltnisse(lat, lon, 300.0)
            kopplung = {b: (h, *verh[b]) for h, b in K.noetig(df, FREI) if b in verh}
            r = K.fit(df, [k for k in FREI if k not in kopplung and k not in ('MSF', 'MF', 'MM')], kopplung)
            kop = '%s an %s (%.0f km)' % ('/'.join(kopplung), pegel, km)
        print('%3d %-34s %4.0f T %4.0f m  M2 %.2f kn  S2 %.2f  K1 %.2f  O1 %.2f  Achse %3.0f %s' % (
            i, e['datei'], tage, tiefe, r['m2'], r['s2'], r['k1'], r['konst'].get('O1', (0, 0))[0], r['achse'], kop), flush=True)
        zeilen.append(dict(datei=e['datei'], region=e['region'], mooring=e['mooring'], lat=lat, lon=lon, boden=e['boden'],
                           tiefe=round(tiefe), tage=round(tage), von=df.index[0].date(), bis=df.index[-1].date(),
                           quelle=e['quelle'], m2_kn=round(r['m2'], 3), s2_kn=round(r['s2'], 3), k1_kn=round(r['k1'], 3),
                           o1_kn=round(r['konst'].get('O1', (0, 0))[0], 3), v95_kn=round(r['smax'], 2),
                           achse=round(r['achse']), kopplung=kop))
        fits.append((e, r, kop, tage, tiefe, lat, lon))
    with open(os.path.join(ROOT, 'harmonics/help/arktis_stromatlas.csv'), 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=list(zeilen[0]))
        w.writeheader()
        w.writerows(zeilen)
    pickle.dump(fits, open(os.path.join(D, 'fits.pkl'), 'wb'))
    print(len(zeilen), 'gefittet')


if __name__ == '__main__':
    main()
