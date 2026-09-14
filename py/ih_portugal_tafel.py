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
PDF_II = os.path.join(ROOT, 'tide_tables/Portugal/TabelaMare_II_2026_signed.pdf')
PDF_2025 = os.path.join(ROOT, 'tide_tables/Portugal/TabMares_I_2025_completa_signed-1.pdf')
_TEXT = {}


def text(pdf=None):
    pdf = pdf or PDF
    if pdf not in _TEXT:
        _TEXT[pdf] = subprocess.run(['pdftotext', '-layout', pdf, '-'], capture_output=True,
                                    text=True).stdout.split('\n')
    return _TEXT[pdf]


def jahr(pdf):
    m = re.search(r'(20\d\d)', os.path.basename(pdf or PDF))
    return int(m.group(1)) if m else 2026


def haefen(pdf=None):
    """{Hafen: (lat, lon)} aus den Kopfzeilen 'Porto de ...' + 'Latitude ... Longitude ...'."""
    L = text(pdf); out = {}
    for i, l in enumerate(L[:-1]):
        if l.strip().startswith('Porto de ') and 'Latitude' in L[i + 1]:
            m = re.search(r"Latitude\s+(\d+)º\s+([\d.]+)'\s*([NS])\s+Longitude\s+(\d+)º\s+([\d.]+)'\s*([EW])", L[i + 1])
            if m and l.strip()[9:] not in out:
                la = (int(m.group(1)) + float(m.group(2)) / 60) * (1 if m.group(3) == 'N' else -1)
                lo = (int(m.group(4)) + float(m.group(5)) / 60) * (1 if m.group(6) == 'E' else -1)
                out[l.strip()[9:]] = (la, lo)
    return out


def scheitel(hafen, pdf=None):
    """-> [(unix-zeit, hoehe m)] aller Hoch- und Niedrigwasser fuer 'Porto de <hafen>' (Zeiten in UT)."""
    L = text(pdf)
    J = jahr(pdf)
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
                        t = dt.datetime(J, mon, tag, int(m.group(1)), int(m.group(2)),
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


# Die Tabelle "Constantes harmonicas fundamentais" nennt keinen Phasenbezug (Vol. II: siehe unten). Fuer das Festland und
# Madeira sind es Greenwich-Phasen (UT); fuer die Azoren sind sie auf die Ortszone UT-1 bezogen:
# alle Messsaetze dort (TICON, UHSLC) liegen gegen diese Werte einheitlich 56-64 min "spaet",
# waehrend dieselben Saetze die Tafelzeiten (in UT) auf 0-2 min treffen (14.09.2026).
ZONE_H = {'VILA DO PORTO': -1.0, 'PONTA DELGADA': -1.0, 'ANGRA DO HEROÍSMO': -1.0, 'HORTA': -1.0,
          'LAJES DAS FLORES': -1.0, 'PORTO GRANDE': -1.0,
          # Vol. II: Angola in UT+1, Mocambique in UT+2 (gegen die eigenen Tafeln: 60-68 bzw. >120 min
          # daneben mit UT, 1-4 min mit Ortszone; 14.09.2026)
          'LUANDA': 1.0, 'LOBITO': 1.0, 'NAMIBE': 1.0,
          'MAPUTO': 2.0, 'INHAMBANE': 2.0, 'CHINDE': 2.0, 'QUELIMANE': 2.0, 'PEBANE': 2.0,
          'ANTÓNIO ENES': 2.0, 'ILHA DE MOÇAMBIQUE': 2.0, 'NACALA': 2.0, 'PEMBA': 2.0}
SPEED = {'M2': 28.9841042, 'S2': 30.0, 'K1': 15.0410686, 'O1': 13.9430356}


def konstanten(pdf=None):
    """{Hafen (Grossbuchstaben): {c: (amp m, G Greenwich)}} aus der Tabelle der Konstanten."""
    out = {}
    for l in text(pdf):
        m = re.match(r'^([A-ZÇÃÕÉÍÓÚÂÊ .\-]+?)\s+(\.\d{3}|\d\.\d{3})\s+([\d.]+)\s+(\.\d{3})\s+([\d.]+)\s+(\.\d{3})\s+([\d.]+)\s+(\.\d{3})\s+([\d.]+)\s*$', l.replace('\t', ' '))
        if m:
            v = [float(x) for x in m.groups()[1:]]
            name = m.group(1).strip()
            z = ZONE_H.get(name.split(' .')[0].strip(), 0.0)
            roh = {'M2': (v[0], v[1]), 'S2': (v[2], v[3]), 'K1': (v[4], v[5]), 'O1': (v[6], v[7])}
            # g_Ortszone = G + speed * zone  ->  G = g - speed * zone
            out[name] = {c: (a, (g - SPEED[c] * z) % 360.0) for c, (a, g) in roh.items()}
    return out


if __name__ == '__main__':
    hafen = sys.argv[1] if len(sys.argv) > 1 else 'Faro-Olhão'
    s = scheitel(hafen)
    print(hafen, len(s), 'Scheitel', dt.datetime.utcfromtimestamp(s[0][0]), dt.datetime.utcfromtimestamp(s[-1][0]))
    print(sorted(konstanten().keys()))
