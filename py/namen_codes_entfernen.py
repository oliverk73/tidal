#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Entfernt interne Codes aus Stationsnamen (Oliver, 1.11.2026).

Die Kennung bleibt im Satzkopf (station_id_context, bodc_ref, imos_code ...);
fehlt sie dort, kommt der alte Name als note dazu. Wo nur der Code zwei Saetze
trennte, tritt eine Lageangabe an seine Stelle. Name in harmonics/help/*.csv
wird mitgezogen, die Abbildung steht in harmonics/help/namen_codes_20261101.csv.

Usage: python3 py/namen_codes_entfernen.py [--schreiben]
"""
import csv
import glob
import math
import os
import re
import sys
import collections

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AKTIV = ['harmonics/utide/harmonics_utide_current_observations.txt',
         'harmonics/utide/harmonics_utide_current_tables.txt',
         'harmonics/utide/harmonics_utide_australia_oceancurrent.txt',
         'harmonics/utide/harmonics_utide_observations.txt',
         'harmonics/noaa/harmonics_noaa_nebenstroeme.txt',
         'harmonics/classic/harmonics-2004-06-14_mod.txt']

QUELLE = r'(?:BODC|IMOS|CSIRO|MDE|SHOM atlas)'
CODE1 = re.compile(r'\)?;\s*' + QUELLE + r'\b[^)]*\)')
CODE2 = re.compile(r'\s*\((?:SHOM atlas|TSPS|BODC|IMOS|CSIRO|MDE)\b[^)]*\)')

# Bezugspunkte fuer Lageangaben (OSM bzw. Karte)
REF = {'Banks Strait ': ('Swan Island', 'Banks Strait', -40.7355, 148.1053),
       'Clarence Strait C': ('Cape Hotham', 'Clarence Strait', -12.0437, 131.2988),
       'Algoa Bay A': ('Bird Island', 'Algoa Bay', -33.84, 26.29),
       'Durban Dbn': ('Durban', None, -29.86, 31.02),
       'Port Alfred PA': ('Port Alfred', None, -33.5981, 26.8915),
       'Richards Bay RiB': ('Richards Bay', None, -28.8011, 32.0583),
       'Hamilton Bank ': ('Hamilton Bank', None, 55.35, -53.7667),
       'Hibernia': ('Hibernia', None, 46.75, -48.78)}
HELGOLAND = ('Helgoland', None, 54.1809, 7.8944)

HAND = {
    'Ducktrap Harbor (NNE of, ACT0536), Maine Current': 'Ducktrap Harbor (NNE of, west), Maine Current',
    'Cape Recife CR01, South Africa Current': 'Cape Recife, South Africa Current',
    'Walters Shoal WSN01, South Africa Current': 'Walters Shoal (North), South Africa Current',
    'Walters Shoal WSS01, South Africa Current': 'Walters Shoal (South), South Africa Current',
    'Kiel 276 (Canary Basin), Portugal Current': 'Canary Basin, Portugal Current',
    'Chignecto (Ray .4), Nova Scotia, Canada': 'Chignecto, Nova Scotia, Canada',
    'Cobequid Bay (Ray .4), Nova Scotia, Canada': 'Cobequid Bay, Nova Scotia, Canada',
    'Minas Basin (Ray .4), Nova Scotia, Canada': 'Minas Basin, Nova Scotia, Canada',
    'Economy (Inshore 5), Nova Scotia, Canada': 'Economy, Nova Scotia, Canada',
    'Five Islands (2), Nova Scotia, Canada': 'Five Islands (West), Nova Scotia, Canada',
    'Byam Channel (Z3), Nunavut, Canada': 'Byam Channel (East), Nunavut, Canada',
    'Byam Channel (Lp), Nunavut, Canada': 'Byam Channel (West), Nunavut, Canada',
    'Eskimo Lakes Station 1c, Northwest Territories, Canada': 'Eskimo Lakes (East), Northwest Territories, Canada',
    'Eskimo Lakes Station 2b, Northwest Territories, Canada': 'Eskimo Lakes (West), Northwest Territories, Canada',
    'Hudson Strait Station 808, Qu\xe9bec, Canada': 'Hudson Strait, Qu\xe9bec, Canada',
    'Nain Bank Station 847, Labrador, Canada': 'Nain Bank, Labrador, Canada',
    'Marley Head (7 km E); IMOS PH100), Australia Current': 'Marley Head (7 km E), Australia Current',
}
# gleiche Lage ohne Code: Paar nach Himmelsrichtung trennen
PAARE = {'Black Point, Hong Kong Current': 'ns', 'Lantau Channel, Hong Kong Current': 'we',
         'East Lamma Channel, Hong Kong Current': 'ns', 'Tathong Channel, Hong Kong Current': 'ns',
         'Sulphur Channel, Hong Kong Current': 'ns', 'Victoria Harbour, Hong Kong Current': 'we'}
HOWTH = {'Howth (35 km E, 10 m deep; BODC 14714), Ireland Current': 'Howth (35 km E, 10 m deep, north), Ireland Current',
         'Howth (35 km E, 10 m deep; BODC 14751), Ireland Current': 'Howth (35 km E, 10 m deep, south), Ireland Current'}
DREHUNG = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE', 'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW']


def lage(lat, lon, ref, nachkomma=0):
    d_n = (lat - ref[2]) * 111.2
    d_e = (lon - ref[3]) * 111.2 * math.cos(math.radians((lat + ref[2]) / 2))
    km = math.hypot(d_n, d_e)
    r = DREHUNG[round(math.degrees(math.atan2(d_e, d_n)) % 360 / 22.5) % 16]
    return ('%.' + str(nachkomma) + 'f km %s') % (km, r)


def saetze(pfad):
    """-> [(zeile, name, lat, lon, kopfanfang)]"""
    z = open(pfad, encoding='iso-8859-1').read().split('\n')
    aus = []
    lat = lon = None
    kopf = 0
    for i, l in enumerate(z[:-1]):
        if l.startswith('# BEGIN HOT'):
            kopf = i
        m = re.match(r'# !latitude: (\S+)', l)
        if m:
            lat = float(m.group(1))
        m = re.match(r'# !longitude: (\S+)', l)
        if m:
            lon = float(m.group(1))
        if l and l[0] != '#' and l != 'x 0 0' and re.match(r'[+-]\d\d:\d\d ', z[i + 1]):
            aus.append((i, l, lat, lon, kopf))
    return z, aus


def neuer_name(n, lat, lon, gruppe):
    if n in HOWTH:
        return HOWTH[n]
    if n in HAND:
        return HAND[n]
    if CODE1.search(n):
        return CODE1.sub(')', n)
    if CODE2.search(n):
        return CODE2.sub('', n)
    m = re.fullmatch(r'Dordrecht (Hollands Diep|Oude Maas) (\d{3}), Netherlands Current', n)
    if m:
        return 'Dordrecht %s (cross-section %d m), Netherlands Current' % (m.group(1), int(m.group(2)))
    m = re.fullmatch(r'(.+) DVW, Belgium', n)
    if m:
        return m.group(1) + ', Belgium'
    if re.fullmatch(r'N\d+[NSW] Benthic Node, Germany Current', n):
        return 'Helgoland (%s), Germany Current' % lage(lat, lon, HELGOLAND)
    for p, ref in REF.items():
        if n.startswith(p) and (p != 'Hibernia' or re.match(r'Hibernia (109|\(780)', n)) \
           and (p != 'Hamilton Bank ' or re.match(r'Hamilton Bank \d', n)):
            ende = n[n.index(',') :]
            inner = lage(lat, lon, ref, gruppe.get(n, 0))
            if ref[1]:
                inner += ', ' + ref[1]
            return '%s (%s)%s' % (ref[0], inner, ende)
    return None


def main():
    schreiben = '--schreiben' in sys.argv
    os.chdir(ROOT)
    daten = {p: saetze(p) for p in AKTIV}
    alle = collections.Counter()
    for p in glob.glob('harmonics/*/*.txt'):
        if '/backup' in p or '/help' in p or '_original' in p:
            continue
        for n in re.findall(r'^([^#x\n].*)\n[+-]\d\d:\d\d ', open(p, encoding='iso-8859-1').read(), re.M):
            alle[n] += 1
    gruppe = {}
    for _ in range(2):
        plan = []
        for p, (z, aus) in daten.items():
            for i, n, lat, lon, kopf in aus:
                neu = neuer_name(n, lat, lon, gruppe)
                if neu and neu != n:
                    plan.append([p, i, n, neu, lat, lon, kopf])
        c = collections.Counter(x[3] for x in plan)
        for x in plan:                                   # gleiche Lage bei ganzen km: eine Nachkommastelle
            if c[x[3]] > 1 and x[3] not in PAARE:
                gruppe[x[2]] = 1
    # Paare
    for neu, achse in PAARE.items():
        pp = [x for x in plan if x[3] == neu]
        if not pp:
            continue
        assert len(pp) == 2, neu
        a, b = sorted(pp, key=lambda x: x[4] if achse == 'ns' else x[5])
        wort = ('South', 'North') if achse == 'ns' else ('West', 'East')
        kurz = neu[:neu.index(',')]
        a[3] = neu.replace(kurz, kurz + ' (%s)' % wort[0], 1)
        b[3] = neu.replace(kurz, kurz + ' (%s)' % wort[1], 1)
    c = collections.Counter(x[3] for x in plan)
    doppelt = [k for k, v in c.items() if v > 1]
    alt = {x[2] for x in plan}
    fremd = sorted({x[3] for x in plan if alle[x[3]] and x[3] not in alt})
    print(len(plan), 'Umbenennungen, doppelt:', doppelt, '\nschon vorhanden:', fremd)
    for x in plan:
        if not re.search(r'; ?' + r'(BODC|IMOS|MDE)', x[2]) and 'SHOM atlas' not in x[2]:
            print('  %-62s -> %s' % (x[2][:62], x[3]))
    if doppelt or not schreiben:
        return
    abb = {}
    for p, (z, aus) in daten.items():
        pl = sorted((x for x in plan if x[0] == p), key=lambda x: -x[1])
        for _, i, n, neu, lat, lon, kopf in pl:
            assert z[i] == n
            z[i] = neu
            m = re.search(r'(?:BODC|IMOS|CSIRO|MDE|TSPS|SHOM atlas) ([^)]+)\)', n)
            if not m or m.group(1) not in ' '.join(z[kopf:i]).replace('-', ' ').replace('_', ' ').replace(m.group(1).replace('-', ' '), m.group(1)):
                z.insert(i, '# note: 20261101 frueherer Name: ' + n)
            abb[n] = neu
        open(p, 'w', encoding='iso-8859-1', newline='').write('\n'.join(z))
    # Listen mitziehen: nur ganze Felder
    teile = sorted(abb, key=len, reverse=True)
    such = re.compile('(?<=[",;])' + '(' + '|'.join(re.escape(k) for k in teile) + ')' + '(?=[";\\t\\r\\n])')
    for p in glob.glob('harmonics/help/*.csv'):
        if p.endswith('namen_codes_20261101.csv'):
            continue
        roh = open(p, 'rb').read()
        for enc in ('utf-8', 'iso-8859-1'):
            try:
                t = roh.decode(enc)
                break
            except UnicodeDecodeError:
                pass
        neu, k = such.subn(lambda m: abb[m.group(1)], t)
        if k:
            open(p, 'wb').write(neu.encode(enc))
            print('  Liste', os.path.basename(p), k)
    ziel = 'harmonics/help/namen_codes_20261101.csv'
    neu_angelegt = not os.path.exists(ziel)
    with open(ziel, 'a', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        if neu_angelegt:
            w.writerow(['datei', 'alt', 'neu'])
        for x in plan:
            w.writerow([x[0], x[2], x[3]])


main()
