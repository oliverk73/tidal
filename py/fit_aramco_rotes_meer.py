#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Saudi Aramco "Red Sea Tide Tables 2018" -> fuenf UTide-Saetze.

Das PDF (tide_tables/saudi_arabia/369180171-Red-Sea-Tide-Tables-2018.pdf,
von Oliver am 17.09.2026 bei Scribd geladen) hat je Station zwoelf
Monatsseiten mit STUENDLICHEN Hoehen (Textebene): je Tag zwei Zeilen mit
zwoelf ganzen Zentimetern (0-11 Uhr und 12-23 Uhr), dahinter die
Hoch-/Niedrigwasserzeiten. Hoehen ueber LAT, Zeiten Ortszeit UTC+3.
Laut Einleitung sind jahreszeitliche Luftdruckeffekte eingerechnet --
UTide nimmt sie als SA/SSA mit.

Weil es kontinuierliche Stundenvorhersagen sind, steht in der Quellenzeile
"hourly predictions" (noaa_pruefstand.klasse -> A).

Usage: venv/bin/python3 py/fit_aramco_rotes_meer.py [--schreiben]
"""
from __future__ import annotations

import datetime as dt
import os
import re
import subprocess
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from health_check import ROOT, curve_diff, km, load_records          # noqa: E402

PDF = os.path.join(ROOT, 'tide_tables/saudi_arabia/369180171-Red-Sea-Tide-Tables-2018.pdf')
ZIEL = os.path.join(ROOT, 'harmonics/utide/harmonics_utide_tidetables.txt')
JAHR = 2018
TZ = 3
MONATE = {m: i for i, m in enumerate(['January', 'February', 'March', 'April', 'May', 'June', 'July',
                                      'August', 'September', 'October', 'November', 'December'], 1)}
# Buchtitel -> (Satzname, lat, lon, MSL-LAT cm) aus "Tide Station Locations"
STATIONEN = {
    'Duba Bulk Plant Terminal': ('Duba Bulk Plant Terminal, Saudi Arabia', (27, 19, 21), (35, 43, 55), 64),
    'Yanbu Marine Terminal': ('Yanbu Marine Terminal, Saudi Arabia', (23, 56, 22), (38, 13, 54), 45),
    'Rabigh Marine Terminal': ('Rabigh Marine Terminal, Saudi Arabia', (22, 44, 3), (38, 59, 43), 36),
    'Jeddah Marine Terminal': ('Jeddah Marine Terminal, Saudi Arabia', (21, 25, 52), (39, 9, 17), 35),
    'Jizan Bulk Plant Terminal': ('Jizan Bulk Plant Terminal, Saudi Arabia', (16, 52, 6), (42, 33, 3), 77),
}


def grad(t):
    return t[0] + t[1] / 60 + t[2] / 3600


def reihen():
    """{Buchtitel: {(monat, tag, stunde): cm}}"""
    out = {}
    anz = int(re.search(r'Pages:\s+(\d+)', subprocess.run(['pdfinfo', PDF], capture_output=True,
                                                            text=True).stdout).group(1))
    for s in range(1, anz + 1):
        t = subprocess.run(['pdftotext', '-layout', '-f', str(s), '-l', str(s), PDF, '-'],
                           capture_output=True, text=True).stdout
        m = re.search(r'^\s*(.+?) - (' + '|'.join(MONATE) + r') ' + str(JAHR), t, re.M)
        if not m or m.group(1).strip() not in STATIONEN or not re.search(r'0:00\s+0?1:00', t):
            continue
        titel, monat = m.group(1).strip(), MONATE[m.group(2)]
        zeilen = []
        for l in t.split('\n'):
            # Golf-Tafel 2026: Tageskennung steht vor der zweiten Zeile ("01 Thu 86 115 ...")
            l = re.sub(r'^\s*\d{1,2}\s+[A-Z][a-z]{2}\s+(?=-?\d)', ' ', l)
            teile = l.split()
            zahlen = []
            for x in teile:
                if re.fullmatch(r'-?\d{1,3}', x):
                    zahlen.append(int(x))
                else:
                    break
            if len(zahlen) >= 12 and not re.match(r'\s*\d{1,2}\s+[A-Z][a-z]{2}\s*$', l):
                zeilen.append(zahlen[:12])
        tage = len(zeilen) // 2
        for d in range(tage):
            werte = zeilen[2 * d] + zeilen[2 * d + 1]
            for h in range(24):
                out.setdefault(titel, {})[(monat, d + 1, h)] = werte[h]
    return out


def fit(serie, lat):
    import utide
    t = np.array([dt.datetime(JAHR, mo, d, h) - dt.timedelta(hours=TZ) for (mo, d, h) in sorted(serie)])
    v = np.array([serie[k] / 100.0 for k in sorted(serie)])
    auto = utide.solve(t, v, lat=lat, nodal=True, trend=False, method='ols', conf_int='none',
                       verbose=False, constit='auto')
    # 365 Tage liegen knapp unter der Rayleigh-Grenze der Jahrestide; 'auto' laesst SA
    # dann weg, und der Jahresgang des Roten Meeres (~25 cm) bleibt als Rest stehen.
    liste = [n.strip() for n in auto['name']]
    liste += [x for x in ('SA', 'SSA') if x not in liste]
    coef = utide.solve(t, v, lat=lat, nodal=True, trend=False, method='ols', conf_int='none',
                       verbose=False, constit=liste)
    rec = utide.reconstruct(t, coef, verbose=False)['h']
    res = v - rec
    return dict(coef=coef, t=t, v=v, rms=float(np.sqrt(np.mean(res ** 2))),
                r2=1 - float(np.sum(res ** 2)) / float(np.sum((v - v.mean()) ** 2)), z0=float(coef['mean']))


def main(argv):
    import dmi_tidevand as D
    from add_uhslc_harmonics import CONSTITUENTS_175
    r = reihen()
    recs = [x for x in load_records() if not x['current'] and x['lat'] is not None]
    saetze = []
    for titel, (name, la, lo, msl) in STATIONEN.items():
        serie = r.get(titel, {})
        lat, lon = grad(la), grad(lo)
        tage = len({(mo, d) for mo, d, _h in serie})
        if tage < 360:
            print(f'{titel}: nur {tage} Tage gelesen -- uebersprungen')
            continue
        f = fit(serie, lat)
        w = D.werte_aus(f['coef'])
        s = D.als_satz(name, {'latitude': lat, 'longitude': lon}, w, f, 'Saudi Arabia')
        s.update(lat=lat, lon=lon, msl=msl, tage=tage)
        saetze.append(s)
        print(f"{name:40} {tage} Tage  r2={f['r2']:.4f} rms={f['rms']:.3f} m  Z0={f['z0']:.2f} (Buch {msl / 100:.2f})"
              f"  M2={w.get('M2', (0,))[0]:.3f} K1={w.get('K1', (0,))[0]:.3f}")
        for d, x in sorted(((km(s, x), x) for x in recs), key=lambda p: p[0])[:3]:
            if d < 40:
                print(f"    {d:5.1f} km  {100 * curve_diff(s, x)[1]:5.1f} %  {x['name'][:44]:44} {os.path.basename(x['file'])}")
    if '--schreiben' not in argv:
        print('(nur Probe; mit --schreiben eintragen)')
        return 0
    import sicher_schreiben
    text = open(ZIEL, encoding='iso-8859-1').read()
    neu = []
    for s in saetze:
        if re.search(r'^' + re.escape(s['name']) + r'$', text, re.M):
            print(f"  schon vorhanden: {s['name']}")
            continue
        f, w = s['fit'], s['werte']
        n_ana = sum(1 for cn, _ in CONSTITUENTS_175 if cn in w)
        L = ['#', f"# {s['name']}", '# BEGIN HOT COMMENTS', '# country: Saudi Arabia',
             '# source: Saudi Aramco Red Sea Tide Tables 2018 (hourly predictions) with UTide',
             f"# station_id_context: ARAMCO-{s['name'].split(',')[0].lower().replace(' ', '_')}",
             f'# date_imported: {dt.datetime.now():%Y%m%d}',
             '# datum: LAT (Lowest Astronomical Tide, Saudi Aramco)',
             '# confidence: 6',
             f"# utide: pts={len(f['t'])} period={f['t'][0]:%Y-%m-%d}..{f['t'][-1]:%Y-%m-%d} "
             f"r2={f['r2']:.4f} rms={f['rms']:.4f}m const={n_ana}",
             f"# note: Z0 {f['z0']:.2f} m, Buch MSL-LAT {s['msl'] / 100:.2f} m; Zeiten der Tafel UTC+3.",
             '# !units: meters', f"# !longitude: {s['lon']:.4f}", f"# !latitude: {s['lat']:.4f}",
             s['name'], '+00:00 :Asia/Riyadh', f"{f['z0']:.4f} meters"]
        for cn, _sp in CONSTITUENTS_175:
            L.append(f'{cn:15s} {w[cn][0]:.4f}  {w[cn][1]:.2f}' if cn in w and w[cn][0] >= 0.00005 else 'x 0 0')
        neu.extend(L)
    if neu:
        sicher_schreiben.schreiben(ZIEL, text.rstrip('\n') + '\n' + '\n'.join(neu) + '\n')
    print(f'{sum(1 for z in neu if z.startswith("# BEGIN HOT"))} Saetze geschrieben')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
