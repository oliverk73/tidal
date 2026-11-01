#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Rechnerisch abgeleitetes N2 der Altsaetze durch Zeugenwerte ersetzen (1.11.2026).

Rund 80 Saetze aus harmonics-2004/1997 tragen kein gemessenes N2, sondern die Lehrbuchregel
N2 = 0.194*M2, g(N2) = g(M2) - 0.536*(g(S2)-g(M2)). Wo S2 frueh liegt, gibt das in Queensland
N2 16 Grad HINTER M2 statt 20 Grad davor und 0.19 statt 0.32 als Verhaeltnis.

Zeugen: naechster Satz mit eigenem N2 bis 100 km (Messung, Tafelfit, TICON, ATT-Standardhafen)
und FES am Ort, beide als Verhaeltnis und Abstand zu M2. Ersetzt wird nur, wenn der Satz um mehr als 15 Grad
oder 25 % abweicht und beide Zeugen auf 25 Grad einig sind (ohne Nachbar: FES allein unter 25 km zum Meer nicht).
M2 des Satzes bleibt der Massstab.

Usage: venv/bin/python py/n2_abgeleitet.py [--schreiben]  -> harmonics/help/n2_abgeleitet_20261101.csv
"""
import csv
import math
import os
import sys

import netCDF4 as nc
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fes_ersatz_inseln as F                                       # noqa: E402
import health_check as hc                                           # noqa: E402
import xtide_modell as X                                            # noqa: E402

ROOT = F.ROOT
QUELLEN = ('harmonics-2004-06-14_mod.txt', 'harmonics-1997-05-25_mod.txt')
ZEUGEN = ('harmonics_utide_observations.txt', 'harmonics_utide_tidetables.txt', 'harmonics_ticon4_worldwide.txt',
          'harmonics_att_np201.txt', 'harmonics_att_np202.txt', 'harmonics_att_np203.txt', 'harmonics_att_np204.txt',
          'harmonics_att_np207.txt', 'harmonics_att_np208.txt')
AUS = os.path.join(ROOT, 'harmonics/help/n2_abgeleitet_20261101.csv')
SP_M2, SP_N2 = 28.9841042, 28.4397295
d = lambda a, b: (a - b + 180) % 360 - 180


def meridian(r):
    return X.satz_lesen(os.path.join(ROOT, r['file']), r['name'])[3]


def lage(r):
    """-> (N2/M2, M2-N2 in Greenwich-Grad)."""
    m = meridian(r)
    a = r['amp']
    return a['N2'][0] / a['M2'][0], d(a['M2'][1] - SP_M2 * m, a['N2'][1] - SP_N2 * m)


def abgeleitet(r):
    a = r['amp']
    if 'S2' not in a or a['M2'][0] * r['scale'] < 0.05:
        return False
    if not 0.188 <= a['N2'][0] / a['M2'][0] <= 0.197:
        return False
    return abs(d(a['N2'][1], a['M2'][1]) + 0.536 * d(a['S2'][1], a['M2'][1])) < 3


def main():
    alle = [r for r in hc.load_records() if not r['current'] and r['lat'] is not None and 'M2' in r['amp'] and 'N2' in r['amp']]
    faelle = [r for r in alle if os.path.basename(r['file']) in QUELLEN and abgeleitet(r)]
    zeugen = [r for r in alle if os.path.basename(r['file']) in ZEUGEN and r['amp']['M2'][0] * r['scale'] > 0.05
              and not (0.188 <= r['amp']['N2'][0] / r['amp']['M2'][0] <= 0.197)]
    dm, dn = (nc.Dataset(os.path.join(F.FES_DIR, f'{t}_fes2022.nc')) for t in ('m2', 'n2'))
    aus = []
    for r in faelle:
        v, ab = lage(r)
        nb = min(zeugen, key=lambda x: hc.km(r, x))
        k = hc.km(r, nb)
        vn, an = lage(nb) if k <= 100 else (None, None)
        am, gm = F.sample(dm, r['lat'], r['lon'])
        a2, g2 = F.sample(dn, r['lat'], r['lon'])
        vf, af = a2 / am, d(gm, g2)
        einig = vn is not None and abs(d(an, af)) <= 25
        if einig:
            ziel_v, ziel_a = (vn + vf) / 2, af + d(an, af) / 2
            art = 'Zeuge+FES'
        elif vn is None:
            ziel_v, ziel_a, art = vf, af, 'nur FES'
        else:
            ziel_v, ziel_a, art = None, None, 'Zeugen uneins'
        tun = ziel_v is not None and (abs(d(ab, ziel_a)) > 15 or abs(v / ziel_v - 1) > 0.25)
        # FES allein nahe den M2-Amphidromen (Papua, Salomonen) gibt kein brauchbares Verhaeltnis
        if art == 'nur FES' and (vf > 0.45 or abs(af) > 45):
            tun = False
        # Zeugen beim Verhaeltnis weit auseinander und die Phase passt schon: lassen
        if einig and max(vn, vf) / min(vn, vf) > 1.7 and abs(d(ab, ziel_a)) < 25:
            tun = False
        aus.append(dict(datei=r['file'], name=r['name'], m2_m=round(r['amp']['M2'][0] * r['scale'], 3), verh=round(v, 3), abstand=round(ab, 1),
                        zeuge=nb['name'], km=round(k, 1), z_verh=None if vn is None else round(vn, 3), z_abst=None if an is None else round(an, 1),
                        fes_verh=round(vf, 3), fes_abst=round(af, 1), art=art, neu_verh=None if ziel_v is None else round(ziel_v, 3),
                        neu_abst=None if ziel_a is None else round(ziel_a, 1), tun=int(tun)))
    with open(AUS, 'w', encoding='utf-8', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=list(aus[0]))
        w.writeheader()
        w.writerows(aus)
    print(len(aus), 'abgeleitet;', sum(x['tun'] for x in aus), 'zu ersetzen;', {k: sum(1 for x in aus if x['art'] == k) for k in ('Zeuge+FES', 'nur FES', 'Zeugen uneins')})
    if '--schreiben' not in sys.argv:
        return
    for pfad in sorted({x['datei'] for x in aus}):
        p = os.path.join(ROOT, pfad)
        z = open(p, encoding='iso-8859-1').read().split('\n')
        for x in aus:
            if x['datei'] != pfad or not x['tun']:
                continue
            r = next(q for q in faelle if q['name'] == x['name'] and q['file'] == pfad)
            m = meridian(r)
            am, km2 = r['amp']['M2']
            g_n = (km2 - SP_M2 * m - x['neu_abst']) % 360
            k = z.index(x['name'])
            for j in range(k + 3, k + 178):
                f = z[j].split()
                if len(f) == 3 and f[0] == 'N2':
                    z[j] = f'{"N2":<16}{am * x["neu_verh"]:.4f}  {(g_n + SP_N2 * m) % 360:.2f}'
                    break
            i = k
            while not z[i].startswith('# !longitude'):
                i -= 1
            z[i:i] = [f'# note: 20261101 N2 war abgeleitet (0.194*M2), neu von {x["art"]}, Zeuge {x["zeuge"][:40]} (py/n2_abgeleitet.py).']
        open(p, 'w', encoding='iso-8859-1').write('\n'.join(z))


if __name__ == '__main__':
    main()
