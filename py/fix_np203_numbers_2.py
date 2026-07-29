#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Korrigiert att-Nummern in harmonics_att_np203_secondary.txt.

Am 20260729 aus den Scans belegt (Part II S.228/229, Part III S.242/243).
Die Nummern in der Datei waren gegenueber dem Buch um eine Zeile verschoben --
dieselbe Fehlerklasse wie am 20260728 im Golf. Namen, Koordinaten und Werte
bleiben unberuehrt, nur die Nummer wird richtiggestellt.

  Rotes Meer (Part II S.228)
    4099 -> 4100   Hurghada (Al Ghardaqah)   Buch: 4100
    4107 -> 4110   Zafarana                  Buch: 4110 Ra's Za'faranah
    4116 -> 4115   Sharm Ash Shaykh          Buch: 4115
    4126 -> 4123   Umm Qusur                 Buch: 4123
    4127 -> 4125   Nu'man                    Buch: 4125 Sharm an Nu'man
    4128 -> 4127   Mardunah                  Buch: 4127
    4133 -> 4135   Jeddah (Ghubbat Asharah)  Buch: 4135 (4133 ist RABIGH, Standardhafen)

  Oman (Part II S.229)
    4171  -> 4170b  Al Lakbi                 Buch: 4170b (4171 ist Ras al Madrakah)
    4183  -> 4182e  Dibab
    4184  -> 4183   Dhagmar
    4185  -> 4184   Quryat
    4185a -> 4185   Bandar Khayran
    4186  -> 4185a  Bandar Jissah            (Buch 4186 ist Khawr Masqat, fehlt bei uns)

Aufruf: python3 py/fix_np203_numbers_2.py [--write]
"""
from __future__ import annotations
import os
import re
import shutil
import sys
from datetime import datetime

TXT = '/home/oliver/weather/harmonics/att/harmonics_att_np203_secondary.txt'
HARM = '/home/oliver/weather/harmonics'

RENUM = {
    '4099': ('4100',  'Hurghada'),
    '4107': ('4110',  "Ra's Za'faranah"),
    '4116': ('4115',  'Sharm Ash Shaykh'),
    '4126': ('4123',  'Umm Qusur'),
    '4127': ('4125',  "Sharm an Nu'man"),
    '4128': ('4127',  'Mardunah'),
    '4133': ('4135',  'Jeddah (Ghubbat Asharah)'),
    '4171': ('4170b', 'Al Lakbi'),
    '4183': ('4182e', 'Dibab'),
    '4184': ('4183',  'Dhagmar'),
    '4185': ('4184',  'Quryat'),
    '4185a': ('4185', 'Bandar Khayran'),
    '4186': ('4185a', 'Bandar Jissah'),
}


def main():
    write = '--write' in sys.argv
    L = open(TXT, encoding='iso-8859-1').read().split('\n')

    # Blockgrenzen einmal ueber den Ausgangszustand bestimmen -- so kann keine
    # Zwischenkollision entstehen, wenn zwei Nummern die Plaetze tauschen.
    blocks = {}
    att = None
    for i, l in enumerate(L):
        if l.startswith('# att_number:'):
            att, ai = l.split(': ')[1].strip(), i
        elif re.match(r'^[+-]\d\d:\d\d :', l) and att:
            blocks[att] = (ai, L[i - 1].strip())
            att = None

    done = 0
    # Von hinten nach vorn, sonst verschiebt die eingefuegte Notizzeile
    # die Indizes aller noch folgenden Bloecke.
    for old, (new, book) in sorted(RENUM.items(), key=lambda kv: -blocks.get(kv[0], (0,))[0]):
        if old not in blocks:
            print(f'{old:6s} nicht in der Datei -- uebersprungen'); continue
        if new in blocks and new not in RENUM:
            print(f'{old:6s} -> {new}: Ziel ist bereits belegt ({blocks[new][1]}) -- ABBRUCH')
            return
        ai, name = blocks[old]
        print(f'{old:6s} -> {new:6s}  {name[:44]:44s} Buch: {book}')
        if write:
            L[ai] = f'# att_number: {new}'
            j = next(k for k in range(ai, len(L)) if L[k].startswith('# date_imported:'))
            L[j:j] = [f'# note: Nummer {datetime.now():%Y%m%d} nach Scan korrigiert '
                      f'({old} -> {new}, Buch: {book}).']
        done += 1

    if write:
        shutil.copy(TXT, f'{HARM}/backup/harmonics_att_np203_secondary_pre_renum_{datetime.now():%Y%m%d}.txt')
        open(TXT, 'w', encoding='iso-8859-1').write('\n'.join(L))
        os.chmod(TXT, 0o600)
        print(f'\n{done} Nummern korrigiert.')
    else:
        print(f'\n{done} Nummern. (Dry-run. --write zum Schreiben.)')


if __name__ == '__main__':
    main()
