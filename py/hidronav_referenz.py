#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Liest die Gezeitentafeln der peruanischen HIDRONAV.

Die Direccion de Hidrografia y Navegacion veroeffentlicht je Hafen und
Monat ein einseitiges PDF. Unter tide_tables/peru/ liegen 26 Haefen fuer
Juni und Juli 2026 sowie derselbe Satz fuer Juni 2024.

Der Textaufbau ist ueber alle 26 Dateien gleich und sehr einfach: eine
Datumszeile, danach die Uhrzeiten des Tages, danach die zugehoerigen
Hoehen in Zentimetern. Zeiten und Hoehen stehen also NICHT nebeneinander,
sondern in zwei Bloecken hintereinander -- gepaart wird ueber die
Position. Ein fehlendes viertes Ereignis ist in beiden Bloecken als "-"
ausgewiesen, die Bloecke bleiben dadurch gleich lang.

Die Zeiten sind Ortszeit, Peru steht ganzjaehrig auf UTC-5 und kennt
keine Sommerzeit.

Hoch- und Niedrigwasser sind nicht beschriftet; die Art wird wie bei den
brasilianischen Tafeln aus den Nachbarwerten bestimmt.

Die Position steht nicht in der Tafel und wird aus dem Bestand geholt
(ORTE). Fuer "Caleta Grau" gibt es dort keinen Satz -- der naechste
Namensverwandte, Puerto Grau in Tacna, liegt 1300 km entfernt in einer
anderen Region. Der Ort bleibt deshalb aussen vor; eine geratene
Position waere schlimmer als eine Luecke.

Usage: python3 py/hidronav_referenz.py            Uebersicht
       python3 py/hidronav_referenz.py <text>     einen Ort zeigen
"""
from __future__ import annotations

import datetime as dt
import glob
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PERU = os.path.join(ROOT, 'tide_tables/peru')
TZ = -5                      # ganzjaehrig, keine Sommerzeit

MONAT = {'ENE': 1, 'FEB': 2, 'MAR': 3, 'ABR': 4, 'MAY': 5, 'JUN': 6,
         'JUL': 7, 'AGO': 8, 'SET': 9, 'SEP': 9, 'OCT': 10, 'NOV': 11,
         'DIC': 12}
# Jeder Tag hat genau vier Plaetze, fehlende sind mit "-" besetzt --
# in BEIDEN Bloecken, sonst kaeme das Paaren aus dem Tritt.
PLAETZE = 4
DATUM = re.compile(r'^(\d{2}) ([A-ZÁÉÍÓÚ]{3})\. (\d{4})$')
UHR = re.compile(r'^(\d{1,2}):(\d{2})$')
CM = re.compile(r'^(-?\d+) cm$')

# Tafelname -> Satzname im Bestand, aus dem die Position kommt.
ORTE = {
    'ancon': 'Ancón, Lima, Peru',
    'atico': 'Atico, Arequipa, Peru',
    'bayovar': 'Bayovar, Peru',
    'cabo blanco': 'Cabo Blanco, Piura, Peru',
    'callao': 'Callao (La Punta), Peru',
    'cerro azul': 'Cerro Azul, Lima, Peru',
    'chala': 'Chala, Peru',
    'chancay': 'Chancay, Peru',
    'chimbote': 'Chimbote, Peru',
    'eten': 'Punta Eten, Peru',
    'huacho': 'Huacho, Peru',
    'huarmey': 'Bahía Huarmey, Peru',
    'ilo': 'Ilo, Peru',
    'lobitos': 'Caleta Lobitos, Peru',
    'lobos de afuera': 'Lobos De Afuera, Peru',
    'malabrigo': 'Malabrigo, La Libertad, Peru',
    'matarani': 'Matarani, Peru',
    'melchorita': 'Pampa Melchorita, Lima, Peru',
    'paita': 'Paita, Peru',
    'pisco': 'Pisco, Peru',
    'salaverry': 'Salaverry (Trujillo), La Libertad, Peru',
    'san juan': 'Puerto San Juan, Peru',
    'supe': 'Supe, Lima, Peru',
    'talara': 'Talara, Peru',
    'zorritos': 'Zorritos, Peru',
}


def _seite(pfad):
    import pymupdf
    with pymupdf.open(pfad) as d:
        return '\n'.join(s.get_text() for s in d)


def _ereignisse(pfad):
    """-> [(datetime UTC, hoehe_m)]

    Je Tag erst alle Uhrzeiten, dann alle Hoehen. Beide Bloecke sind
    gleich lang, weil ein fehlendes Ereignis in beiden als "-" steht.
    """
    zeilen = [z.strip() for z in _seite(pfad).split('\n') if z.strip()]
    aus, tag, uhren, hoehen = [], None, [], []

    def abschliessen():
        if tag is None or len(uhren) != len(hoehen):
            return
        for u, h in zip(uhren, hoehen):
            if u is None or h is None:
                continue
            aus.append((dt.datetime.combine(tag, u) - dt.timedelta(hours=TZ),
                        h / 100.0))

    for z in zeilen:
        m = DATUM.match(z)
        if m:
            abschliessen()
            mon = MONAT.get(m.group(2).upper())
            tag = dt.date(int(m.group(3)), mon, int(m.group(1))) if mon else None
            uhren, hoehen = [], []
            continue
        if tag is None:
            continue
        u, c = UHR.match(z), CM.match(z)
        if u:
            uhren.append(dt.time(int(u.group(1)) % 24, int(u.group(2))))
        elif c:
            hoehen.append(int(c.group(1)))
        elif z == '-':
            # Der Strich steht in beiden Bloecken, und beide Bloecke
            # stehen hintereinander. Ueber die Zugehoerigkeit entscheidet
            # deshalb nur der Platz: die ersten vier Marken sind Zeiten,
            # die naechsten vier Hoehen.
            #
            # Wer stattdessen die Laengen vergleicht, verschiebt den
            # ganzen Tag: am 1. Juni stehen in Callao die Zeiten
            # 06:54/13:33/17:45/- ueber den Hoehen 102/50/64/-, und der
            # Strich landet faelschlich im Hoehenblock. Dann bekommt
            # 13:33 die 102 cm des Morgenhochwassers, und die Tafel ist
            # um ein Ereignis verdreht -- ohne dass etwas auffiele.
            (uhren if len(uhren) < PLAETZE else hoehen).append(None)
    abschliessen()
    return sorted(set(aus))


def stationen():
    import health_check
    VORRANG = ('harmonics_utide_tidetables.txt', 'harmonics_utide_observations.txt')
    recs = {}
    for r in health_check.load_records():
        if r['lat'] is None or r['current']:
            continue
        d = os.path.basename(r['file'])
        rang = VORRANG.index(d) if d in VORRANG else len(VORRANG)
        if r['name'] not in recs or rang < recs[r['name']][0]:
            recs[r['name']] = (rang, r)
    aus = []
    for k, name in sorted(ORTE.items()):
        ps = sorted(glob.glob(os.path.join(PERU, '**', f'Tabla de mareas {k}.pdf'),
                              recursive=True))
        r = recs.get(name)
        if not ps or r is None:
            continue
        aus.append({'code': k, 'name': name, 'lat': r[1]['lat'],
                    'lon': r[1]['lon'], 'dateien': ps})
    return aus


def vorhersage(st, ab=dt.datetime(2026, 1, 1)):
    """Alle Ereignisse in UTC. Der Juni 2024 bleibt aussen vor, damit die
    Messung einen zusammenhaengenden Zeitraum sieht."""
    ev = []
    for p in st['dateien']:
        ev += [(z, h) for z, h in _ereignisse(p) if z >= ab]
    import dhn_qualitaet
    return dhn_qualitaet.art_bestimmen(sorted(set(ev)))


def main(argv):
    nur = next((a for a in argv if not a.startswith('--')), None)
    st = stationen()
    if not nur:
        print(f'{len(st)} Haefen mit Tafel und Position')
        for s in st:
            v = vorhersage(s)
            sp = (f'{min(z for z, _h, _a in v):%Y-%m-%d} bis '
                  f'{max(z for z, _h, _a in v):%Y-%m-%d}') if v else '-'
            print(f'  {s["code"]:16} {s["name"][:40]:40} {s["lat"]:8.4f} '
                  f'{s["lon"]:9.4f}  {len(v):4} Ereignisse  {sp}')
        return 0
    for s in st:
        if nur.lower() not in s['code'] and nur.lower() not in s['name'].lower():
            continue
        v = vorhersage(s)
        print(f'{s["name"]}  {s["lat"]:.4f} {s["lon"]:.4f}  UTC{TZ:+d}  '
              f'{len(v)} Ereignisse')
        for z, h, a in v[:5]:
            print(f'   {z:%Y-%m-%d %H:%M} UTC  {h:6.2f} m  {a}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
