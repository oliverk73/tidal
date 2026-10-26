#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""UTide-Fits der russischen IOC-Pegel Kholmsk, Rudnaya Pristan und Mys Sosunova.

Oliver 16.10.2026 (Vorschlagsseite Russland-Pazifik vom 15.10.): die drei Reihen in
water_levels/Russia_IOC/ waren nicht im Bestand, laufen aber monatsweise stabil gegen
FES (+-10..20 min). Kholmsk ersetzt den FES-Ersatz vom 15.10. (Messung vor Modell).

Vor dem Fit wird je Monat der Zeitversatz Reihe gegen FES geprueft (Kreuzkorrelation);
Monate mit Datumssprung (Tagesmittel springt > 0.3 m) oder grossem Rest fliegen raus.
Phasen in UTC (+00:00), Z0 ueber CD~LAT (19 Jahre rekonstruiert, wie fit_ioc_gaps.py).

Usage: venv/bin/python py/ioc_russland_fit.py [code ...] [--schreiben]
       schreibt harmonics/utide/harmonics_utide_observations.txt
"""
import contextlib
import datetime as dt
import io
import os
import sys

import netCDF4 as nc
import numpy as np
import pandas as pd
import utide

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import xtide_modell as X                                           # noqa: E402
from fes_ersatz_inseln import sample, stem, FES_DIR, ROOT          # noqa: E402
from sicher_schreiben import schreiben                             # noqa: E402

ZIEL = os.path.join(ROOT, 'harmonics/utide/harmonics_utide_observations.txt')
# code, Datei, Name, Breite, Laenge, Positionsnotiz
PEGEL = [
    ('khol', 'ioc_khol_Kholmsk.csv', 'Kholmsk, Sakhalin Oblast, Russia', 47.0520, 142.0417,
     'Position des FES-Ersatzes (Hafen), IOC 47.0506/142.0439'),
    ('rudn', 'ioc_rudn_Rudnaya_Pristan.csv', "Rudnaya Pristan', Primorsky Krai, Russia", 44.3570, 135.8450,
     'IOC 44.35/135.80 (gerundet, an Land); vor das Ufer des Orts gelegt, bitte pruefen'),
    ('sosu', 'ioc_sosu_Sosunovo.csv', 'Mys Sosunova, Primorsky Krai, Russia', 46.5320, 138.3500,
     'IOC "Sosunovo" 46.53/138.33 (gerundet, an Land); Siedlung/Leuchtturm Mys Sosunova, bitte pruefen'),
    # 17.10.2026 (PSMSL-Frage: dort nur Monatsmittel; Stundenwerte beim IOC, py/download_ioc_monate.py)
    # star (Starodubskoe) NICHT: steht seit 20.05.2026 im Bestand (IOC-star); am 17.10. versehentlich doppelt gefittet
    ('seve2', 'ioc_seve2_monate.csv', "Severo-Kuril'sk (Paramushir, Kuril'skiye Ostrova), Sakhalin Oblast, Russia", 50.6785, 156.1404,
     'IOC seve2 50.678/156.1388 (7 m an Land), Hafen; bitte pruefen'),
    ('vodo', 'ioc_vodo_monate.csv', 'Vodopadnaya, Kamchatka Krai, Russia', 51.7243, 157.9865,
     'IOC-Name Vodopadnaya (kein GeoNames-Eintrag am Ort), IOC 51.7268/157.9889 an Land; bitte Name und Position pruefen'),
    ('kril', 'ioc_kril_monate.csv', "Mys Kril'on, Sakhalin Oblast, Russia", 45.8922, 142.0809,
     'IOC Cape Kril\'on 45.9/142.08, GeoNames-Kap 45.8927/142.0809; bitte pruefen'),
]
# Erwarteter Versatz gegen FES, wo FES nachweislich daneben liegt: Severo-Kuril'sk 2010 gegen die JHD-Nachbarn
# Zaliv Kozyrevskogo (5 km) und Mys Savushkina +-16 min, gegen FES +22..+46 min (Kurilenstrasse)
SOLL = {'seve2': 35}
REGION = {'khol': 'Sakhalin Oblast', 'rudn': 'Primorsky Krai', 'sosu': 'Primorsky Krai', 'star': 'Sakhalin Oblast',
          'seve2': 'Sakhalin Oblast', 'vodo': 'Kamchatka Krai', 'kril': 'Sakhalin Oblast'}
TZ = {'khol': 'Asia/Sakhalin', 'rudn': 'Asia/Vladivostok', 'sosu': 'Asia/Vladivostok', 'star': 'Asia/Sakhalin',
      'seve2': 'Asia/Srednekolymsk', 'vodo': 'Asia/Kamchatka', 'kril': 'Asia/Sakhalin'}
FESC = ('M2', 'S2', 'N2', 'K2', 'K1', 'O1', 'P1', 'Q1')


def reihe(datei):
    d = pd.read_csv(os.path.join(ROOT, 'water_levels/Russia_IOC', datei))
    s = pd.Series(pd.to_numeric(d.iloc[:, 1], errors='coerce').values,
                  index=pd.to_datetime(d.iloc[:, 0], utc=True)).dropna()
    s = s[~s.index.duplicated()]
    return s[(s - s.median()).abs() < 6 * s.std()]


def fes_kurve(idx, lat, lon, namen, speeds, arg, fak):
    F = {}
    for c in FESC:
        p = os.path.join(FES_DIR, f'{stem(c)}_fes2022.nc')
        a, g = sample(nc.Dataset(p), lat, lon)
        if a:
            F[c] = (a, g)
    t = (idx.tz_convert(None) - pd.Timestamp('1970-01-01')).total_seconds().values
    return X.kurve(t, 0, F, namen, speeds, arg, fak)


def lag_min(a, b):
    """Versatz von a gegen b in Minuten (positiv: a spaeter), Stundenraster + Parabel."""
    a, b = a - a.mean(), b - b.mean()
    best = max(range(-4, 5), key=lambda k: np.dot(np.roll(a, -k), b))
    c = [np.dot(np.roll(a, -k), b) for k in (best - 1, best, best + 1)]
    den = c[0] - 2 * c[1] + c[2]
    return 60 * (best + (0.5 * (c[0] - c[2]) / den if den else 0))


def main(argv):
    namen, speeds, arg, fak = X.kopf_lesen(ZIEL)
    L = open(ZIEL, encoding='iso-8859-1').read().rstrip('\n').split('\n')
    heute = dt.date.today().strftime('%Y%m%d')
    wahl = [a for a in argv if not a.startswith('--')]
    for code, datei, name, lat, lon, posnote in PEGEL:
        if wahl and code not in wahl:
            continue
        s = reihe(datei)
        # Pegelnull-Sprung = anhaltende Verschiebung (Wochenmedian), nicht ein Sturmflut-Tag (Nordsee 17.10.2026)
        tag = s.resample('D').mean()
        sprung = tag.rolling(7, center=True, min_periods=4).median().diff().abs() > 0.4
        f = pd.Series(fes_kurve(s.index, lat, lon, namen, speeds, arg, fak), index=s.index)
        gut = []
        print('==', name)
        for m, g in s.groupby(s.index.to_period('M')):
            if len(g) < 24 * 20:
                continue
            reg = g.reindex(pd.date_range(g.index[0], g.index[-1], freq='h')).interpolate(limit=3).dropna()
            ff = f.reindex(reg.index).interpolate()
            lg = lag_min(reg.values, ff.values)
            r = np.corrcoef(reg.values, ff.values)[0, 1]
            spr = bool(sprung[str(m)].any()) if str(m) in sprung else False
            ok = abs(lg - SOLL.get(code, 0)) <= (25 if code in SOLL else 30) and r > 0.3 and not spr
            print('   %s  %4d h  Versatz %+5.0f min  r %.2f %s' % (m, len(g), lg, r, '' if ok else ' <- raus'))
            if ok:
                gut.append(g)
        # Pegelnull-Spruenge (Kholmsk 09/2024..08/2025 +1.1 m): neuer Abschnitt, wenn das
        # Monatsmittel um mehr als 0.5 m springt; jeder Abschnitt auf das Niveau des ersten
        stufen, basis, vor = [], None, None
        for g in gut:
            m = g.median()
            if vor is not None and abs(m - vor) > 0.5:
                print('   Pegelnull-Sprung %+.2f m ab %s' % (m - vor, g.index[0].date()))
                basis = None
            if basis is None:
                basis = m - (stufen[0][1] if stufen else m)
            stufen.append((g - basis, m - basis))
            vor = m
        if not stufen:
            print('   keine gueltigen Monate -- uebersprungen')
            continue
        s = pd.concat([g for g, _ in stufen])
        with contextlib.redirect_stdout(io.StringIO()):
            co = utide.solve(s.index.tz_convert(None).to_pydatetime(), s.values, lat=lat, method='ols',
                             conf_int='none', trend=False, nodal=True, verbose=False)
            rec = utide.reconstruct(s.index.tz_convert(None).to_pydatetime(), co, verbose=False)['h']
            tt = [dt.datetime(2007, 1, 1) + dt.timedelta(hours=h) for h in range(0, 19 * 8766, 1)]
            lat_min = float(utide.reconstruct(tt, co, verbose=False)['h'].min())
        res = s.values - rec
        r2 = 1 - np.sum(res ** 2) / np.sum((s.values - s.values.mean()) ** 2)
        rms = float(np.sqrt(np.mean(res ** 2)))
        z0 = float(co['mean']) - lat_min
        k = {n.strip(): (float(a), float(g) % 360) for n, a, g in zip(co['name'], co['A'], co['g'])}
        # Eigenprobe: Fit gegen die eigene Reihe muss 0 min zeigen
        eig = lag_min(rec[:24 * 30], s.values[:24 * 30])
        print('   Fit: %d h %s..%s  R2 %.3f  RMS %.3f m  Eigenversatz %+.0f min  Z0 %.3f' % (
            len(s), s.index[0].date(), s.index[-1].date(), r2, rms, eig, z0))
        print('   ' + '  '.join('%s %.3f@%.0f' % (c, *k[c]) for c in ('M2', 'S2', 'K1', 'O1') if c in k))
        fehlt = [n for n in k if n not in namen]
        if fehlt:
            print('   ohne XTide-Namen:', ' '.join(fehlt))
        blk = ['#', f'# {name}', '# BEGIN HOT COMMENTS', '# country: ' + name.split(',')[-1].strip(),
               '# source: IOC Sea Level Monitoring gauge measurements with UTide',
               f'# station_id_context: IOC-{code}', f'# date_imported: {heute}',
               '# datum: Chart Datum (approx., CD~LAT from constituents)', '# confidence: 7',
               '# utide: pts=%d period=%s..%s r2=%.4f rms=%.4fm const=%d' % (
                   len(s), s.index[0].date(), s.index[-1].date(), r2, rms, sum(1 for n in k if n in namen)),
               f'# note: {heute} Monate mit Versatz > 30 min oder Datumssprung verworfen; {posnote} (Oliver).',
               '# !units: meters', f'# !longitude: {lon:.4f}', f'# !latitude: {lat:.4f}',
               f'# region: {REGION[code]}', name, '+00:00 :' + TZ[code], '%.4f meters' % z0]
        for c in namen:
            blk.append('%-15s %.4f  %.2f' % (c, *k[c]) if c in k and k[c][0] >= 0.00005 else 'x 0 0')
        if name in L:
            print('   existiert schon in', os.path.basename(ZIEL))
            continue
        L += blk
    if '--schreiben' in argv:
        schreiben(ZIEL, '\n'.join(L) + '\n')
        print('->', os.path.relpath(ZIEL, ROOT))


if __name__ == '__main__':
    main(sys.argv[1:])
