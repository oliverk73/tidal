#!/usr/bin/env python3
"""
Download WLP + UTide-Analyse für fehlende Kanada-Stationen.
Appendet Harmonics-Blöcke an die bestehenden Provinz-Dateien.

NB (4): Port Elgin, Cape Tormentine, Cap Pelé, Miguasha
QC (1): Ogdensburg (am St. Lawrence, hat wlp)
"""
import sys
sys.path.insert(0, '/home/oliver/py')

import os
import time
import datetime
import pickle
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import utide

from generate_germany_harmonics_175 import (
    CONSTITUENTS_175,
    find_xtide_match,
)

API = 'https://api-sine.dfo-mpo.gc.ca/api/v1'
OUT_DIR = Path('/home/oliver/water_levels/Canada_IWLS_missing')
OUT_DIR.mkdir(parents=True, exist_ok=True)
CHECKPOINT_DIR = Path('/home/oliver/harmonics/utide/checkpoints_ca_missing')
CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)

NB_PATH = Path('/home/oliver/harmonics/utide/harmonics_utide_canada_nb.txt')
QC_PATH = Path('/home/oliver/harmonics/utide/harmonics_utide_canada_qc.txt')

STATIONS = [
    # (code, name, lat, lon, province, target_file)
    ('01785', 'Port Elgin',      46.051875, -64.082768, 'New Brunswick', NB_PATH),
    ('01790', 'Cape Tormentine',  46.134722, -63.776806, 'New Brunswick', NB_PATH),
    ('01800', 'Cap Pelé',         46.235833, -64.261333, 'New Brunswick', NB_PATH),
    ('02196', 'Miguasha',         48.098812, -66.347140, 'New Brunswick', NB_PATH),
    ('14505', 'Ogdensburg',       44.709167, -75.485556, 'Quebec',        QC_PATH),
]

CONSTIT_93 = [
    'J1', 'K1', 'O1', 'OO1', 'P1', 'Q1', '2Q1', 'RHO1', 'ALP1', 'BET1',
    'CHI1', 'NO1', 'PHI1', 'PI1', 'PSI1', 'SIG1', 'SO1', 'THE1', '2PO1',
    'TAU1', 'UPS1',
    'K2', 'L2', 'M2', 'N2', '2N2', 'R2', 'S2', 'T2', 'LDA2', 'MU2',
    'NU2', 'EPS2', 'ETA2', '2SM2', '2NS2', 'SKM2', 'OP2', 'MKS2', 'MSN2',
    'OQ2',
    'MF', 'MSF', 'MM', 'SA', 'SSA', 'MSM',
    'M3', 'MK3', 'MO3', 'SK3', 'SO3', 'NO3',
    'M4', 'MN4', 'MS4', 'MK4', 'S4', 'SN4', 'N4', 'SL4', '3MS4',
    '2MK5', '2SK5', '2MO5', 'MNO5', 'MSK5', '3KM5', '2MP5', '3MP5', 'MNK5',
    'M6', '2MN6', '2MS6', '2MK6', '2NM6', '2SM6', 'MSK6', 'MSN6', 'S6',
    'M7', '3MK7',
    'M8', '3MN8', '3MS8', '3MK8',
    '4MK9', 'M10', 'M12',
    'H1', 'H2', 'S1',
]


def get_station_id(code):
    r = requests.get(f'{API}/stations', params={'code': code}, timeout=20)
    data = r.json()
    return data[0]['id'] if data else None


def download_wlp(code, station_id, start='2025-01-01', end='2025-12-31'):
    """Download wlp 15-min for one year."""
    csv_path = OUT_DIR / f'{code}_wlp.csv'
    if csv_path.exists() and csv_path.stat().st_size > 5000:
        print(f'  ✓ CSV bereits vorhanden: {csv_path.name}')
        return csv_path

    start_d = datetime.date.fromisoformat(start)
    end_d = datetime.date.fromisoformat(end)
    months = []
    cur = start_d.replace(day=1)
    while cur <= end_d:
        nxt = (cur.replace(day=28) + datetime.timedelta(days=4)).replace(day=1)
        m_end = min(nxt - datetime.timedelta(days=1), end_d)
        months.append((cur, m_end))
        cur = nxt

    rows = []
    for m_start, m_end in months:
        try:
            r = requests.get(
                f'{API}/stations/{station_id}/data',
                params={
                    'time-series-code': 'wlp',
                    'from': f'{m_start}T00:00:00Z',
                    'to':   f'{m_end}T23:59:59Z',
                    'resolution': 'FIFTEEN_MINUTES',
                },
                timeout=30,
            )
            if r.status_code == 200:
                for d in r.json():
                    rows.append((d['eventDate'], d['value']))
            elif r.status_code == 429:
                time.sleep(10)
        except Exception as e:
            print(f'    API-Fehler {m_start}: {e}')
        sys.stdout.write('.'); sys.stdout.flush()
        time.sleep(1.2)
    print()

    if not rows:
        print('  ✗ KEINE WLP-Daten')
        return None

    df = pd.DataFrame(rows, columns=['time', 'waterlevel_m'])
    df = df.drop_duplicates(subset='time').sort_values('time')
    df.to_csv(csv_path, index=False)
    print(f'  ✓ {len(df)} Werte → {csv_path.name}')
    return csv_path


def analyze(code, name, lat, lon, csv_path):
    ckpt = CHECKPOINT_DIR / f'{code}.pkl'
    if ckpt.exists():
        with open(ckpt, 'rb') as f:
            r = pickle.load(f)
        print(f'  ✓ Checkpoint (R²={r["r_squared"]:.4f})')
        return r

    df = pd.read_csv(csv_path)
    df['time'] = pd.to_datetime(df['time'], utc=True).dt.tz_localize(None)
    df = df.dropna(subset=['waterlevel_m'])
    if len(df) < 2000:
        print(f'  ✗ Zu wenig Daten ({len(df)})')
        return None

    dts = df['time'].values.astype('datetime64[ns]')
    dts = pd.to_datetime(dts).to_pydatetime()
    levels = df['waterlevel_m'].values.astype(np.float64)

    print(f'  UTide solve ({len(dts)} Beob., lat={lat:.2f})...', end='', flush=True)
    coef = utide.solve(
        np.array(dts), levels, lat=lat,
        nodal=True, trend=False, method='ols',
        conf_int='none', verbose=False, constit=CONSTIT_93,
    )
    print(' OK')

    from utide._ut_constants import ut_constants
    const_table = ut_constants['const']
    utide_all = [n.strip() for n in const_table.name]

    ures = {}
    for i, uname in enumerate(coef['name']):
        uname = uname.strip()
        if uname not in utide_all:
            continue
        idx = utide_all.index(uname)
        utide_speed = const_table.freq[idx] * 360.0
        xt_name, xt_speed = find_xtide_match(uname, utide_speed)
        if xt_name is None:
            continue
        ures[xt_name] = {
            'amplitude': coef['A'][i],
            'phase': coef['g'][i] % 360,
            'speed': xt_speed,
        }

    constituents = []
    n_an = 0
    for cname, speed in CONSTITUENTS_175:
        if cname in ures:
            r = ures[cname]
            constituents.append({'name': cname, 'amplitude': r['amplitude'],
                                 'phase': r['phase'], 'speed': speed})
            n_an += 1
        else:
            constituents.append({'name': cname, 'amplitude': 0.0, 'phase': 0.0,
                                 'speed': speed, 'not_analyzed': True})

    recon = utide.reconstruct(np.array(dts), coef, verbose=False)
    res = levels - recon['h']
    ss_res = np.sum(res**2)
    ss_tot = np.sum((levels - levels.mean())**2)
    r2 = 1 - ss_res/ss_tot if ss_tot > 0 else 0
    rms = np.sqrt(np.mean(res**2))

    m2 = next((c['amplitude'] for c in constituents if c['name']=='M2'), 0)
    k1 = next((c['amplitude'] for c in constituents if c['name']=='K1'), 0)

    result = {
        'mean': coef['mean'], 'constituents': constituents, 'n_analyzed': n_an,
        'r_squared': r2, 'rms_error': rms, 'm2_amp': m2, 'k1_amp': k1,
        'n_obs': len(dts), 'start_time': dts[0], 'end_time': dts[-1],
        'code': code, 'name': name, 'lat': lat, 'lon': lon,
    }
    with open(ckpt, 'wb') as f:
        pickle.dump(result, f)
    print(f'  R²={r2:.4f}, RMS={rms:.4f}m, M2={m2:.4f}m, K1={k1:.4f}m')
    return result


def format_block(r, province):
    L = []
    L.append('# Harmonic constants derived from CHS tide predictions (reverse-engineered)')
    L.append(f'# using UTide (v{utide.__version__}) with {r["n_obs"]} data points')
    L.append(f'# from {r["start_time"].strftime("%Y-%m-%d")} to {r["end_time"].strftime("%Y-%m-%d")}')
    L.append(f'# R^2 = {r["r_squared"]:.4f}, RMS error = {r["rms_error"]:.4f} m')
    L.append(f'# Constituents analyzed: {r["n_analyzed"]}')
    L.append('#')
    L.append(f'# {r["name"]}')
    L.append('# BEGIN HOT COMMENTS')
    L.append('# country: Canada')
    L.append(f'# province: {province}')
    L.append('# source: Derived from CHS tide predictions (reverse-engineered) with UTide harmonic analysis')
    L.append(f'# station_id_context: CHS-{r["code"]}')
    L.append(f'# date_imported: {datetime.datetime.now().strftime("%Y%m%d")}')
    L.append('# datum: LLWLT')
    L.append('# confidence: 9')
    L.append('# !units: meters')
    L.append(f'# !longitude: {r["lon"]:.6f}')
    L.append(f'# !latitude: {r["lat"]:.6f}')
    L.append(f'{r["name"]}, {province}, Canada')
    L.append('+00:00 :UTC')
    L.append(f'{r["mean"]:.4f} meters')
    for c in r['constituents']:
        if c.get('not_analyzed') or c['amplitude'] < 0.00005:
            L.append('x 0 0')
        else:
            L.append(f'{c["name"]:15s} {c["amplitude"]:.4f}  {c["phase"]:.2f}')
    return '\n'.join(L)


def main():
    print('='*70); print('Kanada fehlende Stationen — Download + UTide + Append'); print('='*70)

    results = []  # list of (result, province, target_path)

    for code, name, lat, lon, province, target in STATIONS:
        print(f'\n── {code} | {name} ({province}) ──')
        sid = get_station_id(code)
        if not sid:
            print('  ✗ Station ID nicht gefunden'); continue
        csv = download_wlp(code, sid)
        if not csv:
            continue
        r = analyze(code, name, lat, lon, csv)
        if r:
            results.append((r, province, target))

    # Group and append
    by_target = {}
    for r, prov, target in results:
        by_target.setdefault(target, []).append((r, prov))

    for target, items in by_target.items():
        print(f'\nAnhängen an {target.name} ({len(items)} Stationen)')
        # Safety: ensure file ends with newline
        content = target.read_bytes()
        if content and not content.endswith(b'\n'):
            with open(target, 'ab') as f:
                f.write(b'\n')
        with open(target, 'a', encoding='iso-8859-1') as f:
            for r, prov in items:
                block = format_block(r, prov)
                f.write(block)
                f.write('\n')
        print(f'  ✓ {target.stat().st_size/1024:.0f} KB')

    print('\n'+'='*70); print('FERTIG')
    for r, prov, _ in results:
        y = r['n_obs']/(4*24*365.25)
        print(f'  {r["code"]} {r["name"]:<25s} {prov:<15s} {y:.1f}J R²={r["r_squared"]:.4f} RMS={r["rms_error"]:.3f}m M2={r["m2_amp"]:.3f}m')


if __name__ == '__main__':
    main()
