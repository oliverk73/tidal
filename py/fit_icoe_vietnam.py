#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ICOE-Vietnam-XLSX (Bảng triều dự báo) -> UTide -> Harmonics-Block.

Quelle: Viện Kỹ thuật Biển (ICOE/VAWR), jaehrliche XLSX mit 34 Stationen,
24 Stundenwerte/Tag in cm. Layout je Sheet: Headerblock (Hệ cao độ,
Koordinaten, Múi giờ -07), dann Monatsbloecke ('Tháng' N 'Năm' Y) mit
Tageszeilen (Spalte 0 Solartag oder 'CN', Spalten 2-25 = Stunde 0-23).

ACHTUNG Datum-Falle (Memory project_vietnam_sources): nur wenige Stationen
sind Kartennull (Hải đồ) — Flussstationen sind Staatshoehensystem + Abfluss.
Dieses Skript fittet nur die uebergebenen Sheets und schreibt KEINE Datei,
sondern gibt den Block auf stdout aus (Insert von Hand/Folgeskript).

Usage: python3 py/fit_icoe_vietnam.py SHEET NAME [--files f1.xlsx f2.xlsx]
Beispiel: python3 py/fit_icoe_vietnam.py CAUDA 'Nha Trang (Cau Da), Vietnam'
"""
from __future__ import annotations
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import openpyxl
import utide

sys.path.insert(0, '/home/oliver/py')
sys.path.insert(0, '/home/oliver/batch')
from generate_germany_harmonics_175 import CONSTITUENTS_175, find_xtide_match
from batch_utide_uk_tidetimes import CONSTIT_67

DEFAULT_FILES = ['/tmp/icoe_2025_h1.xlsx', '/tmp/icoe_2026_q1.xlsx']
UTC_OFF = timedelta(hours=7)


def parse_sheet(path, sheet):
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    ws = wb[sheet]
    meta = {}
    month = year = None
    day = 0
    t, v = [], []
    for row in ws.iter_rows(min_row=1, max_col=30, values_only=True):
        cells = [x for x in row if x not in (None, '')]
        txt = ' '.join(str(x) for x in cells)
        if 'Hệ cao độ' in txt:
            vals = [str(x).strip() for x in row if x not in (None, '')]
            i = next(i for i, x in enumerate(vals) if 'Hệ cao độ' in x)
            if i + 1 < len(vals):
                meta['datum'] = vals[i + 1]
        m = re.search(r"(\d+)o\s*(\d+)'\s*([\d.]*)\s*([NSEW])", txt)
        if m:
            deg = int(m.group(1)) + int(m.group(2)) / 60 + (float(m.group(3) or 0)) / 3600
            if m.group(4) in 'NS':
                meta['lat'] = deg * (1 if m.group(4) == 'N' else -1)
            else:
                meta['lon'] = deg * (1 if m.group(4) == 'E' else -1)
        if 'Tháng' in txt:
            nums = [x for x in cells if isinstance(x, (int, float))]
            if len(nums) >= 2:
                month, year = int(nums[0]), int(nums[1])
                day = 0
            continue
        # Tageszeile: Spalten 2..25 numerisch; Stunden-Headerzeile (0,1,..,23)
        # und 'Ngày/Dương'-Zeilen ueberspringen, Tag aus Spalte 0 (CN=Sonntag)
        hrs = row[2:26]
        if month and sum(1 for x in hrs if isinstance(x, (int, float))) == 24:
            if hrs[:6] == (0, 1, 2, 3, 4, 5):
                continue
            day = int(row[0]) if isinstance(row[0], (int, float)) else day + 1
            base = datetime(year, month, day)
            for h, cm in enumerate(hrs):
                t.append(base + timedelta(hours=h) - UTC_OFF)
                v.append(float(cm) / 100.0)
    return t, v, meta


def main():
    sheet = sys.argv[1]
    name = sys.argv[2]
    files = DEFAULT_FILES
    if '--files' in sys.argv:
        files = sys.argv[sys.argv.index('--files') + 1:]
    t, v, meta = [], [], {}
    for f in files:
        tt, vv, mm = parse_sheet(f, sheet)
        # Ueberlapp vermeiden (gleiche Tage in zwei Dateien): dedup nach Zeit
        t += tt; v += vv; meta.update(mm)
        print(f'# {f}: {len(tt)} Punkte', file=sys.stderr)
    seen = {}
    for ti, vi in zip(t, v):
        seen[ti] = vi
    t = sorted(seen)
    v = [seen[ti] for ti in t]
    t = np.array(t); v = np.array(v)
    print(f'# gesamt {len(t)} Punkte {t[0]}..{t[-1]} | meta={meta}', file=sys.stderr)

    coef = utide.solve(t, v, lat=meta['lat'], nodal=True, trend=False,
                       method='ols', conf_int='none', verbose=False,
                       constit=CONSTIT_67)
    rec = utide.reconstruct(t, coef, verbose=False)
    resid = v - rec['h']
    r2 = 1 - float(np.sum(resid ** 2)) / float(np.sum((v - v.mean()) ** 2))
    rms = float(np.sqrt(np.mean(resid ** 2)))

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
    z0 = float(coef['mean'])
    m2, k1, o1 = (cm.get(c, (0, 0)) for c in ('M2', 'K1', 'O1'))
    print(f'# r2={r2:.4f} rms={rms:.4f} Z0={z0:.2f} M2={m2[0]:.2f}@{m2[1]:.0f} '
          f'K1={k1[0]:.2f}@{k1[1]:.0f} O1={o1[0]:.2f}@{o1[1]:.0f}', file=sys.stderr)

    n_ana = sum(1 for cn, _ in CONSTITUENTS_175 if cn in cm)
    datum = meta.get('datum', '?')
    L = [
        "#", f"# {name}", "# BEGIN HOT COMMENTS", "# country: Vietnam",
        "# source: ICOE/VAWR hourly tide predictions (icoe.org.vn, Bang trieu du bao) with UTide",
        f"# icoe_sheet: {sheet}",
        f"# date_imported: {datetime.now():%Y%m%d}",
        f"# datum: {'chart datum (Kartennull der amtlichen Tidetafel)' if 'đồ' in datum or 'do' in datum.lower() else datum + ' (PRUEFEN: nicht Kartennull!)'}",
        "# confidence: 6",
        f"# utide: pts={len(t)} period={t[0]:%Y-%m-%d}..{t[-1]:%Y-%m-%d} r2={r2:.4f} rms={rms:.4f}m const={n_ana}",
        "# !units: meters",
        f"# !longitude: {meta['lon']:.4f}", f"# !latitude: {meta['lat']:.4f}",
        name, '+00:00 :Asia/Ho_Chi_Minh', f"{z0:.4f} meters",
    ]
    for cn, _sp in CONSTITUENTS_175:
        if cn in cm and cm[cn][0] >= 0.00005:
            L.append(f"{cn:15s} {cm[cn][0]:.4f}  {cm[cn][1]:.2f}")
        else:
            L.append("x 0 0")
    print('\n'.join(L))


if __name__ == '__main__':
    main()
