#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Liest die gedruckten Gezeitentafeln des australischen BOM aus.

tide_tables/australia enthaelt rund 1150 Jahrestafeln im selben Layout:
Stationsname, Position, dann Hoch- und Niedrigwasserzeiten mit Hoehen,
vier Monate je Seite in acht Spalten.

Der Textfluss von pdftotext ist dafuer unbrauchbar -- die Spalten laufen
ineinander. Deshalb ueber Wortkoordinaten (-bbox): Zeiten und Hoehen
werden ueber ihre x-Lage den acht Spalten zugeordnet und ueber ihre
y-Lage der Tageszelle.

Usage: python3 py/bom_referenz.py <pdf> [--monat 7]
"""
from __future__ import annotations

import calendar
import re
import subprocess
import sys

MONATE = ['JANUARY', 'FEBRUARY', 'MARCH', 'APRIL', 'MAY', 'JUNE', 'JULY',
          'AUGUST', 'SEPTEMBER', 'OCTOBER', 'NOVEMBER', 'DECEMBER']
WORT = re.compile(r'<word xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" '
                  r'yMax="([\d.]+)">(.*?)</word>')


def worte(pdf, seite):
    x = subprocess.run(['pdftotext', '-bbox', '-f', str(seite), '-l', str(seite), pdf, '-'],
                       capture_output=True, text=True).stdout
    return [(float(a), float(b), float(c), float(d), t)
            for a, b, c, d, t in WORT.findall(x)]


def kopf(pdf):
    """Stationsname, Breite, Laenge, Jahr von der ersten Tafelseite."""
    for s in (2, 1, 3):
        W = worte(pdf, s)
        txt = ' '.join(w[4] for w in W)
        la = re.search(r'LAT\s*(\d+)\D{1,3}\s*(\d+)\D{0,2}\s*([NS])', txt)
        lo = re.search(r'LONG\s*(\d+)\D{1,3}\s*(\d+)\D{0,2}\s*([EW])', txt)
        if not (la and lo):
            continue
        # Der Name steht in der obersten Zeile der Seite.
        oben = min(w[1] for w in W)
        name = ' '.join(w[4] for w in sorted((w for w in W if w[1] < oben + 4),
                                             key=lambda w: w[0]))
        # Nicht aus dem Text: dort ist "2008" auch eine Uhrzeit (20:08).
        jahr = re.search(r'_(20\d\d)_', pdf) or re.search(r'\b(20\d\d)\b', txt)
        lat = int(la.group(1)) + int(la.group(2)) / 60
        lon = int(lo.group(1)) + int(lo.group(2)) / 60
        if la.group(3) == 'S':
            lat = -lat
        # BOM zaehlt ostwaerts durch und schreibt trotzdem "W", sobald der
        # Wert 180 ueberschreitet: Kiritimati steht als "202 Grad 31' W" und
        # liegt tatsaechlich bei 157.48 West. Erst wrappen, dann Vorzeichen.
        if lon > 180:
            lon -= 360
        elif lo.group(3) == 'W':
            lon = -lon
        # Die Jahreszahl steht auf derselben Hoehe wie der Name und wuerde
        # sonst Teil des Namens -- dann gilt jeder Jahrgang als eigene Station.
        name = re.sub(r'\s*\b20\d\d\b\s*$', '', re.sub(r'\s+', ' ', name)).strip()
        return dict(name=name, lat=lat, lon=lon,
                    jahr=int(jahr.group(1)) if jahr else None, seite=s)
    return None


def spalten(zeiten):
    """Die acht Spalten aus den x-Lagen der Zeitangaben."""
    xs = sorted({round(w[0]) for w in zeiten})
    grp, cur = [], [xs[0]]
    for v in xs[1:]:
        if v - cur[-1] <= 12:
            cur.append(v)
        else:
            grp.append(cur)
            cur = [v]
    grp.append(cur)
    return [(min(g) - 4, max(g) + 40) for g in grp]


def seite_lesen(pdf, seite, jahr, monate=None):
    """-> {(monat, tag): [(stunde, minute, hoehe), ...]}

    Welche Monate auf der Seite stehen, wird aus den Ueberschriften der
    Seite selbst gelesen. Nicht jede Tafel beginnt mit Januar auf Seite 2 --
    manche fangen schon auf Seite 1 an oder mit einem anderen Monat.
    """
    W = worte(pdf, seite)
    monate = [w[4] for w in sorted((w for w in W if w[4] in MONATE),
                                   key=lambda w: w[0])]
    if not monate:
        return {}
    unten = [w for w in W if w[1] > 95]          # Kopfzeilen weglassen
    zeit = [w for w in unten if re.fullmatch(r'\d{4}', w[4])]
    hoehe = [w for w in unten if re.fullmatch(r'-?\d+\.\d\d', w[4])]
    tage = [w for w in unten if re.fullmatch(r'\d{1,2}', w[4])]
    if not zeit:
        return {}
    sp = spalten(zeit)
    if len(sp) != 2 * len(monate):
        return {}
    out = {}
    for i, (a, b) in enumerate(sp):
        monat = monate[i // 2]
        sz = [w for w in zeit if a <= w[0] <= b]
        sh = [w for w in hoehe if a <= w[0] <= b]
        st = sorted((w for w in tage if a - 16 <= w[0] < a), key=lambda w: w[1])
        for k, t in enumerate(st):
            y0 = t[1] - 3
            y1 = st[k + 1][1] - 3 if k + 1 < len(st) else 1e9
            paare = []
            for z in sorted((w for w in sz if y0 <= w[1] < y1), key=lambda w: w[1]):
                h = [w for w in sh if abs(w[1] - z[1]) < 3 and w[0] > z[0]]
                if h:
                    paare.append((int(z[4][:2]), int(z[4][2:]),
                                  float(min(h, key=lambda w: w[0])[4])))
            if paare:
                out[(monat, int(t[4]))] = paare
    return out


def lies(pdf):
    k = kopf(pdf)
    if not k:
        return None
    inf = subprocess.run(['pdfinfo', pdf], capture_output=True, text=True).stdout
    m = re.search(r'Pages:\s+(\d+)', inf)
    letzte = int(m.group(1)) if m else 6
    daten = {}
    for s in range(1, letzte + 1):
        daten.update(seite_lesen(pdf, s, k['jahr']))
    k['tage'] = daten
    return k


def main():
    pdf = sys.argv[1]
    k = lies(pdf)
    if not k:
        print('nicht lesbar')
        return
    print(f"{k['name']}   {k['lat']:.4f} / {k['lon']:.4f}   {k['jahr']}")
    print(f"{len(k['tage'])} Tageszellen gelesen")
    fehl = []
    for i, m in enumerate(MONATE, 1):
        n = calendar.monthrange(k['jahr'], i)[1]
        da = [t for (mm, t) in k['tage'] if mm == m]
        if len(da) != n or sorted(da) != list(range(1, n + 1)):
            fehl.append(f'{m}: {len(da)}/{n}')
    print('vollstaendig' if not fehl else 'unvollstaendig -> ' + ', '.join(fehl))
    ev = sum(len(v) for v in k['tage'].values())
    print(f'{ev} Gezeitenereignisse')
    for key in sorted(k['tage'])[:3]:
        print('   ', key, k['tage'][key])


if __name__ == '__main__':
    main()
