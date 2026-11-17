#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Alle gedruckten Atlas-Raten eines visitMyHarbour-Atlas zu Stromsaetzen (Oliver 17.11.2026: "jeden Satz eintragen,
den es gibt -- Stroemung aendert sich kleinraeumig").

Eingabe: quellen/tidal_streams/visitmyharbour/ablesung/<atlas>.txt, je Zeile "stunde x y nipp,spring" (Pixel im
Stundenbild, von Hand abgelesen mit Gitter). Ablauf:
  1. Ablesungen gleicher Lage (< 28 px) ueber die 13 Stunden zu Punkten zusammenfassen (je Stunde die naechste).
  2. Nur Punkte mit >= 10 Stunden; fehlende Stunden aus den Nachbarstunden.
  3. Richtung: Achse aus FES2014 (M2-Ellipse); Vorzeichen wechselt nur an den Kenterminima der Atlasreihe,
     welche Haelfte Flut ist, entscheidet die Korrelation mit FES2014 (HW Bezugshafen -> Modellstrom).
  4. Lage gegen OSM-Landmaske, Abstand zu vorhandenen Saetzen; Satz wie vmh_atlas (Nipp/Spring nach Hub).

  venv/bin/python py/vmh_ablesung.py thames [--schreiben]
"""
import cmath
import csv
import math
import os
import re
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fes2014_strom as F                                            # noqa: E402
import hafenatlas_stroeme as A                                       # noqa: E402
import health_check as H                                             # noqa: E402
import osm_land as OL                                                # noqa: E402
import vmh_atlas as V                                                # noqa: E402
import xtide_modell as X                                             # noqa: E402

ROOT = V.ROOT
ABL = os.path.join(ROOT, 'quellen/tidal_streams/visitmyharbour/ablesung')
PRUEFLISTE = 'harmonics/help/neu_pruefen_20261117.csv'          # eine Liste fuer die ganze Atlas-Runde (auch nach Mitternacht)
RICHTUNG = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE', 'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW']


def _interp(ticks, v):
    t = sorted(ticks)
    return float(np.interp(v, [a for a, _ in t], [b for _, b in t]))


ATLAS = {
    # Seite aufrecht (thames_estuary_XX.png 1024x1030); Gradnetz am Rand abgelesen, an Margate/Herne Bay geprueft
    'thames': dict(bezug=V.SHEERNESS, atlas='NP249 (Thames Estuary)', land='England, United Kingdom',
                   lat=lambda y: _interp([(180, 52.0), (390, 51 + 50 / 60), (587, 51 + 40 / 60), (787, 51.5), (983, 51 + 20 / 60)], y),
                   lon=lambda x: 1 + (x - 357) / 729.0),
    # Seite quer (east_solent_XX.png 1536x786); 1 Grad W bei x=645, 19,4 px/Laengenminute; 50 50 N bei y=148, 30,5 px/Breitenminute
    'east_solent': dict(bezug=V.PORTSMOUTH, atlas='NP337 (East Solent)', land='England, United Kingdom',
                        lat=lambda y: 50 + 50 / 60 - (y - 148) / (30.5 * 60),
                        lon=lambda x: -1 - (645 - x) / (19.4 * 60),
                        weglassen=[(520, 247)],        # Einfahrt Portsmouth = vorhandener Satz Portsmouth Harbour Entrance
                        achse={(504, 188): 350}),      # im Hafen Portsmouth: Fahrwasser N-S, FES-Zelle liegt in Spithead
    # Seite aufrecht (dover_strait_pXX.png 1024x1417), jede Seite auf den Rahmen der HW-Seite normiert (69..929 x 129..1160);
    # Gradnetz: Laenge 1 Grad bei x=147 .. 1 50' bei x=856, Breite 51 20' bei y=252 .. 50 50' bei y=927 (linear, auch darunter)
    'dover_strait': dict(bezug=V.DOVER, atlas='NP233 (Dover Strait)', land='England, United Kingdom',
                         regionen={'France': 'Hauts-de-France, France', 'United Kingdom': 'England, United Kingdom'},
                         lat=lambda y: float(np.polyval(np.polyfit([252, 478, 704, 927], [51 + 20 / 60, 51 + 10 / 60, 51, 50 + 50 / 60], 1), y)),
                         lon=lambda x: float(np.polyval(np.polyfit([147, 287, 429, 571, 714, 856], [1 + i / 6 for i in range(6)], 1), x))),
    # West Country NP254 (Falmouth-Teignmouth): Seiten per vmh_seiten.py ausgerichtet (wc254_nXX); Gradnetz 5W x=185,
    # 4 30'W x=398, 4W x=610, 3 30'W x=822; 50 30'N y=411, 50N y=737, 49 30'N y=1073. Bezug HW Devonport.
    'west_country_np254': dict(bezug=V.DEVONPORT, atlas='NP254 (West Country)', land='England, United Kingdom',
                               regionen={'United Kingdom': 'England, United Kingdom'},
                               lat=lambda y: float(np.interp(y, [411, 737, 1073], [50.5, 50.0, 49.5], left=None)) if 411 <= y <= 1073
                               else 50.5 - (y - 411) / 652.0,
                               lon=lambda x: -5 + (x - 185) / (212.3 * 2)),
    # West Country NP255 (Lizard-Padstow, Scilly): Seiten per vmh_seiten.py ausgerichtet (wc255_nXX); Gradnetz 6 30'W x=233,
    # 6W x=435, 5 30'W x=636, 5W x=838; 50 30'N y=303, 50N y=609, 49 30'N y=927. Bezug HW Devonport.
    'west_country_np255': dict(bezug=V.DEVONPORT, atlas='NP255 (West Country)', land='England, United Kingdom',
                               regionen={'United Kingdom': 'England, United Kingdom'},
                               lat=lambda y: float(np.polyval(np.polyfit([303, 609, 927], [50.5, 50.0, 49.5], 1), y)),
                               lon=lambda x: -6.5 + (x - 233) / (201.7 * 2), r=34),
    # English Channel East NP250 (Uebersicht, 1 px ~ 280 m): Seiten per vmh_seiten.py (ece_nXX); Gradnetz-Striche oben
    # 2W x=299, 1W x=556, 0 x=812, 1E x=1069 (256,7 px/Grad); 50N y=431, 50 30'N y=239, 49 30'N y=636. Bezug HW Dover.
    # Nur Punkte >= 8 km von vorhandenen Atlas-Saetzen (Kuestennahes decken die Detailatlanten ab).
    'english_channel_east': dict(bezug=V.DOVER, atlas='NP250 (English Channel East)', land='England, United Kingdom',
                                 regionen={'United Kingdom': 'England, United Kingdom', 'France': 'Normandie, France'},
                                 lat=lambda y: float(np.polyval(np.polyfit([239, 431, 636], [50.5, 50.0, 49.5], 1), y)),
                                 lon=lambda x: (x - 812) / 256.7, abstand_atlas=8.0,
                                 sperre=[(48.6, 49.85, -3.2, -1.55)]),    # Kanalinseln: NP264 (Detail) folgt
    # English Channel West NP250 (Uebersicht): Seiten per vmh_seiten.py (ecw_nXX); Gradnetz oben 7W x=137, 6W x=338,
    # 5W x=538, 4W x=737, 3W x=937, 2W x=1138 (200,1 px/Grad); 50N y=281, 49N y=586, 50 30'N y=131, 49 30'N y=746.
    'english_channel_west': dict(bezug=V.DOVER, atlas='NP250 (English Channel West)', land='England, United Kingdom',
                                 regionen={'United Kingdom': 'England, United Kingdom', 'France': 'Bretagne, France'},
                                 lat=lambda y: float(np.polyval(np.polyfit([131, 281, 586, 746], [50.5, 50.0, 49.0, 48.5], 1), y)),
                                 lon=lambda x: -7 + (x - 137) / 200.1, abstand_atlas=8.0,
                                 sperre=[(48.6, 49.85, -3.2, -1.5)]),     # Kanalinseln: NP264 (Detail) folgt
    # Channel Islands NP264: Seiten per vmh_seiten.py (ci_nXX, 1024x1792 aufrecht); Gradnetz 3W x=42, 2W x=649 (607 px/Grad),
    # Breite 49 10'N y=940, 49N y=1095 (933 px/Grad). Bezug HW Dover.
    'channel_islands': dict(bezug=V.DOVER, atlas='NP264 (Channel Islands)', land='Jersey',
                            regionen={'France': 'Normandy, France'},
                            lat=lambda y: 49 + 10 / 60 + (940 - y) / 933.0,
                            lon=lambda x: -3 + (x - 42) / 607.0, r=34),
    # Alderney Race NP264 (Plan): Seiten per Landmaske ausgerichtet (ald_nXX); Gradnetz 2 25'W x=170, 2 20'W x=483,
    # 2 15'W x=800, 2 10'W x=1110 (62,6 px/'); 49 45'N y=287, 49 40'N y=768 (96,2 px/'). Etiketten wandern -> r=110. HW Dover.
    'alderney': dict(bezug=V.DOVER, atlas='NP264 (Alderney Race)', land='Alderney, Guernsey',
                     regionen={'Guernsey': 'Alderney, Guernsey'},
                     lat=lambda y: 49.75 - (y - 287) / (96.2 * 60),
                     lon=lambda x: -2 - 25 / 60 + (x - 170) / (62.6 * 60), r=110),
    # Lyme Bay: Seiten per py/vmh_seiten.py ausgerichtet (lyme_nXX, 1024x1417 aufrecht); Gradnetz 3 30'W x=205, 3W x=418,
    # 2 30'W x=631, 2W x=843; 50 30'N y=551, 50N y=877. Bezug HW Devonport.
    'lyme_bay': dict(bezug=V.DEVONPORT, atlas='NP263 (Lyme Bay)', land='England, United Kingdom',
                     regionen={'United Kingdom': 'England, United Kingdom'},
                     lat=lambda y: 50.5 - (y - 551) / (326.0 * 2),
                     lon=lambda x: -3.5 + (x - 205) / (212.7 * 2)),
    # Portland: Seiten per py/vmh_seiten.py ausgerichtet (portland_nXX); Gradnetz 2 35'W x=335 .. 2 15'W x=1070 (36,7 px/'),
    # 50 35'N y=268, 50 30'N y=550 (56,4 px/'). Bezug HW Devonport.
    'portland': dict(bezug=V.DEVONPORT, atlas='NP257 (Portland)', land='England, United Kingdom',
                     regionen={'United Kingdom': 'England, United Kingdom'},
                     lat=lambda y: 50 + 35 / 60 - (y - 268) / (56.4 * 60),
                     lon=lambda x: -2 - 35 / 60 + (x - 335) / (36.7 * 60),
                     # Westseite Portland (West Bay, Wirbel): FES-Achse 92 Grad unbrauchbar; Pfeile SSE (Flut, speist den
                     # Ostlaufstrom um den Bill) -2..+4, NNW sonst -> Achse und Vorzeichen von Hand
                     achse={(544, 364): 150, (599, 378): 170, (587, 434): 175},
                     vorzeichen={(544, 364): [-1, -1, -1, -1, 1, 1, 1, 1, 1, 1, 1, 1, -1],
                                 (599, 378): [-1, -1, -1, 1, 1, 1, 1, 1, 1, 1, 1, -1, -1],
                                 (587, 434): [-1, -1, -1, 1, 1, 1, 1, 1, 1, 1, 1, -1, -1]}),
    # Seite quer (west_solent_XX.png 1536x786), Seite +1 um 18 px verschoben (Landmaske, in der Ablesung korrigiert);
    # Gradnetz: 2 W x=373, 1 20'W x=1147 (19,35 px/'); 50 50'N y=148, 50 30'N y=757 (30,45 px/')
    'west_solent': dict(bezug=V.PORTSMOUTH, atlas='NP337 (West Solent)', land='England, United Kingdom',
                        regionen={'United Kingdom': 'England, United Kingdom'},
                        lat=lambda y: 50 + 50 / 60 - (y - 148) / (30.45 * 60),
                        lon=lambda x: -2 + (x - 373) / (19.35 * 60),
                        # Poole Harbour (Doppeltide): Pfeile -6..-3 W, -2..0 E, +1..+2 W, +3..+5 E, +6 W; Flut = W in den Hafen
                        achse={(390, 380): 270}, vorzeichen={(390, 380): [1, 1, 1, 1, -1, -1, -1, 1, 1, -1, -1, -1, 1]}),
    # Seite quer (bristol_channel_pXX.png 1536x1004), auf den Rahmen der HW-Seite normiert (95..1257 x 72..777);
    # Gradnetz: 4 30'W x=265, 4W x=530, 3 30'W x=795, 3W x=1062; 51 30'N y=313, 51N y=727. Bezug HW Dover (Atlas: 5 h nach HW Swansea)
    'bristol_channel': dict(bezug=V.DOVER, atlas='NP258 (Bristol Channel)', land='Wales, United Kingdom',
                            regionen={'United Kingdom': 'Wales, United Kingdom'},
                            lat=lambda y: 51 + (727 - y) / 828.0,
                            lon=lambda x: float(np.polyval(np.polyfit([265, 530, 795, 1062], [-4.5, -4, -3.5, -3], 1), x)), r=40),
    # Irish Sea East NP259 (Uebersicht, 1 px ~ 180 m): Seiten per vmh_seiten.py (ise_nXX); Gradnetz 4 30'W x=257, 4W x=440,
    # 3 30'W x=623, 3W x=808; 54 30'N y=283, 54N y=590, 53 30'N y=905. Etiketten wandern bis 45 px. Bezug HW Dover.
    'irish_sea_east': dict(bezug=V.DOVER, atlas='NP259 (Irish Sea East)', land='England, United Kingdom',
                           regionen={'United Kingdom': 'England, United Kingdom'},
                           lat=lambda y: float(np.polyval(np.polyfit([283, 590, 905], [54.5, 54.0, 53.5], 2), y)),
                           lon=lambda x: float(np.polyval(np.polyfit([257, 440, 623, 808], [-4.5, -4, -3.5, -3], 1), x)),
                           r=45, abstand_atlas=8.0,
                           namen={(394, 525): 'Douglas Head (23 km E), Isle of Man Current',
                                  (451, 763): 'Great Orme (43 km N), Wales, United Kingdom Current',
                                  (793, 609): 'Lune Deep (Morecambe Bay), England, United Kingdom Current'}),
    # Irish Sea NP256 (Uebersicht, 1 px ~ 400 m): Seiten per vmh_seiten.py (isb_nXX); Gradnetz 7W x=186, 6W x=343, 5W x=500,
    # 4W x=656, 3W x=814; 54N y=316, 53N y=578, 52N y=836, 51N y=1086. Nur Luecken (abstand_atlas). Bezug HW Dover.
    'irish_sea_bristol': dict(bezug=V.DOVER, atlas='NP256 (Irish Sea)', land='Wales, United Kingdom',
                              regionen={'United Kingdom': 'Wales, United Kingdom', 'Ireland': 'Ireland'},
                              lat=lambda y: float(np.polyval(np.polyfit([316, 578, 836, 1086], [54, 53, 52, 51], 2), y)),
                              lon=lambda x: float(np.polyval(np.polyfit([186, 343, 500, 656, 814], [-7, -6, -5, -4, -3], 1), x)),
                              r=40, abstand_atlas=8.0,
                              namen={(280, 955): 'The Smalls (55 km WSW), Wales, United Kingdom Current',
                                     (366, 1032): 'The Smalls (57 km SSW), Wales, United Kingdom Current',
                                     (472, 410): 'Calf of Man (51 km SSW), Isle of Man Current',
                                     (492, 740): 'Strumble Head (38 km N), Wales, United Kingdom Current',
                                     (444, 653): 'Bardsey Island (39 km W), Wales, United Kingdom Current',
                                     (240, 904): 'Hook Head (48 km SSE), Leinster, Ireland Current',
                                     (418, 1134): 'Trevose Head (45 km NW), England, United Kingdom Current',
                                     (498, 1050): 'Lundy (24 km W), England, United Kingdom Current',
                                     (457, 110): 'Portpatrick (13 km SW), Scotland, United Kingdom Current',
                                     (393, 706): 'Arklow (44 km SE), Leinster, Ireland Current',
                                     (444, 565): 'Wicklow Head (44 km ENE), Leinster, Ireland Current',
                                     (540, 564): 'Caernarfon Bay (west), Wales, United Kingdom Current'}),
    # Firth of Clyde NP222: Seiten per vmh_seiten.py (clyde_nXX); Gradnetz 6W x=145 .. 4 20'W x=858 (71,3 px je 10');
    # 56N y=186, 55 30'N y=568, 55N y=937, 54 40'N y=1190. Bezug HW Dover.
    'firth_of_clyde': dict(bezug=V.DOVER, atlas='NP222 (Firth of Clyde)', land='Scotland, United Kingdom',
                           regionen={'United Kingdom': 'Scotland, United Kingdom'},
                           lat=lambda y: float(np.polyval(np.polyfit([186, 320, 443, 568, 694, 819, 937, 1066, 1190],
                                                                     [56 - i / 6 for i in range(9)], 2), y)),
                           lon=lambda x: -6 + (x - 145) / 427.8, r=30,
                           namen={(659, 212): 'Tail of the Bank (Greenock), Scotland, United Kingdom Current'}),
    # North Channel / North of Ireland NP222: Seiten per vmh_seiten.py (nch_nXX); Gradnetz 7 40'W x=136 .. 6W x=848 (71,2 px je 10');
    # 56N y=186, 55 30'N y=569, 55N y=937. Bezug HW Dover.
    'north_channel': dict(bezug=V.DOVER, atlas='NP222 (North Channel)', land='Northern Ireland, United Kingdom',
                          regionen={'United Kingdom': 'Northern Ireland, United Kingdom'},
                          lat=lambda y: float(np.polyval(np.polyfit([186, 320, 443, 569, 694, 819, 937],
                                                                    [56 - i / 6 for i in range(7)], 2), y)),
                          lon=lambda x: -7 - 40 / 60 + (x - 136) / 427.2, r=40,
                          namen={(487, 575): 'Inishowen Head (29 km N), Ulster, Ireland Current',
                                 (200, 553): 'Malin Head (18 km NNW), Ulster, Ireland Current',
                                 (424, 347): 'Rhinns of Islay (33 km WNW), Scotland, United Kingdom Current',
                                 (626, 195): 'Ardnave Point (18 km NW), Scotland, United Kingdom Current'}),
    # North of Ireland / SW Scotland NP218 (Uebersicht): Seiten per vmh_seiten.py (nis_nXX); Gradnetz 8W x=227, 7W x=413,
    # 6W x=598, 5W x=785; 57N y=257, 56N y=581, 55N y=898. Nur Luecken (abstand_atlas), Bezug HW Dover.
    'n_ireland_sw_scotland': dict(bezug=V.DOVER, atlas='NP218 (North of Ireland and SW Scotland)', land='Scotland, United Kingdom',
                                  regionen={'United Kingdom': 'Scotland, United Kingdom', 'Ireland': 'Ulster, Ireland'},
                                  lat=lambda y: float(np.polyval(np.polyfit([257, 581, 898], [57, 56, 55], 2), y)),
                                  lon=lambda x: float(np.polyval(np.polyfit([227, 413, 598, 785], [-8, -7, -6, -5], 1), x)),
                                  r=35, abstand_atlas=8.0,
                                  namen={(427, 303): 'Canna (20 km W), Scotland, United Kingdom Current',
                                         (197, 765): 'Tory Island (40 km NE), Ulster, Ireland Current'}),
    # West Coast of Scotland NP218 (Uebersicht): Seiten per vmh_seiten.py (wcs_nXX); Gradnetz 8W x=227, 7W x=413, 6W x=598,
    # 5W x=785; 59N y=313, 58N y=680, 57N y=1030. Etiketten wandern bis 40 px. Nur Luecken (abstand_atlas), Bezug HW Dover.
    'west_coast_scotland': dict(bezug=V.DOVER, atlas='NP218 (West Coast of Scotland)', land='Scotland, United Kingdom',
                                regionen={'United Kingdom': 'Scotland, United Kingdom'},
                                lat=lambda y: float(np.polyval(np.polyfit([313, 680, 1030], [59, 58, 57], 2), y)),
                                lon=lambda x: float(np.polyval(np.polyfit([227, 413, 598, 785], [-8, -7, -6, -5], 1), x)),
                                r=45, abstand_atlas=8.0,
                                weglassen=[(513, 1097)],            # Cairns of Coll: NP218-1-Satz 0,6 km daneben
                                namen={(545, 405): 'Butt of Lewis (27 km N), Scotland, United Kingdom Current',
                                       (573, 462): 'Butt of Lewis (12 km NE), Scotland, United Kingdom Current'}),
    # North Sea Southern Portion NP251 (Uebersicht): Seiten per vmh_seiten.py (nss_nXX); Gradnetz 0 x=180, 1E x=327, 2E x=473,
    # 3E x=618, 4E x=763; 55N y=133, 54N y=385, 53N y=630, 52N y=870, 51N y=1105. Nur Luecken, Bezug HW Dover.
    'north_sea_south': dict(bezug=V.DOVER, atlas='NP251 (North Sea Southern)', land='England, United Kingdom',
                            regionen={'United Kingdom': 'England, United Kingdom', 'Netherlands': 'Zuid-Holland, Netherlands'},
                            lat=lambda y: float(np.polyval(np.polyfit([133, 385, 630, 870, 1105], [55, 54, 53, 52, 51], 2), y)),
                            lon=lambda x: float(np.polyval(np.polyfit([180, 327, 473, 618, 763], [0, 1, 2, 3, 4], 1), x)),
                            r=40, abstand_atlas=8.0,
                            namen={(725, 493): 'Brown Ridge (60 km NE), North Sea Current',
                                   (573, 780): 'Lowestoft (64 km E), England, United Kingdom Current',
                                   (785, 100): 'Dogger Bank (143 km ENE), North Sea Current',
                                   (707, 265): 'Dogger Bank (108 km ESE), North Sea Current',
                                   (764, 397): 'Terschelling (106 km NW), Friesland, The Netherlands Current'}),
    # North Sea North-Western NP252 (Uebersicht): Seiten per vmh_seiten.py (nsw_nXX); Gradnetz 4W x=127 .. 3E x=868
    # (105,8 px/Grad); 59N y=266, 58N y=467, 57N y=663, 56N y=855, 55N y=1041. Nur Luecken, Bezug HW Dover.
    'north_sea_nw': dict(bezug=V.DOVER, atlas='NP252 (North Sea North-Western)', land='Scotland, United Kingdom',
                         regionen={'United Kingdom': 'Scotland, United Kingdom'},
                         lat=lambda y: float(np.polyval(np.polyfit([266, 467, 663, 855, 1041], [59, 58, 57, 56, 55], 2), y)),
                         lon=lambda x: -4 + (x - 127) / 105.8, r=45, abstand_atlas=8.0,
                         namen={(489, 855): 'Farne Islands (77 km ENE), England, United Kingdom Current', (689, 509): 'Forties Field (21 km ENE), North Sea Current', (619, 748): "Devil's Hole (22 km WSW), North Sea Current", (760, 754): "Devil's Hole (61 km E), North Sea Current", (803, 857): "Devil's Hole (110 km SE), North Sea Current", (644, 205): 'Fladen Ground (70 km NNE), North Sea Current', (809, 624): 'Forties Field (106 km ESE), North Sea Current', (412, 755): 'Marr Bank (18 km E), Scotland, United Kingdom Current', (532, 370): 'Fladen Ground (46 km WSW), North Sea Current', (786, 204): 'Fladen Ground (119 km NE), North Sea Current', (425, 624): 'Buchan Deep (33 km S), Scotland, United Kingdom Current', (491, 752): 'Marr Bank (64 km E), Scotland, United Kingdom Current', (589, 849): "Devil's Hole (75 km SSW), North Sea Current", (682, 374): 'Fladen Ground (51 km ESE), North Sea Current', (543, 632): 'Buchan Deep (78 km ESE), Scotland, United Kingdom Current', (675, 849): "Devil's Hole (64 km S), North Sea Current", (666, 629): 'Forties Field (62 km S), North Sea Current', (420, 301): 'Fair Isle (81 km SSE), Scotland, United Kingdom Current', (348, 373): 'Copinsay (65 km SE), Scotland, United Kingdom Current'}),
}


def _kopf(r):
    t = open(os.path.join(ROOT, r['file']), encoding='iso-8859-1').read()
    i = t.find('\n' + r['name'] + '\n')
    blk = t[max(0, t.rfind('# BEGIN HOT COMMENTS', 0, i)):i]
    return ' '.join(z for z in blk.split('\n') if z.startswith('# source')), None


def _m2(r):
    kopf = X.kopf_lesen(os.path.join(ROOT, r['file']))
    _z, w, _e, mer = X.satz_lesen(os.path.join(ROOT, r['file']), r['name'])
    return {k: (w[k][0], X.greenwich(w[k][1], kopf[1][k], mer)) for k in ('M2', 'S2') if k in w}


def _gleich(r, alt):
    """Neuer Satz (V.satz-Ergebnis, Greenwich-Phasen) gleich altem (M2/S2 auf 3 %% und 3 Grad)."""
    try:
        a, g = r['konst']['M2']
        b, h = alt['M2']
    except KeyError:
        return False
    d = abs((g - h + 180) % 360 - 180)
    d2 = abs((g - h) % 360 - 180)                                    # gegenlaeufig notiert
    return abs(a - b) <= 0.03 * max(a, b) and min(d, d2) <= 3


def lesen(name):
    out = []
    for z in open(os.path.join(ABL, name + '.txt'), encoding='utf-8'):
        z = z.split('#')[0].split()
        if len(z) == 4:
            n, s = z[3].split(',')
            out.append((int(z[0]), float(z[1]), float(z[2]), int(n) / 10, int(s) / 10))
    return out


def punkte(abl, r=28.0, min_h=10):
    """Zusammenfassen: Startpunkte aus der Stunde mit den meisten Ablesungen, dann iterativ Mittelpunkt."""
    rest = list(abl)
    cl = []
    while rest:
        # Saat: Ablesung mit den meisten Nachbarn
        saat = max(rest, key=lambda a: sum(1 for b in rest if math.hypot(a[1] - b[1], a[2] - b[2]) < r))
        cx, cy = saat[1], saat[2]
        for _ in range(3):
            je = {}
            for b in rest:
                d = math.hypot(b[1] - cx, b[2] - cy)
                if d < r and (b[0] not in je or d < je[b[0]][0]):
                    je[b[0]] = (d, b)
            cx = float(np.mean([b[1] for _, b in je.values()]))
            cy = float(np.mean([b[2] for _, b in je.values()]))
        for _, b in je.values():
            rest.remove(b)
        cl.append((cx, cy, {h: (b[3], b[4]) for h, (_, b) in je.items()}))
    # Verfeinern: je Stunde 1:1-Zuordnung Ablesung <-> Punktmitte (dichte Reihen ~15 px, East Solent 17.11.)
    from scipy.optimize import linear_sum_assignment
    mitten = [(c[0], c[1]) for c in cl]
    for _ in range(3):
        neu = [dict() for _m in mitten]
        for h in sorted({a[0] for a in abl}):
            ah = [a for a in abl if a[0] == h]
            D = np.array([[math.hypot(a[1] - mx, a[2] - my) for mx, my in mitten] for a in ah])
            D = np.where(D < r, D, 1e6)
            ri, ci = linear_sum_assignment(D)
            for i, j in zip(ri, ci):
                if D[i, j] < 1e6:
                    neu[j][h] = ah[i]
        mitten = [(float(np.mean([b[1] for b in n.values()])), float(np.mean([b[2] for b in n.values()]))) if n else m
                  for n, m in zip(neu, mitten)]
    cl = [(m[0], m[1], {h: (b[3], b[4]) for h, b in n.items()}) for m, n in zip(mitten, neu) if n]
    return [c for c in cl if len(c[2]) >= min_h], [c for c in cl if len(c[2]) < min_h]


def vorzeichen(werte, p_model):
    """werte {h: spring}; p_model {h: Modell entlang Achse}. Vorzeichen wechselt an den zwei tiefsten Minima."""
    hs = list(range(-6, 7))
    s = np.array([werte.get(h, np.nan) for h in hs], float)
    ok = ~np.isnan(s)
    s = np.interp(np.arange(13), np.arange(13)[ok], s[ok])
    # Minima: tiefste Stelle, dann tiefste Stelle >= 4 h entfernt
    m1 = int(np.argmin(s))
    kand = [i for i in range(13) if min(abs(i - m1), 12.42 - abs(i - m1)) >= 4]   # -6 und +6 sind dieselbe Tidenphase
    m2 = min(kand, key=lambda i: s[i])
    a, b = sorted((m1, m2))
    seg = np.array([1 if a < i <= b else -1 for i in range(13)], float)
    # Werte genau am Minimum: Vorzeichen egal (klein)
    pm = np.array([p_model[h] for h in hs])
    vz = 1.0 if np.sum(seg * s * pm) >= 0 else -1.0
    return {h: vz * seg[i] for i, h in enumerate(hs)}, s


def main(argv):
    name = argv[0]
    cfg = ATLAS[name]
    abl = lesen(name)
    gut, schlecht = punkte(abl, r=cfg.get('r', 28.0))
    print('%d Ablesungen -> %d Punkte (>= 10 h), %d verworfen' % (len(abl), len(gut), len(schlecht)))
    gut = [c for c in gut if all(math.hypot(c[0] - a, c[1] - b) > 15 for a, b in cfg.get('weglassen', []))]
    P = [(cfg['lat'](cy), cfg['lon'](cx), cx, cy, w) for cx, cy, w in gut]
    # Modell
    zl = F.zellen([(p[0], p[1]) for p in P])
    st = F.stroeme(zl, ks=['M2'])
    hafen, rel = cfg['bezug']
    kopf = X.kopf_lesen(os.path.join(ROOT, rel))
    _z, wb, _e, mer = X.satz_lesen(os.path.join(ROOT, rel), hafen)
    gS = X.greenwich(wb['M2'][1], kopf[1]['M2'], mer)
    om = kopf[1]['M2']
    R = [r for r in H.load_records() if r['current'] and r['lat'] is not None]
    LM = OL.Land([(p[0], p[1]) for p in P])
    import strom_namen_vorort as SV
    if '--landmarken' in argv:                                      # GeoNames-Landmarken um die neuen Punkte ergaenzen
        SV.landmarken([], [(p[0], p[1]) for p in P])
    Lgeo = __import__('json').load(open(os.path.join(ROOT, 'quellen/tidal_streams/strom_landmarken_geonames.json'), encoding='utf-8'))
    zeilen, bl = [], []
    vmh_alt_weit = []                                               # Uebersichtsatlas: alle Atlas-Saetze bis abstand_atlas
    if cfg.get('abstand_atlas'):
        for r_ in R:
            if min(H.km(r_, {'lat': p[0], 'lon': p[1]}) for p in P) < cfg['abstand_atlas'] and 'visitMyHarbour' in _kopf(r_)[0]:
                vmh_alt_weit.append((r_, None))
    vmh_alt = []                                                    # vorhandene visitMyHarbour-Saetze in der Naehe (Dubletten)
    for r_ in R:
        if min(H.km(r_, {'lat': p[0], 'lon': p[1]}) for p in P) < 6:
            q, _ax = _kopf(r_)
            if 'visitMyHarbour' in q:
                vmh_alt.append((r_, _m2(r_)))
    alt_atlas = set()                                               # schon geschriebene Saetze dieses Atlas
    try:
        alt_atlas = {r['name'] for r in csv.DictReader(open(os.path.join(ROOT, 'harmonics/help/vmh_%s_punkte.csv' % name), encoding='utf-8'))}
    except FileNotFoundError:
        pass
    namen = {r['name'] for r in H.load_records()}
    for idx, (la, lo, cx, cy, w) in enumerate(P):
        uv = st['M2'][idx]
        if uv is None:
            print('  kein Modell', la, lo)
            continue
        U, Vv = uv
        # Hauptachse der M2-Ellipse
        best = max(range(0, 180, 2), key=lambda t: abs(F.proj((U, Vv), t)))
        pm = {h: (cmath.exp(1j * math.radians(gS + om * h)) * (U * math.sin(math.radians(best)) + Vv * math.cos(math.radians(best)))).real
              for h in range(-6, 7)}
        fest = [f for (ax, ay), f in cfg.get('achse', {}).items() if math.hypot(cx - ax, cy - ay) < 15]
        if fest:                                                    # Achse von Hand (Fahrwasser), Flut = steigendes Wasser
            best = fest[0]
            pm = {h: math.cos(math.radians(om * (h + 3))) for h in range(-6, 7)}
        sg, sfill = vorzeichen({h: v[1] for h, v in w.items()}, pm)
        hand = [z for (ax, ay), z in cfg.get('vorzeichen', {}).items() if math.hypot(cx - ax, cy - ay) < 15]
        if hand:                                                    # Pfeilrichtungen je Stunde von Hand (Doppeltiden, Poole)
            sg = {h: float(z) for h, z in zip(range(-6, 7), hand[0])}
        werte = {}
        for i, h in enumerate(range(-6, 7)):
            if h in w:
                n, s = w[h]
            else:                                                   # Luecke: Nachbarn, Nipp im Verhaeltnis
                s = sfill[i]
                q = [w[k][0] / w[k][1] for k in w if w[k][1] > 0]
                n = s * (np.median(q) if q else 0.6)
            werte[h] = (n, s, best if sg[h] > 0 else (best + 180) % 360)
        an_land = LM.ist_land(la, lo)
        kue = LM.kueste_km(la, lo)
        nur = [a for a in argv if a.startswith('--nur=')]
        if nur and not any(math.hypot(cx - float(v.split(',')[0]), cy - float(v.split(',')[1])) < 15
                           for v in nur[0][6:].split(';')):
            continue                                                # nur ausgewaehlte Punkte neu rechnen
        # --nur: eigener frueherer Satz an derselben Stelle (< 0,2 km) wird ersetzt (Name bleibt, auch Olivers Umbenennung)
        selbst = [r for r in R if nur and r['name'] in alt_atlas and H.km(r, {'lat': la, 'lon': lo}) < 0.2]
        nah = min(((H.km(r, {'lat': la, 'lon': lo}), r['name']) for r in R if r not in selbst), default=(99, ''))
        # Name: naechste Landmarke (GeoNames, Banken/Rinnen/Kaps/Orte) + Abstand/Richtung
        lm = min(((V.A.km(la, lo, a, b), n_, _t) for n_, a, b, c, _t in Lgeo if abs(a - la) < 0.3 and abs(b - lo) < 0.5), default=None)
        if lm:
            d, ln, region = lm
            a_, b_ = next((a, b) for n_, a, b, c, _t in Lgeo if n_ == ln and abs(V.A.km(la, lo, a, b) - d) < 1e-6)
            az = math.degrees(math.atan2((lo - b_) * math.cos(math.radians(la)), la - a_)) % 360
            nm = ln if d < 1 else '%s (%d km %s)' % (ln, max(1, round(d)), RICHTUNG[int((az + 11.25) % 360 // 22.5)])
        else:
            nm = '%s %.3f %.3f' % (cfg['atlas'], la, lo)
        def mit_landesteil(v):
            """'X (..), United Kingdom Current' -> Landesteil der naechsten Landmarke mit Landesteil (Offshore-Banken)."""
            body = v[:-len(' Current')]
            k = body.rfind(')')
            j = body.find(', ', k + 1 if k >= 0 else 0)
            kopf, tail = body[:j], body[j + 2:]
            if ',' not in tail:
                kand = [(V.A.km(la, lo, a, b), t_) for n_, a, b, c, t_ in Lgeo
                        if abs(a - la) < 0.4 and abs(b - lo) < 0.6 and ',' in t_ and t_.endswith(', ' + tail)]
                tail = min(kand)[1] if kand else cfg.get('regionen', {}).get(tail, tail)
            return '%s, %s Current' % (kopf, tail)
        nm = mit_landesteil('%s, %s Current' % (re.sub(r'[^\x00-\xff]', '', nm), region if lm and region else cfg['land']))
        # bewaehrte Namensregeln (strom_namen_vorort): Landmarke vor Ort bis 2,5 km, sonst Fernregel mit OSM (Rinnen, Windparks)
        v = SV.vorschlag(la, lo, Lgeo)
        if v is None:
            f = SV.fern_vorschlag(la, lo, Lgeo, nm)
            v = f[0] if f else None
        if v:
            nm = mit_landesteil(v)
        hand = [n_ for (ax, ay), n_ in cfg.get('namen', {}).items() if math.hypot(cx - ax, cy - ay) < 15]
        if hand:                                                    # Name von Hand (Fallback "British Isles" u. ae.)
            nm = hand[0]
        if selbst:
            nm = selbst[0]['name']
        k = 2
        basis = nm
        while nm in namen and not selbst:
            nm = basis.replace(' Current', ' (%d) Current' % k)
            k += 1
        namen.add(nm)
        z = dict(name=nm, lat=round(la, 4), lon=round(lo, 4), x=round(cx), y=round(cy), stunden=len(w), achse=best,
                 spring_max=max(v[1] for v in werte.values()), land=int(an_land), kueste_km=round(kue, 2),
                 naechster_km=round(nah[0], 1), naechster=nah[1])
        zeilen.append(z)
        if an_land or nah[0] < 1.0:
            continue
        if cfg.get('abstand_atlas') and any(H.km(d[0], {'lat': la, 'lon': lo}) < cfg['abstand_atlas'] for d in vmh_alt_weit):
            z['dublette'] = 'Detailatlas < %.0f km' % cfg['abstand_atlas']
            continue
        if cfg.get('abstand_atlas') and nah[0] < 5.0:                # Uebersichtsatlas nur fuer Luecken (Barfleur -43 Grad gegen SHOM)
            z['dublette'] = 'Satz < 5 km'
            continue
        if any(a0 <= la <= a1 and b0 <= lo <= b1 for a0, a1, b0, b1 in cfg.get('sperre', [])):
            z['dublette'] = 'Detailatlas folgt'
            continue
        r, hs, hn = V.satz(werte, la, cfg['bezug'])
        # Dublette: gleiche gedruckte Rate aus einem ueberlappenden Atlas (Etikett anders gesetzt -> 2-5 km versetzt)
        dub = [d for d in vmh_alt if H.km(d[0], {'lat': la, 'lon': lo}) < 6 and _gleich(r, d[1])]
        if dub and not selbst:
            print('  Dublette zu', dub[0][0]['name'][:60])
            z['dublette'] = dub[0][0]['name']
            continue
        bl.append((nm, r, la, lo, hs, hn))
    aus = os.path.join(ROOT, 'harmonics/help/vmh_%s_punkte.csv' % name)
    if any(a.startswith('--nur=') for a in argv):
        aus = aus.replace('.csv', '_nur.csv')                       # Gesamtliste nicht ueberschreiben
    elif '--schreiben' not in argv:
        aus = aus.replace('.csv', '_probe.csv')                     # Probelauf: Liste der geschriebenen Saetze bleibt
    with open(aus, 'w', newline='', encoding='utf-8') as fh:
        wr = csv.DictWriter(fh, fieldnames=list(zeilen[0]) + ['dublette'], extrasaction='ignore')
        wr.writeheader()
        wr.writerows(zeilen)
    print('->', os.path.relpath(aus, ROOT), '|', len(bl), 'schreibbar')
    for z in zeilen:
        print('%-62s %3d h  %5.1f kn  %s%s  naechster %.1f km %s' % (z['name'][:62], z['stunden'], z['spring_max'],
              'LAND ' if z['land'] else '', 'kueste %.1f' % z['kueste_km'], z['naechster_km'], z['naechster'][:40]))
    return bl, cfg


if __name__ == '__main__':
    bl, cfg = main(sys.argv[1:])
    if '--schreiben' in sys.argv and bl:
        import datetime as dt
        from sicher_schreiben import schreiben
        hafen = cfg['bezug'][0].split(',')[0]
        T = open(A.ZIEL, encoding='iso-8859-1').read().rstrip('\n')
        neu = [A.block(nm, r, la, lo,
                       'Admiralty %s tidal stream atlas via visitmyharbour.com (members, hourly HW %s -6..+6, every printed rate, read by hand)' % (cfg['atlas'], hafen),
                       'hours from HW %s, neap/spring interpolated by range (spring %.2f m, neap %.2f m); direction axis FES2014, sign from slack pattern' % (hafen, hs, hn),
                       'UKHO %s via visitMyHarbour' % cfg['atlas'].split()[0], '%s-VISITMYHARBOUR' % cfg['atlas'].split()[0])
               for nm, r, la, lo, hs, hn in bl]
        zl = T.split('\n')
        anhang = []
        for (nm, *_r), b in zip(bl, neu):                           # vorhandenen Satz gleichen Namens ersetzen
            bz = b.split('\n')
            if nm in zl:
                i = zl.index(nm)
                k = bz.index(nm)
                st = max(j for j in range(i - k - 5, i) if zl[j].startswith('# Harmonic constants derived'))   # Kopf evtl. umbrochen
                zl[st:i + len(bz) - k] = bz
            else:
                anhang.append(b)
        T = '\n'.join(zl)
        schreiben(A.ZIEL, T + ('\n' + '\n'.join(anhang) if anhang else '') + '\n')
        with open(os.path.join(ROOT, PRUEFLISTE), 'a', encoding='utf-8') as fh:
            for nm, *_r in bl:
                if not any(b.split('\n').count(nm) for b in anhang):
                    continue                                        # ersetzt: steht schon in der Pruefliste
                fh.write('harmonics_utide_current_tables.txt,"%s"\n' % nm)
        print(len(neu), 'Saetze ->', os.path.relpath(A.ZIEL, ROOT))


def entfernen(namen):
    """Atlas-Saetze wieder herausnehmen (Dubletten zwischen ueberlappenden Atlanten); Block = Kopf bis 175 Konstituenten."""
    from sicher_schreiben import schreiben
    z = open(A.ZIEL, encoding='iso-8859-1').read().split('\n')
    for nm in namen:
        i = z.index(nm)
        st = max(j for j in range(i - 30, i) if z[j].startswith('# Harmonic constants derived'))
        en = i + 3 + len(A.CONSTITUENTS_175)
        assert z[i + 1].startswith('+00:00') and z[i + 2].endswith('knots'), nm
        assert en == len(z) or not z[en].strip() or z[en].startswith('#') or z[en - 1].split()[0] in ('x',) or True
        del z[st:en]
    schreiben(A.ZIEL, '\n'.join(z).rstrip('\n') + '\n')
    p = os.path.join(ROOT, PRUEFLISTE)
    t = [l for l in open(p, encoding='utf-8') if not any('"%s"' % nm in l for nm in namen)]
    open(p, 'w', encoding='utf-8').writelines(t)
