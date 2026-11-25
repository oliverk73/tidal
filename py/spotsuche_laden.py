#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sommerwind (Mai-Sep) der Kuestenstationen laden und bewerten (25.11.2026), fuer die Auswahl neuer Testreviere.

Eingabe quellen/thermik/spotsuche/kuestenstationen.csv (py/spotsuche.py + Landmaske).
Rohdaten je Netz (UTC, kn, Grad) -> quellen/thermik/<netz>/<id>.csv mit Spalten t,kn,grad:
  knmi  uurgegevens FH/DD (Stundenmittel, Stempel = Ende der Stunde)
  dwd   10-min FF_10/DD_10 (recent-Zip)
  dmi   metObs wind_speed/wind_dir (10 min)
  coops datagetter product=wind interval=h (Stundenwert)
  meteofrance  aus den Departementsdateien (Stundenmittel FF/DD, Stempel = Ende der Stunde)
Ausgabe harmonics/help/spotsuche_kandidaten.csv: je Station Abdeckung, Mittel 9-19 Uhr (Sonnenzeit ~ UTC+lon/15),
Stunden >= 12 kn, Anteil Wasser im Umkreis.
    venv/bin/python py/spotsuche_laden.py [netz,...]
"""
import glob
import io
import json
import os
import sys
import time
import zipfile

import numpy as np
import pandas as pd
import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
Q = os.path.join(ROOT, 'quellen', 'thermik')
AUS = os.path.join(ROOT, 'harmonics', 'help', 'spotsuche_kandidaten.csv')
VON, BIS = '2026-05-01', '2026-10-01'
MS_KN = 1.943844
UA = {'User-Agent': 'weather-tides/1.0'}


def _pfad(netz, i):
    os.makedirs(os.path.join(Q, netz), exist_ok=True)
    return os.path.join(Q, netz, '%s.csv' % i)


def knmi(ids):
    r = requests.post('https://www.daggegevens.knmi.nl/klimatologie/uurgegevens', timeout=600, data=dict(
        stns=':'.join(ids), vars='DD:FH', start='2026050101', end='2026100124'))
    z = [l for l in r.text.splitlines() if l and not l.startswith('#')]
    d = pd.read_csv(io.StringIO('\n'.join(z)), header=None, names=['stn', 'dat', 'hh', 'dd', 'fh'], skipinitialspace=True)
    d['t'] = pd.to_datetime(d['dat'].astype(str), format='%Y%m%d') + pd.to_timedelta(d['hh'], 'h') - pd.Timedelta(minutes=30)
    for s, g in d.groupby('stn'):
        g = g[(g['dd'] > 0) & (g['dd'] <= 360) | (g['fh'] == 0)]
        pd.DataFrame({'t': g['t'].dt.strftime('%Y-%m-%dT%H:%MZ'), 'kn': g['fh'] / 10 * MS_KN,
                      'grad': g['dd'].where(g['dd'] <= 360)}).to_csv(_pfad('knmi', '%03d' % s), index=False)


def dwd(i):
    url = 'https://opendata.dwd.de/climate_environment/CDC/observations_germany/climate/10_minutes/wind/recent/10minutenwerte_wind_%05d_akt.zip' % int(i)
    r = requests.get(url, timeout=300, headers=UA)
    if r.status_code != 200:
        return
    z = zipfile.ZipFile(io.BytesIO(r.content))
    d = pd.read_csv(z.open(z.namelist()[0]), sep=';', skipinitialspace=True)
    d['t'] = pd.to_datetime(d['MESS_DATUM'].astype(str), format='%Y%m%d%H%M') - pd.Timedelta(minutes=5)
    d = d[(d['FF_10'] >= 0) & (d['DD_10'] >= 0)]
    d = d[(d['t'] >= VON) & (d['t'] < BIS)]
    pd.DataFrame({'t': d['t'].dt.strftime('%Y-%m-%dT%H:%MZ'), 'kn': d['FF_10'] * MS_KN, 'grad': d['DD_10']}).to_csv(
        _pfad('dwd', '%05d' % int(i)), index=False)


def dmi(i):
    werte = {}
    for par in ('wind_speed', 'wind_dir'):
        url = 'https://opendataapi.dmi.dk/v2/metObs/collections/observation/items'
        p = dict(stationId=i, parameterId=par, datetime='%sT00:00:00Z/%sT00:00:00Z' % (VON, BIS), limit=300000)
        for _v in range(5):
            r = requests.get(url, params=p, timeout=300, headers=UA)
            if r.status_code != 429:
                break
            time.sleep(20)
        if r.status_code != 200:
            return
        werte[par] = {f['properties']['observed']: f['properties']['value'] for f in r.json().get('features', [])}
    t = sorted(set(werte['wind_speed']) & set(werte['wind_dir']))
    if not t:
        return
    d = pd.DataFrame({'t': pd.to_datetime(t).tz_localize(None) - pd.Timedelta(minutes=5),
                      'kn': [werte['wind_speed'][x] * MS_KN for x in t], 'grad': [werte['wind_dir'][x] for x in t]})
    d['t'] = d['t'].dt.strftime('%Y-%m-%dT%H:%MZ')
    d.to_csv(_pfad('dmi', i), index=False)


def coops(i):
    teile = []
    for a, b in (('20260501', '20260731'), ('20260801', '20260930')):
        r = requests.get('https://api.tidesandcurrents.noaa.gov/api/prod/datagetter', timeout=300, headers=UA, params=dict(
            product='wind', station=i, begin_date=a, end_date=b, interval='h', units='english', time_zone='gmt',
            format='json', application='weather-tides'))
        js = r.json()
        for x in js.get('data', []):
            try:
                teile.append((x['t'].replace(' ', 'T') + 'Z', float(x['s']), float(x['d'])))
            except (ValueError, KeyError):
                pass
    if teile:
        pd.DataFrame(teile, columns=['t', 'kn', 'grad']).to_csv(_pfad('coops', i), index=False)


def meteofrance(ids):
    ids = set(ids)
    for f in sorted(glob.glob(os.path.join(Q, 'meteofrance', 'H_*_latest-2025-2026.csv.gz'))):
        d = pd.read_csv(f, sep=';', usecols=['NUM_POSTE', 'AAAAMMJJHH', 'FF', 'DD'], dtype={'NUM_POSTE': str})
        d = d[d['NUM_POSTE'].isin(ids) & d['FF'].notna() & d['DD'].notna()]
        d['t'] = pd.to_datetime(d['AAAAMMJJHH'].astype(str), format='%Y%m%d%H') - pd.Timedelta(minutes=5)  # FF = 10-min-Mittel bis zur vollen Stunde
        for s, g in d.groupby('NUM_POSTE'):
            pd.DataFrame({'t': g['t'].dt.strftime('%Y-%m-%dT%H:%MZ'), 'kn': g['FF'] * MS_KN, 'grad': g['DD']}).to_csv(
                _pfad('meteofrance', s), index=False)


def bewerten(k):
    z = []
    for _, s in k.iterrows():
        p = os.path.join(Q, s['netz'], '%s.csv' % s['id'])
        if not os.path.exists(p):
            continue
        d = pd.read_csv(p)
        if not len(d):
            continue
        t = pd.to_datetime(d['t'].str.rstrip('Z'))
        d = d.set_index(t)
        h = d['kn'].resample('1h').mean()
        h = h[(h.index >= VON) & (h.index < BIS)].dropna()
        sonne = (h.index + pd.to_timedelta(s['lon'] / 15, 'h')).hour       # Sonnenzeit
        tag = h[(sonne >= 9) & (sonne <= 18)]
        z.append(dict(netz=s['netz'], id=s['id'], name=s['name'], lat=s['lat'], lon=s['lon'], alt=s.get('alt'),
                      wasser1=s['wasser1'], wasser3=s['wasser3'], stunden=len(tag),
                      abdeckung=round(len(tag) / (153 * 10), 2), mittel_kn=round(tag.mean(), 1),
                      h12=int((tag >= 12).sum()), h15=int((tag >= 15).sum())))
    return pd.DataFrame(z)


def main(argv):
    k = pd.read_csv(os.path.join(Q, 'spotsuche', 'kuestenstationen.csv'), dtype={'id': str})
    netze = argv[0].split(',') if argv else ['knmi', 'meteofrance', 'dwd', 'coops', 'dmi']
    for n in netze:
        ids = k[k['netz'] == n]['id'].tolist()
        print(n, len(ids), 'Stationen', flush=True)
        if n == 'knmi':
            knmi(ids)
        elif n == 'meteofrance':
            meteofrance(ids)
        else:
            for i in ids:
                if os.path.exists(_pfad(n, '%05d' % int(i) if n == 'dwd' else i)):
                    continue
                try:
                    {'dwd': dwd, 'dmi': dmi, 'coops': coops}[n](i)
                except Exception as e:                             # noqa: BLE001
                    print('  ', n, i, repr(e)[:150], flush=True)
                time.sleep(0.5)
    k.loc[k['netz'] == 'dwd', 'id'] = k.loc[k['netz'] == 'dwd', 'id'].map(lambda x: '%05d' % int(x))
    k.loc[k['netz'] == 'knmi', 'id'] = k.loc[k['netz'] == 'knmi', 'id'].map(lambda x: '%03d' % int(x))
    b = bewerten(k).sort_values('h12', ascending=False)
    b.to_csv(AUS, index=False)
    print('->', os.path.relpath(AUS, ROOT), len(b))


if __name__ == '__main__':
    main(sys.argv[1:])
