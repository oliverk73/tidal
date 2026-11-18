#!/usr/bin/env python3
"""Generate an ODS report of all harmonics files with metadata and quality metrics."""

import os
import re
from pathlib import Path
from collections import Counter

from odf.opendocument import OpenDocumentSpreadsheet
from odf.table import Table, TableColumn, TableRow, TableCell
from odf.text import P
from odf.style import Style, TableColumnProperties, TextProperties, TableCellProperties, ParagraphProperties

HARMONICS_DIR = Path("/home/oliver/harmonics")
EXCLUDE_DIRS = {"backup", "binary", "help", "template"}
OUTPUT_ODS = "/home/oliver/harmonics/help/Harmonics_Übersicht.ods"


def fmt_range(values, fmt=".0f"):
    """Format a list of numbers as 'min–max (Ø avg)' or single value."""
    if not values:
        return ""
    mn, mx = min(values), max(values)
    avg = sum(values) / len(values)
    if mn == mx:
        return f"{mn:{fmt}}"
    return f"{mn:{fmt}}–{mx:{fmt}} (Ø {avg:{fmt}})"


def parse_harmonics_file(filepath):
    """Parse a harmonics .txt file and extract metadata + quality metrics."""
    with open(filepath, "r", encoding="iso-8859-1") as f:
        content = f.read()
    lines = content.split("\n")

    # Time of Conversion
    time_of_conversion = ""
    for line in lines[:10]:
        m = re.match(r"^#\s+at\s+(.+)", line)
        if m:
            time_of_conversion = m.group(1).strip()
            break

    # Number of constituents (from header)
    num_constituents = 0
    for i, line in enumerate(lines):
        if "# Number of constituents" in line:
            for j in range(i + 1, min(i + 5, len(lines))):
                stripped = lines[j].strip().lstrip("# ")
                if stripped.isdigit():
                    num_constituents = int(stripped)
                    break
            break

    # Countries
    countries = []
    for line in lines:
        m = re.match(r"^#\s+country:\s*(.+)", line)
        if m:
            countries.append(m.group(1).strip())

    num_stations = len(countries)
    country_counts = Counter(countries)
    country_list = ", ".join(
        f"{c} ({n})" if n > 1 else c
        for c, n in sorted(country_counts.items())
    )

    # Observation periods
    obs_starts = []
    obs_ends = []
    for line in lines:
        m = re.search(r"from\s+(\d{4}-\d{2}-\d{2})\s+to\s+(\d{4}-\d{2}-\d{2})", line)
        if m:
            obs_starts.append(m.group(1))
            obs_ends.append(m.group(2))

    obs_start = ""
    obs_end = ""
    if obs_starts:
        obs_start = f"{min(obs_starts)} – {max(obs_starts)}" if min(obs_starts) != max(obs_starts) else min(obs_starts)
        obs_end = f"{min(obs_ends)} – {max(obs_ends)}" if min(obs_ends) != max(obs_ends) else min(obs_ends)

    # Constituents analyzed (from UTide "# Constituents analyzed: NN")
    analyzed_counts = []
    for line in lines:
        m = re.match(r"^#\s+Constituents analyzed:\s*(\d+)", line)
        if m:
            analyzed_counts.append(int(m.group(1)))

    # Observation counts
    obs_counts = []
    for line in lines:
        m = re.search(r"(?:using|with)\s+(\d+)\s+observations", line)
        if m:
            obs_counts.append(int(m.group(1)))

    # Count actually used constituents per station
    used_counts = []
    if num_constituents > 0:
        lat_indices = [i for i, line in enumerate(lines) if line.strip().startswith("# !latitude:")]
        for lat_idx in lat_indices:
            name_idx = lat_idx + 1
            while name_idx < len(lines) and (lines[name_idx].strip() == "" or lines[name_idx].strip().startswith("#")):
                name_idx += 1
            if name_idx >= len(lines):
                continue
            const_start = name_idx + 3
            if const_start + num_constituents > len(lines):
                continue
            used = 0
            for j in range(const_start, const_start + num_constituents):
                parts = lines[j].strip().split()
                if len(parts) >= 2:
                    try:
                        if float(parts[-2]) > 0:
                            used += 1
                    except ValueError:
                        pass
            used_counts.append(used)

    # R² values
    r2_values = []
    for line in lines:
        m = re.search(r"R\^2\s*=\s*([\d.]+)", line)
        if m:
            r2_values.append(float(m.group(1)))

    # RMS error values
    rms_values = []
    for line in lines:
        m = re.search(r"RMS error\s*=\s*([\d.]+)", line)
        if m:
            rms_values.append(float(m.group(1)))

    # Confidence values
    confidence_values = []
    for line in lines:
        m = re.match(r"^#\s+confidence:\s*(\d+)", line)
        if m:
            confidence_values.append(int(m.group(1)))

    return {
        "filename": str(filepath.relative_to(HARMONICS_DIR)),
        "time_of_conversion": time_of_conversion,
        "countries": country_list,
        "num_stations": num_stations,
        "num_constituents": num_constituents,
        "constituents_analyzed": fmt_range(analyzed_counts),
        "avg_used_constituents": fmt_range(used_counts),
        "obs_count": f"Ø {sum(obs_counts)/len(obs_counts):,.0f}" if obs_counts else "",
        "r2": fmt_range(r2_values, ".4f") if r2_values else "",
        "rms_error": fmt_range(rms_values, ".4f") if rms_values else "",
        "confidence": fmt_range(confidence_values),
        "obs_start": obs_start,
        "obs_end": obs_end,
    }


def create_ods(data, output_path):
    """Create an ODS spreadsheet with the harmonics data."""
    doc = OpenDocumentSpreadsheet()

    bold_style = Style(name="bold", family="table-cell")
    bold_style.addElement(TextProperties(fontweight="bold"))
    bold_style.addElement(ParagraphProperties(textalign="center"))
    bold_style.addElement(TableCellProperties(
        verticalalign="middle", backgroundcolor="#4472C4", padding="0.1cm"
    ))
    doc.styles.addElement(bold_style)

    wrap_style = Style(name="wrap", family="table-cell")
    wrap_style.addElement(TableCellProperties(wrapoption="wrap", verticalalign="top"))
    doc.styles.addElement(wrap_style)

    table = Table(name="Harmonics-Dateien")

    col_widths = [
        "4cm",    # Dateiname
        "3cm",    # Konvertiert
        "7cm",    # Länder
        "1.5cm",  # Stationen
        "1.5cm",  # Const. (Datei)
        "1.5cm",  # Const. (analysiert)
        "3cm",    # Const. (Ø verwendet)
        "2.5cm",  # Ø Observations
        "2.5cm",  # Ø R²
        "2.5cm",  # Ø RMS error
        "2cm",    # Confidence
        "3cm",    # Beob. Start
        "3cm",    # Beob. Ende
    ]
    for i, w in enumerate(col_widths):
        col_style = Style(name=f"col{i}", family="table-column")
        col_style.addElement(TableColumnProperties(columnwidth=w))
        doc.automaticstyles.addElement(col_style)
        table.addElement(TableColumn(stylename=col_style))

    headers = [
        "Dateiname",
        "Konvertiert",
        "Länder",
        "Stationen",
        "Constituents\n(Datei)",
        "Constituents\n(analysiert)",
        "Constituents\n(Ø verwendet)",
        "Ø Observations",
        "R²",
        "RMS error",
        "Confidence",
        "Beobachtung\nStart",
        "Beobachtung\nEnde",
    ]

    header_row = TableRow()
    for h in headers:
        cell = TableCell(stylename=bold_style)
        cell.addElement(P(text=h))
        header_row.addElement(cell)
    table.addElement(header_row)

    fields = [
        "filename", "time_of_conversion", "countries",
        "num_stations", "num_constituents", "constituents_analyzed",
        "avg_used_constituents", "obs_count",
        "r2", "rms_error", "confidence",
        "obs_start", "obs_end",
    ]

    for row_data in data:
        row = TableRow()
        for field in fields:
            val = row_data[field]
            cell = TableCell(stylename=wrap_style)
            cell.addElement(P(text=str(val)))
            row.addElement(cell)
        table.addElement(row)

    doc.spreadsheet.addElement(table)
    doc.save(output_path)
    print(f"Saved to {output_path}")


def main():
    files = []
    for root, dirs, filenames in os.walk(HARMONICS_DIR):
        rel = Path(root).relative_to(HARMONICS_DIR)
        parts = rel.parts
        if parts and parts[0] in EXCLUDE_DIRS:
            continue
        for fn in sorted(filenames):
            if fn.endswith(".txt"):
                files.append(Path(root) / fn)
    files.sort()

    print(f"Found {len(files)} harmonics files")

    results = []
    for f in files:
        print(f"  Parsing {f.relative_to(HARMONICS_DIR)}...")
        results.append(parse_harmonics_file(f))

    create_ods(results, OUTPUT_ODS)

    for r in results:
        print(f"\n{r['filename']}:")
        print(f"  Stations: {r['num_stations']}, Const: {r['num_constituents']}")
        print(f"  Analyzed: {r['constituents_analyzed']}, Used: {r['avg_used_constituents']}")
        print(f"  Obs: {r['obs_count']}, R²: {r['r2']}, RMS: {r['rms_error']}, Conf: {r['confidence']}")
        print(f"  Period: {r['obs_start']} → {r['obs_end']}")


if __name__ == "__main__":
    main()
