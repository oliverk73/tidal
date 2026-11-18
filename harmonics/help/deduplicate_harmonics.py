#!/usr/bin/env python3
"""
Deduplicate harmonics TXT files across all sources.

Modes:
  --dry-run  (default)  Generate ODS report with KEEP/DELETE/REVIEW recommendations
  --apply               Delete only stations marked DELETE (REVIEW untouched)
  --apply-all           Delete stations marked DELETE and REVIEW-DELETE
"""

import os
import sys
import re
import math
import unicodedata
import tempfile
from collections import defaultdict
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

HARMONICS_DIR = Path("/home/oliver/harmonics")
SUBDIRS = ["classic", "ihm", "utide", "ticon"]

# File priority: higher number = better source, wins in duplicate groups
FILE_PRIORITY = {
    # Rank 1 — NOAA, brand new (US only)
    "harmonics-dwf-20251228-free.txt": 100,
    # Rank 2 — Official Spanish ports
    "harmonics_puertos_spain.txt": 90,
    # Rank 3 — Own UTide analysis with recent data
    "harmonics_utide_germany_z0corrected.txt": 80,
    "harmonics_utide_france.txt": 80,
    "harmonics_utide_netherlands.txt": 80,
    "harmonics_utide_belgium.txt": 80,
    "harmonics_utide_uk_bodc.txt": 80,
    "harmonics_utide_uk_ireland.txt": 80,
    "harmonics_utide_ireland.txt": 80,
    "harmonics_utide_canada_all.txt": 80,
    "harmonics_utide_australia.txt": 80,
    "harmonics_utide_australia_qld.txt": 80,
    "harmonics_utide_australia_uhslc.txt": 80,
    "harmonics_utide_denmark.txt": 80,
    # Rank 4 — TICON-4 global
    "harmonics_ticon4_worldwide.txt": 70,
    # Rank 5 — DWF older collections
    "harmonics-dwf-20070318_mod.txt": 60,
    "harmonics-dwf-20100529-nonfree_mod.txt": 60,
    # Rank 6 — Pierre Lavergne
    "harmonics-pierre-lavergne-v10_mod.txt": 50,
    "harmonics-pierre-lavergne-v9-europe_mod.txt": 50,
    # Rank 7 — Classic 2004
    "harmonics-2004-06-14_mod.txt": 30,
    # Rank 8 — Classic 1997
    "harmonics-1997-05-25_mod.txt": 10,
}

# Between these priorities, always REVIEW (never auto-DELETE)
REVIEW_MIN_PRIORITY = 60   # DWF-2007/2010
REVIEW_MAX_PRIORITY = 80   # UTide

# Descriptive words that mark genuinely different measurement stations
DESCRIPTIVE_WORDS = {
    "binnenpegel", "aussenpegel", "außenpegel",
    "oberwasser", "unterwasser",
    "entrance", "inner", "outer", "upper", "lower",
    "offshore", "upstream", "downstream",
    "voorhaven", "buitenhaven", "binnenhaven",
}

# Known country names (lowercase) for stripping from station names
KNOWN_COUNTRIES = {
    "germany", "france", "netherlands", "belgium", "spain", "portugal",
    "united kingdom", "ireland", "norway", "sweden", "denmark", "finland",
    "iceland", "croatia", "slovenia", "italy", "greece", "turkey",
    "brazil", "argentina", "chile", "peru", "colombia", "venezuela",
    "mexico", "el salvador", "panama", "costa rica", "honduras",
    "china", "japan", "south korea", "taiwan", "philippines", "vietnam",
    "india", "indonesia", "malaysia", "thailand", "myanmar", "bangladesh",
    "australia", "new zealand", "fiji", "samoa",
    "nigeria", "cameroon", "ghana", "ivory coast", "mozambique",
    "south africa", "kenya", "tanzania", "madagascar", "mauritius",
    "canada", "curacao", "maldives", "mauritania", "seychelles",
    "egypt", "israel", "iran", "saudi arabia", "oman", "uae",
    "russia", "ukraine", "poland", "romania", "bulgaria",
    "caribbean netherlands", "bermuda", "bahamas", "jamaica",
    "trinidad and tobago", "barbados", "grenada",
    "singapore", "hong kong", "macau",
    "united states", "usa",
    "wales", "england", "scotland", "northern ireland",
    "brittany", "normandy",
}


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def parse_harmonics_file(filepath):
    """Parse a TXT harmonics file, return list of station dicts."""
    with open(filepath, "r", encoding="iso-8859-1") as f:
        lines = f.readlines()

    # Find number of constituents
    num_const = 0
    for i, line in enumerate(lines):
        if "# Number of constituents" in line:
            for j in range(i + 1, min(i + 5, len(lines))):
                stripped = lines[j].strip().lstrip("# ")
                if stripped.isdigit():
                    num_const = int(stripped)
                    break
            break

    if num_const == 0:
        print(f"  WARNUNG: Keine Constituent-Anzahl in {filepath}")
        return []

    basename = os.path.basename(filepath)
    stations = []

    # Find all latitude markers
    lat_indices = []
    for i, line in enumerate(lines):
        if line.strip().startswith("# !latitude:"):
            lat_indices.append(i)

    for idx_pos, lat_idx in enumerate(lat_indices):
        try:
            lat = float(lines[lat_idx].split(":", 1)[1].strip())
        except (ValueError, IndexError):
            continue

        # Find longitude (scan backward up to 15 lines)
        lon = None
        for j in range(max(0, lat_idx - 15), lat_idx):
            if lines[j].strip().startswith("# !longitude:"):
                try:
                    lon = float(lines[j].split(":", 1)[1].strip())
                except (ValueError, IndexError):
                    pass
        if lon is None:
            continue

        # Find station name: first non-comment, non-empty line after latitude
        name_idx = lat_idx + 1
        while name_idx < len(lines) and (
            lines[name_idx].strip().startswith("#") or not lines[name_idx].strip()
        ):
            name_idx += 1
        if name_idx >= len(lines):
            continue

        name = lines[name_idx].rstrip("\n\r")

        # Block end: name + tz + datum + N constituents
        block_end = name_idx + 3 + num_const
        if block_end > len(lines):
            continue

        # Block start: scan backward from longitude line
        lon_idx = lat_idx
        for j in range(max(0, lat_idx - 15), lat_idx):
            if lines[j].strip().startswith("# !longitude:"):
                lon_idx = j
                break

        block_start = lon_idx
        while block_start > 0:
            prev = lines[block_start - 1]
            if prev.startswith("#") or not prev.strip():
                block_start -= 1
            else:
                break
        # Don't overlap with previous station
        if stations:
            prev_end = stations[-1]["block_end"]
            if block_start < prev_end:
                block_start = prev_end

        # Extract metadata from comment lines before station name
        confidence = None
        country = None
        for j in range(block_start, name_idx):
            line = lines[j]
            m = re.match(r"^#\s+confidence:\s*(\d+)", line)
            if m:
                confidence = int(m.group(1))
            m = re.match(r"^#\s+country:\s*(.+)", line)
            if m:
                country = m.group(1).strip()

        # Post-constituent comments (R², RMS, observations)
        rms = r2 = observations = obs_start = obs_end = const_analyzed = None
        post_start = block_end
        if idx_pos + 1 < len(lat_indices):
            post_limit = lat_indices[idx_pos + 1]
        else:
            post_limit = len(lines)
        # Only scan the first ~20 comment lines after constituents
        for j in range(post_start, min(post_start + 20, post_limit)):
            if j >= len(lines):
                break
            line = lines[j]
            if not line.startswith("#"):
                break
            m = re.search(r"R\^2\s*=\s*([\d.]+)", line)
            if m:
                r2 = float(m.group(1))
            m = re.search(r"RMS error\s*=\s*([\d.]+)", line)
            if m:
                rms = float(m.group(1))
            m = re.search(r"(?:using|with)\s+(\d+)\s+observations", line)
            if m:
                observations = int(m.group(1))
            m = re.search(r"from\s+(\d{4}-\d{2}-\d{2})\s+to\s+(\d{4}-\d{2}-\d{2})", line)
            if m:
                obs_start = m.group(1)
                obs_end = m.group(2)
            m = re.match(r"^#\s+Constituents analyzed:\s*(\d+)", line)
            if m:
                const_analyzed = int(m.group(1))

        # Count used constituents (amplitude > 0)
        const_used = 0
        for j in range(name_idx + 3, name_idx + 3 + num_const):
            if j < len(lines):
                parts = lines[j].strip().split()
                if len(parts) >= 2:
                    try:
                        if float(parts[-2]) > 0:
                            const_used += 1
                    except ValueError:
                        pass

        stations.append({
            "name": name,
            "lat": lat,
            "lon": lon,
            "file": basename,
            "filepath": str(filepath),
            "country": country,
            "confidence": confidence,
            "r2": r2,
            "rms": rms,
            "observations": observations,
            "obs_start": obs_start,
            "obs_end": obs_end,
            "const_analyzed": const_analyzed,
            "const_used": const_used,
            "block_start": block_start,
            "block_end": block_end,
            "priority": FILE_PRIORITY.get(basename, 0),
        })

    return stations


# ---------------------------------------------------------------------------
# Name normalization
# ---------------------------------------------------------------------------

def strip_accents(s):
    """Remove accents from a string."""
    nfkd = unicodedata.normalize("NFD", s)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def normalize_name(name):
    """Normalize station name for duplicate comparison."""
    n = name.strip()
    # Remove (2), (3) etc. at end
    n = re.sub(r"\s*\(\d+\)\s*$", "", n)
    # Strip accents and lowercase
    n = strip_accents(n)
    n = n.lower()
    # Resolve abbreviations at word boundaries
    n = re.sub(r"\bbp\b", "binnenpegel", n)
    n = re.sub(r"\bap\b", "aussenpegel", n)
    # Remove country suffix
    parts = [p.strip() for p in n.split(",")]
    if len(parts) > 1 and parts[-1] in KNOWN_COUNTRIES:
        parts = parts[:-1]
    n = ", ".join(parts)
    # Normalize whitespace and hyphens
    n = re.sub(r"[\s-]+", " ", n).strip()
    return n


def get_word_set(name):
    """Get set of significant words from a normalized name.
    Preserves numbers to distinguish depth/measurement variants."""
    clean = re.sub(r"[(),]", " ", name)
    return {w for w in clean.lower().split() if len(w) > 1 or w.isdigit()}


def has_descriptive_suffix(name):
    """Check if name contains a descriptive suffix."""
    lower = strip_accents(name).lower()
    return any(word in lower for word in DESCRIPTIVE_WORDS)


def get_descriptive_parts(name):
    """Extract descriptive parts that distinguish measurement points.
    Uses normalized name to catch abbreviations like BP→Binnenpegel."""
    norm = normalize_name(name)
    return frozenset(w for w in DESCRIPTIVE_WORDS if w in norm)


def extract_base_name(normalized_name):
    """Extract base name (before first parenthesis or comma)."""
    n = re.sub(r"\s*\([^)]*\)", "", normalized_name)
    return n.split(",")[0].strip()


# ---------------------------------------------------------------------------
# Geographic distance
# ---------------------------------------------------------------------------

def haversine_km(lat1, lon1, lat2, lon2):
    """Haversine distance in kilometers."""
    R = 6371.0
    rlat1, rlat2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(rlat1) * math.cos(rlat2) * math.sin(dlon / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def levenshtein_ratio(s1, s2):
    """Levenshtein similarity ratio (0..1)."""
    max_len = max(len(s1), len(s2))
    if max_len == 0:
        return 1.0
    m, n = len(s1), len(s2)
    dp = list(range(n + 1))
    for i in range(1, m + 1):
        prev = dp[0]
        dp[0] = i
        for j in range(1, n + 1):
            tmp = dp[j]
            if s1[i - 1] == s2[j - 1]:
                dp[j] = prev
            else:
                dp[j] = 1 + min(prev, dp[j], dp[j - 1])
            prev = tmp
    return 1.0 - dp[n] / max_len


# ---------------------------------------------------------------------------
# Duplicate detection
# ---------------------------------------------------------------------------

def find_duplicates(all_stations):
    """Find duplicate groups. Returns list of groups (each a list of station dicts)."""
    groups = []
    grouped = set()  # indices of already-grouped stations

    # --- Stufe 1: Name match ---
    name_map = defaultdict(list)
    for i, st in enumerate(all_stations):
        norm = normalize_name(st["name"])
        name_map[norm].append(i)

    for norm_name, indices in name_map.items():
        if len(indices) < 2:
            continue
        # Sub-group by descriptive parts (Binnenpegel ≠ Außenpegel)
        desc_groups = defaultdict(list)
        for idx in indices:
            desc = get_descriptive_parts(all_stations[idx]["name"])
            desc_groups[desc].append(idx)

        for desc_indices in desc_groups.values():
            if len(desc_indices) < 2:
                continue
            group = [all_stations[i].copy() for i in desc_indices]
            for st in group:
                st["match_type"] = "Name"
                st["distance_km"] = 0.0
            groups.append(group)
            grouped.update(desc_indices)

    # Word-set match (catches reordered names)
    ungrouped_data = {}
    for i, st in enumerate(all_stations):
        if i not in grouped:
            norm = normalize_name(st["name"])
            ungrouped_data[i] = (norm, get_word_set(norm), extract_base_name(norm))

    wordset_map = defaultdict(list)
    for i, (norm, ws, base) in ungrouped_data.items():
        if len(ws) >= 2:  # Avoid false matches on single-word names
            key = frozenset(ws)
            wordset_map[key].append(i)

    for key, indices in wordset_map.items():
        if len(indices) < 2:
            continue
        desc_groups = defaultdict(list)
        for idx in indices:
            desc = get_descriptive_parts(all_stations[idx]["name"])
            desc_groups[desc].append(idx)

        for desc_indices in desc_groups.values():
            if len(desc_indices) < 2:
                continue
            group = [all_stations[i].copy() for i in desc_indices]
            for st in group:
                st["match_type"] = "Name (Wortmatch)"
                st["distance_km"] = 0.0
            groups.append(group)
            grouped.update(desc_indices)

    # --- Stufe 2: Coordinate match (<1 km) ---
    ungrouped = [(i, all_stations[i]) for i in range(len(all_stations)) if i not in grouped]

    # Spatial grid
    grid = defaultdict(list)
    for i, st in ungrouped:
        gx = int(st["lat"] * 10)
        gy = int(st["lon"] * 10)
        grid[(gx, gy)].append((i, st))

    coord_pairs = []
    for i, st in ungrouped:
        gx = int(st["lat"] * 10)
        gy = int(st["lon"] * 10)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for j, st2 in grid[(gx + dx, gy + dy)]:
                    if j <= i:
                        continue

                    # Depth-qualified stations (tidal currents at different depths)
                    # are always distinct — never match them by coordinates
                    HAS_DEPTH = re.compile(r"\(depth\s+\d+", re.IGNORECASE)
                    if HAS_DEPTH.search(st["name"]) or HAS_DEPTH.search(st2["name"]):
                        continue

                    dist = haversine_km(st["lat"], st["lon"], st2["lat"], st2["lon"])
                    if dist > 1.0:
                        continue

                    # Different descriptive suffixes → different stations
                    desc1 = get_descriptive_parts(st["name"])
                    desc2 = get_descriptive_parts(st2["name"])
                    if desc1 and desc2 and desc1 != desc2:
                        continue

                    norm1 = normalize_name(st["name"])
                    norm2 = normalize_name(st2["name"])
                    base1 = extract_base_name(norm1)
                    base2 = extract_base_name(norm2)

                    if base1 == base2:
                        coord_pairs.append((i, j, dist))
                    elif dist < 0.5 and levenshtein_ratio(base1, base2) > 0.8:
                        coord_pairs.append((i, j, dist))

    # Union-find to merge coordinate pairs into groups
    parent = {}

    def find(x):
        while parent.get(x, x) != x:
            parent[x] = parent.get(parent[x], parent[x])
            x = parent[x]
        return x

    def union(x, y):
        px, py = find(x), find(y)
        if px != py:
            parent[px] = py

    for i, j, dist in coord_pairs:
        union(i, j)

    coord_groups = defaultdict(set)
    for i, j, dist in coord_pairs:
        root = find(i)
        coord_groups[root].add(i)
        coord_groups[root].add(j)

    for root, indices in coord_groups.items():
        group = []
        for idx in sorted(indices):
            st = all_stations[idx].copy()
            st["match_type"] = "Koordinate"
            min_dist = min(
                haversine_km(st["lat"], st["lon"],
                             all_stations[other]["lat"], all_stations[other]["lon"])
                for other in indices if other != idx
            )
            st["distance_km"] = min_dist
            group.append(st)
        groups.append(group)
        grouped.update(indices)

    return groups


# ---------------------------------------------------------------------------
# Action assignment
# ---------------------------------------------------------------------------

def assign_actions(groups):
    """Assign KEEP/DELETE/REVIEW to each station in each group."""
    for group in groups:
        group.sort(key=lambda s: s["priority"], reverse=True)
        group[0]["action"] = "KEEP"

        best_priority = group[0]["priority"]

        for st in group[1:]:
            p = st["priority"]

            # Coordinate-only match → always REVIEW
            if st["match_type"].startswith("Koordinate"):
                st["action"] = "REVIEW"
                continue

            # Both priorities in review range (60–80) → REVIEW
            if (REVIEW_MIN_PRIORITY <= best_priority <= REVIEW_MAX_PRIORITY and
                    REVIEW_MIN_PRIORITY <= p <= REVIEW_MAX_PRIORITY):
                st["action"] = "REVIEW"
                continue

            # Same priority → REVIEW
            if p == best_priority:
                st["action"] = "REVIEW"
                continue

            # Clear priority difference → DELETE
            st["action"] = "DELETE"


# ---------------------------------------------------------------------------
# ODS Report
# ---------------------------------------------------------------------------

def generate_ods_report(groups, output_path):
    """Generate ODS spreadsheet with duplicate report."""
    from odf.opendocument import OpenDocumentSpreadsheet
    from odf.table import Table, TableColumn, TableRow, TableCell
    from odf.text import P
    from odf.style import Style, TextProperties, TableColumnProperties, TableCellProperties

    doc = OpenDocumentSpreadsheet()

    header_style = Style(name="header", family="table-cell")
    header_style.addElement(TextProperties(fontweight="bold", fontsize="10pt", color="#ffffff"))
    header_style.addElement(TableCellProperties(
        backgroundcolor="#4472C4", padding="0.05cm", border="0.05pt solid #000000"))
    doc.automaticstyles.addElement(header_style)

    keep_style = Style(name="keep", family="table-cell")
    keep_style.addElement(TableCellProperties(
        backgroundcolor="#c6efce", border="0.05pt solid #cccccc"))
    doc.automaticstyles.addElement(keep_style)

    delete_style = Style(name="delete", family="table-cell")
    delete_style.addElement(TableCellProperties(
        backgroundcolor="#ffc7ce", border="0.05pt solid #cccccc"))
    doc.automaticstyles.addElement(delete_style)

    review_style = Style(name="review", family="table-cell")
    review_style.addElement(TableCellProperties(
        backgroundcolor="#ffeb9c", border="0.05pt solid #cccccc"))
    doc.automaticstyles.addElement(review_style)

    widths = ["1.2cm", "1.5cm", "6cm", "5cm", "3cm", "1.8cm", "1.8cm",
              "1.5cm", "2.8cm", "1.3cm", "1.3cm", "1.3cm", "1.8cm", "3.5cm"]
    col_styles = []
    for i, w in enumerate(widths):
        cs = Style(name=f"col{i}", family="table-column")
        cs.addElement(TableColumnProperties(columnwidth=w))
        doc.automaticstyles.addElement(cs)
        col_styles.append(cs)

    table = Table(name="Duplikate")
    for cs in col_styles:
        table.addElement(TableColumn(stylename=cs))

    headers = ["Gruppe", "Aktion", "Stationsname", "Datei", "Land",
               "Lat", "Lon", "Dist (km)", "Match-Typ",
               "Const.", "RMS", "Conf.", "Obs.", "Beob.-Zeitraum"]
    tr = TableRow()
    for h in headers:
        tc = TableCell(stylename=header_style)
        tc.addElement(P(text=h))
        tr.addElement(tc)
    table.addElement(tr)

    for group_nr, group in enumerate(groups, 1):
        for st in group:
            action = st.get("action", "?")
            style = {"KEEP": keep_style, "DELETE": delete_style}.get(action, review_style)

            obs_period = ""
            if st.get("obs_start"):
                obs_period = f"{st['obs_start']} – {st['obs_end']}"

            values = [
                str(group_nr),
                action,
                st["name"],
                st["file"],
                st.get("country") or "",
                f"{st['lat']:.4f}",
                f"{st['lon']:.4f}",
                f"{st.get('distance_km', 0):.3f}" if st.get("distance_km") else "",
                st.get("match_type", ""),
                str(st.get("const_used", "")),
                f"{st['rms']:.4f}" if st.get("rms") else "",
                str(st.get("confidence") or ""),
                f"{st['observations']:,}" if st.get("observations") else "",
                obs_period,
            ]

            tr = TableRow()
            for val in values:
                tc = TableCell(stylename=style)
                tc.addElement(P(text=val))
                tr.addElement(tc)
            table.addElement(tr)

    doc.spreadsheet.addElement(table)
    doc.save(output_path)


# ---------------------------------------------------------------------------
# Apply mode
# ---------------------------------------------------------------------------

def apply_deletions(groups, mode="apply"):
    """Delete station blocks from source files."""
    deletions = defaultdict(list)

    for group in groups:
        for st in group:
            action = st.get("action", "")
            if action == "DELETE":
                deletions[st["filepath"]].append(
                    (st["block_start"], st["block_end"], st["name"]))
            elif action == "REVIEW" and mode == "apply-all":
                deletions[st["filepath"]].append(
                    (st["block_start"], st["block_end"], st["name"]))

    for filepath, del_list in sorted(deletions.items()):
        basename = os.path.basename(filepath)
        with open(filepath, "r", encoding="iso-8859-1") as f:
            lines = f.readlines()

        original_count = sum(1 for l in lines if l.strip().startswith("# !latitude:"))
        del_list.sort(key=lambda x: x[0])

        skip = set()
        for start, end, name in del_list:
            for i in range(start, end):
                skip.add(i)

        new_lines = [l for i, l in enumerate(lines) if i not in skip]

        # Backup
        bak_path = filepath + ".bak"
        if not os.path.exists(bak_path):
            with open(filepath, "rb") as src:
                with open(bak_path, "wb") as dst:
                    dst.write(src.read())

        # Atomic write
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(filepath), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="iso-8859-1") as f:
                f.writelines(new_lines)
            os.replace(tmp, filepath)
        except Exception:
            os.unlink(tmp)
            raise

        new_count = sum(1 for l in new_lines if l.strip().startswith("# !latitude:"))
        deleted = len(del_list)
        print(f"  {basename}: {original_count} → {new_count} Stationen ({deleted} gelöscht)")

        if new_count != original_count - deleted:
            print(f"    WARNUNG: Erwartet {original_count - deleted}, aber {new_count}!")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    mode = "dry-run"
    if "--apply-all" in sys.argv:
        mode = "apply-all"
    elif "--apply" in sys.argv:
        mode = "apply"

    print(f"=== Harmonics Deduplizierung ({mode}) ===\n")

    all_stations = []
    for subdir in SUBDIRS:
        dirpath = HARMONICS_DIR / subdir
        if not dirpath.exists():
            continue
        for txt_file in sorted(dirpath.glob("*.txt")):
            basename = txt_file.name
            if basename.endswith(".bak"):
                continue
            if basename not in FILE_PRIORITY:
                print(f"  ÜBERSPRUNGEN (nicht in Prioritätsliste): {basename}")
                continue
            stations = parse_harmonics_file(txt_file)
            print(f"  {basename}: {len(stations)} Stationen")
            all_stations.extend(stations)

    print(f"\nGesamt: {len(all_stations)} Stationen\n")

    print("Suche Duplikate...")
    groups = find_duplicates(all_stations)
    assign_actions(groups)

    n_delete = sum(1 for g in groups for s in g if s.get("action") == "DELETE")
    n_review = sum(1 for g in groups for s in g if s.get("action") == "REVIEW")
    n_keep = sum(1 for g in groups for s in g if s.get("action") == "KEEP")

    print(f"\n{len(groups)} Duplikat-Gruppen gefunden:")
    print(f"  KEEP:   {n_keep}")
    print(f"  DELETE: {n_delete}")
    print(f"  REVIEW: {n_review}")

    report_path = str(HARMONICS_DIR / "help" / "duplicate_report.ods")
    print(f"\nErzeuge Report: {report_path}")
    generate_ods_report(groups, report_path)
    print("Report erstellt.")

    if mode in ("apply", "apply-all"):
        print(f"\n{'='*60}")
        print(f"LÖSCHE Stationen (Modus: {mode})")
        print(f"{'='*60}")
        apply_deletions(groups, mode)
        print("\nFertig. Bitte TCD und Marker manuell neu bauen.")
    else:
        print(f"\nDry-Run abgeschlossen. Report prüfen, dann mit --apply ausführen.")


if __name__ == "__main__":
    main()
