#!/usr/bin/env python3
"""Fit Pakistan National Hydrographic Office HOURLY tide-table PDFs -> UTide.

NHO PDFs render the hourly height grid as VECTOR CURVES (no text/raster), so
the grid is recovered by multi-pass OCR + majority vote (ocr_nho_tide_pdf.py:
render at several DPIs/PSMs, keep only clean X.XX detections, assign to the
(day x hour) grid by bbox, majority-vote per cell -> ~100%). One PDF = one month
of hourly heights, time zone PST (PKT, UTC+5, no DST), units metres, Chart Datum.
UTide constit='auto' (Rayleigh); ~1 month resolves the major constituents.
Calendar/prediction-derived -> harmonics_utide_tidetables.txt, meridian Asia/Karachi.
"""
import sys
sys.path.insert(0, '/home/oliver/py')
sys.path.insert(0, '/home/oliver/batch')
from datetime import datetime, timedelta
import numpy as np
import utide
from ocr_nho_tide_pdf import ocr_grid
from generate_germany_harmonics_175 import CONSTITUENTS_175, find_xtide_match

PK = '/home/oliver/weather/tide_tables/pakistan/'
TZ_OFFSET_H = 5  # Pakistan Standard Time (UTC+5, no DST)

# code: (display name, pdf, ndays, year, month, lat, lon, confidence)
STATIONS = {
    'ormara':  ('Ormara, Pakistan', PK + '4A- TT ORMARA HOURLY.pdf', 30, 2026, 6,
                25.203653, 64.676439, 7),   # IOC-Koords (ersetzt FES2022-Modell)
    'hajambro': ('Hajambro Creek (Entrance), Pakistan', PK + '7A- TT HAJAMBRO CREEK HOURLY.pdf', 30, 2026, 6,
                24.1333, 67.3667, 6),        # NHO-PDF-Koords (24°08'N 67°22'E), kein IOC
}


def fit_block(code):
    name, pdf, nd, yr, mo, lat, lon, conf = STATIONS[code]
    g = ocr_grid(pdf, nd)
    times, lev = [], []
    for (day, h), v in sorted(g.items()):
        if v is None:
            continue
        times.append(datetime(yr, mo, day, h) - timedelta(hours=TZ_OFFSET_H))
        lev.append(v)
    times = np.array(times); lev = np.array(lev)
    coef = utide.solve(times, lev, lat=lat, nodal=True, trend=False, method='ols',
                       conf_int='none', verbose=False, constit='auto')
    rec = utide.reconstruct(times, coef, verbose=False)['h']
    r2 = 1 - np.sum((lev - rec) ** 2) / np.sum((lev - lev.mean()) ** 2)
    rms = np.sqrt(np.mean((lev - rec) ** 2))
    from utide._ut_constants import ut_constants
    tbl = ut_constants['const']; un = [n.strip() for n in tbl.name]
    mp = {}
    for i, u in enumerate(coef['name']):
        u = u.strip()
        if u not in un:
            continue
        xt, _ = find_xtide_match(u, tbl.freq[un.index(u)] * 360.0)
        if xt:
            mp[xt] = (coef['A'][i], coef['g'][i] % 360)
    n_an = sum(1 for c, _ in CONSTITUENTS_175 if c in mp)
    L = [
        "# Harmonic constants derived from Pakistan NHO hourly tide tables",
        f"# using UTide (v{utide.__version__}) on OCR-extracted hourly heights",
        f"# {len(times)} hourly samples ({len(g)}/{nd*24} cells)",
        f"# from {min(times).strftime('%Y-%m-%d')} to {max(times).strftime('%Y-%m-%d')}",
        f"# R^2 = {r2:.4f}, RMS error = {rms:.4f} m",
        f"# Constituents analyzed: {n_an}",
        "#",
        f"# {name}",
        "# BEGIN HOT COMMENTS",
        "# country: Pakistan",
        "# source: Pakistan National Hydrographic Office tide tables \xd7 UTide",
        f"# station_id_context: NHO-{code}",
        "# date_imported: 20260613",
        "# datum: Chart Datum (NHO Pakistan)",
        f"# confidence: {conf}",
        "# !units: meters",
        f"# !longitude: {lon:.6f}",
        f"# !latitude: {lat:.6f}",
        name,
        "+00:00 :Asia/Karachi",
        f"{coef['mean']:.4f} meters",
    ]
    for cname, _ in CONSTITUENTS_175:
        if cname in mp and mp[cname][0] >= 0.00005:
            L.append(f"{cname:15s} {mp[cname][0]:.4f}  {mp[cname][1]:.2f}")
        else:
            L.append("x 0 0")
    return '\n'.join(L), r2, rms, max(mp[c][0] for c, _ in CONSTITUENTS_175 if c in mp)


if __name__ == '__main__':
    import io
    out = []
    for code in STATIONS:
        block, r2, rms, mx = fit_block(code)
        assert ':Asia/Karachi' in block and ':UTC' not in block and mx < 5
        out.append(block)
        sys.stderr.write(f"{code}: R^2={r2:.4f} RMS={rms:.4f} maxA={mx:.3f}\n")
    open('/tmp/pk_blocks.txt', 'w', encoding='iso-8859-1').write('\n'.join('\n'+b+'\n' for b in out))
    print("blocks -> /tmp/pk_blocks.txt")
