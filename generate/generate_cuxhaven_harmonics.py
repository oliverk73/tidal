#!/usr/bin/env python3
"""
Generate Harmonic Constants for Cuxhaven-Steubenhöft from Pegelonline water level data.
Based on generate_germany_harmonics_175.py, tailored for a single station.

Uses UTide for harmonic analysis, outputs 175 tidal constituents in XTide format.

Station info from BSH DE__506P2026.txt:
  Position: 53°52'04''N  8°43'03''E WGS84
  PNP u. NHN: -5.03 m
  SKN u. NHN: -2.01 m  (SKN ü. PNP: 3.02 m)
  MHW (PNP): 6.56 m, MNW (PNP): 3.66 m
  Timezone: UTC+1h00min (MEZ)
  Def.-Jahr: 2023 (19 years analysis)
"""
import sys
sys.path.insert(0, '/home/oliver/py')

import numpy as np
from datetime import datetime, timedelta, timezone
import json
import zipfile
from pathlib import Path
import utide

# Station metadata from BSH DE__506P2026.txt
STATION_NAME = "Cuxhaven-Steubenhöft (Elbe)"
STATION_FULL = "Cuxhaven-Steubenhöft (Elbe), Germany"
LAT = 53.8678   # 53°52'04''N
LON = 8.7175    # 8°43'03''E
WATER_BODY = "Elbe"
PNP_NHN = -5.03  # PNP relative to NHN
SKN_NHN = -2.01  # SKN/LAT relative to NHN
SKN_PNP = 3.02   # SKN above PNP
MHW_PNP = 6.56   # Mean High Water (PNP)
MNW_PNP = 3.66   # Mean Low Water (PNP)

# Import the 175 constituents list from the existing module
from generate_germany_harmonics_175 import (
    CONSTITUENTS_175,
    XTIDE_BY_SPEED,
    UTIDE_TO_XTIDE_NAME,
    find_xtide_match,
    get_species,
    read_header_from_template,
)


def parse_json_water_levels(zip_path, sample_interval_minutes=60, use_last_n_years=10):
    """
    Parse water level data from Pegelonline ZIP file using streaming JSON parser.
    Memory-efficient: streams JSON array items instead of loading entire file.
    Returns UTC datetime array and levels in meters.
    """
    import ijson

    # Determine cutoff date
    if use_last_n_years is not None:
        cutoff_date = datetime.utcnow() - timedelta(days=use_last_n_years * 365.25)
        print(f"  Cutoff date: {cutoff_date.strftime('%Y-%m-%d')} (last {use_last_n_years} years)")
    else:
        cutoff_date = None

    datetimes_utc = []
    levels = []
    total_records = 0
    skipped_before_cutoff = 0
    skipped_null = 0
    skipped_sample = 0
    record_index = 0

    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            json_name = None
            for name in zf.namelist():
                if name.endswith('.json') and not name.endswith(':Zone.Identifier'):
                    json_name = name
                    break
            if json_name is None:
                print("  No JSON file found in ZIP")
                return None

            print(f"  Streaming JSON: {json_name}")
            with zf.open(json_name) as f:
                for entry in ijson.items(f, 'item'):
                    total_records += 1

                    # Only process every Nth record (sampling)
                    if total_records % sample_interval_minutes != 0:
                        skipped_sample += 1
                        continue

                    value = entry.get('value')
                    if value is None:
                        skipped_null += 1
                        continue

                    ts_str = entry['timestamp']
                    ts_base = ts_str[:19]

                    # Quick date check before full parsing
                    if cutoff_date is not None:
                        year = int(ts_base[:4])
                        if year < cutoff_date.year - 1:
                            skipped_before_cutoff += 1
                            continue

                    try:
                        dt_local = datetime.strptime(ts_base, "%Y-%m-%dT%H:%M:%S")

                        if '+' in ts_str[19:]:
                            offset_str = ts_str[19:].lstrip('+')
                            offset_parts = offset_str.split(':')
                            offset_hours = int(offset_parts[0])
                            offset_minutes = int(offset_parts[1]) if len(offset_parts) > 1 else 0
                            utc_offset = timedelta(hours=offset_hours, minutes=offset_minutes)
                        elif '-' in ts_str[19:]:
                            offset_str = ts_str[19:].lstrip('-')
                            offset_parts = offset_str.split(':')
                            offset_hours = int(offset_parts[0])
                            offset_minutes = int(offset_parts[1]) if len(offset_parts) > 1 else 0
                            utc_offset = -timedelta(hours=offset_hours, minutes=offset_minutes)
                        else:
                            utc_offset = timedelta(hours=1)

                        dt_utc = dt_local - utc_offset

                        if cutoff_date is not None and dt_utc < cutoff_date:
                            skipped_before_cutoff += 1
                            continue

                        level = float(value) / 100.0
                        datetimes_utc.append(dt_utc)
                        levels.append(level)
                    except:
                        skipped_null += 1
                        continue

                    if total_records % 1000000 == 0:
                        print(f"    ... {total_records/1e6:.1f}M records scanned, {len(datetimes_utc)} kept")

    except Exception as e:
        print(f"Error reading ZIP: {e}")
        import traceback
        traceback.print_exc()
        return None

    print(f"  Total records scanned: {total_records}")
    print(f"  Kept: {len(datetimes_utc)}, skipped: cutoff={skipped_before_cutoff}, null={skipped_null}, sampling={skipped_sample}")

    if len(datetimes_utc) < 2000:
        print("  Too few observations")
        return None

    return {
        'datetimes_utc': np.array(datetimes_utc),
        'levels': np.array(levels),
        'start_time': datetimes_utc[0],
        'end_time': datetimes_utc[-1],
        'n_obs': len(datetimes_utc)
    }


def harmonic_analysis_utide(datetimes_utc, levels, lat):
    """
    Perform harmonic analysis using UTide.
    Returns results with Greenwich phases mapped to 175 XTide constituents.
    """
    from utide._ut_constants import ut_constants
    const_table = ut_constants['const']
    utide_all_names = [n.strip() for n in const_table.name]

    print(f"  Running UTide solve (lat={lat}, n_obs={len(datetimes_utc)}, constit=auto)...")
    try:
        coef = utide.solve(
            datetimes_utc,
            levels,
            lat=lat,
            nodal=True,
            trend=False,
            method='ols',
            conf_int='none',
            verbose=False,
            constit='auto',
        )
    except Exception as e:
        print(f"  UTide error: {e}")
        return None

    print(f"  UTide found {len(coef['name'])} constituents")

    # Map UTide results to XTide 175-constituent format
    utide_results = {}
    utide_names = utide_all_names

    for i, uname in enumerate(coef['name']):
        uname = uname.strip()
        amplitude = coef['A'][i]
        greenwich_phase = coef['g'][i]
        snr = coef['SNR'][i] if 'SNR' in coef else 999

        if uname in utide_names:
            idx = utide_names.index(uname)
            utide_speed = const_table.freq[idx] * 360.0
        else:
            continue

        xt_name, xt_speed = find_xtide_match(uname, utide_speed)
        if xt_name is None:
            continue

        # Store Greenwich phase directly (matching DWF convention with +00:00 meridian)
        utide_results[xt_name] = {
            'amplitude': amplitude,
            'phase': greenwich_phase % 360,
            'speed': xt_speed,
            'snr': snr
        }

    # Build full 175-constituent result
    results = {'mean': coef['mean'], 'constituents': []}
    analyzed = 0

    for name, speed in CONSTITUENTS_175:
        if name in utide_results:
            r = utide_results[name]
            results['constituents'].append({
                'name': name,
                'amplitude': r['amplitude'],
                'phase': r['phase'],
                'speed': speed,
                'snr': r['snr']
            })
            analyzed += 1
        else:
            results['constituents'].append({
                'name': name,
                'amplitude': 0.0,
                'phase': 0.0,
                'speed': speed,
                'not_analyzed': True
            })

    # Goodness of fit
    try:
        reconstruction = utide.reconstruct(datetimes_utc, coef, verbose=False)
        h_predicted = reconstruction['h']
        residuals = levels - h_predicted
        ss_res = np.sum(residuals**2)
        ss_tot = np.sum((levels - np.mean(levels))**2)
        results['r_squared'] = 1 - ss_res / ss_tot if ss_tot > 0 else 0
        results['rms_error'] = np.sqrt(np.mean(residuals**2))
    except:
        results['r_squared'] = 0
        results['rms_error'] = 0

    results['n_analyzed'] = analyzed
    print(f"  Mapped to XTide: {analyzed}/175 constituents")
    print(f"  R² = {results['r_squared']:.4f}, RMS error = {results['rms_error']:.4f} m")

    return results


def format_station_block(results, data):
    """Format station block in XTide harmonics format."""
    lines = []

    lines.append(f"# Harmonic constants derived from Pegelonline water level data")
    lines.append(f"# using UTide (v{utide.__version__}) with {data['n_obs']} observations")
    lines.append(f"# from {data['start_time'].strftime('%Y-%m-%d')} to {data['end_time'].strftime('%Y-%m-%d')}")
    lines.append(f"# R^2 = {results['r_squared']:.4f}, RMS error = {results['rms_error']:.4f} m")
    lines.append(f"# Constituents analyzed: {results['n_analyzed']}")
    lines.append(f"#")
    lines.append(f"# {STATION_NAME}")
    lines.append(f"# Water body: {WATER_BODY}")
    lines.append(f"# BSH reference: DE__506P2026")
    lines.append(f"# BSH Position: 53\xb052'04''N  8\xb043'03''E WGS84")
    lines.append(f"# BSH PNP u. NHN: {PNP_NHN:.2f} m")
    lines.append(f"# BSH SKN u. NHN: {SKN_NHN:.2f} m (SKN ueb. PNP: {SKN_PNP:.2f} m)")
    lines.append(f"# BSH MHW (PNP): {MHW_PNP:.2f} m, MNW (PNP): {MNW_PNP:.2f} m")
    lines.append(f"# BEGIN HOT COMMENTS")
    lines.append(f"# country: Germany")
    lines.append(f"# source: Derived from Pegelonline water level data ({data['start_time'].year}-{data['end_time'].year}) with UTide harmonic analysis")
    lines.append(f"# restriction: Non-commercial use only")
    lines.append(f"# station_id_context: WSV/Pegelonline")
    lines.append(f"# station_id: 5990020")
    lines.append(f"# date_imported: {datetime.now().strftime('%Y%m%d')}")
    lines.append(f"# datum: Mean Sea Level")
    lines.append(f"# confidence: 9")
    lines.append(f"# !units: meters")
    lines.append(f"# !longitude: {LON:.4f}")
    lines.append(f"# !latitude: {LAT:.4f}")

    lines.append(f"{STATION_FULL}")
    lines.append(f"+00:00 :Europe/Berlin")
    lines.append(f"{results['mean']:.4f} meters")

    for c in results['constituents']:
        if c.get('not_analyzed') or c['amplitude'] < 0.00005:
            lines.append(f"x 0 0")
        else:
            lines.append(f"{c['name']:15s} {c['amplitude']:.4f}  {c['phase']:.2f}")

    return '\n'.join(lines)


def main():
    zip_path = Path("/home/oliver/water_levels/Germany/pegelonline-cuxhavensteubenhft-W-20000101-20260123.zip")
    template_path = Path("/home/oliver/harmonics/classic/harmonics-dwf-20070318_no_us_no_dupes.txt")
    output_path = Path("/home/oliver/harmonics/utide/harmonics_cuxhaven_steubenhöft_2026-01-25.txt")

    print("=" * 70)
    print("Generate Harmonics for Cuxhaven-Steubenhöft (Elbe)")
    print("=" * 70)
    print(f"  Station: {STATION_FULL}")
    print(f"  Position: {LAT:.4f}°N, {LON:.4f}°E")
    print(f"  Input: {zip_path.name}")
    print(f"  Output: {output_path.name}")
    print()

    # Read header
    print("Reading header from template...")
    header = read_header_from_template(template_path)

    # Parse water levels - use ALL data (26 years)
    print(f"\nParsing water level data from {zip_path.name}...")
    # 60-min sampling for 10 years = ~87k observations, fits in RAM
    # Resolves constituents up to ~M10 (period ~2.5h); M12 (period ~2.07h) is marginal
    data = parse_json_water_levels(zip_path, sample_interval_minutes=60, use_last_n_years=10)
    if data is None:
        print("FAILED: Could not parse water level data")
        return

    print(f"  Time span: {data['start_time'].strftime('%Y-%m-%d %H:%M')} to {data['end_time'].strftime('%Y-%m-%d %H:%M')} UTC")
    print(f"  Total observations: {data['n_obs']}")

    # Run harmonic analysis
    print(f"\nRunning harmonic analysis...")
    results = harmonic_analysis_utide(data['datetimes_utc'], data['levels'], LAT)
    if results is None:
        print("FAILED: Harmonic analysis error")
        return

    # Print key constituents
    print(f"\n  Mean level (PNP): {results['mean']:.4f} m")
    print(f"  Key constituents:")
    for c in results['constituents']:
        if c['name'] in ('M2', 'S2', 'N2', 'K1', 'O1', 'M4', 'MS4', 'K2', 'P1', 'M6'):
            if not c.get('not_analyzed'):
                print(f"    {c['name']:6s}  amp={c['amplitude']:.4f} m  phase={c['phase']:.2f}°")

    # Format output
    print(f"\nFormatting output...")
    station_block = format_station_block(results, data)

    # Write output file
    print(f"Writing to {output_path}...")
    with open(output_path, 'w', encoding='latin-1') as f:
        f.write(header)
        f.write('\n')
        f.write(station_block)
        f.write('\n')

    print(f"\nDone! Created {output_path}")
    print(f"Constituents: {results['n_analyzed']} analyzed / 175 total")
    print(f"R² = {results['r_squared']:.4f}, RMS = {results['rms_error']:.4f} m")


if __name__ == "__main__":
    main()
