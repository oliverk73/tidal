#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Prueft jeden Satz gegen den Konsens seiner unabhaengigen Nachbarn.

Nur 5000 der 14451 Gezeitensaetze haben eine Messreihe. Fuer die anderen
9451 gab es bisher keinen Massstab ausser Dubletten: Wo kein zweiter Satz
an derselben Stelle steht, fiel nichts auf. Olivers Gedanke (12.09.2026):
Nahe Stationen haben aehnliche Tiden; weicht eine von allen Nachbarn ab,
ist sie wahrscheinlich ungenau -- es sei denn, sie liegt hinter einer
Barriere oder in einer Meerenge.

Ein fester Schwellwert geht dafuer nicht. Ueber den ganzen Bestand
gemessen, waechst der Kurvenunterschied mit dem Abstand langsam (Median
6.5 % unter 1 km, 12.5 % bei 20 km), der Ausreisserrand aber stark
(90 % der Paare unter 17 % bzw. 43 %). Im Pentland Firth etwa liegen
Scrabster und Wick 32 km auseinander und 157 min -- echte Physik.

Deshalb entscheidet hier die Mehrheit, nicht ein Grenzwert:

  Grundrauschen  der Median der Kurvenunterschiede, die die Nachbarn
                 UNTEREINANDER haben (je Paar verschiedener Orte).
  Abweichung     der Median der Unterschiede des Satzes zu jedem
                 Nachbarort; innerhalb eines Ortes zaehlt der beste
                 Treffer, der Satz bekommt also den Zweifel zugute.
  Auffaellig     Abweichung ueber MIND_PCT und ueber FAKTOR mal
                 Grundrauschen.

Sind die Nachbarn schon untereinander uneinig (Meerenge, Aestuar,
Trichter), ist das Grundrauschen hoch und die Probe schweigt. Die
Ausnahme "hinter einer Barriere" braucht also keine Liste.

Unabhaengig heisst: nicht dieselbe Abstammung. Alle NOAA-Uebertragungen
von Ullapool sind sich zwangslaeufig einig und bilden sonst eine falsche
Mehrheit; ebenso der Satz selbst und seine Uebertragungen. Verlangt
werden mindestens MIND_ORTE verschiedene Orte und MIND_SIPPEN
verschiedene Abstammungen. Die Spalte dateien sagt zusaetzlich, aus wie
vielen Quelldateien die Mehrheit kommt: steht dort 1, koennte auch ein
Fehler dieser einen Quelle die Mehrheit bilden.

Die Spalten zeit_min und massstab sagen, welcher Art der Verdacht ist:
ein gemeinsamer Zeitversatz zu allen Nachbarn deutet auf einen Zeit- oder
Zonenfehler, ein gemeinsamer Faktor auf Fuss statt Meter oder eine
falsche Skalierung, 180 Grad auf eine umgedrehte Kurve.

Usage: python3 py/nachbarprobe.py [--km 25] [--schreiben]
"""
from __future__ import annotations

import cmath
import collections
import csv
import math
import os
import re
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from health_check import MAIN, SPEED, curve_diff, km, load_records  # noqa: E402
from pegel_dubletten import vermerke  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUS = os.path.join(ROOT, 'harmonics/help/nachbarprobe.csv')

UMKREIS_KM = 25.0      # so weit wird nach Nachbarn gesucht
EIGEN_KM = 0.3         # naeher gilt als derselbe Pegel, nicht als Nachbar
ORT_KM = 0.5           # bis hierhin derselbe Nachbarort
MIND_ORTE = 3
MIND_SIPPEN = 3
MIND_PCT = 20.0        # darunter nie auffaellig
FAKTOR = 2.5           # so viel mal das Grundrauschen

BEZUG = [re.compile(r'[Tt]ransfer (?:from|von)\s+(.+?)\s*\((?:no\.|att\b)', re.S),
         re.compile(r'(?:Uebertragung|Transfer|transfer) (?:von|from)\s+([^.;(\n]+)')]

BINNEN = re.compile(r'\b(lake|lagoon|lagune|basin|river|riviere|rivière|creek|'
                    r'lock|ecluse|écluse|canal|kanal|sperrwerk|weir|upstream|'
                    r'bridge|brücke|haven|bras|loch|fjord|firth|see|sluis|'
                    r'estuary|aestuar|ästuar|inlet|harbour|harbor|hafen)\b', re.I)

FELDER = ['datei', 'name', 'lat', 'lon', 'verdacht', 'abweichung_pct',
          'grundrauschen_pct', 'verhaeltnis', 'orte', 'sippen', 'dateien', 'zeit_min',
          'massstab', 'naechster_km', 'hinweis', 'nachbarn', 'entscheidung']

# Verdachtsarten, nach Gewicht: die ersten beiden sind fast immer Fehler,
# "offen" kann auch echt sein (Onehunga liegt am Manukau Harbour, seine
# Nachbarn am Waitemata; Geelong hinter der Rip in der Port Phillip Bay).
RANG = {'Zeit glatt': 0, '180 Grad': 1, 'Massstab': 2, 'Zeit krumm': 3,
        'offen': 4, 'Binnenlage?': 5}


def sippe(r, text):
    """Abstammung: der Bezugsort, sonst der Satz selbst."""
    for muster in BEZUG:
        m = muster.search(text)
        if m:
            return 'bezug:' + ' '.join(m.group(1).split())
    return 'eigen:%s|%s' % (os.path.basename(r['file']), r['name'])


def versatz_min(a, b):
    """Zeitversatz in Minuten aus M2 und S2 (b gegen a), None ohne Amplitude."""
    out = []
    for x in ('M2', 'S2'):
        if abs(a['z'][x]) > 0.05 and abs(b['z'][x]) > 0.05:
            out.append(math.degrees(cmath.phase(b['z'][x] / a['z'][x])) / SPEED[x] * 60)
    return statistics.median(out) if out else None


def massstab(a, b):
    """Amplitudenverhaeltnis b/a ueber die Hauptpartialtiden."""
    paare = [(abs(b['z'][x]), abs(a['z'][x])) for x in MAIN if abs(a['z'][x]) > 0.05]
    return statistics.median(p / q for p, q in paare) if paare else None


def nachbarn_suchen(recs, umkreis):
    """-> {id(Satz): [Nachbarsatz, ...]} ueber ein Gitter."""
    gitter = collections.defaultdict(list)
    gr = umkreis / 111.2
    for r in recs:
        gitter[(int(r['lat'] / gr), int(r['lon'] / gr / max(0.05, math.cos(math.radians(r['lat'])))))].append(r)
    out = {}
    for (a, b), liste in gitter.items():
        umfeld = [x for da in (-1, 0, 1) for db in (-1, 0, 1)
                  for x in gitter.get((a + da, b + db), ())]
        for r in liste:
            out[id(r)] = [x for x in umfeld if x is not r and km(r, x) <= umkreis]
    return out


def orte(liste):
    """Nachbarn zu Orten zusammenfassen (bis ORT_KM)."""
    gruppen = []
    for r in sorted(liste, key=lambda x: (x['lat'], x['lon'])):
        for g in gruppen:
            if km(g[0], r) <= ORT_KM:
                g.append(r)
                break
        else:
            gruppen.append([r])
    return gruppen


def main(argv):
    umkreis = float(argv[argv.index('--km') + 1]) if '--km' in argv else UMKREIS_KM
    recs = [r for r in load_records()
            if r['lat'] is not None and r['lon'] is not None and not r['current']]
    komm = vermerke()
    for r in recs:
        r['sippe'] = sippe(r, komm.get((r['file'], r['line']), ''))
    nah = nachbarn_suchen(recs, umkreis)

    alt = {}
    if os.path.exists(AUS):
        for z in csv.DictReader(open(AUS, encoding='utf-8')):
            if (z.get('entscheidung') or '').strip():
                alt[(z['datei'], z['name'])] = z['entscheidung'].strip()

    out = []
    for r in recs:
        liste = [x for x in nah[id(r)]
                 if x['sippe'] != r['sippe'] and km(r, x) > EIGEN_KM]
        gruppen = [g for g in orte(liste)]
        if len(gruppen) < MIND_ORTE:
            continue
        if len({x['sippe'] for x in liste}) < MIND_SIPPEN:
            continue
        # Grundrauschen: Nachbarorte untereinander, je Ortspaar der Median
        zwischen = []
        for i, g in enumerate(gruppen):
            for h in gruppen[i + 1:]:
                zwischen.append(statistics.median(curve_diff(x, y)[1] * 100
                                                  for x in g for y in h))
        grund = statistics.median(zwischen)
        # Abweichung: je Nachbarort der beste Treffer
        je_ort = [min(curve_diff(r, x)[1] * 100 for x in g) for g in gruppen]
        abw = statistics.median(je_ort)
        if abw < MIND_PCT or abw < FAKTOR * max(grund, 1e-9):
            continue
        dts = [d for d in (versatz_min(x, r) for x in liste) if d is not None]
        ms = [m for m in (massstab(x, r) for x in liste) if m]
        dt = statistics.median(dts) if dts else None
        mass = statistics.median(ms) if ms else None
        verdacht = 'offen'
        hinweis = []
        einig_zeit = dt is not None and abs(dt) >= 20 and statistics.pstdev(dts) < 25
        einig_mass = bool(mass) and statistics.pstdev(ms) < 0.25
        # Nur wenn die Zeitversaetze untereinander einig sind, sagt ein
        # kleiner Versatz wirklich "keine Verschiebung". Uneinige Versaetze
        # sind das Bild eines Flusslaufs, keins einer falschen Einheit.
        zeit_klar = bool(dts) and statistics.pstdev(dts) < 25
        gedaempft = bool(mass) and not 0.85 < mass < 1.20
        # Eine falsche Zone verschiebt nur die Zeit. Eine Lagune, ein Aestuar
        # oder ein Sperrwerk verschiebt UND daempft -- das ist echt und wird
        # deshalb als Binnenlage gefuehrt, nicht als Fehler.
        if einig_zeit:
            hinweis.append(f'alle Nachbarn um {dt:+.0f} min versetzt')
        if einig_mass and gedaempft:
            hinweis.append(f'Amplituden Faktor {mass:.2f}')
        dreh = [abs(abs(math.degrees(cmath.phase(r['z'][x] / y['z'][x]))) - 180)
                for y in liste for x in MAIN
                if abs(r['z'][x]) > 0.05 and abs(y['z'][x]) > 0.05]
        if dreh and statistics.median(dreh) < 30:
            verdacht = '180 Grad'
            hinweis.append('Kurve um 180 Grad verdreht')
        elif einig_mass and gedaempft and zeit_klar and abs(dt) < 20:
            # Faktor ohne Zeitversatz: Einheit oder Skalierung, keine Physik.
            verdacht = 'Massstab'
            # 0.305 bzw. 3.28 waere Fuss gegen Meter. Vorsicht: ein Fluss
            # daempft auch auf ein Drittel (Bridgwater am Parrett: 0.32),
            # deshalb nur als Hinweis.
            if min(abs(mass - 0.3048), abs(mass - 3.2808) / 3.28) < 0.02:
                hinweis.append('Faktor nahe Fuss/Meter')
        elif einig_zeit and not gedaempft:
            stufe = min(abs(abs(dt) - st) for st in (30, 45, 60, 90, 120, 180, 240, 300))
            verdacht = 'Zeit glatt' if stufe <= 5 else 'Zeit krumm'
        elif gedaempft and (not zeit_klar or abs(dt or 0) >= 20):
            verdacht = 'Binnenlage?'
        out.append(dict(
            datei=os.path.basename(r['file']), name=r['name'],
            lat=f'{r["lat"]:.4f}', lon=f'{r["lon"]:.4f}', verdacht=verdacht,
            abweichung_pct=round(abw, 1), grundrauschen_pct=round(grund, 1),
            verhaeltnis=round(abw / max(grund, 0.1), 1), orte=len(gruppen),
            sippen=len({x['sippe'] for x in liste}),
            dateien=len({os.path.basename(x['file']) for x in liste}),
            zeit_min='' if dt is None else f'{dt:+.0f}',
            massstab='' if mass is None else f'{mass:.2f}',
            naechster_km=round(min(km(r, x) for x in liste), 2),
            hinweis='; '.join(hinweis + (['Name nennt eine Binnenlage']
                                         if BINNEN.search(r['name']) else [])),
            nachbarn='; '.join(f'{g[0]["name"][:28]} {min(curve_diff(r, x)[1] * 100 for x in g):.0f}%'
                               for g in sorted(gruppen, key=lambda g: km(r, g[0]))[:4]),
            entscheidung=alt.get((os.path.basename(r['file']), r['name']), '')))
    out.sort(key=lambda z: (RANG[z['verdacht']], -z['verhaeltnis']))
    print(f'{len(out)} auffaellige Saetze von {len(recs)} (Umkreis {umkreis:.0f} km, '
          f'ab {MIND_PCT:.0f} % und {FAKTOR}x Grundrauschen)')
    for art, n in sorted(collections.Counter(z['verdacht'] for z in out).items(),
                         key=lambda x: RANG[x[0]]):
        print(f'  {art:12} {n:4d}')
    for z in out[:30]:
        print(f'  {z["verdacht"]:11} {z["verhaeltnis"]:5.1f}x {z["abweichung_pct"]:5.1f} % gegen '
              f'{z["grundrauschen_pct"]:4.1f} %  {z["name"][:36]:36} {z["datei"][10:28]:18} {z["hinweis"][:40]}')
    if '--schreiben' in argv:
        with open(AUS, 'w', newline='', encoding='utf-8') as fh:
            w = csv.DictWriter(fh, fieldnames=FELDER)
            w.writeheader()
            w.writerows(out)
        print('->', os.path.relpath(AUS, ROOT))


if __name__ == '__main__':
    main(sys.argv[1:])
