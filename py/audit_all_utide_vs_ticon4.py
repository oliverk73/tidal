#!/usr/bin/env python3
"""Audit ALL UTide stations against TICON4 to detect pipeline-wide phase
bias (the hourly-bin bug). Groups by source/pipeline.

For each UTide station with a TICON4 station within 5 km:
  - delta_phase = (utide_M2_phase - ticon4_M2_phase) wrapped to [-180, +180].

Groups by inferred pipeline. Reports per-group median + IQR.
"""
import re
import math
import os
from collections import defaultdict

ROOT = "/home/oliver/harmonics"
TICON = os.path.join(ROOT, "ticon", "harmonics_ticon4_worldwide.txt")
UTIDE_FILES = [
    os.path.join(ROOT, "utide", "harmonics_utide_observations.txt"),
    os.path.join(ROOT, "utide", "harmonics_utide_tidetables.txt"),
]


def parse_blocks(path):
    """Yield dict per station block."""
    with open(path, encoding='latin-1') as f:
        lines = f.read().split('\n')
    boundaries = [i for i, ln in enumerate(lines)
                  if ln.startswith('# BEGIN HOT COMMENTS')]

    def find_block_start(b):
        k = b - 1
        while k >= 0 and (lines[k] == '' or lines[k].startswith('#')):
            k -= 1
        return k + 1

    starts = [find_block_start(b) for b in boundaries]
    for i, s in enumerate(starts):
        e = starts[i + 1] if i + 1 < len(starts) else len(lines)
        bl = lines[s:e]
        # Extract metadata
        ctx = None
        source = None
        country = None
        lat = lon = None
        name = None
        meridian = None
        m2_amp = m2_ph = None
        # First non-comment, non-empty line is station name
        for j, ln in enumerate(bl):
            if ln.startswith('# station_id_context:'):
                ctx = ln.split(':', 1)[1].strip()
            elif ln.startswith('# source:'):
                source = ln.split(':', 1)[1].strip()
            elif ln.startswith('# country:'):
                country = ln.split(':', 1)[1].strip()
            elif ln.startswith('# !longitude:'):
                try:
                    lon = float(ln.split(':', 1)[1].strip())
                except ValueError:
                    pass
            elif ln.startswith('# !latitude:'):
                try:
                    lat = float(ln.split(':', 1)[1].strip())
                except ValueError:
                    pass
            elif (not ln.startswith('#') and ln.strip() and name is None):
                name = ln.strip()
            elif name is not None and meridian is None and ':' in ln and ln.strip().startswith(('+', '-')):
                meridian = ln.strip()
            elif name is not None:
                m = re.match(r'^M2\s+([\d.]+)\s+([-\d.]+)', ln)
                if m:
                    m2_amp = float(m.group(1))
                    m2_ph = float(m.group(2))
        yield {
            'ctx': ctx, 'source': source, 'country': country,
            'lat': lat, 'lon': lon, 'name': name,
            'meridian': meridian, 'm2_amp': m2_amp, 'm2_ph': m2_ph,
        }


def parse_ticon(path):
    """TICON4 has same structure but per-block 'meridian' may differ."""
    return list(parse_blocks(path))


def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp/2)**2 + math.cos(p1) * math.cos(p2) * math.sin(dl/2)**2
    return 2 * R * math.asin(math.sqrt(a))


def wrap(d):
    while d > 180: d -= 360
    while d <= -180: d += 360
    return d


def classify_pipeline(s):
    """Map a UTide station to a pipeline label based on source/ctx/country."""
    src = (s.get('source') or '').lower()
    ctx = (s.get('ctx') or '')
    country = (s.get('country') or '')
    if ctx.endswith('-chl-shoa') or ctx.endswith('-dart'):
        return 'chile-ioc'
    if 'ioc/shoa' in src:
        return 'chile-ioc'
    if 'india' in src.lower() and 'ioc' in src:
        return 'india-ioc'
    if 'pakistan' in src.lower():
        return 'pakistan-ioc'
    if 'russia' in country.lower() and 'ioc' in src:
        return 'russia-ioc'
    if 'puerto barrios' in src.lower() or ctx == 'IOC-prba':
        return 'puerto-barrios-ioc'
    # Caribbean cluster
    if 'ioc slsmf' in src or 'ioc sea level' in src:
        # Subdivide by country / region
        cc = country.lower()
        if cc in ('aruba', 'bonaire', 'curaçao', 'curacao'):
            return 'abc-ioc'
        if cc in ('british virgin islands', 'virgin islands'):
            return 'bvi-ioc'
        if cc in ('costa rica',):
            return 'costarica-ioc'
        if cc in ('panama',):
            return 'panama-ioc'
        if cc in ('nicaragua',):
            return 'nicaragua-ioc'
        if cc in ('el salvador',):
            return 'elsalvador-ioc'
        if cc in ('colombia',):
            return 'colombia-ioc'
        if cc in ('peru',):
            return 'peru-ioc'
        if cc in ('portugal',):
            return 'portugal-ioc'
        if cc in ('montserrat',):
            return 'montserrat-ioc'
        if cc == 'saint kitts and nevis' or cc == 'st kitts':
            return 'stkitts-ioc'
        if cc in ('china',):
            return 'china-ioc'
        if cc in ('turkey', 'greece'):
            return 'tr-gr-ioc'
        if cc in ('oman', 'egypt'):
            return 'om-eg-ioc'
        return f'caribbean-ioc-other ({country})'
    if 'uhslc' in src:
        return 'uhslc'
    if 'cmems' in src or 'in-situ' in src:
        return 'cmems'
    if 'shom' in src:
        return 'shom'
    if 'pegelonline' in src or 'wsv' in src:
        return 'wsv'
    if 'niwa' in src or 'linz' in src:
        return 'nz'
    if 'fcul' in src or 'antunes' in src:
        return 'fcul-pt'
    return 'other'


def main():
    print('Loading TICON4...')
    ticon = parse_ticon(TICON)
    ticon = [s for s in ticon if s['lat'] is not None and s['lon'] is not None
             and s['m2_ph'] is not None and s['m2_amp'] is not None]
    print(f'  {len(ticon)} TICON4 stations with coords + M2')

    utide = []
    for f in UTIDE_FILES:
        print(f'Loading {f}...')
        cnt = 0
        for s in parse_blocks(f):
            if s['lat'] is None or s['lon'] is None or s['m2_ph'] is None:
                continue
            s['file'] = os.path.basename(f)
            utide.append(s)
            cnt += 1
        print(f'  {cnt} stations with coords + M2')

    print(f'\nMatching ({len(utide)} UTide vs {len(ticon)} TICON)...')
    matches_by_pipeline = defaultdict(list)
    for u in utide:
        # Find nearest TICON within 5 km
        best = None
        best_d = 5.1
        for t in ticon:
            d = haversine_km(u['lat'], u['lon'], t['lat'], t['lon'])
            if d < best_d:
                best_d = d
                best = t
        if best is None:
            continue
        # Phase diff (NOTE: meridian must be consistent — most UTide is +00:00,
        # TICON varies. Skip cases with meridian mismatch for cleanliness.)
        if (u['meridian'] or '+00:00').startswith('+00:00') is False:
            # Skip UTide stations with non-UTC meridian for now
            continue
        if (best['meridian'] or '+00:00').startswith('+00:00') is False:
            # Skip TICON with non-UTC meridian (would need adjustment)
            continue
        delta = wrap(u['m2_ph'] - best['m2_ph'])
        if abs(u['m2_amp'] - best['m2_amp']) > 0.5 * max(u['m2_amp'], best['m2_amp']):
            # Amplitude widely different — skip (not the same station)
            continue
        pipeline = classify_pipeline(u)
        matches_by_pipeline[pipeline].append({
            'utide_name': u['name'], 'utide_ctx': u['ctx'],
            'ticon_name': best['name'], 'distance_km': best_d,
            'delta_phase': delta,
            'utide_m2_amp': u['m2_amp'], 'ticon_m2_amp': best['m2_amp'],
        })

    # Report
    print('\n## Per-pipeline M2-phase bias (UTide − TICON4)\n')
    print(f'{"Pipeline":<28s} | {"N":>4s} | {"med":>7s} | {"p25":>7s} | {"p75":>7s} | bug-suspect?')
    print('-' * 80)

    rows = []
    for p, ms in sorted(matches_by_pipeline.items()):
        deltas = sorted(m['delta_phase'] for m in ms)
        if not deltas:
            continue
        n = len(deltas)
        med = deltas[n//2]
        p25 = deltas[max(0, n//4)]
        p75 = deltas[min(n-1, 3*n//4)]
        suspect = '⚠ BUG?' if (abs(med) > 5 and 8 < abs(med) < 20) else ''
        rows.append((p, n, med, p25, p75, suspect))
    rows.sort(key=lambda r: -abs(r[2]))
    for p, n, med, p25, p75, sus in rows:
        print(f'{p:<28s} | {n:>4d} | {med:>+7.2f} | {p25:>+7.2f} | {p75:>+7.2f} | {sus}')

    # For bug-suspect groups, dump individual stations
    print('\n## Detail for bug-suspect groups (|median| 8–20°)\n')
    for p, n, med, p25, p75, sus in rows:
        if not sus:
            continue
        print(f'\n### {p} (N={n}, median Δ={med:+.2f}°)\n')
        for m in sorted(matches_by_pipeline[p], key=lambda x: -abs(x['delta_phase']))[:15]:
            print(f"  {m['delta_phase']:+7.2f}°  d={m['distance_km']:4.2f}km  "
                  f"M2={m['utide_m2_amp']:.3f}/{m['ticon_m2_amp']:.3f}m  "
                  f"{m['utide_name'][:50]:50s} ctx={m['utide_ctx']}")


if __name__ == '__main__':
    main()
