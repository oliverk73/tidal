#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CMEMS-In-Situ-Pegel für weltweite ECHTE Gezeitenlücken (koordinatenbasiert
gefunden: >6 km von jeder DB-Station, >=1 J Daten, nicht Ostsee/Mittelmeer-
mikrotidal, keine IJsselmeer-Seen). Gemessen, conf>=4 -> Vorrang vor ATT-Transfer.
Wiederverwendet load_nc/harmonic_analysis aus parse_cmems_spain_5.

Aufruf: python3 py/parse_cmems_gaps.py            # dry-run
        python3 py/parse_cmems_gaps.py --write    # an observations.txt anfügen
"""
from __future__ import annotations
import sys
from datetime import datetime
from pathlib import Path

import utide
sys.path.insert(0, '/home/oliver/py')
from parse_cmems_spain_5 import load_nc, harmonic_analysis, XTIDE_175

NC_DIR = Path('/home/oliver/water_levels/CMEMS_gaps')
TARGET = Path('/home/oliver/harmonics/utide/harmonics_utide_observations.txt')
IDX = ('/tmp/cmems_idx2/INSITU_GLO_PHY_SSH_DISCRETE_MY_013_053/'
       'cmems_obs-ins_glo_phy-ssh_my_na_PT1H_202411/index_history.txt')

# file -> (Anzeigename, Land, Gewässer)
META = {
    'GL_TS_TG_Yap_60minute.nc':          ('Yap (Colonia)', 'Micronesia', 'Pacific Ocean (Caroline Islands)'),
    'GL_TS_TG_BlueBay_60minute.nc':      ('Blue Bay', 'Mauritius', 'Indian Ocean'),
    'GL_TS_TG_Barahona_60minute.nc':     ('Barahona', 'Dominican Republic', 'Caribbean Sea'),
    'NO_TS_TG_HanstholmTG_60minute.nc':  ('Hanstholm', 'Denmark', 'North Sea (Skagerrak approaches)'),
    'GL_TS_TG_Agalega_60minute.nc':      ('Agalega', 'Mauritius', 'Indian Ocean'),
    'GL_TS_TG_BlowingPoint_60minute.nc': ('Blowing Point', 'Anguilla', 'Caribbean Sea'),
    'IR_TS_TG_Rosslare_60minute.nc':     ('Rosslare', 'Ireland', "Celtic Sea / St George's Channel"),
    'GL_TS_TG_Scarborough_60minute.nc':  ('Scarborough, Tobago', 'Trinidad and Tobago', 'Caribbean Sea'),
    'GL_TS_TG_Portsmouth2_60minute.nc':  ('Portsmouth', 'Dominica', 'Caribbean Sea'),
    'GL_TS_TG_Charlotteville_60minute.nc': ('Charlotteville, Tobago', 'Trinidad and Tobago', 'Caribbean Sea'),
    'GL_TS_TG_LaCeiba_60minute.nc':      ('La Ceiba', 'Honduras', 'Caribbean Sea'),
}


def index_meta():
    """basename -> (lat, lon, institution)."""
    out = {}
    for line in open(IDX, encoding='utf-8', errors='replace'):
        if line.startswith('#') or not line.strip():
            continue
        p = line.rstrip('\n').split(',')
        if len(p) < 9:
            continue
        bn = p[1].split('/')[-1]
        try:
            out[bn] = (float(p[2]), float(p[4]), p[8].strip())
        except ValueError:
            continue
    return out


def fmt_block(name, country, water, cst, network, lat, lon, res, n, t0, t1, conf):
    nl = f"{name}, {country}"
    per = f"{t0:%Y-%m-%d}..{t1:%Y-%m-%d}"
    L = [
        '# Harmonic constants derived from CMEMS in-situ sea level observations',
        f'# using UTide (v{utide.__version__}) with {n} observations',
        f'# R^2 = {res["r2"]:.4f}, RMS error = {res["rms"]:.4f} m',
        '#', f'# {nl}', '# BEGIN HOT COMMENTS',
        f'# country: {country}', f'# water_body: {water}',
        '# source: Derived from CMEMS in-situ data with UTide harmonic analysis',
        f'# station_id_context: CMEMS-{cst}',
        f'# date_imported: {datetime.now():%Y%m%d}',
        '# datum: Mean Sea Level',
        f'# confidence: {conf}',
        f'# cmems_code: {cst}',
        f'# institution: {network.replace(";", " / ")[:120]}',
        f'# utide: pts={n} period={per} r2={res["r2"]:.4f} rms={res["rms"]:.4f}m const={res["n_analyzed"]}',
        '# !units: meters', f'# !longitude: {lon:.4f}', f'# !latitude: {lat:.4f}',
        nl, '+00:00 :UTC', f'{res["mean"]:.4f} meters',
    ]
    for c in res['constituents']:
        if c.get('missing') or c['amp'] < 0.00005:
            L.append('x 0 0')
        else:
            L.append(f'{c["name"]:15s} {c["amp"]:.4f}  {c["phase"]:.2f}')
    return '\n'.join(L)


def main():
    write = '--write' in sys.argv
    idx = index_meta()
    blocks = []
    for fn, (name, country, water) in META.items():
        path = NC_DIR / fn
        if not path.exists():
            print(f'{name}: FEHLT {fn}'); continue
        lat, lon, inst = idx.get(fn, (None, None, 'CMEMS'))
        cst = fn.split('_TG_')[1].replace('_60minute.nc', '')
        times, levels = load_nc(path)
        # Nodalzyklus-Regel: max ~19 Jahre (sonst Nodal-Fehler + OOM bei UTide).
        import numpy as np
        if len(times):
            cutoff = times[-1] - np.timedelta64(19 * 365 + 5, 'D')
            keep = times >= cutoff
            times, levels = times[keep], levels[keep]
        if len(levels) < 720:
            print(f'{name}: zu wenig Daten ({len(levels)})'); continue
        t0 = times[0].astype('M8[s]').astype(datetime)
        t1 = times[-1].astype('M8[s]').astype(datetime)
        res = harmonic_analysis(times, levels, lat)
        m2 = next((c['amp'] for c in res['constituents'] if c['name'] == 'M2'), 0)
        rng = 2 * sum(next((c['amp'] for c in res['constituents'] if c['name'] == k), 0)
                      for k in ('M2', 'S2', 'K1', 'O1'))
        # conf: gemessen=6; mikrotidal (Hub<0.5m) oder schwacher Fit -> 4
        if res['r2'] < 0.50:
            print(f'{name:22} R2={res["r2"]:.3f} -> VERWORFEN (Fit zu schwach, '
                  f'Vorhersage unzuverlässig)')
            continue
        conf = 6 if (rng >= 0.5 and res['r2'] >= 0.7) else 4
        flag = '  [mikrotidal -> conf4]' if conf == 4 else ''
        print(f'{name:22} R2={res["r2"]:.3f} M2={m2*100:5.1f}cm ~Hub={rng:.2f}m '
              f'pts={len(times)} ({t0:%Y}-{t1:%Y}) conf{conf}{flag}')
        blocks.append(fmt_block(name, country, water, cst, inst, lat, lon, res,
                                len(times), t0, t1, conf))
    if write and blocks:
        raw = TARGET.read_bytes().decode('iso-8859-1')
        if not raw.endswith('\n'):
            raw += '\n'
        raw += '\n'.join(blocks) + '\n'
        TARGET.write_bytes(raw.encode('iso-8859-1'))
        n = raw.count('# !latitude:')
        print(f'\nAngefügt: {len(blocks)} Blöcke -> {TARGET} (!latitude jetzt {n})')
    else:
        print(f'\n(Dry-run, {len(blocks)} Blöcke. --write zum Anfügen.)')


if __name__ == '__main__':
    main()
