#!/usr/bin/env python3
"""Probe Meetnet Vlaamse Banken: authenticate, list catalog, find current parameters."""
import os, json, requests

def load_creds(path='/home/oliver/.meetnet_credentials'):
    c = {}
    for ln in open(path):
        if '=' in ln:
            k, v = ln.strip().split('=', 1)
            c[k.strip()] = v.strip()
    return c

def get_token(user, pw):
    r = requests.post('https://api.meetnetvlaamsebanken.be/Token',
                      data={'grant_type':'password','username':user,'password':pw},
                      timeout=30)
    r.raise_for_status()
    return r.json()['access_token']

def main():
    c = load_creds()
    tok = get_token(c['username'], c['password'])
    print(f"Token erhalten ({len(tok)} Zeichen)")
    h = {'Authorization': f'Bearer {tok}'}

    cat = requests.get('https://api.meetnetvlaamsebanken.be/V2/catalog',
                       headers=h, timeout=60).json()

    print(f"\nKategorien im Katalog: {list(cat.keys())}")
    for k in cat:
        if isinstance(cat[k], list):
            print(f"  {k}: {len(cat[k])} Einträge")

    # Parameters — find currents
    params = cat.get('Parameters', [])
    print(f"\n--- Alle {len(params)} Parameter ---")
    for p in params:
        pid = p.get('ID')
        name = p.get('Name', [{}])[0].get('Message', '') if p.get('Name') else ''
        parent = p.get('ParentID', '')
        unit = p.get('Unit', '')
        print(f"  {pid:30s} | {name:50s} | {unit:15s} | parent={parent}")

    # Locations
    locs = cat.get('Locations', [])
    print(f"\n--- {len(locs)} Locations (erste 20) ---")
    for l in locs[:20]:
        lid = l.get('ID')
        nm = l.get('Name', [{}])[0].get('Message', '') if l.get('Name') else ''
        pgis = l.get('PositionWKT','')
        print(f"  {lid:20s} | {nm:50s} | {pgis[:60]}")

    # AvailableData crossref parameter×location
    avail = cat.get('AvailableData', [])
    print(f"\n--- AvailableData: {len(avail)} Einträge ---")
    # Filter by current-like parameter keywords
    curr_keys = ['CUR','STROOM','CURRENT','VEL','VELOCITY','RICHT','DIRECTION']
    matches = []
    for a in avail:
        pid = a.get('Parameter','') or ''
        if any(k in pid.upper() for k in curr_keys):
            matches.append(a)
    print(f"  Strömungs-ähnliche Einträge: {len(matches)}")
    for m in matches[:30]:
        print(f"    loc={m.get('Location'):15s} param={m.get('Parameter')}")

    # Save raw catalog for later use
    with open('/home/oliver/currents/mvb_catalog.json','w') as f:
        json.dump(cat, f, indent=2, ensure_ascii=False)
    print("\nKatalog gespeichert: /home/oliver/currents/mvb_catalog.json")

if __name__ == '__main__':
    main()
