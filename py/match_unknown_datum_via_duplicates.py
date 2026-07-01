#!/usr/bin/env python3
"""Step 2 — phase 1: For every station with `# datum: Unknown` find a
duplicate (similar name OR very close coordinates) in another harmonics
file that has a *known* datum, and propose to copy that datum + Z₀ over.

Workflow:
  1. Index all stations across all sources with (name, country, lat, lon,
     datum, z0, z0_unit, file_path, line_in_file).
  2. For each Unknown-datum station, find donor candidates:
       - distance < 0.5 km                             → strong match
       - distance < 5 km AND name-Jaccard > 0.5        → likely match
       - exact normalized name match (same country)    → name match
       - distance < 10 km AND name-Jaccard > 0.7       → weak match
  3. Output a TSV report. Apply step is in a separate script.

Read-only — no file modifications here.
"""
from __future__ import annotations

import argparse
import math
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

ROOT = Path("/home/oliver/harmonics")

FILES = [
    (ROOT / "ticon" / "harmonics_ticon4_worldwide.txt",                  "TICON-4",            "block"),
    (ROOT / "utide" / "harmonics_utide_observations.txt",                "UTide-obs",          "block"),
    (ROOT / "utide" / "harmonics_utide_tidetables.txt",                  "UTide-tt",           "block"),
    (ROOT / "utide" / "harmonics_utide_currents.txt",                    "UTide-cur",          "block"),
    (ROOT / "classic"   / "harmonics_puertos_spain.txt",                     "IHM-Spain",          "fixed=Spain"),
    (ROOT / "classic" / "harmonics-1997-05-25_mod.txt",                  "Classic-1997",       "name"),
    (ROOT / "classic" / "harmonics-2004-06-14_mod.txt",                  "Classic-2004",       "name"),
    (ROOT / "classic" / "harmonics-dwf-20070318_mod.txt",                "DWF-2007",           "name"),
    (ROOT / "classic" / "harmonics-dwf-20100529-nonfree_mod.txt",        "DWF-2010",           "name"),
    (ROOT / "classic" / "harmonics-dwf-20251228-free.txt",               "DWF-2025",           "fixed=USA"),
    (ROOT / "classic" / "harmonics-pierre-lavergne-v10_mod.txt",         "Lavergne-v10",       "name"),
    (ROOT / "classic" / "harmonics-pierre-lavergne-v9-europe_mod.txt",   "Lavergne-v9",        "name"),
    # Originals (donor-only): big pool of pre-dedupe stations.
    (ROOT / "classic_original" / "harmonics-1997-05-25.txt",             "Classic-1997-orig",  "name"),
    (ROOT / "classic_original" / "harmonics-2004-06-14.txt",             "Classic-2004-orig",  "name"),
    (ROOT / "classic_original" / "harmonics-dwf-20070318.txt",           "DWF-2007-orig",      "name"),
    (ROOT / "classic_original" / "harmonics-dwf-20100529-nonfree.txt",   "DWF-2010-orig",      "name"),
]

US_STATES = {
    "Alabama","Alaska","Arizona","Arkansas","California","Colorado","Connecticut","Delaware",
    "Florida","Georgia","Hawaii","Idaho","Illinois","Indiana","Iowa","Kansas","Kentucky",
    "Louisiana","Maine","Maryland","Massachusetts","Michigan","Minnesota","Mississippi",
    "Missouri","Montana","Nebraska","Nevada","New Hampshire","New Jersey","New Mexico",
    "New York","North Carolina","North Dakota","Ohio","Oklahoma","Oregon","Pennsylvania",
    "Rhode Island","South Carolina","South Dakota","Tennessee","Texas","Utah","Vermont",
    "Virginia","Washington","West Virginia","Wisconsin","Wyoming","District of Columbia",
    "Puerto Rico","U.S. Virgin Islands","Guam","American Samoa","Northern Mariana Islands",
    "Midway Islands","Wake Island",
}
CA_PROVINCES = {
    "Alberta","British Columbia","Manitoba","New Brunswick","Newfoundland and Labrador",
    "Newfoundland","Nova Scotia","Ontario","Prince Edward Island","Quebec","Québec",
    "Saskatchewan","Northwest Territories","Nunavut","Yukon",
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


@dataclass
class Station:
    name: str
    country: str
    lat: float | None
    lon: float | None
    datum: str
    z0: float
    z0_unit: str          # "meters" or "feet"
    source_label: str
    file_path: str
    line_no: int          # 1-based line number where station name appears


def parse_file(path: Path, source_label: str, country_mode: str) -> list[Station]:
    raw = path.read_bytes().decode("iso-8859-1", errors="replace")
    lines = raw.split("\n")
    fixed = country_mode.split("=", 1)[1] if country_mode.startswith("fixed=") else None

    stations: list[Station] = []
    block_meta: dict = {}
    in_block = False

    for i, ln in enumerate(lines):
        if ln.startswith("# BEGIN HOT COMMENTS"):
            in_block = True
            block_meta = {}
            continue
        if in_block:
            if ln.startswith("# country:"):
                block_meta["country"] = ln.split(":", 1)[1].strip()
            elif ln.startswith("# datum:"):
                block_meta["datum"] = ln.split(":", 1)[1].strip()
            elif ln.startswith("# !latitude:"):
                try:
                    block_meta["lat"] = float(ln.split(":", 1)[1].strip())
                except ValueError:
                    pass
            elif ln.startswith("# !longitude:"):
                try:
                    block_meta["lon"] = float(ln.split(":", 1)[1].strip())
                except ValueError:
                    pass
            # Station-name line ends the HOT-COMMENTS block.
            if (re.match(r"^[A-Za-zÀ-ÿ]", ln) and not ln.startswith("#")
                    and i + 2 < len(lines)
                    and re.match(r"^[+\-]?\d{1,2}:\d{2}", lines[i+1])):
                tz_line = lines[i+1]
                z0_line = lines[i+2]
                m = re.match(r"\s*([+-]?\d+(?:\.\d+)?)\s+(meters|feet)", z0_line)
                if not m:
                    in_block = False
                    block_meta = {}
                    continue
                z0 = float(m.group(1))
                z0_unit = m.group(2)
                if fixed:
                    country = fixed
                elif country_mode == "block" and block_meta.get("country"):
                    country = block_meta["country"]
                else:
                    country = country_from_name(ln)
                stations.append(Station(
                    name=ln.strip(),
                    country=country.strip() or "Unknown",
                    lat=block_meta.get("lat"),
                    lon=block_meta.get("lon"),
                    datum=block_meta.get("datum") or "(none)",
                    z0=z0,
                    z0_unit=z0_unit,
                    source_label=source_label,
                    file_path=str(path),
                    line_no=i + 1,
                ))
                in_block = False
                block_meta = {}
    return stations


def normalize_name(name: str) -> str:
    # Drop ", Country" suffix and ", Region, Country" — keep base toponym.
    base = name.split(",")[0]
    base = re.sub(r"\([^)]*\)", " ", base)             # drop parenthesised parts
    base = re.sub(r"[^\w\s]", " ", base, flags=re.UNICODE)
    base = re.sub(r"\s+", " ", base).strip().lower()
    return base


def name_tokens(name: str) -> set[str]:
    return set(normalize_name(name).split())


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp/2)**2 + math.cos(p1) * math.cos(p2) * math.sin(dl/2)**2
    return 2 * R * math.asin(math.sqrt(a))


def to_meters(z0: float, unit: str) -> float:
    return z0 * 0.3048 if unit == "feet" else z0


def find_matches(unk: Station, donors: list[Station]) -> list[tuple[Station, str, float, float]]:
    """Return list of (donor, kind, distance_km_or_-1, name_jaccard) sorted best-first."""
    out = []
    unk_tokens = name_tokens(unk.name)
    for d in donors:
        # cheap country filter (skip across-country false matches except islands/territories)
        if unk.country != d.country and unk.country != "Unknown" and d.country != "Unknown":
            # Allow when name matches strongly across countries (e.g. UK islands listed under England)
            if jaccard(unk_tokens, name_tokens(d.name)) < 0.75:
                continue
        # name match
        nj = jaccard(unk_tokens, name_tokens(d.name))
        # distance match
        if unk.lat is not None and unk.lon is not None and d.lat is not None and d.lon is not None:
            dist = haversine_km(unk.lat, unk.lon, d.lat, d.lon)
        else:
            dist = -1.0   # unknown distance

        kind = None
        if dist >= 0 and dist < 0.5:
            kind = "STRONG_DIST"
        elif dist >= 0 and dist < 5.0 and nj >= 0.5:
            kind = "LIKELY_DIST_NAME"
        elif nj >= 0.95 and unk.country == d.country:
            kind = "EXACT_NAME"
        elif dist >= 0 and dist < 10.0 and nj >= 0.7:
            kind = "WEAK_DIST_NAME"
        elif nj >= 0.7 and dist < 0:
            kind = "NAME_ONLY"
        if kind:
            out.append((d, kind, dist, nj))
    # Best matches first: by kind rank, then by distance asc, then name desc
    rank = {"STRONG_DIST":0, "EXACT_NAME":1, "LIKELY_DIST_NAME":2,
            "WEAK_DIST_NAME":3, "NAME_ONLY":4}
    out.sort(key=lambda t: (rank[t[1]], (t[2] if t[2] >= 0 else 999), -t[3]))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="/home/oliver/harmonics/help/unknown_datum_matches.tsv")
    args = ap.parse_args()

    all_stations: list[Station] = []
    for path, label, mode in FILES:
        if not path.exists():
            print(f"  ⚠ skip (missing): {path}")
            continue
        stations = parse_file(path, label, mode)
        all_stations.extend(stations)
        print(f"  {label:14s} {len(stations):5d} stations  ({sum(1 for s in stations if s.lat is not None)} w/ coords)")

    unknowns = [s for s in all_stations if s.datum.lower() == "unknown"]
    donors   = [s for s in all_stations if s.datum.lower() not in ("unknown", "(none)", "n/a", "")]
    print(f"\n  Unknown-datum stations: {len(unknowns)}")
    print(f"  Known-datum donors:     {len(donors)}")

    out_lines = ["unk_country\tunk_source\tunk_name\tunk_lat\tunk_lon\tunk_z0_m\tmatch_kind\tdist_km\tname_jacc\tdonor_source\tdonor_datum\tdonor_z0_m\tdonor_name"]
    matched = 0
    no_match = 0
    by_country_match = defaultdict(int)
    by_country_no = defaultdict(int)

    for unk in unknowns:
        unk_z0_m = to_meters(unk.z0, unk.z0_unit)
        matches = find_matches(unk, donors)
        if matches:
            matched += 1
            by_country_match[unk.country] += 1
            best_d, kind, dist, nj = matches[0]
            best_z0_m = to_meters(best_d.z0, best_d.z0_unit)
            out_lines.append("\t".join([
                unk.country, unk.source_label, unk.name,
                f"{unk.lat:.4f}" if unk.lat is not None else "",
                f"{unk.lon:.4f}" if unk.lon is not None else "",
                f"{unk_z0_m:.4f}",
                kind,
                f"{dist:.3f}" if dist >= 0 else "",
                f"{nj:.2f}",
                best_d.source_label, best_d.datum, f"{best_z0_m:.4f}",
                best_d.name,
            ]))
        else:
            no_match += 1
            by_country_no[unk.country] += 1
            out_lines.append("\t".join([
                unk.country, unk.source_label, unk.name,
                f"{unk.lat:.4f}" if unk.lat is not None else "",
                f"{unk.lon:.4f}" if unk.lon is not None else "",
                f"{unk_z0_m:.4f}",
                "NO_MATCH", "", "", "", "", "", "",
            ]))

    Path(args.out).write_text("\n".join(out_lines) + "\n", encoding="utf-8")
    print(f"\n  Match results: {matched} matched, {no_match} no match")
    print(f"  Wrote {args.out}")

    # Top countries with matches and without
    print("\n  Countries with successful matches (top 20):")
    for c, n in sorted(by_country_match.items(), key=lambda kv: -kv[1])[:20]:
        print(f"    {c:30s} {n:4d}")
    print("\n  Countries WITHOUT match (top 20):")
    for c, n in sorted(by_country_no.items(), key=lambda kv: -kv[1])[:20]:
        print(f"    {c:30s} {n:4d}")


if __name__ == "__main__":
    main()
