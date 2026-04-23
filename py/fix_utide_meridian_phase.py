#!/usr/bin/env python3
"""
Fix meridian/phase mismatch in UTide-generated harmonics files.

Bug: phases were stored Greenwich-referenced (UTide output) but meridian
declares a non-zero offset (e.g. +04:00), making XTide predictions off by
speed * offset.

Fix (Option B, same as used for UTide France/Japan):
  phase_new = (phase_greenwich + speed * offset_hours) % 360
  meridian stays at declared local offset.

Reads file as ISO-8859-1, writes in place (backup ".bak").
"""
import re
import sys
from pathlib import Path


SPEED_LINE = re.compile(r'^([A-Za-z0-9_()\-]+)\s+([\d.]+)\s*$')
MERIDIAN_LINE = re.compile(r'^([+\-])(\d{2}):(\d{2}) :(.+)$')
CONSTIT_LINE = re.compile(r'^([A-Za-z0-9_()\-]+)\s+(-?[\d.]+)\s+(-?[\d.]+)\s*$')
MEAN_LINE = re.compile(r'^-?[\d.]+ meters\s*$')


def load_speed_table(lines):
    """Parse the 175 constituent speeds from the file header."""
    speeds = {}
    in_speed_section = False
    count = 0
    for line in lines:
        if '# Constituent speeds' in line:
            in_speed_section = True
            continue
        if in_speed_section:
            if line.startswith('#') or not line.strip():
                if speeds and count >= 170:
                    break
                continue
            m = SPEED_LINE.match(line.strip())
            if m:
                speeds[m.group(1)] = float(m.group(2))
                count += 1
                if count >= 175:
                    break
    return speeds


def parse_meridian(line):
    """Parse '+04:00 :Asia/Muscat' → (4.0, '+04:00 :Asia/Muscat'). Returns None if not a meridian line."""
    m = MERIDIAN_LINE.match(line.rstrip())
    if not m:
        return None
    sign = 1 if m.group(1) == '+' else -1
    hours = int(m.group(2))
    minutes = int(m.group(3))
    offset = sign * (hours + minutes / 60.0)
    return offset


def fix_file(path, force_offset=None, replace_meridian_name=None, new_meridian_line=None, only_sources=None, exclude_names=None):
    """
    Fix meridian/phase in a UTide harmonics file.

    force_offset: if set, override the offset parsed from the meridian line.
    replace_meridian_name: if set, replace the meridian line text (e.g. to correct bogus TZ names).
    only_sources: if set (list of substrings), only fix station blocks whose header
                  contains one of these source substrings. Other blocks stay untouched.
    exclude_names: if set (list of substrings), skip station blocks whose station name
                   line contains one of these substrings (e.g. station already correct).
    """
    raw = Path(path).read_bytes().decode('iso-8859-1')
    lines = raw.split('\n')

    speeds = load_speed_table(lines)
    if len(speeds) < 170:
        print(f"  ERROR: only parsed {len(speeds)} speeds from header")
        return None
    print(f"  speed table: {len(speeds)} constituents")

    # Process stations: find blocks and rewrite phases.
    # Block: optional leading comment lines, then station name, then meridian, then mean, then constituents.
    out_lines = []
    i = 0
    n_stations_fixed = 0
    n_stations_skipped = 0
    while i < len(lines):
        line = lines[i]
        # Detect meridian line
        merid = parse_meridian(line)
        if merid is not None:
            # This is a meridian line. The prev non-comment line should be the station name,
            # the next line should be the mean level, followed by 175 constituent lines.
            # Gather context: find block start (scan back to previous blank or '# Harmonic constants')
            block_start = i
            while block_start > 0:
                prev = lines[block_start - 1]
                if prev.startswith('# Harmonic constants'):
                    block_start -= 1
                    break
                if not prev.startswith('#') and block_start - 1 != i - 1 and not prev.strip():
                    break
                if prev.startswith('#') or prev.strip():
                    block_start -= 1
                else:
                    break
            # Simpler: just find prev block header comments up to blank line
            block_header = '\n'.join(lines[max(0, i - 20):i + 1])

            # Decide whether to fix based on source filter
            if only_sources is not None:
                if not any(src in block_header for src in only_sources):
                    # Skip this station
                    out_lines.append(line)
                    i += 1
                    n_stations_skipped += 1
                    continue

            # Decide whether to skip based on station-name exclusion
            if exclude_names is not None:
                # Find station name line (prev non-comment non-empty)
                station_name = ''
                for j in range(i-1, max(0, i-30), -1):
                    if not lines[j].startswith('#') and lines[j].strip():
                        station_name = lines[j]
                        break
                if any(excl in station_name for excl in exclude_names):
                    out_lines.append(line)
                    i += 1
                    n_stations_skipped += 1
                    continue

            offset = force_offset if force_offset is not None else merid

            # Write meridian line (possibly replaced)
            if replace_meridian_name:
                out_lines.append(replace_meridian_name)
            elif new_meridian_line:
                out_lines.append(new_meridian_line)
            else:
                out_lines.append(line)
            i += 1

            # Mean line
            if i < len(lines) and MEAN_LINE.match(lines[i]):
                out_lines.append(lines[i])
                i += 1

            # Now process 175 constituent lines (some are "x 0 0")
            speed_names = list(speeds.keys())
            constit_idx = 0
            while i < len(lines) and constit_idx < 175:
                cl = lines[i]
                if cl.startswith('x '):
                    out_lines.append(cl)
                    constit_idx += 1
                    i += 1
                    continue
                m = CONSTIT_LINE.match(cl)
                if not m:
                    # End of block
                    break
                cname = m.group(1)
                amp = float(m.group(2))
                phase = float(m.group(3))
                speed = speeds.get(cname)
                if speed is None:
                    # Unknown constituent — keep as is
                    out_lines.append(cl)
                else:
                    new_phase = (phase + speed * offset) % 360.0
                    # Match original formatting: "{name:15s} {amp:.4f}  {phase:.2f}"
                    out_lines.append(f"{cname:15s} {amp:.4f}  {new_phase:.2f}")
                constit_idx += 1
                i += 1

            n_stations_fixed += 1
            continue

        out_lines.append(line)
        i += 1

    print(f"  stations fixed: {n_stations_fixed}, skipped: {n_stations_skipped}")

    # Backup + write
    bak = Path(str(path) + '.bak')
    if not bak.exists():
        bak.write_bytes(Path(path).read_bytes())
    Path(path).write_bytes('\n'.join(out_lines).encode('iso-8859-1'))
    return n_stations_fixed


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("usage: fix_utide_meridian_phase.py <file.txt> [force_offset_hours]")
        sys.exit(1)
    path = sys.argv[1]
    force = float(sys.argv[2]) if len(sys.argv) > 2 else None
    fix_file(path, force_offset=force)
