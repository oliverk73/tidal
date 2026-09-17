#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Arbeitsliste: wo gibt es amtliche Gezeitentafeln fuer unsere Luecken?

Zwei Haelften werden verschraenkt:

  Luecken   jede Uebertragung (NOAA, ATT Part II ...), die weiter als
            LUECKE_KM vom naechsten Satz aus Messung oder amtlicher
            Dauervorhersage (Klasse A) entfernt steht -- je Land gezaehlt.
  Berichte  die IHO-Laenderberichte (py/iho_berichte_sammeln.py): welches
            Amt gibt Gezeitentafeln heraus, und welche Haefen nennt es?

Die Haefen werden aus den Saetzen um das Stichwort gelesen: eine Aufzaehlung
von mindestens drei gross geschriebenen Namen, wie im Bericht Mosambiks
("Maputo, Inhambane, Beira, Chinde, Quelimane, ..."). Das ist eine
Heuristik -- die Spalte "zitat" steht daneben, damit man sie pruefen kann.

Ergebnis: harmonics/help/iho_tafeln_arbeitsliste.csv, sortiert nach Luecke.

Usage: python3 py/iho_tafeln_auswerten.py
"""
from __future__ import annotations

import collections
import csv
import math
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import noaa_pruefstand as P                                         # noqa: E402
from health_check import ROOT, km, load_records                     # noqa: E402

BERICHTE = os.path.join(ROOT, 'tide_tables/catalogues/iho_berichte')
AUS = os.path.join(ROOT, 'harmonics/help/iho_tafeln_arbeitsliste.csv')
LUECKE_KM = 50.0

STICHWORT = re.compile(r'tide tables?|tidal tables?|tide predictions?|tidal predictions?|'
                       r'tabelas? de mar[eé]s|tablas? de mareas?|annuaire des mar[eé]es|'
                       r'pr[eé]dictions? de mar[eé]e|tide book|tide almanac|tidal almanac', re.I)
# Namen, wie sie in Dateinamen und Berichtstiteln vorkommen -> Land im Bestand
LAENDER = {
    'mozambique': 'Mozambique', 'madagascar': 'Madagascar', 'comoros': 'Comoros',
    'tanzania': 'Tanzania', 'kenya': 'Kenya', 'mauritius': 'Mauritius', 'seychelles': 'Seychelles',
    'south africa': 'South Africa', 'south_africa': 'South Africa', 'namibia': 'Namibia',
    'angola': 'Angola', 'nigeria': 'Nigeria', 'ghana': 'Ghana', 'benin': 'Benin', 'togo': 'Togo',
    'cameroon': 'Cameroon', 'cameroun': 'Cameroon', 'gabon': 'Gabon', 'congo': 'Congo',
    'senegal': 'Senegal', 'guinea': 'Guinea', 'sierra leone': 'Sierra Leone', 'liberia': 'Liberia',
    'gambia': 'Gambia', 'mauritania': 'Mauritania', 'morocco': 'Morocco', 'moroccan': 'Morocco',
    'cabo verde': 'Cape Verde', 'cape verde': 'Cape Verde', 'cote d': "Côte d'Ivoire",
    'russia': 'Russia', 'russian': 'Russia', 'india': 'India', 'pakistan': 'Pakistan',
    'bangladesh': 'Bangladesh', 'myanmar': 'Myanmar', 'sri lanka': 'Sri Lanka', 'thailand': 'Thailand',
    'indonesia': 'Indonesia', '_idn': 'Indonesia', 'malaysia': 'Malaysia', 'singapore': 'Singapore',
    'philippines': 'Philippines', 'viet': 'Vietnam', 'china': 'China', 'korea': 'South Korea',
    'japan': 'Japan', 'papua new guinea': 'Papua New Guinea', 'png': 'Papua New Guinea',
    'fiji': 'Fiji', 'tonga': 'Tonga', 'samoa': 'Samoa', 'vanuatu': 'Vanuatu',
    'solomon': 'Solomon Islands', 'kiribati': 'Kiribati', 'tuvalu': 'Tuvalu', 'nauru': 'Nauru',
    'micronesia': 'Micronesia', 'marshall': 'Marshall Islands', 'palau': 'Palau',
    'cook islands': 'Cook Islands', 'niue': 'Niue', 'new zealand': 'New Zealand',
    'australia': 'Australia', 'oman': 'Oman', 'iran': 'Iran', 'iraq': 'Iraq', 'kuwait': 'Kuwait',
    'qatar': 'Qatar', 'bahrain': 'Bahrain', 'uae': 'United Arab Emirates',
    'united arab emirates': 'United Arab Emirates', 'saudi': 'Saudi Arabia', 'ksa': 'Saudi Arabia',
    'egypt': 'Egypt', 'sudan': 'Sudan', 'yemen': 'Yemen', 'mexico': 'Mexico', 'méxico': 'Mexico',
    'cuba': 'Cuba', 'colombia': 'Colombia', 'venezuela': 'Venezuela', 'panama': 'Panama',
    'jamaica': 'Jamaica', 'honduras': 'Honduras', 'nicaragua': 'Nicaragua', 'guatemala': 'Guatemala',
    'belize': 'Belize', 'costa rica': 'Costa Rica', 'dominican': 'Dominican Republic', 'haiti': 'Haiti',
    'brazil': 'Brazil', 'brasil': 'Brazil', 'argentina': 'Argentina', 'uruguay': 'Uruguay',
    'chile': 'Chile', 'peru': 'Peru', 'ecuador': 'Ecuador', 'suriname': 'Suriname',
    'norway': 'Norway', 'denmark': 'Denmark', '_dk': 'Denmark', 'iceland': 'Iceland',
    'sweden': 'Sweden', 'finland': 'Finland', 'estonia': 'Estonia', 'latvia': 'Latvia',
    'lithuania': 'Lithuania', 'poland': 'Poland', 'germany': 'Germany', 'netherlands': 'Netherlands',
    'belgium': 'Belgium', 'france': 'France', 'spain': 'Spain', 'portugal': 'Portugal',
    'italy': 'Italy', 'croatia': 'Croatia', 'slovenia': 'Slovenia', 'montenegro': 'Montenegro',
    'albania': 'Albania', 'greece': 'Greece', 'turkey': 'Turkey', 'türkiye': 'Turkey',
    'cyprus': 'Cyprus', 'malta': 'Malta', 'tunisia': 'Tunisia', 'algeria': 'Algeria',
    'libya': 'Libya', 'lebanon': 'Lebanon', 'israel': 'Israel', 'romania': 'Romania',
    'bulgaria': 'Bulgaria', 'ukraine': 'Ukraine', 'georgia': 'Georgia',
    'united kingdom': 'United Kingdom', '_uk': 'United Kingdom', 'ireland': 'Ireland',
    'canada': 'Canada', 'usa': 'United States', 'united states': 'United States',
}


def land_der_datei(name, text):
    roh = name.lower().replace('-', ' ')
    for schl in sorted(LAENDER, key=len, reverse=True):
        if schl in roh:
            return LAENDER[schl]
    kopf = text[:1500].lower()
    for schl in sorted(LAENDER, key=len, reverse=True):
        if len(schl) > 4 and schl in kopf:
            return LAENDER[schl]
    return ''


def jahr_der_datei(name, text):
    m = re.search(r'(20[12]\d|19[89]\d)', name)
    if m:
        return m.group(1)
    m = re.search(r'\b(20[12]\d)\b', text[:3000])
    return m.group(1) if m else ''


AUFZAEHLUNG = re.compile(r"((?:[A-ZÀ-Ý][\w'’.\-]+(?: (?:de|da|do|dos|das|del|la|el|[A-ZÀ-Ý][\w'’.\-]+))*"
                         r"(?:\s*\([^)]{1,30}\))?\s*,\s*){2,}(?:and\s+|et\s+|e\s+|y\s+)?"
                         r"[A-ZÀ-Ý][\w'’.\-]+(?: (?:de|da|do|dos|das|del|la|el|[A-ZÀ-Ý][\w'’.\-]+))*)")
KEIN_HAFEN = re.compile(r'^(Tide|Tables?|Charts?|ENC|Notices?|List|Lights?|Mariners|Admiralty|'
                        r'Navy|Hydrographic|Office|Service|Institute|Ministry|Department|'
                        r'January|February|March|April|May|June|July|August|September|'
                        r'October|November|December|IHO|IMO|WMO|IOC|GLOSS|UKHO|NOAA|SHOM)\b')


def haefen(stelle):
    out = []
    for m in AUFZAEHLUNG.finditer(stelle):
        teile = [t.strip(' .') for t in re.split(r',|\band\b|\bet\b|\be\b|\by\b', m.group(1)) if t.strip(' .')]
        teile = [t for t in teile if not KEIN_HAFEN.match(t) and len(t) > 2]
        if len(teile) >= 3:
            out.extend(teile)
    return list(dict.fromkeys(out))


def berichte():
    """-> {land: [dict(datei, jahr, zitat, haefen)]}"""
    out = collections.defaultdict(list)
    for f in sorted(os.listdir(BERICHTE)):
        if not f.endswith('.txt'):
            continue
        t = open(os.path.join(BERICHTE, f), encoding='utf-8', errors='replace').read()
        stellen = []
        for m in STICHWORT.finditer(t):
            a, b = max(0, m.start() - 250), min(len(t), m.end() + 500)
            stellen.append(' '.join(t[a:b].split()))
        land = land_der_datei(f, t)
        if not land:
            continue
        hf = []
        for s in stellen:
            hf.extend(haefen(s))
        out[land].append(dict(datei=f[:-4], jahr=jahr_der_datei(f, t),
                              zitat=stellen[0][:400] if stellen else '', haefen=list(dict.fromkeys(hf))[:40],
                              stellen=len(stellen)))
    return out


def luecken():
    """-> {land: (anzahl, groesster Abstand km, Beispiel)} der Uebertragungen ohne Messung."""
    recs = [r for r in load_records() if r['lat'] is not None and not r['current']]
    a = [r for r in recs if P.klasse(r) == 'A']
    gitter = collections.defaultdict(list)
    for r in a:
        gitter[(int(r['lat'] // 2), int(r['lon'] // 2))].append(r)
    out = {}
    for r in recs:
        if P.klasse(r) is not None or 'fes' in r['file']:
            continue
        best = 9999.0
        s = max(1, int(math.ceil(1 / max(0.05, math.cos(math.radians(r['lat']))))))
        for d in range(0, 8):
            for da in range(-d, d + 1):
                for db in range(-d * s, d * s + 1):
                    for x in gitter.get((int(r['lat'] // 2) + da, int(r['lon'] // 2) + db), ()):
                        best = min(best, km(r, x))
            if best < 9999 and d >= 1:
                break
        if best <= LUECKE_KM:
            continue
        teile = [t.strip() for t in re.split(r',(?![^(]*\))', r['name']) if t.strip()]
        land = teile[-1] if len(teile) > 1 else '?'
        n, mx, bsp, orte = out.get(land, (0, 0.0, '', []))
        orte = orte + [teile[0]]
        out[land] = (n + 1, max(mx, best), bsp if mx >= best else r['name'], orte)
    return out


def kern(name):
    """Suchbarer Kern eines Stationsnamens: ohne Klammer und Gattungswoerter."""
    n = re.sub(r'\s*\([^)]*\)', '', name)
    n = re.sub(r'\b(Island|Islands|Bay|Harbou?r|Point|Cape|River|entrance|Anchorage|Road|'
               r'Strait|Reef|Bank|Channel|Port|Pulau|Pulo|Teluk|Tanjung|Sungai|Mys|Ostrov|'
               r'Bukhta|Guba|Zaliv|Reka|Baie|Bahia|Bahía|Baía|Ilha|Isla|Punta|Ponta)\b', '', n, flags=re.I)
    return ' '.join(n.split())


def main(argv):
    lu = luecken()
    be = berichte()
    zeilen = []
    for land in sorted(set(lu) | set(be), key=lambda l: -lu.get(l, (0,))[0]):
        n, mx, bsp, orte = lu.get(land, (0, 0.0, '', []))
        alle_eintraege = be.get(land, [])
        eintraege = sorted([e for e in alle_eintraege if e['stellen']], key=lambda e: e['jahr'], reverse=True)
        # Welche unserer Lueckenorte nennt ein Bericht dieses Landes woertlich?
        texte = ' '.join(open(os.path.join(BERICHTE, e['datei'] + '.txt'), encoding='utf-8',
                              errors='replace').read() for e in alle_eintraege)
        genannt = sorted({o for o in orte if len(kern(o)) >= 4
                          and re.search(r'\b' + re.escape(kern(o)) + r'\b', texte, re.I)})
        juengster = eintraege[0] if eintraege else {}
        alle_haefen = list(dict.fromkeys(h for e in eintraege for h in e['haefen']))
        zeilen.append(dict(land=land, luecken=n, weitester_km=round(mx), beispiel=bsp,
                           berichte=len(eintraege), juengster=juengster.get('jahr', ''),
                           datei=juengster.get('datei', ''), haefen='; '.join(alle_haefen[:40]),
                           lueckenorte_im_bericht='; '.join(genannt),
                           zitat=juengster.get('zitat', '')))
    with open(AUS, 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=['land', 'luecken', 'weitester_km', 'beispiel', 'berichte',
                                           'juengster', 'datei', 'haefen', 'lueckenorte_im_bericht', 'zitat'])
        w.writeheader()
        w.writerows(zeilen)
    print(f'{sum(z["luecken"] for z in zeilen)} Luecken in {sum(1 for z in zeilen if z["luecken"])} Laendern; '
          f'{sum(1 for z in zeilen if z["berichte"])} Laender mit Tafel-Stelle im IHO-Bericht')
    print(f'\n{"Land":22} {"Luecken":>7} {"weitest":>8} {"Berichte":>8}  Lueckenorte, die ein Bericht nennt')
    for z in zeilen[:30]:
        print(f'{z["land"][:22]:22} {z["luecken"]:7d} {z["weitester_km"]:6d} km {z["berichte"]:8d}  '
              f'{z["lueckenorte_im_bericht"][:70]}')
    print('\n->', os.path.relpath(AUS, ROOT))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
