#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Harmonische Konstanten aus NAMRIAs PH-TIDES-Vorhersage (Philippinen).

Die Web-App phtides.namria.gov.ph verlangt eine Anmeldung, ihre Schnittstelle
nicht (gefunden in der Android-App, api/apk-v1):

  api/locations                          alle Stationen (id, code, name)
  api/locations/<id>                     Stationsblatt, Position in Grad/Min/Sek
  api/predicted_hourly_heights/<id>      Stundenwerte des laufenden Jahres
  api/downloads/locations/hourly-heights/secondary   Nebenpegel (22.09.2026: leer)

Zeit: Tafelzeit = UTC+8 (PHT). Am vorhandenen Satz Baler geprueft: mit UTC+8
1.3 cm Rest, mit UTC+7/+9 rund 20 cm. Hoehen ueber MLLW wie die uebrigen
NAMRIA-Saetze; Z0 = Mittel der Vorhersage.

Fit wie bei allen Ein-Jahres-Tafeln: SA/SSA erzwungen, Rayleigh_min 0.9
(sonst fallen SA sowie T2/R2 heraus, siehe py/jahrestide_nachfitten.py).

Ausgabe: water_levels/Philippines_NAMRIA/<id>_<Name>_hourly.json und ein Satz
je Station auf stdout (bzw. --anhaengen an harmonics_utide_tidetables.txt).

Usage: python3 py/fit_namria_phtides.py <id> [<id> ...] [--anhaengen]
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys
import urllib.request
import warnings

import numpy as np
import utide

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import xtide_modell as X                                           # noqa: E402
from health_check import ROOT                                      # noqa: E402

warnings.filterwarnings('ignore')
API = 'https://phtides.namria.gov.ph/api'
UA = 'Mozilla/5.0'
ZIEL = os.path.join(ROOT, 'water_levels/Philippines_NAMRIA')
DATEI = os.path.join(ROOT, 'harmonics/utide/harmonics_utide_tidetables.txt')
PHT = dt.timedelta(hours=8)
# NAMRIA-Namen, die Google Maps nicht findet ("KIG" = Kalayaan Island Group)
NAMEN = {31: 'Pag-asa Island (Kalayaan), Palawan'}


def holen(pfad):
    req = urllib.request.Request(f'{API}/{pfad}', headers={'User-Agent': UA})
    return json.load(urllib.request.urlopen(req, timeout=120))


def grad(s):
    """11° 3' 13" N -> 11.0536"""
    g, m, sek, h = re.match(r"\s*(\d+)\D+(\d+)\D+([\d.]+)\D+([NSEW])", s).groups()
    w = int(g) + int(m) / 60 + float(sek) / 3600
    return -w if h in 'SW' else w


def satz(lid):
    st = holen(f'locations/{lid}')
    werte = holen(f'predicted_hourly_heights/{lid}')
    name_datei = re.sub(r'[^A-Za-z0-9]+', '_', st['name']).strip('_')
    json.dump(werte, open(os.path.join(ZIEL, f"{lid:02d}_{name_datei}_hourly.json"), 'w'))
    t, h = [], []
    for x in werte:
        m, d, y = map(int, x['date'].split('/'))
        t.append(dt.datetime(y, m, d) + dt.timedelta(hours=int(x['hour'].split(':')[0])) - PHT)
        h.append(float(x['tide']))
    t, h = np.array(t), np.array(h)
    lat, lon = grad(st['coordinates_lat']), grad(st['coordinates_long'])
    c = utide.solve(t, h, lat=lat, nodal=True, trend=False, method='ols', conf_int='none',
                    constit='auto', Rayleigh_min=0.9, verbose=False)
    if 'SA' not in c.name:
        c = utide.solve(t, h, lat=lat, nodal=True, trend=False, method='ols', conf_int='none',
                        constit=list(c.name) + ['SA', 'SSA'], verbose=False)
    rest = h - utide.reconstruct(t, c, verbose=False).h
    rms = float(np.sqrt(np.mean(rest ** 2)))
    k = {n: (a, g) for n, a, g in zip(c.name, c.A, c.g)}
    namen, _sp, _a, _f = X.kopf_lesen(DATEI)
    heute = dt.date.today().strftime('%Y%m%d')
    zeilen = ['# BEGIN HOT COMMENTS', '# country: Philippines',
              '# source: Derived from NAMRIA PH TIDES predictions with UTide harmonic analysis',
              f"# station_id_context: NAMRIA-{st['code']}", f'# date_imported: {heute}',
              '# datum: MLLW', '# confidence: 7', f"# namria_code: {st['code']}",
              f"# note: {st.get('location') or st['name']}; api/predicted_hourly_heights/{lid},"
              f" Tafelzeit UTC+8 (py/fit_namria_phtides.py)",
              f'# utide: period={t[0]:%Y-%m-%d}..{t[-1]:%Y-%m-%d} rms={rms:.4f}m const={len(c.name)}',
              '# !units: meters', f'# !longitude: {lon:.6f}', f'# !latitude: {lat:.6f}',
              f"{NAMEN.get(lid, st['name'])}, Philippines", '+00:00 :Asia/Manila', f'{c.mean:.4f} meters']
    for x in namen:
        zeilen.append(f'{x:<16}{k[x][0]:.4f}  {k[x][1] % 360:.2f}' if x in k and k[x][0] >= 0.00005
                      else 'x 0 0')
    print(f"  {lid} {st['name']}: {len(h)} Werte, Rest {rms * 1000:.1f} mm, {len(c.name)} Tiden,"
          f" M2 {k['M2'][0]:.3f} m", file=sys.stderr)
    return '\n'.join(zeilen)


def main(argv):
    ids = [int(a) for a in argv if a.isdigit()]
    bloecke = [satz(i) for i in ids]
    if '--anhaengen' in argv:
        with open(DATEI, 'a', encoding='iso-8859-1') as fh:
            fh.write('\n'.join(bloecke) + '\n')
        print(f'-> {len(bloecke)} Saetze an {os.path.relpath(DATEI, ROOT)} angehaengt', file=sys.stderr)
    else:
        print('\n'.join(bloecke))


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
