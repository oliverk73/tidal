#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sucht Saetze, deren Position nicht am Wasser liegen kann.

Anlass: "Matamoros, Tamaulipas, Mexico" stand auf 25.8833 / -97.5167.
Das ist die Stadt, dreissig Kilometer landeinwaerts -- dort gibt es
weder Meer noch tidenabhaengigen Fluss. Die Angabe stammt
uebereinstimmend von CICESE und von NOAA (Station 9500101), war also
zweimal amtlich und trotzdem falsch; der Pegel liegt an der Playa Lauro
Villar suedlich der Rio-Bravo-Muendung.

Gemessen wird der Abstand zum naechsten Ozean nach der GLOBE-Landmaske
(Paket global-land-mask, rund ein Kilometer Auflösung). Vom Punkt aus
werden Ringe wachsenden Radius abgetastet, bis eine Wasserzelle
gefunden ist.

Zwei fruehere Versuche sind daran gescheitert, dass sie ohne Landmaske
auskommen wollten, und beide Fehlschlaege sind lehrreich genug, um sie
festzuhalten:

  Der Abstand zum naechsten anderen Pegel, gemessen relativ zur
  oertlichen Dichte. Die alte Matamoros-Position kam damit auf Rang 159
  von 5708 -- gefunden, aber unter 158 berechtigten Faellen begraben,
  denn oben stehen Osterinsel, Crozet, Heard und die DART-Bojen, die
  wirklich einsam liegen.

  Die groesste Luecke zwischen den Peilungen zu den naechsten Nachbarn:
  liegen alle auf einer Seite, ist der Punkt "neben" der Kuestenlinie.
  Fuer die alte Position 315 Grad gegen einen Median von 166 -- aber
  1567 Positionen liegen ueber 200 Grad, meist zu Recht (Inseln,
  Kanalenden, Messpunkte vor der Kueste).

Was die Landmaske NICHT kann: sie kennt keine Tidefluesse. Hamburg St.
Pauli liegt 12 km von der naechsten Ozeanzelle und ist trotzdem ein
richtiger Pegel. Der Karnaphuli in Chittagong dagegen ist breit genug,
um selbst als Wasser zu gelten -- Kalurghat kommt auf 1 km.

Der naheliegende Ausweg, zusaetzlich nach einem benannten Fluss zu
fragen, FUNKTIONIERT NICHT, und das ist die wichtigste Erkenntnis
dieses Werkzeugs. Matamoros liegt am Rio Bravo: Natural Earth setzt die
falsche Position 2.5 km vom "Rio Grande", die berichtigte am Strand
dagegen 16 km entfernt. Ein Flusstest haette also genau den falschen
Satz entlastet und den richtigen verdaechtigt. Der Grund ist, dass die
Frage nicht "liegt hier ein Fluss?" lautet, sondern "reicht die Tide
hier herauf?" -- und das ist keine geometrische, sondern eine
hydrographische Frage. Albany liegt 220 km den Hudson hinauf und ist
tidenabhaengig, Matamoros 35 km den Rio Bravo hinauf und nicht.

Was stattdessen hilft, ist die Einsamkeit: an einem echten Tidefluss
steht eine Kette von Pegeln (Hudson, St. Lorenz, Gambia), an einer
verrutschten Position steht nichts. Sortiert wird deshalb nach
min(Abstand zum Wasser, Abstand zum naechsten anderen Pegel). Die alte
Matamoros-Position kommt damit auf Rang 31 von 943, und nur 62
Positionen liegen ueber zwanzig Kilometern -- eine Liste, die ein
Mensch durchsieht. Ueber ihr stehen Amazonas, Gambia, Guyana,
arktische Fjorde und die Fluesse von Sarawak, die alle richtig stehen.

Ein Urteil ist das nicht und kann es nicht sein.

Usage: python3 py/lage_ausreisser.py [--ab_km 8] [--zeige 40] [--csv]
"""
from __future__ import annotations

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from health_check import load_records                              # noqa: E402

AB_KM = 8.0
RINGE = (1, 2, 3, 5, 8, 12, 18, 25, 35, 50, 70, 100)


def ozean_abstand(lat, lon):
    """-> km bis zur naechsten Wasserzelle, 0.0 wenn der Punkt selbst Wasser ist."""
    import numpy as np
    from global_land_mask import globe
    if not globe.is_land(lat, lon):
        return 0.0
    for r in RINGE:
        n = max(8, int(r * 4))
        w = np.linspace(0, 2 * math.pi, n, endpoint=False)
        dl = r / 111.32
        la = np.clip(lat + dl * np.cos(w), -89.9, 89.9)
        # Auf hohen Breiten wird ein Grad Laenge kurz; ohne die Korrektur
        # taestete der Ring in Ostwest-Richtung viel zu eng ab.
        lo = lon + dl * np.sin(w) / max(0.05, math.cos(math.radians(lat)))
        lo = ((lo + 180) % 360) - 180
        if np.any(~globe.is_land(la, lo)):
            return float(r)
    return float('inf')


def main(argv):
    import numpy as np
    g = lambda n, v: (float(argv[argv.index(n) + 1]) if n in argv else v)
    ab, zeige = g('--ab_km', AB_KM), int(g('--zeige', 40))
    alle = [r for r in load_records()
            if r['lat'] is not None and r['lon'] is not None]
    # Nach Position zusammenfassen: an einem Hafen stehen oft mehrere
    # Saetze auf demselben Punkt, und die Landmaske sagt fuer alle
    # dasselbe.
    punkte = {}
    for r in alle:
        punkte.setdefault((round(r['lat'], 3), round(r['lon'], 3)), []).append(r)
    print(f'{len(alle)} Saetze an {len(punkte)} Positionen', file=sys.stderr)

    # Abstand zum naechsten anderen Pegel -- ueber Einheitsvektoren, damit
    # der Datumswechsel kein Sonderfall ist.
    orte = sorted(punkte)
    lat = np.radians(np.array([o[0] for o in orte]))
    lon = np.radians(np.array([o[1] for o in orte]))
    xyz = np.stack([np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon),
                    np.sin(lat)], axis=1)
    m = len(orte)
    nachbar = np.zeros(m)
    for a in range(0, m, 512):
        b = min(a + 512, m)
        dd = np.arccos(np.clip(xyz[a:b] @ xyz.T, -1.0, 1.0)) * 6371.0
        for i in range(b - a):
            dd[i, a + i] = np.inf
        nachbar[a:b] = dd.min(axis=1)

    treffer = []
    for i, o in enumerate(orte):
        rs = punkte[o]
        d = ozean_abstand(rs[0]['lat'], rs[0]['lon'])
        if d >= ab:
            treffer.append((min(d, nachbar[i]), d, nachbar[i], rs))
        if i and i % 2000 == 0:
            print(f'  {i}/{m}', file=sys.stderr, flush=True)
    treffer.sort(key=lambda x: -x[0])

    n = sum(len(rs) for _s, _d, _nb, rs in treffer)
    print(f'\n{len(treffer)} Positionen ({n} Saetze) liegen weiter als '
          f'{ab:.0f} km von der naechsten Wasserzelle, sortiert nach '
          f'min(Wasser, naechster Pegel)\n')
    print(f'{"Rang":>4} {"Wasser":>7} {"Pegel":>8}  Satz')
    for rang, (_s, d, nb, rs) in enumerate(treffer[:zeige], 1):
        r = rs[0]
        mehr = f' (+{len(rs) - 1})' if len(rs) > 1 else ''
        print(f'{rang:4} {d:6.0f} km {nb:7.1f} km  {r["name"][:40]:40}{mehr:5} '
              f'{r["lat"]:8.4f} {r["lon"]:9.4f}  {os.path.basename(r["file"])[:24]}')
    if len(treffer) > zeige:
        print(f'  ... und {len(treffer) - zeige} weitere (--zeige)')

    if '--csv' in argv:
        import csv
        p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         'harmonics/help/lage_ausreisser.csv')
        with open(p, 'w', newline='', encoding='utf-8') as fh:
            w = csv.writer(fh)
            w.writerow(['rang', 'ozean_km', 'pegel_km', 'datei', 'name', 'lat', 'lon'])
            for rang, (_s, d, nb, rs) in enumerate(treffer, 1):
                for r in rs:
                    w.writerow([rang, f'{d:.0f}', f'{nb:.1f}',
                                os.path.basename(r['file']), r['name'],
                                f'{r["lat"]:.4f}', f'{r["lon"]:.4f}'])
        print(f'\n-> {p}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
