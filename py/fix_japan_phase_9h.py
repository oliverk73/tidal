#!/usr/bin/env python3
"""Fix 9h-phase error in harmonics_utide_japan.txt.

The UTide Japan analysis produced phases in Greenwich/UTC reference,
but the file header claims Meridian +09:00 (JST). Verified by comparing
Kisiwada (Classic 2004, JST-ref phases) vs Kishiwada (UTide Japan) at
identical coordinates: M2 amp identical (0.3139), phase differs by exactly
9h × speed for every constituent tested.

Correction: phase_new = (phase_old + 9.0 * speed_deg_per_hour) % 360

Also renames "Kankushima, Japan" → "Kansai Airport, Osaka, Japan".
"""
import sys
sys.exit("OBSOLET (2026-07-19): Einmal-Fix, bereits angewendet. Der Frame-Bug ist jetzt "
         "direkt in batch/batch_utide_japan.py behoben (Phase = g + speed*9h). Ein erneuter "
         "Lauf wuerde korrekte Phasen um +9h verfaelschen.")
import re
import shutil
from pathlib import Path

SRC = Path('/home/oliver/harmonics/utide/harmonics_utide_japan.txt')
BACKUP = Path('/home/oliver/harmonics/utide/harmonics_utide_japan_original_uncorrected.txt')
TEMPLATE = Path('/home/oliver/harmonics/template/harmonics_template.txt')
HOURS = 9.0


def load_constituent_speeds():
    """Parse 175-constituent speeds block from template."""
    speeds = {}
    with open(TEMPLATE, encoding='latin-1') as f:
        lines = f.readlines()
    # Speeds block is bounded by '# Number of constituents\n175\n...\n#' markers.
    # Parse any line matching '^\w\S*\s+\d+\.\d+$' up to the terminating '#'.
    in_speeds = False
    for ln in lines:
        if not in_speeds:
            if ln.strip() == '175':
                in_speeds = True
            continue
        s = ln.rstrip()
        if not s or s.startswith('#'):
            # skip blank/comment; but terminate when we hit a non-speed-format comment
            if s.startswith('#') and speeds:
                break
            continue
        m = re.match(r'^(\S+)\s+(-?\d+\.\d+)\s*$', s)
        if m:
            name, speed = m.group(1), float(m.group(2))
            speeds[name] = speed
    return speeds


def main():
    speeds = load_constituent_speeds()
    print(f'loaded {len(speeds)} constituent speeds')

    if not BACKUP.exists():
        shutil.copy2(SRC, BACKUP)
        print(f'backup → {BACKUP}')
    else:
        print(f'backup exists: {BACKUP}')

    with open(SRC, encoding='latin-1') as f:
        text = f.read()

    # Rename station
    old_name = 'Kankushima, Japan'
    new_name = 'Kansai Airport, Osaka, Japan'
    if old_name in text:
        # Replace only as station-name line (whole-line occurrences between `# Harmonic constants derived`
        # blocks). Safe to use replace_all here since the name does not appear in constituent lines.
        text = text.replace(old_name, new_name)
        print(f'renamed: "{old_name}" → "{new_name}"')

    # Correct phases: for every line matching "CONSTITUENT  amp  phase"
    # where CONSTITUENT is a known speed key.
    lines = text.splitlines(keepends=True)
    corrected = 0
    stations = 0
    for i, ln in enumerate(lines):
        m = re.match(r'^(\S+)(\s+)(-?\d+\.\d+)(\s+)(-?\d+\.\d+)(\s*)$', ln)
        if not m:
            # detect station-block boundary for counting (not strictly needed)
            if ln.startswith('# Harmonic constants derived'):
                stations += 1
            continue
        name = m.group(1)
        if name not in speeds:
            # "x" placeholder rows have name "x" with two integers — skip; also other exotic tokens
            continue
        amp = float(m.group(3))
        phase = float(m.group(5))
        new_phase = (phase + HOURS * speeds[name]) % 360.0
        # Preserve original whitespace, reformat phase with same decimal precision
        new_line = f'{m.group(1)}{m.group(2)}{m.group(3)}{m.group(4)}{new_phase:.2f}{m.group(6)}'
        lines[i] = new_line
        corrected += 1

    print(f'stations encountered: {stations}')
    print(f'phase lines corrected: {corrected}')

    with open(SRC, 'w', encoding='latin-1') as f:
        f.writelines(lines)
    print(f'wrote corrected → {SRC} ({SRC.stat().st_size} bytes)')


if __name__ == '__main__':
    main()
