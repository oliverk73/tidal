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


def read_reference(name):
    """Vollen Konstituenten-Satz eines Standardhafens aus Classic 1997 lesen."""
    lines = open(CLASSIC, encoding='iso-8859-1').read().splitlines()
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
REFS = {
    'YEKAT': dict(classic='Yekaterininskaya, Russia', levels=(3.7, 3.0, 1.3, 0.5)),
    'KEM':   dict(classic='Port Kem, Russia',         levels=(1.83, 1.54, 0.66, 0.37)),
}
for _k, _r in REFS.items():
    _r['con'] = read_reference(_r['classic'])
    _r['spring'] = _r['levels'][0] - _r['levels'][3]


def hm(s):
    """'+0135' -> +1.5833 h ; '-0452' -> -4.8667 h ; None -> None."""
    if s is None:
        return None
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

BLOCKS = [('YEKAT', SEC_YEKAT), ('KEM', SEC_KEM)]


def transfer(s, refkey):
    r = REFS[refkey]
    lev, spring, refcon = r['levels'], r['spring'], r['con']
    tHW, tLW = s[4], s[5]
    dHWS, dHWN, dLWN, dLWS = s[6], s[7], s[8], s[9]
    dts = [x for x in (hm(tHW), hm(tLW)) if x is not None]
    dt = sum(dts) / len(dts)
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


def block(s, refkey):
    att, name = s[0], s[1]
    dt, a, z0, con = transfer(s, refkey)
    refname = 'Ostrov Yekaterininskiy' if refkey == 'YEKAT' else "Port of Kem'"
    ml = s[10] if len(s) > 10 else None
    asym = f'; ML={ml} (shallow-water asymmetry, HW/LW prioritised over MSL)' \
        if (ml is not None and abs(z0 - ml) > 0.25) else ''
    out = ['# BEGIN HOT COMMENTS',
           '# country: Russia',
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
           '+03:00 :Europe/Moscow',
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
    for refkey, sec_list in BLOCKS:
        print(f'--- Block {refkey} ---')
        for s in sec_list:
            total += 1
            if not is_gap(s[2], s[3], inv):
                print(f'  SKIP (Duplikat) {s[0]} {s[1]}')
                skipped += 1
                continue
            dt, a, z0, _ = transfer(s, refkey)
            mhws = REFS[refkey]['levels'][0] + s[6]
            print(f'  {str(s[0]):5} {s[1][:32]:32} dt={dt:+.2f}h scale={a:.3f} Z0={z0:.2f} MHWS={mhws:.1f}')
            lines += block(s, refkey)
            built += 1
    lines.append('# END')
    print(f'  ({built} gebaut, {skipped} Duplikate übersprungen, {total} gesamt)')
    with open(OUT, 'w', encoding='iso-8859-1') as f:
        f.write('\n'.join(lines) + '\n')
    print(f'Geschrieben: {OUT} | {built} Stationen')


if __name__ == '__main__':
    main()
