#!/usr/bin/env python3
# -*- coding: iso-8859-1 -*-
"""UTide-Fit der Firth-of-Forth/Tay 7-Hafen-Tafeln (GMT, kein BST-Shift).

Vergleicht den neuen Fit gegen die bestehenden Eintraege und (mit --write)
ersetzt die schwachen tidetimes-Bloecke in harmonics_utide_tidetables.txt
in-place (Methodik identisch zu refit_tidetimes_bst.py).
"""
import argparse
import re
import sys
from pathlib import Path

import numpy as np
import utide

sys.path.insert(0, '/home/oliver/batch')
sys.path.insert(0, '/home/oliver/py')
from batch_utide_uk_tidetimes import cosine_interpolate, CONSTIT_67
from generate_germany_harmonics_175 import CONSTITUENTS_175, find_xtide_match
from parse_sevenport_pdf import parse_many, PORTS
from refit_tidetimes_bst import parse_blocks, norm_name, render_consts

TIDETABLES = Path('/home/oliver/harmonics/utide/harmonics_utide_tidetables.txt')
PDFS = [Path('tide_tables/UK/sevenPortFormat_24.pdf'),
        Path('tide_tables/UK/sevenPortFormat_25.pdf'),
        Path('tide_tables/UK/sevPortFormat_26.pdf')]
SOURCE = 'Derived from Firth of Forth/Tay 7-port tide tables (GMT) with UTide'

# nur diese ersetzen; Dundee/Leith sind Messdaten, bleiben
REPLACE = {'Burntisland', 'Methil'}


def fit(hw_lw, lat):
    dts, levels = cosine_interpolate(hw_lw)
    coef = utide.solve(dts, levels, lat=lat, nodal=True, trend=False,
                       method='ols', conf_int='none', verbose=False,
                       constit=CONSTIT_67)
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
        if xn:
            res[xn] = (float(coef['A'][i]), float(coef['g'][i]) % 360.0)
    rec = utide.reconstruct(dts, coef, verbose=False)
    resid = levels - rec['h']
    ss = float(np.sum((levels - levels.mean()) ** 2))
    r2 = 1 - float(np.sum(resid ** 2)) / ss if ss > 0 else 0.0
    rms = float(np.sqrt(np.mean(resid ** 2)))
    return float(coef['mean']), res, r2, rms, dts[0], dts[-1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--write', action='store_true')
    args = ap.parse_args()

    data = parse_many(PDFS)
    lines = TIDETABLES.read_text(encoding='iso-8859-1').split('\n')
    blocks = parse_blocks(lines)
    byname = {norm_name(b['name']): b for b in blocks}

    print(f'{"Hafen":16s} {"alt R2":>7s} {"neu R2":>7s} {"neu RMS":>8s} {"pts":>5s}  Aktion')
    replaced = {}
    for name, _ in PORTS:
        lst = data[name]
        b = byname.get(norm_name(name))
        ctext = '\n'.join(b['comments']) if b else ''
        m = re.search(r'r2=([\d.]+)', ctext)
        old_r2 = float(m.group(1)) if m else float('nan')
        m_lat = re.search(r'# !latitude:\s*([-\d.]+)', ctext)
        lat = float(m_lat.group(1)) if m_lat else 56.0
        mean, res, r2, rms, t0, t1 = fit(lst, lat)
        act = 'ERSETZEN' if name in REPLACE else 'nur Vergleich (behalten)'
        print(f'{name:16s} {old_r2:7.4f} {r2:7.4f} {rms:7.3f}m {len(lst):5d}  {act}')
        if name in REPLACE and b:
            new_comments = []
            for c in b['comments']:
                if c.startswith('# source:'):
                    new_comments.append(f'# source: {SOURCE}')
                elif c.startswith('# utide:'):
                    new_comments.append(f'# utide: period={t0.date()}..{t1.date()} r2={r2:.4f} rms={rms:.4f}m const={len(res)}')
                elif c.startswith('# bst_fix:'):
                    continue  # GMT-Quelle, kein BST-Bug mehr
                elif c.startswith('# date_imported:'):
                    new_comments.append('# date_imported: 20260616')
                elif c.startswith('# confidence:'):
                    new_comments.append('# confidence: 8')
                elif re.match(r'^# \d+ HW/LW points', c):
                    new_comments.append(f'# {len(lst)} HW/LW points (official GMT tide tables, 3 years)')
                elif re.match(r'^# R\^2 = ', c):
                    new_comments.append(f'# R^2 = {r2:.4f}, RMS error = {rms:.4f} m')
                else:
                    new_comments.append(c)
            replaced[b['start']] = (b, render_consts(mean, res), new_comments)

    if not args.write:
        print('\nDRY RUN — nichts geschrieben. Mit --write ersetzen.')
        return

    out, i, n = [], 0, len(lines)
    while i < n:
        if i in replaced:
            b, const_lines, new_comments = replaced[i]
            out.extend(new_comments)
            out.append(lines[b['name_idx']])
            out.append(b['meridian'])
            out.extend(const_lines)
            i = b['end']
        else:
            out.append(lines[i]); i += 1
    TIDETABLES.write_text('\n'.join(out), encoding='iso-8859-1')
    print(f'\nGeschrieben: {len(replaced)} Bloecke ersetzt -> {TIDETABLES}')


if __name__ == '__main__':
    main()
