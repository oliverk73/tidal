#!/usr/bin/env python3
"""Shape-corrected interpolation of HW/LW tide tables, for UTide fitting.

Why this exists
---------------
Tide tables print only the extremes. To run a harmonic analysis on them the
gaps have to be filled, and the usual filler is a half cosine between each
HW and the next LW. That is wrong in a specific, one-sided way: a cosine is a
pure semidiurnal shape, so it carries no overtides at all. The analysis can
only recover the overtides that the *interpolation* left in the series, and
the fit therefore comes out systematically too smooth. In the deep ocean this
hardly matters; in a shallow estuary, where the tide curve is visibly skewed
(fast flood, slow ebb), it removes most of M4 and M6.

The audit that prompted this module: of 3760 records in
harmonics_utide_tidetables.txt, the 110 fitted with a plain cosine have a
median M4/M2 of 0.0062 against 0.0200 for the rest -- a factor of three.

What it does instead
--------------------
Round 0 is the plain half cosine, purely to get a first model. Every later
round throws the assumed shape away and uses the *previous round's own model
curve* as the filler: between each published pair of extremes the model curve
is time-warped onto the published interval and affinely rescaled, so that it
still passes exactly through both published values but now bends the way the
model says the tide bends. The published extremes are never moved -- they are
the data. Only the invented points between them get better.

This converges by round 2; a third round changes M4 by well under a percent.

What it cannot fix
------------------
The extremes themselves. If the table carries a seasonal modulation of the
range that the constituent set cannot express, that error stays.

Do not try to fit the HW/LW pairs directly without interpolating. It was tried
and it fails: the samples sit exactly at the extrema of the signal being
fitted, the normal equations are near-singular, and M2 comes out several times
too large.
"""
from datetime import timedelta

import numpy as np
import utide

STEP_MIN = 15
SHAPE_ROUNDS = 2

# an interval outside this range does not describe one HW->LW leg; it bridges a
# dropped or missing extreme and must not be interpolated across
MIN_SPAN_H, MAX_SPAN_H = 2.0, 11.0


def make_grid(pts, step_min=STEP_MIN):
    t0, t1 = pts[0][0], pts[-1][0]
    n = int((t1 - t0).total_seconds() / (60 * step_min)) + 1
    return np.array([t0 + timedelta(minutes=step_min * i) for i in range(n)])


def _walk(pts, grid):
    """Yield (grid index, interval index, fraction) for every grid point that
    lies inside a usable HW->LW interval."""
    j = 0
    for i, t in enumerate(grid):
        while j < len(pts) - 2 and pts[j + 1][0] <= t:
            j += 1
        a, b = pts[j], pts[j + 1]
        span = (b[0] - a[0]).total_seconds()
        if not MIN_SPAN_H * 3600 <= span <= MAX_SPAN_H * 3600:
            continue
        f = (t - a[0]).total_seconds() / span
        if 0.0 <= f <= 1.0:
            yield i, j, f


def cosine_series(pts, grid):
    """Round 0: half cosine between consecutive extremes."""
    lev = np.zeros(len(grid))
    ok = np.zeros(len(grid), bool)
    for i, j, f in _walk(pts, grid):
        a, b = pts[j], pts[j + 1]
        lev[i] = (a[1] + b[1]) / 2 + (a[1] - b[1]) / 2 * np.cos(np.pi * f)
        ok[i] = True
    return lev, ok


def model_extrema(coef, pts, step_s=300):
    """Model HW/LW nearest to each published extreme, plus the fine curve.

    Returns (matches, grid_seconds, heights) where matches[i] is the model
    extreme paired with pts[i], or None if the model has none within 90 min.
    """
    t0, t1 = pts[0][0], pts[-1][0]
    n = int((t1 - t0).total_seconds() / step_s) + 1
    g = np.array([t0 + timedelta(seconds=step_s * i) for i in range(n)])
    h = utide.reconstruct(g, coef, verbose=False)['h']
    idx = [i for i in range(1, n - 1) if (h[i] - h[i - 1]) * (h[i + 1] - h[i]) < 0]
    es = np.array([i * float(step_s) for i in idx])
    ev = np.array([h[i] for i in idx])
    out = []
    for t, _ in pts:
        s = (t - t0).total_seconds()
        if len(es) == 0:
            out.append(None)
            continue
        k = int(np.argmin(np.abs(es - s)))
        out.append((es[k], ev[k]) if abs(es[k] - s) < 5400 else None)
    return out, np.arange(n) * float(step_s), h


def shape_series(coef, pts, grid):
    """Later rounds: warp the model curve so it hits every published extreme."""
    me, gs, h = model_extrema(coef, pts)
    lev = np.zeros(len(grid))
    ok = np.zeros(len(grid), bool)
    for i, j, f in _walk(pts, grid):
        a, b = pts[j], pts[j + 1]
        ma, mb = me[j], me[j + 1]
        # fall back to the cosine where the model has no matching pair, or
        # where rescaling would divide by a vanishing range
        if ma is None or mb is None or mb[0] <= ma[0] \
                or abs(mb[1] - ma[1]) < 0.05 or abs(b[1] - a[1]) < 0.05:
            lev[i] = (a[1] + b[1]) / 2 + (a[1] - b[1]) / 2 * np.cos(np.pi * f)
        else:
            m = np.interp(ma[0] + f * (mb[0] - ma[0]), gs, h)
            lev[i] = a[1] + (m - ma[1]) * (b[1] - a[1]) / (mb[1] - ma[1])
        ok[i] = True
    return lev, ok


def solve(grid, lev, ok, lat, constit='auto'):
    return utide.solve(grid[ok], lev[ok], lat=lat, nodal=True, trend=False,
                       method='ols', conf_int='none', verbose=False,
                       constit=constit)


def fit(pts, lat, constit='auto', rounds=SHAPE_ROUNDS, step_min=STEP_MIN):
    """HW/LW list [(datetime_utc, height)] -> (coef, grid, lev, ok, r2, rms).

    r2/rms are measured against the final interpolated series, so they say how
    well the constants describe that series -- not how well they reproduce the
    book. Use roundtrip() for that.
    """
    pts = sorted(pts)
    grid = make_grid(pts, step_min)
    lev, ok = cosine_series(pts, grid)
    coef = solve(grid, lev, ok, lat, constit)
    for _ in range(rounds):
        lev, ok = shape_series(coef, pts, grid)
        coef = solve(grid, lev, ok, lat, constit)
    rec = utide.reconstruct(grid[ok], coef, verbose=False)['h']
    obs = lev[ok]
    r2 = float(1 - np.sum((obs - rec) ** 2) / np.sum((obs - obs.mean()) ** 2))
    rms = float(np.sqrt(np.mean((obs - rec) ** 2)))
    return coef, grid, lev, ok, r2, rms


def roundtrip(coef, pts):
    """Re-predict HW/LW from the constants and compare with the published table.

    This is the test that matters: it compares what XTide will show against
    what the book prints. Returns (RMS minutes, RMS meters, n matched).
    """
    pts = sorted(pts)
    me, _, _ = model_extrema(coef, pts)
    t0 = pts[0][0]
    dt = [(me[i][0] - (p[0] - t0).total_seconds()) / 60
          for i, p in enumerate(pts) if me[i]]
    dh = [me[i][1] - p[1] for i, p in enumerate(pts) if me[i]]
    if not dt:
        return float('nan'), float('nan'), 0
    return (float(np.sqrt(np.mean(np.square(dt)))),
            float(np.sqrt(np.mean(np.square(dh)))), len(dt))


def amp(coef, name):
    """(amplitude, Greenwich phase) of one constituent, (0,0) if absent."""
    for i, n in enumerate(coef['name']):
        if n.strip() == name:
            return float(coef['A'][i]), float(coef['g'][i] % 360)
    return 0.0, 0.0
