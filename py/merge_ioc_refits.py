#!/usr/bin/env python3
"""Merge all IOC-refit output files into one master input for
patch_chile_observations.py.

Reads multiple harmonics_utide_*.txt files, extracts blocks whose
station_id_context starts with 'IOC-', concatenates them with the
observations.txt XTide header.
"""
import re
import sys
from pathlib import Path

OBS_PATH = Path('/home/oliver/harmonics/utide/harmonics_utide_observations.txt')
UTIDE_DIR = Path('/home/oliver/harmonics/utide')

SOURCE_FILES = [
    # Already-refitted (these are also in obs.txt; skip if already merged)
    'harmonics_utide_chile.txt',           # optional; chile is in observations
    'harmonics_utide_colombia.txt',        # 3 IOC
    'harmonics_utide_elsalvador.txt',      # 2 IOC
    'harmonics_utide_china_v2.txt',        # 3 IOC
    # Newly-refitted pipelines
    'harmonics_utide_pakistan.txt',        # 1 IOC + 1 UHSLC
    'harmonics_utide_peru.txt',
    'harmonics_utide_portugal.txt',
    'harmonics_utide_abc.txt',
    'harmonics_utide_bvi.txt',
    'harmonics_utide_caribbean.txt',
    'harmonics_utide_costarica.txt',
    'harmonics_utide_panama.txt',
    'harmonics_utide_nicaragua.txt',
    'harmonics_utide_montserrat.txt',
    'harmonics_utide_stkitts.txt',
    'harmonics_utide_om_eg.txt',
    'harmonics_utide_russia.txt',
    'harmonics_utide_tr_gr.txt',
    'harmonics_utide_india.txt',
    'harmonics_utide_puerto_barrios.txt',
]


def parse_blocks(path):
    if not path.exists():
        return []
    with open(path, encoding='latin-1') as f:
        lines = f.read().split('\n')
    boundaries = [i for i, ln in enumerate(lines)
                  if ln.startswith('# BEGIN HOT COMMENTS')]
    def find_start(b):
        k = b - 1
        while k >= 0 and (lines[k] == '' or lines[k].startswith('#')):
            k -= 1
        return k + 1
    starts = [find_start(b) for b in boundaries]
    blocks = []
    for i, s in enumerate(starts):
        e = starts[i + 1] if i + 1 < len(starts) else len(lines)
        bl = lines[s:e]
        ctx = None
        for ln in bl:
            m = re.match(r'^# station_id_context:\s*(.+?)\s*$', ln)
            if m:
                ctx = m.group(1)
                break
        text = '\n'.join(bl)
        if e < len(lines):
            text += '\n'
        blocks.append({'ctx': ctx, 'text': text, 'src': path.name})
    return blocks


def main():
    output = Path('/home/oliver/harmonics/help/refit_ioc_master_2026-05-20.txt')
    # File header from observations.txt
    with open(OBS_PATH, encoding='latin-1') as f:
        obs_lines = f.read().split('\n')
    b0 = next(i for i, ln in enumerate(obs_lines)
              if ln.startswith('# BEGIN HOT COMMENTS'))
    k = b0 - 1
    while k >= 0 and (obs_lines[k] == '' or obs_lines[k].startswith('#')):
        k -= 1
    header = '\n'.join(obs_lines[:k + 1]) + '\n'

    all_blocks = {}  # ctx → block (later sources win, but they shouldn't conflict)
    counts_by_file = {}
    for fname in SOURCE_FILES:
        path = UTIDE_DIR / fname
        bls = parse_blocks(path)
        ioc_blks = [b for b in bls if b['ctx'] and b['ctx'].startswith('IOC-')]
        for b in ioc_blks:
            if b['ctx'] in all_blocks:
                print(f"  WARN: dup ctx {b['ctx']} "
                      f"(was {all_blocks[b['ctx']]['src']}, now {b['src']})")
            all_blocks[b['ctx']] = b
        counts_by_file[fname] = len(ioc_blks)
        if path.exists():
            print(f"  {fname:38s} → {len(ioc_blks)} IOC blocks")
        else:
            print(f"  {fname:38s} → MISSING")

    print(f"\nTotal unique IOC blocks: {len(all_blocks)}")

    with open(output, 'w', encoding='latin-1') as f:
        f.write(header)
        for ctx in sorted(all_blocks):
            f.write(all_blocks[ctx]['text'])

    print(f"Wrote merged file: {output}")


if __name__ == '__main__':
    main()
