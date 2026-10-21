#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Aus positions_locked/positions_ambiguous nur die Zeilen bestimmter Saetze stagen (Oliver 21.10.2026).

Oliver hat oft eigene, noch nicht committete Aenderungen in den Sperrlisten. Ein git add wuerde sie
mitnehmen. Dieses Skript nimmt HEAD als Basis und ersetzt nur Zeilen, deren Namensfeld einen der
Suchbegriffe enthaelt (bzw. deren Datei-Feld, mit --datei), an ihrer Stelle.

Usage: python3 py/locks_teilweise_stagen.py [--datei] BEGRIFF [BEGRIFF ...]
       python3 py/locks_teilweise_stagen.py --liste namen.txt     (ein Name je Zeile)
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LISTEN = ['harmonics/help/positions_locked.csv', 'harmonics/help/positions_ambiguous.csv']


def treffer(zeile, begriffe, datei_feld):
    f = zeile.split(',', 2)
    if len(f) < 3:
        return False
    feld = f[1] if datei_feld else f[2]
    return any(b in feld for b in begriffe)


def main(argv):
    datei_feld = '--datei' in argv
    rest = [a for a in argv if a != '--datei']
    if rest[:1] == ['--liste']:
        begriffe = ['"%s"' % z.strip() for z in open(rest[1], encoding='utf-8') if z.strip()]
    else:
        begriffe = rest
    if not begriffe:
        print(__doc__.split('Usage:')[-1].strip())
        return 2
    for f in LISTEN:
        head = subprocess.run(['git', 'show', 'HEAD:' + f], capture_output=True, cwd=ROOT).stdout.decode('utf-8').split('\n')
        work = open(os.path.join(ROOT, f), encoding='utf-8').read().split('\n')
        hs, ws = set(head), set(work)
        neu = [l for l in work if treffer(l, begriffe, datei_feld) and l not in hs]
        weg = {l for l in head if treffer(l, begriffe, datei_feld) and l not in ws}
        out = [l for l in head if l not in weg]
        pos = {l: i for i, l in enumerate(out)}
        for i, l in enumerate(work):
            if l not in neu:
                continue
            j = i - 1
            while j >= 0 and work[j] not in pos:
                j -= 1
            out.insert(pos[work[j]] + 1 if j >= 0 else 0, l)
            pos = {x: n for n, x in enumerate(out)}
        blob = subprocess.run(['git', 'hash-object', '-w', '--stdin'], input='\n'.join(out).encode('utf-8'),
                              capture_output=True, cwd=ROOT).stdout.decode().strip()
        subprocess.run(['git', 'update-index', '--cacheinfo', '100644,%s,%s' % (blob, f)], check=True, cwd=ROOT)
        print(f, 'neu', len(neu), 'weg', len(weg))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
