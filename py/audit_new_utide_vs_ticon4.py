#!/usr/bin/env python3
"""Audit: Find TICON4 duplicates for UTide stations added in the last 10 days.

For each new UTide station:
  - Look up TICON4 by lat/lon (<=20 km).
  - If a TICON4 dup exists, compare:
      - M2 amplitude (relative)
      - M2 phase (absolute deg diff)
      - meridian / timezone match
      - 1h-phase-bug pattern (~M2_speed deg)
  - Flag for inspection.

Outputs a human-readable Markdown table to stdout.
"""

import os
import re
import math
import sys
from collections import defaultdict

ROOT = "/home/oliver/harmonics"
TICON = os.path.join(ROOT, "ticon", "harmonics_ticon4_worldwide.txt")

UTIDE_FILES = [
    os.path.join(ROOT, "utide", "harmonics_utide_observations.txt"),
    os.path.join(ROOT, "utide", "harmonics_utide_tidetables.txt"),
]

# Stations added in the last 10 days (commit log 2026-05-09..05-13).
# Match by station name fragments.
NEW_STATIONS = {
    # Oman
    "Duqm, Oman", "Majis, Oman", "Qurayat, Oman", "Sur, Oman",
    # Russia Far East
    "Korsakov, Russia", "Kuril'sk, Russia", "Poronajsk, Russia",
    "Preobrazheniye, Russia",
    # China
    "Qinglan, China", "Shenzhen, China", "Zhapo, China",
    # Turkey
    "Antalya, Turkey", "Arsuz (Hatay), Turkey", "Erdemli, Turkey",
    "Mentes, Turkey", "Tasucu, Turkey",
    # Adria
    "Trieste, Italy", "Sobra, Croatia", "Stari Grad, Croatia",
    # Mexico CICESE
    "Guerrero Negro, Baja California Sur, Mexico",
    "Golfo de Santa Clara, Sonora, Mexico",
    "Huatulco, Oaxaca, Mexico",
    "Puerto Pe\xf1asco, Sonora, Mexico",
    "Puerto Refugio, Baja California, Mexico",
    "El Sauzal, Baja California, Mexico",
    "Isla Tibur\xf3n, Sonora, Mexico",
    # Chile SHOA
    "Constituci\xf3n, Chile",
    # Chile IOC
    "Pisagua, Chile", "Tocopilla, Chile", "Huasco, Chile",
    "Quiriquina, Chile", "Punta de Choros, Chile",
    "Nehuent\xfae, Chile", "Queule, Chile",
    "Puerto Melinka, Chile", "Puerto Aguirre, Chile",
    "Puerto Ed\xe9n, Chile", "Caleta Meteoro, Chile",
    "Bah\xeda Gregorio, Chile",
    "DART West of Iquique, Chile", "DART West of Antofagasta, Chile",
    "DART West of Caldera, Chile", "DART NW of Valpara\xedso, Chile",
    "DART NW of Concepci\xf3n, Chile",
    # Chile IOC/SHOA Phase 1 (commit 5406330)
    "Arica, Chile", "Patache, Chile", "Paposo, Chile", "Taltal, Chile",
    "Cha\xf1aral, Chile", "Caldera, Chile", "Puerto Aldea, Chile",
    "Pichidangui, Chile", "Quintero, Chile", "Valpara\xedso, Chile",
    "Boyeruca, Chile", "Coliumo, Chile", "Coronel, Chile",
    "Lebu, Chile", "Bah\xeda Mansa, Chile", "Puerto Montt, Chile",
    "Castro, Chile", "Puerto Williams, Chile",
    # Brazil
    "Recife (Porto)", "Recife (Farol)",
}

# All Argentina SHN stations added in commit 5406330
ARG_PATTERN = re.compile(r"^[^,]+,\s*Argentina$")


def parse_harmonics_file(path, encoding="iso-8859-1"):
    """Parse stations from a tide-harmonic file. Returns list of dicts."""
    with open(path, encoding=encoding) as fp:
        lines = fp.read().splitlines()

    stations = []
    current = None
    in_header = False
    in_body = False

    for i, raw in enumerate(lines):
        line = raw.rstrip()

        # Detect station start: comment with 'BEGIN HOT COMMENTS' below name
        if line == "# BEGIN HOT COMMENTS":
            # The line above ("# <name>") is the station identifier comment
            in_header = True
            current = {
                "name": None,
                "lat": None,
                "lon": None,
                "meridian": None,
                "tz": None,
                "datum": None,
                "datum_unit": None,
                "constituents": {},
                "file": os.path.basename(path),
                "line": i + 1,
            }
            # Look back for the name comment
            for j in range(i - 1, max(-1, i - 6), -1):
                cand = lines[j].strip()
                if cand.startswith("# ") and not cand.startswith("# !") \
                        and not cand.startswith("# Harmonic") \
                        and not cand.startswith("# R^2") \
                        and not cand.startswith("# Constituents"):
                    current["name_hint"] = cand[2:].strip()
                    break
            continue

        if in_header:
            if line.startswith("# !longitude:"):
                try:
                    current["lon"] = float(line.split(":", 1)[1].strip())
                except ValueError:
                    pass
            elif line.startswith("# !latitude:"):
                try:
                    current["lat"] = float(line.split(":", 1)[1].strip())
                except ValueError:
                    pass
            elif line and not line.startswith("#"):
                # First non-comment line => station-name line (e.g. "Antalya, Turkey")
                current["name"] = line.strip()
                in_header = False
                in_body = True
                continue

        if in_body:
            if not line:
                continue
            if current["meridian"] is None and ":" in line and "Etc/" in line + " " or \
                    (current["meridian"] is None and re.match(r"^[+-]?\d", line)):
                # meridian line e.g. "+03:00 :Europe/Istanbul"
                parts = line.split(None, 1)
                current["meridian"] = parts[0]
                if len(parts) > 1:
                    rest = parts[1].lstrip(":").strip()
                    current["tz"] = rest
                continue
            if current["datum"] is None and re.match(
                    r"^[-+]?\d+\.?\d*\s+\w+", line):
                parts = line.split()
                try:
                    current["datum"] = float(parts[0])
                    current["datum_unit"] = parts[1]
                except (ValueError, IndexError):
                    pass
                continue
            # Constituent line: NAME  AMP  PHASE
            m = re.match(r"^([A-Z][A-Z0-9]*\d*[A-Z]*)\s+([-\d.]+)\s+([-\d.]+)\s*$",
                         line)
            if m:
                current["constituents"][m.group(1)] = (
                    float(m.group(2)), float(m.group(3))
                )
                continue
            # End of station: comment that starts a new block, or end-marker
            if line.startswith("# END HOT COMMENTS") or line.startswith("#"):
                if current["constituents"]:
                    stations.append(current)
                current = None
                in_body = False

    if current and current["constituents"]:
        stations.append(current)

    return stations


def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


M2_SPEED = 28.9841042  # deg/hour


def main():
    print("Reading TICON4...", file=sys.stderr)
    ticon = parse_harmonics_file(TICON, encoding="iso-8859-1")
    ticon_with_coords = [t for t in ticon if t["lat"] is not None]
    print(f"  TICON4 stations with coords: {len(ticon_with_coords)}", file=sys.stderr)

    print("Reading UTide files...", file=sys.stderr)
    utide_all = []
    for f in UTIDE_FILES:
        u = parse_harmonics_file(f, encoding="iso-8859-1")
        utide_all.extend(u)
        print(f"  {os.path.basename(f)}: {len(u)} stations", file=sys.stderr)

    # Filter to new stations
    new_utide = []
    for u in utide_all:
        if not u["name"]:
            continue
        if u["name"] in NEW_STATIONS or ARG_PATTERN.match(u["name"]):
            new_utide.append(u)

    print(f"\nNew UTide stations matched: {len(new_utide)}", file=sys.stderr)

    # Match each to TICON4
    print()
    print("| New UTide Station | UTide lat/lon | TICON4 match | km | UTide M2 amp/ph | TICON4 M2 amp/ph | Δph | Note |")
    print("|---|---|---|---|---|---|---|---|")

    matches = 0
    no_match = []
    for u in new_utide:
        if u["lat"] is None or u["lon"] is None:
            continue
        best = None
        best_d = 9999
        for t in ticon_with_coords:
            if t["lon"] is None:
                continue
            d = haversine_km(u["lat"], u["lon"], t["lat"], t["lon"])
            if d < best_d:
                best_d = d
                best = t
        if best is None or best_d > 20:
            no_match.append((u["name"], u["lat"], u["lon"], best_d if best else None,
                             best["name"] if best else "—"))
            continue
        matches += 1
        um2 = u["constituents"].get("M2", (None, None))
        tm2 = best["constituents"].get("M2", (None, None))
        dph = None
        note = []
        if um2[1] is not None and tm2[1] is not None:
            d = (tm2[1] - um2[1]) % 360
            if d > 180:
                d -= 360
            dph = d
            if abs(abs(d) - M2_SPEED) < 4:
                note.append(f"1h-phase-shift suspected ({d:+.1f}°)")
            if abs(d) > 15:
                note.append(f"large phase delta")
        if um2[0] is not None and tm2[0] is not None:
            rel = (tm2[0] - um2[0]) / max(um2[0], 0.001)
            if abs(rel) > 0.3:
                note.append(f"amp Δ {rel*100:+.0f}%")
        if u.get("meridian") and best.get("meridian") and \
                u["meridian"] != best["meridian"]:
            note.append(f"meridian mismatch {u['meridian']} vs {best['meridian']}")

        uname = u["name"]
        if len(uname) > 35:
            uname = uname[:33] + ".."
        tname = best.get("name_hint") or best.get("name") or "?"
        if len(tname) > 35:
            tname = tname[:33] + ".."

        ulatlon = f"{u['lat']:.3f},{u['lon']:.3f}"
        u_m2 = f"{um2[0]:.4f}/{um2[1]:.1f}°" if um2[0] is not None else "—"
        t_m2 = f"{tm2[0]:.4f}/{tm2[1]:.1f}°" if tm2[0] is not None else "—"
        dph_s = f"{dph:+.1f}°" if dph is not None else "—"
        note_s = "; ".join(note) if note else ""
        print(f"| {uname} | {ulatlon} | {tname} | {best_d:.1f} | {u_m2} | {t_m2} | {dph_s} | {note_s} |")

    print()
    print(f"**Summary:** {matches} matches within 20 km. "
          f"{len(no_match)} new stations without close TICON4 entry.")

    # Second pass: name-based match for things outside 20 km (rare but possible)
    print()
    print("### Name-based candidates (no <=20km coord match)")
    print()
    print("| New UTide Station | UTide lat/lon | TICON name | km | UTide M2 | TICON M2 | Δph |")
    print("|---|---|---|---|---|---|---|")
    for u in new_utide:
        if u["lat"] is None or u["lon"] is None:
            continue
        # skip if already had close match
        already = False
        for t in ticon_with_coords:
            if t["lon"] is None:
                continue
            if haversine_km(u["lat"], u["lon"], t["lat"], t["lon"]) <= 20:
                already = True
                break
        if already:
            continue
        # name-based: take first word of UTide name
        base = u["name"].split(",")[0].strip().lower()
        base = re.sub(r"[^a-z\s]", "", base).split()
        if not base:
            continue
        first = base[0]
        # require >=4 chars to avoid garbage
        if len(first) < 4:
            continue
        for t in ticon_with_coords:
            tname = (t.get("name_hint") or t.get("name") or "").lower()
            if first in tname:
                d = haversine_km(u["lat"], u["lon"], t["lat"], t["lon"])
                if d > 200:
                    continue
                um2 = u["constituents"].get("M2", (None, None))
                tm2 = t["constituents"].get("M2", (None, None))
                dph = None
                if um2[1] is not None and tm2[1] is not None:
                    dd = (tm2[1] - um2[1]) % 360
                    if dd > 180:
                        dd -= 360
                    dph = dd
                u_m2 = f"{um2[0]:.4f}/{um2[1]:.1f}°" if um2[0] is not None else "—"
                t_m2 = f"{tm2[0]:.4f}/{tm2[1]:.1f}°" if tm2[0] is not None else "—"
                dph_s = f"{dph:+.1f}°" if dph is not None else "—"
                uname = u["name"][:35]
                tname2 = (t.get("name_hint") or t.get("name"))[:35]
                ulatlon = f"{u['lat']:.3f},{u['lon']:.3f}"
                print(f"| {uname} | {ulatlon} | {tname2} | {d:.1f} | {u_m2} | {t_m2} | {dph_s} |")


if __name__ == "__main__":
    main()
