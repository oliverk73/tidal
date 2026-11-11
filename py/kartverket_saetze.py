#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Saetze aus Kartverket-Vorhersagen (vannstand.kartverket.no tideapi), Oliver 11.11.2026.

Anlass: Pruefung der FES-Luecken-Saetze in Fjorden gegen Kartverket. Kartverket rechnet jeden Kuestenpunkt vom
naechsten festen Pegel (Faktor + Zeitversatz; Sogndal = Kaupanger x 1,00). 9 von 10 FES-Saetzen treffen das auf
2,7-5,5 cm, Orkanger nicht (11 cm, -10 min): FES bildet den Trondheimsfjord nicht ab, Kartverket nimmt Trondheim x 0,98.
Kaupanger (KAZ, Sognefjord) ist fester Kartverket-Pegel, fehlte im Bestand; Messungen erst ab 07/2026 abrufbar ->
Fit von zwei Jahren Kartverket-Vorhersage (ein Jahr laesst SA weg: 12 cm Rest) (Probe gegen 132 Tage Messung: 12,5 cm, Messfit 12,7 cm = Wetter).
Falle: 10-min-Messwerte nicht per resample('1h').mean() mitteln (Stempel 25 min zu frueh, M2 12 Grad).

Usage: venv/bin/python py/kartverket_saetze.py [--schreiben | --ersetzen]
"""
import datetime as dt
import os
import re
import sys
import urllib.request

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import qld_msq_fit as Q                                            # noqa: E402
import xtide_modell as X                                           # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ZIEL = os.path.join(ROOT, 'harmonics/utide/harmonics_utide_tidetables.txt')
API = 'https://vannstand.kartverket.no/tideapi.php'
# Name, Provinz, lat, lon, Stationscode (fester Pegel) oder None (Kuestenpunkt), Notiz
SAETZE = [
    ('Kaupanger (Sognefjord), Vestland, Norway', 'Vestland', 61.18248, 7.252396, 'KAZ',
     'fester Pegel KAZ, Messungen ab 07/2026 (Probe 132 Tage: 12.5 cm, Messfit 12.7 = Wetter)'),
    ('Orkanger, Trøndelag, Norway', 'Trøndelag', 63.3209, 9.8559, None,
     'ersetzt FES-Satz vom 11.11. (11 cm/-10 min daneben)'),
]


def vorhersage(code, la, lo):
    q = ('tide_request=stationdata&stationcode=%s' % code) if code else ('tide_request=locationdata&lat=%.6f&lon=%.6f' % (la, lo))
    u = '%s?%s&fromtime=2026-01-01T00:00&totime=2028-01-01T00:00&datatype=pre&refcode=cd&lang=en&interval=60&dst=0&tzone=0' % (API, q)
    x = urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': 'weather-tides/1.0'}), timeout=300).read().decode()
    m = re.search(r'<location ([^>]*?)/?>', x)
    a = dict(re.findall(r'(\w+)="([^"]*)"', m.group(1)))
    pts = re.findall(r'value="(-?[\d.]+)" time="([^"]+)" flag="pre"', x)
    s = pd.Series([float(a) / 100 for a, b in pts], index=pd.to_datetime([b for a, b in pts], utc=True))
    return s, a.get('name', ''), a.get('factor')


def main(argv):
    kopf = X.kopf_lesen(ZIEL)
    namen, speeds, arg, fak = kopf
    heute = dt.date.today().strftime('%Y%m%d')
    neu = []
    bloecke = []
    for name, prov, la, lo, code, notiz in SAETZE:
        start = len(neu)
        s, bezug, faktor = vorhersage(code, la, lo)
        # Bis 11.11. abends fest 730 Tage: bei KAZ (nur 1 Jahr) blies der Fit Paare gleicher Frequenz auf (bis 72 km).
        # Kartverket liefert fuer manche Pegel nur ein Jahr (KAZ): Rayleigh nach echter Laenge; SA trotzdem mit, wenn >= 360 Tage
        tage = (s.index[-1] - s.index[0]).days
        nutz = Q.rayleigh([k for k in namen if k in speeds], speeds, namen, tage)
        if tage >= 360 and 'SA' not in nutz:
            nutz.insert(0, 'SA')
        _s, _t, z0, w, h, _n = Q.fit(s, nutz, kopf, speeds, arg, fak)
        rms = float(np.sqrt(np.mean((_s.values - h) ** 2)))
        assert max(a for a, g in w.values()) < 3 * w['M2'][0] + 0.5, 'aufgeblasene Konstituenten'
        print('%-40s Bezug %s (Faktor %s), %d Werte, %d Tage, %d Tiden, Fit %.2f cm, Z0 %.2f, M2 %.3f/%.0f' % (name, bezug, faktor, len(s), tage, len(nutz), 100 * rms, z0, *w['M2']))
        neu += ['#', '# ' + name, '# BEGIN HOT COMMENTS', '# country: Norway',
                '# source: Kartverket tide predictions (vannstand.kartverket.no)',
                '# date_imported: %s' % heute, '# datum: Chart Datum', '# confidence: 7',
                '# !units: meters', '# !longitude: %.4f' % lo, '# !latitude: %.4f' % la, '# province: %s' % prov,
                ('# note: %s Fit %d Tage stuendlich (%.1f cm), Kartverket-Bezug %s%s; %s' % (
                    heute, tage, 100 * rms, bezug, (' x ' + faktor) if faktor else '', notiz))[:190],
                '# note: py/kartverket_saetze.py',
                name, '+00:00 :Europe/Oslo', '%.4f meters' % z0]
        neu += ['%-15s %.4f  %.2f' % (c, *w[c]) if c in w and w[c][0] >= 0.00005 else 'x 0 0' for c in namen]
        bloecke.append((name, neu[start:]))
    if '--ersetzen' in argv:                                         # vorhandene Saetze an Ort und Stelle ersetzen
        from sicher_schreiben import schreiben
        T = open(ZIEL, encoding='iso-8859-1').read().rstrip('\n').split('\n')
        for name, blk in bloecke:
            i = T.index(name)
            a = T.index('# ' + name, i - 40)
            assert T[a - 1] == '#' and a < i
            T[a - 1:i + 3 + len(namen)] = blk
        '\n'.join(T).encode('latin-1')                           # wirft bei Nicht-Latin-1 (sicher_schreiben)
        schreiben(ZIEL, '\n'.join(T) + '\n')
        print('->', os.path.relpath(ZIEL, ROOT))
    if '--schreiben' in argv:
        from sicher_schreiben import schreiben
        T = open(ZIEL, encoding='iso-8859-1').read().rstrip('\n').split('\n')
        assert not any(x[0] in T for x in SAETZE)
        assert all(c.encode('latin-1') for c in neu)
        schreiben(ZIEL, '\n'.join(T + neu) + '\n')
        print('->', os.path.relpath(ZIEL, ROOT))


if __name__ == '__main__':
    main(sys.argv[1:])
