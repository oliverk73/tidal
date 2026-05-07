#!/usr/bin/env python3
"""Build harmonics/help/datum_overview.ods — overview of stations grouped by
country and source file with the declared chart datum / reference level.

Goal: identify which countries currently use mixed datums across sources,
so we can decide which official chart datum to standardize on per country.

Output: 3 sheets
  1. By country  — for each country: which sources contribute stations,
                   which datums are used, station counts.
  2. By source   — for each source file: total stations, distinct countries
                   and datums.
  3. Stations    — raw per-station list (country, source, datum, name).
"""
from __future__ import annotations

import os
import re
from collections import defaultdict
from pathlib import Path

from odf.opendocument import OpenDocumentSpreadsheet
from odf.style import Style, TableCellProperties, TextProperties, TableColumnProperties
from odf.table import Table, TableColumn, TableRow, TableCell
from odf.text import P

ROOT = Path("/home/oliver/harmonics")

# Each (file, source-name, country-source) tuple. country-source:
#   'block' = read from `# country:` line in HOT COMMENTS block
#   'name'  = parse from last comma-separated token in station name
#   'fixed=<X>' = always X (e.g. DWF-2025 has no country marker → 'USA')
#
# Edit-policy (see harmonics/help/datum_overview_summary.md):
#   - [CONTROLLED] — Maintained by us. All `*_mod.txt` files (the `_mod`
#                    suffix marks them as locally adjusted) plus our own
#                    UTide / TICON-4 / IHM imports.
#   - [EXTERNAL]   — Upstream may publish new versions. Do NOT modify;
#                    re-import on update. Currently: only DWF-2025.
SOURCES = [
    # [CONTROLLED]
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
    # [EXTERNAL] — NOAA / David Flater publishes updates; do NOT edit
    (ROOT / "classic" / "harmonics-dwf-20251228-free.txt", "DWF 2025", "fixed=USA"),
]


# US states / territories (any of these as last comma-token → USA)
US_STATES = {
    "Alabama", "Alaska", "Arizona", "Arkansas", "California", "Colorado",
    "Connecticut", "Delaware", "Florida", "Georgia", "Hawaii", "Idaho",
    "Illinois", "Indiana", "Iowa", "Kansas", "Kentucky", "Louisiana",
    "Maine", "Maryland", "Massachusetts", "Michigan", "Minnesota",
    "Mississippi", "Missouri", "Montana", "Nebraska", "Nevada",
    "New Hampshire", "New Jersey", "New Mexico", "New York",
    "North Carolina", "North Dakota", "Ohio", "Oklahoma", "Oregon",
    "Pennsylvania", "Rhode Island", "South Carolina", "South Dakota",
    "Tennessee", "Texas", "Utah", "Vermont", "Virginia", "Washington",
    "West Virginia", "Wisconsin", "Wyoming",
    "District of Columbia", "Puerto Rico", "U.S. Virgin Islands",
    "Guam", "American Samoa", "Northern Mariana Islands",
    "Midway Islands", "Pacific Ocean", "Wake Island",
}

# Canadian provinces / territories
CA_PROVINCES = {
    "Alberta", "British Columbia", "Manitoba", "New Brunswick",
    "Newfoundland and Labrador", "Newfoundland", "Nova Scotia",
    "Ontario", "Prince Edward Island", "Quebec", "Québec",
    "Saskatchewan", "Northwest Territories", "Nunavut", "Yukon",
}


def country_from_name(name: str) -> str:
    """Heuristic: last comma-token, with US-state and Canadian-province
    promotion to country. 'Honolulu, Hawaii' → 'USA'."""
    if "," not in name:
        return "Unknown"
    last = name.rsplit(",", 1)[-1].strip()
    # Strip ' Current' suffix that some current stations use
    last_clean = last.removesuffix(" Current").strip()
    if last_clean in US_STATES:
        return "USA"
    if last_clean in CA_PROVINCES:
        return "Canada"
    return last_clean or "Unknown"


def parse_blocks(path: Path, source_label: str, country_mode: str):
    """Yield dicts for each station: {country, datum, source, name}."""
    raw = path.read_bytes().decode("iso-8859-1", errors="replace")
    lines = raw.split("\n")

    block = {}
    in_hot = False
    fixed_country = None
    if country_mode.startswith("fixed="):
        fixed_country = country_mode.split("=", 1)[1]

    for i, line in enumerate(lines):
        if line.startswith("# BEGIN HOT COMMENTS"):
            in_hot = True
            block = {"country": None, "datum": None}
            continue
        if in_hot:
            if line.startswith("# country:"):
                block["country"] = line.split(":", 1)[1].strip()
            elif line.startswith("# datum:"):
                block["datum"] = line.split(":", 1)[1].strip()
            # Station name line ends the HOT COMMENTS section
            if (re.match(r"^[A-Z]", line) and not line.startswith("#")
                    and i + 1 < len(lines)
                    and re.match(r"^[+\-]\d{2}:\d{2}", lines[i+1])):
                # Resolve country
                if fixed_country:
                    country = fixed_country
                elif country_mode == "block" and block.get("country"):
                    country = block["country"]
                else:
                    country = country_from_name(line)
                yield {
                    "country": country.strip() or "Unknown",
                    "datum": (block.get("datum") or "(none)").strip(),
                    "source": source_label,
                    "name": line.strip(),
                }
                in_hot = False
                block = {}
        else:
            # Some classic files have no HOT COMMENTS — fall back to
            # reading station name line directly and inferring country from name.
            if (re.match(r"^[A-Z]", line) and not line.startswith("#")
                    and i + 1 < len(lines)
                    and re.match(r"^[+\-]\d{2}:\d{2}", lines[i+1])):
                if fixed_country:
                    country = fixed_country
                else:
                    country = country_from_name(line)
                yield {
                    "country": country.strip() or "Unknown",
                    "datum": "(none)",
                    "source": source_label,
                    "name": line.strip(),
                }


def collect():
    rows = []
    for path, label, mode in SOURCES:
        if not path.exists():
            print(f"  ⚠ skip (missing): {path}")
            continue
        n = 0
        for r in parse_blocks(path, label, mode):
            rows.append(r)
            n += 1
        print(f"  {label}: {n} stations")
    return rows


# --- ODS helpers ---

def _cell(text, *, bold=False, header=False, num=False):
    cell = TableCell()
    if num and isinstance(text, (int, float)):
        cell.setAttribute("valuetype", "float")
        cell.setAttribute("value", str(text))
    p = P()
    p.addText(str(text))
    cell.addElement(p)
    return cell


def _row(cells):
    r = TableRow()
    for c in cells:
        r.addElement(c)
    return r


def build_ods(rows, out_path: Path):
    doc = OpenDocumentSpreadsheet()

    # === Sheet 1: By country ===
    s1 = Table(name="By country")
    s1.addElement(TableColumn(numbercolumnsrepeated=5))
    s1.addElement(_row([
        _cell("Country"), _cell("Source"),
        _cell("# stations"), _cell("Datum(s) used"), _cell("# datums"),
    ]))
    by_cs_datum = defaultdict(lambda: defaultdict(int))  # (country,source) → {datum: count}
    for r in rows:
        by_cs_datum[(r["country"], r["source"])][r["datum"]] += 1
    for (country, source) in sorted(by_cs_datum.keys()):
        datum_counts = by_cs_datum[(country, source)]
        total = sum(datum_counts.values())
        datums = sorted(datum_counts.items(), key=lambda kv: -kv[1])
        datum_str = "; ".join(f"{d} ({c})" for d, c in datums)
        s1.addElement(_row([
            _cell(country), _cell(source),
            _cell(total), _cell(datum_str), _cell(len(datums)),
        ]))
    doc.spreadsheet.addElement(s1)

    # === Sheet 2: By source ===
    s2 = Table(name="By source")
    s2.addElement(TableColumn(numbercolumnsrepeated=5))
    s2.addElement(_row([
        _cell("Source"), _cell("# stations"),
        _cell("# countries"), _cell("# datums"), _cell("Top datums"),
    ]))
    by_source = defaultdict(list)
    for r in rows:
        by_source[r["source"]].append(r)
    for src, srows in sorted(by_source.items()):
        countries = {r["country"] for r in srows}
        datums = defaultdict(int)
        for r in srows:
            datums[r["datum"]] += 1
        top = sorted(datums.items(), key=lambda kv: -kv[1])[:5]
        top_str = "; ".join(f"{d} ({c})" for d, c in top)
        s2.addElement(_row([
            _cell(src), _cell(len(srows)),
            _cell(len(countries)), _cell(len(datums)), _cell(top_str),
        ]))
    doc.spreadsheet.addElement(s2)

    # === Sheet 3: Stations (raw) ===
    s3 = Table(name="Stations")
    s3.addElement(TableColumn(numbercolumnsrepeated=4))
    s3.addElement(_row([
        _cell("Country"), _cell("Source"), _cell("Datum"), _cell("Station name"),
    ]))
    for r in sorted(rows, key=lambda x: (x["country"], x["source"], x["name"])):
        s3.addElement(_row([
            _cell(r["country"]), _cell(r["source"]),
            _cell(r["datum"]), _cell(r["name"]),
        ]))
    doc.spreadsheet.addElement(s3)

    # === Sheet 4: Datum mismatches ===
    # Countries with >1 distinct datum across all their sources — those
    # are the candidates for standardization.
    s4 = Table(name="Datum mismatches")
    s4.addElement(TableColumn(numbercolumnsrepeated=4))
    s4.addElement(_row([
        _cell("Country"), _cell("# distinct datums"),
        _cell("# stations"), _cell("Datum spread (Datum [Source]: count)"),
    ]))
    by_country = defaultdict(list)
    for r in rows:
        by_country[r["country"]].append(r)
    mismatches = []
    for country, crows in by_country.items():
        per_datum = defaultdict(lambda: defaultdict(int))  # datum → source → count
        for r in crows:
            per_datum[r["datum"]][r["source"]] += 1
        if len(per_datum) > 1:
            mismatches.append((country, per_datum, len(crows)))
    # Sort by # distinct datums desc, then by total stations desc
    mismatches.sort(key=lambda x: (-len(x[1]), -x[2]))
    for country, per_datum, total in mismatches:
        spread_parts = []
        for d, srcmap in sorted(per_datum.items(), key=lambda kv: -sum(kv[1].values())):
            for src, cnt in sorted(srcmap.items(), key=lambda kv: -kv[1]):
                spread_parts.append(f"{d} [{src}]: {cnt}")
        s4.addElement(_row([
            _cell(country), _cell(len(per_datum)),
            _cell(total), _cell("; ".join(spread_parts)),
        ]))
    doc.spreadsheet.addElement(s4)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out_path))
    print(f"\nWrote {out_path}")
    print(f"  Sheet 1 'By country':         {len(by_cs_datum)} (country, source) pairs")
    print(f"  Sheet 2 'By source':          {len(by_source)} sources")
    print(f"  Sheet 3 'Stations':           {len(rows)} stations total")
    print(f"  Sheet 4 'Datum mismatches':   {len(mismatches)} countries with mixed datums")


if __name__ == "__main__":
    rows = collect()
    print(f"\nTotal: {len(rows)} stations")
    out = ROOT / "help" / "datum_overview.ods"
    build_ods(rows, out)
