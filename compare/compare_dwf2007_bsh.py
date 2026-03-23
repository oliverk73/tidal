#!/usr/bin/env python3
"""
Compare XTide predictions (from DWF 2007 harmonics) with BSH official predictions
for all matching German tide stations — January 2026.
"""
import subprocess
import re
import os
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path

TCD_FILE = Path("/usr/share/xtide/harmonics-dwf-20070318_no_us_no_dupes.tcd")
TXT_FILE = Path("/home/oliver/harmonics/classic/harmonics-dwf-20070318_no_us_no_dupes.txt")
BSH_DIR = Path("/home/oliver/harmonics/help/BSH")

os.environ['HFILE_PATH'] = str(TCD_FILE)

# Manual mapping: BSH station name -> XTide station name
# (DWF 2007 uses different naming than BSH)
BSH_TO_XTIDE = {
    "Cuxhaven, Steubenhöft, Elbe": "Cuxhaven (Steubenhöft), Germany",
    "Bremerhaven, Weser, Alter Leuchtturm": "Bremerhaven (Alter Leuchtturm), Germany",
    "Bremen, Oslebshausen, Weser": "Bremen, Oslebshausen, Germany",
    "Borkum, Fischerbalje": "Borkum (Fischerbalje), Germany",
    "Emden, Neue Seeschleuse": "Emden (Neue Seeschleuse), Germany",
    "Hamburg, St. Pauli, Elbe": "Hamburg (St. Pauli), Germany",
    "Helgoland, Binnenhafen": "Helgoland, Germany",
    "Husum, Schleuse": "Husum (Speerwerk), Germany",
    "Norderney, Riffgat": "Norderney (Riffgat), Germany",
    "Wilhelmshaven, Alter Vorhafen": "Wilhelmshaven (Alter Vorhafen), Germany",
}


# ── Parse BSH predictions ──────────────────────────────────────────────

def parse_bsh_file(bsh_path):
    """Parse BSH VB2 file. Returns (station_name, pnp_offset, list of {datetime_utc, height_pnp, type})."""
    station_name = None
    pnp_offset = None
    predictions = []

    with open(bsh_path, 'r', encoding='latin-1') as f:
        for line in f:
            line = line.strip()
            if line.startswith('A04#'):
                parts = line.split(':#')
                if len(parts) >= 2:
                    station_name = parts[1].rstrip('#').strip()
            if line.startswith('D01#'):
                # D01#PNP u. NHN :#- 5.03 #
                m = re.search(r'([+-]?\s*[\d.]+)', line.split(':#')[1] if ':#' in line else '')
                if m:
                    pnp_offset = float(m.group(1).replace(' ', ''))
            if not line.startswith('VB2#'):
                continue
            parts = line.split('#')
            hw_nw = parts[3].strip()
            date_str = re.sub(r'\s+', '', parts[5].strip())
            time_str = parts[6].strip()
            height_str = parts[7].strip()

            day, month, year = date_str.split('.')
            day, month, year = int(day), int(month), int(year)
            hour, minute = map(int, time_str.split(':'))
            height = float(height_str)

            dt_mez = datetime(year, month, day, hour, minute)
            dt_utc = dt_mez - timedelta(hours=1)

            predictions.append({
                'datetime_utc': dt_utc,
                'datetime_mez': dt_mez,
                'height_pnp': height,
                'type': 'HW' if hw_nw == 'H' else 'NW',
            })

    return station_name, pnp_offset, predictions


# ── Generate XTide predictions ─────────────────────────────────────────

def get_xtide_stations():
    """List all German station names in the TCD text file."""
    stations = []
    with open(TXT_FILE, 'r', encoding='latin-1') as f:
        for line in f:
            stripped = line.strip()
            if stripped.endswith(', Germany') and not stripped.startswith('#'):
                stations.append(stripped)
    return stations


def get_xtide_predictions(station_name, start_date, end_date):
    """Get HW/NW predictions from XTide for a station and date range."""
    result = subprocess.run(
        ['tide', '-l', station_name,
         '-b', start_date.strftime('%Y-%m-%d 00:00'),
         '-e', end_date.strftime('%Y-%m-%d 00:00'),
         '-m', 'p', '-em', 'pSsMm'],
        capture_output=True, text=True, env=os.environ,
        timeout=30,
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
            date_str = m.group(1)
            time_str = m.group(2)
            tz_label = m.group(3)
            height = float(m.group(4))
            tide_type = 'HW' if m.group(5) == 'High' else 'NW'

            dt_local = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %I:%M %p")
            utc_offset = 2 if tz_label == 'CEST' else 1
            dt_utc = dt_local - timedelta(hours=utc_offset)

            predictions.append({
                'datetime_utc': dt_utc,
                'datetime_mez': dt_local,
                'height_pnp': height,
                'type': tide_type,
            })

    return predictions


# ── Matching ───────────────────────────────────────────────────────────

def normalize(s):
    """Normalize for matching."""
    s = s.lower()
    for old, new in [('ä','ae'),('ö','oe'),('ü','ue'),('ß','ss'),
                     ('\xe4','ae'),('\xf6','oe'),('\xfc','ue')]:
        s = s.replace(old, new)
    return re.sub(r'[^a-z0-9]', '', s)


def find_xtide_match(bsh_name, xtide_stations):
    """Find matching XTide station for a BSH station name."""
    if bsh_name in BSH_TO_XTIDE:
        candidate = BSH_TO_XTIDE[bsh_name]
        if candidate in xtide_stations:
            return candidate

    norm_bsh = normalize(bsh_name)
    best_match = None
    best_score = 0

    for xt_name in xtide_stations:
        norm_xt = normalize(xt_name.replace(', Germany', ''))

        if norm_bsh == norm_xt:
            return xt_name

        if norm_bsh in norm_xt or norm_xt in norm_bsh:
            score = min(len(norm_bsh), len(norm_xt))
            if score > best_score:
                best_score = score
                best_match = xt_name

        bsh_parts = set(re.split(r'[,\s]+', norm_bsh))
        xt_parts = set(re.split(r'[,\s]+', norm_xt))
        common = bsh_parts & xt_parts
        if len(common) >= 2 and len(common) / max(len(bsh_parts), len(xt_parts)) > 0.5:
            score = len(common) * 10
            if score > best_score:
                best_score = score
                best_match = xt_name

    if best_score >= 8:
        return best_match
    return None


def match_events(bsh_preds, xt_preds, max_hours=3):
    """Match BSH events with nearest XTide events of same type."""
    matches = []
    used = set()

    for bsh in bsh_preds:
        best = None
        best_dt = timedelta(hours=max_hours)

        for j, xt in enumerate(xt_preds):
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
                'bsh': bsh, 'xtide': xt,
                'time_diff_min': time_diff,
                'height_diff_m': height_diff,
            })

    return matches


# ── Main ───────────────────────────────────────────────────────────────

def main():
    print("=" * 90)
    print("Vergleich: XTide (DWF 2007 Harmonics) vs BSH offizielle Vorhersagen — Januar 2026")
    print("=" * 90)

    xtide_stations = get_xtide_stations()
    print(f"\nDeutsche XTide-Stationen in DWF 2007: {len(xtide_stations)}")
    for s in xtide_stations:
        print(f"  - {s}")

    bsh_files = sorted(BSH_DIR.glob("DE__*2026.txt"))
    bsh_files = [f for f in bsh_files if ':' not in str(f)]
    print(f"\nBSH-Vorhersagedateien: {len(bsh_files)}")

    print(f"\n{'BSH Station':<45s} {'XTide Match':<45s}")
    print(f"{'─'*45} {'─'*45}")

    matched_pairs = []
    unmatched_bsh = []

    for bsh_file in bsh_files:
        bsh_name, pnp_offset, bsh_preds = parse_bsh_file(bsh_file)
        if not bsh_name or not bsh_preds:
            continue

        bsh_preds_jan = [p for p in bsh_preds if p['datetime_utc'].month == 1]

        xt_match = find_xtide_match(bsh_name, xtide_stations)
        if xt_match:
            matched_pairs.append((bsh_name, xt_match, bsh_preds_jan, bsh_file.name, pnp_offset))
            pnp_str = f" (PNP={pnp_offset:+.2f}m)" if pnp_offset else ""
            print(f"  {bsh_name:<43s} → {xt_match}{pnp_str}")
        else:
            unmatched_bsh.append(bsh_name)

    print(f"\nGematcht: {len(matched_pairs)}, Nicht gematcht: {len(unmatched_bsh)}")

    # Generate XTide predictions and compare
    print(f"\n{'='*90}")
    print("Erzeuge XTide-Vorhersagen und vergleiche...")
    print(f"{'='*90}")

    start = datetime(2026, 1, 1)
    end = datetime(2026, 2, 1)

    all_station_results = []

    for bsh_name, xt_name, bsh_preds, bsh_filename, pnp_offset in matched_pairs:
        print(f"\n  {xt_name}...", end='', flush=True)

        xt_preds = get_xtide_predictions(xt_name, start, end)
        if not xt_preds:
            print(" FEHLGESCHLAGEN (kein XTide-Output)")
            continue

        matches = match_events(bsh_preds, xt_preds)
        if not matches:
            print(" FEHLGESCHLAGEN (keine Matches)")
            continue

        # Calculate mean height offset between BSH (PNP) and XTide (datum)
        # to remove the systematic datum difference
        height_offset = np.mean([m['bsh']['height_pnp'] - m['xtide']['height_pnp'] for m in matches])

        # Recalculate height differences with datum correction
        for m in matches:
            m['height_diff_corrected'] = m['xtide']['height_pnp'] - (m['bsh']['height_pnp'] - height_offset)

        hw_matches = [m for m in matches if m['bsh']['type'] == 'HW']
        nw_matches = [m for m in matches if m['bsh']['type'] == 'NW']

        hw_dt = np.mean(np.abs([m['time_diff_min'] for m in hw_matches])) if hw_matches else 0
        hw_dh = np.mean(np.abs([m['height_diff_corrected'] for m in hw_matches])) if hw_matches else 0
        nw_dt = np.mean(np.abs([m['time_diff_min'] for m in nw_matches])) if nw_matches else 0
        nw_dh = np.mean(np.abs([m['height_diff_corrected'] for m in nw_matches])) if nw_matches else 0

        all_dt = np.mean(np.abs([m['time_diff_min'] for m in matches]))
        all_dh = np.mean(np.abs([m['height_diff_corrected'] for m in matches]))

        result = {
            'bsh_name': bsh_name,
            'xtide_name': xt_name,
            'n_matches': len(matches),
            'n_hw': len(hw_matches),
            'n_nw': len(nw_matches),
            'hw_dt_mean': hw_dt,
            'hw_dh_mean': hw_dh,
            'nw_dt_mean': nw_dt,
            'nw_dh_mean': nw_dh,
            'all_dt_mean': all_dt,
            'all_dh_mean': all_dh,
            'hw_dt_bias': np.mean([m['time_diff_min'] for m in hw_matches]) if hw_matches else 0,
            'nw_dt_bias': np.mean([m['time_diff_min'] for m in nw_matches]) if nw_matches else 0,
            'hw_dh_bias': np.mean([m['height_diff_corrected'] for m in hw_matches]) if hw_matches else 0,
            'nw_dh_bias': np.mean([m['height_diff_corrected'] for m in nw_matches]) if nw_matches else 0,
            'height_offset': height_offset,
        }
        all_station_results.append(result)

        print(f" {len(matches)} Events (Offset={height_offset:.2f}m): "
              f"HW |dT|={hw_dt:.0f}min |dH|={hw_dh:.2f}m, NW |dT|={nw_dt:.0f}min |dH|={nw_dh:.2f}m")

    # Summary table
    print(f"\n\n{'='*90}")
    print("ZUSAMMENFASSUNG: Mittlere absolute Abweichungen (XTide DWF2007 - BSH)")
    print(f"{'='*90}")
    print(f"  {'Station':<40s} {'N':>5s} {'|dT|HW':>8s} {'|dH|HW':>8s} {'|dT|NW':>8s} {'|dH|NW':>8s} {'|dT|all':>8s} {'|dH|all':>8s}")
    print(f"  {'─'*40} {'─'*5} {'─'*8} {'─'*8} {'─'*8} {'─'*8} {'─'*8} {'─'*8}")

    for r in sorted(all_station_results, key=lambda x: x['all_dh_mean']):
        print(f"  {r['xtide_name'][:40]:<40s} {r['n_matches']:>5d} "
              f"{r['hw_dt_mean']:>7.0f}m {r['hw_dh_mean']:>7.2f}m "
              f"{r['nw_dt_mean']:>7.0f}m {r['nw_dh_mean']:>7.2f}m "
              f"{r['all_dt_mean']:>7.0f}m {r['all_dh_mean']:>7.2f}m")

    if all_station_results:
        print(f"  {'─'*40} {'─'*5} {'─'*8} {'─'*8} {'─'*8} {'─'*8} {'─'*8} {'─'*8}")
        avg_hw_dt = np.mean([r['hw_dt_mean'] for r in all_station_results])
        avg_hw_dh = np.mean([r['hw_dh_mean'] for r in all_station_results])
        avg_nw_dt = np.mean([r['nw_dt_mean'] for r in all_station_results])
        avg_nw_dh = np.mean([r['nw_dh_mean'] for r in all_station_results])
        avg_all_dt = np.mean([r['all_dt_mean'] for r in all_station_results])
        avg_all_dh = np.mean([r['all_dh_mean'] for r in all_station_results])
        n_total = sum(r['n_matches'] for r in all_station_results)
        print(f"  {'DURCHSCHNITT':<40s} {n_total:>5d} "
              f"{avg_hw_dt:>7.0f}m {avg_hw_dh:>7.2f}m "
              f"{avg_nw_dt:>7.0f}m {avg_nw_dh:>7.2f}m "
              f"{avg_all_dt:>7.0f}m {avg_all_dh:>7.2f}m")

        # Bias summary
        print(f"\n  BIAS (Mittelwert, positiv = XTide später/höher als BSH):")
        print(f"  {'Station':<40s} {'dT HW':>8s} {'dH HW':>8s} {'dT NW':>8s} {'dH NW':>8s}")
        print(f"  {'─'*40} {'─'*8} {'─'*8} {'─'*8} {'─'*8}")
        for r in sorted(all_station_results, key=lambda x: x['nw_dh_bias']):
            print(f"  {r['xtide_name'][:40]:<40s} "
                  f"{r['hw_dt_bias']:>+7.0f}m {r['hw_dh_bias']:>+7.2f}m "
                  f"{r['nw_dt_bias']:>+7.0f}m {r['nw_dh_bias']:>+7.2f}m")
        avg_hw_dt_bias = np.mean([r['hw_dt_bias'] for r in all_station_results])
        avg_hw_dh_bias = np.mean([r['hw_dh_bias'] for r in all_station_results])
        avg_nw_dt_bias = np.mean([r['nw_dt_bias'] for r in all_station_results])
        avg_nw_dh_bias = np.mean([r['nw_dh_bias'] for r in all_station_results])
        print(f"  {'─'*40} {'─'*8} {'─'*8} {'─'*8} {'─'*8}")
        print(f"  {'DURCHSCHNITT':<40s} "
              f"{avg_hw_dt_bias:>+7.0f}m {avg_hw_dh_bias:>+7.2f}m "
              f"{avg_nw_dt_bias:>+7.0f}m {avg_nw_dh_bias:>+7.2f}m")


if __name__ == "__main__":
    main()
