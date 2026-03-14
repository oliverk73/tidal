#!/usr/bin/env python3
"""
Optimize shallow-water harmonic constituents against BSH reference predictions.

For each station with BSH data:
1. Load UTide checkpoint (original harmonic constants)
2. Parse BSH HW/NW predictions for 2026
3. Reconstruct tide at 6-min resolution using harmonic constants
4. Optimize shallow-water constituent amplitudes/phases + mean level
   to minimize HW/NW differences against BSH
5. Save optimized checkpoint

The optimization adjusts:
- Mean level
- Shallow-water constituents: M4, M6, MS4, MN4, M8, 2MS6, 2MN6, S4, 3MS4, 2SM6, MSK6
- Small phase corrections on M2, S2, N2 (±5°)
"""
import sys
sys.path.insert(0, '/home/oliver/py')

import numpy as np
import re
import pickle
import time
from datetime import datetime, timedelta
from pathlib import Path
from scipy.optimize import minimize
from scipy.signal import argrelextrema

from generate_germany_harmonics_175 import (
    CONSTITUENTS_175,
)


def read_header_from_template(template_path):
    """Read header from template file including all comments until first station data."""
    with open(template_path, 'r', encoding='latin-1') as f:
        lines = f.readlines()

    header_lines = []
    end_count = 0

    for line in lines:
        stripped = line.strip()

        if stripped == '*END*':
            end_count += 1
            header_lines.append(line.rstrip())
            continue

        # After the last *END* (node factors), include remaining comments
        # but stop at the first non-comment, non-empty line (= first station)
        if end_count >= 2:
            if stripped.startswith('#') or stripped == '':
                header_lines.append(line.rstrip())
            else:
                break
        else:
            header_lines.append(line.rstrip())

    return '\n'.join(header_lines)

# ── Paths ─────────────────────────────────────────────────────────────

CHECKPOINT_DIR = Path("/home/oliver/harmonics_working/checkpoints")
OPTIMIZED_DIR = Path("/home/oliver/harmonics_working/checkpoints_optimized")
BSH_DIR = Path("/home/oliver/harmonics_working_help/BSH")
TEMPLATE_PATH = Path("/home/oliver/harmonics_working/harmonics-dwf-20070318_no_us_no_dupes.txt")
OUTPUT_PATH = Path("/home/oliver/harmonics_working/harmonics_utide_germany_optimized.txt")

# Constituents to optimize — only the most important shallow-water ones
SHALLOW_WATER = {'M4', 'M6', 'MS4', 'MN4', 'M8', '2MS6', '2MN6'}

# Major constituents: allow small phase adjustment only
MAJOR_PHASE_ADJ = {'M2', 'S2'}
MAX_PHASE_ADJ = 3.0  # degrees

# Time weight in cost function (minutes² → comparable to cm²)
# 1 minute timing error ~ 1 cm height error
W_TIME = 0.5  # weight for timing errors relative to height errors


# ── BSH Parser ────────────────────────────────────────────────────────

def parse_bsh_file(bsh_path):
    """Parse BSH VB2 file. Returns (station_name, list of events)."""
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
            hour, minute = map(int, time_str.split(':'))
            height = float(height_str)

            dt_mez = datetime(year, month, day, hour, minute)
            dt_utc = dt_mez - timedelta(hours=1)

            predictions.append({
                'datetime_utc': dt_utc,
                'datetime_mez': dt_mez,
                'height_pnp': height,
                'type': 'HW' if hw_nw == 'H' else 'NW',
            })

    return station_name, predictions


# ── Station Matching ──────────────────────────────────────────────────

def normalize(s):
    s = s.lower()
    for old, new in [('ä','ae'),('ö','oe'),('ü','ue'),('ß','ss')]:
        s = s.replace(old, new)
    return re.sub(r'[^a-z0-9]', '', s)


def match_checkpoint_to_bsh(checkpoint_name, bsh_stations):
    """Match a checkpoint station name to a BSH station name."""
    norm_ckpt = normalize(checkpoint_name)

    best_match = None
    best_score = 0

    for bsh_name in bsh_stations:
        norm_bsh = normalize(bsh_name)

        if norm_ckpt == norm_bsh:
            return bsh_name

        if norm_ckpt in norm_bsh or norm_bsh in norm_ckpt:
            score = min(len(norm_ckpt), len(norm_bsh))
            if score > best_score:
                best_score = score
                best_match = bsh_name

        ckpt_parts = set(re.split(r'[,\s]+', norm_ckpt))
        bsh_parts = set(re.split(r'[,\s]+', norm_bsh))
        common = ckpt_parts & bsh_parts
        if len(common) >= 2 and len(common) / max(len(ckpt_parts), len(bsh_parts)) > 0.4:
            score = len(common) * 10
            if score > best_score:
                best_score = score
                best_match = bsh_name

    if best_score >= 6:
        return best_match
    return None


# ── Harmonic Reconstruction ──────────────────────────────────────────

def reconstruct_tide(times_hours, mean, constituents):
    """Reconstruct tide from harmonic constants.

    times_hours: array of hours since epoch
    mean: mean water level
    constituents: list of (speed_deg_per_hour, amplitude, phase_deg)
    """
    h = np.full(len(times_hours), mean)
    for speed, amp, phase in constituents:
        if amp < 1e-6:
            continue
        omega = np.radians(speed)
        phi = np.radians(phase)
        h += amp * np.cos(omega * times_hours - phi)
    return h


def find_hw_nw(times_dt, heights, min_dist=30):
    """Find high and low water events from a time series.

    min_dist: minimum distance between extrema in samples (30 × 6min = 3h)
    """
    order = min_dist
    hw_idx = argrelextrema(heights, np.greater, order=order)[0]
    nw_idx = argrelextrema(heights, np.less, order=order)[0]

    events = []
    for idx in hw_idx:
        events.append({
            'datetime_utc': times_dt[idx],
            'height': heights[idx],
            'type': 'HW',
        })
    for idx in nw_idx:
        events.append({
            'datetime_utc': times_dt[idx],
            'height': heights[idx],
            'type': 'NW',
        })

    events.sort(key=lambda e: e['datetime_utc'])
    return events


def match_events(bsh_events, pred_events, max_hours=3):
    """Match BSH events with predicted events of same type."""
    matches = []
    used = set()

    for bsh in bsh_events:
        best = None
        best_dt = timedelta(hours=max_hours)

        for j, pred in enumerate(pred_events):
            if j in used or pred['type'] != bsh['type']:
                continue
            dt = abs(pred['datetime_utc'] - bsh['datetime_utc'])
            if dt < best_dt:
                best_dt = dt
                best = (j, pred)

        if best is not None:
            j, pred = best
            used.add(j)
            time_diff = (pred['datetime_utc'] - bsh['datetime_utc']).total_seconds() / 60
            height_diff = pred['height'] - bsh['height_pnp']
            matches.append({
                'bsh': bsh,
                'pred': pred,
                'time_diff_min': time_diff,
                'height_diff_m': height_diff,
            })

    return matches


# ── Optimization ──────────────────────────────────────────────────────

def build_optimization(checkpoint, bsh_preds):
    """Build the optimization problem for one station.

    Uses windowed approach: only reconstruct ±3h around each BSH event,
    then find the local extremum. Much faster than full-year reconstruction.

    Returns: (cost_function, x0, bounds, param_info)
    """
    constituents = checkpoint['constituents']
    original_mean = checkpoint['mean']

    epoch = datetime(2026, 1, 1)
    window_half = 2.0  # hours around each BSH event

    # Precompute time windows around BSH events (3-min resolution within windows)
    dt_step = 3.0 / 60.0  # hours (3 minutes)
    n_window = int(2 * window_half / dt_step) + 1  # ~80 points per event

    # For each BSH event, compute time offsets in hours from epoch
    bsh_center_hours = []
    for bsh in bsh_preds:
        center = (bsh['datetime_utc'] - epoch).total_seconds() / 3600.0
        bsh_center_hours.append(center)

    # Build all window time points (concatenated)
    window_offsets = np.linspace(-window_half, window_half, n_window)  # relative hours
    all_times_hours = np.zeros(len(bsh_preds) * n_window)
    for i, center in enumerate(bsh_center_hours):
        all_times_hours[i*n_window:(i+1)*n_window] = center + window_offsets

    # Identify optimizable constituents
    opt_indices = []
    opt_types = []

    for i, c in enumerate(constituents):
        name = c['name']
        if name in SHALLOW_WATER and c['amplitude'] > 0:
            opt_indices.append(i)
            opt_types.append('shallow')
        elif name in MAJOR_PHASE_ADJ and c['amplitude'] > 0:
            opt_indices.append(i)
            opt_types.append('major_phase')

    # Build parameter vector
    x0 = [0.0]  # mean offset
    bounds = [(-0.5, 0.5)]

    for idx, otype in zip(opt_indices, opt_types):
        if otype == 'shallow':
            x0.extend([1.0, 0.0])
            bounds.extend([(0.0, 5.0), (-180.0, 180.0)])
        elif otype == 'major_phase':
            x0.append(0.0)
            bounds.append((-MAX_PHASE_ADJ, MAX_PHASE_ADJ))

    x0 = np.array(x0)

    # Precompute fixed constituent contributions at all window points
    opt_set = set(opt_indices)
    fixed_contrib = np.zeros(len(all_times_hours))
    for i, c in enumerate(constituents):
        if i not in opt_set and c['amplitude'] > 0:
            omega = np.radians(c['speed'])
            phi = np.radians(c['phase'])
            fixed_contrib += c['amplitude'] * np.cos(omega * all_times_hours - phi)

    # Precompute omega arrays for optimizable constituents
    opt_omegas = [np.radians(constituents[idx]['speed']) for idx in opt_indices]

    # Precompute BSH types and heights as arrays for vectorized cost
    bsh_heights = np.array([b['height_pnp'] for b in bsh_preds])
    bsh_is_hw = np.array([b['type'] == 'HW' for b in bsh_preds])
    n_events = len(bsh_preds)

    # Precompute phase arrays for optimizable constituents
    opt_orig_phases = np.array([constituents[idx]['phase'] for idx in opt_indices])
    opt_orig_amps = np.array([constituents[idx]['amplitude'] for idx in opt_indices])

    def cost_function(x):
        h = fixed_contrib + (original_mean + x[0])

        # Add optimizable constituents — vectorized
        xi = 1
        for k, (idx, otype) in enumerate(zip(opt_indices, opt_types)):
            omega = opt_omegas[k]
            if otype == 'shallow':
                amp = opt_orig_amps[k] * x[xi]
                phi = np.radians(opt_orig_phases[k] + x[xi + 1])
                xi += 2
            else:
                amp = opt_orig_amps[k]
                phi = np.radians(opt_orig_phases[k] + x[xi])
                xi += 1
            h = h + amp * np.cos(omega * all_times_hours - phi)

        # Reshape to (n_events, n_window) for vectorized extremum search
        h_2d = h.reshape(n_events, n_window)

        # Find extremum index per event
        hw_ext = np.argmax(h_2d, axis=1)
        nw_ext = np.argmin(h_2d, axis=1)
        ext_idx = np.where(bsh_is_hw, hw_ext, nw_ext)

        # Extract predicted heights and time offsets
        pred_heights = h_2d[np.arange(n_events), ext_idx]
        pred_dt_min = window_offsets[ext_idx] * 60.0

        # Vectorized cost
        dh_cm = (pred_heights - bsh_heights) * 100
        cost = np.mean(dh_cm**2 + W_TIME * pred_dt_min**2)

        return cost

    return cost_function, x0, bounds, None, opt_indices, opt_types


def apply_optimization(checkpoint, x_opt, opt_indices, opt_types):
    """Apply optimized parameters to checkpoint, return new checkpoint."""
    result = dict(checkpoint)
    result['constituents'] = [dict(c) for c in checkpoint['constituents']]

    result['mean'] = checkpoint['mean'] + x_opt[0]

    xi = 1
    for idx, otype in zip(opt_indices, opt_types):
        c = result['constituents'][idx]
        if otype == 'shallow':
            c['amplitude'] = checkpoint['constituents'][idx]['amplitude'] * x_opt[xi]
            c['phase'] = (checkpoint['constituents'][idx]['phase'] + x_opt[xi + 1]) % 360
            xi += 2
        elif otype == 'major_phase':
            c['phase'] = (checkpoint['constituents'][idx]['phase'] + x_opt[xi]) % 360
            xi += 1

    return result


# ── Output Formatting ─────────────────────────────────────────────────

def format_station_block(result):
    """Format a station block in XTide harmonics format."""
    si = result['station_info']
    station_name = si['name']
    lat = si['latitude']
    lon = si['longitude']
    water = si.get('water', 'Unknown')

    lines = []
    lines.append(f"# Harmonic constants derived from Pegelonline water level data")
    lines.append(f"# using UTide, optimized against BSH predictions")
    lines.append(f"# from {result['start_time'].strftime('%Y-%m-%d')} to {result['end_time'].strftime('%Y-%m-%d')}")
    lines.append(f"# R^2 = {result['r_squared']:.4f}, RMS error = {result['rms_error']:.4f} m")
    lines.append(f"# Constituents analyzed: {result['n_analyzed']}")
    if 'optimization' in result:
        opt = result['optimization']
        lines.append(f"# Optimized: mean_offset={opt['mean_offset']:+.4f}m, "
                      f"cost {opt['cost_before']:.1f} -> {opt['cost_after']:.1f}")
    lines.append(f"#")
    lines.append(f"# {station_name}")
    lines.append(f"# Water body: {water}")
    lines.append(f"# BEGIN HOT COMMENTS")
    lines.append(f"# country: Germany")
    lines.append(f"# source: Derived from Pegelonline data with UTide, optimized vs BSH")
    lines.append(f"# restriction: Non-commercial use only")
    lines.append(f"# station_id_context: WSV")
    lines.append(f"# date_imported: {datetime.now().strftime('%Y%m%d')}")
    lines.append(f"# datum: Mean Sea Level")
    lines.append(f"# confidence: 8")
    lines.append(f"# !units: meters")
    lines.append(f"# !longitude: {lon:.4f}")
    lines.append(f"# !latitude: {lat:.4f}")

    lines.append(f"{station_name}, Germany")
    lines.append(f"+00:00 :Europe/Berlin")
    lines.append(f"{result['mean']:.4f} meters")

    for c in result['constituents']:
        if c.get('not_analyzed') or c['amplitude'] < 0.00005:
            lines.append(f"x 0 0")
        else:
            lines.append(f"{c['name']:15s} {c['amplitude']:.4f}  {c['phase']:.2f}")

    return '\n'.join(lines)


# ── Main ──────────────────────────────────────────────────────────────

def main():
    OPTIMIZED_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 85)
    print("Optimize Harmonic Constants against BSH Predictions")
    print("=" * 85)

    # Load all BSH files
    bsh_files = sorted(BSH_DIR.glob("DE__*2026.txt"))
    bsh_files = [f for f in bsh_files if ':' not in str(f)]

    bsh_stations = {}
    for bsh_file in bsh_files:
        name, preds = parse_bsh_file(bsh_file)
        if name and preds:
            bsh_stations[name] = preds

    print(f"  BSH stations: {len(bsh_stations)}")

    # Load all checkpoints
    checkpoint_files = sorted(CHECKPOINT_DIR.glob("*.pkl"))
    checkpoints = {}
    for cp_file in checkpoint_files:
        try:
            with open(cp_file, 'rb') as f:
                data = pickle.load(f)
            if isinstance(data, dict) and 'constituents' in data:
                checkpoints[cp_file.stem] = data
        except:
            pass

    print(f"  Checkpoints: {len(checkpoints)}")

    # Match checkpoints to BSH stations
    matched = []
    for cp_key, cp_data in checkpoints.items():
        station_name = cp_data['station_info']['name']
        # Try matching with the station name from checkpoint
        bsh_match = match_checkpoint_to_bsh(station_name, bsh_stations.keys())
        if bsh_match:
            matched.append((cp_key, cp_data, bsh_match, bsh_stations[bsh_match]))

    print(f"  Matched: {len(matched)}")

    # Process each station
    print(f"\n{'#':>3s}  {'Station':<40s} {'N_BSH':>5s} {'Cost→':>8s} {'→Cost':>8s} "
          f"{'dMean':>7s} {'|dH|HW':>7s} {'|dH|NW':>7s} {'Time':>6s}")
    print(f"{'─'*3}  {'─'*40} {'─'*5} {'─'*8} {'─'*8} {'─'*7} {'─'*7} {'─'*7} {'─'*6}")

    all_results = []
    n_optimized = 0
    n_skipped = 0

    for cp_key, cp_data, bsh_name, bsh_preds in matched:
        t0 = time.time()
        station_name = cp_data['station_info']['name']

        # Check if already optimized
        opt_file = OPTIMIZED_DIR / f"{cp_key}.pkl"
        if opt_file.exists():
            try:
                with open(opt_file, 'rb') as f:
                    opt_result = pickle.load(f)
                all_results.append((cp_key, opt_result))
                n_skipped += 1
                opt = opt_result.get('optimization', {})
                print(f"  ►  {station_name:<40s} {'':>5s} {'':>8s} {'':>8s} "
                      f"{'':>7s} {'':>7s} {'':>7s} {'':>6s} ✓ cached")
                continue
            except:
                pass

        # Filter BSH events to HW/NW only
        hw_nw = [p for p in bsh_preds if p['type'] in ('HW', 'NW')]
        if len(hw_nw) < 20:
            print(f"{'':>3s}  {station_name:<40s} {len(hw_nw):>5d} {'':>8s} {'':>8s} "
                  f"{'':>7s} {'':>7s} {'':>7s} {'':>6s} ✗ too few BSH events")
            # Copy original
            all_results.append((cp_key, cp_data))
            continue

        # Build and run optimization
        try:
            cost_fn, x0, bounds, param_map, opt_indices, opt_types = \
                build_optimization(cp_data, hw_nw)

            cost_before = cost_fn(x0)

            result = minimize(
                cost_fn, x0, method='Powell',
                bounds=bounds,
                options={'maxiter': 3000, 'ftol': 0.01}
            )

            cost_after = cost_fn(result.x)

            # Apply optimization
            opt_result = apply_optimization(cp_data, result.x, opt_indices, opt_types)

            # Compute verification metrics using windowed approach
            epoch = datetime(2026, 1, 1)
            window_half = 2.0
            dt_step = 3.0 / 60.0
            n_win = int(2 * window_half / dt_step) + 1
            win_offsets = np.linspace(-window_half, window_half, n_win)

            hw_diffs = []
            nw_diffs = []
            for bsh_ev in hw_nw:
                center = (bsh_ev['datetime_utc'] - epoch).total_seconds() / 3600.0
                t_win = center + win_offsets
                h_win = np.full(n_win, opt_result['mean'])
                for c in opt_result['constituents']:
                    if c['amplitude'] < 1e-6:
                        continue
                    omega = np.radians(c['speed'])
                    phi = np.radians(c['phase'])
                    h_win += c['amplitude'] * np.cos(omega * t_win - phi)

                if bsh_ev['type'] == 'HW':
                    ext_h = np.max(h_win)
                    hw_diffs.append(abs(ext_h - bsh_ev['height_pnp']))
                else:
                    ext_h = np.min(h_win)
                    nw_diffs.append(abs(ext_h - bsh_ev['height_pnp']))

            hw_dh = np.mean(hw_diffs) if hw_diffs else 0
            nw_dh = np.mean(nw_diffs) if nw_diffs else 0

            opt_result['optimization'] = {
                'cost_before': cost_before,
                'cost_after': cost_after,
                'mean_offset': result.x[0],
                'n_bsh_events': len(hw_nw),
                'n_matched': len(hw_nw),
                'hw_dh_mean': hw_dh,
                'nw_dh_mean': nw_dh,
            }

            # Save optimized checkpoint
            with open(opt_file, 'wb') as f:
                pickle.dump(opt_result, f)

            duration = time.time() - t0
            n_optimized += 1

            print(f"{n_optimized:>3d}  {station_name:<40s} {len(hw_nw):>5d} "
                  f"{cost_before:>8.1f} {cost_after:>8.1f} "
                  f"{result.x[0]:>+6.3f}m {hw_dh:>6.2f}m {nw_dh:>6.2f}m "
                  f"{duration:>5.1f}s")

            all_results.append((cp_key, opt_result))

        except Exception as e:
            print(f"{'':>3s}  {station_name:<40s} {len(hw_nw):>5d} {'':>8s} {'':>8s} "
                  f"{'':>7s} {'':>7s} {'':>7s} {'':>6s} ✗ {e}")
            all_results.append((cp_key, cp_data))

    # Add unmatched stations (copy originals)
    matched_keys = {cp_key for cp_key, _, _, _ in matched}
    for cp_key, cp_data in checkpoints.items():
        if cp_key not in matched_keys:
            all_results.append((cp_key, cp_data))

    # Write output harmonics file
    print(f"\nAssembling output...")
    header = read_header_from_template(TEMPLATE_PATH)

    # Sort by station name
    all_results.sort(key=lambda x: x[1]['station_info']['name'])

    with open(OUTPUT_PATH, 'w', encoding='latin-1') as f:
        f.write(header)
        f.write('\n')
        for cp_key, result in all_results:
            block = format_station_block(result)
            f.write(block)
            f.write('\n')

    print(f"\n{'='*85}")
    print(f"  Optimized: {n_optimized}, Cached: {n_skipped}, "
          f"Total stations: {len(all_results)}")
    print(f"  Output: {OUTPUT_PATH}")
    print(f"  File size: {OUTPUT_PATH.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main()
