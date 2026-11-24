#!/usr/bin/env python3
"""NP160 (UKHO Tidal Harmonic Constants, European Waters) als Zeuge gegen den Bestand.

Abschrift: harmonics/help/np160_part3.tsv (Buchseiten 10-28, von Hand gegen den Scan gelesen,
quellen/harmonics_sources/att/np160_european_waters.pdf). NP160 hat keinen Part II, also keine
Positionen: UK/IE (Nr. < 780) ueber das EasyTide-Verzeichnis (Id = ATT-Nummer), uebriges Europa
ueber harmonics/help/ukho_index_abgleich.csv, sonst ueber '# att_number:' eines Bestandssatzes.

Je NP160-Ort werden alle Gezeitensaetze bis RADIUS_KM verglichen (M2, S2, K1, O1 in UTC-Phase).
Ausgabe: harmonics/help/np160_zeugen_<datum>.csv (eine Zeile je Paar) + Zusammenfassung.

    venv/bin/python py/np160_zeugen.py [--radius 3]
"""
import cmath
import csv
import json
import math
import os
import re
import sys
import unicodedata
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from health_check import load_records, km, ROOT, SPEED  # noqa: E402

TSV = os.path.join(ROOT, 'harmonics', 'help', 'np160_part3.tsv')
SAISON = os.path.join(ROOT, 'harmonics', 'help', 'np160_saison.tsv')
EASY = os.path.join(ROOT, 'quellen', 'harmonics_sources', 'att', 'np160', 'easytide_stations.json')
INDEX = os.path.join(ROOT, 'harmonics', 'help', 'ukho_index_abgleich.csv')
RANG = [('harmonics/utide/', 1), ('harmonics/ticon/', 2), ('harmonics/classic/', 3),
        ('harmonics/att/', 4), ('harmonics/noaa/', 5)]
KONST = ['M2', 'S2', 'K1', 'O1']


def rang(f):
    return next((v for k, v in RANG if f.startswith(k)), 9)


def zahl(s):
    try:
        return float(s)
    except ValueError:
        return None


def nr_norm(s):
    m = re.match(r'0*(\d+)([A-Za-z]?)$', s.strip())
    return (m.group(1) + m.group(2).lower()) if m else s.strip().lower()


def zone_stunden(z):
    """Admiralty-Zone '-0100' = Ortszeit UT+1 -> +1 h (wie NP202-Import: Meridian +01:00)."""
    if z in ('0', '', None):
        return 0.0
    v = -1 if z.startswith('-') else 1
    z = z.lstrip('+-')
    return -v * (int(z[:2]) + int(z[2:]) / 60.0)


def buch():
    saison = {}
    for r in csv.DictReader(open(SAISON), delimiter='\t'):
        if r['groesse'] in ('M2', 'S2') and '-' not in r['nr']:
            werte = [float(r[m]) for m in ('jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec')]
            saison[(r['nr'], r['groesse'])] = sum(werte) / 12
    aus = []
    for r in csv.DictReader(open(TSV), delimiter='\t'):
        h = zone_stunden(r['zone'])
        z = {}
        for c, gk, hk in (('M2', 'm2g', 'm2h'), ('S2', 's2g', 's2h'), ('K1', 'k1g', 'k1h'), ('O1', 'o1g', 'o1h')):
            a = zahl(r[hk]) if r[hk] != 'v' else saison.get((r['nr'], c))
            g = zahl(r[gk])
            if a is None:
                z[c] = None
                continue
            if g is None:                      # '-' bei Amplitude 0.00
                g = 0.0
            z[c] = cmath.rect(a, -math.radians((g - SPEED[c] * h) % 360))
        aus.append(dict(r, z=z, nrn=nr_norm(r['nr'])))
    return aus


# Bekannte Haefen ohne Index-/EasyTide-Eintrag und ohne Namenstreffer (nur fuer die Zeugensuche, 3-km-Umkreis)
HAND = {'390': (55.425, -5.740, 'Hand Machrihanish'), '623a': (53.717, -6.347, 'Hand Drogheda'),
        '1539a': (51.283, 4.330, 'Hand Boudewijnsluis Antwerpen'), '1539b': (51.235, 4.405, 'Hand Royerssluis Antwerpen'),
        '1607': (49.287, -1.930, 'Hand Les Ecrehou'), '1694': (43.325, -1.925, 'Hand Pasaia'),
        '1735': (41.142, -8.620, 'Hand Porto (Douro)'), '1741': (38.703, -9.140, 'Hand Lisboa'),
        '1790': (43.733, 7.425, 'Hand Monaco'), '1850': (43.877, 8.020, 'Hand Imperia'),
        '1851': (44.405, 8.925, 'Hand Genova'), '1995': (32.075, 23.975, 'Hand Tobruk'), '1842': (33.505, 11.115, 'Hand Zarzis')}


def positionen():
    pos = dict(HAND)
    for f in json.load(open(EASY))['features']:
        n = nr_norm(f['properties']['Id'])
        lon, lat = f['geometry']['coordinates']
        pos[n] = (lat, lon, 'EasyTide ' + f['properties']['Name'])
    for r in csv.DictReader(open(INDEX)):
        n = nr_norm(r['nr'])
        if n not in pos and r['lat'] and r['lat'] != 'nan':
            try:
                pos[n] = (float(r['lat']), float(r['lon']), 'UKHO-Index ' + r['satz'])
            except ValueError:
                pass
    return pos


def att_nummern(recs):
    """'# att_number:' der Bestandssaetze -> Liste Datensaetze."""
    cache, aus = {}, {}
    for r in recs:
        if r['file'] not in cache:
            cache[r['file']] = open(os.path.join(ROOT, r['file']), encoding='iso-8859-1').read().split('\n')
        zeilen = cache[r['file']]
        k = r['line'] - 2
        while k >= 0 and zeilen[k].startswith('#'):
            m = re.match(r'#\s*att_number:\s*(\S+)', zeilen[k])
            if m:
                aus.setdefault(nr_norm(m.group(1)), []).append(r)
                r['att'] = nr_norm(m.group(1))
                break
            k -= 1
    return aus


def _woerter(s):
    s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode().lower()
    return [w for w in re.split(r"[^a-z]+", s) if len(w) > 2]


STOPP = {'the', 'port', 'porto', 'puerto', 'harbour', 'harbor', 'bay', 'baie', 'river', 'rio', 'island', 'isla',
         'ile', 'nisos', 'mys', 'guba', 'reka', 'ostrov', 'zaliv', 'bukhta', 'cabo', 'punta', 'capo', 'mina', 'marsa',
         'entrance', 'bar', 'north', 'south', 'west', 'east', 'spain', 'france', 'italy', 'portugal', 'les', 'la', 'le',
         'de', 'del', 'ria', 'ras', 'san', 'santa', 'sur', 'mer', 'baie', 'haven', 'dock', 'pier', 'quay', 'point'}


def namenssuche(b, i, bk, recs, max_anker_km=700.0, namensanker=False):
    """Position ueber den Namen: Bestandssatz mit Namenswort, nahe dem naechsten Buchnachbarn mit Position."""
    anker = None
    for d in range(1, 40):
        for j in (i - d, i + d):
            if 0 <= j < len(bk) and bk[j].get('p') and (namensanker or not bk[j]['p'][2].startswith('Name')):
                anker = bk[j]['p']
                break
        if anker:
            break
    if anker is None:
        return None
    teile = re.split(r'[()]', b['name'])
    worte = [w for t in teile for w in _woerter(t) if w not in STOPP]
    if not worte:
        return None
    best = None
    for r in recs:
        rw = set(_woerter(r['name'].split(',')[0]))
        if not rw or not any(w in rw for w in worte):
            continue
        d = km({'lat': anker[0], 'lon': anker[1]}, r)
        if d > max_anker_km:
            continue
        k = (sum(w in rw for w in worte), -rang(r['file']), -d)
        if best is None or k > best[0]:
            best = (k, r)
    if best is None:
        return None
    r = best[1]
    return (r['lat'], r['lon'], 'Name ' + r['name'])


def vergleich(b, r):
    out = {}
    for c in KONST:
        zb, zr = b['z'][c], r['z'][c]
        if zb is None:
            out[c] = (None, None, None)
            continue
        ab, ar = abs(zb), abs(zr)
        dg = None
        if ab >= 0.02 and ar >= 0.02:
            dg = (math.degrees(cmath.phase(zb) - cmath.phase(zr)) * -1 + 180) % 360 - 180   # Buch - Satz
        out[c] = (ab, ar, dg)
    # Vektorfehler M2+S2+K1+O1 relativ zur Buchsumme
    num = sum(abs(b['z'][c] - r['z'][c]) for c in KONST if b['z'][c] is not None)
    den = sum(abs(b['z'][c]) for c in KONST if b['z'][c] is not None)
    return out, (num / den if den else None)


def main(argv):
    radius = float(argv[argv.index('--radius') + 1]) if '--radius' in argv else 3.0
    bk = buch()
    pos = positionen()
    recs = [r for r in load_records() if not r['current'] and r['lat'] is not None]
    att = att_nummern(recs)
    zeilen, ohne = [], []
    for b in bk:
        p = pos.get(b['nrn'])
        if p is None and b['nrn'] in att:
            s = att[b['nrn']][0]
            p = (s['lat'], s['lon'], 'att_number ' + s['name'])
        b['p'] = p
    for zweit in (False, True):                      # Rest: Name im Bestand nahe den Buchnachbarn
        for i, b in enumerate(bk):
            if b['p'] is None:
                b['p'] = namenssuche(b, i, bk, recs, namensanker=zweit)
    for b in bk:
        p = b['p']
        if p is None:
            ohne.append(b)
            continue
        lat, lon, quelle = p
        nah = sorted(((km({'lat': lat, 'lon': lon}, r), r) for r in recs), key=lambda x: x[0])
        nah = [(d, r) for d, r in nah if d <= radius]
        for r in att.get(b['nrn'], []):              # gleiche ATT-Nummer immer mitnehmen
            if all(r is not x for _, x in nah):
                nah.append((km({'lat': lat, 'lon': lon}, r), r))
        if not nah:
            zeilen.append(dict(nr=b['nr'], name=b['name'], seite=b['buchseite'], lat=lat, lon=lon, pos_quelle=quelle,
                               satz='', datei='', rang='', km='', luecke=1))
            continue
        for d, r in nah:
            v, vek = vergleich(b, r)
            z = dict(nr=b['nr'], name=b['name'], seite=b['buchseite'], lat=round(lat, 4), lon=round(lon, 4),
                     pos_quelle=quelle, satz=r['name'], datei=r['file'], rang=rang(r['file']), km=round(d, 2),
                     gleiche_att=int(r.get('att') == b['nrn']), luecke=0, vektorfehler=round(vek, 3) if vek is not None else '')
            for c in KONST:
                ab, ar, dg = v[c]
                z[c + '_buch'] = '' if ab is None else round(ab, 3)
                z[c + '_satz'] = '' if ar is None else round(ar, 3)
                z[c + '_dg'] = '' if dg is None else round(dg, 1)
            zeilen.append(z)
    aus = os.path.join(ROOT, 'harmonics', 'help', 'np160_zeugen_%s.csv' % date.today().strftime('%Y%m%d'))
    felder = list(dict.fromkeys(k for z in zeilen for k in z))
    with open(aus, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=felder)
        w.writeheader()
        w.writerows(zeilen)
    print('NP160-Orte %d, ohne Position %d, Paare %d, Luecken %d' % (
        len(bk), len(ohne), sum(1 for z in zeilen if not z['luecke']), sum(1 for z in zeilen if z['luecke'])))
    print('ohne Position:', ', '.join('%s %s' % (b['nr'], b['name']) for b in ohne))
    print('->', os.path.relpath(aus, ROOT))


if __name__ == '__main__':
    main(sys.argv[1:])
