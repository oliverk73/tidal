#!/usr/bin/env python3
"""Merge all SHOM harmonics into a single harmonics_utide_shom.txt.

Reads:
  - harmonics/utide/harmonics_utide_shom.txt          (existing consolidated, if any)
  - harmonics/utide/harmonics_utide_*_shom.txt        (per-region scraper output)

Dedupes by station name line. Per-region files win over the consolidated file
(so re-scraping a region updates stations). After merging, per-region files are
removed and only the consolidated file remains.
"""
import re
from pathlib import Path

UTIDE_DIR = Path('/home/oliver/harmonics/utide')
TEMPLATE  = Path('/home/oliver/harmonics/template/harmonics_template.txt')
CONSOLIDATED = UTIDE_DIR / 'harmonics_utide_shom.txt'
STATION_MARK = '# Harmonic constants derived'


def parse_station_blocks(text):
    """Return list of (station_name, block_text) pairs in file order.
    A station block starts at '# Harmonic constants derived' and ends at
    the next such marker or end-of-file. The station name is the first
    line after the block's hot-comments section that doesn't start with #.
    """
    positions = [m.start() for m in re.finditer(re.escape(STATION_MARK), text)]
    if not positions:
        return []
    positions.append(len(text))
    blocks = []
    for i in range(len(positions) - 1):
        block = text[positions[i]:positions[i+1]]
        # station name = first non-comment, non-blank line
        name = None
        for ln in block.splitlines():
            s = ln.strip()
            if s and not s.startswith('#'):
                name = s
                break
        if name:
            blocks.append((name, block))
    return blocks


def main():
    template_text = TEMPLATE.read_text(encoding='latin-1').rstrip() + '\n'

    # Collect blocks: per-region (priority) first, then consolidated (fill-in).
    per_region = sorted(p for p in UTIDE_DIR.glob('harmonics_utide_*_shom.txt')
                        if p != CONSOLIDATED)
    print(f'per-region files found: {len(per_region)}')

    collected = {}  # name -> block_text
    region_count = 0
    for f in per_region:
        for name, block in parse_station_blocks(f.read_text(encoding='latin-1')):
            if name not in collected:
                collected[name] = block
                region_count += 1
        print(f'  {f.name}: processed')

    existing_count = 0
    if CONSOLIDATED.exists():
        for name, block in parse_station_blocks(CONSOLIDATED.read_text(encoding='latin-1')):
            if name not in collected:
                collected[name] = block
                existing_count += 1
        print(f'  {CONSOLIDATED.name}: added {existing_count} stations not in per-region files')

    print(f'\ntotal stations merged: {len(collected)} '
          f'({region_count} from per-region, {existing_count} carried over)')

    # Write consolidated (stations sorted by station-name)
    with open(CONSOLIDATED, 'w', encoding='latin-1') as o:
        o.write(template_text)
        for name in sorted(collected):
            o.write(collected[name])
            if not collected[name].endswith('\n'):
                o.write('\n')
    print(f'wrote {CONSOLIDATED} ({CONSOLIDATED.stat().st_size} bytes)')

    # Delete per-region files
    for f in per_region:
        f.unlink()
        print(f'  deleted {f.name}')


if __name__ == '__main__':
    main()
