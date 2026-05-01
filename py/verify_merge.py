#!/usr/bin/env python3
# -*- coding: iso-8859-1 -*-
"""Verify Phase 3 merge: each station's 178 body lines (name + tz + z0 +
175 constituents) must be byte-identical between source file and merged file.

Reads:  /home/oliver/harmonics/utide/harmonics_utide_*.txt (97 source + 3 merged)
Reports: any station where body bytes differ.
"""

import re
from pathlib import Path
from collections import defaultdict

ENCODING = "iso-8859-1"
UTIDE_DIR = Path("/home/oliver/harmonics/utide")
MERGE_FILES = {
    "observations": UTIDE_DIR / "harmonics_utide_observations.txt",
    "tidetables":   UTIDE_DIR / "harmonics_utide_tidetables.txt",
    "currents":     UTIDE_DIR / "harmonics_utide_currents.txt",
}


def parse_stations(path: Path):
    """Return {station_name: 178-line body tuple}.
    Body = first non-comment line after BEGIN HOT COMMENTS, plus next 177 lines.
    Handles multiple stations with the same name by suffixing :idx (rare)."""
    text = path.read_text(encoding=ENCODING)
    lines = text.split("\n")
    n = len(lines)
    stations = {}
    name_seen = defaultdict(int)
    i = 0
    while i < n:
        if lines[i].strip() == "# BEGIN HOT COMMENTS":
            j = i + 1
            while j < n and lines[j].startswith("#"):
                j += 1
            # skip any blank/comment lines between HOT and body
            while j < n and (lines[j].strip() == "" or lines[j].startswith("#")):
                j += 1
            body = tuple(lines[j:j + 178])
            if len(body) < 178:
                i = j
                continue
            name = body[0].strip()
            count = name_seen[name]
            name_seen[name] += 1
            key = name if count == 0 else f"{name}::{count}"
            # also key by source file for cross-checks
            stations[key] = body
            i = j + 178
        else:
            i += 1
    return stations


def main():
    # parse all source files (excluding the 3 merge files themselves)
    src_stations = {}  # station_name -> body
    src_origin = {}    # station_name -> filename
    for path in sorted(UTIDE_DIR.glob("*.txt")):
        if path.name in ("harmonics_utide_observations.txt",
                         "harmonics_utide_tidetables.txt",
                         "harmonics_utide_currents.txt"):
            continue
        s = parse_stations(path)
        for name, body in s.items():
            if name in src_stations:
                # duplicate station name across files; key with file too
                key = f"{name}@@{path.name}"
            else:
                key = name
            src_stations[key] = body
            src_origin[key] = path.name

    print(f"Source stations parsed: {len(src_stations)}")

    merged_stations = {}
    for cls, mp in MERGE_FILES.items():
        s = parse_stations(mp)
        for name, body in s.items():
            if name in merged_stations:
                key = f"{name}@@{cls}"
            else:
                key = name
            merged_stations[key] = (cls, body)

    print(f"Merged stations parsed: {len(merged_stations)}")
    print()

    # Compare: for each merged station, find its source body.
    matched = 0
    name_only_ok = 0
    body_diff = 0
    not_found = 0
    diff_examples = []

    for mkey, (cls, mbody) in merged_stations.items():
        plain_name = mkey.split("@@")[0].split("::")[0]
        # find any source body that matches
        candidates = []
        for skey, sbody in src_stations.items():
            if skey == mkey or skey.startswith(plain_name):
                candidates.append((skey, sbody))
        # exact body match?
        body_match = None
        for skey, sbody in candidates:
            if sbody == mbody:
                body_match = skey
                break
        if body_match:
            matched += 1
            continue
        # Name match only (body differs)
        if candidates:
            body_diff += 1
            if len(diff_examples) < 5:
                # find first differing line
                sbody = candidates[0][1]
                first_diff = None
                for k in range(min(len(sbody), len(mbody))):
                    if sbody[k] != mbody[k]:
                        first_diff = k
                        break
                diff_examples.append({
                    "station": mkey,
                    "src_file": src_origin.get(candidates[0][0], "?"),
                    "first_diff_line": first_diff,
                    "src": sbody[first_diff] if first_diff is not None else "(end)",
                    "merged": mbody[first_diff] if first_diff is not None else "(end)",
                })
        else:
            not_found += 1

    print(f"Body byte-identical:   {matched:5d}")
    print(f"Name match, body diff: {body_diff:5d}")
    print(f"Not found in source:   {not_found:5d}")
    print()
    if diff_examples:
        print("First 5 body diffs:")
        for d in diff_examples:
            print(f"  station: {d['station']!r}  src_file={d['src_file']}  line {d['first_diff_line']}")
            print(f"    src   : {d['src']!r}")
            print(f"    merged: {d['merged']!r}")


if __name__ == "__main__":
    main()
