#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Liest die amtliche indonesische Gezeitentafel (Pushidrosal 2023) von den Scans.

tide_tables/indonesia/740852083-Tabel-Pasang-Surut-Kepulauan-Indonesia-2023-230-Mb.pdf
enthaelt fuer 100 Haefen STUENDLICHE Vorhersagen (Pushidrosal, aus 1148 Saetzen
eigener harmonischer Konstanten). Das PDF ist ein reiner Scan ohne Textebene;
gelesen wird deshalb mit tesseract.

Aufbau: je Station eine Kopfseite und sechs Tabellenseiten mit je zwei Monaten.
Jede Tabellenseite traegt Stationsnummer, Namen, Position und Zeitzone. Eine
Tagzeile hat 24 Stundenwerte in Metern mit einer Nachkommastelle (0.1 m Raster),
dazwischen Marken (+, *) fuer Hoch- und Niedrigwasser.

Gelesen wird zeilenweise; eine Tagzeile zaehlt nur, wenn genau 24 Werte
herauskommen und die Tagesnummer links und rechts uebereinstimmt. So bleiben
OCR-Fehler draussen, statt Werte zu erfinden.

Ergebnis: tide_tables/indonesia/pushidrosal2023/<nr>_<name>.json
          {"name":..., "lat":..., "lon":..., "tz":..., "tage": {"2023-01-01": [24 Werte], ...}}

Usage: venv/bin/python3 py/pushidrosal_ocr.py --seiten 53,54 [--ordner ...]
       venv/bin/python3 py/pushidrosal_ocr.py --alle
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PDF = os.path.join(ROOT, 'tide_tables/indonesia/740852083-Tabel-Pasang-Surut-Kepulauan-Indonesia-2023-230-Mb.pdf')
ZIEL = os.path.join(ROOT, 'tide_tables/indonesia/pushidrosal2023')
MONATE = {'JANUARI': 1, 'PEBRUARI': 2, 'FEBRUARI': 2, 'MARET': 3, 'APRIL': 4, 'MEI': 5, 'JUNI': 6,
          'JULI': 7, 'AGUSTUS': 8, 'SEPTEMBER': 9, 'OKTOBER': 10, 'NOVEMBER': 11, 'DESEMBER': 12}
TAGE_IM_MONAT = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]


def ocr(seite):
    with tempfile.TemporaryDirectory() as tmp:
        bild = os.path.join(tmp, 'p')
        subprocess.run(['pdftoppm', '-f', str(seite), '-l', str(seite), '-r', '300', '-png', PDF, bild],
                       check=True, capture_output=True)
        png = [os.path.join(tmp, f) for f in os.listdir(tmp) if f.endswith('.png')][0]
        r = subprocess.run(['tesseract', png, 'stdout', '--psm', '6'], capture_output=True, text=True)
        return r.stdout


def grad(text):
    """'01° 43'20.76" U/N' -> +1.7224 ; Richtung U/N, S, T/E, B/W."""
    m = re.search(r"(\d{1,3})\D{1,3}(\d{1,2})\D{1,3}([\d.]+)\D{0,4}([USTBNEW])", text)
    if not m:
        return None
    d = int(m.group(1)) + int(m.group(2)) / 60 + float(m.group(3)) / 3600
    return -d if m.group(4) in ('S', 'B', 'W') else d


def werte(zeile):
    """Stundenwerte einer Tagzeile -> (tag, [24 Werte]) oder None.

    Die OCR schreibt 0.7 als '07', 'O7' oder '0.7', dazu Marken wie '+' und '*'
    zwischen den Zahlen. Eine Zahl ist also ein bis drei Ziffern; 24 davon in
    der Mitte, links und rechts die Tagesnummer.
    """
    z = zeile.replace('O', '0').replace('o', '0').replace('«', ' ').replace('|', ' ')
    z = re.sub(r'[^0-9. ]', ' ', z)
    roh = []
    for t in z.split():
        for stueck in re.findall(r'\d+\.\d|\d+', t):
            roh.append(stueck)
    zahlen = []
    for s in roh:
        if '.' in s:
            zahlen.append(float(s))
        elif len(s) <= 2:
            zahlen.append(int(s) / 10.0)
        else:
            return None                 # verklebte Zahlen -- Zeile verwerfen
    if len(zahlen) < 26:
        return None
    tag_l, tag_r = zahlen[0] * 10, zahlen[-1] * 10
    if abs(tag_l - tag_r) > 0.001 or not 1 <= round(tag_l) <= 31:
        return None
    mitte = zahlen[1:-1]
    if len(mitte) != 24 or any(x < -1.0 or x > 9.0 for x in mitte):
        return None
    return round(tag_l), mitte


def spalten(profil, schwelle, mind=3):
    """Zusammenhaengende dunkle Bereiche eines Profils."""
    out, start = [], None
    for i, v in enumerate(profil):
        if v > schwelle and start is None:
            start = i
        elif v <= schwelle and start is not None:
            if i - start >= mind:
                out.append((start, i))
            start = None
    if start is not None:
        out.append((start, len(profil)))
    return out


def raster(block):
    """-> (Wertspalten, Zeilenbaender) einer Monatstabelle.

    Die Marken fuer Hoch- und Niedrigwasser stehen als schmale Spalten
    zwischen den Werten und kleben in der OCR an den Ziffern ("05405").
    Deshalb wird nicht die Seite gelesen, sondern jede Wertspalte einzeln
    ausgeschnitten und mit breiter Luecke neu gesetzt.
    """
    import numpy as np
    dunkel = block < 128
    sp = dunkel.sum(0)
    ziffern = [c for c in spalten(sp, max(3, sp.max() // 25)) if c[1] - c[0] >= 11]
    if len(ziffern) < 40:
        return None, None, None
    gruppen = [[ziffern[0]]]
    for c in ziffern[1:]:
        (gruppen[-1].append(c) if c[0] - gruppen[-1][-1][1] <= 20 else gruppen.append([c]))
    gruppen = [(g[0][0], g[-1][1]) for g in gruppen]
    werte = [g for g in gruppen if 20 <= g[1] - g[0] <= 60]
    if len(werte) != 24:
        return None, None, None
    # Tagesspalte: die schmale Gruppe links der Werte -- sie kommt mit ins
    # zusammengesetzte Bild, sonst verrutscht die Zuordnung, sobald eine
    # Zeile verworfen wird.
    links = [g for g in gruppen if g[1] <= werte[0][0] and g[1] - g[0] < 45]
    tagspalte = links[-1] if links else None
    zp = dunkel[:, werte[0][0]:werte[-1][1]].sum(1)
    zeilen = [z for z in spalten(zp, 3, mind=12) if z[1] - z[0] > 15]
    return tagspalte, werte, zeilen


def tabelle_lesen(block):
    """-> [(zeilennummer, [24 Werte])] einer Monatstabelle."""
    import numpy as np
    from PIL import Image
    tagspalte, werte, zeilen = raster(block)
    if not werte or not zeilen or not tagspalte:
        return []
    spaltenliste = [tagspalte] + werte
    luecke, hoehe = 45, max(z[1] - z[0] for z in zeilen) + 12
    breite = sum(g[1] - g[0] + luecke for g in spaltenliste) + 60
    bild = Image.new('L', (breite, (hoehe + 18) * len(zeilen) + 40), 255)
    for i, (r0, r1) in enumerate(zeilen):
        x = 30
        for c0, c1 in spaltenliste:
            aus = Image.fromarray(block[max(0, r0 - 6):r1 + 6, max(0, c0 - 3):c1 + 3])
            bild.paste(aus, (x, 20 + i * (hoehe + 18)))
            x += (c1 - c0) + luecke
    with tempfile.TemporaryDirectory() as tmp:
        pfad = os.path.join(tmp, 'z.png')
        bild.save(pfad)
        t = subprocess.run(['tesseract', pfad, 'stdout', '--psm', '6',
                            '-c', 'tessedit_char_whitelist=0123456789. '],
                           capture_output=True, text=True).stdout
    out = []
    for z in t.split('\n'):
        tokens = z.split()
        if len(tokens) != 25:
            continue
        tag = re.sub(r'[^0-9]', '', tokens[0])
        if not tag or not 1 <= int(tag) <= 31:
            continue
        v = []
        for tk in tokens[1:]:
            d = re.sub(r'[^0-9]', '', tk)
            if len(d) == 2:
                v.append(int(d) / 10.0)
            elif len(d) == 3 and d[0] in '0123':
                v.append(int(d[:2]) / 10.0)
            else:
                v = None
                break
        if v and max(abs(v[i + 1] - v[i]) for i in range(23)) <= 0.6:
            out.append((int(tag), v))
    return out


def seite_lesen(seite):
    """-> dict mit Kopfangaben und {datum: [24 Werte]} einer Tabellenseite."""
    import numpy as np
    from PIL import Image
    with tempfile.TemporaryDirectory() as tmp:
        bild = os.path.join(tmp, 'p')
        subprocess.run(['pdftoppm', '-f', str(seite), '-l', str(seite), '-r', '300', '-png', PDF, bild],
                       check=True, capture_output=True)
        png = [os.path.join(tmp, f) for f in os.listdir(tmp) if f.endswith('.png')][0]
        grau = np.array(Image.open(png).convert('L'))
        kopftext = subprocess.run(['tesseract', png, 'stdout', '--psm', '6'],
                                  capture_output=True, text=True).stdout
    zeilen = kopftext.split('\n')
    kopf = ' '.join(zeilen[:8])
    m = re.search(r'(\d{1,3})\s*[.,]\s*([A-Z][A-Z .\'/-]{2,40})', kopf)
    nr = int(m.group(1)) if m else None
    name = re.sub(r'\s+', ' ', m.group(2)).strip(" .'-") if m else None
    mp = re.search(r"(\d{1,3}\D{1,3}\d{1,2}\D{1,3}[\d.]+\D{0,4}[US])\D{0,4}(\d{1,3}\D{1,3}\d{1,2}\D{1,3}[\d.]+\D{0,4}[TB])", kopf)
    lat, lon = (grad(mp.group(1)), grad(mp.group(2))) if mp else (None, None)
    mz = re.search(r'G\.?M\.?T\.?\s*\+?\s*(\d{2})', kopf)
    tz = int(mz.group(1)) if mz else None
    # Monatsnamen in der Reihenfolge ihres Auftretens (oben, unten)
    folge = []
    for z in zeilen:
        g = z.upper()
        for mo, nummer in MONATE.items():
            if mo in g and nummer not in folge:
                folge.append(nummer)
    h = grau.shape[0]
    bloecke = [(int(h * 0.09), int(h * 0.48)), (int(h * 0.49), int(h * 0.93))]
    tage = {}
    for i, (y0, y1) in enumerate(bloecke):
        if i >= len(folge):
            break
        monat = folge[i]
        for tag, v in tabelle_lesen(grau[y0:y1]):
            if tag <= TAGE_IM_MONAT[monat - 1]:
                tage[f'2023-{monat:02d}-{tag:02d}'] = v
    return dict(seite=seite, nr=nr, name=name, lat=lat, lon=lon, tz=tz, monate=folge, tage=tage)


def main(argv):
    os.makedirs(ZIEL, exist_ok=True)
    if '--seiten' in argv:
        seiten = [int(x) for x in argv[argv.index('--seiten') + 1].split(',')]
    else:
        seiten = range(18, 716)
    sammlung = {}
    for s in seiten:
        d = seite_lesen(s)
        if not d['tage']:
            print(f'  Seite {s}: keine Tagzeilen ({d["name"]})', flush=True)
            continue
        soll = sum(TAGE_IM_MONAT[m - 1] for m in d['monate'])
        print(f"  Seite {s:4} {str(d['nr']):>4}. {str(d['name'])[:26]:26} {d['lat']} {d['lon']} GMT+{d['tz']} "
              f"Monate {d['monate']} {len(d['tage'])}/{soll} Tage", flush=True)
        schl = (d['nr'], d['name'])
        eintrag = sammlung.setdefault(schl, dict(nr=d['nr'], name=d['name'], lat=d['lat'], lon=d['lon'],
                                                 tz=d['tz'], seiten=[], tage={}))
        eintrag['seiten'].append(s)
        eintrag['tage'].update(d['tage'])
        for feld in ('lat', 'lon', 'tz'):
            if eintrag[feld] is None:
                eintrag[feld] = d[feld]
    for (nr, name), d in sammlung.items():
        datei = os.path.join(ZIEL, f"{nr or 0:03d}_{re.sub(r'[^A-Za-z0-9]+', '_', name or 'unbekannt').strip('_').lower()}.json")
        alt = json.load(open(datei)) if os.path.exists(datei) else None
        if alt:
            alt['tage'].update(d['tage'])
            alt['seiten'] = sorted(set(alt['seiten']) | set(d['seiten']))
            d = alt
        json.dump(d, open(datei, 'w'), ensure_ascii=False)
        print(f"{os.path.basename(datei)}: {len(d['tage'])} Tage")
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
