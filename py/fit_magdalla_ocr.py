#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Magdalla/Hazira-Tidetafel-Booklets (Scan-PDFs, Phoenix Marine) per OCR -> UTide.

Quelle: 'The Tide Tables for Magdalla Port, Hazira Inner & Hazira Outer'
(Reproduktion der amtlichen Tafeln, Surveyor General of India, old Chart
datum, Zeiten IST UTC+5:30). Scans: Seite 2 = einzelne Buchseite rechts,
ab Seite 3 Doppelseiten. Je Buchseite: 8 Tagesbloecke, 3 Stationen
(TIME/Ht-Spaltenpaare), 3-4 Events/Tag.

OCR: tesseract TSV, Spaltenzuordnung ueber TIME/Ht.-Header-Anker,
Tagesnummern sequentiell verifiziert, Reparatur fehlender Dezimalpunkte/
fuehrender Nullen, Ausreisser ueber 2-Stufen-UTide-Fit (|resid|>0.5m raus).

Usage: python3 py/fit_magdalla_ocr.py  (Dry-Run, Bloecke nach /tmp/magdalla_blocks.txt)
"""
from __future__ import annotations
import csv
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pdfplumber
import utide

sys.path.insert(0, '/home/oliver/py')
sys.path.insert(0, '/home/oliver/batch')
from generate_germany_harmonics_175 import CONSTITUENTS_175, find_xtide_match
from batch_utide_uk_tidetimes import cosine_interpolate, CONSTIT_67

PDFS = [('/home/oliver/water_levels/magdalla-2025.pdf', 2025),
        ('/home/oliver/water_levels/magdalla-2026.pdf', 2026)]
IST = timedelta(hours=5, minutes=30)
MONTHS = {m: i + 1 for i, m in enumerate(
    ['January', 'February', 'March', 'April', 'May', 'June', 'July',
     'August', 'September', 'October', 'November', 'December'])}
STATIONS = ['Magdalla', 'Hazira Inner', 'Hazira Outer']


def ocr_half(img):
    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tf:
        img.save(tf.name)
        out = tf.name[:-4]
    subprocess.run(['tesseract', tf.name, out, '--psm', '6', 'tsv'],
                   capture_output=True)
    words = []
    for r in csv.reader(open(out + '.tsv'), delimiter='\t'):
        if len(r) == 12 and r[11].strip() and r[0] == '5':
            try:
                conf = float(r[10])
            except ValueError:
                continue
            if conf < 10:
                continue
            words.append({'x': int(r[6]), 'y': int(r[7]), 'w': int(r[8]),
                          'text': r[11].strip()})
    Path(tf.name).unlink(missing_ok=True)
    Path(out + '.tsv').unlink(missing_ok=True)
    return words


def fix_time(tok):
    t = re.sub(r'\D', '', tok)  # OCR-Muell ('(0123S' -> '0123')
    if len(t) == 3:
        t = '0' + t
    if len(t) != 4:
        return None
    hh, mm = int(t[:2]), int(t[2:])
    return (hh, mm) if hh < 24 and mm < 60 else None


def fix_height(tok):
    c = re.sub(r'[^0-9.,-]', '', tok).replace(',', '.')  # '«(0.68' -> '0.68'
    m = re.match(r'^(-?\d{1,2})\.(\d{1,2})$', c)
    if m:
        return float(c)
    d = re.sub(r'\D', '', c)
    if len(d) == 3 and not c.startswith('-'):  # Punkt verloren: 461 -> 4.61
        return float(d) / 100.0
    return None


def parse_half(words, prev_month=None, prev_day=None):
    """-> (month, last_day, Liste (month, day, station_idx, (hh,mm), height))"""
    # Monat/Jahr; bei unleserlichem Header aus Vorseiten-Cursor herleiten
    # (Buchseiten sind strikt chronologisch, Monate beginnen auf neuer Seite)
    month = None
    for w in words:
        if w['text'] in MONTHS:
            month = MONTHS[w['text']]
            break
    # Spalten-Anker: 3x TIME, 3x Ht
    times_x = sorted(w['x'] + w['w'] // 2 for w in words if w['text'].upper() == 'TIME')
    hts_x = sorted(w['x'] + w['w'] // 2 for w in words
                   if re.match(r'^Ht\.?$', w['text'], re.I))
    if len(times_x) < 3 or len(hts_x) < 3:
        return month, prev_day, []
    times_x, hts_x = times_x[:3], hts_x[:3]
    left_edge = times_x[0] - 80
    # Zeilen clustern: 30px Zeilenabstand im Block, 60px zwischen Bloecken
    # (an Scan vermessen, 300dpi) -> Zeilen-Split bei 15px, Block-Split bei 45px
    row_list = []
    for w in sorted(words, key=lambda w: w['y']):
        if row_list and w['y'] - row_list[-1][0] < 15:
            row_list[-1][1].append(w)
        else:
            row_list.append((w['y'], [w]))
    row_list = [(y, sorted(ws, key=lambda w: w['x'])) for y, ws in row_list]
    blocks = []
    for y, ws in row_list:
        has_time = any(re.match(r'^\d{3,4}$', re.sub(r'\D', '', w['text']) or 'x')
                       for w in ws)
        if not has_time:
            # Stoerzeilen (Header, Faltschatten) duerfen Bloecke nicht verketten
            continue
        if blocks and y - blocks[-1][-1][0] < 45:
            blocks[-1].append((y, ws))
        else:
            blocks.append([(y, ws)])
    out = []
    day = None
    first_day = None
    for blk in blocks:
        allw = [w for _, ws in blk for w in ws]
        # Tagesnummer im Block (links der ersten TIME-Spalte)
        ds = [int(w['text']) for w in allw
              if w['x'] + w['w'] // 2 < left_edge
              and re.match(r'^\d{1,2}$', w['text']) and 1 <= int(w['text']) <= 31]
        if ds:
            cand = ds[0]
            if day is None or cand in (day + 1, day) or (day >= 28 and cand == 1):
                day = cand
            elif abs(cand - (day + 1)) <= 2:
                day = cand
            else:
                day = day + 1 if day else cand
        elif day is not None:
            day += 1
        if day is None or day > 31:
            continue
        if first_day is None:
            first_day = day
            if month is None and prev_month is not None:
                # Monat herleiten: Tag 1 nach Monatsende -> Folgemonat,
                # sonst Fortsetzung des Vormonats
                month = prev_month + 1 if first_day < (prev_day or 0) else prev_month
                month = (month - 1) % 12 + 1
        if month is None:
            continue
        for y, ws in blk:
            for k in range(3):
                tx, hx = times_x[k], hts_x[k]
                tw = [w for w in ws if abs(w['x'] + w['w'] // 2 - tx) < 60
                      and re.match(r'^\d{3,4}$', re.sub(r'\D', '', w['text']) or 'x')]
                hw = [w for w in ws if abs(w['x'] + w['w'] // 2 - hx) < 60
                      and fix_height(w['text']) is not None]
                if not tw or not hw:
                    continue
                t = fix_time(tw[0]['text'])
                h = fix_height(hw[0]['text'])
                if t and h is not None and h < 12:
                    out.append((month, day, k, t, h))
    return month, day, out


def collect_events():
    ev = {0: [], 1: [], 2: []}
    for pdf_path, year in PDFS:
        prev_month = prev_day = None
        with pdfplumber.open(pdf_path) as pdf:
            for pi, page in enumerate(pdf.pages):
                if pi == 0:
                    continue
                img = page.to_image(resolution=300).original
                w, h = img.size
                halves = [img.crop((0, 0, w // 2, h)), img.crop((w // 2, 0, w, h))] \
                    if pi >= 2 else [img]
                for half in halves:
                    month, lday, items = parse_half(ocr_half(half), prev_month, prev_day)
                    if month is not None:
                        prev_month, prev_day = month, lday
                    if not items:
                        print(f'  !! Halbseite ohne Daten (S.{pi+1})', file=sys.stderr)
                    for mo, d, k, (hh, mi), ht in items:
                        try:
                            dt = datetime(year, mo, d, hh, mi) - IST
                        except ValueError:
                            continue
                        ev[k].append((dt, ht))
                print(f'  {Path(pdf_path).name} S.{pi+1} ok', file=sys.stderr, flush=True)
    for k in ev:
        ev[k].sort(key=lambda e: e[0])
        dedup = []
        for e in ev[k]:
            if not dedup or e[0] > dedup[-1][0]:
                dedup.append(e)
        ev[k] = dedup
    return ev


def fit_station(events, lat):
    # Nur zwischen direkt benachbarten, alternierenden Extremen interpolieren:
    # fehlt ein Event (OCR-Luecke), wuerde der Cosinus-Bogen HW->HW die
    # Zwischentide wegglaetten (tidetimes-Artefakt). Tapi-Aestuar: LW->HW
    # kurz (~4h), HW->LW lang (~9h) -> Bogen nur bei 2..10.5h UND >0.5m Hub.
    dts, lv = [], []
    for (t0, v0), (t1, v1) in zip(events, events[1:]):
        gap = (t1 - t0).total_seconds() / 3600.0
        if not (2.0 < gap < 10.5) or abs(v1 - v0) < 0.5:
            continue
        n = max(2, int(gap * 4))
        for i in range(n + 1):
            f = i / n
            dts.append(t0 + (t1 - t0) * f)
            lv.append((v0 + v1) / 2 + (v0 - v1) / 2 * np.cos(np.pi * f))
    dts, lv = np.array(dts), np.array(lv)
    kw = dict(lat=lat, nodal=True, trend=False, method='ols',
              conf_int='none', verbose=False, constit=CONSTIT_67)
    coef = utide.solve(dts, lv, **kw)
    resid = lv - utide.reconstruct(dts, coef, verbose=False)['h']
    keep = np.abs(resid) < 0.5
    n_drop = int((~keep).sum())
    coef = utide.solve(dts[keep], lv[keep], **kw)
    rec = utide.reconstruct(dts[keep], coef, verbose=False)
    resid = lv[keep] - rec['h']
    r2 = 1 - float(np.sum(resid ** 2)) / float(np.sum((lv[keep] - lv[keep].mean()) ** 2))
    rms = float(np.sqrt(np.mean(resid ** 2)))
    return coef, r2, rms, n_drop, len(events)


def build_block(name, lat, lon, coef, r2, rms, npts, t0, t1):
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
        "# source: Survey of India tide tables (Magdalla/Hazira booklet, OCR) with UTide",
        f"# date_imported: {datetime.now():%Y%m%d}",
        "# datum: chart datum (old chart datum per source booklet)",
        "# confidence: 6",
        f"# utide: pts={npts} hwlw period={t0:%Y-%m-%d}..{t1:%Y-%m-%d} r2={r2:.4f} rms={rms:.4f}m const={sum(1 for cn, _ in CONSTITUENTS_175 if cn in cm)}",
        "# !units: meters", f"# !longitude: {lon:.4f}", f"# !latitude: {lat:.4f}",
        name, '+00:00 :Asia/Kolkata', f"{z0:.4f} meters",
    ]
    for cn, _sp in CONSTITUENTS_175:
        if cn in cm and cm[cn][0] >= 0.00005:
            L.append(f"{cn:15s} {cm[cn][0]:.4f}  {cm[cn][1]:.2f}")
        else:
            L.append("x 0 0")
    return '\n'.join(L)


COORDS = [('Magdalla (Surat), Gujarat, India', 21.143, 72.744),
          ('Hazira Inner, Gujarat, India', 21.095, 72.638),
          ('Hazira Outer, Gujarat, India', 21.060, 72.570)]


def main():
    ev = collect_events()
    blocks = []
    for k, (name, lat, lon) in enumerate(COORDS):
        if len(ev[k]) < 1000:
            print(f'{name}: nur {len(ev[k])} Events - SKIP', file=sys.stderr)
            continue
        coef, r2, rms, n_drop, n = fit_station(ev[k], lat)
        print(f'{name}: n={n} drop={n_drop} r2={r2:.4f} rms={rms:.4f}', file=sys.stderr)
        blocks.append(build_block(name, lat, lon, coef, r2, rms, n,
                                  ev[k][0][0], ev[k][-1][0]))
    Path('/tmp/magdalla_blocks.txt').write_text('\n'.join(blocks) + '\n',
                                                encoding='iso-8859-1')
    import json
    json.dump({str(k): [[e[0].isoformat(), e[1]] for e in ev[k]] for k in ev},
              open('/tmp/magdalla_events.json', 'w'))
    print('Bloecke -> /tmp/magdalla_blocks.txt', file=sys.stderr)


if __name__ == '__main__':
    main()
