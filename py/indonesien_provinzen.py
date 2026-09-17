#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ergaenzt die Provinz im Namen der indonesischen Saetze.

430 der 614 Saetze in Indonesien heissen nur "Ort, Indonesia". Die uebrigen
tragen als mittleres Glied meist gar keine Provinz, sondern eine Insel oder
eine Strasse ("Sumatra", "Bangka Strait") -- das bleibt vorerst, hier geht es
um die 430 ganz ohne Angabe.

Die Provinz kommt aus zwei Quellen, und beide muessen sich einig sein:

  GeoNames        naechster Ort mit Provinzschluessel (tide_tables/catalogues/
                  geonames/indonesien_orte.tsv aus allCountries.txt). Kennt die
                  Teilung Papuas von 2022/23 (Papua Barat Daya, Papua Tengah,
                  Papua Pegunungan, Papua Selatan).
  Natural Earth   das Polygon unter der Position (py/region_felder_fuellen).
                  Aelter, kennt die neuen Provinzen nicht.

Geschrieben wird nur, wo beide dieselbe Provinz nennen oder wo allein GeoNames
eine der neuen Papua-Provinzen sagt (dann ist Natural Earth schlicht veraltet).
Alles andere kommt in die Liste und bleibt unangetastet.

Die Namen stehen in der Landessprache, wie Oliver es fuer Stationsnamen
verlangt: "Sumatera Utara", nicht "North Sumatra".

Ergebnis: harmonics/help/indonesien_provinzen.csv
Mit --schreiben: Name ergaenzt, Feld "# state:" nachgezogen, Vermerk gesetzt.

Usage: python3 py/indonesien_provinzen.py [--schreiben] [--km 60]
"""
from __future__ import annotations

import collections
import csv
import re
import datetime as dt
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import region_felder_fuellen as RF                                  # noqa: E402
import sicher_schreiben                                             # noqa: E402
from health_check import ROOT, km, load_records                     # noqa: E402

ORTE = os.path.join(ROOT, 'tide_tables/catalogues/geonames/indonesien_orte.tsv')
AUS = os.path.join(ROOT, 'harmonics/help/indonesien_provinzen.csv')
UMKREIS = 60.0

# GeoNames fuehrt die Provinzen englisch; im Namen steht die Landessprache.
PROVINZ = {
    '01': 'Aceh', '26': 'Sumatera Utara', '24': 'Sumatera Barat', '37': 'Riau',
    '40': 'Kepulauan Riau', '05': 'Jambi', '32': 'Sumatera Selatan',
    '35': 'Kepulauan Bangka Belitung', '03': 'Bengkulu', '15': 'Lampung',
    '33': 'Banten', '04': 'Jakarta', '30': 'Jawa Barat', '07': 'Jawa Tengah',
    '10': 'Yogyakarta', '08': 'Jawa Timur', '02': 'Bali',
    '17': 'Nusa Tenggara Barat', '18': 'Nusa Tenggara Timur',
    '11': 'Kalimantan Barat', '13': 'Kalimantan Tengah', '12': 'Kalimantan Selatan',
    '14': 'Kalimantan Timur', '42': 'Kalimantan Utara',
    '31': 'Sulawesi Utara', '34': 'Gorontalo', '21': 'Sulawesi Tengah',
    '41': 'Sulawesi Barat', '38': 'Sulawesi Selatan', '22': 'Sulawesi Tenggara',
    '28': 'Maluku', '29': 'Maluku Utara',
    '36': 'Papua', '39': 'Papua Barat', 'PD': 'Papua Barat Daya',
    'PT': 'Papua Tengah', 'PE': 'Papua Pegunungan', 'PS': 'Papua Selatan',
}
# Natural Earth schreibt teils anders und kennt die Teilung Papuas nicht.
NE_GLEICH = {'Bangka-Belitung': 'Kepulauan Bangka Belitung', 'Jakarta Raya': 'Jakarta',
             'Irian Jaya Barat': 'Papua Barat', 'Kepulauan Riau': 'Kepulauan Riau'}
# Provinzen, die es bei Natural Earth noch nicht gibt: Kalimantan Utara wurde
# 2012 abgetrennt, die vier Papua-Provinzen 2022/23. Wo GeoNames eine davon
# nennt und Natural Earth die alte Mutterprovinz, ist GeoNames schlicht neuer.
JUNG = {'Papua Barat Daya': ('Papua', 'Papua Barat'), 'Papua Tengah': ('Papua',),
        'Papua Pegunungan': ('Papua',), 'Papua Selatan': ('Papua',),
        'Kalimantan Utara': ('Kalimantan Timur',)}
# Inselgruppen ohne eigenes Polygon bei Natural Earth (Kepulauan Seribu gehoert
# verwaltungsmaessig zu Jakarta, liegt aber vor der Kueste Bantens).
SEEGEBIET_KM = 30.0

# Die 13 Faelle, in denen GeoNames und Natural Earth sich widersprachen,
# entschieden am 16.09.2026 mit einer Mehrheitsprobe: nicht der naechste
# GeoNames-Ort zaehlt, sondern wie ALLE Orte bis 20 km zugeordnet sind.
# Wo der naechste Eintrag einen veralteten Provinzschluessel traegt (Sulawesi
# Barat 2004, Kepulauan Bangka Belitung 2000 abgetrennt), kippt die Mehrheit
# das Urteil. Die Kepulauan Seribu gehoeren zu Jakarta, obwohl sie vor Banten
# liegen; Gilimanuk liegt auf Bali, obwohl 3 km weiter Java dicht besiedelt ist.
HAND = {
    'Damar Besar': 'Jakarta', 'Pulau Pari': 'Jakarta',
    'Pulau Pulau Seribu': 'Jakarta', 'Kep. Seribu': 'Jakarta',
    'Gilimanuk': 'Bali',                       # naechster Ort: Pelabuhan Gilimanuk, 0.1 km
    'Tanjung Kuala Jelai': 'Kalimantan Tengah',  # Mehrheit 10:6, Distrikt Kuala Jelai
    'Djelai River entrance': 'Kalimantan Tengah',
    'Pulau Berhala': 'Kepulauan Riau',         # Gerichtsentscheid 2013 gegen Jambi
    'Tanjung Datu': 'Kalimantan Barat',        # Kap an der Grenze, 5:0
    'Kokoila': 'Sulawesi Tengah',              # 19:0, Suedspitze Morowali
    'Singkilbaru': 'Aceh',                     # Mehrheit 90:34, naechster Eintrag veraltet
    'Beting Akbar': 'Kepulauan Bangka Belitung',  # Untiefe in der Selat Gelasa
    'Tobintah': 'Sulawesi Barat',              # Mamuju; GeoNames-Schluessel von vor 2004
    # Dieselben Orte noch einmal in alter Schreibweise (eigene Saetze):
    'Pulo Berhala': 'Kepulauan Riau', 'Tandjung Datu': 'Kalimantan Barat',
    # Sadeng: Hafen in Gunungkidul (Yogyakarta). Die Satzposition liegt 33 km
    # vor der Kueste -- die Provinz stimmt trotzdem, die Position ist zu pruefen.
    'Sadeng': 'Yogyakarta',
}


def geonames_gitter():
    gitter = collections.defaultdict(list)
    with open(ORTE, encoding='utf-8') as fh:
        for z in fh:
            p = z.rstrip('\n').split('\t')
            if len(p) < 4 or p[3] not in PROVINZ:
                continue
            try:
                la, lo = float(p[1]), float(p[2])
            except ValueError:
                continue
            gitter[(round(la * 2) / 2, round(lo * 2) / 2)].append((la, lo, p[3], p[0]))
    return gitter


def naechster(lat, lon, gitter, grenze):
    best = None
    schritt = 0.5
    ringe = int(math.ceil(grenze / 55.0)) + 1
    for da in range(-ringe, ringe + 1):
        for db in range(-ringe, ringe + 1):
            for la, lo, code, name in gitter.get((round(lat * 2) / 2 + da * schritt,
                                                  round(lon * 2) / 2 + db * schritt), ()):
                d = km({'lat': lat, 'lon': lon}, {'lat': la, 'lon': lo})
                if d <= grenze and (best is None or d < best[0]):
                    best = (d, PROVINZ[code], name)
    return best


def namensteile(name):
    """-> (Grundname, [Klammerzusaetze], Provinz oder '') aus einem Satznamen.

    "Berembang, Sungi Panai, Sumatra, Indonesia" -> ("Berembang",
    ["Sungi Panai", "Sumatra"], ""). Ein Klammerzusatz, den der Grundname schon
    hat, bleibt vorn: "Pulau Sembilan (Channel)" -> Grundname "Pulau Sembilan",
    Zusatz "Channel" an erster Stelle.
    """
    # Nur Kommata AUSSERHALB der Klammern trennen -- sonst zerlegt der zweite
    # Lauf "Pulau Sembilan (Channel, Sumatra)" und baut daraus die Verschachtelung
    # "Pulau Sembilan (Channel (Sumatra))" (passiert am 16.09.2026, 49 Namen).
    teile = [t.strip() for t in re.split(r',(?![^(]*\))', name) if t.strip()]
    mitte = teile[1:-1]
    prov = ''
    zusatz = []
    for m in mitte:
        if m in PROVINZ.values():
            prov = m
        else:
            zusatz.append(m)
    grund = teile[0]
    m = re.match(r'^(.*?)\s*\(([^)]*)\)\s*$', grund)
    if m:
        grund = m.group(1).strip()
        zusatz.insert(0, m.group(2).strip())
    return grund, zusatz, prov


def klammern(recs, gitter, polys, grenze):
    """Inseln, Meerengen und Fluesse aus dem Mittelglied in die Klammer holen."""
    out = []
    for r in recs:
        grund, zusatz, prov = namensteile(r['name'])
        if not zusatz:
            continue
        if not prov:
            prov = provinz_von(r, gitter, polys, grenze)[0]
        if not prov:
            out.append((r, '', 'keine Provinz gefunden'))
            continue
        neu = f"{grund} ({', '.join(zusatz)}), {prov}, Indonesia"
        out.append((r, neu, ''))
    return out


def klammermodus(recs, gitter, polys, grenze, schreiben):
    """Insel/Meerenge/Fluss aus dem Mittelglied in die Klammer, Provinz dahinter."""
    vorschlaege = [(r, neu, grund) for r, neu, grund in klammern(recs, gitter, polys, grenze)
                   if neu != r['name']]
    klar = [(r, neu) for r, neu, g in vorschlaege if neu]
    offen = [(r, g) for r, neu, g in vorschlaege if not neu]
    print(f'{len(klar)} Saetze umzubenennen, {len(offen)} offen')
    for r, neu in klar[:12]:
        print(f'   {r["name"][:46]:46} -> {neu}')
    for r, g in offen:
        print(f'   offen: {r["name"][:46]:46} {g}')
    if not schreiben:
        print('\n(nur Probe; mit --schreiben --klammern wird umbenannt)')
        return 0
    nach_datei = collections.defaultdict(list)
    for r, neu in klar:
        nach_datei[r['file']].append((r, neu))
    n = 0
    for pfad, liste in nach_datei.items():
        voll = os.path.join(ROOT, pfad)
        zeilen = open(voll, encoding='iso-8859-1').read().split('\n')
        for r, neu in liste:
            tr = [k for k, l in enumerate(zeilen) if l == r['name']]
            if len(tr) != 1:
                print(f'  {r["name"]}: {len(tr)} Treffer -- uebersprungen')
                continue
            k = tr[0]
            j = k - 1
            while j >= 0 and zeilen[j].startswith('#'):
                j -= 1
            zeilen[k] = neu
            for b in range(j + 1, k):
                if zeilen[b].strip() == f'# {r["name"]}':
                    zeilen[b] = f'# {neu}'
                elif zeilen[b].startswith('# state:'):
                    zeilen[b] = f"# state: {neu.split(',')[-2].strip()}"
            n += 1
        sicher_schreiben.schreiben(voll, '\n'.join(zeilen))
        print(f'  {os.path.basename(pfad)}: {len(liste)} umbenannt')
    print(f'\n{n} Saetze. Danach: python3 py/umbenennungen_nachziehen.py --schreiben')
    return 0


def provinz_von(r, gitter, polys, grenze):
    """-> (Provinz, Urteil) aus GeoNames, Natural Earth und der Handliste."""
    gn = naechster(r['lat'], r['lon'], gitter, grenze)
    drin = RF.welches(r['lon'], r['lat'], polys) or RF.naechstes(r['lon'], r['lat'], polys, 100.0)
    ne = NE_GLEICH.get(drin[1], drin[1]) if drin else ''
    kurz = r['name'].split(',')[0].strip()
    kurz = re.sub(r'\s*\([^)]*\)$', '', kurz)
    if kurz in HAND:
        return HAND[kurz], 'Handentscheid (Mehrheitsprobe)'
    if not gn:
        return '', f'GeoNames kennt bis {grenze:.0f} km keinen Ort'
    if gn[1] == ne:
        return gn[1], 'einig'
    if gn[1] in JUNG and ne in JUNG[gn[1]]:
        return gn[1], f'neue Provinz: Natural Earth sagt noch {ne}'
    if not ne and gn[0] <= SEEGEBIET_KM:
        return gn[1], f'kein Polygon (See); GeoNames-Ort {gn[2]} {gn[0]:.0f} km'
    return '', f'uneinig: GeoNames {gn[1]}, Natural Earth {ne or "?"}'


def main(argv):
    grenze = float(argv[argv.index('--km') + 1]) if '--km' in argv else UMKREIS
    schreiben = '--schreiben' in argv
    recs = [r for r in load_records()
            if r['name'].endswith(', Indonesia') and r['lat'] is not None and not r['current']]
    ohne = [r for r in recs if len([t for t in r['name'].split(',') if t.strip()]) == 2]
    print(f'{len(recs)} Saetze in Indonesien, {len(ohne)} ohne Provinz')
    gitter = geonames_gitter()
    polys = RF.polygone()

    if '--klammern' in argv:
        return klammermodus(recs, gitter, polys, grenze, schreiben)

    zeilen = []
    for r in ohne:
        gn = naechster(r['lat'], r['lon'], gitter, grenze)
        drin = RF.welches(r['lon'], r['lat'], polys) or RF.naechstes(r['lon'], r['lat'], polys, 100.0)
        ne = NE_GLEICH.get(drin[1], drin[1]) if drin else ''
        prov, urteil = '', ''
        if not gn:
            urteil = f'GeoNames kennt bis {grenze:.0f} km keinen Ort'
        elif gn[1] == ne:
            prov, urteil = gn[1], 'einig'
        elif gn[1] in JUNG and ne in JUNG[gn[1]]:
            prov, urteil = gn[1], f'neue Provinz: Natural Earth sagt noch {ne}'
        elif not ne and gn[0] <= SEEGEBIET_KM:
            prov, urteil = gn[1], f'kein Polygon (See); GeoNames-Ort {gn[2]} {gn[0]:.0f} km'
        elif r['name'].split(',')[0].strip() in HAND:
            prov = HAND[r['name'].split(',')[0].strip()]
            urteil = f'Handentscheid (Mehrheitsprobe); GeoNames {gn[1]}, Natural Earth {ne or "?"}'
        else:
            urteil = f'uneinig: GeoNames {gn[1]}, Natural Earth {ne or "?"}'
        zeilen.append(dict(datei=os.path.basename(r['file']), name=r['name'],
                           lat=f"{r['lat']:.4f}", lon=f"{r['lon']:.4f}",
                           provinz=prov, geonames=gn[1] if gn else '',
                           gn_ort=gn[2] if gn else '', gn_km=f'{gn[0]:.1f}' if gn else '',
                           natural_earth=ne, urteil=urteil,
                           neuer_name=f"{r['name'].split(',')[0].strip()}, {prov}, Indonesia" if prov else ''))
    with open(AUS, 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=['datei', 'name', 'lat', 'lon', 'provinz', 'geonames',
                                           'gn_ort', 'gn_km', 'natural_earth', 'urteil', 'neuer_name'])
        w.writeheader()
        w.writerows(zeilen)
    klar = [z for z in zeilen if z['provinz']]
    print(f'{len(klar)} eindeutig, {len(zeilen) - len(klar)} offen -> {os.path.relpath(AUS, ROOT)}')
    for p, n in collections.Counter(z['provinz'] for z in klar).most_common():
        print(f'   {n:4d} {p}')
    for z in zeilen:
        if not z['provinz']:
            print(f"   offen: {z['name'][:40]:40} {z['urteil']}")
    if not schreiben:
        print('\n(nur Probe; mit --schreiben werden die Namen ergaenzt)')
        return 0

    nach_datei = collections.defaultdict(list)
    for z in klar:
        nach_datei[z['datei']].append(z)
    pfade = {os.path.basename(r['file']): r['file'] for r in recs}
    n = 0
    for datei, liste in nach_datei.items():
        pfad = os.path.join(ROOT, pfade[datei])
        zeilen_datei = open(pfad, encoding='iso-8859-1').read().split('\n')
        for z in liste:
            tr = [k for k, l in enumerate(zeilen_datei) if l == z['name']]
            if len(tr) != 1:
                print(f"  {z['name']}: {len(tr)} Treffer -- uebersprungen")
                continue
            k = tr[0]
            j = k - 1
            while j >= 0 and zeilen_datei[j].startswith('#'):
                j -= 1
            block = list(range(j + 1, k))
            zeilen_datei[k] = z['neuer_name']
            for b in block:
                if zeilen_datei[b].strip() == f"# {z['name']}":
                    zeilen_datei[b] = f"# {z['neuer_name']}"
                elif zeilen_datei[b].startswith('# state:'):
                    zeilen_datei[b] = f"# state: {z['provinz']}"
            if not any(zeilen_datei[b].startswith('# state:') for b in block):
                u = [b for b in block if zeilen_datei[b].startswith('# !units:')]
                if u:
                    zeilen_datei.insert(u[0], f"# state: {z['provinz']}")
            n += 1
        sicher_schreiben.schreiben(pfad, '\n'.join(zeilen_datei))
        print(f'  {datei}: {len(liste)} Namen ergaenzt')
    print(f'\n{n} Saetze umbenannt. Danach: python3 py/umbenennungen_nachziehen.py --schreiben')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
