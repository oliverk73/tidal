#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Liest die amtliche Gezeitentafel des Instituto Hidrográfico (Tabela de Marés 2026).

tide_tables/Portugal/TabelaMare_I_2026_signed.pdf enthaelt je Standardhafen vier
Seiten mit Hoch- und Niedrigwassern (Uhrzeit in UT, Hoehe ueber Zero
Hidrografico) und am Ende die harmonischen Konstanten M2, S2, K1, O1 aus den
Pegelanalysen des IH (Phasen in UT, also Greenwich).

Aufbau einer Seite: Kopf "Porto de <Name>", eine Zeile mit drei Monatsnamen, je
Monat zwei Spalten (Tag 1-16, Tag 17-31), je Tag ein Block aus bis zu vier
Zeilen "hh:mm  h.h". Bloecke sind durch Leerzeilen getrennt. Die Spalte ergibt
sich aus der Zeichenposition in pdftotext -layout.

Usage: python3 py/ih_portugal_tafel.py [Hafen]   -> Scheitelanzahl je Hafen
"""
from __future__ import annotations

import datetime as dt
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PDF = os.path.join(ROOT, 'tide_tables/Portugal/TabelaMare_I_2026_signed.pdf')
MONATE = {'JANEIRO': 1, 'FEVEREIRO': 2, 'MARÇO': 3, 'ABRIL': 4, 'MAIO': 5, 'JUNHO': 6, 'JULHO': 7,
          'AGOSTO': 8, 'SETEMBRO': 9, 'OUTUBRO': 10, 'NOVEMBRO': 11, 'DEZEMBRO': 12}
PAAR = re.compile(r'(\d{2}):(\d{2})\s+(-?\d\.\d)')
_TEXT = None


def text():
    global _TEXT
    if _TEXT is None:
        _TEXT = subprocess.run(['pdftotext', '-layout', PDF, '-'], capture_output=True,
                               text=True).stdout.split('\n')
    return _TEXT


def scheitel(hafen):
    """-> [(unix-zeit, hoehe m)] aller Hoch- und Niedrigwasser 2026 fuer 'Porto de <hafen>'."""
    L = text()
    out = []
    starts = [i for i, l in enumerate(L) if l.strip() == f'Porto de {hafen}']
    for s in starts:
        i = s
        monate = None
        while i < len(L) and monate is None:
            w = [m for m in re.findall(r'[A-ZÇ]{4,}', L[i]) if m in MONATE]
            if len(w) >= 1 and 'Hora' not in L[i]:
                monate = [MONATE[m] for m in w]
            i += 1
        # Spaltenpositionen aus der Zeile "Hora Altura"
        while i < len(L) and 'Hora' not in L[i]:
            i += 1
        spalten = [m.start() for m in re.finditer(r'Hora', L[i])]
        i += 1
        block, im_block = 0, False
        while i < len(L) and not L[i].strip().startswith('Porto de') and block < 17:
            treffer = list(PAAR.finditer(L[i]))
            if treffer:
                im_block = True
                for m in treffer:
                    c = min(range(len(spalten)), key=lambda k: abs(spalten[k] - m.start()))
                    mon = monate[min(c // 2, len(monate) - 1)]
                    tag = 1 + block if c % 2 == 0 else 17 + block
                    try:
                        t = dt.datetime(2026, mon, tag, int(m.group(1)), int(m.group(2)),
                                        tzinfo=dt.timezone.utc)
                    except ValueError:
                        continue
                    out.append((t.timestamp(), float(m.group(3))))
            elif not L[i].strip():
                if im_block:
                    block += 1
                    im_block = False
            elif re.search(r'\d\s*[–-]\s*\d', L[i]) and 'Hora' not in L[i]:
                break                                   # Seitenzahl -> Seite zu Ende
            i += 1
    return sorted(set(out))


def konstanten():
    """{Hafen (Grossbuchstaben): {c: (amp m, G)}} aus der Tabelle der Konstanten."""
    out = {}
    for l in text():
        m = re.match(r'^([A-ZÇÃÕÉÍÓÚÂÊ .\-]+?)\s+(\.\d{3}|\d\.\d{3})\s+([\d.]+)\s+(\.\d{3})\s+([\d.]+)\s+(\.\d{3})\s+([\d.]+)\s+(\.\d{3})\s+([\d.]+)\s*$', l.replace('\t', ' '))
        if m:
            v = [float(x) for x in m.groups()[1:]]
            out[m.group(1).strip()] = {'M2': (v[0], v[1]), 'S2': (v[2], v[3]), 'K1': (v[4], v[5]), 'O1': (v[6], v[7])}
    return out


if __name__ == '__main__':
    hafen = sys.argv[1] if len(sys.argv) > 1 else 'Faro-Olhão'
    s = scheitel(hafen)
    print(hafen, len(s), 'Scheitel', dt.datetime.utcfromtimestamp(s[0][0]), dt.datetime.utcfromtimestamp(s[-1][0]))
    print(sorted(konstanten().keys()))
