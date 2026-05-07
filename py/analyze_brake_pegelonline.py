#!/usr/bin/env python3
"""Analyse the Brake (Weser) Pegelonline ZIP — last of the seven Tide-flux
gauges that needed UTide. Coords come from the Pegelonline REST API (the
authoritative source), NOT from TICON-4 metadata (TICON-4 carries an
~180 m offset for several German pegel — likely Bessel-vs-WGS84 datum
artefact)."""
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

TARGETS = [
    # (zip prefix, name, lat, lon, water) — all from Pegelonline API
    ("pegelonline-brake", "Brake (Weser)", 53.315979, 8.486546, "Weser"),
]


def find_zip(prefix: str) -> Path:
    matches = sorted(WATER_LEVELS.glob(f"{prefix}-W-*.zip"))
    matches = [m for m in matches if not str(m).endswith(":Zone.Identifier")]
    return matches[-1]


def main():
    blocks = []
    for prefix, name, lat, lon, water in TARGETS:
        zp = find_zip(prefix)
        print(f"  → {name}  via {zp.name}")
        data = parse_json_water_levels(zp, sample_interval_minutes=60)
        if data is None:
            print("     FAILED (parse)"); continue
        results = harmonic_analysis_utide(data["datetimes_utc"], data["levels"], lat)
        if results is None:
            print("     FAILED (utide)"); continue
        m2 = next((c for c in results["constituents"] if c["name"] == "M2"), None)
        m2_amp = m2["amplitude"] if m2 else 0.0
        print(f"     R²={results['r_squared']:.3f}  M2={m2_amp:.3f} m  n={data['n_obs']}")
        if results['r_squared'] < 0:
            print("     ✗ rejected"); continue
        block = format_station_block(name, lat, lon, water, results, data)
        blocks.append(block)

    if not blocks:
        return
    raw = UTIDE_OBS.read_bytes().decode("iso-8859-1")
    if not raw.endswith("\n"): raw += "\n"
    # Normalize datum label inline
    appended = ("\n".join(blocks) + "\n").replace("# datum: Mean Sea Level\n", "# datum: MSL\n")
    UTIDE_OBS.write_bytes((raw + appended).encode("iso-8859-1"))
    new_count = sum(1 for l in UTIDE_OBS.read_text(encoding="iso-8859-1").splitlines()
                    if "BEGIN HOT COMMENTS" in l)
    print(f"\nAppended {len(blocks)} block(s). UTide-obs count: {new_count}")


if __name__ == "__main__":
    main()
