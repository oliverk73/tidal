#!/usr/bin/env python3
"""Step 2 audit: list every station with `# datum: Unknown` in [CONTROLLED]
harmonics files, grouped by country and source.

Output: per-country breakdown (TSV-style) — file, country, station-count,
sample station names. Lets us decide which official datum to apply per
country.

Read-only — no file modifications.
"""
from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

ROOT = Path("/home/oliver/harmonics")

# [CONTROLLED] only — DWF-2025 (the only [EXTERNAL]) is excluded.
FILES = [
    (ROOT / "ticon" / "harmonics_ticon4_worldwide.txt", "TICON-4", "block"),
    (ROOT / "utide" / "harmonics_utide_observations.txt", "UTide observations", "block"),
    (ROOT / "utide" / "harmonics_utide_tidetables.txt", "UTide tidetables", "block"),
    (ROOT / "utide" / "harmonics_utide_currents.txt", "UTide currents", "block"),
    (ROOT / "ihm" / "harmonics_puertos_spain.txt", "IHM Puertos Spain", "fixed=Spain"),
    (ROOT / "classic" / "harmonics-1997-05-25_mod.txt", "Classic 1997", "name"),
    (ROOT / "classic" / "harmonics-2004-06-14_mod.txt", "Classic 2004", "name"),
    (ROOT / "classic" / "harmonics-dwf-20070318_mod.txt", "DWF 2007", "name"),
    (ROOT / "classic" / "harmonics-dwf-20100529-nonfree_mod.txt", "DWF 2010", "name"),
    (ROOT / "classic" / "harmonics-pierre-lavergne-v10_mod.txt", "Lavergne v10", "name"),
    (ROOT / "classic" / "harmonics-pierre-lavergne-v9-europe_mod.txt", "Lavergne v9", "name"),
]

US_STATES = {
    "Alabama","Alaska","Arizona","Arkansas","California","Colorado","Connecticut",
    "Delaware","Florida","Georgia","Hawaii","Idaho","Illinois","Indiana","Iowa",
    "Kansas","Kentucky","Louisiana","Maine","Maryland","Massachusetts","Michigan",
    "Minnesota","Mississippi","Missouri","Montana","Nebraska","Nevada",
    "New Hampshire","New Jersey","New Mexico","New York","North Carolina",
    "North Dakota","Ohio","Oklahoma","Oregon","Pennsylvania","Rhode Island",
    "South Carolina","South Dakota","Tennessee","Texas","Utah","Vermont",
    "Virginia","Washington","West Virginia","Wisconsin","Wyoming",
    "District of Columbia","Puerto Rico","U.S. Virgin Islands","Guam",
    "American Samoa","Northern Mariana Islands","Midway Islands","Wake Island",
}
CA_PROVINCES = {
    "Alberta","British Columbia","Manitoba","New Brunswick",
    "Newfoundland and Labrador","Newfoundland","Nova Scotia","Ontario",
    "Prince Edward Island","Quebec","Québec","Saskatchewan",
    "Northwest Territories","Nunavut","Yukon",
}


def country_from_name(name: str) -> str:
    if "," not in name:
        return "Unknown"
    last = name.rsplit(",", 1)[-1].strip().removesuffix(" Current").strip()
    if last in US_STATES:
        return "USA"
    if last in CA_PROVINCES:
        return "Canada"
    return last or "Unknown"


def parse_unknown(path: Path, label: str, country_mode: str):
    raw = path.read_bytes().decode("iso-8859-1", errors="replace")
    lines = raw.split("\n")
    fixed = country_mode.split("=", 1)[1] if country_mode.startswith("fixed=") else None

    block_country = None
    block_datum = None
    block_active = False

    for i, ln in enumerate(lines):
        if ln.startswith("# BEGIN HOT COMMENTS"):
            block_active = True
            block_country, block_datum = None, None
            continue
        if block_active:
            if ln.startswith("# country:"):
                block_country = ln.split(":", 1)[1].strip()
            elif ln.startswith("# datum:"):
                block_datum = ln.split(":", 1)[1].strip()
            if (re.match(r"^[A-Z]", ln) and not ln.startswith("#")
                    and i + 1 < len(lines)
                    and re.match(r"^[+\-]\d{2}:\d{2}", lines[i+1])):
                if fixed:
                    country = fixed
                elif country_mode == "block" and block_country:
                    country = block_country
                else:
                    country = country_from_name(ln)
                if (block_datum or "").lower() == "unknown":
                    yield country, ln.strip()
                block_active = False
        else:
            # No-HOT-COMMENTS files — datum is implicit "(none)" → not Unknown
            pass


def main():
    by_country = defaultdict(lambda: defaultdict(list))  # country → label → [names]
    grand_total = 0
    for path, label, mode in FILES:
        if not path.exists():
            print(f"  ⚠ skip (missing): {path}")
            continue
        n = 0
        for country, name in parse_unknown(path, label, mode):
            by_country[country][label].append(name)
            n += 1
        if n:
            print(f"  {label:25s} {n:4d} Unknown")
            grand_total += n

    print("\n" + "=" * 70)
    print(f"  Grand total: {grand_total} stations with datum=Unknown")
    print("=" * 70)

    # Per-country breakdown sorted by total stations desc
    rows = []
    for country, by_src in by_country.items():
        total = sum(len(v) for v in by_src.values())
        rows.append((country, total, by_src))
    rows.sort(key=lambda x: (-x[1], x[0]))

    print(f"\n{'Country':30s} {'#':>4s}  Sources (n) — first 3 stations")
    print("-" * 100)
    for country, total, by_src in rows:
        for src, names in sorted(by_src.items(), key=lambda kv: -len(kv[1])):
            sample = "; ".join(names[:3])
            if len(names) > 3:
                sample += f"; … (+{len(names)-3})"
            print(f"  {country:28s} {len(names):>4d}  {src:22s} {sample[:60]}")


if __name__ == "__main__":
    main()
