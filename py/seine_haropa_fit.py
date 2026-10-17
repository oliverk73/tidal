#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Harmonische Saetze fuer HAROPA-Pegel an der Seine aus den gemessenen Reihen (HydroPortail).

Oliver 17.10.2026: Rouen fehlte. Reihen: py/download_hydroportail.py (Rohdaten seit 12/2014, mm ueber CMH =
Cote marine du Havre, 4.38 m unter NGF). Fit: kleinste Quadrate auf Stundenwerte 2016-2025 mit den 67
UTide-Konstituenten plus Obertiden bis M12 (Saegezahn: 7 h Fallen, Anstieg in 30 min); Probe an der
unabhaengigen Messung 2026. Befund Rouen: Fit auf die HAROPA-Tafeln (capitainerie-rouen.com,
py/haropa_seine_tafeln.py) trifft die Tafel auf 10 cm, zwischen den Scheiteln aber 90 cm daneben -> Messfit.

Usage: venv/bin/python py/seine_haropa_fit.py [code ...] [--schreiben]  -> harmonics/utide/harmonics_utide_observations.txt
"""
import datetime as dt
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scheitelfit as SF                                           # noqa: E402
import xtide_modell as X                                           # noqa: E402
from sicher_schreiben import schreiben                             # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ZIEL = os.path.join(ROOT, 'harmonics/utide/harmonics_utide_observations.txt')
REIHEN = os.path.join(ROOT, 'water_levels/France_HydroPortail')
TAFELN = os.path.join(ROOT, 'tide_tables/france/haropa_rouen/haropa_hwlw.json')
# code -> (Satzname, Breite, Laenge, Ort in der HAROPA-Tafel); Position = Hub'Eau-Stationskoordinate
PEGEL = {
    'H503011001': ('Rouen, France', 49.4433, 1.0720, 'Rouen'),
}
OBERTIDEN = ['S6', '2SM6', '2NM6', 'MSN6', 'M7', '3MK7', '2MSN8', '2(MS)8', '3MN8', '3MS8', '2(MN)8', 'M10', '4MS10',
             '4MN10', '3MNS10', 'M12', '5MS12', '4MNS12', '4M2S12', '2MN2', '3MS2', 'MNS2', 'MSN2', '2MS2K2']
FIT = ('2016-01-01', '2025-12-31')


def kq(t, y, nutz, speeds, arg, fak):
    C, S, _ = X.matrix(t, nutz, speeds, arg, fak)
    A = np.hstack([np.ones((len(t), 1)), C, S])
    l, *_ = np.linalg.lstsq(A, y, rcond=None)
    n = len(nutz)
    return float(l[0]), {k: (float(np.hypot(l[1 + j], l[1 + n + j])), float(np.degrees(np.arctan2(l[1 + n + j], l[1 + j])) % 360))
                         for j, k in enumerate(nutz)}


def main(argv):
    kopf = X.kopf_lesen(ZIEL)
    namen, speeds, arg, fak = kopf
    nutz = SF.konstituenten(namen, SF.CONSTIT_67) + [k for k in OBERTIDEN if k in namen]
    L = open(ZIEL, encoding='iso-8859-1').read().rstrip('\n').split('\n')
    heute = dt.date.today().strftime('%Y%m%d')
    tafeln = json.load(open(TAFELN)) if os.path.exists(TAFELN) else {}
    wahl = [a for a in argv if not a.startswith('--')] or list(PEGEL)
    for code in wahl:
        name, lat, lon, tafelort = PEGEL[code]
        s = pd.read_csv(os.path.join(REIHEN, 'hp_%s.csv' % code), parse_dates=['time']).set_index('time')['waterlevel_m']
        tr, te = s[FIT[0]:FIT[1]], s['2026-01-01':]
        t = np.array([i.timestamp() for i in tr.index])
        z0, w = kq(t, tr.values, nutz, speeds, arg, fak)
        h = SF.hoehe_und_ableitungen(t, z0, w, kopf)[0]
        rms = float(np.sqrt(np.mean((tr.values - h) ** 2)))
        r2 = 1 - np.var(tr.values - h) / np.var(tr.values)
        # Eigenversatz: Kurve gegen die eigene Reihe, muss 0 min zeigen
        t30 = t[:24 * 60]
        eig = min(range(-60, 61, 5), key=lambda m: np.std(tr.values[:len(t30)] - SF.hoehe_und_ableitungen(t30 - 60 * m, z0, w, kopf)[0]))
        tt = np.array([i.timestamp() for i in te.index])
        rp = te.values - SF.hoehe_und_ableitungen(tt, z0, w, kopf)[0]
        probe = 'Probe Messung 2026: %.0f cm (sd %.0f)' % (100 * np.sqrt(np.mean(rp ** 2)), 100 * np.std(rp))
        if tafelort in tafeln:
            ev = tafeln[tafelort]
            tz = np.array([dt.datetime.fromisoformat(x[:-1]).replace(tzinfo=dt.timezone.utc).timestamp() for x, _ in ev])
            hz = np.array([v for _, v in ev])
            rt, dtt, _ = SF.guete(tz, hz, z0, w, kopf)
            probe += ', HAROPA-Tafel 2026-30: %.0f cm, %.0f min' % (100 * rt, dtt)
        print('%-30s %d h  R2 %.3f  RMS %.3f m  Eigenversatz %+d min  Z0 %.2f  M2 %.3f@%.0f M4 %.3f@%.0f  %s' % (
            name, len(tr), r2, rms, eig, z0, *w['M2'], *w['M4'], probe))
        blk = ['#', '# ' + name, '# BEGIN HOT COMMENTS', '# country: France',
               '# source: HAROPA gauge (Vigicrues/HydroPortail %s) measurements, least squares' % code,
               '# station_id_context: HydroPortail-%s' % code, '# date_imported: %s' % heute,
               '# datum: CMH (Cote marine du Havre, 4.38 m unter NGF)', '# confidence: 7',
               '# utide: pts=%d period=%s..%s r2=%.4f rms=%.4fm const=%d' % (len(tr), tr.index[0].date(), tr.index[-1].date(), r2, rms, len(nutz)),
               '# note: %s Seine, Flusstide mit Saegezahn, NW im Modell ~35 min zu frueh (py/seine_haropa_fit.py) (Oliver).' % heute,
               '# note: %s.' % probe,
               '# !units: meters', '# !longitude: %.4f' % lon, '# !latitude: %.4f' % lat,
               '# region: Seine-Maritime', name, '+00:00 :Europe/Paris', '%.4f meters' % z0]
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
