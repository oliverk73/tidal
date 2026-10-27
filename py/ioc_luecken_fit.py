#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""UTide-Fits fuer IOC-Pegel ohne eigenen Satz im Bestand (Lueckenliste 17.10.2026).

Oliver 17.10.2026: "Gibt's noch ungenutzte Datenquellen, besonders mit signifikanter Tide?" Abgleich aller
IOC-Pegel mit dem Bestand (Kennung in allen Dateien und Namensteile geprueft), Reihen mit
py/download_ioc_monate.py (Stunde = naechste Stunde). Pruefung wie py/ioc_russland_fit.py: Versatz je
Monat gegen FES (|dt| <= 30 min, r > 0.3, kein Datumssprung), Pegelnull-Spruenge ausgeglichen,
Eigenversatz 0. Position: IOC-Koordinate, liegt sie an Land, das naechste Wasser bis 1 km (OSM).

Usage: venv/bin/python py/ioc_luecken_fit.py [code ...] [--schreiben]  -> harmonics_utide_observations.txt
"""
import datetime as dt
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ioc_russland_fit as R                                       # noqa: E402

ROOT = R.ROOT
# code, Name, Region, IOC-Breite, IOC-Laenge. Verworfen: Malpelo (r ~0, keine Gezeit in der Reihe),
# Grajagan (+38..+76 min ohne Nachbarbeleg), Payangan (2 Monate), Kerachut (R2 0.88, Drucksensor)
PEGEL = [
    ('riba', 'São José de Ribamar, Maranhão, Brazil', 'Maranhão', -2.56, -44.05),
    # verworfen 17.10.: ('malp2', 'Isla de Malpelo, Colombia', 'Valle del Cauca', 4.00, -81.60),
    ('lpbc', 'Henslung Cove (Langara Island), British Columbia, Canada', 'British Columbia', 54.20, -133.10),
    ('mpcw', 'Westhinder (Meetpaal), Belgium', 'West-Vlaanderen', 51.39, 2.44),
    ('mpaw', 'A2 (Meetpaal), Belgium', 'West-Vlaanderen', 51.36, 3.12),
    ('mpww', 'Wandelaar (Meetpaal), Belgium', 'West-Vlaanderen', 51.39, 3.05),
    ('mpsw', 'Scheur Wielingen (Meetpaal), Belgium', 'West-Vlaanderen', 51.42, 3.30),
    ('patu', 'Puerto Atún (Manta), Ecuador', 'Manabí', -0.93, -80.67),
    ('sipa', 'Sipacate, Guatemala', 'Escuintla', 13.92, -91.08),
    ('taza', 'Puerto de Tazacorte (La Palma), Islas Canarias, Spain', 'Canarias', 28.64, -17.94),
    ('gara', 'Garachico (Tenerife), Islas Canarias, Spain', 'Canarias', 28.37, -16.75),
    ('KUTBI', 'Kedonganan (Jimbaran), Bali, Indonesia', 'Bali', -8.76, 115.17),
    # verworfen 17.10.: ('GRJJI', 'Grajagan, Jawa Timur, Indonesia', 'Jawa Timur', -8.60, 114.23),
    # verworfen 17.10.: ('PAYJI', 'Pantai Payangan (Teluk Love), Jawa Timur, Indonesia', 'Jawa Timur', -8.44, 113.58),
    ('BETSI', 'Beo (Pulau Karakelang), Sulawesi Utara, Indonesia', 'Sulawesi Utara', 4.23, 126.79),
    # verworfen 17.10.: ('ms002', 'Kerachut (Penang), Malaysia', 'Pulau Pinang', 5.45, 100.18),
    # 27.10.: ersetzt den ATT-Satz (NP203 2002) am selben Ort, der 2016-2026 gleichmaessig ~13 min zu frueh liegt;
    # Position = Olivers gepruefte ATT-Position (IOC 14.8167/120.2833, 0.4 km)
    ('subi', 'Olongapo (Subic Bay), Zambales, Philippines', 'Zambales', 14.8169, 120.2797),
]


def wasser(la, lo, L):
    if not L.ist_land(la, lo):
        return la, lo, 0
    best = None
    for i in range(-20, 21):
        for j in range(-20, 21):
            p = (la + i * 0.0005, lo + j * 0.0005 / math.cos(math.radians(la)))
            d = math.hypot(i, j) * 55
            if (best is None or d < best[2]) and not L.ist_land(*p) and L.kueste_km(*p) > 0.05:
                best = (p[0], p[1], d)
    return best if best else (la, lo, -1)


def main(argv):
    import osm_land
    from timezonefinder import TimezoneFinder
    tf = TimezoneFinder()
    wahl = [a for a in argv if not a.startswith('--')]
    liste = [p for p in PEGEL if not wahl or p[0] in wahl]
    L = osm_land.Land([(p[3], p[4]) for p in liste])
    eintraege = []
    for code, name, region, la, lo in liste:
        nla, nlo, d = wasser(la, lo, L)
        tz = tf.timezone_at(lat=la, lng=lo) or 'UTC'
        posnote = ('IOC %.4f/%.4f' % (la, lo) + ('' if d == 0 else (' an Land, %.0f m ins Wasser' % d if d > 0 else ' an Land, kein Wasser bis 1 km'))
                   + '; bitte pruefen')
        eintraege.append((code, 'ioc_%s_monate.csv' % code, name, nla, nlo, posnote))
        R.REGION[code] = region
        R.TZ[code] = tz
    # Sao Jose de Ribamar: gegen FES jeden Monat -50 min (r 0.9), gegen die DHN-Nachbarn Itaqui/Ponta da Madeira
    # stabil -15..-23 min -> Uhr in Ordnung, FES in der flachen Bucht daneben
    R.SOLL['riba'] = -50
    R.PEGEL[:] = eintraege
    R.main([e[0] for e in eintraege] + (['--schreiben'] if '--schreiben' in argv else []))


if __name__ == '__main__':
    main(sys.argv[1:])
