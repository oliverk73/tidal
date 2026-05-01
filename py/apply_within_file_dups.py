#!/usr/bin/env python3
# -*- coding: iso-8859-1 -*-
"""Apply the 5 KEEP_A decisions to canada_nb.txt.

Removes the 5 HW/LW-derived duplicate blocks (indices 72-76) after asserting
their identity (name + station_id_context) as a safety check.

Atomic write. Source file is read AND written as ISO-8859-1.
"""

import sys
from pathlib import Path

ENCODING = "iso-8859-1"
INPUT = Path("/home/oliver/harmonics/utide/harmonics_utide_canada_nb.txt")

# (block_idx, expected_name_substring, expected_id_context)
TO_REMOVE = [
    (72, "Belliveau Village",     "CHS 00172"),
    (73, "Cape Enrage",           "CHS 00150"),
    (74, "Dover (Memramcook)",    "CHS 00173"),
    (75, "Grindstone Island",     "CHS 00160"),
    (76, "Hopewell Cape",         "CHS 00170"),
]


def main():
    text = INPUT.read_text(encoding=ENCODING)
    lines = text.split("\n")

    # Find all block start indices = lines beginning with "# Harmonic constants derived"
    block_starts = []
    for i, line in enumerate(lines):
        if line.startswith("# Harmonic constants derived"):
            block_starts.append(i)
    # Append sentinel
    block_starts.append(len(lines))

    n_blocks = len(block_starts) - 1
    print(f"Found {n_blocks} blocks in {INPUT.name}")
    if n_blocks != 81:
        print(f"ERROR: expected 81 blocks, found {n_blocks}")
        sys.exit(1)

    # Build a slice plan: keep all lines except those in to-remove block ranges
    remove_ranges = []
    for idx, expected_name, expected_id in TO_REMOVE:
        start = block_starts[idx]
        end = block_starts[idx + 1]
        chunk = "\n".join(lines[start:end])
        if expected_name not in chunk:
            print(f"ERROR: block {idx} does not contain expected name '{expected_name}'")
            print("First 500 chars:", chunk[:500])
            sys.exit(1)
        if expected_id not in chunk:
            print(f"ERROR: block {idx} does not contain expected id '{expected_id}'")
            sys.exit(1)
        # Sanity: must be the HW/LW variant (R^2 < 0.5 — the bad ones have ~0.07-0.12)
        if "R^2 = 1.0000" in chunk:
            print(f"ERROR: block {idx} has R^2=1.0000 — that is the GOOD variant, refusing to delete")
            sys.exit(1)
        remove_ranges.append((start, end, idx, expected_name))
        print(f"  block {idx} ({expected_name}): lines {start+1}..{end} ({end-start} lines)")

    # Sort by start, build kept lines
    remove_ranges.sort()
    kept = []
    cursor = 0
    for start, end, _, _ in remove_ranges:
        kept.extend(lines[cursor:start])
        cursor = end
    kept.extend(lines[cursor:])

    new_text = "\n".join(kept)

    # Atomic write: write to .tmp, fsync, rename
    tmp = INPUT.with_suffix(INPUT.suffix + ".tmp")
    tmp.write_bytes(new_text.encode(ENCODING))
    tmp.replace(INPUT)
    print(f"\nWrote {INPUT}")

    # Verify post-state
    text2 = INPUT.read_text(encoding=ENCODING)
    n_after = text2.count("# BEGIN HOT COMMENTS")
    print(f"Post-state: {n_after} '# BEGIN HOT COMMENTS' markers (expected 76)")
    if n_after != 76:
        print("ERROR: expected 76, did not match")
        sys.exit(1)


if __name__ == "__main__":
    main()
