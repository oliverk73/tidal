#!/usr/bin/env python3
"""
Generate XTide-compatible harmonic constants for Central/Southern West African
tide stations (Cameroon → Angola) from UHSLC hourly sea-level data using UTide.

Stations:
  816  Port Sonara, Cameroon               (FD, 3.0y)
  225  Sao Tome, Sao Tome and Principe     (FD, 5.9y)
  236a Luanda,  Angola                     (RQ, 3.5y)
  237a Lobito,  Angola                     (RQ, 4.6y)
  238a Mocamedes (Namibe), Angola          (RQ, 3.9y)

Notes:
  - Gabon, Equatorial Guinea, Republic of the Congo and DR Congo have no UHSLC
    stations. SHOM predictions already cover Gabon (Libreville, Port-Gentil)
    and Cameroon (Douala, Port Sonara) in harmonics_utide_shom.txt.
"""
import numpy as np
from datetime import datetime
from pathlib import Path
import pandas as pd
import utide

UHSLC_STATIONS = [
    {'uhslc_id': 816, 'version': 'fd', 'name': 'Port Sonara',
     'country': 'Cameroon',
     'lat':  4.2170, 'lon':   9.1330, 'water': 'Atlantic Ocean (Gulf of Guinea)',
     'csv': '/home/oliver/water_levels/CentralWestAfrica_UHSLC/port_sonara_cameroon.csv'},
    {'uhslc_id': 225, 'version': 'fd', 'name': 'Sao Tome',
     'country': 'Sao Tome and Principe',
     'lat':  0.3480, 'lon':   6.7370, 'water': 'Atlantic Ocean (Gulf of Guinea)',
     'csv': '/home/oliver/water_levels/CentralWestAfrica_UHSLC/sao_tome_stp.csv'},
    {'uhslc_id': 236, 'version': 'a',  'name': 'Luanda',
     'country': 'Angola',
     'lat': -8.7870, 'lon':  13.2370, 'water': 'Atlantic Ocean',
     'csv': '/home/oliver/water_levels/CentralWestAfrica_UHSLC/luanda_angola.csv'},
    {'uhslc_id': 237, 'version': 'a',  'name': 'Lobito',
     'country': 'Angola',
     'lat': -12.3330, 'lon': 13.5580, 'water': 'Atlantic Ocean',
     'csv': '/home/oliver/water_levels/CentralWestAfrica_UHSLC/lobito_angola.csv'},
    {'uhslc_id': 238, 'version': 'a',  'name': 'Mocamedes',
     'country': 'Angola',
     'lat': -15.1920, 'lon': 12.1450, 'water': 'Atlantic Ocean',
     'csv': '/home/oliver/water_levels/CentralWestAfrica_UHSLC/mocamedes_angola.csv'},
]

from generate_caribbean_harmonics import (
    CONSTITUENTS_175, find_xtide_match,
    harmonic_analysis_utide, read_header_from_template,
)

MAX_YEARS = 10.0


def load_uhslc_csv_limited(csv_path, max_years=MAX_YEARS):
    df = pd.read_csv(csv_path)
    df['datetime_utc'] = pd.to_datetime(df['datetime_utc'], utc=True)
    df = df.dropna(subset=['level_mm'])
    df = df[df['level_mm'] != -32767]
    levels = df['level_mm'].values / 1000.0
    times = df['datetime_utc']
    max_obs = int(max_years * 365.25 * 24)
    if len(times) > max_obs:
        times = times.iloc[-max_obs:]
        levels = levels[-max_obs:]
    dt_list = [pd.Timestamp(t).to_pydatetime().replace(tzinfo=None) for t in times]
    n_obs = len(dt_list)
    if n_obs < 2000:
        return None
    first, last = dt_list[0], dt_list[-1]
    years = (last - first).total_seconds() / (365.25 * 86400)
    return {'datetimes_utc': np.array(dt_list), 'levels': np.array(levels),
            'start_time': first, 'end_time': last, 'n_obs': n_obs, 'years': years}


def format_station_block(station, results, data, source_label):
    name = station['name']
    full_name = f"{name}, {station['country']}"
    lines = []
    lines.append(f"# Harmonic constants derived from {source_label}")
    lines.append(f"# using UTide (v{utide.__version__}) with {data['n_obs']} observations")
    lines.append(f"# from {data['start_time'].strftime('%Y-%m-%d')} to {data['end_time'].strftime('%Y-%m-%d')}")
    lines.append(f"# R^2 = {results['r_squared']:.4f}, RMS error = {results['rms_error']:.4f} m")
    lines.append(f"# Constituents analyzed: {results['n_analyzed']}")
    lines.append(f"#")
    lines.append(f"# {full_name}")
    lines.append(f"# BEGIN HOT COMMENTS")
    lines.append(f"# country: {station['country']}")
    lines.append(f"# water body: {station['water']}")
    lines.append(f"# source: Derived from UHSLC data with UTide harmonic analysis")
    lines.append(f"# station_id_context: UHSLC-{station['uhslc_id']}{station['version']}")
    lines.append(f"# date_imported: {datetime.now().strftime('%Y%m%d')}")
    lines.append(f"# datum: Mean Sea Level")
    lines.append(f"# confidence: 7")
    lines.append(f"# !units: meters")
    lines.append(f"# !longitude: {station['lon']:.6f}")
    lines.append(f"# !latitude: {station['lat']:.6f}")
    lines.append(full_name)
    lines.append(f"+00:00 :UTC")
    lines.append(f"0.0000 meters")
    for c in results['constituents']:
        if c.get('not_analyzed') or c['amplitude'] < 0.00005:
            lines.append(f"x 0 0")
        else:
            lines.append(f"{c['name']:15s} {c['amplitude']:.4f}  {c['phase']:.2f}")
    return '\n'.join(lines)


def main():
    template_path = Path('/home/oliver/harmonics/template/harmonics_template.txt')
    output_path = Path('/home/oliver/harmonics/utide/harmonics_utide_cameroon_angola.txt')

    print("=" * 70)
    print("Generate Cameroon → Angola Harmonics with UTide (UHSLC)")
    print("=" * 70)

    header = read_header_from_template(template_path)
    station_blocks = []
    processed = 0
    failed = 0

    for station in UHSLC_STATIONS:
        sid = station['uhslc_id']
        ver = station['version']
        name = station['name']
        print(f"\n[UHSLC-{sid}{ver}] {name}, {station['country']}...")

        csv_path = Path(station['csv'])
        if not csv_path.exists():
            print(f"  NO DATA FILE: {csv_path}")
            failed += 1
            continue

        data = load_uhslc_csv_limited(csv_path)
        if data is None:
            print("  INSUFFICIENT DATA")
            failed += 1
            continue

        print(f"  {data['n_obs']} obs ({data['years']:.1f}y) from {data['start_time'].strftime('%Y-%m-%d')} to {data['end_time'].strftime('%Y-%m-%d')}")
        print(f"  Running UTide...", end='', flush=True)

        results = harmonic_analysis_utide(data['datetimes_utc'], data['levels'], station['lat'])
        if results is None:
            print(" FAILED")
            failed += 1
            continue

        m2 = next((c['amplitude'] for c in results['constituents'] if c['name'] == 'M2'), 0)
        m2p = next((c['phase'] for c in results['constituents'] if c['name'] == 'M2'), 0)
        print(f" OK (R^2={results['r_squared']:.3f}, M2={m2:.3f}m@{m2p:.1f}deg, constit={results['n_analyzed']})")

        block = format_station_block(station, results, data, "UHSLC sea level data")
        station_blocks.append(block)
        processed += 1

    print(f"\n{'='*70}")
    print(f"Processed: {processed}, Failed: {failed}")

    if not station_blocks:
        print("No stations processed!")
        return

    print(f"\nWriting {len(station_blocks)} stations to {output_path}...")
    with open(output_path, 'w', encoding='latin-1') as f:
        f.write(header)
        f.write('\n')
        for block in station_blocks:
            f.write(block)
            f.write('\n')

    print(f"Done! {output_path}")


if __name__ == "__main__":
    main()
