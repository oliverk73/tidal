#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""JCG-Stroemungsvorhersagen (py/jcg_laden.py) in Reihen und Konstanten umsetzen (Oliver 26.10.2026).

Je Abruf: Staerke je Punkt aus der HTML (<AREA coords=x,y,10 TITLE="0.3kn.">, 0,1 kn), Richtung
aus dem Pfeil im PNG um denselben Bildpunkt. Gebiete 01-20: farbige Pfeile auf hellem Grund;
A1 (Akashi) und K1 (Kurushima): schwarze Pfeile auf Farbfeldern.

Georeferenz: Die Tick-Marken innen am Kartenrahmen werden im Bild gesucht; GEO nennt je Gebiet
einen beschrifteten Tick (abgelesen am 26.10.2026) und den Tickabstand in Bogenminuten. Die Karten
sind winkeltreu (Mercator), Bildwinkel = rechtweisende Richtung.

Zeit: JST (UTC+9).

Fit: Stärke mit Vorzeichen entlang der Hauptachse (Mittel der doppelten Winkel). Einzelne Pfeile, deren
Spitze das Bild verwechselt (180 Grad), fallen gegen die Gezeitenkurve auf und werden umgedreht.

Usage: venv/bin/python py/jcg_auswerten.py reihen [GEBIET ...]    -> currents/japan_jcg/reihen/<g>.npz
       venv/bin/python py/jcg_auswerten.py fit [GEBIET ...]       -> currents/japan_jcg/reihen/<g>_fit.json
       venv/bin/python py/jcg_auswerten.py vergleich              -> NOAA-Japan-Stroeme gegen JCG
       venv/bin/python py/jcg_auswerten.py bloecke LISTE.csv      -> harmonics/help/jcg_stroeme_<datum>.txt
         (LISTE: Spalten id = Gebiet/Punkt, name; Flutrichtung per flutrichtung_pruefen: "drehen" wird gedreht)
       venv/bin/python py/jcg_auswerten.py probe GEBIET JJJJMMTTHH  -> Kontrollbild in harmonics/help
"""
from __future__ import annotations

import datetime as dt
import glob
import math
import os
import re
import sys

import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASIS = os.path.join(ROOT, 'currents/japan_jcg')
RAW = os.path.join(BASIS, 'raw')
REIHEN = os.path.join(BASIS, 'reihen')
JST = dt.timedelta(hours=9)

# Gebiet: (x-Tick, Laenge Grad, Minuten je x-Tick, y-Tick, Breite Grad, Minuten je y-Tick)
GEO = {
    '01': (30, 139 + 30 / 60, 10, 71, 35 + 40 / 60, 10),
    '02': (30, 136 + 30 / 60, 10, 76, 35 + 10 / 60, 10),
    '03': (81, 131.0, 10, 61, 34 + 40 / 60, 10),
    '04': (82, 129.0, 10, 98, 34.0, 10),
    '05': (48, 130 + 6 / 60, 2, 73, 33 + 12 / 60, 2),
    '06': (30, 130.0, 2, 72, 32 + 46 / 60, 2),
    '07': (51, 130 + 4 / 60, 2, 80, 32 + 32 / 60, 2),
    '08': (30, 130.0, 2, 82, 32 + 20 / 60, 2),
    '09': (30, 130 + 30 / 60, 2, 89, 31 + 44 / 60, 2),
    '10': (30, 130 + 30 / 60, 2, 59, 31 + 24 / 60, 2),
    '11': (30, 128 + 20 / 60, 10, 77, 28 + 40 / 60, 10),
    '12': (30, 129 + 20 / 60, 10, 114, 31 + 50 / 60, 10),
    '13': (85, 130.0, 10, 62, 31.0, 10),
    '14': (163, 127.0, 10, 105, 27.0, 10),
    '15': (252, 128.0, 10, 155, 27.0, 10),
    '16': (30, 127 + 20 / 60, 10, 553, 26.0, 10),
    '17': (418, 123.0, 2, 115, 24 + 28 / 60, 2),
    '18': (294, 127.0, 10, 178, 26 + 30 / 60, 10),
    '19': (30, 131 + 10 / 60, 2, 116, 25 + 58 / 60, 2),
    '20': (175, 124.0, 10, 94, 25.0, 10),
    'A1': (80, 134 + 59 / 60, 1 / 6, 40, 34 + 39 / 60, 1 / 6),
    'K1': (990, 133.0, 1 / 6, 185, 34 + 10 / 60, 1 / 6),
}
# Pfeilfarben der Gebiete 01-20 (Legende: grau <0,2, violett 0,2-0,5, blau 0,5-1, gruen 1-2, rot >2 kn)
FARBEN = np.array([(153, 153, 153), (106, 90, 205), (0, 0, 255), (0, 64, 0), (255, 0, 0)])


def merc(lat):
    return math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))


def rahmen(a):
    """Kartenrahmen und Tick-Marken (3 px nach innen) -> top, bot, lef, rig, x-Ticks, y-Ticks."""
    blk = a.sum(2) < 60
    H, W = blk.shape
    fr = [i for i in range(H) if blk[i].sum() > 0.3 * W]
    fc = [j for j in range(W) if blk[:, j].sum() > 0.3 * H]
    top, bot, lef, rig = fr[0], fr[-1], fc[0], fc[-1]
    xt = [j for j in range(lef, rig + 1) if blk[top + 2, j]]
    yt = [i for i in range(top, bot + 1) if blk[i, lef + 2]]
    return top, bot, lef, rig, xt, yt


def _gitter(ticks, ref, rand):
    """Ticks auf dem regelmaessigen Raster durch ref -> [(Tick, Index)].

    Rahmenkanten und Doppelpixel fallen weg; Schrittweite = Median der Abstaende (Gebiet 02 hat
    zwischen zwei Ticks Fremdpixel einer Beschriftung, die so nicht mitzaehlen)."""
    t = [x for x in sorted(set(ticks)) if min(abs(x - r) for r in rand) > 2 or x == ref]
    t = [x for i, x in enumerate(t) if i == 0 or x - t[i - 1] > 2]
    s = float(np.median(np.diff(t)))
    return [(x, round((x - ref) / s)) for x in t if abs((x - ref) / s - round((x - ref) / s)) < 0.1]


class Karte:
    """Bildpunkt -> (Breite, Laenge) fuer ein Gebiet."""

    def __init__(self, g, png):
        xr, lon0, dlon, yr, lat0, dlat = GEO[g]
        a = np.array(Image.open(png).convert('RGB')).astype(int)
        top, bot, lef, rig, xt, yt = rahmen(a)
        gx = _gitter(xt, xr, (lef, rig))
        gy = _gitter(yt, yr, (top, bot))
        lon = np.array([lon0 + k * dlon / 60 for _t, k in gx])
        lat = np.array([lat0 - k * dlat / 60 for _t, k in gy])
        self.bx = np.polyfit([t for t, _k in gx], lon, 1)
        self.by = np.polyfit([t for t, _k in gy], [merc(b) for b in lat], 1)
        self.rx = float(np.max(np.abs(np.polyval(self.bx, [t for t, _k in gx]) - lon))) * 60
        self.ry = float(np.max(np.abs([self.geo(0, t)[0] - b for (t, _k), b in zip(gy, lat)]))) * 60
        self.n = (len(gx), len(gy))

    def geo(self, x, y):
        lon = float(np.polyval(self.bx, x))
        lat = math.degrees(2 * math.atan(math.exp(np.polyval(self.by, y)))) - 90
        return lat, lon


def punkte(html, png=None):
    """[(x, y, kn)] aus der HTML-Seite, x/y in Bildpunkten des PNG.

    A1/K1 zeigen das Bild verkleinert (<img ... width=488>), die coords gelten fuer die Anzeige."""
    t = open(html, encoding='utf-8', errors='replace').read()
    f = 1.0
    m = re.search(r'<img [^>]*width=(\d+)', t)
    if m:
        f = Image.open(png or html[:-5] + '.png').size[0] / int(m.group(1))
    return [(round(int(x) * f), round(int(y) * f), float(v)) for x, y, v in
            re.findall(r'coords=(\d+),(\d+),\d+\s+ALT="[^"]*"\s+TITLE="([\d.]+)kn', t)]


def maske(a, schwarz):
    if schwarz:
        return a.sum(2) < 200
    m = np.zeros(a.shape[:2], bool)
    for f in FARBEN:
        m |= np.abs(a - f).sum(2) < 40
    return m


def richtung(m, x, y, r):
    """Pfeilrichtung (Grad rechtweisend) der Pfeilpixel um (x, y) oder None.

    Zusammenhaengende Pixelgruppe, die dem Mittelpunkt am naechsten liegt; Achse per
    Hauptkomponente, Spitze = das Ende, an dem die Pixel quer zur Achse breiter streuen."""
    H, W = m.shape
    y0, y1, x0, x1 = max(0, y - r), min(H, y + r + 1), max(0, x - r), min(W, x + r + 1)
    sub = m[y0:y1, x0:x1]
    if sub.sum() < 6:
        return None
    from scipy import ndimage
    lab, n = ndimage.label(sub, structure=np.ones((3, 3)))
    yy, xx = np.nonzero(lab)
    d = (yy + y0 - y) ** 2 + (xx + x0 - x) ** 2
    k = lab[yy[np.argmin(d)], xx[np.argmin(d)]]
    if d.min() > (r / 2) ** 2:
        return None
    yy, xx = np.nonzero(lab == k)
    if len(yy) < 6:
        return None
    px, py = xx.astype(float), -yy.astype(float)          # Bild-y nach unten -> Nord nach oben
    px -= px.mean()
    py -= py.mean()
    w, V = np.linalg.eigh(np.cov(np.vstack([px, py])))
    ax = V[:, np.argmax(w)]
    t = px * ax[0] + py * ax[1]
    q = -px * ax[1] + py * ax[0]
    mitte = (t.max() + t.min()) / 2
    vorn, hinten = q[t > mitte], q[t < mitte]
    if len(vorn) < 3 or len(hinten) < 3:
        return None
    breit_v = np.percentile(np.abs(vorn), 90)
    breit_h = np.percentile(np.abs(hinten), 90)
    if abs(breit_v - breit_h) < 0.5:
        return None
    if breit_h > breit_v:
        ax = -ax
    return math.degrees(math.atan2(ax[0], ax[1])) % 360


def zeitpunkt(stamm):
    s = os.path.basename(stamm)
    return dt.datetime(int(s[:4]), int(s[4:6]), int(s[6:8]), int(s[8:10])) - JST


def radius(pkte):
    xy = np.array([(x, y) for x, y, _v in pkte], float)
    if len(xy) < 2:
        return 12
    d = np.sqrt(((xy[:, None] - xy[None]) ** 2).sum(2))
    d[d == 0] = 1e9
    return int(max(6, min(16, np.median(d.min(1)) * 0.45)))


def reihen(g):
    dateien = sorted(glob.glob(os.path.join(RAW, g, '*.html')))
    if not dateien:
        return None
    pk0 = punkte(dateien[0])
    karte = Karte(g, dateien[0][:-5] + '.png')
    r = radius(pk0)
    n = len(pk0)
    T, S, D = [], [], []
    for f in dateien:
        png = f[:-5] + '.png'
        if not os.path.exists(png):
            continue
        pk = punkte(f)
        if [(x, y) for x, y, _v in pk] != [(x, y) for x, y, _v in pk0]:
            print('  Punkte weichen ab:', f)
            continue
        m = maske(np.array(Image.open(png).convert('RGB')).astype(int), g in ('A1', 'K1'))
        T.append(zeitpunkt(f[:-5]))
        S.append([v for _x, _y, v in pk])
        D.append([richtung(m, x, y, r) if v >= 0.1 else None for x, y, v in pk])
    D = np.array([[np.nan if d is None else d for d in z] for z in D])
    lat, lon = zip(*[karte.geo(x, y) for x, y, _v in pk0])
    os.makedirs(REIHEN, exist_ok=True)
    np.savez_compressed(os.path.join(REIHEN, g + '.npz'), t=np.array(T, dtype='datetime64[s]'),
                        kn=np.array(S), grad=D, lat=np.array(lat), lon=np.array(lon),
                        xy=np.array([(x, y) for x, y, _v in pk0]))
    ok = np.isfinite(D) | (np.array(S) < 0.1)
    print('%s  %d Punkte  %d Zeiten  Radius %d  Richtung gefunden %.1f %%  Georeferenz %s Ticks, Rest %.2f/%.2f min'
          % (g, n, len(T), r, 100 * ok.mean(), karte.n, karte.rx, karte.ry))
    return True


def fit_punkt(t, kn, grad, lat):
    """-> (Ergebnis von cmems_stroemung_nachholen.analyse, Zahl umgedrehter Pfeile) oder None."""
    import pandas as pd
    import utide
    import cmems_stroemung_nachholen as C
    from shn_corrientes import KONST
    ok = (kn < 0.1) | np.isfinite(grad)
    t, kn, grad = t[ok], kn[ok], grad[ok]
    if len(t) < 300 or np.percentile(kn, 95) < 0.2:
        return None
    th = np.radians(np.where(np.isfinite(grad), grad, 0))
    z = np.sum(kn * np.exp(2j * th))
    achse = math.degrees(np.angle(z)) / 2 % 180
    s = np.where(kn < 0.1, 0.0, kn * np.sign(np.cos(th - math.radians(achse))))
    zeiten = pd.to_datetime(t).to_pydatetime()
    umgedreht = np.zeros(len(s), bool)
    for _runde in range(4):
        coef = utide.solve(zeiten, s, lat=lat, nodal=True, trend=False, method='ols', conf_int='none',
                           verbose=False, constit=KONST)
        rec = utide.reconstruct(zeiten, coef, verbose=False)['h']
        falsch = (kn >= 0.3) & (np.abs(s - rec) > np.abs(-s - rec) + 0.2)
        if not falsch.any():
            break
        s[falsch] = -s[falsch]
        umgedreht ^= falsch
    w = s / C.MS_KN
    rad = math.radians(achse)
    df = pd.DataFrame({'u': w * math.sin(rad), 'v': w * math.cos(rad)}, index=pd.to_datetime(t))
    return C.analyse(df, lat, KONST), int(umgedreht.sum())


def fit(g):
    import json
    p = os.path.join(REIHEN, g + '.npz')
    if not os.path.exists(p):
        return
    d = np.load(p)
    out = []
    for j in range(d['kn'].shape[1]):
        e = fit_punkt(d['t'], d['kn'][:, j], d['grad'][:, j], float(d['lat'][j]))
        if e is None:
            continue
        r, n_um = e
        out.append(dict(gebiet=g, punkt=j, lat=round(float(d['lat'][j]), 5), lon=round(float(d['lon'][j]), 5),
                        achse=round(r['achse'], 1), smax=round(r['smax'], 2), r2=round(r['r2'], 4),
                        rms=round(r['rms'], 3), n=r['n'], umgedreht=n_um, mean=r['mean'],
                        t0=str(r['t0'])[:10], t1=str(r['t1'])[:10],
                        konst={k: [round(a, 4), round(ph, 2)] for k, (a, ph) in r['konst'].items()}))
    json.dump(out, open(os.path.join(REIHEN, g + '_fit.json'), 'w'), indent=0)
    r2 = np.array([o['r2'] for o in out])
    print('%s  %d Punkte gefittet, R2 Median %.3f, < 0,9: %d, >= 1 kn: %d, Pfeile umgedreht %d'
          % (g, len(out), np.median(r2) if len(r2) else 0, (r2 < 0.9).sum(),
             sum(o['smax'] >= 1 for o in out), sum(o['umgedreht'] for o in out)))


def vergleich():
    """NOAA-Japan-Stroeme (harmonics_noaa_currents) gegen den naechsten JCG-Punkt bis 2 km."""
    import json
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from health_check import load_records
    import xtide_modell as X
    SP = {'M2': 28.9841042, 'S2': 30.0, 'K1': 15.0410686, 'O1': 13.9430356}
    fits = []
    for f in sorted(glob.glob(os.path.join(REIHEN, '*_fit.json'))):
        fits += json.load(open(f))
    if not fits:
        return
    la = np.array([o['lat'] for o in fits])
    lo = np.array([o['lon'] for o in fits])
    print('%-52s %5s %5s | %5s %5s %6s | %5s %6s' % ('NOAA', 'km', 'Gebiet', 'M2 N', 'M2 J', 'dG', 'K1 J/N', 'dG'))
    for r in load_records():
        if not (r['current'] and r['lat'] and 'noaa_currents' in r['file'] and 24 < r['lat'] < 36
                and 122.5 < r['lon'] < 141):
            continue
        e = 6371 * np.hypot(np.radians(la - r['lat']), np.radians(lo - r['lon']) * math.cos(math.radians(r['lat'])))
        i = int(np.argmin(e))
        if e[i] > 2:
            print('%-52s %5.1f  (kein JCG-Punkt)' % (r['name'][:52], e[i]))
            continue
        _z, w, _e, mer = X.satz_lesen(r['file'], r['name'])
        o = fits[i]
        zeile = '%-52s %5.1f %5s |' % (r['name'][:52], e[i], o['gebiet'])
        for k in ('M2', 'K1'):
            if k in w and k in o['konst']:
                gn = X.greenwich(w[k][1], SP[k], mer)
                dg = (o['konst'][k][1] - gn + 180) % 360 - 180
                if k == 'M2':
                    zeile += ' %5.2f %5.2f %+6.0f |' % (w[k][0], o['konst'][k][0], dg)
                else:
                    zeile += ' %5.2f %+6.0f' % (o['konst'][k][0] / max(w[k][0], 1e-3), dg)
        print(zeile)


def block(o, name, vz=1.0):
    """XTide-Satz (Knoten, UTC) fuer den Fit o; vz=-1 dreht Flood/Ebb."""
    from cmems_stroemung_nachholen import CONSTITUENTS_175, utide
    from shn_corrientes import KONST
    achse = (o['achse'] + (180 if vz < 0 else 0)) % 360
    L = ['# Harmonic constants derived from the Japan Coast Guard (JCG) current predictions',
         '# (https://www1.kaiho.mlit.go.jp/TIDE/pred2/, area %s), edited: hourly predictions on the 1st and' % o['gebiet'],
         '# 15th of each month %s..%s (speed 0.1 kn from the page, direction read from the arrow map)' % (o['t0'], o['t1']),
         '# (UTide v%s, principal-axis projection, %d fixed constituents)' % (utide.__version__, len(KONST)),
         '# R^2 = %.4f, RMS error = %.4f knots' % (o['r2'], o['rms']),
         '# Major axis: %.1f deg true' % achse, '#',
         '# BEGIN HOT COMMENTS', '# country: Japan',
         '# source: JCG current prediction (edited), UTide analysis',
         '# station_id_context: JCG-CURR-%s-%d' % (o['gebiet'], o['punkt']),
         '# institution: Japan Coast Guard, Hydrographic and Oceanographic Department', '# datum: n/a',
         '# station_type: current', '# major_axis_deg_true: %.1f' % achse, '# confidence: 6',
         '# !units: knots', '# !longitude: %.4f' % o['lon'], '# !latitude: %.4f' % o['lat'],
         '%s Current' % name, '+00:00 :UTC', '%.4f knots' % (vz * o['mean'])]
    for c, _sp in CONSTITUENTS_175:
        a = o['konst'].get(c)
        L.append('%-15s %.4f  %.2f' % (c, a[0], (a[1] + (180 if vz < 0 else 0)) % 360)
                 if a and a[0] >= 0.00005 else 'x 0 0')
    return '\n'.join(L)


def bloecke(liste):
    """Saetze fuer die Kandidatenliste, Flood = Flutstrom nach py/flutrichtung_pruefen."""
    import csv
    import json
    import netCDF4 as nc
    import tempfile
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import flutrichtung_pruefen as F
    from health_check import load_records
    fits = {}
    for f in glob.glob(os.path.join(REIHEN, '*_fit.json')):
        for o in json.load(open(f)):
            fits['%s/%d' % (o['gebiet'], o['punkt'])] = o
    zeilen = list(csv.DictReader(open(liste, encoding='utf-8')))
    fes = {k: nc.Dataset(os.path.join(F.FES_DIR, '%s_fes2022.nc' % k.lower())) for k in F.SPEED}
    T = [r for r in load_records() if r['lat'] is not None and not r['current']]
    pegel = (np.array([r['lat'] for r in T]), np.array([r['lon'] for r in T]), T)
    tmp = tempfile.NamedTemporaryFile('w', suffix='.txt', delete=False, encoding='iso-8859-1')
    tmp.write('\n\n'.join(block(fits[z['id']], z['name']) for z in zeilen) + '\n')
    tmp.close()
    out, urteile = [], []
    for z in zeilen:
        o = fits[z['id']]
        a = F.abstand(dict(file=tmp.name, name=z['name'] + ' Current', lat=o['lat'], lon=o['lon']), fes, pegel)
        u = F.urteil(a[0], a[3]) if a else 'unklar'
        urteile.append(u)
        out.append(block(o, z['name'], -1.0 if u == 'drehen' else 1.0))
        print('%-7s %-58s d %+5.0f %-8s %s' % (z['id'], z['name'][:58], a[0] if a else 0, u, a[4] if a else ''))
    os.unlink(tmp.name)
    ziel = os.path.join(ROOT, 'harmonics/help/jcg_stroeme_%s.txt' % dt.date.today().strftime('%Y%m%d'))
    open(ziel, 'w', encoding='iso-8859-1').write('\n'.join(out) + '\n')
    import collections
    print(collections.Counter(urteile), '->', ziel)


def probe(g, stamm):
    """Kontrollbild: erkannte Richtungen als rote Linien ueber das Original."""
    from PIL import ImageDraw
    f = os.path.join(RAW, g, stamm)
    if not os.path.exists(f + '.png'):
        f = os.path.join(BASIS, 'geo', g)
    im = Image.open(f + '.png').convert('RGB')
    pk = punkte(f + '.html')
    m = maske(np.array(im).astype(int), g in ('A1', 'K1'))
    r = radius(pk)
    im = im.resize((im.size[0] * 2, im.size[1] * 2))
    d = ImageDraw.Draw(im)
    for x, y, v in pk:
        w = richtung(m, x, y, r)
        if w is None:
            d.ellipse((2 * x - 3, 2 * y - 3, 2 * x + 3, 2 * y + 3), outline='red')
            continue
        ex, ey = 2 * x + 2 * r * math.sin(math.radians(w)), 2 * y - 2 * r * math.cos(math.radians(w))
        d.line((2 * x, 2 * y, ex, ey), fill='red', width=2)
        d.text((2 * x + 4, 2 * y + 4), '%.0f' % w, fill='black')
    out = os.path.join(ROOT, 'harmonics/help/jcg_probe_%s_%s.png' % (g, os.path.basename(stamm)))
    im.save(out)
    print('->', out)


if __name__ == '__main__':
    if sys.argv[1] == 'probe':
        probe(sys.argv[2], sys.argv[3])
    elif sys.argv[1] == 'reihen':
        for g in sys.argv[2:] or list(GEO):
            reihen(g)
    elif sys.argv[1] == 'fit':
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        for g in sys.argv[2:] or list(GEO):
            fit(g)
    elif sys.argv[1] == 'vergleich':
        vergleich()
    elif sys.argv[1] == 'bloecke':
        bloecke(sys.argv[2])
