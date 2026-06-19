#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ADMIRALTY NP202 (North Atlantic & Arctic) Part III -> XTide-Harmonics (Tide).

Politik (Oliver 2026-06-15): NUR echte Lücken bauen. NP202-Raum sonst schon
besser abgedeckt (TICON4/UTide/DWF). Lückenanalyse → ~16 abgelegene russisch-
arktische Häfen (Franz-Josef-Land + Severnaya Zemlya + Laptew/Kara/Tschuktsch),
alle als 0-Coverage verifiziert. MIKROTIDAL (M2 meist <0.2 m) → conf niedrig,
nicht 'Recommended'.

Werte visuell aus Scan_20260615 (24).pdf (NP202 Part III S.406, Höhen in METERN).
Phasen-Zone je Block (Part-III-Header): Franz-Josef-Land/Svalbard/Island = UT(GMT)
→ Meridian +00:00; dann ostwärts -0600/-1000/-1200/-0900/-0700/-0500.
N2/K2 inferiert wie py/build_np203.py.
KOORDS: FJL 910-912 amtlich aus Part II (Scan 62, S.360); Rest Geo-Gazetteer
(web-verifiziert, Oliver-Fallback 'IOC sonst Gazetteer').
"""
import os, re

HARM = os.path.expanduser('~/harmonics')
HDRSRC = f'{HARM}/att/harmonics_att_np203.txt'   # gleiche Tide-Congen-Header-Struktur
OUT = f'{HARM}/att/harmonics_att_np202.txt'


def read_header():
    lines = open(HDRSRC, encoding='iso-8859-1').read().splitlines()
    end = max(i for i, l in enumerate(lines) if 'End congen output' in l)
    header = lines[:end + 1]
    order, in_s = [], False
    for l in lines:
        if l.startswith('# Constituent speeds'):
            in_s = True; continue
        if in_s:
            if l.startswith('#') or not l.strip():
                continue
            m = re.match(r'^(\S+)\s+[\d.]+\s*$', l.strip())
            if m:
                order.append(m.group(1))
                if len(order) == 175:
                    break
    assert len(order) == 175, len(order)
    return header, order


HEADER, ORDER = read_header()


def infer_n2k2(con):
    out = dict(con)
    if 'M2' in con and 'S2' in con:
        gM2, aM2 = con['M2']; gS2, aS2 = con['S2']
        out.setdefault('N2', ((gM2 - 0.536 * (gS2 - gM2)) % 360, round(0.19 * aM2, 4)))
        out.setdefault('K2', (gS2 % 360, round(0.27 * aS2, 4)))
    return out


def dm(d, m):
    return d + m / 60.0


# con: {Konstituente: (g_deg, H_m)}; coord_src: 'PartII' | 'gazetteer'
def S(att, name, lat, lon, mer, z0, con, coord_src, conf=3,
      country='Russia', note=None):
    return dict(att=att, name=name, lat=lat, lon=lon, mer=mer, z0=z0, con=con,
                coord_src=coord_src, conf=conf, country=country, note=note)


# M2/S2/K1/O1 = (g, H[m]) aus NP202 Part III S.406
# Koords durchweg AMTLICH aus NP202 Part II (Scan 62 S.360 FJL, Scan 63 Russia):
# Gazetteer-Werte waren teils stark falsch (990 Mys Kharse: Gazetteer Kharasavey 71/66.8
# vs ATT Ob-Bucht 70.10/73.72 = ~250 km!). Part II = gleiche Stationsnr wie Part III.
STATIONS = [
    # Franz-Josef-Land  (Part-III-Zone UT/GMT → +00:00)
    S(910, 'Mys Flora, Franz Josef Land (NP202 910)', dm(79, 57), dm(50, 5), '+00:00', 0.3,
      {'M2': (324, 0.13), 'S2': (23, 0.04), 'K1': (55, 0.07), 'O1': (67, 0.02)}, 'PartII'),
    S(911, 'Bukhta Tikhaya, Franz Josef Land (NP202 911)', dm(80, 20), dm(52, 48), '+00:00', 0.3,
      {'M2': (291, 0.09), 'S2': (350, 0.03), 'K1': (58, 0.07), 'O1': (59, 0.02)}, 'PartII'),
    S(912, 'Bukhta Teplits, Franz Josef Land (NP202 912)', dm(81, 47), dm(57, 56), '+00:00', 0.4,
      {'M2': (211, 0.17), 'S2': (268, 0.06), 'K1': (62, 0.03), 'O1': (33, 0.01)}, 'PartII'),
    # Severnaya Zemlya / Sedov-Archipel  (Zone -0600 → +06:00)
    S(920, 'Ostrov Domashniy, Severnaya Zemlya (NP202 920)', dm(79, 30), dm(91, 8), '+06:00', 0.3,
      {'M2': (28, 0.10), 'S2': (86, 0.04), 'K1': (46, 0.06), 'O1': (36, 0.02)}, 'PartII'),
    # Neusibirische Inseln  (Zone -1000 → +10:00)
    S(930, 'Ostrov Kotelny (NP202 930)', dm(75, 22), dm(137, 10), '+10:00', 0.3,
      {'M2': (41, 0.07), 'S2': (117, 0.05), 'K1': (306, 0.01)}, 'PartII'),
    # Tschuktschen-/Ostsibirische See  (Zone -1200 → +12:00)
    S(950, 'Mys Serdtse-Kamen (NP202 950)', dm(66, 53), -dm(171, 38), '+12:00', 0.2,
      {'M2': (192, 0.04), 'S2': (290, 0.01), 'K1': (69, 0.01), 'O1': (56, 0.01)}, 'PartII'),
    S(951, 'Pitlekaj (NP202 951)', dm(67, 3), -dm(173, 53), '+12:00', 0.2,
      {'M2': (159, 0.02), 'S2': (227, 0.01), 'K1': (46, 0.01), 'O1': (43, 0.01)}, 'PartII'),
    S(958, 'Ostrov Ayon (NP202 958)', dm(69, 53), dm(167, 52), '+12:00', 0.1,
      {'M2': (359, 0.02), 'S2': (59, 0.01)}, 'PartII'),
    # Laptewsee  (Zone -0900 → +09:00)
    S(966, 'Tiksi Bay (NP202 966)', dm(71, 35), dm(128, 55), '+09:00', 0.3,
      {'M2': (47, 0.14), 'S2': (115, 0.05), 'K1': (111, 0.03), 'O1': (90, 0.01)}, 'PartII'),
    # Taymyr / Karasee  (Zone -0700 → +07:00)
    S(971, 'Komsomolskaya Pravda Islands (NP202 971)', dm(77, 26), dm(106, 40), '+07:00', 0.4,
      {'M2': (314, 0.15), 'S2': (356, 0.06), 'K1': (11, 0.06), 'O1': (30, 0.01)}, 'PartII'),
    S(972, 'Mys Chelyuskin (NP202 972)', dm(77, 43), dm(104, 19), '+07:00', 0.4,
      {'M2': (335, 0.13), 'S2': (26, 0.05), 'K1': (25, 0.03), 'O1': (17, 0.03)}, 'PartII'),
    S(973, 'Hansen Island (NP202 973)', dm(77, 34), dm(102, 24), '+07:00', 0.3,
      {'M2': (40, 0.07), 'S2': (68, 0.02), 'K1': (25, 0.03), 'O1': (7, 0.03)}, 'PartII'),
    S(975, 'Rade de Zarya (NP202 975)', dm(76, 8), dm(95, 8), '+07:00', 0.4,
      {'M2': (39, 0.18), 'S2': (119, 0.08), 'K1': (13, 0.04), 'O1': (11, 0.02)}, 'PartII'),
    S(985, 'Bukhta Dikson (NP202 985)', dm(73, 30), dm(80, 25), '+07:00', 0.3,
      {'M2': (161, 0.10), 'S2': (225, 0.05), 'K1': (50, 0.02), 'O1': (293, 0.01)}, 'PartII'),
    S(986, 'Mys Sopochnaya Karga (NP202 986)', dm(71, 50), dm(82, 45), '+07:00', 0.5,
      {'M2': (286, 0.20), 'S2': (22, 0.09), 'K1': (296, 0.04), 'O1': (196, 0.02)}, 'PartII'),
    S(987, 'Ostrov Nasonovskiy (NP202 987)', dm(70, 52), dm(83, 22), '+07:00', 0.37,
      {'M2': (106, 0.11), 'S2': (181, 0.04), 'K1': (147, 0.04)}, 'PartII'),
    # Obskaya Guba (Ob-Bucht)  (Zone -0500 → +05:00)
    S(989, 'Reka Sabule-Yaga, Obskaya Guba (NP202 989)', dm(72, 10), dm(75, 0), '+05:00', 0.46,
      {'M2': (143, 0.32), 'S2': (183, 0.15), 'K1': (239, 0.06), 'O1': (181, 0.03)}, 'PartII'),
    S(990, 'Mys Kharse, Obskaya Guba (NP202 990)', dm(70, 6), dm(73, 43), '+05:00', 0.37,
      {'M2': (341, 0.26), 'S2': (40, 0.09), 'K1': (240, 0.05), 'O1': (353, 0.01)}, 'PartII'),
    S(992, 'Mys Kamennyy, Obskaya Guba (NP202 992)', dm(68, 30), dm(73, 35), '+05:00', 0.35,
      {'M2': (102, 0.18), 'S2': (194, 0.10), 'K1': (151, 0.02), 'O1': (297, 0.01)}, 'PartII'),
    # --- West-/Nord-Novaya-Zemlya + Yamal/Kara (Part III S.408, Scan_20260616.pdf) ---
    # Konstanten doppelt gelesen (M2-Phase als Zeilen-Anker), Koords amtlich Part II
    # (Oliver durchgegeben). Ragozina/Marre-Salya = Festland Kara -> Zone -0500 (Jekaterinburg);
    # Novaya Zemlya = Moskau-Zeit +03:00. Mikrotidal (conf 3), N2/K2 inferiert.
    S(995, 'Mys Ragozina (NP202 995)', dm(73, 23), dm(70, 7), '+05:00 :Asia/Yekaterinburg', 0.37,
      {'M2': (318, 0.32), 'S2': (118, 0.04), 'K1': (264, 0.08), 'O1': (137, 0.03)}, 'PartII'),
    S(998, 'Mys Marre-Salya (NP202 998)', dm(69, 43), dm(66, 48), '+05:00 :Asia/Yekaterinburg', 0.40,
      {'M2': (165, 0.11), 'S2': (226, 0.05), 'K1': (274, 0.04), 'O1': (86, 0.05)}, 'PartII'),
    S(1001, 'Mys Byk, Novaya Zemlya (NP202 1001)', dm(73, 14), dm(56, 24), '+03:00 :Europe/Moscow', 0.40,
      {'M2': (32, 0.15), 'S2': (94, 0.07), 'K1': (232, 0.03), 'O1': (16, 0.05)}, 'PartII'),
    S(1003, 'Zaliv Russkaya Gavan, Novaya Zemlya (NP202 1003)', dm(76, 14), dm(62, 32), '+03:00 :Europe/Moscow', 0.40,
      {'M2': (254, 0.15), 'S2': (300, 0.07), 'K1': (130, 0.03), 'O1': (249, 0.03)}, 'PartII'),
    S(1004, 'Foki Bight, Novaya Zemlya (NP202 1004)', dm(75, 58), dm(59, 55), '+03:00 :Europe/Moscow', 0.40,
      {'M2': (263, 0.15), 'S2': (299, 0.06), 'K1': (114, 0.03), 'O1': (284, 0.01)}, 'PartII'),
    S(1007, 'Mys Seryebryany, Novaya Zemlya (NP202 1007)', dm(73, 21), dm(54, 4), '+03:00 :Europe/Moscow', 0.39,
      {'M2': (257, 0.24), 'S2': (337, 0.05), 'K1': (214, 0.05), 'O1': (81, 0.01)}, 'PartII'),
    # --- Norwegischer Standardhafen Haugesund (Part III S.408 Scan 5), war nur Referenz, nicht in DB ---
    S(1271, 'Haugesund (NP202 1271)', dm(59, 25), dm(5, 16), '+01:00 :Europe/Oslo', 0.55,
      {'M2': (304, 0.23), 'S2': (350, 0.09), 'K1': (185, 0.02), 'O1': (19, 0.02)}, 'PartII', conf=4),

    # === Trinidad/Tobago + Venezuela (Part III S.413 Scan_20260615(30); Koords Part II
    #     S.378 Scan_20260615(50)). Konstanten + Koords VISUELL aus hochaufgel. Crops.
    #     6-km-Gap-Check 2026-06-17: 17 echte Lücken; DUP übersprungen (Punta Gorda,
    #     Man of War Bay, La Guaira, Port of Spain, Point Fortin -> schon gemessen).
    #     M4/M6 aus S.W.-Korrekturen (1/4- bzw. 1/6-diurnal), wo nicht vernachlässigbar.
    #     Golf von Paria semidiurnal-gemischt (M2 0.3-0.6 m); N-/O-Küste mikrotidal. ===
    # --- Ost-Venezuela / Golf von Paria-Süd (ATT-Zone +0430 -> Meridian -04:30) ---
    S(2312, 'Río Pedernales (Lagoven Jetty), Venezuela (NP202 2312)', dm(9, 59), -dm(62, 15),
      '-04:30 :America/Caracas', 0.80,
      {'M2': (134, 0.59), 'S2': (160, 0.18), 'K1': (194, 0.14), 'O1': (202, 0.08),
       'M4': (172, 0.016), 'M6': (31, 0.042)}, 'PartII', conf=4,
      country='Venezuela', note='Orinoco-Delta; Z0 inferred; phases ATT zone +0430; N2/K2 inferred'),
    S(2318, 'Puerto de Hierro, Venezuela (NP202 2318)', dm(10, 36), -dm(62, 15),
      '-04:30 :America/Caracas', 0.58,
      {'M2': (110, 0.45), 'S2': (137, 0.15), 'K1': (177, 0.11), 'O1': (172, 0.08)}, 'PartII', conf=4,
      country='Venezuela', note='Golfo de Paria E; phases ATT zone +0430; N2/K2 inferred'),
    # --- Trinidad (Golf von Paria) + Tobago (ATT-Zone +0400 -> Meridian -04:00) ---
    S(2319, 'Gaspar Grande, Trinidad and Tobago (NP202 2319)', dm(10, 40), -dm(61, 40),
      '-04:00 :America/Port_of_Spain', 0.88,
      {'M2': (110, 0.30), 'S2': (151, 0.08), 'K1': (183, 0.07), 'O1': (191, 0.06)}, 'PartII', conf=3,
      country='Trinidad and Tobago', note='Chaguaramas; phases ATT zone +0400; N2/K2 inferred'),
    S(2320, 'Carenage Bay, Trinidad and Tobago (NP202 2320)', dm(10, 41), -dm(61, 36),
      '-04:00 :America/Port_of_Spain', 0.73,
      {'M2': (117, 0.27), 'S2': (139, 0.09), 'K1': (188, 0.11), 'O1': (183, 0.07)}, 'PartII', conf=3,
      country='Trinidad and Tobago', note='NW Trinidad; phases ATT zone +0400; N2/K2 inferred'),
    S(2322, 'Lisas Point, Trinidad and Tobago (NP202 2322)', dm(10, 23), -dm(61, 29),
      '-04:00 :America/Port_of_Spain', 0.80,
      {'M2': (122, 0.38), 'S2': (145, 0.12), 'K1': (184, 0.12), 'O1': (173, 0.08)}, 'PartII', conf=3,
      country='Trinidad and Tobago', note='Point Lisas; Z0 inferred; phases ATT zone +0400; N2/K2 inferred'),
    S(2323, 'Pointe-à-Pierre, Trinidad and Tobago (NP202 2323)', dm(10, 19), -dm(61, 28),
      '-04:00 :America/Port_of_Spain', 0.81,
      {'M2': (119, 0.39), 'S2': (146, 0.13), 'K1': (189, 0.11), 'O1': (162, 0.10)}, 'PartII', conf=3,
      country='Trinidad and Tobago', note='Golfo de Paria E; phases ATT zone +0400; N2/K2 inferred'),
    S(2325, 'Bonasse Pier, Trinidad and Tobago (NP202 2325)', dm(10, 6), -dm(61, 52),
      '-04:00 :America/Port_of_Spain', 1.13,
      {'M2': (126, 0.47), 'S2': (162, 0.19), 'K1': (185, 0.11), 'O1': (173, 0.09)}, 'PartII', conf=4,
      country='Trinidad and Tobago', note='Cedros/SW Trinidad; phases ATT zone +0400; N2/K2 inferred'),
    S(2327, 'Herine (Erin) Bay, Trinidad and Tobago (NP202 2327)', dm(10, 4), -dm(61, 40),
      '-04:00 :America/Port_of_Spain', 1.12,
      {'M2': (116, 0.61), 'S2': (139, 0.21), 'K1': (191, 0.09), 'O1': (173, 0.09),
       'M6': (161, 0.133)}, 'PartII', conf=4,
      country='Trinidad and Tobago', note='S Trinidad; shallow-water M6; phases ATT zone +0400; N2/K2 inferred'),
    S(2329, 'Guayaguayare Bay, Trinidad and Tobago (NP202 2329)', dm(10, 9), -dm(61, 1),
      '-04:00 :America/Port_of_Spain', 0.76,
      {'M2': (98, 0.41), 'S2': (137, 0.15), 'K1': (165, 0.05), 'O1': (183, 0.03),
       'M4': (194, 0.016)}, 'PartII', conf=4,
      country='Trinidad and Tobago', note='SE Trinidad; phases ATT zone +0400; N2/K2 inferred'),
    S(2331, 'Nariva River (Cocal), Trinidad and Tobago (NP202 2331)', dm(10, 24), -dm(61, 2),
      '-04:00 :America/Port_of_Spain', 0.80,
      {'M2': (104, 0.35), 'S2': (119, 0.10), 'K1': (187, 0.08), 'O1': (182, 0.07)}, 'PartII', conf=3,
      country='Trinidad and Tobago', note='E Trinidad (Manzanilla); Z0 inferred; phases ATT zone +0400; N2/K2 inferred'),
    S(2332, 'Guayamare Point, Trinidad and Tobago (NP202 2332)', dm(10, 45), -dm(60, 58),
      '-04:00 :America/Port_of_Spain', 0.85,
      {'M2': (96, 0.31), 'S2': (111, 0.09), 'K1': (184, 0.08), 'O1': (179, 0.05)}, 'PartII', conf=3,
      country='Trinidad and Tobago', note='NE Trinidad; data approx; phases ATT zone +0400; N2/K2 inferred'),
    S(2333, 'Toco, Trinidad and Tobago (NP202 2333)', dm(10, 50), -dm(60, 56),
      '-04:00 :America/Port_of_Spain', 0.70,
      {'M2': (94, 0.28), 'S2': (119, 0.09), 'K1': (183, 0.10), 'O1': (172, 0.08)}, 'PartII', conf=3,
      country='Trinidad and Tobago', note='NE tip Trinidad; phases ATT zone +0400; N2/K2 inferred'),
    S(2335, 'Las Cuevas Bay, Trinidad and Tobago (NP202 2335)', dm(10, 47), -dm(61, 24),
      '-04:00 :America/Port_of_Spain', 0.42,
      {'M2': (98, 0.23), 'S2': (104, 0.05), 'K1': (178, 0.05), 'O1': (173, 0.04)}, 'PartII', conf=2,
      country='Trinidad and Tobago', note='N coast Trinidad; microtidal; phases ATT zone +0400; N2/K2 inferred'),
    S(2336, 'Scarborough, Tobago, Trinidad and Tobago (NP202 2336)', dm(11, 11), -dm(60, 44),
      '-04:00 :America/Port_of_Spain', 0.69,
      {'M2': (108, 0.28), 'S2': (122, 0.10), 'K1': (181, 0.08), 'O1': (177, 0.08),
       'M4': (108, 0.041), 'M6': (210, 0.100)}, 'PartII', conf=3,
      country='Trinidad and Tobago', note='Tobago S; shallow-water M4/M6; phases ATT zone +0400; N2/K2 inferred'),
    S(2339, 'Plymouth, Tobago, Trinidad and Tobago (NP202 2339)', dm(11, 13), -dm(60, 47),
      '-04:00 :America/Port_of_Spain', 0.62,
      {'M2': (96, 0.25), 'S2': (125, 0.07), 'K1': (174, 0.09), 'O1': (168, 0.08)}, 'PartII', conf=3,
      country='Trinidad and Tobago', note='Tobago NW; phases ATT zone +0400; N2/K2 inferred'),
    # --- Venezuela Nordküste (ATT-Zone +0430 -> Meridian -04:30); mikrotidal ---
    S(2344, 'Puerto Carúpano, Venezuela (NP202 2344)', dm(10, 40), -dm(63, 15),
      '-04:30 :America/Caracas', 0.20,
      {'M2': (60, 0.11), 'S2': (82, 0.03), 'K1': (170, 0.10), 'O1': (167, 0.07)}, 'PartII', conf=2,
      country='Venezuela', note='N coast; microtidal/mixed-diurnal; phases ATT zone +0430; N2/K2 inferred'),
    S(2347, 'Cumaná, Venezuela (NP202 2347)', dm(10, 28), -dm(64, 11),
      '-04:30 :America/Caracas', 0.15,
      {'M2': (32, 0.06), 'S2': (20, 0.01), 'K1': (171, 0.10), 'O1': (172, 0.07)}, 'PartII', conf=2,
      country='Venezuela', note='Golfo de Cariaco; microtidal/diurnal; phases ATT zone +0430; N2/K2 inferred'),

    # === Karibik-Rest, NUR Stationen mit XTide-Tidenhub >=0.40 m (Oliver 2026-06-17).
    #     Übriger Karibik-Raum mikrotidal ODER schon abgedeckt (Bahamas/Turks=Classic 2004
    #     [Admiralty-Quelle], Mexiko-Golf=SEMAR, Kuba/Bermuda/Barbados=gemessen). 6-km-
    #     Gap-Check + XTide-Mittel-Hub-Filter: nur diese 3 echte Lücken übrig. ===
    # --- Venezuela / Estrecho de Maracaibo (ATT-Zone +0430 -> Meridian -04:30) ---
    S(2381, 'Bahía el Tablazo, Venezuela (NP202 2381)', dm(10, 53), -dm(71, 37),
      '-04:30 :America/Caracas', 0.45,
      {'M2': (166, 0.24), 'S2': (83, 0.03), 'K1': (178, 0.05), 'O1': (185, 0.03)}, 'PartII', conf=3,
      country='Venezuela', note='Estrecho de Maracaibo; Hub ~0.47 m; phases ATT zone +0430; N2/K2 inferred'),
    S(2382, 'Punta de Palmas, Venezuela (NP202 2382)', dm(10, 48), -dm(71, 37),
      '-04:30 :America/Caracas', 0.37,
      {'M2': (155, 0.23), 'S2': (75, 0.04), 'K1': (163, 0.04), 'O1': (163, 0.02)}, 'PartII', conf=3,
      country='Venezuela', note='Estrecho de Maracaibo; Hub ~0.46 m; phases ATT zone +0430; N2/K2 inferred'),
    # --- Kuba Ostspitze (ATT-Zone +0500 -> Meridian -05:00) ---
    S(2524, 'Baracoa, Cuba (NP202 2524)', dm(20, 21), -dm(74, 30),
      '-05:00 :America/Havana', 0.24,
      {'M2': (229, 0.25), 'S2': (253, 0.05), 'K1': (139, 0.08), 'O1': (147, 0.06)}, 'PartII', conf=3,
      country='Cuba', note='E-Kuba; Hub ~0.5 m; phases ATT zone +0500; N2/K2 inferred'),
]


def block(s):
    con = infer_n2k2(s['con'])
    note = s['note'] or (f'Arctic gap port; microtidal; phases zone {s["mer"]}; '
                         'N2/K2 inferred')
    out = ['# BEGIN HOT COMMENTS',
           f'# country: {s["country"]}',
           '# source: ADMIRALTY Tide Tables Vol.2 (NP202), Part III Harmonic Constants',
           f'# att_number: {s["att"]}',
           f'# note: {note}',
           f'# coord_source: {"NP202 Part II" if s["coord_src"]=="PartII" else "geo gazetteer (web)"}',
           '# date_imported: 20260615',
           '# datum: Chart Datum (Z0 = mean level above CD)',
           f'# confidence: {s["conf"]}',
           '# !units: meters',
           f'# !longitude: {s["lon"]:.4f}',
           f'# !latitude: {s["lat"]:.4f}',
           s["name"],
           (s["mer"] if ':' in s["mer"] else f'{s["mer"]} :UTC'),
           f'{s["z0"]:.4f} meters']
    for c in ORDER:
        if c in con:
            g, amp = con[c]
            out.append(f'{c:<16}{amp:.4f}  {g:.2f}')
        else:
            out.append('x 0 0')
    return out


def main():
    lines = list(HEADER)
    for s in STATIONS:
        lines += block(s)
    lines.append('# END')
    with open(OUT, 'w', encoding='iso-8859-1') as f:
        f.write('\n'.join(lines) + '\n')
    print(f'Geschrieben: {OUT} | {len(STATIONS)} Stationen')
    for s in STATIONS:
        print(f'  {s["att"]:4} {s["name"][:42]:42} +N2/K2  ({s["coord_src"]})')


if __name__ == '__main__':
    main()
