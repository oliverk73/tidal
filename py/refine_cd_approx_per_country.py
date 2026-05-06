#!/usr/bin/env python3
"""Step 1b: replace 'CD (approx.)' with the country-specific official chart
datum, keeping the '(approx.)' suffix as Z₀-precision caveat.

Input distribution (922 stations, all in harmonics_utide_tidetables.txt):
  United Kingdom: 563 → 'ACD (approx.)'
  Canada:        149 → 'LLWLT (approx.)'
  Ireland:       109 → 'LAT (approx.)'
  South Korea:    77 → 'ALLW (approx.)'
  India:          24 → 'CD (approx.)'  (no national variant)

The country is read from the `# country:` line in each HOT COMMENTS block.
Stations of any other country with 'CD (approx.)' are left as-is and
flagged.

Z₀, phases, amplitudes and station names stay untouched. Pure label fix.
"""
from __future__ import annotations

import argparse
import re
from collections import Counter
from pathlib import Path

PATH = Path("/home/oliver/harmonics/utide/harmonics_utide_tidetables.txt")

COUNTRY_TO_DATUM = {
    "United Kingdom": "ACD (approx.)",
    "Canada":         "LLWLT (approx.)",
    "Ireland":        "LAT (approx.)",
    "South Korea":    "ALLW (approx.)",
    "India":          "CD (approx.)",   # kept (no national variant)
}


def process(apply: bool):
    raw = PATH.read_bytes().decode("iso-8859-1", errors="replace")
    lines = raw.splitlines(keepends=True)

    out = []
    block_start = None
    block_country = None
    block_datum_idx = None
    changes = Counter()
    unmapped = Counter()

    i = 0
    while i < len(lines):
        ln = lines[i]
        if ln.startswith("# BEGIN HOT COMMENTS"):
            block_start = i
            block_country = None
            block_datum_idx = None
        elif ln.startswith("# country:") and block_start is not None:
            block_country = ln.split(":", 1)[1].strip()
        elif ln.startswith("# datum: CD (approx.)") and block_start is not None:
            block_datum_idx = i
        # Station name line ends the HOT COMMENTS block
        if (block_start is not None
                and re.match(r"^[A-Z]", ln) and not ln.startswith("#")
                and i + 1 < len(lines)
                and re.match(r"^[+\-]\d{2}:\d{2}", lines[i+1])):
            # Resolve the datum-line replacement
            if block_datum_idx is not None and block_country:
                target = COUNTRY_TO_DATUM.get(block_country)
                if target and target != "CD (approx.)":
                    old = lines[block_datum_idx]
                    new = f"# datum: {target}\n"
                    if old != new:
                        lines[block_datum_idx] = new
                        changes[(block_country, target)] += 1
                elif not target:
                    unmapped[block_country] += 1
            block_start = None
            block_country = None
            block_datum_idx = None
        i += 1

    print(f"{'DRY RUN' if not apply else 'APPLY':>8s}")
    print("─" * 60)
    for (country, target), n in sorted(changes.items(), key=lambda kv: -kv[1]):
        print(f"  {n:>5d}  {country:20s} → {target}")
    print("─" * 60)
    print(f"  TOTAL: {sum(changes.values())} datum lines refined")
    if unmapped:
        print("\n  Unmapped (left as 'CD (approx.)'):")
        for c, n in unmapped.most_common():
            print(f"    {n:>5d}  {c}")

    if apply:
        # Verify station count is unchanged
        station_count = sum(1 for l in lines if "BEGIN HOT COMMENTS" in l)
        PATH.write_bytes("".join(lines).encode("iso-8859-1"))
        print(f"\n  Wrote {PATH} ({station_count} stations).")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    process(apply=args.apply)
