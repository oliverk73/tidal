#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Harmonische Saetze fuer Tidepegel an franzoesischen Fluessen aus HydroPortail-Messreihen.

Oliver 17.10.2026 "Jetzt bitte die franzoesischen Fluesse": wie die Seine (py/seine_haropa_fit.py) -- an der
Seine war der Messfit doppelt so genau wie die Buchuebertragungen (Duclair 28 gegen 53 cm). Kandidaten aus
Hub'Eau (Tidesignal in den letzten 30 Tagen), Reihen mit py/download_hydroportail.py.

Je Pegel: Jahresmediane ausgeben (Pegelnull-Spruenge von Hand pruefen; die Automatik --spruenge schlaegt bei Hochwasser an),
Fit auf bis zu 10 volle Jahre vor 2026 (67 UTide-Konstituenten + Obertiden bis M12), Probe an der Messung 2026,
Eigenversatz muss 0 min sein. Z0 = Abstand Mittelwasser - tiefster Wert der 19-Jahres-Kurve (CD ~ LAT), weil
das Pegelnull der Fluss-Pegel (NGF oder ein Ortsnull) kein Seekartennull ist.

Liste: harmonics/help/fluss_pegel_frankreich.tsv  (code, name, lat, lon, region, bemerkung)
Usage: venv/bin/python py/fluss_hydroportail_fit.py [code ...] [--schreiben]  -> harmonics_utide_observations.txt
"""
import csv
import datetime as dt
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scheitelfit as SF                                           # noqa: E402
import seine_haropa_fit as S                                       # noqa: E402
import xtide_modell as X                                           # noqa: E402
from sicher_schreiben import schreiben                             # noqa: E402

ROOT = S.ROOT
ZIEL = S.ZIEL
LISTE = os.path.join(ROOT, 'harmonics/help/fluss_pegel_frankreich.tsv')


def liste():
    return [z for z in csv.DictReader(open(LISTE, encoding='utf-8'), delimiter='\t') if z['code'] and not z['code'].startswith('#')]


def abschnitt(s):
    """Juengster Abschnitt ohne Pegelnull-Sprung (Monatsmedian, Fenster 6 Monate, > 0.4 m)."""
    m = s.resample('MS').median().dropna()
    start = s.index[0]
    for i in range(6, len(m) - 6):
        vor, nach = m.iloc[i - 6:i].median(), m.iloc[i:i + 6].median()
        if abs(nach - vor) > 0.4 and abs(m.iloc[i:].median() - vor) > 0.4:
            start = m.index[i]
    return s[start:], start


def main(argv):
    kopf = X.kopf_lesen(ZIEL)
    namen, speeds, arg, fak = kopf
    nutz = SF.konstituenten(namen, SF.CONSTIT_67) + [k for k in S.OBERTIDEN if k in namen]
    L = open(ZIEL, encoding='iso-8859-1').read().rstrip('\n').split('\n')
    heute = dt.date.today().strftime('%Y%m%d')
    wahl = [a for a in argv if not a.startswith('--')]
    for z in liste():
        if wahl and z['code'] not in wahl:
            continue
        pfad = os.path.join(S.REIHEN, 'hp_%s.csv' % z['code'])
        if not os.path.exists(pfad):
            print('%s: keine Reihe' % z['code'])
            continue
        s = pd.read_csv(pfad, parse_dates=['time']).set_index('time')['waterlevel_m'].dropna()
        start = s.index[0]
        if '--spruenge' in argv:
            s, start = abschnitt(s)
        jm = s.groupby(s.index.year).median()
        print('   Jahresmedian: ' + ' '.join('%d:%.2f' % (j, v) for j, v in jm.items()))
        tr = s[:'2025-12-31']
        tr = tr[tr.index >= tr.index[-1] - pd.Timedelta(days=3653)]
        te = s['2026-01-01':]
        if len(tr) < 24 * 300:
            print('%-45s zu kurz (%d h ab %s)' % (z['name'], len(tr), start.date()))
            continue
        # Trockenfallende Pegel (Niedrigwasser-Plateau am Flussbett) nicht aufnehmen: der Fit wackelt am Plateau,
        # XTide meldet Schein-Hochwasser (Etaples 115-137, Cabourg 100 statt 58 im Monat); Weglassen der Plateauwerte
        # verzerrt den Fit (Etaples M4 > M2). Siehe Liste, 17.10.2026.
        t = np.array([i.timestamp() for i in tr.index])
        z0, w = S.kq(t, tr.values, nutz, speeds, arg, fak)
        h = SF.hoehe_und_ableitungen(t, z0, w, kopf)[0]
        # Ausreisser (Fehlwerte wie 9.99 m, Sensorspruenge): Rest > 5 sd -> verwerfen und neu fitten
        r = tr.values - h
        gut = np.abs(r - np.median(r)) < 5 * np.std(r)
        if (~gut).sum():
            tr = tr[gut]
            t = t[gut]
            z0, w = S.kq(t, tr.values, nutz, speeds, arg, fak)
            h = SF.hoehe_und_ableitungen(t, z0, w, kopf)[0]
            print('   %d Ausreisser verworfen' % (~gut).sum())
        rms = float(np.sqrt(np.mean((tr.values - h) ** 2)))
        r2 = 1 - np.var(tr.values - h) / np.var(tr.values)
        sub = slice(None, None, 7)                      # Eigenversatz ueber die ganze Reihe (jede 7. Stunde), 1-min-Schritte
        eig = min(range(-30, 31), key=lambda m: np.std(tr.values[sub] - SF.hoehe_und_ableitungen(t[sub] - 60 * m, z0, w, kopf)[0]))
        probe = ''
        if len(te) > 24 * 30:
            tt = np.array([i.timestamp() for i in te.index])
            rp = te.values - SF.hoehe_und_ableitungen(tt, z0, w, kopf)[0]
            rp = rp[np.abs(rp - np.median(rp)) < 5 * np.std(r)]     # Fehlwerte wie im Fit verwerfen
            probe = 'Probe Messung 2026: %.0f cm (sd %.0f)' % (100 * np.sqrt(np.mean(rp ** 2)), 100 * np.std(rp))
        # Z0 ueber LAT: tiefster Wert der Gezeitenkurve ueber 19 Jahre (halbstuendlich)
        tg = np.arange(dt.datetime(2008, 1, 1).timestamp(), dt.datetime(2027, 1, 1).timestamp(), 1800.0)
        lat = float(SF.hoehe_und_ableitungen(tg, 0.0, w, kopf)[0].min())
        z0_lat = -lat
        print('%-45s %6d h ab %s  R2 %.3f  RMS %.3f  Eigenversatz %+d  M2 %.3f@%.0f  M4 %.3f  Z0 %.2f (Pegel %.2f)  %s' % (
            z['name'], len(tr), tr.index[0].date(), r2, rms, eig, *w['M2'], w.get('M4', (0, 0))[0], z0_lat, z0, probe))
        name = z['name']
        blk = ['#', '# ' + name, '# BEGIN HOT COMMENTS', '# country: France',
               '# source: HydroPortail/Vigicrues gauge %s measurements, least squares' % z['code'],
               '# station_id_context: HydroPortail-%s' % z['code'], '# date_imported: %s' % heute,
               '# datum: approx. LAT (Z0 aus 19-Jahres-Minimum)', '# confidence: 7',  # libtcd: datum hoechstens 70 Zeichen
               '# note: Mittelwasser %.2f m ueber dem Pegelnull von HydroPortail.' % z0,
               '# utide: pts=%d period=%s..%s r2=%.4f rms=%.4fm const=%d' % (len(tr), tr.index[0].date(), tr.index[-1].date(), r2, rms, len(nutz)),
               '# note: %s Flusstide aus der Messreihe (py/fluss_hydroportail_fit.py)%s (Oliver).' % (heute, ('; ' + z['bemerkung']) if z.get('bemerkung') else ''),
               ('# note: %s.' % probe) if probe else '# note: keine Messung 2026 zur Probe.',
               '# !units: meters', '# !longitude: %.4f' % float(z['lon']), '# !latitude: %.4f' % float(z['lat']),
               '# region: %s' % z['region'], name, '+00:00 :Europe/Paris', '%.4f meters' % z0_lat]
        blk += ['%-15s %.4f  %.2f' % (c, *w[c]) if c in w and w[c][0] >= 0.00005 else 'x 0 0' for c in namen]
        if name in L:
            print('   existiert schon')
            continue
        L += blk
    if '--schreiben' in argv:
        schreiben(ZIEL, '\n'.join(L) + '\n')
        print('->', os.path.relpath(ZIEL, ROOT))


if __name__ == '__main__':
    main(sys.argv[1:])
