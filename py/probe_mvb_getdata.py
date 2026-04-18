#!/usr/bin/env python3
"""Test MVB getData: request 7 days of SV3/SR3 for Wandelaar."""
import json, requests, datetime
from probe_mvb_catalog import load_creds, get_token

c = load_creds()
tok = get_token(c['username'], c['password'])
h = {'Authorization': f'Bearer {tok}', 'Content-Type': 'application/json'}

# Try recent week first
end = datetime.datetime.utcnow()
start = end - datetime.timedelta(days=7)

body = {
    'StartTime': start.strftime('%Y-%m-%dT%H:%M:%S.000Z'),
    'EndTime':   end.strftime('%Y-%m-%dT%H:%M:%S.000Z'),
    'IDs': ['MP0SV3','MP0SR3'],
}
r = requests.post('https://api.meetnetvlaamsebanken.be/V2/getData',
                  headers=h, json=body, timeout=60)
print(f"Status: {r.status_code}")
print(f"Response length: {len(r.content)}")

j = r.json()
print(f"Top-level keys: {list(j.keys()) if isinstance(j,dict) else type(j)}")
if isinstance(j, dict):
    for k, v in j.items():
        if isinstance(v, list):
            print(f"  {k}: list of {len(v)}")
            if v: print(f"    first item: {json.dumps(v[0],ensure_ascii=False)[:400]}")
        else:
            print(f"  {k}: {str(v)[:200]}")
