#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""VHO-Vietnam-Saetze nur aus sauberen Jahrgaengen neu rechnen.

py/fit_vho_vietnam.py fittete 2022-2025 gemeinsam und schloss nur einzelne,
von Hand gefundene Jahre aus. Stichprobe 17.09.2026, jeder Jahrgang einzeln
gefittet (CONSTIT_67): 2022-2024 passen an den meisten Stationen auf 3-44 mm,
2025 an ALLEN 17 Stationen nur auf 32-158 mm -- dazu Hon Dau 2022, Da Nang
und Hong Gai 2024. Ein Jahrgang, der sich selbst nicht fitten laesst, ist
kaputt (verschobene oder fremde Seiten); im gemeinsamen Fit verdarb er die
Konstanten (Satz-rms bis 70 mm).

Regel: Ein Jahrgang zaehlt, wenn er mindestens 300 Tage hat, sein Einzel-rms
hoechstens 1.5 x (bester Jahrgang) + 5 mm ist UND sein M2 zum Median der
Jahrgaenge passt (Phase bis 5 Grad, Amplitude bis 5 %). Die zweite Bedingung
braucht es fuer Cua Gianh 2022: in sich stimmig, aber um ~100 Grad verdreht.
Gefittet wird wie damals (CONSTIT_67, Zeiten UTC+7 -> UTC), ersetzt nur der
Zahlenteil des Satzes (Suche ueber "# vho_slug:"), dazu Vermerk und neue
utide-Zeile.

Usage: venv/bin/python3 py/vho_jahrgaenge_neufit.py [--schreiben]
"""
from __future__ import annotations

import datetime as dt
import glob
import json
import os
import re
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from health_check import MERIDIAN, ROOT                             # noqa: E402

DIR = os.path.join(ROOT, 'water_levels/VN_vho')
ZIEL = os.path.join(ROOT, 'harmonics/utide/harmonics_utide_tidetables.txt')


def reihe(pfad):
    d = json.load(open(pfad))
    t, v, y = [], [], []
    for tag, rec in sorted(d.items()):
        if tag.startswith('_') or not rec:
            continue
        basis = dt.datetime.fromisoformat(tag)
        for h, m in enumerate(rec['hourly_m']):
            if m is not None:
                t.append(basis + dt.timedelta(hours=h - 7))
                v.append(float(m))
                y.append(basis.year)
    return np.array(t), np.array(v), np.array(y)


def fit(t, v, lat):
    import utide
    from batch_utide_uk_tidetimes import CONSTIT_67
    c = utide.solve(t, v, lat=lat, nodal=True, trend=False, method='ols', conf_int='none',
                    verbose=False, constit=CONSTIT_67)
    res = v - utide.reconstruct(t, c, verbose=False)['h']
    return c, float(np.sqrt(np.mean(res ** 2))), 1 - float(np.var(res)) / float(np.var(v))


def main(argv):
    import dmi_tidevand as D
    import sicher_schreiben
    from add_uhslc_harmonics import CONSTITUENTS_175
    zeilen = open(ZIEL, encoding='iso-8859-1').read().split('\n')
    heute = f'{dt.date.today():%Y%m%d}'
    n = 0
    for pfad in sorted(glob.glob(os.path.join(DIR, '*_2022-01-01_2026-06-30.json'))):
        slug = os.path.basename(pfad).split('_')[0]
        j = next((i for i, l in enumerate(zeilen) if l.strip() == f'# vho_slug: {slug}'), None)
        if j is None:
            print(f'{slug:14} kein Satz im Bestand (Messsatz vorhanden) -- uebersprungen')
            continue
        k = j + 1
        while zeilen[k].startswith('#'):
            k += 1
        a = j
        while zeilen[a - 1].startswith('#'):
            a -= 1
        kopf = zeilen[a:k]
        lat = float(next(x for x in kopf if x.startswith('# !latitude:')).split(':')[1])
        t, v, y = reihe(pfad)
        einzel, m2 = {}, {}
        for jahr in sorted(set(y)):
            s = y == jahr
            if s.sum() >= 300 * 24:
                c_j, einzel[jahr], _r = fit(t[s], v[s], lat)
                w_j = D.werte_aus(c_j)
                m2[jahr] = w_j['M2']
        bester = min(einzel.values())
        gut = [jahr for jahr, r in einzel.items() if r <= 1.5 * bester + 0.005]
        # Bezug ist der Jahrgang, dem die meisten anderen zustimmen (ein Mittelwert
        # wuerde von einem verdrehten Jahr mitgezogen)
        def passt(i, j):
            return (abs((m2[i][1] - m2[j][1] + 180) % 360 - 180) <= 5
                    and abs(m2[i][0] / m2[j][0] - 1) <= 0.05)
        bezug = max(gut, key=lambda i: sum(passt(i, j) for j in gut))
        gut = [j for j in gut if passt(bezug, j)]
        s = np.isin(y, gut)
        coef, rms, r2 = fit(t[s], v[s], lat)
        w = D.werte_aus(coef)
        ende = k + 3
        while ende < len(zeilen) and zeilen[ende].strip() and not zeilen[ende].startswith('#'):
            ende += 1
        alt = {x.split()[0]: (float(x.split()[1]), float(x.split()[2]))
               for x in zeilen[k + 3:ende] if not x.startswith('x ')}
        alt_rms = re.search(r'rms=([\d.]+)m', ' '.join(kopf))
        am2, ag2 = alt.get('M2', (0, 0))
        dg = (w['M2'][1] - ag2 + 180) % 360 - 180
        print(f"{slug:14} Jahre {'/'.join(map(str, gut)):19} (raus: {'/'.join(str(x) for x in einzel if x not in gut) or '-':9}) "
              f"rms {alt_rms.group(1) if alt_rms else '?'} -> {rms:.4f}  M2 {am2:.3f}/{ag2:5.1f} -> "
              f"{w['M2'][0]:.3f}/{w['M2'][1]:5.1f} ({dg:+.1f} Grad)", flush=True)
        neu = [f"{float(coef['mean']):.4f} meters"] + [
            f'{cn:15s} {w[cn][0]:.4f}  {w[cn][1]:.2f}' if cn in w and w[cn][0] >= 0.00005 else 'x 0 0'
            for cn, _sp in CONSTITUENTS_175]
        if len(neu) != ende - (k + 2):
            print('   Aufbau weicht ab -- uebersprungen')
            continue
        zeilen[k + 2:ende] = neu
        tt = t[s]
        for i in range(a, k):
            if zeilen[i].startswith('# utide:'):
                zeilen[i] = (f"# utide: pts={len(tt)} period={tt[0]:%Y-%m-%d}..{tt[-1]:%Y-%m-%d} "
                             f"r2={r2:.4f} rms={rms:.4f}m const={sum(1 for c, _ in CONSTITUENTS_175 if c in w)}")
        einf = next(i for i in range(a, k) if zeilen[i].startswith('# !units:'))
        zeilen.insert(einf, f"# note: {heute} neu gefittet nur aus sauberen Jahrgaengen {'/'.join(map(str, gut))}; "
                            f"2025 u.a. liessen sich einzeln nicht fitten (py/vho_jahrgaenge_neufit.py).")
        n += 1
    if '--schreiben' in argv and n:
        sicher_schreiben.schreiben(ZIEL, '\n'.join(zeilen))
        print(f'{n} Saetze geschrieben')
    else:
        print('(nur Probe; mit --schreiben eintragen)')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
