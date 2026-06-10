#!/usr/bin/env python3
# -*- coding: iso-8859-1 -*-
"""PLA Thames Tidal Predictions -> UTide-Harmonics fuer 10 Themse-Stationen.

Quelle: tidepredictions.pla.co.uk (Port of London Authority), 2 Jahre
Stundenwerte 2025-2026 in GMT, lokal gesichert unter
water_levels/PLA_thames/hourly_<code>.csv (siehe Memory project_pla_thames_source).

Ersetzt die tidetimes-abgeleiteten Bloecke in harmonics_utide_tidetables.txt
in-place (Namen/Koordinaten bleiben). Konstituenten: UTide auto + erweitertes
Flachwasser-Set (Eval: OOS sigma_t 4.7-8.0 min vs. 37 min vorher).
Richmond Lock: Halbschleusen-Regime, harmonisch nur naeherungsweise
(sigma_t ~38 min) -> confidence 5 + quality: approximate.

Usage:
    python3 fit_pla_thames.py --dry    # nur fitten + berichten
    python3 fit_pla_thames.py          # fitten + tidetables.txt ersetzen
"""
import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import utide

sys.path.insert(0, '/home/oliver/py')
sys.path.insert(0, '/home/oliver/batch')
from refit_tidetimes_bst import parse_blocks, render_consts
from generate_germany_harmonics_175 import CONSTITUENTS_175, find_xtide_match

TIDETABLES = Path('/home/oliver/harmonics/utide/harmonics_utide_tidetables.txt')
DATA_DIR = Path('/home/oliver/water_levels/PLA_thames')

# Erweitertes Flachwasser-Set (zusaetzlich zu UTide-auto), aus der Eval
EXTRA = ['M8', 'M10', '3MK7', '2MK5', 'MSK6', '2SM6', '3MS8', 'MK4', 'SK4',
         '2MN6', 'MSN6', 'M3', 'SO3', 'MO3', 'SK3', '2MS6', 'M6', 'M4',
         'MS4', 'MN4', 'S4', '2SM2', 'MSF']

# code -> (Name in tidetables.txt, confidence, approx-Flag)
STATIONS = {
    '0103':  ('Margate, England, United Kingdom', 7, False),
    '0110':  ('Southend-on-Sea, England, United Kingdom', 7, False),
    '0110A': ('Coryton, England, United Kingdom', 7, False),
    '0111':  ('Tilbury, England, United Kingdom', 7, False),
    '0112':  ('North Woolwich, England, United Kingdom', 7, False),
    '0113':  ('London Bridge (Tower Pier), England, United Kingdom', 7, False),
    '0113A': ('Chelsea Bridge, England, United Kingdom', 7, False),
    '0116':  ('Richmond Lock, England, United Kingdom', 5, True),
    '0116A': ('Shivering Sand, England, United Kingdom', 7, False),
    '0129':  ('Walton-On-The-Naze, England, United Kingdom', 7, False),
}


def fit(code, lat):
    df = pd.read_csv(DATA_DIR / f'hourly_{code}.csv', parse_dates=['dt'])
    t = pd.DatetimeIndex(df['dt'])
    h = df['h'].values
    coef = utide.solve(t, h, lat=lat, nodal=True, trend=False, method='ols',
                       conf_int='none', verbose=False, constit='auto')
    names = sorted({n.strip() for n in coef['name']} | set(EXTRA))
    coef = utide.solve(t, h, lat=lat, nodal=True, trend=False, method='ols',
                       conf_int='none', verbose=False, constit=names)
    from utide._ut_constants import ut_constants
    ct = ut_constants['const']
    allnames = [x.strip() for x in ct.name]
    res = {}
    for i, uname in enumerate(coef['name']):
        uname = uname.strip()
        if uname not in allnames:
            continue
        speed = ct.freq[allnames.index(uname)] * 360.0
        xn, _ = find_xtide_match(uname, speed)
        if xn is None:
            continue
        res[xn] = (float(coef['A'][i]), float(coef['g'][i]) % 360.0)
    rec = utide.reconstruct(t, coef, verbose=False)
    resid = h - rec['h']
    r2 = 1 - float(np.sum(resid ** 2)) / float(np.sum((h - h.mean()) ** 2))
    rms = float(np.sqrt(np.mean(resid ** 2)))
    return (float(coef['mean']), res, r2, rms, len(h),
            t[0].strftime('%Y-%m-%d'), t[-1].strftime('%Y-%m-%d'))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry', action='store_true')
    args = ap.parse_args()

    raw = TIDETABLES.read_text(encoding='iso-8859-1')
    lines = raw.split('\n')
    blocks = {b['name']: b for b in parse_blocks(lines)}

    replaced = {}
    for code, (name, conf, approx) in STATIONS.items():
        b = blocks.get(name)
        if b is None:
            print(f'{name}: NICHT in tidetables.txt — uebersprungen')
            continue
        ctext = '\n'.join(b['comments'])
        m_lat = re.search(r'# !latitude:\s*([-\d.]+)', ctext)
        lat = float(m_lat.group(1)) if m_lat else 51.5
        mean, res, r2, rms, npts, t0, t1 = fit(code, lat)
        print(f'{name}: r2={r2:.5f} rms={rms:.4f}m const={len(res)}')

        new_comments = []
        for c in b['comments']:
            if c.startswith('# source:'):
                new_comments.append('# source: Derived from PLA Thames Tidal Predictions (2y hourly, GMT) with UTide')
            elif c.startswith('# datum:'):
                new_comments.append('# datum: Chart Datum (PLA)')
            elif c.startswith('# confidence:'):
                new_comments.append(f'# confidence: {conf}')
            elif c.startswith('# date_imported:'):
                new_comments.append(f'# date_imported: {datetime.now().strftime("%Y%m%d")}')
            elif re.match(r'^# (utide:|R\^2 = |bst_fix:|quality:|station_id_context:|pla_)', c):
                continue  # werden unten neu gesetzt
            elif 'Harmonic constants derived from tidetimes' in c or \
                 'using UTide' in c and 'cosine' in c or \
                 re.match(r'^# \d+ HW/LW points', c) or \
                 re.match(r'^# from \d{4}-', c) or \
                 re.match(r'^# Constituents analyzed', c):
                continue  # alte tidetimes-Beschreibung raus
            else:
                new_comments.append(c)
        ins = next((i for i, c in enumerate(new_comments) if c.startswith('# !')), len(new_comments))
        extra = [
            f'# station_id_context: UKHO-{code}',
            f'# pla_gauge: {code}',
            '# license_note: PLA-Disclaimer personal use only - Einbau mit Wissen des Betreibers',
            f'# utide: pts={npts} period={t0}..{t1} r2={r2:.4f} rms={rms:.4f}m const={len(res)}',
        ]
        if approx:
            extra.append('# quality: approximate (Richmond half-tide lock haelt Mindestpegel; harmonisch nur Naeherung, sigma_t ~38min)')
        for k, line in enumerate(extra):
            new_comments.insert(ins + k, line)

        replaced[b['start']] = (b, render_consts(mean, res), new_comments)

    if args.dry or not replaced:
        print('DRY RUN — Datei unveraendert.')
        return

    out = []
    i = 0
    n = len(lines)
    while i < n:
        if i in replaced:
            b, const_lines, new_comments = replaced[i]
            out.extend(new_comments)
            out.append(lines[b['name_idx']])
            out.append(b['meridian'])
            out.extend(const_lines)
            i = b['end']
        else:
            out.append(lines[i])
            i += 1
    TIDETABLES.write_text('\n'.join(out), encoding='iso-8859-1')
    print(f'Geschrieben: {TIDETABLES} ({len(replaced)} Bloecke ersetzt)')


if __name__ == '__main__':
    main()
