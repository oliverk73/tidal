#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Hochaufgeloeste Gezeitenstromfelder fuer die Kartenebene (Oliver 19.11.2026: Schwachstromzonen in Starkstrom-
revieren sind fuer die Wegwahl wichtig -> Feld der feinen Modelle statt TPXO, wo vorhanden).

Quellen (Konstanten je Modellpunkt, tiefengemittelt):
  - SSW-RS (FVCOM NW-Schelf, Zellen an Kuesten ~0,7 km): Jahresfit 2018, quellen/tidal_streams/UK_SSWRS/fit_*.npz (kn)
  - AUSTEn (CSIRO COMPAS Australien): Ellipsen CSIRO_tidal_const_v12.nc (m/s)
  - WebTide Upper Fundy (DFO/BIO, Finite Elemente, 74934 Knoten; 21.11.2026): .v2c je Tide (u/v Amplitude m/s, Phase
    Greenwich); nur Knoten bis 2 m ueber Mittelwasser (das Modell rechnet Ueberflutung weit ins Land).
    Probe: Wasserstand M2 an 10 Pegeln 1-6 %, 0-5 Grad; Strom Minas Passage (FORCE-Messung) x1,05, -5 Grad.
`bauen` schreibt quellen/tidal_streams/feinfeld.npz: lat, lon, abstand_km (Nachbarpunkt), U_k/V_k komplex m/s
(c = a*e^{-ig}, Greenwich, wie TPXO in tpxo_strom_karte).

In tpxo_strom_karte.feld: Liegt eine Ausgabezelle im Gebiet eines feinen Modells (naechster Punkt < DECKT x
Punktabstand), bestimmt das feine Modell Wert (inverse Distanz der 3 naechsten Punkte) oder Land; sonst TPXO.

Usage: venv/bin/python py/strom_feinfeld.py bauen
"""
import math
import os
import re
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUS = os.path.join(ROOT, 'quellen/tidal_streams/feinfeld.npz')
KS = ('M2', 'S2', 'N2', 'K2', 'K1', 'O1', 'P1', 'Q1', 'M4', 'MS4', 'MN4')
DECKT = 3.0
# SHOM-Atlanten aus TELEMAC3D geben den OBERFLAECHENstrom, alle anderen Quellen (SSW-RS, AUSTEn, WebTide, SHOM-2D,
# TPXO) tiefengemittelt: im Kanal 20-30 % staerker und ~25 min spaeter (22.11.2026, Baie de Seine/Manche gegen
# Golfe normand-breton/SSW-RS). Zwischen verschiedenen Modellen breiter Uebergang statt Kante (_familie).
OBERFLAECHE = ('SHOM-MANCHE', 'SHOM-PAS-DE-CALAIS', 'SHOM-DUNKERQUE', 'SHOM-CALAIS', 'SHOM-BOULOGNE', 'SHOM-FINISTERE',
               'SHOM-IROISE', 'SHOM-BAIE-DE-SEINE', 'SHOM-LE-HAVRE')
RAND_FAMILIE_KM = 10.0
RAND_TPXO_KM = 6.0         # Uebergang feines Feld -> TPXO (einsetzen)
RAND_KM = 8.0               # Uebergangszone an der Grenze einer feineren Quelle hoechstens (bauen)
_S = {}


def _familie(name):
    """Modelllauf: geschachtelte Gitter desselben Laufs (Iroise in Finistere, Calais in Pas-de-Calais, BSH-Kueste in
    BSH-Nordsee) gehen auf 1,5-2 km ineinander ueber, verschiedene Modelle auf RAND_FAMILIE_KM (SHOM-2D gegen SSW-RS
    bei Sept-Iles: 0,6 gegen 0,2 kn)."""
    n = str(name)
    m = re.search(r'-(5\d\d)-', n)                  # SHOM-Atlasnummer = Modelllauf (560 Finistere+Iroise ...)
    if n.startswith('SHOM') and m:
        return 'SHOM-' + m.group(1)
    return n.split('-')[0]


def _xy(la, lo):
    """Kugel-Einheitsvektoren (fuer KD-Baum ueber Laengengrade hinweg)."""
    a, b = np.radians(la), np.radians(lo)
    return np.c_[np.cos(a) * np.cos(b), np.cos(a) * np.sin(b), np.sin(a)]


def bauen():
    from scipy.spatial import cKDTree
    teile = []
    # SSW-RS
    D = os.path.join(ROOT, 'quellen/tidal_streams/UK_SSWRS')
    F = np.load(os.path.join(D, 'fit_20180101_20181231.npz'))
    g = np.load(os.path.join(D, 'gitter.npz'))
    la, lo = g['latc'].astype(float), ((g['lonc'].astype(float) + 180) % 360) - 180
    uv = {k: (F['U_' + k].astype(np.complex64) * np.float32(0.514444), F['V_' + k].astype(np.complex64) * np.float32(0.514444))
          for k in KS if 'U_' + k in F.files}
    teile.append(('SSW-RS', la, lo, uv))
    # AUSTEn
    import netCDF4
    A = netCDF4.Dataset(os.path.join(ROOT, 'quellen/tidal_streams/Australia_AusTEn/CSIRO_tidal_const_v12.nc'))
    ks = [''.join(c.decode() if isinstance(c, bytes) else str(c) for c in x).strip() for x in A['constituent_name'][:]]
    mj, mn, inc, ph = [A[v][:].filled(np.nan).astype(float) for v in ('u_maj', 'u_min', 'u_inc', 'u_pha')]
    la2, lo2 = A['Mesh2_face_y'][:].astype(float), A['Mesh2_face_x'][:].astype(float)
    ok = np.isfinite(mj[:, ks.index('M2')])
    uv2 = {}
    for k in KS:
        if k not in ks:
            continue
        j = ks.index(k)
        e = np.exp(-1j * np.radians(ph[:, j]))
        p = np.radians(inc[:, j])
        U = e * (mj[:, j] * np.cos(p) - 1j * mn[:, j] * np.sin(p))
        V = e * (mj[:, j] * np.sin(p) + 1j * mn[:, j] * np.cos(p))
        uv2[k] = (np.nan_to_num(U[ok]).astype(np.complex64), np.nan_to_num(V[ok]).astype(np.complex64))
    teile.append(('AUSTEn', la2[ok], lo2[ok], uv2))
    # WebTide Upper Fundy
    W = os.path.join(ROOT, 'quellen/tidal_streams/Canada_WebTide/flood')
    nod = np.loadtxt(os.path.join(W, 'flood_ll.nod'))
    bat = np.loadtxt(os.path.join(W, 'flood.bat'))
    ok3 = bat[:, 1] > -2.0
    uv3 = {}
    for k in KS:
        f_ = os.path.join(W, '%s.barotropic.v2c' % k)
        if os.path.exists(f_):
            v = np.loadtxt(f_, skiprows=3)
            U = v[:, 1] * np.exp(-1j * np.radians(v[:, 2]))
            V = v[:, 3] * np.exp(-1j * np.radians(v[:, 4]))
            uv3[k] = (U[ok3].astype(np.complex64), V[ok3].astype(np.complex64))
    teile.append(('WebTide', nod[ok3, 2], nod[ok3, 1], uv3))
    # WebTide Halifax Harbour + Quatsino Sound (21.11.2026: Wasserstand x1,00 / x0,98, Quatsino Narrows x0,82;
    # Bras d'Or, NE-Pazifik, NW-Atlantik, Arktis, Hudson geprueft und verworfen -- py/webtide_pruefen.py)
    import webtide_pruefen as WP
    for g in ('halifax', 'quatsino'):
        G = WP.gebiet(g)
        ok4 = np.isfinite(G['tief']) & (G['tief'] > 0) & np.isfinite(G['v']['M2'][0])
        uv4 = {k: (np.nan_to_num(G['v'][k][0][ok4]).astype(np.complex64), np.nan_to_num(G['v'][k][1][ok4]).astype(np.complex64))
               for k in KS if k in G['v']}
        teile.append(('WebTide-' + g, G['lat'][ok4], G['lon'][ok4], uv4))
    # SHOM-2D-Atlanten + BSH-Atlas (22.11.2026, py/feinfeld_atlanten.py: Atlasregel wie die Einzelsaetze, linear gefittet)
    import feinfeld_atlanten as FA
    teile += FA.laden()
    # NorKyst800 (22.11.2026, py/norkyst_feinfeld.py): Norwegen, Zellen mit Springstrom >= 0,5 kn + 5 km Saum, Halbjahresfit
    import norkyst_feinfeld as NK
    teile += NK.laden_feinfeld()
    # Ueberlappung: je Quelle der Punktabstand im eigenen Gitter; ein Punkt faellt weg, wenn eine FEINERE Quelle
    # naeher als 0,7 x eigener Abstand einen Punkt hat (Manche 2 km unter Pas-de-Calais 500 m, BSH-Nordsee unter
    # BSH-Kueste, SSW-RS-Schelf unter SHOM/BSH ...).
    ab = []
    for _n, a, b, _uv in teile:
        d, _ = cKDTree(_xy(a, b)).query(_xy(a, b), k=2)
        ab.append(d[:, 1] * 6371)
    behalten = [np.ones(len(t[1]), bool) for t in teile]
    ueber = {}                                     # (fein, grob) -> Grobpunkte unter der feinen Quelle
    for q, (_n, a, b, _uv) in enumerate(teile):
        for p_, (_n2, a2, b2, _uv2) in enumerate(teile):
            if p_ == q or np.median(ab[p_]) >= np.median(ab[q]):
                continue
            d, _ = cKDTree(_xy(a2, b2)).query(_xy(a, b), distance_upper_bound=0.1)
            weg = d * 6371 < 0.7 * ab[q]
            if weg.any():
                ueber[(p_, q)] = weg
            behalten[q] &= ~weg
    # Weicher Rand (22.11.2026): Die Quellen rechnen verschieden (SHOM Finistere/Iroise/Manche = Oberflaeche aus 3D,
    # Gascogne/Golfe normand-breton = tiefengemittelt 2D; Unterschied an der Grenze bis 25 %). Damit an der Kante einer
    # feineren Quelle kein Sprung entsteht, gehen ihre Konstanten auf RAND km zur Grenze linear in die der groeberen
    # ueber (deren Wert am Ort per inverser Distanz aus ALLEN ihren Punkten). Grob zuerst, damit Schachtelungen
    # (Iroise in Finistere in Gascogne) auf den schon angeglichenen Werten aufsetzen.
    # aneinanderstossende Gitter gleicher Feinheit (Abers 563 | Golfe normand-breton 562 bei 3,5 W): keins faellt weg,
    # also auch kein Rand -> das kleinere geht auf seiner Seite in das groessere ueber
    for f in range(len(teile)):
        for g in range(f + 1, len(teile)):
            if (f, g) in ueber or (g, f) in ueber or _familie(teile[f][0]) == _familie(teile[g][0]):
                continue
            klein, gross = (f, g) if len(teile[f][1]) <= len(teile[g][1]) else (g, f)
            d, _ = cKDTree(_xy(teile[gross][1], teile[gross][2])).query(_xy(teile[klein][1], teile[klein][2]),
                                                                       distance_upper_bound=3.0 / 6371)
            if np.isfinite(d).sum() >= 20:
                ueber[(klein, gross)] = None
    for (f, g) in sorted(ueber, key=lambda x: -np.median(ab[x[1]])):
        _n, a, b, uv = teile[f]
        _n2, a2, b2, uv2 = teile[g]
        rand = min(max(3 * float(np.median(ab[g])), 1.5), RAND_KM)      # 500-m-Nachbar 1,5 km, 2-km-Atlas 6 km
        if _familie(teile[f][0]) != _familie(teile[g][0]):
            rand = RAND_FAMILIE_KM
        aussen = behalten[g].copy()
        if not aussen.any():
            continue
        # nur flaechige Abdeckung zaehlt als Rand: einzelne Grobpunkte in Haefen/Buchten, die das feine Gitter nicht
        # hat (SSW-RS-Elemente im Hafen Calais ...), wuerden sonst den ganzen kleinen Atlas angleichen
        ia = np.where(aussen)[0]
        ta = cKDTree(_xy(a2[ia], b2[ia]))
        nn = np.array([len(x) for x in ta.query_ball_point(_xy(a2[ia], b2[ia]), 4 * ab[g][ia] / 6371)])   # je Punkt eigener Abstand
        aussen[ia[nn < 12]] = False
        if not aussen.any():
            continue
        d_rand, _ = cKDTree(_xy(a2[aussen], b2[aussen])).query(_xy(a, b), distance_upper_bound=rand / 6371)
        r = np.clip(d_rand * 6371 / rand, 0, 1)
        nah = r < 1
        if not nah.any():
            continue
        dd, ii = cKDTree(_xy(a2, b2)).query(_xy(a[nah], b[nah]), k=3)
        dd = dd * 6371
        ok = dd[:, 0] < 3 * max(float(np.median(ab[g])), 0.3)
        w = 1 / np.maximum(dd, 0.05) ** 2
        w /= w.sum(1, keepdims=True)
        idx = np.where(nah)[0][ok]
        rr = r[idx].astype(np.float32)
        for k in KS:
            if k not in uv:
                continue
            for c in (0, 1):
                grob = (uv2[k][c][ii[ok]] * w[ok]).sum(1) if k in uv2 else 0
                neu = uv[k][c].copy()
                neu[idx] = rr * uv[k][c][idx] + (1 - rr) * grob
                uv[k] = (neu, uv[k][1]) if c == 0 else (uv[k][0], neu)
        print('  Rand %-26s -> %-26s %6d Punkte (%.0f km)' % (teile[f][0], teile[g][0], len(idx), rand))
    teile = [(n, a[m], b[m], {k: (uv[k][0][m], uv[k][1][m]) for k in uv}) for (n, a, b, uv), m in zip(teile, behalten)]
    out = dict(lat=[], lon=[], quelle=[])
    for k in KS:
        out['U_' + k], out['V_' + k] = [], []
    for q, (name, a, b, uv) in enumerate(teile):
        out['lat'].append(a.astype(np.float32))
        out['lon'].append(b.astype(np.float32))
        out['quelle'].append(np.full(len(a), q, np.int8))
        for k in KS:
            z = np.zeros(len(a), np.complex64)
            out['U_' + k].append(uv[k][0] if k in uv else z)
            out['V_' + k].append(uv[k][1] if k in uv else z)
        print('%-28s %7d Punkte, Tiden %s' % (name, len(a), ','.join(k for k in KS if k in uv)))
    out = {k: np.concatenate(v) for k, v in out.items()}
    d, _ = cKDTree(_xy(out['lat'], out['lon'])).query(_xy(out['lat'], out['lon']), k=2)
    out['abstand_km'] = (d[:, 1] * 6371).astype(np.float32)
    # Naht zwischen zwei Quellen: Randpunkte bekommen den Abstand zur Nachbarquelle (bis 3 km), sonst bleibt zwischen
    # feinem Gitter und den uebrig gebliebenen Grobpunkten ein Streifen ohne Wasser (Finistere 500 m / Gascogne 2 km)
    xyz = _xy(out['lat'], out['lon'])
    for q in range(len(teile)):
        m = out['quelle'] == q
        if m.all() or not m.any():
            continue
        do, _ = cKDTree(xyz[~m]).query(xyz[m], distance_upper_bound=3.0 / 6371)
        do = do * 6371
        a_ = out['abstand_km'][m]
        out['abstand_km'][m] = np.where(np.isfinite(do), np.maximum(a_, do), a_)
    out['quellen'] = np.array([t[0] for t in teile])
    np.savez(AUS, **out)
    print('->', AUS, '%.0f MB' % (os.path.getsize(AUS) / 1e6), ' Abstand Median %.2f km' % np.median(out['abstand_km']))


def _laden():
    if not _S and os.path.exists(AUS):
        from scipy.spatial import cKDTree
        F = np.load(AUS)
        _S.update({k: F[k] for k in F.files})
        _S['baum'] = cKDTree(_xy(_S['lat'].astype(float), _S['lon'].astype(float)))
    return _S


def einsetzen(lat, lon, u, v, t_rel_h, kopf, jahr):
    """lat (ny), lon (nx) der Ausgabezellen, u/v (ny, nx) m/s aus TPXO -> u/v mit feinem Feld, wo es deckt.
    t_rel_h: Stunden seit Jahresbeginn (UTC)."""
    S = _laden()
    if not S:
        return u, v, 0
    LA, LO = np.meshgrid(lat, lon, indexing='ij')
    d, i = S['baum'].query(_xy(LA.ravel(), LO.ravel()), k=3, distance_upper_bound=0.02)   # ~127 km
    d = d * 6371
    gut = np.isfinite(d[:, 0])
    if not gut.any():
        return u, v, 0
    i0 = np.where(gut, i[:, 0], 0)
    deckt = gut & (d[:, 0] < DECKT * np.maximum(S['abstand_km'][i0], 0.3))
    if not deckt.any():
        return u, v, 0
    # Zellweite der Ausgabe: Wasser, wenn ein Punkt naeher als halbe Zelldiagonale oder 1,5 x Punktabstand liegt
    zelle = abs(lat[1] - lat[0]) * 111 if len(lat) > 1 else 1.0
    # Abstand des groebsten der 3 Nachbarn: an der Naht zweier Gitter (Iroise 250 m / Finistere 500 m) bleibt sonst eine
    # schmale Luecke, die die Karte blass auffuellt (22.11.2026)
    ab3 = S['abstand_km'][np.where(np.isfinite(d), i, i0[:, None]) % len(S['abstand_km'])].max(1)
    wasser = deckt & (d[:, 0] < np.maximum(1.5 * ab3, 0.75 * zelle))
    idx = np.where(wasser)[0]
    ii = i[idx]
    dd = d[idx]
    w = np.where(np.isfinite(dd), 1.0 / np.maximum(dd, 0.05) ** 2, 0.0)
    w /= w.sum(1, keepdims=True)
    ii = np.where(np.isfinite(dd), ii, ii[:, :1])
    uu = np.zeros(len(idx))
    vv = np.zeros(len(idx))
    for k in KS:
        E = math.radians(kopf['arg'][jahr][k] + kopf['speeds'][k] * t_rel_h)
        f = kopf['fak'][jahr][k]
        rot = f * complex(math.cos(E), math.sin(E))
        uu += ((S['U_' + k][ii] * rot).real * w).sum(1)
        vv += ((S['V_' + k][ii] * rot).real * w).sum(1)
    uf, vf = u.ravel().copy(), v.ravel().copy()
    # Weicher Rand zu TPXO (23.11.2026, NorKyst-Auswahl endet quer im Fjord): Abstand jeder feinen Zelle zur naechsten
    # Zelle, die nur TPXO hat (TPXO Wasser, feines Feld deckt nicht); auf RAND_TPXO_KM linear von TPXO ins feine Feld.
    # Kueste zaehlt nicht: dort ist TPXO Land (NaN) oder das feine Feld deckt.
    nur_tpxo = (np.isfinite(uf) & ~deckt).reshape(u.shape)
    if nur_tpxo.any() and len(lat) > 1 and len(lon) > 1:
        from scipy import ndimage
        dy = abs(lat[1] - lat[0]) * 111.2
        dx = abs(lon[1] - lon[0]) * 111.2 * math.cos(math.radians(float(np.mean(lat))))
        dist = ndimage.distance_transform_edt(~nur_tpxo, sampling=(dy, dx)).ravel()[idx]
        g = np.clip(dist / RAND_TPXO_KM, 0, 1)
        ut, vt = uf[idx], vf[idx]
        ok = np.isfinite(ut) & np.isfinite(vt) & (g < 1)
        uu[ok] = g[ok] * uu[ok] + (1 - g[ok]) * ut[ok]
        vv[ok] = g[ok] * vv[ok] + (1 - g[ok]) * vt[ok]
    uf[deckt], vf[deckt] = np.nan, np.nan
    uf[idx], vf[idx] = uu, vv
    return uf.reshape(u.shape), vf.reshape(v.shape), int(deckt.sum())


if __name__ == '__main__':
    if sys.argv[1:2] == ['bauen']:
        bauen()
    else:
        print(__doc__)
