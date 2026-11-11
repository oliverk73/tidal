#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Messfits Tema + Takoradi aus den GPHA-Pegelreihen 2019-2025 (Lieferung Ghana Ports and Harbours Authority, 11.11.2026).

Rohdaten: water_levels/Ghana/TEMA AND TAKORADI TIDE DATA _2019 to 2025.zip (entpackt nach water_levels/Ghana/roh/),
Monatsdateien, Tab-getrennt, 10-min-Werte UTC, Spalte "Tide Level"/"Observed" in m. Die mitgelieferte Vorhersagespalte
wird nicht benutzt (Tema 04-07/2020 50 min verschoben).
Pruefung (scratchpad gh_diag.py): Messzeiten in allen Monaten ohne Versatz gegen einen Referenzfit 2022/23.
Takoradi hat zwei Pegelnull-Abschnitte (2020-03-01..2020-07-28 ca. -0.4 m, 2022-02-01..2022-06-24 bis +0.4 m) -> raus.
Tagesfilter: Tagesmedian des Rests > 0.15 m vom 31-Tage-Median oder hochfrequente Reststreuung > 3x typisch -> Tag raus.
Fit wie py/qld_msq_fit.py: Momentanwert zur vollen Stunde, 67 Konstituenten + Obertiden, Rayleigh, Probe am letzten Jahr.

--schreiben ersetzt im vorhandenen Satz (harmonics_utide_observations.txt) Z0 + Konstituenten und die Kopfzeilen
source/station_id_context/date_imported/datum/utide; Kennungen (UHSLC/GLOSS/PSMSL ...), Name und Position bleiben.
Usage: venv/bin/python py/ghana_gpha_fit.py [--schreiben]
"""
import datetime as dt
import glob
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import health_check as H                                           # noqa: E402
import qld_msq_fit as Q                                            # noqa: E402
import scheitelfit as SF                                           # noqa: E402
import seine_haropa_fit as S                                       # noqa: E402
import xtide_modell as X                                           # noqa: E402
from sicher_schreiben import schreiben                             # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROH = os.path.join(ROOT, 'water_levels/Ghana/roh/TEMA AND TAKORADI TIDE DATA _2019 to 2025')
ZIEL = Q.ZIEL
PEGEL = {  # Ort: (Ordner, GPHA-idSite, Name im Bestand, Ausschluss-Abschnitte)
    'Tema': ('TEMA TIDE DATA', 131, 'Tema, Ghana', []),
    'Takoradi': ('TAKORADI TIDE DATA', 130, 'Takoradi, Ghana', [('2020-03-01', '2020-07-29'), ('2022-02-01', '2022-06-25')]),
}


def lesen(ordner):
    T = []
    for f in sorted(glob.glob(os.path.join(ROH, ordner, '*', '*.txt'))):
        T.append(pd.read_csv(f, sep='\t', skiprows=2, header=None, usecols=[2, 3], names=['t', 'obs'], dtype=str))
    d = pd.concat(T)
    d['t'] = pd.to_datetime(d['t'].str.strip(), format='ISO8601', errors='coerce')
    d['obs'] = pd.to_numeric(d['obs'], errors='coerce')
    d = d.dropna().drop_duplicates('t').set_index('t').sort_index()['obs']
    return d[(d > -1) & (d < 4)]


def tagesfilter(s, kopf, nutz, speeds, arg, fak):
    """Vorfit, dann Tage mit Pegelnull-Versatz oder Stoerung entfernen."""
    _, _, z0, w, _, _ = Q.fit(s, nutz, kopf, speeds, arg, fak)
    t = np.array([i.timestamp() for i in s.index])
    r = pd.Series(s.values - SF.hoehe_und_ableitungen(t, z0, w, kopf)[0], index=s.index)
    tm = r.resample('D').median()
    ab = (tm - tm.rolling(31, center=True, min_periods=10).median()).abs()
    hf = (r - r.rolling(13, center=True, min_periods=5).median()).abs().resample('D').median()
    weg = ab[(ab > 0.15)].index.union(hf[hf > 3 * hf.median()].index)
    tage = s.index.normalize()
    return s[~tage.isin(weg)], len(weg)


def main(argv):
    kopf = X.kopf_lesen(ZIEL)
    namen, speeds, arg, fak = kopf
    voll = SF.konstituenten(namen, SF.CONSTIT_67) + [k for k in S.OBERTIDEN if k in namen]
    L = open(ZIEL, encoding='iso-8859-1').read().rstrip('\n').split('\n')
    heute = dt.date.today().strftime('%Y%m%d')
    bestand = [r for r in H.load_records() if r['lat'] and 3.5 < r['lat'] < 6.5 and -3.5 < r['lon'] < 1.5 and not r['current']]
    for ort, (ordner, sid, name, aus) in PEGEL.items():
        d = lesen(ordner)
        for a, b in aus:
            d = d[(d.index < a) | (d.index >= b)]
        s = d[d.index.minute == 0]
        tage = (s.index[-1] - s.index[0]).days
        nutz = Q.rayleigh(voll, speeds, namen, tage)
        s, nweg = tagesfilter(s, kopf, nutz, speeds, arg, fak)
        grenze = s.index[-1] - pd.Timedelta(days=365)
        _, _, pz0, pw, _, _ = Q.fit(s[:grenze], nutz, kopf, speeds, arg, fak)
        te = s[grenze:]
        rp = te.values - SF.hoehe_und_ableitungen(np.array([i.timestamp() for i in te.index]), pz0, pw, kopf)[0]
        rp = rp[np.abs(rp - np.median(rp)) < 5 * np.std(rp)]
        probe = 100 * np.sqrt(np.mean((rp - np.median(rp)) ** 2))
        s, t, z0, w, h, nausr = Q.fit(s, nutz, kopf, speeds, arg, fak)
        rms = float(np.sqrt(np.mean((s.values - h) ** 2)))
        r2 = 1 - np.var(s.values - h) / np.var(s.values)
        sub = slice(None, None, 7)
        eig = min(range(-30, 31), key=lambda m: np.std(s.values[sub] - SF.hoehe_und_ableitungen(t[sub] - 60 * m, z0, w, kopf)[0]))
        tg = np.arange(dt.datetime(2008, 1, 1).timestamp(), dt.datetime(2027, 1, 1).timestamp(), 1800.0)
        lat_kurve = -float(SF.hoehe_und_ableitungen(tg, 0.0, w, kopf)[0].min())
        alt = [r for r in bestand if r['name'] == name and 'utide_observations' in r['file']][0]
        print('\n== %s: %d h %s..%s (%d Tage, %d Konst.), %d Tage gefiltert, %d Ausreisser' % (
            ort, len(s), s.index[0].date(), s.index[-1].date(), tage, len(nutz), nweg, nausr))
        print('   R2 %.4f  RMS %.1f cm  Probe letztes Jahr %.1f cm  Eigenversatz %+d min' % (r2, 100 * rms, probe, eig))
        print('   M2 %.4f@%.2f  S2 %.4f@%.2f  K1 %.4f@%.2f  O1 %.4f@%.2f  Z0 %.3f  (19-J-Minimum %.3f unter Z0)' % (
            *w['M2'], *w['S2'], *w['K1'], *w['O1'], z0, lat_kurve))
        nah = sorted(((H.km(alt, r), r) for r in bestand), key=lambda x: x[0])[:6]
        for k, r in nah:
            print('      ~ %-34s %-30s %5.1f km  %4.1f %%' % (r['name'][:34], os.path.basename(r['file'])[:30], k, 100 * H.curve_diff(Q.rec(w), r)[1]))
        # Pegelnull: Takoradi liegt am 19-Jahres-Minimum (= Kartennull), Tema 0.16 m darueber -> wie qld_msq_fit auf LAT
        datum = 'GPHA gauge zero (approx. chart datum/LAT)'
        if not -0.1 <= z0 - lat_kurve <= 0.4:
            datum = 'approx. LAT (Z0 aus 19-Jahres-Minimum; GPHA-Pegelnull %+.2f m)' % (z0 - lat_kurve)
            print('   Pegelnull %+.2f m gegen LAT-Kurve -> Z0 = %.3f' % (z0 - lat_kurve, lat_kurve))
            z0 = lat_kurve
        if '--schreiben' not in argv:
            continue
        i = L.index(name, max(0, alt['line'] - 5))
        k = i
        while L[k - 1].startswith('#') and L[k - 1].strip() != '#':
            k -= 1
        kopfz = L[k:i]
        neu = []
        for z in kopfz:
            if z.startswith('# source:'):
                z = '# source: Ghana Ports and Harbours Authority (GPHA) tide gauge, least squares'
            elif z.startswith('# station_id_context:'):
                z = '# station_id_context: GPHA-%d' % sid
            elif z.startswith('# date_imported:'):
                z = '# date_imported: %s' % heute
            elif z.startswith('# datum:'):
                z = '# datum: ' + datum
            elif z.startswith('# utide:'):
                z = '# utide: pts=%d period=%s..%s r2=%.4f rms=%.4fm const=%d' % (
                    len(s), s.index[0].date(), s.index[-1].date(), r2, rms, len(nutz))
            elif z.startswith('# note:') and ('IOC' in z or 'Oliver' in z or 'Monate' in z):
                continue
            neu.append(z)
        j = next(n for n, z in enumerate(neu) if z.startswith('# !units'))
        neu[j:j] = ['# note: %s Messfit aus GPHA-10-min-Reihe 2019-2025, Lieferung Y. Koranteng (py/ghana_gpha_fit.py).' % heute,
                    '# note: Probe am letzten Messjahr %.1f cm RMS; %d gestoerte Tage raus%s.' % (
                        probe, nweg, '; Pegelnull-Abschnitte 03-07/2020 + 02-06/2022 raus' if aus else '')]
        tz = L[i + 1]
        blk = neu + [name, tz, '%.4f meters' % z0]
        blk += ['%-15s %.4f  %.2f' % (c, *w[c]) if c in w and w[c][0] >= 0.00005 else 'x 0 0' for c in namen]
        e = i + 3 + len(namen)
        L[k:e] = blk
        print('   ersetzt (%d Zeilen)' % len(blk))
    if '--schreiben' in argv:
        schreiben(ZIEL, '\n'.join(L) + '\n')


if __name__ == '__main__':
    main(sys.argv[1:])
