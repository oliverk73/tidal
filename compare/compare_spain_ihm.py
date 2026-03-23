#!/usr/bin/env python3
"""
Compare XTide predictions (from harmonics_puertos_spain.tcd) with official
IHM (Instituto Hidrográfico de la Marina) predictions for all Spanish stations.
"""
import subprocess
import re
import os
import json
import time
import urllib.request
import numpy as np
from datetime import datetime, timedelta
from pyexcel_ods3 import get_data

TCD_FILE = '/usr/share/xtide/harmonics_puertos_spain.tcd'
ODS_FILE = '/home/oliver/harmonics/help/Spain/tide_stations_spain.ods'
API_URL = 'https://ideihm.covam.es/api-ihm/getmarea'

os.environ['HFILE_PATH'] = TCD_FILE

START_DATE = datetime(2026, 1, 1)
END_DATE = datetime(2026, 1, 31)


def read_stations():
    """Read station metadata from ODS. Returns list of dicts."""
    data = get_data(ODS_FILE)
    rows = data['Tabelle1']
    header = rows[0]
    stations = []
    for row in rows[1:]:
        if len(row) < 6:
            continue
        station = {}
        for i, col in enumerate(header):
            if i < len(row):
                station[col] = row[i]
            else:
                station[col] = ''
        # Skip stations without API ID
        api_id = station.get('ideihm.covam.es ID', '')
        if api_id == '' or api_id is None:
            continue
        stations.append(station)
    return stations


def fetch_ihm_predictions(api_id, date):
    """Fetch IHM predictions for one station and one day."""
    date_str = date.strftime('%Y%m%d')
    url = f'{API_URL}?request=gettide&id={api_id}&format=json&date={date_str}'
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode('utf-8')
            data = json.loads(raw)
    except Exception as e:
        return None

    predictions = []
    mareas = data.get('mareas', data)
    datos = mareas.get('datos', {})
    marea_list = datos.get('marea', [])
    if isinstance(marea_list, dict):
        marea_list = [marea_list]

    fecha_str = mareas.get('fecha', date.strftime('%Y-%m-%d'))

    for entry in marea_list:
        hora = entry.get('hora', '')
        altura = entry.get('altura', '')
        tipo = entry.get('tipo', '')

        if not hora or not altura:
            continue

        try:
            hour, minute = map(int, hora.split(':'))
            height = float(altura)
        except (ValueError, TypeError):
            continue

        dt_local = datetime(date.year, date.month, date.day, hour, minute)
        tide_type = 'HW' if tipo == 'pleamar' else 'NW'

        predictions.append({
            'datetime_local': dt_local,
            'height': height,
            'type': tide_type,
        })

    return predictions


def get_xtide_predictions(station_name, start_date, end_date, tz_offset):
    """Get HW/NW predictions from XTide."""
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
        # Format: "2026-01-28  1:28 AM CET   4.00 meters  Low Tide"
        #     or: "2026-01-28  1:28 AM WET   4.00 meters  Low Tide"
        m = re.match(
            r'(\d{4}-\d{2}-\d{2})\s+(\d{1,2}:\d{2}\s+[AP]M)\s+(\S+)\s+([\d.]+)\s+meters\s+(High|Low)\s+Tide',
            line
        )
        if m:
            date_str = m.group(1)
            time_str = m.group(2)
            height = float(m.group(4))
            tide_type = 'HW' if m.group(5) == 'High' else 'NW'

            dt_local = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %I:%M %p")

            predictions.append({
                'datetime_local': dt_local,
                'height': height,
                'type': tide_type,
            })

    return predictions


def match_events(ihm_preds, xt_preds, max_hours=3):
    """Match IHM events with nearest XTide events of same type."""
    matches = []
    used = set()

    for ihm in ihm_preds:
        best = None
        best_dt = timedelta(hours=max_hours)

        for j, xt in enumerate(xt_preds):
            if j in used or xt['type'] != ihm['type']:
                continue
            dt = abs(xt['datetime_local'] - ihm['datetime_local'])
            if dt < best_dt:
                best_dt = dt
                best = (j, xt)

        if best is not None:
            j, xt = best
            used.add(j)
            time_diff = (xt['datetime_local'] - ihm['datetime_local']).total_seconds() / 60
            height_diff = xt['height'] - ihm['height']
            matches.append({
                'ihm': ihm, 'xtide': xt,
                'time_diff_min': time_diff,
                'height_diff_m': height_diff,
            })

    return matches


def main():
    print("=" * 90)
    print("Vergleich: XTide (Puertos del Estado) vs IHM offizielle Vorhersagen — Januar 2026")
    print("=" * 90)

    stations = read_stations()
    print(f"\nStationen mit API-ID: {len(stations)}")

    all_station_results = []

    for station in stations:
        api_id = station['ideihm.covam.es ID']
        harmonics_name = str(station['harmonics name']).strip()
        official_name = str(station['official name in files']).strip()
        station_num = station['#']

        print(f"\n  {harmonics_name} (ID={api_id})...", end='', flush=True)

        # Determine timezone offset for XTide local time comparison
        lon = float(str(station['longitude']))
        snum = int(station_num)
        if 3450 <= snum <= 3471 or lon < -13:
            tz_offset = 0  # WET
        else:
            tz_offset = 1  # CET

        # Get XTide predictions for January
        xt_preds = get_xtide_predictions(harmonics_name, START_DATE, END_DATE + timedelta(days=1), tz_offset)
        if not xt_preds:
            print(" FEHLGESCHLAGEN (kein XTide-Output)")
            continue

        # Fetch IHM predictions day by day
        ihm_preds = []
        current = START_DATE
        while current <= END_DATE:
            day_preds = fetch_ihm_predictions(api_id, current)
            if day_preds:
                ihm_preds.extend(day_preds)
            current += timedelta(days=1)
            time.sleep(0.2)  # Rate limiting

        if not ihm_preds:
            print(" FEHLGESCHLAGEN (keine IHM-Daten)")
            continue

        # Match and compare
        matches = match_events(ihm_preds, xt_preds)
        if not matches:
            print(" FEHLGESCHLAGEN (keine Matches)")
            continue

        hw_matches = [m for m in matches if m['ihm']['type'] == 'HW']
        nw_matches = [m for m in matches if m['ihm']['type'] == 'NW']

        hw_dt = np.mean(np.abs([m['time_diff_min'] for m in hw_matches])) if hw_matches else 0
        hw_dh = np.mean(np.abs([m['height_diff_m'] for m in hw_matches])) if hw_matches else 0
        nw_dt = np.mean(np.abs([m['time_diff_min'] for m in nw_matches])) if nw_matches else 0
        nw_dh = np.mean(np.abs([m['height_diff_m'] for m in nw_matches])) if nw_matches else 0

        result = {
            'name': harmonics_name,
            'api_id': api_id,
            'n_matches': len(matches),
            'n_hw': len(hw_matches),
            'n_nw': len(nw_matches),
            'hw_dt_mean': hw_dt,
            'hw_dh_mean': hw_dh,
            'nw_dt_mean': nw_dt,
            'nw_dh_mean': nw_dh,
            'hw_dt_bias': np.mean([m['time_diff_min'] for m in hw_matches]) if hw_matches else 0,
            'nw_dt_bias': np.mean([m['time_diff_min'] for m in nw_matches]) if nw_matches else 0,
            'hw_dh_bias': np.mean([m['height_diff_m'] for m in hw_matches]) if hw_matches else 0,
            'nw_dh_bias': np.mean([m['height_diff_m'] for m in nw_matches]) if nw_matches else 0,
        }
        all_station_results.append(result)

        print(f" {len(matches)} Events: HW |dT|={hw_dt:.0f}min |dH|={hw_dh:.2f}m, NW |dT|={nw_dt:.0f}min |dH|={nw_dh:.2f}m")

    # Summary table
    if not all_station_results:
        print("\nKeine Ergebnisse!")
        return

    print(f"\n\n{'='*90}")
    print("ZUSAMMENFASSUNG: Mittlere absolute Abweichungen (XTide - IHM)")
    print(f"{'='*90}")
    print(f"  {'Station':<50s} {'N':>4s} {'|dT|HW':>7s} {'|dH|HW':>7s} {'|dT|NW':>7s} {'|dH|NW':>7s}")
    print(f"  {'─'*50} {'─'*4} {'─'*7} {'─'*7} {'─'*7} {'─'*7}")

    for r in sorted(all_station_results, key=lambda x: x['hw_dh_mean'] + x['nw_dh_mean']):
        print(f"  {r['name'][:50]:<50s} {r['n_matches']:>4d} "
              f"{r['hw_dt_mean']:>6.0f}m {r['hw_dh_mean']:>6.2f}m "
              f"{r['nw_dt_mean']:>6.0f}m {r['nw_dh_mean']:>6.2f}m")

    print(f"  {'─'*50} {'─'*4} {'─'*7} {'─'*7} {'─'*7} {'─'*7}")
    n_total = sum(r['n_matches'] for r in all_station_results)
    avg_hw_dt = np.mean([r['hw_dt_mean'] for r in all_station_results])
    avg_hw_dh = np.mean([r['hw_dh_mean'] for r in all_station_results])
    avg_nw_dt = np.mean([r['nw_dt_mean'] for r in all_station_results])
    avg_nw_dh = np.mean([r['nw_dh_mean'] for r in all_station_results])
    print(f"  {'DURCHSCHNITT':<50s} {n_total:>4d} "
          f"{avg_hw_dt:>6.0f}m {avg_hw_dh:>6.2f}m "
          f"{avg_nw_dt:>6.0f}m {avg_nw_dh:>6.2f}m")

    # Bias
    print(f"\n  BIAS (positiv = XTide später/höher als IHM):")
    print(f"  {'Station':<50s} {'dT HW':>7s} {'dH HW':>7s} {'dT NW':>7s} {'dH NW':>7s}")
    print(f"  {'─'*50} {'─'*7} {'─'*7} {'─'*7} {'─'*7}")
    for r in sorted(all_station_results, key=lambda x: x['nw_dh_bias']):
        print(f"  {r['name'][:50]:<50s} "
              f"{r['hw_dt_bias']:>+6.0f}m {r['hw_dh_bias']:>+6.2f}m "
              f"{r['nw_dt_bias']:>+6.0f}m {r['nw_dh_bias']:>+6.2f}m")
    print(f"  {'─'*50} {'─'*7} {'─'*7} {'─'*7} {'─'*7}")
    print(f"  {'DURCHSCHNITT':<50s} "
          f"{np.mean([r['hw_dt_bias'] for r in all_station_results]):>+6.0f}m "
          f"{np.mean([r['hw_dh_bias'] for r in all_station_results]):>+6.2f}m "
          f"{np.mean([r['nw_dt_bias'] for r in all_station_results]):>+6.0f}m "
          f"{np.mean([r['nw_dh_bias'] for r in all_station_results]):>+6.2f}m")


if __name__ == '__main__':
    main()
