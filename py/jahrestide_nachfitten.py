#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Rechnet SHOM- und FCUL-Jahresfits mit Jahrestide SA/SSA neu.

Stichprobe 17.09.2026: Die SHOM-Vorhersagen (5-min-Reihen in
water_levels/France_SHOM/shom_raw/) und die FCUL-Stundentafeln
(water_levels/Portugal_FCUL/*_AH.TXT) enthalten den jahreszeitlichen
Wasserstand (Monatsmittel 7-17 cm Spanne). Die urspruenglichen Fits
(py/scrape_shom_*.py, py/parse_fcul_portugal.py) liessen UTide die
Partialtiden waehlen; bei knapp einem Jahr faellt SA unter die
Rayleigh-Grenze und fehlte in allen 312 Saetzen. Beyrouth: Rest 37 mm ohne,
4 mm mit SA.

Gerechnet wird wie damals (constit='auto', OLS, nodal), nur mit SA und SSA
erzwungen. Ersetzt wird allein der Zahlenteil des Satzes; Name, Position und
Kopf bleiben, die utide-Zeile bekommt die neuen Kennzahlen, dazu ein Vermerk.

Zweiter Durchgang (17.09.2026, --rayleigh): Die Rohreihen umfassen 359 Tage,
knapp unter der Rayleigh-Grenze fuer T2/S2 und R2/S2. Mit Rayleigh_min=0.9
kommen T2, R2 und fuenf weitere hinzu; Rest Agadir 17 -> 7 mm, Trebeurden
68 -> 49 mm, Lesconil 29 -> 21 mm (Granville 129 -> 112 mm).

Sicherung gegen Fehlgriffe: Aendert sich M2 um mehr als 2 % oder 2 Grad,
wird der Satz nicht angefasst und gemeldet -- dann passt die Rohreihe nicht
mehr zum Satz (z.B. nachtraeglich korrigierte Zeit).

Usage: venv/bin/python3 py/jahrestide_nachfitten.py [--schreiben] [--nur SHOM|FCUL] [--rayleigh]
"""
from __future__ import annotations

import datetime as dt
import os
import re
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from health_check import MERIDIAN, ROOT                             # noqa: E402

ZIEL = os.path.join(ROOT, 'harmonics/utide/harmonics_utide_tidetables.txt')
SHOM = os.path.join(ROOT, 'water_levels/France_SHOM/shom_raw')
FCUL = os.path.join(ROOT, 'water_levels/Portugal_FCUL')
FCUL_DATEI = {'Aveiro': 'AveiroFCUL_AH.TXT', 'FigueiraDaFoz': 'FigueiraFCUL_AH.TXT',
              'Sesimbra': 'Sesimbra_AH.TXT', 'FaroOlhao': 'FaroFCUL_AH.TXT',
              'Setubal': 'SetubalFCUL_AH.TXT', 'VilaRealStAntonio': 'VilaRealFCUL_AH.TXT'}


def reihe(art, kennung):
    if art == 'SHOM':
        import pandas as pd
        df = pd.read_csv(os.path.join(SHOM, f'{kennung}.csv'), parse_dates=['datetime_utc'])
        return df['datetime_utc'].values.astype('datetime64[s]').astype('O'), df['level_m'].values
    import parse_fcul_portugal as F
    from pathlib import Path
    t, v = F.parse_fcul(Path(FCUL) / FCUL_DATEI[kennung])
    return t.astype('M8[s]').astype('O'), v


def fit(t, v, lat, rmin=1.0):
    import utide
    kw = dict(lat=lat, nodal=True, trend=False, method='ols', conf_int='none', verbose=False)
    auto = utide.solve(t, v, constit='auto', Rayleigh_min=rmin, **kw)
    liste = [n.strip() for n in auto['name']]
    liste += [x for x in ('SA', 'SSA') if x not in liste]
    coef = utide.solve(t, v, constit=liste, **kw)
    res = v - utide.reconstruct(t, coef, verbose=False)['h']
    return coef, float(np.sqrt(np.mean(res ** 2))), 1 - float(np.var(res)) / float(np.var(v))


def main(argv):
    import dmi_tidevand as D
    import sicher_schreiben
    from add_uhslc_harmonics import CONSTITUENTS_175
    nur = argv[argv.index('--nur') + 1] if '--nur' in argv else None
    rayleigh = '--rayleigh' in argv
    marke = 'Rayleigh 0.9' if rayleigh else 'Jahrestide SA/SSA'
    zeilen = open(ZIEL, encoding='iso-8859-1').read().split('\n')
    heute = f'{dt.date.today():%Y%m%d}'
    faelle = []
    for j, l in enumerate(zeilen):
        m = re.match(r'# station_id_context: (SHOM|FCUL)-(\S+)\s*$', l)
        if m and (not nur or m.group(1) == nur):
            faelle.append((m.group(1), m.group(2)))
    print(f'{len(faelle)} Saetze', flush=True)
    ok = gemeldet = 0
    for nr, (art, kennung) in enumerate(faelle, 1):
        # Position im (durch Einfuegungen verschobenen) Text jedes Mal neu suchen
        j = next(i for i, l in enumerate(zeilen) if l.strip() == f'# station_id_context: {art}-{kennung}')
        k = j + 1
        while zeilen[k].startswith('#'):
            k += 1
        if not MERIDIAN.match(zeilen[k + 1]):
            print(f'  {kennung}: Satzzeile nicht gefunden')
            gemeldet += 1
            continue
        a = j
        while zeilen[a - 1].startswith('#'):
            a -= 1
        kopf = zeilen[a:k]
        if any(marke in x for x in kopf):
            continue
        lat = float(next(x for x in kopf if x.startswith('# !latitude:')).split(':')[1])
        ende = k + 3
        while ende < len(zeilen) and zeilen[ende].strip() and not zeilen[ende].startswith('#'):
            ende += 1
        alt = {x.split()[0]: (float(x.split()[1]), float(x.split()[2]))
               for x in zeilen[k + 3:ende] if not x.startswith('x ')}
        try:
            t, v = reihe(art, kennung)
            coef, rms, r2 = fit(t, v, lat, 0.9 if rayleigh else 1.0)
        except Exception as e:
            print(f'  {zeilen[k][:40]}: {e}')
            gemeldet += 1
            continue
        w = D.werte_aus(coef)
        neu = [f"{float(coef['mean']):.4f} meters"] + [
            f'{cn:15s} {w[cn][0]:.4f}  {w[cn][1]:.2f}' if cn in w and w[cn][0] >= 0.00005 else 'x 0 0'
            for cn, _sp in CONSTITUENTS_175]
        erwartet = [cn for cn, _ in CONSTITUENTS_175]
        alt_namen = [x.split()[0] for x in zeilen[k + 3:ende]]
        if len(neu) != ende - (k + 2) or any(n != 'x' and n != erwartet[i] for i, n in enumerate(alt_namen)):
            print(f'  {zeilen[k][:40]}: Aufbau des Satzes weicht ab -- uebersprungen')
            gemeldet += 1
            continue
        am2, gm2 = alt.get('M2', (0, 0))
        nm2, ng2 = w.get('M2', (0, 0))
        dg = (ng2 - gm2 + 180) % 360 - 180
        if am2 and (abs(nm2 / am2 - 1) > 0.02 or abs(dg) > 2):
            print(f'  {zeilen[k][:40]}: M2 {am2:.4f}/{gm2:.1f} -> {nm2:.4f}/{ng2:.1f} -- zu verschieden, nicht angefasst')
            gemeldet += 1
            continue
        alt_rms = re.search(r'rms=([\d.]+)m', ' '.join(kopf))
        zeilen[k + 2:ende] = neu
        for i in range(a, k):
            if zeilen[i].startswith('# utide:'):
                zeilen[i] = re.sub(r'r2=[\d.]+ rms=[\d.]+m', f'r2={r2:.4f} rms={rms:.4f}m', zeilen[i])
        einf = next(i for i in range(a, k) if zeilen[i].startswith('# !units:'))
        text = ('neu gefittet mit Rayleigh 0.9 (T2, R2 u.a. dazu)' if rayleigh
                else 'neu gefittet mit Jahrestide SA/SSA (fehlte)')
        zeilen.insert(einf, f'# note: {heute} {text}, '
                            f'rms {alt_rms.group(1) if alt_rms else "?"} -> {rms:.4f} m; py/jahrestide_nachfitten.py.')
        ok += 1
        sa = w.get('SA-IOS', w.get('SA', (0,)))[0]
        print(f'  {nr:3}/{len(faelle)} {zeilen[k + 1][:34]:34} rms {alt_rms.group(1) if alt_rms else "?"} -> '
              f'{rms:.4f}  SA {100 * sa:4.1f} cm  dM2 {100 * (nm2 / am2 - 1) if am2 else 0:+.2f} % {dg:+.2f} Grad',
              flush=True)
    print(f'\n{ok} neu gefittet, {gemeldet} gemeldet')
    if '--schreiben' in argv and ok:
        sicher_schreiben.schreiben(ZIEL, '\n'.join(zeilen))
        print('geschrieben')
    elif ok:
        print('(nur Probe; mit --schreiben eintragen)')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
