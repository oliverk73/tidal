#!/usr/bin/env python3
"""Analyse the 6 additional Pegelonline ZIPs that just got copied to
water_levels/Germany/, generate XTide-format station blocks, and append
them to harmonics_utide_observations.txt.

Targets: Altengamme (Elbe), Dagebüll, Elsfleth (Weser), Farge (Weser),
Mellumplate (Jade), Vegesack (Weser). All six were missing from the
99-station Pegelonline-UTide pass; ZIPs were sourced via the
subscription-based WSV portal.

(Brake (Weser) ZIP not yet available — skipped.)
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from generate_germany_harmonics_175 import (   # noqa: E402
    parse_json_water_levels,
    harmonic_analysis_utide,
    format_station_block,
)

WATER_LEVELS = Path("/home/oliver/water_levels/Germany")
UTIDE_OBS    = Path("/home/oliver/harmonics/utide/harmonics_utide_observations.txt")

# (zip-stem prefix, station-name-without-country, lat, lon, water body)
TARGETS = [
    ("pegelonline-altengamme",   "Altengamme (Elbe)",   53.430842, 10.296788, "Elbe"),
    ("pegelonline-dagebll",      "Dagebüll",            54.732197,  8.688007, "Nordsee"),
    ("pegelonline-elsfleth",     "Elsfleth (Weser)",    53.265469,  8.482405, "Weser"),
    ("pegelonline-farge",        "Farge (Weser)",       53.206225,  8.511185, "Weser"),
    ("pegelonline-mellumplate",  "Mellumplate (Jade)",  53.773295,  8.093437, "Jade"),
    ("pegelonline-vegesack",     "Vegesack (Weser)",    53.170910,  8.620540, "Weser"),
]


def find_zip(prefix: str) -> Path:
    matches = sorted(WATER_LEVELS.glob(f"{prefix}-W-*.zip"))
    matches = [m for m in matches if not str(m).endswith(":Zone.Identifier")]
    if not matches:
        raise FileNotFoundError(f"No ZIP for prefix {prefix!r}")
    return matches[-1]


def main():
    blocks = []
    rejected = []
    for prefix, name, lat, lon, water in TARGETS:
        zp = find_zip(prefix)
        print(f"\n  → {name}  via {zp.name}")
        data = parse_json_water_levels(zp, sample_interval_minutes=60)
        if data is None:
            print(f"     FAILED (parse: insufficient data)")
            rejected.append((name, "parse"))
            continue
        results = harmonic_analysis_utide(data["datetimes_utc"], data["levels"], lat)
        if results is None:
            print(f"     FAILED (UTide error)")
            rejected.append((name, "utide"))
            continue
        m2 = next((c for c in results["constituents"] if c["name"] == "M2"), None)
        m2_amp = m2["amplitude"] if m2 else 0.0
        r2 = results['r_squared']
        print(f"     R²={r2:.3f}  M2={m2_amp:.3f} m  "
              f"n={data['n_obs']}  constit={results['n_analyzed']}")
        if r2 < 0:
            print(f"     ✗ REJECTED — R² < 0 (model worse than mean)")
            rejected.append((name, f"R²={r2:.2f}"))
            continue
        block = format_station_block(name, lat, lon, water, results, data)
        blocks.append((name, r2, block))

    print(f"\n{'='*60}")
    print(f"Accepted: {len(blocks)}, Rejected: {len(rejected)}")
    for nm, why in rejected:
        print(f"  ✗ {nm}: {why}")

    if not blocks:
        print("\nNo blocks produced. Aborting.")
        return

    raw = UTIDE_OBS.read_bytes().decode("iso-8859-1")
    if not raw.endswith("\n"):
        raw += "\n"
    appended = "\n".join(b for _, _, b in blocks) + "\n"
    UTIDE_OBS.write_bytes((raw + appended).encode("iso-8859-1"))
    print(f"\nAppended {len(blocks)} station block(s) to {UTIDE_OBS}")
    new_count = sum(1 for l in UTIDE_OBS.read_text(encoding="iso-8859-1").splitlines()
                    if "BEGIN HOT COMMENTS" in l)
    print(f"  New station count in UTide-obs: {new_count}")


if __name__ == "__main__":
    main()
