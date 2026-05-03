#!/usr/bin/env python3
"""Cross-reference IDs from source harmonics files into legacy files.

Scans source files (DWF 2025, TICON4, UTide tidetables/observations/currents,
IHM Spain) for station blocks containing identifier fields like
`# noaa_station_id:`, `# uhslc_id:`, `# psmsl_id:`, `# ioc_code:` etc.
For each station in target legacy files (1997, 2004, Lavergne v10), finds
the best match by geographic distance + name similarity, then optionally
injects the matched IDs into the target file's HOT COMMENTS block.

Usage:
    python3 cross_reference_ids.py --dry        # build report, do not modify
    python3 cross_reference_ids.py --inject     # rewrite target files (with .bak_id_inject backup)
"""
import argparse
import json
import math
import re
import sys
import unicodedata
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path

ENC = "iso-8859-1"

SOURCE_FILES = [
    "/home/oliver/harmonics/classic/harmonics-dwf-20251228-free.txt",
    "/home/oliver/harmonics/ticon/harmonics_ticon4_worldwide.txt",
    "/home/oliver/harmonics/utide/harmonics_utide_tidetables.txt",
    "/home/oliver/harmonics/utide/harmonics_utide_observations.txt",
    "/home/oliver/harmonics/utide/harmonics_utide_currents.txt",
    "/home/oliver/harmonics/ihm/harmonics_puertos_spain.txt",
]

TARGET_FILES = [
    "/home/oliver/harmonics/classic/harmonics-1997-05-25_mod.txt",
    "/home/oliver/harmonics/classic/harmonics-2004-06-14_mod.txt",
    "/home/oliver/harmonics/classic/harmonics-pierre-lavergne-v10_mod.txt",
]

REPORT_PATH = Path("/home/oliver/harmonics/help/cross_reference_ids_report.json")

# Fields that count as identifiers and should be copied across.
# We deliberately exclude generic `station_id` and `station_id_context`
# (they only make sense paired with their source) but we DO copy
# qualified IDs like `noaa_station_id`, `uhslc_id`, etc.
ID_FIELD_RE = re.compile(
    r"^# ([a-z][a-z0-9]*_(?:station_id|id|code))\s*:\s*(.+?)\s*$",
    re.IGNORECASE,
)
# Fields to skip even when they match the pattern above
SKIP_FIELDS = {"station_id", "station_id_context"}

LAT_RE = re.compile(r"^# !latitude:\s*([-+]?\d+\.?\d*)\s*$")
LON_RE = re.compile(r"^# !longitude:\s*([-+]?\d+\.?\d*)\s*$")
UNITS_RE = re.compile(r"^# !units:\s*(.+?)\s*$")

DIST_THRESHOLD_KM = 2.0
NAME_SIM_THRESHOLD = 0.80
NAME_SIM_REVIEW = 0.50


def normalize_name(name: str) -> str:
    """Lowercase, strip diacritics, collapse non-alphanum to space."""
    s = unicodedata.normalize("NFKD", name)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower()
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def name_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def parse_blocks(path: str):
    """Yield dicts with keys: name, lat, lon, units_line_idx, ids, lines.

    A block is anchored by its `# !latitude:` line. The station name is the
    first non-comment line after `# !latitude:`. The HOT COMMENTS block is
    everything from the previous block's end (or file head) up to `# !units:`
    or `# !longitude:` (whichever comes first).
    """
    with open(path, "r", encoding=ENC) as f:
        lines = f.readlines()

    n = len(lines)
    i = 0
    last_block_end = 0  # index after end of previous station's comment region

    while i < n:
        m = LAT_RE.match(lines[i])
        if not m:
            i += 1
            continue
        lat_idx = i
        try:
            lat = float(m.group(1))
        except ValueError:
            i += 1
            continue

        # Find longitude (typically lat_idx - 1)
        lon = None
        units_idx = None
        for j in range(max(0, lat_idx - 5), lat_idx):
            mlon = LON_RE.match(lines[j])
            if mlon:
                try:
                    lon = float(mlon.group(1))
                except ValueError:
                    pass
            if UNITS_RE.match(lines[j]):
                units_idx = j

        if lon is None or units_idx is None:
            i = lat_idx + 1
            continue

        # Walk back from units_idx to collect the comment block of THIS station.
        # The comment block extends back to the previous data line (or file start).
        comment_start = units_idx
        for j in range(units_idx - 1, last_block_end - 1, -1):
            line = lines[j].rstrip("\n")
            if line.startswith("#") or line.strip() == "":
                comment_start = j
            else:
                break

        # Find name: first non-comment, non-empty line after `# !latitude:`
        name = None
        name_idx = None
        for j in range(lat_idx + 1, n):
            line = lines[j].rstrip("\n")
            if not line.strip():
                continue
            if line.startswith("#"):
                continue
            name = line.strip()
            name_idx = j
            break

        if name is None:
            i = lat_idx + 1
            continue

        # Extract IDs from comment block
        ids = {}
        for j in range(comment_start, units_idx):
            mid = ID_FIELD_RE.match(lines[j].rstrip("\n"))
            if mid:
                field = mid.group(1).lower()
                if field in SKIP_FIELDS:
                    continue
                ids[field] = mid.group(2).strip()

        yield {
            "name": name,
            "lat": lat,
            "lon": lon,
            "comment_start": comment_start,
            "units_idx": units_idx,
            "lat_idx": lat_idx,
            "name_idx": name_idx,
            "ids": ids,
        }

        last_block_end = name_idx + 1
        # Skip past constituent lines: jump to next blank or next # !units
        k = name_idx + 1
        while k < n:
            if lines[k].startswith("# !units:") or lines[k].startswith("# !latitude:"):
                break
            k += 1
        i = k


def build_db():
    """Build cross-reference DB from source files."""
    db = []
    per_source = {}
    for path in SOURCE_FILES:
        if not Path(path).exists():
            print(f"  WARNING: source not found: {path}", file=sys.stderr)
            continue
        count = 0
        with_ids = 0
        for block in parse_blocks(path):
            count += 1
            if block["ids"]:
                with_ids += 1
                db.append({
                    "src": Path(path).name,
                    "name": block["name"],
                    "norm": normalize_name(block["name"]),
                    "lat": block["lat"],
                    "lon": block["lon"],
                    "ids": block["ids"],
                })
        per_source[Path(path).name] = (count, with_ids)
        print(f"  {Path(path).name}: {with_ids}/{count} mit IDs")
    return db, per_source


def build_geo_index(db, cell_deg=1.0):
    """Spatial index: bucket entries by 1°×1° cells for fast neighbour lookup."""
    idx = defaultdict(list)
    for i, e in enumerate(db):
        cx = int(math.floor(e["lon"] / cell_deg))
        cy = int(math.floor(e["lat"] / cell_deg))
        idx[(cx, cy)].append(i)
    return idx


def neighbours(idx, lat, lon, cell_deg=1.0, radius_cells=2):
    """Return DB indices in cells near (lat, lon). radius_cells=2 covers up to ~220 km."""
    cx = int(math.floor(lon / cell_deg))
    cy = int(math.floor(lat / cell_deg))
    out = []
    for dx in range(-radius_cells, radius_cells + 1):
        for dy in range(-radius_cells, radius_cells + 1):
            out.extend(idx.get((cx + dx, cy + dy), []))
    return out


def match_target(target_block, db, geo_idx):
    """Return (best_match_dict_or_None, status, all_close_candidates)."""
    tlat = target_block["lat"]
    tlon = target_block["lon"]
    tnorm = normalize_name(target_block["name"])

    candidates = []
    for di in neighbours(geo_idx, tlat, tlon):
        e = db[di]
        d = haversine_km(tlat, tlon, e["lat"], e["lon"])
        if d > DIST_THRESHOLD_KM:
            continue
        sim = name_similarity(tnorm, e["norm"])
        candidates.append((d, sim, e))

    if not candidates:
        return None, "no_geo_match", []

    # Rank by similarity desc, then distance asc
    candidates.sort(key=lambda c: (-c[1], c[0]))
    best_d, best_sim, best_e = candidates[0]

    if best_sim >= NAME_SIM_THRESHOLD:
        return best_e, "matched", candidates
    if best_sim >= NAME_SIM_REVIEW:
        return None, "review", candidates
    return None, "no_name_match", candidates


def inject_ids(target_path, matches_for_file, dry_run=True):
    """Rewrite target file: insert new # field: value lines just BEFORE # !units:.

    matches_for_file: list of dicts {block: parsed_block, ids_to_add: dict}.
    Existing IDs in the block are not overwritten.
    """
    path = Path(target_path)
    with open(path, "r", encoding=ENC) as f:
        lines = f.readlines()

    # Build map: units_idx -> ids_to_add
    inserts = {}
    for m in matches_for_file:
        ui = m["block"]["units_idx"]
        existing = set(m["block"]["ids"].keys())
        new = {k: v for k, v in m["ids_to_add"].items() if k not in existing}
        if new:
            inserts[ui] = new

    if not inserts:
        print(f"  {path.name}: keine neuen IDs zum Einfügen")
        return 0

    out = []
    added = 0
    for idx, line in enumerate(lines):
        if idx in inserts:
            for field, value in sorted(inserts[idx].items()):
                out.append(f"# {field}: {value}\n")
                added += 1
        out.append(line)

    if dry_run:
        print(f"  {path.name}: würde {added} ID-Felder in {len(inserts)} Blöcken einfügen")
        return added

    backup = path.with_suffix(path.suffix + ".bak_id_inject")
    if not backup.exists():
        backup.write_bytes(path.read_bytes())
        print(f"  Backup angelegt: {backup.name}")
    with open(path, "w", encoding=ENC) as f:
        f.writelines(out)
    print(f"  {path.name}: {added} ID-Felder in {len(inserts)} Blöcken eingefügt")
    return added


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--inject", action="store_true",
                    help="Rewrite target files (default: dry-run)")
    ap.add_argument("--report-only", action="store_true",
                    help="Only generate report, no per-station console output")
    args = ap.parse_args()

    print("== Quellen scannen ==")
    db, per_source = build_db()
    print(f"DB-Einträge mit IDs: {len(db)}")
    geo_idx = build_geo_index(db)

    print("\n== Zieldateien matchen ==")
    overall = {}
    for tpath in TARGET_FILES:
        if not Path(tpath).exists():
            print(f"  WARNING: target not found: {tpath}", file=sys.stderr)
            continue
        target_blocks = list(parse_blocks(tpath))
        stats = {"total": len(target_blocks), "matched": 0, "review": 0,
                 "no_geo": 0, "no_name": 0}
        matches_for_file = []
        review_log = []
        for block in target_blocks:
            best, status, cands = match_target(block, db, geo_idx)
            if status == "matched":
                stats["matched"] += 1
                matches_for_file.append({"block": block, "ids_to_add": best["ids"],
                                         "matched_to": best["name"],
                                         "src": best["src"]})
            elif status == "review":
                stats["review"] += 1
                review_log.append({
                    "target": block["name"],
                    "target_lat": block["lat"],
                    "target_lon": block["lon"],
                    "candidates": [
                        {"name": c[2]["name"], "src": c[2]["src"],
                         "dist_km": round(c[0], 3), "sim": round(c[1], 3),
                         "ids": c[2]["ids"]}
                        for c in cands[:5]
                    ],
                })
            elif status == "no_geo_match":
                stats["no_geo"] += 1
            else:
                stats["no_name"] += 1

        overall[Path(tpath).name] = {
            "stats": stats,
            "matches": [{"target": m["block"]["name"],
                         "target_lat": m["block"]["lat"],
                         "target_lon": m["block"]["lon"],
                         "matched_to": m["matched_to"],
                         "src": m["src"],
                         "ids": m["ids_to_add"]} for m in matches_for_file],
            "review": review_log,
        }
        print(f"  {Path(tpath).name}: matched={stats['matched']} "
              f"review={stats['review']} no_geo={stats['no_geo']} "
              f"no_name={stats['no_name']} total={stats['total']}")

        if args.inject:
            inject_ids(tpath, matches_for_file, dry_run=False)
        else:
            inject_ids(tpath, matches_for_file, dry_run=True)

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(overall, f, indent=2, ensure_ascii=False)
    print(f"\nReport: {REPORT_PATH}")

    if not args.inject:
        print("\n(Dry-run. Mit --inject werden die Zieldateien tatsächlich geändert.)")


if __name__ == "__main__":
    main()
