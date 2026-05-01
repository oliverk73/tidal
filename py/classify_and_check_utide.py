#!/usr/bin/env python3
# -*- coding: iso-8859-1 -*-
"""Phase 3 prep: classify each station as observations / tidetables / currents,
and run pre-merge checks (constituent lists, header boilerplate, year coverage).

Reads:  /home/oliver/harmonics/utide/*.txt
Writes: /home/oliver/harmonics/help/phase3/{classification.csv, prechecks.txt}
"""

import re
import sys
import csv
import json
from pathlib import Path
from collections import Counter, defaultdict

ENCODING = "iso-8859-1"
UTIDE_DIR = Path("/home/oliver/harmonics/utide")
OUT = Path("/home/oliver/harmonics/help/phase3")

# Currents indicators
RE_CURRENT = re.compile(
    r"current|adcp|velocity|tidal\s*stream|imos|saeon", re.IGNORECASE
)
# Tidetables indicators (reverse-engineered predictions)
RE_TIDETABLE = re.compile(
    r"prediction|tide\s*table|hw\s*/?\s*lw|reverse[-\s]*engineer|"
    r"tidetimes\.co\.uk|namria|tides\.gc\.ca|royal\s*thai\s*navy",
    re.IGNORECASE,
)


def classify(source: str, filename: str) -> str:
    if "_currents" in filename or RE_CURRENT.search(source or ""):
        return "currents"
    if RE_TIDETABLE.search(source or ""):
        return "tidetables"
    return "observations"


def parse_blocks(text: str):
    """Return list of dicts: {hot_start, hot_end, body_start, body_end, name, source, ...}"""
    lines = text.split("\n")
    blocks = []
    n = len(lines)
    i = 0
    while i < n:
        if lines[i].strip() == "# BEGIN HOT COMMENTS":
            hot_start = i
            kv = {}
            j = i + 1
            while j < n and lines[j].startswith("#"):
                m = re.match(r"#\s*([A-Za-z_!][A-Za-z0-9_!\s]*?)\s*:\s*(.*)$", lines[j])
                if m:
                    k = m.group(1).strip().lower().replace(" ", "_")
                    v = m.group(2).strip()
                    kv[k] = v
                j += 1
            # station name line
            k_idx = j
            while k_idx < n and (lines[k_idx].strip() == "" or lines[k_idx].startswith("#")):
                k_idx += 1
            name = lines[k_idx].strip() if k_idx < n else ""
            blocks.append({
                "hot_start": hot_start,
                "hot_end": j,
                "name_idx": k_idx,
                "kv": kv,
                "name": name,
            })
            i = j
        else:
            i += 1
    return lines, blocks


def parse_header_constituents(lines):
    """Find the constituent list at the top of the file: lines after
    '# Constituent speeds' until the blank/'#' transition."""
    # find '# Number of constituents'
    n = len(lines)
    i = 0
    while i < n and not lines[i].startswith("# Number of constituents"):
        i += 1
    if i >= n:
        return []
    # next non-comment line is the count
    j = i + 1
    while j < n and lines[j].startswith("#"):
        j += 1
    # then count
    if j < n and lines[j].strip().isdigit():
        count = int(lines[j].strip())
        j += 1
    else:
        return []
    # skip "# Constituent speeds" header lines
    while j < n and lines[j].startswith("#"):
        j += 1
    # collect constituents
    out = []
    while j < n:
        line = lines[j].strip()
        if line == "" or line.startswith("#"):
            break
        parts = line.split()
        if len(parts) >= 2:
            out.append(parts[0])
        j += 1
    return out


def parse_equilibrium_year_range(lines):
    """Find '# Equilibrium arguments' or similar, return year range covered."""
    # The structure: after constituents, there are tables for equilibrium and node factors
    # marked by '# Equilibrium arguments' / '# Node factors'.  Each table has a line
    # giving start year + count.
    n = len(lines)
    years = []
    for idx, line in enumerate(lines):
        if line.startswith("*Equilibrium") or line.startswith("# Equilibrium arguments"):
            # next data line: start_year num_years
            for k in range(idx + 1, min(idx + 6, n)):
                m = re.match(r"\s*(\d{4})\s+(\d+)\s*$", lines[k])
                if m:
                    years.append((int(m.group(1)), int(m.group(2))))
                    break
    return years


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    files = sorted(UTIDE_DIR.glob("*.txt"))

    classification_rows = []
    files_by_class = Counter()
    stations_by_class = Counter()
    sources_by_class = defaultdict(Counter)

    constituent_signatures = {}  # filename -> tuple of constituent symbols
    header_first_lines = {}      # filename -> first 30 lines (joined)
    eq_years = {}                # filename -> [(start_year, n)]

    for path in files:
        text = path.read_text(encoding=ENCODING)
        lines = text.split("\n")
        constituents = parse_header_constituents(lines)
        constituent_signatures[path.name] = tuple(constituents)
        header_first_lines[path.name] = "\n".join(lines[:30])
        eq_years[path.name] = parse_equilibrium_year_range(lines)

        _, blocks = parse_blocks(text)
        file_classes = Counter()
        for blk in blocks:
            cls = classify(blk["kv"].get("source", ""), path.name)
            file_classes[cls] += 1
            stations_by_class[cls] += 1
            sources_by_class[cls][blk["kv"].get("source", "")] += 1
            classification_rows.append({
                "file": path.name,
                "name": blk["name"],
                "source": blk["kv"].get("source", ""),
                "class": cls,
            })
        files_by_class[max(file_classes, key=file_classes.get) if file_classes else "empty"] += 1
        print(f"  {path.name:55s}  {dict(file_classes)}")

    print()
    print(f"Total stations: {sum(stations_by_class.values())}")
    for cls, n in stations_by_class.most_common():
        print(f"  {cls:12s} {n:5d}")
    print()
    print("Files by majority class:")
    for cls, n in files_by_class.most_common():
        print(f"  {cls:12s} {n}")

    # ----- pre-checks: constituent signature variants
    sig_groups = defaultdict(list)
    for name, sig in constituent_signatures.items():
        sig_groups[sig].append(name)

    print()
    print(f"\n=== Pre-check: constituent list variants ===")
    print(f"Distinct constituent signatures across {len(constituent_signatures)} files: {len(sig_groups)}")
    for i, (sig, names) in enumerate(sorted(sig_groups.items(), key=lambda x: -len(x[1]))):
        print(f"  group {i+1}: {len(sig)} constituents, {len(names)} files")
        if i < 6:
            print(f"    first 6 constituents: {sig[:6] if sig else '(none)'}")
            print(f"    files: {names[:3]}{'...' if len(names) > 3 else ''}")

    # union of all constituents (master list)
    union = set()
    for sig in constituent_signatures.values():
        union.update(sig)
    print(f"\n  union (master list): {len(union)} unique constituent symbols")

    # ----- pre-check: equilibrium year ranges
    print(f"\n=== Pre-check: equilibrium year coverage ===")
    yr_summary = Counter()
    for f, ys in eq_years.items():
        if ys:
            start = ys[0][0]
            n = ys[0][1]
            yr_summary[(start, n)] += 1
        else:
            yr_summary[("none",)] += 1
    for (k), n in yr_summary.most_common():
        print(f"  {k}: {n} files")

    # ----- pre-check: header boilerplate consistency (first 30 lines)
    hdr_groups = defaultdict(list)
    for name, hdr in header_first_lines.items():
        hdr_groups[hdr].append(name)
    print(f"\n=== Pre-check: header boilerplate variants ===")
    print(f"Distinct first-30-line headers: {len(hdr_groups)}")
    for i, (hdr, names) in enumerate(sorted(hdr_groups.items(), key=lambda x: -len(x[1]))):
        if i < 5:
            print(f"  group {i+1}: {len(names)} files. Example: {names[0]}")

    # ----- write outputs
    with (OUT / "classification.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["file", "name", "class", "source"])
        w.writeheader()
        w.writerows(classification_rows)

    with (OUT / "prechecks.json").open("w", encoding="utf-8") as f:
        json.dump({
            "stations_by_class": dict(stations_by_class),
            "files_by_majority_class": dict(files_by_class),
            "constituent_signature_groups": [
                {"size": len(sig), "files": names}
                for sig, names in sorted(sig_groups.items(), key=lambda x: -len(x[1]))
            ],
            "equilibrium_year_distribution": {
                str(k): n for k, n in yr_summary.most_common()
            },
            "header_groups_count": len(hdr_groups),
            "master_constituent_count": len(union),
        }, f, indent=2)

    print(f"\nWrote {OUT}/classification.csv")
    print(f"Wrote {OUT}/prechecks.json")


if __name__ == "__main__":
    main()
