#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Liest die Zeitmeridiane der NOAA-Tafeln aus den Buch-PDFs.

Die Tafeln rechnen in Ortszeit. Im Vorwort steht es woertlich: "All
daily tide predictions and predictions compiled by the use of Table 2
data are based on the standard time meridian indicated for each
location." Table 2 druckt diesen Meridian als Zwischenzeile ueber jedem
Block ("Time meridian, 120° E") und daneben den Bezugsort ("on Pusan,
p.48"); Table 1 nennt ihn in der Fusszeile jeder Vorhersageseite ("Time
meridian 135° E.").

Damit ist die Zonendifferenz zwischen Neben- und Bezugsort aus dem Buch
selbst zu haben -- und nicht mehr aus der geografischen Zone, die
timezonefinder zur Position liefert. Der Unterschied ist keine
Feinheit: die Tafel rechnet Casablanca mit UTC+0, waehrend Marokko
heute auf UTC+1 steht, und die Andamanen fuehrt sie unter dem
indischen Meridian, obwohl sie eine eigene Zone haetten.

Zwei Fallen beim Lesen:

  Halbe Zonen stehen als "97° 30' E". Ein Muster, das nur ganze Grad
  kennt, findet die Zeile nicht -- und weil der Meridian bis zur
  naechsten Zwischenzeile gilt, erbt der ganze Block stillschweigend
  den Wert des vorigen. Myanmar stand so unter dem Kurilen-Meridian
  +11 statt +6.5, und die Auswertung zeigte fuer die Gruppe
  einen Versatz, den es nicht gab.

  Der Nullmeridian steht als "Time meridian, 0°" ganz ohne
  Himmelsrichtung.

Usage: python3 py/noaa_buch_zonen.py <pdf> <erste> <letzte> [--json <datei>]
       erste/letzte sind die PDF-Seiten der Table-2-Bloecke.
"""
from __future__ import annotations

import difflib
import json
import re
import subprocess
import sys
import unicodedata

# "Time meridian, 97° 30' E" / "Time meridian 135° E." / "Time meridian, 0°"
MERIDIAN = re.compile(r'Time meridian,?\s+(\d{1,3})\s*°\s*'
                      r'(?:(\d{1,2})\s*[’ʼ\']\s*)?([EW])?')
# Die amerikanischen Baende fuehren einzelne Bloecke unter "Time
# meridian, local": dort gilt die Zone des jeweiligen Ortes, nicht eine
# fuer den ganzen Block. Diese Zeile MUSS erkannt werden, sonst erbt der
# Block stumm den Meridian des vorigen.
LOKAL = re.compile(r'Time meridian,?\s+local', re.I)
BEZUG = re.compile(r'\bon\s+(.+?),\s*p\.?\s*(\d+)')
ZEILE = re.compile(r'^\s{0,8}(\d{1,4})\s+(\S.*?)\s\s')
KOPF = re.compile(r',?\s*20\d\d\s*$')


def _stunden(m):
    grad = int(m.group(1)) + (int(m.group(2)) / 60 if m.group(2) else 0)
    h = grad / 15.0
    return -h if m.group(3) == 'W' else h


def text(pdf, von, bis):
    return subprocess.run(['pdftotext', '-layout', '-f', str(von), '-l', str(bis), pdf, '-'],
                          capture_output=True).stdout.decode('utf-8', 'replace')


def stationen(pdf, von, bis):
    """-> ({Nummer: (Meridian oder "local", Bezugsort)}, {Name: Meridian}).

    Das zweite Ergebnis sind die Bezugsorte selbst: sie stehen in
    Table 2 mit "Daily predictions" statt Differenzen, und damit unter
    dem Meridian ihres eigenen Blocks. Das ist der Ausweg fuer die
    Bezugsorte ohne Table-1-Seite -- fuer JOLO, LEGASPI PORT und SAN
    FERNANDO HARBOR sagt das Vorwort ausdruecklich, dass ihre
    Tagesvorhersagen nicht abgedruckt sind.
    """
    out, taeglich, mer, bezug = {}, {}, None, None
    for line in text(pdf, von, bis).split('\n'):
        if LOKAL.search(line):
            mer = 'local'
        m = MERIDIAN.search(line)
        if m:
            mer = _stunden(m)
        b = BEZUG.search(line)
        if b:
            bezug = b.group(1).strip()
        z = ZEILE.match(line)
        if z and ('°' in line or '. .' in line) and mer is not None:
            out[int(z.group(1))] = (mer, bezug)
            if 'Daily predictions' in line and mer != 'local':
                name = re.split(r'\s*[.{}]\s*', z.group(2))[0].strip()
                taeglich.setdefault(norm(name), mer)
                taeglich.setdefault(norm(name.split(',')[0]), mer)
    return out, taeglich


def norm(s):
    s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode().lower()
    s = re.sub(r'\b(o|ostrov|island|islands|port|harbor|harbour|bar|approach|ent|entrance)\b',
               ' ', s)
    return re.sub(r'[^a-z0-9]', '', s)


def referenzen(pdf, von=1, bis=None):
    """-> {normalisierter Name: Meridian in Stunden} aus den Table-1-Seiten."""
    if bis is None:
        bis = int(subprocess.run(['pdfinfo', pdf], capture_output=True).stdout
                  .decode().split('Pages:')[1].split()[0])
    out = {}
    for seite in text(pdf, von, bis).split('\f'):
        m = MERIDIAN.search(seite)
        if not m:
            continue
        h = _stunden(m)
        for line in [x.strip() for x in seite.split('\n') if x.strip()][:4]:
            if KOPF.search(line) and len(line) > 6:
                name = KOPF.sub('', line).strip().rstrip(',')
                out.setdefault(norm(name.split(',')[0]), h)
                out.setdefault(norm(name), h)
                break
    return out


def suche(tabelle, name):
    """Meridian zu einem Bezugsortnamen.

    Die Schreibweisen gehen zwischen Table 1 und Table 2 auseinander:
    "Gibralter" gegen "Gibraltar", "Suriname Rivier" gegen "Suriname
    River Entrance". Deshalb zuletzt ein unscharfer Vergleich.
    """
    if not name:
        return None
    n = norm(name.split(',')[0])
    if n in tabelle:
        return tabelle[n]
    treffer = [k for k in tabelle if k and (k.startswith(n) or n.startswith(k))]
    if treffer:
        return tabelle[treffer[0]]
    nah = difflib.get_close_matches(n, [k for k in tabelle if k], n=1, cutoff=0.85)
    return tabelle[nah[0]] if nah else None


def main(argv):
    pdf, von, bis = argv[0], int(argv[1]), int(argv[2])
    st, taeglich = stationen(pdf, von, bis)
    ref = referenzen(pdf, 1, von - 1)
    for k, v in taeglich.items():
        ref.setdefault(k, v)                  # Table 1 hat Vorrang
    print(f'{len(st)} Stationen, {len(ref)} Bezugsorte '
          f'({len(taeglich)} davon aus Table 2)', file=sys.stderr)
    if '--json' in argv:
        ziel = argv[argv.index('--json') + 1]
        json.dump({'stationen': {str(k): v for k, v in st.items()}, 'referenzen': ref},
                  open(ziel, 'w'), ensure_ascii=False)
        print(f'-> {ziel}', file=sys.stderr)
    else:
        import collections
        print(sorted(collections.Counter(v[0] for v in st.values()).items()))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
