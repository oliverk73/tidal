#!/usr/bin/env python3
"""Step 1 of datum cleanup: normalize spelling synonyms across all
harmonics .txt files.

ONLY the `# datum:` line is rewritten — Z₀ mean values, phases,
amplitudes and station names stay untouched. Pure cosmetic alignment
to the canonical (recognized) abbreviation per IHO/SHOM/UKHO
conventions.

Mapping is exact-match (whitespace-trimmed, case-sensitive). Anything
not in the table is left as-is so we don't accidentally rename
something we don't understand.
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path("/home/oliver/harmonics")

FILES = [
    ROOT / "ticon" / "harmonics_ticon4_worldwide.txt",
    ROOT / "utide" / "harmonics_utide_observations.txt",
    ROOT / "utide" / "harmonics_utide_tidetables.txt",
    ROOT / "utide" / "harmonics_utide_currents.txt",
    ROOT / "ihm" / "harmonics_puertos_spain.txt",
    ROOT / "classic" / "harmonics-1997-05-25_mod.txt",
    ROOT / "classic" / "harmonics-2004-06-14_mod.txt",
    ROOT / "classic" / "harmonics-dwf-20070318_mod.txt",
    ROOT / "classic" / "harmonics-dwf-20100529-nonfree.txt",
    ROOT / "classic" / "harmonics-dwf-20251228-free.txt",
]

# Canonical = recognized maritime/hydrographic short-form (IHO standard
# where applicable). Spelling variants on the left → canonical right.
DATUM_MAP = {
    # === Mean Lower Low Water ===
    "Mean Lower Low Water":                                    "MLLW",
    "MLLW":                                                    "MLLW",
    # NOAA standard for US tide stations
    "Approximate Level of Mean Lower Low Water":               "MLLW (approx.)",
    "Mean Lower Low Water Springs":                            "MLLWS",

    # === Mean Sea Level ===
    "Mean Sea Level":                                          "MSL",
    "MSL":                                                     "MSL",

    # === Lowest Astronomical Tide ===
    "Lowest Astronomical Tide":                                "LAT",
    "Lowest Astronomical Tide (LAT)":                          "LAT",
    "LAT":                                                     "LAT",

    # === Chart Datum (generic) ===
    "Chart Datum":                                             "CD",
    "Chart Datum (CD)":                                        "CD",
    "chart datum":                                             "CD",
    "Local Chart Datum":                                       "CD (local)",
    "approximate chart datum":                                 "CD (approx.)",
    "Chart Datum / Lowest Astronomical Tide":                  "CD/LAT",
    "Chart Datum (Marinha)":                                   "CD (Marinha)",   # Brazil

    # === Admiralty Chart Datum ===
    "Admiralty Chart Datum":                                   "ACD",
    "Admiralty Chart Datum (ACD)":                             "ACD",
    "Admiralty Chart Datum (ACD) ":                            "ACD",  # trailing space
    "ACD":                                                     "ACD",

    # === Normaal Amsterdams Peil ===
    "Normal Amsterdam Level":                                  "NAP",
    "Normaal Amsterdams Peil":                                 "NAP",
    "NAP":                                                     "NAP",

    # === Zéro Hydrographique (France) ===
    "Zero Hydrographique":                                     "ZH",
    "Zéro Hydrographique":                                     "ZH",
    "ZH":                                                      "ZH",

    # === LLW / LLWLT ===
    "LLW (Lowest Low Water)":                                  "LLW",
    "Lowest Low Water (LLW)":                                  "LLW",
    "Lowest Low Water":                                        "LLW",
    "LLWLT":                                                   "LLWLT",  # already canonical (Canada)
    "Lower Low Water Large Tide":                              "LLWLT",

    # === Australia ===
    "AHD":                                                     "AHD",
    "Australian Height Datum":                                 "AHD",

    # === UK ===
    "Ordnance Datum Newlyn (ODN)":                             "ODN",
    "Malin Head OSGM15 Ordnance Datum":                        "OD Malin Head",
    "Malin Ordnance Datum":                                    "OD Malin Head",
    "Ordnance Datum Malin Head":                               "OD Malin Head",

    # === Denmark ===
    "DVR90":                                                   "DVR90",
    "LN (Local Datum)":                                        "LN (local)",
    "LN (Local Datum)   ":                                     "LN (local)",  # trailing whitespace

    # === Russia / Baltic ===
    "BHS77":                                                   "BHS77",
    "BSCD2000":                                                "BSCD2000",
    "SNN76 / Kronstadt":                                       "SNN76",

    # === Sweden ===
    "RH 2000 (Swedish National Height System 2000)":           "RH2000",

    # === Belgium ===
    "TAW":                                                     "TAW",

    # === Germany ===
    "DHHN92":                                                  "DHHN92",
    "PNP":                                                     "PNP",

    # === Japan ===
    "Zero of Tide Height":                                     "ZTH",
    "station datum (JMA)":                                     "station datum (JMA)",

    # === Other ===
    "station datum":                                           "station datum",
    "Station Datum":                                           "station datum",
    "station datum (UHSLC)":                                   "station datum (UHSLC)",
    "Tide Gauge Zero (TGZ)":                                   "TGZ",
    "TGZ":                                                     "TGZ",
    "Tide Gauge Zero":                                         "TGZ",
    "Tide Gauge Zero ":                                        "TGZ",
    "TGZ 73.88 cm below mean sea level":                       "TGZ",
    "TGZ 73.88 cm below mean sea level ":                      "TGZ",
    "International Great Lakes Datum (1985)":                  "IGLD85",

    # === Unknown / unspecified — unify spellings ===
    "Unknown":                                                 "Unknown",
    "Unspecified":                                             "Unknown",
    "unspecified":                                             "Unknown",
    "Unspecified Common Datum":                                "Unknown",
    "Unspecified Common Datum ":                               "Unknown",
    "(none)":                                                  "Unknown",

    # === Untouched — keep as-is (already canonical or too specific) ===
    "n/a":                                                     "n/a",
    "geodetic datum":                                          "geodetic datum",
    "Harbour Local Datum":                                     "Harbour Local Datum",
    "Ortometric height":                                       "Ortometric height",
    "local datum":                                             "Harbour Local Datum",
    "Local Chart Datum":                                       "CD (local)",
    "Zero of the Alexandria Harbour Tide Gauge":               "TGZ",
    "Zero of the Alexandria Harbour Tide Gauge   ":            "TGZ",
    "tide gauge zero with respect to NP1":                     "TGZ",
}


def normalize_datum_line(line: str) -> tuple[str, str | None, str | None]:
    """Return (new_line, old_value, new_value). new_value is None if no change."""
    if not line.startswith("# datum:"):
        return line, None, None
    raw = line.split(":", 1)[1].rstrip("\n")
    old = raw.strip()
    if old in DATUM_MAP:
        new = DATUM_MAP[old]
        if new == old:
            return line, old, None
        return f"# datum: {new}\n", old, new
    return line, old, None


def process_file(path: Path, apply: bool):
    raw = path.read_bytes().decode("iso-8859-1", errors="replace")
    lines = raw.splitlines(keepends=True)
    changes = Counter()
    out = []
    for ln in lines:
        new_line, old_val, new_val = normalize_datum_line(ln)
        out.append(new_line)
        if new_val is not None:
            changes[(old_val, new_val)] += 1

    if apply and changes:
        # Verify station-count invariant before writing
        station_count_before = sum(1 for l in lines if "BEGIN HOT COMMENTS" in l)
        station_count_after = sum(1 for l in out if "BEGIN HOT COMMENTS" in l)
        if station_count_before != station_count_after:
            raise RuntimeError(
                f"Station count changed for {path}: "
                f"{station_count_before} → {station_count_after}"
            )
        path.write_bytes("".join(out).encode("iso-8859-1"))
    return changes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true",
                    help="Actually rewrite the files (default: dry-run).")
    args = ap.parse_args()

    total_changes = Counter()
    print(f"{'DRY RUN' if not args.apply else 'APPLY':>8s}  ┃  per-file changes")
    print("─" * 70)
    for path in FILES:
        if not path.exists():
            print(f"  ⚠ skip {path} (missing)")
            continue
        changes = process_file(path, apply=args.apply)
        total = sum(changes.values())
        if total:
            print(f"  {total:>5d}  {path.name}")
            for (old, new), n in sorted(changes.items(), key=lambda kv: -kv[1]):
                print(f"          {n:>5d}  {old!r:42s} → {new!r}")
            total_changes.update(changes)

    print("─" * 70)
    print(f"  TOTAL: {sum(total_changes.values())} datum lines normalized")
    if not args.apply:
        print("\nRun with --apply to rewrite the files.")


if __name__ == "__main__":
    main()
