#!/usr/bin/env python3
"""Download WLP from CHS IWLS API for Nunavut stations."""
import os, json, time, datetime, sys, requests
import pandas as pd

API_BASE = 'https://api-sine.dfo-mpo.gc.ca/api/v1'
OUTPUT_DIR = '/home/oliver/water_levels/Canada_IWLS_NU'
CATALOG_PATH = os.path.join(OUTPUT_DIR, '_nu_stations.json')
RESOLUTION = 'FIFTEEN_MINUTES'
START_DATE = '2025-01-01'
END_DATE = '2025-12-31'

NU_CODES_JSON = '/tmp/nu_codes.json'


def build_catalog():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    if os.path.exists(CATALOG_PATH):
        with open(CATALOG_PATH) as f: return json.load(f)
    with open(NU_CODES_JSON) as f:
        codes = set(json.load(f))
    r = requests.get(f'{API_BASE}/stations', timeout=60)
    sel=[{'code':s['code'],'name':s['officialName'],'lat':s['latitude'],'lon':s['longitude'],'id':s['id']}
         for s in r.json() if s['code'] in codes]
    sel.sort(key=lambda x:x['code'])
    with open(CATALOG_PATH,'w') as f: json.dump(sel,f,indent=2)
    return sel


def download_wlp(st):
    safe=st['code']+'_'+st['name'].replace(' ','_').replace('/','_').replace("'",'').replace('.','').replace('#','')
    p=os.path.join(OUTPUT_DIR,f'{safe}_wlp.csv')
    if os.path.exists(p) and os.path.getsize(p)>5000:
        print(f"  vorhanden"); return True
    start=datetime.date.fromisoformat(START_DATE); end=datetime.date.fromisoformat(END_DATE)
    months=[]; cur=start.replace(day=1)
    while cur<=end:
        nxt=(cur.replace(day=28)+datetime.timedelta(days=4)).replace(day=1)
        months.append((cur,min(nxt-datetime.timedelta(days=1),end))); cur=nxt
    rows=[]; empty=0
    for a,b in months:
        try:
            r=requests.get(f'{API_BASE}/stations/{st["id"]}/data',
                params={'time-series-code':'wlp','from':f'{a}T00:00:00Z','to':f'{b}T23:59:59Z','resolution':RESOLUTION},
                timeout=20)
            if r.status_code==429: time.sleep(10); continue
            if r.status_code==200:
                d=r.json()
                if isinstance(d,list) and d:
                    for x in d: rows.append((x['eventDate'],x['value']))
                    empty=0
                else: empty+=1
            else: empty+=1
        except Exception: empty+=1
        sys.stdout.write('.' if rows else 'x'); sys.stdout.flush()
        if empty>=2 and not rows: break
        time.sleep(1.0)
    if not rows: print(" KEINE DATEN"); return False
    df=pd.DataFrame(rows,columns=['time','waterlevel_m']).drop_duplicates('time').sort_values('time')
    df.to_csv(p,index=False); print(f" {len(df)}"); return True


def main():
    sts=build_catalog()
    print(f"{len(sts)} Nunavut-Stationen\n")
    ok=fail=0
    for i,s in enumerate(sts):
        print(f"[{i+1}/{len(sts)}] {s['code']} {s['name']:<30s}",end=' ',flush=True)
        if download_wlp(s): ok+=1
        else: fail+=1
    print(f"\nOK:{ok}  ohne Daten:{fail}")

if __name__=='__main__': main()
