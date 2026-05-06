#!/usr/bin/env python3
"""Parse CMEMS in-situ tide gauge NetCDF for 5 Spanish stations and run
UTide harmonic analysis, then append blocks to harmonics_utide_observations.txt.

Sources:
  - PdE/REDMAR (Puertos del Estado): Cartagena
  - SOCIB (Balearen): Sant Antoni de Portmany, Andratx, Pollença, Sa Rapita

Mediterranean stations have very small tides (~5 cm M2) so R² is lower
than for Atlantic stations.
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import utide
from netCDF4 import Dataset

NC_DIR = Path("/home/oliver/water_levels/Spain_CMEMS_5")
TARGET = Path("/home/oliver/harmonics/utide/harmonics_utide_observations.txt")

STATIONS = [
    {"file": "IR_TS_TG_CartagenaTG_60minute.nc", "cst": "CARTAGENA",
     "name": "Cartagena", "country": "Spain",
     "lat": 37.5967, "lon": -0.9738,
     "water": "Mediterranean Sea", "network": "PdE-REDMAR"},
    {"file": "MO_TS_TG_SANT-ANTONI_60minute.nc", "cst": "SANT-ANTONI",
     "name": "Sant Antoni de Portmany, Ibiza, Baleares", "country": "Spain",
     "lat": 38.9771, "lon": 1.2988,
     "water": "Mediterranean Sea (Balearic Islands)", "network": "SOCIB"},
    {"file": "MO_TS_TG_ANDRATX_60minute.nc", "cst": "ANDRATX",
     "name": "Andratx, Mallorca, Baleares", "country": "Spain",
     "lat": 39.5442, "lon": 2.3785,
     "water": "Mediterranean Sea (Balearic Islands)", "network": "SOCIB"},
    {"file": "MO_TS_TG_POLLENSA_60minute.nc", "cst": "POLLENSA",
     "name": "Pollença, Mallorca, Baleares", "country": "Spain",
     "lat": 39.9046, "lon": 3.0885,
     "water": "Mediterranean Sea (Balearic Islands)", "network": "SOCIB"},
    {"file": "MO_TS_TG_SA-RAPITA_60minute.nc", "cst": "SA-RAPITA",
     "name": "Sa Rapita, Mallorca, Baleares", "country": "Spain",
     "lat": 39.3603, "lon": 2.9533,
     "water": "Mediterranean Sea (Balearic Islands)", "network": "SOCIB"},
]

# 175-constituent XTide order (matches existing FCUL/SHOM blocks).
XTIDE_175 = [
    "J1", "K1", "K2", "L2", "M1", "M2", "M3", "M4", "M6", "M8",
    "N2", "2N2", "O1", "OO1", "P1", "Q1", "2Q1", "R2", "S1", "S2",
    "S4", "S6", "T2", "LDA2", "MU2", "NU2", "RHO1", "MK3", "2MK3",
    "MN4", "MS4", "2SM2", "MF", "MSF", "MM", "SA", "SSA", "SA-IOS",
    "MF-IOS", "S1-IOS", "OO1-IOS", "R2-IOS", "A7", "2MK5", "2MK6",
    "2MN2", "2MN6", "2MS6", "2NM6", "2SK5", "2SM6", "3MK7", "3MN8",
    "3MS2", "3MS4", "3MS8", "ALP1", "BET1", "CHI1", "H1", "H2",
    "KJ2", "ETA2", "KQ1", "UPS1", "M10", "M12", "MK4", "MKS2",
    "MNS2", "EPS2", "MO3", "MP1", "TAU1", "MPS2", "MSK6", "MSM",
    "MSN2", "MSN6", "NLK2", "NO1", "OP2", "OQ2", "PHI1", "KP1",
    "PI1", "TK1", "PSI1", "RP1", "SIG1", "SK3", "SK4", "SN4",
    "SO1", "SO3", "ST36", "ST37", "ST38", "ST40", "ST41", "ST42",
    "ST43", "ST44", "ST45", "ST46", "ST47", "ST1", "ST2", "ST3",
    "ST4", "ST5", "ST6", "ST7", "ST8", "ST9", "ST10", "ST11",
    "ST12", "ST13", "ST14", "ST15", "ST16", "ST17", "ST18", "ST19",
    "ST20", "ST21", "ST22", "ST23", "ST24", "ST25", "ST26", "ST27",
    "ST28", "ST29", "ST30", "ST31", "ST32", "ST33", "ST34", "ST35",
    "MQ3", "2MK2", "2NS6", "2OK1", "2OP2", "2Q1-IOS", "2SK6",
    "3MK4", "4MK5", "4MS2", "4MS4", "5MKS2", "5MS4", "6MNS6",
    "7MK7", "8MK8", "MA2", "MB2", "MC2", "MFM", "MS2", "MSK4",
    "MSO5", "NSK4", "PSI1-IOS", "QQ1", "S3", "S5", "S7", "SO2",
    "T1", "TK3",
]


def load_nc(path: Path) -> tuple[np.ndarray, np.ndarray]:
    ds = Dataset(path)
    t_days = ds["TIME"][:]
    sl = ds["SLEV"][:].squeeze()
    qc = ds["SLEV_QC"][:].squeeze() if "SLEV_QC" in ds.variables else None
    epoch = np.datetime64("1950-01-01T00:00:00")
    dts = epoch + (t_days * 86400).astype("timedelta64[s]")
    mask = ~np.ma.getmaskarray(sl) if hasattr(sl, "mask") else np.ones(len(sl), bool)
    if qc is not None:
        if hasattr(qc, "mask"):
            mask &= ~qc.mask
        qcv = np.asarray(qc, dtype=int)
        mask &= (qcv == 1) | (qcv == 0)
    ds.close()
    return dts[mask], np.asarray(sl)[mask]


def harmonic_analysis(times: np.ndarray, levels: np.ndarray, lat: float):
    py_times = times.astype("M8[s]").astype("O")
    coef = utide.solve(
        py_times, levels,
        lat=lat,
        nodal=True,
        trend=False,
        method="ols",
        conf_int="linear",
        constit="auto",
        verbose=False,
    )
    pred = utide.reconstruct(py_times, coef, verbose=False)
    resid = levels - pred.h
    rms = float(np.sqrt(np.mean(resid ** 2)))
    var_total = float(np.var(levels))
    var_resid = float(np.var(resid))
    r2 = 1.0 - var_resid / var_total if var_total > 0 else 0.0
    cmap = {nm: (float(a), float(g)) for nm, a, g in zip(coef["name"], coef["A"], coef["g"])}
    constituents = []
    for cn in XTIDE_175:
        if cn in cmap:
            a, g = cmap[cn]
            constituents.append({"name": cn, "amp": a, "phase": g % 360.0})
        else:
            constituents.append({"name": cn, "amp": 0.0, "phase": 0.0, "missing": True})
    return {
        "mean": float(np.mean(levels)),
        "r2": r2,
        "rms": rms,
        "n_analyzed": int(len(coef["name"])),
        "constituents": constituents,
    }


def format_block(st: dict, res: dict, n_obs: int,
                 start: datetime, end: datetime) -> str:
    name_line = f"{st['name']}, {st['country']}"
    period = f"{start.strftime('%Y-%m-%d')}..{end.strftime('%Y-%m-%d')}"
    today = datetime.now().strftime("%Y%m%d")
    lines = [
        "# Harmonic constants derived from CMEMS in-situ sea level observations",
        f"# using UTide (v{utide.__version__}) with {n_obs} observations",
        f"# from {start.strftime('%Y-%m-%d')} to {end.strftime('%Y-%m-%d')}",
        f"# R^2 = {res['r2']:.4f}, RMS error = {res['rms']:.4f} m",
        f"# Constituents analyzed: {res['n_analyzed']}",
        "#",
        f"# {name_line}",
        "# BEGIN HOT COMMENTS",
        f"# country: {st['country']}",
        f"# water_body: {st['water']}",
        f"# source: Derived from CMEMS {st['network']} data with UTide harmonic analysis",
        f"# station_id_context: CMEMS-{st['cst']}",
        f"# date_imported: {today}",
        "# datum: Mean Sea Level",
        "# confidence: 6",
        f"# cmems_code: {st['cst']}",
        f"# network: {st['network']}",
        f"# utide: pts={n_obs} period={period} "
        f"r2={res['r2']:.4f} rms={res['rms']:.4f}m const={res['n_analyzed']}",
        "# !units: meters",
        f"# !longitude: {st['lon']:.4f}",
        f"# !latitude: {st['lat']:.4f}",
        name_line,
        "+00:00 :UTC",
        f"{res['mean']:.4f} meters",
    ]
    for c in res["constituents"]:
        if c.get("missing") or c["amp"] < 0.00005:
            lines.append("x 0 0")
        else:
            lines.append(f"{c['name']:15s} {c['amp']:.4f}  {c['phase']:.2f}")
    return "\n".join(lines)


def main():
    target = TARGET
    blocks: list[str] = []

    for idx, st in enumerate(STATIONS, 1):
        path = NC_DIR / st["file"]
        print(f"\n[{idx}/{len(STATIONS)}] {st['name']}  ({path.name})")
        if not path.exists():
            print("  FILE MISSING — skipping")
            continue
        times, levels = load_nc(path)
        first = times[0].astype("M8[s]").astype(datetime)
        last = times[-1].astype("M8[s]").astype(datetime)
        print(f"  loaded: {len(times)} samples  ({first} → {last})")
        if len(levels) < 720:
            print("  too few samples (<720, ~30 days)")
            continue
        print("  running UTide…", end=" ", flush=True)
        res = harmonic_analysis(times, levels, st["lat"])
        m2 = next((c["amp"] for c in res["constituents"] if c["name"] == "M2"), 0)
        m2g = next((c["phase"] for c in res["constituents"] if c["name"] == "M2"), 0)
        print(f"OK (R²={res['r2']:.4f}, RMS={res['rms']:.4f}m, "
              f"M2={m2*100:.2f}cm@{m2g:.2f}°, const={res['n_analyzed']})")
        blocks.append(format_block(st, res, len(times), first, last))

    if not blocks:
        print("\nNo blocks produced.")
        return

    raw = target.read_bytes().decode("iso-8859-1")
    if not raw.endswith("\n"):
        raw += "\n"
    raw += "\n".join(blocks) + "\n"
    target.write_bytes(raw.encode("iso-8859-1"))
    print(f"\nappended {len(blocks)} block(s) → {target}")


if __name__ == "__main__":
    main()
