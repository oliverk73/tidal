#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Liest die Gezeitentafeln der mexikanischen SEMAR.

Die Secretaria de Marina veroeffentlicht je Hafen ein PDF mit einem
vollen Jahr, eine Seite je Monat. Unter tide_tables/mexico_semar/ liegen
32 Haefen fuer 2024, 2025 und 2026 -- drei volle Jahrgaenge, genug zum
Messen und zum Neurechnen.

Gelesen wird ueber Wortkoordinaten, nicht ueber den Textfluss. Die Seite
traegt drei Tagesspalten nebeneinander (1.-10., 11.-20., 21.-31.), und
der Textfluss verschraenkt sie: auf "1 0620 -0.69 -0.21" folgt dort
sofort der 11. und der 21. Wer den Fluss liest, klebt drei Tage
aneinander.

Innerhalb einer Spalte entscheidet die Gestalt des Wortes, was es ist --
vierstellig ist eine Uhrzeit, mit Punkt eine Hoehe, ein- oder zweistellig
der Tag. Das ist sicherer als die x-Mitte, weil die Spaltenkoepfe links,
die Werte aber rechts ausgerichtet sind: "METROS" steht bei x=139, seine
Zahlen bei x=151.

Die Zeitzone muss nicht erraten werden, die Tafel nennt sie auf jeder
Seite selbst ("HORA DEL MERIDIANO LOCAL 90° W"). Der Wert ist nicht
ueberall der geografisch naechste -- Caleta de Campos in Michoacan steht
auf 90° W --, aber er ist der, auf den die Tafel sich bezieht. Ob er
stimmt, zeigt die Messung: ein Datensatz, der sonst passt, haette dann
einen Versatz von vollen Stunden.

Von den beiden Hoehenspalten wird PIES genommen und selbst umgerechnet,
nicht METROS. Die Meterspalte ist naemlich nichts anderes als die auf
Zentimeter gerundete Fussspalte -- 0.30 ft stehen dort als 0.09 m,
obwohl es 0.0914 m sind. Fuss hat mit 0.01 ft rund drei Millimeter
Aufloesung, Meter nur einen Zentimeter.

Erwartet hatte ich davon einiges: in Cozumel betraegt der Hub 28
Zentimeter, die Rundung allein also 3.6 Prozent davon -- mehr als der
ganze Fehler, den wir sonst messen. Gebracht hat es nichts. Ueber alle
35 gemessenen Saetze bleibt der Median bei 2.18 Prozent, zehn werden
minimal besser, acht minimal schlechter. Die Rundung ist also nicht die
Grenze; was an Abweichung bleibt, hat andere Gruende (die Tafeln sind
nicht rein harmonisch, und aus Hoch- und Niedrigwasser allein laesst
sich nicht mehr herausholen).

Genommen wird trotzdem die feinere Spalte -- dieselbe Groesse mit
weniger Rauschen kostet nichts. Wer hier ansetzen will, um die
mexikanischen Saetze zu verbessern, sei gewarnt: an der Rundung liegt
es nicht.

Usage: python3 py/semar_referenz.py             Uebersicht
       python3 py/semar_referenz.py <text>      einen Hafen zeigen
"""
from __future__ import annotations

import datetime as dt
import glob
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEMAR = os.path.join(ROOT, 'tide_tables/mexico_semar')

MONATE = ['ENERO', 'FEBRERO', 'MARZO', 'ABRIL', 'MAYO', 'JUNIO', 'JULIO',
          'AGOSTO', 'SEPTIEMBRE', 'OCTUBRE', 'NOVIEMBRE', 'DICIEMBRE']
MERIDIAN = re.compile(r'MERIDIANO LOCAL\s+(\d+)\s*°?\s*W')
UHR = re.compile(r'^([012]\d|\d)([0-5]\d)$')
ZAHL = re.compile(r'^-?\d+\.\d+$')
TAG = re.compile(r'^([1-9]|[12]\d|3[01])$')

# Vergleichszeitraum und Fit-Jahr.
VON = dt.datetime(2026, 7, 1)
BIS = dt.datetime(2026, 8, 1)
JAHR = 2026


def _seiten(pfad):
    import pymupdf
    with pymupdf.open(pfad) as d:
        for s in d:
            yield s.get_text('words'), s.get_text()


def _gruppen(woerter):
    """Grenzen der drei Tagesspalten aus den Spaltenkoepfen.

    Gesucht wird "DÍA"; davon gibt es drei, und zwischen ihnen liegen die
    Grenzen. Aus der Kopfzeile abgeleitet und nicht fest verdrahtet, damit
    ein anderes Seitenformat nicht stillschweigend danebengreift.
    """
    tage = sorted(x[0] for x in woerter
                  if x[4].upper().rstrip(':') in ('DÍA', 'DIA'))
    if len(tage) < 2:
        return None
    # Die Grenze gehoert VOR jede Tagesspalte, nicht zwischen zwei
    # DÍA-Koepfe: eine Gruppe reicht vom Tag bis zu ihrer Meterspalte,
    # und eine Grenze in der Mitte zwischen zwei DÍA schnitte sie
    # mitten durch -- PIES und METROS der ersten Gruppe faenden sich in
    # der zweiten wieder, und uebrig blieben ein paar Zeilen am
    # Monatsende.
    return [t - 10 for t in tage] + [10 ** 6]


def _monat(woerter, text):
    """Monat, Jahr und Bezugsmeridian der Seite.

    Monat und Jahr kommen aus der Kopfzeile, die ueber ihre y-Lage
    gefunden wird -- nicht aus dem Seitentext. Im Text stehen 1400
    Uhrzeiten, und jede zweite davon sieht aus wie eine Jahreszahl:
    "2006" ist 20:06. Ein Jahresregex ueber die ganze Seite holt sich
    prompt das Jahr 2006 aus einer Abendtide.
    """
    m = MERIDIAN.search(text)
    md = int(m.group(1)) if m else None
    kopf = ' '.join(w for _x, _y, _a, _b, w, *_ in
                    sorted((x for x in woerter if x[1] < 58),
                           key=lambda q: q[0])).upper()
    mon = next((i for i, n in enumerate(MONATE, 1) if n in kopf), None)
    j = re.search(r'\b(20\d\d)\b', kopf)
    return mon, int(j.group(1)) if j else None, md


def _seite_lesen(woerter, text):
    """-> [(datetime Ortszeit, hoehe_m)] einer Monatsseite."""
    mon, jahr, md = _monat(woerter, text)
    gr = _gruppen(woerter)
    if not (mon and jahr and gr):
        return [], None
    # Zeilen ueber die y-Mitte bilden; die Werte einer Zeile stehen
    # innerhalb eines halben Punktes beieinander.
    zeilen = {}
    for x0, y0, _x1, _y1, w, *_ in woerter:
        if y0 < 70:
            continue
        zeilen.setdefault(round(y0, 1), []).append((x0, w.strip()))
    aus = []
    tag_je_gruppe = {}
    for y in sorted(zeilen):
        for g in range(len(gr) - 1):
            teil = sorted((x, w) for x, w in zeilen[y] if gr[g] <= x < gr[g + 1])
            worte = [w for _x, w in teil]
            tag = next((int(w) for w in worte[:1] if TAG.match(w)), None)
            if tag is not None:
                tag_je_gruppe[g] = tag
                worte = worte[1:]
            uhr = next((w for w in worte if UHR.match(w)), None)
            zahlen = [w for w in worte if ZAHL.match(w)]
            if not uhr or len(zahlen) < 2 or g not in tag_je_gruppe:
                continue
            m = UHR.match(uhr)
            std, minute = int(m.group(1)), int(m.group(2))
            if std > 23:
                continue
            try:
                d = dt.date(jahr, mon, tag_je_gruppe[g])
            except ValueError:
                continue
            # zahlen = [PIES, METROS]; genommen wird PIES.
            hoehe = (float(zahlen[0]) * 0.3048 if len(zahlen) >= 2
                     else float(zahlen[-1]))
            aus.append((dt.datetime.combine(d, dt.time(std, minute)), hoehe))
    return aus, md


def _datei_lesen(pfad):
    """-> ([(datetime UTC, hoehe_m)], meridian_grad)"""
    ev, md = [], None
    for woerter, text in _seiten(pfad):
        teil, m = _seite_lesen(woerter, text)
        if m is not None:
            md = m
        ev += teil
    if md is None:
        return [], None
    # Der Meridian gibt den Versatz: 90° W ist UTC-6.
    versatz = dt.timedelta(hours=md / 15.0)
    return sorted(set((z + versatz, h) for z, h in ev)), md


_PUFFER = {}


def datei(pfad):
    if pfad not in _PUFFER:
        _PUFFER[pfad] = _datei_lesen(pfad)
    return _PUFFER[pfad]


def _name(pfad):
    import pymupdf
    with pymupdf.open(pfad) as d:
        w = d[0].get_text('words')
    kopf = [x[4] for x in sorted([x for x in w if x[1] < 58], key=lambda x: x[0])]
    t = ' '.join(kopf)
    t = re.sub(r'^\s*ESTACI[ÓO]N\s*', '', t)
    for n in MONATE:
        t = re.sub(rf'\s*{n}\s*20\d\d\s*$', '', t, flags=re.I)
    return t.strip().rstrip(',')


def stationen():
    """-> [{'code','tafel','name','lat','lon','meridian','dateien'}]"""
    import health_check
    VORRANG = ('harmonics_utide_tidetables.txt', 'harmonics_utide_observations.txt',
               'harmonics-dwf-20251228-free.txt')
    recs = {}
    for r in health_check.load_records():
        if r['lat'] is None or r['current']:
            continue
        d = os.path.basename(r['file'])
        rang = VORRANG.index(d) if d in VORRANG else len(VORRANG)
        if r['name'] not in recs or rang < recs[r['name']][0]:
            recs[r['name']] = (rang, r)
    aus = []
    for ordner in sorted(os.listdir(SEMAR)):
        ps = sorted(glob.glob(os.path.join(SEMAR, ordner, '*.pdf')))
        if not ps:
            continue
        tafel = _name(ps[-1])
        name = ORTE.get(ordner)
        r = recs.get(name) if name else None
        aus.append({'code': ordner, 'tafel': tafel, 'name': name,
                    'lat': r[1]['lat'] if r else None,
                    'lon': r[1]['lon'] if r else None,
                    'dateien': ps})
    return aus


# Ordner -> Satzname im Bestand, aus dem die Position kommt. Die Tafel
# selbst nennt keine.
#
# Fuenf Eintraege sind von Hand gesetzt, weil der Namensvergleich sie
# verfehlt oder -- schlimmer -- sicher danebengreift:
#   Ptomatamoros  "Puerto Matamoros" trifft "Puerto Morelos" in Yucatan
#   cozumel       heisst im Bestand "San Miguel de Cozumel"
#   guayabitos    heisst dort "Rincon de Guayabitos"
#   ptocortes     Puerto Cortes gibt es zweimal: der beste Namenstreffer
#                 ist der HONDURANISCHE, gemeint ist der in Baja
#                 California Sur -- 3000 km entfernt an der anderen Kueste
#   vicente       "Pto. Vicente Guerrero" gegen "Puerto Vicente Guerrero"
ORTE = {
    'Ptomatamoros': 'Matamoros, Tamaulipas, México',
    'altamira': 'Altamira, Tamaulipas, Mexico',
    'altata': 'Altata, Sinaloa, Mexico',
    'asuncion': 'Bahía Asunción, Baja California Sur, Mexico',
    'caleta': 'Caleta de Campos, Michoacán, Mexico',
    'chacala': 'Chacala, Nayarit, Mexico',
    'champoton': 'Champotón, Campeche, Mexico',
    'coatza': 'Coatzacoalcos, Veracruz, Mexico',
    'cozumel': 'San Miguel de Cozumel, Quintana Roo, México',
    'dosbocas': 'Dos Bocas, Tabasco, Mexico',
    'frontera': 'Frontera, Tabasco, Mexico',
    'guayabitos': 'Rincón de Guayabitos, Nayarit, Mexico',
    'iclarion': 'Isla Clarión, Colima, Mexico',
    'icoronado': 'Isla Coronados, Baja California, Mexico',
    'imarias': 'Islas Marías, Nayarit, Mexico',
    'imujeres': 'Isla Mujeres, Quintana Roo, Mexico',
    'lapesca': 'La Pesca, Tamaulipas, Mexico',
    'lazaro': 'Lázaro Cárdenas, Michoacán, Mexico',
    'lerma': 'Lerma, Campeche, Mexico',
    'libertad': 'Puerto Libertad, Sonora, Mexico',
    'mahahual': 'Mahahual, Quintana Roo, Mexico',
    'navidad': 'Barra de Navidad, Jalisco, Mexico',
    'perula': 'Punta Pérula, Jalisco, Mexico',
    'ptocortes': 'Puerto Cortés, Baja California Sur, Mexico',
    'ptoescondido': 'Puerto Escondido, Oaxaca, Mexico',
    'rosalia': 'Santa Rosalia, Baja California Sur, Mexico',
    'sanblas': 'San Blas, Nayarit, Mexico',
    'sanjose': 'San José del Cabo, Baja California Sur, Mexico',
    'teacapan': 'Teacapán, Sinaloa, Mexico',
    'tortugas': 'Bahía Tortugas, Baja California Sur, Mexico',
    'tuxpan': 'Tuxpan, Veracruz, Mexico',
    'vicente': 'Puerto Vicente Guerrero, Guerrero, Mexico',
    'zaragoza': 'Canal de Zaragoza, Quintana Roo, Mexico',
}


def ereignisse(st, von=None, bis=None):
    import dhn_qualitaet
    ev = []
    for p in st['dateien']:
        e, _md = datei(p)
        ev += [(z, h) for z, h in e
               if (not von or z >= von) and (not bis or z < bis)]
    return dhn_qualitaet.art_bestimmen(sorted(set(ev)))


def _neuestes_jahr(st):
    """Juengster Jahrgang, den dieser Hafen hat.

    Nicht jeder hat 2026: fuer Puerto Vicente Guerrero enden die Tafeln
    bei 2025. Der Vergleichsmonat richtet sich deshalb nach dem Hafen,
    nicht nach einem festen Datum -- sonst faellt ein Hafen stumm aus
    der Messung.
    """
    # Gezaehlt, nicht das Maximum genommen: die Dezemberseite schiebt
    # durch die Umrechnung in UTC ihre letzte Abendtide in den 1. Januar
    # des Folgejahrs. Ein einziges solches Ereignis reicht, damit max()
    # auf 2027 zeigt -- und der Juli 2027 ist leer, der Hafen faellt
    # stumm aus der Messung.
    import collections
    c = collections.Counter()
    for p in st['dateien']:
        e, _md = datei(p)
        c.update(z.year for z, _h in e)
    return c.most_common(1)[0][0] if c else None


def vorhersage(st):
    j = _neuestes_jahr(st)
    if j is None:
        return []
    return ereignisse(st, dt.datetime(j, 7, 1), dt.datetime(j, 8, 1))


def jahresreihe(st, jahr=None):
    """Ein voller Jahrgang fuer den Neufit."""
    j = jahr or _neuestes_jahr(st)
    if j is None:
        return []
    ev = []
    for p in st['dateien']:
        e, _md = datei(p)
        ev += [(z, h) for z, h in e
               if dt.datetime(j, 1, 1) <= z < dt.datetime(j + 1, 1, 1)]
    return sorted(set(ev))


def main(argv):
    nur = next((a for a in argv if not a.startswith('--')), None)
    st = stationen()
    if not nur:
        print(f'{len(st)} Haefen')
        for s in st:
            e, md = datei(s['dateien'][-1])
            print(f'  {s["code"]:14} {s["tafel"][:38]:38} '
                  f'{(str(md) + "°W") if md else "  ?  ":>6}  '
                  f'{len(e):4} Ereignisse im Jahr  '
                  f'{"-> " + s["name"][:30] if s["name"] else "(keine Position)"}')
        return 0
    for s in st:
        if nur.lower() not in s['code'] and nur.lower() not in s['tafel'].lower():
            continue
        e, md = datei(s['dateien'][-1])
        print(f'{s["tafel"]} ({s["code"]})  Meridian {md}° W  {len(e)} Ereignisse')
        for z, h in e[:5]:
            print(f'   {z:%Y-%m-%d %H:%M} UTC  {h:6.2f} m')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
