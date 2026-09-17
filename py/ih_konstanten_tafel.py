#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Liest die amtlichen harmonischen Konstanten aus der IH-Tabela de Marés.

Volume II (PALOP) druckt auf Seite 3-11 "CONSTANTES HARMÓNICAS FUNDAMENTAIS":
M2, S2, K1 und O1 fuer die 23 Haupthaefen von Kap Verde, Guinea-Bissau,
S. Tome e Principe, Angola und Mosambik. Die Phasen stehen in der ORTSZEIT
des Hafens (Angola UT+1, Mosambik UT+2, Kap Verde UT-1) -- die Tagestafeln
dagegen in UT, wie ihr Kopf sagt ("Horas do Fuso: 0 (TU)").

Dazu wird die Lage des Pegels gesammelt: Jede Tafelseite traegt sie im Kopf
("Latitude 19° 49.40' S  Longitude 34° 50.00' E"), und genau die gehoert zur
Konstantenzeile. Das ist wichtig, weil der Buchname nicht immer der Ort ist,
den man erwartet: Die Zeile "QUELIMANE" gehoert zum Pegel an der Muendung
(Tafel "Ponta Tangalane, Barra de Quelimane"), nicht zur Stadt 25 km
flussaufwaerts.

Ergebnis: harmonics/help/ih_konstanten.csv
  hafen, land, lat, lon, zone_h, quelle_seite, M2_H, M2_G, S2_H, S2_G, ...

Usage: python3 py/ih_konstanten_tafel.py [--pdf <datei>]
"""
from __future__ import annotations

import csv
import os
import re
import subprocess
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from health_check import ROOT                                       # noqa: E402

PDF = os.path.join(ROOT, 'tide_tables/Portugal/TabelaMare_II_2026_signed.pdf')
AUS = os.path.join(ROOT, 'harmonics/help/ih_konstanten.csv')
# Das Buch mischt die Zonen: Porto Grande steht in Ortszeit (UT-1), Praia und
# Palmeira auf denselben Seiten in UT. Welcher Hafen wie zaehlt, ist am
# 14.09.2026 an den Tagestafeln des Buchs selbst gemessen worden und steht in
# py/ih_portugal_tafel.ZONE_H; hier gilt diese Tabelle, und nur wo sie schweigt,
# die Landeszone.
import ih_portugal_tafel as IHT                                     # noqa: E402
LANDZONE = {'CABO VERDE': 0.0, 'GUINÉ-BISSAU': 0.0, 'S. TOMÉ E PRÍNCIPE': 0.0,
            'ANGOLA': 1.0, 'MOÇAMBIQUE': 2.0}


def zone_von(hafen, land):
    kurz = hafen.split(' (')[0].strip()
    for name in (hafen, kurz):
        if name in IHT.ZONE_H:
            return IHT.ZONE_H[name], 'gemessen (ih_portugal_tafel)'
    return LANDZONE[land], 'Landeszone'

POS = re.compile(r"Latitude\s+(\d+)[º°]\s*([\d.,]+)'?\s*([NS])\s+Longitude\s+(\d+)[º°]\s*([\d.,]+)'?\s*([EW])")
ZEILE = re.compile(r"^\s*([A-ZÇÁÉÍÓÚÂÊÔÃÕ.\s()',\-]{3,45}?)\s{2,}"
                   r"(\.?\d[\d.]*)\s+([\d.]+)\s+(\.?\d[\d.]*)\s+([\d.]+)\s+"
                   r"(\.?\d[\d.]*)\s+([\d.]+)\s+(\.?\d[\d.]*)\s+([\d.]+)\s*$")
# Die Punktfuehrung ("PRAIA . . . . .  .313") frisst sonst den Dezimalpunkt des
# ersten Wertes: ein Punkt, dem Leerzeichen oder Punkt folgt, ist Fuehrung --
# ein Punkt vor einer Ziffer gehoert zur Zahl.
FUEHRUNG = re.compile(r"\.(?=[\s.])")


def flach(s):
    s = unicodedata.normalize('NFKD', s)
    s = ''.join(c for c in s if not unicodedata.combining(c))
    return re.sub(r'[^a-z0-9]+', '', s.lower())


def seiten(pdf):
    """-> [(nummer, text)] aller Seiten."""
    n = int(re.search(r'Pages:\s+(\d+)',
                      subprocess.run(['pdfinfo', pdf], capture_output=True, text=True).stdout).group(1))
    out = []
    for p in range(1, n + 1):
        t = subprocess.run(['pdftotext', '-layout', '-f', str(p), '-l', str(p), pdf, '-'],
                           capture_output=True, text=True).stdout
        out.append((p, t))
    return out


def positionen(seiten_liste):
    """-> {flacher Name: (lat, lon, seite)} aus den Tafelkoepfen."""
    out = {}
    for p, t in seiten_liste:
        zeilen = [z for z in t.split('\n')]
        for i, z in enumerate(zeilen):
            m = POS.search(z)
            if not m:
                continue
            name = ''
            for j in range(i - 1, max(-1, i - 4), -1):
                if zeilen[j].strip():
                    name = zeilen[j].strip()
                    break
            lat = (int(m.group(1)) + float(m.group(2).replace(',', '.')) / 60) * (1 if m.group(3) == 'N' else -1)
            lon = (int(m.group(4)) + float(m.group(5).replace(',', '.')) / 60) * (1 if m.group(6) == 'E' else -1)
            if name:
                out.setdefault(flach(name), (round(lat, 4), round(lon, 4), p))
    return out


def konstanten(seiten_liste):
    """-> [(hafen, land, {konstituente: (H, G)}, seite)] von der Konstantenseite."""
    out = []
    for p, t in seiten_liste:
        if 'CONSTANTES HARM' not in t.upper():
            continue
        land = None
        roh = t.split('\n')
        # Lange Namen stehen umgebrochen ("MOCÍMBOA DA PRAIA" / Zahlen darunter):
        # eine Zeile ohne Zahlen, deren naechste mit Zahlen beginnt, wird angehaengt.
        zeilen = []
        for i, z in enumerate(roh):
            z = FUEHRUNG.sub(' ', z)
            if (not re.search(r'\d', z) and z.strip() and i + 1 < len(roh)
                    and re.match(r'^[\s.]*\.?\d', FUEHRUNG.sub(' ', roh[i + 1]))):
                zeilen.append(z.rstrip(' .') + '  ' + FUEHRUNG.sub(' ', roh[i + 1]).strip(' .'))
                continue
            zeilen.append(z)
        for z in zeilen:
            kopf = z.strip().rstrip('.').strip()
            if kopf.upper() in LANDZONE:
                land = kopf.upper()
                continue
            m = ZEILE.match(z)
            if not m or land is None:
                continue
            name = ' '.join(m.group(1).split()).strip(' .')
            if flach(name) in ('porto', '') or name.upper() in LANDZONE:
                continue
            v = [float(x) for x in m.groups()[1:]]
            out.append((name, land, dict(M2=(v[0], v[1]), S2=(v[2], v[3]),
                                         K1=(v[4], v[5]), O1=(v[6], v[7])), p))
    return out


# Der Buchname der Konstantenzeile und die Ueberschrift der Tafel sind nicht
# immer gleich; hier steht, welche Tafel zu welcher Zeile gehoert.
TAFEL = {'quelimane': 'pontatangalanebarradequelimane',
         'antonioenes': 'angochaeantonioenes',
         'namibe': 'portodonamibemocamedes',
         'soyostoantoniodozaire': 'portodesoyosantoantoniodozaire',
         'palmeira': 'portodapalmeirailhadosal',
         'praia': 'portodapraiailhadesantiago',
         'portogrande': 'portogrande'}


def main(argv):
    pdf = argv[argv.index('--pdf') + 1] if '--pdf' in argv else PDF
    print('lese', os.path.relpath(pdf, ROOT), flush=True)
    sl = seiten(pdf)
    pos = positionen(sl)
    print(f'{len(pos)} Tafelkoepfe mit Position', flush=True)
    zeilen = []
    for name, land, k, seite in konstanten(sl):
        f = flach(name)
        treffer = pos.get(TAFEL.get(f, f))
        if not treffer:
            kand = [v for kk, v in pos.items() if f in kk or kk in f]
            treffer = kand[0] if kand else (None, None, None)
        z_h, z_q = zone_von(name, land)
        zeilen.append(dict(hafen=name, land=land.title(), lat=treffer[0], lon=treffer[1],
                           zone_h=z_h, zone_quelle=z_q, tafel_seite=treffer[2], konstanten_seite=seite,
                           **{f'{c}_{x}': k[c][i] for c in ('M2', 'S2', 'K1', 'O1')
                              for i, x in enumerate(('H', 'G'))}))
    felder = (['hafen', 'land', 'lat', 'lon', 'zone_h', 'zone_quelle', 'tafel_seite', 'konstanten_seite']
              + [f'{c}_{x}' for c in ('M2', 'S2', 'K1', 'O1') for x in ('H', 'G')])
    with open(AUS, 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=felder)
        w.writeheader()
        w.writerows(zeilen)
    ohne = [z['hafen'] for z in zeilen if z['lat'] is None]
    print(f'{len(zeilen)} Haefen -> {os.path.relpath(AUS, ROOT)}')
    if ohne:
        print('ohne Position:', ', '.join(ohne))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
