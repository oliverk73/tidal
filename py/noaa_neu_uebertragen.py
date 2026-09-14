#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Uebertraegt alle NOAA-Table-2-Saetze neu -- mit dem am Pruefstand belegten Kern.

Grundlage ist py/noaa_pruefstand.py. Dort wurde an 1133 heutigen NOAA-Saetzen
mit amtlicher Wahrheit unter 3 km gemessen (14.09.2026):
  * Buchzonen statt keiner/geografischer Zone            (bestaetigt)
  * Hube im Verhaeltnis Neben-/Bezugsort des Buchs statt
    synthetischer Messung mit Faktor CAL 1.10             M2 1.075 -> 0.989, S2 1.028 -> 0.968
  * Bezugssatz je Buch-Bezugsort am Pruefstand gewaehlt   Port Phillip 36.8 -> 9.1 %, Surabaja 17.3 -> 6.3 %
  * Flachwassertiden des Bezugs behalten/weglassen und
    HW/NW-Ungleichheit (M4) je Gruppe gewaehlt
  gewichteter Median der Kurvenabweichung 5.15 -> 4.49 %.
Das ersetzt die Flickstellen im Bestand (Gruppen-Shifts -48/-55/-60 min, +9 h
Japan, Zonendrehungen, S2-Nachzug, Bezugsort-Neuuebertragungen).

Gruppenregel (harmonics/help/noaa_pruefstand_gruppen.csv):
  gewaehlt  -- bester Bezug/Einstellung, wenn n >= 3 und Gewinn >= 0.5 Punkte
               oder n < 3 und Gewinn >= 2 Punkte gegen den Bau-Bezug
  bau       -- Bezug wie beim Bau, Grundeinstellung (Buchquotient, Buchzone)
  behalten  -- die Gruppe wird am Pruefstand schlechter als der Bestand
Satzregel: geschrieben wird nur, was an der Wahrheit, sonst an einer echten
Reihe, sonst an den unabhaengigen Nachbarn nicht schlechter wird.
Name, Position, Z0, Meridianzeile und alle Vermerke bleiben.

Usage: python3 py/noaa_neu_uebertragen.py              -> harmonics/help/noaa_neu_uebertragen.csv
       python3 py/noaa_neu_uebertragen.py --schreiben  (Zeilen mit entscheidung 'schreiben')
"""
from __future__ import annotations

import collections
import csv
import datetime as dt
import math
import os
import shutil
import statistics
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import noaa_pruefstand as P                                        # noqa: E402
import xtide_modell as X                                           # noqa: E402
from health_check import MERIDIAN, km, load_records                # noqa: E402
from sicher_schreiben import schreiben                             # noqa: E402

ROOT = P.ROOT
HELP = P.HELP
AUS = os.path.join(HELP, 'noaa_neu_uebertragen.csv')
GRUPPEN = os.path.join(HELP, 'noaa_pruefstand_gruppen.csv')
KONST = os.path.join(HELP, 'noaa_neu_uebertragen_konstanten.json')
HEUTE = dt.date.today().strftime('%Y%m%d')
TOL_PCT, TOL_CM = 0.3, 0.3


def gruppenregel():
    out = {}
    for z in csv.DictReader(open(GRUPPEN, encoding='utf-8')):
        n = int(z['n'])
        best = float(z['best_pct'])
        bau = float(z['bau_neu_pct']) if z['bau_neu_pct'] else None
        bestand = float(z['bestand_pct']) if z['bestand_pct'] else None
        gewinn = (bau - best) if bau is not None else 0.0
        if bestand is not None and best > bestand + 0.5:
            regel = 'behalten'
        elif 'Bau' not in z['bezug_weg'] and ((n >= 3 and gewinn >= 0.5) or (n < 3 and gewinn >= 2.0)):
            regel = 'gewaehlt'
        elif 'Bau' in z['bezug_weg']:
            regel = 'gewaehlt' if z['einstellung'] != 'Flach behalten' and n >= 3 else 'bau'
        else:
            regel = 'bau'
        out[(z['band'], z['ref'], z['teilgruppe'])] = dict(regel=regel, bezug=z['bezug'], einstellung=z['einstellung'], n=n)
    return out


def ref_record(recs_ab, beschriftung):
    """'Name [datei]' -> record."""
    name, datei = beschriftung.rsplit(' [', 1)
    datei = datei.rstrip(']')
    for r in recs_ab:
        if r['name'] == name and os.path.basename(r['file']) == datei:
            return r
    return None


def nachbarn_idx(recs_ab):
    lat = np.radians([r['lat'] for r in recs_ab]); lon = np.radians([r['lon'] for r in recs_ab])
    def suche(r, radius=5.0):
        la, lo = math.radians(r['lat']), math.radians(r['lon'])
        a = np.sin((lat - la) / 2) ** 2 + np.cos(la) * np.cos(lat) * np.sin((lon - lo) / 2) ** 2
        d = 2 * 6371 * np.arcsin(np.sqrt(np.minimum(a, 1)))
        return [recs_ab[i] for i in np.where(d <= radius)[0] if P.klasse(recs_ab[i]) is not None]
    return suche


def pegel_rms(pfad, z0, alt, neu):
    import messreihe_qualitaet as M
    import scheitelfit as S
    obs = M.lies(pfad)
    if len(obs) < 3000:
        return None
    t = np.array([o[0] for o in obs])[-20000:]; h = np.array([o[1] for o in obs])[-20000:]
    kopf = X.kopf_lesen(os.path.join(ROOT, 'harmonics/utide/harmonics_utide_tidetables.txt'))
    out = []
    for con in (alt, neu):
        d = h - S.hoehe_und_ableitungen(t, z0, con, kopf)[0]
        out.append(float(np.sqrt(np.mean((d - d.mean()) ** 2))) * 100)
    return out


def pruefen():
    recs = [r for r in load_records() if r['lat'] is not None]
    recs_ab = [r for r in recs if '/noaa/' not in r['file'] and 'current' not in r['file'].lower()]
    F = [f for f in P.faelle(recs, alle=True) if f['heute'] is not None]
    regel = gruppenregel()
    zeilen_buch, _z, _r = P.buch()
    nachbarn = nachbarn_idx(recs_ab)
    bau_bezug = P.bezugssaetze(recs, zeilen_buch)
    import noaa_s2_nachziehen as N
    pegel = N.pegelpfade()
    zeilen = []
    for i, f in enumerate(F):
        r = f['heute']
        band, s = f['band'], f['s']
        g = regel.get((band, s['ref'], P.teilgruppe(f)))
        z0_alt, alt = P.satz(r)
        z = dict(datei=os.path.basename(r['file']), name=r['name'], no=f"{band}-{f['no']}", buch_bezug=s['ref'],
                 regel=g['regel'] if g else 'bau (ohne Pruefstand)', bezug='', einstellung='',
                 wahr_alt_pct='', wahr_neu_pct='', pegel_alt_cm='', pegel_neu_cm='',
                 nachbar_alt_pct='', nachbar_neu_pct='', m2_amp_alt='', m2_amp_neu='', beleg='', entscheidung='')
        if g and g['regel'] == 'behalten':
            z['entscheidung'] = 'behalten (Gruppe am Pruefstand schlechter)'
            zeilen.append(z); continue
        if g and g['regel'] == 'gewaehlt':
            ref = ref_record(recs_ab, g['bezug'])
            v = {**P.GRUNDV, **P.EINSTELLUNGEN[g['einstellung']]}
            z['einstellung'] = g['einstellung']
        else:
            ref = f['ref'] if f['ref_weg'] == 'wie beim Bau' else (bau_bezug.get((band, s['ref']), (None,))[0] or f['ref'])
            v = dict(P.GRUNDV)
            z['einstellung'] = 'Flach behalten'
        if ref is None:
            z['entscheidung'] = 'behalten (kein Bezugssatz)'
            zeilen.append(z); continue
        z['bezug'] = f"{ref['name']} [{os.path.basename(ref['file'])}]"
        neu = P.uebertragen(s, P.satz(ref)[1], ref['name'], f['zn'], f['zb'], v, f.get('refbuch'))
        if not neu or 'M2' not in neu:
            z['entscheidung'] = 'behalten (Uebertragung nicht moeglich)'
            zeilen.append(z); continue
        z['m2_amp_alt'] = round(alt.get('M2', (0, 0))[0], 3); z['m2_amp_neu'] = round(neu['M2'][0], 3)
        belege = []
        if f.get('wahr') is not None:
            w = P.satz(f['wahr'])[1]
            a, b = P.messen(alt, w)['kurve_pct'], P.messen(neu, w)['kurve_pct']
            z['wahr_alt_pct'], z['wahr_neu_pct'] = round(a, 2), round(b, 2)
            belege.append(('Wahrheit', b <= a + TOL_PCT))
        pg = pegel.get((z['datei'], r['name']))
        if pg:
            res = pegel_rms(pg[0], z0_alt, alt, neu)
            if res:
                z['pegel_alt_cm'], z['pegel_neu_cm'] = round(res[0], 1), round(res[1], 1)
                belege.append(('Pegel', res[1] <= res[0] + TOL_CM))
        if not belege:
            nb = [q for q in nachbarn(r) if q is not f.get('wahr')]
            if nb:
                aa = [P.messen(alt, P.satz(q)[1])['kurve_pct'] for q in nb[:5]]
                bb = [P.messen(neu, P.satz(q)[1])['kurve_pct'] for q in nb[:5]]
                z['nachbar_alt_pct'], z['nachbar_neu_pct'] = round(statistics.median(aa), 2), round(statistics.median(bb), 2)
                belege.append(('Nachbarn', statistics.median(bb) <= statistics.median(aa) + TOL_PCT))
        z['_f'] = f
        z['beleg'] = ', '.join(f"{k} {'ok' if ok else 'schlechter'}" for k, ok in belege)
        if not belege:
            z['entscheidung'] = 'schreiben (ohne Einzelbeleg)'
        elif belege[0][1]:
            z['entscheidung'] = 'schreiben'
        else:
            z['entscheidung'] = 'behalten (Beleg schlechter)'
        z['_con'] = neu
        zeilen.append(z)
        if (i + 1) % 200 == 0:
            print(f'  {i + 1}/{len(F)}', flush=True)
    # Saetze ohne eigenen Beleg: Sätze derselben Buchgruppe mit Wahrheit im Umkreis von 300 km
    mit = [z for z in zeilen if z.get('wahr_alt_pct') not in ('', None) and '_f' in z]
    for z in zeilen:
        if z['entscheidung'] != 'schreiben (ohne Einzelbeleg)':
            continue
        f = z['_f']
        lokal = [y for y in mit if y['buch_bezug'] == z['buch_bezug'] and y['no'].split('-')[0] == z['no'].split('-')[0]
                 and km(y['_f']['heute'], f['heute']) <= 300.0]
        if len(lokal) >= 2:
            d = statistics.median(float(y['wahr_neu_pct']) - float(y['wahr_alt_pct']) for y in lokal)
            z['beleg'] = f'Gruppe lokal n={len(lokal)} {d:+.2f} Punkte'
            z['entscheidung'] = 'schreiben (Gruppenbeleg lokal)' if d <= 0.0 else 'behalten (Gruppe lokal schlechter)'
        else:
            z['entscheidung'] = 'offen (ohne Beleg)'
    import json
    json.dump({f"{z['datei']}|{z['name']}": {c: [round(a, 5), round(g, 3)] for c, (a, g) in z['_con'].items()}
               for z in zeilen if '_con' in z},
              open(KONST, 'w', encoding='utf-8'))
    with open(AUS, 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=[k for k in zeilen[0] if not k.startswith('_')])
        w.writeheader()
        w.writerows({k: v for k, v in z.items() if not k.startswith('_')} for z in zeilen)
    zaehl = collections.Counter(z['entscheidung'] for z in zeilen)
    print('->', os.path.relpath(AUS, ROOT), len(zeilen), 'Saetze')
    for k, n in zaehl.most_common():
        print(f'   {k:50} {n:5d}')
    for art in ('wahr', 'pegel', 'nachbar'):
        paare = [(float(z[f'{art}_alt_' + ('cm' if art == 'pegel' else 'pct')]), float(z[f'{art}_neu_' + ('cm' if art == 'pegel' else 'pct')]))
                 for z in zeilen if z.get(f'{art}_alt_' + ('cm' if art == 'pegel' else 'pct')) not in ('', None)]
        if paare:
            print(f"   {art:8} n={len(paare):5d}  Median {statistics.median(p[0] for p in paare):.2f} -> {statistics.median(p[1] for p in paare):.2f}  "
                  f"besser {sum(1 for a, b in paare if b < a - 0.1)}  schlechter {sum(1 for a, b in paare if b > a + 0.1)}")
    return zeilen


def anwenden():
    """Schreibt die Zeilen mit entscheidung 'schreiben...' in die NOAA-Dateien."""
    import json
    konst = json.load(open(KONST, encoding='utf-8'))
    liste = [z for z in csv.DictReader(open(AUS, encoding='utf-8')) if z['entscheidung'].startswith('schreiben')]
    nach = collections.defaultdict(list)
    for z in liste:
        nach[z['datei']].append(z)
    for datei, zs in nach.items():
        pfad = os.path.join(ROOT, 'harmonics/noaa', datei)
        namen, speeds, _a, _f = X.kopf_lesen(pfad)
        lines = open(pfad, encoding='iso-8859-1').read().split('\n')
        index = collections.defaultdict(list)
        for k in range(len(lines) - 1):
            if lines[k] and not lines[k].startswith('#') and MERIDIAN.match(lines[k + 1]):
                index[lines[k]].append(k)
        n = 0
        for z in sorted(zs, key=lambda z: -(index.get(z['name']) or [0])[0]):
            ks = index.get(z['name'], [])
            con = konst.get(f"{datei}|{z['name']}")
            if len(ks) != 1 or not con:
                print(f'  uebersprungen ({len(ks)} Treffer): {z["name"]}')
                continue
            k = ks[0]
            mer = lines[k + 1].split()[0]
            vz = -1.0 if mer.startswith('-') else 1.0
            hh, mm = mer.lstrip('+-').split(':')
            mer_h = vz * (int(hh) + int(mm) / 60.0)
            einheit = lines[k + 2].split()[1] if len(lines[k + 2].split()) > 1 else 'meters'
            sk = 1 / 0.3048 if einheit.startswith('f') else 1.0
            j = k + 3
            ende = j
            while ende < len(lines) and lines[ende] and not lines[ende].startswith('#') \
                    and not (ende + 1 < len(lines) and MERIDIAN.match(lines[ende + 1])):
                ende += 1
            neu = []
            for c in namen:
                if c in con and con[c][0] >= 0.00005:
                    a, g = con[c]
                    kap = (g + speeds[c] * mer_h) % 360.0          # Greenwich -> Meridian des Satzes
                    neu.append(f'{c:<16}{a * sk:.4f}  {kap:.2f}')
                else:
                    neu.append('x 0 0')
            if ende - j != len(namen):
                print(f'  Konstituentenzahl passt nicht ({ende - j} statt {len(namen)}): {z["name"]}')
                continue
            lines[j:ende] = neu
            beleg = z['beleg'] or 'ohne'
            lines[k:k] = [f"# note: {HEUTE} neu uebertragen (py/noaa_neu_uebertragen.py): Bezug {z['bezug'][:60]},",
                          f"# note: {z['einstellung']}, Buchzonen, Hube im Buchverhaeltnis; Beleg: {beleg[:50]}."]
            n += 1
        shutil.copy2(pfad, os.path.join(ROOT, 'harmonics/backup', f'{datei}.vor_neuuebertragung_{HEUTE}'))
        schreiben(pfad, '\n'.join(lines))
        print(f'  {datei}: {n} Saetze neu uebertragen')


if __name__ == '__main__':
    if '--schreiben' in sys.argv:
        anwenden()
    else:
        pruefen()
