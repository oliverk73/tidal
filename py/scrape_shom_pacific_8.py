#!/usr/bin/env python3
"""Scrape SHOM Pacific stations missing from our data.

8 SHOM stations matched to TICON-4-only South Pacific stations:
  AVATORU_LAGON, MATAVAI, NOUMEA_CHALEIX, QUAI_DE_FARE,
  RIKITEA, ROCHERS_NOIRS, THIO, VAIRAO_OUTUTAATA

Same scrape window and block format as Pointe-Noire (2025-04-20 → 2026-04-14).
Output appended to harmonics_utide_tidetables.txt.
"""
import sys
import time
from datetime import datetime
from pathlib import Path

import requests
import utide

sys.path.insert(0, "/home/oliver/py")
import scrape_shom_nw_africa as base
from scrape_shom_nw_africa import (  # noqa: E402
    SHOM_WL_URL, HEADERS, CSV_DIR,
    save_csv, load_csv, harmonic_analysis, scrape_station,
)

base.START_DATE = datetime(2025, 4, 20)
base.BLOCK_DAYS = 60
base.NUM_BLOCKS = 6

# SHOM Pacific stations to pull, with country/water context for the block.
STATIONS = [
    {"cst": "AVATORU_LAGON",    "name": "Avatoru lagon",         "country": "French Polynesia",
     "water": "Pacific Ocean (French Polynesia)", "lat": -14.9500, "lon": -147.7000},
    {"cst": "MATAVAI",          "name": "Matavai",               "country": "French Polynesia",
     "water": "Pacific Ocean (French Polynesia)", "lat": -17.5167, "lon": -149.5167},
    {"cst": "NOUMEA_CHALEIX",   "name": "Nouméa - Chaleix",      "country": "New Caledonia",
     "water": "Pacific Ocean (New Caledonia)",    "lat": -22.2917, "lon":  166.4350},
    {"cst": "QUAI_DE_FARE",     "name": "Mouillage de Fare",     "country": "French Polynesia",
     "water": "Pacific Ocean (French Polynesia)", "lat": -16.7167, "lon": -151.0333},
    {"cst": "RIKITEA",          "name": "Rikitea",               "country": "French Polynesia",
     "water": "Pacific Ocean (French Polynesia)", "lat": -23.1167, "lon": -134.9667},
    {"cst": "ROCHERS_NOIRS",    "name": "Rochers Noirs - Tubuai", "country": "French Polynesia",
     "water": "Pacific Ocean (French Polynesia)", "lat": -23.3400, "lon": -149.4750},
    {"cst": "THIO",             "name": "Thio",                  "country": "New Caledonia",
     "water": "Pacific Ocean (New Caledonia)",    "lat": -21.6133, "lon":  166.2483},
    {"cst": "VAIRAO_OUTUTAATA", "name": "Vairao Oututaata",      "country": "French Polynesia",
     "water": "Pacific Ocean (French Polynesia)", "lat": -17.8083, "lon": -149.2940},
]


def format_block(st, res, n_obs, start, end):
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
    target = Path("/home/oliver/harmonics/utide/harmonics_utide_tidetables.txt")
    session = requests.Session()
    new_blocks = []

    for idx, st in enumerate(STATIONS, 1):
        print(f"\n[{idx}/{len(STATIONS)}] {st['cst']}  ({st['name']}, {st['country']})", flush=True)
        csv_path = CSV_DIR / f"{st['cst']}.csv"
        if csv_path.exists():
            times, levels = load_csv(st["cst"])
            print(f"  cached: {len(times)} samples", flush=True)
        else:
            try:
                times, levels = scrape_station(st["cst"], session)
            except Exception as e:
                print(f"  SCRAPE FAILED: {e}", flush=True); continue
            save_csv(st["cst"], times, levels)
            print(f"  scraped: {len(times)} samples", flush=True)
        if len(times) < 2000:
            print("  insufficient samples, skipping"); continue
        print("  running UTide…", end=" ", flush=True)
        res = harmonic_analysis(times, levels, st["lat"])
        if res is None:
            print("FAILED"); continue
        m2 = next((c["amp"] for c in res["constituents"] if c["name"] == "M2"), 0)
        print(f"OK (R²={res['r2']:.4f}, M2={m2:.3f}m, const={res['n_analyzed']})")
        new_blocks.append(format_block(st, res, len(times), times[0], times[-1]))

    if not new_blocks:
        print("\nNo blocks produced — nothing to append."); return

    raw = target.read_bytes().decode("iso-8859-1")
    if not raw.endswith("\n"):
        raw += "\n"
    raw += "\n".join(new_blocks) + "\n"
    target.write_bytes(raw.encode("iso-8859-1"))
    print(f"\nappended {len(new_blocks)} block(s) → {target}")


if __name__ == "__main__":
    main()
