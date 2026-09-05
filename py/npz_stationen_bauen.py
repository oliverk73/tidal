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

Wo kein Katalog daliegt, bleibt der Name der Datei. --namen baut das
Beiblatt fuer CSV-Ordner ueber ihn: die niederlaendischen Reihen heissen
"breskens.veerhaven.csv", die malaysischen "johor_baharu.csv". Fuer
Malaysia liegen die Anzeigenamen im Scraper selbst
(py/scrape_malaysia_phn.py fuehrt STATIONS als Paare aus Klarname und
Dateikennung), und die treffen unseren Bestand besser als die Kennung.

Usage: python3 py/npz_stationen_bauen.py [Ordner]     (Vorgabe: Germany)
       python3 py/npz_stationen_bauen.py --katalog [Ordner ...]
       python3 py/npz_stationen_bauen.py --spiegel Quelle Ziel
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
    kataloge = (glob.glob(os.path.join(basis, '_*_stations.json'))
                + glob.glob(os.path.join(basis, '_station_catalog.json')))
    if not kataloge:
        # Canada_IWLS und Canada_IWLS_PEI fuehren keinen eigenen Katalog,
        # ihre Codes stehen aber in denen der Geschwisterordner. Gesucht
        # wird deshalb bei allen, die denselben ersten Namensteil tragen.
        stamm = ordner.split('_')[0]
        kataloge = glob.glob(os.path.join(REIHEN, f'{stamm}_*',
                                          '_*_stations.json'))
    if not kataloge:
        return 0, 0
    eintraege = []
    for k in kataloge:
        try:
            d = json.load(open(k, encoding='utf-8'))
            eintraege += d if isinstance(d, list) else list(d.values())
        except Exception:
            pass
    # Die Kataloge schreiben ihre Felder verschieden: Kanada code/name/lat/lon,
    # Belgien einmal station_no/station_name/station_latitude und einmal
    # code/name/lat/lon.
    def hol(e, *namen):
        for n in namen:
            if e.get(n) not in (None, ''):
                return e[n]
        return None

    nach_code = {}
    for e in eintraege:
        c = hol(e, 'code', 'station_no', 'station_number', 'id')
        la = hol(e, 'lat', 'latitude', 'station_latitude')
        lo = hol(e, 'lon', 'longitude', 'station_longitude')
        if c is None or la is None or lo is None:
            continue
        nach_code[str(c)] = (float(la), float(lo),
                             hol(e, 'name', 'station_name', 'toponyme') or str(c))
    out, dateien = {}, glob.glob(os.path.join(basis, '*.csv'))
    for pfad in dateien:
        n = os.path.basename(pfad)
        stamm = os.path.splitext(n)[0]
        e = (nach_code.get(stamm) or nach_code.get(stamm.split('_', 1)[0])
             or nach_code.get(stamm.lstrip('0')))
        if not e:
            # Belgien haengt der Kennung im Dateinamen eine 04 voran.
            for c, v in nach_code.items():
                if stamm.endswith(c) or c.endswith(stamm):
                    e = v
                    break
        if not e:
            continue
        la, lo, name = e
        out[n] = dict(lat=round(la, 5), lon=round(lo, 5),
                      name=f'{name} ({ordner})')
    if out:
        json.dump(out, open(os.path.join(basis, 'stationen.json'), 'w',
                            encoding='utf-8'), ensure_ascii=False, indent=1)
    return len(out), len([d for d in dateien if not os.path.basename(d).startswith('_')])


ALIAS_QUELLE = {'Malaysia_PHN': 'scrape_malaysia_phn.py'}


def spiegel(quelle, ziel):
    """Traegt die Zuordnung eines aufgeloesten Ordners auf einen zweiten.

    JMA_Japan_2026 fuehrt dieselben Stationen wie JMA_Japan, nur einen
    Jahrgang spaeter -- die Tafeln von 2026 gegen die von 2011-2025. Der
    Hauptweg loest nur den ersten der beiden auf, weil beide dieselbe
    Kennung tragen und reihendateien() den ersten Fund behaelt. Statt die
    Stationsliste neu zu holen (sie lag in /tmp und ist weg), wird die
    fertige Zuordnung des einen Ordners auf den anderen uebertragen:
    gleicher Dateiname, gleiche Station.
    """
    import re as _re
    import messreihe_qualitaet as M
    kopf = M.kopfdaten()
    dateien = M.reihendateien(quelle)
    nach_pfad = {}
    for r in load_records():
        if r['lat'] is None or r['current']:
            continue
        sid = kopf.get((r['file'], r['line']), (None, None, ''))[0]
        if not sid:
            continue
        teile = [t for t in _re.split(r'[ \-_]', sid) if t]
        for i in range(len(teile)):
            for j in range(len(teile)):
                if i == j:
                    continue
                p = dateien.get((teile[i].upper(), teile[j].upper()))
                if p:
                    nach_pfad.setdefault(os.path.basename(p), r)
    basis = os.path.join(REIHEN, ziel)
    out = {}
    for pfad in sorted(glob.glob(os.path.join(basis, '*'))):
        n = os.path.basename(pfad)
        r = nach_pfad.get(n)
        if r:
            out[n] = dict(lat=round(r['lat'], 5), lon=round(r['lon'], 5),
                          name=f"{r['name']} ({ziel})")
    if out:
        json.dump(out, open(os.path.join(basis, 'stationen.json'), 'w',
                            encoding='utf-8'), ensure_ascii=False, indent=1)
    return len(out), len(glob.glob(os.path.join(basis, '*')))


def aliasse(ordner):
    """-> {Dateikennung: Klarname} aus der STATIONS-Liste eines Scrapers."""
    quelle = ALIAS_QUELLE.get(ordner)
    if not quelle:
        return {}
    pfad = os.path.join(os.path.dirname(os.path.abspath(__file__)), quelle)
    try:
        text = open(pfad, encoding='utf-8').read()
    except Exception:
        return {}
    m = re.search(r'STATIONS = \[(.*?)\n\]', text, re.S)
    if not m:
        return {}
    return {b: a for a, b in re.findall(r"\('([^']+)',\s*'([^']+)'\)", m.group(1))}


def namen(ordner, kand):
    """Beiblatt ueber die Dateinamen, wo kein Katalog daliegt."""
    basis = os.path.join(REIHEN, ordner)
    alias = aliasse(ordner)
    out, dateien = {}, [p for p in glob.glob(os.path.join(basis, '*.csv'))
                        if not os.path.basename(p).startswith('_')]
    for pfad in dateien:
        n = os.path.basename(pfad)
        stamm = os.path.splitext(n)[0]
        roh = stamm.replace('.', ' ').replace('_', ' ')
        # Kanada schreibt "01650 Souris wlp": vorn die Pegelnummer, hinten
        # die Messgroesse (wlp Vorhersage, wlo Beobachtung).
        ohne = re.sub(r'^\d+\s+', '', roh)
        ohne = re.sub(r'\s+(wlp|wlo|wl)$', '', ohne, flags=re.I)
        formen_datei = {roh, ohne, re.sub(r'[ .]\d+$', '', stamm).replace(
            '.', ' ').replace('_', ' ')}
        if stamm in alias:
            formen_datei |= formen(alias[stamm])
        treffer = [r for f in formen_datei for s in schluessel(f)
                   for r in kand.get(s, [])]
        if not treffer:
            continue
        c = collections.Counter((round(r['lat'], 4), round(r['lon'], 4))
                                for r in treffer)
        (la, lo), n_hits = c.most_common(1)[0]
        if len(c) > 1 and n_hits == c.most_common(2)[1][1]:
            continue
        name = next(r['name'] for r in treffer
                    if round(r['lat'], 4) == la and round(r['lon'], 4) == lo)
        out[n] = dict(lat=la, lon=lo, name=f'{name} ({ordner})')
    if out:
        json.dump(out, open(os.path.join(basis, 'stationen.json'), 'w',
                            encoding='utf-8'), ensure_ascii=False, indent=1)
    return len(out), len(dateien)


def main(argv):
    if '--spiegel' in argv:
        a = [x for x in argv if not x.startswith('--')]
        n, gesamt = spiegel(a[0], a[1])
        print(f'  {a[1]:24s} {n:5} von {gesamt:5} Reihen -> stationen.json')
        return 0
    if '--namen' in argv:
        recs = [r for r in load_records()
                if r['lat'] is not None and not r['current']]
        kand = collections.defaultdict(list)
        for r in recs:
            for f in formen(r['name']):
                for s in schluessel(f):
                    kand[s].append(r)
        for o in [a for a in argv if not a.startswith('--')]:
            n, gesamt = namen(o, kand)
            print(f'  {o:24s} {n:5} von {gesamt:5} Reihen -> stationen.json')
        return 0
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
