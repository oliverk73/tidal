#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ordnet npz-Reihen ohne eigene Kennung einer Position zu.

Die meisten Reihen bringen Name und Position im Archiv mit. Die
deutschen PEGELONLINE-Reihen nicht: sie enthalten nur datetimes_utc und
levels_cm. Damit fielen alle 99 aus jeder Guetepruefung heraus -- und
das war ausgerechnet der Bestand, in dem die TICON-Saetze 40 Minuten zu
spaet liegen. Der Fehler blieb unsichtbar, weil die Reihe unlesbar war.

Zugeordnet wird ueber die amtliche Kennung, nicht ueber den Namen. Zu
jeder Reihe liegt das Archiv, aus dem sie stammt, und darin eine
zeitreiheninformation.txt mit station_name und station_number -- die
WSV-Pegelnummer. PEGELONLINE gibt zu jeder Nummer Koordinaten heraus
(rest-api/v2/stations.json, 786 Pegel), und damit ist die Position
exakt statt geraten.

Ein erster Anlauf hat stattdessen den Dateinamen geraten und kam auf 59
von 105. Der Name ist dort eine Kurzform ohne Sonderzeichen, mit
WEGGELASSENEN Umlauten -- "borkumsdstrand" ist Borkum (Suedstrand),
nicht "borkumsudstrand" --, und Kuerzel wie "bhvalterleuchtturm"
(Bremerhaven Alter Leuchtturm) oder "whvneuervorhafen" (Wilhelmshaven
Neuer Vorhafen) sind so gar nicht aufzuloesen. Die Namenssuche bleibt
nur als Rueckfall fuer Reihen ohne Archiv.

Die Pegelliste wird einmal geholt und daneben abgelegt; danach laeuft
das Werkzeug ohne Netz.

Das Ergebnis liegt als npz_stationen.json neben den Reihen und wird von
py/messreihe_qualitaet.py gelesen. Es steht bewusst dort und nicht im
Baum: water_levels ist nicht versioniert, dieses Skript schon.

Fuer Ordner mit CSV-Reihen und einem Stationskatalog daneben schreibt
--katalog dasselbe Beiblatt unter dem Namen stationen.json. Die
kanadischen Ordner fuehren je Provinz ein _xx_stations.json mit Code,
Name und Koordinaten, und die Reihen heissen <Code>_<Name>_wlp.csv --
1136 Dateien, von denen bisher zehn gelesen wurden.

Usage: python3 py/npz_stationen_bauen.py [Ordner]     (Vorgabe: Germany)
       python3 py/npz_stationen_bauen.py --katalog [Ordner ...]
"""
from __future__ import annotations

import collections
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from health_check import load_records, ROOT                       # noqa: E402

REIHEN = os.path.join(ROOT, 'water_levels')
KASTEN = {'Germany': (48, 56, 5, 15)}     # lat/lon-Fenster je Ordner


def schluessel(s):
    """-> zwei Formen: Umlaute umschrieben und Umlaute getilgt."""
    s = s.lower()
    a = b = s
    for x, y in (('ä', 'a'), ('ö', 'o'), ('ü', 'u'), ('ß', 'ss')):
        a = a.replace(x, y)
    for x in 'äöü':
        b = b.replace(x, '')
    b = b.replace('ß', 'ss')
    return {re.sub(r'[^a-z0-9]', '', a), re.sub(r'[^a-z0-9]', '', b)}


def formen(name):
    v = name.split(',')[0]
    out = {v, re.sub(r'\s*\(.*?\)', '', v), v.replace('(', '').replace(')', '')}
    m = re.match(r'^(.*?)\s*\((.*)\)\s*$', v)
    if m:
        out |= {m.group(1), m.group(2), f'{m.group(1)} {m.group(2)}',
                f'{m.group(2)} {m.group(1)}'}
    return out


PEGELONLINE = ('https://www.pegelonline.wsv.de/webservices/rest-api/v2/'
               'stations.json')


def pegelliste(ordner):
    """-> {Pegelnummer: (lat, lon, Name)} von PEGELONLINE, einmal geholt."""
    import urllib.request
    zwischen = os.path.join(REIHEN, ordner, 'pegelonline_stations.json')
    if not os.path.exists(zwischen):
        req = urllib.request.Request(
            PEGELONLINE, headers={'User-Agent': 'tidal-corpus/1.0 '
                                  '(harmonic constant verification)'})
        d = json.load(urllib.request.urlopen(req, timeout=60))
        json.dump(d, open(zwischen, 'w', encoding='utf-8'), ensure_ascii=False)
    d = json.load(open(zwischen, encoding='utf-8'))
    return {x['number']: (x['latitude'], x['longitude'], x['longname'])
            for x in d if x.get('latitude') and x.get('longitude')}


def kennung(reihe, ordner):
    """-> (station_number, station_name) aus dem Archiv neben der Reihe."""
    import zipfile
    basis = os.path.join(REIHEN, ordner)
    kandidaten = glob.glob(os.path.join(basis, f'*-{reihe}-*', 
                                        'zeitreiheninformation.txt'))
    for pfad in kandidaten:
        return _lies_info(open(pfad, encoding='utf-8', errors='replace').read())
    for z in glob.glob(os.path.join(basis, f'*-{reihe}-*.zip')):
        try:
            with zipfile.ZipFile(z) as f:
                for n in f.namelist():
                    if n.endswith('zeitreiheninformation.txt'):
                        return _lies_info(f.read(n).decode('utf-8', 'replace'))
        except Exception:
            pass
    return None, None


def _lies_info(text):
    nr = name = None
    for zeile in text.split('\n'):
        if zeile.startswith('station_number='):
            nr = zeile.split('=', 1)[1].strip()
        elif zeile.startswith('station_name='):
            name = zeile.split('=', 1)[1].strip()
    return nr, name


def katalog(ordner):
    """Beiblatt aus einem Stationskatalog neben den CSV-Reihen.

    Erwartet eine JSON-Liste mit code/name/lat/lon und Reihen, deren
    Dateiname mit dem Code beginnt. Genau so liegen die kanadischen
    Provinzordner.
    """
    basis = os.path.join(REIHEN, ordner)
    kataloge = glob.glob(os.path.join(basis, '_*_stations.json'))
    if not kataloge:
        return 0, 0
    eintraege = []
    for k in kataloge:
        try:
            eintraege += json.load(open(k, encoding='utf-8'))
        except Exception:
            pass
    nach_code = {str(e['code']): e for e in eintraege
                 if e.get('lat') is not None and e.get('lon') is not None}
    out, dateien = {}, glob.glob(os.path.join(basis, '*.csv'))
    for pfad in dateien:
        n = os.path.basename(pfad)
        code = n.split('_', 1)[0]
        e = nach_code.get(code)
        if not e:
            continue
        out[n] = dict(lat=round(float(e['lat']), 5), lon=round(float(e['lon']), 5),
                      name=f"{e.get('name', code)} ({ordner} {code})")
    if out:
        json.dump(out, open(os.path.join(basis, 'stationen.json'), 'w',
                            encoding='utf-8'), ensure_ascii=False, indent=1)
    return len(out), len([d for d in dateien if not os.path.basename(d).startswith('_')])


def main(argv):
    if '--katalog' in argv:
        ordner = [a for a in argv if not a.startswith('--')]
        if not ordner:
            ordner = sorted(d for d in os.listdir(REIHEN)
                            if os.path.isdir(os.path.join(REIHEN, d))
                            and glob.glob(os.path.join(REIHEN, d, '_*_stations.json')))
        for o in ordner:
            n, gesamt = katalog(o)
            if gesamt:
                print(f'  {o:24s} {n:5} von {gesamt:5} Reihen -> stationen.json')
        return 0
    ordner = argv[0] if argv else 'Germany'
    la1, la2, lo1, lo2 = KASTEN.get(ordner, (-90, 90, -180, 180))
    try:
        amtlich = pegelliste(ordner)
    except Exception as e:
        print(f'PEGELONLINE nicht erreichbar ({e}) -- nur Namenssuche')
        amtlich = {}
    recs = [r for r in load_records()
            if r['lat'] is not None and not r['current']
            and la1 < r['lat'] < la2 and lo1 < r['lon'] < lo2]
    kand = collections.defaultdict(list)
    for r in recs:
        for f in formen(r['name']):
            for s in schluessel(f):
                kand[s].append(r)

    out, fehlt = {}, []
    pfade = sorted(glob.glob(os.path.join(REIHEN, ordner, '**', '*.npz'),
                             recursive=True))
    import numpy as np
    ueber_nummer = eigen = 0
    for pfad in pfade:
        n = os.path.basename(pfad)[:-4]
        try:
            d = np.load(pfad, allow_pickle=True)
            if 'latitude' in d and 'longitude' in d:
                eigen += 1        # bringt alles selbst mit, braucht kein Beiblatt
                continue
        except Exception:
            pass
        nr, amtsname = kennung(n, ordner)
        if nr and nr in amtlich:
            la, lo, lang = amtlich[nr]
            out[n] = dict(lat=round(la, 5), lon=round(lo, 5),
                          name=f'{amtsname or lang} (PEGELONLINE {nr})')
            ueber_nummer += 1
            continue
        treffer = [r for s in schluessel(n) for r in kand.get(s, [])]
        if not treffer:
            fehlt.append(n)
            continue
        c = collections.Counter((round(r['lat'], 4), round(r['lon'], 4))
                                for r in treffer)
        (la, lo), n_hits = c.most_common(1)[0]
        if len(c) > 1 and n_hits == c.most_common(2)[1][1]:
            fehlt.append(f'{n} (uneindeutig)')
            continue
        name = next(r['name'] for r in treffer
                    if round(r['lat'], 4) == la and round(r['lon'], 4) == lo)
        out[n] = dict(lat=la, lon=lo, name=name)

    ziel = os.path.join(REIHEN, ordner, 'npz_stationen.json')
    json.dump(out, open(ziel, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f'{len(out)} von {len(pfade) - eigen} Reihen ohne eigene Kennung zugeordnet '
          f'({ueber_nummer} ueber die Pegelnummer, {len(out) - ueber_nummer} '
          f'ueber den Namen; {eigen} brauchen keins) -> '
          f'{os.path.relpath(ziel, ROOT)}')
    if fehlt:
        print(f'{len(fehlt)} ohne Zuordnung: ' + ', '.join(fehlt[:20]))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
