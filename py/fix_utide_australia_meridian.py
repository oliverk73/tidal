#!/usr/bin/env python3
"""
Fix meridian/phase for Australian UTide harmonics files (multi-timezone).

Stations span multiple AU states → per-station meridian required.
Classify by state substring in station name, set correct meridian + phase shift.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, '/home/oliver/py')
from fix_utide_meridian_phase import load_speed_table, CONSTIT_LINE, MEAN_LINE, MERIDIAN_LINE, parse_meridian

# State → (offset_hours, meridian_line_text)
STATE_MAP = {
    'Western Australia':   ( 8.0,    '+08:00 :Australia/Perth'),
    'Northern Territory':  ( 9.5,    '+09:30 :Australia/Darwin'),
    'South Australia':     ( 9.5,    '+09:30 :Australia/Adelaide'),
    'Queensland':          (10.0,    '+10:00 :Australia/Brisbane'),
    'New South Wales':     (10.0,    '+10:00 :Australia/Sydney'),
    'Victoria':            (10.0,    '+10:00 :Australia/Melbourne'),
    'Tasmania':            (10.0,    '+10:00 :Australia/Hobart'),
    'Cocos Islands':       ( 6.5,    '+06:30 :Indian/Cocos'),
    'Christmas Island':    ( 7.0,    '+07:00 :Indian/Christmas'),
    'Norfolk Island':      (11.0,    '+11:00 :Pacific/Norfolk'),
    'Tasman Sea':          (10.5,    '+10:30 :Australia/Lord_Howe'),
}


def classify(name):
    for state, (offset, merid) in STATE_MAP.items():
        if state in name:
            return offset, merid
    return None, None


def fix_file(path):
    raw = Path(path).read_bytes().decode('iso-8859-1')
    lines = raw.split('\n')
    speeds = load_speed_table(lines)
    if len(speeds) < 170:
        print(f"  ERROR: only parsed {len(speeds)} speeds")
        return None

    out = []
    i = 0
    n_fixed = 0
    n_unmatched = 0
    while i < len(lines):
        line = lines[i]
        if parse_meridian(line) is None:
            out.append(line)
            i += 1
            continue

        # Meridian line found — prev non-comment non-empty line is station name
        name = None
        for j in range(i - 1, max(0, i - 30), -1):
            if not lines[j].startswith('#') and lines[j].strip():
                name = lines[j]
                break
        if name is None:
            out.append(line)
            i += 1
            continue

        offset, new_merid = classify(name)
        if offset is None:
            print(f"  UNMATCHED: {name}")
            n_unmatched += 1
            out.append(line)
            i += 1
            continue

        # Write new meridian line
        out.append(new_merid)
        i += 1

        # Mean line
        if i < len(lines) and MEAN_LINE.match(lines[i]):
            out.append(lines[i])
            i += 1

        # 175 constituent lines
        constit_idx = 0
        while i < len(lines) and constit_idx < 175:
            cl = lines[i]
            if cl.startswith('x '):
                out.append(cl)
                constit_idx += 1
                i += 1
                continue
            m = CONSTIT_LINE.match(cl)
            if not m:
                break
            cname = m.group(1)
            amp = float(m.group(2))
            phase = float(m.group(3))
            speed = speeds.get(cname)
            if speed is None:
                out.append(cl)
            else:
                new_phase = (phase + speed * offset) % 360.0
                out.append(f"{cname:15s} {amp:.4f}  {new_phase:.2f}")
            constit_idx += 1
            i += 1
        n_fixed += 1

    print(f"  fixed: {n_fixed}, unmatched: {n_unmatched}")
    # Backup + write
    bak = Path(str(path) + '.bak')
    if not bak.exists():
        bak.write_bytes(Path(path).read_bytes())
    Path(path).write_bytes('\n'.join(out).encode('iso-8859-1'))


if __name__ == '__main__':
    for p in sys.argv[1:]:
        print(f"=== {p} ===")
        fix_file(p)
