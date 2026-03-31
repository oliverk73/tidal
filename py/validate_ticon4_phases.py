#!/usr/bin/env python3
"""
Validiert TICON4-Stationen gegen FES2022b-Tidenmodell.

Für jede Station werden die Phasen der Hauptkonstituenten (M2, S2, K1, O1)
mit FES2022b verglichen. Wenn die Phasen um ~180° abweichen, ist die Station
vermutlich invertiert.

Ausgabe: ODS-Datei mit allen Stationen und ihrem Validierungsstatus.
"""

import re
import os
import sys
import numpy as np
import netCDF4 as nc
from collections import OrderedDict

# --- Konfiguration ---
TICON4_FILE = '/home/oliver/harmonics/ticon/harmonics_ticon4_worldwide.txt'
FES_DIR = '/home/oliver/tide_models/fes2022b/ocean_tide_extrapolated/'
OUTPUT_ODS = '/home/oliver/harmonics/help/ticon4_phase_validation.ods'

# Hauptkonstituenten für den Vergleich (die größten, zuverlässigsten)
COMPARE_CONSTITUENTS = ['M2', 'S2', 'K1', 'O1', 'N2', 'K2', 'P1', 'Q1']

# Schwellenwerte
PHASE_INVERT_THRESHOLD = 120  # Wenn Delta > 120° UND < 240°, gilt als ~180° invertiert
AMPLITUDE_MIN = 0.005  # Nur Konstituenten mit Amplitude > 5mm vergleichen (TICON4)
FES_AMPLITUDE_MIN = 0.1  # FES: mindestens 1mm (0.1 cm)


def parse_ticon4_stations(filepath):
    """Parse alle Stationen aus der TICON4-Datei."""
    with open(filepath, 'r', encoding='iso-8859-1') as f:
        lines = f.readlines()

    tz_pat = re.compile(r'^([+-]\d{2}:\d{2})\s+:(.+)')
    stations = []
    i = 0

    while i < len(lines):
        m = tz_pat.match(lines[i])
        if m and i > 0:
            tz_offset = m.group(1)
            tz_name = m.group(2).strip()
            station_name = lines[i - 1].strip()

            # Parse coordinates from HOT COMMENTS above
            lat, lon = None, None
            for j in range(i - 2, max(i - 30, 0), -1):
                line = lines[j].strip()
                if line.startswith('# !latitude:'):
                    lat = float(line.split(':')[1].strip())
                elif line.startswith('# !longitude:'):
                    lon = float(line.split(':')[1].strip())
                elif line.startswith('# BEGIN HOT COMMENTS'):
                    break

            # Parse datum
            i += 1
            datum_line = lines[i].strip() if i < len(lines) else ''

            # Parse constituents
            constituents = {}
            i += 1
            while i < len(lines):
                line = lines[i].strip()
                # End of station block: next station name or end of file
                if not line or tz_pat.match(lines[i]) if i < len(lines) else True:
                    break
                # Check if this is the next station's name (next line is tz)
                if i + 1 < len(lines) and tz_pat.match(lines[i + 1]):
                    break
                # Check for BEGIN HOT COMMENTS (start of next station block)
                if '# BEGIN HOT COMMENTS' in line or line.startswith('#'):
                    break

                # Parse constituent line: "NAME  amplitude  phase" or "x 0 0"
                parts = line.split()
                if len(parts) >= 3 and parts[0] != 'x':
                    try:
                        name = parts[0]
                        amp = float(parts[1])
                        phase = float(parts[2])
                        constituents[name] = (amp, phase)
                    except ValueError:
                        pass
                i += 1

            if lat is not None and lon is not None:
                stations.append({
                    'name': station_name,
                    'lat': lat,
                    'lon': lon,
                    'tz_offset': tz_offset,
                    'tz_name': tz_name,
                    'constituents': constituents,
                })
            continue
        i += 1

    return stations


def load_fes_grids(constituents):
    """Lade FES2022b-Gitter für die gewünschten Konstituenten."""
    grids = {}
    # Load lat/lon from first file
    first_file = os.path.join(FES_DIR, f'{constituents[0].lower()}_fes2022.nc')
    ds = nc.Dataset(first_file)
    fes_lat = ds['lat'][:].data
    fes_lon = ds['lon'][:].data
    ds.close()

    for const in constituents:
        fes_name = const.lower()
        fpath = os.path.join(FES_DIR, f'{fes_name}_fes2022.nc')
        if not os.path.exists(fpath):
            print(f"  WARNUNG: FES-Datei nicht gefunden: {fpath}")
            continue
        ds = nc.Dataset(fpath)
        amp = ds['amplitude'][:].data  # cm
        phase = ds['phase'][:].data  # degrees
        grids[const] = {'amplitude': amp, 'phase': phase}
        ds.close()

    return fes_lat, fes_lon, grids


def get_fes_value(fes_lat, fes_lon, grids, const, lat, lon):
    """Hole FES2022b-Wert für eine Koordinate (nächster Gitterpunkt)."""
    if const not in grids:
        return None, None

    # Longitude: FES nutzt 0-360
    fes_lon_query = lon % 360

    lat_idx = np.argmin(np.abs(fes_lat - lat))
    lon_idx = np.argmin(np.abs(fes_lon - fes_lon_query))

    amp = grids[const]['amplitude'][lat_idx, lon_idx]
    phase = grids[const]['phase'][lat_idx, lon_idx]

    # Masked/invalid values
    if amp > 9000 or phase > 9000:
        return None, None

    return amp, phase


def phase_diff(p1, p2):
    """Berechne kürzeste Phasendifferenz (0-180°)."""
    d = abs(p1 - p2) % 360
    if d > 180:
        d = 360 - d
    return d


def classify_station(ticon_const, fes_lat, fes_lon, grids, lat, lon):
    """
    Vergleiche TICON4-Phasen mit FES2022b.
    Gibt zurück: (status, details)
    status: 'OK', 'INVERTIERT', 'UNKLAR', 'KEINE_DATEN'
    """
    diffs_normal = []  # Differenzen bei normaler Phase
    diffs_inverted = []  # Differenzen bei invertierter Phase (+ 180°)
    details = []

    for const in COMPARE_CONSTITUENTS:
        if const not in ticon_const:
            continue
        ticon_amp, ticon_phase = ticon_const[const]
        if ticon_amp < AMPLITUDE_MIN:
            continue

        fes_amp, fes_phase = get_fes_value(fes_lat, fes_lon, grids, const, lat, lon)
        if fes_amp is None or fes_amp < FES_AMPLITUDE_MIN:
            continue

        # Normal difference
        diff_normal = phase_diff(ticon_phase, fes_phase)
        # Inverted difference (TICON phase + 180°)
        diff_inverted = phase_diff((ticon_phase + 180) % 360, fes_phase)

        diffs_normal.append(diff_normal)
        diffs_inverted.append(diff_inverted)
        details.append({
            'constituent': const,
            'ticon_amp': ticon_amp,
            'ticon_phase': ticon_phase,
            'fes_amp': fes_amp,
            'fes_phase': fes_phase,
            'diff_normal': diff_normal,
            'diff_inverted': diff_inverted,
        })

    if not diffs_normal:
        return 'KEINE_DATEN', details, 0, 0

    avg_normal = np.mean(diffs_normal)
    avg_inverted = np.mean(diffs_inverted)

    # Gewichtete Entscheidung: Wenn invertiert deutlich besser passt
    if avg_normal < 45:
        return 'OK', details, avg_normal, avg_inverted
    elif avg_inverted < 45:
        return 'INVERTIERT', details, avg_normal, avg_inverted
    elif avg_normal < avg_inverted:
        if avg_normal < 60:
            return 'OK', details, avg_normal, avg_inverted
        else:
            return 'UNKLAR', details, avg_normal, avg_inverted
    else:
        if avg_inverted < 60:
            return 'INVERTIERT', details, avg_normal, avg_inverted
        else:
            return 'UNKLAR', details, avg_normal, avg_inverted


def write_ods(results, filepath):
    """Schreibe Ergebnisse als ODS."""
    from odf.opendocument import OpenDocumentSpreadsheet
    from odf.table import Table, TableRow, TableCell, TableColumn
    from odf.text import P
    from odf.style import Style, TableCellProperties, TableColumnProperties

    doc = OpenDocumentSpreadsheet()

    # Styles
    style_ok = Style(name="OK", family="table-cell")
    style_ok.addElement(TableCellProperties(backgroundcolor="#90EE90"))
    doc.automaticstyles.addElement(style_ok)

    style_inv = Style(name="INV", family="table-cell")
    style_inv.addElement(TableCellProperties(backgroundcolor="#FF6B6B"))
    doc.automaticstyles.addElement(style_inv)

    style_unklar = Style(name="UNKLAR", family="table-cell")
    style_unklar.addElement(TableCellProperties(backgroundcolor="#FFD700"))
    doc.automaticstyles.addElement(style_unklar)

    style_header = Style(name="Header", family="table-cell")
    style_header.addElement(TableCellProperties(backgroundcolor="#4472C4"))
    doc.automaticstyles.addElement(style_header)

    style_nodata = Style(name="NODATA", family="table-cell")
    style_nodata.addElement(TableCellProperties(backgroundcolor="#D3D3D3"))
    doc.automaticstyles.addElement(style_nodata)

    # --- Übersichts-Sheet ---
    table = Table(name="Übersicht")

    # Header
    header = TableRow()
    for h in ['Station', 'Lat', 'Lon', 'TZ-Offset', 'TZ-Name', 'Status',
              'Ø Diff Normal (°)', 'Ø Diff Invertiert (°)',
              'M2 Δ°', 'S2 Δ°', 'K1 Δ°', 'O1 Δ°']:
        cell = TableCell(stylename="Header")
        cell.addElement(P(text=h))
        header.addElement(cell)
    table.addElement(header)

    status_style = {
        'OK': 'OK',
        'INVERTIERT': 'INV',
        'UNKLAR': 'UNKLAR',
        'KEINE_DATEN': 'NODATA',
    }

    for r in results:
        row = TableRow()

        # Station name
        cell = TableCell()
        cell.addElement(P(text=r['name']))
        row.addElement(cell)

        # Lat
        cell = TableCell(valuetype="float", value=str(r['lat']))
        cell.addElement(P(text=f"{r['lat']:.4f}"))
        row.addElement(cell)

        # Lon
        cell = TableCell(valuetype="float", value=str(r['lon']))
        cell.addElement(P(text=f"{r['lon']:.4f}"))
        row.addElement(cell)

        # TZ offset
        cell = TableCell()
        cell.addElement(P(text=r['tz_offset']))
        row.addElement(cell)

        # TZ name
        cell = TableCell()
        cell.addElement(P(text=r['tz_name']))
        row.addElement(cell)

        # Status (colored)
        sty = status_style.get(r['status'], 'NODATA')
        cell = TableCell(stylename=sty)
        cell.addElement(P(text=r['status']))
        row.addElement(cell)

        # Avg diffs
        cell = TableCell(valuetype="float", value=str(round(r['avg_normal'], 1)))
        cell.addElement(P(text=f"{r['avg_normal']:.1f}"))
        row.addElement(cell)

        cell = TableCell(valuetype="float", value=str(round(r['avg_inverted'], 1)))
        cell.addElement(P(text=f"{r['avg_inverted']:.1f}"))
        row.addElement(cell)

        # Individual constituent diffs
        for const in ['M2', 'S2', 'K1', 'O1']:
            detail = next((d for d in r['details'] if d['constituent'] == const), None)
            if detail:
                cell = TableCell(valuetype="float", value=str(round(detail['diff_normal'], 1)))
                cell.addElement(P(text=f"{detail['diff_normal']:.1f}"))
            else:
                cell = TableCell()
                cell.addElement(P(text="-"))
            row.addElement(cell)

        table.addElement(row)

    doc.spreadsheet.addElement(table)

    # --- Zusammenfassung ---
    summary = Table(name="Zusammenfassung")
    counts = {}
    for r in results:
        counts[r['status']] = counts.get(r['status'], 0) + 1

    header = TableRow()
    for h in ['Status', 'Anzahl', 'Prozent']:
        cell = TableCell(stylename="Header")
        cell.addElement(P(text=h))
        header.addElement(cell)
    summary.addElement(header)

    total = len(results)
    for status in ['OK', 'INVERTIERT', 'UNKLAR', 'KEINE_DATEN']:
        row = TableRow()
        sty = status_style.get(status, 'NODATA')

        cell = TableCell(stylename=sty)
        cell.addElement(P(text=status))
        row.addElement(cell)

        n = counts.get(status, 0)
        cell = TableCell(valuetype="float", value=str(n))
        cell.addElement(P(text=str(n)))
        row.addElement(cell)

        pct = (n / total * 100) if total > 0 else 0
        cell = TableCell(valuetype="float", value=str(round(pct, 1)))
        cell.addElement(P(text=f"{pct:.1f}%"))
        row.addElement(cell)

        summary.addElement(row)

    # Total row
    row = TableRow()
    cell = TableCell()
    cell.addElement(P(text="GESAMT"))
    row.addElement(cell)
    cell = TableCell(valuetype="float", value=str(total))
    cell.addElement(P(text=str(total)))
    row.addElement(cell)
    cell = TableCell()
    cell.addElement(P(text="100%"))
    row.addElement(cell)
    summary.addElement(row)

    doc.spreadsheet.addElement(summary)

    doc.save(filepath)
    print(f"\nODS gespeichert: {filepath}")


def main():
    print("=== TICON4 Phasen-Validierung gegen FES2022b ===\n")

    print("Lade FES2022b-Gitter...")
    fes_lat, fes_lon, grids = load_fes_grids(COMPARE_CONSTITUENTS)
    print(f"  {len(grids)} Konstituenten geladen: {list(grids.keys())}")

    print("\nParse TICON4-Stationen...")
    stations = parse_ticon4_stations(TICON4_FILE)
    print(f"  {len(stations)} Stationen mit Koordinaten gefunden")

    print("\nValidiere Stationen...")
    results = []
    counts = {'OK': 0, 'INVERTIERT': 0, 'UNKLAR': 0, 'KEINE_DATEN': 0}

    for idx, st in enumerate(stations):
        status, details, avg_n, avg_i = classify_station(
            st['constituents'], fes_lat, fes_lon, grids, st['lat'], st['lon']
        )
        counts[status] += 1

        results.append({
            'name': st['name'],
            'lat': st['lat'],
            'lon': st['lon'],
            'tz_offset': st['tz_offset'],
            'tz_name': st['tz_name'],
            'status': status,
            'avg_normal': avg_n,
            'avg_inverted': avg_i,
            'details': details,
        })

        if (idx + 1) % 200 == 0:
            print(f"  {idx + 1}/{len(stations)} verarbeitet... "
                  f"(OK: {counts['OK']}, INV: {counts['INVERTIERT']}, "
                  f"UNKLAR: {counts['UNKLAR']}, KEINE: {counts['KEINE_DATEN']})")

    print(f"\n=== Ergebnis ===")
    print(f"  OK:          {counts['OK']}")
    print(f"  INVERTIERT:  {counts['INVERTIERT']}")
    print(f"  UNKLAR:      {counts['UNKLAR']}")
    print(f"  KEINE_DATEN: {counts['KEINE_DATEN']}")
    print(f"  GESAMT:      {len(results)}")

    # Sort: INVERTIERT first, then UNKLAR, then OK, then KEINE_DATEN
    sort_order = {'INVERTIERT': 0, 'UNKLAR': 1, 'OK': 2, 'KEINE_DATEN': 3}
    results.sort(key=lambda r: (sort_order.get(r['status'], 4), r['name']))

    print("\nSchreibe ODS...")
    write_ods(results, OUTPUT_ODS)

    # Print inverted stations
    inv = [r for r in results if r['status'] == 'INVERTIERT']
    if inv:
        print(f"\n=== INVERTIERTE Stationen ({len(inv)}) ===")
        for r in inv[:30]:
            print(f"  {r['name']} ({r['tz_offset']}, {r['tz_name']}) "
                  f"Δnormal={r['avg_normal']:.1f}° Δinv={r['avg_inverted']:.1f}°")
        if len(inv) > 30:
            print(f"  ... und {len(inv) - 30} weitere")


if __name__ == '__main__':
    main()
