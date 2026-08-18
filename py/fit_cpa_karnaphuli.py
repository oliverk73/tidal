#!/usr/bin/env python3
"""Fit the Chittagong Port Authority "Handbook of Tide Tables" -> UTide blocks.

Source: CPA Department of Hydrography, "KARNAPHULI RIVER, Handbook of Tide
Tables 2026", eight stations (Kalurghat, Sadarghat, CCT-1, Khal No-09,
Khal No-18, Bay Terminal, Sangu River, Matarbari). The booklet is a scan; the
HW/LW pairs come from py/ocr_cpa_tide_pdf.py.

Times are Bangladesh Standard Time (UTC+6, no DST), heights are on Chart Datum
(the booklet states CD is approximately LAT). Positions are the booklet's own
"LIST OF CPA TIDE GAUGE STATION (AUTO)" on page 5, in arcseconds -- far more
precise than the whole arcminutes the ADMIRALTY tables print.

Fitting: the extrema are interpolated to a 15-minute series first. Fitting the
HW/LW pairs *directly* was tried and does not work -- the samples sit exactly at
the extrema of the signal being fitted, the normal equations are near-singular,
and M2 at Khal No. 18 came out at 6.6 m instead of 1.76 m. The interpolation is
what makes the problem well posed.

Round 0 of the interpolation is the plain half-cosine used for the Payra
booklet. Its known cost is that a symmetric shape between HW and LW damps the
shallow-water overtides. Later rounds therefore replace the assumed cosine by
the previous round's own model curve, time-warped and affinely rescaled so it
still passes exactly through the two published extremes; the shape assumption
converges to the station's real curve. At Khal No. 18 this lifts M4 from 0.050
to 0.066 m and M6 from 0.0038 to 0.0065 m and settles by round 2.

Samples that would have to bridge a dropped extreme (interval outside 2-11 h)
are masked out instead of interpolated across.

Residual limit of the method: the CPA predictions carry a seasonal modulation of
the tidal *range* -- HW is about 0.33 m higher in the SW monsoon than in winter
while LW barely moves -- which needs the annual sidebands of M2. Neither UTide
nor the XTide constituent list has them, so this part cannot be represented in a
harmonic block at all. It is what remains in the ~0.3 m RMS of the re-prediction
check; the timing is good to about 7 minutes.

Cleaning, in this order, because OCR of a scanned table does produce wrong
digits: gross-outlier clip on the height, drop days whose HW/LW sequence does
not alternate, drop implausible intervals between consecutive extremes, then one
pass of residual clipping against the fit itself.

Greenwich phases, displayed via meridian Asia/Dhaka.
"""
import json
import sys
from datetime import datetime, timedelta

import numpy as np
import utide

sys.path.insert(0, '/home/oliver/weather/py')
from generate_germany_harmonics_175 import CONSTITUENTS_175, find_xtide_match

TZ_OFFSET_H = 6                      # Bangladesh Standard Time
BASE = '/home/oliver/weather/tide_tables/bangladesh/chattogram'
JSON = BASE + '/cpa2026.json'
OUT = BASE + '/cpa_blocks.txt'

# OCR key: (display name, lat, lon, confidence, note)
# Positions are read off the gauge list on page 5. The 2026 list renamed two
# rows without moving them -- CCT-1 became "Dock Office" and Khal No-9 became
# "Khal No-10" -- while the tables kept the old names, so those two positions
# come from the 2025 edition, where name and coordinate still agree.
STATIONS = {
    'KALURGHAT': (
        'Kalurghat (Karnaphuli River), Bangladesh', 22.397500, 91.888056, 4,
        None),
    'SADARGHAT': (
        'Sadarghat (Karnaphuli River), Bangladesh', 22.324167, 91.833472, 4,
        None),
    'CCT-1': (
        'Chittagong Container Terminal (Karnaphuli River), Bangladesh',
        22.301889, 91.796583, 4,
        'Position aus der Pegelliste der Ausgabe 2025; die Ausgabe 2026 fuehrt '
        'dieselbe Position unter "Dock Office"'),
    'KHAL-09': (
        'Khal No. 9 (Karnaphuli River), Bangladesh', 22.268156, 91.821017, 4,
        'Position aus der Pegelliste der Ausgabe 2025; Ausgabe 2026 und die '
        'Baende bis 2021 nennen denselben Pegel "Khal No. 10"'),
    'KHAL-18': (
        'Khal No. 18, Bangladesh', 22.227331, 91.800497, 4, None),
    'BAY TERMINAL': (
        'Bay Terminal (Chittagong), Bangladesh', 22.329112, 91.753914, 4, None),
    'SANGURIVER': (
        'Sangu River, Bangladesh', 22.136443, 91.843394, 4, None),
    'MATARBARI': (
        'Matarbari, Bangladesh', 21.705194, 91.873481, 4, None),
}


def load(code):
    """Return the station's HW/LW pairs in UTC, sorted and de-duplicated."""
    raw = json.load(open(JSON))[code]
    pts = []
    for k, h in raw.items():
        t = datetime.strptime(k, '%Y-%m-%d %H:%M') - timedelta(hours=TZ_OFFSET_H)
        pts.append((t, float(h)))
    pts.sort()
    out = [pts[0]]
    for p in pts[1:]:
        if p[0] > out[-1][0]:
            out.append(p)
    return out


def clip_gross(pts):
    """Drop heights far outside the robust spread -- a misread digit can turn
    3.50 m into 35.02 m, and one such point wrecks the whole fit."""
    h = np.array([p[1] for p in pts])
    med = np.median(h)
    mad = np.median(np.abs(h - med)) or 0.1
    lim = 6 * 1.4826 * mad
    keep = np.abs(h - med) <= lim
    return [p for p, k in zip(pts, keep) if k], int((~keep).sum())


def alternating(pts):
    """Drop days whose HW/LW sequence does not alternate up-down-up-down."""
    by_day = {}
    for t, h in pts:
        by_day.setdefault(t.date(), []).append((t, h))
    good, n = [], 0
    for _, e in sorted(by_day.items()):
        if len(e) < 3:
            good += e
            continue
        d = [e[i + 1][1] - e[i][1] for i in range(len(e) - 1)]
        if all(d[i] * d[i + 1] < 0 for i in range(len(d) - 1)):
            good += e
        else:
            n += len(e)
    return good, n


def spacing(pts):
    """Drop extremes whose neighbour spacing is impossible for a semi-diurnal
    tide (a misread hour digit shows up here)."""
    keep = [True] * len(pts)
    for i in range(len(pts) - 1):
        dt = (pts[i + 1][0] - pts[i][0]).total_seconds() / 3600
        if dt < 2.0 or dt > 11.0:
            keep[i] = keep[i + 1] = False
    return [p for p, k in zip(pts, keep) if k], keep.count(False)


STEP_MIN = 15
SHAPE_ROUNDS = 2


def make_grid(pts):
    t0, t1 = pts[0][0], pts[-1][0]
    n = int((t1 - t0).total_seconds() / (60 * STEP_MIN)) + 1
    return np.array([t0 + timedelta(minutes=STEP_MIN * i) for i in range(n)])


def _walk(pts, grid):
    """Yield (index, interval, fraction) for every grid point inside a usable
    HW->LW interval; intervals that would bridge a dropped extreme are skipped."""
    j = 0
    for i, t in enumerate(grid):
        while j < len(pts) - 2 and pts[j + 1][0] <= t:
            j += 1
        a, b = pts[j], pts[j + 1]
        span = (b[0] - a[0]).total_seconds()
        if not 2 * 3600 <= span <= 11 * 3600:
            continue
        f = (t - a[0]).total_seconds() / span
        if 0.0 <= f <= 1.0:
            yield i, j, f


def cosine_series(pts, grid):
    lev = np.zeros(len(grid))
    ok = np.zeros(len(grid), bool)
    for i, j, f in _walk(pts, grid):
        a, b = pts[j], pts[j + 1]
        lev[i] = (a[1] + b[1]) / 2 + (a[1] - b[1]) / 2 * np.cos(np.pi * f)
        ok[i] = True
    return lev, ok


def model_extrema(coef, pts):
    """Model HW/LW nearest to each published extreme, plus the 5-min curve."""
    t0, t1 = pts[0][0], pts[-1][0]
    n = int((t1 - t0).total_seconds() / 300) + 1
    g = np.array([t0 + timedelta(minutes=5 * i) for i in range(n)])
    h = utide.reconstruct(g, coef, verbose=False)['h']
    idx = [i for i in range(1, n - 1) if (h[i] - h[i - 1]) * (h[i + 1] - h[i]) < 0]
    es = np.array([i * 300.0 for i in idx])
    ev = np.array([h[i] for i in idx])
    out = []
    for t, _ in pts:
        s = (t - t0).total_seconds()
        k = int(np.argmin(np.abs(es - s)))
        out.append((es[k], ev[k]) if abs(es[k] - s) < 5400 else None)
    gs = np.arange(n) * 300.0
    return out, gs, h


def shape_series(coef, pts, grid):
    """Warp the model curve so it hits every published extreme exactly."""
    me, gs, h = model_extrema(coef, pts)
    lev = np.zeros(len(grid))
    ok = np.zeros(len(grid), bool)
    for i, j, f in _walk(pts, grid):
        a, b = pts[j], pts[j + 1]
        ma, mb = me[j], me[j + 1]
        if ma is None or mb is None or mb[0] <= ma[0] \
                or abs(mb[1] - ma[1]) < 0.05 or abs(b[1] - a[1]) < 0.05:
            lev[i] = (a[1] + b[1]) / 2 + (a[1] - b[1]) / 2 * np.cos(np.pi * f)
        else:
            m = np.interp(ma[0] + f * (mb[0] - ma[0]), gs, h)
            lev[i] = a[1] + (m - ma[1]) * (b[1] - a[1]) / (mb[1] - ma[1])
        ok[i] = True
    return lev, ok


def run(grid, lev, ok, lat):
    return utide.solve(grid[ok], lev[ok], lat=lat, nodal=True, trend=False,
                       method='ols', conf_int='none', verbose=False,
                       constit='auto')


def fit(code):
    name, lat, lon, conf, note = STATIONS[code]
    pts = load(code)
    n_raw = len(pts)
    pts, n_gross = clip_gross(pts)
    pts, n_alt = alternating(pts)
    pts, n_gap = spacing(pts)

    grid = make_grid(pts)
    lev, ok = cosine_series(pts, grid)
    coef = run(grid, lev, ok, lat)

    # one residual pass against the fit -- catches OCR damage that survived the
    # structural checks
    t = np.array([p[0] for p in pts])
    r = np.array([p[1] for p in pts]) - utide.reconstruct(t, coef,
                                                          verbose=False)['h']
    s = 1.4826 * (np.median(np.abs(r - np.median(r))) or 0.02)
    keep = np.abs(r) <= max(4 * s, 0.25)
    n_res = int((~keep).sum())
    if n_res:
        pts = [p for p, k in zip(pts, keep) if k]
        grid = make_grid(pts)
        lev, ok = cosine_series(pts, grid)
        coef = run(grid, lev, ok, lat)

    for _ in range(SHAPE_ROUNDS):
        lev, ok = shape_series(coef, pts, grid)
        coef = run(grid, lev, ok, lat)

    rec = utide.reconstruct(grid[ok], coef, verbose=False)['h']
    obs = lev[ok]
    r2 = 1 - np.sum((obs - rec) ** 2) / np.sum((obs - obs.mean()) ** 2)
    rms = float(np.sqrt(np.mean((obs - rec) ** 2)))
    return dict(code=code, name=name, lat=lat, lon=lon, conf=conf, note=note,
                coef=coef, t=grid, pts=pts, n_raw=n_raw, n_used=len(pts),
                n_drop=(n_gross, n_alt, n_gap, n_res), r2=r2, rms=rms)


def check(f):
    """Re-predict HW/LW from the fitted constants and compare with the book.

    This is the test that matters: it compares what XTide will show against
    what the booklet prints, and it also exposes OCR damage the fit swallowed.
    """
    pts = f['pts']
    me, _, _ = model_extrema(f['coef'], pts)
    t0 = pts[0][0]
    dt = [(me[i][0] - (p[0] - t0).total_seconds()) / 60
          for i, p in enumerate(pts) if me[i]]
    dh = [me[i][1] - p[1] for i, p in enumerate(pts) if me[i]]
    return (float(np.sqrt(np.mean(np.square(dt)))),
            float(np.sqrt(np.mean(np.square(dh)))), len(dt))


def amp(coef, name):
    for i, n in enumerate(coef['name']):
        if n.strip() == name:
            return float(coef['A'][i]), float(coef['g'][i] % 360)
    return 0.0, 0.0


def block(f, dt, dh):
    coef = f['coef']
    from utide._ut_constants import ut_constants
    tbl = ut_constants['const']
    unames = [n.strip() for n in tbl.name]
    mp = {}
    for i, un in enumerate(coef['name']):
        un = un.strip()
        if un not in unames:
            continue
        sp = tbl.freq[unames.index(un)] * 360.0
        xt, _ = find_xtide_match(un, sp)
        if xt:
            mp[xt] = (coef['A'][i], coef['g'][i] % 360)
    n_an = sum(1 for c, _ in CONSTITUENTS_175 if c in mp)
    g, a, sp_, r = f['n_drop']

    L = [
        '# Harmonic constants derived from Chittagong Port Authority tide tables',
        f'# using UTide (v{utide.__version__}) with shape-corrected interpolation of HW/LW data',
        f'# {f["n_used"]} of {f["n_raw"]} HW/LW points'
        f' (verworfen: {g} Ausreisser, {a} nicht alternierend,'
        f' {sp_} Abstand, {r} Residuum)',
        f'# from {f["t"][0].strftime("%Y-%m-%d")} to'
        f' {f["t"][-1].strftime("%Y-%m-%d")}',
        f'# R^2 = {f["r2"]:.4f}, RMS error = {f["rms"]:.4f} m',
        f'# Constituents analyzed: {n_an}',
        '#',
        f'# {f["name"]}',
        '# BEGIN HOT COMMENTS',
        '# country: Bangladesh',
        # libtcd erlaubt in dieser Zeile hoechstens 90 Zeichen
        '# source: Chittagong Port Authority, Karnaphuli Tide Tables 2026 '
        '\xd7 UTide',
        f'# station_id_context: CPA-{f["code"]}',
        '# date_imported: 20260807',
        '# datum: Chart Datum (CPA gauge zero, ~LAT)',
        f'# confidence: {f["conf"]}',
        '# note: Buchtabelle per OCR eingelesen; Zeiten BST (UTC+6), Hoehen ueber CD.',
        f'# note: Rueckrechnung gegen die Buchtabelle: {dt:.1f} min, {dh:.3f} m RMS.',
        '# note: Der Rest der Abweichung ist die jahreszeitliche Modulation des '
        'Tidenhubs (HW im SW-Monsun ~0.33 m hoeher, NW fast unveraendert). Sie '
        'braeuchte die Jahresseitenbaender von M2, die es in XTide nicht gibt.',
    ]
    if f['note']:
        L.append(f'# note: {f["note"]}')
    L += [
        '# !units: meters',
        f'# !longitude: {f["lon"]:.6f}',
        f'# !latitude: {f["lat"]:.6f}',
        f['name'],
        '+00:00 :Asia/Dhaka',
        f'{coef["mean"]:.4f} meters',
    ]
    for cname, _ in CONSTITUENTS_175:
        if cname in mp and mp[cname][0] >= 0.00005:
            L.append(f'{cname:15s} {mp[cname][0]:.4f}  {mp[cname][1]:.2f}')
        else:
            L.append('x 0 0')
    return '\n'.join(L)


def main():
    blocks = []
    print(f'{"Station":13} {"n benutzt":>12} {"R2":>7} {"RMS":>6} '
          f'{"Kontrolle":>15} {"Z0":>6} {"M2":>6} {"S2":>6} {"M4":>6} {"M4/M2":>6}')
    for code in STATIONS:
        f = fit(code)
        dt, dh, n = check(f)
        m2 = amp(f['coef'], 'M2')[0]
        s2 = amp(f['coef'], 'S2')[0]
        m4 = amp(f['coef'], 'M4')[0]
        print(f'{code:13} {f["n_used"]:5d}/{f["n_raw"]:<6d} {f["r2"]:7.4f} '
              f'{f["rms"]:6.3f} {dt:6.1f} min {dh:5.3f} m '
              f'{f["coef"]["mean"]:6.3f} {m2:6.3f} {s2:6.3f} {m4:6.3f} '
              f'{m4/m2:6.4f}')
        blocks.append(block(f, dt, dh))
    if '--write' in sys.argv:
        with open(OUT, 'w', encoding='iso-8859-1') as fh:
            fh.write('\n\n'.join(blocks) + '\n')
        print('geschrieben ->', OUT)


if __name__ == '__main__':
    main()
