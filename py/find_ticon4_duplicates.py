#!/usr/bin/env python3
"""
Find duplicate stations in TICON-4 harmonics file based on geographic proximity.
Compares quality metrics to recommend which station to keep.
"""

import re
import math
from collections import defaultdict

INPUT_FILE = "/home/oliver/harmonics/ticon/harmonics_ticon4_worldwide_edited.txt"
DISTANCE_THRESHOLD_KM = 5.0

# Constituent names in order (from file header)
# Index 0=J1, 1=K1, 2=K2, 3=L2, 4=M1, 5=M2, ...
M2_INDEX = 5  # M2 is the 6th constituent (0-indexed)


def haversine(lat1, lon1, lat2, lon2):
    """Calculate distance in km between two points."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def parse_stations(filepath):
    """Parse all TICON-4 station blocks from the harmonics file."""
    with open(filepath, "r", encoding="iso-8859-1") as f:
        lines = f.readlines()

    stations = []
    i = 0
    n = len(lines)

    while i < n:
        # Look for TICON-4 block start
        if "Harmonic constants from TICON-4" not in lines[i]:
            i += 1
            continue

        block_start = i
        comment_lines = []

        # Collect all comment lines
        while i < n and lines[i].startswith("#"):
            comment_lines.append(lines[i].rstrip())
            i += 1

        # Now we should be at the station name line
        # But first check: the line after comments should be station name
        # Actually, looking at the structure:
        # After comments comes: station name, timezone, datum, then 175 constituents
        # But wait - the coordinates are in the HOT COMMENTS as !longitude and !latitude

        # Extract lat/lon from comments
        lat = None
        lon = None
        station_id = None
        country = None
        r_squared = None
        obs_info = None
        quality_info = None
        source_info = None
        constituents_matched = None
        comment_name = None

        for cl in comment_lines:
            m = re.search(r"#\s*!latitude:\s*([-\d.]+)", cl)
            if m:
                lat = float(m.group(1))
            m = re.search(r"#\s*!longitude:\s*([-\d.]+)", cl)
            if m:
                lon = float(m.group(1))
            m = re.search(r"#\s*station_id_context:\s*(.+)", cl)
            if m:
                station_id = m.group(1).strip()
            m = re.search(r"#\s*country:\s*(.+)", cl)
            if m:
                country = m.group(1).strip()
            m = re.search(r"#\s*R²\s*=\s*([\d.]+)", cl)
            if m:
                r_squared = float(m.group(1))
            m = re.match(r"#\s*(\d+)\s+observations\s+over\s+(\d+)\s+years", cl)
            if m:
                obs_info = f"{m.group(1)} obs / {m.group(2)} years"
            m = re.search(r"#\s*Quality:\s*(.+)", cl)
            if m:
                quality_info = m.group(1).strip()
            m = re.search(r"#\s*Source:\s*(.+)", cl)
            if m:
                source_info = m.group(1).strip()
            m = re.search(r"#\s*Constituents matched:\s*(\S+)", cl)
            if m:
                constituents_matched = m.group(1).strip()
            # Station name in comment (line after empty comment or specific pattern)
            m = re.match(r"#\s+([A-Z][\w\s\-\(\),.'/]+)$", cl)
            if m and "BEGIN HOT" not in cl and "Harmonic" not in cl and "Quality" not in cl and "Source" not in cl and "Constituents" not in cl and "country" not in cl and "station_id" not in cl and "date_imported" not in cl and "datum" not in cl and "confidence" not in cl and "units" not in cl and "longitude" not in cl and "latitude" not in cl and "observations" not in cl and "from " not in cl and "obvious" not in cl:
                comment_name = m.group(1).strip()

        if lat is None or lon is None:
            # Skip malformed blocks
            continue

        # Station name line (first non-comment, non-empty line after comments)
        if i >= n:
            continue
        station_name = lines[i].rstrip()
        i += 1

        # Timezone line
        if i >= n:
            continue
        timezone = lines[i].rstrip()
        i += 1

        # Datum offset line
        if i >= n:
            continue
        datum = lines[i].rstrip()
        i += 1

        # 175 constituent lines
        constituents = []
        for j in range(175):
            if i >= n:
                break
            line = lines[i].rstrip()
            i += 1
            # Parse amplitude and phase
            # Format: "NAME              amplitude  phase" or "x 0 0" for missing
            parts = line.split()
            if len(parts) >= 3 and parts[0] != 'x':
                try:
                    amp = float(parts[1])
                    phase = float(parts[2])
                    constituents.append((parts[0], amp, phase))
                except ValueError:
                    constituents.append((parts[0], 0.0, 0.0))
            elif len(parts) >= 3 and parts[0] == 'x':
                constituents.append(('x', 0.0, 0.0))
            else:
                constituents.append(('?', 0.0, 0.0))

        # Extract M2 amplitude
        m2_amp = 0.0
        if len(constituents) > M2_INDEX:
            m2_amp = constituents[M2_INDEX][1]

        # Count non-zero amplitude constituents
        nonzero_count = sum(1 for _, amp, _ in constituents if amp > 0)

        # Extract observation count and years for sorting
        obs_count = 0
        obs_years = 0
        for cl in comment_lines:
            m = re.match(r"#\s*(\d+)\s+observations\s+over\s+(\d+)\s+years", cl)
            if m:
                obs_count = int(m.group(1))
                obs_years = int(m.group(2))

        stations.append({
            "name": station_name,
            "lat": lat,
            "lon": lon,
            "m2_amp": m2_amp,
            "nonzero": nonzero_count,
            "station_id": station_id,
            "country": country,
            "r_squared": r_squared,
            "obs_info": obs_info,
            "obs_count": obs_count,
            "obs_years": obs_years,
            "quality_info": quality_info,
            "source_info": source_info,
            "constituents_matched": constituents_matched,
            "comment_name": comment_name,
            "block_start_line": block_start + 1,  # 1-indexed
        })

    return stations


def find_duplicate_clusters(stations, threshold_km):
    """Find clusters of stations within threshold_km of each other."""
    n = len(stations)
    # Use Union-Find for clustering
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    # Sort by latitude for efficiency
    indexed = sorted(range(n), key=lambda i: stations[i]["lat"])

    for idx_a in range(len(indexed)):
        i = indexed[idx_a]
        lat_i = stations[i]["lat"]
        for idx_b in range(idx_a + 1, len(indexed)):
            j = indexed[idx_b]
            lat_j = stations[j]["lat"]
            # Early exit: if latitude difference > ~0.05 degrees (~5.5km), skip
            if lat_j - lat_i > 0.06:
                break
            dist = haversine(lat_i, stations[i]["lon"], lat_j, stations[j]["lon"])
            if dist <= threshold_km:
                union(i, j)

    # Group by cluster
    clusters = defaultdict(list)
    for i in range(n):
        clusters[find(i)].append(i)

    # Return only clusters with 2+ stations
    return {k: v for k, v in clusters.items() if len(v) >= 2}


def quality_score(station):
    """Higher = better quality."""
    score = 0
    score += station["m2_amp"] * 100  # M2 amplitude weight
    score += station["nonzero"] * 2    # Non-zero constituents
    score += station["obs_years"] * 1  # More years = better
    score += station["obs_count"] / 100000  # More observations
    if station["r_squared"] is not None:
        score += station["r_squared"] * 50
    return score


def main():
    print("Parsing stations...")
    stations = parse_stations(INPUT_FILE)
    print(f"Found {len(stations)} TICON-4 stations\n")

    print(f"Finding duplicates within {DISTANCE_THRESHOLD_KM} km...")
    clusters = find_duplicate_clusters(stations, DISTANCE_THRESHOLD_KM)
    print(f"Found {len(clusters)} duplicate clusters\n")

    if not clusters:
        print("No duplicates found.")
        return

    # Sort clusters by first station name for readability
    sorted_clusters = sorted(clusters.values(), key=lambda c: stations[c[0]]["name"])

    total_to_delete = 0
    delete_names = []

    print("=" * 100)
    print("DUPLICATE STATION REPORT")
    print("=" * 100)

    for cluster_idx, indices in enumerate(sorted_clusters, 1):
        # Sort by quality score descending
        scored = [(i, quality_score(stations[i])) for i in indices]
        scored.sort(key=lambda x: -x[1])

        best_idx = scored[0][0]
        best = stations[best_idx]

        print(f"\n--- Cluster {cluster_idx} ({len(indices)} stations) ---")

        # Print distances matrix
        for a_pos, (a_i, a_score) in enumerate(scored):
            sa = stations[a_i]
            if a_pos == 0:
                label = "KEEP  "
            else:
                label = "DELETE"
                total_to_delete += 1
                delete_names.append(sa["name"])

            print(f"  [{label}] {sa['name']}")
            print(f"           Lat/Lon: {sa['lat']:.6f}, {sa['lon']:.6f}  |  Line: {sa['block_start_line']}")
            print(f"           M2: {sa['m2_amp']:.4f}m  |  Non-zero: {sa['nonzero']}/175  |  Score: {a_score:.1f}")
            print(f"           Obs: {sa['obs_info'] or 'N/A'}  |  Quality: {sa['quality_info'] or 'N/A'}  |  Source: {sa['source_info'] or 'N/A'}")
            print(f"           Constituents matched: {sa['constituents_matched'] or 'N/A'}  |  Station ID: {sa['station_id'] or 'N/A'}")
            if sa["r_squared"] is not None:
                print(f"           R²: {sa['r_squared']}")

            # Distance to best
            if a_pos > 0:
                dist = haversine(sa["lat"], sa["lon"], best["lat"], best["lon"])
                print(f"           Distance to KEEP: {dist:.2f} km")

    print("\n" + "=" * 100)
    print(f"SUMMARY: {len(clusters)} duplicate clusters, {total_to_delete} stations to delete")
    print("=" * 100)

    if delete_names:
        print("\nStations to DELETE (one per line):")
        for name in sorted(delete_names):
            print(f"  {name}")


if __name__ == "__main__":
    main()
