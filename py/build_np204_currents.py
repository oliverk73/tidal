#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ADMIRALTY NP204 (ATT Vol.4, Pazifik) Part IIIa - Tidal Stream Harmonic Constants
-> Stromsaetze (Knoten).

Quelle: Foto-Doppelseite S.390-391 in tide_tables/att/np204_doppelseiten_p326-391.pdf
(PDF-Seite 31). S.388-389 fehlen im Scan (Oliver hat das Buch nicht) - dort beginnt
Part IIIa vermutlich (Russland/Korea?). 774-786 stehen auf beiden Seiten gleich
(Gegenprobe der Abschrift: identisch).

Formate wie py/build_np203_currents.py:
  * R   (reversierend): Dir(+)/Dir(-), eine Zeile -> 1D, Flutrichtung = Dir(+)
  * ROT (N/E-Komponenten): Ellipse, Projektion auf die M2-Hauptachse
S.W. corrections sind FAKTOREN (wie py/build_np208.py swcorr):
  H4 = F4*H_M2^2, g4 = 2*g_M2 + f4;  H6 = F6*H_M2^3, g6 = 3*g_M2 + f6
(bei N/E je Komponente mit deren eigenem M2, danach projiziert).
N2/K2/P1 nach Gleichgewicht ergaenzt (wie NP203/NP208).

Aufruf: venv/bin/python py/build_np204_currents.py [AUSGABE.txt] [--nur=703,703a,...|--alle]
(ohne Option nur AUFNEHMEN; --alle = alle 31 Buchstationen, fuer Gegenproben)
"""
import cmath
import math
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HEADER_SRC = os.path.join(ROOT, 'harmonics/utide/harmonics_utide_current_tables.txt')
OUT = os.path.join(ROOT, 'harmonics/att/harmonics_att_np204_currents.txt')
SOURCE = 'ADMIRALTY Tide Tables Vol.4 (NP204), Part IIIa Tidal Streams, p.390-391'


def dm(d, m):
    return math.copysign(abs(d) + m / 60.0, d)


def mer_from_zone(zone):
    """'-0800' -> '+08:00' (Meridian ost-positiv = negierte Zone)."""
    return ('+' if zone[0] == '-' else '-') + f'{zone[1:3]}:{zone[3:5]}'


def K(m2, s2, k1, o1, sw4=None, sw6=None):
    """Druckwerte je Konstituente als (g, H); sw4/sw6 = (f, F) oder None."""
    out = {}
    for c, v in zip(('M2', 'S2', 'K1', 'O1'), (m2, s2, k1, o1)):
        if v is not None and v[1] > 0:
            out[c] = v
    if 'M2' in out:
        g, H = out['M2']
        if sw4:
            f4, F4 = sw4
            out['M4'] = ((2 * g + f4) % 360, round(F4 * H * H, 4))
        if sw6:
            f6, F6 = sw6
            out['M6'] = ((3 * g + f6) % 360, round(F6 * H ** 3, 4))
    return out


def R(no, lat, lon, flood, ebb, z0, kon, zone, tz, land, note=''):
    return dict(no=no, lat=lat, lon=lon, flood=flood, ebb=ebb, z0=z0, const=kon,
                zone=zone, tz=tz, land=land, type='reversing', note=note)


def ROT(no, lat, lon, z0n, n, z0e, e, zone, tz, land, note=''):
    return dict(no=no, lat=lat, lon=lon, z0n=z0n, z0e=z0e, n=n, e=e,
                zone=zone, tz=tz, land=land, type='rotary', note=note)


CN, HK, JP, AK, US = 'Asia/Shanghai', 'Asia/Hong_Kong', 'Asia/Tokyo', 'America/Anchorage', 'America/Los_Angeles'
o = None

# Abschrift S.390/391. Reihenfolge in K(): M2, S2, K1, O1 je (g, H Kn), dann (f4, F4), (f6, F6).
STATIONS = [
    # ---- China, Zone -0800 ----
    R('703', dm(20, 10.0), dm(110, 20.0), 90, 270, -0.31,
      K((229, 0.71), None, (128, 0.92), (61, 0.92)), '-0800', CN, 'China', 'S2 im Buch "-"'),
    R('703a', dm(20, 4.5), dm(110, 22.6), 216, 36, 0.00,
      K((11, 0.30), (117, 0.02), (284, 0.50), (243, 0.48), (149, 0.406)), '-0800', CN, 'China'),
    R('711', dm(22, 17.1), dm(114, 14.2), 300, 120, 0.00,
      K((176, 0.94), (218, 0.35), (181, 0.55), (163, 0.30), (288, 0.087)), '-0800', HK, 'Hong Kong'),
    # ---- Japan, Zone -0900 ----
    ROT('766', dm(30, 5.0), dm(129, 43.6),
        +0.39, K((66, 0.96), (114, 0.28), (26, 0.17), (353, 0.19), (56, 0.065)),
        -0.19, K((245, 0.51), (284, 0.17), (198, 0.10), (164, 0.11), (186, 0.082)), '-0900', JP, 'Japan'),
    ROT('766a', dm(33, 2.7), dm(129, 45.9),
        -0.21, K((51, 1.71), (100, 0.92), (4, 0.42), (324, 0.40), (160, 0.048)),
        0.00, K((238, 1.02), (276, 0.43), (186, 0.27), (193, 0.18), (1, 0.026)), '-0900', JP, 'Japan'),
    ROT('766b', dm(33, 3.7), dm(129, 44.6),
        0.00, K((52, 1.90), (109, 0.72), (15, 0.36), (354, 0.32), (154, 0.020)),
        +0.14, K((272, 0.06), (61, 0.12), (226, 0.04), (356, 0.12), (344, 0.656)), '-0900', JP, 'Japan'),
    ROT('771', dm(26, 11.3), dm(127, 20.2),
        -0.19, K((188, 0.86), (194, 0.24), (30, 0.36), (138, 0.11), (236, 0.089)),
        -0.41, K((192, 0.47), (211, 0.13), (22, 0.21), (157, 0.07), (265, 0.163)), '-0900', JP, 'Japan'),
    ROT('771a', dm(26, 12.6), dm(127, 24.4),
        0.00, K((177, 1.31), (214, 0.43), (22, 0.44), (209, 0.39), (43, 0.014)),
        -0.41, K((33, 0.10), (56, 0.09), (186, 0.02), (292, 0.06), (293, 0.856)), '-0900', JP, 'Japan'),
    ROT('771b', dm(26, 10.4), dm(127, 36.6),
        +0.11, K((141, 0.56), (174, 0.17), (252, 0.04), (273, 0.15), (187, 0.144)),
        +0.12, K((345, 0.13), (358, 0.01), (13, 0.04), (316, 0.02), (69, 2.855)), '-0900', JP, 'Japan'),
    ROT('771c', dm(26, 4.2), dm(127, 37.8),
        -0.39, K((173, 0.44), (238, 0.17), (255, 0.19), (262, 0.55), (222, 0.093)),
        -0.16, K((345, 0.36), (27, 0.17), (76, 0.16), (32, 0.32), (299, 0.252)), '-0900', JP, 'Japan'),
    ROT('774', dm(30, 20.8), dm(130, 47.2),
        0.00, K((173, 1.25), (188, 0.38), (186, 0.31), (162, 0.17), (177, 0.054)),
        0.00, K((321, 0.47), (342, 0.18), (99, 0.13), (268, 0.25), (324, 0.135)), '-0900', JP, 'Japan'),
    ROT('774a', dm(30, 53.7), dm(130, 47.9),
        +0.32, K((214, 0.34), (266, 0.43), (172, 0.49), (137, 0.25), (72, 0.170)),
        0.00, K((347, 0.67), (45, 0.41), (307, 0.25), (204, 0.08), (34, 0.012)), '-0900', JP, 'Japan'),
    ROT('779', dm(33, 26.5), dm(132, 4.8),
        0.00, K((186, 0.81), (216, 0.32), (89, 0.37), (315, 0.12), (311, 0.018)),
        0.00, K((202, 0.85), (237, 0.34), (150, 0.37), (72, 0.37), (124, 0.101)), '-0900', JP, 'Japan'),
    ROT('779a', dm(33, 25.1), dm(132, 3.4),
        0.00, K((174, 0.79), (208, 0.36), (96, 0.31), (359, 0.10), (330, 0.061)),
        0.00, K((210, 1.10), (254, 0.41), (155, 0.36), (83, 0.26), (325, 0.037)), '-0900', JP, 'Japan'),
    R('782', dm(33, 57.2), dm(132, 42.9), 45, 225, 0.00,
      K((254, 1.75), (284, 0.82), (173, 0.44), (138, 0.40), (111, 0.020)), '-0900', JP, 'Japan'),
    ROT('782a', dm(34, 11.9), dm(132, 39.1),
        -0.19, K((227, 0.66), (250, 0.30), (155, 0.14), (118, 0.02), (230, 0.230)),
        -0.30, K((238, 1.72), (254, 0.59), (141, 0.21), (108, 0.19), (233, 0.036)), '-0900', JP, 'Japan'),
    ROT('782b', dm(34, 12.1), dm(132, 39.7),
        0.00, K((216, 0.87), (291, 0.41), (238, 0.62), (216, 0.47), (209, 0.020)),
        0.00, K((230, 2.09), (274, 0.61), (151, 0.41), (114, 0.40), (260, 0.045)), '-0900', JP, 'Japan',
        'Buch: Data approximate'),
    R('786', dm(34, 16.5), dm(134, 59.4), 355, 175, 0.00,
      K((202, 2.03), (222, 0.44), (143, 0.75), (109, 0.69), (179, 0.038)), '-0900', JP, 'Japan'),
    # ---- Alaska, Zone +0900 ----
    R('843', dm(58, 42.0), dm(-157, 15.0), 55, 240, -0.28,
      K((7, 2.48), (92, 0.03), (192, 0.53), (197, 0.24), (328, 0.031), (215, 0.006)), '+0900', AK, 'Alaska'),
    R('850', dm(54, 1.0), dm(-166, 3.0), 295, 115, +0.34,
      K((95, 5.26), (141, 0.84), (109, 1.93), (110, 1.38), (203, 0.005)), '+0900', AK, 'Alaska'),
    R('850a', dm(54, 22.0), dm(-164, 48.0), 295, 105, +0.50,
      K((121, 2.65), (157, 0.73), (138, 1.48), (134, 1.06), (167, 0.010), (16, 0.002)), '+0900', AK, 'Alaska'),
    R('851', dm(54, 51.6), dm(-163, 24.0), 0, 185, -0.32,
      K((80, 3.13), (93, 0.41), (90, 0.66), (105, 0.29), (267, 0.007), (215, 0.002)), '+0900', AK, 'Alaska'),
    # ---- United States, Zone +0800 ----
    R('916', dm(48, 27.7), dm(-122, 57.0), 10, 180, 0.00,
      K((55, 2.34), (50, 0.59), (56, 1.06), (44, 0.53), (0, 0.008), (355, 0.002)), '+0800', US, 'Washington'),
    R('916a', dm(48, 24.4), dm(-122, 38.4), 90, 270, -0.59,
      K((9, 6.05), (44, 0.92), (24, 1.03), (2, 0.47), (170, 0.004), (228, 0.001)), '+0800', US, 'Washington'),
    R('916b', dm(48, 28.0), dm(-122, 47.0), 335, 175, -0.45,
      K((75, 1.33), (103, 0.38), (89, 0.91), (88, 0.35), (318, 0.050), (357, 0.018)), '+0800', US, 'Washington'),
    R('918', dm(47, 18.2), dm(-122, 32.8), 135, 335, 0.00,
      K((75, 2.86), (110, 0.66), (81, 0.93), (62, 0.63), (335, 0.013)), '+0800', US, 'Washington'),
    R('920', dm(48, 2.0), dm(-122, 38.0), 180, 5, -0.50,
      K((66, 1.96), (84, 0.46), (73, 0.85), (66, 0.42)), '+0800', US, 'Washington'),
    R('922', dm(46, 55.0), dm(-124, 8.0), 60, 240, -0.30,
      K((302, 2.27), (325, 0.59), (48, 0.57), (47, 0.30), (174, 0.014)), '+0800', US, 'Washington'),
    R('930', dm(37, 48.6), dm(-122, 30.1), 61, 239, -0.49,
      K((294, 2.36), (300, 0.58), (37, 0.76), (34, 0.46), (36, 0.017), (333, 0.002)), '+0800', US, 'California'),
    R('930a', dm(38, 3.7), dm(-122, 13.2), 98, 289, -0.17,
      K((11, 2.21), (11, 0.35), (97, 0.79), (98, 0.40), (329, 0.038)), '+0800', US, 'California'),
    R('936', dm(32, 40.9), dm(-117, 13.8), 355, 175, -0.09,
      K((198, 1.28), (184, 0.55), (11, 0.41), (0, 0.25), (143, 0.016), (195, 0.005)), '+0800', US, 'California'),
]


def infer(const):
    """N2/K2/P1 nach Gleichgewicht; Werte (g, H)."""
    out = dict(const)
    if 'M2' in const and 'S2' in const:
        gM2, aM2 = const['M2']; gS2, aS2 = const['S2']
        d = (gS2 - gM2 + 180) % 360 - 180          # normiert, s. np203-part3-import
        out.setdefault('N2', ((gM2 - 0.536 * d) % 360, round(0.19 * aM2, 4)))
        out.setdefault('K2', (gS2 % 360, round(0.27 * aS2, 4)))
    elif 'M2' in const:
        out.setdefault('N2', (const['M2'][0], round(0.19 * const['M2'][1], 4)))
    if 'K1' in const:
        out.setdefault('P1', (const['K1'][0], round(0.33 * const['K1'][1], 4)))
    return out


def phasor(H, g):
    return H * cmath.exp(-1j * math.radians(g))


def from_phasor(P):
    return (-math.degrees(cmath.phase(P))) % 360.0, abs(P)


def project_rotary(n, e):
    gN, HN = n['M2']; gE, HE = e['M2']
    Ux = phasor(HE, gE); Uy = phasor(HN, gN)
    Wp = (Ux + 1j * Uy) / 2.0
    Wm = (Ux.conjugate() + 1j * Uy.conjugate()) / 2.0
    gross = abs(Wp) + abs(Wm)
    ell = (abs(Wp) - abs(Wm)) / gross if gross else 0.0
    theta = (cmath.phase(Wp) + cmath.phase(Wm)) / 2.0
    D0 = (90.0 - math.degrees(theta)) % 360.0
    s, c = math.sin(math.radians(D0)), math.cos(math.radians(D0))
    out = {}
    for k in set(n) | set(e):
        gn, hn = n.get(k, (0, 0)); ge, he = e.get(k, (0, 0))
        out[k] = from_phasor(phasor(he, ge) * s + phasor(hn, gn) * c)
    return D0, out, ell


def kopf():
    L = open(HEADER_SRC, encoding='iso-8859-1').readlines()
    cut = next(i for i, l in enumerate(L) if 'BEGIN HOT COMMENTS' in l or l.startswith('# UTide harmonic analysis'))
    order, an = [], False
    for l in L:
        if l.startswith('# Constituent speeds'):
            an = True; continue
        if an:
            m = re.match(r'^(\S+)\s+[\d.]+\s*$', l)
            if m:
                order.append(m.group(1))
                if len(order) == 175:
                    break
    return L[:cut], order


def name_von(st):
    return NAMEN.get(st['no'], f"NP204 {st['no']}, {st['land']} Current")


# Namen nach Klammer-Regel; Lage per Nominatim (7.11.2026)
NAMEN = {
    '703': 'Qiongzhou Haixia (N of Haikou), Hainan, China Current',
    '703a': 'Haikou (Jiangdong), Hainan, China Current',
    '766': 'Tokara Kaikyo (NW of Kuchinoshima), Kagoshima, Japan Current',
    '766b': 'Hario Seto, Nagasaki, Japan Current',
    '771b': 'Kerama Kaikyo (W of Senagajima), Okinawa, Japan Current',
    '771c': 'Itoman (SW off), Okinawa, Japan Current',
    '774a': 'Osumi Kaikyo (17 km SE of Odomari), Kagoshima, Japan Current',
    '779': 'Iyo Nada (N of Kushi), Ehime, Japan Current',
}

# Aufgenommen werden nur Orte ohne gleichwertigen Satz im Bestand (Abgleich 7.11.2026,
# 30 Tage Kurve, Kreuzkorrelation). Gegenprobe der Abschrift an den Dubletten:
#   711 Lei Yue Mun (HK-TSPS) r 0.96 / 20 min; 771, 771a Kerama (JCG) 0.97/0.96, 15 min;
#   782a/782b Mebyo no Seto 0.94/0.97; 786 Tomogashima 0.99; 850 Akutan 0.995;
#   850a Unimak 0.994; 916b Rosario 0.99; 922 Grays Harbor 0.997; 936 Ballast Pt 0.99;
#   Staerke 0.9-1.1 -> Abschrift stimmt. Alaska/USA alle mit NOAA-Satz <= 1 km.
#   Weitere Dubletten: 774 = Yakushima Kaikyo SW of Kumano (JCG, r 0.94, 5 min, x1.06),
#   782 = Tsurushima Suido (NOAA, r 0.97, 15 min, x1.06), 779a = 779 (r 0.99),
#   766a = 766b (r 0.99; 766b liegt in der Engstelle an der Saikai-Bruecke).
AUFNEHMEN = ['703', '703a', '766', '766b', '771b', '771c', '774a', '779']

# Die M2-Hauptachse hat kein Vorzeichen; Probe wie py/flutrichtung_pruefen.py (Strom-
# gegen Wasserstandsphase) und Vorzeichen der JCG-Nachbarn (7.11.2026):
DREHEN = {
    '766b': 'Flut laeuft in die Omura-Bucht nach S; Probe d=+167/-171',
    '771b': 'Probe drehen d=+119/+117; JCG Kerama Kaikyo r -0.77/-0.89',
    '774a': 'Probe d=+160/-172; JCG Osumi Kaikyo r -0.74..-0.85',
    '779': 'Probe drehen d=+138/+127; JCG Iyo Nada r -0.95/-0.97',
}


def block(st, order):
    a = []
    a.append('# BEGIN HOT COMMENTS\n')
    a.append(f"# country: {st['land'] if st['land'] not in ('Alaska', 'Washington', 'California') else 'USA'}\n")
    a.append(f'# source: {SOURCE}\n')
    a.append('# station_type: current\n')
    a.append(f"# att_number: {st['no']}\n")
    a.append(f"# att_zone: {st['zone']}\n")
    a.append(f"# stream_type: {st['type']}\n")
    if st['type'] == 'reversing':
        const = infer(st['const']); datum = st['z0']
        a.append(f"# flood_dir: {st['flood']:03d}\n# ebb_dir: {st['ebb']:03d}\n")
    else:
        flut, c, ell = project_rotary(st['n'], st['e'])
        if st['no'] in DREHEN:      # Hauptachse zeigt in die Ebbe -> um 180 Grad drehen
            flut = (flut + 180) % 360
            c = {k: ((g + 180) % 360, H) for k, (g, H) in c.items()}
            a.append(f"# note: Flutrichtung gedreht ({DREHEN[st['no']]})\n")
        const = infer(c)
        D = math.radians(flut)
        datum = st['z0e'] * math.sin(D) + st['z0n'] * math.cos(D)
        a.append(f'# flood_dir: {round(flut) % 360:03d}\n# ebb_dir: {round(flut + 180) % 360:03d}\n')
        a.append(f'# ellipticity_m2: {ell:+.3f}\n')
        if abs(ell) > 0.25:
            a.append('# rotary_caveat: strongly rotary (|e|>0.25) - 1D major-axis underrepresents speed and shows false slacks\n')
        a.append('# n_e_components: ' + '; '.join(
            f"{comp} {k} {st[comp][k][1]:.2f}kn/{st[comp][k][0]:.0f}" for comp in ('n', 'e') for k in ('M2', 'S2', 'K1', 'O1') if k in st[comp]) + '\n')
    a.append('# inferred: N2 (0.19*M2), K2 (0.27*S2), P1 (0.33*K1) - Part IIIa fuehrt nur M2/S2/K1/O1\n')
    a.append('# shallow_water: M4/M6 aus f4/F4, f6/F6 (H4=F4*H_M2^2, g4=2g_M2+f4)\n')
    if st['note']:
        a.append(f"# note: {st['note']}\n")
    a.append('# datum: Z0 residual current (knots)\n# !units: knots\n')
    a.append(f"# !longitude: {st['lon']:.6f}\n# !latitude: {st['lat']:.6f}\n")
    a.append(name_von(st) + '\n')
    a.append(f"{mer_from_zone(st['zone'])} :{st['tz']}\n")
    a.append(f'{datum:.4f} knots\n')
    for k in order:
        if k in const:
            g, H = const[k]
            a.append(f'{k:<12} {H:.4f}  {g:.2f}\n')
        else:
            a.append(f'{k:<12} x 0 0\n')
    return a


def main(argv):
    out_pfad = next((x for x in argv if not x.startswith('--')), OUT)
    nur = next((x.split('=', 1)[1].split(',') for x in argv if x.startswith('--nur=')), None)
    if nur is None and '--alle' not in argv:
        nur = AUFNEHMEN
    kopf_z, order = kopf()
    z = list(kopf_z)
    n = 0
    for st in STATIONS:
        if nur and st['no'] not in nur:
            continue
        z += block(st, order); n += 1
    open(out_pfad, 'w', encoding='iso-8859-1').writelines(z)
    print(f'{out_pfad}: {n} Stromsaetze')


if __name__ == '__main__':
    main(sys.argv[1:])
