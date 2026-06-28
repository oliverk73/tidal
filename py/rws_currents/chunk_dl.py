#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ameland.nes (2011) + borndiep (2008): ADCP-Multi-Bin -> in 10-Tage-Bloecken laden
(Request-Limit 263088). ~5 Monate, reicht fuer Stroemungs-UTide."""
import ddlpy, datetime, os
import pandas as pd

CD = '/home/oliver/currents/Netherlands'
TASKS = [('ameland.nes', 2011), ('borndiep', 2008)]


def dl(row, b, e):
    m = ddlpy.measurements(row, start_date=b, end_date=e)
    if m is None or len(m) == 0:
        return None
    s = m[['Meetwaarde.Waarde_Numeriek']].rename(columns={'Meetwaarde.Waarde_Numeriek': 'v'})
    return s[~s.index.duplicated(keep='first')]


def main():
    locs = ddlpy.locations()
    shd = locs[locs['Grootheid.Code'] == 'STROOMSHD']
    rtg = locs[locs['Grootheid.Code'] == 'STROOMRTG']
    for code, yr in TASKS:
        out = f'{CD}/GAP_{code}.csv'
        if os.path.exists(out) and os.path.getsize(out) > 4096:
            print(f'{code}: vorhanden, skip', flush=True); continue
        sr = shd.loc[[code]].iloc[0]; rr = rtg.loc[[code]].iloc[0]
        parts = []
        d = datetime.datetime(yr, 3, 1)
        end = datetime.datetime(yr, 8, 1)
        while d < end:
            d2 = min(d + datetime.timedelta(days=10), end)
            try:
                s = dl(sr, d, d2); r = dl(rr, d, d2)
            except Exception as ex:
                print(f'  {code} {d:%Y-%m-%d}: ERR {str(ex)[:60]}', flush=True)
                d = d2; continue
            if s is not None and r is not None:
                s.columns = ['speed']; r.columns = ['direction']
                m = s.join(r, how='inner')
                if len(m):
                    parts.append(m)
            print(f'  {code} {d:%m-%d}: {0 if not parts else len(parts[-1])}', flush=True)
            d = d2
        if parts:
            df = pd.concat(parts).sort_index()
            df = df[~df.index.duplicated(keep='first')]
            df.index.name = 'time'
            df.to_csv(out)
            print(f'{code}: {len(df)} Werte -> {os.path.basename(out)}', flush=True)
        else:
            print(f'{code}: KEINE Daten', flush=True)
    print('CHUNK FERTIG', flush=True)


if __name__ == '__main__':
    main()
