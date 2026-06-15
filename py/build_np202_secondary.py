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
import os, re

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


def read_reference():
    """Vollen Konstituenten-Satz von 'Yekaterininskaya, Russia' (Classic) lesen."""
    lines = open(CLASSIC, encoding='iso-8859-1').read().splitlines()
    i = next(k for k, l in enumerate(lines) if l.startswith('Yekaterininskaya, Russia'))
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


REF = read_reference()
# Referenz-Pegelstände (ATT Ostrov Yekaterininskiy, MHWS/MHWN/MLWN/MLWS)
REF_LEVELS = (3.7, 3.0, 1.3, 0.5)
REF_SPRING = REF_LEVELS[0] - REF_LEVELS[3]   # 3.2 m


def hm(s):
    """'+0135' -> +1.5833 h ; '-0452' -> -4.8667 h ; None -> None."""
    if s is None:
        return None
    sign = -1 if s[0] == '-' else 1
    s = s.lstrip('+-')
    return sign * (int(s[:-2]) + int(s[-2:]) / 60.0)


def dm(d, m):
    return d + m / 60.0


# (att, name, lat, lon, dT_HW, dT_LW, dMHWS,dMHWN,dMLWN,dMLWS)
SEC = [
    (1009, 'Guba Belushya, Novaya Zemlya', dm(71, 32), dm(52, 19), '+0135', '+0120', -3.2, -2.6, -1.2, -0.4),
    (1010, 'Guba Nekhvatova, Novaya Zemlya', dm(71, 16), dm(53, 30), '+0143', None, -3.4, -2.8, -1.2, -0.4),
    (1011, 'Guba Kamyenka, Kara Strait', dm(70, 36), dm(57, 27), '+0735', '+0725', -3.0, -2.5, -1.0, -0.4),
    (1012, 'Guba Dolgaya, Kara Strait', dm(70, 15), dm(58, 43), '-0452', '-0656', -3.2, -2.6, -1.1, -0.4),
    (1013, 'Bukhta Varneka, Yugorski Strait', dm(69, 42), dm(60, 4), '-0213', '-0224', -2.9, -2.4, -1.0, -0.3),
    (1014, 'Ostrov Sokoliy, Yugorski Strait', dm(69, 50), dm(60, 44), '-0430', '-0440', -2.9, -2.4, -1.0, -0.3),
    (1015, 'Khabarovo, Yugorski Strait', dm(69, 39), dm(60, 25), '-0330', '-0340', -3.1, -2.5, -1.1, -0.4),
]


def transfer(s):
    att, name, lat, lon, tHW, tLW, dHWS, dHWN, dLWN, dLWS = s
    dts = [x for x in (hm(tHW), hm(tLW)) if x is not None]
    dt = sum(dts) / len(dts)
    sec = (REF_LEVELS[0] + dHWS, REF_LEVELS[1] + dHWN, REF_LEVELS[2] + dLWN, REF_LEVELS[3] + dLWS)
    a = (sec[0] - sec[3]) / REF_SPRING
    z0 = sum(sec) / 4.0
    con = {}
    for k, (amp, g) in REF.items():
        con[k] = (round(a * amp, 4), (g + SPEED[k] * dt) % 360)
    return dt, a, z0, con


def block(s):
    att, name = s[0], s[1]
    dt, a, z0, con = transfer(s)
    out = ['# BEGIN HOT COMMENTS',
           '# country: Russia',
           '# source: ADMIRALTY Tide Tables Vol.2 (NP202), Part II Secondary Port',
           f'# att_number: {att}',
           f'# note: Transfer from Ostrov Yekaterininskiy (dt={dt:+.2f}h, scale={a:.3f}); approximate',
           '# coord_source: NP202 Part II',
           '# date_imported: 20260615',
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
    print(f'Referenz-Konstituenten: {len(REF)} (M2={REF["M2"]})')
    lines = list(HEADER)
    for s in SEC:
        dt, a, z0, _ = transfer(s)
        print(f'  {s[0]} {s[1][:34]:34} dt={dt:+.2f}h scale={a:.3f} Z0={z0:.2f} '
              f'MHWS={REF_LEVELS[0]+s[6]:.1f}')
        lines += block(s)
    lines.append('# END')
    with open(OUT, 'w', encoding='iso-8859-1') as f:
        f.write('\n'.join(lines) + '\n')
    print(f'Geschrieben: {OUT} | {len(SEC)} Stationen')


if __name__ == '__main__':
    main()
