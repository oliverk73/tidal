#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Namen, denen Sonderzeichen fehlen (Oliver 9.11.2026: "Austervag (Bjornoya)" muss "Austervåg (Bjørnøya)" heissen).

Je Satz werden Suchwort (vor Klammer/Komma) und Klammerinhalt einzeln geprueft: Liegt bis KM ein GeoNames-Ort
(Haupt- oder Alternativname), der ohne Akzente genau so heisst, aber Sonderzeichen hat, ist das ein Kandidat.
Nur Formen, die in Latin-1 passen (Harmonics-Dateien sind Latin-1; UTF-8 erst ganz am Ende).
GeoNames-Laenderdateien: download.geonames.org/export/dump/<CC>.zip -> harmonics/help/geonames/<CC>.txt

Usage: venv/bin/python py/sonderzeichen_pruefen.py  -> harmonics/help/sonderzeichen_<datum>.csv
"""
import collections
import csv
import datetime as dt
import io
import math
import os
import re
import sys
import unicodedata
import urllib.request
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import health_check as H                                           # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GN = os.path.join(ROOT, 'harmonics/help/geonames')
KM = 25.0
LAENDER = {
    'Canada': 'CA', 'Newfoundland Canada': 'CA', 'France': 'FR', 'Germany': 'DE', 'Brazil': 'BR', 'Norway': 'NO',
    'Netherlands': 'NL', 'Chile': 'CL', 'Spain': 'ES', 'Argentina': 'AR', 'Denmark': 'DK', 'Greenland': 'GL',
    'Portugal': 'PT', 'Mexico': 'MX', 'México': 'MX', 'Sweden': 'SE', 'Italy': 'IT', 'Iceland': 'IS',
    'New Caledonia': 'NC', 'Mozambique': 'MZ', 'Turkey': 'TR', 'Belgium': 'BE', 'Puerto Rico': 'PR',
    'French Polynesia': 'PF', 'Ecuador': 'EC', 'Morocco': 'MA', 'Cuba': 'CU', 'Panama': 'PA', 'Peru': 'PE',
    'Tunisia': 'TN', 'Finland': 'FI', 'Faroe Islands': 'FO', 'Guinea-Bissau': 'GW', 'Colombia': 'CO', 'Angola': 'AO',
    'Estonia': 'EE', 'Venezuela': 'VE', 'Svalbard': 'SJ', 'Jan Mayen': 'SJ', 'Senegal': 'SN', 'Cape Verde': 'CV',
    'Costa Rica': 'CR', 'Cameroon': 'CM', 'Mauritania': 'MR', 'French Guiana': 'GF', 'Poland': 'PL',
    'Martinique': 'MQ', 'Guinea': 'GN', 'Western Sahara': 'EH', 'Gabon': 'GA', 'Guadeloupe': 'GP', 'Djibouti': 'DJ',
    'Ivory Coast': 'CI', 'Dominican Republic': 'DO', 'Equatorial Guinea': 'GQ', 'Guatemala': 'GT', 'Uruguay': 'UY',
    'São Tomé and Príncipe': 'ST', 'Honduras': 'HN', 'Nicaragua': 'NI', 'El Salvador': 'SV', 'Mayotte': 'YT',
    'Réunion': 'RE', 'Wallis and Futuna': 'WF', 'Comoros': 'KM', 'Haiti': 'HT', 'Saint-Pierre-et-Miquelon': 'PM',
    'Curaçao': 'CW', 'Togo': 'TG', 'Benin': 'BJ', 'Democratic Republic of the Congo': 'CD', 'Albania': 'AL',
    'Montenegro': 'ME', 'Croatia': 'HR', 'Latvia': 'LV', 'Madagascar': 'MG', 'Algeria': 'DZ',
    'French Southern Territories': 'TF', 'Îles Éparses': 'TF',
}
ERSATZ = str.maketrans({'ø': 'o', 'Ø': 'O', 'æ': 'ae', 'Æ': 'Ae', 'ß': 'ss', 'ð': 'd', 'Ð': 'D', 'þ': 'th', 'Þ': 'Th',
                        'œ': 'oe', 'Œ': 'Oe', 'ı': 'i'})


def ohne(s):
    """-> Formen ohne Sonderzeichen (aeoeue und aou fuer Umlaute)."""
    s2 = s.translate(ERSATZ)
    a = unicodedata.normalize('NFKD', s2).encode('ascii', 'ignore').decode()
    b = unicodedata.normalize('NFKD', s2.replace('ä', 'ae').replace('ö', 'oe').replace('ü', 'ue').replace('Ä', 'Ae')
                              .replace('Ö', 'Oe').replace('Ü', 'Ue')).encode('ascii', 'ignore').decode()
    return {a.lower(), b.lower()}


def latin1(s):
    try:
        s.encode('iso-8859-1')
        return True
    except UnicodeEncodeError:
        return False


def geonames(cc):
    pfad = os.path.join(GN, '%s.txt' % cc)
    if not os.path.exists(pfad):
        z = zipfile.ZipFile(io.BytesIO(urllib.request.urlopen(
            'https://download.geonames.org/export/dump/%s.zip' % cc, timeout=600).read()))
        open(pfad, 'wb').write(z.read('%s.txt' % cc))
    out = []
    for z in open(pfad, encoding='utf-8'):
        f = z.rstrip('\n').split('\t')
        if len(f) < 8:
            continue
        namen = {f[1]}       # nur Hauptname: Alternativnamen enthalten fremdsprachige Formen (Buenos Aires -> Buenos Aires mit Akzenten)
        namen = {n for n in namen if not n.isascii() and latin1(n) and re.search('[A-Za-z]', n)}
        if namen:
            out.append((float(f[4]), float(f[5]), namen, f[7]))
    return out


def teile(name):
    """-> Suchwort und Klammerinhalte (ohne Land/Verwaltung, ohne ' Current')."""
    kern = name.replace(' Current', '').split(',')[0]
    t = [re.split(r'\s*\(', kern)[0].strip()] + re.findall(r'\(([^)]*)\)', kern)
    return [x.strip() for x in t if x.strip() and x.strip().isascii() and len(re.sub('[^A-Za-z]', '', x)) >= 4]


def main(argv):
    os.makedirs(GN, exist_ok=True)
    recs = [r for r in H.load_records() if r['lat'] is not None]
    nach_land = collections.defaultdict(list)
    for r in recs:
        land = r['name'].replace(' Current', '').split(',')[-1].strip()
        if land in LAENDER:
            nach_land[LAENDER[land]].append(r)
    zeilen = []
    for cc, rs in sorted(nach_land.items()):
        try:
            G = geonames(cc)
        except Exception as e:                                         # noqa: BLE001
            print(cc, 'GeoNames fehlt:', e)
            continue
        for r in rs:
            for t in teile(r['name']):
                tl = t.lower()
                treffer = collections.Counter()
                for la, lo, namen, fcode in G:
                    if abs(la - r['lat']) > KM / 111 or abs(lo - r['lon']) > KM / 111 / max(0.1, math.cos(math.radians(la))):
                        continue
                    for n in namen:
                        if tl in ohne(n):
                            treffer[n] += 1
                if treffer:
                    neu = treffer.most_common(1)[0][0]
                    zeilen.append(dict(datei=r['file'].split('harmonics/')[-1], name=r['name'], teil=t, vorschlag=neu,
                                       varianten='; '.join('%s (%d)' % x for x in treffer.most_common(4))))
        print(cc, len(rs), 'Saetze', sum(1 for z in zeilen if z['name'] in {r['name'] for r in rs}), 'Kandidaten', flush=True)
    ziel = os.path.join(ROOT, 'harmonics/help/sonderzeichen_%s.csv' % dt.date.today().strftime('%Y%m%d'))
    with open(ziel, 'w', encoding='utf-8', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=['datei', 'name', 'teil', 'vorschlag', 'varianten'])
        w.writeheader()
        w.writerows(zeilen)
    print(len(zeilen), 'Kandidaten ->', os.path.relpath(ziel, ROOT))


if __name__ == '__main__':
    main(sys.argv[1:])
