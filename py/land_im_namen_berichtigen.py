#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Berichtigt das Land im Stationsnamen nach einer Handentscheidung.

Gegenstueck zu py/country_berichtigen.py: dort folgt das Feld dem Namen,
hier folgt der Name der Entscheidung. Gebraucht wird das, wo der Name
selbst falsch ist -- "Pinang (Georgetown), Indonesia" liegt in Malaysia,
"Anewa Bay, Bougainville, Solomon Islands" liegt in Papua-Neuguinea,
"Weizhou Dao, Vietnam" liegt vor der chinesischen Kueste.

Gelesen wird harmonics/help/land_gegen_position_Edit.csv, Spalte
entscheidung: dort steht das Land, das gelten soll. "ok" heisst, dass
die Position recht hat und deren Land uebernommen wird.

Mitgezogen werden das Feld country und die Region, denn die haengt am
Land. Der alte Name bleibt als Kommentar im Satz, und die Guetetabellen
werden nachgezogen -- sie sind auf den Namen verschluesselt.

Ohne --schreiben wird nur gezeigt, was passieren wuerde.

Usage: python3 py/land_im_namen_berichtigen.py [--schreiben]
"""
from __future__ import annotations

import collections
import csv
import datetime as dt
import glob
import os
import re
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import region_felder_fuellen as rf                                  # noqa: E402
import sicher_schreiben                                             # noqa: E402
from health_check import load_records, ROOT, MERIDIAN               # noqa: E402

HELP = os.path.join(ROOT, 'harmonics/help')
BACKUP = os.path.join(ROOT, 'harmonics/backup')
QUELLE = os.path.join(HELP, 'land_gegen_position_Edit.csv')
LOG = os.path.join(HELP, 'land_im_namen_berichtigt.csv')
TIPPFEHLER = {'senegel': 'Senegal'}
# Was kein Land ist und deshalb nicht als letztes Namensglied taugt --
# dazu die De-facto-Gebiete, die Natural Earth eigenstaendig fuehrt, der
# Bestand aber zum Staat zaehlt. Oliver hat das ausdruecklich so
# entschieden: Somaliland gehoert zu Somalia, Nordzypern zu Zypern, und
# die Hongkonger Saetze heissen ohnehin schon richtig
# "Ko Lau Wan, Hong Kong, China" -- Hongkong als Region, China als Land.
KEIN_LAND = {'somaliland', 'northern cyprus',
             'hong kong s.a.r.', 'macao s.a.r.', 'macao s.a.r'}
# Guantanamo ist der Gegenfall zu Somaliland: die USA haben die
# Kontrolle, Kuba nach dem Pachtvertrag von 1903 ausdruecklich die
# Souveraenitaet ("ultimate sovereignty of the Republic of Cuba"). Ein
# Stuetzpunkt ist zudem kein Land und taugt nicht als letztes
# Namensglied. Der Stuetzpunkt wandert deshalb in den Namen, das Land
# bleibt Kuba.
SONDERFORM = {'US Naval Base Guantanamo Bay':
              ('Cuba', 'Guantanamo Bay (US Naval Base), Cuba')}


POSITION = re.compile(r'Position\s*korrigieren\s*:\s*(-?[\d.]+)\s*,\s*(-?[\d.]+)',
                      re.I)


def positionen():
    """-> {(Name, Dateibasis): (lat, lon)} aus der Kommentarspalte.

    Die Liste hat neben der Entscheidung eine Spalte fuer Anmerkungen,
    und dort stand "Position korrigieren: 40.116040, 124.387975" fuer
    Dandong. Beim ersten Lauf habe ich nur die Entscheidungsspalte
    gelesen und die Anmerkung uebersehen -- deshalb wird sie jetzt
    ausgewertet. Erkannt wird genau diese Schreibweise; alles andere
    bleibt Text fuer Menschen.
    """
    out = {}
    for r in csv.DictReader(open(QUELLE, encoding='utf-8')):
        for wert in r.values():
            m = POSITION.search(wert or '')
            if m:
                out[(r['name'], r['datei'])] = (float(m.group(1)), float(m.group(2)))
                break
    return out


def entscheidungen():
    """-> {(Name, Dateibasis): Soll-Land}."""
    out = {}
    for r in csv.DictReader(open(QUELLE, encoding='utf-8')):
        e = (r.get('entscheidung') or '').strip()
        if not e:
            continue
        soll = r['liegt_in'] if e.lower() == 'ok' else TIPPFEHLER.get(e.lower(), e)
        if soll in SONDERFORM:
            out[(r['name'], r['datei'])] = SONDERFORM[soll]
            continue
        if rf._flach(soll) in KEIN_LAND:
            continue
        if rf._flach(soll) == rf._flach(r['land_im_namen']):
            continue
        out[(r['name'], r['datei'])] = soll
    return out


def main(argv):
    schreiben = '--schreiben' in argv
    soll = entscheidungen()
    # Eine Entscheidung ueber ein Land gilt fuer den PEGEL, nicht fuer die
    # Zeile der Liste. "Puerto de Hierro, Trinidad and Tobago" stand
    # zweimal im Bestand, gemeldet war nur einer -- der andere liegt im
    # Golf von Paria, wo kein Polygon greift. Ich habe daraufhin einen
    # umbenannt und den anderen stehen lassen. Dasselbe war bei den
    # Falklandinseln passiert: 4 von 18 berichtigt. Deshalb gilt die
    # Entscheidung ab jetzt fuer jeden Satz mit demselben Namen.
    nach_name = {}
    for (name, _datei), wahl in soll.items():
        nach_name.setdefault(name, wahl)
    recs = [r for r in load_records() if r['name'] in nach_name]
    soll = {(r['name'], os.path.basename(r['file'])): nach_name[r['name']]
            for r in recs}
    print(f'{len(soll)} Entscheidungen, {len(recs)} Saetze betroffen')
    polys = rf.polygone()
    heute = dt.datetime.now().strftime('%Y%m%d')
    stamp = dt.datetime.now().strftime('%Y%m%d_%H%M')

    proDatei = collections.defaultdict(list)
    umbenannt = []
    for r in recs:
        wahl = soll[(r['name'], os.path.basename(r['file']))]
        fest = None
        if isinstance(wahl, tuple):
            land, fest = wahl
        else:
            land = wahl
        teile = [x.strip() for x in r['name'].split(',')]
        # Traegt der Name auch eine Region, gehoert die zum ALTEN Land.
        # "Taraku Jima, Hokkaido, Japan" darf nicht zu "..., Hokkaido,
        # Russia" werden -- Hokkaido ist eine japanische Praefektur. Die
        # Region wird deshalb aus der Position im neuen Land neu bestimmt
        # oder weggelassen.
        neu_reg = None
        if r['lat'] is not None:
            t = (rf.welches(r['lon'], r['lat'], polys, land)
                 or rf.naechstes(r['lon'], r['lat'], polys, 100.0, land))
            neu_reg = rf.latin1(t[1]) if t else None
        # Bei kleinen Gebieten heisst die Region wie das Land ("Falkland
        # Islands, Falkland Islands") -- dann faellt sie weg.
        if neu_reg and rf._flach(neu_reg) == rf._flach(land):
            neu_reg = None
        if rf._flach(land) in ('united states of america', 'united states'):
            # Der Bestand schreibt US-Stationen als "Ort, Staat" ohne Land.
            neu_name = ', '.join(teile[:1] + ([neu_reg] if neu_reg else []))
        elif len(teile) >= 3:
            neu_name = ', '.join(teile[:-2] + ([neu_reg] if neu_reg else [])
                                 + [land])
        else:
            neu_name = ', '.join(teile[:-1] + [land])
        if fest:
            neu_name = fest
        proDatei[r['file']].append((r['line'], r, neu_name, land))
        umbenannt.append((r['name'], neu_name, os.path.basename(r['file'])))
    for a, b, d in sorted(umbenannt)[:60]:
        print(f'   {a[:46]:48} -> {b[:46]}')
    if not schreiben:
        print(f'\n{len(umbenannt)} Namen waeren zu aendern')
        return 0

    for datei, menge in sorted(proDatei.items()):
        voll = os.path.join(ROOT, datei)
        lines = open(voll, encoding='iso-8859-1').read().split('\n')
        vorher = sum(1 for k, l in enumerate(lines)
                     if l and not l.startswith('#') and k + 1 < len(lines)
                     and MERIDIAN.match(lines[k + 1]))
        for zeile, r, neu_name, land in sorted(menge, key=lambda x: -x[0]):
            i = zeile - 1
            if lines[i].rstrip() != r['name']:
                print(f'   UEBERSPRUNGEN: Zeile {zeile} ist nicht {r["name"]!r}')
                continue
            t = None
            if r['lat'] is not None:
                t = (rf.welches(r['lon'], r['lat'], polys, land)
                     or rf.naechstes(r['lon'], r['lat'], polys, 100.0, land))
            neu_reg = rf.latin1(t[1]) if t else None
            j = i - 1
            while j >= 0 and lines[j].startswith('#'):
                m = re.match(r'#\s*([a-z_0-9]+):', lines[j])
                if m:
                    if m.group(1) == 'country':
                        lines[j] = f'# country: {land}'
                    elif m.group(1) in rf.FELDER and neu_reg:
                        lines[j] = f'# {m.group(1)}: {neu_reg}'
                j -= 1
            lines[i] = neu_name
            lines[i:i] = [f'# note: {heute} Land im Namen berichtigt (vorher '
                          f'"{r["name"]}"),',
                          '# note: -- die Position liegt in einem anderen Staat; '
                          'von Hand entschieden.']
        shutil.copy2(voll, os.path.join(
            BACKUP, os.path.basename(datei) + f'.vor_landname_{stamp}'))
        sicher_schreiben.schreiben(voll, '\n'.join(lines))
        nachher = sum(1 for k, l in enumerate(lines)
                      if l and not l.startswith('#') and k + 1 < len(lines)
                      and MERIDIAN.match(lines[k + 1]))
        print(f'   {os.path.basename(datei):46} {len(menge):4} Namen, '
              f'{vorher} -> {nachher}')
        if nachher != vorher:
            print('   ACHTUNG: Satzzahl veraendert!')
            return 1

    # Guetetabellen nachziehen -- sie sind auf den Namen verschluesselt.
    karte = {(a, d): b for a, b, d in umbenannt}
    n = 0
    for p in sorted(glob.glob(os.path.join(HELP, '*qualitaet*.csv'))):
        rows = list(csv.DictReader(open(p, encoding='utf-8')))
        if not rows or 'satz' not in rows[0]:
            continue
        k = 0
        for row in rows:
            neu = karte.get((row.get('satz', ''), row.get('datei', '')))
            if neu:
                row['satz'] = neu
                k += 1
        if k:
            with open(p, 'w', newline='', encoding='utf-8') as fh:
                w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
                w.writeheader()
                w.writerows(rows)
            n += k
    print(f'{n} Tabellenzeilen nachgezogen')
    neu_datei = not os.path.exists(LOG)
    with open(LOG, 'a', newline='', encoding='utf-8') as fh:
        w = csv.writer(fh)
        if neu_datei:
            w.writerow(['datum', 'name_alt', 'name_neu', 'datei'])
        for a, b, d in umbenannt:
            w.writerow([heute, a, b, d])
    print(f'\n{len(umbenannt)} Namen berichtigt -> {LOG}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
