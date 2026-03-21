#!/usr/bin/env python3
"""
Compare both UTide TCD variants (with/without Z0 correction) vs BSH — January 2026.
Only shows the summary lines for quick comparison.
"""
import subprocess
import re
import os
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path


BSH_DIR = Path("/home/oliver/harmonics_working_help/BSH")


def parse_bsh_file(bsh_path):
    station_name = None
    predictions = []
    with open(bsh_path, 'r', encoding='latin-1') as f:
        for line in f:
            line = line.strip()
            if line.startswith('A04#'):
                parts = line.split(':#')
                if len(parts) >= 2:
                    station_name = parts[1].rstrip('#').strip()
            if not line.startswith('VB2#'):
                continue
            parts = line.split('#')
            hw_nw = parts[3].strip()
            date_str = re.sub(r'\s+', '', parts[5].strip())
            time_str = parts[6].strip()
            height_str = parts[7].strip()
            day, month, year = date_str.split('.')
            hour, minute = map(int, time_str.split(':'))
            height = float(height_str)
            dt_mez = datetime(int(year), int(month), int(day), hour, minute)
            dt_utc = dt_mez - timedelta(hours=1)
            predictions.append({
                'datetime_utc': dt_utc, 'height_pnp': height,
                'type': 'HW' if hw_nw == 'H' else 'NW',
            })
    return station_name, predictions


def get_xtide_stations(txt_file):
    stations = []
    with open(txt_file, 'r', encoding='latin-1') as f:
        for line in f:
            stripped = line.strip()
            if stripped.endswith(', Germany') and not stripped.startswith('#'):
                stations.append(stripped)
    return stations


def get_xtide_predictions(station_name, start_date, end_date):
    result = subprocess.run(
        ['tide', '-l', station_name,
         '-b', start_date.strftime('%Y-%m-%d 00:00'),
         '-e', end_date.strftime('%Y-%m-%d 00:00'),
         '-m', 'p', '-em', 'pSsMm'],
        capture_output=True, text=True, env=os.environ, timeout=30,
    )
    if result.returncode != 0:
        return None
    predictions = []
    for line in result.stdout.strip().split('\n'):
        line = line.strip()
        if not line or line.startswith('Indexing') or '°' in line:
            continue
        m = re.match(
            r'(\d{4}-\d{2}-\d{2})\s+(\d{1,2}:\d{2}\s+[AP]M)\s+(CES?T)\s+([\d.]+)\s+meters\s+(High|Low)\s+Tide',
            line
        )
        if m:
            dt_local = datetime.strptime(f"{m.group(1)} {m.group(2)}", "%Y-%m-%d %I:%M %p")
            utc_offset = 2 if m.group(3) == 'CEST' else 1
            predictions.append({
                'datetime_utc': dt_local - timedelta(hours=utc_offset),
                'height_pnp': float(m.group(4)),
                'type': 'HW' if m.group(5) == 'High' else 'NW',
            })
    return predictions


def normalize(s):
    s = s.lower()
    for old, new in [('ä','ae'),('ö','oe'),('ü','ue'),('ß','ss')]:
        s = s.replace(old, new)
    return re.sub(r'[^a-z0-9]', '', s)


def find_xtide_match(bsh_name, xtide_stations):
    norm_bsh = normalize(bsh_name)
    best_match, best_score = None, 0
    for xt_name in xtide_stations:
        norm_xt = normalize(xt_name.replace(', Germany', ''))
        if norm_bsh == norm_xt:
            return xt_name
        if norm_bsh in norm_xt or norm_xt in norm_bsh:
            score = min(len(norm_bsh), len(norm_xt))
            if score > best_score:
                best_score, best_match = score, xt_name
        bsh_parts = set(re.split(r'[,\s]+', norm_bsh))
        xt_parts = set(re.split(r'[,\s]+', norm_xt))
        common = bsh_parts & xt_parts
        if len(common) >= 2 and len(common) / max(len(bsh_parts), len(xt_parts)) > 0.5:
            score = len(common) * 10
            if score > best_score:
                best_score, best_match = score, xt_name
    return best_match if best_score >= 8 else None


def match_events(bsh_preds, xt_preds, max_hours=3):
    matches, used = [], set()
    for bsh in bsh_preds:
        best, best_dt = None, timedelta(hours=max_hours)
        for j, xt in enumerate(xt_preds):
            if j in used or xt['type'] != bsh['type']:
                continue
            dt = abs(xt['datetime_utc'] - bsh['datetime_utc'])
            if dt < best_dt:
                best_dt, best = dt, (j, xt)
        if best is not None:
            j, xt = best
            used.add(j)
            matches.append({
                'bsh': bsh, 'xtide': xt,
                'time_diff_min': (xt['datetime_utc'] - bsh['datetime_utc']).total_seconds() / 60,
                'height_diff_m': xt['height_pnp'] - bsh['height_pnp'],
            })
    return matches


def run_comparison(tcd_path, txt_path, label):
    os.environ['HFILE_PATH'] = str(tcd_path)
    xtide_stations = get_xtide_stations(txt_path)

    bsh_files = sorted(BSH_DIR.glob("DE__*2026.txt"))
    bsh_files = [f for f in bsh_files if ':' not in str(f)]

    start, end = datetime(2026, 1, 1), datetime(2026, 2, 1)
    results = {}

    for bsh_file in bsh_files:
        bsh_name, bsh_preds = parse_bsh_file(bsh_file)
        if not bsh_name or not bsh_preds:
            continue
        bsh_preds = [p for p in bsh_preds if p['datetime_utc'].month == 1]
        xt_match = find_xtide_match(bsh_name, xtide_stations)
        if not xt_match:
            continue

        xt_preds = get_xtide_predictions(xt_match, start, end)
        if not xt_preds:
            continue

        matches = match_events(bsh_preds, xt_preds)
        if not matches:
            continue

        # Datum correction
        height_offset = np.mean([m['bsh']['height_pnp'] - m['xtide']['height_pnp'] for m in matches])
        for m in matches:
            m['height_diff_corrected'] = m['xtide']['height_pnp'] - (m['bsh']['height_pnp'] - height_offset)

        hw = [m for m in matches if m['bsh']['type'] == 'HW']
        nw = [m for m in matches if m['bsh']['type'] == 'NW']

        results[bsh_name] = {
            'xtide_name': xt_match,
            'n': len(matches),
            'hw_dt': np.mean(np.abs([m['time_diff_min'] for m in hw])) if hw else 0,
            'hw_dh': np.mean(np.abs([m['height_diff_corrected'] for m in hw])) if hw else 0,
            'nw_dt': np.mean(np.abs([m['time_diff_min'] for m in nw])) if nw else 0,
            'nw_dh': np.mean(np.abs([m['height_diff_corrected'] for m in nw])) if nw else 0,
            'hw_dt_bias': np.mean([m['time_diff_min'] for m in hw]) if hw else 0,
            'nw_dt_bias': np.mean([m['time_diff_min'] for m in nw]) if nw else 0,
            'hw_dh_bias': np.mean([m['height_diff_corrected'] for m in hw]) if hw else 0,
            'nw_dh_bias': np.mean([m['height_diff_corrected'] for m in nw]) if nw else 0,
        }

    return results


def main():
    tcds = [
        (
            Path("/usr/share/xtide/harmonics-dwf-20070318_no_us_no_dupes.tcd"),
            Path("/home/oliver/harmonics_working/harmonics-dwf-20070318_no_us_no_dupes.txt"),
            "DWF 2007",
        ),
        (
            Path("/home/oliver/harmonics_working/harmonics_utide_germany_2026-03-15.tcd"),
            Path("/home/oliver/harmonics_working/harmonics_utide_germany_2026-03-15.txt"),
            "UTide (ohne Z0)",
        ),
        (
            Path("/home/oliver/harmonics_working/harmonics_utide_germany_2026-03-15_z0corrected.tcd"),
            Path("/home/oliver/harmonics_working/harmonics_utide_germany_2026-03-15_z0corrected.txt"),
            "UTide (Z0-korr.)",
        ),
    ]

    all_results = {}
    for tcd, txt, label in tcds:
        print(f"Berechne {label}...", flush=True)
        all_results[label] = run_comparison(tcd, txt, label)
        print(f"  → {len(all_results[label])} BSH-Stationen gematcht")

    labels = [l for _, _, l in tcds]

    # All BSH stations across all TCDs
    all_bsh_stations = set()
    for label in labels:
        all_bsh_stations |= set(all_results[label].keys())

    # Stations present in DWF 2007
    dwf_stations = set(all_results["DWF 2007"].keys())
    common_stations = sorted(dwf_stations)
    utide_only = sorted(all_bsh_stations - dwf_stations)

    # ── Show XTide name mapping ──
    print(f"\n{'='*120}")
    print("STATIONSZUORDNUNG (BSH → XTide-Name pro TCD)")
    print(f"{'='*120}")
    for bsh in common_stations:
        print(f"\n  BSH: {bsh}")
        for label in labels:
            r = all_results[label].get(bsh)
            if r:
                print(f"    {label:<20s} → {r['xtide_name']}")

    # ── Per-station comparison ──
    def print_table(title, stations, show_labels):
        print(f"\n{'='*120}")
        print(title)
        print(f"{'='*120}")

        print(f"\n  {'BSH Station':<42s}", end='')
        for label in show_labels:
            print(f" │ {label:^25s}", end='')
        print()

        print(f"  {'':42s}", end='')
        for _ in show_labels:
            print(f" │ {'|dT|HW':>7s} {'|dH|HW':>6s} {'|dT|NW':>7s} {'|dH|NW':>6s}", end='')
        print()

        print(f"  {'─'*42}", end='')
        for _ in show_labels:
            print(f" ┼ {'─'*27}", end='')
        print()

        for station in stations:
            print(f"  {station[:42]:<42s}", end='')
            for label in show_labels:
                r = all_results[label].get(station)
                if r:
                    print(f" │ {r['hw_dt']:>6.0f}m {r['hw_dh']:>5.2f}m {r['nw_dt']:>6.0f}m {r['nw_dh']:>5.2f}m", end='')
                else:
                    print(f" │ {'—':^27s}", end='')
            print()

        print(f"  {'─'*42}", end='')
        for _ in show_labels:
            print(f" ┼ {'─'*27}", end='')
        print()

        print(f"  {'DURCHSCHNITT':<42s}", end='')
        for label in show_labels:
            vals = [all_results[label][s] for s in stations if s in all_results[label]]
            if vals:
                print(f" │ {np.mean([v['hw_dt'] for v in vals]):>6.0f}m {np.mean([v['hw_dh'] for v in vals]):>5.2f}m "
                      f"{np.mean([v['nw_dt'] for v in vals]):>6.0f}m {np.mean([v['nw_dh'] for v in vals]):>5.2f}m", end='')
            else:
                print(f" │ {'—':^27s}", end='')
        print()

    def print_bias_table(title, stations, show_labels):
        print(f"\n{'='*120}")
        print(title)
        print(f"{'='*120}")

        print(f"\n  {'BSH Station':<42s}", end='')
        for label in show_labels:
            print(f" │ {label:^25s}", end='')
        print()

        print(f"  {'':42s}", end='')
        for _ in show_labels:
            print(f" │ {'dT HW':>7s} {'dH HW':>6s} {'dT NW':>7s} {'dH NW':>6s}", end='')
        print()

        print(f"  {'─'*42}", end='')
        for _ in show_labels:
            print(f" ┼ {'─'*27}", end='')
        print()

        for station in stations:
            print(f"  {station[:42]:<42s}", end='')
            for label in show_labels:
                r = all_results[label].get(station)
                if r:
                    print(f" │ {r['hw_dt_bias']:>+6.0f}m {r['hw_dh_bias']:>+5.2f}m {r['nw_dt_bias']:>+6.0f}m {r['nw_dh_bias']:>+5.2f}m", end='')
                else:
                    print(f" │ {'—':^27s}", end='')
            print()

        print(f"  {'─'*42}", end='')
        for _ in show_labels:
            print(f" ┼ {'─'*27}", end='')
        print()

        print(f"  {'DURCHSCHNITT':<42s}", end='')
        for label in show_labels:
            vals = [all_results[label][s] for s in stations if s in all_results[label]]
            if vals:
                print(f" │ {np.mean([v['hw_dt_bias'] for v in vals]):>+6.0f}m {np.mean([v['hw_dh_bias'] for v in vals]):>+5.2f}m "
                      f"{np.mean([v['nw_dt_bias'] for v in vals]):>+6.0f}m {np.mean([v['nw_dh_bias'] for v in vals]):>+5.2f}m", end='')
            else:
                print(f" │ {'—':^27s}", end='')
        print()

    print_table(
        f"VERGLEICH: DWF 2007 vs UTide — {len(common_stations)} gemeinsame BSH-Stationen",
        common_stations, labels
    )

    print_bias_table(
        "BIAS (positiv = XTide später/höher als BSH)",
        common_stations, labels
    )

    if utide_only:
        print_table(
            f"NUR IN UTIDE ({len(utide_only)} zusätzliche BSH-Stationen)",
            utide_only, labels[1:]  # skip DWF
        )


if __name__ == "__main__":
    main()
