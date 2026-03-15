#!/usr/bin/env python3
"""
Correct Z0 (mean level) in the filtered harmonics file based on BSH comparison.

For each station matched to BSH data:
- Compare XTide predictions (from filtered TCD) with BSH predictions for January 2026
- Calculate the mean height bias (XTide - BSH) across all HW+NW events
- Subtract this bias from Z0 in the harmonics text file
- Rebuild the TCD

This corrects the systematic NW bias without affecting timing.
"""

import subprocess
import re
import os
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
import shutil

FILTERED_TXT = Path("/home/oliver/harmonics_working/harmonics_utide_germany_2026-03-11_filtered.txt")
OUTPUT_TXT = Path("/home/oliver/harmonics_working/harmonics_utide_germany_z0corrected.txt")
OUTPUT_TCD = OUTPUT_TXT.with_suffix(".tcd")
BSH_DIR = Path("/home/oliver/harmonics_working_help/BSH")

os.environ['HFILE_PATH'] = str(FILTERED_TXT.with_suffix(".tcd"))


def parse_bsh_file(bsh_path):
    """Parse BSH VB2 file for January 2026."""
    station_name = None
    predictions = []
    with open(bsh_path, 'r', encoding='latin-1') as f:
        for line in f:
            line = line.strip()
            if line.startswith('A04#'):
                parts = line.split(':#')
                if len(parts) >= 2:
                    station_name = parts[1].rstrip('#').strip()
            if not line.startswith('VB2#'):
                continue
            parts = line.split('#')
            hw_nw = parts[3].strip()
            date_str = re.sub(r'\s+', '', parts[5].strip())
            time_str = parts[6].strip()
            height_str = parts[7].strip()
            day, month, year = date_str.split('.')
            day, month, year = int(day), int(month), int(year)
            if month != 1:
                continue
            hour, minute = map(int, time_str.split(':'))
            height = float(height_str)
            dt_mez = datetime(year, month, day, hour, minute)
            dt_utc = dt_mez - timedelta(hours=1)
            predictions.append({
                'datetime_utc': dt_utc,
                'height_pnp': height,
                'type': 'HW' if hw_nw == 'H' else 'NW',
            })
    return station_name, predictions


def get_xtide_predictions(station_name):
    """Get XTide predictions for January 2026."""
    result = subprocess.run(
        ['tide', '-l', station_name,
         '-b', '2026-01-01 00:00',
         '-e', '2026-02-01 00:00',
         '-m', 'p', '-em', 'pSsMm'],
        capture_output=True, text=True, env=os.environ, timeout=30)
    if result.returncode != 0:
        return None
    predictions = []
    for line in result.stdout.strip().split('\n'):
        m = re.match(
            r'(\d{4}-\d{2}-\d{2})\s+(\d{1,2}:\d{2}\s+[AP]M)\s+(CES?T)\s+([\d.]+)\s+meters\s+(High|Low)\s+Tide',
            line.strip())
        if m:
            dt_local = datetime.strptime(f"{m.group(1)} {m.group(2)}", "%Y-%m-%d %I:%M %p")
            utc_offset = 2 if m.group(3) == 'CEST' else 1
            predictions.append({
                'datetime_utc': dt_local - timedelta(hours=utc_offset),
                'height_pnp': float(m.group(4)),
                'type': 'HW' if m.group(5) == 'High' else 'NW',
            })
    return predictions


def normalize(s):
    s = s.lower()
    for old, new in [('ä', 'ae'), ('ö', 'oe'), ('ü', 'ue'), ('ß', 'ss'),
                     ('\xe4', 'ae'), ('\xf6', 'oe'), ('\xfc', 'ue')]:
        s = s.replace(old, new)
    return re.sub(r'[^a-z0-9]', '', s)


def find_xtide_match(bsh_name, xtide_stations):
    norm_bsh = normalize(bsh_name)
    best_match, best_score = None, 0
    for xt_name in xtide_stations:
        norm_xt = normalize(xt_name.replace(', Germany', ''))
        if norm_bsh == norm_xt:
            return xt_name
        if norm_bsh in norm_xt or norm_xt in norm_bsh:
            score = min(len(norm_bsh), len(norm_xt))
            if score > best_score:
                best_score, best_match = score, xt_name
        bsh_parts = set(re.split(r'[,\s]+', norm_bsh))
        xt_parts = set(re.split(r'[,\s]+', norm_xt))
        common = bsh_parts & xt_parts
        if len(common) >= 2 and len(common) / max(len(bsh_parts), len(xt_parts)) > 0.5:
            score = len(common) * 10
            if score > best_score:
                best_score, best_match = score, xt_name
    return best_match if best_score >= 8 else None


def match_events(bsh_preds, xt_preds, max_hours=3):
    """Match BSH events with nearest XTide events of same type."""
    matches = []
    used = set()
    for bsh in bsh_preds:
        best, best_dt = None, timedelta(hours=max_hours)
        for j, xt in enumerate(xt_preds):
            if j in used or xt['type'] != bsh['type']:
                continue
            dt = abs(xt['datetime_utc'] - bsh['datetime_utc'])
            if dt < best_dt:
                best_dt, best = dt, (j, xt)
        if best is not None:
            j, xt = best
            used.add(j)
            matches.append({
                'height_diff': xt['height_pnp'] - bsh['height_pnp'],
                'type': bsh['type'],
            })
    return matches


def calculate_z0_corrections(xtide_stations):
    """Calculate Z0 correction for each station based on BSH comparison."""
    corrections = {}  # xtide_name -> correction_m

    bsh_files = sorted(BSH_DIR.glob("DE__*2026.txt"))
    bsh_files = [f for f in bsh_files if ':' not in str(f)]

    for bsh_file in bsh_files:
        bsh_name, bsh_preds = parse_bsh_file(bsh_file)
        if not bsh_name or not bsh_preds:
            continue

        xt_match = find_xtide_match(bsh_name, xtide_stations)
        if not xt_match:
            continue

        xt_preds = get_xtide_predictions(xt_match)
        if not xt_preds:
            continue

        matches = match_events(bsh_preds, xt_preds)
        if not matches:
            continue

        # Calculate mean height bias across ALL events (HW + NW)
        all_dh = [m['height_diff'] for m in matches]
        hw_dh = [m['height_diff'] for m in matches if m['type'] == 'HW']
        nw_dh = [m['height_diff'] for m in matches if m['type'] == 'NW']

        mean_bias = np.mean(all_dh)
        hw_bias = np.mean(hw_dh) if hw_dh else 0
        nw_bias = np.mean(nw_dh) if nw_dh else 0

        # Strip ", Germany" for matching with harmonics file
        station_key = xt_match.replace(', Germany', '')
        corrections[station_key] = {
            'bias': mean_bias,
            'hw_bias': hw_bias,
            'nw_bias': nw_bias,
            'n_events': len(matches),
        }

        print(f"  {station_key:<45s} bias={mean_bias:+.3f}m  (HW={hw_bias:+.3f}, NW={nw_bias:+.3f}, n={len(matches)})")

    return corrections


def apply_z0_corrections(corrections):
    """Apply Z0 corrections to the harmonics text file."""
    with open(FILTERED_TXT, 'r', encoding='latin-1') as f:
        content = f.read()

    lines = content.split('\n')
    corrected_count = 0
    uncorrected_stations = []

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Check if this is a station name line
        if stripped.endswith(', Germany') and not stripped.startswith('#'):
            station_key = stripped.replace(', Germany', '')

            # Next two lines should be timezone and mean level
            if i + 2 < len(lines):
                mean_line = lines[i + 2].strip()
                m = re.match(r'^([\d.]+)\s+meters$', mean_line)
                if m:
                    old_mean = float(m.group(1))

                    if station_key in corrections:
                        corr = corrections[station_key]
                        new_mean = old_mean - corr['bias']
                        lines[i + 2] = f"{new_mean:.4f} meters"
                        corrected_count += 1
                    else:
                        uncorrected_stations.append(station_key)
        i += 1

    with open(OUTPUT_TXT, 'w', encoding='latin-1') as f:
        f.write('\n'.join(lines))

    print(f"\nCorrected: {corrected_count} stations")
    if uncorrected_stations:
        print(f"Uncorrected (no BSH match): {len(uncorrected_stations)}")
        for s in uncorrected_stations:
            print(f"  - {s}")

    return corrected_count


def build_tcd():
    """Build TCD from corrected text file."""
    result = subprocess.run(
        ['build_tide_db', str(OUTPUT_TCD), str(OUTPUT_TXT)],
        capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        print(f"ERROR building TCD: {result.stderr}")
        return False
    print(f"\nTCD built: {OUTPUT_TCD} ({OUTPUT_TCD.stat().st_size / 1024:.0f} KB)")
    return True


def main():
    print("=" * 70)
    print("Z0 Correction based on BSH Comparison — January 2026")
    print("=" * 70)

    # Get XTide station list
    txt_file = FILTERED_TXT
    xtide_stations = []
    with open(txt_file, 'r', encoding='latin-1') as f:
        for line in f:
            stripped = line.strip()
            if stripped.endswith(', Germany') and not stripped.startswith('#'):
                xtide_stations.append(stripped)
    print(f"XTide stations: {len(xtide_stations)}")

    # Calculate corrections
    print(f"\nCalculating Z0 corrections from BSH data...")
    corrections = calculate_z0_corrections(xtide_stations)
    print(f"\nCorrections calculated for {len(corrections)} stations")

    # Summary stats
    biases = [c['bias'] for c in corrections.values()]
    print(f"  Mean bias: {np.mean(biases):+.3f}m")
    print(f"  Min bias:  {np.min(biases):+.3f}m")
    print(f"  Max bias:  {np.max(biases):+.3f}m")

    # Apply corrections
    print(f"\nApplying corrections to {FILTERED_TXT.name}...")
    n = apply_z0_corrections(corrections)

    # Build TCD
    print(f"\nBuilding TCD...")
    build_tcd()

    print(f"\nOutput: {OUTPUT_TXT}")
    print(f"        {OUTPUT_TCD}")


if __name__ == "__main__":
    main()
