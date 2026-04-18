#!/usr/bin/env python3
"""Probe historic range for MVB SV3/SR3. Try various years."""
import requests, datetime, json
from probe_mvb_catalog import load_creds, get_token

c = load_creds()
tok = get_token(c['username'], c['password'])
h = {'Authorization': f'Bearer {tok}', 'Content-Type': 'application/json'}

# Test years
for yr in [2024, 2022, 2020, 2018, 2015, 2012, 2010, 2008, 2005, 2000]:
    start = datetime.datetime(yr, 1, 1)
    end = datetime.datetime(yr, 1, 8)
    body = {
        'StartTime': start.strftime('%Y-%m-%dT%H:%M:%S.000Z'),
        'EndTime':   end.strftime('%Y-%m-%dT%H:%M:%S.000Z'),
        'IDs': ['MP0SV3'],
    }
    try:
        r = requests.post('https://api.meetnetvlaamsebanken.be/V2/getData',
                          headers=h, json=body, timeout=30)
        j = r.json()
        n = len(j['Values'][0]['Values']) if j.get('Values') and j['Values'][0].get('Values') else 0
        print(f"  {yr} week1: {n} points")
    except Exception as e:
        print(f"  {yr}: ERR {e}")

# Now check entire year 2015 to see max range
print("\n--- full year 2015 MP0 SV3 ---")
body = {
    'StartTime': '2015-01-01T00:00:00.000Z',
    'EndTime':   '2016-01-01T00:00:00.000Z',
    'IDs': ['MP0SV3'],
}
r = requests.post('https://api.meetnetvlaamsebanken.be/V2/getData',
                  headers=h, json=body, timeout=60)
j = r.json()
vals = j['Values'][0].get('Values', [])
print(f"total points 2015: {len(vals)}")
if vals:
    print(f"first: {vals[0]}")
    print(f"last:  {vals[-1]}")
