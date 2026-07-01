#!/usr/bin/env python3
"""Step 2 — phase 2: Apply the matches found by
match_unknown_datum_via_duplicates.py.

For each Unknown-datum station with a confident duplicate match, copy the
donor's `# datum:` and Z₀ value into the recipient's station block.

Rules:
- Apply: match_kind in {STRONG_DIST, EXACT_NAME, LIKELY_DIST_NAME}
- Skip:  hard-coded exclusions for unsafe matches (see EXCLUDE).
- Promote: donor datum like "X (approx.)" → "X" when transferring to a
           real-data station (TICON-4/UTide-obs are real-data).
- Z₀: convert units if recipient and donor differ (1 ft = 0.3048 m).

Dry-run by default. Pass --apply to actually rewrite files.
"""
from __future__ import annotations

import argparse
import csv
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path("/home/oliver/harmonics")
TSV  = ROOT / "help" / "unknown_datum_matches.tsv"

# --- Exclusions: matches we deemed unsafe in manual review ---
# Key = (recipient station name, recipient source label).
EXCLUDE = {
    ("Lübeck-Bauhof (Trave), Germany", "TICON-4"),  # SNN76 donor uncertain
}

# Match kinds we accept
APPLY_KINDS = {"STRONG_DIST", "EXACT_NAME", "LIKELY_DIST_NAME"}

# Sources that hold real-data analyses (so an "approx." donor should be promoted)
REAL_DATA_SOURCES = {"TICON-4", "UTide-obs"}

APPROX_RE = re.compile(r"\s*\(approx\.\)\s*$")

# Synonym normalisation — same canonical form Step 1 already enforces
# in our [CONTROLLED] files. Donors from classic_original/ predate that
# pass and use verbose names, so we normalise on transfer.
DATUM_NORMALIZE = {
    "Mean Lower Low Water":       "MLLW",
    "Mean Sea Level":             "MSL",
    "Lowest Astronomical Tide":   "LAT",
    "Chart Datum":                "CD",
    "Chart Datum (CD)":           "CD",
    "Admiralty Chart Datum":      "ACD",
    "Admiralty Chart Datum (ACD)":"ACD",
    "Normal Amsterdam Level":     "NAP",
    "Zero Hydrographique":        "ZH",
    "Zéro Hydrographique":        "ZH",
    "Lower Low Water Large Tide": "LLWLT",
    "Zero of Tide Height":        "ZTH",
}


def promote(datum: str, recipient_source: str) -> str:
    if recipient_source in REAL_DATA_SOURCES:
        return APPROX_RE.sub("", datum)
    return datum


def normalize(datum: str) -> str:
    return DATUM_NORMALIZE.get(datum.strip(), datum)


def feet_to_m(x: float) -> float: return x * 0.3048
def m_to_feet(x: float) -> float: return x / 0.3048


def load_matches() -> list[dict]:
    rows = []
    with TSV.open(encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for r in reader:
            rows.append(r)
    return rows


# Per-file rewrite logic
class FilePatcher:
    def __init__(self, path: Path):
        self.path = path
        raw = path.read_bytes().decode("iso-8859-1", errors="replace")
        self.lines = raw.split("\n")
        self.changes = 0

    def find_station_block(self, station_name: str,
                           target_lat: float | None = None,
                           target_lon: float | None = None) -> tuple[int, int] | None:
        """Return (datum_line_idx, z0_line_idx) of first matching station.
        If target_lat/lon supplied, prefer the station-block whose
        `# !latitude:` / `# !longitude:` are closest (within 0.01°)."""
        in_block = False
        datum_idx = None
        block_lat = None
        block_lon = None
        candidates = []   # (datum_idx, z0_idx, lat, lon)
        for i, ln in enumerate(self.lines):
            if ln.startswith("# BEGIN HOT COMMENTS"):
                in_block = True
                datum_idx = None
                block_lat = None
                block_lon = None
                continue
            if in_block:
                if ln.startswith("# datum:"):
                    datum_idx = i
                elif ln.startswith("# !latitude:"):
                    try: block_lat = float(ln.split(":", 1)[1].strip())
                    except ValueError: pass
                elif ln.startswith("# !longitude:"):
                    try: block_lon = float(ln.split(":", 1)[1].strip())
                    except ValueError: pass
                if (re.match(r"^[A-Za-zÀ-ÿ]", ln) and not ln.startswith("#")
                        and i + 2 < len(self.lines)
                        and re.match(r"^[+\-]?\d{1,2}:\d{2}", self.lines[i+1])):
                    if ln.strip() == station_name:
                        candidates.append((datum_idx, i + 2, block_lat, block_lon))
                    in_block = False
                    datum_idx = None
                    block_lat = None
                    block_lon = None
        if not candidates:
            return None
        if target_lat is not None and target_lon is not None and len(candidates) > 1:
            candidates.sort(key=lambda c: (
                999 if c[2] is None or c[3] is None
                else abs(c[2] - target_lat) + abs(c[3] - target_lon)
            ))
        return candidates[0][0], candidates[0][1]

    def apply(self, station_name: str, new_datum: str, new_z0: float,
              new_unit: str,
              target_lat: float | None = None,
              target_lon: float | None = None):
        loc = self.find_station_block(station_name, target_lat, target_lon)
        if loc is None:
            print(f"  ⚠ not found in {self.path.name}: {station_name!r}")
            return False
        datum_idx, z0_idx = loc
        if datum_idx is not None:
            self.lines[datum_idx] = f"# datum: {new_datum}"
        # Rewrite Z₀ line, preserving unit of the recipient
        old = self.lines[z0_idx]
        m = re.match(r"\s*([+-]?\d+(?:\.\d+)?)\s+(meters|feet)\s*$", old)
        if not m:
            print(f"  ⚠ Z0 line malformed in {self.path.name}: {old!r}")
            return False
        old_unit = m.group(2)
        z0_in_recipient_unit = new_z0 if new_unit == old_unit else (
            feet_to_m(new_z0) if new_unit == "feet" else m_to_feet(new_z0)
        )
        # XTide-style — 4-decimal precision, unit unchanged
        self.lines[z0_idx] = f"{z0_in_recipient_unit:.4f} {old_unit}"
        self.changes += 1
        return True

    def save(self):
        self.path.write_bytes("\n".join(self.lines).encode("iso-8859-1"))


SOURCE_TO_PATH = {
    "TICON-4":      ROOT / "ticon"   / "harmonics_ticon4_worldwide.txt",
    "UTide-obs":    ROOT / "utide"   / "harmonics_utide_observations.txt",
    "UTide-tt":     ROOT / "utide"   / "harmonics_utide_tidetables.txt",
    "UTide-cur":    ROOT / "utide"   / "harmonics_utide_currents.txt",
    "IHM-Spain":    ROOT / "classic"     / "harmonics_puertos_spain.txt",
    "Classic-1997": ROOT / "classic" / "harmonics-1997-05-25_mod.txt",
    "Classic-2004": ROOT / "classic" / "harmonics-2004-06-14_mod.txt",
    "DWF-2007":     ROOT / "classic" / "harmonics-dwf-20070318_mod.txt",
    "DWF-2010":     ROOT / "classic" / "harmonics-dwf-20100529-nonfree_mod.txt",
    "Lavergne-v10": ROOT / "classic" / "harmonics-pierre-lavergne-v10_mod.txt",
    "Lavergne-v9":  ROOT / "classic" / "harmonics-pierre-lavergne-v9-europe_mod.txt",
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    rows = load_matches()
    plan_by_source: dict[str, list[tuple[str, str, float, str]]] = defaultdict(list)
    skipped = []
    promoted = Counter()
    accepted_kinds = Counter()

    for r in rows:
        kind = r["match_kind"]
        if kind not in APPLY_KINDS:
            continue
        key = (r["unk_name"], r["unk_source"])
        if key in EXCLUDE:
            skipped.append((r["unk_name"], r["unk_source"], "manual exclusion"))
            continue
        # Skip recipients in donor-only files (classic_original/*).
        if r["unk_source"] not in SOURCE_TO_PATH:
            skipped.append((r["unk_name"], r["unk_source"], "donor-only file (read-only)"))
            continue
        donor_datum = normalize(r["donor_datum"])
        promoted_datum = promote(donor_datum, r["unk_source"])
        if promoted_datum != donor_datum:
            promoted[(donor_datum, promoted_datum)] += 1

        # Donor Z₀ is given in METERS in the TSV (we converted at extraction time).
        donor_z0_m = float(r["donor_z0_m"])
        try:
            recip_lat = float(r["unk_lat"]) if r["unk_lat"] else None
            recip_lon = float(r["unk_lon"]) if r["unk_lon"] else None
        except ValueError:
            recip_lat = recip_lon = None
        plan_by_source[r["unk_source"]].append(
            (r["unk_name"], promoted_datum, donor_z0_m, "meters", recip_lat, recip_lon)
        )
        accepted_kinds[kind] += 1

    # Summary
    print(f"\n{'DRY RUN' if not args.apply else 'APPLY':>8s}\n" + "─" * 70)
    for kind, n in accepted_kinds.most_common():
        print(f"  {kind:20s} {n:5d}")
    print(f"  {'TOTAL accepted':20s} {sum(accepted_kinds.values()):5d}")
    print(f"  {'Skipped (manual)':20s} {len(skipped):5d}")
    if promoted:
        print("\n  Promoted (approx.) → official:")
        for (old, new), n in promoted.items():
            print(f"    {n:>3d}  {old!r:30s} → {new!r}")
    if skipped:
        print("\n  Skipped:")
        for name, src, why in skipped:
            print(f"    [{src}]  {name}  ({why})")
    print(f"\n  Per source / file:")
    for src, items in plan_by_source.items():
        print(f"    {src:14s} {len(items):4d} stations")

    if args.apply:
        print("\n  Writing changes…")
        for src, items in plan_by_source.items():
            path = SOURCE_TO_PATH[src]
            patcher = FilePatcher(path)
            for name, datum, z0_m, unit, lat, lon in items:
                # FilePatcher needs (datum, z0, donor_unit) — donor unit is "meters"
                # because TSV always reports donor_z0_m in meters.
                patcher.apply(name, datum, z0_m, unit, lat, lon)
            patcher.save()
            print(f"    {src:14s} {patcher.changes} stations rewritten in {path.name}")
    else:
        print("\n  Run with --apply to actually rewrite files.")


if __name__ == "__main__":
    main()
