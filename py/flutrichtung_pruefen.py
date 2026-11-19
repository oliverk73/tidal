#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Zeigt XTides "Flood" bei unseren Stroemungssaetzen in Flutrichtung? (Oliver 25.10.2026)

cmems_stroemung_nachholen.analyse legt die Hauptachse immer in 0-180 Grad. Positiv (XTide "Flood")
ist damit die Richtung, die zufaellig in diese Haelfte faellt -- bei Luis Correia war es die Ebbe.

Probe: Phasenabstand d = G(Strom, Hauptkonstituente) - G(Wasserstand FES2022 am selben Ort). Der
Flutstrom hat sein Maximum zwischen Niedrigwasser-Mitte und kurz nach Hochwasser (stehende Welle:
~ -90 Grad, fortschreitende: ~0 Grad). Geeicht an den Saetzen mit sicherer Flutrichtung (NOAA/CHS).
Hauptkonstituente: M2, bei Tagestiden (K1+O1 > M2+S2) K1.

Unklar -> TPXO10 (18.11.2026): Laufrichtung der Tidewelle = Richtung zunehmender Phase (Ebenen-Fit ueber 9x9
Zellen). Liegt die Flutrichtung (Achse) darin, ist der Satz richtig, sonst drehen. Nur bei Gradient >= 0.5 Grad/km und
|cos(Achse - Laufrichtung)| >= 0.3. Geeicht an den NOAA-Saetzen im unklaren Fenster: 154/154 richtig.
Seit 18.11. abends: Schwelle 0.3 Grad/km (20/21), nicht im Solent; zusaetzlich Nachbarregel (nachbar_urteil,
15 km, Eichung 141/141). Widersprechen sich TPXO und Nachbarn, bleibt der Satz unklar.

Usage: venv/bin/python py/flutrichtung_pruefen.py [--eichen] [--schreiben]
"""
from __future__ import annotations

import collections
import csv
import datetime as dt
import os
import sys

import math
import re

import netCDF4 as nc
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from health_check import load_records, ROOT, active_files                         # noqa: E402
import xtide_modell as X                                           # noqa: E402
import tpxo as TP                                                  # noqa: E402
from fes_ersatz_inseln import sample, FES_DIR                      # noqa: E402

SPEED = {'M2': 28.9841042, 'K1': 15.0410686, 'S2': 30.0, 'O1': 13.9430356}
ZWEITE = {'M2': 'S2', 'K1': 'O1'}
GEPRUEFT = ('harmonics_utide_current_observations.txt', 'harmonics_utide_current_tables.txt',
            'harmonics_utide_australia_oceancurrent.txt',
            # ATT Part IIIa: Dir(+) ist nur die positive Richtung, N/E-Saetze haben eine
            # willkuerliche Achse -> gleiche Probe (seit 7.11.2026)
            'harmonics_att_np203_currents.txt', 'harmonics_att_np204_currents.txt',
            'harmonics_att_np208_currents.txt')
EICHUNG = ('harmonics-dwf-20251228-free.txt', 'harmonics_noaa_currents.txt')
HILFE = os.path.join(ROOT, 'harmonics/help')
BIS_KM = 15.0


def wrap(x):
    return (x + 180.0) % 360.0 - 180.0


def urteil(d, d2):
    """richtig / drehen / unklar -- beide Konstituenten muessen im selben Fenster liegen."""
    def zone(x):
        if x is None:
            return None
        if -120 <= x <= 0:
            return 'richtig'
        if x >= 60:
            return 'drehen'
        return 'unklar'
    a, b = zone(d), zone(d2)
    return a if a != 'unklar' and (b is None or b == a) else 'unklar'


def km(a, b, c, d):
    p = np.pi / 180
    x = np.sin(a * p) * np.sin(c * p) + np.cos(a * p) * np.cos(c * p) * np.cos((b - d) * p)
    return 6371.0 * np.arccos(np.clip(x, -1, 1))


def pegel_phase(r, k, pegel):
    """Greenwich-Phase von k am naechsten Gezeitenpegel bis BIS_KM -> (G, Name, km) oder None.
    In engen Buchten trifft FES den Wasserstand schlecht (Pembina Terminal: FES +112, Messung +40 Grad)."""
    lat, lon, recs = pegel
    e = km(r['lat'], r['lon'], lat, lon)
    for i in np.argsort(e)[:5]:
        if e[i] > BIS_KM:
            return None
        p = recs[i]
        try:
            _z, w, _e, mer = X.satz_lesen(p['file'], p['name'])
        except KeyError:
            continue
        if k in w and w[k][0] > 0:
            return X.greenwich(w[k][1], SPEED[k], mer) % 360, p['name'], float(e[i])
    return None


def abstand(r, fes, pegel=None):
    """-> (d in Grad, Konstituente, Strom-Amplitude, d2, Bezug) oder None."""
    try:
        z0, w, _e, mer = X.satz_lesen(r['file'], r['name'])
    except KeyError:
        return None
    m2, s2 = w.get('M2', (0, 0))[0], w.get('S2', (0, 0))[0]
    k1, o1 = w.get('K1', (0, 0))[0], w.get('O1', (0, 0))[0]
    k = 'K1' if k1 + o1 > m2 + s2 else 'M2'
    if k not in w or w[k][0] <= 0:
        return None
    gs = X.greenwich(w[k][1], SPEED[k], mer) % 360
    bezug = 'FES2022'
    pp = pegel_phase(r, k, pegel) if pegel else None
    if pp:
        gt, bezug = pp[0], '%s (%.1f km)' % (pp[1], pp[2])
    else:
        amp, gt = sample(fes[k], r['lat'], r['lon'])
    if gt is None:
        return None
    # Zweite Konstituente desselben Bandes als Gegenprobe (S2 zu M2, O1 zu K1)
    k2 = ZWEITE[k]
    d2 = None
    if k2 in w and w[k2][0] > 0:
        pp2 = pegel_phase(r, k2, pegel) if pp else None
        gt2 = pp2[0] if pp2 else sample(fes[k2], r['lat'], r['lon'])[1]
        if gt2 is not None:
            d2 = wrap(X.greenwich(w[k2][1], SPEED[k2], mer) % 360 - gt2)
    return wrap(gs - gt), k, w[k][0], d2, bezug


GRAD_MIN, COS_MIN = 0.3, 0.3          # Eichung NOAA unklar: >=0.5 154/154, 0.3-0.5 20/21, darunter Muenzwurf
# TPXO loest die Solent-Doppeltide nicht auf (7 Widersprueche zu Nachbarn, 18.11.2026)
OHNE_TPXO = [(50.65, 50.90, -1.65, -0.85)]
NACHBAR_KM, NACHBAR_C = 15.0, 0.6       # Eichung NOAA unklar gegen sichere NOAA-Nachbarn: 141/141
# Nach Nachbarvergleich bewusst nicht drehen (18.11.2026), Urteil 'behalten'
BEHALTEN = {
    'Bird Island (35 km SSE, Algoa Bay), South Africa Current',            # 0.01 kn, Nachbarn gleich
    'Horse Sand Fort Lighthouse (2 km NNE), England, United Kingdom Current',  # Solent-Doppeltide, wie Spitbank
    'Epson Shoal (7 km ENE), England, United Kingdom Current',              # wie Tater Du (1 km)
    'Hario Seto (W Entrance), Nagasaki, Japan Current',                     # Flut nach S in die Omura-Bucht (TPXO: Enge)
    'Gabriola Passage, British Columbia, Canada Current',                   # CHS-Ereignisse 16.10. gegengeprueft
    # Messsaetze, 19.11.2026 (Oliver ok): eigener Phasentest grenzwertig (d ~54 Grad), Ausschlag gaeben nur
    # die neuen SSW-RS-Modellnachbarn, die nach derselben Regel gerichtet sind -> keine unabhaengigen Zeugen
    'Falls Gap (6 km E, 41 m deep), England, United Kingdom Current',
    'Falls Gap (6 km E, 9 m deep), England, United Kingdom Current',
    'Bray (2 km NE, 8 m deep), Ireland Current',
}
# Fortschreitende Welle: Achse in Laufrichtung (|cos| >= 0.5, Gradient >= 0.2) UND Flutmaximum -60..+60 Grad um HW
# (bzw. gespiegelt fuer drehen). Eichung: Kanal-Konvention 94/94, NOAA unklar 11/11 (18.11.2026).
FORT_GRAD, FORT_COS = 0.2, 0.5
GRAD_ALLEIN = 0.5    # darunter (0.3-0.5) zaehlt TPXO nur mit Nachbarbestaetigung: Hario Seto/Gabriola widersprachen


def achse(r):
    """Flutrichtung des Satzes (flood_dir / max_direction / Hauptachse) aus den Hot Comments."""
    L = open(os.path.join(ROOT, r['file']), encoding='iso-8859-1').read().split('\n')
    i = L.index(r['name'])
    a = i
    while a > 0 and L[a - 1].startswith('#'):    # nur der Kommentarkopf direkt ueber dem Satz
        a -= 1
    blk = '\n'.join(L[a:i])
    m = re.search(r'# (?:flood_dir|max_direction): (\d+)', blk)
    if m:
        return float(m.group(1))
    m = re.search(r'# (?:major_axis_deg_true|Major axis): ([-\d.]+)', blk)
    return float(m.group(1)) if m else None


def laufrichtung(k, lat, lon, s=4):
    """TPXO10: (Richtung zunehmender Phase, Grad/km) per Ebenen-Fit, oder None."""
    f = TP.feld('10', k.lower())
    z = TP.naechste_wasserzelle('10', lat, lon, 30)
    if f is None or z is None or z[2] > 10:
        return None
    i, j, _dk = z
    if i - s < 0 or i + s >= TP.NY:
        return None
    ii = np.arange(i - s, i + s + 1)
    jj = np.arange(j - s, j + s + 1) % TP.NX
    blk = np.asarray(f[ii[0]:ii[-1] + 1][:, jj])
    h = blk[..., 0] - 1j * blk[..., 1]
    ok = np.abs(h) > 0
    if ok.sum() < 8 or h[s, s] == 0:
        return None
    ph = np.degrees(np.angle(h / h[s, s]))
    Y, Xg = np.meshgrid((ii - i) / 30 * 111.2, ((jj - j + TP.NX // 2) % TP.NX - TP.NX // 2) / 30 * 111.2
                        * math.cos(math.radians(lat)), indexing='ij')
    A = np.c_[Xg[ok], Y[ok], np.ones(ok.sum())]
    (gx, gy, _), *_ = np.linalg.lstsq(A, ph[ok], rcond=None)
    return math.degrees(math.atan2(gx, gy)) % 360, math.hypot(gx, gy)


# Amtliche Flut-Konvention je Gebiet (Box lat0, lat1, lon0, lon1; Flut-Bezugsrichtung). Gilt nur fuer unklare Saetze.
# Aermelkanal/Pas-de-Calais: SHOM/Admiralty "le flot porte a l'Est/NE" (fortschreitende Welle, Flutmaximum 0-45 Grad nach HW)
KONVENTION = [((48.6, 51.25, -6.0, 2.1), 60.0, 'Kanal: Flut setzt nach E/NE (SHOM/UKHO)')]


def kopf(r):
    L = open(os.path.join(ROOT, r['file']), encoding='iso-8859-1').read().split('\n')
    i = L.index(r['name'])
    a = i
    while a > 0 and L[a - 1].startswith('#'):
        a -= 1
    return '\n'.join(L[a:i])


def quelle_urteil(r, ax):
    """Flutrichtung aus der Quelle selbst -> ('richtig'|'drehen', Begruendung) oder (None, '')."""
    if ax is None:
        return None, ''
    blk = kopf(r)
    m = re.search(r'# flood (\d+) deg / ebb \d+ deg true \(page footer\)', blk)      # SHOA 3015 Fusszeile
    if m:
        c = math.cos(math.radians(ax - float(m.group(1))))
        return ('richtig' if c > 0 else 'drehen'), 'SHOA-Fusszeile flood %s' % m.group(1)
    if 'IWLS API predictions' in blk:        # 16.10.2026 alle gegen CHS wcp1-events (Flut/Ebbe-Extrema) geprueft
        return 'richtig', 'CHS-Ereignisse 16.10.'
    if 'LINZ tidal stream predictions (slack times)' in blk:     # Flut/Ebbe-Beginn aus LINZ
        return 'richtig', 'LINZ Flut-/Ebbebeginn'
    return None, ''


def konvention_urteil(r, ax):
    if ax is None or any(a <= r['lat'] <= b and c0 <= r['lon'] <= d0 for a, b, c0, d0 in OHNE_TPXO):
        return None, ''
    for (a, b, c0, d0), ref, warum in KONVENTION:
        if a <= r['lat'] <= b and c0 <= r['lon'] <= d0:
            c = math.cos(math.radians(ax - ref))
            if abs(c) >= 0.3:
                return ('richtig' if c > 0 else 'drehen'), warum
    return None, ''


def m2_info(r, ax=None):
    """(lat, lon, Achse, M2-Amplitude, M2-Greenwich-Phase) oder None."""
    try:
        _z, w, _e, mer = X.satz_lesen(r['file'], r['name'])
    except KeyError:
        return None
    ax = achse(r) if ax is None else ax
    if ax is None or 'M2' not in w or w['M2'][0] <= 0:
        return None
    return r['lat'], r['lon'], ax, w['M2'][0], X.greenwich(w['M2'][1], SPEED['M2'], mer) % 360


def nachbar_urteil(a, sicher):
    """Flutrichtung von sicher entschiedenen Nachbarsaetzen uebernehmen, wenn sie physikalisch denselben Strom
    zeigen (Achse und Phase je |cos| >= 0.7, Produkt >= NACHBAR_C, Amplitude Faktor <= 2).
    sicher: Liste (lat, lon, Flutrichtung, A, g). -> 'richtig' | 'drehen' | 'widerspruch' | None"""
    st = n = 0
    for b in sicher:
        if b is a or abs(b[0] - a[0]) > NACHBAR_KM / 100 or km(a[0], a[1], b[0], b[1]) > NACHBAR_KM:
            continue
        if not 0.5 <= a[3] / b[3] <= 2:
            continue
        ca, cg = math.cos(math.radians(a[2] - b[2])), math.cos(math.radians(a[4] - b[4]))
        if abs(ca) < 0.7 or abs(cg) < 0.7 or ca * cg < NACHBAR_C:
            continue
        st += 1 if ca > 0 else -1
        n += 1
    if n == 0:
        return None
    if abs(st) < n:
        return 'widerspruch'
    return 'richtig' if st > 0 else 'drehen'


def tpxo_urteil(r, k):
    """-> ('richtig'|'drehen'|None, Laufrichtung, Gradient, cos)."""
    ax, lr = achse(r), laufrichtung(k, r['lat'], r['lon'])
    if ax is None or lr is None:
        return None, None, None, None
    c = math.cos(math.radians(ax - lr[0]))
    if any(a <= r['lat'] <= b and c0 <= r['lon'] <= d0 for a, b, c0, d0 in OHNE_TPXO):
        return None, None, None, None
    if lr[1] < GRAD_MIN or abs(c) < COS_MIN:
        return None, round(lr[0]), round(lr[1], 2), round(c, 2)
    return ('richtig' if c > 0 else 'drehen'), round(lr[0]), round(lr[1], 2), round(c, 2)


def main(argv):
    fes = {k: nc.Dataset(os.path.join(FES_DIR, '%s_fes2022.nc' % k.lower())) for k in SPEED}
    alle = [r for r in load_records() if r['lat'] is not None]
    R = [r for r in alle if r['current']]
    T = [r for r in alle if not r['current']]
    pegel = (np.array([r['lat'] for r in T]), np.array([r['lon'] for r in T]), T)
    dateien = EICHUNG if '--eichen' in argv else GEPRUEFT
    zeilen = []
    info = {}
    for r in R:
        f = os.path.basename(r['file'])
        if f not in dateien:
            continue
        a = abstand(r, fes, pegel)
        if a is None:
            continue
        u = urteil(a[0], a[3])
        tu = lr = gr = cs = None
        quelle = ''
        if r['name'] in BEHALTEN:
            u = 'behalten'
        else:
            ax = achse(r)
            qu, quelle = quelle_urteil(r, ax)
            if qu:
                u = qu
            elif u == 'unklar':
                qu, quelle = konvention_urteil(r, ax)
                ds = [x for x in (a[0], a[3]) if x is not None]
                # nur wenn die eigene Phase dazu passt (Flutmaximum -120..+60 Grad um HW), sonst Wirbel/Bucht
                if qu == 'richtig' and all(-120 <= x <= 60 for x in ds) or \
                        qu == 'drehen' and all(x >= 60 or x <= -120 for x in ds):
                    u = qu
                else:
                    quelle = ''
        if u == 'unklar':
            tu, lr, gr, cs = tpxo_urteil(r, a[1])
        zeilen.append(dict(datei=f, name=r['name'], lat=r['lat'], lon=r['lon'], konst=a[1],
                           amp=round(a[2], 3), d=round(a[0], 1),
                           d2='' if a[3] is None else round(a[3], 1), urteil=u, bezug=a[4],
                           tpxo='' if tu is None else tu, laufrichtung='' if lr is None else lr,
                           grad='' if gr is None else gr, cos='' if cs is None else cs, nachbarn='', quelle=quelle))
        info[r['name']] = (r, m2_info(r))
    # Zweite Stufe: unklare Saetze gegen sicher entschiedene Nachbarn (Phasenfenster, NOAA/CHS-Eichsaetze)
    if '--eichen' not in argv:
        sicher = []
        for r in R:
            if os.path.basename(r['file']) in EICHUNG:
                m = m2_info(r)
                if m:
                    sicher.append(m)
        for z in zeilen:
            m = info[z['name']][1]
            if m and z['urteil'] in ('richtig', 'drehen'):
                sicher.append(m if z['urteil'] == 'richtig' else (m[0], m[1], (m[2] + 180) % 360, m[3], (m[4] + 180) % 360))
        for z in zeilen:
            if z['urteil'] != 'unklar':
                continue
            m = info[z['name']][1]
            nu = nachbar_urteil(m, sicher) if m else None
            z['nachbarn'] = nu or ''
            tu = z['tpxo'] or None
            nu = nu if nu in ('richtig', 'drehen') else None
            fort = None
            if z['grad'] != '' and float(z['grad']) >= FORT_GRAD and abs(float(z['cos'])) >= FORT_COS:
                ds = [x for x in (z['d'], z['d2']) if x != '']
                p = 'richtig' if float(z['cos']) > 0 else 'drehen'
                if p == 'richtig' and all(-60 <= x <= 60 for x in ds) or p == 'drehen' and all(abs(x) >= 120 for x in ds):
                    fort = p
            if tu and not nu and not fort and float(z['grad']) < GRAD_ALLEIN:
                tu = None                        # schwacher Gradient allein reicht nicht
            if not tu and fort:
                tu = fort
                z['quelle'] = 'fortschreitende Welle'
            if tu and nu and tu != nu:
                z['urteil'] = 'unklar'           # Widerspruch TPXO/Nachbarn
            elif tu or nu:
                z['urteil'] = tu or nu
    d = np.array([z['d'] for z in zeilen])
    print(len(zeilen), 'Saetze', collections.Counter(z['urteil'] for z in zeilen))
    h, kanten = np.histogram(d, bins=12, range=(-180, 180))
    for n, k0 in zip(h, kanten):
        print('  %+5.0f..%+5.0f  %4d %s' % (k0, k0 + 30, n, '#' * (n // 5)))
    if '--eichen' in argv:
        return zeilen
    heute = dt.date.today().strftime('%Y%m%d')
    out = os.path.join(HILFE, 'flutrichtung_%s.csv' % heute)
    with open(out, 'w', newline='', encoding='utf-8') as fh:
        wr = csv.DictWriter(fh, fieldnames=list(zeilen[0].keys()))
        wr.writeheader()
        wr.writerows(zeilen)
    print('->', out)
    return zeilen


def drehen(zeilen):
    """Saetze mit Urteil 'drehen': Phasen +180, Z0 negiert, Achse +180, Notiz."""
    import re
    pro = collections.defaultdict(set)
    for z in zeilen:
        if z['urteil'] == 'drehen':
            pro[z['datei']].add(z['name'])
    for f, namen in sorted(pro.items()):
        pfad = next(os.path.join(ROOT, p) for p in active_files() if os.path.basename(p) == f)
        L = open(pfad, encoding='iso-8859-1').read().split('\n')
        n = 0
        for i in reversed([k for k, l in enumerate(L) if l in namen]):
            a = i
            while a > 0 and L[a - 1].startswith('#'):
                a -= 1
            # Kommentarkopf vor BEGIN HOT COMMENTS gehoert mit zum Satz
            while a > 0 and (L[a - 1].startswith('#') or not L[a - 1].strip()) and 'End congen' not in L[a - 1]:
                a -= 1
            for k in range(a, i):
                fe = re.match(r'# (flood_dir|ebb_dir): (\d+)\s*$', L[k])
                if fe:   # Flut- und Ebbrichtung tauschen
                    L[k] = '# %s: %03d' % (fe.group(1), (int(fe.group(2)) + 180) % 360)
                    continue
                m = re.match(r'(# Major axis: |# major_axis_deg_true: )([-\d.]+)(.*)', L[k])
                if m:
                    L[k] = '%s%.1f%s' % (m.group(1), (float(m.group(2)) + 180) % 360, m.group(3))
            z0 = L[i + 2].split()
            L[i + 2] = '%.4f %s' % (-float(z0[0]), ' '.join(z0[1:]))
            k = i + 3
            while k < len(L) and L[k].strip() and not L[k].startswith('#'):
                f3 = L[k].split()
                if f3[0] != 'x':                 # Platzhalter "x 0 0" unveraendert lassen
                    L[k] = '%-15s %s  %.2f' % (f3[0], f3[1], (float(f3[2]) + 180) % 360)
                k += 1
            L.insert(i, '# note: ' + dt.date.today().strftime('%Y%m%d') + ' Vorzeichen gedreht, damit XTide-Flood der Flutstrom ist '
                        '(Phase gegen den Wasserstand, py/flutrichtung_pruefen.py)')
            n += 1
        open(pfad, 'w', encoding='iso-8859-1').write('\n'.join(L))
        print('  %-45s %d Saetze gedreht' % (f, n))


if __name__ == '__main__':
    z = main(sys.argv)
    if '--schreiben' in sys.argv:
        drehen(z)
