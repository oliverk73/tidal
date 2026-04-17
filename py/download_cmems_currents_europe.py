#!/usr/bin/env python3
"""Download CMEMS in-situ current data for European coastal stations.

Covers 3 regional products: NWS, IBI, MED. Crash-resumable via state file.
Skips platforms already present in currents/<country>/ (so DE/NL/BE etc.
won't re-download — but new stations in those regions still get pulled).

Usage:
    python3 download_cmems_currents_europe.py --dry-run   # just enumerate
    python3 download_cmems_currents_europe.py --refresh-indexes
    python3 download_cmems_currents_europe.py             # download
"""
import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

HOME = Path.home()
IDX_DIR = Path('/tmp/cm_idx')
RAW_DIR = HOME / 'currents' / 'cmems_raw'
STATE_FILE = RAW_DIR / '_download_state.json'
CURRENTS_DIR = HOME / 'currents'

PRODUCTS = {
    'nws': ('INSITU_NWS_PHYBGCWAV_DISCRETE_MYNRT_013_036',
            'cmems_obs-ins_nws_phybgcwav_mynrt_na_irr'),
    'ibi': ('INSITU_IBI_PHYBGCWAV_DISCRETE_MYNRT_013_033',
            'cmems_obs-ins_ibi_phybgcwav_mynrt_na_irr'),
    'med': ('INSITU_MED_PHYBGCWAV_DISCRETE_MYNRT_013_035',
            'cmems_obs-ins_med_phybgcwav_mynrt_na_irr'),
}

# European bbox (generous, keeps overseas + Arctic out but allows all EU coasts)
EU_LAT_MIN, EU_LAT_MAX = 30.0, 75.0
EU_LON_MIN, EU_LON_MAX = -25.0, 45.0

CURRENT_VARS = {'HCSP', 'HCDT', 'EWCT', 'NSCT'}
MIN_DAYS = 180


def index_dir(key):
    prod_id, ds_id = PRODUCTS[key]
    return IDX_DIR / key / prod_id / f'{ds_id}_202311'


def refresh_indexes():
    for key, (prod_id, ds_id) in PRODUCTS.items():
        target = IDX_DIR / key
        cmd = ['copernicusmarine', 'get', '-i', ds_id,
               '--index-parts', '-o', str(target),
               '--overwrite', '--log-level', 'WARN']
        print(f'Refreshing {key} index...')
        subprocess.run(cmd, check=True)


def parse_history(key):
    """Yield dicts per file row in index_history.txt."""
    path = index_dir(key) / 'index_history.txt'
    header = None
    with open(path) as f:
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


def platform_code_from_filename(fname):
    """Extract platform_code from relative file_name path.

    Pattern: <DC>_<DT>_<FT>_<PLATFORM>[_<YYYYMM>].nc
    """
    base = os.path.basename(fname)
    if not base.endswith('.nc'):
        return None
    stem = base[:-3]
    parts = stem.split('_')
    if len(parts) < 4:
        return None
    # strip trailing YYYYMM partition suffix
    if len(parts[-1]) == 6 and parts[-1].isdigit():
        parts = parts[:-1]
    return '_'.join(parts[3:])


def is_hfr(platform_code, institution):
    pc = platform_code or ''
    return (pc.startswith('HFR') or '-Total' in pc
            or 'HF-radar' in institution or 'High Frequency Radar' in institution)


def is_moored_file(fname):
    """Only accept moored station files (fixed position).

    Skips drifting buoys (DB), profilers (PF/CT), gliders (GL/SM), HF radar (HF),
    trajectories (TX), and other non-fixed platforms.
    """
    return '/history/MO/' in fname


def parse_ts(s):
    try:
        return datetime.fromisoformat(s.replace('Z', '+00:00'))
    except ValueError:
        return None


def collect_platforms():
    """Build dict: platform_code -> aggregated info across all products."""
    platforms = {}
    n_rows = 0
    n_with_currents = 0
    for key in PRODUCTS:
        for row in parse_history(key):
            n_rows += 1
            fname = row['file_name']
            if not is_moored_file(fname):
                continue
            params = set(row.get('parameters', '').split())
            if not (params & CURRENT_VARS):
                continue
            n_with_currents += 1
            pc = platform_code_from_filename(fname)
            if not pc:
                continue
            inst = row.get('institution', '')
            if is_hfr(pc, inst):
                continue

            try:
                lat_min = float(row['geospatial_lat_min'])
                lat_max = float(row['geospatial_lat_max'])
                lon_min = float(row['geospatial_lon_min'])
                lon_max = float(row['geospatial_lon_max'])
            except (ValueError, KeyError):
                continue

            ts_start = parse_ts(row.get('time_coverage_start', ''))
            ts_end = parse_ts(row.get('time_coverage_end', ''))
            if not ts_start or not ts_end:
                continue

            lat = (lat_min + lat_max) / 2
            lon = (lon_min + lon_max) / 2
            if not (EU_LAT_MIN <= lat <= EU_LAT_MAX and EU_LON_MIN <= lon <= EU_LON_MAX):
                continue

            p = platforms.get(pc)
            if p is None:
                p = {'files': [], 'products': set(), 'institution': inst,
                     'lat_sum': 0.0, 'lon_sum': 0.0, 'n_pos': 0,
                     'parameters': set(),
                     'span_start': ts_start, 'span_end': ts_end}
                platforms[pc] = p
            p['files'].append((key, row['file_name']))
            p['products'].add(key)
            p['lat_sum'] += lat
            p['lon_sum'] += lon
            p['n_pos'] += 1
            p['parameters'] |= (params & CURRENT_VARS)
            if ts_start < p['span_start']:
                p['span_start'] = ts_start
            if ts_end > p['span_end']:
                p['span_end'] = ts_end

    # Filter by duration
    out = {}
    for pc, p in platforms.items():
        span_days = (p['span_end'] - p['span_start']).days
        if span_days < MIN_DAYS:
            continue
        lat = p['lat_sum'] / p['n_pos']
        lon = p['lon_sum'] / p['n_pos']
        out[pc] = {
            'files': p['files'],
            'products': sorted(p['products']),
            'institution': p['institution'],
            'lat': round(lat, 4),
            'lon': round(lon, 4),
            'parameters': sorted(p['parameters']),
            'span_days': span_days,
            'span_start': p['span_start'].date().isoformat(),
            'span_end': p['span_end'].date().isoformat(),
        }

    print(f'  rows parsed: {n_rows}, with current vars: {n_with_currents}, '
          f'European platforms ≥{MIN_DAYS}d: {len(out)}')
    return out


def existing_platform_codes():
    """Scan currents/<country>/ for existing <platform>.csv files."""
    found = set()
    if not CURRENTS_DIR.exists():
        return found
    for sub in CURRENTS_DIR.iterdir():
        if not sub.is_dir() or sub.name == 'cmems_raw':
            continue
        for f in sub.glob('*.csv'):
            name = f.stem
            if name.startswith('_'):
                continue
            found.add(name)
    return found


def load_state():
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            return json.load(f)
    return {'completed': [], 'failed': {}, 'started_at': None}


def save_state(state):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix('.json.tmp')
    with open(tmp, 'w') as f:
        json.dump(state, f, indent=2)
    tmp.replace(STATE_FILE)


_PLATFORM_SAFE_RE = re.compile(r'[^A-Za-z0-9_\-]')


def download_platform(pc, pdata):
    """Run copernicusmarine get for one platform across relevant products."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    # build regex anchored on platform position between 3rd '_' and optional _YYYYMM
    safe_pc = _PLATFORM_SAFE_RE.sub('.', pc)  # dot-escape any weird chars
    regex = rf'.*_TS_MO_{safe_pc}(_\d{{6}})?\.nc$'
    any_ok = False
    errors = []
    for key in pdata['products']:
        ds_id = PRODUCTS[key][1]
        cmd = [
            'copernicusmarine', 'get',
            '-i', ds_id,
            '--dataset-part', 'history',
            '--regex', regex,
            '-o', str(RAW_DIR),
            '--no-directories',
            '--overwrite',
            '--log-level', 'WARN',
        ]
        try:
            r = subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=900)
            any_ok = True
        except subprocess.CalledProcessError as e:
            errors.append(f'{key}: {(e.stderr or "")[:200]}')
        except subprocess.TimeoutExpired:
            errors.append(f'{key}: timeout')
    return any_ok, errors


def summarize_by_region(platforms):
    buckets = []
    for pc, p in platforms.items():
        lat, lon = p['lat'], p['lon']
        if lat >= 56 and -5 <= lon <= 16:
            label = 'Scandinavia (NO/SE/DK/North DE)'
        elif lat >= 53 and -12 <= lon <= 2:
            label = 'UK/Scotland/Ireland'
        elif lat >= 51 and 2 <= lon <= 10:
            label = 'DE/NL/BE North Sea'
        elif 49 <= lat < 53 and -6 <= lon <= 2:
            label = 'FR Channel / UK south'
        elif 43 <= lat < 49 and -10 <= lon <= 2:
            label = 'FR Biscay / Brittany'
        elif 36 <= lat < 44 and -10 <= lon <= -1:
            label = 'ES/PT Atlantic'
        elif 36 <= lat < 44 and -1 <= lon <= 6:
            label = 'FR/ES Mediterranean W'
        elif 36 <= lat < 46 and 6 < lon <= 20:
            label = 'IT / Adriatic / Tyrrhenian'
        elif 33 <= lat < 42 and 20 < lon <= 36:
            label = 'GR / East Med / TR'
        elif lat >= 36 and 20 < lon < 32:
            label = 'Aegean / Black Sea'
        else:
            label = f'other  ({lat:.1f},{lon:.1f})'
        buckets.append(label)
    from collections import Counter
    c = Counter(buckets)
    for k, v in sorted(c.items(), key=lambda x: -x[1]):
        print(f'  {v:4d}  {k}')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true', help='enumerate only, no download')
    ap.add_argument('--refresh-indexes', action='store_true')
    ap.add_argument('--limit', type=int, help='limit number of downloads (for testing)')
    args = ap.parse_args()

    if args.refresh_indexes:
        refresh_indexes()

    for key in PRODUCTS:
        if not (index_dir(key) / 'index_history.txt').exists():
            print(f'Missing index for {key}, run with --refresh-indexes first', file=sys.stderr)
            sys.exit(1)

    print('Parsing CMEMS indexes...')
    platforms = collect_platforms()

    existing = existing_platform_codes()
    print(f'  {len(existing)} platform_codes already present in currents/<country>/')

    new_platforms = {pc: p for pc, p in platforms.items() if pc not in existing}
    print(f'  -> {len(new_platforms)} NEW platforms to download\n')

    print('Distribution of new platforms by rough region:')
    summarize_by_region(new_platforms)

    # snapshot discovery for inspection
    disc_file = RAW_DIR / '_discovery.json'
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    with open(disc_file, 'w') as f:
        json.dump({
            'total_platforms': len(platforms),
            'existing': sorted(existing),
            'new_platforms': {
                pc: {k: v for k, v in p.items() if k != 'files'}
                for pc, p in new_platforms.items()},
        }, f, indent=2, ensure_ascii=False)
    print(f'\nDiscovery snapshot written: {disc_file}')

    if args.dry_run:
        return

    state = load_state()
    state['completed'] = list(set(state.get('completed', [])))
    state['started_at'] = state.get('started_at') or datetime.now().isoformat(timespec='seconds')
    done = set(state['completed'])

    queue = sorted(pc for pc in new_platforms if pc not in done)
    if args.limit:
        queue = queue[:args.limit]
    print(f'\n{len(queue)} to download (already done: {len(done)})')

    for i, pc in enumerate(queue, 1):
        p = new_platforms[pc]
        prods = ','.join(p['products'])
        print(f'[{i}/{len(queue)}] {pc:30s} {prods:7s} {p["span_days"]:>5d}d '
              f'@ {p["lat"]:7.3f},{p["lon"]:7.3f}  {p["institution"][:40]}')
        ok, errs = download_platform(pc, p)
        if ok:
            state['completed'].append(pc)
        else:
            state['failed'][pc] = errs
        if i % 5 == 0 or i == len(queue):
            save_state(state)
    save_state(state)
    print(f'\nDone. completed={len(state["completed"])}  failed={len(state["failed"])}')


if __name__ == '__main__':
    main()
