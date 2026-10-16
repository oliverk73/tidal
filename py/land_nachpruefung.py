#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Nachpruefung eines Landes auf dem heutigen Stand: ganze Kurve gegen FES, Dubletten, Ausreisser.

Oliver 16.10.2026: "Kannst Du alle Laender (vorzugsweise die von mir bereits editierten)
abarbeiten?" Nach seinen Positions- und Namenskorrekturen koennen neue Dubletten entstanden sein
(zwei Saetze jetzt am selben Ort) und alte Bewertungen veraltet sein.

Je Satz (keine Stroeme): 60 Tage ganze Kurve gegen FES2022 an der eigenen Position
(RMS ohne Mittel, Hub 92/8-Perzentil, Median und 90-%-Wert der Scheitelzeit-Abweichung).

Dubletten (Regeln aus Olivers Vorgaben, Memory "eigene-pegel-keine-duplikate", "zwillinge-vor-fes"):
  - Paar bis 0.5 km, oder bis 2 km bei gleichem Namenskern, verschiedene Dateien.
  - Messung (utide/ticon/classic-Messsatz) gegen Uebertragung (noaa/att-Nebenhafen): Messung bleibt,
    ausser die Uebertragung liegt mindestens 2 cm naeher an FES.
  - gleichrangig: der FES-naehere bleibt; unter 1 cm Unterschied entscheidet der Rang.
  - identische Tafel (Kurvenabweichung < 3 %): die rangniedere Fassung geht.
  - FES gilt nur an offener Kueste (fes_kuestentyp): in Buchten/Fluessen/Lagunen (Hub weicht > 25 %
    von FES ab bei BEIDEN Saetzen) wird nichts entschieden.
Ausreisser (nur gemeldet): offene Kueste, |Zeit-Median| > 30 min oder Hub > 25 % daneben.

Usage: venv/bin/python py/land_nachpruefung.py <Land> [<Land> ...] [--filter python-ausdruck]
       -> harmonics/help/nachpruefung_<land>_<datum>.json/.csv (Loeschliste-Vorschlag) + Konsole
"""
import csv
import datetime as dt
import glob
import json
import math
import os
import re
import sys

import netCDF4 as nc
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dubletten_kurven as D                                       # noqa: E402
import xtide_modell as X                                           # noqa: E402
from fes_ersatz_inseln import sample, FES_DIR, ROOT                # noqa: E402

CS = ('M2', 'S2', 'N2', 'K2', 'K1', 'O1', 'P1', 'Q1', 'M4', 'MS4', 'MN4', '2N2', 'NU2', 'L2', 'MU2')
RANG = [('harmonics/utide/harmonics_fes2022', 6), ('harmonics/utide/', 1), ('harmonics/ticon/', 2),
        ('harmonics/classic/', 3), ('harmonics/att/', 4), ('harmonics/noaa/', 5)]
GATTUNG = {'bay', 'point', 'island', 'harbor', 'harbour', 'port', 'river', 'cape', 'entrance', 'bukhta', 'zaliv',
           'mys', 'ostrov', 'jima', 'shima', 'ko', 'wan', 'minato', 'hang', 'do', 'pulau', 'teluk', 'tanjung'}


def rang(f):
    return next((v for k, v in RANG if f.startswith(k)), 9)


def messung(s):
    """Grob: utide-Fits auf Beobachtungen, TICON, klassische Analysen = Messung; Buchuebertragungen nicht."""
    f = s['file']
    if '/noaa/' in f or 'fes2022' in f:
        return False
    if '/att/' in f:
        return 'secondary' not in f            # ATT Part III der Haupthaefen ist eine Analyse
    if 'tidetables' in f:
        return False                           # Fit auf Vorhersagetafeln (Memory tafelfit-misst-die-tafel)
    return True


def kern(n):
    for w in re.findall(r"[A-Za-z']+", n.split(',')[0]):
        if len(w) >= 4 and w.lower() not in GATTUNG:
            return w.lower()
    return n.split(',')[0].lower()


def km(a, b):
    return math.hypot((a['lat'] - b['lat']) * 111.2, (a['lon'] - b['lon']) * 111.2 * math.cos(math.radians(a['lat'])))


def ext(h):
    i = np.where((h[1:-1] > h[:-2]) & (h[1:-1] > h[2:]))[0] + 1
    j = np.where((h[1:-1] < h[:-2]) & (h[1:-1] < h[2:]))[0] + 1
    return i, j


def hub(h):
    i, j = ext(h)
    return np.percentile(h[i], 92) - np.percentile(h[j], 8)


def bewerten(saetze):
    namen, speeds, arg, fak = X.kopf_lesen('harmonics/noaa/harmonics_noaa_cptt.txt')
    t = np.arange(0, 60 * 86400, 600) + X.jahresbeginn(2026)
    DS = {c: nc.Dataset(os.path.join(FES_DIR, c.lower() + '_fes2022.nc')) for c in CS
          if os.path.exists(os.path.join(FES_DIR, c.lower() + '_fes2022.nc'))}
    for s in saetze:
        F = {c: sample(d, s['lat'], s['lon']) for c, d in DS.items() if c in speeds}
        F = {c: v for c, v in F.items() if v[0] and np.isfinite(v[0])}
        _, w, _, m = X.satz_lesen(s['file'], s['name'])
        C = X.kurve(t, 0, {c: (a, g - speeds[c] * m) for c, (a, g) in w.items() if c in speeds}, namen, speeds, arg, fak)
        s['_kurve'] = C
        s['hub'] = float(hub(C))
        if not F:
            continue
        fes = X.kurve(t, 0, F, namen, speeds, arg, fak)
        dd = []
        for x, y in zip(ext(fes), ext(C)):
            x, y = t[x], t[y]
            dd += [(y[np.argmin(abs(y - v))] - v) / 60 for v in x if len(y) and abs(y - v).min() < 4 * 3600]
        s.update(fhub=float(hub(fes)), rms=float(np.sqrt(np.mean(((C - C.mean()) - (fes - fes.mean())) ** 2))),
                 dtm=float(np.median(dd)) if dd else 99.0, dt90=float(np.percentile(np.abs(dd), 90)) if dd else 999.0)


def main(argv):
    filt = argv[argv.index('--filter') + 1] if '--filter' in argv else None
    laender = [a for i, a in enumerate(argv) if not a.startswith('--') and (i == 0 or argv[i - 1] != '--filter')]
    fs = sorted(os.path.relpath(p, ROOT) for p in glob.glob(ROOT + '/harmonics/*/*.txt')
                if not re.search(r'/(backup|help)/|classic_original', p))
    os.chdir(ROOT)
    heute = dt.date.today().strftime('%Y%m%d')
    for land in laender:
        S = [s for s in D.saetze(land, fs) if not s['name'].endswith('Current')]
        if filt:
            S = [s for s in S if eval(filt, {}, {'s': s, 'r': s})]
        print('==', land, len(S), 'Saetze', flush=True)
        bewerten(S)
        paare, ausreisser, raus = [], [], []
        for i, a in enumerate(S):
            for b in S[i + 1:]:
                if a['file'] == b['file']:
                    continue
                d = km(a, b)
                if d > 2.0 or (d > 0.5 and kern(a['name']) != kern(b['name'])):
                    continue
                if 'rms' not in a or 'rms' not in b:
                    continue
                abw = float(np.sqrt(np.mean((a['_kurve'] - a['_kurve'].mean() - b['_kurve'] + b['_kurve'].mean()) ** 2))
                            / max(np.std(a['_kurve']), 1e-6))
                bucht = abs(a['hub'] / a['fhub'] - 1) > 0.25 and abs(b['hub'] / b['fhub'] - 1) > 0.25
                ra, rb = rang(a['file']), rang(b['file'])
                ma, mb = messung(a), messung(b)
                if abw < 0.03:
                    gut, weg = (a, b) if ra <= rb else (b, a)
                    grund = 'identische Tafel (%.0f %%), Rang' % (100 * abw)
                elif bucht:
                    paare.append((a, b, d, abw, 'Bucht/Fluss: FES kein Schiedsrichter, nichts entschieden'))
                    continue
                elif ma != mb:
                    mess, ueb = (a, b) if ma else (b, a)
                    if ueb['rms'] <= mess['rms'] - 0.02:
                        gut, weg, grund = ueb, mess, 'Uebertragung %.1f cm naeher an FES als die Messung' % (100 * (mess['rms'] - ueb['rms']))
                    else:
                        gut, weg, grund = mess, ueb, 'Messung vor Uebertragung (%.1f gegen %.1f cm)' % (100 * mess['rms'], 100 * ueb['rms'])
                else:
                    if abs(a['rms'] - b['rms']) < 0.01:
                        gut, weg = (a, b) if ra <= rb else (b, a)
                        grund = 'gleich gut (%.1f/%.1f cm), Rang' % (100 * gut['rms'], 100 * weg['rms'])
                    else:
                        gut, weg = (a, b) if a['rms'] < b['rms'] else (b, a)
                        grund = 'FES naeher (%.1f gegen %.1f cm)' % (100 * gut['rms'], 100 * weg['rms'])
                paare.append((gut, weg, d, abw, grund))
        weg_ids = set()
        for gut, weg, d, abw, grund in paare:
            if grund.startswith('Bucht'):
                continue
            k = (weg['file'], weg['name'])
            if k in weg_ids or (gut['file'], gut['name']) in weg_ids:
                continue
            weg_ids.add(k)
            raus.append(dict(datei=weg['file'], name=weg['name'], fehler_prozent=round(100 * (weg['hub'] / weg['fhub'] - 1)),
                             begruendung='Dublette zu "%s" (%s) %.1f km: %s; Kurvenabweichung %.0f %%. Oliver 16.10.2026' % (
                                 gut['name'], os.path.basename(gut['file']), d, grund, 100 * abw)))
        t = np.arange(0, 60 * 86400, 600)
        for s in S:
            if 'rms' not in s or (s['file'], s['name']) in weg_ids:
                continue
            h = s['hub'] / s['fhub'] - 1
            if abs(h) > 0.25 or abs(s['dtm']) <= 30:
                continue
            # Zwillinge vor FES: Zeitversatz gegen Nachbarn bis 30 km (andere Orte, nicht weg)
            nb = []
            for x in S:
                if x is s or (x['file'], x['name']) in weg_ids or km(s, x) > 30 or km(s, x) < 0.3:
                    continue
                dd = []
                for p_, q_ in zip(ext(x['_kurve']), ext(s['_kurve'])):
                    p_, q_ = t[p_], t[q_]
                    dd += [(q_[np.argmin(abs(q_ - v))] - v) / 60 for v in p_ if len(q_) and abs(q_ - v).min() < 4 * 3600]
                if dd:
                    nb.append((km(s, x), float(np.median(dd)), x['name']))
            nb.sort()
            nmed = float(np.median([d_ for _, d_, _ in nb[:4]])) if nb else None
            if nmed is not None and abs(nmed) < 20:
                continue                                  # Nachbarn bestaetigen den Satz: FES liegt hier daneben
            ausreisser.append((s, 'Zeit %+.0f min gegen FES (90 %% bis %.0f), Hub %+.0f %%; Nachbarn: %s' % (
                s['dtm'], s['dt90'], 100 * h, '%+.0f min (%s)' % (nmed, '; '.join('%s %.0f km %+.0f' % (n_.split(',')[0], k_, d_) for k_, d_, n_ in nb[:3]))
                if nb else 'keine bis 30 km')))
        stem = 'harmonics/help/nachpruefung_%s_%s' % (re.sub(r'\W+', '_', land.lower()), heute)
        with open(stem + '_loeschen.csv', 'w', newline='', encoding='utf-8') as fh:
            w = csv.DictWriter(fh, fieldnames=['datei', 'name', 'fehler_prozent', 'begruendung'])
            w.writeheader()
            w.writerows(raus)
        json.dump(dict(paare=[dict(behalten=g['name'], bdatei=g['file'], weg=w_['name'], wdatei=w_['file'], km=d, abw=abw, grund=gr)
                              for g, w_, d, abw, gr in paare],
                       ausreisser=[dict(name=s['name'], datei=s['file'], lat=s['lat'], lon=s['lon'], befund=b) for s, b in ausreisser]),
                  open(stem + '.json', 'w'), ensure_ascii=False, indent=0)
        print('   %d Paare, %d zum Archivieren vorgeschlagen, %d offen (Bucht), %d Zeit-Ausreisser' % (
            len(paare), len(raus), sum(1 for p in paare if p[4].startswith('Bucht')), len(ausreisser)))
        for r in raus:
            print('   - %s [%s]: %s' % (r['name'], os.path.basename(r['datei']), r['begruendung'][:150]))
        for s, b in ausreisser[:40]:
            print('   ? %s [%s]: %s' % (s['name'], os.path.basename(s['file']), b))
        print('   ->', stem + '_loeschen.csv', flush=True)


if __name__ == '__main__':
    main(sys.argv[1:])
