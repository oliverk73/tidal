#!/usr/bin/env python3
"""Scrape SHOM Pointe-Noire (Congo, RC), run UTide, append to tidetables.txt.

Single-station extension of scrape_shom_nw_africa.py for Pointe-Noire,
matching the existing block format used for SHOM-derived West Africa stations
(Cotonou, Lomé, Saint-Louis etc.) in harmonics_utide_tidetables.txt.
"""
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import requests

sys.path.insert(0, "/home/oliver/py")
from scrape_shom_nw_africa import (  # noqa: E402
    SHOM_WL_URL, HEADERS, CSV_DIR,
    save_csv, load_csv, harmonic_analysis, scrape_station,
)
import scrape_shom_nw_africa as base
import utide

# Match the existing SHOM West-Africa batch (1 year, ending early-2026)
base.START_DATE = datetime(2025, 4, 20)
base.BLOCK_DAYS = 60
base.NUM_BLOCKS = 6

STATION = {
    "cst": "POINTE_NOIRE",
    "name": "Pointe-Noire",
    "country": "Republic of the Congo",
    "water": "Atlantic Ocean (West Africa)",
    "lat": -4.7833,
    "lon": 11.8333,
}


def format_block_like_cotonou(st, res, n_obs, start, end):
    """Match the existing Cotonou/Lomé/Saint-Louis block format in tidetables.txt."""
    name_line = f"{st['name']}, {st['country']}"
    period = f"{start.strftime('%Y-%m-%d')}..{end.strftime('%Y-%m-%d')}"
    today = datetime.now().strftime("%Y%m%d")
    lines = [
        "# Harmonic constants derived from SHOM tide predictions",
        f"# using UTide (v{utide.__version__}) with {n_obs} observations",
        f"# from {start.strftime('%Y-%m-%d')} to {end.strftime('%Y-%m-%d')}",
        f"# R^2 = {res['r2']:.4f}, RMS error = {res['rms']:.4f} m",
        f"# Constituents analyzed: {res['n_analyzed']}",
        "#",
        f"# {name_line}",
        "# BEGIN HOT COMMENTS",
        f"# country: {st['country']}",
        f"# water_body: {st['water']}",
        "# source: Derived from SHOM tide predictions with UTide harmonic analysis",
        f"# station_id_context: SHOM-{st['cst']}",
        f"# date_imported: {today}",
        "# datum: Mean Sea Level",
        "# confidence: 6",
        f"# shom_code: {st['cst']}",
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
    csv_path = CSV_DIR / f"{STATION['cst']}.csv"
    if csv_path.exists():
        times, levels = load_csv(STATION["cst"])
        print(f"cached: {len(times)} samples")
    else:
        session = requests.Session()
        print(f"scraping {STATION['cst']}…")
        times, levels = scrape_station(STATION["cst"], session)
        save_csv(STATION["cst"], times, levels)
        print(f"  scraped: {len(times)} samples → {csv_path.name}")

    if len(times) < 2000:
        print("insufficient samples"); return

    print("running UTide…", end=" ", flush=True)
    res = harmonic_analysis(times, levels, STATION["lat"])
    if res is None:
        print("FAILED"); return
    m2 = next((c["amp"] for c in res["constituents"] if c["name"] == "M2"), 0)
    print(f"OK (R²={res['r2']:.4f}, M2={m2:.3f}m, constit={res['n_analyzed']})")

    block = format_block_like_cotonou(STATION, res, len(times), times[0], times[-1])

    # Append to harmonics_utide_tidetables.txt
    target = Path("/home/oliver/harmonics/utide/harmonics_utide_tidetables.txt")
    raw = target.read_bytes().decode("iso-8859-1")
    if not raw.endswith("\n"):
        raw += "\n"
    target.write_bytes((raw + block + "\n").encode("iso-8859-1"))
    print(f"\nappended → {target}")
    print(f"\nblock preview (first 25 lines):")
    for ln in block.splitlines()[:25]:
        print(f"  {ln}")


if __name__ == "__main__":
    main()
