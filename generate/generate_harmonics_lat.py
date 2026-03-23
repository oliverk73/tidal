#!/usr/bin/env python3
"""
Generate Harmonic Constants from German Pegelonline water level measurements.
Uses UTide for harmonic analysis and outputs in LAT/SKN reference level.

Reads SKN offsets from BSH E-Format files (D03 field: SKN über PNP).
"""
import numpy as np
from datetime import datetime, timedelta
import os
import json
import zipfile
import re
from pathlib import Path
import pandas as pd
import utide

# Directories
WATER_LEVELS_DIR = Path("/home/oliver/water_levels/Germany")
BSH_DIR = Path("/home/oliver/harmonics/help/BSH")
ODS_FILE = Path("/home/oliver/harmonics/help/tide_stations_pegelonline.ods")
OUTPUT_DIR = Path("/home/oliver/harmonics/utide/harmonics_utide_lat")


def extract_skn_offset_from_bsh(bsh_file):
    """
    Extract SKN über PNP (D03) value from BSH E-Format file.
    Returns the offset in meters, or None if not found.
    """
    try:
        with open(bsh_file, 'r', encoding='latin-1') as f:
            content = f.read()

        # Look for D03 line: D03#SKN ü. PNP :#  3.02 #
        match = re.search(r'D03#SKN.*?PNP.*?#\s*([\d.-]+)\s*#', content)
        if match:
            return float(match.group(1))

        # Alternative pattern
        match = re.search(r'D03#.*?#\s*([\d.-]+)\s*#', content)
        if match:
            return float(match.group(1))

    except Exception as e:
        print(f"  Error reading {bsh_file}: {e}")

    return None


def extract_station_info_from_bsh(bsh_file):
    """Extract station name, coordinates, and reference levels from BSH file."""
    info = {}
    try:
        with open(bsh_file, 'r', encoding='latin-1') as f:
            for line in f:
                if line.startswith('A04#GT-Name'):
                    # A04#GT-Name    :#Cuxhaven, Steubenhöft, Elbe#
                    match = re.search(r'A04#.*?:#(.+?)#', line)
                    if match:
                        info['name'] = match.group(1).strip()

                elif line.startswith('A08#Position'):
                    # A08#Position   :#53°52'04''N   8°43'03''E WGS84#
                    match = re.search(r"(\d+)°(\d+)'(\d+)''([NS])\s+(\d+)°(\d+)'(\d+)''([EW])", line)
                    if match:
                        lat_d, lat_m, lat_s, lat_dir = match.groups()[:4]
                        lon_d, lon_m, lon_s, lon_dir = match.groups()[4:]
                        lat = float(lat_d) + float(lat_m)/60 + float(lat_s)/3600
                        lon = float(lon_d) + float(lon_m)/60 + float(lon_s)/3600
                        if lat_dir == 'S': lat = -lat
                        if lon_dir == 'W': lon = -lon
                        info['lat'] = lat
                        info['lon'] = lon

                elif line.startswith('D01#PNP'):
                    match = re.search(r'D01#.*?#\s*([\d.-]+)\s*#', line)
                    if match:
                        info['pnp_nhn'] = float(match.group(1))

                elif line.startswith('D02#SKN'):
                    match = re.search(r'D02#.*?#\s*([\d.-]+)\s*#', line)
                    if match:
                        info['skn_nhn'] = float(match.group(1))

                elif line.startswith('D03#SKN'):
                    match = re.search(r'D03#.*?#\s*([\d.-]+)\s*#', line)
                    if match:
                        info['skn_pnp'] = float(match.group(1))

                elif line.startswith('G01#MHW'):
                    match = re.search(r'G01#.*?#\s*([\d.-]+)\s*#', line)
                    if match:
                        info['mhw'] = float(match.group(1))

                elif line.startswith('G02#MNW'):
                    match = re.search(r'G02#.*?#\s*([\d.-]+)\s*#', line)
                    if match:
                        info['mnw'] = float(match.group(1))

    except Exception as e:
        print(f"  Error parsing {bsh_file}: {e}")

    return info


def find_zip_file_for_station(station_name, zip_files):
    """
    Find the matching ZIP file for a station name.
    Uses fuzzy matching on normalized names.
    """
    def normalize(s):
        s = s.lower()
        # Remove ", Germany" and parenthetical parts
        s = re.sub(r',\s*germany$', '', s)
        s = re.sub(r'\s*\([^)]*\)', '', s)
        # Replace umlauts
        s = s.replace('ä', 'a').replace('ö', 'o').replace('ü', 'u').replace('ß', 'ss')
        # Remove non-alphanumeric
        s = re.sub(r'[^a-z0-9]', '', s)
        return s

    station_norm = normalize(station_name)

    for zf in zip_files:
        # Extract key from filename: pegelonline-cuxhavensteubenhft-W-...
        parts = zf.stem.split('-')
        if len(parts) >= 2:
            zip_key = normalize(parts[1])

            # Check for match
            if zip_key in station_norm or station_norm in zip_key:
                return zf

            # Check overlap
            if len(set(zip_key) & set(station_norm)) > min(len(zip_key), len(station_norm)) * 0.6:
                return zf

    return None


# Manual mapping for difficult cases
ZIP_MAPPING = {
    'Altengamme': 'altengamme',
    'Bake Z': 'bakez',
    'Belum (Oste)': 'belum',
    'Borkum (Fischerbalje)': 'borkumfischerbalje',
    'Borkum (Südstrand)': 'borkumsdstrand',
    'Breitenberg (Stör)': 'breitenberg',
    'Bremen (Wilhelm-Kaisen-Brücke, Weser)': 'grosseweserbrcke',
    'Bremen-Borgfeld (Wümme)': 'borgfeld',
    'Bremen-Weserwehr (Unterpegel)': 'weserwehruw',
    'Bremerhaven (Alter Leuchtturm)': 'bhvalterleuchtturm',
    'Bremervörde (Oste)': 'bremervrdeuw',
    'Brokdorf (Elbe)': 'brokdorf',
    'Brunsbüttel (Elbe)': 'brunsbttelmpm',
    'Büsum (Schleuse)': 'büsum',
    'Buttelerhörne (Hunte)': 'buttelerhrne',
    'Buxtehude (Este)': 'buxtehude',
    'Cranz (Este-Sperrwerk)': 'cranz',
    'Cuxhaven-Steubenhöft (Elbe)': 'cuxhavensteubenhft',
    'Dreyschloot (Leda)': 'dreyschloot',
    'Dukegat': 'dukegat',
    'Dwarsgat (Unterfeuer)': 'dwarsgat',
}


def parse_pegelonline_zip(zip_path, sample_interval_minutes=60, use_last_n_years=None):
    """
    Parse water level data from Pegelonline ZIP file.
    Returns UTC datetime array and levels in meters (PNP reference).
    """
    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            for name in zf.namelist():
                if name.endswith(':Zone.Identifier'):
                    continue
                with zf.open(name) as f:
                    content = f.read()
                    break
    except Exception as e:
        print(f"  Error opening ZIP: {e}")
        return None

    try:
        data = json.loads(content.decode('utf-8'))
    except:
        print(f"  Error parsing JSON")
        return None

    if not data or len(data) < 1000:
        print(f"  Insufficient data: {len(data) if data else 0} records")
        return None

    # Use only the last n years of data if specified
    if use_last_n_years:
        samples_per_year = 365 * 24 * 60  # 1-minute data
        max_samples = use_last_n_years * samples_per_year
        if len(data) > max_samples:
            data = data[-max_samples:]

    datetimes_utc = []
    levels = []

    # Sample at specified interval
    for i in range(0, len(data), sample_interval_minutes):
        entry = data[i]
        value = entry.get('value')

        if value is None:
            continue

        ts_str = entry['timestamp']
        try:
            # Parse timestamp: "2000-01-01T01:00:00+01:00" (CET)
            ts_base = ts_str[:19]
            dt_local = datetime.strptime(ts_base, "%Y-%m-%dT%H:%M:%S")

            # Parse UTC offset
            if '+' in ts_str[19:]:
                offset_str = ts_str[19:].lstrip('+')
                offset_parts = offset_str.split(':')
                offset_hours = int(offset_parts[0])
                utc_offset = timedelta(hours=offset_hours)
            elif '-' in ts_str[19:]:
                offset_str = ts_str[19:].lstrip('-')
                offset_parts = offset_str.split(':')
                offset_hours = int(offset_parts[0])
                utc_offset = -timedelta(hours=offset_hours)
            else:
                utc_offset = timedelta(hours=1)  # Default CET

            # Convert to UTC
            dt_utc = dt_local - utc_offset

            level = float(value) / 100.0  # cm to meters
            datetimes_utc.append(dt_utc)
            levels.append(level)
        except:
            continue

    if len(datetimes_utc) < 8760:  # Minimum ~1 year of hourly data
        print(f"  Warning: only {len(datetimes_utc)} observations")
        if len(datetimes_utc) < 2000:
            return None

    return {
        'datetimes_utc': np.array(datetimes_utc),
        'levels': np.array(levels),
        'start_time': datetimes_utc[0],
        'end_time': datetimes_utc[-1],
        'n_obs': len(datetimes_utc)
    }


def run_utide_analysis(datetimes_utc, levels, lat):
    """
    Run UTide harmonic analysis.
    Returns coefficients with Greenwich phase lags.
    """
    try:
        coef = utide.solve(
            datetimes_utc,
            levels,
            lat=lat,
            nodal=True,
            trend=False,
            method='ols',
            conf_int='linear',
            verbose=False,
            constit='auto',
        )
    except Exception as e:
        print(f"  UTide error: {e}")
        return None

    # Calculate goodness of fit
    try:
        reconstruction = utide.reconstruct(datetimes_utc, coef, verbose=False)
        h_predicted = reconstruction['h']
        residuals = levels - h_predicted
        ss_res = np.sum(residuals**2)
        ss_tot = np.sum((levels - np.mean(levels))**2)
        r_squared = 1 - ss_res / ss_tot if ss_tot > 0 else 0
        rms_error = np.sqrt(np.mean(residuals**2))
    except:
        r_squared = 0
        rms_error = 0

    return {
        'coef': coef,
        'mean_pnp': coef['mean'],
        'r_squared': r_squared,
        'rms_error': rms_error,
        'n_constituents': len(coef['name']),
    }


def format_harmonics_output(station_name, lat, lon, bsh_info, utide_results, data_info, skn_offset):
    """
    Format harmonics in XTide-compatible format with LAT/SKN reference.
    """
    coef = utide_results['coef']
    mean_pnp = utide_results['mean_pnp']
    mean_lat = mean_pnp - skn_offset  # Convert to LAT

    lines = []
    lines.append(f"# Harmonic constants derived from Pegelonline water level data")
    lines.append(f"# using UTide with {data_info['n_obs']} observations")
    lines.append(f"# Period: {data_info['start_time'].strftime('%Y-%m-%d')} to {data_info['end_time'].strftime('%Y-%m-%d')}")
    lines.append(f"# R² = {utide_results['r_squared']:.4f}, RMS error = {utide_results['rms_error']:.4f} m")
    lines.append(f"# Constituents analyzed: {utide_results['n_constituents']}")
    lines.append(f"#")
    lines.append(f"# Reference Level Conversion:")
    lines.append(f"#   PNP unter NHN: {bsh_info.get('pnp_nhn', 'N/A')} m")
    lines.append(f"#   SKN unter NHN: {bsh_info.get('skn_nhn', 'N/A')} m")
    lines.append(f"#   SKN über PNP:  {skn_offset:.2f} m")
    lines.append(f"#   Mean (PNP): {mean_pnp:.4f} m")
    lines.append(f"#   Mean (LAT): {mean_lat:.4f} m")
    if 'mhw' in bsh_info and 'mnw' in bsh_info:
        lines.append(f"#   BSH MHW (PNP): {bsh_info['mhw']:.2f} m -> LAT: {bsh_info['mhw'] - skn_offset:.2f} m")
        lines.append(f"#   BSH MNW (PNP): {bsh_info['mnw']:.2f} m -> LAT: {bsh_info['mnw'] - skn_offset:.2f} m")
    lines.append(f"#")
    lines.append(f"# {station_name}")
    lines.append(f"# !latitude: {lat:.4f}")
    lines.append(f"# !longitude: {lon:.4f}")
    lines.append(f"# !units: meters")
    lines.append(f"# datum: LAT (Lowest Astronomical Tide / SKN)")
    lines.append(f"#")

    lines.append(f"{station_name}, Germany")
    lines.append(f"+00:00 :Europe/Berlin")
    lines.append(f"{mean_lat:.4f} meters")

    # Sort constituents by amplitude
    names = coef['name']
    amplitudes = coef['A']
    phases = coef['g']

    sorted_idx = np.argsort(amplitudes)[::-1]

    for idx in sorted_idx:
        name = names[idx].strip()
        amp = amplitudes[idx]
        phase = phases[idx] % 360

        if amp < 0.0001:  # Skip very small constituents
            continue

        lines.append(f"{name:15s} {amp:.4f}  {phase:.2f}")

    return '\n'.join(lines)


def main():
    print("=" * 70)
    print("Generate Harmonics with LAT Reference from Pegelonline Data")
    print("=" * 70)

    # Create output directory
    OUTPUT_DIR.mkdir(exist_ok=True)

    # Read station list from ODS
    print(f"\nReading station list from {ODS_FILE.name}...")
    df = pd.read_excel(ODS_FILE, engine='odf')

    # Get first 21 stations
    stations = df[['Station', 'Datum Wert', 'Latitude', 'Longitude', 'Datei']].head(21)
    print(f"Processing {len(stations)} stations")

    # Get all ZIP files
    zip_files = list(WATER_LEVELS_DIR.glob("pegelonline-*.zip"))
    zip_files = [f for f in zip_files if 'Zone.Identifier' not in str(f)]
    print(f"Found {len(zip_files)} water level files")

    # Build ZIP lookup by key
    zip_lookup = {}
    for zf in zip_files:
        parts = zf.stem.split('-')
        if len(parts) >= 2:
            zip_lookup[parts[1].lower()] = zf

    print("\n" + "=" * 70)
    print("Processing Stations")
    print("=" * 70)

    results = []

    for i, row in stations.iterrows():
        station_name = row['Station'].replace(', Germany', '')
        bsh_file = row['Datei']
        lat = row['Latitude']
        lon = row['Longitude']

        print(f"\n[{i+1}/21] {station_name}")

        # Find BSH file
        if pd.isna(bsh_file):
            print(f"  ⚠ No BSH file specified, skipping")
            continue

        bsh_path = BSH_DIR / bsh_file
        if not bsh_path.exists():
            print(f"  ⚠ BSH file not found: {bsh_file}")
            continue

        # Extract BSH info including SKN offset
        bsh_info = extract_station_info_from_bsh(bsh_path)
        skn_offset = bsh_info.get('skn_pnp')

        if skn_offset is None:
            print(f"  ⚠ No SKN offset found in BSH file")
            continue

        print(f"  BSH: SKN über PNP = {skn_offset:.2f} m")

        # Find matching ZIP file
        zip_key = ZIP_MAPPING.get(station_name)
        if zip_key and zip_key in zip_lookup:
            zip_file = zip_lookup[zip_key]
        else:
            zip_file = find_zip_file_for_station(station_name, zip_files)

        if zip_file is None:
            print(f"  ⚠ No water level data found")
            continue

        print(f"  ZIP: {zip_file.name}")

        # Load water level data
        data = parse_pegelonline_zip(zip_file, sample_interval_minutes=60, use_last_n_years=5)
        if data is None:
            print(f"  ⚠ Failed to load water level data")
            continue

        years = (data['end_time'] - data['start_time']).days / 365.25
        print(f"  Data: {data['n_obs']} obs, {years:.1f} years")

        # Run UTide analysis
        utide_results = run_utide_analysis(data['datetimes_utc'], data['levels'], lat)
        if utide_results is None:
            print(f"  ⚠ UTide analysis failed")
            continue

        print(f"  UTide: R²={utide_results['r_squared']:.3f}, {utide_results['n_constituents']} constituents")
        print(f"  Mean: {utide_results['mean_pnp']:.3f} m (PNP) -> {utide_results['mean_pnp'] - skn_offset:.3f} m (LAT)")

        # Format output
        output = format_harmonics_output(
            station_name, lat, lon, bsh_info, utide_results, data, skn_offset
        )

        # Save to file
        safe_name = station_name.replace(' ', '_').replace('/', '_').replace('(', '').replace(')', '')
        output_file = OUTPUT_DIR / f"{safe_name}_harmonics_lat.txt"
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(output)

        print(f"  ✓ Saved: {output_file.name}")

        results.append({
            'station': station_name,
            'skn_offset': skn_offset,
            'mean_pnp': utide_results['mean_pnp'],
            'mean_lat': utide_results['mean_pnp'] - skn_offset,
            'r_squared': utide_results['r_squared'],
            'n_constituents': utide_results['n_constituents'],
        })

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Processed: {len(results)} stations")
    print(f"Output: {OUTPUT_DIR}")

    if results:
        print(f"\n{'Station':<40} {'SKN offset':>10} {'Mean LAT':>10} {'R²':>8}")
        print("-" * 70)
        for r in results:
            print(f"{r['station']:<40} {r['skn_offset']:>10.2f} {r['mean_lat']:>10.3f} {r['r_squared']:>8.3f}")


if __name__ == "__main__":
    main()
