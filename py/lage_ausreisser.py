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
richtiger Pegel. Solche Faelle stehen erwartungsgemaess in der Liste,
und darum ist es eine Liste zum Nachsehen und kein Urteil. Der
Karnaphuli in Chittagong dagegen ist breit genug, um selbst als Wasser
zu gelten -- Kalurghat kommt auf 1 km.

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

    treffer = []
    for i, ((la, lo), rs) in enumerate(sorted(punkte.items()), 1):
        d = ozean_abstand(rs[0]['lat'], rs[0]['lon'])
        if d >= ab:
            treffer.append((d, rs))
        if i % 2000 == 0:
            print(f'  {i}/{len(punkte)}', file=sys.stderr, flush=True)
    treffer.sort(key=lambda x: -x[0])

    n = sum(len(rs) for _d, rs in treffer)
    print(f'\n{len(treffer)} Positionen ({n} Saetze) liegen weiter als '
          f'{ab:.0f} km von der naechsten Wasserzelle\n')
    for d, rs in treffer[:zeige]:
        r = rs[0]
        mehr = f' (+{len(rs) - 1})' if len(rs) > 1 else ''
        print(f'  {d:6.0f} km  {r["name"][:44]:44}{mehr:5} {r["lat"]:8.4f} '
              f'{r["lon"]:9.4f}  {os.path.basename(r["file"])[:26]}')
    if len(treffer) > zeige:
        print(f'  ... und {len(treffer) - zeige} weitere (--zeige)')

    if '--csv' in argv:
        import csv
        p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         'harmonics/help/lage_ausreisser.csv')
        with open(p, 'w', newline='', encoding='utf-8') as fh:
            w = csv.writer(fh)
            w.writerow(['ozean_km', 'datei', 'name', 'lat', 'lon'])
            for d, rs in treffer:
                for r in rs:
                    w.writerow([f'{d:.0f}', os.path.basename(r['file']), r['name'],
                                f'{r["lat"]:.4f}', f'{r["lon"]:.4f}'])
        print(f'\n-> {p}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
