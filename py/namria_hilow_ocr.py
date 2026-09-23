#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Liest NAMRIAs Hoch-/Niedrigwassertafeln der Nebenpegel (PDF-Bilder) per OCR.

Quelle: phtides.namria.gov.ph/api/downloads/<id>/secondary-hi-low/<Zeitraum>
(Liste: api/downloads/locations/hi-low/secondary), geladen nach
water_levels/Philippines_NAMRIA/secondary_hilow/<station>_<Zeitraum>.pdf.

Jede Seite: vier Monate nebeneinander, je Monat zwei Spalten (Tag 1-15, 16-31),
je Tag 1-4 Zeilen "hh mm  h.hh". Tafelzeit 120 E (UTC+8), Hoehen ueber MLLW.
Die Zahlen sind Vektorgrafik (kein Textlayer); Seiten kommen in A4 und
US-Letter. Seite mit 300 dpi rendern und ZWEIMAL lesen:
  a) ganze Seite als lose Woerter (Tesseract psm 11)
  b) jede der 8 Spalten einzeln als Textblock (psm 6)
Die Spaltenlage kommt aus den Hoehenwerten, die Tage werden ueber die
Wochentags-Kuerzel verankert (die grossen Tagesziffern erkennt Tesseract
schlecht; der Wochentag legt den Tag eindeutig fest).

Ein Tag gilt, wenn Lesart a ihn sauber liefert (jede Zeile mit Ziffern
lesbar, 1-4 Ereignisse, Zeiten aufsteigend, Hoch/Niedrig abwechselnd) und
Lesart b, falls sie ihn auch liefert, nicht widerspricht. Das Minuszeichen
laesst a oft fallen; es wird deshalb aus den Pixeln bestimmt (vorzeichen()).

Ausgabe: <pdf>.csv  (utc, hoehe_m, typ H/L/?)

Usage: python3 py/namria_hilow_ocr.py <pdf> [<pdf> ...]
"""
from __future__ import annotations

import csv
import datetime as dt
import os
import re
import subprocess
import sys
import tempfile

MONATE = {'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6, 'Jul': 7, 'Aug': 8,
          'Sep': 9, 'Sept': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12}
PHT = dt.timedelta(hours=8)
WOCHE = {'MON': 0, 'TUE': 1, 'WED': 2, 'THU': 3, 'FRI': 4, 'SAT': 5, 'SUN': 6}
UNTEN = 3350          # letzte Tabellenzeile (300 dpi), darunter Fusszeile


def zeitraum(pdf):
    """'85_Jan-Apr_2024.pdf' -> (2024, [1,2,3,4])"""
    m = re.search(r'_([A-Za-z]+)-([A-Za-z]+)_(\d{4})\.pdf$', pdf)
    a, b, jahr = MONATE[m.group(1)], MONATE[m.group(2)], int(m.group(3))
    return jahr, list(range(a, b + 1))


def _tsv(pfad, psm, dx=0):
    subprocess.run(['tesseract', pfad, pfad + '.o', '--psm', str(psm), 'tsv'],
                   check=True, capture_output=True)
    zeilen = open(pfad + '.o.tsv', encoding='utf-8').read().split('\n')
    kopf = zeilen[0].split('\t')
    out = []
    for z in zeilen[1:]:
        f = z.split('\t')
        if len(f) != len(kopf):
            continue
        r = dict(zip(kopf, f))
        t = r['text'].strip()
        if t:
            out.append((int(r['left']) + dx, int(r['top']), int(r['width']), int(r['height']), t))
    return out


def spalten(ws):
    """x-Lage der 8 Zeitspalten aus den Hoehenwerten (h.hh): die stehen immer
    ~95 px (300 dpi) rechts vom Zeitanfang."""
    xs = sorted(x for x, y, w, h, t in ws if re.match(r'^-?\d\.\d{2}$', t))
    grp = []
    for x in xs:
        if not grp or x - grp[-1][-1] > 100:
            grp.append([x])
        else:
            grp[-1].append(x)
    grp = sorted(sorted(grp, key=len)[-8:], key=lambda g: g[0])
    return [sorted(g)[len(g) // 2] - 95 for g in grp]


def lesarten(pdf):
    """-> (Spalten, [Woerter Lesart a, Woerter Lesart b])"""
    from PIL import Image
    with tempfile.TemporaryDirectory() as d:
        subprocess.run(['pdftoppm', '-r', '300', '-png', '-gray', '-f', '1', '-l', '1', pdf, f'{d}/s'],
                       check=True)
        png = os.path.join(d, [f for f in os.listdir(d) if f.endswith('.png')][0])
        ganz = _tsv(png, 11)
        sx = spalten(ganz)
        im = Image.open(png)
        block = []
        for i, tx in enumerate(sx):
            x0 = max(0, int(tx - 130))
            im.crop((x0, 0, int(tx + 200), im.size[1])).save(f'{d}/c{i}.png')
            block += _tsv(f'{d}/c{i}.png', 6, x0)
        pix = im.convert("L").load()
        return sx, [vorzeichen(ganz, pix), vorzeichen(block, pix)]


def vorzeichen(ws, pix):
    """Vorzeichen der Hoehen aus dem Bild statt aus der OCR.

    Die Ganzseiten-Lesart laesst das Minus oft einfach weg (0.13 statt -0.13),
    die Blocklesart nicht immer. Das Minus ist ein kurzer waagerechter Strich
    unmittelbar links der ersten Ziffer, auf halber Zeichenhoehe.
    """
    out = []
    for x, y, w, h, t in ws:
        m = re.match(r'^(-?)(\d?\.\d{2})\W*$', t)
        if m:
            breite = 10 if m.group(1) else 0            # Kasten schliesst das Minus ggf. ein
            x1 = x + breite                              # Beginn der ersten Ziffer
            dunkel = sum(1 for xx in range(x1 - 13, x1 - 1) for yy in range(y + h * 3 // 10, y + h * 7 // 10)
                         if pix[xx, yy] < 128)
            t = ('-' if dunkel >= 8 else '') + m.group(2)
            x = x1
        out.append((x, y, w, h, t))
    return out


def tage_lesen(ws, sx, jahr, monate):
    """-> ({datum: [(hh, mm, hoehe), ...]} sauberer Tage, Zahl unsauberer Tage)"""
    y0 = 450
    gut, schlecht = {}, 0
    for c, tx in enumerate(sx):
        if c // 2 >= len(monate):
            continue
        monat, erster = monate[c // 2], (1 if c % 2 == 0 else 16)
        teil = [w for w in ws if tx - 115 <= w[0] <= tx + 190 and y0 <= w[1] <= UNTEN]
        wt = sorted((y, WOCHE[t]) for x, y, w, h, t in teil if t in WOCHE and x < tx - 15)
        tage, d = [], erster
        for y, wd in wt:
            while d <= erster + 15:
                try:
                    if dt.date(jahr, monat, d).weekday() == wd:
                        break
                except ValueError:
                    d = 99
                    break
                d += 1
            if d > erster + 15:
                break
            tage.append((y - 40, d))
            d += 1
        for i, (ytag, tag) in enumerate(tage):
            yende = tage[i + 1][0] if i + 1 < len(tage) else UNTEN
            zeilen = {}
            for x, y, w, h, t in teil:
                if ytag <= y < yende and x >= tx - 15 and h < 36:
                    zeilen.setdefault(round(y / 14), []).append((x, t))
            werte, kandidaten = [], 0
            for k in sorted(zeilen):
                if any(re.search(r'\d', t) and tx - 10 <= x <= tx + 170 for x, t in zeilen[k]):
                    kandidaten += 1          # Zeile mit Ziffern in Zeit/Hoehe -> muss lesbar sein
                # Rahmenstriche und Klammern, die Tesseract an Zahlen klebt, abstreifen
                tok = [re.sub(r'[^0-9.\-]', '', t.replace('O', '0').replace('o', '0'))
                       for x, t in sorted(zeilen[k])]
                s = ' '.join(x for x in tok if re.search(r'\d', x))
                m = re.match(r'^(\d{2})\s?(\d{2})\s+(-?\d?\.\d{2})$', s)
                if m:
                    werte.append((int(m.group(1)), int(m.group(2)), float(m.group(3))))
            try:
                datum = dt.date(jahr, monat, tag)
            except ValueError:
                continue
            ok = (len(werte) == kandidaten and 1 <= len(werte) <= 4
                  and all(0 <= hh < 24 and 0 <= mm < 60 for hh, mm, _ in werte)
                  and all((werte[j][0], werte[j][1]) < (werte[j + 1][0], werte[j + 1][1])
                          for j in range(len(werte) - 1))
                  and all((werte[j][2] - werte[j + 1][2]) * (werte[j + 1][2] - werte[j + 2][2]) < 0
                          for j in range(len(werte) - 2)))
            if ok:
                gut[datum] = werte
            else:
                schlecht += 1
    return gut, schlecht


def lesen(pdf):
    jahr, monate = zeitraum(pdf)
    sx, ls = lesarten(pdf)
    a, _ = tage_lesen(ls[0], sx, jahr, monate)
    b, _ = tage_lesen(ls[1], sx, jahr, monate)
    tage, streit = {}, 0
    # Quelle ist die Ganzseiten-Lesart a: im Bildvergleich lag sie bei allen
    # Widerspruechen richtig, die Blocklesart b verwechselt Ziffern (1/4, 5/8).
    # b dient nur als Veto.
    for datum in a:
        if datum in b and a[datum] != b[datum]:
            streit += 1
            continue
        tage[datum] = a[datum]
    ereignisse = sorted((dt.datetime.combine(d, dt.time(hh, mm)) - PHT, h)
                        for d, werte in tage.items() for hh, mm, h in werte)
    aus = []
    for j, (t, h) in enumerate(ereignisse):
        nb = [ereignisse[k][1] for k in (j - 1, j + 1) if 0 <= k < len(ereignisse)]
        aus.append((t, h, 'H' if all(h > x for x in nb) else 'L' if all(h < x for x in nb) else '?'))
    soll = sum((dt.date(jahr + (m == 12), m % 12 + 1, 1) - dt.date(jahr, m, 1)).days for m in monate)
    return aus, dict(tage=len(tage), soll=soll, beide=len(set(a) & set(b)), streit=streit)


def main(argv):
    for pdf in argv:
        aus, q = lesen(pdf)
        with open(pdf[:-4] + '.csv', 'w', newline='') as fh:
            w = csv.writer(fh)
            w.writerow(['utc', 'hoehe_m', 'typ'])
            for t, h, typ in aus:
                w.writerow([t.isoformat(), f'{h:.2f}', typ])
        print(f"{os.path.basename(pdf)}: {q['tage']}/{q['soll']} Tage, {len(aus)} Ereignisse,"
              f" beide Lesarten {q['beide']}, davon Widerspruch {q['streit']}")


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
