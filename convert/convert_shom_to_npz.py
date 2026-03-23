#!/usr/bin/env python3
"""
Convert SHOM REFMAR raw JSON files to NPZ format.

Input:  JSON files with 10-min observations (source 3 = validated), datum: ZH (hydrographic zero)
Output: NPZ with datetimes_utc (datetime64) and levels_m (float64)

Also extracts station metadata from SML files.
"""

import json
import glob
import numpy as np
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime

RAW_DIR = Path("/home/oliver/water_levels/France_SHOM/raw_json")
OUTPUT_DIR = Path("/home/oliver/water_levels/France_SHOM/npz")


def parse_sml(sml_path):
    """Extract station metadata from SML file."""
    try:
        tree = ET.parse(sml_path)
        root = tree.getroot()
        ns = {'sml': 'http://www.opengis.net/sensorML/1.0.1',
              'swe': 'http://www.opengis.net/swe/1.0.1'}
        vals = [v.text for v in root.findall('.//swe:value', ns)]
        if len(vals) >= 4:
            return {
                'name': vals[0],
                'longitude': float(vals[2]),
                'latitude': float(vals[3]),
            }
    except Exception:
        pass
    return {'name': sml_path.stem, 'longitude': 0.0, 'latitude': 0.0}


def convert_station(station_id):
    """Convert all JSON year files for one station to a single NPZ."""
    sml_path = RAW_DIR / f"{station_id}.sml"
    npz_path = OUTPUT_DIR / f"{station_id}.npz"

    if npz_path.exists():
        d = np.load(npz_path, allow_pickle=True)
        n = len(d['levels_m'])
        years = n / (6 * 24 * 365.25)
        print(f"  already exists ({n} values, {years:.1f}y)")
        return True

    # Get metadata
    meta = parse_sml(sml_path) if sml_path.exists() else {
        'name': station_id, 'longitude': 0.0, 'latitude': 0.0}

    # Load all year JSONs
    json_files = sorted(glob.glob(str(RAW_DIR / f"{station_id}_*.json")))
    if not json_files:
        print(f"  no JSON files")
        return False

    timestamps = []
    values = []

    for jf in json_files:
        try:
            with open(jf) as f:
                data = json.load(f)
            for entry in data.get('data', []):
                if entry.get('value') is not None:
                    timestamps.append(entry['timestamp'])
                    values.append(float(entry['value']))
        except (json.JSONDecodeError, KeyError):
            continue

    if not timestamps:
        print(f"  no data")
        return False

    # Parse timestamps (format: "2007/01/01 00:00:00")
    datetimes = np.array([np.datetime64(t.replace('/', '-')) for t in timestamps])

    # Sort and deduplicate
    sort_idx = np.argsort(datetimes)
    datetimes = datetimes[sort_idx]
    levels = np.array(values, dtype=np.float64)[sort_idx]

    # Remove duplicates
    _, unique_idx = np.unique(datetimes, return_index=True)
    datetimes = datetimes[unique_idx]
    levels = levels[unique_idx]

    # Save NPZ
    np.savez_compressed(
        npz_path,
        datetimes_utc=datetimes,
        levels_m=levels,
        name=meta['name'],
        latitude=meta['latitude'],
        longitude=meta['longitude'],
        station_id=station_id,
    )

    years = len(levels) / (6 * 24 * 365.25)
    print(f"  {meta['name']}: {len(levels)} values ({years:.1f}y)")
    return True


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Find all station IDs from SML files
    sml_files = sorted(RAW_DIR.glob("*.sml"), key=lambda p: int(p.stem) if p.stem.isdigit() else 0)
    station_ids = [f.stem for f in sml_files]

    print("=" * 70)
    print("Convert SHOM REFMAR JSON -> NPZ")
    print(f"Stations: {len(station_ids)}")
    print("=" * 70)

    success = 0
    for i, sid in enumerate(station_ids):
        print(f"\n[{i+1}/{len(station_ids)}] Station {sid}")
        if convert_station(sid):
            success += 1

    print(f"\n{'='*70}")
    print(f"Result: {success}/{len(station_ids)} converted")

    total_mb = sum(f.stat().st_size for f in OUTPUT_DIR.glob("*.npz")) / (1024*1024)
    print(f"Total NPZ size: {total_mb:.1f} MB")


if __name__ == '__main__':
    main()
