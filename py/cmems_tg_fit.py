#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Messfits aus CMEMS-Stundenreihen (INSITU_GLO_PHY_SSH_DISCRETE_MY_013_053, oeffentlicher S3, TIME in UTC).

28.10.2026: Greifswald (TICON-4 aus GESLA-4 CMEMS, Meridian +01:00) liegt gegen die eigene Quellreihe -126 min (M2), nach
der Meridian-Berichtigung immer noch -66 min -- keine glatte Stufe (py/ticon_cmems_meridian.py). Die CMEMS-Reihe ist
2014-2025 in sich stabil (M2-Phase je Jahr 625..673 min) und passt zu Ruden/Thiessow (+6/+13 min); der TICON-Satz
Greifswald-Wieck (BfG, derselbe Pegel 0.8 km daneben) liegt ebenfalls -63..-113 min. Beide archiviert
(harmonics/help/greifswald_20261028_loeschen.csv), ein Messfit unter dem Wieck-Namen an der Pegelposition.
28.10. (2): 12 Ostsee-Nebenorte aus NP202 (harmonics_att_np202_secondary.txt) tragen alle denselben Satz (M2 3.3 cm,
S2 2.7 cm, K1 0.2 cm), gemessen sind M2 0.3-0.9 cm und K1 bis 2 cm. Wo CMEMS eine Reihe am Ort hat, ersetzt ein Messfit
den Satz (letzte 10 Jahre der Reihe; Bjoern und Draghaellan nur historisch bis 1978/1969). Ohne Reihe archiviert:
Yttergrund, Baltiysk, Swinoujscie, Arkona (harmonics/help/np202_ostsee_20261028_loeschen.csv).
Download: water_levels/cmems_tg_files.txt -> https://s3.waw3-1.cloudferro.com/mdl-native-03/... nach
water_levels/CMEMS_tg_pruefung/. Fit wie py/rws_plattform_fit.py (Stundenwerte, 67 Konstituenten + Obertiden, Probe am
letzten Jahr, Eigenversatz 0).
Usage: venv/bin/python py/cmems_tg_fit.py [Name ...] [--schreiben]  -> harmonics_utide_observations.txt
"""
import datetime as dt
import os
import sys

import netCDF4
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import health_check as H                                           # noqa: E402
import qld_msq_fit as Q                                            # noqa: E402
import scheitelfit as SF                                           # noqa: E402
import seine_haropa_fit as S                                       # noqa: E402
import xtide_modell as X                                           # noqa: E402
from sicher_schreiben import schreiben                             # noqa: E402

ROOT = S.ROOT
ZIEL = S.ZIEL
REIHEN = os.path.join(ROOT, 'water_levels/CMEMS_tg_pruefung')

# CMEMS-Datei, Name/Position (wie der ersetzte, von Oliver gepruefte Bestandssatz), Land, Zeitzone, ab Jahr, ersetzter Satz
PEGEL = [
    ('NO_TS_TG_GreifswaldTG_60minute.nc', 'Greifswald-Wieck, Germany', 54.097711, 13.457153, 'Germany', 'Europe/Berlin', 2016,
     'TICON Greifswald und Greifswald-Wieck (60-130 min zu frueh)'),
] + [(d, n, la, lo, land, tz, None, 'NP202-Einheitssatz (M2 3.3 cm wie alle Ostsee-Nebenorte)') for d, n, la, lo, land, tz in [
    ('BO_TS_TG_LandsortNorra_60minute.nc', 'Landsort, Sweden', 58.7449, 17.8643, 'Sweden', 'Europe/Stockholm'),
    ('BO_TS_TG_Bjorn_60minute.nc', 'Björn, Sweden', 60.6388, 17.9860, 'Sweden', 'Europe/Stockholm'),
    ('BO_TS_TG_Draghallan_60minute.nc', 'Draghällan (Sundsvall), Sweden', 62.3397, 17.4394, 'Sweden', 'Europe/Stockholm'),
    ('BO_TS_TG_Ratan_60minute.nc', 'Ratan, Sweden', 63.9902, 20.8913, 'Sweden', 'Europe/Stockholm'),
    ('BO_TS_TG_Helsinki_60minute.nc', 'Helsinki, Finland', 60.1667, 24.9555, 'Finland', 'Europe/Helsinki'),
    ('BO_TS_TG_Tallinn_60minute.nc', 'Tallinn, Estonia', 59.4493, 24.7755, 'Estonia', 'Europe/Tallinn'),
    ('BO_TS_TG_Liepaja_60minute.nc', 'Liepaja, Latvia', 56.5333, 20.9833, 'Latvia', 'Europe/Riga'),
    ('BO_TS_TG_Klaipeda_60minute.nc', 'Klaipeda (Memel), Lithuania', 55.7269, 21.0925, 'Lithuania', 'Europe/Vilnius')]]


def reihe(datei, ab):
    d = netCDF4.Dataset(os.path.join(REIHEN, datei))
    t = netCDF4.num2date(d['TIME'][:], d['TIME'].units, only_use_cftime_datetimes=False)
    s, q = d['SLEV'][:, 0], d['SLEV_QC'][:, 0]
    ok = (~np.ma.getmaskarray(s)) & np.isin(np.asarray(q), [1, 2])
    r = pd.Series(np.asarray(s)[ok].astype(float), index=pd.DatetimeIndex(np.array(t)[ok]))
    r = r[~r.index.duplicated()].sort_index()
    if ab is None:                                                 # letzte 10 Jahre der Reihe
        return r[r.index >= r.index[-1] - pd.Timedelta(days=3653)]
    return r[r.index.year >= ab]


def main(argv):
    kopf = X.kopf_lesen(ZIEL)
    namen, speeds, arg, fak = kopf
    voll = SF.konstituenten(namen, SF.CONSTIT_67) + [k for k in S.OBERTIDEN if k in namen]
    L = open(ZIEL, encoding='iso-8859-1').read().rstrip('\n').split('\n')
    heute = dt.date.today().strftime('%Y%m%d')
    bestand = [r for r in H.load_records() if r['lat'] and not r['current']]
    nur = [a for a in argv if not a.startswith('--')]
    for datei, name, la, lo, land, tz, ab, alt in PEGEL:
        if nur and name not in nur:
            continue
        s, start = Q.abschnitt(reihe(datei, ab))
        tage = (s.index[-1] - s.index[0]).days
        nutz = Q.rayleigh(voll, speeds, namen, tage)
        grenze = s.index[-1] - pd.Timedelta(days=365)
        _, _, pz0, pw, _, _ = Q.fit(s[:grenze], nutz, kopf, speeds, arg, fak)
        te = s[grenze:]
        rp = te.values - SF.hoehe_und_ableitungen(np.array([i.timestamp() for i in te.index]), pz0, pw, kopf)[0]
        rp = rp[np.abs(rp - np.median(rp)) < 5 * np.std(rp)]
        probe = '%.0f' % (100 * np.sqrt(np.mean(rp ** 2)))
        s, t, z0, w, h, aus = Q.fit(s, nutz, kopf, speeds, arg, fak)
        rms = float(np.sqrt(np.mean((s.values - h) ** 2)))
        r2 = 1 - np.var(s.values - h) / np.var(s.values)
        sub = slice(None, None, 7)
        eig = min(range(-30, 31), key=lambda m: np.std(s.values[sub] - SF.hoehe_und_ableitungen(t[sub] - 60 * m, z0, w, kopf)[0]))
        print('== %s  %d h %s..%s  R2 %.3f  RMS %.3f  Probe %s cm  Eigenversatz %+d  M2 %.3f@%.1f  S2 %.3f@%.1f  K1 %.3f@%.1f  O1 %.3f@%.1f  Z0 %.2f' % (
            name, len(s), s.index[0].date(), s.index[-1].date(), r2, rms, probe, eig, *w['M2'], *w['S2'], *w['K1'], *w['O1'], z0))
        nah = sorted(((H.km({'lat': la, 'lon': lo}, r), r) for r in bestand), key=lambda x: x[0])[:3]
        for k, r in nah:
            print('      ~ %s [%s] %.1f km %.0f%%' % (r['name'].split(',')[0], r['file'].split('/')[-1][9:31], k, 100 * H.curve_diff(Q.rec(w), r)[1]))
        blk = ['#', '# %s (CMEMS %s)' % (name.split(',')[0], datei.split('_TG_')[1].split('_')[0]), '# BEGIN HOT COMMENTS',
               '# country: %s' % land, '# source: CMEMS in-situ %s, least squares' % datei.replace('_60minute.nc', ''),
               '# note: CMEMS INSITU_GLO_PHY_SSH_DISCRETE_MY_013_053, Stundenwerte SLEV (QC 1/2), UTC.',
               '# station_id_context: CMEMS-%s' % datei.replace('_60minute.nc', ''), '# date_imported: %s' % heute,
               '# datum: CMEMS SLEV', '# confidence: 9',
               '# utide: pts=%d period=%s..%s r2=%.4f rms=%.4fm const=%d' % (len(s), s.index[0].date(), s.index[-1].date(), r2, rms, len(nutz)),
               '# note: %s Messfit (py/cmems_tg_fit.py) ersetzt %s.' % (heute, alt),
               '# note: Probe am letzten Messjahr %s cm RMS.' % probe,
               '# !units: meters', '# !longitude: %.4f' % lo, '# !latitude: %.4f' % la,
               name, '+00:00 :%s' % tz, '%.4f meters' % z0]
        blk += ['%-15s %.4f  %.2f' % (c, *w[c]) if c in w and w[c][0] >= 0.00005 else 'x 0 0' for c in namen]
        if name in L:
            print('   existiert schon in %s' % os.path.basename(ZIEL))
            continue
        L += blk
    if '--schreiben' in argv:
        schreiben(ZIEL, '\n'.join(L) + '\n')
        print('->', os.path.relpath(ZIEL, ROOT))


if __name__ == '__main__':
    main(sys.argv[1:])
