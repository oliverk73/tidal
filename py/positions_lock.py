#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sperrliste fuer Stationspositionen und -namen.

Baut aus der Git-Historie eine Momentaufnahme aller Pegel und markiert, welche
Position bzw. welcher Name von Hand geaendert wurde (heutiger Wert weicht von
der Fassung ab, in der der Datensatz zuerst eingecheckt wurde).

Ein Datensatz wird ueber den Hash seines Konstituentenblocks identifiziert --
den aendert die Handarbeit nie, Namen und Positionen dagegen schon.

Ergebnis:
  harmonics/help/positions_locked.csv     alle Pegel, Spalte provenance manual|source
  harmonics/help/positions_ambiguous.csv  Faelle, in denen der Fingerabdruck nicht eindeutig ist

Die Harmonics-Dateien selbst werden nicht angefasst.

Usage: python3 py/positions_lock.py [--file <pfad>]
"""
from __future__ import annotations

import csv
import hashlib
import math
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_LOCK = os.path.join(ROOT, 'harmonics/help/positions_locked.csv')
OUT_AMB = os.path.join(ROOT, 'harmonics/help/positions_ambiguous.csv')
MERIDIAN = re.compile(r'^[+-]\d\d:\d\d')


def active_files():
    out = []
    for dirpath, _dirnames, names in os.walk(os.path.join(ROOT, 'harmonics')):
        rel = os.path.relpath(dirpath, ROOT)
        if any(p in rel for p in ('backup', 'classic_original', 'template', 'help', 'binary')):
            continue
        for n in sorted(names):
            if n.endswith('.txt'):
                out.append(os.path.relpath(os.path.join(dirpath, n), ROOT))
    return sorted(out)


def parse(text):
    """-> {fingerprint: [(name, lat, lon, units, slots), ...]}"""
    lines = text.split('\n')
    recs = {}
    lat = lon = units = None
    for k, line in enumerate(lines):
        if line.startswith('# !latitude:'):
            lat = _num(line)
        elif line.startswith('# !longitude:'):
            lon = _num(line)
        elif line.startswith('# !units:'):
            units = line.split(':', 1)[1].strip()
        elif (line and not line.startswith('#') and k + 1 < len(lines)
              and MERIDIAN.match(lines[k + 1])):
            rows = []
            j, c = k + 3, 0
            while j < len(lines) and c < 175:
                p = lines[j].split()
                if not p or p[0].startswith('#'):
                    break
                if p[0] != 'x':
                    rows.append(' '.join(p[:3]))
                c += 1
                j += 1
            fp = hashlib.md5('|'.join(rows).encode()).hexdigest()
            recs.setdefault(fp, []).append((line, lat, lon, units, c))
            lat = lon = units = None
    return recs


def _num(line):
    try:
        return float(line.split(':', 1)[1])
    except ValueError:
        return None


def git(*args):
    return subprocess.run(['git'] + list(args), cwd=ROOT,
                          capture_output=True).stdout


def first_seen(path):
    """Fuer jeden Fingerabdruck die aelteste eingecheckte Fassung.

    Gibt zusaetzlich zurueck, wie viele Commits ausgewertet wurden.
    """
    shas = git('log', '--reverse', '--format=%H', '--', path).decode().split()
    seen = {}
    blobs = set()
    dates = {}
    for sha in shas:
        blob = git('rev-parse', f'{sha}:{path}').decode().strip()
        if not blob or blob in blobs:
            continue
        blobs.add(blob)
        text = git('cat-file', 'blob', blob).decode('iso-8859-1')
        date = git('log', '-1', '--format=%cs', sha).decode().strip()
        for fp, entries in parse(text).items():
            if fp in seen:
                continue
            if len(entries) != 1:          # mehrdeutig, spaeter melden
                seen[fp] = None
                continue
            seen[fp] = entries[0]
            dates[fp] = (sha[:8], date)
    return seen, dates, len(shas), len(blobs)


def metres(la1, lo1, la2, lo2):
    if None in (la1, lo1, la2, lo2):
        return None
    return 6371000 * math.hypot(math.radians(la1 - la2),
                                math.radians(lo1 - lo2) * math.cos(math.radians(la1)))


def main():
    only = None
    if '--file' in sys.argv:
        only = sys.argv[sys.argv.index('--file') + 1]
    files = [only] if only else active_files()
    if '--rest' in sys.argv and os.path.exists(OUT_LOCK):
        with open(OUT_LOCK, encoding='utf-8') as fh:
            have = {r['file'] for r in csv.DictReader(fh)}
        files = [f for f in files if f not in have]
        print(f'{len(have)} Dateien erfasst, {len(files)} offen', flush=True)

    lock_rows, amb_rows = [], []
    tot = manual_pos = manual_name = ambiguous = untracked = 0

    for path in files:
        now = parse(open(os.path.join(ROOT, path), encoding='iso-8859-1').read())
        old, dates, n_commits, n_blobs = first_seen(path)
        n_here = sum(len(v) for v in now.values())
        tot += n_here
        f_pos = f_name = f_amb = f_new = 0

        for fp, entries in sorted(now.items()):
            if n_commits == 0:
                # Datei steht nicht unter Versionskontrolle -- Herkunft der
                # Werte laesst sich nicht rekonstruieren, Sperre gilt trotzdem
                for name, lat, lon, _u, _c in entries:
                    lock_rows.append([fp, path, name, lat, lon, 'unversioned',
                                      '', '', '', '', ''])
                f_new += len(entries)
                continue
            if len(entries) != 1 or old.get(fp) is None:
                # Fingerabdruck nicht eindeutig -- Herkunft nicht entscheidbar
                for name, lat, lon, _u, _c in entries:
                    amb_rows.append([fp, path, name, lat, lon, len(entries)])
                    lock_rows.append([fp, path, name, lat, lon, 'ambiguous',
                                      '', '', '', '', ''])
                f_amb += len(entries)
                continue
            name, lat, lon, _u, _c = entries[0]
            if fp not in old:
                lock_rows.append([fp, path, name, lat, lon, 'untracked',
                                  '', '', '', '', ''])
                f_new += 1
                continue
            oname, olat, olon, _ou, _oc = old[fp]
            d = metres(olat, olon, lat, lon)
            moved = d is not None and d > 1.0
            renamed = name != oname
            prov = 'manual' if (moved or renamed) else 'source'
            sha, date = dates.get(fp, ('', ''))
            lock_rows.append([fp, path, name, lat, lon, prov,
                              oname if renamed else '',
                              olat if moved else '', olon if moved else '',
                              f'{d:.0f}' if moved else '', f'{sha} {date}'.strip()])
            if moved:
                f_pos += 1
            if renamed:
                f_name += 1

        manual_pos += f_pos
        manual_name += f_name
        ambiguous += f_amb
        untracked += f_new
        print(f'{n_here:6d} Pegel  {f_pos:5d} Position  {f_name:5d} Name  '
              f'{f_amb:4d} mehrdeutig  {f_new:4d} unverfolgt  '
              f'({n_blobs}/{n_commits} Fassungen)  {path}', flush=True)

    os.makedirs(os.path.dirname(OUT_LOCK), exist_ok=True)
    append = os.path.exists(OUT_LOCK) and '--rest' in sys.argv
    with open(OUT_LOCK, 'a' if append else 'w', newline='', encoding='utf-8') as fh:
        w = csv.writer(fh)
        if not append:
            w.writerow(['fingerprint', 'file', 'name', 'lat', 'lon', 'provenance',
                        'orig_name', 'orig_lat', 'orig_lon', 'moved_m', 'first_seen'])
        w.writerows(lock_rows)
    with open(OUT_AMB, 'a' if append else 'w', newline='', encoding='utf-8') as fh:
        w = csv.writer(fh)
        if not append:
            w.writerow(['fingerprint', 'file', 'name', 'lat', 'lon', 'n_identical'])
        w.writerows(amb_rows)

    print(f'\n{tot} Pegel gesamt')
    print(f'   Position von Hand geaendert : {manual_pos}')
    print(f'   Name von Hand geaendert     : {manual_name}')
    print(f'   Fingerabdruck mehrdeutig    : {ambiguous}')
    print(f'   nicht in der Historie       : {untracked}')
    print(f'\n-> {OUT_LOCK}\n-> {OUT_AMB}')


if __name__ == '__main__':
    main()
