#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Liest die gedruckten Gezeitentafeln der brasilianischen Marine (DHN).

Jede Tafel deckt ein Jahr auf drei Seiten ab, je vier Monate. Ein Monat
belegt zwei Spaltenpaare (Tage 1-16 und 17-31), jedes Paar aus einer
Spalte HORA (HHMM) und einer Spalte ALT (Meter). Die Tagesnummer steht
links davon, auf Hoehe des ersten Ereignisses des Tages.

Anders als die australischen Tafeln druckt die DHN ihre Zeitzone in den
Kopf ("Fuso +03.0 horas"), ebenso Position und mittleren Wasserstand.
Der Zeitversatz muss also nicht aus dem Vergleich geschaetzt werden.

Gelesen wird ueber die Textkoordinaten, nicht ueber das Zeilenlayout:
pdftotext -layout mischt die acht Spalten je nach Zeilenhoehe
durcheinander, sobald ein Tag drei statt vier Ereignisse hat.

Die Tafeln stammen aus mehreren Jahrgaengen und weichen im Kleinen
voneinander ab -- Minuten mit oder ohne Zehntel, Hoehen mit einer oder
zwei Nachkommastellen, Dezimalpunkt oder -komma, Fuso als Betrag oder
als Zone, Tagesspalte 20 oder 30 Punkte links der Uhrzeit. Deshalb wird
nichts an festen Koordinaten festgemacht, sondern jede Seite aus ihren
eigenen Spaltenhaeufungen erschlossen.

Stand: 174 der 176 Tafeln werden vollstaendig gelesen (alle Tage des
Jahres belegt). Die zwei uebrigen -- capitania_dos_portos_de_sergipe und
terminal_maritimo_inacio_barbosa, beide 2024 -- sind reine Scans ohne
Textebene und brauchen OCR.

Usage: python3 py/dhn_referenz.py <tafel.pdf>
       python3 py/dhn_referenz.py --alle       Koepfe aller Tafeln pruefen
"""
from __future__ import annotations

import datetime as dt
import os
import re
import sys
import unicodedata

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PDFS = os.path.join(ROOT, 'tide_tables/brazil')

MONATE = ['Janeiro', 'Fevereiro', 'Marco', 'Abril', 'Maio', 'Junho',
          'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro']
# Spaltenbreite in Punkten: so weit darf ein Wort von der Spaltenmitte
# abweichen und noch dazugehoeren. Die Spalten liegen rund 63 Punkte
# auseinander, die Haelfte davon trennt sie sicher.
SPALTE = 26.0
TAG = re.compile(r'^([0-2]\d|3[01])$')
UHR = re.compile(r'^([0-2]\d)([0-5]\d)$')
# Aeltere Tafeln drucken eine Nachkommastelle, neuere zwei. Und ein Teil
# der Tafeln schreibt das Dezimalkomma portugiesisch ("1,49").
HOEHE = re.compile(r'^-?\d+[.,]\d\d?$')


def _ohne_akzent(t):
    return ''.join(c for c in unicodedata.normalize('NFD', t)
                   if unicodedata.category(c) != 'Mn')


def _worte(seite):
    return [(x0, y0, t) for x0, y0, _x1, _y1, t, *_ in seite.get_text('words')]


def _spalten(w, muster, mindest):
    """x-Mitten der Spalten, in denen das Muster gehaeuft auftritt.

    Der Mindestwert wirft Einzelfunde weg: die Jahreszahl der Titelzeile
    ("... - 2024") sieht aus wie eine Uhrzeit und bildet sonst eine
    neunte Spalte.
    """
    aus = []
    for x in sorted(round(x) for x, _y, t in w if muster.match(t)):
        if not aus or x - aus[-1][-1] > SPALTE:
            aus.append([x])
        else:
            aus[-1].append(x)
    return [sum(s) / len(s) for s in aus if len(s) >= mindest]


def kopf(pfad):
    """-> {'name','lat','lon','fuso','jahr','nivel_medio'} oder None.

    Die Gradangaben stehen als "00o 45'.8 N" da -- der Dezimalpunkt der
    Minuten steht VOR der Nachkommastelle. Manche Tafeln geben nur ganze
    Minuten ("02o 24' S"), auch gemischt innerhalb eines Kopfes.

    Das Feld Fuso kommt in zwei Schreibweisen vor und meint beide Male
    dasselbe: "Fuso +03.0 horas" ist der Betrag, den man zur Ortszeit
    addiert, um UTC zu bekommen; "Fuso UTC -03.0 horas" nennt direkt die
    Zone. Zurueckgegeben wird immer der Zonen-Offset, fuer Brasilien also
    negativ.
    """
    import pymupdf
    d = pymupdf.open(pfad)
    t = d[0].get_text()
    d.close()
    g = (r"(\d+)\s*[^\d\s]{0,3}\s*(\d+)'(?:\.(\d))?\s*([NSEWO])")
    la = re.search(r'Latitude\s*' + g, t)
    lo = re.search(r'Longitude\s*' + g, t)
    if not (la and lo):
        return None

    def grad(m):
        zehntel = int(m.group(3)) / 10 if m.group(3) else 0.0
        v = int(m.group(1)) + (int(m.group(2)) + zehntel) / 60
        return -v if m.group(4) in ('S', 'W', 'O') else v

    fu = re.search(r'Fuso\s*(UTC)?\s*([+-]?\d+(?:\.\d+)?)', t)
    fuso = None
    if fu:
        v = float(fu.group(2))
        # Ohne "UTC" ist es der Betrag zum Addieren, also die Gegenzahl
        # der Zone. Mit "UTC" steht die Zone schon da.
        fuso = v if fu.group(1) else -v
    nm = re.search(r'N[íi]vel\s+M[ée]dio\s*(-?[\d.,]+)', t)
    ja = re.search(r'\b(20\d\d)\b', t)
    # Der Stationsname steht in der Kopfzeile vor "- <Jahr>".
    nam = ''
    for z in t.split('\n')[:8]:
        m = re.match(r'\s*(.+?)\s*-\s*20\d\d\s*$', z.strip())
        if m and len(m.group(1)) > 2:
            nam = m.group(1).strip()
            break
    return dict(name=nam, lat=grad(la), lon=grad(lo),
                fuso=fuso,
                nivel_medio=float(nm.group(1).replace(',', '.')) if nm else None,
                jahr=int(ja.group(1)) if ja else None)


def lies(pfad):
    """-> (kopf, [(datetime Ortszeit, hoehe_m), ...]) nach Zeit sortiert."""
    import pymupdf
    k = kopf(pfad)
    if not k or not k.get('jahr'):
        return None, []
    d = pymupdf.open(pfad)
    aus = []
    for seite in d:
        w = _worte(seite)
        # Die vier Monatsnamen der Seite geben die Zuordnung Spalte->Monat.
        mon = sorted((x, _ohne_akzent(t)) for x, y, t in w
                     if _ohne_akzent(t) in MONATE)
        if not mon:
            continue
        # Acht Uhrzeitspalten: ihre x-Werte sind die haeufigsten unter den
        # Woertern, die wie HHMM aussehen.
        mitten = _spalten(w, UHR, 20)
        # Die Tagesspalte steht links der Uhrzeit, je nach Tafel 20 bis 30
        # Punkte davor. Statt einen festen Abstand anzunehmen, werden beide
        # Spaltensaetze getrennt gebildet und der Reihe nach gepaart -- die
        # Abstaende schwanken zwischen den Jahrgaengen.
        tagx = _spalten(w, TAG, 10)
        if len(mitten) != 8 or len(tagx) != 8:
            continue
        for i, mx in enumerate(mitten):
            monat = MONATE.index(mon[i // 2][1]) + 1
            tage = sorted((y, int(t)) for x, y, t in w
                          if TAG.match(t) and abs(x - tagx[i]) < SPALTE)
            if not tage:
                continue
            werte = sorted((y, x, t) for x, y, t in w
                           if abs(x - mx) < SPALTE and UHR.match(t))
            hoehen = sorted((y, x, t) for x, y, t in w
                            if mx < x < mx + 2 * SPALTE and HOEHE.match(t))
            for y, _x, u in werte:
                # Der Tag ist der letzte, dessen Zeile nicht unter dieser
                # liegt; Tagesnummer und erstes Ereignis stehen auf gleicher
                # Hoehe, die folgenden Ereignisse darunter.
                kand = [t for ty, t in tage if ty <= y + 2]
                if not kand:
                    continue
                h = [ht for hy, _hx, ht in hoehen if abs(hy - y) < 2]
                if not h:
                    continue
                m = UHR.match(u)
                try:
                    z = dt.datetime(k['jahr'], monat, kand[-1],
                                    int(m.group(1)), int(m.group(2)))
                except ValueError:
                    continue           # 31. in einem 30-Tage-Monat o.ae.
                aus.append((z, float(h[0].replace(',', '.'))))
    d.close()
    aus = sorted(set(aus))
    return k, aus


def main(argv):
    if '--alle' in argv:
        gut = schlecht = 0
        for fn in sorted(os.listdir(PDFS)):
            if not fn.lower().endswith('.pdf'):
                continue
            try:
                k = kopf(os.path.join(PDFS, fn))
            except Exception as e:
                print(f'  FEHLER {fn}: {type(e).__name__}')
                schlecht += 1
                continue
            if not k:
                print(f'  Kopf nicht lesbar: {fn}')
                schlecht += 1
                continue
            gut += 1
            print(f'{k["name"][:34]:36s} {k["lat"]:8.4f} {k["lon"]:9.4f}  '
                  f'Fuso {k["fuso"]}  {k["jahr"]}  NM {k["nivel_medio"]}')
        print(f'\n{gut} Koepfe gelesen, {schlecht} nicht')
        return 0
    if not argv:
        print(__doc__)
        return 1
    k, ev = lies(argv[0])
    if not k:
        print('Kopf nicht lesbar')
        return 1
    print(f'{k["name"]}   {k["lat"]:.4f} / {k["lon"]:.4f}   Fuso {k["fuso"]}   '
          f'{k["jahr"]}   Nivel Medio {k["nivel_medio"]} m')
    print(f'{len(ev)} Ereignisse')
    for z, h in ev[:8]:
        print(f'   {z:%Y-%m-%d %H:%M}  {h:5.2f} m')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
