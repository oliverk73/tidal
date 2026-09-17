#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""DHN-Peru-Saetze aus zwei Jahren Tageswerten neu rechnen.

Bisher (py/build_dhn_peru.py, Juni 2026): je Hafen nur zwei Juni-Monate
(2024 und 2026) Hoch-/Niedrigwasser, feste 8 Partialtiden, direkt auf die
Scheitelpunkte gefittet. Seit 17.09.2026 holt py/dhn_peru_tage.py beliebige
Zeitraeume (tide_tables/peru/tage/<hafen>.csv, Ortszeit UTC-5, cm ueber dem
Kartennull der DHN).

Hier: Scheitel nach UTC, Kosinus-Interpolation zwischen den Scheiteln
(batch_utide_uk_tidetimes.cosine_interpolate, wie bei den anderen Tafelfits),
UTide mit CONSTIT_67 plus SA/SSA. Ersetzt wird nur der Zahlenteil der
bestehenden DHN-Saetze (Suche ueber station_id_context), Name/Position/Kopf
bleiben.

Pruefstein: An den Haefen, an denen ein Messsatz steht (Callao, Paita,
Talara, Matarani, Ilo, Chimbote, Chancay, Chala, Pisco, San Juan, Lobos de
Afuera), wird die DHN-Tafel genauso gefittet und gegen den Messsatz gelegt
-- das zeigt, wie gut Tafel plus Verfahren sind, bevor irgendetwas
geschrieben wird.

Usage: venv/bin/python3 py/dhn_peru_refit.py [--mind-tage 600] [--schreiben]
"""
from __future__ import annotations

import csv
import datetime as dt
import os
import re
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from health_check import MERIDIAN, ROOT, curve_diff, km, load_records  # noqa: E402

TAGE = os.path.join(ROOT, 'tide_tables/peru/tage')
ZIEL = os.path.join(ROOT, 'harmonics/utide/harmonics_utide_tidetables.txt')
KENNUNG = {'caleta_grau': 'PUERTO_GRAU'}


def scheitel(hafen):
    out = []
    for z in csv.DictReader(open(os.path.join(TAGE, f'{hafen}.csv'))):
        t = dt.datetime.fromisoformat(f"{z['datum']}T{z['zeit']}") + dt.timedelta(hours=5)
        out.append((t, int(z['hoehe_cm']) / 100.0))
    return sorted(set(out))


def fit(punkte, lat):
    import utide
    from batch_utide_uk_tidetimes import CONSTIT_67, cosine_interpolate
    t, v = cosine_interpolate(punkte)
    liste = list(CONSTIT_67) + [x for x in ('SA', 'SSA') if x not in CONSTIT_67]
    coef = utide.solve(t, v, lat=lat, nodal=True, trend=False, method='ols', conf_int='none',
                       verbose=False, constit=liste)
    res = v - utide.reconstruct(t, coef, verbose=False)['h']
    return coef, t, float(np.sqrt(np.mean(res ** 2))), 1 - float(np.var(res)) / float(np.var(v))


def main(argv):
    import dmi_tidevand as D
    mind = int(argv[argv.index('--mind-tage') + 1]) if '--mind-tage' in argv else 600
    recs = [r for r in load_records() if not r['current'] and r['lat'] is not None]
    zeilen = open(ZIEL, encoding='iso-8859-1').read().split('\n')
    import noaa_pruefstand as P
    ergebnisse = []
    for datei in sorted(os.listdir(TAGE)):
        if not datei.endswith('.csv'):
            continue
        hafen = datei[:-4]
        punkte = scheitel(hafen)
        tage = len({t.date() for t, _h in punkte})
        kennung = f"DHN-PERU-{KENNUNG.get(hafen, hafen.upper())}"
        j = next((i for i, l in enumerate(zeilen) if l.strip() == f'# station_id_context: {kennung}'), None)
        if j is not None:
            k = j + 1
            while zeilen[k].startswith('#'):
                k += 1
            satz = next(r for r in recs if r['name'] == zeilen[k])
        else:
            satz = None
        if tage < mind:
            print(f'{hafen:16} nur {tage} Tage -- spaeter')
            continue
        lat = satz['lat'] if satz else None
        # Ohne DHN-Satz: Lage vom naechsten Messsatz gleichen Namens (nur zur Pruefung)
        a_satz = None
        kand = [r for r in recs if P.klasse(r) == 'A' and r['name'].endswith('Peru')
                and hafen.split('_')[0] in r['name'].lower().replace('ó', 'o')]
        if kand:
            a_satz = kand[0]
            lat = lat or a_satz['lat']
        if lat is None:
            print(f'{hafen:16} keine Lage bekannt')
            continue
        coef, t, rms, r2 = fit(punkte, lat)
        w = D.werte_aus(coef)
        neu = D.als_satz(hafen, {'latitude': lat, 'longitude': (satz or a_satz)['lon']}, w, None, 'Peru')
        neu.update(lat=lat, lon=(satz or a_satz)['lon'])
        zeile = f"{hafen:16} {tage:4} Tage  r2={r2:.4f} rms={100 * rms:4.1f} cm  M2 {w['M2'][0]:.3f}/{w['M2'][1]:5.1f}"
        if satz:
            zeile += f"  | alt {100 * curve_diff(neu, satz)[1]:4.1f} %"
        if a_satz:
            d = km(neu, a_satz)
            ma, mg = abs(a_satz['z']['M2']), (-np.degrees(np.angle(a_satz['z']['M2']))) % 360
            zeile += (f"  | Messsatz {d:4.1f} km: {100 * curve_diff(neu, a_satz)[1]:4.1f} %, "
                      f"M2 {ma:.3f}/{mg:5.1f}")
        print(zeile, flush=True)
        ergebnisse.append((hafen, satz, w, coef, t, rms, r2, tage))
    if '--schreiben' not in argv:
        print('(nur Probe; mit --schreiben werden die DHN-Saetze ersetzt)')
        return 0
    import sicher_schreiben
    from add_uhslc_harmonics import CONSTITUENTS_175
    heute = f'{dt.date.today():%Y%m%d}'
    n = 0
    for hafen, satz, w, coef, t, rms, r2, tage in ergebnisse:
        if not satz:
            continue
        k = next(i for i, l in enumerate(zeilen) if l == satz['name']
                 and i + 1 < len(zeilen) and MERIDIAN.match(zeilen[i + 1]))
        ende = k + 3
        while ende < len(zeilen) and zeilen[ende].strip() and not zeilen[ende].startswith('#'):
            ende += 1
        block = [f"{float(coef['mean']):.4f} meters"] + [
            f'{cn:15s} {w[cn][0]:.4f}  {w[cn][1]:.2f}' if cn in w and w[cn][0] >= 0.00005 else 'x 0 0'
            for cn, _sp in CONSTITUENTS_175]
        if len(block) != ende - (k + 2):
            print(f'  {satz["name"]}: Aufbau weicht ab -- uebersprungen')
            continue
        zeilen[k + 2:ende] = block
        a = k
        while zeilen[a - 1].startswith('#'):
            a -= 1
        for i in range(a, k):
            if zeilen[i].startswith('# utide:'):
                zeilen[i] = (f"# utide: pts={len(t)} period={t[0]:%Y-%m-%d}..{t[-1]:%Y-%m-%d} "
                             f"r2={r2:.4f} rms={rms:.4f}m const={sum(1 for c, _ in CONSTITUENTS_175 if c in w)}")
        einf = next(i for i in range(a, k) if zeilen[i].startswith('# !units:'))
        zeilen.insert(einf, f'# note: {heute} neu gefittet aus {tage} Tagen DHN-Tageswerten '
                            f'(py/dhn_peru_tage.py, Kosinus-Interpolation, CONSTIT_67+SA/SSA).')
        n += 1
    sicher_schreiben.schreiben(ZIEL, '\n'.join(zeilen))
    print(f'{n} DHN-Saetze ersetzt')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
