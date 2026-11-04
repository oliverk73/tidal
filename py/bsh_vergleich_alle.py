#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Guetenachweis der eigenen HW/NW-Rechnung (Stufe 4, Oliver 4.11.2026): an allen Pegeln mit BSH-Tafel 2026
(tide_tables/germany_bsh/DE__<nr>P2026.txt) die letzten 30 Tage Pegelonline-Messung gegen
  BSH (HDdU-Vorausberechnung) | harmonischer Satz | eigene Rechnung (hwnw_ungleichheiten.vorhersage_kombi).
Kein Messwert dieses Zeitraums steckt in einer Eichung (Reihen enden Januar 2026).

Zuordnung: BSH-Feld A13 Messstelle = Pegelonline-Stationsnummer = station_number der Zip-Exporte
(water_levels/Germany/pegelonline-*.zip) -> hwnw_alle-Kurzname.
Messung: Pegelonline REST v2 .../stations/<nr>/W/measurements.json?start=P30D (1 min, cm PNP), Cache in
water_levels/pegelonline_bsh_test/alle/<nr>.json (am selben Tag nicht neu geladen).
Ergebnis: harmonics/help/bsh_vergleich_<datum>.csv
Usage: venv/bin/python py/bsh_vergleich_alle.py
"""
from __future__ import annotations

import datetime as dt
import glob
import json
import os
import re
import sys
import time
import urllib.request
import zipfile

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bsh_hddu_test as B                                           # noqa: E402
import hwnw_alle as A                                               # noqa: E402
import hwnw_ungleichheiten as HU                                    # noqa: E402

ROOT = HU.ROOT
BSH = os.path.join(ROOT, 'tide_tables/germany_bsh')
CACHE = os.path.join(ROOT, 'water_levels/pegelonline_bsh_test/alle')
API = 'https://www.pegelonline.wsv.de/webservices/rest-api/v2/stations/{}/W/measurements.json?start=P30D'


def bsh_tafeln():
    """-> [(bsh_nr, name, messstelle)]"""
    out = []
    for f in sorted(glob.glob(os.path.join(BSH, 'DE__*P2026.txt'))):
        kopf = {}
        for z in open(f, encoding='latin-1'):
            if z.startswith('VB'):
                break
            t = z.split('#')
            if len(t) > 2:
                kopf[t[0]] = t[2].strip()
        nr = re.search(r'DE__(\w+?)P2026', f).group(1)
        out.append((nr, kopf.get('A04', ''), kopf.get('A13', '').strip()))
    return out


def stationsnummern():
    """Pegelonline-Stationsnummer -> hwnw-Kurzname"""
    out = {}
    for f in glob.glob(os.path.join(ROOT, 'water_levels/Germany/pegelonline-*-W-*.zip')):
        k = A.kurzname(os.path.basename(f).split('-W-')[0][len('pegelonline-'):])
        with zipfile.ZipFile(f) as z:
            n = [x for x in z.namelist() if x.endswith('zeitreiheninformation.txt')]
            if n:
                m = re.search(r'station_number=(\d+)', z.read(n[0]).decode('latin-1'))
                if m:
                    out[m.group(1)] = k
    return out


def messung(nr):
    os.makedirs(CACHE, exist_ok=True)
    p = os.path.join(CACHE, nr + '.json')
    if not os.path.exists(p) or dt.date.fromtimestamp(os.path.getmtime(p)) < dt.date.today():
        req = urllib.request.Request(API.format(nr), headers={'User-Agent': 'tiden-pruefung/1.0'})
        with urllib.request.urlopen(req, timeout=60) as r:
            open(p, 'wb').write(r.read())
        time.sleep(0.5)
    d = json.load(open(p))
    s = pd.Series([x['value'] / 100 for x in d], index=pd.to_datetime([x['timestamp'] for x in d], utc=True))
    s = s[~s.index.duplicated()].sort_index().resample('1min').mean().interpolate(limit=10)
    ev = B.scheitel(s)
    h, a = np.array([e[1] for e in ev]), np.array([e[2] for e in ev])
    ok = ~HU.unplausibel(h, a) if len(ev) > 10 else np.zeros(len(ev), bool)
    t0, t1 = s.index[0].timestamp() + 3 * 3600, s.index[-1].timestamp() - 3 * 3600
    return [e for e, g in zip(ev, ok) if g and t0 <= e[0] <= t1], t0, t1


def kennzahlen(mess, pred):
    P = HU.zuordnen(mess, pred)
    out = {}
    for art in 'HN':
        q = P[P.art == art]
        if len(q) < 20:
            return None
        dz = (q.t_pred - q.t_mess).values / 60.0
        dh = (q.h_pred - q.h_mess).values
        out[art] = (len(q), dz.mean(), np.sqrt((dz ** 2).mean()), dh.mean(), np.sqrt((dh ** 2).mean()))
    return out


def main():
    nummern = stationsnummern()
    modelle = {f[:-5] for f in os.listdir(HU.ZIEL) if f.endswith('.json')}
    P = A.pegel()
    zeilen, ges = [], []
    for nr, name, ms in bsh_tafeln():
        k = nummern.get(ms)
        if not k or k not in P:
            print(f'{nr:5} {name:30} ohne Pegelonline-Reihe/Satz ({ms})')
            continue
        try:
            mess, t0, t1 = messung(ms)
        except Exception as e:  # noqa: BLE001
            print(f'{nr:5} {name:30} Messung fehlt: {e}')
            continue
        r = {'bsh': kennzahlen(mess, B.bsh(nr, t0 - 6 * 3600, t1 + 6 * 3600)),
             'harm': kennzahlen(mess, HU.satz_ereignisse(os.path.join(ROOT, A.OBS), P[k]['satz'], t0 - 86400, t1 + 86400)),
             'neu': kennzahlen(mess, HU.vorhersage_kombi(k, t0 - 86400, t1 + 86400)) if k in modelle else None}
        if not r['bsh'] or not r['harm']:
            print(f'{nr:5} {name:30} zu wenig Scheitel')
            continue
        r['neu'] = r['neu'] or r['harm']
        ges.append((k, r))
        z = [nr, name, k, r['bsh']['H'][0]]
        for art in 'HN':
            for v in ('bsh', 'harm', 'neu'):
                z += [f'{r[v][art][2]:.1f}', f'{r[v][art][1]:+.1f}']
        for art in 'HN':
            for v in ('bsh', 'harm', 'neu'):
                z += [f'{100 * r[v][art][4]:.0f}', f'{100 * r[v][art][3]:+.0f}']
        zeilen.append(';'.join(str(x) for x in z))
        print(f'{nr:5} {name[:28]:28} HW rms BSH {r["bsh"]["H"][2]:5.1f} Satz {r["harm"]["H"][2]:5.1f} neu {r["neu"]["H"][2]:5.1f} | '
              f'NW BSH {r["bsh"]["N"][2]:5.1f} Satz {r["harm"]["N"][2]:5.1f} neu {r["neu"]["N"][2]:5.1f} min', flush=True)
    kopf = 'bsh_nr;bsh_name;kurz;n_hw'
    for g in ('zeit', 'hoehe_cm'):
        for art in ('hw', 'nw'):
            for v in ('bsh', 'satz', 'neu'):
                kopf += f';{g}_rms_{art}_{v};{g}_mittel_{art}_{v}'
    aus = os.path.join(ROOT, 'harmonics/help', f'bsh_vergleich_{dt.date.today():%Y%m%d}.csv')
    open(aus, 'w', encoding='utf-8').write(kopf + '\n' + '\n'.join(zeilen) + '\n')
    for art in 'HN':
        m = {v: np.median([r[v][art][2] for _, r in ges]) for v in ('bsh', 'harm', 'neu')}
        hm = {v: np.median([100 * r[v][art][4] for _, r in ges]) for v in ('bsh', 'harm', 'neu')}
        besser = sum(r['neu'][art][2] < r['bsh'][art][2] for _, r in ges)
        print(f'{art}W Median Zeit-RMS: BSH {m["bsh"]:.1f}  Satz {m["harm"]:.1f}  neu {m["neu"]:.1f} min;  '
              f'Hoehe BSH {hm["bsh"]:.0f}  Satz {hm["harm"]:.0f}  neu {hm["neu"]:.0f} cm;  neu besser als BSH an {besser}/{len(ges)}')
    print('->', aus)


if __name__ == '__main__':
    main()
