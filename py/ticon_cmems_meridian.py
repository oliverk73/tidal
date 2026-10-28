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
Nicht angefasst: Blankenberge (stimmt).

Nachtrag 28.10.2026: die uebrigen CMEMS-Saetze mit Meridian ungleich 0 gegen die CMEMS-Stundenreihen selbst
(INSITU_GLO_PHY_SSH_DISCRETE_MY_013_053, oeffentlicher S3, TIME in UTC, water_levels/CMEMS_tg_pruefung/, Fit der
letzten 3 Jahre): Amplituden gleich, Phasen um Meridian x 60 min zu frueh -- Ostsee DE/PL -45..-66 (+01:00),
FI/EE/BG/GR -95..-141 (+02:00), Trabzon -177 (+03:00), Morlaix -56, Porto Torres -48..-56. Kronstadt/Sankt Petersburg
(+03:00) -142/-148, Mikrotide mit +-40 min Jahresstreuung; nach der Berichtigung +32/+38 statt -148.
Greifswald (-126) passt zu keiner glatten Stufe -> Messfit statt Berichtigung (py/cmems_tg_fit.py).

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


# 28.10.: Fit der CMEMS-Stundenreihe 2023-2025 (bzw. letzte 3 Jahre), Median M2/S2/K1/O1 in min
NACHTRAG = {'balchik-bal-bgr-cmems': -121, 'burgas-bur-bgr-cmems': -112, 'burgassouth-bur-bgr-cmems': -142,
            'darlowo-dar-pol-cmems': -54, 'gdansk-gda-pol-cmems': -51, 'hamina-ham-fin-cmems': -113,
            'hanko-han-fin-cmems': -105, 'heltermaa-hel-est-cmems': -112, 'ioc_trab-ioc-tur-cmems': -178,
            'itea-ite-grc-cmems': -120, 'kalkgrundtg-kal-deu-cmems': -58, 'kasos-kas-grc-cmems': -120,
            'kronstadt-kro-rus-cmems': -146, 'lehtma-leh-est-cmems': -124, 'luebecktg-lue-deu-cmems': -56,
            'morlaixvigicruestg_06minute-mor-fra-cmems': -60, 'narvajoesuu-nar-est-cmems': -131,
            'paldiski-pal-est-cmems': -122, 'plimiri-pli-grc-cmems': -115, 'rmn_portotorres-rmn-ita-cmems': -51,
            'rohukula-roh-est-cmems': -119, 'rostocktg-ros-deu-cmems': -64, 'schleswigtg-sch-deu-cmems': -64,
            'sillamae-sil-est-cmems': -102, 'soru-sor-est-cmems': -134, 'stpetersburg-stp-rus-cmems': -128,
            'thessaloniki-the-grc-cmems': -126, 'triigi-tri-est-cmems': -114, 'turku-tur-fin-cmems': -117,
            'ustka-ust-pol-cmems': -52, 'varna-var-bgr-cmems': -112, 'wismartg-wis-deu-cmems': -62,
            'zakynthos-zak-grc-cmems': -121}


def grund(sid):
    if sid in NACHTRAG:
        return 'CMEMS-Stundenreihe (UTC) %+d min' % NACHTRAG[sid]
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
        if k + 1 < len(zeilen) and re.match(r'\+0[1-3]:00 ', zeilen[k + 1]):
            m = re.search(r'station_id_context:\s*(\S+)', '\n'.join(kopf[-30:]))
            g = grund(m.group(1)) if m else None
            if g:
                treffer.append((k, z, g))
        kopf = []
    for _, name, g in treffer:
        print('%-40s %s %s' % (name, zeilen[_ + 1][:6], g))
    print('%d Saetze' % len(treffer))
    if '--schreiben' not in argv:
        return 0
    for k, name, g in reversed(treffer):
        mer = zeilen[k + 1][:6]
        zeilen[k + 1] = '+00:00 ' + zeilen[k + 1].split(' ', 1)[1]
        zeilen[k:k] = ['# note: %s Zeit berichtigt: Meridian %s -> +00:00, +%d.00 h (Phasen waren UTC).' % (HEUTE, mer, int(mer[1:3])),
                       '# note: -- %s' % g[:70],
                       '# note: -- Belegt gegen Messreihen, siehe py/ticon_cmems_meridian.py.']
    shutil.copy2(DATEI, os.path.join(ROOT, 'harmonics/backup', os.path.basename(DATEI) + '.vor_cmems_meridian_%s' % HEUTE))
    schreiben(DATEI, '\n'.join(zeilen))
    print('%d Saetze berichtigt' % len(treffer))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
