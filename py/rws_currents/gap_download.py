#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Phase B: bestes Jahr je Luecken-Station via ddlpy laden -> CSV (time,speed,direction)."""
import ddlpy, datetime, json, os, sys, urllib.request
import pandas as pd

CD = '/home/oliver/currents/Netherlands'
BASE = 'https://ddapi20-waterwebservices.rijkswaterstaat.nl/ONLINEWAARNEMINGENSERVICES/OphalenAantalWaarnemingen'

GAPS = ['maasmond.stroommeetpaal', 'ameland.nes', 'borndiep', 'egmondlander',
        'dantziggat.pietscheveplaat.zuid', 'holwerd.vaargeul',
        'haringvlietbrug.1', 'alblasserdam', 'dordrecht.dordtschekil']


def best_year(code, lon, lat):
    body = {"AquoMetadataLijst": [{"Grootheid": {"Code": "STROOMSHD"}}],
            "LocatieLijst": [{"X": lon, "Y": lat, "Code": code, "Coordinatenstelsel": "ETRS89"}],
            "Periode": {"Begindatumtijd": "2005-01-01T00:00:00.000+01:00",
                        "Einddatumtijd": "2027-01-01T00:00:00.000+01:00"},
            "Groeperingsperiode": "Jaar"}
    req = urllib.request.Request(BASE, data=json.dumps(body).encode(),
                                 headers={'Content-Type': 'application/json', 'X-API-KEY': 'dummy'})
    d = json.loads(urllib.request.urlopen(req, timeout=90).read())
    yc = {}
    for blk in d.get('AantalWaarnemingenPerPeriodeLijst', []):
        for m in blk.get('AantalMetingenPerPeriodeLijst', []):
            y = m['Groeperingsperiode'].get('Jaarnummer')
            if y:
                yc[y] = yc.get(y, 0) + m['AantalMetingen']
    if not yc:
        return None
    return max(yc, key=yc.get)


def dl(row, b, e):
    m = ddlpy.measurements(row, start_date=b, end_date=e)
    if m is None or len(m) == 0:
        return None
    return m[['Meetwaarde.Waarde_Numeriek']].rename(columns={'Meetwaarde.Waarde_Numeriek': 'v'})


def main():
    locs = ddlpy.locations()
    shd = locs[locs['Grootheid.Code'] == 'STROOMSHD']
    rtg = locs[locs['Grootheid.Code'] == 'STROOMRTG']
    meta = json.load(open(f'{CD}/_stations.json'))
    for code in GAPS:
        out = f'{CD}/GAP_{code}.csv'
        if os.path.exists(out) and os.path.getsize(out) > 2048:
            print(f'{code}: vorhanden, skip', flush=True); continue
        if code not in shd.index or code not in rtg.index:
            print(f'{code}: nicht in SHD/RTG-Katalog', flush=True); continue
        sr = shd.loc[[code]].iloc[0]; rr = rtg.loc[[code]].iloc[0]
        lon = float(sr['X']) if pd.notna(sr.get('X')) else meta.get(code, {}).get('lon', 4.0)
        lat = float(sr['Y']) if pd.notna(sr.get('Y')) else meta.get(code, {}).get('lat', 52.0)
        try:
            yr = best_year(code, lon, lat)
        except Exception as ex:
            print(f'{code}: best_year ERR {ex}', flush=True); continue
        if yr is None:
            print(f'{code}: keine Jahre', flush=True); continue
        b = datetime.datetime(yr, 1, 1)
        e = datetime.datetime(yr, 12, 31, 23, 59) if yr < 2026 else datetime.datetime(2026, 6, 27)
        print(f'{code}: bestes Jahr {yr} -> lade...', flush=True)
        try:
            s = dl(sr, b, e); r = dl(rr, b, e)
        except Exception as ex:
            print(f'{code}: download ERR {ex}', flush=True); continue
        if s is None or r is None:
            print(f'{code}: leer', flush=True); continue
        s.columns = ['speed']; r.columns = ['direction']
        s = s[~s.index.duplicated(keep='first')]; r = r[~r.index.duplicated(keep='first')]
        df = s.join(r, how='inner')
        df.index.name = 'time'
        df.to_csv(out)
        print(f'{code}: {len(df)} Werte ({yr}) -> {os.path.basename(out)}', flush=True)
    print('FERTIG', flush=True)


if __name__ == '__main__':
    main()
