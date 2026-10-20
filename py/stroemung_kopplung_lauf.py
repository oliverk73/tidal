#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Kurze Stroemungsreihen ohne K2 mit gekoppelten Nachbartiden neu fitten (Oliver 20.10.2026).

Fuer jeden Satz in harmonics_utide_current_observations.txt ohne K2: Rohreihe holen (BODC-QXF,
RWS-CSV, MDE-Pickles in currents/UK_MDE/_arbeit/), mit allen Tiden des alten Satzes frei und
K2->S2, P1->K1 (unter 27,6 Tagen auch N2->M2) gekoppelt fitten (py/stroemung_kopplung.py).
Ersetzt werden nur die Konstanten, Z0 und die R^2-Zeile; dazu eine Notiz. Weicht M2 um mehr
als 15 % oder 15 Grad vom alten Satz ab, bleibt der Satz und wird gemeldet.

Usage: venv/bin/python py/stroemung_kopplung_lauf.py [--schreiben]
"""
import os
import pickle
import re
import sys
from datetime import date

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'rws_currents'))
import bodc_stroemung as B                                          # noqa: E402
import health_check as hc                                           # noqa: E402
import sicher_schreiben                                             # noqa: E402
import stroemung_kopplung as K                                      # noqa: E402
from generate_germany_harmonics_175 import CONSTITUENTS_175         # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATEI = os.path.join(ROOT, 'harmonics/utide/harmonics_utide_current_observations.txt')
ARB = os.path.join(ROOT, 'currents/UK_MDE/_arbeit/')
# MDE: Namensanfang -> (Pickle, Schluessel)
MDE = {'Hunstanton (': ('anglia.pkl', 'BM1 - The Wash'), 'Blakeney (': ('anglia.pkl', 'BM2 - Wells'),
       'Felixstowe (': ('anglia.pkl', 'BM4 - Deben'), 'Walton-on-the-Naze (': ('anglia.pkl', 'BM5 - Walton-on-the-Naze'),
       'Clacton-on-Sea (': ('anglia.pkl', 'BM6 - Clacton-on-Sea'), 'West Mersea (': ('anglia.pkl', 'BM7 - Blackwater_Colne_Pyefleet'),
       'Southend-on-Sea (': ('anglia.pkl', 'BM9 - Southend West'), "St David's Head (": ('stdavids.pkl', 'St Davids'),
       'Egilsay (': ('westray.pkl', 'Site 3'), 'Portnahaven (': ('islay.pkl', 'DP2'), 'Cantick Head (': ('brims.pkl', 'ST008'),
       'Brims (': ('brims2.pkl', 'Site22'), 'Fall of Warness (': ('orkney.pkl', 'FoW13'), 'Kylerhea (': ('kyle.pkl', 'K2'),
       'The Skerries (': ('skerries.pkl', 'S2'), 'Fair Head (': [('fairhead.pkl', 'L1'), ('fairhead.pkl', 'L4')],
       'Swanage (20 km SE': ('aeltere.pkl', 'Swanage (20 km SE'), 'Swanage (22 km SSE': ('aeltere.pkl', 'Swanage (22 km SSE'),
       'Worthing (': ('aeltere.pkl', 'Worthing ('), 'Brighton (': ('aeltere.pkl', 'Brighton ('),
       'Lundy (24 km N': ('aeltere.pkl', 'Lundy (24 km N'), 'Ilfracombe (24 km WNW': ('aeltere.pkl', 'Ilfracombe (24 km WNW'),
       'Skomer (96 km SW': ('aeltere.pkl', 'Skomer (96 km SW'), 'Padstow (71 km NW': ('aeltere.pkl', 'Padstow (71 km NW')}
NAMEN175 = [n for n, _ in CONSTITUENTS_175]
_PK = {}


def mde_reihe(name):
    teile = next((v for p, v in MDE.items() if name.startswith(p)), None)
    if teile is None:
        return None
    dfs = []
    for p, k in (teile if isinstance(teile, list) else [teile]):
        if p not in _PK:
            _PK[p] = pickle.load(open(ARB + p, 'rb'))
        dfs.append(_PK[p][k]['df'])
    df = pd.concat(dfs).sort_index()
    return df[~df.index.duplicated()]


def bodc_reihe(M, text, la, lo):
    g = re.search(r'deployments combined, BODC refs (\d+)\.\.(\d+)', text)
    liste = re.search(r'deployments combined, BODC refs ([\d ]+)$', text, re.M)
    b = re.search(r'# bodc_ref: BODC(\d+)', text)
    if g:
        refs = [r for r, m in M.items() if int(g.group(1)) <= int(r) <= int(g.group(2))
                and hc.km(dict(lat=la, lon=lo), dict(lat=float(m['Latitude A']), lon=float(m['Longitude A']))) < 1.5]
    elif liste:
        refs = liste.group(1).split()
    elif b:
        refs = [b.group(1)]
    else:
        return None
    dfs = []
    for r in refs:
        if r not in M:
            continue
        m = M[r]
        x = B.reihe(os.path.join(m['_dir'], 'b%07d.qxf' % int(r)), float(m['Sea floor depth (m)'] or 'nan'))
        if x and len(x[0]) >= (B.MIN_STUNDEN if len(refs) > 1 else 300):
            dfs.append(x[0])
    if not dfs:
        return None
    df = pd.concat(dfs).sort_index()
    return df[~df.index.duplicated()]


def rws_reihe(text):
    import fit2
    c = re.search(r'# rws_loccode: (\S+)', text).group(1)
    p = re.search(r'period=(\d{4}-\d\d-\d\d)\.\.(\d{4}-\d\d-\d\d)', text)
    for pfad in (os.path.join(ROOT, 'currents/Netherlands/%s.csv' % c), os.path.join(ROOT, 'currents/Netherlands/GAP_%s.csv' % c)):
        if os.path.exists(pfad):
            df = fit2.load(pfad)
            df = df.loc[p.group(1):p.group(2) + ' 23:59']
            u, v, t = fit2.to_scalar(df, fit2.infer_scale(df['speed'].abs().values))
            return pd.DataFrame({'u': u, 'v': v}, index=pd.DatetimeIndex(t))
    return None


def main(argv):
    L = open(DATEI, encoding='iso-8859-1').read().split('\n')
    M = B.metadaten()
    st = [k for k in range(len(L) - 1) if L[k] and not L[k].startswith('#') and hc.MERIDIAN.match(L[k + 1])]
    vorher, aend, gemeldet = 0, [], []
    for k in st:
        kopf = L[vorher:k]
        vorher = k
        text = '\n'.join(kopf)
        slots = L[k + 3:k + 3 + len(NAMEN175)]
        alt = {}
        for n, z in zip(NAMEN175, slots):
            f = z.split()
            if f[0] != 'x':
                assert f[0] == n, (L[k], n, z)
                alt[n] = (float(f[1]), float(f[2]))
        if 'K2' in alt or 'short-series' in text or '20261020 refit' in text:
            continue
        assert L[k + 1].startswith('+00:00'), L[k + 1]
        la = float(re.search(r'# !latitude: (\S+)', text).group(1))
        lo = float(re.search(r'# !longitude: (\S+)', text).group(1))
        if 'BODC current meter' in text:
            df = bodc_reihe(M, text, la, lo)
        elif 'Rijkswaterstaat' in text:
            df = rws_reihe(text)
        elif '# mde_id:' in text:
            df = mde_reihe(L[k])
        else:
            continue
        if df is None or len(df) < 300:
            gemeldet.append(('keine Rohreihe', L[k]))
            continue
        tage = (df.index[-1] - df.index[0]).total_seconds() / 86400
        stunden = df.index.floor('1h').nunique()
        paare = []
        if tage < 182.6 or stunden < 4380:
            paare += [('S2', 'K2'), ('K1', 'P1')]
        if tage < 27.6:
            paare += [('M2', 'N2')]
        rat, pn, km = K.verhaeltnisse(la, lo, 150.0 if any(paare) else 1e9)
        if rat is None:
            rat, pn, km = K.verhaeltnisse(la, lo, 300.0)        # Hochsee: K2/S2 aendert sich langsam
        if rat is None:
            gemeldet.append(('kein Pegel bis 150 km', L[k]))
            continue
        kop = {b: (h, rat[b][0], rat[b][1]) for h, b in paare if h in alt}
        frei = list(alt) + ([] if paare else ['K2', 'P1'])     # ueber ein halbes Jahr: K2/P1 frei dazu
        r = K.fit(df, frei, kop)
        m2a, m2n = alt.get('M2', (0, 0)), r['konst'].get('M2', (0, 0))
        dphi = abs((m2n[1] - m2a[1] + 180) % 360 - 180)
        flip = dphi > 90                                  # Achse andersherum: alle Phasen +180
        if flip:
            r['konst'] = {n: (a, (p + 180) % 360) for n, (a, p) in r['konst'].items()}
            r['mean'] = -r['mean']
            m2n = r['konst']['M2']; dphi = abs((m2n[1] - m2a[1] + 180) % 360 - 180)
        damp = abs(m2n[0] / m2a[0] - 1) if m2a[0] else 1
        zeile = '%-70s %3.0f d  K2 %.2f (S2 %.2f->%.2f) P1 %.2f  M2 %+.0f%% %+.0f Grad  r2 %.3f  %s %.0f km' % (
            L[k][:70], tage, r['konst'].get('K2', (0, 0))[0], alt.get('S2', (0, 0))[0], r['konst'].get('S2', (0, 0))[0],
            r['konst'].get('P1', (0, 0))[0], 100 * (m2n[0] / m2a[0] - 1) if m2a[0] else 0, dphi, r['r2'], pn.split(',')[0], km)
        if damp > 0.15 or dphi > 15:
            gemeldet.append(('M2 weicht ab', zeile))
            continue
        print(zeile, flush=True)
        aend.append((k, r, pn, km, [b for _h, b in paare if b in kop]))
    for k, r, pn, km, gek in reversed(aend):
        for j, n in enumerate(NAMEN175):
            a = r['konst'].get(n)
            L[k + 3 + j] = '%-15s %.4f  %.2f' % (n, a[0], a[1]) if a and a[0] >= 0.00005 else 'x 0 0'
        L[k + 2] = '%.4f knots' % r['mean']
        j = k - 1
        while j > 0 and L[j].startswith('#'):
            if L[j].startswith('# R^2 = '):
                L[j] = '# R^2 = %.4f, RMS error = %.4f knots (refit 20261020, coupled constituents)' % (r['r2'], r['rms'])
            j -= 1
            L.insert(k, ('# note: 20261020 refit, %s coupled to %s by ratio/lag of %s (%.0f km): series < 6 months' % (
            '/'.join(gek), '/'.join({'K2': 'S2', 'P1': 'K1', 'N2': 'M2'}[b] for b in gek), pn.split(',')[0][:40], km)) if gek
            else '# note: 20261020 refit with K2 and P1 added (combined deployments span more than 6 months)')
    print('\n%d Saetze neu gefittet' % len(aend))
    for g, z in gemeldet:
        print('GEMELDET', g, '|', z)
    if '--schreiben' in argv:
        sicher_schreiben.schreiben(DATEI, '\n'.join(L))


if __name__ == '__main__':
    main(sys.argv[1:])
