#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Rechnet NOAA-Table-2-Uebertragungen gegen ihre Buchzeile nach (Bestand und Archiv).

Oliver 17.10.2026: Im Kara-/Ob-Gebiet lagen 9 Yekaterininskaya-Uebertragungen genau 120 min neben der
Buchzeile (Zonendrehung 3.9. nur -1 h statt -3/-4 h). Probe fuer alle Bezugsorte: Phase des Satzes minus
Buchdifferenz, in Greenwich-Zeit (Zone Neben-/Bezugsort aus dem Buch):
    roh = G_satz - speed * (dt_mittel - (Zone_neben - Zone_bezug) * 60) / 60
Innerhalb einer Bezugsgruppe muss roh fuer alle Saetze gleich sein (= G des Bezugsorts); der Gruppenmedian
dient als Bezug, Abweichungen ueber 40 min werden gemeldet. Halbtaegig ueber M2, taegliche Orte ueber K1.
Archivierte Saetze (harmonics/backup/geloescht) laufen mit, damit kein wegen dieses Fehlers geloeschter
Satz unentdeckt bleibt.

Usage: venv/bin/python py/noaa_buchzeilen_probe.py  -> harmonics/help/noaa_buchzeilen_probe.csv
"""
import collections
import csv
import json
import os
import re
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import xtide_modell as X                                           # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HELP = os.path.join(ROOT, 'harmonics/help')
DATEIEN = {'harmonics_noaa_eutt.txt': ['eutt2020'], 'harmonics_noaa_cptt.txt': ['cptt2018'],
           'harmonics_noaa_amtt.txt': ['ectt2020', 'wctt2020']}
GRENZE = 40


def buch():
    out = {}
    for b in ['eutt2020', 'cptt2018', 'ectt2020', 'wctt2020']:
        z = json.load(open(os.path.join(HELP, 'zonen_%s.json' % b), encoding='utf-8'))
        zs = {int(k.split('-')[-1]): v for k, v in z['stationen'].items()}
        for x in json.load(open(os.path.join(HELP, '%s_table2_full.json' % b), encoding='utf-8')):
            try:
                no = int(str(x['no']).rstrip('abc'))
            except ValueError:
                continue
            out.setdefault(b, {})[no] = (x, zs.get(no), z['referenzen'])
    return out


def bloecke(pfad, namen):
    """-> [(name, kommentare, meridian, {c: (a, kappa)})] fuer Bestand oder Archiv."""
    L = open(pfad, encoding='iso-8859-1').read().split('\n')
    res, kom = [], []
    i = 0
    while i < len(L):
        l = L[i]
        if l.startswith('#'):
            kom.append(l)
            i += 1
            continue
        if l and i + 2 < len(L) and ':' in L[i + 1] and L[i + 2].endswith(('meters', 'feet', 'knots')) and 'transfer from' in ' '.join(kom):
            w = {}
            for j, c in enumerate(namen):
                t = L[i + 3 + j].split()
                if t and t[0] != 'x':
                    w[c] = (float(t[1]), float(t[2]))
            res.append((l, kom, L[i + 1].split()[0], w))
            i += 3 + len(namen)
            kom = []
            continue
        if l.strip() == '':
            kom = []
        i += 1
    return res


def main():
    B = buch()
    zeilen = []
    for datei, baender in DATEIEN.items():
        aktiv = os.path.join(ROOT, 'harmonics/noaa', datei)
        namen, sp, _a, _f = X.kopf_lesen(aktiv)
        for herkunft, pfad in [('bestand', aktiv), ('archiv', os.path.join(ROOT, 'harmonics/backup/geloescht', datei))]:
            if not os.path.exists(pfad):
                continue
            for name, kom, mer, w in bloecke(pfad, namen):
                v = ' '.join(kom)
                m = re.search(r'transfer from (.+?) \(no\.(\d+)\)', v)
                if not m:
                    continue
                no = int(m.group(2))
                uid = re.search(r'noaa_uid: (\w+)-(\d+)', v)
                kand = [b for b in baender if no in B.get(b, {})]
                if uid:
                    kand = [b for b in kand if b.startswith(uid.group(1))] or kand
                if len(kand) > 1:
                    kand = [b for b in kand if re.sub(r'\W', '', B[b][no][0]['ref'].lower())[:6] in re.sub(r'\W', '', m.group(1).lower())] or kand
                if not kand:
                    continue
                band = kand[0]
                x, zone, refz = B[band][no]
                if x.get('dtHW') is None or zone is None:
                    continue
                zn, ref = zone
                zb = refz.get(re.sub(r'[^a-z0-9]', '', ref.lower()))
                if isinstance(zb, list):
                    zb = zb[0]
                if zb is None or isinstance(zn, str) or isinstance(zb, str):
                    continue                             # 'local'-Meridiane: keine Zonenrechnung moeglich
                tag = (w.get('K1', (0, 0))[0] + w.get('O1', (0, 0))[0]) > 1.5 * (w.get('M2', (0, 0))[0] + w.get('S2', (0, 0))[0])
                c = 'K1' if tag else 'M2'
                if c not in w:
                    continue
                hh, mm = mer.lstrip('+-').split(':')
                g = X.greenwich(w[c][1], sp[c], (-1 if mer.startswith('-') else 1) * (int(hh) + int(mm) / 60)) % 360
                dtm = (x['dtHW'] + (x['dtLW'] if x['dtLW'] is not None else x['dtHW'])) / 2
                roh = (g - sp[c] * (dtm - (zn - zb) * 60) / 60) % 360
                zeilen.append(dict(band=band, ref=ref, no=no, herkunft=herkunft, datei=datei, name=name, konst=c,
                                   speed=sp[c], roh=roh, archivgrund=(kom[0][:160] if herkunft == 'archiv' else '')))
    gruppen = collections.defaultdict(list)
    for z in zeilen:
        gruppen[(z['band'], z['ref'], z['konst'])].append(z)
    for k, g in gruppen.items():
        best = g if len([z for z in g if z['herkunft'] == 'bestand']) < 3 else [z for z in g if z['herkunft'] == 'bestand']
        # zirkulaerer Median: der roh-Wert mit der kleinsten Summe der Abstaende
        med = min((z['roh'] for z in best), key=lambda r: sum(abs((q['roh'] - r + 180) % 360 - 180) for q in best))
        for z in g:
            z['n_gruppe'] = len(best)
            z['abw_min'] = round(((z['roh'] - med + 180) % 360 - 180) / z['speed'] * 60)
    aus = os.path.join(HELP, 'noaa_buchzeilen_probe.csv')
    felder = ['band', 'ref', 'no', 'herkunft', 'datei', 'name', 'konst', 'n_gruppe', 'abw_min', 'archivgrund']
    with open(aus, 'w', newline='', encoding='utf-8') as fh:
        wr = csv.DictWriter(fh, fieldnames=felder, extrasaction='ignore')
        wr.writeheader()
        for z in sorted(zeilen, key=lambda z: (z['band'], z['ref'], z['no'])):
            wr.writerow(z)
    auff = [z for z in zeilen if abs(z['abw_min']) > GRENZE and z['n_gruppe'] >= 3]
    print('%d Saetze geprueft (%d Bestand, %d Archiv), %d ueber %d min:' % (
        len(zeilen), sum(z['herkunft'] == 'bestand' for z in zeilen), sum(z['herkunft'] == 'archiv' for z in zeilen), len(auff), GRENZE))
    for z in sorted(auff, key=lambda z: (z['herkunft'], z['band'], z['ref'], z['no'])):
        print('%-7s %-8s %-22s %5d %-55s %s %+5d min (n=%d)' % (z['herkunft'], z['band'], z['ref'][:22], z['no'], z['name'][:55], z['konst'], z['abw_min'], z['n_gruppe']))
    print('->', os.path.relpath(aus, ROOT))


if __name__ == '__main__':
    main()
