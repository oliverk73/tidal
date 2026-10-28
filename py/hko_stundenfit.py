#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Hongkong: 14 HKO-Saetze aus Stundenwerten statt aus interpolierten HW/NW neu gefittet (28.10.2026).

Die Saetze vom 09.04.2026 (harmonics_utide_tidetables) stammen aus HKO-HW/NW, dazwischen interpoliert: gegen HKOs eigene
Stundenvorhersage 2025-2026 RMS 6-8 cm, Ko Lau Wan 11, Tai Po Kau 14 cm (bis 72 cm). HKO-Open-Data liefert die
astronomische Stundentide (dataType=HHOT, HKT, m ueber CD, Stunde "01" = 01:00) -> Cache tide_tables/hongkong_hko.
Fit wie scheitelfit (67 Konstituenten, ohne Steigungszeilen), Probe Fit 2025 gegen 2026, geschrieben wird der Endfit
2025-2026, wenn er besser ist als der alte Satz.

Usage: venv/bin/python py/hko_stundenfit.py [--schreiben]
"""
import datetime as dt
import json
import os
import sys
import urllib.request

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scheitelfit as SF                                           # noqa: E402
import xtide_modell as X                                           # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATEI = os.path.join(ROOT, 'harmonics/utide/harmonics_utide_tidetables.txt')
CACHE = os.path.join(ROOT, 'tide_tables/hongkong_hko')
URL = 'https://data.weather.gov.hk/weatherAPI/opendata/opendata.php?dataType=HHOT&lang=en&rformat=json&station=%s&year=%d'
JAHRE = (2025, 2026)
NAMEN = dict(CCH='Cheung Chau', CLK='Chek Lap Kok', CMW='Chi Ma Wan', KCT='Kwai Chung', KLW='Ko Lau Wan', LOP='Lok On Pai',
             MWC='Gemini Point (Ma Wan)', QUB='Quarry Bay', SPW='Shek Pik', TAO='Tai O', TBT='Tsim Bei Tsui',
             TMW='Tai Miu Wan', TPK='Tai Po Kau', WAG='Waglan Island')


def reihe(code):
    t, h = [], []
    for y in JAHRE:
        pfad = os.path.join(CACHE, '%s_%d.json' % (code, y))
        if not os.path.exists(pfad):
            os.makedirs(CACHE, exist_ok=True)
            open(pfad, 'wb').write(urllib.request.urlopen(URL % (code, y), timeout=120).read())
        for z in json.load(open(pfad))['data']:
            d0 = dt.datetime(y, int(z[0]), int(z[1]), tzinfo=dt.timezone.utc) - dt.timedelta(hours=8)
            for k, v in enumerate(z[2:]):
                if v not in ('', '---'):
                    t.append((d0 + dt.timedelta(hours=k + 1)).timestamp())
                    h.append(float(v))
    return np.array(t), np.array(h)


def rest(t, h, z0, w, kopf):
    m, _, _ = SF.hoehe_und_ableitungen(t, z0, w, kopf)
    return m - h


def main(argv):
    kopf = X.kopf_lesen(DATEI)
    namen, speeds, arg, fak = kopf
    nutz = SF.konstituenten(namen, SF.CONSTIT_67)
    grenze = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc).timestamp()
    heute = dt.date.today().strftime('%Y%m%d')
    for code, n in NAMEN.items():
        name = n + ', Hong Kong, China'
        t, h = reihe(code)
        z_alt, w_alt, _, mer = X.satz_lesen(DATEI, name)
        wg_alt = {k: (a, X.greenwich(g, speeds[k], mer)) for k, (a, g) in w_alt.items() if k in speeds}
        r_alt = rest(t, h, z_alt, wg_alt, kopf)
        lern = t < grenze
        z1, w1 = SF.fit(t[lern], h[lern], nutz, speeds, arg, fak, gewicht=0)
        r_pr = rest(t[~lern], h[~lern], z1, w1, kopf)
        z0, w = SF.fit(t, h, nutz, speeds, arg, fak, gewicht=0)
        r_neu = rest(t, h, z0, w, kopf)
        besser = np.std(r_pr) < np.std(r_alt[~lern]) and np.std(r_neu) < np.std(r_alt)
        print('%-24s alt %4.1f cm (max %4.1f) | Probe 2026 %4.1f | neu %4.1f cm (max %4.1f)  %s' % (
            n, np.std(r_alt) * 100, np.abs(r_alt - r_alt.mean()).max() * 100, np.std(r_pr) * 100,
            np.std(r_neu) * 100, np.abs(r_neu).max() * 100, 'schreiben' if besser else 'bleibt'))
        if '--schreiben' in argv and besser:
            wm = {k: (a, g + speeds[k] * mer) for k, (a, g) in w.items()}          # Greenwich -> Meridian des Satzes
            SF.satz_schreiben(DATEI, name, z0, wm, namen, [
                '%s Neufit an HKO-Stundenvorhersage (HHOT %s) 2025-2026 statt interpolierter HW/NW (py/hko_stundenfit.py):' % (heute, code),
                '-- RMS %.1f cm (vorher %.1f cm), Probe Fit 2025 gegen 2026 %.1f cm.' % (
                    np.std(r_neu) * 100, np.std(r_alt) * 100, np.std(r_pr) * 100)])


if __name__ == '__main__':
    main(sys.argv[1:])
