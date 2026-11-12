#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Arrifana (IOC arri) neu fitten (Oliver 12.11.2026: "Ja").

Anlass py/modell_reihen_vergleich.py: der Satz vom 20.05.2026 (UTide, R2 0.68, RMS 0.51 m) war an der eigenen Reihe 4.5 cm
schlechter als FES; K1 0.101 statt 0.07 m wie an allen Nachbarn. Ursache: 09/2019-06/2021 liefert der Sensor Unsinn
(Mittel -3.3 m, Hub ~0, Versatz +-2 h) und lag mit im Fit. Monatspruefung gegen FES (scratchpad arri.py):
sauber 08/2018-08/2019 und 07/2021-10/2022 (Versatz 0, Hubfaktor 0.96-1.05), dazwischen Pegelnull-Sprung ~0.6 m.
IOC hat nach 10/2022 keine Daten mehr.
Vorgehen: Fit des juengeren Abschnitts, Versatz des aelteren = Median seines Rests dagegen, dann gemeinsamer Fit
(Momentanwert zur vollen Stunde, Rayleigh, Tagesfilter wie ghana_gpha_fit). Z0 bleibt MSL (0) wie bisher.
--schreiben ersetzt Konstituenten + utide-/source-Kopfzeilen im Bestandssatz.
Usage: venv/bin/python py/arrifana_neufit.py [--schreiben]
"""
import datetime as dt
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ghana_gpha_fit as G                                         # noqa: E402
import health_check as H                                           # noqa: E402
import messreihe_qualitaet as M                                    # noqa: E402
import qld_msq_fit as Q                                            # noqa: E402
import scheitelfit as SF                                           # noqa: E402
import seine_haropa_fit as S                                       # noqa: E402
import xtide_modell as X                                           # noqa: E402
from sicher_schreiben import schreiben                             # noqa: E402

NAME = 'Arrifana, Portugal'
REIHE = os.path.join(M.REIHEN, 'Portugal_IOC/arri_Arrifana.csv')
ABSCHNITTE = [('2018-08-29', '2019-09-01'), ('2021-07-01', '2022-10-04')]


def main(argv):
    kopf = X.kopf_lesen(Q.ZIEL)
    namen, speeds, arg, fak = kopf
    voll = SF.konstituenten(namen, SF.CONSTIT_67) + [k for k in S.OBERTIDEN if k in namen]
    o = M.lies(REIHE)
    s = pd.Series([h for _t, h in o], index=pd.to_datetime([t for t, _h in o], unit='s')).sort_index()
    s.index = s.index.round('1min')
    s = s[~s.index.duplicated()]
    s = s[s.index.minute == 0]
    a = s[ABSCHNITTE[0][0]:ABSCHNITTE[0][1]]
    b = s[ABSCHNITTE[1][0]:ABSCHNITTE[1][1]]
    nb = Q.rayleigh(voll, speeds, namen, (b.index[-1] - b.index[0]).days)
    b, nwb = G.tagesfilter(b, kopf, nb, speeds, arg, fak)
    _, _, z0b, wb, _, _ = Q.fit(b, nb, kopf, speeds, arg, fak)
    ta = np.array([i.timestamp() for i in a.index])
    versatz = float(np.median(a.values - SF.hoehe_und_ableitungen(ta, z0b, wb, kopf)[0]))
    a = a - versatz
    print('aelterer Abschnitt: %d h, Pegelnull-Versatz %+.3f m' % (len(a), versatz))
    s = pd.concat([a, b]).sort_index()
    tage = (s.index[-1] - s.index[0]).days
    nutz = Q.rayleigh(voll, speeds, namen, tage)
    s, nwa = G.tagesfilter(s, kopf, nutz, speeds, arg, fak)
    s, t, z0, w, h, aus = Q.fit(s, nutz, kopf, speeds, arg, fak)
    rms = float(np.sqrt(np.mean((s.values - h) ** 2)))
    r2 = 1 - np.var(s.values - h) / np.var(s.values)
    # Probe: Fit nur juengerer (lueckenloser) Abschnitt -> aelterer
    rp = a.values - SF.hoehe_und_ableitungen(ta, z0b, wb, kopf)[0] + versatz
    probe = 100 * float(np.std(rp))
    print('Fit: %d h %s..%s, %d Konst., R2 %.4f, RMS %.1f cm, Probe juengerer->aelterer %.1f cm, %d Tage gefiltert' % (
        len(s), s.index[0].date(), s.index[-1].date(), len(nutz), r2, 100 * rms, probe, nwa))
    for k in ('M2', 'S2', 'N2', 'K2', 'K1', 'O1'):
        print('   %-3s %.4f@%.2f' % (k, *w[k]))
    alt = [r for r in H.load_records() if r['name'] == NAME][0]
    print('   alt: M2 %.4f@%.2f  K1 %.4f@%.2f' % (*alt['amp']['M2'], *alt['amp']['K1']))
    if '--schreiben' not in argv:
        return
    L = open(Q.ZIEL, encoding='iso-8859-1').read().rstrip('\n').split('\n')
    i = L.index(NAME)
    assert L[i + 1].startswith('+00:00 ')
    k = i
    while L[k - 1].startswith('#'):
        k -= 1
    heute = dt.date.today().strftime('%Y%m%d')
    kopfz = []
    for z in L[k:i]:
        if z.startswith('# Harmonic constants derived') or z.startswith('# using UTide') or z.startswith('# from 20') \
                or z.startswith('# R^2') or z.startswith('# Constituents analyzed'):
            continue
        if z.startswith('# source:'):
            z = '# source: IOC Sea Level Monitoring (arri), least squares'
        if z.startswith('# date_imported:'):
            z = '# date_imported: %s' % heute
        kopfz.append(z)
    j = next(n for n, z in enumerate(kopfz) if z.startswith('# !units'))
    kopfz[j:j] = ['# utide: pts=%d period=%s..%s r2=%.4f rms=%.4fm const=%d' % (
                      len(s), s.index[0].date(), s.index[-1].date(), r2, rms, len(nutz)),
                  '# note: %s Neufit (py/arrifana_neufit.py): Sensorausfall 09/2019-06/2021 raus, alter Fit R2 0.68.' % heute,
                  '# note: Abschnitte 08/2018-08/2019 + 07/2021-10/2022, Pegelnull-Sprung %+.2f m angeglichen; Probe %.1f cm.' % (
                      versatz, probe)]
    blk = kopfz + [NAME, L[i + 1], '0.0000 meters']
    blk += ['%-15s %.4f  %.2f' % (c, *w[c]) if c in w and w[c][0] >= 0.00005 else 'x 0 0' for c in namen]
    L[k:i + 3 + len(namen)] = blk
    schreiben(Q.ZIEL, '\n'.join(L) + '\n')
    print('geschrieben')


if __name__ == '__main__':
    main(sys.argv[1:])
