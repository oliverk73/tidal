#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Legt die NP203-Sekundaerhaefen an, die im Buch stehen und uns fehlten.

Der Abgleich aller att-Nummern der Part-II-Seiten 222-230 und 233-237 gegen
unsere Dateien ergab am 20260801 vierundfuenfzig Luecken. Siebenundzwanzig
davon sind Standardhaefen -- fuer die druckt ATT keine Konstanten, sie sind
hier nicht zu machen. Bleiben siebenundzwanzig Sekundaerhaefen, von denen
achtzehn sogar stationseigene Part-III-Konstanten haben.

Nicht angelegt werden sechs Haefen, bei denen das Buch WEDER Hoehendifferenzen
NOCH ein ML angibt (3828 Mchenga, 3840 Moma River Bar, 3883 Maravoai,
4371 Angria Bank, 4478 Burhabalang River Entrance, 4487 Akra Semaphore). Ohne
ML gibt es kein Datum; wir wuerden eine Station erfinden, die nur der um einen
Zeitversatz verschobene Bezugshafen ist.

Kontrolle der Zeilenzuordnung: Bei allen achtzehn Part-III-Stationen stimmt das
ML aus Part II exakt mit dem aus Part III ueberein. Die drei Transferzeilen sind
einzeln im Scan nachgeprueft.

Aufruf: python3 py/add_np203_fehlende.py [--write]
"""
from __future__ import annotations
import json
import os
import re
import shutil
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
_argv, sys.argv = sys.argv, ['add_np203_fehlende']
import build_np203_tablev as B          # noqa: E402  (PAGES + constituents)
import rebuild_np203_transfer as R      # noqa: E402  (lies, transfer, ZONE_STD)
sys.argv = _argv

TXT = R.TXT
HARM = R.HARM


def dm(g, m):
    return g + m / 60.0


# Part II: Name, Land, Position, Zeitzone. Positionen am 20260801 aus den
# Scans gelesen; p3 = Seite in Part III, sonst Transfer aus Part II.
NEU = [
    # -- mit stationseigenen Part-III-Konstanten ----------------------------
    dict(att='3790',  name='Knysna, South Africa', land='South Africa',
         lat=-dm(34, 4), lon=dm(23, 3), tz='Africa/Johannesburg', p2=222),
    dict(att='3871',  name='Andoany (Hellville), Madagascar', land='Madagascar',
         lat=-dm(13, 24), lon=dm(48, 18), tz='Indian/Antananarivo', p2=224),
    dict(att='4024',  name='Malindi, Kenya', land='Kenya',
         lat=-dm(3, 13), lon=dm(40, 8), tz='Africa/Nairobi', p2=227),
    dict(att='4317',  name='Pasni, Pakistan', land='Pakistan',
         lat=dm(25, 16), lon=dm(63, 29), tz='Asia/Karachi', p2=234),
    dict(att='4319',  name='Ormara, Pakistan', land='Pakistan',
         lat=dm(25, 11), lon=dm(64, 41), tz='Asia/Karachi', p2=234),
    dict(att='4322a', name='Ghizri Creek, Pakistan', land='Pakistan',
         lat=dm(24, 46), lon=dm(67, 6), tz='Asia/Karachi', p2=234),
    dict(att='4322b', name='Port Qasim Entrance, Pakistan', land='Pakistan',
         lat=dm(24, 42), lon=dm(67, 8), tz='Asia/Karachi', p2=234),
    dict(att='4322c', name='Hasan Point, Pakistan', land='Pakistan',
         lat=dm(24, 47), lon=dm(67, 14), tz='Asia/Karachi', p2=234),
    dict(att='4322e', name='Jhari Creek, Pakistan', land='Pakistan',
         lat=dm(24, 44), lon=dm(67, 19), tz='Asia/Karachi', p2=234),
    dict(att='4329',  name='Navinal Point (Mundra), Gujarat, India', land='India',
         lat=dm(22, 44), lon=dm(69, 43), tz='Asia/Kolkata', p2=234),
    dict(att='4338',  name='Porbandar, Gujarat, India', land='India',
         lat=dm(21, 38), lon=dm(69, 36), tz='Asia/Kolkata', p2=234),
    dict(att='4353',  name='Suvali, Gujarat, India', land='India',
         lat=dm(21, 11), lon=dm(72, 37), tz='Asia/Kolkata', p2=234),
    dict(att='4368',  name='Jaigarh, Maharashtra, India', land='India',
         lat=dm(17, 18), lon=dm(73, 14), tz='Asia/Kolkata', p2=235),
    dict(att='4369',  name='Ratnagiri Bay, Maharashtra, India', land='India',
         lat=dm(16, 59), lon=dm(73, 18), tz='Asia/Kolkata', p2=235),
    dict(att='4382',  name='Coondapoor, Karnataka, India', land='India',
         lat=dm(13, 38), lon=dm(74, 40), tz='Asia/Kolkata', p2=235),
    dict(att='4388',  name='Tellicherry, Kerala, India', land='India',
         lat=dm(11, 45), lon=dm(75, 29), tz='Asia/Kolkata', p2=235),
    dict(att='4463',  name='Vishakhapatnam, Andhra Pradesh, India', land='India',
         lat=dm(17, 41), lon=dm(83, 17), tz='Asia/Kolkata', p2=237),
    # ML steht bei 4475a als "w" -> Table VI S.xxxviii: Average ML 2.00,
    # MSf-Amplitude 0.06 m. Beides wird hier gleich mitgesetzt.
    dict(att='4475a', name='Dhamra, Odisha, India', land='India',
         lat=dm(20, 48), lon=dm(86, 54), tz='Asia/Kolkata', p2=237,
         ml=2.00, msf=(0.060, None)),

    # -- nur Part-II-Transfer ----------------------------------------------
    dict(att='4323',  name='Hajambro Creek, Pakistan', land='Pakistan',
         lat=dm(24, 6), lon=dm(67, 19), tz='Asia/Karachi', p2=234,
         zone=5.0, t=(5, None), h=(0.4, 0.4, None, None), ml=1.8),
    dict(att='4353a', name='Hazira, Gujarat, India', land='India',
         lat=dm(21, 6), lon=dm(72, 37), tz='Asia/Kolkata', p2=234,
         zone=5.5, t=(None, None), h=(-2.8, -2.3, -0.4, 0.3), ml=4.50),
    dict(att='4454',  name='Krishnapatnam, Andhra Pradesh, India', land='India',
         lat=dm(14, 17), lon=dm(80, 7), tz='Asia/Kolkata', p2=237,
         zone=5.5, t=(None, None), h=(0.1, 0.2, 0.3, 0.4), ml=0.8),
]

# Buchnummern ohne Hoehendifferenz UND ohne ML -- bewusst nicht angelegt.
NICHT = {
    '3828':  'Mchenga (Sambesi), S.223',
    '3840':  'Moma River Bar, S.223',
    '3883':  'Maravoai, S.224',
    '4371':  'Angria Bank, S.235',
    '4478':  'Burhabalang River Entrance, S.237',
    '4487':  'Akra Semaphore, S.237',
}


def main():
    write = '--write' in sys.argv
    L = open(TXT, encoding='iso-8859-1').read().split('\n')
    ORDER = R.order(L)
    _, SEC = R.lies(TXT)
    _, STD = R.lies(R.STD)
    refs = {**SEC, **STD}
    for a, r in R.lies_extern().items():
        refs.setdefault(a, r)
    G = json.load(open(R.GRUPPEN))['gruppen']
    P3 = {a: (s, row) for s, rows in B.PAGES.items() for a, row in rows.items()}

    print(f'Nicht anzulegen (Buch gibt weder Hoehendifferenz noch ML): '
          f'{", ".join(sorted(NICHT))}\n')
    print(f'{"att":7s} {"Station":40s} {"Quelle":10s} {"Z0":>5s} {"M2":>15s}  einfuegen vor')
    print('-' * 112)

    blocks = []
    for s in NEU:
        if s['att'] in SEC:
            print(f'{s["att"]:7s} steht bereits in der Datei'); continue
        if s['att'] in P3:
            seite, row = P3[s['att']]
            con = B.constituents(row)
            mer = row[7]
            z0 = s.get('ml', row[0])
            quelle, herkunft = 'Part III', (
                f'# note: NP203 Part III S.{seite} (2015), Meridian {mer}. Stationseigene '
                f'Konstanten.',
                f'# note: Position und Name aus Part II S.{s["p2"]}. N2/K2 inferiert.')
        else:
            g = R.gruppe(s['att'], G)
            r = refs[g['ref']]
            tr = R.transfer(r['con'], g['pegel'], s['h'], s['t'],
                            R.ZONE_STD[g['ref']] - s['zone'], s['ml'])
            con, mer, z0 = tr['con'], r['mer'], s['ml']
            quelle, herkunft = 'Part II', (
                f'# note: NP203 Part II Sekundaerhafen-Transfer von {r["name"]} '
                f'(att {g["ref"]}).',
                f'# note: fS={tr["fS"]:.2f} fN={tr["fN"]:.2f} dt={tr["dt"]*60:+.0f}min, '
                f'skaliert gegen die publizierten',
                f'# note: Pegel {g["pegel"]} aus dem Gruppenkopf S.{g["seite"]}. '
                f'Zeit-/Hoehendiff. aus S.{s["p2"]}.')
        if 'msf' in s:
            gm = (con['S2'][1] - con['M2'][1]) % 360
            con['MSF'] = (s['msf'][0], round(gm, 2))
            herkunft += (f'# note: MSf aus NP203 Table VI S.xxxviii (ML im Buch "w"): '
                         f'Amplitude {s["msf"][0]:.3f} m,',
                         f'# note: Phase = g(S2)-g(M2) = {gm:.1f} Grad.')

        # Ankerstation: die naechsthoehere vorhandene Nummer
        spaeter = sorted((x for x in SEC if R.key(x) > R.key(s['att'])), key=R.key)
        if not spaeter:
            print(f'{s["att"]:7s} keine Ankerstation gefunden'); continue
        anker = SEC[spaeter[0]]['name']

        blk = ['# BEGIN HOT COMMENTS', f'# country: {s["land"]}',
               f'# source: ADMIRALTY Tide Tables Vol.3 (NP203), '
               f'{"Table V (Part III)" if quelle == "Part III" else "Part II Secondary Port Transfer"}',
               f'# att_number: {s["att"]}', *herkunft,
               f'# note: {datetime.now():%Y%m%d} neu angelegt -- Station fehlte in der Sammlung.',
               f'# date_imported: {datetime.now():%Y%m%d}',
               '# datum: Chart Datum (Z0 = mean level above CD)',
               f'# confidence: {7 if quelle == "Part III" else 4}', '# !units: meters',
               f'# !longitude: {s["lon"]:.4f}', f'# !latitude: {s["lat"]:.4f}',
               s['name'], f'{mer} :{s["tz"]}', f'{z0:.4f} meters']
        blk += [f'{c:<16}{con[c][0]:.4f}  {con[c][1]:.2f}' if c in con else 'x 0 0'
                for c in ORDER]
        m2 = con['M2']
        print(f'{s["att"]:7s} {s["name"][:40]:40s} {quelle:10s} {z0:5.2f} '
              f'{m2[0]:7.3f} @ {m2[1]:5.1f}  {anker[:34]}')
        blocks.append((anker, blk))

    if not write:
        print(f'\n{len(blocks)} Stationen. (Dry-run. --write zum Schreiben.)')
        return

    shutil.copy(TXT, f'{HARM}/backup/harmonics_att_np203_secondary_pre_fehlende_'
                     f'{datetime.now():%Y%m%d}.txt')
    # von hinten nach vorn einfuegen, damit die Indizes gueltig bleiben
    stellen = []
    for anker, blk in blocks:
        i = L.index(anker)
        stellen.append((max(k for k in range(i) if L[k] == '# BEGIN HOT COMMENTS'), blk))
    for pos, blk in sorted(stellen, key=lambda x: -x[0]):
        L[pos:pos] = blk

    open(TXT, 'w', encoding='iso-8859-1').write('\n'.join(L))
    os.chmod(TXT, 0o600)
    print(f'\n{len(blocks)} Stationen angelegt. Datei: '
          f'{sum(1 for l in L if l.startswith("# !latitude:"))} Stationen')


if __name__ == '__main__':
    main()
