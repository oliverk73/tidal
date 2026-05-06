#!/usr/bin/env python3
"""Parse FCUL hourly tide-height tables and run UTide harmonic analysis.

Source: https://webpages.ciencias.ulisboa.pt/~cmantunes/hidrografia/
Files: <Station>FCUL_AH.TXT (or Sesimbra_AH.TXT) — hourly heights for 2026,
referenced to ZH (Zero Hidrográfico, ZH = MSL_Cascais_1938 - 2.00m).
Times are UTC year-round (IH convention).

Output: appended blocks in harmonics_utide_tidetables.txt for the 4 IH
main ports without coverage so far: Aveiro, Figueira da Foz, Sesimbra,
Faro-Olhão.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import utide

FCUL_DIR = Path("/home/oliver/water_levels/Portugal_FCUL")
TARGET = Path("/home/oliver/harmonics/utide/harmonics_utide_tidetables.txt")

PT_MONTHS = {
    "JANEIRO": 1, "FEVEREIRO": 2, "MARÇO": 3, "ABRIL": 4,
    "MAIO": 5, "JUNHO": 6, "JULHO": 7, "AGOSTO": 8,
    "SETEMBRO": 9, "OUTUBRO": 10, "NOVEMBRO": 11, "DEZEMBRO": 12,
}

STATIONS_DONE = [
    # Already appended on 2026-05-06:
    {"file": "AveiroFCUL_AH.TXT",   "cst": "Aveiro",          "name": "Aveiro",
     "country": "Portugal", "lat": 40.6442, "lon": -8.7487,
     "water": "Atlantic Ocean (Iberian Peninsula)"},
    {"file": "FigueiraFCUL_AH.TXT", "cst": "FigueiraDaFoz",   "name": "Figueira da Foz",
     "country": "Portugal", "lat": 40.1500, "lon": -8.8666,
     "water": "Atlantic Ocean (Iberian Peninsula)"},
    {"file": "Sesimbra_AH.TXT",     "cst": "Sesimbra",        "name": "Sesimbra",
     "country": "Portugal", "lat": 38.4426, "lon": -9.1034,
     "water": "Atlantic Ocean (Iberian Peninsula)"},
    {"file": "FaroFCUL_AH.TXT",     "cst": "FaroOlhao",       "name": "Faro-Olhão",
     "country": "Portugal", "lat": 36.9833, "lon": -7.8667,
     "water": "Atlantic Ocean (Iberian Peninsula)"},
]

STATIONS = [
    {"file": "SetubalFCUL_AH.TXT",  "cst": "Setubal",         "name": "Setúbal",
     "country": "Portugal", "lat": 38.4962, "lon": -8.9015,
     "water": "Atlantic Ocean (Iberian Peninsula)"},
    {"file": "VilaRealFCUL_AH.TXT", "cst": "VilaRealStAntonio", "name": "Vila Real de Santo António",
     "country": "Portugal", "lat": 37.1833, "lon": -7.4167,
     "water": "Atlantic Ocean (Iberian Peninsula)"},
]

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


def parse_fcul(path: Path) -> tuple[np.ndarray, np.ndarray]:
    """Return (times[ndarray of datetime64], heights[ndarray of float meters])."""
    raw = path.read_bytes().decode("iso-8859-1")
    times: list[datetime] = []
    levels: list[float] = []

    cur_year: int | None = None
    cur_month: int | None = None
    in_table = False

    for line in raw.splitlines():
        s = line.strip()
        if not s:
            in_table = False
            continue
        if "ALTURAS" in s and "MAR" in s:
            # Header: "Tabela de ALTURAS HORÁRIAS DE MARÉ (m), <ST>  <MONTH>  de <YEAR>  ZH = ..."
            parts = s.split()
            cur_month = None
            month_idx = -1
            for i, tok in enumerate(parts):
                t = tok.strip(",").upper()
                if t in PT_MONTHS:
                    cur_month = PT_MONTHS[t]
                    month_idx = i
                    break
            cur_year = None
            for tok in parts[month_idx + 1:]:
                try:
                    y = int(tok)
                    if 1900 <= y <= 2100:
                        cur_year = y
                        break
                except ValueError:
                    continue
            in_table = False
            continue
        if s.startswith("HORAS"):
            continue
        if s.startswith("DIAS"):
            in_table = True
            continue
        if not in_table:
            continue
        # Data row: "  D   h00 h01 ... h23"
        toks = s.split()
        if len(toks) < 2:
            continue
        try:
            day = int(toks[0])
        except ValueError:
            continue
        if cur_year is None or cur_month is None:
            continue
        # 24 height values follow
        if len(toks) - 1 < 24:
            continue
        for hour, tok in enumerate(toks[1:25]):
            try:
                lvl = float(tok)
            except ValueError:
                continue
            try:
                t = datetime(cur_year, cur_month, day, hour)
            except ValueError:
                continue
            times.append(t)
            levels.append(lvl)

    return np.array(times, dtype="datetime64[s]"), np.asarray(levels, dtype=float)


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

    cmap = {nm: (float(a), float(g))
            for nm, a, g in zip(coef["name"], coef["A"], coef["g"])}

    constituents = []
    for cn in XTIDE_175:
        if cn in cmap:
            a, g = cmap[cn]
            constituents.append({"name": cn, "amp": a, "phase": g % 360.0})
        else:
            constituents.append({"name": cn, "amp": 0.0, "phase": 0.0,
                                 "missing": True})
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
        "# Harmonic constants derived from FCUL hourly tide predictions",
        f"# using UTide (v{utide.__version__}) with {n_obs} observations",
        f"# from {start.strftime('%Y-%m-%d')} to {end.strftime('%Y-%m-%d')}",
        f"# R^2 = {res['r2']:.4f}, RMS error = {res['rms']:.4f} m",
        f"# Constituents analyzed: {res['n_analyzed']}",
        "#",
        f"# {name_line}",
        "# BEGIN HOT COMMENTS",
        f"# country: {st['country']}",
        f"# water_body: {st['water']}",
        "# source: Derived from FCUL tide predictions with UTide harmonic analysis",
        f"# station_id_context: FCUL-{st['cst']}",
        f"# date_imported: {today}",
        "# datum: Mean Sea Level",
        "# confidence: 6",
        f"# fcul_code: {st['cst']}",
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
        path = FCUL_DIR / st["file"]
        print(f"\n[{idx}/{len(STATIONS)}] {st['name']}  ({path.name})")
        if not path.exists():
            print("  FILE MISSING — skipping")
            continue
        times, levels = parse_fcul(path)
        print(f"  parsed: {len(times)} samples  ({times[0]} → {times[-1]})")
        if len(levels) < 2000:
            print("  too few samples")
            continue
        print("  running UTide…", end=" ", flush=True)
        res = harmonic_analysis(times, levels, st["lat"])
        m2 = next((c["amp"] for c in res["constituents"] if c["name"] == "M2"), 0)
        m2g = next((c["phase"] for c in res["constituents"] if c["name"] == "M2"), 0)
        print(f"OK (R²={res['r2']:.4f}, RMS={res['rms']:.4f}m, "
              f"M2={m2:.3f}m@{m2g:.2f}°, const={res['n_analyzed']})")
        first = times[0].astype("M8[s]").astype(datetime)
        last = times[-1].astype("M8[s]").astype(datetime)
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
