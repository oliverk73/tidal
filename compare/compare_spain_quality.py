#!/usr/bin/env python3
"""
Compare Spanish tide predictions from our harmonics files against
official IHM (Instituto Hidrográfico de la Marina) predictions.

Uses XTide's `tide` command for our predictions, IHM API for official ones.
"""
import json
import subprocess
import re
import time as time_module
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import requests

PUERTOS_TCD = "/home/oliver/harmonics/ihm/harmonics_puertos_spain.tcd"
TICON4_TCD = "/home/oliver/harmonics/ticon/harmonics_ticon4_worldwide_edited.tcd"
IHM_API = "https://ideihm.covam.es/api-ihm/getmarea"
MADRID_TZ = ZoneInfo('Europe/Madrid')

# Station mapping: search_name -> (ihm_id, puertos_name, ticon4_name)
STATIONS = [
    ('Pasajes',        1,  'Pasajes, España',        'Pasajes, España'),
    ('Bilbao',         2,  'Bilbao, España',          'Bilbao, España'),
    ('Santander',      3,  'Santander, España',       'Santander, España'),
    ('Gijón',          6,  'Gijón, España',           'Gijón, España'),
    ('San Cibrao',    14,  'San Cibrao, España',      'San Cibrao, España'),
    ('A Coruña',      20,  'A Coruña, España',        'A Coruña, España'),
    ('Vigo',          29,  'Vigo, España',             'Vigo, España'),
    ('Mazagón',       36,  'Mazagón (Huelva), Spain',  'Mazagón (Huelva), Spain'),
    ('Cádiz',         42,  None,                       'Cádiz, España'),
    ('Algeciras',     49,  'Algeciras (San Roque), España', 'Algeciras, Spain'),
    ('Tarifa',        48,  'Tarifa, España',           'Tarifa, España'),
    ('Arrecife',      53,  'Arrecife, Lanzarote, Islas Canarias, España', 'Arrecife, Lanzarote, Islas Canarias, España'),
    ('Puerto de la Luz', 56, 'Puerto de la Luz, Gran Canaria, España', 'Puerto de la Luz, Gran Canaria, España'),
    ('Sta Cruz Tenerife', 60, 'Santa Cruz de Tenerife, Islas Canarias, España', 'Santa Cruz de Tenerife, Islas Canarias, España'),
    ('Sta Cruz La Palma', 66, 'Santa Cruz de La Palma, Islas Canarias, España', 'Santa Cruz de La Palma, Islas Canarias, España'),
]

TEST_START = datetime(2026, 3, 24)
TEST_DAYS = 14


def get_xtide_extrema(tcd_path, station_name, start, end):
    """Get HW/LW predictions from XTide."""
    cmd = [
        'tide',
        '-l', station_name,
        '-b', start.strftime('%Y-%m-%d %H:%M'),
        '-e', end.strftime('%Y-%m-%d %H:%M'),
        '-m', 'p', '-em', 'pSsMm',  # plain mode, suppress sun/moon
    ]
    env = dict(__import__('os').environ)
    env['HFILE_PATH'] = tcd_path
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, env=env)
        output = result.stdout + result.stderr
    except Exception as e:
        return None

    extrema = []
    for line in output.split('\n'):
        line = line.strip()
        if not line:
            continue
        # Parse: "2026-03-24 12:38 AM CET  -1.62 meters  Low Tide"
        m = re.match(
            r'(\d{4}-\d{2}-\d{2})\s+(\d{1,2}:\d{2}\s+[AP]M)\s+(\w+)\s+'
            r'(-?[\d.]+)\s+meters\s+(High|Low)\s+Tide',
            line
        )
        if m:
            date_str, time_str, tz_abbr, height, tide_type = m.groups()
            dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %I:%M %p")
            # XTide outputs DST variants in summer — convert to standard time
            # CEST→CET for mainland, WEST→WET for Canary Islands
            # IHM always outputs standard time (CET for mainland, WET for Canaries)
            if tz_abbr in ('CEST', 'WEST'):
                dt = dt - timedelta(hours=1)
            extrema.append({
                'time': dt,
                'height': float(height),
                'type': 'pleamar' if tide_type == 'High' else 'bajamar',
            })
    return extrema


def fetch_ihm_predictions(ihm_id, start, days):
    """Fetch official HW/LW predictions from IHM API."""
    all_data = []
    for d in range(days):
        date = start + timedelta(days=d)
        date_str = date.strftime('%Y%m%d')
        url = f"{IHM_API}?request=gettide&id={ihm_id}&format=json&date={date_str}"
        try:
            resp = requests.get(url, timeout=15)
            if resp.status_code != 200:
                continue
            data = resp.json()
            mareas = data.get('mareas', {}).get('datos', {}).get('marea', [])
            if isinstance(mareas, dict):
                mareas = [mareas]
            for m in mareas:
                hora = m['hora']
                h, mi = hora.split(':')
                # IHM always returns CET (UTC+1), no DST correction needed
                cet_dt = datetime(date.year, date.month, date.day,
                                  int(h), int(mi))
                all_data.append({
                    'time': cet_dt,
                    'height': float(m['altura']),
                    'type': m['tipo'],
                })
        except Exception as e:
            print(f"    IHM error for {date_str}: {e}")
        time_module.sleep(0.2)
    return all_data


def compare_extrema(our_data, ihm_data):
    """Match and compare HW/LW events."""
    comparisons = []
    for ihm in ihm_data:
        best = None
        best_dt = None
        for our in our_data:
            if our['type'] != ihm['type']:
                continue
            dt_min = abs((our['time'] - ihm['time']).total_seconds()) / 60.0
            if dt_min > 180:
                continue
            if best_dt is None or dt_min < best_dt:
                best_dt = dt_min
                best = our

        if best is not None:
            dt_signed = (best['time'] - ihm['time']).total_seconds() / 60.0
            dh = best['height'] - ihm['height']
            comparisons.append({
                'ihm_time': ihm['time'],
                'ihm_height': ihm['height'],
                'our_time': best['time'],
                'our_height': best['height'],
                'type': ihm['type'],
                'dt_min': dt_signed,
                'dh': dh,
            })
    return comparisons


def main():
    print("=" * 90)
    print("Vergleich: Spanische Tidenvorhersagen vs. offizielle IHM-Vorhersagen")
    print(f"Zeitraum: {TEST_START.strftime('%d.%m.%Y')} — "
          f"{(TEST_START + timedelta(days=TEST_DAYS)).strftime('%d.%m.%Y')} ({TEST_DAYS} Tage)")
    print("=" * 90)

    end = TEST_START + timedelta(days=TEST_DAYS)
    all_results = []

    for display_name, ihm_id, puertos_name, ticon4_name in STATIONS:
        print(f"\n{'━' * 90}")
        print(f"  {display_name} (IHM ID: {ihm_id})")
        print(f"{'━' * 90}")

        # Fetch IHM reference
        ihm_data = fetch_ihm_predictions(ihm_id, TEST_START, TEST_DAYS)
        if not ihm_data:
            print("  Keine IHM-Daten")
            continue
        print(f"  IHM: {len(ihm_data)} HW/NW")

        for source_name, tcd_path, station_name in [
            ('Puertos', PUERTOS_TCD, puertos_name),
            ('TiCon4', TICON4_TCD, ticon4_name),
        ]:
            if station_name is None:
                continue

            our_data = get_xtide_extrema(tcd_path, station_name, TEST_START, end)
            if not our_data:
                print(f"  {source_name}: Keine XTide-Daten für '{station_name}'")
                continue

            comparisons = compare_extrema(our_data, ihm_data)
            if not comparisons:
                print(f"  {source_name}: Keine Matches (XTide: {len(our_data)} Extrema)")
                continue

            td = np.array([c['dt_min'] for c in comparisons])
            hd = np.array([c['dh'] for c in comparisons])
            hw = [c for c in comparisons if c['type'] == 'pleamar']
            nw = [c for c in comparisons if c['type'] == 'bajamar']

            print(f"\n  {source_name} ({len(comparisons)} Vergleiche):")
            print(f"  {'':>4s} {'Ø ΔZeit':>10s} {'σ ΔZeit':>10s} {'Ø ΔHöhe':>10s} {'σ ΔHöhe':>10s}")
            if hw:
                hw_td = [c['dt_min'] for c in hw]
                hw_hd = [c['dh'] for c in hw]
                print(f"  {'HW':>4s} {np.mean(hw_td):>+9.0f}m {np.std(hw_td):>9.0f}m {np.mean(hw_hd):>+9.3f}m {np.std(hw_hd):>9.3f}m")
            if nw:
                nw_td = [c['dt_min'] for c in nw]
                nw_hd = [c['dh'] for c in nw]
                print(f"  {'NW':>4s} {np.mean(nw_td):>+9.0f}m {np.std(nw_td):>9.0f}m {np.mean(nw_hd):>+9.3f}m {np.std(nw_hd):>9.3f}m")
            print(f"  {'Ges':>4s} {np.mean(td):>+9.0f}m {np.std(td):>9.0f}m {np.mean(hd):>+9.3f}m {np.std(hd):>9.3f}m")

            all_results.append({
                'station': display_name,
                'source': source_name,
                'n': len(comparisons),
                'mean_dt': np.mean(td),
                'std_dt': np.std(td),
                'mean_dh': np.mean(hd),
                'std_dh': np.std(hd),
                'abs_dh': np.mean(np.abs(hd)),
            })

    # Summary
    if all_results:
        print(f"\n\n{'=' * 90}")
        print("ZUSAMMENFASSUNG")
        print(f"{'=' * 90}")
        print(f"{'Station':<25s} {'Quelle':<9s} {'N':>3s} {'Ø ΔZeit':>9s} {'σ ΔZeit':>9s} {'Ø ΔHöhe':>9s} {'Ø |ΔH|':>9s}")
        print(f"{'─'*25} {'─'*9} {'─'*3} {'─'*9} {'─'*9} {'─'*9} {'─'*9}")

        for r in all_results:
            print(f"{r['station']:<25s} {r['source']:<9s} {r['n']:>3d} "
                  f"{r['mean_dt']:>+8.0f}m {r['std_dt']:>8.0f}m "
                  f"{r['mean_dh']:>+8.3f}m {r['abs_dh']:>8.3f}m")

        for src in ['Puertos', 'TiCon4']:
            sr = [r for r in all_results if r['source'] == src]
            if sr:
                print(f"\n  {src} Durchschnitt ({len(sr)} Stationen):")
                print(f"    Ø Zeitfehler:  {np.mean([r['mean_dt'] for r in sr]):+.0f} min (σ {np.mean([r['std_dt'] for r in sr]):.0f} min)")
                print(f"    Ø |Höhenfehler|: {np.mean([r['abs_dh'] for r in sr]):.3f} m")


if __name__ == '__main__':
    main()
