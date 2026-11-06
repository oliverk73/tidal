#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Eigene HW/NW-Rechnung gegen die amtlichen Vorhersagen (Oliver 6.11.2026), wie bsh_vergleich_alle.py fuer Deutschland.

Pruefjahr 2025 (in keiner Eichung enthalten): gemessene HW/NW (Scheitel-CSV aus hwnw_alle.py) gegen
  amtlich  USA: NOAA CO-OPS predictions interval=hilo (MLLW, metrisch, UTC)
           NL:  Rijkswaterstaat astronomische Getijextreme (GETETBRKD2, NAP)
  satz     harmonischer Satz (Scheitel)
  neu      eigene Rechnung (hwnw_ungleichheiten.vorhersage_kombi)
Nur Orte mit Modell (harmonics/hwnw/us_*, nl_*). Amtliche Vorhersagen werden in water_levels/amtlich_2025/ gecacht.
Ergebnis: harmonics/help/amtlich_vergleich_<datum>.csv
Usage: venv/bin/python py/amtlich_vergleich.py [--land=us|nl]
"""
from __future__ import annotations

import datetime as dt
import glob
import json
import os
import sys
import time
import urllib.request

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hwnw_alle as A                                               # noqa: E402
import hwnw_ungleichheiten as HU                                    # noqa: E402

ROOT = HU.ROOT
JAHR = 2025
CACHE = os.path.join(ROOT, 'water_levels/amtlich_2025')
T0 = dt.datetime(JAHR, 1, 1, tzinfo=dt.timezone.utc).timestamp()
T1 = dt.datetime(JAHR + 1, 1, 1, tzinfo=dt.timezone.utc).timestamp()


def noaa(nr):
    p = os.path.join(CACHE, f'us_{nr}.json')
    if not os.path.exists(p):
        url = ('https://api.tidesandcurrents.noaa.gov/api/prod/datagetter?product=predictions&interval=hilo'
               f'&station={nr}&begin_date={JAHR}0101&end_date={JAHR}1231&datum=MLLW&units=metric&time_zone=gmt'
               '&format=json&application=tiden_pruefung')
        with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'tiden-pruefung/1.0'}), timeout=120) as r:
            open(p, 'wb').write(r.read())
        time.sleep(1.5)
    d = json.load(open(p)).get('predictions', [])
    return [(dt.datetime.strptime(x['t'], '%Y-%m-%d %H:%M').replace(tzinfo=dt.timezone.utc).timestamp(),
             float(x['v']), 'H' if x['type'] == 'H' else 'N') for x in d]


def rws(code):
    p = os.path.join(CACHE, f'nl_{code}.json')
    if not os.path.exists(p):
        h = A._rws(code, 'WATHTE', JAHR, groep='GETETBRKD2')
        t = A._rws(code, 'NVT', JAHR, groep='GETETBRKD2')
        json.dump({'h': h, 't': t}, open(p, 'w'))
        time.sleep(0.5)
    d = json.load(open(p))
    out = []
    for ts, w in d['h'].items():
        typ = (d['t'].get(ts) or {}).get('Waarde_Alfanumeriek', '')
        if typ.startswith(('hoogwater', 'laagwater')) and w.get('Waarde_Numeriek') is not None:
            out.append((dt.datetime.fromisoformat(ts).timestamp(), w['Waarde_Numeriek'] / 100,
                        'H' if typ == 'hoogwater' else 'N'))
    return sorted(out)


def kennzahlen(mess, pred):
    if not pred:
        return None
    P = HU.zuordnen(mess, pred)
    out = {}
    for art in 'HN':
        q = P[P.art == art]
        if len(q) < 100:
            return None
        dz = (q.t_pred - q.t_mess).values / 60.0
        out[art] = (len(q), float(dz.mean()), float(np.sqrt((dz ** 2).mean())))
    return out


def main(argv):
    opt = dict(a[2:].split('=', 1) for a in argv if a.startswith('--'))
    os.makedirs(CACHE, exist_ok=True)
    P = dict(A.pegel_usa(), **A.pegel_nl())
    zeilen, ges = [], []
    for f in sorted(glob.glob(os.path.join(HU.ZIEL, '*.json'))):
        k = os.path.basename(f)[:-5]
        land = k[:2]
        if land not in ('us', 'nl') or k not in P or (opt.get('land') and land != opt['land']):
            continue
        E = HU.laden(k)
        mess = HU.scheitel_csv(A.scheitel_pfad(k), JAHR, JAHR)
        try:
            amt = noaa(P[k]['quelle'][1]) if land == 'us' else rws(P[k]['quelle'][1])
        except Exception as e:  # noqa: BLE001
            print(f'{k:30} amtlich fehlt: {e}', flush=True)
            continue
        r = {'amtlich': kennzahlen(mess, amt),
             'satz': kennzahlen(mess, HU.satz_ereignisse(os.path.join(ROOT, E['datei']), E['satz'], T0 - 86400, T1 + 86400)),
             'neu': kennzahlen(mess, HU.vorhersage_kombi(k, T0 - 86400, T1 + 86400))}
        if not all(r.values()):
            print(f'{k:30} zu wenig Paare', flush=True)
            continue
        ges.append((k, r))
        z = [k, E['satz']] + [f'{r[v][a][i]:.1f}' for a in 'HN' for v in ('amtlich', 'satz', 'neu') for i in (2, 1)]
        zeilen.append(';'.join(z))
        print(f"{k:30} HW rms amtl {r['amtlich']['H'][2]:5.1f} Satz {r['satz']['H'][2]:5.1f} neu {r['neu']['H'][2]:5.1f} | "
              f"NW amtl {r['amtlich']['N'][2]:5.1f} Satz {r['satz']['N'][2]:5.1f} neu {r['neu']['N'][2]:5.1f}", flush=True)
    kopf = 'kurz;satz;' + ';'.join(f'{a}_{v}_{m}' for a in ('hw', 'nw') for v in ('amtlich', 'satz', 'neu') for m in ('rms', 'mittel'))
    aus = os.path.join(ROOT, 'harmonics/help', f'amtlich_vergleich_{dt.date.today():%Y%m%d}.csv')
    open(aus, 'w', encoding='utf-8').write(kopf + '\n' + '\n'.join(zeilen) + '\n')
    for land in ('us', 'nl'):
        g = [r for k, r in ges if k.startswith(land)]
        if not g:
            continue
        for a in 'HN':
            m = {v: np.median([r[v][a][2] for r in g]) for v in ('amtlich', 'satz', 'neu')}
            besser = sum(r['neu'][a][2] < r['amtlich'][a][2] for r in g)
            print(f"{land.upper()} {a}W ({len(g)} Orte) Median Zeit-RMS: amtlich {m['amtlich']:.1f}  Satz {m['satz']:.1f}  "
                  f"neu {m['neu']:.1f} min; neu besser als amtlich an {besser}/{len(g)}")
    print('->', aus)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
