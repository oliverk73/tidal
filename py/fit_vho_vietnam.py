#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""UTide-Fit fuer die VHO-Vietnam-Stationen (nach download_vho_vietnam.py).

Stuendliche amtliche Tidetafel-Werte (m ueber Kartennull, Ortszeit UTC+7,
thuydacvietnam.org.vn / Vietnam Hydrographic Office Navy) -> UTide ->
neue Bloecke in harmonics_utide_tidetables.txt (UTide TC).

Konventionen wie fit_nmdis_stations.py: Zeiten -> UTC, Greenwich-Phasen,
Meridian +00:00, R2-Gate 0.95, ISO-8859-1-sicheres atomares Schreiben.
ASCII-Namen (vietnamesische Diakritika passen nicht in ISO-8859-1).

Skips: Quy Nhon + Vung Tau (bessere UHSLC-Messfits in observations.txt
vorhanden); Hon Dau wird gefittet, aber nur mit --include-hondau
geschrieben (UHSLC-Bestandsfit 1959-1995, Vergleich noetig).

Aufruf:  python3 py/fit_vho_vietnam.py [--write] [--include-hondau]
"""
from __future__ import annotations
import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import utide

sys.path.insert(0, '/home/oliver/py')
sys.path.insert(0, '/home/oliver/batch')
from generate_germany_harmonics_175 import CONSTITUENTS_175, find_xtide_match
from batch_utide_uk_tidetimes import CONSTIT_67

DIR = Path('/home/oliver/water_levels/VN_vho')
HARM = Path('/home/oliver/harmonics/utide/harmonics_utide_tidetables.txt')
UTC_OFF = timedelta(hours=7)
R2_GATE = 0.95
SPAN = '2022-01-01_2026-06-30'

# slug -> (Anzeigename, Land, tz-Label)
STATIONS = {
    'hong-gai': ('Hong Gai (Ha Long)', 'Vietnam', 'Asia/Ho_Chi_Minh'),
    'hon-dau': ('Hon Dau', 'Vietnam', 'Asia/Ho_Chi_Minh'),
    'cua-hoi': ('Cua Hoi', 'Vietnam', 'Asia/Ho_Chi_Minh'),
    'cua-gianh': ('Cua Gianh', 'Vietnam', 'Asia/Ho_Chi_Minh'),
    'cua-viet': ('Cua Viet', 'Vietnam', 'Asia/Ho_Chi_Minh'),
    'da-nang': ('Da Nang', 'Vietnam', 'Asia/Ho_Chi_Minh'),
    # 'quy-nhon': UHSLC-Messfit "Qui Nhon" vorhanden -> skip
    'cam-ranh': ('Cam Ranh', 'Vietnam', 'Asia/Ho_Chi_Minh'),  # lon nachtraeglich 109.2333->109.165 (Minutenrundung lag auf der Halbinsel, Tafel gilt fuer die Bucht)
    # 'vung-tau': UHSLC-Messfit vorhanden -> skip
    'sai-gon': ('Sai Gon (Ho Chi Minh City)', 'Vietnam', 'Asia/Ho_Chi_Minh'),  # lon nachtraeglich 106.700->106.7075 (Minutenrundung lag auf Land)
    'ha-tien': ('Ha Tien', 'Vietnam', 'Asia/Ho_Chi_Minh'),
    'phu-quoc': ('Phu Quoc (An Thoi)', 'Vietnam', 'Asia/Ho_Chi_Minh'),
    'cong-pong-xom': ('Kampong Som (Sihanoukville)', 'Cambodia', 'Asia/Phnom_Penh'),
    'hoang-sa': ('Hoang Sa (Paracel Islands)', 'Vietnam', 'Asia/Ho_Chi_Minh'),
    'song-tu-tay': ('Song Tu Tay (Southwest Cay, Spratly Islands)', 'Vietnam', 'Asia/Ho_Chi_Minh'),
    'nam-yet': ('Nam Yet (Namyit Island, Spratly Islands)', 'Vietnam', 'Asia/Ho_Chi_Minh'),
    'truong-sa': ('Truong Sa (Spratly Island)', 'Vietnam', 'Asia/Ho_Chi_Minh'),
}


# Defekte Quell-Segmente (per-Jahr-Fits 2026-06-11):
# - 2026-Seiten an vielen Stationen inkonsistent (Z0/std springen) -> global raus
# - Da Nang 2024: Amplituden ~0, Z0 0.08 statt 0.95 (kaputtes Jahr)
# - Hong Gai 2024: O1/M2-Phasen ~165 deg verdreht (fremde/verdrehte Tabellen)
# - Cua Gianh 2022: O1/M2-Phasen ~100 deg verdreht, 2023-2025 konsistent
CUTOFF = '2026-01-01'
EXCLUDE_YEARS = {'da-nang': {2024}, 'hong-gai': {2024}, 'cua-gianh': {2022}}


def load_series(slug):
    d = json.loads((DIR / f'{slug}_{SPAN}.json').read_text())
    meta = d.get('_meta', {})
    excl = EXCLUDE_YEARS.get(slug, set())
    t, v = [], []
    for day, rec in sorted(d.items()):
        if day.startswith('_') or not rec or day >= CUTOFF:
            continue
        if int(day[:4]) in excl:
            continue
        base = datetime.fromisoformat(day)
        for h, m in enumerate(rec['hourly_m']):
            if m is None:
                continue
            t.append(base + timedelta(hours=h) - UTC_OFF)
            v.append(float(m))
    return np.array(t), np.array(v), meta


def map_const(coef):
    from utide._ut_constants import ut_constants
    table = ut_constants['const']
    unames = [n.strip() for n in table.name]
    out = {}
    for i, u in enumerate(coef['name']):
        u = u.strip()
        if u not in unames:
            continue
        speed = table.freq[unames.index(u)] * 360.0
        xt, _ = find_xtide_match(u, speed)
        if xt:
            out[xt] = (float(coef['A'][i]), float(coef['g'][i]) % 360.0)
    return out


def build_block(name, country, tzlabel, slug, lat, lon, z0, cm, r2, rms,
                npts, t0, t1):
    n_ana = sum(1 for cn, _ in CONSTITUENTS_175 if cn in cm)
    L = [
        "#", f"# {name}", "# BEGIN HOT COMMENTS", f"# country: {country}",
        "# source: VHO Navy hourly tide predictions (thuydacvietnam.org.vn) with UTide",
        f"# vho_slug: {slug}",
        f"# date_imported: {datetime.now():%Y%m%d}",
        "# datum: chart datum (Kartennull der amtlichen Tidetafel)",
        "# confidence: 7",
        f"# utide: pts={npts} period={t0:%Y-%m-%d}..{t1:%Y-%m-%d} r2={r2:.4f} rms={rms:.4f}m const={n_ana}",
        "# !units: meters", f"# !longitude: {lon:.4f}", f"# !latitude: {lat:.4f}",
        name, f'+00:00 :{tzlabel}', f"{z0:.4f} meters",
    ]
    for cn, _sp in CONSTITUENTS_175:
        if cn in cm and cm[cn][0] >= 0.00005:
            L.append(f"{cn:15s} {cm[cn][0]:.4f}  {cm[cn][1]:.2f}")
        else:
            L.append("x 0 0")
    return L


def main():
    write = '--write' in sys.argv
    include_hondau = '--include-hondau' in sys.argv
    lines = HARM.read_text(encoding='iso-8859-1').split('\n')
    n_new = n_skip = 0
    for slug, (base_name, country, tzlabel) in STATIONS.items():
        if slug == 'hon-dau' and not include_hondau:
            print(f"  {slug:14s} Hon Dau: nur Vergleich (--include-hondau zum Schreiben)")
        t, v, meta = load_series(slug)
        if len(t) < 8000:
            print(f"  {slug:14s} nur {len(t)} pts - skip"); n_skip += 1
            continue
        name = f'{base_name}, {country}'
        lat, lon = meta.get('lat'), meta.get('lon')
        if lat is None:
            print(f"  {slug:14s} KEINE KOORDINATEN - skip"); n_skip += 1
            continue
        if any(l == name for l in lines):
            print(f"  {slug:14s} {name[:38]:38s} EXISTIERT SCHON - skip"); n_skip += 1
            continue
        coef = utide.solve(t, v, lat=lat, nodal=True, trend=False, method='ols',
                           conf_int='none', verbose=False, constit=CONSTIT_67)
        rec = utide.reconstruct(t, coef, verbose=False)
        resid = v - rec['h']
        r2 = 1 - float(np.sum(resid ** 2)) / float(np.sum((v - v.mean()) ** 2))
        rms = float(np.sqrt(np.mean(resid ** 2)))
        cm = map_const(coef)
        z0 = float(coef['mean'])
        m2 = cm.get('M2', (0, 0))
        k1 = cm.get('K1', (0, 0))
        o1 = cm.get('O1', (0, 0))
        flag = ''
        if r2 < R2_GATE:
            flag = f' !! R2<{R2_GATE} - SKIP'
        print(f"  {slug:14s} {name[:38]:38s} lat={lat:.3f} lon={lon:.3f} "
              f"pts={len(t)} r2={r2:.4f} rms={rms:.3f} Z0={z0:.2f} "
              f"M2={m2[0]:.2f}@{m2[1]:.0f} K1={k1[0]:.2f}@{k1[1]:.0f} O1={o1[0]:.2f}@{o1[1]:.0f}{flag}")
        if 'SKIP' in flag:
            n_skip += 1
            continue
        if slug == 'hon-dau' and not include_hondau:
            continue
        blk = build_block(name, country, tzlabel, slug, lat, lon, z0, cm,
                          r2, rms, len(t), t[0], t[-1])
        end = len(lines)
        while end > 0 and lines[end - 1].strip() == '':
            end -= 1
        lines = lines[:end] + blk + lines[end:]
        n_new += 1
    n_st = sum(1 for l in lines if l == '# BEGIN HOT COMMENTS')
    print(f'\nNeu: {n_new}, uebersprungen: {n_skip}, Stationszahl: {n_st}')
    if write:
        data = '\n'.join(lines).encode('iso-8859-1')
        tmp = HARM.with_suffix('.txt.tmp')
        tmp.write_bytes(data)
        import os
        os.replace(tmp, HARM)
        print(f'Geschrieben: {HARM}')
    else:
        print('(Dry-run — --write zum Schreiben.)')


if __name__ == '__main__':
    main()
