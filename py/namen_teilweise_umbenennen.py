#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Namenszeilen umbenennen und nur diese Aenderung stagen (Oliver 21.10.2026).

Arbeitskopie und HEAD bekommen dieselbe Umbenennung; gestaged wird HEAD + Umbenennung, so bleiben
Olivers offene Aenderungen in derselben Datei ungestaged.

Usage: python3 py/namen_teilweise_umbenennen.py liste.tsv     (je Zeile: alter Name <TAB> neuer Name)
"""
import glob
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def wende(text, m):
    L = text.split('\n')
    n = 0
    for k, l in enumerate(L[:-1]):
        if l in m and not l.startswith('#') and not L[k + 1].startswith('#'):
            L[k] = m[l]
            n += 1
    return '\n'.join(L), n


def main(argv):
    m = dict(z.rstrip('\n').split('\t') for z in open(argv[0], encoding='utf-8') if '\t' in z)
    for b in m.values():
        b.encode('iso-8859-1')
    for pfad in sorted(glob.glob(os.path.join(ROOT, 'harmonics/*/*.txt'))):
        if '/backup/' in pfad:
            continue
        datei = os.path.relpath(pfad, ROOT)
        w, n = wende(open(pfad, encoding='iso-8859-1').read(), m)
        if not n:
            continue
        open(pfad, 'w', encoding='iso-8859-1', newline='').write(w)
        head = subprocess.run(['git', 'show', 'HEAD:' + datei], capture_output=True, cwd=ROOT).stdout.decode('iso-8859-1')
        h, nh = wende(head, m)
        blob = subprocess.run(['git', 'hash-object', '-w', '--stdin'], input=h.encode('iso-8859-1'), capture_output=True,
                              cwd=ROOT).stdout.decode().strip()
        subprocess.run(['git', 'update-index', '--cacheinfo', '100644,%s,%s' % (blob, datei)], check=True, cwd=ROOT)
        print(datei, n, 'umbenannt,', nh, 'gestaged')


if __name__ == '__main__':
    main(sys.argv[1:])
