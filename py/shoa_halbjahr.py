#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SHOA-Tafelsaetze (Chile) ueber zwei Fenster neu fitten (10.11.2026).

Die 15 SHOA-Saetze in harmonics_utide_tidetables.txt stammen aus 3 Monaten HW/NW (Browser-Seiten, SHOA blockt
Skripte); K2/P1 wurden am 21.10. ueber Nachbarn angekoppelt. Oliver speichert ein zweites Fenster (eine Seite
zeigt 3 Monate als Reiter). Mit ~6 Monaten ueber > 182 Tage Spanne trennen sich K2/S2 und P1/K1 selbst ->
Scheitelfit (py/scheitelfit.py) ueber alle Scheitel, ohne Kopplung.

Gegenprobe: alt/neu gegen die naechsten Messsaetze (nicht Tafel) in 100 km. (Fenster-gegen-Fenster taugt nicht:
67 Konstituenten in 3 Monaten laufen aus dem Ruder, 52 cm.)
SHOA-Zeiten: UTC-4 fest (Seitentext), Hoehen ueber Plano de Reduccion.

Usage: venv/bin/python py/shoa_halbjahr.py "<Satzname>" <html/htm ...> [--schreiben]
"""
import datetime as dt
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'batch'))
import batch_utide_shoa_chile as B                                 # noqa: E402
import health_check as H                                           # noqa: E402
import qld_msq_fit as Q                                            # noqa: E402
import scheitelfit as SF                                           # noqa: E402
import xtide_modell as X                                           # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ZIEL = os.path.join(ROOT, 'harmonics/utide/harmonics_utide_tidetables.txt')


def main(argv):
    schreib = '--schreiben' in argv
    argv = [a for a in argv if a != '--schreiben']
    name, dateien = argv[0], argv[1:]
    kopf = X.kopf_lesen(ZIEL)
    namen, speeds, arg, fak = kopf
    nutz = SF.konstituenten(namen, SF.CONSTIT_67)
    ent = {}
    for f in dateien:
        for t, h, _k in B.parse_shoa_html(f):
            ent[t] = h
    tl = sorted(ent)
    t = np.array([(x - dt.timedelta(hours=B.TZ_OFFSET_H)).replace(tzinfo=dt.timezone.utc).timestamp() for x in tl])
    h = np.array([ent[x] for x in tl])
    monate = sorted({(x.year, x.month) for x in tl})
    print(name, len(t), 'Scheitel,', len(monate), 'Monate', monate[0], '..', monate[-1])
    z0, w = SF.fit(t, h, nutz, speeds, arg, fak)
    rr, tm, _ = SF.guete(t, h, z0, w, kopf, versatz=False)
    rec = [r for r in H.load_records() if r['name'] == name and r['file'].endswith('harmonics_utide_tidetables.txt')]
    assert len(rec) == 1, rec
    r = rec[0]
    neu = Q.rec(w)
    print('  Treue %.1f cm / %.0f min | neu vs. alt %.1f %%' % (rr * 100, tm, 100 * H.curve_diff(neu, r)[1]))
    print('   ', ', '.join('%s %.3f/%.0f' % (k, *w[k]) for k in ('M2', 'S2', 'K2', 'N2', 'K1', 'P1', 'O1')))
    zeugen = sorted((H.km(r, m), m) for m in H.load_records()
                    if not m['current'] and m['lat'] is not None and 'observations' in m['file'] and H.km(r, m) <= 100)
    for km, m in zeugen[:3]:
        print('  Zeuge %-40s %3.0f km: alt %.1f %%, neu %.1f %%' % (m['name'][:40], km, 100 * H.curve_diff(r, m)[1],
                                                                    100 * H.curve_diff(neu, m)[1]))
    if not schreib:
        return
    from sicher_schreiben import schreiben
    heute = dt.date.today().strftime('%Y%m%d')
    L = open(ZIEL, encoding='iso-8859-1').read().rstrip('\n').split('\n')     # frisch lesen
    k = [i for i, x in enumerate(L) if x == name and L[i + 1].startswith(('+', '-')) and ':' in L[i + 1]]
    assert len(k) == 1, k
    e = k[0]
    a = e
    while L[a - 1].startswith('#') and L[a - 1] != '#':
        a -= 1
    kopfz = [x for x in L[a:e] if not (x.startswith('# note: 20261021 S2/K1 corrected for K2/P1'))]
    kopfz.append('# note: %s Scheitelfit %d Monate %d-%02d..%d-%02d (py/shoa_halbjahr.py): %d Scheitel, Treue %.1f cm / %.0f min;'
                 ' K2/P1 aus eigenen Daten statt Kopplung' % (heute, len(monate), *monate[0], *monate[-1], len(t), rr * 100, tm))
    # Vorspann ueber dem Satz (UTide-Statistik des alten Fits) nachziehen
    v = a - 1
    while v > 0 and L[v].startswith('#') and 'Harmonic constants derived from SHOA' not in L[v]:
        v -= 1
    if 'Harmonic constants derived from SHOA' in L[v]:
        for i in range(v, a):
            if 'HW/LW points' in L[i]:
                L[i] = '# %d HW/LW points, Scheitelfit (refit %s)' % (len(t), heute)
            elif L[i].startswith('# from '):
                L[i] = '# from %d-%02d-01 to %d-%02d-end (%d months)' % (*monate[0], *monate[-1], len(monate))
            elif L[i].startswith('# R^2'):
                L[i] = '# RMS error = %.4f m at the table extremes, median time error %.0f min' % (rr, tm)
            elif L[i].startswith('# Constituents analyzed:'):
                L[i] = '# Constituents analyzed: %d' % len(nutz)
    assert L[e + 2].endswith('meters'), L[e:e + 3]
    n = 0
    while e + 3 + n < len(L) and (L[e + 3 + n][:1].isalnum() or L[e + 3 + n].startswith('x ')) and not L[e + 3 + n].startswith('#'):
        n += 1
    assert n == len(namen), (n, len(namen))
    tz = ['%-15s %.4f  %.2f' % (c, *w[c]) if c in w and w[c][0] >= 0.00005 else 'x 0 0' for c in namen]
    L[a:e + 3 + n] = kopfz + [L[e], L[e + 1], '%.4f meters' % z0] + tz
    schreiben(ZIEL, '\n'.join(L) + '\n')
    print('-> geschrieben')


if __name__ == '__main__':
    main(sys.argv[1:])
