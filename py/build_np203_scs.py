#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""NP203 Ausgabe 2002, Suedchinesisches Meer und Indonesien -> XTide-Harmonics.

Die Ausgabe 2015 des Bandes reicht nur bis Myanmar (att 4491). Die Ausgabe 2002
hiess noch "Indian Ocean AND SOUTH CHINA SEA" und fuehrt weiter bis Irian Jaya,
Vietnam und die Paracel-Inseln. Fuer diesen ganzen Bereich hatten wir bisher
keine einzige Station.

Quellen (beide von den Scanseiten abgelesen, die OCR ist dort unbrauchbar):
  harmonics/help/np203_2002_part3_scs.tsv       Konstanten, Buchseiten 322-338
  harmonics/help/np203_2002_part2_scs_pos.tsv   Position und ML, Buchseiten 281-309

Part III gibt M2, S2, K1, O1 und die Flachwasserkorrekturen f4/F4 und f6/F6;
letztere werden zu M4 und M6. N2 und K2 werden wie im uebrigen NP203 abgeleitet:
  N2 = 0.19 * M2, g = g_M2 - 0.536 * d   mit d = (g_S2 - g_M2) auf (-180,180]
  K2 = 0.27 * S2, g = g_S2
Die Normierung von d ist wichtig -- ohne sie liegt N2 bei Nulldurchgang 167 Grad
daneben (siehe py/fix_np203_part3_gegen_2015.py).

Aufruf: venv/bin/python py/build_np203_scs.py
"""
from __future__ import annotations
import os
import re

HARM = '/home/oliver/weather/harmonics'
LIT = f'{HARM}/classic/harmonics_literature.txt'
P3 = f'{HARM}/help/np203_2002_part3_scs.tsv'
P2 = f'{HARM}/help/np203_2002_part2_scs_pos.tsv'
OUT = f'{HARM}/att/harmonics_att_np203_scs.txt'

# att-Bereich -> (Land, IANA-Zone). Die Grenzen folgen den Laenderueberschriften
# der Buchseiten; die Buchzone steht ohnehin je Station in der TSV.
LAND = [
    (4495, 4517, 'Bangladesh', 'Asia/Dhaka'),
    (4520, 4595, 'Myanmar', 'Asia/Yangon'),
    (4597, 4625, 'India', 'Asia/Kolkata'),          # Andamanen und Nikobaren
    (4628, 4628, 'Australia', 'Indian/Cocos'),
    (4629, 4629, 'Australia', 'Indian/Christmas'),
    (4630, 4649, 'Thailand', 'Asia/Bangkok'),
    (4650, 4739, 'Malaysia', 'Asia/Kuala_Lumpur'),
    (4740, 4763, 'Indonesia', 'Asia/Jakarta'),
    (4764, 4876, 'Indonesia', 'Asia/Jakarta'),
    (4879, 4911, 'Malaysia', 'Asia/Kuala_Lumpur'),
    (4917, 4918, 'Spratly and Scarborough', 'Asia/Manila'),
    (4920, 5095, 'Philippines', 'Asia/Manila'),
    (5097, 5137, 'Malaysia', 'Asia/Kuching'),
    (5138, 5143, 'Brunei', 'Asia/Brunei'),
    (5144, 5176, 'Malaysia', 'Asia/Kuching'),
    (5177, 5542, 'Indonesia', None),                # Zone entscheidet, s.u.
    (6851, 6896, 'Thailand', 'Asia/Bangkok'),
    (6900, 6903, 'Cambodia', 'Asia/Phnom_Penh'),
    (6906, 7015, 'Vietnam', 'Asia/Ho_Chi_Minh'),
    (7050, 7050, 'Paracel Islands', 'Asia/Shanghai'),
]
# Singapur haengt mitten im malaiischen Block
SINGAPUR = {'4714', '4716', '4717', '4718', '4718b', '4718c', '4719', '4725'}
# Indonesien nach Buchzone
IDZONE = {'-0700': 'Asia/Jakarta', '-0800': 'Asia/Makassar', '-0900': 'Asia/Jayapura'}


def kopf():
    """Kopfteil und Konstituentenreihenfolge aus der Klassik-Datei."""
    lines = open(LIT, encoding='iso-8859-1').read().splitlines()
    end = max(i for i, l in enumerate(lines) if 'End congen output' in l)
    order, in_s = [], False
    for l in lines:
        if l.startswith('# Constituent speeds'):
            in_s = True
            continue
        if in_s:
            if l.startswith('# Starting year') or l.startswith('*END*'):
                break
            m = re.match(r'^(\S+)\s+([\d.]+)\s*$', l.strip())
            if m:
                order.append(m.group(1))
    return lines[:end + 1], order


def tsv(pfad):
    for l in open(pfad, encoding='utf-8'):
        if l.startswith('#') or not l.strip():
            continue
        yield l.rstrip('\n').split('\t')


def land_zone(att, zone):
    n = int(re.match(r'\d+', att).group())
    if att in SINGAPUR:
        return 'Singapore', 'Asia/Singapore'
    for a, b, land, tz in LAND:
        if a <= n <= b:
            return land, (tz or IDZONE[zone])
    raise KeyError(att)


def inferenz(m2, s2):
    (am, gm), (as_, gs) = m2, s2
    d = (gs - gm + 180) % 360 - 180
    return (0.19 * am, (gm - 0.536 * d) % 360), (0.27 * as_, gs % 360)


def main():
    HEADER, ORDER = kopf()
    pos = {r[0]: r for r in tsv(P2)}

    bloecke, ohne_z0 = [], []
    for r in tsv(P3):
        att, name, zone, z0 = r[0], r[1], r[2], r[3]
        p = pos[att]
        lat = (int(p[1]) + int(p[2]) / 60.0) * (-1 if p[3] == 'S' else 1)
        lon = (int(p[4]) + int(p[5]) / 60.0) * (-1 if p[6] == 'W' else 1)
        if z0 == 'w':
            if p[7] == '-':
                ohne_z0.append(att)
                continue
            z0 = p[7]
        z0 = float(z0)

        con = {}
        for k, gi, hi in (('M2', 4, 5), ('S2', 6, 7), ('K1', 8, 9), ('O1', 10, 11)):
            if r[gi] != '-' and float(r[hi]) > 0:
                con[k] = (float(r[hi]), float(r[gi]))
        for k, gi, hi in (('M4', 12, 13), ('M6', 14, 15)):
            if r[gi] != '-':
                con[k] = (float(r[hi]), float(r[gi]))
        if 'M2' in con and 'S2' in con:
            con['N2'], con['K2'] = inferenz(con['M2'], con['S2'])

        land, tz = land_zone(att, zone)
        mer = f'{-int(zone[:3]):+03d}:{zone[3:]}'   # -0700 -> +07:00
        b = ['# BEGIN HOT COMMENTS',
             f'# country: {land}',
             '# source: ADMIRALTY Tide Tables Vol.3 (NP203, Ausgabe 2002), Simplified Harmonic Method',
             f'# att_number: {att}',
             f'# note: NP203 Part III (2002), Zone {zone}. Die Ausgabe 2015 fuehrt dieses',
             '# note: Gebiet nicht mehr -- der Band hiess 2002 noch "Indian Ocean and South',
             '# note: China Sea". Position und ML aus Part II desselben Bandes.',
             '# note: N2/K2 inferiert.' + (' M4/M6 aus den S.W.-Korrekturen.' if 'M4' in con else ''),
             '# date_imported: 20260802',
             '# datum: Chart Datum (Z0 = mean level above CD)',
             '# confidence: 6',
             '# !units: meters',
             f'# !longitude: {lon:.4f}',
             f'# !latitude: {lat:.4f}',
             f'{name}, {land}' if not name.endswith(land) else name,
             f'{mer} :{tz}',
             f'{z0:.4f} meters']
        for c in ORDER:
            if c in con:
                b.append(f'{c:<15s} {con[c][0]:.4f}  {con[c][1]:.2f}')
            else:
                b.append('x 0 0')
        bloecke.append(b)

    txt = '\n'.join(HEADER) + '\n' + '\n'.join('\n'.join(b) for b in bloecke) + '\n'
    open(OUT, 'w', encoding='iso-8859-1').write(txt)
    os.chmod(OUT, 0o600)
    print(f'{len(bloecke)} Stationen -> {OUT}')
    if ohne_z0:
        print('ohne ML, uebersprungen:', ohne_z0)


if __name__ == '__main__':
    main()
