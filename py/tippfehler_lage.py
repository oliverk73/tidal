#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sucht Positionen, die wie ein Tippfehler aussehen.

Anlass: "Anadyr, Russia" stand auf -177.5330 statt 177.5330, also
190 km jenseits der Datumsgrenze. Ein fehlendes Vorzeichen, ein
Ziffernbeh:eine Position kann auf wenige, klar benennbare Weisen
verrutschen -- und jede davon laesst sich ausprobieren.

Der Test dreht die Frage deshalb um. Er fragt nicht "ist diese
Position plausibel?", sondern: "gibt es einen Tippfehler, der sie
plausibel machen wuerde?" Geprueft werden

  Vorzeichen   Breite, Laenge oder beide gespiegelt
  Vertauscht   Breite und Laenge verwechselt
  Grad-Dreher  zwei benachbarte Ziffern im Gradanteil getauscht
  Min-Dreher   zwei benachbarte Ziffern in den Minuten getauscht
  Ziffer fehlt eine Ziffer des Gradanteils verschluckt (105 -> 15)

Der Massstab ist die Nachbarschaft im eigenen Land: aus dem Namen
wird das letzte Glied als Gebiet genommen ("..., Russia") und
gemessen, wie weit der naechste andere Pegel desselben Gebiets
entfernt ist. Steht ein Satz einsam da und ruecke ihn eine der
Verwechslungen mitten in die Kette der anderen Pegel, dann ist das
kein Zufall mehr.

Eine Nachbarschaft allein reicht aber nicht: entlegene Inseln
verschieben sich unter dem Test zufaellig in die Naehe irgendeines
anderen Pegels. Deshalb kommt die Kurve dazu. Zu jeder Stelle werden
die drei naechsten Saetze gesucht und mit dem geprueften verglichen;
verrutscht ist ein Satz erst dann, wenn er an der berichtigten
Stelle auch tidenmaessig besser hineinpasst. Cape Cockburn war der
Fall, der das gelehrt hat: der Ziffernbeh:eher 79->97 haette den Satz
sauber nach Bathurst Island gesetzt, aber seine Kurve gehoert mit
drei Prozent zum Lancaster Sound und passt mit 47 Prozent nicht in
die Barrow Strait.

Zwei Fallen stecken darin, und beide haben den ersten Lauf
unbrauchbar gemacht:

  Der Satz selbst steht mit im Suchbaum. Ohne ihn auszuschliessen
  misst man nur den Betrag der Verschiebung und bekommt fuer jeden
  Min-Dreher dieselben 16.7 km gemeldet -- 60 Fehlalarme, kein
  einziger Treffer.

  Dubletten decken sich gegenseitig. Anadyr steht zweimal im
  Bestand, in der ATT- und in der NOAA-Datei, beide Male mit
  demselben Tippfehler. Solange jeder Satz den anderen als
  "Nachbarn in 0 km" sieht, faellt keiner von beiden auf. Gezaehlt
  werden deshalb Positionen, nicht Saetze.

Was der Test nicht kann: kleine Verschiebungen. Das alte Matamoros
lag 37 km daneben und mitten unter mexikanischen Nachbarn -- dafuer
ist py/lage_ausreisser.py da, das ueber die Landmaske geht. Die
beiden Werkzeuge ergaenzen sich: dieses findet die groben Spruenge
auch auf offener See, jenes die stillen Verrutscher an Land.

Usage: python3 py/tippfehler_lage.py [--ab_km 150] [--nah_km 25]
                                      [--faktor 5] [--wasser]
       --wasser  zusaetzlich den Abstand zur naechsten Wasserzelle
                 zeigen (langsam, braucht global-land-mask)
       --alle    auch Kandidaten zeigen, deren Kurve dagegen spricht
"""
from __future__ import annotations

import collections
import math
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from health_check import load_records, curve_diff                  # noqa: E402

AB_KM = 150.0        # ab hier gilt ein Satz im eigenen Gebiet als einsam
NAH_KM = 25.0        # so nah muss die berichtigte Stelle an einen Nachbarn ruecken
FAKTOR = 5.0         # und um mindestens diesen Faktor besser sein
MIND_GEBIET = 8      # kleinere Gebiete geben keinen Massstab her


def gebiet(name):
    """Letztes Glied des Namens; Stroemungssaetze zaehlen zum selben Gebiet."""
    return re.sub(r'\s+Current$', '', name.split(',')[-1].strip())


def _dreher(ziffern):
    """Alle Vertauschungen zweier benachbarter Ziffern."""
    out = set()
    for i in range(len(ziffern) - 1):
        if ziffern[i] != ziffern[i + 1]:
            out.add(ziffern[:i] + ziffern[i + 1] + ziffern[i] + ziffern[i + 2:])
    return out


def kandidaten(lat, lon):
    """-> [(bezeichnung, lat, lon)] fuer jeden denkbaren Tippfehler."""
    c = [('Vorzeichen Breite', -lat, lon),
         ('Vorzeichen Laenge', lat, -lon),
         ('beide Vorzeichen', -lat, -lon)]
    if abs(lon) <= 90:
        c.append(('Breite/Laenge vertauscht', lon, lat))
    for istlat, wert, rest in ((True, lat, lon), (False, lon, lat)):
        was = 'Breite' if istlat else 'Laenge'
        grenze = 90 if istlat else 180
        vz = -1 if wert < 0 else 1
        grad = int(abs(wert))
        minuten = (abs(wert) - grad) * 60
        zs = f'{grad:d}'
        for t in _dreher(zs):
            v = vz * (int(t) + minuten / 60)
            if abs(v) <= grenze:
                c.append((f'Grad-Dreher {was} {grad}->{int(t)}',
                          v if istlat else rest, rest if istlat else v))
        for i in range(len(zs)):
            t = zs[:i] + zs[i + 1:]
            if not t or int(t) == grad:
                continue
            v = vz * (int(t) + minuten / 60)
            if abs(v) <= grenze:
                c.append((f'Ziffer fehlt {was} {grad}->{int(t)}',
                          v if istlat else rest, rest if istlat else v))
        mi = int(round(minuten))
        for t in _dreher(f'{mi:02d}'):
            if int(t) >= 60:
                continue
            v = vz * (grad + (minuten - mi + int(t)) / 60)
            if abs(v) <= grenze:
                c.append((f'Min-Dreher {was} {mi}->{int(t)}',
                          v if istlat else rest, rest if istlat else v))
    return c


def _xyz(lat, lon):
    import numpy as np
    la, lo = np.radians(lat), np.radians(lon)
    return np.stack([np.cos(la) * np.cos(lo), np.cos(la) * np.sin(lo),
                     np.sin(la)], axis=-1)


def _km(sehne):
    return 2 * 6371.0 * math.asin(min(1.0, sehne / 2))


def _kurve(ziel, baum, welt, lat, lon, k=3):
    """-> mittlere Kurvenabweichung zu den k naechsten fremden Saetzen."""
    import numpy as np
    d, jj = baum.query(_xyz(np.array(lat), np.array(lon)), k=k + 12)
    rel = []
    for j in zip(jj):
        x = welt[j[0]]
        if x['fp'] == ziel['fp'] or (abs(x['lat'] - ziel['lat']) < 1e-3
                                     and abs(x['lon'] - ziel['lon']) < 1e-3):
            continue
        rel.append(curve_diff(ziel, x)[1])
        if len(rel) == k:
            break
    return sum(rel) / len(rel) if rel else None


def main(argv):
    import numpy as np
    from scipy.spatial import cKDTree
    g = lambda n, v: (float(argv[argv.index(n) + 1]) if n in argv else v)
    ab, nah, faktor = g('--ab_km', AB_KM), g('--nah_km', NAH_KM), g('--faktor', FAKTOR)

    recs = [r for r in load_records() if r['lat'] is not None and r['lon'] is not None]
    # Fuer den Kurvenvergleich zaehlen nur Tidensaetze: Stroemungen stehen
    # in Knoten und sind mit Pegeln nicht vergleichbar.
    welt = [r for r in recs if not r['current']]
    weltbaum = cKDTree(_xyz(np.array([r['lat'] for r in welt]),
                            np.array([r['lon'] for r in welt])))
    nach = collections.defaultdict(dict)
    for r in recs:
        # Dubletten stehen auf derselben Position und tragen denselben
        # Tippfehler; als Nachbarn wuerden sie sich gegenseitig decken.
        nach[gebiet(r['name'])].setdefault(
            (round(r['lat'], 3), round(r['lon'], 3)), []).append(r)

    treffer = []
    for reg, orte in nach.items():
        if len(orte) < MIND_GEBIET:
            continue
        punkte = sorted(orte)
        baum = cKDTree(_xyz(np.array([p[0] for p in punkte]),
                            np.array([p[1] for p in punkte])))
        for i, p in enumerate(punkte):
            d, _j = baum.query(_xyz(np.array(p[0]), np.array(p[1])), k=2)
            einsam = _km(d[1])
            if einsam < ab:
                continue
            r = orte[p][0]
            ka = None if r['current'] else _kurve(r, weltbaum, welt, p[0], p[1])
            best = None
            for was, la, lo in kandidaten(p[0], p[1]):
                dd, jj = baum.query(_xyz(np.array(la), np.array(lo)), k=2)
                neu = min([_km(x) for x, j in zip(dd, jj) if j != i] or [math.inf])
                if neu >= nah or neu * faktor >= einsam:
                    continue
                kn = None if r['current'] else _kurve(r, weltbaum, welt, la, lo)
                # Passt der Satz an der alten Stelle DEUTLICH besser in
                # die Nachbarschaft, ist dieser Tippfehler nur ein Zufall.
                # Die Schwelle ist mit Absicht grob: in Buchten und
                # Aestuaren weichen auch richtige Nachbarn stark
                # voneinander ab (Anadyr gegen die offene Kueste des
                # Anadyr-Golfs: 74 gegen 44 Prozent). Wer hier scharf
                # filtert, wirft den einen echten Fall mit den
                # Fehlalarmen zusammen hinaus.
                if (ka is not None and kn is not None
                        and kn > 2 * ka + 0.10 and '--alle' not in argv):
                    continue
                # Gesucht ist die Verwechslung, die tidenmaessig am besten
                # passt -- nicht die, die geometrisch am naechsten liegt.
                rang = (kn if kn is not None else 0.0, neu)
                if best is None or rang < best[0]:
                    best = (rang, neu, was, la, lo, kn)
            if not best:
                continue
            treffer.append((einsam, best[1:5], orte[p], reg, ka, best[5]))
    treffer.sort(key=lambda x: -x[0])

    wasser = None
    if '--wasser' in argv:
        from lage_ausreisser import ozean_abstand
        wasser = ozean_abstand

    print(f'{len(recs)} Saetze in {len(nach)} Gebieten; '
          f'einsam ab {ab:.0f} km, berichtigt naeher als {nah:.0f} km '
          f'und um Faktor {faktor:.0f} besser\n')
    print(f'{len(treffer)} Positionen sehen nach einem Tippfehler aus\n')
    for einsam, (neu, was, la, lo), rs, reg, ka, kn in treffer:
        r = rs[0]
        mehr = f' ({len(rs)} Saetze)' if len(rs) > 1 else ''
        print(f'{r["name"]}{mehr}')
        print(f'    {was}:  {r["lat"]:9.4f} {r["lon"]:10.4f}  ->  {la:9.4f} {lo:10.4f}')
        print(f'    naechster Pegel in {reg}: {einsam:.0f} km  ->  {neu:.1f} km')
        if ka is not None or kn is not None:
            f = lambda v: 'keine' if v is None else f'{v * 100:.0f}%'
            print(f'    Kurve gegen die Nachbarn: {f(ka)}  ->  {f(kn)}')
        if wasser:
            print(f'    Abstand zum Wasser: {wasser(r["lat"], r["lon"]):.0f} km  ->  '
                  f'{wasser(la, lo):.0f} km')
        for x in rs:
            print(f'    {os.path.basename(x["file"])}:{x["line"]}')
        print()
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
