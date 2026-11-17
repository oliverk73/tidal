#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Stromsaetze aus den Admiralty-Atlanten bei visitMyHarbour (Mitgliedskacheln, Oliver 17.11.2026).

Bilder: quellen/tidal_streams/visitmyharbour/vmh_<atlas>_<id>.png (Zoom 6, 13 Stundenbilder HW Dover -6..+6 untereinander).
Abgelesen von Hand: nur Punkte mit gedruckten Knoten "nipp,spring" (Zehntelknoten), Richtung aus dem Pfeil am Punkt.
Umrechnung wie hafenatlas_stroeme.mm_satz: Nipp/Spring nach dem Hub am Bezugspegel interpoliert, UTide-Fit.

  venv/bin/python py/vmh_atlas.py [--schreiben]
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cmems_stroemung_nachholen as C                               # noqa: E402
import hafenatlas_stroeme as A                                      # noqa: E402
import health_check as H                                            # noqa: E402
import xtide_modell as X                                            # noqa: E402

ROOT = A.ROOT
DOVER = ('Dover, England, United Kingdom', 'harmonics/ticon/harmonics_ticon4_worldwide.txt')
DEVONPORT = ('Devonport, England, United Kingdom', 'harmonics/utide/harmonics_utide_observations.txt')

def _w(fl, eb, reihe):
    """13 (vz, nipp, spring) HW -6..+6 -> {h: (nipp, spring, Richtung)}; vz +1 Flut fl, -1 Ebbe eb, 0 Stillwasser."""
    return {h: (n / 10, sp / 10, fl if vz >= 0 else eb) for h, (vz, n, sp) in zip(range(-6, 7), reihe)}


# NP209 Orkney and Shetland, Pentland-Firth-Blatt (VMH 0000209-1). Bildachsen Zoom 6: 3 deg 20' W bei x=232,
# 27 px je Laengenminute; 58 deg 45' N bei y=388, 51 px je Breitenminute.
# (Name, lat, lon, {Stunde HW Dover: (nipp, spring, Richtung)})
PF = [
    ('Pentland Firth West Entrance (Dunnet Head 6 km N), Scotland, United Kingdom Current', 58.7265, -3.3750,
     dict(zip(range(-6, 7), [(0.7, 1.7, 280), (0.3, 0.7, 165), (0.8, 1.9, 110), (1.2, 3.1, 105), (1.3, 3.3, 100),
                             (1.0, 2.6, 105), (0.5, 1.4, 100), (0.2, 0.5, 15), (0.7, 1.7, 300), (1.1, 2.7, 295),
                             (1.2, 3.1, 290), (1.3, 3.2, 280), (0.9, 2.3, 280)]))),
    ('Pentland Skerries (10 km ESE), Scotland, United Kingdom Current', 58.6450, -2.7620,
     dict(zip(range(-6, 7), [(0.4, 1.0, 45), (0.5, 1.1, 60), (0.6, 1.5, 105), (0.6, 1.4, 115), (0.3, 0.8, 135),
                             (0.4, 0.8, 200), (0.5, 1.2, 225), (0.6, 1.4, 230), (0.6, 1.4, 255), (0.5, 1.2, 305),
                             (0.4, 1.0, 330), (0.5, 1.1, 0), (0.4, 1.0, 30)]))),
    # NP209 Orkney-Blatt (0000209-2), 59 N bei y=378, 11,87 px/'; 3 W bei x=886, 6,26 px/'. HW Dover -5 ohne Zahl
    # (Kentern Ebbe->Flut, Pfeile schon SE) -> zwischen -6 und -4 interpoliert.
    ('Westray Firth, Scotland, United Kingdom Current', 59.2330, -3.0480,
     _w(130, 310, [(-1, 4, 8), (1, 9, 16), (1, 14, 25), (1, 16, 29), (1, 16, 28), (1, 9, 17), (1, 4, 8), (-1, 5, 9),
                   (-1, 11, 20), (-1, 16, 28), (-1, 17, 31), (-1, 12, 22), (-1, 7, 13)])),
    # NP209 Shetland-Blatt (0000209-0, Zoom 7), Nebenkarte Yell Sound (Kasten 60.446-60.571 N, 1.200-1.425 W), Hauptfahrwasser
    # (Zufahrt Sullom Voe). Nord = Ebbe hinaus, Sued = Flut.
    ('Yell Sound, Scotland, United Kingdom Current', 60.5400, -1.2750,
     _w(160, 340, [(-1, 7, 15), (1, 5, 10), (1, 6, 13), (1, 7, 14), (1, 6, 11), (1, 2, 4), (1, 1, 2), (-1, 3, 6),
                   (-1, 6, 13), (-1, 10, 21), (-1, 10, 21), (-1, 13, 26), (-1, 10, 21)])),
    # NP218 N of Ireland/SW Scotland (0000218-1, Zoom 7), Nebenkarte Firth of Lorn: Scarba (56.18 N, 5.70 W) bei (335,945),
    # Luing (56.23, -5.64) bei (390,860) -> 1700 px/Grad Breite, 917 px/Grad Laenge. Punkt Sound of Luing (Fladda).
    ('Sound of Luing (900 m NE of Poll na h-Ealaidh), Scotland, United Kingdom Current', 56.1980, -5.6640,
     _w(190, 10, [(0, 0, 0), (1, 6, 16), (1, 9, 23), (1, 6, 21), (1, 6, 16), (1, 3, 8), (-1, 4, 9), (-1, 6, 15),
                  (-1, 8, 19), (-1, 9, 21), (-1, 7, 18), (-1, 5, 12), (-1, 2, 6)])),
]


PORTSMOUTH = ('Portsmouth, England, United Kingdom', 'harmonics/utide/harmonics_utide_observations.txt')


# NP337 East Solent (VMH 0000337-0), HW Portsmouth -6..+6, abgelesen 17.11.2026. Bild: 1 deg W bei x=645, 19,4 px je
# Laengenminute; 50 deg 50' N bei y=148, 30,5 px je Breitenminute. Monty-Saetze (Gurnard, Nab ...) nicht doppelt.
ES = [
    ('Netley / Hythe (Southampton Water), England, United Kingdom Current', 50.8730, -1.3700, _w(315, 135, [
        (1, 4, 6), (1, 3, 5), (1, 1, 1), (1, 2, 4), (1, 6, 10), (1, 3, 6), (0, 0, 0), (-1, 1, 2), (-1, 2, 3), (-1, 6, 9),
        (-1, 11, 17), (-1, 2, 4), (1, 4, 6)])),
    ('Calshot (4 km S, Solent), England, United Kingdom Current', 50.7830, -1.3090, _w(50, 230, [
        (1, 10, 20), (1, 11, 21), (1, 10, 20), (1, 8, 16), (1, 5, 10), (-1, 1, 2), (-1, 10, 21), (-1, 13, 26), (-1, 11, 23),
        (-1, 9, 18), (-1, 5, 10), (1, 2, 4), (1, 9, 17)])),
    ("No Man's Land Fort (2 km SE, Spithead), England, United Kingdom Current", 50.7284, -1.0690, _w(110, 290, [
        (1, 3, 6), (1, 6, 12), (1, 7, 13), (1, 3, 5), (-1, 2, 4), (-1, 5, 10), (-1, 8, 15), (-1, 9, 17), (-1, 5, 10),
        (1, 1, 2), (1, 5, 9), (1, 3, 7), (1, 2, 4)])),
    ('Langstone Harbour (inside entrance), England, United Kingdom Current', 50.8050, -1.0215, _w(20, 200, [
        (1, 2, 4), (1, 3, 5), (1, 3, 6), (1, 5, 10), (1, 7, 13), (1, 4, 7), (-1, 2, 4), (-1, 2, 4), (-1, 3, 5),
        (-1, 8, 16), (-1, 7, 14), (-1, 1, 2), (1, 2, 4)])),
    ('Chichester Harbour Entrance (Itchenor Channel), England, United Kingdom Current', 50.8000, -0.9055, _w(45, 225, [
        (1, 2, 4), (1, 2, 4), (0, 0, 0), (1, 3, 7), (1, 6, 12), (1, 8, 16), (1, 3, 7), (-1, 4, 7), (-1, 2, 5),
        (-1, 8, 17), (-1, 8, 15), (-1, 5, 10), (1, 1, 2)])),
]

SHEERNESS = ('Sheerness, England, United Kingdom', 'harmonics/ticon/harmonics_ticon4_worldwide.txt')
# NP249 Thames Estuary (VMH 0000249-0, Zoom 7, Hochformat; Bild 90 Grad gedreht: Nord links). HW Sheerness -6..+6.
# Breite = 51.945 - (x-255)*0.000841 (Margate/Harwich), Laenge = 1 + (668-y)/744 (Gradnetz 12,4 px/').
# Flut nach W/SW in die Themse, Ebbe nach E/NE.
TH = [
    ('Knock John Channel, England, United Kingdom Current', 51.5200, 1.1520, _w(235, 55, [
        (1, 2, 3), (1, 8, 12), (1, 13, 19), (1, 12, 18), (1, 12, 18), (1, 7, 10), (0, 0, 0), (-1, 8, 13), (-1, 11, 17),
        (-1, 11, 17), (-1, 8, 12), (-1, 5, 8), (0, 0, 0)])),
    ('Oaze Deep, England, United Kingdom Current', 51.4780, 0.9370, _w(255, 75, [
        (1, 2, 3), (1, 7, 10), (1, 11, 17), (1, 11, 17), (1, 10, 16), (1, 7, 10), (0, 0, 0), (-1, 7, 13), (-1, 9, 14),
        (-1, 16, 24), (-1, 12, 19), (-1, 7, 10), (0, 0, 0)])),
    ('West Barrow (3 km NW, East Swin), England, United Kingdom Current', 51.6090, 1.0910, _w(225, 45, [
        (1, 4, 6), (1, 10, 16), (1, 12, 19), (1, 11, 18), (1, 9, 14), (1, 5, 8), (-1, 3, 4), (-1, 10, 15), (-1, 13, 20),
        (-1, 11, 18), (-1, 9, 14), (-1, 5, 6), (0, 0, 0)])),
    ('Reculver (7 km N), England, United Kingdom Current', 51.4400, 1.1790, _w(255, 75, [
        (1, 3, 5), (1, 8, 12), (1, 9, 14), (1, 9, 14), (1, 9, 14), (1, 7, 10), (0, 0, 0), (-1, 7, 13), (-1, 12, 18),
        (-1, 10, 15), (-1, 7, 11), (-1, 4, 6), (0, 0, 0)])),
]

# NP258 Bristol Channel (0000258-0, Zoom 6), HW Dover. Laenge = -4 + (x-530)/532, Breite = 51 + (752-y)/828
# (geprueft an Cardiff und Avonmouth). Flut ENE den Kanal hinauf.
BC = [
    ('Charlcombe Bay (1 km NW, Bristol Deep), England, United Kingdom Current', 51.4764, -2.8290, _w(65, 245, [
        (1, 23, 43), (1, 16, 29), (1, 9, 16), (-1, 6, 11), (-1, 16, 30), (-1, 20, 38), (-1, 20, 37), (-1, 20, 37),
        (-1, 17, 32), (-1, 7, 13), (1, 18, 34), (1, 31, 58), (1, 26, 48)])),
    ('Steep Holm (1 km NW), England, United Kingdom Current', 51.3470, -3.1260, _w(65, 245, [
        (1, 19, 36), (1, 6, 12), (1, 2, 5), (-1, 14, 28), (-1, 19, 36), (-1, 17, 33), (-1, 14, 28), (-1, 12, 23),
        (-1, 4, 7), (1, 9, 18), (1, 15, 29), (1, 20, 39), (1, 19, 36)])),
]


def satz(werte, la, bezug=None):
    hafen, rel = bezug or DOVER
    hd = os.path.join(ROOT, rel)
    _z0, w, e, _m = X.satz_lesen(hd, hafen)
    f = 0.3048 if e.startswith('f') else 1.0
    hs, hn = 2 * (w['M2'][0] + w['S2'][0]) * f, 2 * (w['M2'][0] - w['S2'][0]) * f
    sp = {h: (s * math.sin(math.radians(r)), s * math.cos(math.radians(r))) for h, (_n, s, r) in werte.items()}
    ni = {h: (n * math.sin(math.radians(r)), n * math.cos(math.radians(r))) for h, (n, _s, r) in werte.items()}
    return C.analyse(A.reihe_sn(sp, ni, hafen, hd, hs, hn), la, C.KONST), hs, hn


def main(argv):
    R = [r for r in H.load_records() if r['current'] and r['lat'] is not None]
    vorhanden = {r['name'] for r in R}
    bl = []
    for name, la, lo, werte, bezug, atlas in [p + (DOVER, 'NP209 (Orkney and Shetland)') for p in PF] + \
            [p + (PORTSMOUTH, 'NP337 (Solent)') for p in ES] + [p + (SHEERNESS, 'NP249 (Thames Estuary)') for p in TH] + \
            [p + (DOVER, 'NP258 (Bristol Channel)') for p in BC]:
        if name in vorhanden:
            print('vorhanden:', name)
            continue
        import osm_land as OL                                     # 17.11.: Clevedon lag an Land (Atlas-Beschriftung neben dem Fahrwasser)
        LM = OL.Land([(la, lo)])
        if LM.ist_land(la, lo):
            print('AN LAND, uebersprungen (Position ins Fahrwasser setzen):', name, la, lo)
            continue
        r, hs, hn = satz(werte, la, bezug)
        nah = sorted((A.km(la, lo, x['lat'], x['lon']), x['name']) for x in R)[:3]
        print('%-80s Achse %3.0f  M2 %.2f kn  S2 %.2f  max %.1f kn | naechste: %s' % (
            name, r['achse'], r['m2'], r['s2'], r['smax'], '; '.join('%s %.0f km' % (n[:40], d) for d, n in nah)))
        bl.append(A.block(name, r, la, lo,
                          'Admiralty %s tidal stream atlas via visitmyharbour.com (members, hourly HW %s -6..+6, read by hand)' % (atlas, bezug[0].split(',')[0]),
                          'hours from HW %s, neap/spring rates interpolated by range (spring %.2f m, neap %.2f m); only points with printed rates' % (bezug[0].split(',')[0], hs, hn),
                          'UKHO %s via visitMyHarbour' % atlas.split()[0], '%s-VISITMYHARBOUR' % atlas.split()[0]))
    if '--schreiben' in argv and bl:
        from sicher_schreiben import schreiben
        T = open(A.ZIEL, encoding='iso-8859-1').read().rstrip('\n')
        schreiben(A.ZIEL, T + '\n' + '\n'.join(bl) + '\n')
        import datetime as dt
        with open(os.path.join(ROOT, 'harmonics/help/neu_pruefen_%s.csv' % dt.date.today().strftime('%Y%m%d')), 'a', encoding='utf-8') as fh:
            for b in bl:
                fh.write('harmonics_utide_current_tables.txt,"%s"\n' % next(z for z in b.split('\n') if z.endswith(' Current')))
        print('->', os.path.relpath(A.ZIEL, ROOT))


if __name__ == '__main__':
    main(sys.argv[1:])
