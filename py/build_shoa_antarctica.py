#!/usr/bin/env python3
"""Build harmonic constants for 8 SHOA Chilean-Antarctic tide stations.

Reuses the SHOA pipeline (batch_utide_shoa_chile): parse HTML HW/LW ->
cosine-interpolate -> UTide constit='auto' -> XTide block. These stations were
saved as SUBDIRECTORIES under tide_tables/chile/ (generic HTML filenames),
each with 3 monthly files spanning May-Jul 2026 (~350 HW/LW after dedup).

Coordinates: O'Higgins (ohig) and Prat (prat) from IOC sea-level monitoring;
the other 6 from Wikipedia/official base positions. SHOA times are UTC-4 (no DST,
per pipeline). Appends blocks to harmonics_utide_tidetables.txt (UTide TC group).
"""
import sys
sys.path.insert(0, '/home/oliver/batch')
sys.path.insert(0, '/home/oliver/py')
from pathlib import Path
from batch_utide_shoa_chile import parse_shoa_html, analyze_station, format_station_block

CHILE = Path('/home/oliver/tide_tables/chile')
TIDETABLES = '/home/oliver/harmonics/utide/harmonics_utide_tidetables.txt'

# code, subdir, display name, lat, lon, coord source
NEW = [
    ('fildes',     'base_frei_bahia_fildes_isla_rey_jorge',
     'Base Frei (Bahía Fildes, Isla Rey Jorge)', -62.2002, -58.9626, 'Wikipedia'),
    ('copper',     'base_risopatron_caleta_cooper_mine_isla_robert',
     'Base Risopatrón (Caleta Cooper Mine, Isla Robert)', -62.3738, -59.6922, 'Wikipedia'),
    ('soberania',  'base_prat_bahia_chile_isla_greenwich',
     'Base Prat (Bahía Chile, Isla Greenwich)', -62.479, -59.663, 'IOC prat'),
    ('snow',       'caleta_snow_isla_snow',
     'Caleta Snow (Isla Snow)', -62.783, -61.383, 'Wikipedia (Snow Island)'),
    ('balleneros', 'caleta_balleneros_isla_decepcion',
     'Caleta Balleneros (Isla Decepción)', -62.983, -60.567, 'Wikipedia (Whalers Bay)'),
    ('covadonga',  "base_o'higgins_rada_covadonga_peninsula_tierra_o'higgins",
     "Base O'Higgins (Rada Covadonga)", -63.32, -57.899, 'IOC ohig'),
    ('paraiso',    "base_gonzalez_videla_bahia_paraiso_peninsula_tierra_o'higgins",
     'Base González Videla (Bahía Paraíso)', -64.824, -62.857, 'Wikipedia'),
    ('doumer',     "base_yelcho_bahia_sur_isla_doumer",
     'Base Yelcho (Bahía Sur, Isla Doumer)', -64.876, -63.584, 'Wikipedia'),
]


def parse_dir(subdir):
    files = sorted((CHILE / subdir).glob('*.html'))
    allp = []
    for f in files:
        allp += parse_shoa_html(f)
    seen = set()
    ded = [e for e in sorted(allp, key=lambda x: x[0]) if not (e[0] in seen or seen.add(e[0]))]
    return files, ded


def build():
    out = []
    for code, subdir, name, lat, lon, csrc in NEW:
        files, ded = parse_dir(subdir)
        if not files:
            print(f"{code}: KEINE HTML in {subdir}"); continue
        span = f"{ded[0][0].date()}..{ded[-1][0].date()}" if ded else "-"
        print(f"\n{code} ({name}) [{csrc}]: {len(files)} files, {len(ded)} HW/LW {span}")
        r = analyze_station(code, name, lat, lon, ded)
        if r:
            out.append((r, format_station_block(r)))
    return out


if __name__ == '__main__':
    results = build()
    print("\n=== Zusammenfassung ===")
    for r, _ in results:
        print(f"  {r['name'][:42]:42} R²={r['r_squared']:.4f} RMS={r['rms_error']:.3f}m "
              f"M2={r['m2_amp']:.3f}m Z0={r['mean']:.3f}m n={r['n_hwlw']}")
    if '--write' in sys.argv and results:
        with open(TIDETABLES, 'rb') as f:
            data = f.read()
        sep = '' if data.endswith(b'\n\n') else ('\n' if data.endswith(b'\n') else '\n\n')
        with open(TIDETABLES, 'a', encoding='iso-8859-1') as f:
            f.write(sep + '\n'.join('\n' + b for _, b in results) + '\n')
        print(f"\nangehängt: {len(results)} Stationen an tidetables.txt")
