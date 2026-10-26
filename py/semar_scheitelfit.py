#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SEMAR-Saetze mit Tagestide: Scheitelfit statt Kosinus-Zwischenkurve (Oliver 26.10.2026).

Die SEMAR-Saetze in harmonics_utide_tidetables.txt sind UTide-Fits auf eine
Kosinuskurve zwischen den gedruckten Hoch- und Niedrigwassern (Import 12.05.2026).
Wo die Tagestide ueberwiegt (Formzahl > 3), gibt es an vielen Tagen nur einen
Scheitel je Richtung; die Kosinusboegen tragen dann kaum halbtaegiges Signal,
und der Fit verliert M2: 47-66 % von FES, Phase 8-25 Grad spaet (Coatzacoalcos
M2 4.5 cm gegen 7.4 cm aus 32 Jahren UNAM-Messung).

Hier wird mit py/scheitelfit.py direkt an die Scheitel gefittet (h(t_i)=h_i,
h'(t_i)=0 im XTide-Modell). Probe: Fit 2024+2025, gemessen an den Scheiteln von
2026; danach Endfit ueber alle drei Jahrgaenge.

Usage: venv/bin/python py/semar_scheitelfit.py [--schreiben] [code ...]
"""
import calendar
import datetime as dt
import os
import sys
import unicodedata

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import health_check as H                                           # noqa: E402
import scheitelfit as SF                                            # noqa: E402
import semar_referenz as SR                                         # noqa: E402
import xtide_modell as X                                            # noqa: E402

ZIEL = os.path.join(SR.ROOT, 'harmonics/utide/harmonics_utide_tidetables.txt')
GEWICHT = 3.0   # Stunden; 0.3 aus scheitelfit.py liess bei Tagestide die Scheitelzeiten 20-50 min laufen
CODES = ['altamira', 'coatza', 'dosbocas', 'frontera', 'lapesca', 'rosalia', 'tuxpan']


def ohne_akzent(t):
    return unicodedata.normalize('NFKD', t).encode('ascii', 'ignore').decode()


def epoche(z):
    return calendar.timegm(z.timetuple())


def main(argv):
    kopf = X.kopf_lesen(ZIEL)
    namen, speeds, arg, fak = kopf
    nutz = SF.konstituenten(namen, SF.CONSTIT_67)
    nur = [a for a in argv if not a.startswith('--')] or CODES
    recs = [r for r in H.load_records() if r['lat'] is not None and not r['current']]
    heute = dt.date.today().strftime('%Y%m%d')
    for st in SR.stationen():
        if st['code'] not in nur:
            continue
        ev = []
        for p in st['dateien']:
            ev += SR.datei(p)[0]
        ev = sorted(set(ev))
        t = np.array([epoche(z) for z, _h in ev], dtype=float)
        h = np.array([x for _z, x in ev])
        grenze = epoche(dt.datetime(2026, 1, 1))
        # ORTE schreibt "Santa Rosalia", der Bestand "Santa Rosalía"
        alt = [r for r in recs if ohne_akzent(r['name']) == ohne_akzent(st['name']) and r['file'].endswith('harmonics_utide_tidetables.txt')]
        print('\n== %s (%s)  %d Scheitel %s..%s' % (st['name'], st['code'], len(ev), ev[0][0].date(), ev[-1][0].date()))
        lern, test = t < grenze, t >= grenze
        if test.sum() > 100 and lern.sum() > 300:
            z0, w = SF.fit(t[lern], h[lern], nutz, speeds, arg, fak, GEWICHT)
            rms, dtm, _ = SF.guete(t[test], h[test], z0, w, kopf, versatz=False)
            print('   Probe 2026 (Fit 24+25): %.1f cm, Scheitelzeit %.0f min' % (rms * 100, dtm))
        for r in alt:
            for n_, d_, rr, tt, oo in SF.bestand([r], r['lat'], r['lon'], kopf, t, h, umkreis=0.01):
                print('   alter Satz, alle Jahre:  %.1f cm, Scheitelzeit %.0f min (Hoehenversatz %+.1f cm)' % (rr * 100, tt, oo * 100))
        z0, w = SF.fit(t, h, nutz, speeds, arg, fak, GEWICHT)
        rms, dtm, _ = SF.guete(t, h, z0, w, kopf, versatz=False)
        lo, hi = SF.bandbreite(t, h, z0, w, kopf)
        print('   Endfit: %.1f cm, %.0f min; Kurve %.2f..%.2f m, Tafel %.2f..%.2f m' % (rms * 100, dtm, lo, hi, h.min(), h.max()))
        print('   M2 %.3f/%.0f  S2 %.3f/%.0f  K1 %.3f/%.0f  O1 %.3f/%.0f  Z0 %.3f' % (
            *w['M2'], *w['S2'], *w['K1'], *w['O1'], z0))
        if '--schreiben' in argv and len(alt) == 1:
            if lo < h.min() - 0.15 or hi > h.max() + 0.15:
                print('   NICHT geschrieben: Kurve verlaesst die Tafel')
                continue
            SF.satz_schreiben(alt[0]['file'], alt[0]['name'], z0, w, namen, [
                '%s Scheitelfit aus den SEMAR-Tafeln 2024-2026 (py/semar_scheitelfit.py):' % heute,
                'der vorige UTide-Fit auf Kosinusboegen verlor bei Tagestide M2 (47-66 Prozent von FES).',
                'Tafeltreue %.1f cm an %d Scheiteln, Scheitelzeit %.0f min. Oliver.' % (rms * 100, len(t), dtm)])
            print('   geschrieben')


if __name__ == '__main__':
    main(sys.argv[1:])
