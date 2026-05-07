#!/usr/bin/env python3
"""Analyse the 4 Pegelonline ZIPs that were never folded into the
UTide-obs corpus, generate XTide-format station blocks, and append them
to harmonics_utide_observations.txt.

Targets: Bremervörde UW (Oste), Ritterhude (Hamme), Wasserhorst (Lesum),
Wehr Geesthacht UP (Elbe). All four have ZIPs in water_levels/Germany/
but were not part of the original 99-station Pegelonline-UTide pass.

Reuses parse_json_water_levels / harmonic_analysis_utide /
format_station_block from generate_germany_harmonics_175.py — same
99-other-station convention (datum: Mean Sea Level → normalised to MSL,
175-constituent format).

Read-only on the source files; writes the new blocks at the end of
harmonics_utide_observations.txt.
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
# Coords copied from TICON-4 metadata for these stations.
TARGETS = [
    ("pegelonline-bremervrdeuw",     "Bremervörde UW (Oste)",       53.485666,  9.155876, "Oste"),
    ("pegelonline-ritterhude",       "Ritterhude (Hamme)",          53.183440,  8.764377, "Hamme"),
    ("pegelonline-wasserhorst",      "Wasserhorst (Lesum)",         53.164336,  8.719232, "Lesum"),
    ("pegelonline-wehrgeesthachtup", "Wehr Geesthacht UP (Elbe)",   53.424819, 10.336041, "Elbe"),
]


def find_zip(prefix: str) -> Path:
    matches = sorted(WATER_LEVELS.glob(f"{prefix}-W-*.zip"))
    matches = [m for m in matches if not str(m).endswith(":Zone.Identifier")]
    if not matches:
        raise FileNotFoundError(f"No ZIP for prefix {prefix!r}")
    return matches[-1]   # most recent


def main():
    blocks = []
    for prefix, name, lat, lon, water in TARGETS:
        zp = find_zip(prefix)
        print(f"  → {name}  via {zp.name}")
        data = parse_json_water_levels(zp, sample_interval_minutes=60)
        if data is None:
            print(f"     FAILED (parse: insufficient data)")
            continue
        results = harmonic_analysis_utide(data["datetimes_utc"], data["levels"], lat)
        if results is None:
            print(f"     FAILED (UTide error)")
            continue
        m2 = next((c for c in results["constituents"] if c["name"] == "M2"), None)
        m2_amp = m2["amplitude"] if m2 else 0.0
        print(f"     R²={results['r_squared']:.3f}  M2={m2_amp:.3f} m  "
              f"n={data['n_obs']}  constit={results['n_analyzed']}")
        block = format_station_block(name, lat, lon, water, results, data)
        blocks.append(block)

    if not blocks:
        print("No blocks produced. Aborting.")
        return

    raw = UTIDE_OBS.read_bytes().decode("iso-8859-1")
    if not raw.endswith("\n"):
        raw += "\n"
    appended = "\n".join(blocks) + "\n"
    UTIDE_OBS.write_bytes((raw + appended).encode("iso-8859-1"))
    print(f"\nAppended {len(blocks)} station block(s) to {UTIDE_OBS}")
    # Sanity check
    new_count = sum(1 for l in UTIDE_OBS.read_text(encoding="iso-8859-1").splitlines()
                    if "BEGIN HOT COMMENTS" in l)
    print(f"  New station count in UTide-obs: {new_count}")


if __name__ == "__main__":
    main()
