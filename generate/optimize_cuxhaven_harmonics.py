#!/usr/bin/env python3
"""
Optimize Cuxhaven-Steubenhöft harmonic constants against BSH reference data.

The standard UTide OLS fit produces excellent HW predictions but systematic
NW bias (+16 cm too high, -13 min too early) due to non-linear shallow-water
effects in the Elbe that the linear model cannot fully capture.

This script adjusts shallow-water constituent amplitudes/phases and mean level
to minimize combined HW/NW prediction errors against BSH 2026 predictions.

Key optimizations:
- Precomputes cosine/sine basis vectors for fast reconstruction (no utide.reconstruct in loop)
- Vectorized HW/NW finding and matching with numpy
"""
import sys
sys.path.insert(0, '/home/oliver/py')

import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
from copy import deepcopy
from scipy.optimize import minimize, differential_evolution
from scipy.signal import argrelextrema
import utide

from compare_cuxhaven_bsh import parse_bsh_predictions, find_hw_nw, match_predictions
from generate_cuxhaven_harmonics import (
    STATION_NAME, STATION_FULL, LAT, LON, WATER_BODY,
    PNP_NHN, SKN_NHN, SKN_PNP, MHW_PNP, MNW_PNP,
    parse_json_water_levels, harmonic_analysis_utide,
)
from generate_germany_harmonics_175 import (
    CONSTITUENTS_175, find_xtide_match, read_header_from_template,
)

# ── Configuration ─────────────────────────────────────────────────────

ZIP_PATH = Path("/home/oliver/water_levels/Germany/pegelonline-cuxhavensteubenhft-W-20000101-20260123.zip")
BSH_FILE = Path("/home/oliver/harmonics/help/BSH/DE__506P2026.txt")
TEMPLATE_PATH = Path("/home/oliver/harmonics/classic/harmonics-dwf-20070318_no_us_no_dupes.txt")
OUTPUT_PATH = Path("/home/oliver/harmonics/utide/harmonics_cuxhaven_steubenhöft_2026-01-25.txt")

# Shallow-water constituents to optimize (amplitude + phase each)
SHALLOW_WATER = ['M4', 'M6', 'MS4', 'MN4', 'M8', '2MS6', '2MN6', 'S4',
                 'MK4', '2MK6', '2SM6']

# Major constituents: allow small phase adjustments only
MAJOR_PHASE_ADJUST = ['M2', 'S2', 'N2']

# Time weight in cost function
W_TIME = 0.0001  # 10 min ≈ 0.10 m equivalent


# ── Fast reconstruction via precomputed basis ─────────────────────────

def precompute_basis(t_pred, coef):
    """
    Precompute cosine and sine basis vectors for each constituent.
    h(t) = mean + Σ_i A_i * [cos(g_i) * C_i(t) + sin(g_i) * S_i(t)]
    """
    n_const = len(coef['name'])
    n_time = len(t_pred)

    coef_zero = deepcopy(coef)
    coef_zero['A'][:] = 0.0
    h_mean_only = utide.reconstruct(t_pred, coef_zero, verbose=False)['h']

    print("   Precomputing basis vectors...")
    cos_basis = np.zeros((n_const, n_time))
    sin_basis = np.zeros((n_const, n_time))

    for i in range(n_const):
        coef_i = deepcopy(coef)
        coef_i['A'][:] = 0.0
        coef_i['A'][i] = 1.0
        coef_i['g'][i] = 0.0
        h_cos = utide.reconstruct(t_pred, coef_i, verbose=False)['h'] - coef['mean']
        cos_basis[i, :] = h_cos

        coef_i['g'][i] = 90.0
        h_sin = utide.reconstruct(t_pred, coef_i, verbose=False)['h'] - coef['mean']
        sin_basis[i, :] = h_sin

        if (i + 1) % 20 == 0:
            print(f"     ... {i+1}/{n_const} constituents")

    print(f"   Done: {n_const} basis vectors, {n_time} time points")
    return cos_basis, sin_basis, h_mean_only


def fast_reconstruct(mean_offset, A_mod, g_mod_rad, cos_basis, sin_basis, h_mean_only):
    """Fast reconstruction: h(t) = h_mean + offset + Σ A*[cos(g)*C + sin(g)*S]"""
    return h_mean_only + mean_offset + \
        (A_mod * np.cos(g_mod_rad)) @ cos_basis + \
        (A_mod * np.sin(g_mod_rad)) @ sin_basis


# ── Fast HW/NW finding and matching ──────────────────────────────────

def fast_find_hw_nw(h_pred, order=30):
    """Find HW/NW indices from time series. Returns (hw_indices, nw_indices)."""
    hw_idx = argrelextrema(h_pred, np.greater, order=order)[0]
    nw_idx = argrelextrema(h_pred, np.less, order=order)[0]
    return hw_idx, nw_idx


def prepare_bsh_arrays(bsh_preds, t_start_minutes):
    """Convert BSH predictions to numpy arrays for fast matching.
    Returns: hw_times_min, hw_heights, nw_times_min, nw_heights
    (times in minutes since t_start)
    """
    hw_times, hw_heights = [], []
    nw_times, nw_heights = [], []
    for p in bsh_preds:
        t_min = (p['datetime_utc'] - t_start_minutes).total_seconds() / 60.0
        if p['type'] == 'HW':
            hw_times.append(t_min)
            hw_heights.append(p['height_pnp'])
        else:
            nw_times.append(t_min)
            nw_heights.append(p['height_pnp'])
    return (np.array(hw_times), np.array(hw_heights),
            np.array(nw_times), np.array(nw_heights))


def fast_match_and_cost(h_pred, hw_idx, nw_idx, t_minutes,
                        bsh_hw_t, bsh_hw_h, bsh_nw_t, bsh_nw_h,
                        w_time, max_dt_min=180):
    """
    Fast vectorized matching and cost computation.
    t_minutes: time array in minutes since reference.
    Returns cost (float) and stats dict.
    """
    # UTide HW/NW times and heights
    ut_hw_t = t_minutes[hw_idx]
    ut_hw_h = h_pred[hw_idx]
    ut_nw_t = t_minutes[nw_idx]
    ut_nw_h = h_pred[nw_idx]

    cost = 0.0
    n_matched = 0
    hw_dh_sum = 0.0; hw_dt_sum = 0.0; n_hw = 0
    nw_dh_sum = 0.0; nw_dt_sum = 0.0; n_nw = 0
    hw_abs_dh_sum = 0.0; hw_abs_dt_sum = 0.0
    nw_abs_dh_sum = 0.0; nw_abs_dt_sum = 0.0

    # Match BSH HW with nearest UTide HW
    if len(ut_hw_t) > 0 and len(bsh_hw_t) > 0:
        # For each BSH HW, find nearest UTide HW
        # Broadcast: |bsh_hw_t[i] - ut_hw_t[j]|
        dt_matrix = np.abs(bsh_hw_t[:, None] - ut_hw_t[None, :])
        best_j = np.argmin(dt_matrix, axis=1)
        best_dt = dt_matrix[np.arange(len(bsh_hw_t)), best_j]

        valid = best_dt < max_dt_min
        for i in np.where(valid)[0]:
            j = best_j[i]
            dt_min = ut_hw_t[j] - bsh_hw_t[i]
            dh = ut_hw_h[j] - bsh_hw_h[i]
            cost += dh**2 + w_time * dt_min**2
            hw_dh_sum += dh; hw_dt_sum += dt_min
            hw_abs_dh_sum += abs(dh); hw_abs_dt_sum += abs(dt_min)
            n_hw += 1
            n_matched += 1

    # Match BSH NW with nearest UTide NW
    if len(ut_nw_t) > 0 and len(bsh_nw_t) > 0:
        dt_matrix = np.abs(bsh_nw_t[:, None] - ut_nw_t[None, :])
        best_j = np.argmin(dt_matrix, axis=1)
        best_dt = dt_matrix[np.arange(len(bsh_nw_t)), best_j]

        valid = best_dt < max_dt_min
        for i in np.where(valid)[0]:
            j = best_j[i]
            dt_min = ut_nw_t[j] - bsh_nw_t[i]
            dh = ut_nw_h[j] - bsh_nw_h[i]
            cost += dh**2 + w_time * dt_min**2
            nw_dh_sum += dh; nw_dt_sum += dt_min
            nw_abs_dh_sum += abs(dh); nw_abs_dt_sum += abs(dt_min)
            n_nw += 1
            n_matched += 1

    if n_matched == 0:
        return 1e10, {}

    cost /= n_matched

    stats = {
        'hw_dh': hw_dh_sum / n_hw if n_hw else 0,
        'hw_dt': hw_dt_sum / n_hw if n_hw else 0,
        'nw_dh': nw_dh_sum / n_nw if n_nw else 0,
        'nw_dt': nw_dt_sum / n_nw if n_nw else 0,
        'hw_abs_dh': hw_abs_dh_sum / n_hw if n_hw else 0,
        'hw_abs_dt': hw_abs_dt_sum / n_hw if n_hw else 0,
        'nw_abs_dh': nw_abs_dh_sum / n_nw if n_nw else 0,
        'nw_abs_dt': nw_abs_dt_sum / n_nw if n_nw else 0,
        'n_hw': n_hw, 'n_nw': n_nw, 'n_total': n_matched,
    }
    return cost, stats


# ── Parameter handling ────────────────────────────────────────────────

def build_param_info(coef):
    """Build parameter names and mapping to constituent indices."""
    coef_names = [n.strip() for n in coef['name']]
    param_names = ['mean_offset']
    coef_idx_map = {}

    for name in SHALLOW_WATER:
        if name in coef_names:
            coef_idx_map[name] = coef_names.index(name)
            param_names.append(f'{name}_amp_scale')
            param_names.append(f'{name}_phase_offset')

    for name in MAJOR_PHASE_ADJUST:
        if name in coef_names:
            coef_idx_map[name] = coef_names.index(name)
            param_names.append(f'{name}_phase_offset')

    return param_names, coef_idx_map


def get_x0_and_bounds(param_names):
    x0, bounds = [], []
    for name in param_names:
        if name == 'mean_offset':
            x0.append(0.0); bounds.append((-0.15, 0.15))
        elif name.endswith('_amp_scale'):
            x0.append(1.0); bounds.append((0.3, 3.0))
        elif name.endswith('_phase_offset'):
            cname = name.replace('_phase_offset', '')
            if cname in MAJOR_PHASE_ADJUST:
                x0.append(0.0); bounds.append((-5.0, 5.0))
            else:
                x0.append(0.0); bounds.append((-45.0, 45.0))
    return np.array(x0), bounds


def apply_params_fast(params, param_names, coef_idx_map, A_orig, g_orig_deg):
    """Apply parameter vector → (mean_offset, A_mod, g_mod_rad)."""
    A_mod = A_orig.copy()
    g_mod_deg = g_orig_deg.copy()
    p = dict(zip(param_names, params))

    for name in SHALLOW_WATER:
        if name in coef_idx_map:
            idx = coef_idx_map[name]
            A_mod[idx] = A_orig[idx] * p.get(f'{name}_amp_scale', 1.0)
            g_mod_deg[idx] = g_orig_deg[idx] + p.get(f'{name}_phase_offset', 0.0)

    for name in MAJOR_PHASE_ADJUST:
        if name in coef_idx_map:
            idx = coef_idx_map[name]
            g_mod_deg[idx] = g_orig_deg[idx] + p.get(f'{name}_phase_offset', 0.0)

    return p['mean_offset'], A_mod, np.deg2rad(g_mod_deg)


# ── Cost function ─────────────────────────────────────────────────────

def cost_function(params, param_names, coef_idx_map, A_orig, g_orig_deg,
                  cos_basis, sin_basis, h_mean_only, t_minutes,
                  bsh_hw_t, bsh_hw_h, bsh_nw_t, bsh_nw_h, call_count):
    """Fast cost function."""
    call_count[0] += 1

    mean_offset, A_mod, g_mod_rad = apply_params_fast(
        params, param_names, coef_idx_map, A_orig, g_orig_deg)

    h_pred = fast_reconstruct(mean_offset, A_mod, g_mod_rad,
                               cos_basis, sin_basis, h_mean_only)

    hw_idx, nw_idx = fast_find_hw_nw(h_pred)
    if len(hw_idx) < 50 or len(nw_idx) < 50:
        return 1e10

    cost, stats = fast_match_and_cost(
        h_pred, hw_idx, nw_idx, t_minutes,
        bsh_hw_t, bsh_hw_h, bsh_nw_t, bsh_nw_h, W_TIME)

    if call_count[0] % 200 == 0 and stats:
        print(f"  [{call_count[0]:5d}] cost={cost:.6f}  "
              f"HW: dH={stats['hw_dh']:+.3f}m dT={stats['hw_dt']:+.1f}min  "
              f"NW: dH={stats['nw_dh']:+.3f}m dT={stats['nw_dt']:+.1f}min")

    return cost


# ── Build final harmonics ────────────────────────────────────────────

def build_optimized_results(coef_opt, results_orig):
    """Build XTide 175-constituent results from optimized UTide coefficients."""
    from utide._ut_constants import ut_constants
    const_table = ut_constants['const']
    utide_all_names = [n.strip() for n in const_table.name]

    utide_results = {}
    for i, uname in enumerate(coef_opt['name']):
        uname = uname.strip()
        if uname in utide_all_names:
            idx = utide_all_names.index(uname)
            utide_speed = const_table.freq[idx] * 360.0
        else:
            continue
        xt_name, xt_speed = find_xtide_match(uname, utide_speed)
        if xt_name is None:
            continue
        utide_results[xt_name] = {
            'amplitude': coef_opt['A'][i],
            'phase': coef_opt['g'][i] % 360,
            'speed': xt_speed,
            'snr': coef_opt['SNR'][i] if 'SNR' in coef_opt else 999,
        }

    results = {
        'mean': coef_opt['mean'], 'constituents': [],
        'r_squared': results_orig['r_squared'],
        'rms_error': results_orig['rms_error'],
        'n_analyzed': results_orig['n_analyzed'],
    }
    for name, speed in CONSTITUENTS_175:
        if name in utide_results:
            r = utide_results[name]
            results['constituents'].append({
                'name': name, 'amplitude': r['amplitude'],
                'phase': r['phase'], 'speed': speed, 'snr': r['snr']
            })
        else:
            results['constituents'].append({
                'name': name, 'amplitude': 0.0, 'phase': 0.0,
                'speed': speed, 'not_analyzed': True
            })
    return results


# ── Main ──────────────────────────────────────────────────────────────

def main():
    print("=" * 75)
    print("Optimize Cuxhaven-Steubenhöft Harmonics against BSH Reference")
    print("=" * 75)

    # 1. Parse BSH predictions
    print(f"\n1. Parsing BSH predictions...")
    bsh_preds = parse_bsh_predictions(BSH_FILE)
    print(f"   {len(bsh_preds)} predictions")

    # 2. UTide harmonic analysis
    print(f"\n2. Running UTide harmonic analysis...")
    data = parse_json_water_levels(ZIP_PATH, sample_interval_minutes=60, use_last_n_years=10)
    if data is None:
        print("FAILED"); return

    results_orig = harmonic_analysis_utide(data['datetimes_utc'], data['levels'], LAT)
    if results_orig is None:
        print("FAILED"); return

    print("   Getting raw UTide coefficients...")
    coef_orig = utide.solve(
        data['datetimes_utc'], data['levels'], lat=LAT,
        nodal=True, trend=False, method='ols',
        conf_int='none', verbose=False, constit='auto',
    )
    print(f"   {len(coef_orig['name'])} constituents, mean={coef_orig['mean']:.4f} m")

    # 3. Create 2026 time array
    print(f"\n3. Creating 2026 reconstruction grid...")
    t_start = datetime(2025, 12, 31, 23, 0)
    t_end = datetime(2027, 1, 1, 1, 0)
    n_points = int((t_end - t_start).total_seconds() / 360) + 1
    t_pred = np.array([t_start + timedelta(minutes=6 * i) for i in range(n_points)])
    t_minutes = np.array([(t - t_start).total_seconds() / 60.0 for t in t_pred])
    print(f"   {len(t_pred)} points")

    # Prepare BSH arrays for fast matching
    bsh_hw_t, bsh_hw_h, bsh_nw_t, bsh_nw_h = prepare_bsh_arrays(bsh_preds, t_start)
    print(f"   BSH: {len(bsh_hw_t)} HW, {len(bsh_nw_t)} NW")

    # 4. Precompute basis vectors
    print(f"\n4. Precomputing basis vectors...")
    cos_basis, sin_basis, h_mean_only = precompute_basis(t_pred, coef_orig)

    # Verify
    h_utide = utide.reconstruct(t_pred, coef_orig, verbose=False)['h']
    A_orig = coef_orig['A'].copy()
    g_orig_deg = coef_orig['g'].copy()
    h_basis = fast_reconstruct(0.0, A_orig, np.deg2rad(g_orig_deg),
                                cos_basis, sin_basis, h_mean_only)
    print(f"   Verification: max |utide - basis| = {np.max(np.abs(h_utide - h_basis)):.6f} m")

    # 5. Baseline evaluation
    print(f"\n5. Baseline evaluation...")
    hw_idx, nw_idx = fast_find_hw_nw(h_utide)
    _, base_stats = fast_match_and_cost(
        h_utide, hw_idx, nw_idx, t_minutes,
        bsh_hw_t, bsh_hw_h, bsh_nw_t, bsh_nw_h, W_TIME)
    print(f"   HW ({base_stats['n_hw']}): mean dH={base_stats['hw_dh']:+.3f}m, mean dT={base_stats['hw_dt']:+.1f}min")
    print(f"   NW ({base_stats['n_nw']}): mean dH={base_stats['nw_dh']:+.3f}m, mean dT={base_stats['nw_dt']:+.1f}min")

    # 6. Optimization
    print(f"\n6. Setting up optimization...")
    param_names, coef_idx_map = build_param_info(coef_orig)
    x0, bounds = get_x0_and_bounds(param_names)
    print(f"   {len(param_names)} parameters:")
    for i, name in enumerate(param_names):
        print(f"     [{i:2d}] {name:25s}  x0={x0[i]:.2f}  bounds={bounds[i]}")

    call_count = [0]
    cost_args = (param_names, coef_idx_map, A_orig, g_orig_deg,
                 cos_basis, sin_basis, h_mean_only, t_minutes,
                 bsh_hw_t, bsh_hw_h, bsh_nw_t, bsh_nw_h, call_count)

    # Pass 1: Differential Evolution
    print(f"\n   --- Pass 1: Differential Evolution ---")
    result_de = differential_evolution(
        cost_function, bounds, args=cost_args,
        maxiter=150, popsize=15, tol=1e-8,
        mutation=(0.5, 1.5), recombination=0.9,
        seed=42, polish=False,
    )
    print(f"   DE: {result_de.message}")
    print(f"   {call_count[0]} evaluations, cost={result_de.fun:.6f}")

    # Pass 2: Powell refinement
    print(f"\n   --- Pass 2: Powell ---")
    call_count[0] = 0
    result_pw = minimize(
        cost_function, result_de.x, args=cost_args,
        method='Powell', bounds=bounds,
        options={'maxiter': 5000, 'ftol': 1e-12},
    )
    print(f"   Powell: {result_pw.message}")
    print(f"   {call_count[0]} evaluations, cost={result_pw.fun:.6f}")

    best_params = result_pw.x

    # 7. Results
    print(f"\n7. Optimized parameters:")
    for i, name in enumerate(param_names):
        print(f"     {name:25s}  {best_params[i]:+.4f}  (change: {best_params[i] - x0[i]:+.4f})")

    mean_off, A_opt, g_opt_rad = apply_params_fast(
        best_params, param_names, coef_idx_map, A_orig, g_orig_deg)
    h_opt = fast_reconstruct(mean_off, A_opt, g_opt_rad, cos_basis, sin_basis, h_mean_only)
    hw_idx_o, nw_idx_o = fast_find_hw_nw(h_opt)
    _, opt_stats = fast_match_and_cost(
        h_opt, hw_idx_o, nw_idx_o, t_minutes,
        bsh_hw_t, bsh_hw_h, bsh_nw_t, bsh_nw_h, W_TIME)

    print(f"\n8. Comparison: Baseline vs Optimized")
    print(f"   {'':30s} {'BASELINE':>15s} {'OPTIMIZED':>15s} {'CHANGE':>15s}")
    print(f"   {'─'*75}")
    for label, bk, ok in [
        ('HW mean dH (m)', base_stats['hw_dh'], opt_stats['hw_dh']),
        ('HW mean dT (min)', base_stats['hw_dt'], opt_stats['hw_dt']),
        ('HW mean |dH| (m)', base_stats['hw_abs_dh'], opt_stats['hw_abs_dh']),
        ('HW mean |dT| (min)', base_stats['hw_abs_dt'], opt_stats['hw_abs_dt']),
        ('NW mean dH (m)', base_stats['nw_dh'], opt_stats['nw_dh']),
        ('NW mean dT (min)', base_stats['nw_dt'], opt_stats['nw_dt']),
        ('NW mean |dH| (m)', base_stats['nw_abs_dh'], opt_stats['nw_abs_dh']),
        ('NW mean |dT| (min)', base_stats['nw_abs_dt'], opt_stats['nw_abs_dt']),
    ]:
        fmt = '.3f' if '(m)' in label else '.1f'
        print(f"   {label:30s} {bk:>+15{fmt}} {ok:>+15{fmt}} {ok-bk:>+15{fmt}}")

    # 9. Write harmonics file
    print(f"\n9. Writing optimized harmonics...")
    coef_opt = deepcopy(coef_orig)
    coef_opt['mean'] = coef_orig['mean'] + mean_off
    coef_opt['A'] = A_opt.copy()
    coef_opt['g'] = np.rad2deg(g_opt_rad) % 360

    results_opt = build_optimized_results(coef_opt, results_orig)
    header = read_header_from_template(TEMPLATE_PATH)

    lines = []
    lines.append(f"# Harmonic constants derived from Pegelonline water level data")
    lines.append(f"# using UTide (v{utide.__version__}) with {data['n_obs']} observations")
    lines.append(f"# from {data['start_time'].strftime('%Y-%m-%d')} to {data['end_time'].strftime('%Y-%m-%d')}")
    lines.append(f"# R^2 = {results_orig['r_squared']:.4f}, RMS error = {results_orig['rms_error']:.4f} m")
    lines.append(f"# Constituents analyzed: {results_orig['n_analyzed']}")
    lines.append(f"# OPTIMIZED against BSH DE__506P2026 HW/NW predictions")
    lines.append(f"# Optimization: shallow-water constituents + mean level adjusted")
    lines.append(f"# NW bias reduced from {base_stats['nw_dh']:+.3f}m/{base_stats['nw_dt']:+.1f}min "
                 f"to {opt_stats['nw_dh']:+.3f}m/{opt_stats['nw_dt']:+.1f}min")
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
    lines.append(f"# source: Derived from Pegelonline data ({data['start_time'].year}-{data['end_time'].year}) with UTide, optimized against BSH predictions")
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
    lines.append(f"{results_opt['mean']:.4f} meters")

    for c in results_opt['constituents']:
        if c.get('not_analyzed') or c['amplitude'] < 0.00005:
            lines.append(f"x 0 0")
        else:
            lines.append(f"{c['name']:15s} {c['amplitude']:.4f}  {c['phase']:.2f}")

    with open(OUTPUT_PATH, 'w', encoding='latin-1') as f:
        f.write(header)
        f.write('\n')
        f.write('\n'.join(lines))
        f.write('\n')

    print(f"   Written to {OUTPUT_PATH}")
    print(f"\nDone! Run compare_cuxhaven_bsh.py to verify.")


if __name__ == "__main__":
    main()
