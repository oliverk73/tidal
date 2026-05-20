#!/usr/bin/env python3
"""
Download radar water-level data from IOC Sea Level Monitoring for Puerto Barrios
(code=prba). Chunks by month, filters to rad sensor, resamples to hourly mean.
"""
import json
import time
import requests
import pandas as pd
from pathlib import Path

OUTPUT_DIR = Path('/home/oliver/water_levels/Guatemala_IOC')
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_CSV = OUTPUT_DIR / 'prba_Puerto_Barrios.csv'
API = 'http://www.ioc-sealevelmonitoring.org/service.php'

START = '2014-03-01'
END   = '2025-07-04'


def fetch_month(code, month_start):
    month_end = (pd.Timestamp(month_start) + pd.offsets.MonthEnd(1)).strftime('%Y-%m-%d')
    params = {
        'query': 'data',
        'code': code,
        'format': 'json',
        'timestart': month_start,
        'timestop': month_end,
    }
    for attempt in range(3):
        try:
            r = requests.get(API, params=params, timeout=120)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            if attempt < 2:
                time.sleep(10 * (attempt + 1))
            else:
                print(f"  ERROR {month_start}: {e}")
                return []
    return []


def main():
    months = pd.date_range(START, END, freq='MS')
    all_rad = []
    for m in months:
        ms = m.strftime('%Y-%m-%d')
        data = fetch_month('prba', ms)
        rad = [(d['stime'], d['slevel']) for d in data if d.get('sensor') == 'rad']
        print(f"  {ms}: {len(rad)} rad records", flush=True)
        all_rad.extend(rad)
        time.sleep(0.5)

    if not all_rad:
        print("No data retrieved")
        return

    df = pd.DataFrame(all_rad, columns=['time', 'level_m'])
    df['time'] = pd.to_datetime(df['time'])
    df = df.drop_duplicates(subset='time').sort_values('time').set_index('time')

    # Outlier removal: 3-sigma on full series, then on residuals from rolling median
    rolling = df['level_m'].rolling('1h', center=True).median()
    resid = df['level_m'] - rolling
    mask = resid.abs() < 0.5  # drop spikes > 50 cm from local median
    before = len(df)
    df = df[mask].dropna()
    print(f"Dropped {before - len(df)} spikes (>50cm from 1h rolling median)")

    # Resample to hourly mean using nearest-hour rounding (avoids ~14.5°
    # M2 phase lag from labeling [HH:00, HH+1:00) bin at HH:00).
    hourly = df['level_m'].shift(freq='30min').resample('1h').mean().dropna()
    hourly.to_csv(OUT_CSV, header=['waterlevel_m'])

    years = len(hourly) / (24 * 365.25)
    print(f"\nRaw hourly: {len(hourly)} values ({years:.1f} years) saved to {OUT_CSV.name}")
    print(f"Mean: {hourly.mean():.3f} m, std: {hourly.std():.3f} m")

    # Produce a datum-corrected series for 2014-2018 (stable sensor window)
    # for use in UTide pipeline. Sensor had recurring datum jumps so we
    # subtract a 30-day rolling median to isolate the tidal signal.
    stable = hourly.loc['2014-03-01':'2018-12-31']
    trend = stable.rolling('30D', center=True, min_periods=24*7).median()
    detrended = (stable - trend + stable.mean()).dropna()

    pipeline_csv = Path('/home/oliver/water_levels/Caribbean_UHSLC_CubaJamaicaBahamas/prba_Puerto_Barrios.csv')
    pipeline_csv.parent.mkdir(parents=True, exist_ok=True)
    detrended.to_csv(pipeline_csv, header=['waterlevel_m'])
    print(f"\nDetrended 2014-2018 for UTide: {len(detrended)} values -> {pipeline_csv}")
    print(f"Mean: {detrended.mean():.3f} m, std: {detrended.std():.3f} m")


if __name__ == '__main__':
    main()
