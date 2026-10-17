#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Liest die Tidenkalender der Payra Port Authority (Rabnabad-Kanal, Bangladesch).

Oliver 17.10.2026: Die PDFs lagen seit Juni in tide_tables/bangladesh/payra (ppa_*.pdf), Payra fehlte
im Bestand. Jede Seite: Monat/Jahr, zwei oder drei Pegel nebeneinander (Charipara, Kauar Char,
Monopile-1, Monopile-2, aelter auch Ander Manik), je Tag ein Block mit Hoch-/Niedrigwasser
"HHMM h.hh". Zeiten in Ortszeit UTC+6, Hoehen ueber Pegelnull (~LAT).

Zuordnung: jede Zahlengruppe gehoert zur naechstgelegenen Spaltenueberschrift; das Datum folgt den
gedruckten Tagesnummer des Blocks (fehlende Seiten verschieben so nichts), sonst dem Uhrzeitlauf.

Usage: python3 py/payra_tafeln.py  -> tide_tables/bangladesh/payra/payra_hwlw.json  {Pegel: [[iso_utc, m], ...]}
"""
import collections
import datetime as dt
import glob
import json
import os
import re
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORDNER = os.path.join(ROOT, 'tide_tables/bangladesh/payra')
MONATE = {m: i + 1 for i, m in enumerate(['JANUARY', 'FEBRUARY', 'MARCH', 'APRIL', 'MAY', 'JUNE', 'JULY',
                                          'AUGUST', 'SEPTEMBER', 'OCTOBER', 'NOVEMBER', 'DECEMBER'])}
MONATE['SEPEMBER'] = 9
PEGEL = {'CHARIPARA': 'Charipara', 'KAURCHAR': 'Kauar Char', 'KAUAR': 'Kauar Char', 'MONOPILE-1': 'Monopile-1',
         'MONOPILE-2': 'Monopile-2', 'ANDER': 'Ander Manik', 'ANDERMANIK': 'Ander Manik'}
TAG = re.compile(r'^\s{0,3}(\d{1,2})(?:[A-Z]{1,2})?(?=\s|$)')
PAAR = re.compile(r'(?<!\d)([0-2]\d[0-5]\d)\s+(-?\d\.\d{2})(?!\d)')


def seiten(pdf):
    txt = subprocess.run(['pdftotext', '-layout', pdf, '-'], capture_output=True, encoding='utf-8', errors='ignore').stdout
    return txt.split('\f')


def main():
    erg = collections.defaultdict(lambda: collections.defaultdict(dict))   # Pegel -> (Monat, PDF) -> {t: h}
    for pdf in sorted(glob.glob(os.path.join(ORDNER, 'ppa_*.pdf'))):
        stand = {}                                        # Pegel -> (Jahr, Monat, Tag, letzte Minute)
        for s in seiten(pdf):
            z = s.split('\n')
            kopf = next((l for l in z[:8] if re.search(r'(%s)\s*-?\s*(20\d\d)' % '|'.join(MONATE), l.upper())
                         and not re.search(r'\bTO\b', l.upper())), None)   # Titel 'SEPTEMBER TO DECEMBER 2021' ueberspringen
            if not kopf:
                continue
            m = re.search(r'(%s)\s*-?\s*(20\d\d)' % '|'.join(MONATE), kopf.upper())
            jahr, monat = int(m.group(2)), MONATE[m.group(1)]
            spalten = []
            for l in z[:8]:
                for w in re.finditer(r'[A-Z][A-Z\-0-9]+', l.upper()):
                    k = w.group(0).replace(' ', '')
                    if k in PEGEL and all(abs(w.start() - c) > 5 for c, _ in spalten):
                        spalten.append((w.start() + len(k) / 2, PEGEL[k]))
            if not spalten:
                continue
            # Uhrzeitlauf je Spalte; eine gedruckte Tagesnummer (links am Zeilenanfang, neben dem ersten oder
            # zweiten Scheitel des Tages) zieht die Zaehlung nach -- fehlende Seiten verschieben so nichts.
            # Ein Tag wird erst geschrieben, wenn er abgeschlossen ist (Uhrzeitruecksprung oder Seitenende).
            offen = {}                                # Spalte -> [(Minute, Hoehe)] des laufenden Tages

            def schreibe(col):
                j, mo, tag, _ = stand[col]
                for mi, hh in offen.get(col, []):
                    try:
                        t = dt.datetime(j, mo, tag, mi // 60, mi % 60) - dt.timedelta(hours=6)
                    except ValueError:
                        continue                      # Tag > Monatslaenge: Lesefehler
                    erg[col][('%04d-%02d' % (j, mo), os.path.basename(pdf))][t.isoformat() + 'Z'] = hh
                offen[col] = []

            for l in z:
                t_ = TAG.match(l)
                for p in PAAR.finditer(l):
                    col = min(spalten, key=lambda c: abs(c[0] - p.start()))[1]
                    hhmm, h = p.group(1), float(p.group(2))
                    minute = int(hhmm[:2]) * 60 + int(hhmm[2:])
                    if col not in stand or stand[col][:2] != (jahr, monat):
                        stand[col] = (jahr, monat, 1, -1)
                        offen[col] = []
                    j, mo, tag, letzte = stand[col]
                    if minute < letzte:
                        schreibe(col)
                        tag += 1
                    stand[col] = (j, mo, tag, minute)
                    offen.setdefault(col, []).append((minute, h))
                if t_ and 1 <= int(t_.group(1)) <= 31:
                    n = int(t_.group(1))
                    for _, col in spalten:
                        if col in stand and stand[col][:2] == (jahr, monat):
                            j, mo, tag, letzte = stand[col]
                            stand[col] = (j, mo, n, letzte)
            for _, col in spalten:
                if col in stand:
                    schreibe(col)
    # Dezember 2021/2022 stehen in zwei Ausgaben: je Pegel und Monat nur die vollstaendigste Ausgabe
    out = {}
    for k, v in erg.items():
        wahl = {}
        for (mon, pdf), ev in v.items():
            if mon not in wahl or len(ev) > len(v[(mon, wahl[mon])]):
                wahl[mon] = pdf
        alle = {}
        for mon, pdf in wahl.items():
            alle.update(v[(mon, pdf)])
        # Seiten mit falscher Ueberschrift (z. B. Monopile-Seite als KAURCHAR, Feb. 2025) erzeugen Tage mit
        # mehr als 6 Scheiteln -- diese Tage ganz verwerfen
        tage = collections.Counter((dt.datetime.fromisoformat(t[:-1]) + dt.timedelta(hours=6)).date() for t in alle)
        out[k] = sorted((t, h) for t, h in alle.items()
                        if tage[(dt.datetime.fromisoformat(t[:-1]) + dt.timedelta(hours=6)).date()] <= 6)
    pfad = os.path.join(ORDNER, 'payra_hwlw.json')
    json.dump(out, open(pfad, 'w'), indent=0)
    for k, v in out.items():
        print('%-12s %5d Scheitel  %s .. %s' % (k, len(v), v[0][0][:10], v[-1][0][:10]))


if __name__ == '__main__':
    main()
