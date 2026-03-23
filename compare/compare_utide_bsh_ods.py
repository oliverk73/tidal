#!/usr/bin/env python3
"""
Compare XTide predictions (from harmonics_utide_germany_2026-03-13.tcd)
with BSH official predictions from tide_prediction_pegelonline_utide.ods.

Only compares BSH rows (Quelle='BSH') with PNP datum.
Date range: 28.01.2026 - 31.01.2026 (from ODS sheet name).
"""
import subprocess
import re
import os
import numpy as np
from datetime import datetime, timedelta
from odf.opendocument import load
from odf.table import Table, TableRow, TableCell
from odf.text import P

TCD_FILE = "/usr/share/xtide/harmonics_utide_germany_2026-03-13.tcd"
ODS_FILE = "/home/oliver/harmonics/help/tide_prediction_pegelonline_utide.ods"

os.environ['HFILE_PATH'] = TCD_FILE

# BSH station name -> XTide station name mapping
BSH_TO_XTIDE = {
    'Bremerhaven, Weser, Alter Leuchtturm': 'Bremerhaven (Alter Leuchtturm), Germany',
    'Borkum, Fischerbalje': 'Borkum (Fischerbalje), Germany',
    'Brunsbüttel, Elbe, Ost': 'Brunsbüttel (Elbe), Germany',
    'Büsum, Schleuse': 'Büsum (Schleuse), Germany',
    'Hamburg, St. Pauli, Elbe': 'Hamburg (St. Pauli), Germany',
    'Emden, Ems, Große Seeschleuse': 'Emden (Ems, Große Seeschleuse), Germany',
    'Helgoland, Binnenhafen': 'Helgoland (Binnenhafen), Germany',
    'Husum, Schleuse': 'Husum (Schleuse), Germany',
    'Norderney, Riffgat': 'Norderney (Riffgat), Germany',
    'Bremen, Oslebshausen, Weser': 'Oslebshausen (Weser), Germany',
    'Wilhelmshaven, Alter Vorhafen': 'Wilhelmshaven (Alter Vorhafen), Germany',
    'Cuxhaven, Steubenhöft, Elbe': 'Cuxhaven-Steubenhöft (Elbe), Germany',
}


def get_row_values(row):
    """Extract all cell values from an ODS row, handling repeated cells."""
    vals = []
    for cell in row.getElementsByType(TableCell):
        ps = cell.getElementsByType(P)
        text = ''.join([str(p) for p in ps]) if ps else ''
        repeat = cell.getAttribute('numbercolumnsrepeated')
        n = int(repeat) if repeat else 1
        if n > 100:
            break
        for _ in range(n):
            vals.append(text)
    return vals


def parse_bsh_from_ods():
    """Parse BSH predictions from ODS. Returns dict of station -> list of events."""
    doc = load(ODS_FILE)
    sheet = doc.spreadsheet.getElementsByType(Table)[0]
    sheet_name = sheet.getAttribute('name')
    rows = sheet.getElementsByType(TableRow)

    # Extract date range from sheet name: "Tide prediction 28.01.2026 - 31.01.2026"
    m = re.search(r'(\d{2})\.(\d{2})\.(\d{4})\s*-\s*(\d{2})\.(\d{2})\.(\d{4})', sheet_name)
    if m:
        start_date = datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        end_date = datetime(int(m.group(6)), int(m.group(5)), int(m.group(4)))
    else:
        start_date = datetime(2026, 1, 28)
        end_date = datetime(2026, 1, 31)

    n_days = (end_date - start_date).days + 1

    stations = {}

    for row in rows[1:]:
        vals = get_row_values(row)
        if len(vals) < 8:
            continue
        if vals[1] != 'BSH':
            continue
        if vals[2] != 'PNP':
            continue

        station = vals[0].strip()

        # Parse time/level pairs across the date range
        events = []
        pair_index = 0
        for i in range(7, len(vals) - 1, 2):
            t_str = vals[i].strip()
            l_str = vals[i + 1].strip() if i + 1 < len(vals) else ''
            if not t_str or not l_str:
                continue

            # Parse time HH:MM
            hour, minute = map(int, t_str.split(':'))
            # Parse level (German decimal: comma)
            level = float(l_str.replace(',', '.'))

            # Determine which day this event belongs to
            # Events are sequential across days; detect day rollover
            if events and hour < events[-1]['hour']:
                pair_index += 1  # day rolled over

            day_offset = pair_index
            if day_offset >= n_days:
                break

            dt_mez = start_date + timedelta(days=day_offset, hours=hour, minutes=minute)
            dt_utc = dt_mez - timedelta(hours=1)

            # Determine HW/NW by comparing with neighbors (will refine later)
            events.append({
                'datetime_utc': dt_utc,
                'datetime_mez': dt_mez,
                'height_pnp': level,
                'hour': hour,
            })

        # Label HW/NW by alternating pattern (BSH alternates NW/HW or HW/NW)
        if len(events) >= 2:
            # First event: if level is higher than second, it's HW
            if events[0]['height_pnp'] > events[1]['height_pnp']:
                for j, ev in enumerate(events):
                    ev['type'] = 'HW' if j % 2 == 0 else 'NW'
            else:
                for j, ev in enumerate(events):
                    ev['type'] = 'NW' if j % 2 == 0 else 'HW'

        stations[station] = events

    return stations, start_date, end_date


def get_xtide_predictions(station_name, start_date, end_date):
    """Get HW/NW predictions from XTide."""
    result = subprocess.run(
        ['tide', '-l', station_name,
         '-b', start_date.strftime('%Y-%m-%d 00:00'),
         '-e', (end_date + timedelta(days=1)).strftime('%Y-%m-%d 00:00'),
         '-m', 'p', '-em', 'pSsMm'],
        capture_output=True, text=True, env=os.environ, timeout=30,
    )

    if result.returncode != 0:
        return None

    predictions = []
    for line in result.stdout.strip().split('\n'):
        line = line.strip()
        if not line or 'Indexing' in line or '°' in line:
            continue
        m = re.match(
            r'(\d{4}-\d{2}-\d{2})\s+(\d{1,2}:\d{2}\s+[AP]M)\s+\w+\s+([\d.]+)\s+meters\s+(High|Low)\s+Tide',
            line
        )
        if m:
            date_str = m.group(1)
            time_str = m.group(2)
            height = float(m.group(3))
            tide_type = 'HW' if m.group(4) == 'High' else 'NW'

            dt_mez = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %I:%M %p")
            dt_utc = dt_mez - timedelta(hours=1)

            predictions.append({
                'datetime_utc': dt_utc,
                'datetime_mez': dt_mez,
                'height_pnp': height,
                'type': tide_type,
            })

    return predictions


def match_events(bsh_events, xt_events, max_hours=3):
    """Match BSH events with nearest XTide events of same type."""
    matches = []
    used = set()

    for bsh in bsh_events:
        best = None
        best_dt = timedelta(hours=max_hours)

        for j, xt in enumerate(xt_events):
            if j in used or xt['type'] != bsh['type']:
                continue
            dt = abs(xt['datetime_utc'] - bsh['datetime_utc'])
            if dt < best_dt:
                best_dt = dt
                best = (j, xt)

        if best is not None:
            j, xt = best
            used.add(j)
            time_diff = (xt['datetime_utc'] - bsh['datetime_utc']).total_seconds() / 60
            height_diff = xt['height_pnp'] - bsh['height_pnp']
            matches.append({
                'bsh': bsh,
                'xtide': xt,
                'time_diff_min': time_diff,
                'height_diff_m': height_diff,
            })

    return matches


def main():
    print("=" * 85)
    print("Comparison: XTide (19-year UTide TCD) vs BSH Official — from ODS")
    print("=" * 85)
    print(f"  TCD: {TCD_FILE}")
    print(f"  ODS: {ODS_FILE}")

    # Parse BSH predictions
    print("\nParsing BSH predictions from ODS (Quelle='BSH', Datum='PNP')...")
    bsh_stations, start_date, end_date = parse_bsh_from_ods()
    print(f"  Date range: {start_date.strftime('%d.%m.%Y')} - {end_date.strftime('%d.%m.%Y')}")
    print(f"  BSH stations: {len(bsh_stations)}")

    for name, events in bsh_stations.items():
        hw = sum(1 for e in events if e.get('type') == 'HW')
        nw = sum(1 for e in events if e.get('type') == 'NW')
        print(f"    {name:<45s} {len(events)} events ({hw} HW, {nw} NW)")

    # Generate XTide predictions and compare
    print(f"\n{'='*85}")
    print("Generating XTide predictions and comparing...")
    print(f"{'='*85}")

    all_matches = []
    station_results = []

    for bsh_name, bsh_events in bsh_stations.items():
        xt_name = BSH_TO_XTIDE.get(bsh_name)
        if not xt_name:
            print(f"\n  {bsh_name}: NO XTIDE MAPPING — skipped")
            continue

        xt_preds = get_xtide_predictions(xt_name, start_date, end_date)
        if not xt_preds:
            print(f"\n  {bsh_name}: XTIDE FAILED — no output for '{xt_name}'")
            continue

        matches = match_events(bsh_events, xt_preds)
        if not matches:
            print(f"\n  {bsh_name}: NO MATCHES")
            continue

        hw_matches = [m for m in matches if m['bsh']['type'] == 'HW']
        nw_matches = [m for m in matches if m['bsh']['type'] == 'NW']

        # Print detail for this station
        print(f"\n  {bsh_name}  →  {xt_name}")
        print(f"  {'Type':4s} {'BSH (MEZ)':>14s} {'BSH Ht':>7s}   {'XTide (MEZ)':>14s} {'XT Ht':>7s}   {'dT':>6s} {'dH':>6s}")
        print(f"  {'─'*4} {'─'*14} {'─'*7}   {'─'*14} {'─'*7}   {'─'*6} {'─'*6}")

        for m in matches:
            b = m['bsh']
            x = m['xtide']
            print(f"  {b['type']:4s} {b['datetime_mez'].strftime('%d.%m. %H:%M'):>14s} {b['height_pnp']:>7.2f}   "
                  f"{x['datetime_mez'].strftime('%d.%m. %H:%M'):>14s} {x['height_pnp']:>7.2f}   "
                  f"{m['time_diff_min']:>+5.0f}m {m['height_diff_m']:>+5.2f}m")

        hw_dt = np.mean(np.abs([m['time_diff_min'] for m in hw_matches])) if hw_matches else 0
        hw_dh = np.mean(np.abs([m['height_diff_m'] for m in hw_matches])) if hw_matches else 0
        nw_dt = np.mean(np.abs([m['time_diff_min'] for m in nw_matches])) if nw_matches else 0
        nw_dh = np.mean(np.abs([m['height_diff_m'] for m in nw_matches])) if nw_matches else 0

        print(f"  Summary: HW |dT|={hw_dt:.0f}min |dH|={hw_dh:.2f}m  NW |dT|={nw_dt:.0f}min |dH|={nw_dh:.2f}m")

        station_results.append({
            'bsh_name': bsh_name,
            'xtide_name': xt_name,
            'n': len(matches),
            'hw_dt': hw_dt, 'hw_dh': hw_dh,
            'nw_dt': nw_dt, 'nw_dh': nw_dh,
            'hw_dt_bias': np.mean([m['time_diff_min'] for m in hw_matches]) if hw_matches else 0,
            'nw_dt_bias': np.mean([m['time_diff_min'] for m in nw_matches]) if nw_matches else 0,
            'hw_dh_bias': np.mean([m['height_diff_m'] for m in hw_matches]) if hw_matches else 0,
            'nw_dh_bias': np.mean([m['height_diff_m'] for m in nw_matches]) if nw_matches else 0,
        })
        all_matches.extend(matches)

    # Summary
    print(f"\n\n{'='*85}")
    print("SUMMARY")
    print(f"{'='*85}")
    print(f"  {'Station':<40s} {'N':>3s} {'|dT|HW':>8s} {'|dH|HW':>8s} {'|dT|NW':>8s} {'|dH|NW':>8s}")
    print(f"  {'─'*40} {'─'*3} {'─'*8} {'─'*8} {'─'*8} {'─'*8}")

    for r in station_results:
        print(f"  {r['bsh_name']:<40s} {r['n']:>3d} "
              f"{r['hw_dt']:>7.0f}m {r['hw_dh']:>7.2f}m "
              f"{r['nw_dt']:>7.0f}m {r['nw_dh']:>7.2f}m")

    if station_results:
        print(f"  {'─'*40} {'─'*3} {'─'*8} {'─'*8} {'─'*8} {'─'*8}")
        n_total = sum(r['n'] for r in station_results)
        avg_hw_dt = np.mean([r['hw_dt'] for r in station_results])
        avg_hw_dh = np.mean([r['hw_dh'] for r in station_results])
        avg_nw_dt = np.mean([r['nw_dt'] for r in station_results])
        avg_nw_dh = np.mean([r['nw_dh'] for r in station_results])
        print(f"  {'DURCHSCHNITT':<40s} {n_total:>3d} "
              f"{avg_hw_dt:>7.0f}m {avg_hw_dh:>7.2f}m "
              f"{avg_nw_dt:>7.0f}m {avg_nw_dh:>7.02f}m")

        print(f"\n  BIAS (positiv = XTide später/höher als BSH):")
        print(f"  {'Station':<40s} {'dT HW':>8s} {'dH HW':>8s} {'dT NW':>8s} {'dH NW':>8s}")
        print(f"  {'─'*40} {'─'*8} {'─'*8} {'─'*8} {'─'*8}")
        for r in station_results:
            print(f"  {r['bsh_name']:<40s} "
                  f"{r['hw_dt_bias']:>+7.0f}m {r['hw_dh_bias']:>+7.02f}m "
                  f"{r['nw_dt_bias']:>+7.0f}m {r['nw_dh_bias']:>+7.02f}m")
        avg_hw_dt_b = np.mean([r['hw_dt_bias'] for r in station_results])
        avg_hw_dh_b = np.mean([r['hw_dh_bias'] for r in station_results])
        avg_nw_dt_b = np.mean([r['nw_dt_bias'] for r in station_results])
        avg_nw_dh_b = np.mean([r['nw_dh_bias'] for r in station_results])
        print(f"  {'─'*40} {'─'*8} {'─'*8} {'─'*8} {'─'*8}")
        print(f"  {'DURCHSCHNITT':<40s} "
              f"{avg_hw_dt_b:>+7.0f}m {avg_hw_dh_b:>+7.02f}m "
              f"{avg_nw_dt_b:>+7.0f}m {avg_nw_dh_b:>+7.02f}m")


if __name__ == "__main__":
    main()
