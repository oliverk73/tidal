#!/usr/bin/env python3
"""Fit Payra Port Authority (Rabnabad Channel) HW/LW tide tables -> UTide blocks.

Source: PPA Department of Hydrography "Rabnabad Channel Tide Table 2025" PDF
(text layer, two stations per page; see parse_payra_pdf.py). Heights refer to
zero on the tide gauge, ~Lowest Astronomical Tide. Times are Bangladesh
Standard Time (UTC+6, no DST). HW/LW are cosine-interpolated to 15-min and
analyzed with UTide constit='auto' (Rayleigh) to avoid short-record diurnal-band
blow-up. Greenwich phases, displayed via meridian Asia/Dhaka.
Calendar-derived -> harmonics_utide_tidetables.txt (UTide TC group).

Coordinates from the booklet page "POSITIONS OF PPA TIDE GAUGES".
"""
import sys
sys.path.insert(0, '/home/oliver/py')
sys.path.insert(0, '/home/oliver/batch')
from datetime import timedelta
import numpy as np
import utide

from parse_payra_pdf import parse_station
import batch_utide_shoa_chile as B
from generate_germany_harmonics_175 import CONSTITUENTS_175, find_xtide_match

PDF = '/home/oliver/annual_predictions/bangladesh/payra/ppa_10.pdf'
TZ_OFFSET_H = 6  # Bangladesh Standard Time (UTC+6, no DST)
YEAR = 2025

# code: (display name, lat, lon, confidence, meridian)
STATIONS = {
    'charipara':  ('Charipara (Rabnabad Channel), Bangladesh', 21.951389, 90.300556, 4, 'Asia/Dhaka'),
    'kaurchar':   ('Kauar Char (Rabnabad Channel), Bangladesh', 21.832778, 90.255000, 4, 'Asia/Dhaka'),
    'monopile-1': ('Monopile-1 (Rabnabad Channel), Bangladesh', 21.621389, 90.208056, 4, 'Asia/Dhaka'),
    'monopile-2': ('Monopile-2 (Rabnabad Channel), Bangladesh', 21.457778, 90.126389, 4, 'Asia/Dhaka'),
}


def fit_block(code):
    name, lat, lon, conf, meridian = STATIONS[code]
    hwlw = parse_station(PDF, code, YEAR)
    pts = [(dt - timedelta(hours=TZ_OFFSET_H), h) for dt, h in hwlw]  # BST -> UTC
    pts.sort()
    cl = [pts[0]]
    for p in pts[1:]:
        if p[0] > cl[-1][0]:
            cl.append(p)
    t, l = B.cosine_interpolate(cl)
    coef = utide.solve(t, l, lat=lat, nodal=True, trend=False, method='ols',
                       conf_int='none', verbose=False, constit='auto')
    rec = utide.reconstruct(t, coef, verbose=False)['h']
    r2 = 1 - np.sum((l - rec) ** 2) / np.sum((l - l.mean()) ** 2)
    rms = np.sqrt(np.mean((l - rec) ** 2))

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

    L = [
        "# Harmonic constants derived from Payra Port Authority tide tables",
        f"# using UTide (v{utide.__version__}) with cosine-interpolated HW/LW data",
        f"# {len(cl)} HW/LW points -> {len(t)} interpolated points",
        f"# from {t[0].strftime('%Y-%m-%d')} to {t[-1].strftime('%Y-%m-%d')}",
        f"# R^2 = {r2:.4f}, RMS error = {rms:.4f} m",
        f"# Constituents analyzed: {n_an}",
        "#",
        f"# {name}",
        "# BEGIN HOT COMMENTS",
        "# country: Bangladesh",
        "# source: Payra Port Authority (Dept. of Hydrography) tide tables \xd7 UTide",
        f"# station_id_context: PPA-{code}",
        "# date_imported: 20260613",
        "# datum: Chart Datum (PPA gauge zero, ~LAT)",
        f"# confidence: {conf}",
        "# !units: meters",
        f"# !longitude: {lon:.6f}",
        f"# !latitude: {lat:.6f}",
        name,
        f"+00:00 :{meridian}",
        f"{coef['mean']:.4f} meters",
    ]
    for cname, _ in CONSTITUENTS_175:
        if cname in mp and mp[cname][0] >= 0.00005:
            L.append(f"{cname:15s} {mp[cname][0]:.4f}  {mp[cname][1]:.2f}")
        else:
            L.append("x 0 0")
    return '\n'.join(L), r2, rms


if __name__ == '__main__':
    blocks = []
    for code in STATIONS:
        block, r2, rms = fit_block(code)
        print(f"{code:12} R^2={r2:.4f}  RMS={rms:.4f} m")
        blocks.append(block)
    if '--write' in sys.argv:
        out = '/home/oliver/annual_predictions/bangladesh/payra_blocks.txt'
        with open(out, 'w', encoding='iso-8859-1') as f:
            f.write('\n'.join(blocks) + '\n')
        print("written ->", out)
