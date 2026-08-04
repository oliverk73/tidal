#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Die beiden letzten Luecken des NP203 schliessen: 4322 Karachi (Entrance)
und 4276A Abadan.

4322 KARACHI (ENTRANCE) -- Standardhafen, Bezugshafen fuer 4322a bis 4322e,
fehlte in der ATT-Sammlung komplett. Unter "Karachi, Pakistan" steckt er zwar
in classic_original, TICON und UTide, aber ohne att_number und nicht aus dem
Buch. Konstanten von Part III S.247 (2015) abgelesen, Position aus Part II
S.234. Kommt in die Standardhafen-Datei.

4276A ABADAN -- die Ausgabe 2015 fuehrt ihn als Standardhafen (Table V Part 1:
2.0 / 1.6 / 0.6 / 0.6, MSL 1.2, HAT 2.6), druckt aber KEINE harmonischen
Konstanten: Part III springt von 4271 Al Basrah zu 4276b Khowr-e Musa
Approaches. Die Ausgabe 2002 fuehrt ihn dagegen noch als Sekundaerhafen
(Nr. 4270) mit Differenzen auf 4268 Shatt al Arab Outer Bar:

    4270 Abadan   30 20 N  48 16 E   +0250 +0345   -1.0 -0.8 -0.7 +0.2   ML 1.22

Probe: auf die publizierten Pegel des Bezugshafens angewendet ergibt das
3.0-1.0=2.0, 2.4-0.8=1.6, 1.3-0.7=0.6, 0.4+0.2=0.6 -- exakt die Pegel, die die
Ausgabe 2015 fuer Abadan in Table V druckt. Die beiden Ausgaben sind sich also
einig, und der Transfer reproduziert die publizierten Werte.

Beide Blocks liegen in derselben Zone -0300 (Abadan steht 2002 noch im
irakischen Block), es gibt also keinen Zonensprung.

Aufruf: venv/bin/python py/add_np203_karachi_abadan.py
"""
from __future__ import annotations
import importlib.util
import os
import re
import shutil
import time

HARM = '/home/oliver/weather/harmonics'
STD = f'{HARM}/att/harmonics_att_np203.txt'
SEC = f'{HARM}/att/harmonics_att_np203_secondary.txt'
BACKUP = f'{HARM}/backup'

spec = importlib.util.spec_from_file_location(
    'rb', '/home/oliver/weather/py/rebuild_np203_transfer.py')
rb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rb)


def inferenz(m2, s2):
    """wie py/fix_np203_part3_gegen_2015.py -- Phasendifferenz normiert."""
    (am, gm), (as_, gs) = m2, s2
    d = (gs - gm + 180) % 360 - 180
    return (round(0.19 * am, 4), round((gm - 0.536 * d) % 360, 2)), \
           (round(0.27 * as_, 4), round(gs % 360, 2))


def lies_block(pfad, att):
    """Konstanten eines vorhandenen Eintrags holen."""
    L = open(pfad, encoding='iso-8859-1').read().split('\n')
    for i, l in enumerate(L):
        if l.strip() == f'# att_number: {att}':
            a = max(j for j in range(i) if L[j].startswith('# BEGIN HOT COMMENTS'))
            b = next(j for j in range(i + 1, len(L))
                     if L[j].startswith('# BEGIN HOT COMMENTS'))
            con = {}
            for l2 in L[a:b]:
                m = re.match(r'^(\w+)\s+([\d.]+)\s+([\d.]+)\s*$', l2)
                if m:
                    con[m.group(1)] = (float(m.group(2)), float(m.group(3)))
            return con
    raise KeyError(att)


def block(name, land, att, note, lat, lon, mer, tz, z0, con, order, conf):
    b = ['# BEGIN HOT COMMENTS',
         f'# country: {land}',
         '# source: ADMIRALTY Tide Tables Vol.3 (NP203)']
    b += [f'# att_number: {att}']
    b += [f'# note: {n}' for n in note]
    b += [f'# date_imported: {time.strftime("%Y%m%d")}',
          '# datum: Chart Datum (Z0 = mean level above CD)',
          f'# confidence: {conf}',
          '# !units: meters',
          f'# !longitude: {lon:.4f}',
          f'# !latitude: {lat:.4f}',
          name,
          f'{mer} :{tz}',
          f'{z0:.4f} meters']
    for c in order:
        b.append(f'{c:<15s} {con[c][0]:.4f}  {con[c][1]:.2f}'
                 if c in con else 'x 0 0')
    return b


def einfuegen(pfad, neu, vor_att):
    """Block vor dem Eintrag mit att-Nummer vor_att einsetzen (Buchreihenfolge)."""
    L = open(pfad, encoding='iso-8859-1').read().split('\n')
    i = next(j for j, l in enumerate(L) if l.strip() == f'# att_number: {vor_att}')
    a = max(j for j in range(i) if L[j].startswith('# BEGIN HOT COMMENTS'))
    L[a:a] = neu
    stamp = time.strftime('%Y%m%d')
    shutil.copy2(pfad, f'{BACKUP}/{os.path.basename(pfad)[:-4]}_pre_luecken_{stamp}.txt')
    open(pfad, 'w', encoding='iso-8859-1').write('\n'.join(L))
    os.chmod(pfad, 0o600)


def main():
    ORDER = rb.order(open(STD, encoding='iso-8859-1').read().split('\n'))

    # ---------- 4322 Karachi (Entrance) ----------
    con = {'M2': (0.80, 305.0), 'S2': (0.28, 344.0),
           'K1': (0.40, 58.0), 'O1': (0.21, 45.0)}
    con['N2'], con['K2'] = inferenz(con['M2'], con['S2'])
    kar = block('Karachi (Entrance), Pakistan', 'Pakistan', '4322',
                ['NP203 Part III S.247 (2015), Meridian +05:00. Stationseigene Konstanten.',
                 'Position aus Part II S.234 (24 48 N, 66 58 E). N2/K2 inferiert.',
                 f'{time.strftime("%Y%m%d")} neu angelegt -- der Bezugshafen der Gruppe',
                 '4322a bis 4322e fehlte in der ATT-Sammlung. Unter "Karachi, Pakistan"',
                 'steht er auch in classic_original, TICON und UTide, dort aber ohne',
                 'att_number und nicht aus dem Buch.'],
                24 + 48 / 60, 66 + 58 / 60, '+05:00', 'Asia/Karachi', 1.67,
                con, ORDER, 7)
    if not any(l.strip() == '# att_number: 4322'
               for l in open(STD, encoding='iso-8859-1')):
        einfuegen(STD, kar, '4325')

    # ---------- 4276A Abadan ----------
    ref = lies_block(STD, '4268')                     # Shatt al Arab Outer Bar
    r = rb.transfer(ref,
                    pegel=(3.0, 2.4, 1.3, 0.4),       # publiziert, Table V
                    h=(-1.0, -0.8, -0.7, +0.2),       # Part II 2002, Nr. 4270
                    t=(170, 225),                     # +0250 / +0345
                    dz=0.0,                           # beide Zone -0300
                    ml=1.22)
    aba = block('Abadan, Iran', 'Iran', '4276A',
                ['NP203 Part-II-Transfer von 4268 Shatt al Arab Outer Bar.',
                 'Die Ausgabe 2015 fuehrt Abadan als Standardhafen (Table V Part 1),',
                 'druckt aber keine Konstanten -- Part III springt von 4271 zu 4276b.',
                 'Differenzen daher aus der Ausgabe 2002, wo er noch Sekundaerhafen',
                 'Nr. 4270 war: +0250 / +0345, -1.0 -0.8 -0.7 +0.2, ML 1.22.',
                 'Probe: auf die Pegel des Bezugshafens angewendet ergibt das',
                 '2.0 / 1.6 / 0.6 / 0.6 -- genau die Pegel der Ausgabe 2015.',
                 f'fS={r["fS"]:.3f} fN={r["fN"]:.3f} dt={r["dt"]*60:.0f} min.'],
                30 + 20 / 60, 48 + 16 / 60, '+03:00', 'Asia/Tehran', 1.22,
                r['con'], ORDER, 5)
    einfuegen(SEC, aba, '4276b')   # 4277 ist Standardhafen, steht nicht in dieser Datei

    print('4322 Karachi (Entrance):', {k: con[k] for k in ('M2', 'S2', 'K1', 'O1')})
    print(f'4276A Abadan: fS={r["fS"]:.3f} fN={r["fN"]:.3f} dt={r["dt"]*60:.0f} min')
    print('  M2', r['con']['M2'], ' S2', r['con']['S2'],
          ' K1', r['con']['K1'], ' O1', r['con']['O1'])


if __name__ == '__main__':
    main()
