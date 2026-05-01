#!/usr/bin/env python3
# -*- coding: iso-8859-1 -*-
"""Phase 1: Within-file duplicate detector for UTide harmonics files.

READ-ONLY: produces a review CSV with candidate duplicates and recommendations.
Does NOT modify any harmonics files.

Hard-Rules (no dup):
  * descriptive parens: Binnenpegel, Aussenpegel, Unterwasser, Oberwasser,
    outer, inner, entrance, in/out, upper/lower
  * depth markers: (depth NN ft), (depth NN m), (bin N), (layer N)
  * different countries
  * different parenthetical disambiguators that differ between candidates

Detection:
  * normalised name (lower, ASCII fold, parens stripped) match
  * Haversine distance < 200 m

Recommendation hierarchy (Plan v2, sec 4):
  1. Source-quality override (none applicable within single UTide file)
  2. Data quality: period length, frequency, recency
  3. Tie-breakers: constituent count, RMS
  4. Hard-rules: keep all if hit
"""

import argparse
import csv
import math
import os
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

ENCODING = "iso-8859-1"

# Hard-rule regex patterns: if matched in EITHER candidate, treat as distinct
HARD_RULE_PATTERNS = [
    (r"\(\s*depth\s+\d+(\.\d+)?\s*(ft|m|meter|meters)\s*\)", "depth"),
    (r"\(\s*bin\s+\d+\s*\)", "bin"),
    (r"\(\s*layer\s+\d+\s*\)", "layer"),
    (r"\bbinnenpegel\b", "binnenpegel"),
    (r"\baussenpegel\b", "aussenpegel"),
    (r"\bau[ss]enpegel\b", "aussenpegel"),
    (r"\bunterwasser\b", "unterwasser"),
    (r"\boberwasser\b", "oberwasser"),
    (r"\bouter\b", "outer"),
    (r"\binner\b", "inner"),
    (r"\bentrance\b", "entrance"),
]
HARD_RULE_RES = [(re.compile(p, re.IGNORECASE), tag) for p, tag in HARD_RULE_PATTERNS]


@dataclass
class Station:
    name: str
    lat: float
    lon: float
    country: str = ""
    province: str = ""
    source: str = ""
    station_id_context: str = ""
    datum: str = ""
    confidence: str = ""
    date_imported: str = ""
    # UTide stats (from comment block above HOT COMMENTS)
    utide_data_points: int = 0
    utide_period_start: str = ""
    utide_period_end: str = ""
    utide_r2: float = 0.0
    utide_rms_error: float = 0.0
    utide_constituents: int = 0
    # bookkeeping
    line_index: int = 0  # 0-based block index in file (for stable refs)


def parse_file(path: Path):
    """Parse all stations from a UTide harmonics file. Returns list of Station."""
    text = path.read_text(encoding=ENCODING)
    lines = text.split("\n")

    stations = []
    i = 0
    n = len(lines)
    block_idx = 0

    # find each "# BEGIN HOT COMMENTS" and walk backwards/forwards
    while i < n:
        if lines[i].strip() == "# BEGIN HOT COMMENTS":
            # backwards: scan up to ~15 lines for utide stats block
            stats = {}
            j = i - 1
            while j >= 0 and j > i - 30:
                line = lines[j]
                m = re.match(r"#\s*using\s+UTide.*?\bwith\s+(\d+)\s+(?:observations|data points)", line)
                if m:
                    stats["data_points"] = int(m.group(1))
                m = re.match(r"#\s*from\s+(\d{4}-\d{2}-\d{2})\s+to\s+(\d{4}-\d{2}-\d{2})", line)
                if m:
                    stats["period_start"] = m.group(1)
                    stats["period_end"] = m.group(2)
                m = re.match(r"#\s*R\^?2\s*=\s*([\d.]+),\s*RMS\s+error\s*=\s*([\d.]+)\s*m", line)
                if m:
                    stats["r2"] = float(m.group(1))
                    stats["rms_error"] = float(m.group(2))
                m = re.match(r"#\s*Constituents analy[sz]ed:\s*(\d+)", line)
                if m:
                    stats["constituents"] = int(m.group(1))
                j -= 1

            # forwards: parse HOT COMMENTS block
            hot = {}
            k = i + 1
            while k < n and lines[k].startswith("#"):
                line = lines[k]
                m = re.match(r"#\s*([A-Za-z_][A-Za-z0-9_ ]*?)\s*:\s*(.*)$", line)
                if m:
                    key = m.group(1).strip().lower().replace(" ", "_")
                    val = m.group(2).strip()
                    hot[key] = val
                m = re.match(r"#\s*!\s*([A-Za-z_]+)\s*:\s*(.*)$", line)
                if m:
                    key = "!" + m.group(1).strip().lower()
                    val = m.group(2).strip()
                    hot[key] = val
                k += 1

            # next non-comment line should be station name
            while k < n and (lines[k].strip() == "" or lines[k].startswith("#")):
                k += 1
            if k >= n:
                break
            name = lines[k].strip()

            try:
                lat = float(hot.get("!latitude", "nan"))
                lon = float(hot.get("!longitude", "nan"))
            except ValueError:
                lat = float("nan")
                lon = float("nan")

            st = Station(
                name=name,
                lat=lat,
                lon=lon,
                country=hot.get("country", ""),
                province=hot.get("province", ""),
                source=hot.get("source", ""),
                station_id_context=hot.get("station_id_context", ""),
                datum=hot.get("datum", ""),
                confidence=hot.get("confidence", ""),
                date_imported=hot.get("date_imported", ""),
                utide_data_points=stats.get("data_points", 0),
                utide_period_start=stats.get("period_start", ""),
                utide_period_end=stats.get("period_end", ""),
                utide_r2=stats.get("r2", 0.0),
                utide_rms_error=stats.get("rms_error", 0.0),
                utide_constituents=stats.get("constituents", 0),
                line_index=block_idx,
            )
            stations.append(st)
            block_idx += 1
            i = k + 1
        else:
            i += 1

    return stations


def normalise_name(name: str) -> str:
    """Lower, ASCII fold, strip parentheticals and trailing country/province."""
    s = name.lower()
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"\([^)]*\)", " ", s)  # strip everything in parens
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    parts = [p for p in s.split() if p]
    # also strip very short tokens that are just country abbreviations
    return " ".join(parts).strip()


def haversine_m(lat1, lon1, lat2, lon2) -> float:
    """Distance in metres."""
    R = 6371000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlmb / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def parens_set(name: str) -> frozenset:
    """Return parenthetical content tokens (lowercased) for a name."""
    bits = re.findall(r"\(([^)]*)\)", name.lower())
    return frozenset(b.strip() for b in bits)


def hard_rule_hit(name: str):
    """If name matches a hard-rule pattern, return tag, else None."""
    for rx, tag in HARD_RULE_RES:
        if rx.search(name):
            return tag
    return None


def is_distinct_by_hard_rules(a: Station, b: Station):
    """If hard-rules say A and B are distinct stations (not duplicates), return reason str. Else None."""
    if a.country and b.country and a.country != b.country:
        return f"different country: {a.country} vs {b.country}"
    a_tag = hard_rule_hit(a.name)
    b_tag = hard_rule_hit(b.name)
    if a_tag != b_tag:
        return f"hard-rule asymmetric: A={a_tag or '-'}, B={b_tag or '-'}"
    if a_tag and b_tag:
        # both hit — only distinct if the parenthetical content differs
        pa = parens_set(a.name)
        pb = parens_set(b.name)
        if pa != pb:
            return f"both hard-rule '{a_tag}' but different parens: {sorted(pa)} vs {sorted(pb)}"
    # parenthetical disambiguators differ at all (e.g. "Brest" vs "Brest (Inner Harbour)")
    pa = parens_set(a.name)
    pb = parens_set(b.name)
    if pa and pb and pa != pb:
        return f"different parens: {sorted(pa)} vs {sorted(pb)}"
    if (pa and not pb) or (pb and not pa):
        return f"only one has parens: A={sorted(pa)} B={sorted(pb)}"
    return None


def period_days(s: Station) -> int:
    if not s.utide_period_start or not s.utide_period_end:
        return 0
    try:
        a = date.fromisoformat(s.utide_period_start)
        b = date.fromisoformat(s.utide_period_end)
        return (b - a).days
    except ValueError:
        return 0


def freq_per_day(s: Station) -> float:
    d = period_days(s)
    if d <= 0 or s.utide_data_points <= 0:
        return 0.0
    return s.utide_data_points / d


def recommend(a: Station, b: Station, today: date) -> tuple[str, str]:
    """Return (KEEP_A | KEEP_B | REVIEW, reason)."""
    da = period_days(a)
    db = period_days(b)
    fa = freq_per_day(a)
    fb = freq_per_day(b)

    # Recency override (Plan v2 K5)
    end_a = date.fromisoformat(a.utide_period_end) if a.utide_period_end else None
    end_b = date.fromisoformat(b.utide_period_end) if b.utide_period_end else None
    if end_a and end_b:
        age_a_yr = (today - end_a).days / 365.25
        age_b_yr = (today - end_b).days / 365.25
        if abs(age_a_yr - age_b_yr) > 15 and max(age_a_yr, age_b_yr) > 30:
            if age_a_yr < age_b_yr:
                return ("KEEP_A", f"recency override: A ends {end_a} (age {age_a_yr:.0f}y) vs B ends {end_b} (age {age_b_yr:.0f}y)")
            else:
                return ("KEEP_B", f"recency override: B ends {end_b} (age {age_b_yr:.0f}y) vs A ends {end_a} (age {age_a_yr:.0f}y)")

    # Period length (>= 19 yr threshold)
    yr_a = da / 365.25
    yr_b = db / 365.25
    nodal = 19.0
    if yr_a >= nodal and yr_b < nodal:
        return ("KEEP_A", f"period: A={yr_a:.1f}y >=19 nodal, B={yr_b:.1f}y")
    if yr_b >= nodal and yr_a < nodal:
        return ("KEEP_B", f"period: B={yr_b:.1f}y >=19 nodal, A={yr_a:.1f}y")
    if yr_a >= nodal and yr_b >= nodal:
        if abs(yr_a - yr_b) > 5:
            if yr_a > yr_b:
                return ("KEEP_A", f"period: A={yr_a:.1f}y > B={yr_b:.1f}y (>5y diff, both >=19)")
            return ("KEEP_B", f"period: B={yr_b:.1f}y > A={yr_a:.1f}y (>5y diff, both >=19)")

    # Frequency (higher = better at equal period)
    if fa > 0 and fb > 0 and abs(yr_a - yr_b) < 1.0:
        if fa / max(fb, 1e-9) > 1.5:
            return ("KEEP_A", f"frequency: A={fa:.1f}/d > B={fb:.1f}/d")
        if fb / max(fa, 1e-9) > 1.5:
            return ("KEEP_B", f"frequency: B={fb:.1f}/d > A={fa:.1f}/d")

    # Tie-breakers: constituent count
    if a.utide_constituents and b.utide_constituents:
        if a.utide_constituents - b.utide_constituents >= 5:
            return ("KEEP_A", f"constituents: A={a.utide_constituents} > B={b.utide_constituents}")
        if b.utide_constituents - a.utide_constituents >= 5:
            return ("KEEP_B", f"constituents: B={b.utide_constituents} > A={a.utide_constituents}")

    # RMS (smaller = better)
    if a.utide_rms_error > 0 and b.utide_rms_error > 0:
        if abs(yr_a - yr_b) < 1.0:
            if b.utide_rms_error / max(a.utide_rms_error, 1e-12) > 1.3:
                return ("KEEP_A", f"rms: A={a.utide_rms_error}m < B={b.utide_rms_error}m")
            if a.utide_rms_error / max(b.utide_rms_error, 1e-12) > 1.3:
                return ("KEEP_B", f"rms: B={b.utide_rms_error}m < A={a.utide_rms_error}m")

    return ("REVIEW", f"too close to call: A={yr_a:.1f}y/{a.utide_constituents}c/{a.utide_rms_error}m B={yr_b:.1f}y/{b.utide_constituents}c/{b.utide_rms_error}m")


def find_dups_in_file(stations: list, max_dist_m: float = 200.0):
    """Group stations into dup-candidate pairs."""
    groups = []
    n = len(stations)
    seen_pair = set()
    # bucket by normalised name
    by_norm = {}
    for s in stations:
        key = normalise_name(s.name)
        by_norm.setdefault(key, []).append(s)
    for key, lst in by_norm.items():
        if len(lst) < 2:
            continue
        # within same normalised name: check all pairs
        for i in range(len(lst)):
            for j in range(i + 1, len(lst)):
                a, b = lst[i], lst[j]
                pid = (a.line_index, b.line_index)
                if pid in seen_pair:
                    continue
                seen_pair.add(pid)
                if math.isnan(a.lat) or math.isnan(b.lat):
                    dist = float("nan")
                else:
                    dist = haversine_m(a.lat, a.lon, b.lat, b.lon)
                if not math.isnan(dist) and dist > max_dist_m:
                    continue
                groups.append((a, b, dist))
    return groups


def write_csv(out_path: Path, rows):
    fieldnames = [
        "file", "group", "decision", "reason", "distance_m",
        "A_idx", "A_name", "A_lat", "A_lon", "A_country", "A_province",
        "A_source", "A_station_id_context", "A_period_start", "A_period_end",
        "A_data_points", "A_constituents", "A_r2", "A_rms_error",
        "B_idx", "B_name", "B_lat", "B_lon", "B_country", "B_province",
        "B_source", "B_station_id_context", "B_period_start", "B_period_end",
        "B_data_points", "B_constituents", "B_r2", "B_rms_error",
    ]
    with out_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def process_file(path: Path, today: date):
    stations = parse_file(path)
    pairs = find_dups_in_file(stations)
    rows = []
    for gi, (a, b, dist) in enumerate(pairs):
        hard = is_distinct_by_hard_rules(a, b)
        if hard:
            decision, reason = "KEEP_BOTH", f"hard-rule: {hard}"
        else:
            decision, reason = recommend(a, b, today)
        rows.append({
            "file": path.name,
            "group": gi,
            "decision": decision,
            "reason": reason,
            "distance_m": f"{dist:.1f}" if not math.isnan(dist) else "",
            "A_idx": a.line_index, "A_name": a.name, "A_lat": a.lat, "A_lon": a.lon,
            "A_country": a.country, "A_province": a.province, "A_source": a.source,
            "A_station_id_context": a.station_id_context,
            "A_period_start": a.utide_period_start, "A_period_end": a.utide_period_end,
            "A_data_points": a.utide_data_points, "A_constituents": a.utide_constituents,
            "A_r2": a.utide_r2, "A_rms_error": a.utide_rms_error,
            "B_idx": b.line_index, "B_name": b.name, "B_lat": b.lat, "B_lon": b.lon,
            "B_country": b.country, "B_province": b.province, "B_source": b.source,
            "B_station_id_context": b.station_id_context,
            "B_period_start": b.utide_period_start, "B_period_end": b.utide_period_end,
            "B_data_points": b.utide_data_points, "B_constituents": b.utide_constituents,
            "B_r2": b.utide_r2, "B_rms_error": b.utide_rms_error,
        })
    return stations, rows


def main():
    ap = argparse.ArgumentParser(description="Find within-file duplicates in UTide harmonics")
    ap.add_argument("paths", nargs="+", help="Files or globs to scan")
    ap.add_argument("--out", default="/home/oliver/harmonics/help/within_file_dups",
                    help="Output directory for review CSVs")
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    today = date.today()

    files = []
    for p in args.paths:
        path = Path(p)
        if path.is_file():
            files.append(path)
        else:
            files.extend(sorted(Path("/home/oliver/harmonics/utide").glob(p)))

    grand_rows = []
    file_summary = []
    for path in files:
        stations, rows = process_file(path, today)
        n_pairs = len(rows)
        n_keep_both = sum(1 for r in rows if r["decision"] == "KEEP_BOTH")
        n_review = sum(1 for r in rows if r["decision"] == "REVIEW")
        n_act = sum(1 for r in rows if r["decision"] in ("KEEP_A", "KEEP_B"))
        file_summary.append({
            "file": path.name,
            "stations": len(stations),
            "pair_candidates": n_pairs,
            "hard_rule_keep_both": n_keep_both,
            "auto_decision": n_act,
            "review": n_review,
        })
        grand_rows.extend(rows)
        print(f"{path.name}: {len(stations)} stations, {n_pairs} candidate pairs "
              f"(keep_both={n_keep_both}, auto={n_act}, review={n_review})")

    out_csv = out_dir / "candidates.csv"
    write_csv(out_csv, grand_rows)
    print(f"\nWrote {out_csv}  ({len(grand_rows)} rows)")

    out_summary = out_dir / "summary.csv"
    with out_summary.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(file_summary[0].keys()) if file_summary else
                           ["file", "stations", "pair_candidates", "hard_rule_keep_both", "auto_decision", "review"])
        w.writeheader()
        for r in file_summary:
            w.writerow(r)
    print(f"Wrote {out_summary}")


if __name__ == "__main__":
    main()
