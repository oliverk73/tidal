#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Kenya Ports Authority Tide Tables 2026 (tide_tables/kenya_kpa/, Oliver 28.10.2026) als Gegenprobe; Z0 auf Kartennull.

Die KPA-Tafeln (HW/NW Kilindini und Dar es Salaam, EAT = UTC+3, Hoehen ueber Kartennull der Admiralty-Karten) bestaetigen unsere
UHSLC-Messfits in der Zeit (Scheitel 4-5 min), die Hoehen liegen aber glatt verschoben: die Saetze stehen auf dem UHSLC-Pegelnull
(faelschlich "datum: MSL"). Z0 wird um den Median-Versatz gegen die Tafel-Scheitel verschoben -> Kilindini MSL 1.85 m (KPA: 1.88).
Nebenorte (KPA nur Zeitdifferenzen): Malindi, Kilifi, Shimoni/Wasini, Tanga, Kilwa, Lindi, Mtwara passen auf <=7 min; Lamu KPA +40,
unser UHSLC-Messfit +14 (Messung bleibt).
Usage: venv/bin/python3 py/kpa_kartennull.py [--schreiben]
"""
import datetime as dt
import os
import re
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scheitelfit as SF                                           # noqa: E402
import xtide_modell as X                                           # noqa: E402
from sicher_schreiben import schreiben                             # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TXT = os.path.join(ROOT, 'tide_tables/kenya_kpa/kpa.txt')            # pdftotext -layout des PDFs
MON = ['JANUARY', 'FEBRUARY', 'MARCH', 'APRIL', 'MAY', 'JUNE', 'JULY', 'AUGUST', 'SEPTEMBER', 'OCTOBER', 'NOVEMBER', 'DECEMBER']
SAETZE = {'KILINDINI': [('harmonics/utide/harmonics_utide_observations.txt', 'Mombasa (Kilindini Harbour), Kenya')],
          'DAR': [('harmonics/utide/harmonics_utide_observations.txt', 'Dar es Salaam, Tanzania'),
                  ('harmonics/ticon/harmonics_ticon4_worldwide.txt', 'Dar Es Salaam, Tanzania')]}


def scheitel():
    ev = {k: [] for k in SAETZE}
    ort = mon = None
    for z in open(TXT, encoding='utf-8').read().split('\n'):
        u = z.upper()
        if 'KILINDINI TIDES' in u:
            ort = 'KILINDINI'
        elif 'DAR-ES-SALAAM TIDES' in u:
            ort = 'DAR'
        if z.strip().upper() in MON:
            mon = MON.index(z.strip().upper()) + 1
        m = re.match(r'^\s*(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\w*\s+(\d\d)\s+(.*)$', z)
        if m and ort and mon:
            for hhmm, h in re.findall(r'(\d{4})\s+(-?\d+\.\d)', m.group(3)):
                try:
                    t = dt.datetime(2026, mon, int(m.group(2)), int(hhmm[:2]), int(hhmm[2:]), tzinfo=dt.timezone.utc) - dt.timedelta(hours=3)
                except ValueError:
                    continue
                ev[ort].append((t.timestamp(), float(h)))
    return {k: sorted(set(v)) for k, v in ev.items()}


def main(argv):
    ev = scheitel()
    heute = dt.date.today().strftime('%Y%m%d')
    for ort, saetze in SAETZE.items():
        t = np.array([e[0] for e in ev[ort]])
        h = np.array([e[1] for e in ev[ort]])
        for datei, name in saetze:
            pfad = os.path.join(ROOT, datei)
            kopf = X.kopf_lesen(pfad)
            z0, w, _, _ = X.satz_lesen(pfad, name)
            r, tm, versatz = SF.guete(t, h, z0, w, kopf, versatz=True)
            print('%-38s %d Scheitel  Zeit %.0f min  Hoehe %.1f cm nach Versatz %+.3f m  Z0 %.4f -> %.4f' % (
                name, len(t), tm, r * 100, versatz, z0, z0 + versatz))
            if '--schreiben' not in argv:
                continue
            L = open(pfad, encoding='iso-8859-1').read().split('\n')
            i = L.index(name)
            assert L[i + 2].endswith(' meters')
            L[i + 2] = '%.4f meters' % (z0 + versatz)
            k = i
            while not L[k].startswith('# datum:'):
                k -= 1
            L[k] = '# datum: Chart Datum (KPA Tide Tables 2026, Admiralty-Karte)'
            L[i:i] = ['# note: %s Z0 %+.3f m auf Kartennull der KPA-Tafel 2026 (vorher UHSLC-Pegelnull);' % (heute, versatz),
                      '# note: -- Zeit gegen %d KPA-Scheitel %.0f min, siehe py/kpa_kartennull.py.' % (len(t), tm)]
            schreiben(pfad, '\n'.join(L))


if __name__ == '__main__':
    main(sys.argv[1:])
