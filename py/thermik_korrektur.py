#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Spot-Korrektur fuer die Live-Windvorhersage: Koeffizienten lernen + anwenden (25.11.2026).

Lernen (venv/bin/python py/thermik_korrektur.py [revier,...]):
  je Revier aus allen vorhandenen Sommern (Messung + Open-Meteo-Archiv, siehe thermik_pruefung/thermik_mehrjahre)
  mehrere Saetze  wind = a[Stunde] + sum(b_m * modell_m), 9-19 Uhr Ortszeit, Ridge wie korrektur_cv:
    kurz   alle Modelle, die live >= 36 h voraus rechnen (ICON-D2, AROME-HD ...)
    mittel Modelle >= 120 h (ICON-EU, ICON-CH2 ...)
    lang   Modelle >= 160 h (ECMWF, UKMO, GFS)
  Live gilt je Stunde der erste Satz, dessen Modelle alle Werte haben.
  -> static/wind_stations/korrektur.json

Anwenden: vorhersage(name) holt Open-Meteo live (30 min Zwischenspeicher) und rechnet korrigierte Stundenwerte.
Achtung: gelernt mit kurzem Vorlauf (Archiv = juengster Lauf); wie gut es bei 2-7 Tagen haelt, misst erst der
Sammler (tidal-sammler wind_vorhersagen, seit 25.11.2026).
"""
import datetime as dt
import json
import os
import sys
import time

import numpy as np
import pandas as pd
import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KOEFF = os.path.join(ROOT, 'static', 'wind_stations', 'korrektur.json')
SAMMEL = os.path.join(ROOT, 'quellen', 'thermik', 'vorhersagen')
REICHWEITE = (('kurz', 36), ('mittel', 120), ('lang', 160))
STUNDEN = list(range(9, 20))
MONATE = [5, 6, 7, 8, 9]   # nur Sommer gelernt: im Winter fehlt die Thermik, der Stundengang wuerde sie erfinden
                           # (Test 25.11.2026: Torbole +5-6 kn "Ora" im November)


def _live_reichweite():
    """Je Spot und Modell: wie viele Stunden ab 00 UTC rechnet es live (aus dem juengsten Sammlerabruf)."""
    import glob
    import gzip
    fs = sorted(glob.glob(os.path.join(SAMMEL, '*', '*.json.gz')))
    if not fs:
        fs = sorted(glob.glob(os.path.expanduser('~/tidal-sammler/wind_vorhersagen/*/*.json.gz')))
    js = json.load(gzip.open(fs[-1], 'rt'))
    return {s['name']: {m: v[0] + len(v[1]) for m, v in s['m'].items()} for s in js['spots']}


def lernen(argv):
    import thermik_pruefung as T
    import thermik_mehrjahre as MJ
    live = _live_reichweite()
    alt = json.load(open(KOEFF)) if os.path.exists(KOEFF) else {}
    wahl = [r for r in T.REVIERE if not argv or any(a.lower() in r[0].lower() for a in argv[0].split(','))]
    for r in wahl:
        name, tz = r[0], r[1]
        if name not in live:
            print('%-40s nicht im Sammler (spots.json) -- uebersprungen' % name)
            continue
        try:
            la, lo = (r[4], r[5]) if r[4] is not None else T._synop_ort(r[3])
            obs = T.messung(r)
        except Exception as e:                                         # noqa: BLE001
            print('%-40s keine Messung (%r)' % (name, e))
            continue
        jahre = [2026] + [j for j in (2023, 2024, 2025) if os.path.exists(
            os.path.join(T.Q, 'modelle', '%s_%d.json' % (r[3].replace(':', '_'), j)))]
        teile = []
        for j in jahre:
            mod = MJ.modelle_jahr(r, la, lo, j)
            x = pd.concat([obs[['sp']]] + [s.rename(m) for m, s in mod.items() if m != 'best_match'], axis=1, sort=True)
            x = x[(x.index >= pd.Timestamp('%d-05-01' % j, tz='UTC')) & (x.index < pd.Timestamp('%d-10-01' % j, tz='UTC'))]
            x = x[x['sp'].notna()]
            x['stunde'] = x.index.tz_convert(tz).hour
            teile.append(x[x['stunde'].isin(STUNDEN)])
        d = pd.concat(teile, sort=True)
        saetze = []
        for satz, h in REICHWEITE:
            ms = [m for m in T.MODELLE if m != 'best_match' and live[name].get(m, 0) >= h
                  and m in d and d[m].notna().mean() > 0.5]
            if not ms:
                continue
            x = d[['sp', 'stunde'] + ms].dropna()
            if len(x) < 300:
                continue
            st = sorted(set(x['stunde']))            # 3-stuendliche SYNOP: fehlende Stunden spaeter interpoliert
            A = MJ.matrix(x['stunde'], x[ms].values, st)
            b = MJ.lernen(A, x['sp'].values, len(st))
            res = np.clip(A @ b, 0, None) - x['sp'].values
            saetze.append(dict(satz=satz, modelle=ms, stunden=[int(v) for v in st], a=[round(v, 3) for v in b[:len(st)]],
                               b=[round(v, 4) for v in b[len(st):]], n=len(x),
                               mae_lern=round(float(np.abs(res).mean()), 2)))
        if saetze:
            alt[name] = dict(tz=tz, lat=la, lon=lo, stunden=STUNDEN, monate=MONATE, jahre=jahre, saetze=saetze)
            print('%-40s %s' % (name, '; '.join('%s %d Modelle MAE %.2f (n=%d)' % (
                s['satz'], len(s['modelle']), s['mae_lern'], s['n']) for s in saetze)))
    json.dump(alt, open(KOEFF, 'w'), ensure_ascii=False, indent=0)
    print('->', os.path.relpath(KOEFF, ROOT), '(%d Reviere)' % len(alt))


_CACHE = {}


def vorhersage(name):
    """Korrigierte Stundenwerte (9-19 Uhr Ortszeit) fuer die naechsten 7 Tage + best_match zum Vergleich."""
    k = json.load(open(KOEFF)).get(name)
    if not k:
        return None
    jetzt = time.time()
    if name in _CACHE and jetzt - _CACHE[name][0] < 1800:
        return _CACHE[name][1]
    ms = sorted({m for s in k['saetze'] for m in s['modelle']} | {'best_match'})
    h = requests.get('https://api.open-meteo.com/v1/forecast', timeout=60, params=dict(
        latitude=k['lat'], longitude=k['lon'], hourly='wind_speed_10m,wind_direction_10m,wind_gusts_10m',
        models=','.join(ms), forecast_days=7, wind_speed_unit='kn', timezone='GMT', cell_selection='nearest')).json()['hourly']
    t = pd.to_datetime(h['time']).tz_localize('UTC').tz_convert(k['tz'])
    stunden = []
    for i, ts in enumerate(t):
        if ts.hour not in k['stunden'] or ts < pd.Timestamp.now(tz=k['tz']).floor('h'):
            continue
        bm = h.get('wind_speed_10m_best_match', [None] * len(t))[i]
        wert, satz = None, None
        for s in (k['saetze'] if ts.month in k.get('monate', MONATE) else []):
            x = [h.get('wind_speed_10m_' + m, [None] * len(t))[i] for m in s['modelle']]
            if all(v is not None for v in x):
                a = float(np.interp(ts.hour, s['stunden'], s['a']))
                wert = max(0.0, a + float(np.dot(s['b'], x)))
                satz = s['satz']
                break
        stunden.append(dict(t=ts.strftime('%Y-%m-%dT%H:%M'), korr=None if wert is None else round(wert, 1),
                            satz=satz, best_match=None if bm is None else round(bm, 1),
                            ri=h.get('wind_direction_10m_best_match', [None] * len(t))[i],
                            boe=h.get('wind_gusts_10m_best_match', [None] * len(t))[i]))
    aus = dict(name=name, tz=k['tz'], abgerufen=dt.datetime.utcnow().strftime('%Y-%m-%dT%H:%MZ'),
               lernjahre=k['jahre'], monate=k.get('monate', MONATE), stunden=stunden)
    _CACHE[name] = (jetzt, aus)
    return aus


if __name__ == '__main__':
    lernen(sys.argv[1:])
