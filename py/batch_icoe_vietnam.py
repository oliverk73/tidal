#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ICOE-Vietnam-Batch: 24 Staatshoehensystem-Stationen -> UTide -> Harmonics.

Die Sheets sind 'Hệ cao độ Nhà Nước' (Staatshoehensystem, Z0~0, Minima bis
-2.5 m). Fuer die App wird das Bezugsniveau auf abgeleitetes LAT geschoben:
19-Jahre-Stundenrekonstruktion (1 Nodalzyklus), Minimum -> 0. Original-Z0
bleibt in datum_note dokumentiert (reversibel).

Ausgeschlossen (siehe Survey 2026-06-12): TANHIEP (nicht tidal, M2=0.01,
Copy-Paste-Koordinaten von Rach Gia), CAMAU (R2=0.87, abflussdominiert),
VUNGTAU/PHUAN/HATIEN/HONDAU/PHUQUOC/QUYNHON (besser via VHO/Messung gedeckt).

Usage: python3 py/batch_icoe_vietnam.py > harmonics/help/icoe_vn_blocks_20260612.txt
"""
from __future__ import annotations
import sys
import warnings
from datetime import datetime, timedelta

import numpy as np
import utide

warnings.filterwarnings('ignore')
sys.path.insert(0, '/home/oliver/py')
sys.path.insert(0, '/home/oliver/batch')
from generate_germany_harmonics_175 import CONSTITUENTS_175, find_xtide_match
from batch_utide_uk_tidetimes import CONSTIT_67
from fit_icoe_vietnam import parse_sheet, DEFAULT_FILES

# sheet -> Anzeigename (ASCII, ISO-8859-1-sicher; Stil wie VHO-Import)
STATIONS = {
    'VAMKENH':   'Vam Kenh (Cua Tieu), Vietnam',
    'BINHDAI':   'Binh Dai (Cua Dai), Vietnam',
    'HOABINH':   'Hoa Binh, Tien Giang, Vietnam',
    'TRAVINH':   'Tra Vinh, Vietnam',
    'ANTHUAN':   'An Thuan (Cua Ham Luong), Vietnam',
    'BENTRAI':   'Ben Trai (Cua Co Chien), Vietnam',
    'DAINGAI':   'Dai Ngai (Song Hau), Vietnam',
    'TRANDE':    'Tran De (Song Hau), Vietnam',
    'MYTHANH':   'My Thanh, Vietnam',
    'GANHHAO':   'Ganh Hao, Vietnam',
    'NAMCAN':    'Nam Can (Song Cua Lon), Vietnam',
    'SONGDOC':   'Song Doc, Vietnam',
    'RACHGIA':   'Rach Gia, Vietnam',
    'XEORO':     'Xeo Ro (Song Cai Lon), Vietnam',
    'MYTHO':     'My Tho, Vietnam',
    'MYHOA':     'My Hoa (Ben Tre), Vietnam',
    'CHOLACH':   'Cho Lach, Vietnam',
    'MYTHUAN':   'My Thuan, Vietnam',
    'CANTHO':    'Can Tho, Vietnam',
    'TANAN':     'Tan An (Vam Co Tay), Vietnam',
    'BENLUC':    'Ben Luc (Vam Co Dong), Vietnam',
    'NHABE':     'Nha Be, Vietnam',
    'BIENHOA':   'Bien Hoa (Dong Nai River), Vietnam',
    'THUDAUMOT': 'Thu Dau Mot (Saigon River), Vietnam',
}


def confidence(r2):
    if r2 >= 0.998:
        return 6
    if r2 >= 0.98:
        return 5
    return 4


def fit_station(sheet, name):
    t, v, meta = [], [], {}
    for f in DEFAULT_FILES:
        tt, vv, mm = parse_sheet(f, sheet)
        t += tt; v += vv; meta.update(mm)
    seen = dict(zip(t, v))
    t = sorted(seen)
    v = np.array([seen[ti] for ti in t])
    t = np.array(t)

    coef = utide.solve(t, v, lat=meta['lat'], nodal=True, trend=False,
                       method='ols', conf_int='none', verbose=False,
                       constit=CONSTIT_67)
    rec = utide.reconstruct(t, coef, verbose=False)
    resid = v - rec['h']
    r2 = 1 - float(np.sum(resid ** 2)) / float(np.sum((v - v.mean()) ** 2))
    rms = float(np.sqrt(np.mean(resid ** 2)))

    # LAT ueber 1 Nodalzyklus (19 Jahre, stuendlich) aus der Rekonstruktion
    t19 = np.array([datetime(2026, 1, 1) + timedelta(hours=h)
                    for h in range(19 * 8766)])
    h19 = utide.reconstruct(t19, coef, verbose=False)['h']
    lat_level = float(np.min(h19))

    from utide._ut_constants import ut_constants
    table = ut_constants['const']
    unames = [n.strip() for n in table.name]
    cm = {}
    for i, u in enumerate(coef['name']):
        u = u.strip()
        if u not in unames:
            continue
        xt, _ = find_xtide_match(u, table.freq[unames.index(u)] * 360.0)
        if xt:
            cm[xt] = (float(coef['A'][i]), float(coef['g'][i]) % 360.0)

    z0_state = float(coef['mean'])
    z0_lat = z0_state - lat_level
    n_ana = sum(1 for cn, _ in CONSTITUENTS_175 if cn in cm)
    conf = confidence(r2)
    m2 = cm.get('M2', (0, 0))
    print(f"{sheet:10s} r2={r2:.4f} rms={rms:.3f} M2={m2[0]:.2f} "
          f"Z0_state={z0_state:+.2f} LAT={lat_level:+.2f} Z0_LAT={z0_lat:.2f} "
          f"conf={conf}", file=sys.stderr)

    L = [
        "#", f"# {name}", "# BEGIN HOT COMMENTS", "# country: Vietnam",
        "# source: ICOE/VAWR hourly tide predictions (icoe.org.vn, Bang trieu du bao) with UTide",
        f"# icoe_sheet: {sheet}",
        f"# date_imported: {datetime.now():%Y%m%d}",
        "# datum: LAT (approx.)",
        ("# datum_note: derived LAT=0 from 19y reconstruction; source datum "
         f"He cao do Nha Nuoc (state datum), original Z0={z0_state:+.3f}m, "
         f"shift {-lat_level:+.3f}m"),
        f"# confidence: {conf}",
        f"# utide: pts={len(t)} period={t[0]:%Y-%m-%d}..{t[-1]:%Y-%m-%d} "
        f"r2={r2:.4f} rms={rms:.4f}m const={n_ana}",
        "# !units: meters",
        f"# !longitude: {meta['lon']:.4f}", f"# !latitude: {meta['lat']:.4f}",
        name, '+00:00 :Asia/Ho_Chi_Minh', f"{z0_lat:.4f} meters",
    ]
    for cn, _sp in CONSTITUENTS_175:
        if cn in cm and cm[cn][0] >= 0.00005:
            L.append(f"{cn:15s} {cm[cn][0]:.4f}  {cm[cn][1]:.2f}")
        else:
            L.append("x 0 0")
    return '\n'.join(L)


def main():
    blocks = [fit_station(sheet, name) for sheet, name in STATIONS.items()]
    print('\n'.join(blocks))


if __name__ == '__main__':
    main()
