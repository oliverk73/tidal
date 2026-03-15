#!/usr/bin/env python3
"""
Convert Hamburg HPA water level CSV files to NPZ format.

Input:  1-minute CSV data in cm Seekartennull (SKN), timezone MEZ (UTC+1)
Output: 10-minute resampled NPZ with datetimes_utc and levels_cm (in PNP)

Conversion: PNP_cm = SKN_cm - OffsetZuNN + |PNP_offset_NHN| * 100
"""

import numpy as np
from pathlib import Path
from datetime import datetime, timedelta
import glob
import re

INPUT_DIR = Path("/home/oliver/water_levels/Germany/HH")
OUTPUT_DIR = Path("/home/oliver/water_levels/Germany/HH/npz")
USE_LAST_N_YEARS = 19
RESAMPLE_MINUTES = 10

# Station metadata from tide_stations_hamburg.ods
# prefix: (station_name, pnp_offset_nhn_m, latitude, longitude, water_body)
STATIONS = {
    'STP': ('Hamburg (St. Pauli)', -5.00, 53.5456, 9.9700, 'Norderelbe'),
    'HAR': ('Hamburg-Harburg (Elbe, Schleuse)', -5.02, 53.473, 9.992, 'Süderelbe'),
    'UBN': ('Hamburg-Blankenese (Elbe, Unterfeuer)', -5.02, 53.558, 9.796, 'Elbe'),
    'SMH': ('Hamburg Seemannshöft (Elbe)', -5.02, 53.540, 9.881, 'Norderelbe'),
    'SPS': ('Hamburg Dove-Elbe (Einfahrt)', -5.02, 53.508, 10.062, 'Dove-Elbe'),
    'BHS': ('Hamburg-Bunthaus (Elbe)', -5.02, 53.461, 10.064, 'Norderelbe'),
}


def parse_csv(filepath):
    """Parse HPA CSV file. Returns (datetimes_mez, levels_skn_cm, offset_nn)."""
    datetimes = []
    levels = []
    offset_nn = None

    with open(filepath, 'r', encoding='utf-8-sig') as f:
        in_data = False
        for line in f:
            line = line.strip()
            if line.startswith('Datum/Uhrzeit'):
                in_data = True
                continue
            if not in_data:
                continue

            parts = line.split(';')
            if len(parts) < 4:
                continue
            try:
                dt = datetime.strptime(parts[0], '%Y-%m-%d %H:%M:%S')
                level = int(parts[1])
                if offset_nn is None:
                    offset_nn = float(parts[3].replace(',', '.'))
                datetimes.append(dt)
                levels.append(level)
            except (ValueError, IndexError):
                continue

    return datetimes, levels, offset_nn


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for prefix, (name, pnp_nhn, lat, lon, water) in STATIONS.items():
        print(f"\n{'='*70}")
        print(f"Station: {name} ({prefix})")
        print(f"{'='*70}")

        # Find all CSV files for this station
        csv_files = sorted(glob.glob(str(INPUT_DIR / f"Pegel_{prefix}_*.csv")))
        csv_files = [f for f in csv_files if 'Zone' not in f]
        print(f"  CSV files: {len(csv_files)}")

        # Parse all files
        all_datetimes = []
        all_levels = []
        offset_nn = None

        for csv_path in csv_files:
            dts, lvls, off = parse_csv(csv_path)
            if off is not None and offset_nn is None:
                offset_nn = off
            all_datetimes.extend(dts)
            all_levels.extend(lvls)

        if not all_datetimes:
            print(f"  SKIP: no data")
            continue

        print(f"  Total observations: {len(all_datetimes):,}")
        print(f"  Date range: {all_datetimes[0]} to {all_datetimes[-1]} (MEZ)")
        print(f"  OffsetZuNN: {offset_nn}")

        # Convert to numpy datetime64 directly (much faster than python datetime arrays)
        import pandas as pd
        dt_series = pd.to_datetime(all_datetimes)
        level_array = np.array(all_levels, dtype=np.float64)

        # Build DataFrame for fast resampling
        df = pd.DataFrame({'level': level_array}, index=dt_series)
        df = df[~df.index.duplicated(keep='first')]
        print(f"  After dedup: {len(df):,}")

        # Use last N years
        cutoff = df.index[-1] - pd.Timedelta(days=USE_LAST_N_YEARS * 365.25)
        df = df[df.index >= cutoff]
        print(f"  Last {USE_LAST_N_YEARS} years: {len(df):,} ({df.index[0]} to {df.index[-1]})")

        # Convert MEZ → UTC (subtract 1 hour)
        df.index = df.index - pd.Timedelta(hours=1)

        # Resample to 10-minute intervals (median, fast with pandas)
        print(f"  Resampling to {RESAMPLE_MINUTES}-minute intervals...")
        df_resampled = df.resample(f'{RESAMPLE_MINUTES}min').median().dropna()

        dt64_resampled = df_resampled.index.values.astype('datetime64[s]')
        levels_resampled = df_resampled['level'].values

        # Convert SKN cm → PNP cm
        # NHN_cm = SKN_cm - OffsetZuNN
        # PNP_cm = NHN_cm - PNP_offset_NHN_cm = NHN_cm + |PNP_offset|*100
        pnp_offset_cm = abs(pnp_nhn) * 100
        levels_pnp_cm = levels_resampled - offset_nn + pnp_offset_cm

        print(f"  Resampled: {len(dt64_resampled):,} data points")
        print(f"  SKN mean: {np.mean(levels_resampled):.1f} cm")
        print(f"  PNP mean: {np.mean(levels_pnp_cm):.1f} cm ({np.mean(levels_pnp_cm)/100:.3f} m)")

        # Check for gaps
        dt_diff = np.diff(dt64_resampled) / np.timedelta64(1, 'm')
        n_gaps = np.sum(dt_diff > RESAMPLE_MINUTES * 2)
        max_gap = np.max(dt_diff)
        print(f"  Gaps (>{RESAMPLE_MINUTES*2}min): {n_gaps}, max gap: {max_gap:.0f} min ({max_gap/60:.1f}h)")

        # Save NPZ
        npz_path = OUTPUT_DIR / f"{prefix}.npz"
        np.savez_compressed(
            npz_path,
            datetimes_utc=dt64_resampled,
            levels_cm=levels_pnp_cm,
            station_name=name,
            latitude=lat,
            longitude=lon,
            water_body=water,
            pnp_offset_nhn=pnp_nhn,
            offset_nn=offset_nn,
            resample_minutes=RESAMPLE_MINUTES,
        )
        print(f"  Saved: {npz_path} ({npz_path.stat().st_size / 1024:.0f} KB)")


if __name__ == '__main__':
    main()
