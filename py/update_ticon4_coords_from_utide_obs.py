#!/usr/bin/env python3
"""For each TICON-4 station whose name matches a station in
harmonics_utide_observations.txt exactly, overwrite the TICON-4
`# !latitude:` and `# !longitude:` values with the UTide-obs values.

UTide-obs coords come from official pegel registries (BODC, CMEMS,
pegelonline, …) and are typically more precise (5 decimals vs ~3 in
TICON-4 / GESLA-4 metadata).

Datum, Z₀, harmonic constants, station name — all unchanged.

Dry-run by default. Pass --apply to rewrite the file.
"""
from __future__ import annotations

import argparse
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path("/home/oliver/harmonics")
UTIDE_OBS = ROOT / "utide" / "harmonics_utide_observations.txt"
TICON4    = ROOT / "ticon" / "harmonics_ticon4_worldwide.txt"


def parse_name_to_coords(path: Path) -> dict[str, list[tuple[float, float]]]:
    """Parse XTide HOT-COMMENTS-style file.  Return {station_name: [(lat, lon), ...]}.
    Multiple entries per name are kept (Whitby BODC + CMEMS); we'll prefer
    near-duplicate coords later."""
    raw = path.read_bytes().decode("iso-8859-1", errors="replace")
    lines = raw.split("\n")
    out: dict[str, list[tuple[float, float]]] = defaultdict(list)
    in_block = False
    block_lat = None
    block_lon = None
    for i, ln in enumerate(lines):
        if ln.startswith("# BEGIN HOT COMMENTS"):
            in_block = True
            block_lat = None
            block_lon = None
            continue
        if in_block:
            if ln.startswith("# !latitude:"):
                try: block_lat = float(ln.split(":", 1)[1].strip())
                except ValueError: pass
            elif ln.startswith("# !longitude:"):
                try: block_lon = float(ln.split(":", 1)[1].strip())
                except ValueError: pass
            if (re.match(r"^[A-Za-zÀ-ÿ]", ln) and not ln.startswith("#")
                    and i + 2 < len(lines)
                    and re.match(r"^[+\-]?\d{1,2}:\d{2}", lines[i+1])):
                if block_lat is not None and block_lon is not None:
                    out[ln.strip()].append((block_lat, block_lon))
                in_block = False
                block_lat = None
                block_lon = None
    return out


def rewrite_ticon4(name_to_coords: dict[str, list[tuple[float, float]]],
                   apply: bool):
    raw = TICON4.read_bytes().decode("iso-8859-1", errors="replace")
    lines = raw.split("\n")

    in_block = False
    block_meta: dict = {}
    rewrites = []   # (station_name, old_lat, new_lat, old_lon, new_lon, dist_marker)

    for i, ln in enumerate(lines):
        if ln.startswith("# BEGIN HOT COMMENTS"):
            in_block = True
            block_meta = {"lat_idx": None, "lon_idx": None,
                          "lat": None, "lon": None}
            continue
        if in_block:
            if ln.startswith("# !latitude:"):
                block_meta["lat_idx"] = i
                try: block_meta["lat"] = float(ln.split(":", 1)[1].strip())
                except ValueError: pass
            elif ln.startswith("# !longitude:"):
                block_meta["lon_idx"] = i
                try: block_meta["lon"] = float(ln.split(":", 1)[1].strip())
                except ValueError: pass
            if (re.match(r"^[A-Za-zÀ-ÿ]", ln) and not ln.startswith("#")
                    and i + 2 < len(lines)
                    and re.match(r"^[+\-]?\d{1,2}:\d{2}", lines[i+1])):
                name = ln.strip()
                donor_coords = name_to_coords.get(name)
                if donor_coords:
                    # If multiple donors with same name, pick the one closest
                    # to the recipient (TICON-4) coords, fall back to first.
                    if block_meta["lat"] is not None and block_meta["lon"] is not None:
                        donor_coords_sorted = sorted(donor_coords, key=lambda c:
                            abs(c[0] - block_meta["lat"]) + abs(c[1] - block_meta["lon"]))
                        new_lat, new_lon = donor_coords_sorted[0]
                    else:
                        new_lat, new_lon = donor_coords[0]
                    if (block_meta["lat_idx"] is not None
                            and block_meta["lon_idx"] is not None
                            and block_meta["lat"] is not None
                            and block_meta["lon"] is not None):
                        # Only rewrite if the donor coordinate is meaningfully
                        # different — > 0.001° (≈100 m) on either axis. Smaller
                        # differences are usually rounding artefacts where one
                        # source has trailing zeros while the other doesn't,
                        # so applying them risks LOSING precision rather than
                        # gaining it.
                        dlat = abs(block_meta["lat"] - new_lat)
                        dlon = abs(block_meta["lon"] - new_lon)
                        if dlat > 1e-3 or dlon > 1e-3:
                            lines[block_meta["lat_idx"]] = f"# !latitude: {new_lat}"
                            lines[block_meta["lon_idx"]] = f"# !longitude: {new_lon}"
                            rewrites.append((
                                name,
                                block_meta["lat"], new_lat,
                                block_meta["lon"], new_lon,
                            ))
                in_block = False
                block_meta = {}

    print(f"\n{'DRY RUN' if not apply else 'APPLY':>8s}")
    print("─" * 90)
    for name, old_lat, new_lat, old_lon, new_lon in rewrites[:25]:
        print(f"  {name[:55]:55s}  ({old_lat:.4f}, {old_lon:.4f}) → ({new_lat:.4f}, {new_lon:.4f})")
    if len(rewrites) > 25:
        print(f"  ... +{len(rewrites)-25} more")
    print("─" * 90)
    print(f"  TOTAL: {len(rewrites)} TICON-4 stations would be re-coordinated")

    if apply and rewrites:
        before = sum(1 for l in lines if "BEGIN HOT COMMENTS" in l)
        TICON4.write_bytes("\n".join(lines).encode("iso-8859-1"))
        after = sum(1 for l in TICON4.read_text(encoding="iso-8859-1").splitlines() if "BEGIN HOT COMMENTS" in l)
        if before != after:
            raise RuntimeError(f"Station-count changed: {before} → {after}")
        print(f"  Wrote {TICON4} ({before} stations preserved).")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    name_to_coords = parse_name_to_coords(UTIDE_OBS)
    print(f"  UTide-obs: {len(name_to_coords)} unique station names parsed")
    rewrite_ticon4(name_to_coords, apply=args.apply)


if __name__ == "__main__":
    main()
