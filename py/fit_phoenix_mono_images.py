#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Phoenix-Marine-Monatstafeln im Monospace-Layout (Rozi, Sikka) -> UTide-Block.

Layout je Monatsbild: Kopf 'ROZI  January 2026 / Position: 22°34'N 070°02'E',
darunter 4 Spaltengruppen (Tage 1-8 / 9-16 / 17-24 / 25-31), je Gruppe
Day/DoW | Time(HHMM) | Ht(m, 1 Dezimale), 3-4 Events/Tag, Zeiten IST.

OCR: tesseract TSV; Spaltengruppen ueber 'Time'-Header-Anker, Tagesnummern
je Gruppe sequentiell (Block-Clustering ueber y-Luecken).

Usage: python3 py/fit_phoenix_mono_images.py DIR JAHR 'Name' LAT LON CONF [monatsmuster]
  monatsmuster: 'name' fuer <dir>/<stem>-january.jpg oder 'num' fuer <stem>1.jpg
Beispiel: ... water_levels/phoenix_sikka 2026 'Sikka, Gujarat, India' 22.4333 69.8167 4 num
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
import utide
from PIL import Image

sys.path.insert(0, '/home/oliver/py')
sys.path.insert(0, '/home/oliver/batch')
from generate_germany_harmonics_175 import CONSTITUENTS_175, find_xtide_match
from batch_utide_uk_tidetimes import CONSTIT_67

IST = timedelta(hours=5, minutes=30)
MONTH_NAMES = ['january', 'february', 'march', 'april', 'may', 'june', 'july',
               'august', 'september', 'october', 'november', 'december']


def ocr_words(img):
    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tf:
        img.save(tf.name)
        out = tf.name[:-4]
    subprocess.run(['tesseract', tf.name, out, '--psm', '6', 'tsv'], capture_output=True)
    words = []
    for r in csv.reader(open(out + '.tsv'), delimiter='\t'):
        if len(r) == 12 and r[11].strip() and r[0] == '5':
            try:
                if float(r[10]) < 15:
                    continue
            except ValueError:
                continue
            words.append({'x': int(r[6]), 'y': int(r[7]), 'w': int(r[8]), 'text': r[11].strip()})
    Path(tf.name).unlink(missing_ok=True)
    Path(out + '.tsv').unlink(missing_ok=True)
    return words


def parse_month(path, year, month):
    img = Image.open(path).convert('RGB')
    img = img.resize((img.width * 2, img.height * 2), Image.LANCZOS)
    words = ocr_words(img)
    # Spaltengruppen-Anker: 'Time'-Header
    times_x = sorted(w['x'] + w['w'] // 2 for w in words if w['text'] == 'Time')
    if len(times_x) < 3:
        return []
    # Zeilen clustern
    rows = []
    for w in sorted(words, key=lambda w: w['y']):
        if rows and w['y'] - rows[-1][0] < 18:
            rows[-1][1].append(w)
        else:
            rows.append((w['y'], [w]))
    # Tagesbloecke ueber y-Luecken (nur Zeilen mit Zeit-Tokens)
    def has_time(ws):
        return any(re.match(r'^\d{4}$', w['text']) for w in ws)
    data_rows = [(y, sorted(ws, key=lambda w: w['x'])) for y, ws in rows if has_time(ws)]
    if len(data_rows) < 8:
        return []
    gaps = [b[0] - a[0] for a, b in zip(data_rows, data_rows[1:])]
    med = sorted(gaps)[len(gaps) // 2]
    blocks = [[data_rows[0]]]
    for (y, ws), g in zip(data_rows[1:], gaps):
        if g > med * 1.6:
            blocks.append([])
        blocks[-1].append((y, ws))
    events = []
    days = {k: None for k in range(len(times_x))}
    for blk in blocks:
        # je Spaltengruppe: Tagesnummer + Events
        for k, tx in enumerate(times_x):
            x_lo = tx - 220
            x_hi = times_x[k + 1] - 220 if k + 1 < len(times_x) else 10 ** 9
            ds = []
            evs = []
            for y, ws in blk:
                band = [w for w in ws if x_lo <= w['x'] + w['w'] // 2 < x_hi]
                for i, w in enumerate(band):
                    if re.match(r'^\d{1,2}$', w['text']) and 1 <= int(w['text']) <= 31 \
                            and w['x'] + w['w'] // 2 < tx - 60:
                        ds.append(int(w['text']))
                    m = re.match(r'^(\d{2})(\d{2})$', w['text'])
                    if m and abs(w['x'] + w['w'] // 2 - tx) < 90:
                        hh, mi = int(m.group(1)), int(m.group(2))
                        if hh > 23 or mi > 59:
                            continue
                        ht = None
                        for v in band[i + 1:]:
                            mh = re.match(r'^(-?\d{1,2})[.,](\d{1,2})$', v['text'])
                            if mh and 0 < v['x'] - w['x'] < 400:
                                ht = float(mh.group(1) + '.' + mh.group(2))
                                break
                        if ht is not None and ht < 14:
                            evs.append((hh, mi, ht))
            d = ds[0] if ds else (days[k] + 1 if days[k] else None)
            if d is None or d > 31:
                continue
            days[k] = d
            for hh, mi, ht in evs:
                try:
                    events.append((datetime(year, month, d, hh, mi) - IST, ht))
                except ValueError:
                    pass
    return events


def main():
    d, year, name, lat, lon, conf = sys.argv[1], int(sys.argv[2]), sys.argv[3], \
        float(sys.argv[4]), float(sys.argv[5]), sys.argv[6]
    mode = sys.argv[7] if len(sys.argv) > 7 else 'name'
    files = sorted(Path(d).glob('*.jpg')) + sorted(Path(d).glob('*.webp'))
    stem = re.sub(r'(-(' + '|'.join(MONTH_NAMES) + r')|\d+)?\.(jpg|webp)$', '',
                  files[0].name)
    events = []
    for m in range(1, 13):
        if mode == 'num':
            p = Path(d) / f'{stem}{m}.jpg'
        else:
            p = Path(d) / f'{stem}-{MONTH_NAMES[m-1]}.jpg'
        if not p.exists():
            print(f'# {p.name} fehlt', file=sys.stderr)
            continue
        ev = parse_month(p, year, m)
        print(f'# Monat {m}: {len(ev)} Events', file=sys.stderr, flush=True)
        events += ev
    events.sort(key=lambda e: e[0])
    events = [e for i, e in enumerate(events) if i == 0 or e[0] > events[i - 1][0]]
    print(f'# gesamt {len(events)}', file=sys.stderr)
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
        "# source: Phoenix Marine monthly tide tables (derived from official tables) with UTide",
        f"# date_imported: {datetime.now():%Y%m%d}",
        "# datum: chart datum (assumed, per source tide table)",
        f"# confidence: {conf}",
        f"# utide: pts={len(events)} hwlw period={events[0][0]:%Y-%m-%d}..{events[-1][0]:%Y-%m-%d} r2={r2:.4f} rms={rms:.4f}m const={sum(1 for cn, _ in CONSTITUENTS_175 if cn in cm)}",
        "# !units: meters", f"# !longitude: {lon:.4f}", f"# !latitude: {lat:.4f}",
        name, '+00:00 :Asia/Kolkata', f"{z0:.4f} meters",
    ]
    for cn, _sp in CONSTITUENTS_175:
        if cn in cm and cm[cn][0] >= 0.00005:
            L.append(f"{cn:15s} {cm[cn][0]:.4f}  {cm[cn][1]:.2f}")
        else:
            L.append("x 0 0")
    print('\n'.join(L))


if __name__ == '__main__':
    main()
