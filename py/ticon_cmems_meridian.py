#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TICON-Saetze aus GESLA-4 'CMEMS' mit Meridian +01:00, deren Phasen UTC sind -> Meridian +00:00 (Phasen bleiben).

Befund 27.10.2026 (Nachtrag zu py/ticon_zeit_richten.py vom 10.09., das nur Saetze mit Zwilling bis 2 km sah):
gegen eigene Fits amtlicher Messreihen liegen M2/S2/O1 glatt -60 min daneben (K1 bei Mikrotide verrauscht):
  * DMI (opendataapi.dmi.dk, sealev_dvr, ohne Schluessel): 27 von 43 daenischen Saetzen gemessen, alle -57..-66 min
    (Aarhus, Ballen, Dragoer, Drogden, Fredericia, Frederikshavn, Fynshav, Grenaa, Hobro, Holbaek, Hou, Juelsminde, Koege,
    Korsoer, Kobenhavn, Nyborg, Randers, Rodvig, Roskilde, Roedbyhavn, Sjaellands Odde, Udbyhoej, Vedbaek, Bagenkop,
    Nordre Roese, Skagen, Vidaaslusen). Die uebrigen 16 aus derselben Lieferung: FES -31..-58 min, wo pruefbar.
  * SMHI (opendata-download-ocobs, RW timvaerde): Uddevalla, Goeteborg Agnesberg, Juten -60; Kristineberg gegen
    Brofjorden/Smoegen -53..-61. Goeteborg Klippan stimmt (0 min) und bleibt.
  * RWS-Messung 2015-2025 (py/rws_plattform_fit.py): F3 -58, L9-1 -60 min.
  * Bayonne (Pont Blanc): Messfit-Zwilling am selben Ort -60..-72 min.
Nicht angefasst: Blankenberge (stimmt), deutsche/polnische Ostsee-Saetze, Morlaix, Porto Torres (keine Messreihe zur Hand).

Usage: venv/bin/python3 py/ticon_cmems_meridian.py [--schreiben]
"""
import datetime as dt
import os
import re
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sicher_schreiben import schreiben                             # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATEI = os.path.join(ROOT, 'harmonics/ticon/harmonics_ticon4_worldwide.txt')
HEUTE = dt.date.today().strftime('%Y%m%d')

EINZELN = {'uddevalla-udd-swe-cmems': 'SMHI Uddevalla -60 min',
           'goteborgagnesberg-got-swe-cmems': 'SMHI Goeteborg-Agnesberg -60 min',
           'juten-jut-swe-cmems': 'SMHI Juten-Djuroekvarn -62 min',
           'kristineberg-kri-swe-cmems': 'SMHI Brofjorden/Smoegen -53..-61 min',
           'f3platformtg-f3p-nld-cmems': 'RWS-Messung F3 -58 min',
           'l91tg-l91-nld-cmems': 'RWS-Messung L9 -60 min',
           'bayonnepontblanctg_05minute-bay-fra-cmems': 'Messfit-Zwilling Bayonne (Pont Blanc) -60 min'}


def grund(sid):
    if sid.endswith('-dnk-cmems'):
        return 'DMI-Messreihen: 27 von 43 daenischen CMEMS-Saetzen -60 min'
    return EINZELN.get(sid)


def main(argv):
    zeilen = open(DATEI, encoding='iso-8859-1').read().split('\n')
    kopf, treffer = [], []
    for k, z in enumerate(zeilen):
        if z.startswith('#'):
            kopf.append(z)
            continue
        if k + 1 < len(zeilen) and zeilen[k + 1].startswith('+01:00 '):
            m = re.search(r'station_id_context:\s*(\S+)', '\n'.join(kopf[-30:]))
            g = grund(m.group(1)) if m else None
            if g:
                treffer.append((k, z, g))
        kopf = []
    for _, name, g in treffer:
        print('%-40s %s' % (name, g))
    print('%d Saetze' % len(treffer))
    if '--schreiben' not in argv:
        return 0
    for k, name, g in reversed(treffer):
        zeilen[k + 1] = '+00:00 ' + zeilen[k + 1].split(' ', 1)[1]
        zeilen[k:k] = ['# note: %s Zeit berichtigt: Meridian +01:00 -> +00:00, +1.00 h (Phasen waren UTC).' % HEUTE,
                       '# note: -- %s' % g[:70],
                       '# note: -- Belegt gegen Messreihen, siehe py/ticon_cmems_meridian.py.']
    shutil.copy2(DATEI, os.path.join(ROOT, 'harmonics/backup', os.path.basename(DATEI) + '.vor_cmems_meridian_%s' % HEUTE))
    schreiben(DATEI, '\n'.join(zeilen))
    print('%d Saetze berichtigt' % len(treffer))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
