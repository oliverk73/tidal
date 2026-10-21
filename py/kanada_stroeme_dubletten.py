#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Kanadische Stromstationen: Dubletten zu CHS bereinigen, Provinz in den Namen (Oliver 21.10.2026).

Bester Satz = CHS (zustaendige Behoerde); CHS-Messfit (1-5 Jahre) vor CHS-Tafelfit am selben Ort.
Archiviert werden bis 1 km neben einem CHS-Satz: XTide-2004-Kopien, NOAA-Stromtabellen (auch bis 3 km bei
gleichem Ort/Namen), gleichnamige CHS-Tafelfits neben einem CHS-Messfit. Wertvolle Namensteile der
archivierten Saetze gehen in den CHS-Namen; alle kanadischen Stroeme bekommen die Provinz.

Usage: python3 py/kanada_stroeme_dubletten.py [--schreiben]
"""
import csv
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import health_check as hc                                           # noqa: E402
import osm_land                                                     # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OBS = 'harmonics/utide/harmonics_utide_current_observations.txt'
TAB = 'harmonics/utide/harmonics_utide_current_tables.txt'
OST = {'Brier Island': 'Nova Scotia', 'Gannet Rock': 'New Brunswick', 'Boars Head': 'Nova Scotia',
       'Prim Point': 'Nova Scotia', 'Cape Spencer': 'New Brunswick', 'Grand Manan Channel': 'New Brunswick',
       "Big Bras D'Or": 'Nova Scotia', 'Abegweit Passage': 'Prince Edward Island'}
# Namen der CHS-Saetze, verbessert mit Teilen der archivierten Zwillinge (Klammer-Regel)
BESSER = {'Grand Manan Channel': 'Grand Manan Channel (Bay of Fundy Entrance)',
          'Seymour Narrows': 'Seymour Narrows (Discovery Passage)',
          'First Narrows': 'First Narrows (Burrard Inlet)',
          'Second Narrows': 'Second Narrows (Burrard Inlet)',
          'Juan de Fuca - East': 'Juan de Fuca Strait (East)',
          'Johnstone Strait - Central': 'Johnstone Strait (Central)',
          'Tillicum Bridge': 'Tillicum Bridge (Gorge)',
          "Big Bras D'Or": "Big Bras d'Or", 'Blackney passage': 'Blackney Passage'}


def provinz(r):
    base = r['name'].split(',')[0].split(' (')[0]
    for k, p in OST.items():
        if r['name'].startswith(k):
            return p
    return 'British Columbia' if r['lon'] < -110 else None


def main(argv):
    R = [r for r in hc.load_records() if r['current'] and r['lat'] is not None]
    chs = [r for r in R if r['file'] in (OBS, TAB) and r['name'].endswith(', Canada Current')]
    chs_obs = [r for r in chs if r['file'] == OBS]
    raus = []
    for r in R:
        if r in chs_obs:
            continue
        kern = r['name'].split(',')[0].split(' (')[0].lower().replace('passage', 'pass').replace('seechelt', 'sechelt')
        for c in sorted((c for c in (chs_obs if r['file'] == TAB else chs) if c is not r),
                        key=lambda c: osm_land.km(r['lat'], r['lon'], c['lat'], c['lon'])):
            d = osm_land.km(r['lat'], r['lon'], c['lat'], c['lon'])
            ckern = c['name'].split(',')[0].split(' (')[0].lower().replace('passage', 'pass')
            if r['file'] == TAB and r['name'] == c['name'] and d < 1:
                raus.append((r, c, d, 'CHS-Tafelfit neben laengerem CHS-Messfit'))
                break
            if r['file'].endswith(('harmonics-2004-06-14_mod.txt', 'harmonics_noaa_currents.txt')) and (
                    d < 1 or (d < 3 and kern == ckern)):
                raus.append((r, c, d, 'Kopie/aeltere Fassung neben CHS-Satz'))
                break
    raus_ids = {(r['file'], r['name'], r['lat']) for r, *_ in raus}
    for r, c, d, w in raus:
        print('ARCHIV %-55s %-28s | %.1f km | %s' % (r['name'][:55], os.path.basename(r['file'])[9:37], d, c['name'][:45]))
    um = {}
    for r in R:
        if (r['file'], r['name'], r['lat']) in raus_ids or not r['name'].endswith(', Canada Current'):
            continue
        p = provinz(r)
        if not p or any(q in r['name'] for q in ('British Columbia', 'New Brunswick', 'Nova Scotia', 'Prince Edward Island')):
            continue
        kopf = r['name'][:-len(', Canada Current')]
        kopf = BESSER.get(kopf, kopf)
        neu = '%s, %s, Canada Current' % (kopf, p)
        if neu != r['name']:
            um.setdefault(r['file'], {})[r['name']] = neu
    namen_alle = {(r['file'], r['name']) for r in R if (r['file'], r['name'], r['lat']) not in raus_ids}
    for f, m in um.items():
        for a, b in m.items():
            assert len(b) <= 88, b
            assert (f, b) not in namen_alle, ('Kollision', f, b)
    print(len(raus), 'archivieren,', sum(len(m) for m in um.values()), 'umbenennen')
    for f, m in sorted(um.items()):
        for a, b in sorted(m.items())[:6]:
            print('  %-28s %s -> %s' % (os.path.basename(f)[9:37], a, b))
    if '--schreiben' not in argv:
        return
    liste = os.path.join(ROOT, 'harmonics/help/kanada_stroeme_20261021_loeschen.csv')
    with open(liste, 'w', newline='', encoding='utf-8') as fh:
        w = csv.writer(fh)
        w.writerow(['datei', 'name', 'fehler_prozent', 'begruendung'])
        for r, c, d, why in raus:
            w.writerow([r['file'], r['name'], '-', '%s (%s, %.1f km). Oliver 21.10.2026' % (why, c['name'], d)])
    subprocess.run([sys.executable, os.path.join(ROOT, 'py/saetze_loeschen.py'), liste, '--schreiben'], check=True, cwd=ROOT)
    tsv = os.path.join(ROOT, 'harmonics/help/kanada_stroeme_20261021_namen.tsv')
    with open(tsv, 'w', encoding='utf-8') as fh:
        for f, m in um.items():
            for a, b in m.items():
                fh.write('%s\t%s\n' % (a, b))
    subprocess.run([sys.executable, os.path.join(ROOT, 'py/namen_teilweise_umbenennen.py'), tsv], check=True, cwd=ROOT)


if __name__ == '__main__':
    main(sys.argv[1:])
