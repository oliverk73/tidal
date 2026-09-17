#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Bestandsaufnahme: welche Saetze haben falsche Namen oder Positionen?

Oliver 16.09.2026: "Viele NOAA- und ATT- und auch andere Stationen haben
immer noch falsche Koordinaten oder falsche oder veraltete Namen. Das
muesste man eigentlich erstmal korrigieren." Also vor den Loeschlisten.

Geprueft wird der ganze Bestand (ohne Stroemungen) gegen:

  GeoNames   Kennt der Ortsname die Stelle? Getrennt nach: Hauptname
             passt, nur Alternativname (alte Umschrift), andere
             Schreibweise, Name sitzt 15-50 km weiter, gar nicht bekannt.
  Landmaske  Liegt die Position an Land, und wie weit bis zum Wasser?
  Raster     Steht die Position auf ganzen Bogenminuten (Buchwert,
             +-0.93 km) -- und gibt es einen genaueren Satz daneben?
  Herkunft   Ist der Satz seit dem Import angefasst worden (Git-Spur aus
             positions_locked.csv) oder traegt sein Vermerk eine
             Korrektur? Dann ist er schon einmal angesehen worden.

Geschrieben wird nur harmonics/help/namen_positionen_probe.csv.

GeoNames wird in Kacheln gelesen, sonst passt der Ausschnitt (3 Mio.
Eintraege) nicht in den Speicher: erst werden die Eintraege nach
10-Grad-Kacheln in den Scratch-Ordner sortiert, dann Kachel fuer Kachel
geprueft.

Usage: python3 py/namen_positionen_probe.py [--nur-datei <teil>]
"""
from __future__ import annotations

import collections
import csv
import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import noaa_guete_probelauf as G                                    # noqa: E402
import noaa_pruefstand as P                                         # noqa: E402
import pegel_dubletten                                              # noqa: E402
from health_check import ROOT, auf_raster, km, load_records         # noqa: E402

HELP = os.path.join(ROOT, 'harmonics/help')
AUS = os.path.join(HELP, 'namen_positionen_probe.csv')
LOCK = os.path.join(HELP, 'positions_locked.csv')
GEONAMES = os.path.join(ROOT, 'tide_tables/catalogues/geonames/umfeld.tsv')
KACHEL = 10.0
HAND = re.compile(r'Oliver|HANDENTSCHEIDUNG|berichtigt|umbenannt|Handkorrektur|verschoben')


def kachel_von(lat, lon):
    return int((lat + 90) // KACHEL), int((lon + 180) // KACHEL)


def geonames_sortieren(kacheln, ordner):
    """Einmal durch den Ausschnitt; jede Zeile in die Datei ihrer Kachel."""
    dateien = {}
    try:
        with open(GEONAMES, encoding='utf-8') as fh:
            for line in fh:
                p = line.split('\t')
                try:
                    k = kachel_von(float(p[4]), float(p[5]))
                except (ValueError, IndexError):
                    continue
                if k not in kacheln:
                    continue
                if k not in dateien:
                    dateien[k] = open(os.path.join(ordner, f'{k[0]}_{k[1]}.tsv'), 'w', encoding='utf-8')
                dateien[k].write(line)
    finally:
        for f in dateien.values():
            f.close()
    return set(dateien)


def gitter_lesen(pfad):
    """Wie G.geonames_laden, aber aus einer Kacheldatei."""
    import math
    gitter = collections.defaultdict(list)
    with open(pfad, encoding='utf-8') as fh:
        for line in fh:
            p = line.rstrip('\n').split('\t')
            lat, lon = float(p[4]), float(p[5])
            e = (p[1], lat, lon, p[6], p[7], p[8])
            haupt = {G.schluessel(p[1]), G.schluessel(p[2]),
                     G.kernschluessel(p[1]), G.kernschluessel(p[2])} - {''}
            alle = set(haupt)
            for alt in p[3].split(','):
                if alt and len(alt) < 60:
                    alle |= {G.schluessel(alt), G.kernschluessel(alt)}
            gitter[(int(math.floor(lat * 10)), int(math.floor(lon * 10)))].append((e, haupt, alle - {''}))
    return gitter


def herkunft():
    """{(datei, name): 'angesehen'|'skript'|'unveraendert'|'unklar'} aus der Git-Spur."""
    out = {}
    if not os.path.exists(LOCK):
        return out
    for r in csv.DictReader(open(LOCK, encoding='utf-8')):
        out[(r['file'], r['name'])] = r
    return out


def main(argv):
    nur = argv[argv.index('--nur-datei') + 1] if '--nur-datei' in argv else None
    recs = [r for r in load_records()
            if r['lat'] is not None and r['lon'] is not None and not r['current']
            and (not nur or nur in r['file'])]
    print(f'{len(recs)} Saetze', flush=True)
    lock = herkunft()
    verm = pegel_dubletten.vermerke()

    nach_kachel = collections.defaultdict(list)
    for r in recs:
        nach_kachel[kachel_von(r['lat'], r['lon'])].append(r)
    # Randkacheln mitnehmen: ein Ort kann jenseits der Kachelgrenze liegen
    gebraucht = set()
    for (a, b) in nach_kachel:
        for da in (-1, 0, 1):
            for db in (-1, 0, 1):
                gebraucht.add((a + da, b + db))

    ordner = tempfile.mkdtemp(prefix='geonames_kacheln_')
    print(f'GeoNames sortieren -> {ordner}', flush=True)
    da = geonames_sortieren(gebraucht, ordner)
    print(f'{len(da)} Kacheln', flush=True)

    out = []
    for nr, (k, liste) in enumerate(sorted(nach_kachel.items()), 1):
        gitter = collections.defaultdict(list)
        for da_ in (-1, 0, 1):
            for db in (-1, 0, 1):
                pfad = os.path.join(ordner, f'{k[0] + da_}_{k[1] + db}.tsv')
                if os.path.exists(pfad):
                    for zelle, eintraege in gitter_lesen(pfad).items():
                        gitter[zelle].extend(eintraege)
        for r in liste:
            befund, vn, vla, vlo, text = G.namensprobe(r, gitter)
            abstand = G.landabstand(r['lat'], r['lon'])
            l = lock.get((r['file'], r['name']))
            v = verm.get((r['file'], r['line']), '')
            stand = ('angesehen' if HAND.search(v) else
                     'skript' if l and l['provenance'] == 'manual' else
                     'unklar' if not l or l['provenance'] == 'ambiguous' else 'unveraendert')
            if not befund and abstand < 3 and not auf_raster(r['lat'], r['lon']):
                continue
            out.append(dict(
                datei=os.path.basename(r['file']), name=r['name'],
                lat=f"{r['lat']:.4f}", lon=f"{r['lon']:.4f}",
                klasse=P.klasse(r) or 'Uebertragung/Modell', stand=stand,
                raster='ja' if auf_raster(r['lat'], r['lon']) else '',
                an_land=f'{abstand:.0f}' if abstand >= 3 else '',
                fluss='ja' if abstand >= 3 and G.P_FLUSS.search(r['name']) else '',
                name_befund=befund, vorschlag_name=vn,
                vorschlag_lat=vla, vorschlag_lon=vlo, hinweis=text, entscheidung=''))
        print(f'  Kachel {nr}/{len(nach_kachel)} {k}: {len(liste)} Saetze, {len(out)} Befunde', flush=True)

    felder = ['datei', 'name', 'lat', 'lon', 'klasse', 'stand', 'raster', 'an_land', 'fluss',
              'name_befund', 'vorschlag_name', 'vorschlag_lat', 'vorschlag_lon', 'hinweis', 'entscheidung']
    with open(AUS, 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=felder)
        w.writeheader()
        w.writerows(out)
    print(f'\n{len(out)} Saetze mit Befund von {len(recs)}')
    for feld in ('name_befund', 'stand', 'klasse'):
        for wert, n in collections.Counter(z[feld] for z in out).most_common():
            print(f'  {feld:12} {wert or "(ohne)":22} {n:6d}')
    print(f"  an Land >=3 km {sum(1 for z in out if z['an_land']):6d}")
    print(f"  Rasterposition {sum(1 for z in out if z['raster']):6d}")
    print('->', os.path.relpath(AUS, ROOT))


if __name__ == '__main__':
    main(sys.argv[1:])
