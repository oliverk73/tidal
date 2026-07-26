#!/usr/bin/env python3
"""
UTide harmonic analysis for Cyprus tide gauges from IOC 1-minute data.
Creates harmonics_utide_cyprus.txt (ISO-8859-1).

Data:    IOC Sea Level Station Monitoring Facility, radar gauges, 1 min.
         Downloaded with fetch_ioc.py into water_levels/IOC/ioc_<code>.csv.
         These stations are live, so the service still serves their full
         history -- no SHELDA detour needed (unlike the Israeli stations,
         which are offline and whose IOC records have been purged).

Stations: the four the collection is missing (Paralimni, Larnaka, Pafos,
         Pomos) plus Limassol.  Limassol is the control: ATT NP208 already
         has it, so its UTide result can be compared against an independent
         source before the other four are trusted.  It also has by far the
         longest record (since 2023-06), which makes it the only one where
         the annual constituents SA/SSA mean anything.

Meridian: IOC timestamps are UTC, so the block declares +00:00 and the
         Greenwich phase from utide is written unchanged.

Record length caveat: four of the five stations only started in Nov 2025,
         i.e. roughly 8 months.  The Rayleigh criterion needs 182.6 days to
         separate S2/K2 and K1/P1, so those pairs are only just resolvable
         and SA/SSA are not resolvable at all.  constit='auto' lets utide
         decide; the count of resolved constituents is written into each
         block header so the limitation stays visible in the TCD.
"""
import sys
sys.path.insert(0, '/home/oliver/weather/py')

import argparse
import csv
import gc
import time as timer
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import utide

from generate_germany_harmonics_175 import (
    CONSTITUENTS_175,
    find_xtide_match,
    read_header_from_template,
)

DATA_DIR = Path("/home/oliver/weather/water_levels/IOC")
TEMPLATE_PATH = Path("/home/oliver/weather/harmonics/classic/harmonics-dwf-20070318_mod.txt")
# Zwischenprodukt, kein Sammelbestand: die fertigen Bloecke werden an
# utide/harmonics_utide_observations.txt angehaengt (dort liegen alle
# utide-analysierten Pegelmessungen, Stand 2026-07-26: 1153 Stationen).
# Danach diese Datei loeschen -- genauso wie bei batch_utide_japan.py.
OUTPUT_PATH = Path("/home/oliver/weather/scratchpad/harmonics_utide_cyprus.txt")

TZ = 'Asia/Nicosia'
# Positions from the IOC station list, retrieved 2026-07-26.
STATIONS = [
    dict(code='para1', name='Paralimni',            lat=35.038000, lon=34.036000),
    dict(code='larn3', name='Larnaka',              lat=34.928000, lon=33.645000),
    dict(code='pafo',  name='Pafos',                lat=34.755000, lon=32.408000),
    dict(code='pomo',  name='Pomos',                lat=35.175000, lon=32.556000),
    # Kontrollstation -- Name bewusst abweichend von "Limassol, Cyprus" aus
    # ATT NP208, sonst sind die beiden ueber `tide -l` nicht unterscheidbar.
    dict(code='leme',  name='Lemesos (Limassol)',   lat=34.669000, lon=33.042000),
]

MIN_HOURS = 24 * 120        # mindestens 120 Tage Stundenwerte
SPIKE_SIGMA = 6.0           # Ausreisserfilter auf den Stundenmitteln


def load_csv(code):
    path = DATA_DIR / f"ioc_{code}.csv"
    if not path.is_file():
        return None, None, f"Datei fehlt: {path}"
    times, levels = [], []
    with open(path) as f:
        for row in csv.DictReader(f):
            try:
                t = datetime.strptime(row['utc'][:19], "%Y-%m-%d %H:%M:%S")
                v = float(row['level_m'])
            except (ValueError, KeyError):
                continue
            if not np.isfinite(v):
                continue
            times.append(t.replace(tzinfo=timezone.utc))
            levels.append(v)
    if not times:
        return None, None, "keine gueltigen Werte"
    return np.asarray(times), np.asarray(levels, dtype='f8'), None


def to_hourly(times, levels):
    """1-Minuten-Werte zu Stundenmitteln buendeln (UTC, volle Stunde)."""
    epoch = np.array([t.timestamp() for t in times])
    hour = np.floor(epoch / 3600.0).astype('int64')
    uniq, inv = np.unique(hour, return_inverse=True)
    mean = np.bincount(inv, weights=levels) / np.bincount(inv)
    dts = np.array([datetime.fromtimestamp(h * 3600, tz=timezone.utc) for h in uniq])
    return dts, mean


def despike(dts, lev):
    """Grobe Ausreisser entfernen (Radarpegel setzen bei Stoerungen Spruenge)."""
    med = np.median(lev)
    mad = np.median(np.abs(lev - med))
    if mad <= 0:
        return dts, lev, 0
    keep = np.abs(lev - med) < SPIKE_SIGMA * 1.4826 * mad
    return dts[keep], lev[keep], int((~keep).sum())


def analyze(st, constit):
    t0 = timer.time()
    print(f"\n{st['code']}: {st['name']}, Cyprus")

    times, levels, err = load_csv(st['code'])
    if err:
        print(f"  {err}")
        return None
    print(f"  Rohdaten: {len(times)} Minutenwerte")

    dts, lev = to_hourly(times, levels)
    dts, lev, nspike = despike(dts, lev)
    if nspike:
        print(f"  {nspike} Ausreisser entfernt")

    span_days = (dts[-1] - dts[0]).days
    expected = (dts[-1] - dts[0]).total_seconds() / 3600.0 + 1
    gaps = max(0.0, 1 - len(dts) / expected)
    print(f"  {len(dts)} Stundenwerte, {dts[0]:%Y-%m-%d} bis {dts[-1]:%Y-%m-%d} "
          f"({span_days} Tage, {gaps*100:.1f}% Luecken), "
          f"Bereich {lev.min():.3f}..{lev.max():.3f} m")

    if len(dts) < MIN_HOURS:
        print(f"  ZU KURZ (< {MIN_HOURS} Stundenwerte) -- uebersprungen")
        return None
    if span_days < 182:
        print(f"  HINWEIS: {span_days} Tage < 182.6 -- S2/K2 und K1/P1 nicht "
              f"nach Rayleigh trennbar, utide inferiert sie")

    print(f"  UTide (constit={constit})...", end='', flush=True)
    try:
        coef = utide.solve(dts, lev, lat=st['lat'], nodal=True, trend=False,
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
        xt_name, xt_speed = find_xtide_match(uname, const_table.freq[uid] * 360.0)
        if xt_name is None:
            continue
        # Meridian +00:00 -> Greenwich-Phase unveraendert uebernehmen.
        utide_results[xt_name] = dict(amplitude=coef['A'][i],
                                      phase=coef['g'][i] % 360)

    constituents, n_analyzed = [], 0
    for cname, speed in CONSTITUENTS_175:
        if cname in utide_results:
            r = utide_results[cname]
            constituents.append(dict(name=cname, amplitude=r['amplitude'],
                                     phase=r['phase']))
            n_analyzed += 1
        else:
            constituents.append(dict(name=cname, amplitude=0.0, phase=0.0,
                                     not_analyzed=True))

    recon = utide.reconstruct(dts, coef, verbose=False)
    resid = lev - recon['h']
    ss_tot = np.sum((lev - np.mean(lev)) ** 2)
    r2 = 1 - np.sum(resid ** 2) / ss_tot if ss_tot > 0 else 0.0
    rms = np.sqrt(np.mean(resid ** 2))

    def amp(n):
        return next((c['amplitude'] for c in constituents if c['name'] == n), 0.0)

    m2, s2, k1, o1 = amp('M2'), amp('S2'), amp('K1'), amp('O1')
    form = (k1 + o1) / (m2 + s2) if (m2 + s2) > 0 else float('nan')

    r = dict(constituents=constituents, n_analyzed=n_analyzed, r_squared=r2,
             rms_error=rms, mean=coef['mean'], n_obs=len(dts),
             start_time=dts[0], end_time=dts[-1], span_days=span_days,
             m2=m2, s2=s2, k1=k1, o1=o1, form=form,
             duration=timer.time() - t0, **st)

    print(f"  R2={r2:.4f}  RMS={rms:.4f} m  M2={m2:.4f}  S2={s2:.4f}  "
          f"K1={k1:.4f}  O1={o1:.4f}  F={form:.2f}  ({r['duration']:.0f}s)")

    del coef, recon, dts, lev, resid
    gc.collect()
    return r


def format_station_block(r):
    location = f"{r['name']}, Cyprus"
    L = []
    L.append("# Harmonic constants derived from IOC 1-minute sea level data")
    L.append(f"# using UTide (v{utide.__version__}) harmonic analysis")
    L.append(f"# {r['n_obs']} hourly means over {r['span_days']} days")
    L.append(f"# from {r['start_time']:%Y-%m-%d} to {r['end_time']:%Y-%m-%d}")
    L.append(f"# R^2 = {r['r_squared']:.4f}, RMS error = {r['rms_error']:.4f} m")
    L.append(f"# Constituents analyzed: {r['n_analyzed']}")
    if r['span_days'] < 182:
        L.append("# NOTE: record shorter than 182.6 d -- S2/K2 and K1/P1 inferred, "
                 "SA/SSA not resolvable")
    L.append("#")
    L.append(f"# {location}")
    L.append("# BEGIN HOT COMMENTS")
    L.append("# country: Cyprus")
    L.append(f"# source: IOC Sea Level Station Monitoring Facility (station "
             f"{r['code']}), UTide analysis")
    L.append(f"# station_id_context: IOC {r['code']}")
    L.append(f"# note: {r['span_days']} Tage 1-Minuten-Radarpegel, "
             f"{r['n_analyzed']} Konstituenten, R^2={r['r_squared']:.4f}, "
             f"F=({r['k1']:.3f}+{r['o1']:.3f})/({r['m2']:.3f}+{r['s2']:.3f})"
             f"={r['form']:.2f}.")
    L.append(f"# date_imported: {datetime.now():%Y%m%d}")
    L.append("# datum: station datum (IOC), Z0 = mean of the analysed record")
    L.append(f"# confidence: {6 if r['span_days'] < 182 else 8}")
    L.append("# !units: meters")
    L.append(f"# !longitude: {r['lon']:.6f}")
    L.append(f"# !latitude: {r['lat']:.6f}")
    L.append(location)
    L.append(f"+00:00 :{TZ}")
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
    ap.add_argument('--only', help="nur diese Codes (kommagetrennt)")
    args = ap.parse_args()

    print("=" * 70)
    print("UTide Harmonic Analysis -- Cyprus (IOC)")
    print("=" * 70)

    wanted = set(args.only.split(',')) if args.only else None
    results = []
    for st in STATIONS:
        if wanted and st['code'] not in wanted:
            continue
        try:
            r = analyze(st, args.constit)
        except Exception as e:
            print(f"  FEHLER bei {st['code']}: {e}")
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
    print(f"{len(results)} Stationen -> {OUTPUT_PATH}\n")
    print(f"{'Station':24s} {'Tage':>5s} {'R2':>7s} {'RMS':>7s} "
          f"{'M2':>7s} {'S2':>7s} {'K1':>7s} {'O1':>7s} {'F':>5s}")
    for r in results:
        print(f"{r['name']:24s} {r['span_days']:5d} {r['r_squared']:7.4f} "
              f"{r['rms_error']:7.4f} {r['m2']:7.4f} {r['s2']:7.4f} "
              f"{r['k1']:7.4f} {r['o1']:7.4f} {r['form']:5.2f}")


if __name__ == '__main__':
    main()
