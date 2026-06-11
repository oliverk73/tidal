#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Phoenix-Marine-Monats-Tidetafeln (digital gerenderte Bilder) -> UTide-Block.

Layout (z.B. Dahej 2026, dahej<1..12>.webp): Kalendergrid 4 Spalten x N Zeilen,
je Tageszelle 'Day DoW' + 3-5 Zeilen 'HH:MM  H.HH' (gruen=HW, rot=NW egal,
Hoehen m. Kartennull vermutet), Header mit Lat/Long und Time Zone +05:30.

OCR: tesseract TSV auf 2x-Upscale; Tageszellen ueber Tagesnummer-Anker
(Spaltenbaender), Events dem Anker darueber in derselben Spalte zugeordnet.

Usage: python3 py/fit_phoenix_monthly_images.py DIR GLOB JAHR 'Name' LAT LON [conf]
Beispiel: ... water_levels/dahej_2026 'dahej{m}.webp' 2026 'Dahej, Gujarat, India' 21.70 72.5167 4
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


def ocr_words(img):
    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tf:
        img.save(tf.name)
        out = tf.name[:-4]
    subprocess.run(['tesseract', tf.name, out, '--psm', '6', 'tsv'], capture_output=True)
    words = []
    for r in csv.reader(open(out + '.tsv'), delimiter='\t'):
        if len(r) == 12 and r[11].strip() and r[0] == '5':
            try:
                if float(r[10]) < 20:
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
    # Zeilen clustern
    rows = []
    for w in sorted(words, key=lambda w: w['y']):
        if rows and w['y'] - rows[-1][0] < 14:
            rows[-1][1].append(w)
        else:
            rows.append((w['y'], [w]))
    # Tages-Anker: Zahl 1-31 gefolgt von DoW-Token (OCR-tolerant: 'Ww' etc.)
    anchors = []
    for y, ws in rows:
        ws = sorted(ws, key=lambda w: w['x'])
        for i, w in enumerate(ws):
            if re.match(r'^\d{1,2}$', w['text']) and 1 <= int(w['text']) <= 31:
                nxt = [v for v in ws[i + 1:] if 0 < v['x'] - w['x'] < 130]
                if nxt and re.match(r'^(M|TU|W+|TH|F|SA|SU)$',
                                    re.sub(r'[^A-Z]', '', nxt[0]['text'].upper()) or 'x'):
                    anchors.append({'x': w['x'], 'y': y, 'day': int(w['text'])})
    if len(anchors) < 8:
        return []
    # Grid-Geometrie: Tag = Zeile*4 + Spalte + 1 (zeilenweise Nummerierung).
    # Spalten-/Zeilenbaender aus den gefundenen Ankern clustern, fehlende
    # Anker (DoW-OCR-Fehler) werden so geometrisch ueberbrueckt.
    def cluster(vals, tol):
        out = []
        for v in sorted(vals):
            if out and v - out[-1][-1] < tol:
                out[-1].append(v)
            else:
                out.append([v])
        return [sum(c) // len(c) for c in out]
    cols = cluster([a['x'] for a in anchors], 120)
    rws = cluster([a['y'] for a in anchors], 60)
    def cell_day(x, y):
        ci = min(range(len(cols)), key=lambda i: abs(cols[i] - x))
        cand = [i for i in range(len(rws)) if rws[i] <= y + 8]
        if not cand:
            return None
        return cand[-1] * 4 + ci + 1
    # Konsistenz pruefen
    ok = sum(1 for a in anchors if cell_day(a['x'], a['y']) == a['day'])
    if ok < len(anchors) * 0.8:
        print(f'# WARNUNG: Grid-Modell passt nur {ok}/{len(anchors)}', file=sys.stderr)
    events = []
    for y, ws in rows:
        ws = sorted(ws, key=lambda w: w['x'])
        for i, w in enumerate(ws):
            m = re.match(r'^(\d{1,2}):(\d{2})$', w['text'])
            if not m:
                continue
            hh, mi = int(m.group(1)), int(m.group(2))
            if hh > 23 or mi > 59:
                continue
            ht = None
            for v in ws[i + 1:]:
                if 0 < v['x'] - w['x'] < 200:
                    mh = re.match(r'^(\d{1,2})[.,](\d{1,2})$', v['text'])
                    if mh:
                        ht = float(mh.group(1) + '.' + mh.group(2))
                    break
            if ht is None or ht > 14:
                continue
            # Zelle geometrisch: Zeit-Token sitzt rechts der Tagesnummer-Spalte
            day = cell_day(w['x'] - 150, y)
            if day is None:
                continue
            try:
                dt = datetime(year, month, day, hh, mi) - IST
            except ValueError:
                continue
            events.append((dt, ht))
    return events


def main():
    d, pat, year, name, lat, lon = sys.argv[1], sys.argv[2], int(sys.argv[3]), \
        sys.argv[4], float(sys.argv[5]), float(sys.argv[6])
    conf = sys.argv[7] if len(sys.argv) > 7 else '5'
    events = []
    for m in range(1, 13):
        p = Path(d) / pat.format(m=m)
        if not p.exists():
            print(f'# {p} fehlt', file=sys.stderr)
            continue
        ev = parse_month(p, year, m)
        print(f'# Monat {m}: {len(ev)} Events', file=sys.stderr, flush=True)
        events += ev
    events.sort(key=lambda e: e[0])
    events = [e for i, e in enumerate(events) if i == 0 or e[0] > events[i - 1][0]]
    print(f'# gesamt {len(events)} Events', file=sys.stderr)
    # Paar-Interpolation (nur benachbarte alternierende Extreme)
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
        "# datum_note: Quelle 'Extrapolated/Inner', private Aufbereitung amtlicher Tafeln",
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
