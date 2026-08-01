#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Legt Stationen an, die in ATT NP203 stehen, aber in keiner unserer Dateien.

Konstanten aus Part III (stationseigen), Position aus Part II. Kein Transfer noetig.
Am 20260728 aus den Scans gelesen:

  4208a Khawr Ghurabi   Part II S.230: 24 49 N / 54 43 E, ML 0.88
                        Part III S.244: M2 008/0.36 S2 072/0.14 K1 164/0.26 O1 115/0.13
  4215  Zaqqum Oilfield Part II S.230: 24 51 N / 53 31 E, ML 1.2
        (Platform Zws)  Part III S.244: M2 016/0.26 S2 067/0.12 K1 153/0.34 O1 100/0.18

Zaqqum liess sich aus Part II nicht bauen: Die Zeile hat weder Zeit- noch
Hochwasserdifferenz (nur MLLW +0.3), der Transfer verwirft sie deshalb. Mit
Part III ist sie vollstaendig.

Aufruf: python3 py/add_np203_tablev_new.py [--write]
"""
from __future__ import annotations
import os
import re
import shutil
import sys
from datetime import datetime

TXT = '/home/oliver/weather/harmonics/att/harmonics_att_np203_secondary.txt'
HARM = '/home/oliver/weather/harmonics'

NEU = [
    dict(att='4208a', name='Khawr Ghurabi, United Arab Emirates', country='United Arab Emirates',
         lat=24 + 49 / 60, lon=54 + 43 / 60, ml=0.88, mer='+04:00', tz='Asia/Dubai',
         con={'M2': (0.36, 8), 'S2': (0.14, 72), 'K1': (0.26, 164), 'O1': (0.13, 115)},
         p3=244, p2=230, before="Khawr Sa'diyat, United Arab Emirates"),
    dict(att='4215', name='Zaqqum Oilfield (Platform Zws), United Arab Emirates',
         country='United Arab Emirates',
         lat=24 + 51 / 60, lon=53 + 31 / 60, ml=1.20, mer='+04:00', tz='Asia/Dubai',
         con={'M2': (0.26, 16), 'S2': (0.12, 67), 'K1': (0.34, 153), 'O1': (0.18, 100)},
         p3=244, p2=230, before='Zirku, United Arab Emirates'),
    # 20260729: Part III S.243 / Part II S.229. Lag zwischen Sidab (4185b) und
    # Port Sultan Qaboos (4186a) und fehlte in der Sammlung ganz.
    dict(att='4186', name='Khawr Masqat, Oman', country='Oman',
         lat=23 + 37 / 60, lon=58 + 36 / 60, ml=1.80, mer='+04:00', tz='Asia/Muscat',
         con={'M2': (0.61, 277), 'S2': (0.23, 312), 'K1': (0.36, 43), 'O1': (0.20, 38)},
         p3=243, p2=229, before='Mina Al Fahal, Oman'),
]


def order(L):
    i = next(k for k, l in enumerate(L) if l.startswith('# Constituent speeds'))
    out = []
    for l in L[i:]:
        m = re.match(r'^(\S+)\s+[\d.]+\s*$', l)
        if m:
            out.append(m.group(1))
        elif out and l.startswith('#'):
            break
    return out


def block(s, ORDER):
    con = dict(s['con'])
    aM2, gM2 = con['M2']; aS2, gS2 = con['S2']
    con['N2'] = (round(0.19 * aM2, 4), (gM2 - 0.536 * (gS2 - gM2)) % 360)
    con['K2'] = (round(0.27 * aS2, 4), gS2 % 360)
    out = ['# BEGIN HOT COMMENTS', f'# country: {s["country"]}',
           '# source: ADMIRALTY Tide Tables Vol.3 (NP203), Table V (Part III)',
           f'# att_number: {s["att"]}',
           f'# note: NP203 Part III S.{s["p3"]} (2015), Meridian {s["mer"]}. Stationseigene Konstanten.',
           f'# note: Position aus Part II S.{s["p2"]}. N2/K2 inferiert.',
           f'# note: {datetime.now():%Y%m%d} neu angelegt -- Station fehlte in der Sammlung.',
           f'# date_imported: {datetime.now():%Y%m%d}',
           '# datum: Chart Datum (Z0 = mean level above CD)',
           '# confidence: 7', '# !units: meters',
           f'# !longitude: {s["lon"]:.4f}', f'# !latitude: {s["lat"]:.4f}',
           s['name'], f'{s["mer"]} :{s["tz"]}', f'{s["ml"]:.4f} meters']
    for c in ORDER:
        out.append(f'{c:<16}{con[c][0]:.4f}  {con[c][1]:.2f}' if c in con else 'x 0 0')
    return out


def main():
    write = '--write' in sys.argv
    L = open(TXT, encoding='iso-8859-1').read().split('\n')
    ORDER = order(L)
    for s in NEU:
        if s['name'] in L:
            print(f'{s["att"]}: {s["name"]} steht bereits in der Datei.'); continue
        if s['before'] not in L:
            print(f'{s["att"]}: Ankerstation "{s["before"]}" nicht gefunden.'); continue
        blk = block(s, ORDER)
        i = L.index(s['before'])
        start = max(k for k in range(i) if L[k] == '# BEGIN HOT COMMENTS')
        if write:
            L[start:start] = blk
        print(f'{s["att"]:6s} {s["name"][:44]:44s} {s["lat"]:.4f}/{s["lon"]:.4f}  Z0 {s["ml"]:.2f}  '
              f'M2 {s["con"]["M2"][0]}@{s["con"]["M2"][1]}  vor "{s["before"][:24]}"')
    if write:
        shutil.copy(TXT, f'{HARM}/backup/harmonics_att_np203_secondary_pre_neu_{datetime.now():%Y%m%d}.txt')
        open(TXT, 'w', encoding='iso-8859-1').write('\n'.join(L))
        os.chmod(TXT, 0o600)
        print(f'\nGeschrieben. Stationen: {sum(1 for l in L if l.startswith("# !latitude:"))}')
    else:
        print('\n(Dry-run. --write zum Schreiben.)')


if __name__ == '__main__':
    main()
