#!/usr/bin/env python3
"""Build station -> sea/ocean lookup using IHO Sea Areas (S-23 boundaries).

Reads:
  harmonics/help/iho_sea_areas.json   (101 polygons from MarineRegions WFS)
  static/js/leaflet_markers_data.json (~12k stations with lat/lon/slug)

Writes:
  harmonics/help/station_seas.json    (slug -> sea name)

Lookup algorithm:
  1. Spatial index (STRtree) -> point-in-polygon test for direct hit
  2. Fallback to nearest polygon within 5° (~500 km) for stations slightly
     outside the polygon boundary (e.g., harbours that fall on the land side
     of the polygon edge)
  3. Stations more than 5° from any sea polygon are skipped
"""
import json
import os
import sys
from shapely.geometry import shape, Point
from shapely.strtree import STRtree

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IHO_PATH = os.path.join(ROOT, "harmonics", "help", "iho_sea_areas.json")
STATIONS_PATH = os.path.join(ROOT, "static", "js", "leaflet_markers_data.json")
OUT_PATH = os.path.join(ROOT, "harmonics", "help", "station_seas.json")

# Cleaner / SEO-friendlier names than the raw IHO labels
NAME_CLEANUP = {
    "Andaman or Burma Sea": "Andaman Sea",
    "Mediterranean Sea - Eastern Basin": "Mediterranean Sea",
    "Mediterranean Sea - Western Basin": "Mediterranean Sea",
    "Balearic (Iberian Sea)": "Balearic Sea",
    "Irish Sea and St. George's Channel": "Irish Sea",
    "Inner Seas off the West Coast of Scotland": "Inner Hebrides",
    "The Coastal Waters of Southeast Alaska and British Columbia": "Inside Passage",
    "The Northwestern Passages": "Northwest Passage",
    "Seto Naikai or Inland Sea": "Seto Inland Sea",
    "Eastern China Sea": "East China Sea",
    "Japan Sea": "Sea of Japan",
    "Barentsz Sea": "Barents Sea",
}


def load_iho():
    with open(IHO_PATH) as f:
        d = json.load(f)
    polys, names = [], []
    for feat in d["features"]:
        raw = feat["properties"].get("name") or "?"
        polys.append(shape(feat["geometry"]))
        names.append(NAME_CLEANUP.get(raw, raw))
    return polys, names


def main():
    print(f"Loading IHO polygons from {IHO_PATH} ...")
    polys, names = load_iho()
    print(f"  {len(polys)} polygons")

    print("Building STRtree spatial index ...")
    tree = STRtree(polys)

    print(f"Loading stations from {STATIONS_PATH} ...")
    with open(STATIONS_PATH) as f:
        d = json.load(f)
    stations = d["stations"]
    print(f"  {len(stations)} stations")

    result = {}
    direct_hits = 0
    nearest_hits = 0
    misses = []
    for s in stations:
        # [displayName, lat, lon, source, groupIdx, isCurrent, slug, ...]
        name, lat, lon, _, _, _, slug = s[:7]
        try:
            lat_f, lon_f = float(lat), float(lon)
        except (TypeError, ValueError):
            continue
        pt = Point(lon_f, lat_f)
        sea = None
        # Direct point-in-polygon
        for i in tree.query(pt):
            if polys[i].contains(pt):
                sea = names[i]
                direct_hits += 1
                break
        if sea is None:
            # Nearest within 5° (handles harbours just outside polygon edge)
            best_i, best_d = None, float("inf")
            for i, poly in enumerate(polys):
                dist = poly.distance(pt)
                if dist < best_d:
                    best_d = dist
                    best_i = i
            if best_d < 5.0:
                sea = names[best_i]
                nearest_hits += 1
            else:
                misses.append((name, lat_f, lon_f))
        if sea:
            result[slug] = sea

    print(f"\nDirect hits:  {direct_hits}")
    print(f"Nearest <5°:  {nearest_hits}")
    print(f"Misses (>5°): {len(misses)}")
    if misses[:10]:
        print("  Sample misses:")
        for m in misses[:10]:
            print(f"    {m}")

    print(f"\nUnique seas covered: {len(set(result.values()))}")
    from collections import Counter
    counts = Counter(result.values())
    for sea, n in counts.most_common(15):
        print(f"  {n:5d}  {sea}")

    with open(OUT_PATH, "w") as f:
        json.dump(result, f, ensure_ascii=False, separators=(",", ":"))
    print(f"\nWrote {OUT_PATH} ({os.path.getsize(OUT_PATH)/1024:.1f} KB)")


if __name__ == "__main__":
    main()
