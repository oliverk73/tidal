#!/usr/bin/env python3
# -*- coding: iso-8859-1 -*-
"""BST-Fix fuer HW-only-Transfer-Bloecke (# transfer:) in tidetables.txt.

fit_hwonly_transfer.py las die tidetimes-HW-Zeiten ohne Konvertierung
(tidetimes publiziert ganzjaehrig BST = UTC+1) -> dt um exakt +60 min
inflationiert -> alle Transfer-Stationen ganzjaehrig +1h zu spaet
(verifiziert: Porthmadog vs. EasyTide-API +60.1 min, Juni 2026).

Fix analog France-Meridian-Bug: g_neu = (g - speed*1h) mod 360 fuer alle
Konstituenten der Transfer-Bloecke; dt im Kommentar -60 min korrigiert.
a/z0/sigma bleiben (hoehenbasiert bzw. zeitdifferenz-streuung, unveraendert).

Usage: python3 fix_transfer_bst.py [--dry]
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, '/home/oliver/py')
from generate_germany_harmonics_175 import CONSTITUENTS_175
from refit_tidetimes_bst import parse_blocks

TIDETABLES = Path('/home/oliver/harmonics/utide/harmonics_utide_tidetables.txt')
SPEED = dict(CONSTITUENTS_175)

CONST_RE = re.compile(r'^(\S+(?: \(\S+\))?)\s+(\d+\.\d+)\s+(\d+\.\d+)\s*$')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry', action='store_true')
    args = ap.parse_args()

    raw = TIDETABLES.read_text(encoding='iso-8859-1')
    lines = raw.split('\n')
    blocks = parse_blocks(lines)

    targets = []
    for b in blocks:
        ctext = '\n'.join(b['comments'])
        if '# transfer:' in ctext and '# bst_fix:' not in ctext:
            targets.append(b)
    print(f'Transfer-Bloecke zu korrigieren: {len(targets)}')

    # Rueckwaerts: das Einfuegen der bst_fix-Zeile verschiebt alle spaeteren
    # Indizes — von hinten nach vorn bleiben unbearbeitete Bloecke stabil.
    n_const = 0
    for b in sorted(targets, key=lambda x: -x['start']):
        # Kommentar: dt korrigieren + bst_fix-Marker
        for ci in range(b['start'], b['name_idx']):
            m = re.match(r'^(# transfer: dt=)(-?\d+\.\d)(min.*)$', lines[ci])
            if m:
                lines[ci] = f'{m.group(1)}{float(m.group(2)) - 60.0:.1f}{m.group(3)}'
        ins_at = next((i for i in range(b['start'], b['name_idx'])
                       if lines[i].startswith('# !')), b['name_idx'])
        lines.insert(ins_at, '# bst_fix: 20260610 Phasen -speed*1h (tidetimes-HW-Zeiten waren ganzjaehrig BST, dt +60min inflationiert)')
        b['name_idx'] += 1
        b['end'] += 1
        # Konstituenten-Zeilen: name_idx+1=Meridian, +2=mean, ab +3 Konstituenten
        for li in range(b['name_idx'] + 3, b['end']):
            line = lines[li]
            if line.startswith('x '):
                continue
            m = CONST_RE.match(line)
            if not m:
                continue
            cname, amp, pha = m.group(1), float(m.group(2)), float(m.group(3))
            sp = SPEED.get(cname)
            if sp is None:
                continue
            new_pha = (pha - sp * 1.0) % 360.0
            lines[li] = f'{cname:15s} {amp:.4f}  {new_pha:.2f}'
            n_const += 1

    print(f'Konstituenten korrigiert: {n_const}')
    if args.dry:
        print('DRY RUN — nichts geschrieben.')
        return
    TIDETABLES.write_text('\n'.join(lines), encoding='iso-8859-1')
    print(f'Geschrieben: {TIDETABLES}')


if __name__ == '__main__':
    main()
