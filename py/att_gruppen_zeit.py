#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ATT-Nebenhaefen gruppenweise auf Zeitfehler pruefen (Oliver 11.11.2026: "Ja").

Anlass: Norwegen (py/kartverket_pruefen.py) -- die NP202-Nebenhaefen unter Narvik/Bodoe lagen gruppenweise 15-25 min
zu spaet (Buch-Zeitdifferenzen). py/zeit_pruefung.py prueft einzeln ab 20 min + Umweg und sah das nicht.

Je ATT-Nebenhafen S der naechste Vergleichssatz M (Messfits, TICON, amtliche Tafelfits/Konstanten) bis MAX_KM, beide M2 >= 0,1 m:
    e = (S - FES an S) - (M - FES an M)   [M2-Phase in Minuten; positiv = S zu spaet]
FES nimmt den echten Unterschied zwischen den Orten heraus. Gruppe = Bezugshafen aus der Notiz ("(att N)",
"Bezugshafen N") bzw. "Buchkonstanten". Mass 2 (alle Saetze): Versatz gegen FES minus oertlicher FES-Fehler (Median der Vergleichssaetze bis 100 km).
Meldung: Gruppe mit >= 3 Nachbarpaaren oder >= 4 FES-Werten und |Median| >= 10 min.
Eichung: die am 11.11. archivierten Norwegen-Saetze (backup/geloescht) laufen als Gruppe "NO-Archiv" mit.
Schreibt nur harmonics/help/att_gruppen_zeit.csv.

Usage: venv/bin/python py/att_gruppen_zeit.py
"""
import cmath
import collections
import csv
import math
import os
import re
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fes_kuestentyp as F                                         # noqa: E402
import health_check as H                                           # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAX_KM = 15.0
SP_M2 = 28.9841042
ARCHIV = 'harmonics/backup/geloescht/harmonics_att_np202_secondary.txt'
AUS = os.path.join(ROOT, 'harmonics/help/att_gruppen_zeit.csv')


REF_DATEIEN = ('utide_observations', '/ticon/', 'utide_tidetables', 'bsh_germany', 'dwf-20251228-free', 'big_srgi',
               'pushidrosal_tables', 'puertos_spain')


def vadahub_namen():
    T = open(os.path.join(ROOT, 'harmonics/utide/harmonics_utide_tidetables.txt'), encoding='iso-8859-1').read().split('\n')
    out = set()
    for i, z in enumerate(T):
        if z.startswith('# source: Korean sea-area-use'):
            j = i
            while T[j].startswith('#'):
                j += 1
            out.add(T[j])
    return out


def gruppe(pfad, zeile):
    T = open(os.path.join(ROOT, pfad), encoding='iso-8859-1').read().split('\n')
    k = zeile - 2
    kopf = []
    while k >= 0 and T[k].startswith('#') and T[k].strip() != '#':
        kopf.append(T[k])
        k -= 1
    text = ' '.join(kopf)
    m = re.search(r'Transfer von ([^(]+?) \(att (\w+)\)', text)
    if m:
        return 'att %s %s' % (m.group(2), m.group(1).strip())
    m = re.search(r'Bezugshafen (\d+)', text)
    if m:
        return 'Bezugshafen %s' % m.group(1)
    return 'Buchkonstanten'


def fes_min(r):
    z, f = r['z'].get('M2'), r['fes_rec']['z']['M2']
    if not z or abs(f) < 0.05 or abs(z) < 0.1:
        return None
    return math.degrees(cmath.phase(z / f)) / SP_M2 * 60


def main(argv):
    alt = H.active_files
    H.active_files = lambda: alt() + [ARCHIV]
    R = [r for r in H.load_records() if not r['current'] and r['lat'] is not None]
    H.active_files = alt
    weg = {z['name'] for z in csv.DictReader(open(os.path.join(ROOT, 'harmonics/help/norwegen_att_20261111_loeschen.csv'), encoding='utf-8'))}
    att = [r for r in R if '/att/' in r['file'] and 'secondary' in r['file'] and 'current' not in r['file']]
    att += [r for r in R if r['file'] == ARCHIV and r['name'] in weg]
    # Vergleich: Messfits und amtliche Konstanten/Tafelfits; nicht ATT, FES, Classic-1997/2004, NOAA-Buchuebertragungen,
    # nicht die vadahub-Gutachtensaetze
    vh = vadahub_namen()
    ref = [r for r in R if any(k in r['file'] for k in REF_DATEIEN) and r['name'] not in vh and r['file'] != ARCHIV]
    F.fes_dazu(att + ref)
    paare = []
    rf = [(m, fes_min(m)) for m in ref]
    rf = [(m, v) for m, v in rf if v is not None]
    for s in att:
        fs = fes_min(s)
        if fs is None:
            continue
        # Mass 2: gegen FES, bereinigt um den oertlichen FES-Fehler (Median der Vergleichssaetze bis 100 km)
        um = [v for m, v in rf if H.km(s, m) <= 100 and m['name'] != s['name']]
        e2 = -(fs - float(np.median(um))) if len(um) >= 2 else None
        if e2 is not None:
            e2 = (e2 + 6 * 60) % (12.42 * 60) - 6 * 60
        nb = sorted(((H.km(s, m), m) for m in ref), key=lambda x: x[0])
        nb = [(d, m) for d, m in nb[:6] if d <= MAX_KM and m['name'] != s['name'] and fes_min(m) is not None]
        if nb:
            d, m = nb[0]
            e = -(fs - fes_min(m))                                    # phase(z/f) = -(g_S - g_FES): spaeter = negativ
            e = (e + 6 * 60) % (12.42 * 60) - 6 * 60                 # auf +-6 h falten
        elif e2 is None:
            continue
        g = 'NO-Archiv ' + gruppe(s['file'], s['line']) if s['file'] == ARCHIV else gruppe(s['file'], s['line'])
        paare.append(dict(gruppe=g, datei=os.path.basename(s['file']), name=s['name'],
                          mess=m['name'] if nb else '', km='%.1f' % d if nb else '', e_min='%.0f' % e if nb else '',
                          hub_m2='%.2f' % (abs(s['z']['M2']) / abs(m['z']['M2'])) if nb else '',
                          e_fes_min='%.0f' % e2 if e2 is not None else '', n_umkreis=len(um)))
    G = collections.defaultdict(list)
    for p in paare:
        G[(p['datei'] if not p['gruppe'].startswith('NO-') else 'Archiv', p['gruppe'])].append(p)
    print('%d Paare in %d Gruppen\n' % (len(paare), len(G)))
    zeilen = []
    def med(ps, k):
        v = [float(p[k]) for p in ps if p[k] != '']
        return (float(np.median(v)), len(v)) if v else (float('nan'), 0)
    for (datei, g), ps in sorted(G.items(), key=lambda x: -abs(np.nan_to_num(med(x[1], 'e_fes_min')[0]))):
        m1, n1 = med(ps, 'e_min')
        m2, n2 = med(ps, 'e_fes_min')
        flag = (n1 >= 3 and abs(m1) >= 10) or (n2 >= 4 and abs(m2) >= 10)
        if n1 >= 3 or n2 >= 4:
            print('%s %-36s %-40s Nachbar n=%2d %+4.0f | FES n=%3d %+4.0f min' % (
                '!!' if flag else '  ', datei[:36], g[:40], n1, m1, n2, m2))
        for p in ps:
            p.update(gruppe_median_nachbar='%.0f' % m1, gruppe_median_fes='%.0f' % m2, meldung='JA' if flag else '')
            zeilen.append(p)
    with open(AUS, 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=list(zeilen[0]))
        w.writeheader()
        w.writerows(zeilen)
    print('->', os.path.relpath(AUS, ROOT))


if __name__ == '__main__':
    main(sys.argv[1:])
