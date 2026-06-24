#!/usr/bin/env python3
"""Enumerate moored tidal-current platforms WORLDWIDE from CMEMS global in-situ
product INSITU_GLO_PHYBGCWAV_DISCRETE_MYNRT_013_030.

Strategy mirrors download_cmems_currents_europe.py but:
  - global product (covers everything outside the EU regional TACs),
  - no bbox filter (we want the whole world),
  - buckets results by coarse world region so we can see where the prize is.

Index-coordinate caveat (see project_currents_ph_br_cl_blocked): geospatial_*
columns in the index are sometimes wrong. We only use them here for a ROUGH
regional histogram; real positions get read from the NetCDF after download.
"""
import os
from collections import Counter, defaultdict
from datetime import datetime

IDX = ('/home/oliver/water_levels/CMEMS_currents_idx/glo/'
       'INSITU_GLO_PHYBGCWAV_DISCRETE_MYNRT_013_030/'
       'cmems_obs-ins_glo_phybgcwav_mynrt_na_irr_202311/index_history.txt')

CURRENT_VARS = {'HCSP', 'HCDT', 'EWCT', 'NSCT'}
MIN_DAYS = 180


def parse_rows(path):
    header = None
    with open(path, encoding='latin-1') as f:
        for line in f:
            line = line.rstrip('\n')
            if not line:
                continue
            if line.startswith('#'):
                if 'product_id' in line and ',' in line:
                    header = [h.strip() for h in line.lstrip('# ').split(',')]
                continue
            if header is None:
                continue
            fields = line.split(',')
            if len(fields) != len(header):
                continue
            yield dict(zip(header, fields))


def platform_code(fname):
    base = os.path.basename(fname)
    if not base.endswith('.nc'):
        return None
    parts = base[:-3].split('_')
    if len(parts) < 4:
        return None
    if len(parts[-1]) == 6 and parts[-1].isdigit():
        parts = parts[:-1]
    return '_'.join(parts[3:])


def parse_ts(s):
    try:
        return datetime.fromisoformat(s.replace('Z', '+00:00'))
    except ValueError:
        return None


def region_of(lat, lon):
    if lon > 180:
        lon -= 360
    # coarse buckets, tuned to the gap regions of interest
    if -60 <= lat <= 15 and -90 <= lon <= -30:
        return 'S-America (BR/AR/CL/UY/Peru)'
    if 15 < lat <= 33 and -120 <= lon <= -60:
        return 'C-America / Mexico / Caribbean'
    if 0 <= lat <= 25 and 95 <= lon <= 130:
        return 'SE-Asia (PH/ID/VN/MY/TH)'
    if -10 <= lat <= 45 and 45 <= lon <= 100:
        return 'Indian Ocean / India / Arabia'
    if 20 <= lat <= 50 and 120 <= lon <= 150:
        return 'E-Asia (CN/KR/JP/TW)'
    if -50 <= lat <= -5 and 105 <= lon <= 180:
        return 'Australia / NZ / SW-Pacific'
    if -40 <= lat <= 40 and -180 <= lon <= -120 or -40 <= lat <= 40 and 150 <= lon <= 180:
        return 'Pacific open/islands'
    if 30 <= lat <= 75 and -25 <= lon <= 45:
        return 'Europe (regional TAC covers)'
    if lat > 60:
        return 'Arctic / high-lat'
    if -60 <= lat <= 10 and -25 <= lon <= 25:
        return 'W-Africa / Gulf of Guinea'
    if 10 <= lat <= 45 and -100 <= lon <= -60:
        return 'US-E / Gulf of Mexico'
    if 30 <= lat <= 60 and -160 <= lon <= -110:
        return 'US-W / NE-Pacific'
    return f'other ({lat:.0f},{lon:.0f})'


def main():
    platforms = {}
    n_rows = n_mo = n_cur = 0
    for row in parse_rows(IDX):
        n_rows += 1
        fname = row['file_name']
        if '/history/MO/' not in fname:
            continue
        n_mo += 1
        params = set(row.get('parameters', '').split())
        if not (params & CURRENT_VARS):
            continue
        n_cur += 1
        pc = platform_code(fname)
        if not pc:
            continue
        try:
            lat = (float(row['geospatial_lat_min']) + float(row['geospatial_lat_max'])) / 2
            lon = (float(row['geospatial_lon_min']) + float(row['geospatial_lon_max'])) / 2
        except (ValueError, KeyError):
            continue
        ts0, ts1 = parse_ts(row.get('time_coverage_start', '')), parse_ts(row.get('time_coverage_end', ''))
        if not ts0 or not ts1:
            continue
        p = platforms.get(pc)
        if p is None:
            p = {'lat': lat, 'lon': lon, 'inst': row.get('institution', ''),
                 'params': set(), 's0': ts0, 's1': ts1, 'n': 0, 'mode': set()}
            platforms[pc] = p
        p['params'] |= (params & CURRENT_VARS)
        p['mode'].add(row.get('data_mode', ''))
        p['n'] += 1
        if ts0 < p['s0']:
            p['s0'] = ts0
        if ts1 > p['s1']:
            p['s1'] = ts1

    kept = {pc: p for pc, p in platforms.items()
            if (p['s1'] - p['s0']).days >= MIN_DAYS}

    print(f'rows={n_rows}  MO-files={n_mo}  with-current-vars={n_cur}')
    print(f'unique MO current platforms: {len(platforms)}  (>={MIN_DAYS}d span: {len(kept)})\n')

    by_region = defaultdict(list)
    for pc, p in kept.items():
        by_region[region_of(p['lat'], p['lon'])].append((pc, p))

    print('=== moored current platforms >=180d by region ===')
    for reg, items in sorted(by_region.items(), key=lambda x: -len(x[1])):
        spans = sorted((p['s1'] - p['s0']).days for _, p in items)
        med = spans[len(spans) // 2]
        print(f'  {len(items):4d}  {reg:38s}  median span {med}d')

    # detail dump for the priority gap regions
    print('\n=== detail: gap regions of interest ===')
    targets = ['S-America (BR/AR/CL/UY/Peru)', 'SE-Asia (PH/ID/VN/MY/TH)',
               'Indian Ocean / India / Arabia', 'W-Africa / Gulf of Guinea',
               'Australia / NZ / SW-Pacific']
    for reg in targets:
        items = sorted(by_region.get(reg, []), key=lambda x: -(x[1]['s1'] - x[1]['s0']).days)
        print(f'\n--- {reg}  ({len(items)}) ---')
        for pc, p in items[:40]:
            days = (p['s1'] - p['s0']).days
            print(f'  {pc:22.22s} {p["lat"]:8.3f},{p["lon"]:9.3f} {days:5d}d '
                  f'{"/".join(sorted(p["params"])):14s} {"".join(sorted(p["mode"]))} '
                  f'{p["inst"][:34]}')


if __name__ == '__main__':
    main()
