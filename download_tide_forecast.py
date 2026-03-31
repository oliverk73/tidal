#!/usr/bin/env python3
"""
Compute tide height forecasts from FES2022 on a global grid and export
as compact binary files for client-side Canvas rendering.

Source: FES2022 extrapolated (34 constituents, ~1/30° native resolution)
        Precomputed amplitudes/phases interpolated to target grid.

Output per frame:
  tide_f{NNN}.bin  — int16 LE, tide height in mm (signed, -32768..+32767)

Binary encoding:
  value = round(tide_height_meters * 1000)
  → +1500 = +1.5m,  -800 = -0.8m,  -32768 = no data (land)

Usage:
    python3 download_tide_forecast.py [--hours 24] [--step 1] [--res 0.5]
"""

import os
import json
import argparse
import numpy as np
import xarray as xr
from datetime import datetime, timezone, timedelta

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "static", "tides")

FES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "tide_models", "fes2022b", "ocean_tide_extrapolated")

NO_DATA = -32768

# Constituent angular speeds in degrees/hour (from IHO/Schureman)
SPEEDS_DEG_PER_HOUR = {
    "2n2":    27.8953548,
    "eps2":   27.9682084,
    "j1":     15.5854433,
    "k1":     15.0410686,
    "k2":     30.0821373,
    "l2":     29.5284789,
    "lambda2":29.4556253,
    "m2":     28.9841042,
    "m3":     43.4761563,
    "m4":     57.9682084,
    "m6":     86.9523127,
    "m8":    115.9364169,
    "mf":      1.0980331,
    "mks2":   29.0662415,
    "mm":      0.5443747,
    "mn4":    57.4238337,
    "ms4":    58.9841042,
    "msf":     1.0158958,
    "msqm":    2.1136868,
    "mtm":     1.6424078,
    "mu2":    27.9682084,
    "n2":     28.4397295,
    "nu2":    28.5125831,
    "o1":     13.9430356,
    "p1":     14.9589314,
    "q1":     13.3986609,
    "r2":     30.0410667,
    "s1":     15.0000000,
    "s2":     30.0000000,
    "s4":     60.0000000,
    "sa":      0.0410686,
    "ssa":     0.0821373,
    "t2":     29.9589333,
}


def compute_nodal_corrections(t_ref):
    """Compute nodal modulation factors f and u for time t_ref.

    Uses simplified formulas based on N (longitude of ascending node).
    Good enough for ~1 year around t_ref.
    """
    # Julian centuries from J2000.0
    jd = 2451545.0 + (t_ref - datetime(2000, 1, 1, 12, 0, 0,
                                        tzinfo=timezone.utc)).total_seconds() / 86400.0
    T = (jd - 2451545.0) / 36525.0

    # Longitude of ascending node of moon's orbit (degrees)
    N = 125.04452 - 1934.136261 * T
    N_rad = np.radians(N)

    # Longitude of lunar perigee
    P = 83.3535 + 4069.0137 * T
    P_rad = np.radians(P)

    cosN = np.cos(N_rad)
    sinN = np.sin(N_rad)
    cos2N = np.cos(2 * N_rad)
    sin2N = np.sin(2 * N_rad)

    # Nodal factors f and phase corrections u (degrees) for major constituents
    # From Schureman / Foreman
    f = {}
    u = {}

    # Semidiurnal
    f["m2"] = 1.0004 - 0.0373 * cosN + 0.0002 * cos2N
    u["m2"] = np.degrees(-0.0374 * sinN)

    f["s2"] = 1.0
    u["s2"] = 0.0

    f["n2"] = f["m2"]
    u["n2"] = u["m2"]

    f["k2"] = 1.0241 + 0.2863 * cosN + 0.0083 * cos2N
    u["k2"] = np.degrees(-0.3013 * sinN - 0.0092 * sin2N)

    f["2n2"] = f["m2"] ** 2
    u["2n2"] = 2 * u["m2"]

    f["mu2"] = f["m2"] ** 2
    u["mu2"] = 2 * u["m2"]

    f["nu2"] = f["m2"]
    u["nu2"] = u["m2"]

    f["l2"] = 1.0  # simplified
    u["l2"] = 0.0

    f["lambda2"] = 1.0
    u["lambda2"] = 0.0

    f["t2"] = 1.0
    u["t2"] = 0.0

    f["r2"] = 1.0
    u["r2"] = 0.0

    f["eps2"] = f["m2"] ** 2
    u["eps2"] = 2 * u["m2"]

    # Diurnal
    f["k1"] = 1.0060 + 0.1150 * cosN - 0.0088 * cos2N
    u["k1"] = np.degrees(-0.1546 * sinN + 0.0119 * sin2N)

    f["o1"] = 1.0089 + 0.1871 * cosN - 0.0147 * cos2N
    u["o1"] = np.degrees(0.1885 * sinN - 0.0234 * sin2N)

    f["p1"] = 1.0
    u["p1"] = 0.0

    f["q1"] = f["o1"]
    u["q1"] = u["o1"]

    f["j1"] = f["k1"]
    u["j1"] = u["k1"]

    f["s1"] = 1.0
    u["s1"] = 0.0

    # Shallow-water
    f["m4"] = f["m2"] ** 2
    u["m4"] = 2 * u["m2"]

    f["ms4"] = f["m2"]
    u["ms4"] = u["m2"]

    f["mn4"] = f["m2"] ** 2
    u["mn4"] = 2 * u["m2"]

    f["m6"] = f["m2"] ** 3
    u["m6"] = 3 * u["m2"]

    f["m8"] = f["m2"] ** 4
    u["m8"] = 4 * u["m2"]

    f["m3"] = f["m2"] ** 1.5
    u["m3"] = 1.5 * u["m2"]

    f["s4"] = 1.0
    u["s4"] = 0.0

    f["mks2"] = f["m2"] * f["k2"]
    u["mks2"] = u["m2"] + u["k2"]

    # Long period
    f["mf"] = 1.0429 + 0.4135 * cosN
    u["mf"] = np.degrees(-0.4143 * sinN)

    f["mm"] = 1.0
    u["mm"] = 0.0

    f["sa"] = 1.0
    u["sa"] = 0.0

    f["ssa"] = 1.0
    u["ssa"] = 0.0

    f["msf"] = 1.0
    u["msf"] = 0.0

    f["msqm"] = f["mf"]
    u["msqm"] = u["mf"]

    f["mtm"] = f["mf"]
    u["mtm"] = u["mf"]

    return f, u


def compute_V0(t_ref):
    """Compute astronomical argument V0 for each constituent at t_ref.

    Returns dict of V0 in degrees.
    """
    # Julian date
    jd = 2451545.0 + (t_ref - datetime(2000, 1, 1, 12, 0, 0,
                                        tzinfo=timezone.utc)).total_seconds() / 86400.0
    T = (jd - 2451545.0) / 36525.0

    # Mean longitudes (degrees)
    # s = mean longitude of Moon
    s = 218.3165 + 481267.8813 * T
    # h = mean longitude of Sun
    h = 280.4661 + 36000.7698 * T
    # p = longitude of lunar perigee
    p = 83.3535 + 4069.0137 * T
    # N = longitude of ascending node (already negative in convention)
    N = 125.0445 - 1934.1363 * T
    # p1 = longitude of solar perigee
    p1 = 282.9384 + 1.7195 * T

    # GMST in degrees (for sidereal-based constituents)
    # tau = GMST + 180 - s (hour angle of mean moon)
    GMST = 280.46061837 + 360.98564736629 * (jd - 2451545.0) + \
           0.000387933 * T**2
    tau = GMST + 180.0 - s

    V0 = {}
    # Semidiurnal
    V0["m2"]  = 2*tau + 2*s - 2*h
    V0["s2"]  = 2*tau + 2*s - 2*h + 2*h - 2*s  # = 2*tau = 2*GMST + 360 - 2*s ... simplify
    V0["s2"]  = 2*(GMST + 180.0)  # S2 = 2T_solar
    V0["n2"]  = 2*tau + 2*s - 2*h - s + p  # = 2*tau + s - 2*h + p
    V0["k2"]  = 2*tau + 2*s - 2*h + 2*h - 2*s + 2*s  # = 2*(tau + s) = 2*GMST + 360
    V0["k2"]  = 2*(GMST + 180.0 + s - s + h - h)
    # Proper V0 definitions
    V0["m2"]  = 2*tau + 2*(s - h)
    V0["s2"]  = 2*tau + 2*(s - h) + 2*(h - s)
    V0["n2"]  = 2*tau + 2*(s - h) - (s - p)
    V0["k2"]  = 2*tau + 2*(s - h) + 2*(h - s) + 2*s
    V0["2n2"] = 2*tau + 2*(s - h) - 2*(s - p)
    V0["mu2"] = 2*tau + 2*(s - h) - 2*(s - h)  # = 2*tau
    V0["nu2"] = 2*tau + 2*(s - h) - (s - p) + (s - 2*h + p)  # correction
    V0["l2"]  = 2*tau + 2*(s - h) + (s - p)  # simplified
    V0["lambda2"] = 2*tau + 2*(s - h) - (s - p) + 180.0
    V0["t2"]  = 2*tau + 2*(s - h) + (h - p1)  # approximate
    V0["r2"]  = 2*tau + 2*(s - h) - (h - p1) + 180.0
    V0["eps2"] = 2*tau + 2*(s - h) - 2*(s - h)  # same as mu2
    V0["mks2"] = 2*tau + 2*(s - h) + (s - p)  # simplified

    # Properly redefine using standard Doodson
    tau_d = tau  # = GMST + 180 - s
    V0["m2"]  = 2*tau_d + 2*s - 2*h
    V0["s2"]  = 2*tau_d + 2*h  # wrong ... let me use standard

    # Use standard V0 = Doodson * (tau, s, h, p, N', p1)
    # Standard astronomical arguments
    V0 = {}
    V0["m2"]      = 2*tau + 2*s - 2*h
    V0["s2"]      = 2*tau + 2*s  # Doodson: 2 0 0 0 0 0, but tau already = GMST+180-s
    # Actually let me use the simple approach: V0 = speed * T from epoch
    # This is equivalent but simpler. Use standard Cartwright convention.

    # Correct Doodson-based V0:
    # V0(const) = n1*tau + n2*s + n3*h + n4*p + n5*(-N) + n6*p1
    doodson = {
        "m2":      (2, 0, 0, 0, 0, 0),
        "s2":      (2, 2,-2, 0, 0, 0),
        "n2":      (2,-1, 0, 1, 0, 0),
        "k2":      (2, 2, 0, 0, 0, 0),
        "2n2":     (2,-2, 0, 2, 0, 0),
        "mu2":     (2,-2, 2, 0, 0, 0),
        "nu2":     (2,-1, 2,-1, 0, 0),
        "l2":      (2, 1, 0,-1, 0, 0),
        "lambda2": (2,-1, 0, 1, 0, 2),  # has correction
        "t2":      (2, 2,-3, 0, 0, 1),
        "r2":      (2, 2,-1, 0, 0,-1),
        "eps2":    (2,-3, 2, 1, 0, 0),  # corrected
        "mks2":    (2, 2, 0, 0, 0, 0),  # same as K2
        "k1":      (1, 1, 0, 0, 0, 0),
        "o1":      (1,-1, 0, 0, 0, 0),
        "p1":      (1, 1,-2, 0, 0, 0),
        "q1":      (1,-2, 0, 1, 0, 0),
        "j1":      (1, 2, 0,-1, 0, 0),
        "s1":      (1, 1,-1, 0, 0, 0),
        "m4":      (4, 0, 0, 0, 0, 0),
        "ms4":     (4, 2,-2, 0, 0, 0),
        "mn4":     (4,-1, 0, 1, 0, 0),
        "m6":      (6, 0, 0, 0, 0, 0),
        "m8":      (8, 0, 0, 0, 0, 0),
        "m3":      (3, 0, 0, 0, 0, 0),
        "s4":      (4, 4,-4, 0, 0, 0),
        "mf":      (0, 2, 0, 0, 0, 0),
        "mm":      (0, 1, 0,-1, 0, 0),
        "sa":      (0, 0, 1, 0, 0, 0),
        "ssa":     (0, 0, 2, 0, 0, 0),
        "msf":     (0, 2,-2, 0, 0, 0),
        "msqm":    (0, 3, 0,-1, 0, 0),  # approximate
        "mtm":     (0, 3,-2, 1, 0, 0),  # approximate
    }

    Nm = -N  # N' = -N (negative of ascending node)

    V0 = {}
    for name, (n1, n2, n3, n4, n5, n6) in doodson.items():
        V0[name] = n1*tau + n2*s + n3*h + n4*p + n5*Nm + n6*p1

    # Normalize to 0-360
    for k in V0:
        V0[k] = V0[k] % 360.0

    return V0


def load_fes_grid(target_res):
    """Load FES2022 amplitudes and phases, interpolated to target grid.

    Returns: lats, lons, amp_grids, pha_grids (dict by constituent name)
    """
    files = sorted([f for f in os.listdir(FES_DIR)
                    if f.endswith('.nc') and not f.startswith('mask')])

    # Determine target grid from first file
    ds0 = xr.open_dataset(os.path.join(FES_DIR, files[0]))
    native_lats = ds0['lat'].values
    native_lons = ds0['lon'].values
    ds0.close()

    native_res = abs(native_lats[1] - native_lats[0])
    step = max(1, int(round(target_res / native_res)))

    lats = native_lats[::step]
    lons = native_lons[::step]

    # Ensure lat goes North→South for the binary output
    if lats[0] < lats[-1]:
        lats = lats[::-1]
        flip_lat = True
    else:
        flip_lat = False

    print(f"  Native: {len(native_lats)}x{len(native_lons)} ({native_res:.4f}°)")
    print(f"  Target: {len(lats)}x{len(lons)} ({target_res}°, step={step})")

    amp_grids = {}
    pha_grids = {}

    for f in files:
        name = f.replace('_fes2022.nc', '')
        if name not in SPEEDS_DEG_PER_HOUR:
            print(f"  Skipping unknown constituent: {name}")
            continue

        ds = xr.open_dataset(os.path.join(FES_DIR, f))
        amp = ds['amplitude'].values[::step, ::step]  # in cm
        pha = ds['phase'].values[::step, ::step]       # in degrees
        ds.close()

        if flip_lat:
            amp = amp[::-1]
            pha = pha[::-1]

        amp_grids[name] = amp / 100.0  # cm → m
        pha_grids[name] = pha
        print(f"  Loaded {name:8s}: max amp {np.nanmax(amp):.1f} cm")

    return lats, lons, amp_grids, pha_grids


def predict_tide_grid(lats, lons, amp_grids, pha_grids, t, t_ref, V0, f_nod, u_nod):
    """Compute tide height for entire grid at time t.

    h(t) = sum_i [ f_i * A_i * cos(V0_i + speed_i * dt + u_i - G_i) ]

    where dt = hours since t_ref, G_i = Greenwich phase lag from FES
    """
    dt_hours = (t - t_ref).total_seconds() / 3600.0
    ny, nx = len(lats), len(lons)
    height = np.zeros((ny, nx), dtype=np.float64)

    for name, amp in amp_grids.items():
        pha = pha_grids[name]
        speed = SPEEDS_DEG_PER_HOUR[name]
        v0 = V0.get(name, 0.0)
        fn = f_nod.get(name, 1.0)
        un = u_nod.get(name, 0.0)

        # Phase argument in degrees
        argument = v0 + speed * dt_hours + un - pha

        # Add to height (only where amp is valid)
        valid = ~np.isnan(amp) & (amp > 0)
        cos_arg = np.cos(np.radians(argument))
        contribution = fn * amp * cos_arg
        contribution[~valid] = 0.0
        height += contribution

    return height


def main():
    parser = argparse.ArgumentParser(description="Compute FES2022 tide forecast grid")
    parser.add_argument("--hours", type=int, default=25,
                        help="Forecast hours (default: 25)")
    parser.add_argument("--step", type=int, default=1,
                        help="Hour step between frames (default: 1)")
    parser.add_argument("--res", type=float, default=0.5,
                        help="Target resolution in degrees (default: 0.5)")
    args = parser.parse_args()

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Clean old files
    for f in os.listdir(OUTPUT_DIR):
        if f.startswith("tide_f") and f.endswith(".bin"):
            os.remove(os.path.join(OUTPUT_DIR, f))

    print(f"FES2022 Tide Forecast")
    print(f"  Resolution: {args.res}°")
    print(f"  Hours: {args.hours}, step: {args.step}h")
    print()

    # Load FES2022 grid data
    print("Loading FES2022 constituents...")
    lats, lons, amp_grids, pha_grids = load_fes_grid(args.res)
    print(f"  {len(amp_grids)} constituents loaded")
    print()

    # Build a land mask: where ALL constituents are NaN or zero
    land_mask = np.ones((len(lats), len(lons)), dtype=bool)
    for amp in amp_grids.values():
        land_mask &= (np.isnan(amp) | (amp <= 0))

    # Reference time = start of current hour
    now = datetime.now(timezone.utc)
    t_ref = now.replace(minute=0, second=0, microsecond=0)

    # Compute astronomical arguments and nodal corrections
    print("Computing V0 and nodal corrections...")
    V0 = compute_V0(t_ref)
    f_nod, u_nod = compute_nodal_corrections(t_ref)
    print()

    # Generate frames
    fhours = list(range(0, args.hours + 1, args.step))
    frames = []
    grid_info = None
    ny, nx = len(lats), len(lons)

    for fh in fhours:
        t = t_ref + timedelta(hours=fh)
        print(f"  Computing f{fh:03d} ({t.strftime('%d.%m. %H:%M UTC')})... ",
              end="", flush=True)

        height = predict_tide_grid(lats, lons, amp_grids, pha_grids,
                                    t, t_ref, V0, f_nod, u_nod)

        # Apply land mask
        height[land_mask] = np.nan

        # Convert to int16 millimeters, NaN → NO_DATA
        h_mm = np.round(height * 1000).astype(np.float64)
        h_mm[np.isnan(h_mm)] = NO_DATA
        h_i16 = np.clip(h_mm, -32767, 32767).astype(np.int16)
        h_i16[land_mask] = NO_DATA

        fname = f"tide_f{fh:03d}.bin"
        h_i16.tofile(os.path.join(OUTPUT_DIR, fname))
        fsize = os.path.getsize(os.path.join(OUTPUT_DIR, fname))

        ocean_pts = (~land_mask).sum()
        h_valid = height[~land_mask]
        if len(h_valid) > 0:
            print(f"OK ({nx}x{ny}, {fsize//1024} KB, "
                  f"range {h_valid.min():.2f}..{h_valid.max():.2f}m, "
                  f"{ocean_pts} ocean pts)")
        else:
            print(f"OK ({nx}x{ny}, {fsize//1024} KB, no ocean)")

        if grid_info is None:
            dx = round(abs(float(lons[1] - lons[0])), 4)
            dy = round(abs(float(lats[0] - lats[1])), 4)
            grid_info = {
                "nx": nx, "ny": ny,
                "la1": round(float(lats[0]), 4),
                "la2": round(float(lats[-1]), 4),
                "lo1": round(float(lons[0]), 4),
                "lo2": round(float(lons[-1]), 4),
                "dx": dx, "dy": dy,
            }

        frames.append({
            "file": fname,
            "hour": fh,
            "label": t.strftime("%d.%m. %H:%M UTC"),
        })

    # Write metadata
    meta = {
        "source": "FES2022 extrapolated",
        "resolution": args.res,
        "generated": datetime.now(timezone.utc).isoformat(),
        "refTime": t_ref.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "grid": grid_info,
        "frames": frames,
    }
    meta_path = os.path.join(OUTPUT_DIR, "tide_meta.json")
    with open(meta_path, "w") as fp:
        json.dump(meta, fp, indent=2)

    total_size = sum(
        os.path.getsize(os.path.join(OUTPUT_DIR, f["file"]))
        for f in frames
    )
    print(f"\nFertig! {len(frames)} Frames in {OUTPUT_DIR}/")
    print(f"  Grid: {nx}x{ny}, {args.res}°")
    print(f"  Gesamt: {total_size // (1024*1024)} MB")
    print(f"  Metadaten: {meta_path}")


if __name__ == "__main__":
    main()
