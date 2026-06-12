#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Survey-of-India-Monats-Tidetafeln (PDF, 2-Spalten-Tageslayout) -> UTide-Block.

Quelle: surveyofindia.gov.in /pages/tidal, monatliche ZIPs (Wayback + live) in
water_levels/IN_soi/months/<zip>/<MONAT JAHR>/<STATION>.pdf. Je PDF 1 Seite,
Kopf 'TIME ZONE -0530', zwei Tagesspalten (1-15 | 16-31), je Tag 3-5 Zeilen
'HHMM  H.HH' (Zeit lokal, Hoehe m ueber Kartennull). Zeichenweise gerendert ->
Parsen ueber page.chars mit Zeilen-Clustering und x-Baendern um die beiden
'TIME'-Header.

Usage:
  python3 py/fit_soi_tide_pdf.py --list                      # Stationsdateien zaehlen
  python3 py/fit_soi_tide_pdf.py STATION 'Name, Region, Land' LAT LON CONF
STATION = Dateiname ohne .pdf (case-insensitiv, z.B. KANDLA).
"""
from __future__ import annotations
import glob
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pdfplumber
import utide

sys.path.insert(0, '/home/oliver/py')
sys.path.insert(0, '/home/oliver/batch')
from generate_germany_harmonics_175 import CONSTITUENTS_175, find_xtide_match
from batch_utide_uk_tidetimes import CONSTIT_67

MONTHS_DIR = '/home/oliver/water_levels/IN_soi/months'
MONTH_NUM = {n: i + 1 for i, n in enumerate(
    ['JANUARY', 'FEBRUARY', 'MARCH', 'APRIL', 'MAY', 'JUNE', 'JULY',
     'AUGUST', 'SEPTEMBER', 'OCTOBER', 'NOVEMBER', 'DECEMBER'])}


def parse_page(page):
    """-> (year, month, tz_offset_hours, [(datetime_utc, height_m), ...])

    Daten ~6.5-7.6pt ArialMT; Tagesnummern fett >9pt, teils mit unsichtbaren
    horizontalen Wiederholungen; Kopf teils gesperrt gesetzt -> Kopf ueber
    verdichteten Gesamttext, Spaltenanker aus den Zeit-Token-x-Clustern.
    """
    chars = {}
    for c in page.chars:
        if not c['text'].strip():
            continue
        key = (round(c['x0'], 1), round(c['top'], 1))
        chars[key] = c
    chars = sorted(chars.values(), key=lambda c: (round(c['top'], 1), c['x0']))
    # Tokens: zusammenhaengende Zeichen (gleiche Zeile ±1.5px, x-Luecke < 2.8px)
    toks = []  # [text, x0, x1, top, size]
    for c in chars:
        merged = False
        for t in reversed(toks[-12:]):
            if abs(c['top'] - t[3]) < 1.5 and -0.5 <= c['x0'] - t[2] < 2.8 \
                    and abs(c['size'] - t[4]) < 2.0:
                t[0] += c['text']
                t[2] = c['x1']
                merged = True
                break
        if not merged:
            toks.append([c['text'], c['x0'], c['x1'], c['top'], c['size']])

    squash = ''.join(t[0] for t in toks)
    mz = re.search(r'TIMEZONE(-?)(\d{2})(\d{2})', squash)
    if not mz:
        raise ValueError('TIME ZONE fehlt')
    sign = 1 if mz.group(1) == '-' else -1  # invertierte Konvention wie NMDIS
    tzoff = sign * (int(mz.group(2)) + int(mz.group(3)) / 60.0)
    my = re.search(r'YEAR(\d{4})', squash)
    if not my:
        raise ValueError('YEAR fehlt')
    year = int(my.group(1))
    # Monat steht NACH der YEAR-Zeile (Titel kann Monatsnamen enthalten: MAYapur!)
    tail = squash.upper()[my.end():my.end() + 200]
    month = None
    best = len(tail) + 1
    for name, num in MONTH_NUM.items():
        i = tail.find(name)
        if 0 <= i < best:
            best = i
            month = num
    if not month:
        raise ValueError('Monat fehlt')

    def time_ht(t):
        """-> (hh, mi, ht|None) falls Token Zeit (+evtl. angeklebte Hoehe)."""
        if t[4] >= 9:
            return None
        m = re.fullmatch(r'(\d{2})(\d{2})(-?\d{1,2}[.,]\d{1,2})?', t[0])
        if not m:
            return None
        hh, mi = int(m.group(1)), int(m.group(2))
        if hh > 23 or mi > 59:
            return None
        ht = float(m.group(3).replace(',', '.')) if m.group(3) else None
        return hh, mi, ht

    def is_time(t):
        return time_ht(t) is not None

    times = [t for t in toks if is_time(t)]
    if len(times) < 30:
        raise ValueError(f'nur {len(times)} Zeit-Tokens')
    # Spaltenanker: x0 der Zeiten clustern, die 2 groessten Cluster
    xs = sorted(t[1] for t in times)
    clusters = []
    for x in xs:
        if clusters and x - clusters[-1][-1] < 12:
            clusters[-1].append(x)
        else:
            clusters.append([x])
    clusters.sort(key=len, reverse=True)
    if len(clusters) < 2:
        raise ValueError('Zeitspalten-Cluster < 2')
    anchors = sorted(sum(c) / len(c) for c in clusters[:2])
    mid = (anchors[0] + anchors[1]) / 2
    y_lo = min(t[3] for t in times) - 5
    y_hi = max(t[3] for t in times) + 5

    events = []
    for k, ax in enumerate(anchors):
        x_lo = 0 if k == 0 else mid
        x_hi = mid if k == 0 else 10 ** 9
        band = [t for t in toks if x_lo <= t[1] < x_hi and y_lo <= t[3] <= y_hi]
        # Eventzeilen des Bandes -> Bloecke ueber y-Luecken; Tage sequentiell
        # (Band 0 = 1..15, Band 1 = 16..Monatsende). Fette Tagesnummern nur
        # als Pin-Verifikation (PDF rendert sie mehrfach versetzt/lueckenhaft).
        rows = []
        for t in sorted((t for t in band if is_time(t) and abs(t[1] - ax) <= 15),
                        key=lambda t: t[3]):
            if rows and t[3] - rows[-1][0] < 2.0:
                rows[-1][1].append(t)
            else:
                rows.append([t[3], [t]])
        if len(rows) < 8:
            continue
        gaps = sorted(b[0] - a[0] for a, b in zip(rows, rows[1:]))
        pitch = gaps[len(gaps) // 4]  # unteres Quartil = Zeilenabstand im Block
        blocks = [[rows[0]]]
        for prev, cur in zip(rows, rows[1:]):
            if cur[0] - prev[0] > pitch * 1.45:
                blocks.append([])
            blocks[-1].append(cur)
        day0 = 1 if k == 0 else 16
        # Pin-Verifikation gegen fette Tagesnummern
        digs = [t for t in band if t[4] > 9 and re.fullmatch(r'\d{1,2}', t[0])
                and t[1] < ax - 3
                and (1 if k == 0 else 16) <= int(t[0]) <= (15 if k == 0 else 31)]
        ok = bad = 0
        for t in digs:
            for bi, blk in enumerate(blocks):
                if blk[0][0] - 6 <= t[3] <= blk[-1][0] + 6:
                    if int(t[0]) == day0 + bi:
                        ok += 1
                    else:
                        bad += 1
                    break
        if bad > max(2, ok * 0.2):
            print(f'# WARNUNG Band {k}: Tag-Pins {ok} ok / {bad} falsch '
                  f'({len(blocks)} Bloecke)', file=sys.stderr)
        for bi, blk in enumerate(blocks):
            d = day0 + bi
            if d > 31:
                continue
            for top, ts in blk:
                for t in ts:
                    hh, mi, ht = time_ht(t)
                    if ht is None:
                        hts = [v for v in band
                               if v[4] < 9
                               and re.fullmatch(r'-?\d{1,2}[.,]\d{1,2}', v[0])
                               and 0 < v[1] - t[2] < 40 and abs(v[3] - t[3]) < 2.0]
                        if not hts:
                            continue
                        ht = float(hts[0][0].replace(',', '.'))
                    try:
                        dt = datetime(year, month, d, hh, mi) - timedelta(hours=tzoff)
                        events.append((dt, ht))
                    except ValueError:
                        pass
    return year, month, tzoff, events


def collect_events(station):
    """station: pipe-getrennte Alias-Alternativen, z.B. 'KANDLA|DEENDAYAL'."""
    events = []
    months_seen = set()
    pats = [re.compile(re.escape(a.strip()).replace(r'\ ', r'[ _-]?'), re.I)
            for a in station.split('|')]
    for pdf_path in sorted(glob.glob(MONTHS_DIR + '/**/*.pdf', recursive=True)) + \
            sorted(glob.glob(MONTHS_DIR + '/**/*.PDF', recursive=True)):
        stem = Path(pdf_path).stem.upper()
        if not any(p.search(stem) for p in pats):
            continue
        try:
            with pdfplumber.open(pdf_path) as pdf:
                y, m, tz, ev = parse_page(pdf.pages[0])
        except Exception as e:
            print(f'# FEHLER {pdf_path}: {e}', file=sys.stderr)
            continue
        if (y, m) in months_seen:
            continue
        months_seen.add((y, m))
        print(f'# {y}-{m:02d}: {len(ev)} Events (TZ {tz:+.1f}) {Path(pdf_path).name}',
              file=sys.stderr, flush=True)
        events += ev
    events.sort(key=lambda e: e[0])
    return [e for i, e in enumerate(events) if i == 0 or e[0] > events[i - 1][0]]


def fit(events, name, lat, lon, conf, tzname):
    dts, lv = [], []
    for (t0, v0), (t1, v1) in zip(events, events[1:]):
        gap = (t1 - t0).total_seconds() / 3600.0
        if not (2.0 < gap < 10.5) or abs(v1 - v0) < 0.3:
            continue
        n = max(2, int(gap * 4))
        for i in range(n + 1):
            f = i / n
            dts.append(t0 + (t1 - t0) * f)
            lv.append((v0 + v1) / 2 + (v0 - v1) / 2 * np.cos(np.pi * f))
    dts, lv = np.array(dts), np.array(lv)
    kw = dict(lat=lat, nodal=True, trend=False, method='ols', conf_int='none',
              verbose=False, constit=CONSTIT_67)
    coef = utide.solve(dts, lv, **kw)
    resid = lv - utide.reconstruct(dts, coef, verbose=False)['h']
    keep = np.abs(resid) < 0.5
    coef = utide.solve(dts[keep], lv[keep], **kw)
    rec = utide.reconstruct(dts[keep], coef, verbose=False)
    resid = lv[keep] - rec['h']
    r2 = 1 - float(np.sum(resid ** 2)) / float(np.sum((lv[keep] - lv[keep].mean()) ** 2))
    rms = float(np.sqrt(np.mean(resid ** 2)))
    print(f'# r2={r2:.4f} rms={rms:.4f} drop={int((~keep).sum())}', file=sys.stderr)

    from utide._ut_constants import ut_constants
    table = ut_constants['const']
    unames = [n.strip() for n in table.name]
    cm = {}
    for i, u in enumerate(coef['name']):
        u = u.strip()
        if u in unames:
            xt, _ = find_xtide_match(u, table.freq[unames.index(u)] * 360.0)
            if xt:
                cm[xt] = (float(coef['A'][i]), float(coef['g'][i]) % 360.0)
    z0 = float(coef['mean'])
    L = [
        "#", f"# {name}", "# BEGIN HOT COMMENTS", "# country: India",
        "# source: Survey of India monthly tide tables (surveyofindia.gov.in) with UTide",
        f"# date_imported: {datetime.now():%Y%m%d}",
        "# datum: chart datum (per Indian Tide Tables)",
        f"# confidence: {conf}",
        f"# utide: pts={len(events)} hwlw period={events[0][0]:%Y-%m-%d}..{events[-1][0]:%Y-%m-%d} r2={r2:.4f} rms={rms:.4f}m const={sum(1 for cn, _ in CONSTITUENTS_175 if cn in cm)}",
        "# !units: meters", f"# !longitude: {lon:.4f}", f"# !latitude: {lat:.4f}",
        name, f'+00:00 :{tzname}', f"{z0:.4f} meters",
    ]
    for cn, _sp in CONSTITUENTS_175:
        if cn in cm and cm[cn][0] >= 0.00005:
            L.append(f"{cn:15s} {cm[cn][0]:.4f}  {cm[cn][1]:.2f}")
        else:
            L.append("x 0 0")
    print('\n'.join(L))


def main():
    if sys.argv[1] == '--list':
        names = {}
        for p in glob.glob(MONTHS_DIR + '/**/*.pdf', recursive=True):
            names.setdefault(Path(p).stem.upper(), 0)
            names[Path(p).stem.upper()] += 1
        for n, c in sorted(names.items()):
            print(f'{c:3d}  {n}')
        return
    station, name, lat, lon, conf = sys.argv[1], sys.argv[2], \
        float(sys.argv[3]), float(sys.argv[4]), sys.argv[5]
    tzname = sys.argv[6] if len(sys.argv) > 6 else 'Asia/Kolkata'
    events = collect_events(station)
    print(f'# gesamt {len(events)} Events', file=sys.stderr)
    if len(events) < 300:
        print('# ZU WENIG EVENTS', file=sys.stderr)
        sys.exit(1)
    fit(events, name, lat, lon, conf, tzname)


if __name__ == '__main__':
    main()
