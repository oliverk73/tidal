#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Massen-UTide-Fit fuer NMDIS-China-Stationen (nach batch_download_nmdis.py).

Wie fit_qinhuangdao_nmdis.py, aber generisch ueber batch_plan.json:
stuendliche NMDIS-Werte (cm ueber Tidenull, Beijing UTC+8) -> UTide ->
neue Bloecke in harmonics_utide_tidetables.txt (UTide TC).

Stationsnamen: Title-Case aus enname (Typesetting-Reste bereinigt),
Provinz korrigiert (NMDIS nennt Guangdong faelschlich "Guangzhou").
Z0-Check gegen benchmark-Text ("在平均海面下NNcm"), R2-Gate 0.95.

Aufruf:  python3 py/fit_nmdis_stations.py --prios P1 [--write]
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

DIR = Path('/home/oliver/water_levels/CN_nmdis')
PLAN = DIR / 'batch_plan.json'
HARM = Path('/home/oliver/harmonics/utide/harmonics_utide_tidetables.txt')
UTC_OFF = timedelta(hours=8)
R2_GATE = 0.95
D0, D1 = '2025-07-01', '2026-06-30'

PROVINCE_FIX = {'Guangzhou': 'Guangdong'}
NAME_FIX = {
    'HUANGPUGONGYUAN': 'Huangpu Gongyuan',
    'HAIMEN(GUANGDONG)': 'Haimen',
    'HUANGHUAGANG(YIQIMEIMATOU)': 'Huanghua Gang',
    'MAOSHIHUA(SHUIDONGGANG)': 'Shuidong Gang (Maoshihua)',
}


def display_name(st):
    en = re.sub(r'〖[^〗]*〗', ' ', st['enname']).strip()
    en = NAME_FIX.get(en.upper().replace(' ', ''), None) or en
    en = re.sub(r'\(', ' (', en)
    en = re.sub(r'\s+', ' ', en).title().strip()
    prov = PROVINCE_FIX.get(st['province'], st['province'])
    return f'{en}, {prov}, China'


def load_series(code):
    d = json.loads((DIR / f'{code}_{D0}_{D1}.json').read_text())
    t, v, bench, ta = [], [], None, None
    for day, rec in sorted(d.items()):
        if not rec:
            continue
        bench = bench or rec.get('benchmark')
        ta = ta or rec.get('timearea')
        base = datetime.fromisoformat(day)
        for h, cm in enumerate(rec['hourly_cm']):
            if cm is None:
                continue
            t.append(base + timedelta(hours=h) - UTC_OFF)
            v.append(float(cm) / 100.0)
    return np.array(t), np.array(v), bench, ta


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


def build_block(name, st, z0, cm, r2, rms, npts, t0, t1, bench_cm):
    n_ana = sum(1 for cn, _ in CONSTITUENTS_175 if cn in cm)
    # TCD hat ein hartes Limit an unterschiedlichen datum-Strings (~64,
    # DEFAULT_DATUM_BITS) — Benchmark-Detail daher in eigene Kommentarzeile!
    datum = '# datum: Chart Datum (China, theoretical lowest tide)'
    if bench_cm is not None:
        datum += f'\n# datum_note: {bench_cm:.0f}cm below MSL'
    L = [
        "#", f"# {name}", "# BEGIN HOT COMMENTS", "# country: China",
        f"# source: NMDIS hourly tide predictions (mds.nmdis.org.cn, sitecode {st['code']}) with UTide",
        f"# nmdis_site: {st['code']} {re.sub(r'[^ -~]', ' ', st['enname']).strip()}",
        f"# date_imported: {datetime.now():%Y%m%d}",
        datum,
        "# confidence: 7",
        f"# utide: pts={npts} period={t0:%Y-%m-%d}..{t1:%Y-%m-%d} r2={r2:.4f} rms={rms:.4f}m const={n_ana}",
        "# !units: meters", f"# !longitude: {st['lon']:.4f}", f"# !latitude: {st['lat']:.4f}",
        name, '+00:00 :Asia/Shanghai', f"{z0:.4f} meters",
    ]
    for cn, _sp in CONSTITUENTS_175:
        if cn in cm and cm[cn][0] >= 0.00005:
            L.append(f"{cn:15s} {cm[cn][0]:.4f}  {cm[cn][1]:.2f}")
        else:
            L.append("x 0 0")
    return L


def main():
    write = '--write' in sys.argv
    prios = ('P1',)
    if '--prios' in sys.argv:
        prios = tuple(sys.argv[sys.argv.index('--prios') + 1].split(','))
    plan = [s for s in json.loads(PLAN.read_text()) if s['prio'] in prios]
    lines = HARM.read_text(encoding='iso-8859-1').split('\n')
    n_new = n_skip = 0
    for st in plan:
        f = DIR / f"{st['code']}_{D0}_{D1}.json"
        if not f.exists():
            print(f"  {st['code']} {st['enname'][:24]:24s} KEINE DATEI - skip"); n_skip += 1
            continue
        t, v, bench, ta = load_series(st['code'])
        if len(t) < 8000:
            print(f"  {st['code']} {st['enname'][:24]:24s} nur {len(t)} pts - skip"); n_skip += 1
            continue
        assert ta == '-0800', f"{st['code']}: timearea {ta}"
        name = display_name(st)
        if any(l == name for l in lines):
            print(f"  {st['code']} {name[:40]:40s} EXISTIERT SCHON - skip"); n_skip += 1
            continue
        coef = utide.solve(t, v, lat=st['lat'], nodal=True, trend=False, method='ols',
                           conf_int='none', verbose=False, constit=CONSTIT_67)
        rec = utide.reconstruct(t, coef, verbose=False)
        resid = v - rec['h']
        r2 = 1 - float(np.sum(resid ** 2)) / float(np.sum((v - v.mean()) ** 2))
        rms = float(np.sqrt(np.mean(resid ** 2)))
        cm = map_const(coef)
        z0 = float(coef['mean'])
        mb = re.search(r'(\d+)\s*cm', bench or '')
        bench_cm = float(mb.group(1)) if mb else None
        dz = z0 - bench_cm / 100.0 if bench_cm is not None else None
        m2 = cm.get('M2', (0, 0))
        k1 = cm.get('K1', (0, 0))
        flag = ''
        if r2 < R2_GATE:
            flag = f' !! R2<{R2_GATE} - SKIP'; n_skip += 1
        elif dz is not None and abs(dz) > 0.08:
            flag = f' ?? Z0-Benchmark-Delta {dz:+.2f}m'
        print(f"  {st['code']} {name[:38]:38s} r2={r2:.4f} rms={rms:.3f} Z0={z0:.2f}"
              f" (bench {bench_cm or '?'}cm) M2={m2[0]:.2f}@{m2[1]:.0f} K1={k1[0]:.2f}@{k1[1]:.0f}{flag}")
        if 'SKIP' in flag:
            continue
        blk = build_block(name, st, z0, cm, r2, rms, len(t), t[0], t[-1], bench_cm)
        end = len(lines)
        while end > 0 and lines[end - 1].strip() == '':
            end -= 1
        lines = lines[:end] + blk + lines[end:]
        n_new += 1
    n_st = sum(1 for l in lines if l == '# BEGIN HOT COMMENTS')
    print(f'\nNeu: {n_new}, uebersprungen: {n_skip}, Stationszahl: {n_st}')
    if write:
        # erst encodieren (wirft VOR Dateizugriff), dann atomar via temp+rename —
        # write_text leerte 2026-06-10 die Datei bei UnicodeEncodeError mittendrin
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
