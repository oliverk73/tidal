#!/usr/bin/env python3
# -*- coding: iso-8859-1 -*-
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
HDRSRC = f'{HARM}/utide/harmonics_att_np203.txt'   # gleiche Tide-Congen-Header-Struktur
OUT = f'{HARM}/utide/harmonics_att_np202.txt'


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
def S(att, name, lat, lon, mer, z0, con, coord_src, conf=3):
    return dict(att=att, name=name, lat=lat, lon=lon, mer=mer, z0=z0, con=con,
                coord_src=coord_src, conf=conf)


# M2/S2/K1/O1 = (g, H[m]) aus NP202 Part III S.406
STATIONS = [
    # Franz-Josef-Land  (Part-III-Zone UT/GMT → +00:00; Koords Part II S.360)
    S(910, 'Mys Flora, Franz Josef Land (NP202 910)', dm(79, 57), dm(50, 5), '+00:00', 0.3,
      {'M2': (324, 0.13), 'S2': (23, 0.04), 'K1': (55, 0.07), 'O1': (67, 0.02)}, 'PartII'),
    S(911, 'Bukhta Tikhaya, Franz Josef Land (NP202 911)', dm(80, 20), dm(52, 48), '+00:00', 0.3,
      {'M2': (291, 0.09), 'S2': (350, 0.03), 'K1': (58, 0.07), 'O1': (59, 0.02)}, 'PartII'),
    S(912, 'Bukhta Teplits, Franz Josef Land (NP202 912)', dm(81, 47), dm(57, 56), '+00:00', 0.4,
      {'M2': (211, 0.17), 'S2': (268, 0.06), 'K1': (62, 0.03), 'O1': (33, 0.01)}, 'PartII'),
    # Severnaya Zemlya / Sedov-Archipel  (Zone -0600 → +06:00)
    S(920, 'Ostrov Domashniy, Severnaya Zemlya (NP202 920)', 79.50, 91.13, '+06:00', 0.3,
      {'M2': (28, 0.10), 'S2': (86, 0.04), 'K1': (46, 0.06), 'O1': (36, 0.02)}, 'gazetteer'),
    # Neusibirische Inseln  (Zone -1000 → +10:00)
    S(930, 'Ostrov Kotelny (NP202 930)', 75.95, 137.87, '+10:00', 0.3,
      {'M2': (41, 0.07), 'S2': (117, 0.05), 'K1': (306, 0.01)}, 'gazetteer'),
    # Tschuktschen-/Ostsibirische See  (Zone -1200 → +12:00)
    S(950, 'Mys Serdtse-Kamen (NP202 950)', 66.908, -171.631, '+12:00', 0.2,
      {'M2': (192, 0.04), 'S2': (290, 0.01), 'K1': (69, 0.01), 'O1': (56, 0.01)}, 'gazetteer'),
    S(951, 'Pitlekaj (NP202 951)', 67.08, -173.38, '+12:00', 0.2,
      {'M2': (159, 0.02), 'S2': (227, 0.01), 'K1': (46, 0.01), 'O1': (43, 0.01)}, 'gazetteer'),
    S(958, 'Ostrov Ayon (NP202 958)', 69.79, 168.66, '+12:00', 0.1,
      {'M2': (359, 0.02), 'S2': (59, 0.01)}, 'gazetteer'),
    # Laptewsee  (Zone -0900 → +09:00)
    S(966, 'Tiksi Bay (NP202 966)', 71.65, 129.14, '+09:00', 0.3,
      {'M2': (47, 0.14), 'S2': (115, 0.05), 'K1': (111, 0.03), 'O1': (90, 0.01)}, 'gazetteer'),
    # Taymyr / Karasee  (Zone -0700 → +07:00)
    S(971, 'Komsomolskaya Pravda Islands (NP202 971)', 77.33, 107.00, '+07:00', 0.4,
      {'M2': (314, 0.15), 'S2': (356, 0.06), 'K1': (11, 0.06), 'O1': (30, 0.01)}, 'gazetteer'),
    S(972, 'Mys Chelyuskin (NP202 972)', 77.733, 104.25, '+07:00', 0.4,
      {'M2': (335, 0.13), 'S2': (26, 0.05), 'K1': (25, 0.03), 'O1': (17, 0.03)}, 'gazetteer'),
    S(985, 'Bukhta Dikson (NP202 985)', 73.507, 80.546, '+07:00', 0.3,
      {'M2': (161, 0.10), 'S2': (225, 0.05), 'K1': (50, 0.02), 'O1': (293, 0.01)}, 'gazetteer'),
    S(986, 'Mys Sopochnaya Karga (NP202 986)', 71.88, 82.67, '+07:00', 0.5,
      {'M2': (286, 0.20), 'S2': (22, 0.09), 'K1': (296, 0.04), 'O1': (196, 0.02)}, 'gazetteer'),
    S(987, 'Ostrov Nasonovskiy (NP202 987)', 70.92, 83.14, '+07:00', 0.37,
      {'M2': (106, 0.11), 'S2': (181, 0.04), 'K1': (147, 0.04)}, 'gazetteer'),
    # Yamal / Ob-Bucht  (Zone -0500 → +05:00)
    S(990, 'Mys Kharasavey (NP202 990)', 71.18, 66.77, '+05:00', 0.37,
      {'M2': (341, 0.26), 'S2': (40, 0.09), 'K1': (240, 0.05), 'O1': (353, 0.01)}, 'gazetteer'),
    S(992, 'Mys Kamennyy (NP202 992)', 68.51, 73.57, '+05:00', 0.35,
      {'M2': (102, 0.18), 'S2': (194, 0.10), 'K1': (151, 0.02), 'O1': (297, 0.01)}, 'gazetteer'),
]

# DEFERRED (Koords nicht zuverlässig auffindbar): 973 Hansen Island,
# 975 Rade de Zarya, 989 Reka Sabule-Yaga (M2 0.32!) -> wenn Part-I-Header/Index gescannt.


def block(s):
    con = infer_n2k2(s['con'])
    out = ['# BEGIN HOT COMMENTS',
           '# country: Russia',
           '# source: ADMIRALTY Tide Tables Vol.2 (NP202), Part III Harmonic Constants',
           f'# att_number: {s["att"]}',
           f'# note: Arctic gap port; microtidal; phases zone {s["mer"]}; N2/K2 inferred',
           f'# coord_source: {"NP202 Part II" if s["coord_src"]=="PartII" else "geo gazetteer (web)"}',
           '# date_imported: 20260615',
           '# datum: Chart Datum (Z0 = mean level above CD)',
           f'# confidence: {s["conf"]}',
           '# !units: meters',
           f'# !longitude: {s["lon"]:.4f}',
           f'# !latitude: {s["lat"]:.4f}',
           f'{s["name"]} Tide',
           f'{s["mer"]} :UTC',
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
