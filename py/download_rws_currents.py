#!/usr/bin/env python3
"""
Download current measurements (Stroomsnelheid + Stroomrichting) from
Rijkswaterstaat for all stations that provide both variables.

For each station both series are downloaded and merged on timestamp into
one CSV with columns: speed_cm_s, direction_deg. These can then be fed
into UTide (complex u+iv) to derive harmonic constants for tidal currents.
"""

import os
import time
import datetime
import ddlpy
import pandas as pd

OUTPUT_DIR = '/home/oliver/currents/Netherlands'
START_DATE = datetime.datetime(2015, 1, 1)
END_DATE = datetime.datetime(2026, 3, 18)


def get_current_stations():
    print("Lade Stationskatalog von RWS...")
    locs = ddlpy.locations()
    shd = locs[locs['Grootheid.Code'] == 'STROOMSHD']
    rtg = locs[locs['Grootheid.Code'] == 'STROOMRTG']
    common = sorted(set(shd.index) & set(rtg.index))
    print(f"{len(common)} Stationen mit SHD+RTG gefunden.")
    return shd, rtg, common


def download_series(station_row, start, end):
    m = ddlpy.measurements(station_row, start_date=start, end_date=end)
    if m is None or len(m) == 0:
        return None
    return m[['Meetwaarde.Waarde_Numeriek']].rename(
        columns={'Meetwaarde.Waarde_Numeriek': 'value'}
    )


def download_station(code, shd_df, rtg_df, start, end, output_dir):
    safe = code.replace('/', '_').replace('\\', '_').replace(' ', '_')
    csv_path = os.path.join(output_dir, f"{safe}.csv")
    if os.path.exists(csv_path) and os.path.getsize(csv_path) > 1024:
        print(f"  vorhanden, überspringe.")
        return True

    shd_row = shd_df.loc[[code]].iloc[0]
    rtg_row = rtg_df.loc[[code]].iloc[0]

    # Year-by-year streaming to keep memory bounded (Eemshaven etc. are huge).
    import gc
    tmp_path = csv_path + '.partial'
    header_written = False
    total = 0
    for yr in range(start.year, end.year + 1):
        y_start = max(start, datetime.datetime(yr, 1, 1))
        y_end = min(end, datetime.datetime(yr, 12, 31, 23, 59, 59))
        print(f"  {yr}:", end='', flush=True)
        try:
            s = download_series(shd_row, y_start, y_end)
            r = download_series(rtg_row, y_start, y_end)
        except Exception as e:
            print(f" ERR({e.__class__.__name__})", end='', flush=True)
            continue
        if s is None or r is None or len(s) == 0 or len(r) == 0:
            print(" -", end='', flush=True)
            continue
        s.columns = ['speed']; r.columns = ['direction']
        s = s[~s.index.duplicated(keep='first')]
        r = r[~r.index.duplicated(keep='first')]
        m = s.join(r, how='inner')
        del s, r; gc.collect()
        if m.empty:
            print(" 0", end='', flush=True); del m; continue
        m.to_csv(tmp_path, mode='a', header=not header_written)
        header_written = True
        total += len(m)
        print(f" {len(m)}", end='', flush=True)
        del m; gc.collect()
    if total == 0:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        print(" KEINE DATEN")
        return False
    os.rename(tmp_path, csv_path)
    years = total / (6 * 24 * 365.25)
    print(f"  -> {total} Werte ({years:.1f} Jahre)")
    return True


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    shd, rtg, codes = get_current_stations()

    print(f"Zeitraum: {START_DATE.date()} .. {END_DATE.date()}")
    print(f"Ausgabe:  {OUTPUT_DIR}\n")

    success = failed = 0
    for i, code in enumerate(codes):
        name = shd.loc[[code]].iloc[0].get('Naam', code)
        print(f"[{i+1}/{len(codes)}] {name} ({code})")
        try:
            ok = download_station(code, shd, rtg, START_DATE, END_DATE, OUTPUT_DIR)
        except Exception as e:
            print(f"  FEHLER: {e}")
            ok = False
        success += int(ok)
        failed += int(not ok)
        if i < len(codes) - 1:
            time.sleep(1)

    print(f"\nErfolgreich: {success}  Fehlgeschlagen: {failed}  Gesamt: {len(codes)}")


if __name__ == '__main__':
    main()
