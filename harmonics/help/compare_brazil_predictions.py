#!/usr/bin/env python3
"""
Compare all Brazilian tide predictions from harmonics against official DHN predictions.

For each Brazilian station found in any harmonics source:
1. Extract official HW/LW from DHN 2026 PDF
2. Generate prediction using tide command from each harmonics source
3. Compare timing and height differences
"""

import re
import os
import sys
import subprocess
import math
from datetime import datetime, timedelta
from collections import defaultdict
import fitz  # PyMuPDF

BASE = '/home/oliver/weather/tide_tables/brazil/'

# ============================================================
# Station definitions from parse script (all 55 DHN + coords)
# ============================================================
# Import from parse script
sys.path.insert(0, '/home/oliver/harmonics/help')
from parse_brazil_dhn_harmonics import STATIONS as DHN_STATIONS, parse_pdf_fitz

# ============================================================
# All harmonics sources with Brazilian stations
# ============================================================
HARMONICS_SOURCES = {
    'utide_brazil_dhn': '/usr/share/xtide/harmonics_utide_brazil_dhn.tcd',
    'utide_brazil': '/usr/share/xtide/harmonics_utide_brazil.tcd',
    'classic_1997': '/usr/share/xtide/harmonics-1997-05-25_mod.tcd',
    'classic_2004': '/usr/share/xtide/harmonics-2004-06-14_mod.tcd',
    'ticon4': '/usr/share/xtide/harmonics_ticon4_worldwide.tcd',
}

# Explicit name overrides where coordinate matching fails
# Format: {dhn_number: {source_name: [station_name, ...]}}
NAME_OVERRIDES = {
    18: {  # Areia Branca
        'utide_brazil': ['Areia Branca (TERMISA), Rio Grande do Norte, Brazil'],
        'utide_brazil_dhn': ['Areia Branca (Terminal Salineiro), Rio Grande do Norte, Brazil'],
        'classic_1997': ['Areia Branca (Terminal Salineiro), Rio Grande do Norte, Brazil'],
    },
    40: {  # Arraial do Cabo
        'utide_brazil_dhn': ['Arraial do Cabo (Porto do Forno), Rio de Janeiro, Brazil'],
        'classic_1997': ['Araial do Cabo (Porto do Forno), Rio de Janeiro, Brazil'],
    },
    47: {  # Ponta do Félix
        'utide_brazil_dhn': ['Ponta do Félix, Paraná, Brazil'],
    },
    49: {  # Paranaguá - Canal Sueste
        'utide_brazil_dhn': ['Ilha do Mel (Canal Sueste), Paraná, Brazil'],
    },
    50: {  # Paranaguá - Cais Oeste
        'utide_brazil_dhn': ['Paranaguá (Cais Oeste), Paraná, Brazil'],
        'classic_1997': ['Paranaguá (Cais Leste), Paraná, Brazil'],
    },
    51: {  # São Francisco do Sul
        'utide_brazil_dhn': ['São Francisco do Sul (Clube Náutico Cruzeiro do Sul), Santa Catarina, Brazil'],
        'classic_1997': ['São Francisco do Sul (Terminal Marítimo Gás Sul), Santa Catarina, Brazil'],
    },
    56: {  # Estação Antártica
        'utide_brazil_dhn': ['Estação Antártica Comandante Ferraz, Antártica, Brazil'],
    },
}


def get_tide_events(station_name, source_tcd, start_date, end_date):
    """Generate HW/LW events using tide command from a specific TCD file."""
    cmd = [
        'tide', '-l', station_name,
        '-b', start_date,
        '-e', end_date,
        '-m', 'p', '-f', 'c', '-z', '-u', 'm'
    ]
    env = os.environ.copy()
    env['HFILE_PATH'] = source_tcd

    try:
        result = subprocess.run(cmd, capture_output=True, timeout=30, env=env)
        if result.returncode != 0:
            return None
        try:
            stdout = result.stdout.decode('utf-8')
        except UnicodeDecodeError:
            stdout = result.stdout.decode('iso-8859-1')
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None

    events = []
    for line in stdout.strip().split('\n'):
        if not line or line.startswith('Indexing'):
            continue
        parts = line.split(',')
        if len(parts) < 5:
            continue
        event_type = parts[4].strip()
        if event_type not in ('High Tide', 'Low Tide'):
            continue
        # Parse date and time
        date_str = parts[1].strip()
        time_str = parts[2].strip()
        height_str = parts[3].strip().replace(' m', '')
        try:
            dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %I:%M %p UTC")
            height = float(height_str)
            events.append({
                'time': dt,
                'height': height,
                'type': 'HW' if event_type == 'High Tide' else 'LW'
            })
        except (ValueError, IndexError):
            continue

    return events


def list_brazil_stations(source_tcd):
    """List all Brazilian stations in a TCD file. Returns list of (name, lat, lon)."""
    cmd = ['tide', '-m', 'l']
    env = os.environ.copy()
    env['HFILE_PATH'] = source_tcd
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=30, env=env)
        # Try UTF-8 first (for ticon4 etc), fall back to ISO-8859-1
        try:
            stdout = result.stdout.decode('utf-8')
        except UnicodeDecodeError:
            stdout = result.stdout.decode('iso-8859-1')
    except:
        return []

    stations = []
    for line in stdout.strip().split('\n'):
        if 'Indexing' in line or 'Location list' in line:
            continue
        # Parse: "Station Name       Ref  12.3456° S,  45.6789° W"
        # Note: long names get truncated, so "Brazil" may be cut off
        m = re.match(r'^(.+?)\s{2,}Ref\s+(\d+\.?\d*).+?([NS]),\s+(\d+\.?\d*).+?([EW])', line)
        if not m:
            continue
        sname = m.group(1).strip()
        slat = float(m.group(2)) * (-1 if m.group(3) == 'S' else 1)
        slon = float(m.group(4)) * (-1 if m.group(5) == 'W' else 1)
        stations.append((sname, slat, slon))
    return stations


# Pre-build station listings for each source
_station_cache = {}

def get_station_list(source_tcd):
    if source_tcd not in _station_cache:
        _station_cache[source_tcd] = list_brazil_stations(source_tcd)
    return _station_cache[source_tcd]


def find_station_in_source(station_name, lat, lon, source_tcd, dhn_num=None, src_name=None):
    """Find a station in a TCD file by coordinates or explicit override.
    Returns the actual station name in this TCD, or None."""
    # Check explicit overrides first
    if dhn_num and src_name and dhn_num in NAME_OVERRIDES:
        overrides = NAME_OVERRIDES[dhn_num]
        if src_name in overrides:
            # Return first override name that works
            for override_name in overrides[src_name]:
                events = get_tide_events(override_name, source_tcd,
                                         "2026-01-01 00:00", "2026-01-02 00:00")
                if events:
                    return override_name

    # Fall back to coordinate matching
    stations = get_station_list(source_tcd)

    best_name = None
    best_dist = 0.006  # max ~670 meters

    for sname, slat, slon in stations:
        dist = math.sqrt((slat - lat)**2 + (slon - lon)**2)
        if dist < best_dist:
            best_dist = dist
            best_name = sname

    return best_name


def extract_dhn_events(station, year=2026):
    """Extract HW/LW events from a DHN PDF for a given year."""
    if year not in station['pdfs']:
        return None

    pdf_path = os.path.join(BASE, station['pdfs'][year])
    if not os.path.exists(pdf_path):
        return None

    try:
        entries = parse_pdf_fitz(pdf_path, year)
    except Exception as e:
        print(f"  PDF parse error: {e}")
        return None

    if not entries:
        return None

    # Convert to HW/LW events by detecting local maxima/minima
    entries.sort(key=lambda x: x[0])

    # DHN tables directly give HW/LW times and heights
    events = []
    for i, (dt, height) in enumerate(entries):
        # Determine if HW or LW by comparing with neighbors
        if i == 0:
            if len(entries) > 1:
                etype = 'HW' if height > entries[1][1] else 'LW'
            else:
                etype = 'HW'
        elif i == len(entries) - 1:
            etype = 'HW' if height > entries[i-1][1] else 'LW'
        else:
            prev_h = entries[i-1][1]
            next_h = entries[i+1][1]
            # Same day context
            if height >= prev_h and height >= next_h:
                etype = 'HW'
            elif height <= prev_h and height <= next_h:
                etype = 'LW'
            else:
                # Alternating pattern - check if higher or lower than mean
                mean_h = (prev_h + next_h) / 2
                etype = 'HW' if height > mean_h else 'LW'

        # DHN times are in local time (UTC-3 for most stations, UTC-2 for some)
        utc_offset = station.get('utc_offset', 3)
        dt_utc = dt + timedelta(hours=utc_offset)

        events.append({
            'time': dt_utc,
            'height': height,
            'type': etype
        })

    return events


def match_events(official, predicted, max_dt_hours=3):
    """Match official events to predicted events by type and time proximity."""
    matches = []
    used_pred = set()

    for off_evt in official:
        best_match = None
        best_dt = timedelta(hours=max_dt_hours)

        for j, pred_evt in enumerate(predicted):
            if j in used_pred:
                continue
            if pred_evt['type'] != off_evt['type']:
                continue
            dt = abs(pred_evt['time'] - off_evt['time'])
            if dt < best_dt:
                best_dt = dt
                best_match = (j, pred_evt)

        if best_match is not None:
            j, pred_evt = best_match
            used_pred.add(j)
            time_diff_min = (pred_evt['time'] - off_evt['time']).total_seconds() / 60
            height_diff = pred_evt['height'] - off_evt['height']
            matches.append({
                'official': off_evt,
                'predicted': pred_evt,
                'time_diff_min': time_diff_min,
                'height_diff_m': height_diff,
            })

    return matches


def compute_stats(matches):
    """Compute statistics from matched events."""
    if not matches:
        return None

    hw_matches = [m for m in matches if m['official']['type'] == 'HW']
    lw_matches = [m for m in matches if m['official']['type'] == 'LW']

    def stats_for(mlist):
        if not mlist:
            return None
        time_diffs = [m['time_diff_min'] for m in mlist]
        height_diffs = [m['height_diff_m'] for m in mlist]
        n = len(mlist)
        mean_t = sum(time_diffs) / n
        mean_h = sum(height_diffs) / n
        rms_t = math.sqrt(sum(t**2 for t in time_diffs) / n)
        rms_h = math.sqrt(sum(h**2 for h in height_diffs) / n)
        max_t = max(abs(t) for t in time_diffs)
        max_h = max(abs(h) for h in height_diffs)
        return {
            'n': n,
            'mean_time_min': mean_t,
            'rms_time_min': rms_t,
            'max_time_min': max_t,
            'mean_height_m': mean_h,
            'rms_height_m': rms_h,
            'max_height_m': max_h,
        }

    return {
        'all': stats_for(matches),
        'hw': stats_for(hw_matches),
        'lw': stats_for(lw_matches),
        'n_matched': len(matches),
    }


# ============================================================
# Main comparison
# ============================================================
def main():
    year = 2026
    # Use January for comparison (first month, full data)
    start_date = f"{year}-01-01 00:00"
    end_date = f"{year}-04-01 00:00"  # 3 months for good statistics

    print(f"=" * 100)
    print(f"Vergleich: Brasilianische Tidenvorhersagen vs. offizielle DHN-Vorhersagen ({year}, Jan-Mar)")
    print(f"=" * 100)

    # First, build a mapping of which stations exist in which sources
    print("\nSchritt 1: Stationen in Harmonics-Quellen suchen...")
    print("-" * 80)

    all_results = []
    unmatched = []

    for dhn_st in DHN_STATIONS:
        dhn_num = dhn_st['dhn']
        name = dhn_st['name']
        lat = dhn_st['lat']
        lon = dhn_st['lon']

        print(f"\nDHN {dhn_num:2d}: {name}")

        # Extract official predictions
        official = extract_dhn_events(dhn_st, year)
        if official is None:
            print(f"  ⚠ Keine offizielle 2026-PDF gefunden/parsbar")
            continue

        # Filter to Jan-Mar
        start_dt = datetime(year, 1, 1)
        end_dt = datetime(year, 4, 1)
        official_filtered = [e for e in official if start_dt <= e['time'] < end_dt]

        if len(official_filtered) < 10:
            print(f"  ⚠ Nur {len(official_filtered)} offizielle Events in Jan-Mar")
            if len(official_filtered) == 0:
                continue

        n_hw = sum(1 for e in official_filtered if e['type'] == 'HW')
        n_lw = sum(1 for e in official_filtered if e['type'] == 'LW')
        print(f"  Offiziell: {len(official_filtered)} Events ({n_hw} HW, {n_lw} LW)")

        station_results = {
            'dhn': dhn_num,
            'name': name,
            'n_official': len(official_filtered),
            'sources': {}
        }

        for src_name, src_tcd in HARMONICS_SOURCES.items():
            if not os.path.exists(src_tcd):
                continue

            # Find station in this source
            found_name = find_station_in_source(name, lat, lon, src_tcd,
                                                 dhn_num=dhn_num, src_name=src_name)
            if found_name is None:
                continue

            # Show if name differs between sources
            if found_name != name:
                print(f"    → In {src_name} als: {found_name}")

            # Generate predictions
            predicted = get_tide_events(found_name, src_tcd, start_date, end_date)
            if predicted is None or len(predicted) == 0:
                continue

            # Match and compare
            matches = match_events(official_filtered, predicted)
            stats = compute_stats(matches)

            if stats and stats['all']:
                s = stats['all']
                src_label = src_name.replace('_', ' ')
                matched_pct = stats['n_matched'] / len(official_filtered) * 100

                print(f"  {src_label:25s} ({found_name})")
                print(f"    Matches: {stats['n_matched']:4d}/{len(official_filtered)} ({matched_pct:.0f}%)"
                      f"  | Zeit: Ø{s['mean_time_min']:+5.0f}min RMS={s['rms_time_min']:5.0f}min Max={s['max_time_min']:5.0f}min"
                      f"  | Höhe: Ø{s['mean_height_m']:+.3f}m RMS={s['rms_height_m']:.3f}m Max={s['max_height_m']:.3f}m")

                if stats['hw']:
                    h = stats['hw']
                    print(f"    HW({h['n']:3d}): Zeit Ø{h['mean_time_min']:+5.0f}min RMS={h['rms_time_min']:5.0f}min"
                          f"  | Höhe Ø{h['mean_height_m']:+.3f}m RMS={h['rms_height_m']:.3f}m")
                if stats['lw']:
                    l = stats['lw']
                    print(f"    LW({l['n']:3d}): Zeit Ø{l['mean_time_min']:+5.0f}min RMS={l['rms_time_min']:5.0f}min"
                          f"  | Höhe Ø{l['mean_height_m']:+.3f}m RMS={l['rms_height_m']:.3f}m")

                station_results['sources'][src_name] = {
                    'found_as': found_name,
                    'stats': stats,
                }

        if not station_results['sources']:
            unmatched.append((dhn_num, name))
            print(f"  ✗ In keiner Harmonics-Quelle gefunden!")

        all_results.append(station_results)

    # Summary
    print(f"\n\n{'=' * 100}")
    print("ZUSAMMENFASSUNG")
    print(f"{'=' * 100}")

    print(f"\n{'Station':50s} {'Quelle':25s} {'Match%':>7s} {'ØZeit':>7s} {'RMSZeit':>8s} {'ØHöhe':>7s} {'RMSHöhe':>8s}")
    print("-" * 115)

    for r in all_results:
        for src_name, src_data in r['sources'].items():
            s = src_data['stats']['all']
            if s:
                matched_pct = src_data['stats']['n_matched'] / r['n_official'] * 100
                print(f"{r['name']:50s} {src_name:25s} {matched_pct:6.0f}% {s['mean_time_min']:+6.0f}m {s['rms_time_min']:7.0f}m "
                      f"{s['mean_height_m']:+6.3f} {s['rms_height_m']:7.3f}")

    if unmatched:
        print(f"\nKeine Harmonics-Zuordnung für:")
        for dhn, name in unmatched:
            print(f"  DHN {dhn}: {name}")

    # Check for Brazilian stations in harmonics that are NOT DHN stations
    print(f"\n\nNicht-DHN-Stationen in Harmonics-Quellen:")
    print("-" * 80)
    dhn_coords = {(round(s['lat'], 2), round(s['lon'], 2)) for s in DHN_STATIONS}

    for src_name, src_tcd in HARMONICS_SOURCES.items():
        if not os.path.exists(src_tcd):
            continue
        cmd = ['tide', '-m', 'l', '-f', 'c']
        env = os.environ.copy()
        env['HFILE_PATH'] = src_tcd
        try:
            result = subprocess.run(cmd, capture_output=True, env=env, timeout=30)
            try:
                stdout = result.stdout.decode('utf-8')
            except UnicodeDecodeError:
                stdout = result.stdout.decode('iso-8859-1')
        except:
            continue

        for line in stdout.strip().split('\n'):
            if 'Brazil' not in line:
                continue
            parts = line.split(',')
            if len(parts) < 3:
                continue
            try:
                sname = parts[0].strip().replace('|', ',')
                slat = round(float(parts[1].strip()), 2)
                slon = round(float(parts[2].strip()), 2)
                # Check if this is near any DHN station
                is_dhn = False
                for dlat, dlon in dhn_coords:
                    if abs(slat - dlat) < 0.15 and abs(slon - dlon) < 0.15:
                        is_dhn = True
                        break
                if not is_dhn:
                    print(f"  {src_name:25s}: {sname} ({slat}, {slon})")
            except (ValueError, IndexError):
                continue


if __name__ == '__main__':
    main()
