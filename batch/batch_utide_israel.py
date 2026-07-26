#!/usr/bin/env python3
"""
UTide harmonic analysis for Israeli tide gauges from SHELDA NetCDF data.
Creates harmonics_utide_israel.txt (ISO-8859-1).

Data:    SHELDA -- Sub-hourly European Quality Controlled Sea Level Dataset
         Balic, M.; Sepic, J. (2025), doi:10.14284/764, CC BY-NC 4.0
         257 tide gauges, 2007-2021, 1-15 min sampling, quality controlled.
         Source of the raw records: IOC Sea Level Station Monitoring Facility.
         The IOC live service only serves the last ~2 months, so SHELDA is
         the only remaining route to the Israeli records (all IOC stations in
         Israel went offline between 2015 and 2023).

Stations: haif/hade/hade2/ashd/ashd1/askl on the Mediterranean, elat on the
         Red Sea.  Neighbouring Aqaba (JOR) is analysed too as a cross-check
         for Eilat -- same basin, 10 km apart.

Meridian: the records are UTC, so the XTide block declares +00:00 and the
         Greenwich phase from utide is written unchanged.  (Contrast with
         batch_utide_japan.py, which declares +09:00 and therefore has to
         add speed*9h to the phase.)

Usage:  batch_utide_israel.py --inspect     show NetCDF structure, no analysis
        batch_utide_israel.py               run the analysis
"""
import sys
sys.path.insert(0, '/home/oliver/weather/py')

import argparse
import gc
import time as timer
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import netCDF4
import utide

from generate_germany_harmonics_175 import (
    CONSTITUENTS_175,
    find_xtide_match,
    read_header_from_template,
)

SHELDA_DIR = Path("/home/oliver/weather/scratchpad/shelda/nc")
TEMPLATE_PATH = Path("/home/oliver/weather/harmonics/classic/harmonics-dwf-20070318_mod.txt")
# Zwischenprodukt, kein Sammelbestand: die fertigen Bloecke werden an
# utide/harmonics_utide_observations.txt angehaengt (dort liegen alle
# utide-analysierten Pegelmessungen, Stand 2026-07-26: 1153 Stationen).
# Danach diese Datei loeschen -- genauso wie bei batch_utide_japan.py.
OUTPUT_PATH = Path("/home/oliver/weather/scratchpad/harmonics_utide_israel.txt")

# IOC station codes -> XTide location name, country, timezone.
# Coordinates come from the NetCDF attributes; the values here are only a
# fallback and a sanity check (IOC station list, retrieved 2026-07-26).
STATIONS = {
    'haif':  dict(name='Haifa',                  country='Israel', tz='Asia/Jerusalem', lat=32.822454, lon=35.007042),
    'hade':  dict(name='Hadera',                 country='Israel', tz='Asia/Jerusalem', lat=32.470530, lon=34.863057),
    'hade2': dict(name='Hadera Port',            country='Israel', tz='Asia/Jerusalem', lat=32.472330, lon=34.882600),
    'ashd':  dict(name='Ashdod',                 country='Israel', tz='Asia/Jerusalem', lat=31.830510, lon=34.641550),
    'ashd1': dict(name='Ashdod Marina',          country='Israel', tz='Asia/Jerusalem', lat=31.796269, lon=34.626447),
    'askl':  dict(name='Ashkelon',               country='Israel', tz='Asia/Jerusalem', lat=31.634928, lon=34.493757),
    'elat':  dict(name='Eilat',                  country='Israel', tz='Asia/Jerusalem', lat=29.501808, lon=34.917743),
    'aqab':  dict(name='Al `Aqabah',             country='Jordan', tz='Asia/Amman',     lat=29.409000, lon=34.979000),
}

# Same 67 constituents as the Japan run.
CONSTIT_67 = [
    'K1', 'O1', 'P1', 'Q1', 'J1', 'OO1', '2Q1', 'RHO1',
    'NO1', 'CHI1', 'PI1', 'PHI1', 'PSI1', 'SIG1', 'THE1', 'SO1',
    'M2', 'S2', 'N2', 'K2', 'L2', '2N2', 'R2', 'T2',
    'LDA2', 'MU2', 'NU2', 'EPS2', 'ETA2',
    'MF', 'MSF', 'MM', 'SA', 'SSA', 'MSM',
    'M3', 'MK3', 'MO3', 'SK3', 'SO3',
    'M4', 'MN4', 'MS4', 'MK4', 'S4', 'SN4',
    'M6', '2MS6', '2MN6',
    'M8',
    'H1', 'H2', 'S1',
    'ALP1', 'BET1', 'TAU1', 'UPS1',
    '2SM2', 'OP2', 'MKS2', 'SKM2',
    'NO3',
]

MIN_HOURS = 24 * 180          # at least half a year of hourly values
SPIKE_SIGMA = 8.0             # residual outlier filter on the hourly means

# SHELDA layout (verified 2026-07-26):
#   time          float64, "seconds since 2000-01-01 00:00:00 UTC"
#   sea_level_qc  float64, m   -- the quality-controlled series
#   residual      float64, m   -- de-tided, must NOT be analysed
#   qc_flags      int8         -- 1 = high-quality data, 2 = missing
LEVEL_VAR = 'sea_level_qc'
TIME_VAR = 'time'
FLAG_VAR = 'qc_flags'
FLAG_GOOD = 1


def find_files():
    """Map station code -> NetCDF path, by matching the code in the filename."""
    if not SHELDA_DIR.is_dir():
        sys.exit(f"SHELDA-Verzeichnis fehlt: {SHELDA_DIR}\n"
                 f"Erst das ZIP entpacken (nc/ als Zielverzeichnis).")
    ncs = sorted(SHELDA_DIR.rglob('*.nc'))
    if not ncs:
        sys.exit(f"Keine .nc-Dateien unter {SHELDA_DIR}")
    print(f"{len(ncs)} NetCDF-Dateien in {SHELDA_DIR}")
    found = {}
    for code in STATIONS:
        for p in ncs:
            stem = p.stem.lower()
            if stem == code or stem.startswith(code + '_') or f'_{code}_' in stem \
               or stem.endswith('_' + code):
                found[code] = p
                break
    return found


def parse_coord(value):
    """SHELDA stores coordinates as e.g. '31.80 degree N' -- to signed float."""
    s = str(value).strip()
    parts = s.split()
    try:
        v = float(parts[0])
    except (ValueError, IndexError):
        return None
    if parts[-1].upper() in ('S', 'W'):
        v = -v
    return v


def inspect(path):
    with netCDF4.Dataset(path) as ds:
        print(f"\n=== {path.name} ===")
        print("global attrs:", {k: str(ds.getncattr(k))[:70] for k in ds.ncattrs()})
        print("dims:", {d: len(ds.dimensions[d]) for d in ds.dimensions})
        for n, v in ds.variables.items():
            attrs = {k: str(v.getncattr(k))[:40] for k in v.ncattrs()}
            print(f"  {n:22s} {str(v.dtype):10s} {v.dimensions} {attrs}")


def load_series(path):
    """Read the NetCDF and return (datetimes_utc, levels_m, meta)."""
    with netCDF4.Dataset(path) as ds:
        for v in (TIME_VAR, LEVEL_VAR):
            if v not in ds.variables:
                raise RuntimeError(f"Variable '{v}' fehlt "
                                   f"(vorhanden: {list(ds.variables)})")
        tvar, lvar = ds.variables[TIME_VAR], ds.variables[LEVEL_VAR]
        times = netCDF4.num2date(tvar[:], tvar.units,
                                 only_use_cftime_datetimes=False,
                                 only_use_python_datetimes=True)
        levels = np.ma.filled(lvar[:].astype('f8'), np.nan)

        units = getattr(lvar, 'units', 'm').lower()
        if units.startswith('cm'):
            levels = levels / 100.0
        elif units.startswith('mm'):
            levels = levels / 1000.0

        # qc_flags: 1 = high quality, 2 = missing.  Trusting NaN alone is not
        # enough -- missing samples are present in the time axis.
        if FLAG_VAR in ds.variables:
            flags = np.ma.filled(ds.variables[FLAG_VAR][:], 2).astype('i2')
            good = flags == FLAG_GOOD
        else:
            good = np.ones(levels.shape, dtype=bool)

        meta = dict(
            level_units=getattr(lvar, 'units', '?'),
            lat=parse_coord(getattr(ds, 'Latitude', '')),
            lon=parse_coord(getattr(ds, 'Longitude', '')),
            provider=str(getattr(ds, 'Data provider', '?')).strip(),
            shelda_mean=str(getattr(ds, 'Mean value', '?')).strip(),
            n_total=len(levels),
        )

    times = np.asarray([t.replace(tzinfo=timezone.utc) for t in times])
    ok = good & np.isfinite(levels)
    meta['n_good'] = int(ok.sum())
    return times[ok], levels[ok], meta


def to_hourly(times, levels):
    """Average the 1-15 min samples into hourly bins (UTC, on the full hour)."""
    epoch = np.array([t.timestamp() for t in times])
    hour = np.floor(epoch / 3600.0).astype('int64')
    uniq, inv = np.unique(hour, return_inverse=True)
    total = np.bincount(inv, weights=levels)
    count = np.bincount(inv)
    mean = total / count
    dts = np.array([datetime.fromtimestamp(h * 3600, tz=timezone.utc) for h in uniq])
    return dts, mean


def analyze(code, path, constit):
    st = STATIONS[code]
    t0 = timer.time()
    print(f"\n{code}: {st['name']}, {st['country']}  [{path.name}]")

    times, levels, meta = load_series(path)
    if len(times) == 0:
        print("  keine gueltigen Werte")
        return None
    print(f"  Rohdaten: {meta['n_good']} von {meta['n_total']} Minutenwerten "
          f"mit QC-Flag 1 ({meta['n_good']/meta['n_total']*100:.1f}%), "
          f"Einheit {meta['level_units']}")

    dts, lev = to_hourly(times, levels)
    med = np.median(lev)
    mad = np.median(np.abs(lev - med))
    if mad > 0:
        keep = np.abs(lev - med) < SPIKE_SIGMA * 1.4826 * mad
        if (~keep).any():
            print(f"  {int((~keep).sum())} Ausreisser entfernt")
        dts, lev = dts[keep], lev[keep]

    span = (dts[-1] - dts[0]).days / 365.25
    expected = (dts[-1] - dts[0]).total_seconds() / 3600.0 + 1
    gaps = max(0.0, 1 - len(dts) / expected)
    print(f"  {len(dts)} Stundenwerte, {dts[0]:%Y-%m-%d} bis {dts[-1]:%Y-%m-%d} "
          f"({span:.1f} Jahre, {gaps*100:.1f}% Luecken), "
          f"Bereich {lev.min():.3f}..{lev.max():.3f} m")

    if len(dts) < MIN_HOURS:
        print(f"  ZU KURZ (< {MIN_HOURS} Stundenwerte) -- uebersprungen")
        return None

    # SHELDA rounds its coordinates to 2 decimals -- keep the sharper IOC
    # position and only use the file's as a cross-check.
    lat, lon = st['lat'], st['lon']
    if meta['lat'] is not None and (abs(meta['lat'] - lat) > 0.02
                                    or abs(meta['lon'] - lon) > 0.02):
        print(f"  WARNUNG: SHELDA-Position {meta['lat']:.2f}/{meta['lon']:.2f} "
              f"weicht von der IOC-Position {lat:.4f}/{lon:.4f} ab")

    print(f"  UTide (constit={constit})...", end='', flush=True)
    try:
        coef = utide.solve(dts, lev, lat=lat, nodal=True, trend=False,
                           method='ols', conf_int='none', verbose=False,
                           constit=constit)
    except Exception as e:
        print(f" FEHLER: {e}")
        return None
    print(f" OK ({len(coef['name'])} Konstituenten)", flush=True)

    from utide._ut_constants import ut_constants
    const_table = ut_constants['const']
    utide_all_names = [n.strip() for n in const_table.name]

    utide_results = {}
    for i, uname in enumerate(coef['name']):
        uname = uname.strip()
        if uname not in utide_all_names:
            continue
        uid = utide_all_names.index(uname)
        utide_speed = const_table.freq[uid] * 360.0
        xt_name, xt_speed = find_xtide_match(uname, utide_speed)
        if xt_name is None:
            continue
        # Record-Header deklariert Meridian +00:00 -> Greenwich-Phase direkt.
        utide_results[xt_name] = dict(amplitude=coef['A'][i],
                                      phase=coef['g'][i] % 360,
                                      speed=xt_speed)

    constituents, n_analyzed = [], 0
    for cname, speed in CONSTITUENTS_175:
        if cname in utide_results:
            r = utide_results[cname]
            constituents.append(dict(name=cname, amplitude=r['amplitude'],
                                     phase=r['phase'], speed=speed))
            n_analyzed += 1
        else:
            constituents.append(dict(name=cname, amplitude=0.0, phase=0.0,
                                     speed=speed, not_analyzed=True))

    recon = utide.reconstruct(dts, coef, verbose=False)
    resid = lev - recon['h']
    ss_res = np.sum(resid ** 2)
    ss_tot = np.sum((lev - np.mean(lev)) ** 2)
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0
    rms = np.sqrt(np.mean(resid ** 2))

    def amp(n):
        return next((c['amplitude'] for c in constituents if c['name'] == n), 0.0)

    result = dict(code=code, name=st['name'], country=st['country'], tz=st['tz'],
                  lat=lat, lon=lon, mean=coef['mean'], constituents=constituents,
                  n_analyzed=n_analyzed, r_squared=r2, rms_error=rms,
                  n_obs=len(dts), start_time=dts[0], end_time=dts[-1],
                  span_years=span, gaps=gaps,
                  m2=amp('M2'), s2=amp('S2'), k1=amp('K1'), o1=amp('O1'),
                  duration=timer.time() - t0)

    form = (result['k1'] + result['o1']) / (result['m2'] + result['s2']) \
        if (result['m2'] + result['s2']) > 0 else float('nan')
    print(f"  R2={r2:.4f}  RMS={rms:.4f} m  M2={result['m2']:.4f}  "
          f"S2={result['s2']:.4f}  K1={result['k1']:.4f}  O1={result['o1']:.4f}  "
          f"F={form:.2f}  ({result['duration']:.0f}s)")

    del coef, recon, dts, lev, resid
    gc.collect()
    return result


def format_station_block(r):
    location = f"{r['name']}, {r['country']}"
    L = []
    L.append("# Harmonic constants derived from SHELDA sub-hourly sea level data")
    L.append(f"# using UTide (v{utide.__version__}) harmonic analysis")
    L.append(f"# {r['n_obs']} hourly means")
    L.append(f"# from {r['start_time']:%Y-%m-%d} to {r['end_time']:%Y-%m-%d}")
    L.append(f"# R^2 = {r['r_squared']:.4f}, RMS error = {r['rms_error']:.4f} m")
    L.append(f"# Constituents analyzed: {r['n_analyzed']}")
    L.append("#")
    L.append(f"# {location}")
    L.append("# BEGIN HOT COMMENTS")
    L.append(f"# country: {r['country']}")
    L.append(f"# source: SHELDA sub-hourly sea level dataset (IOC station {r['code']}), "
             f"UTide analysis")
    L.append(f"# station_id_context: IOC {r['code']}")
    # 'restriction' is an enumerated TCD field, not free text -- build_tide_db
    # rejects anything outside its list.  The licence detail goes into note.
    L.append("# restriction: Non-commercial use only")
    L.append("# note: SHELDA (Balic & Sepic 2025, doi:10.14284/764), CC BY-NC 4.0. "
             f"{r['span_years']:.1f} Jahre 1-Minuten-Pegel, {r['n_analyzed']} "
             f"Konstituenten, R^2={r['r_squared']:.4f}.")
    L.append(f"# date_imported: {datetime.now():%Y%m%d}")
    L.append("# datum: station datum (IOC/SHELDA), Z0 = mean of the analysed record")
    # Luecken und Reihenlaenge bestimmen die Vertrauensstufe -- Ashdod Marina
    # (42% Luecken, instabiles Split-half) rechtfertigt keine 9 wie Haifa.
    conf = 9 if (r['gaps'] < 0.30 and r['span_years'] >= 2.0) else 7
    L.append(f"# confidence: {conf}")
    L.append("# !units: meters")
    L.append(f"# !longitude: {r['lon']:.6f}")
    L.append(f"# !latitude: {r['lat']:.6f}")
    L.append(location)
    L.append(f"+00:00 :{r['tz']}")
    L.append(f"{r['mean']:.4f} meters")
    for c in r['constituents']:
        if c.get('not_analyzed') or c['amplitude'] < 0.00005:
            L.append("x 0 0")
        else:
            L.append(f"{c['name']:15s} {c['amplitude']:.4f}  {c['phase']:.2f}")
    return '\n'.join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--constit', default='auto',
                    help="utide constit-Parameter (default: auto)")
    ap.add_argument('--inspect', action='store_true',
                    help='NetCDF-Struktur zeigen, keine Analyse')
    args = ap.parse_args()

    print("=" * 70)
    print("UTide Harmonic Analysis -- Israel (SHELDA)")
    print("=" * 70)

    files = find_files()
    missing = [c for c in STATIONS if c not in files]
    print(f"gefunden: {', '.join(sorted(files)) or '(keine)'}")
    if missing:
        print(f"nicht in SHELDA: {', '.join(missing)}")
    if not files:
        sys.exit("Keine der gesuchten Stationen im Datensatz.")

    if args.inspect:
        for code, p in sorted(files.items()):
            inspect(p)
        return

    results = []
    for code, p in sorted(files.items()):
        try:
            r = analyze(code, p, args.constit)
        except Exception as e:
            print(f"  FEHLER bei {code}: {e}")
            continue
        if r:
            results.append(r)

    if not results:
        sys.exit("\nKeine Station lieferte ein Ergebnis.")

    header = read_header_from_template(TEMPLATE_PATH)
    blocks = [format_station_block(r) for r in results]
    output = header.rstrip('\n') + '\n' + '\n'.join(blocks) + '\n'
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_bytes(output.encode('iso-8859-1'))

    print("\n" + "=" * 70)
    print(f"{len(results)} Stationen -> {OUTPUT_PATH}")
    for r in results:
        print(f"  {r['name']:16s} {r['lat']:8.4f} {r['lon']:8.4f}  "
              f"R2={r['r_squared']:.4f}  M2={r['m2']:.4f} m  "
              f"{r['start_time']:%Y-%m}..{r['end_time']:%Y-%m}")
    print("\nDanach:  build_tide_db "
          "/home/oliver/weather/harmonics/binary/harmonics_utide_israel.tcd \\\n"
          f"           {OUTPUT_PATH}")


if __name__ == '__main__':
    main()
