#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Stromsaetze aus dem CHS-Atlas der Gezeitenstroeme, Saint-Laurent von Cap de Bon-Desir bis Trois-Rivieres (2008), 21.11.2026.

Quelle: quellen/tidal_streams/Canada_CHS_atlas/chs-shc-atlas-stlawrence-saintlaurent-2008-41023195.pdf
(waves-vagues.dfo-mpo.gc.ca, Nachdruck nicht-kommerziell frei). 9 Abschnitte x 12 Stundenkarten (3D-Modell DFO, 400 m,
Sommerabfluss, ohne Wind), dazu Stromtabellen A-K (S. X).

Verfahren:
  1. Pfeile = Vektorflaechen (6 Linien) im PDF; Staerke = Laenge / (pt je Knoten), pt je Knoten je Abschnitt aus den
     Farbklassen (schwarz 0-1, dunkelblau 1-2, blau 2-3, gruen 3-4, orange 4-5, rot 5-6 kn; < 0,2 % Ausreisser).
  2. Georeferenz je Abschnitt: gedruckter Massstab (1:250 000 / 200 000 / 80 000 / 120 000, Mercator 47 N), Drehung und
     Lage per Kreuzkorrelation der Kartenfarben (Wasser/Land) mit der Wassermaske des DFO-Modells (ERDDAP mpoStleCourants,
     quellen/.../dfo_stle_maske_20260410.nc). Gegenprobe: Raute "I" faellt auf die Tabellenkoordinate Pont de Quebec.
  3. Kartenwerte gelten fuer einen bestimmten Hub; "Facteur de correction" je Abschnitt (Gerade ueber dem Hub am
     Bezugshafen) aus den Diagrammen abgelesen -> KORR.
  4. Zeit: Abschnitte 1-3 Stunden zu HW/NW Pointe-au-Pere, 4-9 zu HW/NW Quebec (Lauzon); jede Karte an IHR Ereignis
     gebunden (Steigdauer Quebec ~5 h, Fall ~7,3 h). Synthetisches Jahr 2026 (10 min), je Tide Faktor nach deren Hub,
     dann UTide wie bei den UK-Hafenatlanten (hafenatlas_stroeme).
  5. Saetze: Tabellenpunkte A-K direkt aus den Tabellen (mittlere Tide; "Var."-Richtung aus der Karte), sonst Karten-
     punkte an den staerksten Stellen (Abstand 6 km Aestuar / 4 km Fluss, Spitze >= 1,5 kn, nicht naeher als 2 km an A-K).
Gegen die Tabellen streuen die Kartenwerte am Tabellenort um +-25-30 % (starke Querschnittsgradienten, Raute am Ufer).

Usage: venv/bin/python py/stlorenz_atlas.py [--schreiben]
"""
import csv
import datetime as dt
import math
import os
import re
import sys

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cmems_stroemung_nachholen as C                               # noqa: E402
import shom_atlas_stroemung as S                                    # noqa: E402
from generate_germany_harmonics_175 import CONSTITUENTS_175         # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PDF = os.path.join(ROOT, 'quellen/tidal_streams/Canada_CHS_atlas/chs-shc-atlas-stlawrence-saintlaurent-2008-41023195.pdf')
MASKE = os.path.join(ROOT, 'quellen/tidal_streams/Canada_CHS_atlas/dfo_stle_maske_20260410.nc')
ZIEL = os.path.join(ROOT, 'harmonics/utide/harmonics_utide_current_tables.txt')
TIDE = os.path.join(ROOT, 'harmonics/utide/harmonics_utide_tidetables.txt')
PRUEF = os.path.join(ROOT, 'harmonics/help/neu_pruefen_%s.csv' % dt.date.today().strftime('%Y%m%d'))
R47 = 6378137.0 * math.cos(math.radians(47.0))

# Abschnitt: (Drehung Grad, Meter je pt, Mercator-Ost-, Nordversatz) aus der Maskenkorrelation 21.11.2026
GEO = {1: (49.90, 88.19450, -5324852.69, 4158713.75), 2: (55.30, 70.5556, -5345287.68, 4112942.21),
       3: (52.20, 70.5556, -5377798.68, 4075989.97), 4: (46.65, 70.5556, -5413332.83, 4044183.62),
       5: (20.50, 28.22224, -5421637.66, 4035605.81), 6: (-0.25, 42.33336, -5447575.22, 4031456.44),
       7: (0.00, 42.33336, -5473544.98, 4023548.63), 8: (0.00, 42.33336, -5495728.92, 4014531.99),
       9: (0.15, 42.33336, -5513014.09, 3996248.90)}
TITEL = {1: 'Cap de Bon-Desir to Saint-Simeon', 2: 'Saint-Simeon to Cap aux Oies', 3: 'Cap aux Oies to Sault-au-Cochon',
         4: 'Cap Gribane to Quebec', 5: 'Quebec Harbour', 6: 'Cap-Rouge to Sainte-Croix', 7: 'Sainte-Croix to Grondines',
         8: 'Grondines to Batiscan', 9: 'Gentilly to Trois-Rivieres'}
KLASSE = {(0.14, 0.12, 0.13): 0, (0.22, 0.23, 0.59): 1, (0.0, 0.48, 0.76): 2, (0.0, 0.58, 0.44): 3,
          (0.97, 0.6, 0.11): 4, (0.88, 0.22, 0.24): 5}
# Korrekturgeraden (Hub min, Hub max, Faktor dort), Diagramme "Facteur de correction" je Abschnitt
KORR = {1: (1.0, 5.0, 0.80, 1.53), 2: (1.0, 5.0, 0.74, 1.50), 3: (1.0, 5.0, 0.70, 1.32), 4: (2.5, 5.5, 0.60, 1.40),
        5: (2.5, 5.5, 1.07, 1.28), 6: (2.5, 5.5, 1.13, 1.24), 7: (2.5, 5.5, 1.01, 0.98), 8: (2.5, 5.5, 1.08, 0.97),
        9: (2.5, 5.5, 1.11, 0.92)}
BEZUG = {'PAP': 'Pointe-au-Père, Québec, Canada', 'QUE': 'Lauzon, Québec, Canada'}
# Seitenfolge je Abschnitt = Zeilenfolge der Tabellen (S. X): (Ereignis, Stunden ab Ereignis, Stundenmitte)
STUNDEN = {'PAP': [('N', 0.5), ('N', 1.5), ('N', 2.5), ('H', -2.5), ('H', -1.5), ('H', -0.5),
                   ('H', 0.5), ('H', 1.5), ('H', 2.5), ('N', -2.5), ('N', -1.5), ('N', -0.5)],
           'QUE': [('N', 0.5), ('N', 1.5), ('H', -2.5), ('H', -1.5), ('H', -0.5), ('H', 0.5),
                   ('H', 1.5), ('H', 2.5), ('H', 3.5), ('N', -2.5), ('N', -1.5), ('N', -0.5)]}


def bezug(k):
    return 'PAP' if k <= 3 else 'QUE'


def faktor(k, hub):
    a, b, fa, fb = KORR[k]
    return fa + (fb - fa) * (hub - a) / (b - a)


def _r(s):
    return [None if d in ('Var', 'W', 'NE', 'N') else int(d) for d in s.split()]


# Stromtabellen S. X: Abschnitt, Lage, Richtung je Seite (None = "Var." bzw. nur Buchstabe), Knoten (mittlere Tide)
TABELLE = {
    "Île Rouge (aval)": (1, 48 + 7.2 / 60, -(69 + 35.1 / 60), _r('065 Var Var Var 223 242 Var Var 022 056 080 077'),
                         [1.9, 1.2, 0.4, 1.0, 1.2, 1.1, 0.8, 0.7, 2.5, 2.9, 2.5, 2.3]),
    "Île Rouge (amont)": (1, 48 + 3.1 / 60, -(69 + 36.7 / 60), _r('053 062 Var Var Var W W Var 035 056 053 049'),
                          [5.1, 3.7, 1.8, 1.2, 1.7, 2.2, 2.1, 1.4, 1.9, 3.0, 3.9, 5.3]),
    "Passe de l'Île aux Lièvres": (1, 47 + 47.2 / 60, -(69 + 47.2 / 60), _r('066 Var Var W 255 253 250 249 Var Var 063 067'),
                                   [1.8, 0.9, 1.0, 2.2, 2.6, 2.8, 2.4, 1.6, 0.6, 1.1, 2.3, 2.5]),
    "Cap aux Oies": (3, 47 + 28.6 / 60, -(70 + 13.5 / 60), _r('061 062 Var Var Var 240 248 Var Var 064 060 060'),
                     [2.9, 2.6, 1.8, 0.8, 0.7, 1.6, 2.0, 1.6, 0.6, 1.6, 2.7, 3.0]),
    "Saint-Joseph-de-la-Rive": (3, 47 + 26.1 / 60, -(70 + 24.1 / 60), _r('077 077 076 061 Var 252 249 242 Var Var 080 079'),
                                [4.8, 4.7, 3.8, 1.3, 1.2, 3.1, 3.2, 2.5, 1.1, 1.5, 3.0, 4.2]),
    "Baie-Saint-Paul": (3, 47 + 24.4 / 60, -(70 + 27.3 / 60), _r('028 024 021 011 Var 211 215 198 Var Var 029 029'),
                        [4.5, 4.6, 3.8, 1.4, 0.7, 2.3, 2.8, 2.2, 1.3, 1.0, 2.3, 3.8]),
    "Traverse Saint-Roch": (3, 47 + 21.9 / 60, -(70 + 15.0 / 60), _r('026 027 030 Var 208 205 206 205 205 Var 032 027'),
                            [3.8, 3.2, 2.3, 0.8, 3.0, 4.1, 4.2, 3.6, 2.0, 1.1, 2.9, 3.9]),
    "Traverse du Nord": (4, 47 + 4.4 / 60, -(70 + 43.8 / 60), _r('217 213 215 215 Var 034 037 036 035 033 032 Var'),
                         [1.7, 2.8, 2.6, 1.6, 0.5, 0.8, 1.7, 2.2, 2.4, 2.4, 2.1, 1.1]),
    "Pont de Québec": (5, 46 + 44.7 / 60, -(71 + 17.4 / 60), _r('094 094 Var 270 270 270 Var 093 093 094 094 094'),
                       [6.0, 4.6, 1.7, 3.3, 3.8, 2.8, 1.7, 4.9, 6.3, 6.7, 6.2, 6.2]),
    "Traverse Saint-Augustin": (6, 46 + 42.6 / 60, -(71 + 27.8 / 60), _r('079 079 Var 261 262 263 Var 078 079 079 079 079'),
                                [3.7, 3.6, 1.2, 2.4, 3.1, 2.0, 0.8, 2.1, 2.9, 3.3, 3.5, 3.6]),
    "Île Richelieu": (7, 46 + 38.5 / 60, -(71 + 55.0 / 60), _r('050 050 050 050 NE N N N 051 050 050 050'),
                      [4.6, 4.8, 4.9, 4.6, 1.8, 0.9, 0.9, 1.1, 2.6, 3.7, 4.1, 4.3]),
}
# Buchstaben-Richtungen der Tabelle (W, NE, N) sind echte Richtungen, nur "Var." ist unbestimmt
TABELLE_BUCHST = {"Île Rouge (amont)": {5: 270, 6: 270}, "Passe de l'Île aux Lièvres": {3: 270}, "Île Richelieu": {4: 45, 7: 0}}


def km(a, b, c, d):
    return math.hypot((c - a) * 111.2, (d - b) * 111.2 * math.cos(math.radians(a)))


def ll(k, x, y):
    rot, m, ex, ny = GEO[k]
    c, s = math.cos(math.radians(rot)), math.sin(math.radians(rot))
    E = m * (c * x + s * y) + ex
    N = m * (s * x - c * y) + ny
    return math.degrees(2 * math.atan(math.exp(N / R47)) - math.pi / 2), math.degrees(E / R47)


def pfeile_seite(p):
    """Pfeilflaechen (6 Linien): (Rueckpunkt, Mitte der Spitzenseite, Laenge pt, Fuellfarbe)."""
    out = []
    for g in p.get_drawings():
        it = g['items']
        if not g.get('fill') or len(it) != 6 or not all(i[0] == 'l' for i in it):
            continue
        P = np.array([[i[1].x, i[1].y] for i in it])
        dd = [np.linalg.norm(P[k] - np.delete(P, k, 0).mean(0)) for k in range(len(P))]
        a = P[int(np.argmax(dd))]
        b = P[np.argsort(np.linalg.norm(P - a, axis=1))[-2:]].mean(0)
        L = float(np.linalg.norm(b - a))
        if 2 <= L <= 120:
            out.append((a, b, L, tuple(round(c, 2) for c in g['fill'])))
    return out


def eichung(R):
    L = [(a[2], KLASSE[a[3]]) for p in R for a in p if a[3] in KLASSE]
    fs = np.arange(3, 25, 0.02)
    bad = np.array([sum(1 for l_, i in L if not (i * f * 0.97 <= l_ <= (i + 1) * f * 1.03)) for f in fs])
    return float(np.median(fs[bad <= bad.min()]))


def abschnitt(k):
    """-> 12 Listen [(lat, lon, u_kn, v_kn)] (Kartenwert, ohne Korrekturfaktor), pt je Knoten."""
    import fitz
    D = fitz.open(PDF)
    R = [pfeile_seite(D[23 + 12 * (k - 1) + j]) for j in range(12)]
    f = eichung(R)
    rot = GEO[k][0]
    c, s = math.cos(math.radians(rot)), math.sin(math.radians(rot))
    out = []
    for p in R:
        z = []
        for a, b, L, _c in p:
            mid = (a + b) / 2
            dx, dy = b - a                                    # Rueckpunkt -> Spitze (Gegenprobe Tabellen A-K)
            e, n = c * dx + s * dy, s * dx - c * dy
            sk = L / f / math.hypot(e, n)
            z.append((*ll(k, *mid), e * sk, n * sk))
        out.append(z)
    return out, f


class Feld:
    def __init__(self, stunden):
        self.T = []
        for Z in stunden:
            A = np.array(Z)
            self.T.append((cKDTree(np.c_[A[:, 0] * 111.2, A[:, 1] * 111.2 * math.cos(math.radians(47))]), A[:, 2:]))

    def lesen(self, la, lo, n=3, rmax=1.0):
        q = [la * 111.2, lo * 111.2 * math.cos(math.radians(47))]
        V = []
        for T, UV in self.T:
            d, i = T.query(q, k=n)
            ok = d <= rmax
            if not ok.any():
                V.append([np.nan, np.nan])
                continue
            w = 1 / (0.15 + d[ok])
            V.append(w @ UV[i[ok]] / w.sum())
        return np.array(V)

    def naechster(self, la, lo):
        q = [la * 111.2, lo * 111.2 * math.cos(math.radians(47))]
        return min(T.query(q)[0] for T, _ in self.T)


_EREIG = {}


def ereignisse(ref):
    """HW/NW 2025-12-31..2027-01-01 am Bezugshafen: (Zeiten, Hub je Ereignis) fuer 'H' und 'N'."""
    if ref not in _EREIG:
        t0 = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc).timestamp()
        t = np.arange(t0 - 86400, t0 + 367 * 86400, 120.0)
        h = S.gezeit(TIDE, BEZUG[ref], t)
        th, hh = S.scheitel(t, h, True)
        tn, hn = S.scheitel(t, h, False)
        hub_h = hh - np.interp(th, tn, hn)                 # HW minus NW (interpoliert zwischen den Nachbar-NW)
        hub_n = np.interp(tn, th, hh) - hn
        _EREIG[ref] = {'H': (th, hub_h), 'N': (tn, hub_n), 'mittel': float(np.mean(hub_h))}
    return _EREIG[ref]


def reihe(k, zyklus, relativ=False):
    """zyklus: 12 x (u, v) Knoten in Seitenfolge -> 10-min-Reihe 2026 (m/s). relativ: Tabelle (mittlere Tide) ->
    Faktor(Hub)/Faktor(mittlerer Hub), sonst Kartenwert x Faktor(Hub)."""
    ref = bezug(k)
    E = ereignisse(ref)
    f0 = faktor(k, E['mittel']) if relativ else 1.0
    tk, uk, vk = [], [], []
    for (ev, off), (u, v) in zip(STUNDEN[ref], zyklus):
        te, hub = E[ev]
        f = np.array([faktor(k, x) for x in hub]) / f0
        tk.append(te + off * 3600)
        uk.append(u * f)
        vk.append(v * f)
    tk, uk, vk = np.concatenate(tk), np.concatenate(uk), np.concatenate(vk)
    o = np.argsort(tk, kind='stable')
    t0 = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc).timestamp()
    ts = np.arange(t0, t0 + 365 * 86400, 600.0)
    return pd.DataFrame({'u': np.interp(ts, tk[o], uk[o]) / C.MS_KN, 'v': np.interp(ts, tk[o], vk[o]) / C.MS_KN},
                        index=pd.to_datetime(ts, unit='s'))


def block(name, r, la, lo, k, art):
    ref = bezug(k)
    heute = dt.date.today().strftime('%Y%m%d')
    if art == 'tabelle':
        regel = 'currents table (atlas p. X), mean tide; rate x correction factor(range)/factor(mean range)'
    else:
        regel = 'hourly arrow chart, rate x correction factor(tidal range at %s)' % ('Pointe-au-Pere' if ref == 'PAP' else 'Quebec')
    L = ['# Harmonic constants derived from the CHS Atlas of Tidal Currents, St. Lawrence Estuary, Cap de Bon-Desir to',
         '# Trois-Rivieres (2008), sector %d %s; surface currents, summer runoff, no wind; digitised %s' % (k, TITEL[k], heute),
         '# Atlas rule: %s; hours from HW/LW %s' % (regel, 'Pointe-au-Pere' if ref == 'PAP' else 'Quebec (Lauzon)'),
         '# (UTide v0.3.1, principal-axis projection)',
         '# %d 10-minute samples, synthetic year 2026' % r['n'],
         '# R^2 = %.4f, RMS error = %.4f knots' % (r['r2'], r['rms']),
         '# Major axis: %.1f deg true' % r['achse'], '#',
         '# BEGIN HOT COMMENTS', '# country: Canada',
         '# source: CHS Atlas of Tidal Currents St. Lawrence Estuary 2008, UTide analysis',   # libtcd: <= 90 Zeichen
         '# station_id_context: CHS-ATLAS-STL-%s' % ('TABLE' if art == 'tabelle' else 'S%d' % k),
         '# institution: Canadian Hydrographic Service',
         '# datum: n/a', '# station_type: current', '# major_axis_deg_true: %.1f' % r['achse'], '# confidence: 5',
         '# utide: period=2026-01-01..2026-12-31 const=%d' % len(r['konst']),
         '# !units: knots', '# !longitude: %.4f' % lo, '# !latitude: %.4f' % la,
         name, '+00:00 :UTC', '%.4f knots' % r['mean']]
    for kk, _sp in CONSTITUENTS_175:
        a = r['konst'].get(kk)
        L.append('%-15s %.4f  %.2f' % (kk, a[0], a[1]) if a and a[0] >= 0.00005 else 'x 0 0')
    return '\n'.join(L)


def tabelle_zyklus(nm, feld):
    """Tabellenzeilen -> 12 x (u, v) kn; "Var." bekommt die Richtung der Karte (sonst der Nachbarzeile)."""
    k, la, lo, dirs, kn = TABELLE[nm]
    V = feld.lesen(la, lo, n=4, rmax=2.0)
    zyk = []
    for j in range(12):
        d = dirs[j] if dirs[j] is not None else TABELLE_BUCHST.get(nm, {}).get(j)
        if d is None:
            if np.isfinite(V[j]).all() and math.hypot(*V[j]) > 0.05:
                d = math.degrees(math.atan2(V[j][0], V[j][1])) % 360
            else:
                d = next(dirs[(j + s_) % 12] for s_ in (1, -1, 2, -2, 3, -3) if dirs[(j + s_) % 12] is not None)
        zyk.append((kn[j] * math.sin(math.radians(d)), kn[j] * math.cos(math.radians(d))))
    return zyk


_FELD = {}


def rohreihe(text, name, la, lo):
    """Fuer strom_ellipsen_eigen (Kompass): synthetische Jahresreihe u, v (m/s) wie beim Fit."""
    m = re.search(r'CHS-ATLAS-STL-(TABLE|S(\d))', text)
    if not m:
        return None
    nm = re.sub(r', Qu.bec, Canada Current$', '', name)
    k = TABELLE[nm][0] if m.group(1) == 'TABLE' else int(m.group(2))
    if k not in _FELD:
        _FELD[k] = Feld(abschnitt(k)[0])
    if m.group(1) == 'TABLE':
        return reihe(k, tabelle_zyklus(nm, _FELD[k]), relativ=True)
    V = pd.DataFrame(_FELD[k].lesen(la, lo)).interpolate(limit_direction='both').values
    return reihe(k, [tuple(v) for v in V])


GEONAMES = os.path.join(ROOT, 'quellen/tidal_streams/Canada_CHS_atlas/geonames_stlorenz.tsv')
# GeoNames fuehrt hier viele Kaps/Feuer nur englisch (alte CHS-Seekarten); Landessprache franzoesisch (Oliver: Ortsnamen Landessprache)
HAND = {'Goose Cape Lighthouse': 'Cap aux Oies', 'Ile Rouge Lighthouse': 'Île Rouge', 'Coudres Island Light': 'Île aux Coudres',
        'Cape Corbeau Front Light': 'Cap aux Corbeaux', 'Cape Corbeau Rear Light': 'Cap aux Corbeaux',
        'Cap au Saumon Lighthouse': 'Cap au Saumon', 'Cap de la Tete au Chien Lighthouse': 'Cap de la Tête au Chien',
        'Bicquette Light': 'Île Bicquette', 'Prairie Point Lighthouse': 'Pointe de la Prairie', 'Stone Pillar Light': 'Pilier de Pierre',
        'Pointe-au-Pic Lighthouse': 'Pointe-au-Pic', 'Cape Brule': 'Cap Brûlé', 'Brule Bank': 'Banc du Cap Brûlé',
        'Cape Gribanne': 'Cap Gribane', 'Cape Maillard': 'Cap Maillard', 'Cape St. Joseph': 'Cap Saint-Joseph',
        'Cape Tourmente': 'Cap Tourmente', 'Cape St. Ignace': 'Cap Saint-Ignace', 'North Channel': 'Chenal du Nord',
        'South Traverse': 'Traverse du Sud'}
PUNKTE_GN = {'CAPE', 'PT', 'PTS', 'LTHSE', 'ISLET', 'RK', 'RKS', 'RF', 'SHOL', 'BNK'}


def name_fuer(la, lo, G):
    """Punkt (Kap, Spitze, Feuer, Untiefe; Insel nur bis 1 km) bis 2,5 km, sonst Ort oder Punkt bis 30 km mit Abstand/Richtung;
    in einer Rinne (CHN bis 2 km) deren Name mit dem naechsten Punkt als Kontext."""
    def ri(a, b):
        az = math.degrees(math.atan2((lo - b) * math.cos(math.radians(la)), la - a)) % 360
        return RICHTUNG[int((az + 11.25) % 360 // 22.5)]
    nah = sorted((km(la, lo, a, b), n, a, b, c) for n, a, b, c, e in G if abs(a - la) < 0.25 and abs(b - lo) < 0.4)
    pkt = [x for x in nah if x[4] in PUNKTE_GN or (x[4] == 'ISL' and x[0] <= 1.0)]
    rinne = [x for x in nah if x[4] in ('CHN', 'NRWS') and x[0] <= 2.0]
    if rinne and pkt and pkt[0][0] <= 15:
        d, n, a, b, _c = pkt[0]
        return '%s (%s), Québec, Canada Current' % (rinne[0][1], n if d < 1 else '%s %d km %s' % (n, round(d), ri(a, b)))
    if pkt and pkt[0][0] <= 2.5:
        d, n, a, b, _c = pkt[0]
        return '%s, Québec, Canada Current' % n if d < 1 else '%s (%d km %s), Québec, Canada Current' % (n, max(1, round(d)), ri(a, b))
    alle = [x for x in nah if x[4] in PUNKTE_GN or x[4].startswith('PPL')]
    if alle and alle[0][0] <= 30:
        d, n, a, b, _c = alle[0]
        return '%s (%d km %s), Québec, Canada Current' % (n, max(1, round(d)), ri(a, b))
    return 'Fleuve Saint-Laurent %.3f %.3f, Québec, Canada Current' % (la, lo)


RICHTUNG = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE', 'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW']


def main(argv):
    import netCDF4
    import health_check as H
    nc = netCDF4.Dataset(MASKE)
    LAT, LON = nc['latitude'][:].data, nc['longitude'][:].data
    WAS = np.isfinite(np.ma.filled(nc['u'][0], np.nan))

    def wasser(la, lo):
        i = int(round((la - LAT[0]) / (LAT[1] - LAT[0])))
        j = int(round((lo - LON[0]) / (LON[1] - LON[0])))
        return 0 <= i < len(LAT) and 0 <= j < len(LON) and bool(WAS[i, j])

    F, PTKN = {}, {}
    for k in GEO:
        st, PTKN[k] = abschnitt(k)
        F[k] = Feld(st)
        print('Abschnitt %d: %d Pfeile, %.2f pt/kn' % (k, sum(len(z) for z in st), PTKN[k]), flush=True)
    for ref in BEZUG:
        print('Bezug %s: mittlerer Hub %.2f m' % (BEZUG[ref], ereignisse(ref)['mittel']))
    massstab = {k: GEO[k][1] for k in GEO}
    punkte = []                                           # (Name oder None, k, la, lo, zyklus, art)
    for nm, (k, la, lo, dirs, kn) in TABELLE.items():
        zyk = tabelle_zyklus(nm, F[k])
        punkte.append((nm, k, la, lo, zyk, 'tabelle'))
    # Kartenpunkte: 0,5-km-Raster ueber den Pfeilen, staerkste Stellen zuerst
    kand = []
    for k in GEO:
        f_m = faktor(k, ereignisse(bezug(k))['mittel'])
        orte = set()
        for T, _uv in F[k].T:
            for x, y in T.data:
                orte.add((round(x * 2) / 2, round(y * 2) / 2))
        feiner = [k2 for k2 in GEO if massstab[k2] < massstab[k]]
        for x, y in orte:
            la, lo = x / 111.2, y / (111.2 * math.cos(math.radians(47)))
            if not wasser(la, lo) or any(F[k2].naechster(la, lo) < 0.7 for k2 in feiner):
                continue
            V = F[k].lesen(la, lo)
            if np.isnan(V[:, 0]).sum() > 1:
                continue
            V = pd.DataFrame(V).interpolate(limit_direction='both').values
            spitze = float(np.max(np.hypot(V[:, 0], V[:, 1]))) * f_m
            kand.append((spitze, k, la, lo, [tuple(v) for v in V]))
    kand.sort(key=lambda x: -x[0])
    gewaehlt = []
    for sp, k, la, lo, zyk in kand:
        if sp < 1.5:
            break
        abst = 6.0 if k <= 3 else 4.0
        if any(km(la, lo, p[2], p[3]) < 2.0 for p in punkte if p[5] == 'tabelle'):
            continue
        if any(km(la, lo, g[2], g[3]) < abst for g in gewaehlt):
            continue
        gewaehlt.append((None, k, la, lo, zyk, 'karte'))
    punkte += gewaehlt
    print('%d Tabellen- + %d Kartenpunkte' % (len(TABELLE), len(gewaehlt)), flush=True)
    # Namen: eigene GeoNames-Auswahl (geonames_stlorenz.tsv, ohne "(historical)"), englische Altnamen von Hand franzoesisch
    G = []
    for z in open(GEONAMES, encoding='utf-8'):
        n_, a_, b_, c_, e_ = z.rstrip('\n').split('\t')
        n_ = HAND.get(n_, n_)
        n_ = re.sub(r'^Ile ', 'Île ', n_)
        n_ = re.sub(r'^(Pointe|Cap|Anse|Île) a ', r'\1 à ', n_).replace(' Tete ', ' Tête ')
        n_ = n_.replace('-Sur-', '-sur-').replace('-Aux-', '-aux-').replace(' De ', ' de ').replace('Saint Romuald', 'Saint-Romuald')
        n_ = {'Île-aux-Grues': "L'Isle-aux-Grues", 'St-Jean-Port-Joli': 'Saint-Jean-Port-Joli'}.get(n_, n_)
        G.append((n_, float(a_), float(b_), c_, int(e_ or 0)))
    namen = {r['name'] for r in H.load_records()}
    bl, zeilen = [], []
    for nm, k, la, lo, zyk, art in punkte:
        if nm is None and 'NM' not in locals():
            import stlorenz_namen                       # 21.11.: CGNDB franzoesisch, Inseln mit Abstand zur Kueste
            NM = stlorenz_namen.Namen([(p_[2], p_[3]) for p_ in punkte])
        name = ('%s, Québec, Canada Current' % nm) if nm else (NM.name(la, lo)[0] or name_fuer(la, lo, G))
        basis, n2 = name, 2
        while name in namen:
            name = basis.replace(' Current', ' (%d) Current' % n2)
            n2 += 1
        namen.add(name)
        df = reihe(k, zyk, relativ=(art == 'tabelle'))
        r = C.analyse(df, la, C.KONST)
        print('%-62s S%d %-7s %.4f %.4f Achse %3.0f M2 %.2f S2 %.2f max %.1f kn Rest %+.2f' % (
            name[:62], k, art, la, lo, r['achse'], r['m2'], r['s2'], r['smax'], r['mean']), flush=True)
        zeilen.append(dict(name=name, abschnitt=k, art=art, lat='%.4f' % la, lon='%.4f' % lo, achse='%.0f' % r['achse'],
                           m2='%.2f' % r['m2'], max_kn='%.1f' % r['smax'], mittel_kn='%.2f' % r['mean']))
        bl.append(block(name, r, la, lo, k, art))
    with open(os.path.join(ROOT, 'harmonics/help/stlorenz_atlas_punkte.csv'), 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=list(zeilen[0]))
        w.writeheader()
        w.writerows(zeilen)
    if '--schreiben' in argv and bl:
        from sicher_schreiben import schreiben
        T = open(ZIEL, encoding='iso-8859-1').read().rstrip('\n')
        schreiben(ZIEL, T + '\n' + '\n'.join(bl) + '\n')
        neu = not os.path.exists(PRUEF)
        with open(PRUEF, 'a', newline='', encoding='utf-8') as fh:
            w = csv.writer(fh)
            if neu:
                w.writerow(['datei', 'name'])
            for z in zeilen:
                w.writerow([os.path.basename(ZIEL), z['name']])
        print('->', os.path.relpath(ZIEL, ROOT), '+', os.path.relpath(PRUEF, ROOT))


if __name__ == '__main__':
    main(sys.argv[1:])
