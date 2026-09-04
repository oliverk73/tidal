#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Findet Saetze, die denselben Pegel meinen -- ohne den Namen zu fragen.

py/dubletten_aufraeumen.py gruppiert nach exaktem Namen. Damit findet es
"Arica, Chile" dreimal, aber nur solange alle drei innerhalb eines
Kilometers stehen; die drei Arica-Saetze liegen 1.4 km auseinander und
fielen deshalb heraus. Und es findet gar nichts, wenn dieselbe Stelle in
drei Sprachen heisst: "Kaoh Mul" (Admiralty), "Ilot Cone" (SHOM) und
"Cone Island" (NOAA) sind derselbe Felsen vor Kambodscha, 0.8 bis 2.4 km
Streuung in der Position, und kein Wort gemeinsam.

Der Name ist bei diesen Baenden das schwaechste Merkmal: er kommt aus dem
Buch, das den Satz geliefert hat, und die Buecher schreiben franzoesisch,
englisch, portugiesisch oder eine Umschrift des Landes. Belastbar sind
Lage und Kurve.

Drei Spuren, alle drei nur Kandidaten -- geloescht wird nichts:

  N  Nahspur     bis 2 km auseinander und Kurven bis 10 Prozent
                 verschieden. Das ist derselbe Pegel, zweimal gemessen.
  H  Herkunft    bis 2 km auseinander, Kurven weiter auseinander, aber
                 mindestens einer der beiden ist ein gerechneter Satz
                 (Table-2- oder Part-II-Uebertragung). Dann ist die
                 Abweichung keine zweite Meinung, sondern der Preis der
                 Rechnung -- gleicher Pegel, ein Satz ist abgeleitet.
  G  Gleichname  derselbe Name (ohne Land, ohne Klammerzusatz) bis
                 25 Kilometer Abstand, Kurven bis 10 Prozent verschieden.
                 Deckt die Luecke zwischen der Namensgruppe von
                 dubletten_aufraeumen (unter 1 km) und health_check [B]
                 (ueber 25 km): "Ream, Cambodia" steht zweimal im
                 Bestand, 5.4 km auseinander, und fiel bisher durch beide
                 Raster.
  K  Kopie       ein gerechneter Satz bis 5 Kilometer neben einem
                 gemessenen, und der Zeitversatz zwischen beiden ist
                 null bei einer Guete von 0.99 aufwaerts. Zwei
                 verschiedene Pegel haben immer etwas Laufzeit
                 zwischen sich; ist da gar nichts, ist der gerechnete
                 Satz eine skalierte Kopie desselben Pegels.
  L  Altlage     einer der beiden wurde von Hand verschoben. Verglichen
                 wird zusaetzlich gegen seine urspruengliche Position aus
                 positions_locked.csv. So faellt auf, dass
                 "Braamspunt (Suriname River)" bis zur Verschiebung auf
                 genau der Position stand, auf der heute
                 "Suriname Rivier Entrance" steht.

Warum die 2 km so eng bleiben muessen: "My Thanh" und "Tran De" liegen
9 km auseinander und ihre Kurven unterscheiden sich um 3.6 Prozent --
zwei verschiedene Flussmuendungen im selben Delta. Wer die Nahspur auf
zehn Kilometer aufmacht, loescht Pegel. Weiter entfernte Faelle findet
nur die Altlagenspur, und die stuetzt sich auf eine Entscheidung, die
schon einmal jemand von Hand getroffen hat.

Usage: python3 py/pegel_dubletten.py [--csv] [--alle]
       --alle  auch die Gruppen zeigen, die dubletten_aufraeumen schon sieht
"""
from __future__ import annotations

import collections
import csv
import difflib
import math
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from health_check import (load_records, active_files, km, curve_diff,   # noqa: E402
                          namekey, ROOT)
from transfer_zonen import zeitversatz                                  # noqa: E402

LOCK = os.path.join(ROOT, 'harmonics/help/positions_locked.csv')
AUS = os.path.join(ROOT, 'harmonics/help/pegel_dubletten.csv')

NAH_KM = 2.0        # Nahspur: enger geht nicht, weiter trifft Nachbarpegel
GLEICH = 0.10       # bis hier gilt die Kurve als dieselbe
ALT_KM = 1.0        # Altlagenspur: die alte Position muss genau passen
ALT_GLEICH = 0.20   # dort darf die Kurve weiter auseinander liegen
NAME_KM = 1.0       # so nah sieht dubletten_aufraeumen die Gruppe selbst
GLEICHNAME_KM = 25.0  # Gleichnamenspur: darueber greift health_check [B]
KOPIE_KM = 5.0      # Kopienspur: Umkreis um einen abgeleiteten Satz
KOPIE_DT = 0.10     # und dessen Zeitversatz zum gemessenen Satz
KOPIE_GUETE = 0.99

ABGELEITET = re.compile(r'Table 2 transfer|Part II Transfer|transfer from', re.I)


def vermerke():
    """-> {(Datei, Zeile des Namens): Kommentarblock darueber}."""
    out = {}
    for path in active_files():
        lines = open(os.path.join(ROOT, path), encoding='iso-8859-1').read().split('\n')
        for k, line in enumerate(lines):
            if not line or line.startswith('#'):
                continue
            j, block = k - 1, []
            while j >= 0 and lines[j].startswith('#'):
                block.append(lines[j])
                j -= 1
            out[(path, k + 1)] = '\n'.join(reversed(block))
    return out


def altlagen():
    """-> {(Datei, Name): (lat, lon)} der Position VOR einer Handkorrektur."""
    out = {}
    if not os.path.exists(LOCK):
        return out
    for row in csv.DictReader(open(LOCK, encoding='utf-8')):
        try:
            la, lo = float(row['orig_lat']), float(row['orig_lon'])
        except (TypeError, ValueError):
            continue
        out[(row['file'], row['name'])] = (la, lo)
    return out


def _km(la1, lo1, la2, lo2):
    return km({'lat': la1, 'lon': lo1}, {'lat': la2, 'lon': lo2})


class Union:
    def __init__(self):
        self.p = {}

    def find(self, a):
        self.p.setdefault(a, a)
        while self.p[a] != a:
            self.p[a] = self.p[self.p[a]]
            a = self.p[a]
        return a

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[ra] = rb


def main(argv):
    alle = '--alle' in argv
    # Stroemungssaetze bleiben draussen: dort stehen an einer Position mit
    # Absicht mehrere Saetze, einer je Messtiefe ("(depth 42 ft)"). Das ist
    # keine Dublette, das ist das Profil.
    recs = [r for r in load_records()
            if r['lat'] is not None and r['lon'] is not None and not r['current']]
    komm = vermerke()
    alt = altlagen()
    for r in recs:
        r['abgeleitet'] = bool(ABGELEITET.search(komm.get((r['file'], r['line']), '')))
        r['alt'] = alt.get((r['file'], r['name']))

    # Nachbarschaft ueber ein Gradgitter: bei 18000 Saetzen ist alles gegen
    # alles zwar machbar, aber die Zelle kostet nichts.
    gitter = collections.defaultdict(list)
    for i, r in enumerate(recs):
        gitter[(round(r['lat'] * 20), round(r['lon'] * 20))].append(i)

    u = Union()
    grund = {}
    for i, a in enumerate(recs):
        cz = round(a['lat'] * 20)
        for dz in (-1, 0, 1):
            for dm in (-1, 0, 1):
                for j in gitter.get((cz + dz, round(a['lon'] * 20) + dm), ()):
                    if j <= i:
                        continue
                    b = recs[j]
                    d = km(a, b)
                    rel = curve_diff(a, b)[1]
                    spur = None
                    if d <= NAH_KM and rel < GLEICH:
                        spur = 'N'
                    elif d <= NAH_KM and (a['abgeleitet'] or b['abgeleitet']):
                        spur = 'H'
                    if spur:
                        u.union(i, j)
                        grund[(i, j)] = (spur, d, rel)

    # Gleichnamenspur: derselbe Schluessel, bis 25 km, Kurve wie die Nahspur.
    nach_name = collections.defaultdict(list)
    for i, r in enumerate(recs):
        nach_name[r['key']].append(i)
    for schluessel, idx in nach_name.items():
        if not schluessel or len(idx) < 2:
            continue
        for a_ in range(len(idx)):
            for b_ in range(a_ + 1, len(idx)):
                i, j = idx[a_], idx[b_]
                if (min(i, j), max(i, j)) in grund:
                    continue
                d = km(recs[i], recs[j])
                rel = curve_diff(recs[i], recs[j])[1]
                if d <= GLEICHNAME_KM and rel < GLEICH:
                    u.union(i, j)
                    grund[(min(i, j), max(i, j))] = ('G', d, rel)

    # Kopienspur: ein gerechneter Satz ohne jede Laufzeit zum Nachbarn.
    # Je gerechnetem Satz wird nur der naechste Partner genommen. Ohne das
    # kettet sich die Strasse von Shimonoseki zusammen: der abgeleitete
    # Satz liegt dort innerhalb von fuenf Kilometern neben acht gemessenen
    # Pegeln, und ueber ihn wachsen acht verschiedene Pegel zu einem
    # Haufen mit 47 Prozent Kurvenspanne zusammen. Eine Kopie ist die
    # Kopie EINES Pegels.
    for i, a in enumerate(recs):
        cz, cm = round(a['lat'] * 20), round(a['lon'] * 20)
        w = int(KOPIE_KM / 5.5) + 1
        nah = [j for dz in range(-w, w + 1) for dm in range(-w, w + 1)
               for j in gitter.get((cz + dz, cm + dm), ())]
        kandidat = []
        for j in nah:
            if j == i or (min(i, j), max(i, j)) in grund:
                continue
            b = recs[j]
            if a['abgeleitet'] == b['abgeleitet']:
                continue
            if km(a, b) > KOPIE_KM:
                continue
            dt, gu = zeitversatz(a, b)
            if dt is None or abs(dt) > KOPIE_DT or gu < KOPIE_GUETE:
                continue
            kandidat.append((km(a, b), j))
        if kandidat:
            _d, j = min(kandidat)
            u.union(i, j)
            grund[(min(i, j), max(i, j))] = ('K', _d,
                                             curve_diff(a, recs[j])[1])

    # Altlagenspur laeuft ausserhalb des Gitters: die alte Position kann
    # beliebig weit weg liegen.
    for i, a in enumerate(recs):
        if not a['alt']:
            continue
        cz, cm = round(a['alt'][0] * 20), round(a['alt'][1] * 20)
        nah = [j for dz in (-1, 0, 1) for dm in (-1, 0, 1)
               for j in gitter.get((cz + dz, cm + dm), ())]
        for j in nah:
            b = recs[j]
            if j == i:
                continue
            d = _km(a['alt'][0], a['alt'][1], b['lat'], b['lon'])
            if d > ALT_KM:
                continue
            rel = curve_diff(a, b)[1]
            if rel < ALT_GLEICH or a['abgeleitet'] or b['abgeleitet']:
                if (min(i, j), max(i, j)) in grund:
                    continue
                u.union(i, j)
                grund[(min(i, j), max(i, j))] = ('L', km(a, b), rel)

    haufen = collections.defaultdict(list)
    for i in u.p:
        haufen[u.find(i)].append(i)

    # Aus den Paaren werden Haufen -- aber nur vollstaendige. Wer nur ueber
    # einen Mittelsmann dazugehoert, gehoert nicht dazu: in der Strasse von
    # Shimonoseki liegen zehn verschiedene Pegel jeweils paarweise dicht
    # beieinander, und ueber die Kette waeren sie ein einziger Pegel mit
    # 47 Prozent Kurvenspanne. Verlangt wird deshalb, dass JEDES Paar im
    # Haufen selbst als Paar gefunden wurde.
    kante = {}
    for (i, j), v in grund.items():
        kante[(i, j)] = v
    nachbar = collections.defaultdict(set)
    for i, j in kante:
        nachbar[i].add(j)
        nachbar[j].add(i)

    def paarwert(i, j):
        return kante.get((min(i, j), max(i, j)), ('-', 99.0, 9.9))[1]

    gruppen = []
    for teil in haufen.values():
        offen = set(teil)
        while offen:
            start = max(offen, key=lambda i: len(nachbar[i] & offen))
            g = [start]
            offen.discard(start)
            for j in sorted(nachbar[start] & offen,
                            key=lambda j: paarwert(start, j)):
                if all((min(j, m), max(j, m)) in kante for m in g):
                    g.append(j)
                    offen.discard(j)
            if len(g) > 1:
                gruppen.append(sorted(g))
    gruppen.sort(key=lambda g: recs[g[0]]['name'])

    def namenslage(g):
        """gleich / aehnlich / verschieden -- nur zum Sortieren der Arbeit.

        Ein Kandidat mit gleichem Namen ist schnell entschieden, einer mit
        fremdem Namen braucht die Karte. Entschieden wird er dadurch nicht:
        "Kaoh Mul" und "Ilot Cone" haben keinen Buchstaben gemeinsam und
        sind derselbe Felsen.
        """
        k = {recs[i]['key'] for i in g}
        if len(k) == 1:
            return 'gleich'
        paare = [difflib.SequenceMatcher(None, recs[i]['key'], recs[j]['key']).ratio()
                 for i in g for j in g if i < j]
        return 'aehnlich' if min(paare) >= 0.7 else 'verschieden'

    def kette(g):
        weit = max(km(recs[i], recs[j]) for i in g for j in g if i < j)
        spanne = max(curve_diff(recs[i], recs[j])[1]
                     for i in g for j in g if i < j)
        return weit > 3.0 or spanne > 0.25

    neu, bekannt = [], []
    for g in gruppen:
        namen = {recs[i]['name'] for i in g}
        weit = max(km(recs[i], recs[j]) for i in g for j in g if i < j)
        # Was dubletten_aufraeumen selbst sieht: gleicher Name, unter 1 km.
        if len(namen) == 1 and weit < NAME_KM:
            bekannt.append(g)
        else:
            neu.append(g)

    print(f'{len(gruppen)} Haufen aus mehreren Saetzen auf einem Pegel')
    print(f'  {len(bekannt)} davon sieht py/dubletten_aufraeumen.py schon '
          f'(gleicher Name, unter {NAME_KM:.0f} km)')
    print(f'  {len(neu)} sind neu: anderer Name oder zu weit fuer die Namensgruppe\n')

    zeigen = gruppen if alle else neu
    kzahl = collections.Counter()
    for g in zeigen:
        for i in g:
            for j in g:
                if (i, j) in grund:
                    kzahl[grund[(i, j)][0]] += 1
    print('Spuren in den gezeigten Haufen: '
          + '  '.join(f'{k}={v}' for k, v in sorted(kzahl.items())) + '\n')

    for g in zeigen[:60]:
        namen = {recs[i]['name'] for i in g}
        kopf = 'gleicher Name' if len(namen) == 1 else 'verschiedene Namen'
        warn = '  -- KETTE, von Hand trennen' if kette(g) else ''
        print(f'* {recs[g[0]]["name"][:60]}  ({len(g)} Saetze, {kopf}){warn}')
        for i in g:
            r = recs[i]
            mark = ' [abgeleitet]' if r['abgeleitet'] else ''
            altstr = (f'  frueher {r["alt"][0]:.4f} {r["alt"][1]:.4f}'
                      if r['alt'] else '')
            print(f'    {r["lat"]:9.4f} {r["lon"]:10.4f}  {r["name"][:46]:46s} '
                  f'[{os.path.basename(r["file"])}:{r["line"]}]{mark}{altstr}')
        for a in range(len(g)):
            for b in range(a + 1, len(g)):
                i, j = g[a], g[b]
                sp, d, rel = grund.get((i, j), ('-', km(recs[i], recs[j]),
                                                curve_diff(recs[i], recs[j])[1]))
                dt, gu = zeitversatz(recs[i], recs[j])
                dts = f'{dt:+.2f} h (G {gu:.2f})' if dt is not None else 'n/a'
                print(f'      {sp}  {d:6.2f} km  Kurve {rel * 100:5.1f} %  dt {dts}')
        print()
    if len(zeigen) > 60:
        print(f'... und {len(zeigen) - 60} weitere. Vollstaendig mit --csv.')

    if '--csv' in argv:
        with open(AUS, 'w', newline='', encoding='utf-8') as fh:
            w = csv.writer(fh)
            w.writerow(['haufen', 'spur', 'name', 'datei', 'zeile', 'lat', 'lon',
                        'abgeleitet', 'alt_lat', 'alt_lon', 'max_km', 'max_kurve',
                        'kette', 'namen'])
            for n, g in enumerate(gruppen, 1):
                weit = max(km(recs[i], recs[j]) for i in g for j in g if i < j)
                rmax = max(curve_diff(recs[i], recs[j])[1]
                           for i in g for j in g if i < j)
                spuren = ''.join(sorted({grund[(i, j)][0] for i in g for j in g
                                         if (i, j) in grund}))
                for i in g:
                    r = recs[i]
                    w.writerow([n, spuren, r['name'], r['file'], r['line'],
                                f'{r["lat"]:.4f}', f'{r["lon"]:.4f}',
                                '1' if r['abgeleitet'] else '',
                                f'{r["alt"][0]:.4f}' if r['alt'] else '',
                                f'{r["alt"][1]:.4f}' if r['alt'] else '',
                                f'{weit:.2f}', f'{rmax:.3f}',
                                '1' if kette(g) else '', namenslage(g)])
        print(f'\n-> {os.path.relpath(AUS, ROOT)}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
