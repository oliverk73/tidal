#!/usr/bin/env python3
"""Fix TICON-4 CMEMS-source +1h phase bug per timezone offset.

Bug observed: For TICON-4 stations with `# Source: gesla4.CMEMS`, the M2/S2/N2/K1/O1
phases are systematically shifted by +TZ_offset hours compared to clean PdE/FCUL
references. Confirmed for all 4 collocated Spanish stations:

  Bonanza:  TICON 92.70°  vs PdE 63.73° → +29.0° = +1h (TZ +01:00)
  Ferrol:   TICON 115.78° vs PdE 86.81° → +29.0° = +1h (TZ +01:00)
  Palma:    TICON 237.24° vs PdE 208.19°→ +29.1° = +1h (TZ +01:00)
  Sevilla:  TICON 194.38° vs PdE 165.47°→ +28.9° = +1h (TZ +01:00)

Confirmed clean for TZ +00:00:
  Tubuai:   TICON 258.43° vs REFMAR 258.43° → 0h
  Gomera:   TICON 23.58°  vs PdE 23.60° → 0h

Hypothesis (from existing project_utide_france_phase_fix.md): GESLA-4/CMEMS times
are stored in local time but interpreted as UTC by the harmonic analysis, so
phases need correction by `phase_new = (phase - speed_deg_per_hour * tz_hours) % 360`.

Note opposite sign vs UTide France fix: there phases were too LOW (+correction);
here they're too HIGH (-correction).
"""
from __future__ import annotations

import re
from pathlib import Path

SPEED_LINE = re.compile(r"^([A-Za-z0-9_()\-]+)\s+([\d.]+)\s*$")
MERIDIAN_LINE = re.compile(r"^([+\-])(\d{2}):(\d{2}) :(.+)$")
CONSTIT_LINE = re.compile(r"^([A-Za-z0-9_()\-]+)\s+(-?[\d.]+)\s+(-?[\d.]+)\s*$")
MEAN_LINE = re.compile(r"^-?[\d.]+ meters\s*$")


def load_speed_table(lines: list[str]) -> dict[str, float]:
    speeds = {}
    in_section = False
    count = 0
    for line in lines:
        if "# Constituent speeds" in line:
            in_section = True
            continue
        if not in_section:
            continue
        if line.startswith("#") or not line.strip():
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


def parse_meridian_offset(line: str) -> float | None:
    m = MERIDIAN_LINE.match(line.rstrip())
    if not m:
        return None
    sign = 1 if m.group(1) == "+" else -1
    hours = int(m.group(2))
    minutes = int(m.group(3))
    return sign * (hours + minutes / 60.0)


def fix_file(path: str | Path, source_marker: str = "# Source: gesla4.CMEMS"):
    """Apply phase_new = (phase - speed × tz) % 360 to all stations whose block
    contains `source_marker`. Block context = up to 50 lines before meridian line.
    """
    raw = Path(path).read_bytes().decode("iso-8859-1")
    lines = raw.split("\n")
    speeds = load_speed_table(lines)
    if len(speeds) < 170:
        raise RuntimeError(f"speed table incomplete: {len(speeds)}")
    print(f"  speed table: {len(speeds)} constituents")

    out = []
    i = 0
    n_fixed = 0
    n_skipped = 0
    by_tz: dict[float, int] = {}

    while i < len(lines):
        offset = parse_meridian_offset(lines[i])
        if offset is None:
            out.append(lines[i])
            i += 1
            continue

        # This is a meridian line. Check if station is from CMEMS source.
        block_header = "\n".join(lines[max(0, i - 50): i + 1])
        if source_marker not in block_header:
            out.append(lines[i])
            i += 1
            n_skipped += 1
            continue

        # Append meridian (unchanged), then mean, then 175 constituent lines with phase fix.
        out.append(lines[i])
        i += 1
        if i < len(lines) and MEAN_LINE.match(lines[i]):
            out.append(lines[i])
            i += 1

        constit_idx = 0
        while i < len(lines) and constit_idx < 175:
            cl = lines[i]
            if cl.startswith("x "):
                out.append(cl)
                constit_idx += 1
                i += 1
                continue
            m = CONSTIT_LINE.match(cl)
            if not m:
                break
            cname, amp_s, phase_s = m.group(1), m.group(2), m.group(3)
            amp = float(amp_s)
            phase = float(phase_s)
            speed = speeds.get(cname)
            if speed is None:
                out.append(cl)
            else:
                new_phase = (phase - speed * offset) % 360.0
                out.append(f"{cname:15s} {amp:.4f}  {new_phase:.2f}")
            constit_idx += 1
            i += 1

        n_fixed += 1
        by_tz[offset] = by_tz.get(offset, 0) + 1

    print(f"  stations fixed: {n_fixed}, skipped: {n_skipped}")
    print(f"  fixed-by-offset: {sorted(by_tz.items())}")

    Path(path).write_bytes("\n".join(out).encode("iso-8859-1"))
    return n_fixed


if __name__ == "__main__":
    fix_file("/home/oliver/harmonics/ticon/harmonics_ticon4_worldwide.txt")
