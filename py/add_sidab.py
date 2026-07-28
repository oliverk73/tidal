#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ergaenzt Sidab, Oman (ATT NP203 Part II 4185b) in harmonics_att_np203_secondary.txt.

Warum die Station fehlte: page_229.json vergibt die Nummer 4186b zweimal --
einmal an Sidab, einmal an Mina al Fahl. Die Dublettensperre im Generator hat
daraufhin den zweiten Treffer verworfen; Sidab fiel heraus. Exakt derselbe
Mechanismus wie bei Yanbu al Bahr (dort 4131 doppelt).

Nummer und Position stammen aus dem Scan (Oliver, 20260728): 4185b, 23 36 N,
58 36 E. Die Transkription hatte beides falsch (4186b, 23.61/58.59). Die
Nachbarn 4186 Bandar Jissah, 4186a Port Sultan Qaboos, 4186b Mina al Fahl und
4186c Marsa al Murjan sind damit unveraendert richtig.

Zeit-/Hoehendiff. je -0.1 und tHW 0 aus page_229.json; ML 1.79 aus dem Scan
(Oliver, 20260728) -- die Transkription hatte 1.80.

Laeuft mehrfach: ein vorhandener Sidab-Block wird ersetzt.

Aufruf: python3 py/add_sidab.py            # dry-run
        python3 py/add_sidab.py --write
"""
from __future__ import annotations
import importlib.util
import os
import sys

TXT = '/home/oliver/weather/harmonics/att/harmonics_att_np203_secondary.txt'

SIDAB = dict(att='4185b', name='Sidab', region='Oman', std='Muscat (Sultan Qaboos',
             lat=23.60, lon=58.60, t=(0, None), h=(-0.1, -0.1, -0.1, -0.1), ml=1.79)
# Vor diesem Block einfuegen -- die Datei steht in att-Reihenfolge:
# 4185 Quryat, 4185a Bandar Khayran, 4185b Sidab, 4186 Bandar Jissah.
BEFORE = 'Bandar Jissah, Oman'
NOTES = [
    '# note: 20260728 nachgetragen. Die Transkription page_229.json vergab 4186b',
    '# note: doppelt (Sidab und Mina al Fahl); Sidab wurde dadurch als Dublette',
    '# note: verworfen. Nummer 4185b und Position 23 36 N / 58 36 E aus dem Scan',
    '# note: nachgelesen; die Transkription hatte 4186b und 23.61/58.59.',
]


def load_engine():
    os.environ['HOME'] = '/home/oliver/weather'      # ~/harmonics == weather/harmonics
    spec = importlib.util.spec_from_file_location(
        'B', '/home/oliver/weather/py/build_np203_secondary.py')
    B = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(B)
    return B


def bounds(L, name):
    """Grenzen des Stationsblocks mit dieser Namenszeile."""
    i = L.index(name)
    start = max(k for k in range(i) if L[k] == '# BEGIN HOT COMMENTS')
    end = i + 1
    while end < len(L) and not L[end].startswith('#'):
        end += 1
    return start, end


def main():
    write = '--write' in sys.argv
    L = open(TXT, encoding='iso-8859-1').read().split('\n')
    B = load_engine()

    refname, rr = B.find(SIDAB['std'])
    if rr is None:
        sys.exit(f'Bezugshafen nicht gefunden: {SIDAB["std"]}')
    tr = B.transfer(SIDAB, rr)
    tr['refname'] = refname
    blk, name, conf = B.block(SIDAB, tr)

    j = blk.index('# date_imported: 20260618')
    blk[j] = '# date_imported: 20260728'
    blk[j:j] = NOTES

    if name in L:                       # vorhandenen Block entfernen
        s, e = bounds(L, name)
        del L[s:e]
        print(f'Vorhandener Block ersetzt (Zeile {s}).')
    i = L.index(BEFORE)
    start = max(k for k in range(i) if L[k] == '# BEGIN HOT COMMENTS')
    L[start:start] = blk

    print(f'{name} (att {SIDAB["att"]}) aus {refname}:')
    print(f'  fS={tr["fS"]:.2f} fN={tr["fN"]:.2f} dt={tr["dt"]*60:+.0f}min  confidence {conf}')
    print(f'  Z0 {SIDAB["ml"]:.2f} m   {SIDAB["lat"]:.4f} N / {SIDAB["lon"]:.4f} E')
    for c in ('M2', 'S2', 'N2', 'K1', 'O1'):
        if c in tr['con']:
            a, g = tr['con'][c]
            print(f'  {c:3s} {a:.4f} @ {g:6.2f}')
    print(f'  eingefuegt vor "{BEFORE}" (Zeile {start})')

    if write:
        open(TXT, 'w', encoding='iso-8859-1').write('\n'.join(L))
        os.chmod(TXT, 0o600)
        n = sum(1 for l in L if l.startswith('# !latitude:'))
        print(f'\nGeschrieben. Stationen: {n}')
    else:
        print('\n(Dry-run. --write zum Schreiben.)')


if __name__ == '__main__':
    main()
