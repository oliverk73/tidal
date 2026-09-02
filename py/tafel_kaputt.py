#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sucht Saetze, die gegen eine Tafelmessung nachweislich falsch sind.

Ergaenzt tafel_dubletten: dort geht es um zwei Saetze desselben Pegels,
hier um Saetze, die schlicht nicht stimmen -- gleich ob der Nachbar
denselben Namen traegt. Gerade die Namensgleichheit fehlt oft: Father
Point und Pointe-au-Pere sind derselbe Pegel, Pikyulik Island und Ile
Pikiyulik auch.

Vier Regeln, jede aus einem Fehlgriff gelernt:

1. Bewertet wird an der Tafel, die dem Satz am GUENSTIGSTEN ist, nicht
   an der schlechtesten. Sonst wird ein Satz dafuer bestraft, dass er
   nicht zur Tafel des Nachbarn passt. Im Gorge Waterway bei Victoria,
   einem Kanal mit Stromschnellen, unterscheiden sich Pegel in 700 m
   Abstand wirklich; neun Saetze standen deswegen zu Unrecht auf der
   Liste.

2. Wer an irgendeiner Tafel der beste ist, hat einen eigenen Pegel und
   kommt nie auf die Liste.

3. Der bessere Nachbar muss nah stehen. Was zwei Kilometer entfernt
   liegt, kann eine andere Bucht sein.

4. Ein gedaempftes Becken ist kein kaputter Satz. Hinter einer Nehrung
   sind alle Amplituden kleiner, und zwar die kurzen Perioden staerker
   als die langen -- Esquimalt Lagoon hat M2 auf 0.11 des Hafenwerts,
   S2 auf 0.06, K1 auf 0.38, O1 auf 0.26, dazu durchgehenden Nachlauf.
   Das ist Physik. Solche Faelle werden ausgesondert und getrennt
   ausgewiesen, nicht geloescht.

Ein Wort zur Zirkularitaet: wo die Sieger aus derselben Tafel gefittet
wurden, die hier den Massstab abgibt, sagt ihr guter Wert nichts ueber
ihre Guete. Der schlechte Wert des Verlierers sagt trotzdem etwas, wenn
er aus einer unabhaengigen Quelle stammt -- er weicht dann wirklich von
der amtlichen Vorhersage ab. Genau das, und nicht mehr, behauptet diese
Liste.

Usage: python3 py/tafel_kaputt.py --csv shn_qualitaet.csv
                                  [--grenze 4] [--gut 1.5] [--faktor 3]
                                  [--km 2] [--liste shn_kaputt.csv]
"""
from __future__ import annotations

import collections
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from health_check import load_records, km, ROOT                    # noqa: E402

HELP = os.path.join(ROOT, 'harmonics/help')

GRENZE = 4.0        # ab hier gilt ein Satz als falsch (Prozent des Hubs)
GUT = 1.5           # so gut muss der Nachbar sein
FAKTOR = 3.0        # und um so viel besser
NAH_KM = 2.0        # so nah muss er stehen
TAFEL_KM = 2.5      # so nah muss die Tafel am Satz stehen, die ihn beurteilt
KON = ('M2', 'S2', 'K1', 'O1')


def konstituenten(rec, namen=KON):
    """Amplitude und Phase der Hauptkonstituenten eines Satzes."""
    l = open(rec['file'], encoding='iso-8859-1').read().split('\n')
    i = 0
    while i < len(l) and l[i].strip() != rec['name']:
        i += 1
    aus = {}
    for z in l[i + 3:]:
        if not z.strip() or z.startswith('#'):
            break
        t = z.split()
        if len(t) >= 3 and t[0] in namen:
            aus[t[0]] = (float(t[1]), float(t[2]))
    return aus


def gedaempft(verlierer, sieger):
    """Sieht der Unterschied nach einem gedaempften Becken aus?

    Kennzeichen: alle Amplituden deutlich kleiner, und die halbtaegigen
    staerker gedaempft als die ganztaegigen. Umgekehrt (alles groesser)
    gibt es das nicht -- ein Becken verstaerkt nicht.
    """
    a, b = konstituenten(sieger), konstituenten(verlierer)
    paare = [(n, b[n][0] / a[n][0]) for n in KON
             if n in a and n in b and a[n][0] > 0.01]
    if len(paare) < 4:
        return False
    v = dict(paare)
    if max(v.values()) > 0.7:
        return False                       # nicht durchgehend kleiner
    halb = (v['M2'] + v['S2']) / 2
    ganz = (v['K1'] + v['O1']) / 2
    return halb < ganz * 0.7               # kurze Perioden staerker gedaempft


def main(argv):
    g = lambda name, vor: (float(argv[argv.index(name) + 1])
                           if name in argv else vor)
    grenze, gut, faktor = g('--grenze', GRENZE), g('--gut', GUT), g('--faktor', FAKTOR)
    nah, tafel = g('--km', NAH_KM), g('--tafel', TAFEL_KM)
    quelle = argv[argv.index('--csv') + 1] if '--csv' in argv else None
    if not quelle:
        print(__doc__)
        return 1
    if not os.path.isabs(quelle):
        quelle = os.path.join(HELP, os.path.basename(quelle))
    ziel = argv[argv.index('--liste') + 1] if '--liste' in argv else None
    if ziel and not os.path.isabs(ziel):
        ziel = os.path.join(HELP, os.path.basename(ziel))

    byname = {}
    for r in load_records():
        byname.setdefault((os.path.basename(r['file']), r['name']), r)

    # Je Satz und Tafel die beste Messung, und nur Tafeln in Reichweite.
    best = {}
    for z in csv.DictReader(open(quelle, encoding='utf-8')):
        hub = float(z.get('hub_m') or 0)
        if hub <= 0 or float(z['abstand_m']) > tafel * 1000:
            continue
        z['_p'] = float(z['rms_m']) / hub * 100
        k = (z['station'], z['datei'], z['satz'])
        if k not in best or z['_p'] < best[k]['_p']:
            best[k] = z

    gruppen = collections.defaultdict(list)
    for z in best.values():
        gruppen[z['station']].append(z)

    eigen = set()                                     # Regel 2
    for rs in gruppen.values():
        s = min(rs, key=lambda x: x['_p'])
        eigen.add((s['datei'], s['satz']))

    guenstig = {}                                     # Regel 1
    for z in best.values():
        k = (z['datei'], z['satz'])
        if k not in guenstig or z['_p'] < guenstig[k]:
            guenstig[k] = z['_p']

    faelle, becken = {}, []
    for st, rs in sorted(gruppen.items()):
        rs.sort(key=lambda x: x['_p'])
        for i in range(len(rs)):
            for j in range(i + 1, len(rs)):
                a, b = rs[i], rs[j]
                kb = (b['datei'], b['satz'])
                if kb in eigen:
                    continue
                ra, rb = byname.get((a['datei'], a['satz'])), byname.get(kb)
                if not (ra and rb):
                    continue
                d = km(ra, rb)
                if d > nah:                           # Regel 3
                    continue
                pb, pa = guenstig[kb], guenstig[(a['datei'], a['satz'])]
                if pb < grenze or pa > gut or pb < pa * faktor:
                    continue
                if kb not in faelle or pb > faelle[kb][0]:
                    faelle[kb] = (pb, pa, d, st, a, b, rb, ra)

    for kb, (pb, pa, d, st, a, b, rb, ra) in sorted(faelle.items()):
        if gedaempft(rb, ra):                         # Regel 4
            becken.append((pb, pa, d, st, a, b))
    for pb, _pa, _d, _st, _a, b in becken:
        faelle.pop((b['datei'], b['satz']), None)

    print(f'{os.path.basename(quelle)}: {len(best)} Messungen in Reichweite, '
          f'{len(gruppen)} Tafeln')
    print(f'{len(faelle)} Saetze ueber {grenze} % des Hubs, mit einem Nachbarn '
          f'unter {gut} %, {faktor}x besser, hoechstens {nah} km entfernt, '
          f'nirgends selbst der beste\n')
    for pb, pa, d, st, a, b, _rb, _ra in sorted(faelle.values(), key=lambda x: -x[0]):
        print(f'  {pb:6.2f} % -> {pa:4.2f} %  {d*1000:5.0f} m  '
              f'{b["satz"][:42]:42} {b["datei"][:30]:30}')
        print(f'  {"":34}bleibt: {a["satz"][:42]:42} {a["datei"][:30]}')
    if becken:
        print(f'\n{len(becken)} als gedaempftes Becken ausgesondert -- bleiben stehen:')
        for pb, pa, d, st, _a, b in sorted(becken, key=lambda x: -x[0]):
            print(f'  {pb:6.2f} %  {b["satz"][:44]:44} {b["datei"][:30]}')
    print()
    for f, n in collections.Counter(k[0] for k in faelle).most_common():
        print(f'   {n:3}  {f}')

    if ziel:
        with open(ziel, 'w', newline='', encoding='utf-8') as fh:
            w = csv.writer(fh)
            w.writerow(['datei', 'name', 'fehler_prozent', 'begruendung'])
            for pb, pa, d, st, a, b, rb, _ra in sorted(faelle.values(),
                                                       key=lambda x: -x[0]):
                w.writerow([os.path.relpath(rb['file'], ROOT), b['satz'],
                            f'{pb:.1f}',
                            f'Auch an der ihm guenstigsten Tafel ({st}) {pb:.1f} % '
                            f'des Hubs, gegen {pa:.1f} % von "{a["satz"]}" '
                            f'({a["datei"]}) in {d*1000:.0f} m Entfernung. '
                            f'Nirgends selbst der beste Satz.'])
        print(f'\nLoeschliste: {ziel}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
