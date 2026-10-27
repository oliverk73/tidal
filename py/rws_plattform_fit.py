#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Messfits der niederlaendischen Nordsee-Plattformen aus Rijkswaterstaat-Messungen (WATHTE, 10 min, UTC).

27.10.2026: Die TICON-4-Saetze aus GESLA-4 'RWS' (station_id_context ...-nld-rws) liegen an allen pruefbaren
Plattformen krumm ~24 min zu frueh (Greenwich: halbtaegig -12 Grad, eintaegig -6 Grad, Amplitude 3-4 % kleiner;
J6, L9, A12, D15, Q1, F16 gegen RWS-Messung) -> nicht glatt korrigierbar, daher Neufit aus der Messung, alte Saetze
archiviert (harmonics/help/rws_plattformen_20261027_loeschen.csv). K13A platform (classic 2004) und K14 stimmen (1 %).
F3 und L9-1 (TICON aus CMEMS) hatten +01:00 mit UTC-Phasen -> py/ticon_cmems_meridian.py.

Download ueber die RWS-DDAPI (ddapi20-waterwebservices, ohne Schluessel) monatsweise nach water_levels/Netherlands_RWS_platforms/.
Fit wie py/qld_msq_fit.py (Momentanwert zur vollen Stunde, 67 Konstituenten + Obertiden, Probe am letzten Jahr, Eigenversatz 0).
Usage: venv/bin/python py/rws_plattform_fit.py [--laden] [--schreiben]  -> harmonics_utide_observations.txt
"""
import datetime as dt
import json
import os
import sys
import urllib.request

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
REIHEN = os.path.join(ROOT, 'water_levels/Netherlands_RWS_platforms')
URL = 'https://ddapi20-waterwebservices.rijkswaterstaat.nl/ONLINEWAARNEMINGENSERVICES/OphalenWaarnemingen'
JAHRE = range(2015, 2026)

# RWS-Code, Name (wie der ersetzte Bestandssatz, von Oliver geprueft), Position aus dem RWS-Katalog, ersetzter Satz
PLATTFORMEN = [
    ('j6', 'Platform J6, Netherlands', 53.816632, 2.95001, 'Platform J6, Netherlands'),
    ('l9', 'L9 Platform, Netherlands', 53.616667, 4.966667, 'L9 Platform, Netherlands'),
    ('a12', 'Platform A12, Netherlands', 55.383333, 3.8, 'Platform A12, Netherlands'),
    ('d15', 'Platform D15 A, Netherlands', 54.325667, 2.93575, 'Platform D15 A, Netherlands'),
    ('q1.1', 'Platform Hoorn Q1, Netherlands', 52.925335, 4.150361, 'Platform Hoorn Q1, Netherlands'),
    ('f16', 'Platform F16 A, Netherlands', 54.116667, 4.012222, 'Platform F16 A, Netherlands'),
]


def laden(code):
    """Monatsweise WATHTE-Messung (ProcesType meting), UTC, eine Hoedanigheid (die haeufigste)."""
    os.makedirs(REIHEN, exist_ok=True)
    pfad = os.path.join(REIHEN, code + '.csv')
    rows = []
    for j in JAHRE:
        for m in range(1, 13):
            b = '%d-%02d-01T00:00:00.000+00:00' % (j, m)
            e = '%d-%02d-01T00:00:00.000+00:00' % (j + (m == 12), m % 12 + 1)
            q = {'Locatie': {'Code': code}, 'Periode': {'Begindatumtijd': b, 'Einddatumtijd': e},
                 'AquoPlusWaarnemingMetadata': {'AquoMetadata': {'Compartiment': {'Code': 'OW'}, 'Grootheid': {'Code': 'WATHTE'},
                                                                 'ProcesType': 'meting'}}}
            try:
                r = json.load(urllib.request.urlopen(urllib.request.Request(URL, json.dumps(q).encode(), {'Content-Type': 'application/json'}),
                                                     timeout=120))
            except Exception:                                          # leerer Monat: Antwort ohne JSON
                continue
            for wl in r.get('WaarnemingenLijst', []):
                hd = wl['AquoMetadata'].get('Hoedanigheid', {}).get('Code')
                for x in wl['MetingenLijst']:
                    v = x['Meetwaarde'].get('Waarde_Numeriek')
                    if v is not None and abs(v) < 1000:
                        rows.append((x['Tijdstip'], v / 100.0, hd))
    d = pd.DataFrame(rows, columns=['t', 'waterlevel_m', 'hoedanigheid'])
    if d.empty:
        print('%s: keine Messung' % code)
        return
    d = d[d.hoedanigheid == d.hoedanigheid.value_counts().index[0]]
    d['time_utc'] = pd.to_datetime(d.t, utc=True).dt.tz_localize(None)
    d = d.drop_duplicates('time_utc').sort_values('time_utc')
    d[['time_utc', 'waterlevel_m', 'hoedanigheid']].to_csv(pfad, index=False)
    print('%s: %d Werte %s..%s (%s)' % (code, len(d), d.time_utc.iloc[0].date(), d.time_utc.iloc[-1].date(), d.hoedanigheid.iloc[0]))


def main(argv):
    if '--laden' in argv:
        for p in PLATTFORMEN:
            laden(p[0])
    kopf = X.kopf_lesen(ZIEL)
    namen, speeds, arg, fak = kopf
    voll = SF.konstituenten(namen, SF.CONSTIT_67) + [k for k in S.OBERTIDEN if k in namen]
    L = open(ZIEL, encoding='iso-8859-1').read().rstrip('\n').split('\n')
    heute = dt.date.today().strftime('%Y%m%d')
    bestand = [r for r in H.load_records() if r['lat'] and 51 < r['lat'] < 57 and 1 < r['lon'] < 8 and not r['current']]
    for code, name, la, lo, alt in PLATTFORMEN:
        pfad = os.path.join(REIHEN, code + '.csv')
        if not os.path.exists(pfad):
            print('%s: keine Reihe' % code)
            continue
        d = pd.read_csv(pfad, parse_dates=['time_utc']).set_index('time_utc')['waterlevel_m'].dropna()
        hd = pd.read_csv(pfad, usecols=['hoedanigheid']).hoedanigheid.iloc[0]
        d = d[d.index.minute == 0]                                   # Momentanwert zur vollen Stunde
        jm = d.groupby(d.index.year).median()
        print('\n== %s (%s)\n   Jahresmedian: %s' % (name, code, ' '.join('%d:%.2f' % (j, v) for j, v in jm.items())))
        s, start = Q.abschnitt(d)
        if start != d.index[0]:
            print('   Pegelnull-Sprung: Reihe ab %s' % start.date())
        tage = (s.index[-1] - s.index[0]).days
        if len(s) < 24 * 300:
            print('   zu kurz (%d h)' % len(s))
            continue
        nutz = Q.rayleigh(voll, speeds, namen, tage)
        probe = ''
        if tage >= 2 * 365:
            grenze = s.index[-1] - pd.Timedelta(days=365)
            _, _, pz0, pw, _, _ = Q.fit(s[:grenze], nutz, kopf, speeds, arg, fak)
            te = s[grenze:]
            tt = np.array([i.timestamp() for i in te.index])
            rp = te.values - SF.hoehe_und_ableitungen(tt, pz0, pw, kopf)[0]
            rp = rp[np.abs(rp - np.median(rp)) < 5 * np.std(rp)]
            probe = '%.0f' % (100 * np.sqrt(np.mean(rp ** 2)))
        s, t, z0, w, h, aus = Q.fit(s, nutz, kopf, speeds, arg, fak)
        rms = float(np.sqrt(np.mean((s.values - h) ** 2)))
        r2 = 1 - np.var(s.values - h) / np.var(s.values)
        sub = slice(None, None, 7)
        eig = min(range(-30, 31), key=lambda m: np.std(s.values[sub] - SF.hoehe_und_ableitungen(t[sub] - 60 * m, z0, w, kopf)[0]))
        nah = sorted(((H.km({'lat': la, 'lon': lo}, r), r) for r in bestand), key=lambda x: x[0])
        nah = [(k, r) for i, (k, r) in enumerate(nah) if k <= 6.0 or (i < 3 and k <= 40.0)]
        print('   %d h %s..%s (%d d, %d Konst.)  R2 %.3f  RMS %.3f  Probe %s cm  Eigenversatz %+d  M2 %.3f@%.1f  S2 %.3f@%.1f  K1 %.3f@%.1f  O1 %.3f@%.1f  Z0 %.2f%s' % (
            len(s), s.index[0].date(), s.index[-1].date(), tage, len(nutz), r2, rms, probe or '-', eig, *w['M2'], *w['S2'], *w['K1'], *w['O1'], z0,
            ('  %d Ausreisser' % aus) if aus else ''))
        for k, r in nah:
            print('      ~ %s [%s] %.1f km %.0f%%' % (r['name'].split(',')[0], r['file'].split('/')[-1].replace('harmonics', '').replace('.txt', '')[:22],
                                                    k, 100 * H.curve_diff(Q.rec(w), r)[1]))
        blk = ['#', '# %s (RWS %s)' % (name.split(',')[0], code), '# BEGIN HOT COMMENTS', '# country: Netherlands',
               '# source: Rijkswaterstaat WATHTE %s, least squares' % code,
               '# note: Rijkswaterstaat Waterwebservices (DDAPI), gemessene 10-min-Werte, UTC, Bezug %s.' % hd,
               '# station_id_context: RWS-%s' % code, '# date_imported: %s' % heute, '# datum: %s' % ('MSL' if hd == 'MSL' else hd),
               '# confidence: 9',
               '# utide: pts=%d period=%s..%s r2=%.4f rms=%.4fm const=%d' % (len(s), s.index[0].date(), s.index[-1].date(), r2, rms, len(nutz)),
               '# note: %s Messfit (py/rws_plattform_fit.py) ersetzt %s; der alte Satz lag ~36 min zu spaet.' % (heute, alt),
               ('# note: Probe am letzten Messjahr %s cm RMS.' % probe) if probe else '# note: Reihe kuerzer als zwei Jahre, keine Probe.',
               '# !units: meters', '# !longitude: %.4f' % lo, '# !latitude: %.4f' % la,
               name, '+00:00 :Europe/Amsterdam', '%.4f meters' % z0]
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
