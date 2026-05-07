#!/usr/bin/env python3
"""Build refresh list: all UK stations in classic-1997 + dwf-20100529.
Matches them against tidetimes.co.uk station list by name or coord (<5km).
Overwrites missing_stations.json and deletes existing JSON/checkpoint so
download_tidetimes_uk.py redownloads and batch_utide_uk_tidetimes.py reanalyses.
"""
import re
import json
import math
import requests
from pathlib import Path

CLASSIC_FILES = [
    Path("/home/oliver/harmonics/classic/harmonics-1997-05-25_mod.txt"),
    Path("/home/oliver/harmonics/classic/harmonics-dwf-20100529-nonfree_mod.txt"),
]
UK_DIR = Path("/home/oliver/water_levels/UK_tidetimes")
CHECKPOINT_DIR = Path("/home/oliver/harmonics/utide/checkpoints_uk_tidetimes")
MISSING_JSON = UK_DIR / "missing_stations.json"

HEADERS = {'User-Agent': 'Mozilla/5.0'}
UK_REGION_RE = re.compile(r'United Kingdom|England|Scotland|Wales|Ireland|Channel Islands|Isle of Man')


def parse_classic(path):
    """Extract (name, lat, lon) for UK/Ireland stations. Coords are in the
    preceding HOT COMMENTS block (# !latitude / # !longitude)."""
    lines = path.read_text(encoding='iso-8859-1').splitlines()
    stations = []
    for i, line in enumerate(lines):
        if line.startswith('#') or not line.strip():
            continue
        if not UK_REGION_RE.search(line):
            continue
        name = line.strip()
        lat = lon = None
        for j in range(max(0, i - 30), i):
            L = lines[j]
            m = re.match(r'#\s*!?latitude:\s*(-?[\d.]+)', L)
            if m: lat = float(m.group(1))
            m = re.match(r'#\s*!?longitude:\s*(-?[\d.]+)', L)
            if m: lon = float(m.group(1))
        if lat is not None and lon is not None:
            stations.append({'name': name, 'lat': lat, 'lon': lon})
    return stations


def get_tidetimes_stations():
    r = requests.get('https://www.tidetimes.co.uk', headers=HEADERS, timeout=30)
    m = re.search(r'tt\.locations\s*=\s*(\[.*?\]);', r.text, re.DOTALL)
    data = json.loads(m.group(1))
    return [{'slug': s['slug'], 'name': s['name'],
             'lat': float(s['lat']), 'lon': float(s['lng'])} for s in data]


def km(lat1, lon1, lat2, lon2):
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return 6371 * 2 * math.asin(math.sqrt(a))


def norm(s):
    s = s.lower()
    s = re.sub(r'\([^)]*\)', '', s)
    s = s.split(',')[0]
    s = re.sub(r'[^a-z0-9 ]', ' ', s)
    return re.sub(r'\s+', ' ', s).strip()


def match(classic, tt):
    cname = norm(classic['name'])
    best = None
    best_d = 99
    for t in tt:
        d = km(classic['lat'], classic['lon'], t['lat'], t['lon'])
        if d < best_d:
            best_d = d
            best = t
        if d < 5 and cname == norm(t['name']):
            return t, d
    if best and best_d < 5:
        return best, best_d
    return None, best_d


def safe_filename(name):
    return name.replace(' ', '_').replace('/', '_').replace("'", '').replace('"', '')


def main():
    classics = []
    for f in CLASSIC_FILES:
        s = parse_classic(f)
        print(f"{f.name}: {len(s)} UK/IE stations")
        classics.extend(s)

    # dedupe by (name,lat,lon)
    seen = set()
    uniq = []
    for c in classics:
        k = (c['name'], round(c['lat'], 3), round(c['lon'], 3))
        if k not in seen:
            seen.add(k)
            uniq.append(c)
    print(f"Total unique: {len(uniq)}")

    tt = get_tidetimes_stations()
    print(f"tidetimes.co.uk: {len(tt)} stations")

    refresh = []
    unmatched = []
    seen_slug = set()
    for c in uniq:
        t, d = match(c, tt)
        if t and t['slug'] not in seen_slug:
            seen_slug.add(t['slug'])
            refresh.append(t)
        elif not t:
            unmatched.append((c, d))

    print(f"\nMatched → refresh: {len(refresh)}")
    print(f"Unmatched: {len(unmatched)}")
    for c, d in unmatched[:15]:
        print(f"  {c['name'][:55]:55s}  nearest={d:.1f}km")

    # Delete existing JSON + checkpoint so download/analysis redoes them
    deleted_j = 0
    deleted_c = 0
    for t in refresh:
        jp = UK_DIR / f"{safe_filename(t['name'])}.json"
        if jp.exists():
            jp.unlink()
            deleted_j += 1
        cp = CHECKPOINT_DIR / f"{safe_filename(t['name'])}.pkl"
        if cp.exists():
            cp.unlink()
            deleted_c += 1
    print(f"\nDeleted {deleted_j} JSON, {deleted_c} checkpoints")

    MISSING_JSON.write_text(json.dumps(refresh, indent=2))
    print(f"Wrote {MISSING_JSON} ({len(refresh)} stations)")


if __name__ == '__main__':
    main()
