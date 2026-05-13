#!/usr/bin/env python3
"""
Predict 3 months hourly for Sfax from:
  - cabaigne UTide fit (in pickle)
  - SHOM-derived UTide TCD (harmonics_utide_tidetables.tcd) — file pred_shom_utide.txt
  - Legacy 1997 SHOM TCD (harmonics-1997-05-25_mod.tcd) — file pred_shom_1997.txt

Compute pairwise RMS and bias differences after removing mean (so different datums
don't dominate the comparison).
"""
from __future__ import annotations
import sys, pickle
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, '/home/oliver/py')
import utide


PRED_DIR = Path('/tmp/cabaigne_sfax')


def load_tide_output(path: Path):
    """Parse `tide -m m -z` lines: '2026-01-01 12:00 AM UTC 1.393394'"""
    times, vals = [], []
    for line in open(path):
        parts = line.strip().split()
        if len(parts) < 5:
            continue
        date = parts[0]; time_s = parts[1]; ampm = parts[2]
        if parts[3] != 'UTC':
            continue
        val = float(parts[4])
        dt = datetime.strptime(f"{date} {time_s} {ampm}", "%Y-%m-%d %I:%M %p")
        times.append(dt); vals.append(val)
    return np.array(times), np.array(vals)


def predict_from_pickle(pkl_path: Path, datetimes_utc: np.ndarray) -> np.ndarray:
    """Predict water levels at given datetimes from the cabaigne UTide pickle."""
    with open(pkl_path, 'rb') as f:
        d = pickle.load(f)
    coef = d['coef']
    recon = utide.reconstruct(datetimes_utc, coef, verbose=False)
    return recon['h']


def compare(a_name, a_vals, b_name, b_vals):
    """RMS difference after removing per-series mean (datum-agnostic comparison)."""
    a = a_vals - np.mean(a_vals)
    b = b_vals - np.mean(b_vals)
    diff = a - b
    rms = np.sqrt(np.mean(diff**2))
    bias = np.mean(a_vals - b_vals)
    corr = np.corrcoef(a, b)[0, 1]
    a_std = np.std(a); b_std = np.std(b)
    print(f"  {a_name} vs {b_name}:")
    print(f"    RMS(centered) = {rms:.4f} m  (corr={corr:.4f})")
    print(f"    σ(a)={a_std:.3f} m  σ(b)={b_std:.3f} m  ratio={b_std/a_std:.3f}")
    print(f"    mean(a-b) = {bias:+.4f} m  (datum offset)")
    return rms, corr, bias


def main():
    print("Loading TCD predictions...")
    t_shom_utide, v_shom_utide = load_tide_output(PRED_DIR / 'pred_shom_utide.txt')
    t_shom_1997, v_shom_1997 = load_tide_output(PRED_DIR / 'pred_shom_1997.txt')
    print(f"  SHOM-UTide (TCD): {len(t_shom_utide)} pts")
    print(f"  SHOM-1997 (TCD):  {len(t_shom_1997)} pts")

    # Verify same time grid
    assert np.array_equal(t_shom_utide, t_shom_1997)

    # Predict cabaigne fit on same grid
    print("Predicting cabaigne UTide at same grid...")
    v_cab = predict_from_pickle(PRED_DIR / 'sfax_fit.pkl', t_shom_utide)

    print("\n=== Pairwise comparisons (3 months, hourly, Jan-Mar 2026) ===\n")
    compare("cabaigne-UTide   ", v_cab, "SHOM-UTide TCD   ", v_shom_utide)
    print()
    compare("cabaigne-UTide   ", v_cab, "SHOM-1997 legacy ", v_shom_1997)
    print()
    compare("SHOM-UTide TCD   ", v_shom_utide, "SHOM-1997 legacy ", v_shom_1997)

    # Per-day HW/LW timing — find peaks in cabaigne fit
    print("\n=== Sample peaks Jan 1-3 2026 (top 3 of each) ===")
    for name, vals in [("cabaigne-UTide", v_cab),
                       ("SHOM-UTide TCD", v_shom_utide),
                       ("SHOM-1997 leg.", v_shom_1997)]:
        # Find local maxima in first 72 hours
        idx_peaks = []
        for i in range(1, 71):
            if vals[i] > vals[i-1] and vals[i] > vals[i+1]:
                idx_peaks.append(i)
        peaks = [(t_shom_utide[i], vals[i]) for i in idx_peaks[:3]]
        print(f"  {name}: {[(t.strftime('%m-%d %H:00 UTC'), round(v,3)) for t,v in peaks]}")


if __name__ == '__main__':
    main()
