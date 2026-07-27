#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Setzt die Anzeige-Zeitzone der in timezone_audit_*.csv gemeldeten Gruppe-B-
Stationen auf die an ihren Koordinaten geltende Zone.

Geaendert wird ausschliesslich der Teil hinter dem Doppelpunkt. Der Meridian
bleibt stehen -- er gehoert zu den Phasen, nicht zur Anzeige. Kein Rechenwert
aendert sich.

Uebersprungen werden Stationen, bei denen der Treffer eher auf einen
Koordinatenfehler als auf eine falsche Zone hindeutet (SKIP unten).

Aufruf: python3 py/fix_station_timezones.py DATEI.txt            # dry-run
        python3 py/fix_station_timezones.py DATEI.txt --write
"""
from __future__ import annotations
import csv
import os
import re
import shutil
import sys
from datetime import datetime

HARM = '/home/oliver/weather/harmonics'
CSV = f'{HARM}/help/timezone_audit_2026-07-27.csv'
MER = re.compile(r'^([+-]\d\d:\d\d) :(\S+)\s*$')

# Stationen, deren Zeitzonen-Treffer in Wahrheit ein Koordinatenproblem ist.
# Hier waere eine TZ-Korrektur die falsche Reparatur.
SKIP = {
    'Niue Island, Niue',        # steht richtig auf Pacific/Niue; 169.92 muss WEST sein
    'Shortland Island, Solomon Islands',   # -10.53/151.08 liegt in der Milne Bay (PNG);
                                           # die echten Shortlands: -7.05/155.85

    # --- Grenznah: der Treffer ist ein Artefakt, der Bestand ist richtig ---
    'Cap Blanc, Mauritania',            # Nouadhibou ist mauretanisch (UTC+0 wie Dakar);
                                        # timezonefinder greift auf die Westsahara
    'Dhalqut, Oman',                    # 53.05 E liegt in Dhofar/Oman (+4), nicht Jemen
    'Khowr-e Musa Approaches, Iran',    # iranisches Fahrwasser, Asia/Tehran ist richtig
    'Khawr Abd Allah Current',          # Wasserstrasse Irak/Kuwait, offshore
    'Dandong, Liaoning, China',         # chinesische Stadt am Yalu, Asia/Shanghai richtig
    'Sulawesi Current',                 # Sulawesi ist WITA (+8) = Asia/Makassar
    'Finsch Islands, Greenland',        # NO-Groenland, Zonengrenze Danmarkshavn/Nuuk unklar

    # --- Umstritten oder offshore: keine eindeutige Landzone ---
    'El Bunduq Oilfield, United Arab Emirates',   # Feld VAE/Katar gemeinsam
    'Hoang Sa (Paracel Islands), Vietnam',        # umstritten VN/CN
    'Shuangzijiao (Nansha Qundao), Hainan, China',  # Spratly, umstritten

    # --- Konvention schlaegt Geografie ---
    'Singapore Strait Current',         # ATT rechnet die Strasse in Singapur-Zeit (+8);
                                        # die Punkte liegen z.T. in indonesischem Wasser
}

# timezonefinder liefert eine Zone mit richtigem Versatz, aber der administrativ
# passendere Name ist ein anderer. Reine Kosmetik -- die angezeigte Uhrzeit ist
# in beiden Faellen identisch.
PREFER = {
    'Asia/Magadan': ('Asia/Sakhalin', 'Kuril'),   # Kurilen gehoeren zur Oblast Sachalin
}


def find_file(arg):
    if os.path.isfile(arg):
        return arg
    hits = [os.path.join(d, f)
            for d in ('att', 'noaa', 'classic', 'utide', 'ticon')
            for f in os.listdir(f'{HARM}/{d}')
            if f == arg or f == arg.replace('.txt', '_mod.txt')]
    if len(hits) == 1:
        return f'{HARM}/{hits[0]}'
    sys.exit(f'Datei nicht eindeutig: {arg} -> {hits}')


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    path = find_file(sys.argv[1])
    base = os.path.basename(path)
    write = '--write' in sys.argv

    # Schluessel ist (Name, Ist-Zone), nicht nur der Name: 13 Stationen kommen in
    # harmonics-2004-06-14_mod.txt mehrfach vor, zwei davon mit verschiedenen
    # Zonen. Ueber den Namen allein wuerde der zweite Block still uebergangen.
    want = {}
    for r in csv.DictReader(open(CSV, encoding='utf-8')):
        if r['gruppe'] == 'B' and r['datei'] == base:
            want.setdefault((r['station'], r['tz_ist']), []).append(r)
    if not want:
        sys.exit(f'Keine Gruppe-B-Befunde fuer {base}.')

    L = open(path, encoding='iso-8859-1').read().split('\n')
    done, skipped, missed = [], [], []
    for i, l in enumerate(L):
        m = MER.match(l)
        if not m:
            continue
        name = L[i - 1].strip()
        bucket = want.get((name, m.group(2)))
        if not bucket:
            continue
        r = bucket.pop(0)
        if not bucket:
            del want[(name, m.group(2))]
        if name in SKIP:
            skipped.append((name, r['tz_ist'], r['tz_geo']))
            continue
        ziel = r['tz_geo']
        alt = PREFER.get(ziel)
        if alt and alt[1] in name:
            ziel = alt[0]
        L[i] = f"{m.group(1)} :{ziel}"
        done.append((name, r['tz_ist'], ziel, r['max_delta_h']))

    for name, _, _, _ in []:
        pass
    print(f'{base}: {len(done)} zu aendern, {len(skipped)} uebersprungen, '
          f'{len(missed)} veraltet, {len(want)} nicht gefunden\n')
    for name, a, b, d in sorted(done, key=lambda x: (-float(x[3]), x[0])):
        print(f'  {d:>5s}h  {name[:46]:46s} :{a:22s} -> :{b}')
    for name, a, b in skipped:
        print(f'  SKIP    {name[:46]:46s} :{a} (Koordinate pruefen)')
    for name, ist, csv_tz in missed:
        print(f'  VERALTET {name[:44]:44s} Datei hat :{ist}, Audit sah :{csv_tz}')
    for (name, tz), rows in want.items():
        print(f'  FEHLT   {name}  (:{tz}, {len(rows)}x)')

    if write and done:
        bak = (f'{HARM}/backup/'
               f'{base.replace(".txt","")}_pre_tzfix_{datetime.now():%Y%m%d}.txt')
        shutil.copy(path, bak)
        open(path, 'w', encoding='iso-8859-1').write('\n'.join(L))
        print(f'\nGeschrieben. Sicherung: {os.path.basename(bak)}')
    else:
        print('\n(Dry-run. --write zum Schreiben.)')


if __name__ == '__main__':
    main()
