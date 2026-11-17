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
]


def satz(werte, la):
    hafen, rel = DOVER
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
    for name, la, lo, werte in PF:
        if name in vorhanden:
            print('vorhanden:', name)
            continue
        r, hs, hn = satz(werte, la)
        nah = sorted((A.km(la, lo, x['lat'], x['lon']), x['name']) for x in R)[:3]
        print('%-80s Achse %3.0f  M2 %.2f kn  S2 %.2f  max %.1f kn | naechste: %s' % (
            name, r['achse'], r['m2'], r['s2'], r['smax'], '; '.join('%s %.0f km' % (n[:40], d) for d, n in nah)))
        bl.append(A.block(name, r, la, lo,
                          'Admiralty NP209 (Orkney and Shetland) tidal stream atlas via visitmyharbour.com (members, hourly HW Dover -6..+6, read by hand)',
                          'hours from HW Dover, neap/spring rates interpolated by range (spring %.2f m, neap %.2f m); only points with printed rates' % (hs, hn),
                          'UKHO NP209 via visitMyHarbour', 'NP209-VISITMYHARBOUR'))
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
