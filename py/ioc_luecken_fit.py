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
    # 02.11.2026: Madagaskar, IOC seit 01/2026 (Radar); Tolagnaro bisher nur ATT-Uebertragung, Toliara SHOM-Vorhersagefit
    # verworfen 02.11.: ('mfdf', 'Tolagnaro (Fort-Dauphin), Madagascar', 'Anosy', -25.0279, 46.9967),  Radar, Wellenrauschen rms 0,27 m, Jan/Feb Uhr +3 h; bestaetigt nur FES-Hub
    # nicht geschrieben 02.11.: ('mtul', 'Toliara, Madagascar', 'Atsimo-Andrefana', -23.3764, 43.6647),  bestaetigt den SHOM-Satz (M2 0,80 gegen 0,82 m), Eigenversatz +7 min
    # 02.11.2026: Komoren; IOC-Kennung war per Falschzuordnung an Comox (BC) vergeben -> Pegel galt als genutzt
    ('como', 'Moroni (Ngazidja / Grande Comore), Comoros', 'Grande Comore', -11.7035, 43.2481),
    # 02.11.2026: IOC-Lueckensuche nach Kennungsbereinigung (Springhub >= 1 m, kein guter Satz < 5 km)
    ('orma', 'Ormara, Balochistan, Pakistan', 'Balochistan', 25.2037, 64.6764),
    ('diba', 'Dibba Al-Baya, Musandam, Oman', 'Musandam', 25.649, 56.269),
    ('ashk', 'Al Ashkharah, Ash Sharqiyah South, Oman', 'Ash Sharqiyah South', 21.85, 59.57),
    ('losu', 'Marina Los Sueños (Herradura), Puntarenas, Costa Rica', 'Puntarenas', 9.6502, -84.6665),
    ('papa', 'Marina Papagayo, Guanacaste, Costa Rica', 'Guanacaste', 10.6420, -85.656),
    ('psjs', 'San Juan del Sur, Rivas, Nicaragua', 'Rivas', 11.251, -85.875),
    ('psdn', 'Puerto Sandino, León, Nicaragua', 'León', 12.2011, -86.7644),
    ('asro', 'Aserradores, Chinandega, Nicaragua', 'Chinandega', 12.626, -87.342),
    # 9.11.2026 nachgeprueft (Reihen bis 10/2026): psjs nur 1 guter Monat (sonst +60 min, r 0.86), asro 2 Monate -> weiter
    # verworfen; pots 5 gute Monate 2020-2025 (3265 h, Eigenversatz -1 min), M2 1,25@250 wie La Union 1,16 / Amapala 1,19,
    # FES-Satz am Ort 1,00 -> eingetragen, FES archiviert.
    ('pots', 'Puerto Potosí (Golfo de Fonseca), Chinandega, Nicaragua', 'Chinandega', 13.0104, -87.504),
    ('hain', 'Haing Gyi Kyun (Haigyi Island), Ayeyarwady, Myanmar', 'Ayeyarwady', 16.0004, 94.3176),
    ('iclr', 'Isla Clarión (Revillagigedo), Colima, Mexico', 'Colima', 18.5338, -114.7227),
    ('ms006', 'Lahad Datu, Sabah, Malaysia', 'Sabah', 5.0756, 119.0775),
    ('stan', 'Stanley (Port Stanley), Falkland Islands', '', -51.75, -57.9333),
    ('sanp', 'Isla San Pedro (Golfo de Penas), Aysén, Chile', 'Aysén', -47.7038, -74.8661),
    ('inha', 'Ponta da Barra (Inhambane), Mozambique', 'Inhambane', -23.9167, 35.5),
    ('TBSSI', 'Talengen (Sangihe), Sulawesi Utara, Indonesia', 'Sulawesi Utara', 3.5904, 125.5666),
    ('TASJI', 'Pantai Baron (Gunungkidul), Yogyakarta, Indonesia', 'Yogyakarta', -8.1310, 110.5485),
    ('GESJI', 'Pantai Gesing (Gunungkidul), Yogyakarta, Indonesia', 'Yogyakarta', -8.1077, 110.4684),
    ('MRTMI', 'Bere-Bere (Pulau Morotai), Maluku Utara, Indonesia', 'Maluku Utara', 2.3889, 128.6669),
    ('LAMSI', 'Lamteng (Pulau Nasi), Aceh, Indonesia', 'Aceh', 5.6404, 95.1592),
    ('CIDJI', 'Pantai Jayanti (Cianjur), Jawa Barat, Indonesia', 'Jawa Barat', -7.4992, 107.3869),
    ('KMMSI', 'Kema, Sulawesi Utara, Indonesia', 'Sulawesi Utara', 1.3580, 125.0768),
    ('kame', 'Kamesang (Ngatpang), Palau', 'Ngatpang', 7.4960, 134.4853),
    ('pele', 'Peleliu, Palau', 'Peleliu', 7.0490, 134.2665),
    ('imek', 'Imekang (Ngiwal), Palau', 'Ngiwal', 7.5372, 134.6250),
    # Mittelmeer (8.11.2026, Oliver: Windstau macht Mikrotide-Orte relevant; Inventar
    # harmonics/help/pegel_mittelmeer_20261108.csv, kein Satz <= 3 km). Weggelassen: asty (= Astypalaia 3,2 km),
    # prev1/sole2 (Zweitsensor). Reihen 11/2024-10/2026. Eingetragen 8.11. nur RCCL SMLE kala prev peir matr
    # (>= 6 Monate, Eigenversatz <= 5 min, FES < 10 %); verworfen: sole (= Solenzara 3,4 km, 0,8 %), marn1 (K1 146 Grad
    # gegen Matruh, FES 16 %), PSCA (Rest 27 cm), kata (K1 unplausibel), delo/myko (Eigenversatz -18/+8), usti/syro/amor
    # (3-4 Monate), lekm/vasi/kopi/karp (erst ab 10/2026), sira/trem/BRLT/MNPL/kiss/gokc/batr1 (keine gueltigen Monate),
    # sobr/mrms (Name schon im Bestand).
    ('sole', 'Solenzara (Corse), France', 'Corse', 41.836, 9.374),
    ('PSCA', 'Scauri (Pantelleria), Italy', 'Sicilia', 36.769, 11.964),
    ('usti', 'Ustica, Italy', 'Sicilia', 38.705, 13.176),
    ('sira', 'Siracusa, Italy', 'Sicilia', 37.112, 15.253),
    ('trem', 'Messina (Tremestieri), Italy', 'Sicilia', 38.132, 15.523),
    ('BRLT', 'Barletta, Italy', 'Puglia', 41.333, 16.290),
    ('RCCL', 'Roccella Ionica, Italy', 'Calabria', 38.327, 16.432),
    ('MNPL', 'Monopoli, Italy', 'Puglia', 40.956, 17.308),
    ('sobr', 'Sobra (Mljet), Croatia', 'Dubrovacko-neretvanska', 42.793, 17.620),
    ('SMLE', 'Santa Maria di Leuca, Italy', 'Puglia', 39.795, 18.359),
    ('lekm', 'Lefkimmi (Kerkyra), Greece', 'Ionian Islands', 39.415, 20.099),
    ('vasi', 'Vasiliki (Lefkada), Greece', 'Ionian Islands', 38.628, 20.606),
    ('prev', 'Preveza, Greece', 'Epirus', 38.949, 20.729),
    ('kata', 'Katakolo, Greece', 'Western Greece', 37.640, 21.319),
    ('kala', 'Kalamata, Greece', 'Peloponnese', 37.022, 22.110),
    ('peir', 'Peiraias (Piraeus), Greece', 'Attica', 37.935, 23.621),
    ('kiss', 'Kissamos (Kriti), Greece', 'Crete', 35.514, 23.637),
    ('kopi', 'Kokkinos Pyrgos (Kriti), Greece', 'Crete', 35.082, 24.737),
    ('syro', 'Ermoupoli (Syros), Greece', 'South Aegean', 37.438, 24.941),
    ('delo', 'Delos, Greece', 'South Aegean', 37.399, 25.265),
    ('myko', 'Tourlos (Mykonos), Greece', 'South Aegean', 37.465, 25.322),
    ('amor', 'Katapola (Amorgos), Greece', 'South Aegean', 36.831, 25.865),
    ('karp', 'Pigadia (Karpathos), Greece', 'South Aegean', 35.510, 27.210),
    ('gokc', 'Kuzu Limani (Gökçeada), Turkey', 'Canakkale', 40.231, 25.894),
    ('mrms', 'Marmaris, Turkey', 'Mugla', 36.838, 28.385),
    ('matr', 'Marsa Matruh, Egypt', 'Matrouh', 31.370, 27.204),
    ('marn1', 'Marina El Alamein, Egypt', 'Matrouh', 30.844, 28.977),
    ('batr1', 'Batroun, Lebanon', 'North Lebanon', 34.252, 35.656),
]
MITTELMEER = ('sole', 'PSCA', 'usti', 'sira', 'trem', 'BRLT', 'RCCL', 'MNPL', 'sobr', 'SMLE', 'lekm', 'vasi', 'prev',
              'kata', 'kala', 'peir', 'kiss', 'kopi', 'syro', 'delo', 'myko', 'amor', 'karp', 'gokc', 'mrms', 'matr',
              'marn1', 'batr1')


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
