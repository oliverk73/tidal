#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Messsatz aus dem Thai-Marine-Pegelnetz anlegen (Oliver 11.11.2026: Phraek Mueang).

Daten: water_levels/Thailand_RTN/<station>_<sensor>.json (py/download_rtn_thailand.py, 6 Stichprobenwochen 15 min,
UTC+7, Ausreisser per gleitendem Median wie in py/rtn_thailand_pruefen.py). Fit mit 11 Haupttiden (mehr laufen auf
den luckenhaften Wochen aus dem Ruder: Kreuzprobe 20-160 cm). Kreuzprobe Phraek Mueang: 10,6 cm gegen 22,8 cm fuer
den naechsten Satz (Pak Nam Pak Phanang, 39 km). Pegelnull willkuerlich -> Z0 = -Minimum der 19-Jahres-Kurve.

Usage: venv/bin/python py/rtn_thailand_messsatz.py [--schreiben]
"""
import datetime as dt
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import qld_msq_fit as Q                                            # noqa: E402
import rtn_thailand_pruefen as P                                   # noqa: E402
import scheitelfit as SF                                           # noqa: E402
import xtide_modell as X                                           # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ZIEL = os.path.join(ROOT, 'harmonics/utide/harmonics_utide_observations.txt')
NUTZ = ['M2', 'S2', 'N2', 'K2', 'K1', 'O1', 'P1', 'Q1', 'M4', 'MS4', 'MN4']
SAETZE = [('37_41.json', 'Phraek Mueang (Hua Sai), Nakhon Si Thammarat, Thailand', 'Nakhon Si Thammarat', 8.0175, 100.3197,
           'RTN-Pegel 37 (Phraek Mueang), Sensor 41')]


def main(argv):
    kopf = X.kopf_lesen(ZIEL)
    namen, speeds, arg, fak = kopf
    tg = np.arange(dt.datetime(2008, 1, 1).timestamp(), dt.datetime(2027, 1, 1).timestamp(), 3600.0)
    neu = []
    for datei, name, prov, la, lo, kennung in SAETZE:
        t, h, _s = P.messung(os.path.join(ROOT, 'water_levels/Thailand_RTN', datei))
        s = pd.Series(h, index=pd.to_datetime(t, unit='s', utc=True))
        _s, _t, z0, w, hh, n = Q.fit(s, NUTZ, kopf, speeds, arg, fak)
        rms = float(np.sqrt(np.mean(P.wochenmittel_ab(_t, _s.values - hh) ** 2)))
        zc = -float(SF.hoehe_und_ableitungen(tg, 0.0, w, kopf)[0].min())
        tage = len(np.unique((t // 86400).astype(int)))
        print('%s: %d Werte, %d Tage, RMS %.1f cm, %s, Z0 %.2f' % (name, len(t), tage, 100 * rms,
              ' '.join('%s %.3f/%.0f' % (k, *w[k]) for k in ('M2', 'S2', 'K1', 'O1')), zc))
        neu += ['#', '# ' + name, '# BEGIN HOT COMMENTS', '# country: Thailand', '# province: %s' % prov,
                '# source: Royal Thai Navy tide gauge network (SDA), 15-min data', '# station_id_context: %s' % kennung,
                '# date_imported: %s' % dt.date.today().strftime('%Y%m%d'),
                '# datum: Chart Datum (approx., CD~LAT from constituents)', '# confidence: 6',
                '# note: %d Tage in 6 Stichprobenwochen %s..%s, 11 Tiden, RMS %.1f cm; Kreuzprobe 10.6 cm (Nachbar 39 km 22.8 cm)'
                % (tage, dt.datetime.fromtimestamp(t[0], dt.timezone.utc).date(), dt.datetime.fromtimestamp(t[-1], dt.timezone.utc).date(), 100 * rms),
                '# note: py/rtn_thailand_messsatz.py', '# !units: meters', '# !longitude: %.4f' % lo, '# !latitude: %.4f' % la,
                name, '+00:00 :Asia/Bangkok', '%.4f meters' % zc]
        neu += ['%-15s %.4f  %.2f' % (c, *w[c]) if c in w and w[c][0] >= 0.00005 else 'x 0 0' for c in namen]
    if '--schreiben' in argv:
        from sicher_schreiben import schreiben
        T = open(ZIEL, encoding='iso-8859-1').read().rstrip('\n').split('\n')
        assert not any(x[1] in T for x in SAETZE)
        schreiben(ZIEL, '\n'.join(T + neu) + '\n')
        print('->', os.path.relpath(ZIEL, ROOT))


if __name__ == '__main__':
    main(sys.argv[1:])
