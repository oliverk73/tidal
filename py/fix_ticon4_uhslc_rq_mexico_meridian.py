#!/usr/bin/env python3
"""Fix TICON-4 UHSLC_RQ Mexico stations: meridian +00:00 → -06:00.

The 17 Mexico stations under `Source: gesla4.UHSLC_RQ` were imported with
`+00:00` meridian, but their stored phases are in Mexico-CST (-06:00) local
convention — identical to the verified UNAM_HIST stored phases.

Cross-source check (e.g. Cedros):
  UHSLC_RQ:  stored M2 303.43°  meridian +00:00  → eff Greenwich 303.43°  ❌ (off by 180°)
  UNAM_HIST: stored M2 303.43°  meridian -06:00  → eff Greenwich 117.43°  ✓
  UTide:     stored M2 123.43°  meridian +00:00  → eff Greenwich 123.43°  ✓

Fix: set meridian to `-06:00` on the 17 UHSLC_RQ Mexico blocks.
Phases stay unchanged (they are already in Lokal-CST convention).
"""
from __future__ import annotations

import re
from pathlib import Path

PATH = Path("/home/oliver/harmonics/ticon/harmonics_ticon4_worldwide.txt")
SRC = "# Source: gesla4.UHSLC_RQ"
COUNTRY = "# country: Mexico"
OLD_MERIDIAN_PREFIX = "+00:00 "
NEW_MERIDIAN_PREFIX = "-06:00 "


def fix() -> int:
    raw = PATH.read_bytes().decode("iso-8859-1")
    lines = raw.split("\n")

    out = []
    i = 0
    n = len(lines)
    fixed = 0
    while i < n:
        line = lines[i]
        # Detect a UHSLC_RQ Mexico block — find the Source line, scan for Mexico country
        # within the next ~50 lines, then replace the meridian line.
        if line.strip() == SRC:
            # Look ahead for country and meridian line
            block_country = False
            j = i + 1
            while j < min(i + 60, n):
                if lines[j].strip() == COUNTRY:
                    block_country = True
                # Meridian line appears after the station name (capital letter, not '#')
                if re.match(r"^[+\-]\d{2}:\d{2}\s", lines[j]):
                    if block_country:
                        if lines[j].startswith(OLD_MERIDIAN_PREFIX):
                            lines[j] = NEW_MERIDIAN_PREFIX + lines[j][len(OLD_MERIDIAN_PREFIX):]
                            fixed += 1
                            print(f"  fixed line {j+1}: ...{lines[j-1][:60]}... → meridian -06:00")
                        else:
                            print(f"  WARN line {j+1}: meridian not +00:00 ({lines[j][:30]})")
                    break
                j += 1
        i += 1

    out_text = "\n".join(lines)
    PATH.write_bytes(out_text.encode("iso-8859-1"))
    return fixed


if __name__ == "__main__":
    n = fix()
    print(f"\nTotal fixed: {n}")
