#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Massen-UTide-Fit fuer internationale NMDIS-Stationen (Luecken + Classic-Upgrades).

Wie fit_nmdis_stations.py, aber:
- Plan = water_levels/CN_nmdis/intl_plan.json (klass GAP/OLD)
- UTC-Offset dynamisch aus timearea (INVERTIERT: '-0800'=UTC+8, '0500'=UTC-5;
  an Charleston/NOAA und Dover/UKHO verifiziert, immer Standardzeit ohne DST)
- Land aus enname-Praefix ('CUBA-SANTIAGO'), Anzeige 'Santiago de Cuba, Cuba'
- XTide-Zeitzone: bei OLD-Upgrades von der nahen Classic-Station geerbt,
  bei GAP aus Laender-Map
- Namenskollision mit Bestand -> Suffix ' (2)'

Aufruf:  python3 py/fit_nmdis_intl.py [--write]
"""
from __future__ import annotations
import glob
import json
import math
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
PLAN = DIR / 'intl_plan.json'
HARM = Path('/home/oliver/harmonics/utide/harmonics_utide_tidetables.txt')
R2_GATE = 0.95
D0, D1 = '2025-07-01', '2026-06-30'

COUNTRY = {
    'CANADA': 'Canada', 'CAROLINE ISLANDS': 'Micronesia', 'CHILE': 'Chile',
    'CUBA': 'Cuba', 'D.P.R.K.': 'North Korea', 'EASTERN ARCHIPELAGO': 'Indonesia',
    'EGYPT': 'Egypt', 'GREENLAND': 'Greenland', 'GUINEA-BISSAU': 'Guinea-Bissau',
    'GUINEA': 'Guinea', 'GUYANA': 'Guyana', 'IRAN': 'Iran', 'JAVA': 'Indonesia',
    'KALIMANTAN': 'Indonesia', 'KURIL ISLANDS': 'Russia', 'KUWAIT': 'Kuwait',
    'MOCAMBIQUE': 'Mozambique', 'MYANMA': 'Myanmar', 'NIGERIA': 'Nigeria',
    'PAKISTAN': 'Pakistan', 'PAPUA NEW GUINEA': 'Papua New Guinea',
    'QATAR': 'Qatar', 'RUSSIA': 'Russia', 'SAO TOME E PRINCIPE': 'Sao Tome and Principe',
    'SAUDI ARABIA': 'Saudi Arabia', 'SIERRA LEONE': 'Sierra Leone',
    'SINGAPORE STRAIT': 'Singapore', 'SRI LANKA': 'Sri Lanka',
    'SUMATERA': 'Indonesia', 'SURINAM': 'Suriname', 'UAE': 'United Arab Emirates',
    'INDIA': 'India',
    'VENEZUELA': 'Venezuela', 'WEST MALAYSIA': 'Malaysia',
}
# Sonderfaelle: code -> kompletter Anzeigename
NAME_FIX = {
    'T316': 'Shatt al Arab (Outer Bar), Iraq',
    'T411': 'Santiago de Cuba, Cuba',
    'T214': 'Ostrov Mamya (Matua), Kuril Islands, Russia',
    'T215': 'Ostrov Paramushir, Kuril Islands, Russia',
    'T248': 'Bandar Victoria (Labuan), Malaysia (2)',
    'T250': 'Sungai Sarawak, Malaysia (2)',
    'T289': 'Dublon Island, Chuuk, Micronesia',
    'T444': 'Danmarks O (Scoresby Sund), Greenland',
    'T445': 'Finsch Islands, Greenland',
    'T446': 'Danmarks Havn, Greenland (2)',
    'T389': 'Port Kem, Russia',
    'T388': 'Yekaterininskaya (Kolskiy Zaliv), Russia',
    'T315': 'Khowr-e Musa Bar, Iran',
    'T321': "Musay'id (Outer Channel Entrance), Qatar",
    'T307': 'Bhavnagar, Gujarat, India',
}
# GAP-Stationen: Laender-Map fuer XTide-TZ; OLD erbt von Classic-Nachbar
TZ_GAP = {
    'India': ':Asia/Kolkata',
    'Cuba': ':America/Havana', 'Greenland': ':America/Nuuk', 'Iran': ':Asia/Tehran',
    'Pakistan': ':Asia/Karachi', 'United Arab Emirates': ':Asia/Dubai',
    'Saudi Arabia': ':Asia/Riyadh', 'Guyana': ':America/Guyana',
    'Venezuela': ':America/Caracas', 'Guinea-Bissau': ':Africa/Bissau',
    'Micronesia': ':Pacific/Chuuk',
}
TZ_FIX = {'T446': ':America/Danmarkshavn', 'T445': ':America/Danmarkshavn',
          'T444': ':America/Scoresbysund'}


def parse_offset(ta):
    """timearea -> UTC-Offset in Stunden (invertierte NMDIS-Konvention)."""
    neg = ta.strip().startswith('-')
    dig = ta.strip().lstrip('+-')
    hh, mm = int(dig[:-2] or 0), int(dig[-2:])
    off = hh + mm / 60.0
    return off if neg else -off


def display_name(st):
    if st['code'] in NAME_FIX:
        return NAME_FIX[st['code']]
    en = re.sub(r'〖[^〗]*〗', ' ', st['enname']).strip()
    pref = None
    for p in sorted(COUNTRY, key=len, reverse=True):
        if en.upper().startswith(p):
            pref = p
            break
    rest = en[len(pref):].lstrip(' -') if pref else en
    rest = re.sub(r'\(', ' (', rest)
    rest = re.sub(r'\s+', ' ', rest).title().strip()
    rest = re.sub(r"(['’])S\b", r"\1s", rest)
    return f'{rest}, {COUNTRY[pref]}' if pref else f'{rest}'


def existing_stations():
    out = []
    for f in glob.glob('/home/oliver/harmonics/**/*.txt', recursive=True):
        if any(x in f for x in ('/help/', 'old_xtide', '/backup/', 'original')):
            continue
        lon = lat = None
        for l in open(f, encoding='iso-8859-1').read().splitlines():
            if l.startswith('# !longitude:'):
                try:
                    lon = float(l.split(':')[1])
                except ValueError:
                    lon = None
            elif l.startswith('# !latitude:'):
                try:
                    lat = float(l.split(':')[1])
                except ValueError:
                    lat = None
            elif lat is not None and lon is not None and l and \
                    not l.startswith(('#', 'x ')) and re.match(r'^[A-Za-z\xc0-\xff]', l):
                out.append((l.strip(), lat, lon, f))
                lat = lon = None
    return out


def classic_tz(st, existing):
    """TZ-String der naechsten Classic-Station (<10km) aus deren Block."""
    best = None
    for nm, la, lo, f in existing:
        if 'classic/' not in f and 'ticon' not in f and 'lavergne' not in f and '2004' not in f:
            continue
        d = math.hypot((la - st['lat']) * 111,
                       (lo - st['lon']) * 111 * math.cos(math.radians(st['lat'])))
        if d < 10 and (best is None or d < best[0]):
            best = (d, nm, f)
    if not best:
        return None
    lines = open(best[2], encoding='iso-8859-1').read().splitlines()
    try:
        i = lines.index(best[1])
    except ValueError:
        return None
    # TZ-Name, nicht die Offset-Doppelpunkte ('-05:00 :America/Iqaluit')
    m = re.search(r'(:[A-Za-z]\S+)', lines[i + 1])
    return m.group(1) if m else None


def load_series(code):
    d = json.loads((DIR / f'{code}_{D0}_{D1}.json').read_text())
    t, v, bench, tas = [], [], None, set()
    for day, rec in sorted(d.items()):
        if not rec:
            continue
        bench = bench or rec.get('benchmark')
        if rec.get('timearea'):
            tas.add(rec['timearea'])
        base = datetime.fromisoformat(day)
        off = timedelta(hours=parse_offset(rec.get('timearea') or '0000'))
        for h, cm in enumerate(rec['hourly_cm']):
            if cm is None:
                continue
            t.append(base + timedelta(hours=h) - off)
            v.append(float(cm) / 100.0)
    return np.array(t), np.array(v), bench, tas


def map_const(coef):
    from utide._ut_constants import ut_constants
    table = ut_constants['const']
    unames = [n.strip() for n in table.name]
    out = {}
    for i, u in enumerate(coef['name']):
        u = u.strip()
        if u not in unames:
            continue
        xt, _ = find_xtide_match(u, table.freq[unames.index(u)] * 360.0)
        if xt:
            out[xt] = (float(coef['A'][i]), float(coef['g'][i]) % 360.0)
    return out


def build_block(name, st, tz, z0, cm, r2, rms, npts, t0, t1, bench_cm):
    country = name.rsplit(',', 1)[-1].strip()
    datum = '# datum: Chart Datum (NMDIS tide table zero)'
    if bench_cm is not None:
        datum += f'\n# datum_note: {bench_cm:.0f}cm below MSL'
    L = [
        "#", f"# {name}", "# BEGIN HOT COMMENTS", f"# country: {country}",
        f"# source: NMDIS hourly tide predictions (mds.nmdis.org.cn, sitecode {st['code']}) with UTide",
        f"# nmdis_site: {st['code']} {re.sub(r'[^ -~]', ' ', st['enname']).strip()}",
        f"# date_imported: {datetime.now():%Y%m%d}",
        datum,
        "# confidence: 6",
        f"# utide: pts={npts} period={t0:%Y-%m-%d}..{t1:%Y-%m-%d} r2={r2:.4f} rms={rms:.4f}m const={sum(1 for cn, _ in CONSTITUENTS_175 if cn in cm)}",
        "# !units: meters", f"# !longitude: {st['lon']:.4f}", f"# !latitude: {st['lat']:.4f}",
        name, f'+00:00 {tz}', f"{z0:.4f} meters",
    ]
    for cn, _sp in CONSTITUENTS_175:
        if cn in cm and cm[cn][0] >= 0.00005:
            L.append(f"{cn:15s} {cm[cn][0]:.4f}  {cm[cn][1]:.2f}")
        else:
            L.append("x 0 0")
    return L


def main():
    write = '--write' in sys.argv
    plan = json.loads(PLAN.read_text())
    existing = existing_stations()
    names_existing = {e[0] for e in existing}
    lines = HARM.read_text(encoding='iso-8859-1').split('\n')
    n_new = n_skip = 0
    for st in plan:
        f = DIR / f"{st['code']}_{D0}_{D1}.json"
        if not f.exists():
            print(f"  {st['code']} {st['enname'][:30]:30s} KEINE DATEI - skip"); n_skip += 1
            continue
        t, v, bench, tas = load_series(st['code'])
        if len(t) < 8000:
            print(f"  {st['code']} {st['enname'][:30]:30s} nur {len(t)} pts - skip"); n_skip += 1
            continue
        if len(tas) > 1:
            print(f"  {st['code']} {st['enname'][:30]:30s} timearea wechselt {tas} - skip"); n_skip += 1
            continue
        name = display_name(st)
        if name in names_existing or any(l == name for l in lines):
            name += ' (2)'
        tz = TZ_FIX.get(st['code']) or (classic_tz(st, existing) if st['klass'] == 'OLD' else None) \
            or TZ_GAP.get(name.rsplit(',', 1)[-1].strip())
        if not tz:
            print(f"  {st['code']} {name[:40]:40s} KEINE TZ - skip"); n_skip += 1
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
        m2, k1 = cm.get('M2', (0, 0)), cm.get('K1', (0, 0))
        flag = ''
        if r2 < R2_GATE:
            flag = f' !! R2<{R2_GATE} - SKIP'; n_skip += 1
        elif dz is not None and abs(dz) > 0.08:
            flag = f' ?? Z0-Benchmark-Delta {dz:+.2f}m'
        ta = next(iter(tas)) if tas else '?'
        print(f"  {st['code']} {name[:40]:40s} ta={ta:5s} {tz:24s} r2={r2:.4f} rms={rms:.3f}"
              f" Z0={z0:.2f} (bench {bench_cm or '?'}cm) M2={m2[0]:.2f}@{m2[1]:.0f} K1={k1[0]:.2f}@{k1[1]:.0f}{flag}")
        if 'SKIP' in flag:
            continue
        blk = build_block(name, st, tz, z0, cm, r2, rms, len(t), t[0], t[-1], bench_cm)
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
