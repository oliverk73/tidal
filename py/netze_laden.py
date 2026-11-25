#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Windreihen weiterer amtlicher Netze laden, Sommer (Mai-Sep) 2023-2026 (25.11.2026).

Ausgabe wie py/spotsuche_laden.py: quellen/thermik/<netz>/<id>.csv mit Spalten t (UTC, Intervallmitte), kn, grad.
  smhi        SMHI Open Data metobs, Parameter 4 (Wind 10-min-Mittel, 1x/h, m/s) + 3 (Richtung);
              corrected-archive (bis ~3 Monate zurueck) + latest-months. Stempel = Ende des 10-min-Mittels.
  rws         Rijkswaterstaat Waterwebservices (DD-API 2.0), WINDSHD/WINDRTG 10 min, m/s, Zeit in MEZ (+01:00,
              ohne Sommerzeit, steht im Stempel). Stempel = Ende des 10-min-Mittels.
  meteireann  Met Eireann hly<stn>.zip (cli.fusio.net): wdsp in kn, wddir; Stundenwert der vollen Stunde.

    venv/bin/python py/netze_laden.py <netz> <id> [<id> ...]
"""
import io
import os
import sys
import time
import zipfile

import numpy as np
import pandas as pd
import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
Q = os.path.join(ROOT, 'quellen', 'thermik')
MS_KN = 1.943844
UA = {'User-Agent': 'weather-tides/1.0'}
JAHRE = (2023, 2024, 2025, 2026)


def _sommer(t):
    return t.dt.month.between(5, 9) & t.dt.year.isin(JAHRE)


def _speichern(netz, i, t, kn, grad):
    d = pd.DataFrame({'t': t, 'kn': kn, 'grad': grad}).dropna()
    d = d[_sommer(d['t'])].drop_duplicates('t').sort_values('t')
    os.makedirs(os.path.join(Q, netz), exist_ok=True)
    d.assign(t=d['t'].dt.strftime('%Y-%m-%dT%H:%MZ')).to_csv(os.path.join(Q, netz, '%s.csv' % i), index=False)
    return len(d)


def _get(url, **kw):
    for v in range(4):
        try:
            r = requests.get(url, headers=UA, timeout=300, **kw)
            if r.status_code in (200, 404):
                return r
        except requests.RequestException:
            pass
        time.sleep(5 * (v + 1))
    raise RuntimeError('kein Abruf: ' + url)


def _smhi_param(i, p):
    teile = []
    for periode in ('corrected-archive', 'latest-months'):
        r = _get('https://opendata-download-metobs.smhi.se/api/version/1.0/parameter/%d/station/%s/period/%s/data.csv'
                 % (p, i, periode))
        if r.status_code != 200:
            continue
        zeilen = r.content.decode('utf-8-sig').splitlines()
        k = next((n for n, z in enumerate(zeilen) if z.startswith('Datum;')), None)
        if k is None:
            continue
        x = pd.read_csv(io.StringIO('\n'.join(z.split(';;')[0] for z in zeilen[k:])), sep=';')
        x['t'] = pd.to_datetime(x['Datum'] + ' ' + x['Tid (UTC)'])
        teile.append(x.set_index('t').iloc[:, 2])
    if not teile:
        return pd.Series(dtype=float)
    s = pd.concat(teile)
    return s[~s.index.duplicated(keep='last')]


def smhi(i):
    sp, ri = _smhi_param(i, 4), _smhi_param(i, 3)
    d = pd.DataFrame({'sp': sp, 'ri': ri}).dropna()
    t = pd.Series(d.index - pd.Timedelta(minutes=5))
    return _speichern('smhi', i, t, d['sp'].values * MS_KN, d['ri'].values)


RWS = 'https://ddapi20-waterwebservices.rijkswaterstaat.nl/ONLINEWAARNEMINGENSERVICES/OphalenWaarnemingen'


def _rws_reihe(code, grootheid, a, b):
    body = {"Locatie": {"Code": code},
            "AquoPlusWaarnemingMetadata": {"AquoMetadata": {"Compartiment": {"Code": "LT"}, "Grootheid": {"Code": grootheid}}},
            "Periode": {"Begindatumtijd": a + "T00:00:00.000+00:00", "Einddatumtijd": b + "T00:00:00.000+00:00"}}
    for v in range(4):
        try:
            r = requests.post(RWS, json=body, timeout=300, headers=UA)
            if r.status_code == 204:
                return {}
            j = r.json()
            break
        except (requests.RequestException, ValueError):
            time.sleep(5 * (v + 1))
    else:
        raise RuntimeError('RWS %s %s %s' % (code, grootheid, a))
    out = {}
    for w in j.get('WaarnemingenLijst', []):
        if (w['AquoMetadata'].get('Hoedanigheid') or {}).get('Code') not in ('NVT', 'WARNDN', None):
            continue                                       # MSL (Hoehe ueber Meer) nur wenn nichts anderes da ist
        for m in w['MetingenLijst']:
            v = (m.get('Meetwaarde') or {}).get('Waarde_Numeriek')
            if v is not None and v < 1e6:
                out[m['Tijdstip']] = v
    return out


def rws(code):
    sp, ri = {}, {}
    for j in JAHRE:
        for a, b in (('%d-05-01' % j, '%d-06-01' % j), ('%d-06-01' % j, '%d-07-01' % j), ('%d-07-01' % j, '%d-08-01' % j),
                     ('%d-08-01' % j, '%d-09-01' % j), ('%d-09-01' % j, '%d-10-01' % j)):
            sp.update(_rws_reihe(code, 'WINDSHD', a, b))
            ri.update(_rws_reihe(code, 'WINDRTG', a, b))
    t = sorted(set(sp) & set(ri))
    if not t:
        return 0
    tt = pd.Series(pd.to_datetime(t, utc=True).tz_localize(None)) - pd.Timedelta(minutes=5)
    return _speichern('rws', code, tt, np.array([sp[x] for x in t]) * MS_KN, np.array([ri[x] for x in t]))


def meteireann(i):
    r = _get('https://cli.fusio.net/cli/climate_data/webdata/hly%s.zip' % i)
    if r.status_code != 200:
        return 0
    z = zipfile.ZipFile(io.BytesIO(r.content))
    zeilen = z.open(z.namelist()[0]).read().decode('latin-1').splitlines()
    k = next(n for n, x in enumerate(zeilen) if x.startswith('date,'))
    d = pd.read_csv(io.StringIO('\n'.join(zeilen[k:])), low_memory=False)
    d['t'] = pd.to_datetime(d['date'], format='%d-%b-%Y %H:%M')
    d['wdsp'] = pd.to_numeric(d['wdsp'], errors='coerce')
    d['wddir'] = pd.to_numeric(d['wddir'], errors='coerce')
    return _speichern('meteireann', i, d['t'], d['wdsp'], d['wddir'])


DWDS = 'https://opendata.dwd.de/climate_environment/CDC/observations_germany/climate/hourly/wind_synop/'


def _dwd_zip(url):
    r = _get(url)
    if r.status_code != 200:
        return None
    z = zipfile.ZipFile(io.BytesIO(r.content))
    p = next(n for n in z.namelist() if n.startswith('produkt'))
    d = pd.read_csv(z.open(p), sep=';', skipinitialspace=True)
    return d[(d['FF'] >= 0) & (d['DD'] >= 0)]


def dwd_synop(i):
    """DWD Stundenwerte Wind aus SYNOP (hourly/wind_synop): FF m/s (ganze m/s), DD; Stempel = Termin (10-min-Mittel davor)."""
    i = '%05d' % int(i)
    teile = []
    liste = _get(DWDS + 'historical/').text
    import re
    for name in sorted(set(re.findall(r'stundenwerte_F_%s_\d{8}_(\d{8})_hist\.zip' % i, liste))):
        if name >= '20230501':
            f = re.search(r'stundenwerte_F_%s_\d{8}_%s_hist\.zip' % (i, name), liste).group(0)
            teile.append(_dwd_zip(DWDS + 'historical/' + f))
    teile.append(_dwd_zip(DWDS + 'recent/stundenwerte_F_%s_akt.zip' % i))
    d = pd.concat([x for x in teile if x is not None])
    t = pd.to_datetime(d['MESS_DATUM'].astype(str), format='%Y%m%d%H') - pd.Timedelta(minutes=5)
    return _speichern('dwd_synop', i, t.reset_index(drop=True), d['FF'].values * MS_KN, d['DD'].values)


def main(argv):
    netz, ids = argv[0], argv[1:]
    f = {'smhi': smhi, 'rws': rws, 'meteireann': meteireann, 'dwd_synop': dwd_synop}[netz]
    for i in ids:
        try:
            print(netz, i, f(i), 'Werte', flush=True)
        except Exception as e:                             # noqa: BLE001
            print(netz, i, 'FEHLER', repr(e)[:200], flush=True)


if __name__ == '__main__':
    main(sys.argv[1:])
