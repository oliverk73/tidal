#!/usr/bin/env python3
# -*- coding: iso-8859-1 -*-
"""NP202 Secondary-Port -> Harmonics via Admiralty-Transfer (Pilot).

Demonstriert: aus Part-II-Sekundärhafen-Offsets (ΔT, Höhendiffs) + den
Konstituenten des Referenz-Standardhafens neue Harmonik-Stationen erzeugen.
  A_k = a · A_k,ref ;  g_k = (g_k,ref + speed_k · dt) % 360
  dt  = Mittel(ΔT_HW, ΔT_LW) [h]   (Part-II-Zeitdifferenzen)
  a   = Sek.-Springhub / Ref.-Springhub  (aus MHWS..MLWS-Diffs)
  Z0  = Mittel(MHWS,MHWN,MLWN,MLWS)_sek
Referenz: Ostrov Yekaterininskiy (= Classic 'Yekaterininskaya, Russia',
Z0 2.15, M2 1.161/212, MHWS≈3.7/MHWN≈3.0 = exakt ATT). Meridian +03:00 (Zone -0300).
Pilot: 7 Novaya-Zemlya/Kara-Lücken (1009-1015), alle 0-Coverage. conf 2 (Näherung).
Werte aus Scan_20260615 (64).pdf (NP202 Part II).
"""
import os, re, math

HARM = os.path.expanduser('~/harmonics')
HDRSRC = f'{HARM}/utide/harmonics_att_np203.txt'
CLASSIC = f'{HARM}/classic/harmonics-1997-05-25_mod.txt'
OBS = f'{HARM}/utide/harmonics_utide_observations.txt'
OUT = f'{HARM}/utide/harmonics_att_np202_secondary.txt'


def read_header():
    lines = open(HDRSRC, encoding='iso-8859-1').read().splitlines()
    end = max(i for i, l in enumerate(lines) if 'End congen output' in l)
    header = lines[:end + 1]
    order, speed, in_s = [], {}, False
    for l in lines:
        if l.startswith('# Constituent speeds'):
            in_s = True; continue
        if in_s:
            if l.startswith('#') or not l.strip():
                continue
            m = re.match(r'^(\S+)\s+([\d.]+)\s*$', l.strip())
            if m:
                order.append(m.group(1)); speed[m.group(1)] = float(m.group(2))
                if len(order) == 175:
                    break
    return header, order, speed


HEADER, ORDER, SPEED = read_header()


def read_reference(name, path=CLASSIC):
    """Vollen Konstituenten-Satz eines Standardhafens aus einer Harmonics-Datei lesen."""
    lines = open(path, encoding='iso-8859-1').read().splitlines()
    i = next(k for k, l in enumerate(lines) if l.startswith(name))
    con = {}
    for l in lines[i + 3:]:
        t = l.split()
        if t == ['x', '0', '0']:
            continue
        if len(t) == 3 and t[0] in SPEED:
            con[t[0]] = (float(t[1]), float(t[2]))   # (amp, g)
        else:
            break   # nächste Station / Blockende
    return con


def load_inventory():
    """Alle deployten Stationen (inkl. Classic 1997) für Gap-Check."""
    import json
    d = json.load(open(os.path.expanduser('~/static/js/leaflet_markers_data.json')))
    # EIGENE secondary-Stationen ausschließen, sonst Selbst-Duplikat beim Re-Build
    return [(s[1], s[2]) for s in d['stations']
            if isinstance(s[1], (int, float)) and 'att_np202_secondary' not in str(s[3] if len(s) > 3 else '')]


def is_gap(lat, lon, inv, km=6.0):
    """True wenn KEINE existierende Station innerhalb km -> echte Lücke."""
    for la, lo in inv:
        d = (((la - lat) * 111.0) ** 2 + ((lo - lon) * 111.0 * math.cos(math.radians(lat))) ** 2) ** 0.5
        if d < km:
            return False
    return True


# Standardhafen-Registry: Konstituenten (Classic 1997) + ATT-Pegelstände
# (MHWS,MHWN,MLWN,MLWS). KEM-Stände nach Admiralty-Näherung MHWS=Z0+(M2+S2) etc.
# aus Classic-Konstituenten (Z0 1.10, M2 0.586, S2 0.144); reproduziert die ATT-
# Stände von Yekaterininskiy exakt (Quercheck), daher für Kem ebenso angesetzt.
def p3_ref(con3, z0):
    """Part-III-Standardhafen (NP202 S.408): con3={Konst:(H,g)} M2/S2/K1/O1,
    N2/K2 inferiert, Pegel-Stände + Spring aus Konstituenten (Admiralty-Näherung
    MHWS=Z0+(M2+S2) usw.). Phasen in Lokalzeit -> Meridian via Block. KEINE
    Kalibrierung nötig (Admiralty-konsistent mit den Part-II-Differenzen)."""
    con = dict(con3)
    (hM2, gM2), (hS2, gS2) = con['M2'], con['S2']
    con['N2'] = (round(0.19 * hM2, 4), (gM2 - 0.536 * (gS2 - gM2)) % 360)
    con['K2'] = (round(0.27 * hS2, 4), gS2 % 360)
    levels = (z0 + hM2 + hS2, z0 + hM2 - hS2, z0 - hM2 + hS2, z0 - hM2 - hS2)
    return dict(con=con, levels=levels, spring=2 * (hM2 + hS2))


REFS = {
    'YEKAT': dict(name='Yekaterininskaya, Russia', path=CLASSIC, levels=(3.7, 3.0, 1.3, 0.5)),
    'KEM':   dict(name='Port Kem, Russia',         path=CLASSIC, levels=(1.83, 1.54, 0.66, 0.37)),
}
for _k, _r in REFS.items():
    _r['con'] = read_reference(_r['name'], _r['path'])
    _r['spring'] = _r['levels'][0] - _r['levels'][3]

# Norwegische Standardhäfen: Part-III-Direkt-Konstanten (NP202 S.408 = Scan 25),
# Phasen Lokalzeit Zone -0100. Gegen gemessenes Honningsvåg validiert (Narvik-Ref):
# HW-Versatz 10 min, Höhe 4 cm OHNE Kalibrierung. (H,g) = Amplitude[m], Phase[°].
REFS['NARVIK'] = p3_ref({'M2': (1.00, 4), 'S2': (0.35, 44), 'K1': (0.11, 212), 'O1': (0.03, 58)}, 1.82)
REFS['HAMMERFEST'] = p3_ref({'M2': (0.89, 48), 'S2': (0.28, 88), 'K1': (0.08, 229), 'O1': (0.03, 64)}, 1.67)
REFS['TROMSO'] = p3_ref({'M2': (0.84, 29), 'S2': (0.28, 73), 'K1': (0.07, 223), 'O1': (0.04, 66)}, 1.61)
REFS['LODINGEN'] = p3_ref({'M2': (0.96, 3), 'S2': (0.36, 45), 'K1': (0.11, 222), 'O1': (0.03, 61)}, 1.69)
REFS['ALESUND'] = p3_ref({'M2': (0.62, 319), 'S2': (0.21, 357), 'K1': (0.06, 168), 'O1': (0.06, 23)}, 1.20)
REFS['BERGEN'] = p3_ref({'M2': (0.45, 312), 'S2': (0.16, 353), 'K1': (0.03, 178), 'O1': (0.03, 27)}, 0.90)


def hm(s):
    """'+0135' -> +1.5833 h ; '-0452' -> -4.8667 h ; float -> float ; None -> None.

    Floats erlauben vorgemittelte ΔT (Mittel der zwei HW- bzw. LW-Spalten), wo
    die beiden Spalten merklich differieren (z. B. Narvik-Block, ~30 min Diurnal)."""
    if s is None or isinstance(s, float):
        return s
    sign = -1 if s[0] == '-' else 1
    s = s.lstrip('+-')
    return sign * (int(s[:-2]) + int(s[-2:]) / 60.0)


def dm(d, m):
    return d + m / 60.0


# (att, name, lat, lon, dT_HW, dT_LW, dMHWS,dMHWN,dMLWN,dMLWS[, ML])
# ML (11. Feld, optional) = ATT-Spalte "ML Z0" = Mittelwasser über Kartennull;
# wenn vorhanden direkt als XTide-Z0 genutzt (sonst aus Ständen berechnet).
# --- Block A: Referenz OSTROV YEKATERININSKIY ---
SEC_YEKAT = [
    (1009, 'Guba Belushya, Novaya Zemlya', dm(71, 32), dm(52, 19), '+0135', '+0120', -3.2, -2.6, -1.2, -0.4),
    (1010, 'Guba Nekhvatova, Novaya Zemlya', dm(71, 16), dm(53, 30), '+0143', None, -3.4, -2.8, -1.2, -0.4),
    (1011, 'Guba Kamyenka, Kara Strait', dm(70, 36), dm(57, 27), '+0735', '+0725', -3.0, -2.5, -1.0, -0.4),
    (1012, 'Guba Dolgaya, Kara Strait', dm(70, 15), dm(58, 43), '-0452', '-0656', -3.2, -2.6, -1.1, -0.4),
    (1013, 'Bukhta Varneka, Yugorski Strait', dm(69, 42), dm(60, 4), '-0213', '-0224', -2.9, -2.4, -1.0, -0.3),
    (1014, 'Ostrov Sokoliy, Yugorski Strait', dm(69, 50), dm(60, 44), '-0430', '-0440', -2.9, -2.4, -1.0, -0.3),
    (1015, 'Khabarovo, Yugorski Strait', dm(69, 39), dm(60, 25), '-0330', '-0340', -3.1, -2.5, -1.1, -0.4),
    # --- Batch 2: Pechora-See / Kolguyev / Kanin / Weißmeer-Trichter (Mezen-Bucht) ---
    # Werte aus Scan_20260615 (64).pdf, doppelt gelesen. LW ⊙ -> dt=nur HW.
    (1017, 'Ostrov Dolgiy', dm(69, 12), dm(59, 10), '-0331', None, -2.7, -2.2, -0.9, -0.3),
    (1021, 'Ostrov Varandyey', dm(68, 49), dm(58, 0), '-0329', None, -2.7, -2.2, -0.9, -0.3),
    (1023, 'Mys Russki Zavorot', dm(68, 59), dm(54, 34), '-0515', None, -2.7, -2.2, -0.9, -0.3),
    (1024, 'Reka Pechora bar', dm(68, 23), dm(54, 26), '-0156', '-0208', -2.8, -2.3, -0.9, -0.3),
    (1025, 'Bugrino, Kolguyev Island', dm(68, 48), dm(49, 16), '+0519', '+0537', -2.1, -1.8, -0.7, -0.2),
    (1026, 'Reka Indiga', dm(67, 42), dm(48, 46), '+0846', '+0830', -1.7, -1.2, -0.5, 0.1),
    ('1026a', 'Mys Mikulkin', dm(67, 48), dm(46, 41), '+0733', '+0724', -0.2, 0.3, -0.2, 0.4),
    (1027, 'Ostrov Korga', dm(68, 23), dm(46, 10), '+0545', '+0534', -1.3, -1.1, -0.3, -0.1),
    (1028, 'Mys Kanin Nos', dm(68, 40), dm(43, 47), '+0310', '+0258', -0.6, -0.5, -0.2, -0.1),
    (1031, 'Reka Kiya Mouth', dm(67, 40), dm(44, 6), '+0435', '+0446', 0.5, 0.5, 0.4, 0.5),
    (1032, 'Banka Litke', dm(67, 11), dm(42, 48), '+0412', None, 2.3, 1.9, 0.8, 0.4),
    (1033, 'Mys Konushin', dm(67, 11), dm(43, 47), '+0602', '+0553', 3.5, 2.9, 1.2, 0.5),
    (1034, 'Semzha, Mezen River', dm(66, 9), dm(44, 6), '+0619', '+0644', 4.0, 3.9, 0.6, 0.6),
    (1036, 'Ostrov Morzhovets', dm(66, 44), dm(42, 27), '+0506', '+0454', 2.2, 1.9, 0.6, 0.4),
    (1037, 'Mys Voronov', dm(66, 31), dm(42, 14), '+0349', None, 3.1, 2.6, 1.1, 0.4),
    # 1035 Kamenka: kleiner Hub (~1.5 m) trotz Mezen-Trichter, weil flussaufwärts
    #   OBERHALB der Mezen-Sandbarre reibungsgedämpft. KEIN Druckfehler -> Buch-MLZ0=1.4
    #   bestätigt intern (Mittel der 4 Stände = 1.5 ≈ 1.4). Oliver-Gegencheck 2026-06-16.
    (1035, 'Kamenka, Mezen River', dm(65, 53), dm(44, 8), '+0821', '+0726', -1.4, -0.9, -0.4, 0.3),
]

# --- Block B: Referenz PORT OF KEM' (Karelische Küste + Kandalaksha-Golf) ---
# Werte aus Scan_20260615 (65).pdf = NP202 Part II S.363, doppelt gelesen.
# Zone -0300 -> Meridian +03:00. LW ⊙ -> dt=nur HW; 11. Feld ML = ATT-"ML Z0".
# 1067 PORT OF KEM' selbst NICHT enthalten (= Classic 'Port Kem', schon vorhanden).
SEC_KEM = [
    (1065, 'Ostrov Solovetskiy', dm(65, 1), dm(35, 42), '+0022', '+0032', -0.9, -0.7, -0.3, -0.2),
    (1066, 'Ostrov Yuzhnyy Rombak', dm(65, 2), dm(35, 2), '-0001', '-0013', 0.0, 0.0, 0.0, 0.0),
    (1069, "Mys Pon'goma Navolok", dm(65, 20), dm(34, 32), '-0022', None, -0.1, -0.1, 0.0, 0.0),
    (1070, 'Mys Solomenny', dm(65, 41), dm(34, 53), '-0033', None, -0.1, -0.1, 0.0, 0.0),
    (1071, 'Kalgalaksha', dm(65, 45), dm(34, 41), '+0008', None, -0.3, -0.3, -0.1, -0.1),
    (1072, 'Gridina', dm(65, 55), dm(34, 41), '-0107', '-0110', -0.2, -0.2, -0.2, -0.2, 0.94),
    (1073, 'Ostrov Sryedniy, Guba Keret', dm(66, 18), dm(33, 39), '-0120', '-0102', 0.1, 0.2, 0.1, 0.0),
    (1074, 'Reka Kovda', dm(66, 42), dm(32, 52), '-0114', None, 0.4, 0.4, 0.2, 0.1),
    (1075, 'Kandalaksha', dm(67, 8), dm(32, 25), '-0131', '-0057', 1.2, 1.1, 0.5, 0.2, 1.25),
    (1076, 'Guba Porya', dm(66, 46), dm(33, 48), '-0130', '-0122', -0.3, -0.3, -0.2, -0.3, 0.85),
    (1077, 'Guba Malaya Pirya', dm(66, 40), dm(34, 20), '-0114', '-0052', -0.3, -0.3, 0.0, -0.1, 0.95),
    (1079, 'Reka Varzuga', dm(66, 16), dm(36, 57), '-0113', None, -0.3, -0.3, None, -0.1),
    (1080, 'Tetrino', dm(66, 4), dm(38, 15), '-0143', None, 0.0, 0.0, 0.0, 0.0),
]

# --- Block C: Referenz OSTROV YEKATERININSKIY, Terskiy-/Murman-Küste + Kola-Bucht ---
# Scan_20260615 (65).pdf = NP202 Part II S.363 (untere Hälfte), doppelt gelesen.
# Gezeiten-Maximum an der Gorlo-Enge (Orlov-Terskiy/Gorodetskiy ~+2.4), nach
# beiden Seiten abnehmend -> physikalisch konsistent. ML-Spalte als Quercheck
# (Z0 stimmt überall ±3 cm). Kola-Bucht-Häfen ~identisch zur Referenz (Diff 0).
# No. der Kola-Bucht-Enden (1105/1107/1108) im blassen Rand leicht unsicher.
SEC_YEKAT2 = [
    (1082, 'Ostrov Sosnovets', dm(66, 30), dm(40, 41), '+0446', '+0439', 0.2, 0.1, -0.4, -0.1, 2.0),
    (1083, 'Ostrov Veshnyak', dm(67, 6), dm(41, 23), '+0401', '+0402', 2.1, 1.6, 0.0, -0.3, 3.0),
    (1084, 'Mys Orlov-Terskiy Tonkiy', dm(67, 12), dm(41, 20), '+0344', '+0347', 2.1, 1.6, 0.3, -0.1, 3.09),
    (1085, "Mys Bol'shoy Gorodetskiy", dm(67, 43), dm(40, 55), '+0213', '+0213', 2.9, 2.4, 1.1, 0.4),
    (1087, 'Guba Gremikha', dm(68, 4), dm(39, 30), '+0200', '+0148', 2.0, 1.6, 0.8, 0.5, 3.35),
    (1088, 'Guba Savikha', dm(68, 11), dm(39, 7), '+0143', '+0138', 1.8, 1.5, 0.7, 0.3),
    (1089, 'Reka Drozdovka', dm(68, 20), dm(38, 25), '+0127', '+0119', 0.8, 0.7, 0.6, 0.6, 2.81),
    (1090, 'Guba Vostochnaya Litsa', dm(68, 38), dm(37, 48), '+0124', '+0117', 1.1, 0.8, 0.4, 0.2),
    (1091, 'Reka Kharlovka', dm(68, 47), dm(37, 19), '+0110', '+0106', 0.2, 0.2, 0.2, 0.3, 2.37),
    (1092, 'Guba Rynda', dm(68, 55), dm(36, 50), '+0101', '+0057', 0.4, 0.4, 0.2, 0.1, 2.32),
    (1093, 'Guba Porchnikha', dm(69, 5), dm(36, 18), '+0046', '+0041', 0.5, 0.4, 0.1, 0.2, 2.32),
    (1094, 'Guba Podpakhta', dm(69, 9), dm(35, 56), '+0045', '+0040', 0.4, 0.4, 0.2, 0.1, 2.30),
    (1095, 'Guba Teriberskaya', dm(69, 11), dm(35, 8), '+0020', '+0020', 0.2, 0.0, 0.1, 0.0, 2.23),
    (1096, 'Proliv Malyy Oleniy', dm(69, 15), dm(34, 41), '+0015', '+0015', 0.2, 0.0, 0.1, 0.0),
    (1097, "Guba Mogil'naya, Ostrov Kildin", dm(69, 19), dm(34, 20), '+0017', '+0017', 0.3, 0.2, 0.1, 0.0, 2.27),
    (1098, 'Guba Zelenetskaya Zapadnaya', dm(69, 18), dm(33, 45), '-0001', '-0001', 0.0, 0.0, 0.0, 0.0),
    (1099, 'Guba Sayda', dm(69, 15), dm(33, 15), '+0003', '+0003', 0.0, 0.0, 0.0, 0.0),
    (1101, 'Mys Velikiy', dm(69, 5), dm(33, 17), '+0001', '+0001', 0.0, 0.0, 0.0, 0.0),
    (1102, 'Mys Bazisnyy', dm(69, 1), dm(33, 4), '+0017', '+0017', 0.0, 0.0, 0.0, 0.0),
    (1103, 'Murmansk', dm(68, 58), dm(33, 3), '+0016', '+0005', -0.4, -0.2, 0.1, 0.3, 2.09),
    (1105, 'Guba Korelinskiy', dm(69, 25), dm(33, 25), '-0003', '-0003', 0.0, 0.0, 0.0, 0.0),
    (1107, 'Port Vladimir, Guba Ura', dm(69, 25), dm(33, 9), '+0008', '-0004', -0.5, -0.4, 0.1, 0.3, 2.01),
    (1108, 'Bukhta Nasha', dm(69, 23), dm(32, 55), '-0003', '-0003', 0.0, 0.0, 0.0, 0.0),
    (1110, 'Guba Zapadnaya Litsa', dm(69, 29), dm(32, 30), '-0003', '-0003', 0.0, 0.0, 0.0, 0.0),
    (1111, 'Bukhta Ozerko', dm(69, 44), dm(32, 9), '-0010', '-0010', 0.0, 0.0, 0.0, 0.0),
    (1112, "Guba Malyy Korabel'naya", dm(69, 35), dm(32, 45), '-0001', '-0001', 0.0, 0.0, 0.0, 0.0),
]

# --- Block D: letzte russische Kola-Häfen (Pechenga), Yekat-Ref, Zone -0300 ---
# Scan_20260615 (66).pdf = S.364 oben.
SEC_YEKAT3 = [
    (1113, "Guba Bol'shoy Korabel'naya", dm(69, 41), dm(33, 6), '-0005', '-0005', 0.0, 0.0, 0.0, 0.0),
    (1114, 'Guba Zubovskaya', dm(69, 47), dm(32, 40), '-0014', '-0014', 0.0, 0.0, 0.0, 0.0),
    (1115, 'Guba Vayda', dm(69, 56), dm(32, 0), '-0023', '-0023', -0.1, -0.1, 0.0, 0.0),
    (1118, 'Linakhamari, Guba Pechenga', dm(69, 39), dm(31, 22), '-0030', '-0035', -0.4, -0.2, 0.1, 0.1),
    (1119, 'Guba Bazarnaya', dm(69, 46), dm(31, 2), '-0029', '-0029', -0.3, -0.3, -0.1, 0.0),
]

# --- Block D2: West-/Nord-Novaya-Zemlya, Ref Yekaterininskiy, Zone -0300 ---
# Part-II-Werte von Oliver durchgegeben (Part-III-K1/O1 nicht sicher lesbar -> Transfer).
# Geschwister mit Part-III-Direktkonstanten (995/998/1001/1003/1004/1007) stehen in build_np202.py.
SEC_YEKAT4 = [
    (1002, 'Mys Zhelaniya', dm(76, 57), dm(68, 35), '+0155', '+0145', -3.1, -2.5, -1.0, -0.3),
    (1005, 'Guba Krestovaya', dm(74, 7), dm(55, 30), '+0130', '+0120', -2.9, -2.3, -0.9, -0.3),
    (1006, 'Guba Mityushikha', dm(73, 39), dm(54, 48), '+0140', '+0130', -2.7, -2.1, -1.0, -0.3),
    (1008, 'Zaliv Pukhovyy', dm(72, 39), dm(52, 42), '+0115', '+0105', -2.8, -2.3, -1.0, -0.3),
]

# --- Block E: norwegische Finnmark-Häfen, Ref OSTROV YEKATERININSKIY, ZONE -0100 ---
# Scan 66/S.364. WICHTIG (Vard\xf8-validiert, 11 min): Output-Meridian = Sekundär-
# Ortszone +01:00, ATT-Diff DIREKT angewandt (die 2h Moskau/Norwegen-Zonendiff
# steckt bereits in den großen -02xx/-03xx/-04xx-Differenzen). \xf8=ø \xe5=å.
# 1131 KIRKENES + 1188 NARVIK + 1150 HAMMERFEST = Standardhäfen (nicht hier).
# Vard\xf8 (1134) Duplikat -> Gap-Check skippt. Narvik-/Hammerfest-ref Bl\xf6cke
# (Russenes, Honningsv\xe5g..., Karhavn...) ZURÜCKGESTELLT: Referenz nur als
# UTide-Messung (+00:00) vorhanden -> ~40 min Timing-Versatz (Honningsv\xe5g-Test).
SEC_NORWAY_YEKAT = [
    (1130, 'Grense Jakobselv', dm(69, 46), dm(30, 44), '-0240', '-0240', -0.3, -0.4, -0.1, 0.0),
    (1132, 'Karlbotn, Varangerfjorden', dm(70, 7), dm(28, 36), '-0240', '-0245', -0.2, -0.3, -0.1, 0.0),
    (1133, 'Vads\xf8', dm(70, 4), dm(29, 45), '-0235', '-0235', -0.2, -0.2, -0.1, 0.1),
    (1134, 'Vard\xf8', dm(70, 20), dm(31, 6), '-0245', '-0255', -0.3, -0.3, -0.1, 0.1),
    (1135, 'Syltefjorden', dm(70, 34), dm(30, 14), '-0305', '-0310', -0.6, -0.6, -0.1, 0.2),
    (1136, 'Kongsfjorden', dm(70, 43), dm(29, 19), '-0315', '-0315', -0.8, -0.6, -0.1, 0.2),
    (1137, 'Berlev\xe5g', dm(70, 52), dm(29, 6), '-0330', '-0335', -1.0, -0.8, -0.3, 0.0),
    (1138, 'Smalfjorden, Tanafjorden', dm(70, 26), dm(28, 4), '-0340', '-0345', -0.8, -0.8, -0.3, 0.0),
    (1139, 'Skj\xe5nes, Hopsfjorden', dm(70, 48), dm(28, 7), '-0340', '-0345', -0.9, -0.8, -0.3, 0.1),
    (1140, 'Mehamn', dm(71, 2), dm(27, 51), '-0405', '-0410', -1.0, -0.8, -0.3, 0.0),
    (1141, 'Kj\xf8llefjord', dm(70, 57), dm(27, 21), '-0425', '-0430', -0.9, -0.9, -0.4, 0.1),
    (1142, 'Ifjorden, Laksfjorden', dm(70, 28), dm(27, 6), '-0425', '-0430', -1.0, -0.8, -0.3, 0.1),
]

# --- Block F: norweg. Finnmark, Ref NARVIK (Part III S.408), ZONE -0100 ---
# Scan 66/S.364. ΔT als vorgemittelte Dezimalstunden (HW- u. LW-Spaltenmittel,
# da die zwei Spalten ~30 min differieren). Referenz = Part-III-Direktkonstanten
# (KEINE Kalibrierung; gegen gemessenes Honningsv\xe5g 10 min/4 cm validiert).
# Honningsv\xe5g (1145) Duplikat -> Gap-Check skippt. \xe6=æ \xf8=ø \xe5=å.
SEC_NORWAY_NARVIK = [
    (1143, 'Russenes, Porsangen', dm(70, 29), dm(25, 5), 2.833, 2.875, -0.3, -0.1, -0.3, 0.0),
    (1144, 'Hamnbukt, Porsangen', dm(70, 6), dm(25, 5), 2.917, 2.958, -0.2, -0.1, -0.1, 0.0),
    (1145, 'Honningsv\xe5g', dm(70, 59), dm(25, 59), 2.917, 2.958, -0.3, -0.2, -0.3, 0.0),
    (1146, 'Gjesv\xe6r', dm(71, 6), dm(25, 23), 2.417, 2.458, -0.3, -0.1, -0.3, 0.0),
    (1147, 'Hav\xf8ysund', dm(71, 0), dm(24, 40), 2.208, 2.25, -0.3, -0.1, 0.0, 0.0),
    (1148, 'Finneset, Ing\xf8y', dm(71, 5), dm(24, 1), 1.833, 1.875, -0.6, -0.3, -0.3, -0.1),
    (1149, 'Litlefjorden, Revsbotn', dm(70, 42), dm(24, 39), 1.75, 1.792, -0.4, -0.2, -0.3, -0.1),
]

# --- Block G: norweg. Finnmark, Ref HAMMERFEST (Part III S.408), ZONE -0100 ---
# Scan 66/S.364 unten. ΔT vorgemittelt (HW/LW-Spaltenmittel, ~30 min Diurnal). \xf8=ø \xe6=æ
SEC_NORWAY_HAM = [
    (1151, 'Karhavn, S\xf8r\xf8ysundet', dm(70, 33), dm(23, 9), 1.417, 1.417, -0.5, -0.3, -0.2, -0.1),
    (1152, 'Skarvfjorden, S\xf8r\xf8ya', dm(70, 46), dm(23, 7), 1.5, 1.542, -0.3, -0.2, -0.1, 0.0),
    (1153, 'S\xf8rv\xe6r, S\xf8r\xf8ya', dm(70, 38), dm(21, 59), 1.25, 1.292, -0.5, -0.3, -0.2, 0.0),
    (1154, 'Komagfjord, Vargsundet', dm(70, 16), dm(23, 23), 1.25, 1.292, -0.2, -0.2, -0.1, 0.0),
]

# --- Block H: Troms-Fjorde, Ref NARVIK (Part III), ZONE -0100 (Scan 67/S.365 oben) ---
# ΔT vorgemittelte Dezimalstd (HW/LW-Spaltenmittel). \xe6=æ \xf8=ø \xe5=å
SEC_NORWAY_NARVIK2 = [
    (1157, 'Badderen, Kv\xe6nangenfjorden', dm(69, 51), dm(22, 1), 1.125, 1.083, -0.3, -0.2, -0.2, 0.0),
    (1158, 'Skjerv\xf8y', dm(70, 2), dm(20, 58), 1.25, 1.167, -0.3, -0.2, -0.1, 0.0),
    (1159, 'Lyngseidet, Lyngenfjorden', dm(69, 35), dm(20, 13), 1.042, 0.917, -0.2, -0.1, -0.2, 0.0),
    (1160, 'J\xf8vik, Ullsfjorden', dm(69, 36), dm(19, 50), 1.042, 0.833, -0.3, -0.3, -0.3, 0.0),
    (1161, 'Torsv\xe5g', dm(70, 15), dm(19, 31), 0.958, 0.833, -0.5, -0.3, -0.3, 0.0),
    (1162, 'Finnkroken, Grotsundet', dm(69, 50), dm(19, 26), 1.125, 1.0, -0.3, -0.2, -0.3, 0.0),
]

# --- Block I: Troms-Fjorde, Ref TROMSO (Part III), ZONE -0100 (Scan 67/S.365 Mitte) ---
# Nördliche Troms-Fjordhäfen, eindeutig Tromsø-ref (kleine +ΔT, alle 68.6-70°N).
# ΔT vorgemittelt. \xf8=ø \xe6=æ. Vesterålen/Lofoten (Risøyhamn südwärts) ZURÜCKGESTELLT:
# Referenz wechselt dort zu Narvik/Lødingen + alter Scan 67 zu unsicher -> flacher Rescan.
SEC_NORWAY_TROMSO = [
    (1164, 'Ling\xf8ya', dm(69, 55), dm(18, 29), 0.542, 0.417, -0.9, -0.6, -0.4, -0.1),
    (1165, 'Tennes, Balsfjorden', dm(69, 18), dm(19, 21), 1.125, 1.0, -0.5, -0.2, -0.3, 0.0),
    (1166, 'Rystraumen, Balsfjorden', dm(69, 34), dm(18, 45), 1.125, 1.0, -0.6, -0.4, -0.4, 0.0),
    (1167, 'Laukvik, Malangen', dm(69, 34), dm(17, 54), 0.542, 0.417, -1.0, -0.7, -0.4, -0.1),
    (1168, 'Keianes, Malangen', dm(69, 16), dm(18, 43), 0.625, 0.5, -0.9, -0.7, -0.4, -0.1),
    (1169, 'Gibostad, Gisundet', dm(69, 21), dm(18, 5), 0.583, 0.5, -1.2, -0.8, -0.5, -0.2),
    (1170, 'Gryllefjord', dm(69, 22), dm(17, 4), 0.542, 0.417, -1.2, -0.7, -0.5, -0.1),
    (1171, 'Finnlandsneset, Dyr\xf8ysundet', dm(69, 6), dm(17, 38), 0.542, 0.417, -1.0, -0.6, -0.4, -0.1),
    (1172, 'Skrolsvik', dm(69, 4), dm(16, 49), 0.542, 0.417, -1.0, -0.7, -0.4, -0.1),
    (1173, 'Sol\xf8y', dm(68, 47), dm(17, 47), 0.542, 0.417, -0.7, -0.4, -0.5, -0.1),
    (1175, 'For\xf8ys\xe6ter, Gullesfjorden', dm(68, 38), dm(15, 47), 0.542, 0.417, -0.9, -0.8, -0.4, -0.1),
]

# --- Block I2: Vesterålen/Lofoten, Ref TROMSO, ZONE -0100 (Scan_20260616 (14)=S.365 flach) ---
# Referenz per STANDARD-PORT-Marker bestätigt: Block läuft von TROMSO bis NARVIK(unten) -> alle Tromsø-ref
# (norweg. Außenküste nahezu gleichphasig, kleine ΔT korrekt). ΔT vorgemittelt. \xe6=æ \xf8=ø \xe5=å \xd8=Ø
SEC_NORWAY_TROMSO2 = [
    (1176, 'Evenskj\xe6r', dm(68, 35), dm(16, 33), 0.458, 0.333, -0.9, -0.6, -0.3, -0.1),
    (1178, 'Ris\xf8yhamn', dm(68, 58), dm(15, 39), 0.583, 0.208, -1.1, -0.8, -0.4, -0.1),
    (1179, '\xd8ksnes', dm(68, 53), dm(14, 56), 0.417, 0.583, -1.1, -1.0, -0.4, -0.1),
    (1180, 'Sortland', dm(68, 42), dm(15, 26), 0.417, 0.583, -1.2, -0.8, -0.3, -0.1),
    (1181, 'Stokmarknes', dm(68, 34), dm(14, 56), 0.417, 0.583, -1.2, -0.9, -0.3, -0.1),
    (1183, 'Eggum, Lofoten', dm(68, 19), dm(13, 41), 0.417, 0.542, -1.0, -0.4, -0.1, -0.1),
    (1184, 'Stamsund, Lofoten', dm(68, 8), dm(13, 52), 0.333, 0.5, -0.6, -0.4, -0.2, 0.0),
    (1185, 'S\xf8rv\xe5gen, Lofoten', dm(67, 53), dm(13, 2), 0.333, 0.5, -0.4, -0.2, -0.2, -0.1),
    (1186, 'R\xf8st', dm(67, 30), dm(12, 5), 0.167, 0.333, -0.7, -0.4, -0.3, -0.1),
    (1187, 'L\xf8dingen', dm(68, 25), dm(16, 0), 0.25, 0.417, -0.2, -0.3, -0.1, -0.1),
]

# --- Block J: Vestfjord/Salten/Helgeland, Ref NARVIK, ZONE -0100 (Scan_20260616 (15)=S.366 flach) ---
# Alle 1190-1218 = NARVIK-ref (TRONDHEIM 1219 = Standardhafen unten). ΔT vorgemittelt.
# Innenfjord-Häfen (Tuv/Finneid/Rognan) großer Lag +0210/+0230. \xe6=æ \xf8=ø \xe5=å
SEC_NORWAY_NARVIK3 = [
    (1190, 'Kj\xf8psvik, Tysfjorden', dm(68, 6), dm(16, 22), 0.333, 0.5, -0.1, -0.2, 0.0, -0.1),
    (1191, 'Tran\xf8y, Hamar\xf8y', dm(68, 11), dm(15, 41), 0.333, 0.5, -0.2, -0.2, 0.0, -0.1),
    (1192, 'Tommernes, Sagfjorden', dm(67, 55), dm(15, 53), 0.25, 0.417, -0.3, -0.3, -0.1, -0.1),
    (1193, 'Gr\xf8t\xf8y', dm(67, 50), dm(14, 47), 0.25, 0.417, -0.3, -0.3, 0.0, -0.1),
    (1194, 'Morsvikbotn, Nordfolla', dm(67, 42), dm(15, 50), 0.167, 0.333, -0.4, -0.3, -0.1, 0.0),
    (1195, 'Djupvik, Sorfolda', dm(67, 22), dm(15, 33), 0.167, 0.333, -0.5, -0.4, -0.1, 0.0),
    (1196, 'Helligv\xe6r', dm(67, 24), dm(13, 55), 0.167, 0.333, -0.5, -0.5, -0.2, -0.1),
    (1198, 'Straumen, Saltfjorden', dm(67, 14), dm(14, 37), 0.25, 0.417, -0.7, -0.5, -0.2, -0.1),
    (1199, 'Tuv, Svefjorden', dm(67, 13), dm(14, 38), 1.833, 2.0, -1.8, -1.3, -0.8, -0.3),
    ('1199a', 'Finneid, Skjerstadfjorden', dm(67, 17), dm(15, 30), 1.958, 2.042, -1.5, -1.2, -0.6, -0.2),
    (1200, 'Rognan, Saltdalsfjorden', dm(67, 6), dm(15, 24), 2.0, 2.167, -1.7, -1.2, -0.7, -0.3),
    (1201, 'Tvervik, Beiaren', dm(67, 3), dm(14, 35), 0.417, 0.583, -0.5, -0.4, -0.1, -0.1),
    (1202, 'St\xf8tt', dm(66, 55), dm(13, 27), 0.0, 0.042, -0.6, -0.4, -0.2, 0.0),
    (1203, 'Glomfjord', dm(66, 49), dm(13, 59), -0.167, -0.125, -0.6, -0.4, -0.2, 0.0),
    (1204, 'Indre Kvar\xf8y', dm(66, 29), dm(12, 59), -0.25, -0.208, -0.7, -0.5, -0.3, 0.0),
    (1206, 'Nesna', dm(66, 12), dm(13, 1), -0.25, -0.208, -0.6, -0.5, -0.2, 0.0),
    (1208, 'Sandnessj\xf8en, Alstfjorden', dm(66, 1), dm(12, 38), -0.25, -0.208, -0.5, -0.4, -0.1, 0.0),
    (1209, 'Mosj\xf8en, Vefsenfjorden', dm(65, 51), dm(13, 12), -0.333, -0.292, -0.4, -0.3, -0.1, 0.0),
    (1210, 'Skj\xe6rv\xe6r', dm(65, 46), dm(11, 36), -0.417, -0.375, -0.7, -0.5, -0.3, 0.0),
    (1211, 'Hommelst\xf8, Velfjorden', dm(65, 25), dm(12, 34), -0.417, -0.375, -0.6, -0.6, -0.3, 0.0),
    ('1211a', 'Br\xf8nn\xf8ysund', dm(65, 28), dm(12, 12), -0.5, -0.458, -0.4, -0.4, -0.1, 0.0),
    (1212, 'Borkamo, Tosenfjorden', dm(65, 20), dm(12, 56), -0.583, -0.542, -0.7, -0.5, -0.3, -0.2),
    (1214, 'Kongsmoen, Indre Folla', dm(64, 53), dm(12, 27), -0.333, -0.292, -0.5, -0.4, -0.1, 0.0),
    (1215, 'Namsos, Namsenfjorden', dm(64, 28), dm(11, 30), -0.75, -0.708, -0.7, -0.5, -0.2, 0.0),
    (1216, 'Buholmr\xe5sa', dm(64, 24), dm(10, 28), -0.833, -0.792, -0.7, -0.7, -0.4, 0.0),
    ('1216a', 'Bessaker', dm(64, 15), dm(10, 19), -0.75, -0.708, -0.7, -0.5, -0.2, -0.1),
    (1217, 'Stokksundet, Linesfjorden', dm(64, 2), dm(10, 3), -0.708, -0.875, -0.7, -0.6, -0.3, 0.0),
    (1218, 'Selvnes, Trondheimsfjorden', dm(63, 37), dm(9, 44), -0.917, -0.833, -0.3, -0.4, -0.2, 0.0),
]

# --- Block K: Trøndelag/Nordmøre, Ref NARVIK, ZONE -0100 (Scan_20260616 (16)=S.367 flach) ---
# 1220-1232 NARVIK-ref (ALESUND 1233 = Standardhafen; ab 1233a -> Ålesund-ref, separat).
# Südl. Außenküste: negative ΔT (HW vor Narvik, Tide läuft nordwärts). \xe6=æ \xf8=ø \xe5=å \xc5=Å
SEC_NORWAY_NARVIK4 = [
    (1220, 'Levanger', dm(63, 45), dm(11, 18), -0.583, -0.5, 0.0, -0.2, -0.1, 0.1),
    (1221, 'Steinkjer', dm(64, 1), dm(11, 28), -0.75, -0.667, 0.2, -0.1, 0.1, 0.1),
    (1223, 'Ytre Kvenv\xe6r, Ramsoyfjorden', dm(63, 29), dm(8, 18), -1.167, -1.083, -0.9, -0.7, -0.4, 0.0),
    (1225, 'Vinje\xf8ra, Vinjefjorden', dm(63, 13), dm(8, 59), -1.25, -1.167, -0.9, -0.7, -0.3, 0.0),
    (1227, 'Surna', dm(62, 58), dm(8, 38), -1.25, -1.167, -1.0, -0.7, -0.5, 0.0),
    (1228, 'Sunndals\xf8ra, Sunndalsfjorden', dm(62, 41), dm(8, 33), -1.292, -1.25, -1.2, -0.8, -0.3, 0.0),
    (1229, 'Bj\xf8rnsund', dm(62, 54), dm(6, 49), -1.25, -1.167, -1.2, -0.8, -0.3, -0.2),
    (1230, 'Molde', dm(62, 44), dm(7, 10), -1.292, -1.25, -1.2, -0.9, -0.4, 0.0),
    (1231, '\xc5ndalsnes', dm(62, 34), dm(7, 41), -1.5, -1.417, -1.2, -0.7, -0.3, -0.2),
    (1232, 'Leps\xf8yrevet', dm(62, 35), dm(6, 15), -1.333, -1.25, -1.2, -0.9, -0.3, -0.2),
    # 1233a-1236 (nach ALESUND-Standardhafen) weiter NARVIK-ref (große ΔT, Abschnitt):
    ('1233a', 'Stranda, Norddalsfjorden', dm(62, 19), dm(6, 57), -1.5, -1.417, -1.1, -0.9, -0.4, -0.1),
    (1234, 'Merok, Geirangerfjord', dm(62, 6), dm(7, 13), -1.417, -1.333, -1.2, -0.8, -0.2, -0.2),
    (1235, 'Fyrde', dm(62, 4), dm(6, 19), -1.333, -1.25, -1.2, -0.9, -0.3, -0.2),
    (1236, 'Stattvagen, Stattlandet', dm(62, 12), dm(5, 13), -1.5, -1.417, -1.3, -0.9, -0.3, -0.2),
]

# --- Block L: West-/Sognefjord, Ref BERGEN (Part III), ZONE -0100 (Scan_20260616 (16)=S.367) ---
# Near-cophase mit Bergen (ΔT konstant ~ -0.2h), Innen-Sognefjord verstärkt (Höhendiffs +).
# \xe6=æ \xf8=ø \xe5=å. Maloy 1237 dup.
SEC_NORWAY_BERGEN = [
    (1238, 'Kj\xf8lsdal, Nordfjord', dm(61, 55), dm(5, 38), -0.15, -0.15, 0.4, 0.3, 0.2, 0.1),
    (1239, 'Olden, Nordfjord', dm(61, 51), dm(6, 49), -0.2, -0.2, 0.5, 0.4, 0.2, 0.0),
    (1240, 'Flor\xf8', dm(61, 36), dm(5, 2), -0.067, -0.067, 0.2, 0.2, 0.1, 0.0),
    (1241, 'F\xf8rde, Fordefjorden', dm(61, 28), dm(5, 50), -0.05, -0.05, 0.3, 0.3, 0.2, -0.1),
    (1242, 'Askvoll, Granesund', dm(61, 21), dm(5, 4), -0.15, -0.15, 0.3, 0.3, 0.2, -0.1),
    (1244, 'Nara, Ytre Sula', dm(61, 1), dm(4, 45), -0.183, -0.183, 0.1, 0.1, 0.0, -0.1),
    (1245, 'Rutletangen, Sognefjord', dm(61, 4), dm(5, 11), -0.2, -0.2, 0.3, 0.2, 0.2, -0.1),
    (1246, 'Vadheim, Sognefjord', dm(61, 13), dm(5, 49), -0.2, -0.2, 0.3, 0.2, 0.2, -0.1),
    (1247, 'Vikisogn, Sognefjord', dm(61, 5), dm(6, 35), -0.2, -0.2, 0.2, 0.2, 0.2, -0.1),
    (1248, 'Fl\xe5m, Sognefjord', dm(60, 52), dm(7, 8), -0.217, -0.217, 0.3, 0.3, 0.2, 0.0),
    (1249, 'L\xe6rdals\xf8yri, Sognefjord', dm(61, 6), dm(7, 28), -0.233, -0.233, 0.3, 0.3, 0.2, 0.0),
    (1250, 'Skjolden, Sognefjord', dm(61, 29), dm(7, 36), -0.2, -0.2, 0.3, 0.3, 0.2, 0.0),
    # --- S.368 (Scan 17): weitere BERGEN-ref (cophase, ΔT=Einzelwert) ---
    # Skip ohne Höhendaten: 1252 Eidsfjord, 1266 Engesund, 1268 Fjæra; 1259 Vatlestraumen unsicher; 1267 Leirvik dup.
    (1251, 'Skjerjehamn, Undelandsund', dm(60, 57), dm(4, 58), 0.05, 0.05, 0.2, 0.0, 0.0, -0.1),
    (1253, 'Matre, Masfjord', dm(60, 53), dm(5, 35), -0.183, -0.183, 0.1, 0.0, 0.2, -0.1),
    (1254, 'Kilstraumen, Fensfjord', dm(60, 48), dm(4, 57), 0.183, 0.183, 0.1, 0.1, 0.0, -0.1),
    (1255, 'Alverstraumen, Radsund', dm(60, 35), dm(5, 13), 0.233, 0.233, 0.1, 0.1, 0.2, -0.1),
    (1256, 'Stamneshella, Sorfjord', dm(60, 40), dm(5, 45), -0.05, -0.05, 0.1, 0.1, 0.2, -0.1),
    (1257, 'Blomv\xe5g, Rorsundet', dm(60, 32), dm(4, 53), -0.233, -0.233, 0.0, -0.1, 0.0, -0.1),
    (1260, 'Tysse, Samnangerfjord', dm(60, 24), dm(5, 44), -0.3, -0.3, -0.2, -0.1, 0.0, -0.1),
    (1261, 'Lokksund, Hardangerfjord', dm(60, 3), dm(5, 43), 0.117, 0.117, -0.3, -0.2, 0.0, -0.1),
    (1262, 'Norheimsund, Hardangerfjord', dm(60, 22), dm(6, 9), 0.333, 0.333, -0.2, -0.2, -0.1, -0.1),
    (1263, 'S\xf8rfjord (Odda), Hardangerfjord', dm(60, 4), dm(6, 33), 0.4, 0.4, 0.0, 0.0, 0.0, -0.1),
    (1264, 'Eidfjord, Hardangerfjord', dm(60, 28), dm(7, 4), 0.317, 0.317, 0.0, 0.0, 0.2, -0.1),
    (1265, 'Stolmen', dm(60, 1), dm(5, 5), -0.267, -0.267, -0.2, -0.2, 0.0, -0.1),
    (1269, '\xd8len, Akrafjord', dm(59, 36), dm(5, 48), 0.117, 0.117, -0.3, -0.2, 0.0, -0.1),
    (1270, 'Espev\xe6r, Bomlo', dm(59, 36), dm(5, 10), -0.317, -0.317, -0.5, -0.4, -0.1, -0.1),
]

# (refkey, meridian, country, cal_h, sec_list)
BLOCKS = [
    ('YEKAT', '+03:00 :Europe/Moscow', 'Russia', 0.0, SEC_YEKAT),
    ('KEM', '+03:00 :Europe/Moscow', 'Russia', 0.0, SEC_KEM),
    ('YEKAT', '+03:00 :Europe/Moscow', 'Russia', 0.0, SEC_YEKAT2),
    ('YEKAT', '+03:00 :Europe/Moscow', 'Russia', 0.0, SEC_YEKAT3),
    ('YEKAT', '+03:00 :Europe/Moscow', 'Russia', 0.0, SEC_YEKAT4),
    ('YEKAT', '+01:00 :Europe/Oslo', 'Norway', 0.0, SEC_NORWAY_YEKAT),
    ('NARVIK', '+01:00 :Europe/Oslo', 'Norway', 0.0, SEC_NORWAY_NARVIK),
    ('HAMMERFEST', '+01:00 :Europe/Oslo', 'Norway', 0.0, SEC_NORWAY_HAM),
    ('NARVIK', '+01:00 :Europe/Oslo', 'Norway', 0.0, SEC_NORWAY_NARVIK2),
    ('TROMSO', '+01:00 :Europe/Oslo', 'Norway', 0.0, SEC_NORWAY_TROMSO),
    ('TROMSO', '+01:00 :Europe/Oslo', 'Norway', 0.0, SEC_NORWAY_TROMSO2),
    ('NARVIK', '+01:00 :Europe/Oslo', 'Norway', 0.0, SEC_NORWAY_NARVIK3),
    ('NARVIK', '+01:00 :Europe/Oslo', 'Norway', 0.0, SEC_NORWAY_NARVIK4),
    ('BERGEN', '+01:00 :Europe/Oslo', 'Norway', 0.0, SEC_NORWAY_BERGEN),
]


def transfer(s, refkey, cal=0.0):
    r = REFS[refkey]
    lev, spring, refcon = r['levels'], r['spring'], r['con']
    tHW, tLW = s[4], s[5]
    dHWS, dHWN, dLWN, dLWS = s[6], s[7], s[8], s[9]
    dts = [x for x in (hm(tHW), hm(tLW)) if x is not None]
    dt = sum(dts) / len(dts) + cal       # cal = Referenz-Timing-Kalibrierung (h)
    sec_hws, sec_lws = lev[0] + dHWS, lev[3] + dLWS
    a = (sec_hws - sec_lws) / spring          # Spring-Hub-Verhältnis (robust)
    # Z0 = symmetrischer Mittelpunkt der Stände -> reproduziert HW/LW-Höhen.
    # (NICHT die ATT-ML-Spalte: bei flachwasser-asymm. Häfen wie Kandalaksha läge
    #  HW/LW dann ~0.5 m zu tief, weil die linear skalierten Konst. symmetrisch sind.)
    if dHWN is not None and dLWN is not None:
        z0 = (lev[0] + dHWS + lev[1] + dHWN + lev[2] + dLWN + lev[3] + dLWS) / 4.0
    else:                                      # MHWN/MLWN unvollständig -> Spring-Mittel
        z0 = (sec_hws + sec_lws) / 2.0
    con = {}
    for k, (amp, g) in refcon.items():
        con[k] = (round(a * amp, 4), (g + SPEED[k] * dt) % 360)
    return dt, a, z0, con


REFNAMES = {'YEKAT': 'Ostrov Yekaterininskiy', 'KEM': "Port of Kem'", 'NARVIK': 'Narvik (NP202 Part III)',
            'HAMMERFEST': 'Hammerfest (NP202 Part III)', 'TROMSO': 'Tromso (NP202 Part III)',
            'LODINGEN': 'Lodingen (NP202 Part III)', 'ALESUND': 'Alesund (NP202 Part III)',
            'BERGEN': 'Bergen (NP202 Part III)'}


def block(s, refkey, mer, country, cal=0.0):
    att, name = s[0], s[1]
    dt, a, z0, con = transfer(s, refkey, cal)
    refname = REFNAMES[refkey]
    ml = s[10] if len(s) > 10 else None
    asym = f'; ML={ml} (shallow-water asymmetry, HW/LW prioritised over MSL)' \
        if (ml is not None and abs(z0 - ml) > 0.25) else ''
    out = ['# BEGIN HOT COMMENTS',
           f'# country: {country}',
           '# source: ADMIRALTY Tide Tables Vol.2 (NP202), Part II Secondary Port',
           f'# att_number: {att}',
           f'# note: Transfer from {refname} (dt={dt:+.2f}h, scale={a:.3f}); approximate{asym}',
           '# coord_source: NP202 Part II',
           '# date_imported: 20260616',
           '# datum: Chart Datum (Z0 = mean level above CD)',
           '# confidence: 2',
           '# !units: meters',
           f'# !longitude: {s[3]:.4f}',
           f'# !latitude: {s[2]:.4f}',
           f'{name} (NP202 {att}) Tide',
           mer,
           f'{z0:.4f} meters']
    for c in ORDER:
        if c in con:
            amp, g = con[c]
            out.append(f'{c:<16}{amp:.4f}  {g:.2f}')
        else:
            out.append('x 0 0')
    return out


def main():
    for k, r in REFS.items():
        print(f'Referenz {k}: {len(r["con"])} Konst. (M2={r["con"]["M2"]}, spring={r["spring"]:.2f})')
    inv = load_inventory()
    lines = list(HEADER)
    built = skipped = total = 0
    for refkey, mer, country, cal, sec_list in BLOCKS:
        print(f'--- Block {refkey} / {country} / {mer} / cal={cal:+.2f}h ---')
        for s in sec_list:
            total += 1
            if not is_gap(s[2], s[3], inv):
                print(f'  SKIP (Duplikat) {s[0]} {s[1]}')
                skipped += 1
                continue
            dt, a, z0, _ = transfer(s, refkey, cal)
            mhws = REFS[refkey]['levels'][0] + s[6]
            print(f'  {str(s[0]):5} {s[1][:30]:30} dt={dt:+.2f}h scale={a:.3f} Z0={z0:.2f} MHWS={mhws:.1f}')
            lines += block(s, refkey, mer, country, cal)
            built += 1
    lines.append('# END')
    print(f'  ({built} gebaut, {skipped} Duplikate übersprungen, {total} gesamt)')
    with open(OUT, 'w', encoding='iso-8859-1') as f:
        f.write('\n'.join(lines) + '\n')
    print(f'Geschrieben: {OUT} | {built} Stationen')


if __name__ == '__main__':
    main()
