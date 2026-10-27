#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Gegenprobe unserer Saetze an den NP202-Standardhaefen gegen ATT NP202 Table V Part 1.

Table V Part 1 (harmonics/help/np202_2015_table5_part1_standard.tsv, 27.10.2026 abgelesen) nennt
fuer 101 Standardhaefen LAT, MLWS, MLWN, MSL, MHWN, MHWS und HAT ueber Kartennull. Die Transfers
brauchen sie nicht (die Gruppenkoepfe in Part II tragen ihre Pegel selbst), sie pruefen aber die
Saetze, die wir an diesen Haefen fuehren -- die stammen aus Messungen, NOAA, TICON, nicht aus NP202.

Verglichen wird, was vom Bezug unabhaengig ist:
  halbtaegig:  Springhub MHWS-MLWS gegen 2(M2+S2), Nipphub MHWN-MLWN gegen 2(M2-S2)
  beide:       HAT-LAT gegen Hoechst- minus Tiefststand der Kurve 2026-2044 (10 min)
und, nur bei Saetzen mit Kartennull als Bezug, Z0 gegen MSL.
Das Buch rundet auf 0,1 m; auffaellig ist erst, was um mehr als 0,25 m bzw. 15 % abweicht.

Ergebnis 27.10.2026: Der Nipphub liegt an der ganzen Nordseekueste 0,3-0,9 m unter dem Buch, bei allen
Messsaetzen gleich -- im Flachwasser sind MHWN/MLWN keine 2(M2-S2). Ein Nipphub-Befund allein gilt
deshalb nicht als auffaellig. Gefunden: Hamburg-Bunthaus (Fit voller Fehlwerte, neu gefittet).

Aufruf: venv/bin/python py/np202_standardhaefen_probe.py
        -> harmonics/help/np202_standardhaefen_probe.csv
"""
import csv
import math
import os
import re
import sys
import unicodedata

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import xtide_modell as X                                           # noqa: E402
from health_check import load_records, ROOT                        # noqa: E402

TAB = os.path.join(ROOT, 'harmonics/help/np202_2015_table5_part1_standard.tsv')
AUS = os.path.join(ROOT, 'harmonics/help/np202_standardhaefen_probe.csv')

# Buchname -> (Muster auf den Satznamen vor dem ersten Komma bzw. der Klammer, Pflichtwort im Namen)
SUCHE = {
    'Torshavn': ('torshavn', 'faroe'), 'Bergen': ('bergen', 'norway'), 'Oslo': ('oslo', 'norway'), "Arkhangel'sk": ('arkhangel', 'russia'),
    "Port of Kem'": ('kem', 'russia'), 'Ostrov Yekaterininskiy': ('ostrov yekaterininsk', 'russia'),
    'Brunsbuttel Mole 1': ('brunsbuttel', 'germany'), 'Antwerp (Prosperpolder)': ('prosperpolder', ''),
    'Vlissingen (Flushing)': ('vlissingen', ''), 'St. Malo': ('saint-malo|st\\.? malo', 'france'),
    'Lorient (Arsenal)': ('lorient', 'france'), 'La Rochelle - La Pallice': ('la pallice|la rochelle', 'france'),
    'Georgetown (Guyana)': ('georgetown', 'guyana'), 'Bermuda (St. Georges Is)': ("st\\.? george'?s|esso pier", 'bermuda'),
    'Miami Harbour': ('miami', 'florida'), 'Palm Beach': ('palm beach|lake worth', 'florida'),
    'Savannah': ('savannah', 'georgia'), 'Charleston': ('charleston', 'south carolina'),
    'Hampton Roads': ('hampton roads|sewells point', 'virginia'), 'Baltimore': ('baltimore', 'maryland'),
    'Marcus Hook': ('marcus hook', 'pennsylvania'), 'Billingsport': ('billingsport', 'new jersey'),
    'Sandy Hook (New York Bay)': ('sandy hook', 'new jersey'), 'The Battery': ('the battery', 'new york'),
    'New Haven Harbour': ('new haven', 'connecticut'), 'Boston': ('boston', 'massachusetts'),
    'Saint John NB': ('saint john', 'new brunswick'), 'Halifax': ('halifax', 'nova scotia'),
    'Point Tupper': ('point tupper', 'nova scotia'), 'Pointe-au-Pere': ('pointe-au-pere|rimouski', 'quebec'),
    'Port Alfred': ('port-alfred|port alfred', 'quebec'), 'Quebec': ('quebec|lauzon', 'quebec'),
    'Baie Comeau': ('baie-comeau|baie comeau', 'quebec'), 'Harrington Harbour': ('harrington harbour', 'quebec'),
    'Argentia': ('argentia', 'newfoundland'), "St. John's Harbour (Newfoundland)": ("st\\.? john'?s", 'newfoundland'),
    'Ponta Delgada': ('ponta delgada', 'azores|portugal'), 'Port of Spain': ('port of spain', 'trinidad'),
    'Lisas Point': ('lisas', 'trinidad'), 'Puerto la Guaira': ('la guaira', 'venezuela'),
    'Amuay': ('amuay|punta cardon', 'venezuela'), 'Malecon (Isla Zapara)': ('malecon|zapara', 'venezuela'),
    'Santa Marta': ('santa marta', 'colombia'), 'Cartagena': ('cartagena', 'colombia'),
    'Punta Covenas': ('covenas', 'colombia'), 'Punta Yarumal': ('yarumal', 'colombia'),
    'Colon': ('colon|cristobal', 'panama'), 'Bridgetown': ('bridgetown', 'barbados'),
    'Castries': ('castries', 'lucia'), 'Saint Croix (Limetree Bay)': ('limetree', 'virgin'),
    'Santo Domingo': ('santo domingo', 'dominican'), 'Habana': ('habana|havana', 'cuba'),
    'Progreso': ('progreso', 'yucatan'), 'Campeche': ('campeche', 'campeche'),
    'Dos Bocas': ('dos bocas', 'tabasco'), 'Vera Cruz': ('veracruz|vera cruz', 'veracruz'),
    'Tampico': ('tampico|madero', 'tamaulipas'), 'Matamaros': ('matamoros|el mezquital', 'tamaulipas'),
    'Corpus Christi': ('corpus christi', 'texas'), 'Galveston': ('galveston', 'texas'),
    'Manchester': ('manchester', 'texas'), 'Sabine Pass': ('sabine pass', 'texas|louisiana'),
    'Mobile': ('mobile', 'alabama'), 'St. Petersburg': ('st\\.? petersburg', 'florida'),
    'Mckay Bay Entrance': ('mckay bay', 'florida'), 'Aulds Cove': ('aulds cove', 'nova scotia'),
    'Pictou': ('pictou', 'nova scotia'), 'Pointe St. Pierre': ('pointe saint-pierre|pointe st\\.? pierre', 'quebec'),
}


def norm(s):
    s = s.replace('ø', 'o').replace('Ø', 'O').replace('æ', 'ae').replace('ð', 'd')
    return unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode().lower()


def buch():
    out = []
    for z in csv.reader(open(TAB, encoding='utf-8'), delimiter='\t'):
        if not z or z[0].startswith('#'):
            continue
        w = [float(x) if x not in ('',) else None for x in z[2:9]]
        out.append(dict(hafen=z[0], typ=z[1], lat=w[0], mlws=w[1], mlwn=w[2], msl=w[3], mhwn=w[4],
                        mhws=w[5], hat=w[6]))
    return out


def kandidaten(h, recs):
    muster, pflicht = SUCHE.get(h['hafen'], (re.escape(norm(h['hafen'])), ''))
    rx = re.compile(r'^(%s)\b' % muster)
    out = []
    for r in recs:
        n = norm(r['name'])
        kopf = n.split(',')[0]
        if (rx.search(kopf) or rx.search(re.sub(r'^.*\(', '', kopf))) and (not pflicht or re.search(pflicht, n)):
            out.append(r)
    return out


def kurve_extreme(r):
    namen, speeds, arg, fak = X.kopf_lesen(os.path.join(ROOT, r['file']))
    z0, werte, einheit, mer = X.satz_lesen(os.path.join(ROOT, r['file']), r['name'])
    sk = 0.3048 if einheit.startswith('f') else 1.0
    lo, hi = math.inf, -math.inf
    for jahr in range(2026, 2045):
        if jahr not in arg:
            continue
        t0 = X.jahresbeginn(jahr)
        t = t0 + np.arange(0, 366 * 86400, 600.0)
        t = t[t < X.jahresbeginn(jahr + 1)]
        h = X.kurve(t, z0, werte, namen, speeds, arg, fak, sk)
        lo, hi = min(lo, h.min()), max(hi, h.max())
    m2 = werte.get('M2', (0, 0))[0] * sk
    s2 = werte.get('S2', (0, 0))[0] * sk
    return z0 * sk, lo, hi, m2, s2


def datum_cd(r):
    k = open(os.path.join(ROOT, r['file']), encoding='iso-8859-1').read().split('\n')
    for j in range(r['line'] - 1, max(0, r['line'] - 80), -1):
        if k[j].startswith('# datum:'):
            return k[j][8:].strip()
        if 'BEGIN HOT' in k[j]:
            break
    return ''


def main(argv):
    recs = [r for r in load_records() if r['lat'] is not None and not r['current']
            and 'fes' not in r['file'] and '/backup/' not in r['file']]
    zeilen = []
    for h in buch():
        ks = kandidaten(h, recs)
        if not ks:
            zeilen.append(dict(hafen=h['hafen'], satz='', datei='', urteil='kein Satz'))
            continue
        for r in ks:
            z0, lo, hi, m2, s2 = kurve_extreme(r)
            d = datum_cd(r)
            z = dict(hafen=h['hafen'], satz=r['name'], datei=os.path.basename(r['file']), datum=d[:40])
            fehler = []
            if h['typ'] == 'halbtaegig':
                sb, nb = h['mhws'] - h['mlws'], h['mhwn'] - h['mlwn']
                z.update(spring_buch=sb, spring=round(2 * (m2 + s2), 2), nipp_buch=nb, nipp=round(2 * (m2 - s2), 2))
                if abs(2 * (m2 + s2) - sb) > max(0.25, 0.15 * sb):
                    fehler.append('Springhub')
                if abs(2 * (m2 - s2) - nb) > max(0.25, 0.15 * max(nb, 0.1)):
                    fehler.append('Nipphub')
            hb = h['hat'] - h['lat']
            z.update(hatlat_buch=round(hb, 2), hatlat=round(hi - lo, 2))
            if abs((hi - lo) - hb) > max(0.25, 0.15 * hb):
                fehler.append('HAT-LAT')
            if re.search(r'(?i)chart datum|LAT|kartennull', d) and not re.search(r'(?i)approx', d):
                z.update(msl_buch=h['msl'], z0=round(z0, 2), lat_ueber_cd=round(lo, 2))
                if abs(z0 - h['msl']) > 0.25:
                    fehler.append('Z0/MSL')
            z['urteil'] = ', '.join(fehler) or 'passt'
            zeilen.append(z)
    felder = ['hafen', 'urteil', 'satz', 'datei', 'datum', 'spring_buch', 'spring', 'nipp_buch', 'nipp',
              'hatlat_buch', 'hatlat', 'msl_buch', 'z0', 'lat_ueber_cd']
    with open(AUS, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=felder, extrasaction='ignore')
        w.writeheader()
        w.writerows(zeilen)
    n = sum(1 for z in zeilen if z['satz'])
    a = [z for z in zeilen if z['urteil'] not in ('passt', 'kein Satz', 'Nipphub')]
    print('%d Saetze an %d Haefen, %d auffaellig, %d Haefen ohne Satz -> %s' % (
        n, len({z['hafen'] for z in zeilen if z['satz']}), len(a),
        sum(1 for z in zeilen if z['urteil'] == 'kein Satz'), AUS))
    for z in a:
        print('  %-26s %-44s %-28s %s' % (z['hafen'][:26], z['satz'][:44], z['datei'][:28], z['urteil']))


if __name__ == '__main__':
    main(sys.argv[1:])
