#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PNG-Nebenhaefen: welche Methode trifft Mess-/Amtssaetze besser? (8.11.2026, Oliver: objektive Kriterien)

Methoden je AHO-Nebenhafen (py/aho_png_neben.py):
  T  = Uebertragung vom Standardhafen-Tafelfit (Zeitunterschied + Pegelzerlegung)
  F  = FES2022 roh an der Buchposition
  FG = FES2022 geeicht wie py/fes_neu_geeicht.py (3 naechste Referenzen <= 200 km mit FES < 6 %),
       Leave-one-out: der Pruefsatz und alles <= 2 km davon bleibt aus der Eichung.
Wahrheit: Saetze aus Messung/amtlicher Tafel (REF_DATEI wie luecken_fes_welt) <= RADIUS km, deren Kopf weder
FES noch AHO nennt (AHO-Standardhafen-Saetze sind die Quelle der Uebertragung selbst).
Fehler = health_check.curve_diff (relativ zum Hub, wie ueberall im Bestand).

Usage: venv/bin/python py/png_methodenvergleich.py [RADIUS_KM]
"""
import cmath
import math
import os
import statistics as st
import sys

import netCDF4 as nc

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import aho_png as A                                                # noqa: E402
import aho_png_neben as N                                          # noqa: E402
import health_check as H                                           # noqa: E402
import qld_msq_fit as Q                                            # noqa: E402
from fes_ersatz_inseln import sample, stem, FES_DIR                # noqa: E402
from luecken_fes_welt import REF_DATEI                             # noqa: E402

RADIUS = float(sys.argv[1]) if len(sys.argv) > 1 else 5.0
REF_ANZAHL, REF_KM, REF_GUETE = 3, 200.0, 6.0
EICH = ('M2', 'S2', 'N2', 'K2', 'K1', 'O1', 'P1', 'Q1')
GRUPPE = {'S2': 'S2', 'K2': 'S2', 'M2': 'M2', 'N2': 'M2', 'K1': 'K1', 'P1': 'K1', 'O1': 'O1', 'Q1': 'O1'}

ds = {}


def fes(c, la, lo):
    p = os.path.join(FES_DIR, '%s_fes2022.nc' % stem(c))
    if not os.path.exists(p):
        return None
    if c not in ds:
        ds[c] = nc.Dataset(p)
    a, g = sample(ds[c], la, lo)
    return cmath.rect(a, math.radians(g)) if a else None


def kopf(r, cache={}):
    if r['file'] not in cache:
        cache[r['file']] = open(r['file'], encoding='iso-8859-1').read().split('\n')
    T = cache[r['file']]
    i = T.index(r['name'])
    a = i
    while a > 0 and T[a - 1].startswith('#'):
        a -= 1
    return '\n'.join(T[a:i])


def vek(r):
    """z aus load_records: a*e^(-ig) -> Greenwich-Vektor a*e^(+ig) wie FES."""
    return {c: r['z'][c].conjugate() for c in H.MAIN if c in r['z'] and abs(r['z'][c]) > 0}


def fes_geeicht(la, lo, refs, ohne):
    nah = [x for x in refs if not any(H.km(x[0], o) <= 2 for o in ohne)]
    nah = sorted(nah, key=lambda x: H.km({'lat': la, 'lon': lo}, x[0]))[:REF_ANZAHL]
    nah = [x for x in nah if H.km({'lat': la, 'lon': lo}, x[0]) <= REF_KM]
    eich = {}
    for c in H.MAIN:
        fa, dg = [], []
        for r, v, _f in nah:
            m = fes(c, r['lat'], r['lon'])
            if c in v and m:
                fa.append(abs(v[c]) / abs(m))
                dg.append((math.degrees(cmath.phase(v[c] / m)) + 180) % 360 - 180)
        if fa:
            eich[c] = (st.median(fa), st.median(dg))
    w = {}
    for c in H.MAIN:
        m = fes(c, la, lo)
        if m:
            e = eich.get(c) or eich.get(GRUPPE.get(c, ''), (1.0, 0.0))
            w[c] = (abs(m) * e[0], (math.degrees(cmath.phase(m)) + e[1]) % 360)
    return Q.rec(w), nah


def main():
    rows, std_pegel = N.tabelle()
    for r in rows:
        if r['no'] in N.POS:
            r['lat'], r['lon'] = N.POS[r['no']]
    fits = A.fit_alle({k: v for k, v in A.lesen().items() if k in N.STD.values()})
    alle = [r for r in H.load_records() if not r['current'] and r['lat'] and -15 < r['lat'] < 3 and 135 < r['lon'] < 165]
    # Referenzen fuer die FES-Eichung (wie fes_neu_geeicht.py, aber regional)
    refs = []
    for r in alle:
        if 'fes2022' in r['file'] or 'secondary' in r['file'] or not REF_DATEI.search(os.path.basename(r['file'])):
            continue
        if 'FES' in kopf(r):
            continue
        v = vek(r)
        f = {c: fes(c, r['lat'], r['lon']) for c in ('M2', 'S2', 'N2', 'K1', 'O1')}
        cs = [c for c in f if f[c] and c in v]
        if 'M2' not in cs:
            continue
        fe = 100 * math.sqrt(sum(abs(v[c] - f[c]) ** 2 for c in cs) / 2) / max(0.15, sum(abs(v[c]) for c in cs))
        if fe < REF_GUETE:
            refs.append((r, v, fe))
    wahr = [r for r in alle if REF_DATEI.search(os.path.basename(r['file'])) and 'fes2022' not in r['file']
            and 'secondary' not in r['file'] and 'FES' not in kopf(r) and 'AHO' not in kopf(r)]
    print('%d Referenzen fuer die Eichung, %d Wahrheitssaetze im Gebiet, Radius %.0f km' % (len(refs), len(wahr), RADIUS))
    erg = []
    for s in rows:
        u = N.uebertragen(fits[N.STD[s['std']]]['w'], std_pegel[s['std']], s)
        if not u:
            continue
        T = Q.rec(u[0])
        F =Q.rec({c: (abs(m), math.degrees(cmath.phase(m)) % 360) for c in H.MAIN for m in [fes(c, s['lat'], s['lon'])] if m})
        for w in wahr:
            d = H.km(s, w)
            if d > RADIUS:
                continue
            FG, nah = fes_geeicht(s['lat'], s['lon'], refs, [w])
            e = dict(no=s['no'], name=s['name'], std=s['std'], km=d, w=w,
                     T=100 * H.curve_diff(T, w)[1], F=100 * H.curve_diff(F, w)[1], FG=100 * H.curve_diff(FG, w)[1],
                     TF=100 * H.curve_diff(T, F)[1])
            erg.append(e)
    print()
    print('%-5s %-22s %-14s %4s  %5s %5s %5s  %5s  %s' % ('Nr', 'Nebenhafen', 'Standard', 'km', 'Ueb', 'FES', 'FESg', 'Ueb-F', 'Wahrheit'))
    for e in sorted(erg, key=lambda e: (e['std'], e['T'])):
        print('%-5s %-22s %-14s %4.1f  %4.0f%% %4.0f%% %4.0f%%  %4.0f%%  %s [%s]' % (
            e['no'], e['name'][:22], e['std'][:14], e['km'], e['T'], e['F'], e['FG'], e['TF'],
            e['w']['name'].split(',')[0][:24], os.path.basename(e['w']['file'])[:28]))
    print()
    print('Median je Standardhafen-Gruppe (Fehler gegen Wahrheit):')
    for g in sorted({e['std'] for e in erg}) + ['ALLE']:
        E = [e for e in erg if g in ('ALLE', e['std'])]
        print('  %-18s n=%2d  Uebertragung %4.1f %%  FES roh %4.1f %%  FES geeicht %4.1f %%   Uebertragung besser: %d/%d' % (
            g, len(E), st.median(e['T'] for e in E), st.median(e['F'] for e in E), st.median(e['FG'] for e in E),
            sum(e['T'] < e['FG'] for e in E), len(E)))
    return erg


if __name__ == '__main__':
    main()
