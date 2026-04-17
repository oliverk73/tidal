#!/usr/bin/env python3
"""Download SAEON / DEA-MIMS current mooring ZIPs for South Africa.

Records curated from the SAEON catalogue (catalogue.saeon.ac.za) that host
hourly-sampled ADCP mooring currents on the public Nextcloud
(repository.ocean.gov.za, no login).

Output: currents/South_Africa_SAEON/raw/<doi_stub>.zip
"""
import argparse
import sys
import urllib.request
from pathlib import Path

HOME = Path.home()
RAW_DIR = HOME / 'currents' / 'South_Africa_SAEON' / 'raw'

# (doi_stub, nextcloud share id)
RECORDS = [
    ('DEA_MIMS_41042025', 'orTHZ2e4t79Ry2c'),  # Algoa Bay 2005-2014 (big bundle)
    ('DEA_MIMS_78072024', 'aofA9qWg2Zdjx47'),  # KZN Bight 2009-2013
    ('DEA_MIMS_29112024', 'ziTp3WcCjs5REHD'),  # Port St Johns (both deployments)
    ('DEA_MIMS_30042025', 'cwdmNrmopBZFMSW'),  # Walters Shoal (both moorings)
]

NC_BASE = 'https://repository.ocean.gov.za/index.php/s'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--overwrite', action='store_true')
    args = ap.parse_args()

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    for stub, share in RECORDS:
        dest = RAW_DIR / f'{stub}.zip'
        if dest.exists() and not args.overwrite:
            print(f'{stub}: exists ({dest.stat().st_size/1e6:.1f} MB), skip')
            continue
        url = f'{NC_BASE}/{share}/download'
        print(f'{stub}: downloading from {url}')
        try:
            with urllib.request.urlopen(url, timeout=120) as r:
                data = r.read()
        except Exception as e:
            print(f'  FAILED: {e}', file=sys.stderr)
            continue
        dest.write_bytes(data)
        print(f'  -> {dest} ({len(data)/1e6:.1f} MB)')


if __name__ == '__main__':
    main()
