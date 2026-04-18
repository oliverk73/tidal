#!/usr/bin/env python3
"""
Download CHS IWLS current measurements (wcs1 speed + wcd1 direction) and/or
current predictions (wcsp1 speed + wcdp1 direction) for Canadian stations.

Invoke:
  python3 download_chs_currents.py measured     -> /home/oliver/currents/Canada_CHS_measured
  python3 download_chs_currents.py predicted    -> /home/oliver/currents/Canada_CHS_predicted

Year-by-year streaming (CHS API limits single request to ~7 days; we chunk
7 days per request).
"""
import os, sys, time, datetime, requests, json
import pandas as pd

API = 'https://api-iwls.dfo-mpo.gc.ca/api/v1'

def list_stations(kind):
    r = requests.get(f'{API}/stations?limit=5000', timeout=60)
    r.raise_for_status()
    data = r.json()
    if kind == 'measured':
        spd_code, dir_code = 'wcs1', 'wcd1'
    elif kind == 'predicted':
        spd_code, dir_code = 'wcsp1', 'wcdp1'
    else:
        raise ValueError(kind)
    out = []
    for s in data:
        codes = {ts['code'] for ts in s.get('timeSeries', [])}
        if spd_code in codes and dir_code in codes:
            out.append({
                'id': s['id'], 'code': s['code'],
                'name': s['officialName'],
                'lat': s['latitude'], 'lon': s['longitude'],
                'operating': s['operating'],
                'spd_code': spd_code, 'dir_code': dir_code,
            })
    return out

def fetch(sid, ts_code, start, end):
    url = f'{API}/stations/{sid}/data'
    params = {'time-series-code': ts_code,
              'from': start.strftime('%Y-%m-%dT%H:%M:%SZ'),
              'to':   end.strftime('%Y-%m-%dT%H:%M:%SZ')}
    for attempt in range(3):
        try:
            r = requests.get(url, params=params, timeout=60)
            if r.status_code == 200:
                return r.json()
            if r.status_code == 429:
                time.sleep(5)
                continue
            return None
        except Exception:
            time.sleep(2 ** attempt)
    return None

def download_station(stn, start_yr, end_yr, out_dir):
    code = stn['code']
    csv_path = os.path.join(out_dir, f'{code}.csv')
    if os.path.exists(csv_path) and os.path.getsize(csv_path) > 1024:
        print(f"  {code} vorhanden, skip")
        return True
    tmp = csv_path + '.partial'
    header = False
    total = 0
    cur = datetime.datetime(start_yr, 1, 1)
    end = datetime.datetime(end_yr + 1, 1, 1)
    chunks = 0
    while cur < end:
        nxt = cur + datetime.timedelta(days=7)
        if nxt > end: nxt = end
        s = fetch(stn['id'], stn['spd_code'], cur, nxt)
        d = fetch(stn['id'], stn['dir_code'], cur, nxt)
        chunks += 1
        if s and d:
            ds = pd.DataFrame(s)
            dd = pd.DataFrame(d)
            if not ds.empty and not dd.empty:
                ds = ds.rename(columns={'eventDate':'time','value':'speed'})[['time','speed']]
                dd = dd.rename(columns={'eventDate':'time','value':'direction'})[['time','direction']]
                ds['time'] = pd.to_datetime(ds['time'])
                dd['time'] = pd.to_datetime(dd['time'])
                ds = ds.set_index('time'); dd = dd.set_index('time')
                ds = ds[~ds.index.duplicated(keep='first')]
                dd = dd[~dd.index.duplicated(keep='first')]
                m = ds.join(dd, how='inner')
                if not m.empty:
                    m.to_csv(tmp, mode='a', header=not header)
                    header = True
                    total += len(m)
        if chunks % 10 == 0:
            print(f"    {cur.date()} total={total}", flush=True)
        cur = nxt
    if total == 0:
        if os.path.exists(tmp): os.remove(tmp)
        print(f"  {code} KEINE DATEN")
        return False
    os.rename(tmp, csv_path)
    years = total / (288 * 365.25)  # assume 5-min data
    print(f"  {code} -> {total} Werte (~{years:.1f} Jahre)")
    return True

def detect_range(stn):
    """Find first and last years with data via per-year probe."""
    years = []
    for yr in range(2015, 2027):
        s = fetch(stn['id'], stn['spd_code'],
                  datetime.datetime(yr, 6, 1),
                  datetime.datetime(yr, 6, 3))
        if s and len(s) > 0:
            years.append(yr)
    return years

def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ('measured','predicted'):
        print("Usage: download_chs_currents.py {measured|predicted}")
        sys.exit(1)
    kind = sys.argv[1]
    out_dir = f'/home/oliver/currents/Canada_CHS_{kind}'
    os.makedirs(out_dir, exist_ok=True)

    stations = list_stations(kind)
    print(f"{kind}: {len(stations)} Stationen")

    meta = {}
    for s in stations:
        print(f"\n-- {s['code']} {s['name']} ({s['lat']:.3f},{s['lon']:.3f}) --")
        yrs = detect_range(s)
        if not yrs:
            print("  keine Daten"); continue
        print(f"  Jahre: {min(yrs)}..{max(yrs)}")
        s['start_year'] = min(yrs); s['end_year'] = max(yrs)
        meta[s['code']] = {k:s[k] for k in ('name','lat','lon','start_year','end_year','operating')}

    with open(os.path.join(out_dir,'_stations.json'),'w') as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)

    print("\n=== Download ===")
    for s in stations:
        if s['code'] not in meta: continue
        print(f"\n[{s['code']}] {s['name']}")
        download_station(s, s['start_year'], s['end_year'], out_dir)

if __name__ == '__main__':
    main()
