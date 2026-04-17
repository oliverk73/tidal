#!/usr/bin/env python3
"""Download IMOS ANMN hourly velocity NetCDFs for all Australian mooring stations.

Crawls the public S3 bucket imos-data for all
  IMOS/ANMN/{NRS,NSW,QLD,SA,WA,AM}/*/hourly_timeseries/*_VZ_*velocity-hourly-timeseries*.nc
and downloads them to currents/Australia_IMOS/raw/.

Resume-capable: records completed files in _download_state.json (atomic rename).
"""
import argparse
import json
import os
import sys
import time
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

HOME = Path.home()
RAW_DIR = HOME / 'currents' / 'Australia_IMOS' / 'raw'
STATE_FILE = HOME / 'currents' / 'Australia_IMOS' / '_download_state.json'

S3_BASE = 'https://s3-ap-southeast-2.amazonaws.com/imos-data'
S3_LIST = 'https://s3-ap-southeast-2.amazonaws.com/imos-data/'
REGIONS = ['NRS', 'NSW', 'QLD', 'SA', 'WA', 'AM']

NS = {'s3': 'http://s3.amazonaws.com/doc/2006-03-01/'}


def list_s3(prefix):
    """List all keys in imos-data bucket under prefix. Returns list of (key, size)."""
    out = []
    token = None
    while True:
        q = {'list-type': '2', 'prefix': prefix, 'max-keys': '1000'}
        if token:
            q['continuation-token'] = token
        url = S3_LIST + '?' + urllib.parse.urlencode(q)
        with urllib.request.urlopen(url, timeout=60) as r:
            tree = ET.parse(r)
        root = tree.getroot()
        for c in root.findall('s3:Contents', NS):
            k = c.findtext('s3:Key', default='', namespaces=NS)
            s = int(c.findtext('s3:Size', default='0', namespaces=NS))
            out.append((k, s))
        truncated = root.findtext('s3:IsTruncated', default='false', namespaces=NS) == 'true'
        if not truncated:
            break
        token = root.findtext('s3:NextContinuationToken', default='', namespaces=NS)
    return out


def crawl_all_velocity():
    """Return list of (site_code, key, size) for all hourly velocity NCs."""
    results = []
    for region in REGIONS:
        prefix = f'IMOS/ANMN/{region}/'
        try:
            items = list_s3(prefix)
        except Exception as e:
            print(f'  S3 list failed for {prefix}: {e}', file=sys.stderr)
            continue
        for key, size in items:
            parts = key.split('/')
            # IMOS/ANMN/<REGION>/<SITE>/hourly_timeseries/<file>.nc
            if len(parts) < 6: continue
            if parts[4] != 'hourly_timeseries': continue
            fname = parts[-1]
            if '_VZ_' not in fname: continue
            if 'velocity-hourly-timeseries' not in fname: continue
            if not fname.endswith('.nc'): continue
            site = parts[3]
            results.append((site, key, size))
        print(f'  [{region}] {sum(1 for s,k,z in results if k.split("/")[2]==region)} velocity files')
    return results


def load_state():
    if STATE_FILE.exists():
        with open(STATE_FILE) as f: return json.load(f)
    return {'completed': {}, 'failed': {}}


def save_state(state):
    tmp = STATE_FILE.with_suffix('.json.tmp')
    with open(tmp, 'w') as f: json.dump(state, f, indent=2)
    tmp.replace(STATE_FILE)


def download_one(site, key, size, dest):
    url = f'{S3_BASE}/{key}'
    tmp = dest.with_suffix('.nc.tmp')
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=120) as r:
        with open(tmp, 'wb') as f:
            while True:
                chunk = r.read(1024*1024)
                if not chunk: break
                f.write(chunk)
    tmp.replace(dest)
    actual = dest.stat().st_size
    if size and actual != size:
        return False, f'size mismatch {actual} != {size}'
    return True, actual


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--workers', type=int, default=4)
    ap.add_argument('--overwrite', action='store_true')
    args = ap.parse_args()

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    state = load_state()

    print('Crawling S3 bucket for velocity NCs...')
    items = crawl_all_velocity()
    print(f'\nTotal velocity files found: {len(items)}')
    total_bytes = sum(z for _, _, z in items)
    print(f'Total size: {total_bytes/1e9:.1f} GB')

    # one file per site — if multiple, keep newest (name sort works with dates)
    by_site = {}
    for site, key, size in items:
        if site not in by_site or key > by_site[site][1]:
            by_site[site] = (site, key, size)
    items = sorted(by_site.values())
    print(f'After dedup by site: {len(items)} files')

    if args.dry_run:
        for site, key, size in items[:20]:
            print(f'  {site:12s} {size/1e6:7.1f} MB  {key}')
        if len(items) > 20: print(f'  ... ({len(items)-20} more)')
        return

    t_start = time.time()
    done_count = len([k for k in state['completed']])
    print(f'\nStarting download ({done_count} already complete)...')

    def worker(item):
        site, key, size = item
        dest = RAW_DIR / f'{site}.nc'
        if not args.overwrite and site in state['completed'] and dest.exists() \
                and dest.stat().st_size == size:
            return site, 'skip', size
        try:
            ok, info = download_one(site, key, size, dest)
        except Exception as e:
            return site, 'error', str(e)
        return site, 'ok', info

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(worker, it): it for it in items}
        for i, fut in enumerate(as_completed(futs), 1):
            site, status, info = fut.result()
            if status == 'ok':
                state['completed'][site] = {'size': info, 'time': time.time()}
                print(f'  [{i:3d}/{len(items)}] {site:12s} OK  ({info/1e6:.1f} MB)')
            elif status == 'skip':
                print(f'  [{i:3d}/{len(items)}] {site:12s} already done')
            else:
                state['failed'][site] = info
                print(f'  [{i:3d}/{len(items)}] {site:12s} FAIL {info}')
            if i % 5 == 0:
                save_state(state)

    save_state(state)
    dur = time.time() - t_start
    print(f'\nDone in {dur:.0f}s. Completed: {len(state["completed"])}, Failed: {len(state["failed"])}')


if __name__ == '__main__':
    main()
