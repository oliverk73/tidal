#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Minimaler xlsx-Leser aus der Standardbibliothek.

openpyxl liess sich auf diesem Rechner nicht mehr installieren -- seit
dem Wechsel auf ein PEP-668-Python lehnt pip jede Installation ausserhalb
einer virtuellen Umgebung ab. Damit lief py/fit_icoe_vietnam.py nicht
mehr, und die 34 vietnamesischen Vorhersagereihen lagen unerreichbar in
zwei Arbeitsmappen.

Ein xlsx ist ein Zip aus XML. Gebraucht werden hier nur Blattnamen und
Zellwerte; Formeln, Formate und Datumstypen bleiben aussen vor. Zahlen
kommen als float zurueck, alles andere als Text.
"""
from __future__ import annotations

import re
import zipfile
import xml.etree.ElementTree as ET

NS = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
NSR = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'


def _strings(z):
    """Die gemeinsame Zeichenkettentabelle der Mappe."""
    if 'xl/sharedStrings.xml' not in z.namelist():
        return []
    return [''.join(t.text or '' for t in si.iter(NS + 't'))
            for si in ET.fromstring(z.read('xl/sharedStrings.xml'))]


def blaetter(z):
    """-> [(Name, Pfad im Zip)] in Mappenreihenfolge."""
    rels = {r.get('Id'): r.get('Target') for r in
            ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))}
    out = []
    for sh in ET.fromstring(z.read('xl/workbook.xml')).iter(NS + 'sheet'):
        ziel = rels[sh.get(NSR + 'id')].lstrip('/')
        out.append((sh.get('name'), ziel if ziel.startswith('xl/') else 'xl/' + ziel))
    return out


def namen(pfad):
    """-> Blattnamen der Mappe."""
    with zipfile.ZipFile(pfad) as z:
        return [b for b, _ in blaetter(z)]


def _spalte(bezug):
    """A1 -> 0, B1 -> 1, AA1 -> 26."""
    i = 0
    for ch in re.match(r'([A-Z]+)', bezug or 'A').group(1):
        i = i * 26 + ord(ch) - 64
    return i - 1


def zeilen(pfad, blatt):
    """-> Zeilen des Blattes als Listen von Werten (float oder str).

    Leerzellen sind None. Die Zeilen kommen einzeln, damit auch grosse
    Mappen nicht vollstaendig im Speicher stehen.
    """
    with zipfile.ZipFile(pfad) as z:
        sst = _strings(z)
        ziel = dict(blaetter(z)).get(blatt)
        if ziel is None:
            raise KeyError(blatt)
        for _ev, el in ET.iterparse(z.open(ziel)):
            if el.tag != NS + 'row':
                continue
            werte = {}
            for c in el.iter(NS + 'c'):
                v = c.find(NS + 'v')
                if c.get('t') == 'inlineStr':
                    txt = ''.join(t.text or '' for t in c.iter(NS + 't'))
                elif v is None or v.text is None:
                    continue
                elif c.get('t') == 's':
                    txt = sst[int(v.text)]
                else:
                    txt = v.text
                try:
                    werte[_spalte(c.get('r'))] = float(txt)
                except ValueError:
                    werte[_spalte(c.get('r'))] = txt
            el.clear()
            yield ([werte.get(i) for i in range(max(werte) + 1)] if werte else [])
