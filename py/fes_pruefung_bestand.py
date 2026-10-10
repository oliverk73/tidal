#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Prueft den ganzen Bestand gegen FES2022 -- dort, wo FES nachweislich traegt.

Grundlage ist die Eichung von py/fes_kuestentyp.py (02.10.2026, 1423 Messorte):
FES trifft offene Kuesten im Median auf 1,8 % (P90 9 %), Inselwelten und
gemischte Kuesten auf 2,5-3,2 % (P90 17 %). In Buchten, Muendungen und Lagunen
(binnen) und wo die FES-Zelle >= 5 km hochgerechnet ist, taugt FES nicht.

Geprueft werden deshalb nur Saetze mit Kuestentyp offen/insel/gemischt und
echtem FES-Wasser unter 5 km. Verdacht: Kurvenfehler ueber VERDACHT Prozent
(das ueberschreiten an solchen Kuesten nur ~3-7 % der Messpegel).

Art des Satzes (aus Datei und Quellzeile):
  Uebertragung  NOAA Table 2, ATT-Sekundaerhaefen, IH-Konkordanzen
  Tafel-Fit     Fits auf Vorhersagetafeln (tidetimes, NMDIS, NAMRIA, DHN, BIG, JMA, RWS ...)
  Buch          ATT Part III / amtliche Konstanten aus Tafelwerken
  Altbestand    XTide-Altbestand (1997, 2004, Lavergne, dwf-nonfree)
  Messung       TICON, eigene Messfits, NOAA-dwf (zur Gegenkontrolle)

Hinweis auf die Fehlerart (wie nachbarprobe.py):
  Zeitversatz   alle Partialtiden um denselben Betrag verschoben -> Zone/Meridian/dt
  Tagestiden    nur K1/O1 daneben, M2/S2 stimmen
  Amplitude     Phasen ok, Hub um mehr als 30 % daneben -> Einheit/Skalierung/Hubverhaeltnis
  gemischt      alles andere (oft Binnenlage, die die Landmaske nicht sieht)

Ergebnis: harmonics/help/fes_pruefung_bestand.csv und Uebersicht auf stdout.
NUR ZUM FINDEN -- entschieden wird wie gehabt an Nachbarn bzw. von Hand.

Aufruf: venv/bin/python py/fes_pruefung_bestand.py
"""
from __future__ import annotations

import cmath
import collections
import csv
import math
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fes_kuestentyp as F                                           # noqa: E402
from health_check import load_records, curve_diff, SPEED             # noqa: E402

ROOT = F.ROOT
OUT = os.path.join(ROOT, 'harmonics/help/fes_pruefung_bestand.csv')
VERDACHT = 20.0
MIND_AMP = 0.05

UEBERTRAGUNG = ('/noaa/', '_secondary', 'harmonics_ih_tabelas')
TAFELFIT = ('harmonics_utide_tidetables', 'harmonics_utide_big_srgi', 'harmonics_utide_pushidrosal',
            'harmonics_utide_chile_shoa', 'harmonics_noaa_refs')
BUCH = ('/att/', '/bsh/', 'harmonics_puertos_spain', 'harmonics_literature', 'harmonics_mascaret')
ALT = ('harmonics-1997', 'harmonics-2004', 'lavergne', 'dwf-20100529', 'dwf-20070318')
MESSUNG = ('/ticon/', 'harmonics_utide_observations', 'harmonics-dwf-20251228')
OHNE = ('harmonics_fes2022',)




def kopf(texte, r):
    """Kommentarzeilen direkt vor dem Satznamen (mit oder ohne BEGIN HOT COMMENTS)."""
    L = texte[r['file']]
    i = r['line'] - 1
    k = i
    while k > 0 and L[k - 1].startswith('#'):
        k -= 1
    return L[k:i]


def art(r, quelle):
    f = r['file']
    if any(x in f for x in OHNE):
        return None
    if 'harmonics_utide_observations' in f and ('JMA hourly' in quelle or 'astronomical' in quelle):
        return 'Tafel-Fit'
    for name, muster in (('Uebertragung', UEBERTRAGUNG), ('Tafel-Fit', TAFELFIT), ('Altbestand', ALT),
                         ('Messung', MESSUNG), ('Buch', BUCH)):
        if any(x in f for x in muster):
            return name
    return 'sonstige'


def versatz(r, c):
    a, fa = abs(r['z'][c]), abs(r['fes_rec']['z'][c])
    if a < MIND_AMP or fa < MIND_AMP:
        return None
    g = -math.degrees(cmath.phase(r['z'][c]))
    gf = -math.degrees(cmath.phase(r['fes_rec']['z'][c]))
    return ((g - gf + 180) % 360 - 180) / SPEED[c] * 60


def fehlerart(r):
    v = {c: versatz(r, c) for c in ('M2', 'S2', 'K1', 'O1')}
    da = [x for x in v.values() if x is not None]
    halb = [v[c] for c in ('M2', 'S2') if v[c] is not None]
    tag = [v[c] for c in ('K1', 'O1') if v[c] is not None]
    hub = r['tot'] / max(1e-6, r['fes_rec']['tot'])
    if len(da) >= 3 and max(da) - min(da) <= 25 and abs(statistics.median(da)) >= 20:
        return f'Zeitversatz {statistics.median(da):+.0f} min', v, hub
    if halb and tag and all(abs(x) <= 15 for x in halb) and any(abs(x) >= 30 for x in tag):
        return 'Tagestiden', v, hub
    if da and all(abs(x) <= 15 for x in da) and abs(hub - 1) > 0.3:
        return f'Amplitude x{hub:.2f}', v, hub
    return 'gemischt', v, hub


def main():
    recs = [r for r in load_records() if r['lat'] is not None and not r['current']]
    texte = {}
    for r in recs:
        if r['file'] not in texte:
            texte[r['file']] = open(os.path.join(ROOT, r['file']), encoding='iso-8859-1').read().split('\n')
        k = kopf(texte, r)
        r['quelle'] = next((x[10:].strip() for x in k if x.startswith('# source:')), '')
        r['land'] = next((x.split(':', 1)[1].strip() for x in k if x.startswith('# country:')), '')
        r['art'] = art(r, r['quelle'])
    recs = [r for r in recs if r['art']]
    print(f'{len(recs)} Saetze, FES abfragen ...', file=sys.stderr, flush=True)
    F.fes_dazu(recs)
    print('Kuestentyp bestimmen ...', file=sys.stderr, flush=True)
    for r in recs:
        r['typ'] = F.typ(r)
        d, rel = curve_diff(r, r['fes_rec'])
        r['abs'], r['rel'] = d, 100 * rel
        r['geeignet'] = (r['typ'] != 'binnen' and r['fes_wasser_km'] < 5 and r['fes_ersatz_km'] == 0)
        r['fart'], r['v'], r['hub'] = fehlerart(r)
    g = [r for r in recs if r['geeignet']]

    with open(OUT, 'w', encoding='utf-8', newline='') as fh:
        w = csv.writer(fh)
        w.writerow(['verdacht', 'fehler_prozent', 'fehlerart', 'art', 'datei', 'name', 'land', 'lat', 'lon', 'typ',
                    'fes_wasser_km', 'm2_min', 's2_min', 'k1_min', 'o1_min', 'hub_verhaeltnis', 'quelle'])
        for r in sorted(recs, key=lambda r: (not r['geeignet'], -r['rel'])):
            fm = lambda c: '' if r['v'][c] is None else f'{r["v"][c]:.0f}'
            w.writerow([int(r['geeignet'] and r['rel'] > VERDACHT), f'{r["rel"]:.1f}',
                        r['fart'] if r['geeignet'] else 'nicht pruefbar', r['art'], r['file'], r['name'],
                        r['land'], r['lat'], r['lon'], r['typ'], f'{r["fes_wasser_km"]:.1f}',
                        fm('M2'), fm('S2'), fm('K1'), fm('O1'), f'{r["hub"]:.2f}', r['quelle'][:70]])

    print(f'\n{len(recs)} Saetze, davon pruefbar (nicht binnen, FES-Wasser < 5 km): {len(g)}')
    print(f'\n{"Art":14} {"pruefbar":>8} {"Median":>7} {"P90":>6} {"> " + str(int(VERDACHT)) + " %":>7}')
    for a in ('Uebertragung', 'Tafel-Fit', 'Buch', 'Altbestand', 'Messung', 'sonstige'):
        rs = sorted(r['rel'] for r in g if r['art'] == a)
        if not rs:
            continue
        print(f'{a:14} {len(rs):8} {statistics.median(rs):6.1f}% {rs[int(.9 * (len(rs) - 1))]:5.1f}%'
              f' {sum(x > VERDACHT for x in rs):7}')
    v = [r for r in g if r['rel'] > VERDACHT]
    print(f'\nVerdacht nach Datei ({len(v)}):')
    for f, n in collections.Counter(r['file'].split('/')[-1] for r in v).most_common():
        m = sum(1 for r in g if r['file'].split('/')[-1] == f)
        print(f'  {n:5} von {m:5}  {f}')
    print('\nVerdacht nach Fehlerart:')
    for f, n in collections.Counter(r['fart'].split(' ')[0] for r in v).most_common():
        print(f'  {n:5}  {f}')
    print('\nVerdacht nach Land (Top 25):')
    for f, n in collections.Counter(r['land'] or '?' for r in v).most_common(25):
        print(f'  {n:5}  {f}')
    print(f'\n-> {OUT}')


if __name__ == '__main__':
    main()
