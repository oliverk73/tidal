#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Stromsaetze aus Hafen-Stromatlanten (Pfeilkarten je Stunde relativ zu HW eines Bezugshafens), 13.11.2026.

Gemeinsamer Teil fuer Harwich (HHA, Vektor-PDF), River Tees (PD Ports) und Milford Haven (MHPA):
  1. je Zielpunkt und Atlasstunde die Pfeile im Umkreis RADIUS_M mitteln (u, v in Knoten),
  2. eine synthetische Jahresreihe 2026 bauen: Zeit seit dem naechsten HW des Bezugshafens (unser Satz, XTide-Modell),
     periodisch ueber eine halbtaegige Tide (12,42 h) interpoliert; Staerke mal Tidenhub/mittlerer Hub
     (Atlas = mittlere Tide) bzw. zwischen Nipp- und Springbild interpoliert, wenn beide vorliegen,
  3. wie eine Messreihe mit UTide fitten (cmems_stroemung_nachholen.analyse) -> Block fuer
     harmonics_utide_current_tables.txt.

Harwich: venv/bin/python py/hafenatlas_stroeme.py harwich [--schreiben]
"""
import datetime as dt
import math
import os
import re
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cmems_stroemung_nachholen as C                               # noqa: E402
import shom_atlas_stroemung as S                                    # noqa: E402
from generate_germany_harmonics_175 import CONSTITUENTS_175         # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ZIEL = os.path.join(ROOT, 'harmonics/utide/harmonics_utide_current_tables.txt')
NEU = os.path.join(ROOT, 'tide_tables/att/Neu')
RADIUS_M = 300.0
PERIODE_H = 12.4206


def km(a, b, c, d):
    return math.hypot((c - a) * 111.2, (d - b) * 111.2 * math.cos(math.radians(a)))


def mittel(pfeile, la, lo, radius_m=RADIUS_M):
    """pfeile: [(lat, lon, u, v)] einer Stunde -> gewichtetes Mittel (u, v) oder None."""
    w, su, sv = 0.0, 0.0, 0.0
    for a, b, u, v in pfeile:
        d = km(la, lo, a, b) * 1000
        if d <= radius_m:
            g = 1.0 / (1.0 + d / 100.0)
            w, su, sv = w + g, su + g * u, sv + g * v
    return (su / w, sv / w) if w else None


def staerkster(stunden, la, lo, such_m):
    """Pfeilort mit der groessten mittleren Staerke im Umkreis such_m (Engstelle: staerkste Rinne)."""
    kand = {(round(a, 4), round(b, 4)) for p in stunden.values() for a, b, *_ in p if km(la, lo, a, b) * 1000 <= such_m}
    best = None
    for a, b in kand:
        z = [mittel(p, a, b) for p in stunden.values()]
        if sum(x is None for x in z) > 1:
            continue
        s = np.mean([math.hypot(*x) for x in z if x])
        if best is None or s > best[0]:
            best = (s, a, b)
    return best


def reihe(zyklus, hafen, hafen_datei, mittlerer_hub, jahr=2026, schritt_min=10):
    """zyklus: {stunde_rel_HW: (u, v)} -> DataFrame u, v (Knoten) fuer ein Jahr."""
    t0 = dt.datetime(jahr, 1, 1, tzinfo=dt.timezone.utc).timestamp()
    t = np.arange(t0 - 86400, t0 + 367 * 86400, 120.0)
    h = S.gezeit(hafen_datei, hafen, t)
    thw, hhw = S.scheitel(t, h, True)
    tnw, hnw = S.scheitel(t, h, False)
    hub = hhw - np.interp(thw, tnw, hnw)                 # Hub HW minus vorangehendes/umgebendes NW
    ts = np.arange(t0, t0 + 365 * 86400, schritt_min * 60.0)
    k = np.clip(np.searchsorted(thw, ts), 1, len(thw) - 1)
    k -= (ts - thw[k - 1]) < (thw[k] - ts)
    tau = (ts - thw[k]) / 3600.0
    st = sorted(zyklus)
    xs = np.array(st + [st[0] + PERIODE_H])               # periodisch schliessen
    u = np.array([zyklus[s][0] for s in st] + [zyklus[st[0]][0]])
    v = np.array([zyklus[s][1] for s in st] + [zyklus[st[0]][1]])
    tt = (tau - st[0]) % PERIODE_H + st[0]
    f = hub[k] / mittlerer_hub
    return pd.DataFrame({'u': np.interp(tt, xs, u) * f / C.MS_KN, 'v': np.interp(tt, xs, v) * f / C.MS_KN},
                        index=pd.to_datetime(ts, unit='s'))


def block(name, r, la, lo, quelle, regel, inst, kontext):
    heute = dt.date.today().strftime('%Y%m%d')
    L = ['# Harmonic constants derived from the %s, depth-averaged where stated, atlas digitised %s' % (quelle, heute),
         '# Atlas rule: %s' % regel,
         '# (UTide v0.3.1, principal-axis projection)',
         '# %d 10-minute samples, synthetic year 2026' % r['n'],
         '# R^2 = %.4f, RMS error = %.4f knots' % (r['r2'], r['rms']),
         '# Major axis: %.1f deg true' % r['achse'], '#',
         '# BEGIN HOT COMMENTS', '# country: United Kingdom',
         '# source: %s tidal stream atlas, UTide analysis' % inst,   # libtcd: source <= 90 Zeichen
         '# station_id_context: %s' % kontext, '# institution: %s' % inst,
         '# datum: n/a', '# station_type: current', '# major_axis_deg_true: %.1f' % r['achse'], '# confidence: 5',
         '# utide: period=2026-01-01..2026-12-31 const=%d' % len(r['konst']),
         '# !units: knots', '# !longitude: %.4f' % lo, '# !latitude: %.4f' % la,
         name, '+00:00 :UTC', '%.4f knots' % r['mean']]
    for k, _sp in CONSTITUENTS_175:
        a = r['konst'].get(k)
        L.append('%-15s %.4f  %.2f' % (k, a[0], a[1]) if a and a[0] >= 0.00005 else 'x 0 0')
    return '\n'.join(L)


# ---------------------------------------------------------------- Harwich Haven Authority (Vektor-PDF)
HHA = os.path.join(NEU, 'HHA-Tidal-Maps-All-NEW.pdf')
HHA_LEGENDE_PT = 10.54          # Legendenpfeil "Tidal Current = 1 Knot", beide Karten
# Pfeillaenge gegen die beschrifteten Werte ("0.9 KTS"): Pfeile im Median ~8 % kuerzer -> Faktor aus den Beschriftungen
HHA_ZIELE = [   # Name, Anker (lat, lon), Suchradius m; Deben-Muendung (Felixstowe Ferry) weggelassen: Kuesten- und Flussstrom gemischt, Flut ohne klare Richtung
    ('Landguard Point (Harwich Harbour entrance)', 51.9375, 1.3150, 600),
    ('Shotley Spit (Harwich Harbour)', 51.9525, 1.2990, 500),
    ('Harwich approach channel (Landguard buoy)', 51.9230, 1.3150, 600),
    ('Parkeston (River Stour)', 51.9500, 1.2400, 500),
    ('Wrabness (River Stour)', 51.9470, 1.1650, 1500),
    ('Fagbury (River Orwell)', 51.9660, 1.2820, 500),
    ('Pin Mill (River Orwell)', 51.9960, 1.2160, 1500),
    ('Stone Point (Hamford Water entrance)', 51.8880, 1.2760, 700),
]


def hha_pfeile():
    import fitz
    D = fitz.open(HHA)
    stunden, kal = {}, []
    for p in D:
        kopf = [x for x in p.get_text().split('\n') if x.startswith('HIGH WATER HARWICH')][0]
        m = re.search(r'([+-])\s*([\d.]+)\s*hours', kopf)
        std = (1 if m.group(1) == '+' else -1) * float(m.group(2)) if m else 0.0
        pf, beschr = [], []
        for x in p.get_drawings():
            f = x.get('fill')
            if not f or tuple(round(v, 2) for v in f) != (0.19, 0.34, 0.43) or x['type'] != 'f':
                continue
            if not all(i[0] == 'l' for i in x['items']) or len(x['items']) not in (7, 8, 9):
                continue
            P = np.array([[i[1].x, i[1].y] for i in x['items']])
            dd = [np.linalg.norm(P[k] - np.delete(P, k, 0).mean(0)) for k in range(len(P))]
            tail = P[int(np.argmax(dd))]
            tip = P[int(np.argmax(np.linalg.norm(P - tail, axis=1)))]
            if 160 < tail[0] < 185 and (380 < tail[1] < 395 or 770 < tail[1] < 785):
                continue                                      # Legendenpfeil
            mid = (tail + tip) / 2
            # beide Karten sind winkeltreu (Mercator-nah): Bild-y nach unten -> Nord = -dy
            dx, dy = tip - tail
            sp = math.hypot(dx, dy) / HHA_LEGENDE_PT
            az = math.atan2(dx, -dy)
            pf.append((*hha_ll(mid), sp * math.sin(az), sp * math.cos(az), mid))
        for b in p.get_text('dict')['blocks']:
            for ln in b.get('lines', []):
                for s in ln['spans']:
                    mm = re.match(r'([\d.]+)\s*KTS?', s['text'].strip())
                    if mm:
                        beschr.append((np.array([(s['bbox'][0] + s['bbox'][2]) / 2, (s['bbox'][1] + s['bbox'][3]) / 2]), float(mm.group(1))))
        for c, w in beschr:
            n = min(pf, key=lambda q: np.linalg.norm(q[4] - c))
            if np.linalg.norm(n[4] - c) < 9 and w >= 0.4:
                kal.append(w / math.hypot(n[2], n[3]))
        stunden[std] = [(a, b, u, v) for a, b, u, v, _m in pf]
    faktor = float(np.median(kal))
    for s in stunden:
        stunden[s] = [(a, b, u * faktor, v * faktor) for a, b, u, v in stunden[s]]
    # gleicher Ort auf beiden Karten: die genauere Hafenkarte (unten) gewinnt -- ueber den Radius automatisch gemischt
    return stunden, faktor, len(kal)


def hha_ll(pt):
    x, y = pt
    if y < 440:   # obere Uebersichtskarte: 1'E = 21,39 pt ab 1 deg 04' (x=130,45); 1'N = 34,59 pt, y=83,0 -> 52 deg 02,1'
        return 52 + (2.1 - (y - 83.0) / 34.59) / 60, 1 + (4 + (x - 130.45) / 21.39) / 60
    # untere Hafenkarte: 1'E = 57,78 pt ab 1 deg 13,1' (x=119,94); 1'N = 93,69 pt, y=480,29 -> 51 deg 58,2'
    return 51 + (58.2 - (y - 480.29) / 93.69) / 60, 1 + (13.1 + (x - 119.94) / 57.78) / 60


def harwich(argv):
    stunden, faktor, n = hha_pfeile()
    print('%d Atlasstunden, %d Pfeile; Laengenfaktor aus %d Beschriftungen x%.2f' % (
        len(stunden), sum(len(p) for p in stunden.values()), n, faktor))
    hafen = 'Harwich, England, United Kingdom'
    hd = os.path.join(ROOT, 'harmonics/classic/harmonics-dwf-20100529-nonfree_mod.txt')
    t = np.arange(dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc).timestamp(), dt.datetime(2027, 1, 1, tzinfo=dt.timezone.utc).timestamp(), 120.0)
    h = S.gezeit(hd, hafen, t)
    thw, hhw = S.scheitel(t, h, True)
    tnw, hnw = S.scheitel(t, h, False)
    mhub = float(np.mean(hhw - np.interp(thw, tnw, hnw)))
    print('mittlerer Hub Harwich %.2f m' % mhub)
    bl = []
    for name, la, lo, such in HHA_ZIELE:
        b = staerkster(stunden, la, lo, such)
        if not b:
            print('  %s: keine Pfeile' % name)
            continue
        _s, pla, plo = b
        zyk = {s: mittel(p, pla, plo) for s, p in stunden.items()}
        zyk = {s: z for s, z in zyk.items() if z}
        df = reihe(zyk, hafen, hd, mhub)
        r = C.analyse(df, pla, C.KONST)
        voll = '%s, England, United Kingdom Current' % name
        print('%-62s %.4f %.4f  Achse %3.0f  M2 %.2f kn  S2 %.2f  max %.1f kn  (%d Stunden)' % (
            voll, pla, plo, r['achse'], r['m2'], r['s2'], r['smax'], len(zyk)))
        bl.append(block(voll, r, pla, plo, 'Harwich Haven Authority tidal stream maps (HHA Tidal Maps, hourly HW Harwich -5..+6 h)',
                        'hours from HW Harwich, mean tide, strength x (range/mean range %.2f m); arrow length x%.2f from printed rates' % (mhub, faktor),
                        'Harwich Haven Authority', 'HHA-TIDAL-MAPS'))
    if '--schreiben' in argv and bl:
        from sicher_schreiben import schreiben
        T = open(ZIEL, encoding='iso-8859-1').read().rstrip('\n')
        schreiben(ZIEL, T + '\n' + '\n'.join(bl) + '\n')
        print('->', os.path.relpath(ZIEL, ROOT))


# ---------------------------------------------------------------- River Tees (PD Ports, Rasterbilder, von Hand abgelesen)
# Hauptrinne Tees Mouth zwischen den Molen (Bild 767x1038 px, Seite 3-15 rechts; Gradnetz 1'N = 175,5 px, 1'E = 104 px,
# 54 deg 38'N bei y=200, 1 deg 10'W bei x=127). Zahlen "Spring,Nipp" in Zehntelknoten; Flut SSW (205 Grad) in den Fluss,
# Ebbe NNE (25 Grad). Abgelesen 13.11.2026 aus der Montage aller 13 Stundenbilder (die Beschriftungen wandern je Seite;
# genommen wurde jeweils die Hauptrinne zwischen Eingang und Bran Sands, bei zwei Werten deren Mittel).
TEES = ('Tees Mouth (River Tees entrance)', 54.6385, -1.1470)
TEES_KN = {  # Stunde rel. HW River Tees Entrance: (Spring, Nipp, Richtung Grad)
    -6: (0.2, 0.2, 205), -5: (0.6, 0.25, 205), -4: (0.8, 0.4, 205), -3: (0.85, 0.45, 205), -2: (0.9, 0.5, 205),
    -1: (0.4, 0.35, 205), 0: (0.25, 0.25, 205), 1: (0.3, 0.1, 25), 2: (0.6, 0.25, 25), 3: (0.75, 0.35, 25),
    4: (0.55, 0.35, 25), 5: (0.6, 0.35, 25), 6: (0.1, 0.1, 25)}


def reihe_sn(spring, nipp, hafen, hafen_datei, hub_s, hub_n, jahr=2026, schritt_min=10):
    """Wie reihe(), aber zwischen Nipp- und Springbild nach dem Hub interpoliert (ausserhalb linear extrapoliert,
    nicht unter 0,5 x Nipp)."""
    t0 = dt.datetime(jahr, 1, 1, tzinfo=dt.timezone.utc).timestamp()
    t = np.arange(t0 - 86400, t0 + 367 * 86400, 120.0)
    h = S.gezeit(hafen_datei, hafen, t)
    thw, hhw = S.scheitel(t, h, True)
    tnw, hnw = S.scheitel(t, h, False)
    hub = hhw - np.interp(thw, tnw, hnw)
    ts = np.arange(t0, t0 + 365 * 86400, schritt_min * 60.0)
    k = np.clip(np.searchsorted(thw, ts), 1, len(thw) - 1)
    k -= (ts - thw[k - 1]) < (thw[k] - ts)
    tau = (ts - thw[k]) / 3600.0
    w = np.clip((hub[k] - hub_n) / (hub_s - hub_n), -0.5, 1.5)
    st = sorted(spring)
    xs = np.array(st)
    tt = np.clip(tau, st[0], st[-1])
    out = {}
    for j, c in enumerate(('u', 'v')):
        a = np.interp(tt, xs, [spring[x][j] for x in st])
        b = np.interp(tt, xs, [nipp[x][j] for x in st])
        out[c] = (b + (a - b) * w) / C.MS_KN
    return pd.DataFrame(out, index=pd.to_datetime(ts, unit='s'))


def tees(argv):
    import xtide_modell as X
    hafen = 'River Tees (Teesmouth), England, United Kingdom'
    hd = os.path.join(ROOT, 'harmonics/classic/harmonics-1997-05-25_mod.txt')
    _z0, w, e, _m = X.satz_lesen(hd, hafen)
    f = 0.3048 if e.startswith('f') else 1.0
    hub_s, hub_n = 2 * (w['M2'][0] + w['S2'][0]) * f, 2 * (w['M2'][0] - w['S2'][0]) * f
    sp = {s: (a * math.sin(math.radians(r)), a * math.cos(math.radians(r))) for s, (a, _n, r) in TEES_KN.items()}
    ni = {s: (n * math.sin(math.radians(r)), n * math.cos(math.radians(r))) for s, (_a, n, r) in TEES_KN.items()}
    name, la, lo = TEES
    r = C.analyse(reihe_sn(sp, ni, hafen, hd, hub_s, hub_n), la, C.KONST)
    voll = '%s, England, United Kingdom Current' % name
    print('Hub Spring %.2f m, Nipp %.2f m' % (hub_s, hub_n))
    print('%-60s %.4f %.4f  Achse %3.0f  M2 %.2f kn  S2 %.2f  max %.1f kn' % (voll, la, lo, r['achse'], r['m2'], r['s2'], r['smax']))
    b = block(voll, r, la, lo, 'PD Ports River Tees & Tees Bay tidal stream atlas (hourly HW River Tees Entrance -6..+6 h, read by hand)',
              'hours from HW River Tees Entrance, spring/neap rates interpolated by range (spring %.2f m, neap %.2f m)' % (hub_s, hub_n),
              'PD Teesport', 'PDPORTS-TEES-ATLAS')
    if '--schreiben' in argv:
        from sicher_schreiben import schreiben
        T = open(ZIEL, encoding='iso-8859-1').read().rstrip('\n')
        schreiben(ZIEL, T + '\n' + b + '\n')
        print('->', os.path.relpath(ZIEL, ROOT))


# ---------------------------------------------------------------- Milford Haven (MHPA Vol. 2 Lower Reaches, Messungen 1998-99)
# Vektor-PDF in ~15.000 Splitterflaechen -> Seiten gerendert (130 dpi, clip 95,30,500,810, -90 Grad gedreht) und abgelesen.
# Georeferenz per Kuestenabgleich mit den OSM-Landpolygonen (IoU 0,96; Stack Rock 30 m neben OSM):
# 194,29 px/km, Drehung 2,34 Grad, Bildursprung -5,115762 E / 51,716447 N. Pfeilrichtungen im Bild minus 2,3 Grad = rechtweisend.
MH_GEO = (194.28558772695777, 2.338731022035103, -5.115761895221098, 51.716447191138464)
MH_PUNKTE = [  # Name, Bild-x, Bild-y (130 dpi) ; Werte je Stunde rel. HW Milford Haven: (Spring kn, Richtung, Nipp kn, Richtung)
    ('Stack Rock (Milford Haven)', 303, 378, {
        -6: (0.2, 130, 0.1, 260), -5: (0.5, 115, 0.2, 90), -4: (1.0, 115, 0.5, 120), -3: (1.4, 117, 0.6, 120),
        -2: (1.3, 117, 0.5, 115), -1: (0.8, 118, 0.4, 125), 0: (0.2, 130, 0.1, 155), 1: (0.5, 290, 0.2, 295),
        2: (0.9, 280, 0.4, 290), 3: (1.0, 280, 0.4, 280), 4: (0.9, 285, 0.4, 275), 5: (0.5, 270, 0.3, 270), 6: (0.1, 195, 0.2, 265)}),
    ('Esso buoy (Milford Haven)', 400, 462, {
        -6: (0.1, 140, 0.1, 235), -5: (0.6, 100, 0.3, 110), -4: (1.0, 95, 0.4, 95), -3: (1.3, 100, 0.5, 95),
        -2: (1.2, 100, 0.5, 95), -1: (0.9, 105, 0.4, 90), 0: (0.3, 110, 0.1, 65), 1: (0.6, 275, 0.2, 280),
        2: (1.2, 275, 0.5, 270), 3: (1.4, 270, 0.5, 270), 4: (1.3, 270, 0.6, 270), 5: (0.9, 260, 0.5, 260), 6: (0.3, 260, 0.3, 270)}),
    ('East Angle (Milford Haven)', 693, 455, {
        -6: (0.1, 70, 0.1, 70), -5: (0.6, 85, 0.3, 75), -4: (1.0, 80, 0.5, 80), -3: (1.2, 80, 0.6, 75),
        -2: (1.2, 80, 0.5, 70), -1: (0.9, 85, 0.4, 75), 0: (0.3, 75, 0.0, 90), 1: (0.5, 260, 0.2, 270),
        2: (0.9, 255, 0.4, 260), 3: (1.1, 260, 0.4, 260), 4: (1.0, 260, 0.5, 260), 5: (0.6, 260, 0.3, 260), 6: (0.2, 235, 0.1, 280)}),
    ('Milford Docks (Milford Haven)', 1080, 393, {
        -6: (0.1, 80, 0.1, 70), -5: (0.6, 90, 0.3, 85), -4: (1.1, 90, 0.5, 85), -3: (1.3, 90, 0.6, 88),
        -2: (1.4, 90, 0.6, 88), -1: (1.1, 90, 0.5, 88), 0: (0.5, 85, 0.1, 120), 1: (0.5, 270, 0.3, 210),
        2: (1.1, 270, 0.5, 265), 3: (1.1, 270, 0.5, 270), 4: (1.2, 275, 0.4, 270), 5: (0.8, 270, 0.3, 265), 6: (0.2, 275, 0.1, 300)}),
]


def mh_ll(x, y):
    s, rot, lo0, la0 = MH_GEO
    c, sn = math.cos(math.radians(rot)), math.sin(math.radians(rot))
    e, n = (c * x + sn * y) / s, -(-sn * x + c * y) / s
    return la0 + n / 111.2, lo0 + e / (111.2 * math.cos(math.radians(51.7)))


def milford(argv):
    import xtide_modell as X
    hafen = 'Milford Haven, Wales, United Kingdom'
    hd = os.path.join(ROOT, 'harmonics/utide/harmonics_utide_observations.txt')
    _z0, w, e, _m = X.satz_lesen(hd, hafen)
    hub_s, hub_n = 2 * (w['M2'][0] + w['S2'][0]), 2 * (w['M2'][0] - w['S2'][0])
    print('Hub Spring %.2f m, Nipp %.2f m' % (hub_s, hub_n))
    bl = []
    for name, x, y, werte in MH_PUNKTE:
        la, lo = mh_ll(x, y)
        sp = {h: (a * math.sin(math.radians(r - 2.3)), a * math.cos(math.radians(r - 2.3))) for h, (a, r, _n, _r) in werte.items()}
        ni = {h: (n * math.sin(math.radians(r - 2.3)), n * math.cos(math.radians(r - 2.3))) for h, (_a, _r, n, r) in werte.items()}
        r = C.analyse(reihe_sn(sp, ni, hafen, hd, hub_s, hub_n), la, C.KONST)
        voll = '%s, Wales, United Kingdom Current' % name
        print('%-55s %.4f %.4f  Achse %3.0f  M2 %.2f kn  S2 %.2f  max %.1f kn' % (voll, la, lo, r['achse'], r['m2'], r['s2'], r['smax']))
        bl.append(block(voll, r, la, lo, 'Milford Haven Port Authority tidal stream atlas Vol. 2 (observed 1998-99, Hyder; HW Milford Haven -6..+6 h, read by hand)',
                        'hours from HW Milford Haven, spring/neap rates interpolated by range (spring %.2f m, neap %.2f m); position by coastline fit to OSM' % (hub_s, hub_n),
                        'Milford Haven Port Authority', 'MHPA-ATLAS-VOL2'))
    if '--schreiben' in argv:
        from sicher_schreiben import schreiben
        T = open(ZIEL, encoding='iso-8859-1').read().rstrip('\n')
        schreiben(ZIEL, T + '\n' + '\n'.join(bl) + '\n')
        print('->', os.path.relpath(ZIEL, ROOT))


# ---------------------------------------------------------------- Monty Mariner (nachgezeichnete Admiralty-Atlanten)
# montymariner.co.uk/tide-stream-charts (13.11.2026, Oliver: verwerten; Seite: nur privat/Lehre, nicht kommerziell).
# Bilder in tide_tables/att/montymariner/<gebiet>/01..13.png = HW-6..+6. Zahlen "Nipp Spring" in Zehntelknoten
# (Admiralty: Nipp zuerst). Gradnetz aus den Rahmenstrichen (1' je Strich):
MM_GEO = {   # gebiet: (x0, lon0, px je ' Laenge, y0, lat0, px je ' Breite)
    'solent_west': (53.5, -(2 + 10 / 60), 17.0, 142.5, 50 + 50 / 60, 27.0),
    'solent_east': (461.5, -1.0, 17.0, 143.5, 50 + 50 / 60, 27.0),
    'portland': (310.5, -2.5, 32.0, 472.0, 50.5, 51.0),
}
MM_BEZUG = {'solent_west': ('Portsmouth, England, United Kingdom', 'harmonics/utide/harmonics_utide_observations.txt'),
            'solent_east': ('Portsmouth, England, United Kingdom', 'harmonics/utide/harmonics_utide_observations.txt'),
            'portland': ('Weymouth, England, United Kingdom', 'harmonics/utide/harmonics_utide_observations.txt')}


def mm_ll(gebiet, x, y):
    x0, lo0, px, y0, la0, py = MM_GEO[gebiet]
    return la0 - (y - y0) / py / 60, lo0 + (x - x0) / px / 60


def mm_satz(gebiet, x, y, werte):
    """werte: {stunde: (nipp_kn, spring_kn, richtung_grad)} -> UTide-Ergebnis + (lat, lon)."""
    import xtide_modell as X
    hafen, rel = MM_BEZUG[gebiet]
    hd = os.path.join(ROOT, rel)
    _z0, w, _e, _m = X.satz_lesen(hd, hafen)
    hub_s, hub_n = 2 * (w['M2'][0] + w['S2'][0]), 2 * (w['M2'][0] - w['S2'][0])
    sp = {h: (sk * math.sin(math.radians(r)), sk * math.cos(math.radians(r))) for h, (_n, sk, r) in werte.items()}
    ni = {h: (n * math.sin(math.radians(r)), n * math.cos(math.radians(r))) for h, (n, _s, r) in werte.items()}
    la, lo = mm_ll(gebiet, x, y)
    return C.analyse(reihe_sn(sp, ni, hafen, hd, hub_s, hub_n), la, C.KONST), la, lo, hub_s, hub_n


def _w(fl, eb, reihe):
    """reihe: 13 (nipp, spring) fuer HW-6..+6, Vorzeichen +1 Flutrichtung fl, -1 Ebbrichtung eb."""
    return {h: (n / 10, sp / 10, fl if vz > 0 else eb) for h, (vz, n, sp) in zip(range(-6, 7), reihe)}


# Von Hand abgelesen 13.11.2026 (Montagen aller 13 Stundenbilder). Pruefung gegen Messsaetze: Needles 4 %, Freshwater
# Bay 6 %, Nab Tower 12 % Kurvenfehler. Inneres Ost-Solent/Spithead und Portland (Race, Wirbel, wandernde Beschriftung)
# nicht abgelesen: zu unsicher.
MM_PUNKTE = [
    ('Hurst Narrows (Solent)', 'solent_west', 687, 357, _w(70, 250, [(1, 16, 32), (1, 19, 39), (1, 13, 35), (1, 17, 35), (1, 12, 25), (-1, 1, 2),
        (-1, 14, 28), (-1, 20, 40), (-1, 22, 44), (-1, 22, 33), (-1, 11, 22), (-1, 4, 8), (1, 16, 33)])),
    ('Needles Channel (Solent)', 'solent_west', 612, 437, _w(55, 240, [(1, 9, 18), (1, 12, 25), (1, 13, 25), (1, 11, 25), (1, 8, 17), (1, 2, 4),
        (-1, 7, 15), (-1, 12, 24), (-1, 15, 25), (-1, 15, 29), (-1, 10, 20), (-1, 2, 5), (1, 7, 14)])),
    ('Yarmouth (Western Solent)', 'solent_west', 720, 345, _w(60, 240, [(1, 12, 24), (1, 12, 24), (1, 11, 22), (1, 9, 19), (1, 5, 10), (-1, 1, 3),
        (-1, 8, 17), (-1, 14, 27), (-1, 14, 28), (-1, 12, 25), (-1, 10, 20), (1, 2, 3), (1, 10, 20)])),
    ('Lymington (Western Solent)', 'solent_west', 750, 307, _w(60, 235, [(1, 11, 22), (1, 11, 22), (1, 11, 22), (1, 9, 18), (1, 4, 8), (-1, 4, 9),
        (-1, 12, 24), (-1, 12, 25), (-1, 12, 25), (-1, 11, 22), (-1, 4, 9), (1, 5, 10), (1, 11, 22)])),
    ('Gurnard (Central Solent)', 'solent_west', 872, 267, _w(65, 245, [(1, 14, 29), (1, 17, 34), (1, 17, 33), (1, 15, 29), (1, 8, 17), (-1, 2, 4),
        (-1, 15, 29), (-1, 18, 35), (-1, 16, 33), (-1, 15, 30), (-1, 11, 23), (1, 1, 2), (1, 13, 26)])),
    ('Nab Tower (Eastern Solent approach)', 'solent_east', 525, 420, {
        -6: (.3, .7, 90), -5: (.8, 1.6, 85), -4: (.9, 1.8, 85), -3: (.8, 1.5, 70), -2: (.4, .9, 60), -1: (.1, .2, 330), 0: (.7, 1.3, 275),
        1: (.7, 1.5, 265), 2: (.8, 1.6, 250), 3: (.6, 1.2, 220), 4: (.4, .8, 200), 5: (.2, .4, 190), 6: (.2, .4, 90)}),
    ('Selsey Bill (4 km S)', 'solent_east', 660, 385, {
        -6: (.8, 1.7, 90), -5: (1.2, 2.4, 85), -4: (1.2, 2.4, 85), -3: (.9, 1.8, 95), -2: (.4, .7, 90), -1: (.4, .8, 285), 0: (1.1, 2.2, 280),
        1: (1.3, 2.5, 275), 2: (1.0, 2.0, 275), 3: (.7, 1.3, 240), 4: (.2, .5, 240), 5: (.2, .5, 80), 6: (.7, 1.4, 85)}),
    ("St Catherine's Point (3 km S)", 'solent_east', 180, 603, {
        -6: (1.2, 2.3, 80), -5: (1.8, 3.7, 75), -4: (1.5, 3.3, 75), -3: (1.5, 2.9, 80), -2: (1.2, 2.4, 75), -1: (.1, .3, 70), 0: (1.2, 2.4, 265),
        1: (1.7, 3.4, 265), 2: (1.9, 3.8, 260), 3: (1.7, 3.4, 250), 4: (1.2, 2.3, 270), 5: (.4, .6, 250), 6: (.8, 1.6, 80)}),
]


def monty(argv):
    bl = []
    for name, gebiet, x, y, werte in MM_PUNKTE:
        r, la, lo, hs, hn = mm_satz(gebiet, x, y, werte)
        voll = '%s, England, United Kingdom Current' % name
        print('%-62s %.4f %.4f  Achse %3.0f  M2 %.2f kn  S2 %.2f  max %.1f kn' % (voll, la, lo, r['achse'], r['m2'], r['s2'], r['smax']))
        bl.append(block(voll, r, la, lo, 'Admiralty NP337 Solent tidal stream atlas as redrawn by montymariner.co.uk (hourly HW Portsmouth -6..+6 h, read by hand)',
                        'hours from HW Portsmouth, neap/spring rates interpolated by range (spring %.2f m, neap %.2f m); checked against measured sets Needles 4 %%, Freshwater 6 %%, Nab 12 %%' % (hs, hn),
                        'UKHO NP337 via Monty Mariner', 'NP337-MONTYMARINER'))
    if '--schreiben' in argv:
        from sicher_schreiben import schreiben
        T = open(ZIEL, encoding='iso-8859-1').read().rstrip('\n')
        schreiben(ZIEL, T + '\n' + '\n'.join(bl) + '\n')
        print('->', os.path.relpath(ZIEL, ROOT))


if __name__ == '__main__':
    if sys.argv[1:2] == ['harwich']:
        harwich(sys.argv[2:])
    elif sys.argv[1:2] == ['tees']:
        tees(sys.argv[2:])
    elif sys.argv[1:2] == ['milford']:
        milford(sys.argv[2:])
    elif sys.argv[1:2] == ['monty']:
        monty(sys.argv[2:])
    else:
        print(__doc__)
