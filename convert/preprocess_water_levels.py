#!/usr/bin/env python3
"""
Pre-process Pegelonline ZIP files → compact NPZ files.
Converts 1-minute JSON water level data to hourly numpy arrays.

Output per station: {station_key}.npz containing:
  - datetimes_utc: array of datetime objects (hourly, UTC)
  - levels_cm: array of int16 water levels in cm (saves space)
  - station_key: string identifier
"""
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
import zipfile
import ijson
import os
import sys
import time
from multiprocessing import Pool, cpu_count


INPUT_DIR = Path("/home/oliver/water_levels/Germany")
OUTPUT_DIR = Path("/home/oliver/water_levels/Germany/npz")
SAMPLE_INTERVAL = 60  # minutes (hourly)


def extract_zip_key(filename):
    """Extract station key from ZIP filename."""
    basename = os.path.basename(filename)
    parts = basename.replace('.zip', '').split('-')
    if len(parts) >= 2:
        return parts[1].lower()
    return None


def convert_one_station(zip_path):
    """Convert a single ZIP to NPZ. Returns (key, n_obs, duration_sec) or (key, 0, error_msg)."""
    t0 = time.time()
    zip_path = Path(zip_path)
    key = extract_zip_key(str(zip_path))
    if not key:
        return (str(zip_path), 0, "no key")

    npz_path = OUTPUT_DIR / f"{key}.npz"

    # Skip if already converted and newer than ZIP
    if npz_path.exists() and npz_path.stat().st_mtime > zip_path.stat().st_mtime:
        # Load to report count
        try:
            d = np.load(npz_path, allow_pickle=True)
            n = len(d['levels_cm'])
            return (key, n, time.time() - t0, "skipped")
        except:
            pass  # re-convert

    datetimes_utc = []
    levels_cm = []
    count = 0
    nulls = 0

    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            json_name = None
            for name in zf.namelist():
                if name.endswith('.json') and ':' not in name:
                    json_name = name
                    break
            if json_name is None:
                return (key, 0, time.time() - t0, "no JSON in ZIP")

            with zf.open(json_name) as f:
                for entry in ijson.items(f, 'item'):
                    count += 1
                    if count % SAMPLE_INTERVAL != 0:
                        continue

                    val = entry.get('value')
                    if val is None:
                        nulls += 1
                        continue

                    ts = entry['timestamp']
                    ts_base = ts[:19]

                    try:
                        dt_local = datetime.strptime(ts_base, "%Y-%m-%dT%H:%M:%S")

                        # Parse UTC offset from timestamp
                        if '+' in ts[19:]:
                            oh = int(ts[20:22])
                            om = int(ts[23:25]) if len(ts) > 23 else 0
                            dt_utc = dt_local - timedelta(hours=oh, minutes=om)
                        elif '-' in ts[19:]:
                            oh = int(ts[20:22])
                            om = int(ts[23:25]) if len(ts) > 23 else 0
                            dt_utc = dt_local + timedelta(hours=oh, minutes=om)
                        else:
                            dt_utc = dt_local - timedelta(hours=1)

                        datetimes_utc.append(dt_utc)
                        levels_cm.append(int(round(float(val))))
                    except:
                        nulls += 1
                        continue

    except Exception as e:
        return (key, 0, time.time() - t0, str(e))

    if len(datetimes_utc) < 100:
        return (key, 0, time.time() - t0, f"only {len(datetimes_utc)} obs")

    # Save as NPZ
    dt_arr = np.array(datetimes_utc, dtype='datetime64[s]')
    lv_arr = np.array(levels_cm, dtype=np.int32)

    np.savez_compressed(npz_path, datetimes_utc=dt_arr, levels_cm=lv_arr)

    duration = time.time() - t0
    return (key, len(datetimes_utc), duration, "ok")


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    zip_files = sorted(INPUT_DIR.glob("*.zip"))
    zip_files = [f for f in zip_files if ':' not in str(f)]
    print(f"Found {len(zip_files)} ZIP files")
    print(f"Output: {OUTPUT_DIR}")
    print(f"Sampling: every {SAMPLE_INTERVAL} minutes")
    print()

    n_workers = min(4, cpu_count())
    print(f"Processing with {n_workers} parallel workers...")
    print(f"{'#':>4s}  {'Station':<35s} {'Obs':>8s} {'Time':>6s} {'Status'}")
    print(f"{'─'*4}  {'─'*35} {'─'*8} {'─'*6} {'─'*10}")

    t_start = time.time()

    with Pool(n_workers) as pool:
        results = pool.map(convert_one_station, zip_files)

    total_obs = 0
    ok_count = 0
    skip_count = 0
    fail_count = 0

    for i, result in enumerate(results):
        key, n_obs, duration, status = result
        total_obs += n_obs
        symbol = "✓" if status == "ok" else ("→" if status == "skipped" else "✗")
        if status == "ok":
            ok_count += 1
        elif status == "skipped":
            skip_count += 1
        else:
            fail_count += 1
        print(f"{i+1:>4d}  {key:<35s} {n_obs:>8d} {duration:>5.1f}s {symbol} {status}")

    t_total = time.time() - t_start
    print(f"\n{'='*70}")
    print(f"Done in {t_total:.0f}s ({t_total/60:.1f} min)")
    print(f"  Converted: {ok_count}, Skipped: {skip_count}, Failed: {fail_count}")
    print(f"  Total observations: {total_obs:,}")

    # Show disk usage
    npz_size = sum(f.stat().st_size for f in OUTPUT_DIR.glob("*.npz"))
    zip_size = sum(f.stat().st_size for f in zip_files)
    print(f"  ZIP total: {zip_size/1024**2:.0f} MB → NPZ total: {npz_size/1024**2:.1f} MB")


if __name__ == "__main__":
    main()
