#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Setzt S2 und K2 der NOAA-Table-2-Uebertragungen auf den Springhub des Buchs.

Die Bauskripte (py/build_noaa_{eutt,amtt,cptt}.py, transfer() Schritt 2)
skalieren S2/K2 so, dass (Springhub - mittlerer Hub) der Referenz zum Buch
passt. Den Springhub der Referenz massen sie aber als
    Perzentil 92 der Hochwasser - Perzentil 8 der Niedrigwasser,
also als Rand der Verteilung statt als mittleren Springhub, und ohne den
Faktor CAL, der beim mittleren Hub steht. Der Unterschied wird dadurch zu
gross und S2 zu klein: Gegen unabhaengige Nachbarn unter 5 km liegt S2/M2
der Uebertragungen im Median bei 0.37-0.48 des Nachbarn (1068 Saetze, nur
2 darueber). An 80 echten Pegeln brachte schon die grobe Buchformel
S2/M2 = Springhub/mittlerer Hub - 1 im Median 21.9 -> 17.8 cm (13.09.2026).

Hier wird nicht neu uebertragen -- seit dem Bau wurden Zonen gedreht,
Bezugsorte getauscht, Positionen berichtigt. Stattdessen am vorhandenen Satz:
    mittlerer Hub   = Mittel aller Hochwasser - Mittel aller Niedrigwasser
    Springhub       = dasselbe nur fuer Scheitel, an denen M2 und S2 in Phase
                      sind (Abstand bis SPRING_GRAD)
und S2/K2 mit einem Faktor f multipliziert, bis
    Springhub - mittlerer Hub = CAL * (Buch-Springhub - Buch-Mittelhub).
Zeitverschiebungen aendern Hube nicht, darum gehen die Phasen roh ein.

Geprueft wird jeder Satz an einer echten Reihe unter 3 km (Qualitaetstabellen),
sonst am S2/M2 unabhaengiger Nachbarn unter 5 km. Schlechter wird nichts:
dort bleibt der alte Wert.

Usage: python3 py/noaa_s2_nachziehen.py              -> harmonics/help/noaa_s2_nachziehen.csv
       python3 py/noaa_s2_nachziehen.py --schreiben  (Zeilen mit empfehlung 'anwenden...')
"""
from __future__ import annotations

import csv
import datetime as dt
import glob
import json
import math
import os
import re
import shutil
import statistics
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import xtide_modell as X                                           # noqa: E402
from health_check import MERIDIAN, km, load_records                # noqa: E402
from sicher_schreiben import schreiben                             # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HELP = os.path.join(ROOT, 'harmonics/help')
AUS = os.path.join(HELP, 'noaa_s2_nachziehen.csv')
DATEIEN = ('harmonics_noaa_eutt.txt', 'harmonics_noaa_amtt.txt', 'harmonics_noaa_cptt.txt')
BUECHER = ('eutt2020', 'ectt2020', 'wctt2020', 'cptt2018')
FT, CAL = 0.3048, 1.10               # CAL wie in den Bauskripten
SPRING_GRAD = 30.0
F_MIN, F_MAX = 0.5, 15.0            # Buenos Aires: S2/M2 0.02 gegen Nachbarn 0.14-0.25
F_GROSS = 4.0                        # darueber nur mit Beleg (Pegel oder Nachbarn)
HEUTE = dt.date.today().strftime('%Y%m%d')

_T = np.arange(0, 180 * 24, 0.25)    # Stunden, 180 Tage


def hube(con, speeds):
    """-> (mittlerer Hub, Springhub) einer knotenfreien Synthese."""
    if 'M2' not in con or 'S2' not in con:
        return None
    h = np.zeros_like(_T)
    for c, (a, g) in con.items():
        if a > 0 and c in speeds:
            h += a * np.cos(np.radians(speeds[c] * _T - g))
    # Ein Hoch- und ein Niedrigwasser je M2-Periode: an Orten mit Stillstand
    # oder doppeltem Niedrigwasser (Portland, Solent) zaehlt ein lokaler
    # Nebenscheitel sonst als eigenes Hochwasser und drueckt den Mittelhub.
    per = 360.0 / speeds['M2']
    fenster = (_T // per).astype(int)
    n_f = fenster.max()
    grenzen = np.searchsorted(fenster, np.arange(n_f + 1))
    hi = np.array([grenzen[i] + np.argmax(h[grenzen[i]:grenzen[i + 1]]) for i in range(n_f)])
    lo = np.array([grenzen[i] + np.argmin(h[grenzen[i]:grenzen[i + 1]]) for i in range(n_f)])
    if len(hi) < 20 or 'M2' not in con or 'S2' not in con:
        return None
    mittel = h[hi].mean() - h[lo].mean()
    dw = speeds['S2'] - speeds['M2']
    dg = con['S2'][1] - con['M2'][1]

    def spring(ix):
        phi = (dw * _T[ix] - dg + 180.0) % 360.0 - 180.0
        return ix[np.abs(phi) <= SPRING_GRAD]
    shi, slo = spring(hi), spring(lo)
    if len(shi) < 5 or len(slo) < 5:
        return None
    return float(mittel), float(h[shi].mean() - h[slo].mean())


def faktor(con, speeds, ziel):
    """f fuer S2/K2, sodass Springhub - Mittelhub = ziel (Bisektion)."""
    def diff(f):
        c2 = {c: ((a * f if c in ('S2', 'K2') else a), g) for c, (a, g) in con.items()}
        r = hube(c2, speeds)
        return None if r is None else r[1] - r[0]
    lo, hi = F_MIN, F_MAX
    d_lo, d_hi = diff(lo), diff(hi)
    if d_lo is None or d_hi is None:
        return None
    if ziel <= d_lo:
        return F_MIN
    if ziel >= d_hi:
        return F_MAX
    for _ in range(30):
        mid = 0.5 * (lo + hi)
        if diff(mid) < ziel:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def buch():
    out = {}
    for b in BUECHER:
        for e in json.load(open(os.path.join(HELP, f'{b}_table2_full.json'), encoding='utf-8')):
            out[(b[:4], e['no'])] = e
    return out


def kommentare(pfad):
    L = open(pfad, encoding='iso-8859-1').read().split('\n')
    out = {}
    for i in range(1, len(L) - 1):
        if not L[i].startswith('#') and MERIDIAN.match(L[i + 1]):
            j, c = i - 1, []
            while j >= 0 and L[j].startswith('#'):
                c.append(L[j])
                j -= 1
            out[L[i]] = '\n'.join(c)
    return out


def pegelpfade():
    """{(datei, satz): (pfad, abstand_m)} aus den Qualitaetstabellen, <= 3 km.

    Reihen, an denen kein Satz unter 20 cm bleibt, zaehlen nicht (EA Chesil
    Cove rloi3289: alle Saetze 46-70 cm; Padstow 146 cm).
    """
    beste = {}
    for q in ('messreihe_qualitaet_alle.csv', 'bodc_qualitaet.csv', 'ea_qualitaet.csv'):
        p = os.path.join(HELP, q)
        if os.path.exists(p):
            for z in csv.DictReader(open(p, encoding='utf-8')):
                if z.get('rms_m'):
                    k = (z['reihe'], z['station'])
                    beste[k] = min(beste.get(k, 9.0), float(z['rms_m']))
    out = {}
    for q in ('messreihe_qualitaet_alle.csv', 'bodc_qualitaet.csv', 'ea_qualitaet.csv'):
        p = os.path.join(HELP, q)
        if not os.path.exists(p):
            continue
        for z in csv.DictReader(open(p, encoding='utf-8')):
            if z['datei'] not in DATEIEN or not z.get('abstand_m'):
                continue
            ab = float(z['abstand_m'])
            if ab > 3000 or beste.get((z['reihe'], z['station']), 9.0) > 0.20:
                continue
            pfad = os.path.join(ROOT, 'water_levels', z['reihe'], z['station'])
            if not os.path.exists(pfad):
                t = glob.glob(os.path.join(ROOT, 'water_levels', z['reihe'], '*', z['station']))
                if len(t) != 1:
                    continue
                pfad = t[0]
            alt = out.get((z['datei'], z['satz']))
            if alt is None or ab < alt[1]:
                out[(z['datei'], z['satz'])] = (pfad, ab)
    return out


def pegel_rms(pfad, z0, g, kopf, f):
    import messreihe_qualitaet as M
    import scheitelfit as S
    obs = M.lies(pfad)
    if len(obs) < 3000:
        return None
    t = np.array([o[0] for o in obs])[-35000:]
    h = np.array([o[1] for o in obs])[-35000:]
    out = []
    for ff in (1.0, f):
        gg = {c: ((a * ff if c in ('S2', 'K2') else a), p) for c, (a, p) in g.items()}
        d = h - S.hoehe_und_ableitungen(t, z0, gg, kopf)[0]
        out.append(float(np.sqrt(np.mean((d - d.mean()) ** 2))))
    return out


def s2m2(r):
    try:
        z0, w, e, mer = X.satz_lesen(r['file'], r['name'])
    except (KeyError, IndexError, ValueError):
        return None
    if 'M2' not in w or 'S2' not in w or w['M2'][0] < 0.05:
        return None
    return w['S2'][0] / w['M2'][0]


def pruefen():
    import scheitelfit as S
    kopf = X.kopf_lesen(S.KOPFQUELLE)
    speeds = kopf[1]
    B = buch()
    recs = load_records()
    unabh = [r for r in recs if '/noaa/' not in r['file'] and 'current' not in r['file'].lower()
             and 'utide_tidetables' not in r['file'] and 'bsh_germany' not in r['file']]
    pegel = pegelpfade()
    u_lat = np.radians([q['lat'] for q in unabh])
    u_lon = np.radians([q['lon'] for q in unabh])

    def nachbarn(r, radius_km=5.0):
        la, lo = math.radians(r['lat']), math.radians(r['lon'])
        a = (np.sin((u_lat - la) / 2) ** 2
             + np.cos(la) * np.cos(u_lat) * np.sin((u_lon - lo) / 2) ** 2)
        d = 2 * 6371.0 * np.arcsin(np.sqrt(np.minimum(a, 1.0)))
        return [unabh[i] for i in np.where(d <= radius_km)[0]]
    zeilen = []
    for datei in DATEIEN:
        pfad = os.path.join(ROOT, 'harmonics/noaa', datei)
        kom = kommentare(pfad)
        for r in [r for r in recs if os.path.basename(r['file']) == datei]:
            c = kom.get(r['name'], '')
            if 'Table 2 transfer' not in c:
                continue
            m = re.search(r'noaa_uid: (\w+)-(\d+)', c)
            n = re.search(r'noaa_number: (\d+)', c)
            band = m.group(1) if m else datei[15:19]
            no = int(m.group(2)) if m else (int(n.group(1)) if n else None)
            e = B.get((band, no))
            if not e or e.get('coltype') != 'MS' or not e.get('mean_ft') or not e.get('spring_ft'):
                continue
            if e['spring_ft'] <= e['mean_ft']:
                continue
            z0, w, einheit, mer = X.satz_lesen(r['file'], r['name'])
            sk = FT if einheit.startswith('f') else 1.0
            con = {k: (a * sk, g) for k, (a, g) in w.items() if k in speeds}
            if 'S2' not in con or 'M2' not in con:
                continue
            hb = hube(con, speeds)
            if hb is None:
                continue
            ziel = CAL * (e['spring_ft'] - e['mean_ft']) * FT
            f = faktor(con, speeds, ziel)
            if f is None:
                continue
            ratio_alt = con['S2'][0] / con['M2'][0]
            nb = [x for x in (s2m2(q) for q in nachbarn(r)) if x is not None]
            nachbar = statistics.median(nb) if nb else None
            z = dict(datei=datei, name=r['name'], no=f'{band}-{no}', faktor=round(f, 3),
                     s2_alt=round(con['S2'][0], 4), s2_neu=round(con['S2'][0] * f, 4),
                     s2m2_alt=round(ratio_alt, 3), s2m2_neu=round(ratio_alt * f, 3),
                     nachbar_s2m2='' if nachbar is None else round(nachbar, 3), n_nachbarn=len(nb),
                     mittelhub_satz_m=round(hb[0], 2), mittelhub_buch_m=round(CAL * e['mean_ft'] * FT, 2),
                     pegel='', pegel_km='', pegel_alt_cm='', pegel_neu_cm='', empfehlung='', form_F='')
            pg = pegel.get((datei, r['name']))
            if pg:
                g = {k: (a * sk, X.greenwich(kap, speeds[k], mer)) for k, (a, kap) in w.items() if k in speeds}
                res = pegel_rms(pg[0], z0 * sk, g, kopf, f)
                if res:
                    z.update(pegel=os.path.basename(pg[0]), pegel_km=round(pg[1] / 1000, 2),
                             pegel_alt_cm=round(res[0] * 100, 1), pegel_neu_cm=round(res[1] * 100, 1))
            form = ((con.get('K1', (0, 0))[0] + con.get('O1', (0, 0))[0])
                    / max(1e-6, con['M2'][0] + con['S2'][0] * f))
            z['form_F'] = round(form, 2)
            # Gemischte Tide: dort traf die Nachbarprobe bei Faktor > 4 nur 30 von 52
            # (halbtaegig 9 von 10) -- ohne Beleg nicht anwenden.
            if f in (F_MIN, F_MAX):
                z['empfehlung'] = 'pruefen (Faktor an der Grenze)'
            elif f > F_GROSS and z['pegel_alt_cm'] == '' and nachbar is None:
                z['empfehlung'] = 'pruefen (grosser Faktor ohne Beleg)'
            elif form >= 1.5 and z['pegel_alt_cm'] == '' and nachbar is None:
                z['empfehlung'] = 'pruefen (eintaegige Tide ohne Beleg)'
            elif z['pegel_alt_cm'] != '':
                z['empfehlung'] = ('anwenden (Pegel)' if z['pegel_neu_cm'] <= z['pegel_alt_cm'] + 0.2
                                   else 'lassen (Pegel schlechter)')
            elif nachbar is not None:
                z['empfehlung'] = ('anwenden (Nachbarn)' if abs(ratio_alt * f - nachbar) <= abs(ratio_alt - nachbar)
                                   else 'lassen (Nachbarn)')
            else:
                z['empfehlung'] = 'anwenden (nur Buch)'
            zeilen.append(z)
            if len(zeilen) % 100 == 0:
                print(f'  {len(zeilen)} ...', flush=True)
    with open(AUS, 'w', newline='', encoding='utf-8') as fh:
        wr = csv.DictWriter(fh, fieldnames=list(zeilen[0].keys()))
        wr.writeheader()
        wr.writerows(zeilen)
    print('->', os.path.relpath(AUS, ROOT), len(zeilen), 'Saetze')


def anwenden():
    zeilen = [z for z in csv.DictReader(open(AUS, encoding='utf-8'))
              if z['empfehlung'].startswith('anwenden') or z.get('entscheidung', '').startswith('anwenden')]
    nach = {}
    for z in zeilen:
        if z.get('entscheidung', '').startswith('lassen'):
            continue
        nach.setdefault(z['datei'], []).append(z)
    for datei, zs in nach.items():
        pfad = os.path.join(ROOT, 'harmonics/noaa', datei)
        lines = open(pfad, encoding='iso-8859-1').read().split('\n')
        index = {}
        for k in range(len(lines) - 1):
            if not lines[k].startswith('#') and MERIDIAN.match(lines[k + 1]):
                index.setdefault(lines[k], []).append(k)
        n = 0
        for z in sorted(zs, key=lambda z: -index.get(z['name'], [0])[0]):
            ks = index.get(z['name'], [])
            if len(ks) != 1:
                print(f'  NICHT EINDEUTIG ({len(ks)}): {z["name"]}')
                continue
            k, f = ks[0], float(z['faktor'])
            j, geaendert = k + 3, 0
            while j < len(lines) and lines[j] and not lines[j].startswith('#'):
                p = lines[j].split()
                if p[0] in ('S2', 'K2') and len(p) >= 3:
                    lines[j] = f'{p[0]:<16}{float(p[1]) * f:.4f}  {float(p[2]):.2f}'
                    geaendert += 1
                j += 1
            if geaendert == 0:
                continue
            lines[k:k] = [f'# note: {HEUTE} S2/K2 x {f:.2f} auf den Springhub des Buchs ({z["no"]}); der Bau',
                          '# note: mass den Springhub der Referenz als 92/8-Perzentil, S2 kam zu klein heraus.',
                          f'# note: Probe: {z["empfehlung"]}'
                          + (f', Pegel {z["pegel_alt_cm"]} -> {z["pegel_neu_cm"]} cm' if z['pegel_alt_cm'] else '')
                          + (f', S2/M2 Nachbarn {z["nachbar_s2m2"]}' if z['nachbar_s2m2'] else '')
                          + '. Siehe py/noaa_s2_nachziehen.py.']
            n += 1
        shutil.copy2(pfad, os.path.join(ROOT, 'harmonics/backup', f'{datei}.vor_s2_{HEUTE}'))
        schreiben(pfad, '\n'.join(lines))
        print(f'  {datei}: {n} Saetze geaendert')


if __name__ == '__main__':
    if '--schreiben' in sys.argv:
        anwenden()
    else:
        pruefen()
