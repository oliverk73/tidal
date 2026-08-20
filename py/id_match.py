#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Kennungsabgleich: welche Datensaetze beschreiben denselben Pegel?

Verknuepft ueber global gueltige Stationskennungen (PSMSL, UHSLC, GLOSS,
SSC, IOC, SONEL, CHS, SHOM, BOM, LINZ, JMA, NOAA CO-OPS ...). Quellen-interne
Tafelnummern wie noaa_number oder att_number sind dafuer ungeeignet -- dieselbe
Nummer bedeutet in verschiedenen Werken verschiedene Stationen -- und werden
nur zur Suche nach Dubletten innerhalb derselben Datei benutzt.

Ausgabe: Bericht auf stdout, Gruppen als CSV mit --csv <datei>.

Usage: python3 py/id_match.py [--csv <datei>] [--min-conflict-km 3]
"""
from __future__ import annotations

import collections
import csv
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from health_check import load_records, km, curve_diff   # noqa: E402

# Kennungen, die weltweit eindeutig eine Messstelle bezeichnen
GLOBAL_TAGS = [
    'psmsl_id', 'uhslc_id', 'gloss_id', 'ssc_id', 'ioc_code', 'ptwc_code',
    'sonel_tg_id', 'chs_id', 'shom_code', 'bom_id', 'linz_station_id',
    'jma_code', 'nz_chart_id', 'nmdis_site', 'noaa_station_id',
    'station_id_context',
]
# nur innerhalb derselben Datei aussagekraeftig
LOCAL_TAGS = ['noaa_number', 'att_number', 'rtn_pdf']
# reine Behoerdenkuerzel, die als Schluessel nichts leisten
NOT_A_KEY = {'nos', 'wsv', 'rws', 'bsh', 'meds', 'pol', 'chs', 'bom', 'jma',
             'shom', 'linz', 'ioc', 'psmsl', 'uhslc', 'sonel', 'noaa'}

TAGLINE = re.compile(r'#\s*([a-zA-Z][a-zA-Z0-9_]{2,30})\s*:\s*(\S.*)$')
MERIDIAN = re.compile(r'^[+-]\d\d:\d\d')
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read_tags(recs):
    """Liest die Kopfzeilen erneut und haengt sie an die Datensaetze."""
    per_file = collections.defaultdict(list)
    for i, r in enumerate(recs):
        per_file[r['file']].append(i)
    for path, idx in per_file.items():
        lines = open(os.path.join(ROOT, path), encoding='iso-8859-1').read().split('\n')
        it = iter(sorted(idx, key=lambda i: recs[i]['line']))
        cur = next(it, None)
        head = {}
        for k, line in enumerate(lines):
            if line.startswith('#'):
                m = TAGLINE.match(line)
                if m:
                    head.setdefault(m.group(1), []).append(m.group(2).strip())
            elif (line and k + 1 < len(lines) and MERIDIAN.match(lines[k + 1])):
                if cur is not None and recs[cur]['line'] == k + 1:
                    recs[cur]['tags'] = head
                    cur = next(it, None)
                head = {}
            else:
                head = {}
    for r in recs:
        r.setdefault('tags', {})


def keys_of(rec):
    out = set()
    for tag in GLOBAL_TAGS:
        for raw in rec['tags'].get(tag, []):
            for tok in re.split(r'[,;]\s*|\s{2,}', raw):
                tok = tok.strip().lower()
                if not tok or len(tok) < 2 or tok in NOT_A_KEY:
                    continue
                if tag == 'station_id_context' and not (
                        re.search(r'\d', tok) and re.search(r'[-_]', tok)):
                    continue
                out.add((tag, tok))
    return out


def main():
    recs = load_records()
    read_tags(recs)
    tide = [r for r in recs if not r['current']]

    key_map = collections.defaultdict(list)
    tagged = 0
    for i, r in enumerate(tide):
        ks = keys_of(r)
        r['keys'] = ks
        if ks:
            tagged += 1
        for k in ks:
            key_map[k].append(i)

    print(f'{len(tide)} Pegel, davon {tagged} mit mindestens einer globalen '
          f'Kennung ({100*tagged/len(tide):.0f} %)')
    print(f'{len(key_map)} verschiedene Kennungen\n')

    # Gruppen ohne Verkettung: je Kennung
    multi = {k: v for k, v in key_map.items() if len(v) > 1}
    print(f'Kennungen, die mehr als einen Datensatz tragen: {len(multi)}')

    # Verkettung ueber gemeinsame Kennungen (Union-Find)
    par = list(range(len(tide)))

    def find(a):
        while par[a] != a:
            par[a] = par[par[a]]
            a = par[a]
        return a

    for _k, idx in multi.items():
        for j in idx[1:]:
            a, b = find(idx[0]), find(j)
            if a != b:
                par[a] = b
    groups = collections.defaultdict(list)
    for i in range(len(tide)):
        groups[find(i)].append(i)
    groups = {g: v for g, v in groups.items() if len(v) > 1}

    sizes = collections.Counter(len(v) for v in groups.values())
    n_in = sum(len(v) for v in groups.values())
    print(f'{len(groups)} Pegel-Gruppen mit zusammen {n_in} Datensaetzen')
    print(f'Einsparpotential bei "ein Pegel = ein Datensatz": '
          f'{n_in - len(groups)} Datensaetze\n')
    print('Gruppengroesse:  ' + '  '.join(f'{s}x{c}' for s, c in sorted(sizes.items())))

    conflict_km = 3.0
    conflict_rel = 0.10
    rows = []
    far, differ = [], []
    for _g, idx in groups.items():
        with_pos = [i for i in idx if tide[i]['lat'] is not None]
        dmax = rmax = 0.0
        pair_far = pair_dif = None
        for a in range(len(with_pos)):
            for b in range(a + 1, len(with_pos)):
                r1, r2 = tide[with_pos[a]], tide[with_pos[b]]
                d = km(r1, r2)
                _abs, rel = curve_diff(r1, r2)
                if d > dmax:
                    dmax, pair_far = d, (r1, r2)
                if rel > rmax:
                    rmax, pair_dif = rel, (r1, r2)
        names = '; '.join(sorted({tide[i]['name'] for i in idx}))
        files = '; '.join(sorted({tide[i]['file'].split('/')[-1] for i in idx}))
        rows.append([len(idx), f'{dmax:.2f}', f'{rmax:.3f}', names, files])
        if dmax > conflict_km:
            far.append((dmax, pair_far))
        if rmax > conflict_rel:
            differ.append((rmax, pair_dif))

    far.sort(reverse=True, key=lambda t: t[0])
    differ.sort(reverse=True, key=lambda t: t[0])
    print(f'\nGruppen mit Positionskonflikt (> {conflict_km:.0f} km): {len(far)}')
    for d, (r1, r2) in far[:15]:
        print(f'   {d:8.1f} km  {r1["name"][:32]:32} {r1["lat"]:8.3f} {r1["lon"]:9.3f} '
              f'[{r1["file"].split("/")[-1][:22]:22}]')
        print(f'   {"":11}  {r2["name"][:32]:32} {r2["lat"]:8.3f} {r2["lon"]:9.3f} '
              f'[{r2["file"].split("/")[-1][:22]}]')
    print(f'\nGruppen mit Datenkonflikt (Kurven > {conflict_rel*100:.0f} %): {len(differ)}')
    for rel, (r1, r2) in differ[:15]:
        print(f'   {rel*100:6.0f} %  {r1["name"][:32]:32} [{r1["file"].split("/")[-1][:24]:24}]')
        print(f'   {"":8}  {r2["name"][:32]:32} [{r2["file"].split("/")[-1][:24]}]')

    # Dubletten innerhalb derselben Datei ueber quellen-interne Nummern
    # Tafelnummern gelten nur je Band. harmonics_noaa_amtt.txt etwa fuehrt
    # East- und West-Coast-Tide-Tables zusammen, beide mit eigener Zaehlung;
    # den Band verraet das Praefix in noaa_uid (ectt-/wctt-).
    local = collections.defaultdict(list)
    for i, r in enumerate(tide):
        uid = (r['tags'].get('noaa_uid') or [''])[0]
        vol = uid.split('-')[0] if '-' in uid else ''
        for tag in LOCAL_TAGS:
            for v in r['tags'].get(tag, []):
                local[(r['file'], vol, tag, v.strip())].append(i)
    dup_local = {k: v for k, v in local.items() if len(v) > 1}
    print(f'\nDubletten innerhalb derselben Datei (gleiche Tafelnummer): {len(dup_local)}')
    for (f, _vol, tag, v), idx in sorted(dup_local.items())[:10]:
        print(f'   {f.split("/")[-1]}  {tag} {v}: '
              + ' | '.join(tide[i]['name'][:30] for i in idx[:3]))

    if '--csv' in sys.argv:
        out = sys.argv[sys.argv.index('--csv') + 1]
        with open(out, 'w', newline='', encoding='utf-8') as fh:
            w = csv.writer(fh)
            w.writerow(['n_records', 'max_km', 'max_curve_rel', 'names', 'files'])
            w.writerows(sorted(rows, key=lambda r: -float(r[1])))
        print(f'\nCSV -> {out}')


if __name__ == '__main__':
    main()
