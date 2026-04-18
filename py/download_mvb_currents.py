#!/usr/bin/env python3
"""
Download historical current measurements (speed SV3 + direction SR3) from
Meetnet Vlaamse Banken (MVB) for all stations that have both parameters.

MVB getData limits range (works for up to ~7 days). We stream in 7-day chunks
across each station's available history.

Output: /home/oliver/currents/Belgium/<code>.csv with columns
  time, speed (m/s), direction (deg)

Token is refreshed every few hundred requests.
"""
import os, json, time, datetime, sys, requests
import pandas as pd

sys.path.insert(0, '/home/oliver/py')
from probe_mvb_catalog import load_creds, get_token

OUTPUT_DIR = '/home/oliver/currents/Belgium'
API = 'https://api.meetnetvlaamsebanken.be'

# Probe each year's first half to detect coverage
SCAN_YEARS = range(2000, 2027)
CHUNK_DAYS = 7


def refresh_token():
    c = load_creds()
    return get_token(c['username'], c['password'])


def post_getdata(tok, ids, start, end):
    h = {'Authorization': f'Bearer {tok}', 'Content-Type': 'application/json'}
    body = {
        'StartTime': start.strftime('%Y-%m-%dT%H:%M:%S.000Z'),
        'EndTime':   end.strftime('%Y-%m-%dT%H:%M:%S.000Z'),
        'IDs': ids,
    }
    for attempt in range(3):
        try:
            r = requests.post(f'{API}/V2/getData', headers=h, json=body, timeout=60)
            if r.status_code == 401:
                return 'REAUTH', None
            r.raise_for_status()
            return 'OK', r.json()
        except Exception as e:
            if attempt == 2:
                return 'ERR', str(e)
            time.sleep(2 ** attempt)
    return 'ERR', 'retries exhausted'


def detect_range(tok, stn):
    """Find first and last years with data by probing one week per year."""
    ids = [f'{stn}SV3', f'{stn}SR3']
    years_with_data = []
    for yr in SCAN_YEARS:
        start = datetime.datetime(yr, 6, 1)
        end = datetime.datetime(yr, 6, 3)
        status, j = post_getdata(tok, ids, start, end)
        if status == 'REAUTH':
            tok = refresh_token()
            status, j = post_getdata(tok, ids, start, end)
        if status != 'OK':
            continue
        sv = next((v for v in j.get('Values', []) if v['ID'] == f'{stn}SV3'), None)
        sr = next((v for v in j.get('Values', []) if v['ID'] == f'{stn}SR3'), None)
        nsv = len(sv.get('Values') or []) if sv else 0
        nsr = len(sr.get('Values') or []) if sr else 0
        if nsv > 0 and nsr > 0:
            years_with_data.append(yr)
    return years_with_data, tok


def download_station(tok, stn, name, start_year, end_year, out_dir):
    safe = stn
    csv_path = os.path.join(out_dir, f'{safe}.csv')
    if os.path.exists(csv_path) and os.path.getsize(csv_path) > 1024:
        print(f"  {stn} schon vorhanden, überspringe.")
        return True, tok

    ids = [f'{stn}SV3', f'{stn}SR3']
    tmp_path = csv_path + '.partial'
    header_written = False
    total = 0

    start = datetime.datetime(start_year, 1, 1)
    end = datetime.datetime(end_year + 1, 1, 1)
    req_count = 0
    cur = start
    while cur < end:
        nxt = cur + datetime.timedelta(days=CHUNK_DAYS)
        if nxt > end:
            nxt = end
        status, j = post_getdata(tok, ids, cur, nxt)
        req_count += 1
        if status == 'REAUTH':
            tok = refresh_token()
            status, j = post_getdata(tok, ids, cur, nxt)
        if status != 'OK':
            print(f"    {cur.date()} ERR: {j}", flush=True)
            cur = nxt
            continue

        sv = next((v for v in j.get('Values', []) if v['ID'] == f'{stn}SV3'), None)
        sr = next((v for v in j.get('Values', []) if v['ID'] == f'{stn}SR3'), None)
        sv_pts = sv.get('Values') or [] if sv else []
        sr_pts = sr.get('Values') or [] if sr else []

        if sv_pts and sr_pts:
            dv = pd.DataFrame(sv_pts).rename(columns={'Timestamp':'time','Value':'speed'})
            dr = pd.DataFrame(sr_pts).rename(columns={'Timestamp':'time','Value':'direction'})
            dv['time'] = pd.to_datetime(dv['time'])
            dr['time'] = pd.to_datetime(dr['time'])
            dv = dv.set_index('time')
            dr = dr.set_index('time')
            dv = dv[~dv.index.duplicated(keep='first')]
            dr = dr[~dr.index.duplicated(keep='first')]
            m = dv.join(dr, how='inner')
            if not m.empty:
                m.to_csv(tmp_path, mode='a', header=not header_written)
                header_written = True
                total += len(m)

        if req_count % 10 == 0:
            print(f"    {cur.date()} total={total}", flush=True)

        # Refresh token every 300 requests to stay safe
        if req_count % 300 == 0:
            print("    refreshing token ...", flush=True)
            tok = refresh_token()

        cur = nxt

    if total == 0:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        print(f"  {stn} KEINE DATEN")
        return False, tok
    os.rename(tmp_path, csv_path)
    years = total / (6 * 24 * 365.25)
    print(f"  {stn} -> {total} Werte ({years:.1f} Jahre)")
    return True, tok


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    with open('/home/oliver/currents/mvb_catalog.json') as f:
        cat = json.load(f)
    locs = {l['ID']: l for l in cat['Locations']}
    avail = cat['AvailableData']

    sv3 = set(a['Location'] for a in avail if a['Parameter'] == 'SV3')
    sr3 = set(a['Location'] for a in avail if a['Parameter'] == 'SR3')
    stations = sorted(sv3 & sr3)
    print(f"Stationen mit SV3+SR3: {stations}")

    tok = refresh_token()

    # Build metadata cache + detect year range
    meta = {}
    print("\n=== Detektiere Datenzeitraum je Station ===")
    for stn in stations:
        lnm = locs[stn]
        name = lnm.get('Name', [{}])[0].get('Message', stn) if lnm.get('Name') else stn
        pos = lnm.get('PositionWKT', '')
        # parse POINT (lon lat)
        lon = lat = None
        if pos.startswith('POINT'):
            try:
                parts = pos.replace('POINT','').strip('() ').split()
                lon = float(parts[0])
                lat = float(parts[1])
            except Exception:
                pass

        print(f"\n-- {stn} | {name} | ({lat},{lon}) --")
        yrs, tok = detect_range(tok, stn)
        if not yrs:
            print(f"  keine Daten gefunden, skip")
            continue
        print(f"  Jahre mit Daten: {min(yrs)}..{max(yrs)} ({len(yrs)} Stichproben-Jahre)")
        meta[stn] = {'name':name,'lat':lat,'lon':lon,
                     'start_year':min(yrs),'end_year':max(yrs)}

    with open(os.path.join(OUTPUT_DIR,'_stations.json'),'w') as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)

    # Download
    print("\n=== Download ===")
    for stn, m in meta.items():
        print(f"\n[{stn}] {m['name']} ({m['start_year']}..{m['end_year']})")
        ok, tok = download_station(tok, stn, m['name'],
                                   m['start_year'], m['end_year'], OUTPUT_DIR)


if __name__ == '__main__':
    main()
