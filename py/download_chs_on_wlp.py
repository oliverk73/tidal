#!/usr/bin/env python3
"""
Download WLP (Water Level Predictions) from CHS IWLS API for Ontario
James/Hudson Bay coast stations (no Great Lakes).
"""
import os, json, time, datetime, sys, requests
import pandas as pd

API_BASE = 'https://api-sine.dfo-mpo.gc.ca/api/v1'
OUTPUT_DIR = '/home/oliver/water_levels/Canada_IWLS_ON'
CATALOG_PATH = os.path.join(OUTPUT_DIR, '_on_stations.json')
RESOLUTION = 'FIFTEEN_MINUTES'
START_DATE = '2025-01-01'
END_DATE = '2025-12-31'

ON_CODES = ['04730','04740','04780','04790','04800','04810','04840','04880','04920']


def build_catalog():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    if os.path.exists(CATALOG_PATH):
        with open(CATALOG_PATH) as f:
            return json.load(f)
    print("Fetching IWLS station catalog…")
    r = requests.get(f'{API_BASE}/stations', timeout=60)
    all_st = r.json()
    sel = []
    for s in all_st:
        if s['code'] in ON_CODES:
            sel.append({
                'code': s['code'],
                'name': s['officialName'],
                'lat': s['latitude'],
                'lon': s['longitude'],
                'id': s['id'],
            })
    sel.sort(key=lambda x: x['code'])
    with open(CATALOG_PATH, 'w') as f:
        json.dump(sel, f, indent=2)
    return sel


def download_wlp(station):
    code = station['code']
    name = station['name']
    sid = station['id']
    safe = code + '_' + name.replace(' ', '_').replace('/', '_').replace("'", '').replace('.', '').replace('#', '')
    csv_path = os.path.join(OUTPUT_DIR, f'{safe}_wlp.csv')
    if os.path.exists(csv_path) and os.path.getsize(csv_path) > 5000:
        n = sum(1 for _ in open(csv_path)) - 1
        print(f"  vorhanden ({n} Werte)")
        return True

    start = datetime.date.fromisoformat(START_DATE)
    end = datetime.date.fromisoformat(END_DATE)
    months = []
    cur = start.replace(day=1)
    while cur <= end:
        nxt = (cur.replace(day=28) + datetime.timedelta(days=4)).replace(day=1)
        months.append((cur, min(nxt - datetime.timedelta(days=1), end)))
        cur = nxt

    rows = []
    empty = 0
    for a, b in months:
        try:
            r = requests.get(f'{API_BASE}/stations/{sid}/data',
                params={'time-series-code':'wlp','from':f'{a}T00:00:00Z','to':f'{b}T23:59:59Z','resolution':RESOLUTION},
                timeout=20)
            if r.status_code == 429:
                time.sleep(10); continue
            if r.status_code == 200:
                d = r.json()
                if isinstance(d, list) and d:
                    for x in d: rows.append((x['eventDate'], x['value']))
                    empty = 0
                else:
                    empty += 1
            else:
                empty += 1
        except Exception:
            empty += 1
        sys.stdout.write('.' if rows else 'x'); sys.stdout.flush()
        if empty >= 2 and not rows:
            break
        time.sleep(1.2)

    if not rows:
        print(" KEINE WLP-DATEN"); return False
    df = pd.DataFrame(rows, columns=['time','waterlevel_m']).drop_duplicates('time').sort_values('time')
    df.to_csv(csv_path, index=False)
    print(f" {len(df)} Werte")
    return True


def main():
    stations = build_catalog()
    print(f"\n{len(stations)} Ontario-Stationen, Zeitraum {START_DATE}..{END_DATE}\n")
    ok = fail = 0
    for i, s in enumerate(stations):
        print(f"[{i+1}/{len(stations)}] {s['code']} {s['name']:<30s}", end=' ', flush=True)
        if download_wlp(s): ok += 1
        else: fail += 1
    print(f"\nFertig: {ok} OK, {fail} ohne Daten")


if __name__ == '__main__':
    main()
