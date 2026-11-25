#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Korrektur je Revier aus mehreren Sommern lernen und an einem unbekannten Sommer pruefen (25.11.2026).

thermik_pruefung.py lernt nur innerhalb von Mai-Sep 2026 (Kreuzvalidierung ueber Monate). Hier:
Korrektur (Stundengang + Modellfaktor, wie dort) aus den Sommern LERN gelernt, getestet am Sommer TEST -
so wie sie spaeter live laufen wuerde. Nur Modelle, die es in allen Jahren gibt (Open-Meteo Historical
Forecast: ICON-D2/EU, AROME-HD, ECMWF, UKMO, GFS ab 2023; ICON-CH1 erst ab 2025).

    venv/bin/python py/thermik_mehrjahre.py Torbole [2023,2024,2025 2026]
      -> harmonics/help/thermik_mehrjahre.csv
"""
import json
import os
import sys
import time

import numpy as np
import pandas as pd
import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import thermik_pruefung as T  # noqa: E402

AUS = os.path.join(T.ROOT, 'harmonics', 'help', 'thermik_mehrjahre.csv')


def modelle_jahr(r, la, lo, jahr):
    if jahr == 2026:
        return {m: d['sp'] for m, d in T.modelle(r, la, lo).items()}
    pfad = os.path.join(T.Q, 'modelle', '%s_%d.json' % (r[3].replace(':', '_'), jahr))
    if not os.path.exists(pfad):
        for _v in range(5):
            js = requests.get('https://historical-forecast-api.open-meteo.com/v1/forecast', timeout=300, params=dict(
                latitude=la, longitude=lo, hourly='wind_speed_10m,wind_direction_10m', models=','.join(T.MODELLE),
                start_date='%d-05-01' % jahr, end_date='%d-09-30' % jahr, wind_speed_unit='kn', timezone='GMT',
                cell_selection='nearest')).json()
            if 'limit exceeded' not in str(js.get('reason', '')):
                break
            time.sleep(65)
        if 'hourly' not in js:
            raise RuntimeError(js)
        json.dump(js, open(pfad, 'w'))
    h = json.load(open(pfad))['hourly']
    t = pd.to_datetime(h['time']).tz_localize('UTC')
    out = {}
    for m in T.MODELLE:
        sp = h.get('wind_speed_10m_' + m)
        if sp is not None and pd.Series(sp, dtype=float).notna().mean() > 0.8:
            out[m] = pd.Series(np.array(sp, float), index=t)
    return out


def matrix(stunde, X, stunden):
    H = np.array([[1.0 if s == k else 0.0 for k in stunden] for s in stunde])
    return np.hstack([H, X])


def lernen(A, y, n_h):
    lam = np.eye(A.shape[1])
    lam[:n_h, :n_h] = 0
    return np.linalg.solve(A.T @ A + lam, A.T @ y)


def main(argv):
    r = [x for x in T.REVIERE if argv[0].lower() in x[0].lower()][0]
    lern = [int(j) for j in (argv[1] if len(argv) > 1 else '2023,2024,2025').split(',')]
    test = int(argv[2]) if len(argv) > 2 else 2026
    name, tz = r[0], r[1]
    la, lo = r[4], r[5]
    if la is None:
        la, lo = T._synop_ort(r[3])
    obs = T.messung(r)
    mod = {j: modelle_jahr(r, la, lo, j) for j in lern + [test]}
    gemeinsam = [m for m in T.MODELLE if all(m in mod[j] for j in mod) and m != 'best_match']
    print('%s: Lernsommer %s, Test %d; Modelle in allen Jahren: %s'
          % (name, lern, test, ', '.join(T.KURZ[m] for m in gemeinsam)))

    teile = []
    for j in lern + [test]:
        x = pd.concat([obs[['sp']]] + [mod[j][m].rename(m) for m in gemeinsam], axis=1, sort=True)
        x = x[(x.index >= pd.Timestamp('%d-05-01' % j, tz='UTC')) & (x.index < pd.Timestamp('%d-10-01' % j, tz='UTC'))]
        lk = x.index.tz_convert(tz)
        x = x[(lk.hour >= 9) & (lk.hour <= 19)].dropna()
        x['jahr'] = j
        x['stunde'] = x.index.tz_convert(tz).hour
        x['monat'] = x.index.tz_convert(tz).month
        teile.append(x)
        print('  %d: %4d Stunden, Messmittel %.1f kn, %d h >= 12 kn' % (j, len(x), x['sp'].mean(), (x['sp'] >= 12).sum()))
    d = pd.concat(teile)
    tr, te = d[d['jahr'].isin(lern)], d[d['jahr'] == test]
    stunden = sorted(set(d['stunde']))
    zeilen = []
    for m in gemeinsam + ['mischung']:
        cols = gemeinsam if m == 'mischung' else [m]
        label = 'Mischung (%d)' % len(cols) if m == 'mischung' else T.KURZ[m]
        roh = te[cols].mean(axis=1).values
        b = lernen(matrix(tr['stunde'], tr[cols].values, stunden), tr['sp'].values, len(stunden))
        vor = np.clip(matrix(te['stunde'], te[cols].values, stunden) @ b, 0, None)
        innen = T.korrektur_cv(te[cols].values, te['sp'].values, te['monat'].values, te['stunde'].values)
        ok = np.isfinite(innen)
        o = te['sp'].values
        k_roh = T.kennzahlen(o, roh, o, o)
        k_vor = T.kennzahlen(o, vor, o, o)
        k_in = T.kennzahlen(o[ok], innen[ok], o[ok], o[ok])
        zeilen.append(dict(revier=name, modell=label, lern=','.join(map(str, lern)), test=test, n=k_vor['n'],
                           roh_bias=k_roh['bias_kn'], roh_mae=k_roh['mae_kn'], roh_pod12=k_roh['pod12'],
                           vorjahre_bias=k_vor['bias_kn'], vorjahre_mae=k_vor['mae_kn'],
                           vorjahre_pod12=k_vor['pod12'], vorjahre_far12=k_vor['far12'],
                           nur_testjahr_mae=k_in['mae_kn'], nur_testjahr_pod12=k_in['pod12'],
                           nur_testjahr_far12=k_in['far12']))
    z = pd.DataFrame(zeilen).sort_values('vorjahre_mae')
    print('\n  %-22s | roh: %5s %5s %4s | aus Vorjahren: %5s %5s %4s %4s | nur %d (CV): %5s %4s %4s'
          % ('Modell', 'Bias', 'MAE', 'POD', 'Bias', 'MAE', 'POD', 'FAR', test, 'MAE', 'POD', 'FAR'))
    for _, x in z.iterrows():
        print('  %-22s | %+9.1f %5.2f %4.2f | %+20.1f %5.2f %4.2f %4.2f | %16.2f %4.2f %4.2f'
              % (x['modell'], x['roh_bias'], x['roh_mae'], x['roh_pod12'], x['vorjahre_bias'], x['vorjahre_mae'],
                 x['vorjahre_pod12'], x['vorjahre_far12'], x['nur_testjahr_mae'], x['nur_testjahr_pod12'],
                 x['nur_testjahr_far12']))
    if os.path.exists(AUS):
        alt = pd.read_csv(AUS)
        z = pd.concat([alt[alt['revier'] != name], z], ignore_index=True)
    z.to_csv(AUS, index=False)
    print('\n->', os.path.relpath(AUS, T.ROOT))


if __name__ == '__main__':
    main(sys.argv[1:])
