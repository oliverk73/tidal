#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Longyearbyen aus der amtlichen Kartverket-Tafel fitten.

Auf Svalbard steht nur ein dauerhafter Pegel (Ny-Alesund), und dafuer
gibt es im Bestand schon zwei Saetze aus Messungen. Fuer Longyearbyen
dagegen stammt der einzige Satz aus dem XTide-Bestand von 1997. Kartverket
veroeffentlicht dort eine amtliche Tafel; zwei Jahrgaenge davon
(water_levels/Norway_Kartverket/tafel_LYR.csv, geladen mit
py/svalbard_kartverket.py) ergeben einen frischen Satz.

Verfahren wie bei den uebrigen Tafelfits: Hoch- und Niedrigwasser werden
mit einer halben Kosinuswelle zu einer Kurve verbunden
(py/batch_utide_uk_tidetimes.cosine_interpolate), darauf UTide. Das ist
Klasse B -- eine Tafel ist keine Messung --, aber die Tafel ist amtlich,
aktuell und in UTC.

Ohne --schreiben wird nur gerechnet und mit dem vorhandenen Satz verglichen.

Usage: python3 py/fit_svalbard_longyearbyen.py [--schreiben]
"""
from __future__ import annotations

import csv
import datetime as dt
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sicher_schreiben                                             # noqa: E402
from add_uhslc_harmonics import CONSTITUENTS_175, find_xtide_match  # noqa: E402
from batch_utide_uk_tidetimes import CONSTIT_67, cosine_interpolate  # noqa: E402
from health_check import ROOT                                       # noqa: E402

TAFEL = os.path.join(ROOT, 'water_levels/Norway_Kartverket/tafel_LYR.csv')
ZIEL = os.path.join(ROOT, 'harmonics/utide/harmonics_utide_tidetables.txt')
NAME = 'Longyearbyen (Adventfjorden), Svalbard, Norway'
LAT, LON = 78.22314, 15.64686


def scheitel():
    out = []
    for z in csv.DictReader(open(TAFEL, encoding='utf-8')):
        t = dt.datetime.fromisoformat(z['time'])
        out.append((t.astimezone(dt.timezone.utc).replace(tzinfo=None), float(z['value_cm']) / 100.0))
    out.sort()
    return out


def main(argv):
    import utide
    paare = scheitel()
    t, v = cosine_interpolate(paare)
    if t is None:
        print('zu wenig zusammenhaengende Scheitel')
        return 1
    print(f'{len(paare)} Scheitel -> {len(t)} Stuetzpunkte, {t[0]:%Y-%m-%d} bis {t[-1]:%Y-%m-%d}')
    # utide nimmt die datetime-Reihe selbst; die Umrechnung auf Matlab-Datenum
    # von Hand lieferte 0 Konstituenten.
    coef = utide.solve(t, v, lat=LAT, nodal=True, trend=False, method='ols',
                       conf_int='none', verbose=False, constit=CONSTIT_67)
    rec = utide.reconstruct(t, coef, verbose=False)
    resid = v - rec['h']
    rms = float(np.sqrt(np.mean(resid ** 2)))
    r2 = 1 - float(np.sum(resid ** 2)) / float(np.sum((v - v.mean()) ** 2))
    print(f'UTide: {len(coef["name"])} Konstituenten, r2={r2:.4f}, rms={rms:.4f} m')

    from utide._ut_constants import ut_constants
    tab = ut_constants['const']
    unamen = [n.strip() for n in tab.name]
    werte = {}
    for i, u in enumerate(coef['name']):
        u = u.strip()
        if u not in unamen:
            continue
        speed = tab.freq[unamen.index(u)] * 360.0
        xt, _ = find_xtide_match(u, speed)
        if xt:
            werte[xt] = (float(coef['A'][i]), float(coef['g'][i]) % 360.0)
    z0 = float(np.mean(v))
    for c in ('M2', 'S2', 'N2', 'K1', 'O1'):
        if c in werte:
            print(f'   {c:4} {werte[c][0]:6.3f} m  {werte[c][1]:6.1f} Grad')

    # Gegenprobe: der vorhandene Satz von 1997
    import xtide_modell as X
    alt = os.path.join(ROOT, 'harmonics/classic/harmonics-1997-05-25_mod.txt')
    try:
        z0a, w, e, mer = X.satz_lesen(alt, 'Longyearbyen, Spitsbergen, Norway')
        sp = X.kopf_lesen(alt)[1]
        print('\nGegen den Satz von 1997 (Greenwich-Phasen):')
        for c in ('M2', 'S2', 'N2', 'K1', 'O1'):
            if c in w and c in werte:
                ga = X.greenwich(w[c][1], sp[c], mer) % 360
                d = (werte[c][1] - ga + 180) % 360 - 180
                print(f'   {c:4} Amplitude {w[c][0]:.3f} -> {werte[c][0]:.3f} m, Phase {d:+6.1f} Grad'
                      f'  ({d / sp[c] * 60:+5.0f} min)')
    except KeyError:
        print('1997er Satz nicht gefunden')

    if '--schreiben' not in argv:
        print('\n(nur gerechnet; mit --schreiben wird der Satz angelegt)')
        return 0

    n_ana = sum(1 for cn, _ in CONSTITUENTS_175 if cn in werte)
    L = ['#', f'# {NAME}', '# BEGIN HOT COMMENTS', '# country: Norway',
         '# source: Kartverket tide table (vannstand.kartverket.no, tide_request=locationdata TAB) with UTide',
         '# station_id_context: KARTVERKET-LYR',
         f'# date_imported: {dt.datetime.now():%Y%m%d}',
         '# datum: Chart Datum (sjokartnull)',
         '# confidence: 6',
         f'# utide: pts={len(t)} period={t[0]:%Y-%m-%d}..{t[-1]:%Y-%m-%d} r2={r2:.4f} '
         f'rms={rms:.4f}m const={n_ana}',
         '# note: Amtliche Tafel, keine Messung: Svalbard hat nur in Ny-Alesund einen Pegel.',
         '# !units: meters', f'# !longitude: {LON:.4f}', f'# !latitude: {LAT:.4f}',
         '# region: Svalbard',
         NAME, '+00:00 :Arctic/Longyearbyen', f'{z0:.4f} meters']
    for cn, _sp in CONSTITUENTS_175:
        if cn in werte and werte[cn][0] >= 0.00005:
            L.append(f'{cn:15s} {werte[cn][0]:.4f}  {werte[cn][1]:.2f}')
        else:
            L.append('x 0 0')
    text = open(ZIEL, encoding='iso-8859-1').read()
    if NAME in text:
        print('Satz existiert schon -- nichts geschrieben')
        return 1
    sicher_schreiben.schreiben(ZIEL, text.rstrip('\n') + '\n' + '\n'.join(L) + '\n')
    print(f'\ngeschrieben: {NAME}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
