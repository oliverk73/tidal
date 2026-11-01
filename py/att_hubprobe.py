#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sucht ATT-Uebertragungen mit falschem Hub oder S2/M2 (1.11.2026).

Anlass Nes Farm, Ferrat, Papey: Buchzeilen ohne Niedrigwasser oder ganz ohne Hoehen lassen den Hub
des Bezugshafens stehen. Zeugen: naechster Messsatz/Tafelfit/TICON/ATT-Standardhafen bis 60 km und FES
am Ort. Gemeldet wird nur, wenn BEIDE in dieselbe Richtung widersprechen.

Usage: venv/bin/python py/att_hubprobe.py  -> harmonics/help/att_hubprobe_20261101.csv
"""
import csv
import glob
import os
import sys

import netCDF4 as nc

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fes_ersatz_inseln as F                                       # noqa: E402
import health_check as hc                                           # noqa: E402

ROOT = F.ROOT
AUS = os.path.join(ROOT, 'harmonics/help/att_hubprobe_20261101.csv')
ZEUGEN = ('harmonics_utide_observations.txt', 'harmonics_utide_tidetables.txt', 'harmonics_ticon4_worldwide.txt',
          'harmonics_att_np202.txt', 'harmonics_att_np203.txt', 'harmonics_att_np204.txt', 'harmonics_att_np207.txt', 'harmonics_att_np208.txt')
SET = ('harmonics_att_np202_secondary.txt', 'harmonics_att_np203_secondary.txt', 'harmonics_att_np203_scs_secondary.txt',
       'harmonics_att_np204_secondary.txt', 'harmonics_att_np208_secondary.txt')


def kenn(r):
    a = r['amp']
    m, s = a['M2'][0] * r['scale'], a['S2'][0] * r['scale']
    return m, s


def main():
    alle = [r for r in hc.load_records() if not r['current'] and r['lat'] is not None and 'M2' in r['amp'] and 'S2' in r['amp']]
    faelle = [r for r in alle if os.path.basename(r['file']) in SET and r['amp']['M2'][0] * r['scale'] >= 0.1]
    zeugen = [r for r in alle if os.path.basename(r['file']) in ZEUGEN and r['amp']['M2'][0] * r['scale'] >= 0.05]
    dm, ds = (nc.Dataset(os.path.join(F.FES_DIR, f'{t}_fes2022.nc')) for t in ('m2', 's2'))
    aus = []
    for r in faelle:
        m, s = kenn(r)
        nb = min((z for z in zeugen if z is not r), key=lambda z: hc.km(r, z))
        k = hc.km(r, nb)
        if k > 60:
            continue
        mz, sz = kenn(nb)
        mf = F.sample(dm, r['lat'], r['lon'])[0]
        sf = F.sample(ds, r['lat'], r['lon'])[0]
        hub_z, hub_f = (m + s) / (mz + sz), (m + s) / (mf + sf)
        v, vz, vf = s / m, sz / mz, sf / mf
        fehler = []
        if (hub_z > 1.3 and hub_f > 1.3) or (hub_z < 0.7 and hub_f < 0.7):
            fehler.append('Hub')
        if (v > 1.5 * vz and v > 1.5 * vf) or (v < 0.65 * vz and v < 0.65 * vf):
            fehler.append('S2/M2')
        if fehler:
            aus.append(dict(fehler='+'.join(fehler), datei=os.path.basename(r['file']), name=r['name'], m2=round(m, 3), s2=round(s, 3),
                            verh=round(v, 2), zeuge=nb['name'], km=round(k, 1), z_m2=round(mz, 3), z_s2=round(sz, 3), z_verh=round(vz, 2),
                            f_m2=round(mf, 3), f_s2=round(sf, 3), f_verh=round(vf, 2), hub_z=round(hub_z, 2), hub_f=round(hub_f, 2)))
    with open(AUS, 'w', encoding='utf-8', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=list(aus[0]))
        w.writeheader()
        w.writerows(aus)
    print(len(faelle), 'geprueft,', len(aus), 'gemeldet')
    for x in aus:
        print(f"{x['fehler']:9s} {x['name'][:40]:40s} {x['datei'][13:23]:10s} M2 {x['m2']:.3f} S2 {x['s2']:.3f} v {x['verh']:.2f} | {x['zeuge'][:24]:24s} {x['km']:5.1f} {x['z_m2']:.3f} {x['z_s2']:.3f} {x['z_verh']:.2f} | F {x['f_m2']:.3f} {x['f_s2']:.3f} {x['f_verh']:.2f}")


if __name__ == '__main__':
    main()
