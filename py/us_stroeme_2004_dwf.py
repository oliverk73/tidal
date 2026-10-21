#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""XTide-2004-Stroeme, die neben einem dwf-free-Satz (NOAA 2025) liegen, archivieren (Oliver 21.10.2026).

dwf-free ist der aktuelle NOAA-Stand und damit der beste Satz. Ein 2004-Strom bis 1 km neben einem dwf-Strom
gilt als aeltere Fassung derselben Station, wenn auch der Name passt (gemeinsames kennzeichnendes Wort).
Ohne passenden Namen nur melden. Dazu 2004-Stroeme neben gleichnamigem NOAA-Nebenstrom (aktuelle Tafeln).

Usage: python3 py/us_stroeme_2004_dwf.py [--schreiben]
"""
import csv, os, re, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import health_check as hc, osm_land                                 # noqa: E402
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GLEICH = {'Delaware Bay Entrance, Delaware Current', 'Key West, Florida Current',
          'The Narrows (North End, Puget Sound), Washington Current', 'The Narrows (Midchannel, New York Harbor), New York Current'}
ALLG = {'entrance', 'channel', 'harbor', 'harbour', 'bay', 'river', 'south', 'north', 'east', 'west', 'middle',
        'midchannel', 'depth', 'point', 'pass', 'passage', 'strait', 'island', 'sound', 'narrows', 'bridge', 'inlet', 'between'}


def woerter(n):
    t = re.sub(r'[^a-z ]', ' ', n.lower().replace("'", ''))
    return {w for w in t.split() if len(w) > 3 and w not in ALLG and w not in ('current', 'california', 'florida', 'washington',
            'massachusetts', 'alaska', 'texas', 'york', 'carolina', 'maryland', 'delaware', 'jersey', 'pennsylvania', 'hampshire', 'alabama', 'rico', 'puerto')}


def main(argv):
    C = [r for r in hc.load_records() if r['current'] and r['lat'] is not None]
    c04 = [r for r in C if r['file'].endswith('2004-06-14_mod.txt')]
    dwf = [r for r in C if r['file'].endswith('dwf-20251228-free.txt')]
    neb = [r for r in C if r['file'].endswith('nebenstroeme.txt')]
    raus, melden = [], []
    for r in c04:
        near = [q for q in dwf if abs(q['lat'] - r['lat']) < 0.02 and osm_land.km(r['lat'], r['lon'], q['lat'], q['lon']) <= 1]
        w = woerter(r['name'].split(',')[0])
        tw = [q for q in near if w & woerter(q['name'])]
        if tw:
            q = min(tw, key=lambda q: osm_land.km(r['lat'], r['lon'], q['lat'], q['lon']))
            raus.append((r, q, 'aeltere Fassung derselben NOAA-Station; dwf-free (NOAA 2025) ist besser'))
            continue
        nb = [q for q in neb if abs(q['lat'] - r['lat']) < 0.02 and osm_land.km(r['lat'], r['lon'], q['lat'], q['lon']) <= 1
              and w and w <= woerter(q['name'])]
        if nb:
            raus.append((r, nb[0], 'gleichnamiger NOAA-Nebenstrom aus den aktuellen Tafeln'))
        elif near and r['name'] in GLEICH:
            raus.append((r, min(near, key=lambda q: osm_land.km(r['lat'], r['lon'], q['lat'], q['lon'])), 'aeltere Fassung derselben NOAA-Station (von Hand bestaetigt); dwf-free ist besser'))
        elif near:
            melden.append((r, near[0]))
    for r, q, why in raus:
        print('ARCHIV %-55s | %.2f km %s' % (r['name'][:55], osm_land.km(r['lat'], r['lon'], q['lat'], q['lon']), q['name'][:60]))
    for r, q in melden:
        print('MELDEN %-55s | %.2f km %s' % (r['name'][:55], osm_land.km(r['lat'], r['lon'], q['lat'], q['lon']), q['name'][:60]))
    print(len(raus), 'archivieren,', len(melden), 'melden')
    if '--schreiben' in argv:
        liste = os.path.join(ROOT, 'harmonics/help/us_stroeme_2004_20261021_loeschen.csv')
        with open(liste, 'w', newline='', encoding='utf-8') as fh:
            wr = csv.writer(fh); wr.writerow(['datei', 'name', 'fehler_prozent', 'begruendung'])
            for r, q, why in raus:
                wr.writerow([r['file'], r['name'], '-', '%s (%s, %.2f km). Oliver 21.10.2026' % (why, q['name'], osm_land.km(r['lat'], r['lon'], q['lat'], q['lon']))])
        subprocess.run([sys.executable, os.path.join(ROOT, 'py/saetze_loeschen.py'), liste, '--schreiben'], check=True, cwd=ROOT)


if __name__ == '__main__':
    main(sys.argv[1:])
