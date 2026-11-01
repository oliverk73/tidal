#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Liest die LINZ-Harmonischen (tide_tables/newzealand/linz_harm, CC BY 4.0, Release 2025).

Kopf: "STATION 043 TIME ZONE = 180, LATITUDE = 4117, LONGITUDE = 17400" (Grad+Minuten, Sued, Ost/West
nach Lage), Tabelle NO NAME FREQUENCY STN M-Y/M-Y A G; A in cm, Z0 ueber Kartennull. 

Usage: als Modul -- saetze() -> [dict(id, name, lat, lon, zone, z0, werte, zeitraum, datei)]
"""
from __future__ import annotations

import glob
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORD = os.path.join(ROOT, 'tide_tables/newzealand/linz_harm')


def saetze():
    aus = []
    for p in sorted(glob.glob(os.path.join(ORD, '*'))):
        t = open(p, encoding='latin-1').read()
        m = re.search(r'STATION\s+(\d+)\s+TIME ZONE\s*=\s*(-?\d+),\s*LATITUDE\s*=\s*(\d+),\s*LONGITUDE\s*=\s*(\d+)', t)
        name = t.strip().split('\n')[0].split('Units')[0].strip()
        la, lo = int(m[3]), int(m[4])
        if m[1] == '077':      # Kopf nennt 1416, Nelson liegt auf 41 16 S
            la = 4116
        lat = -(la // 100 + (la % 100) / 60)
        lon = lo // 100 + (lo % 100) / 60
        w, z0 = {}, None
        am = re.search(r'AVERAGE\s*=\s*(-?\d+\.\d+)', t)
        for z in re.finditer(r'^\s*\d+\s+(\S+)\s+\.?\d*\.?\d+\s+\d+\s+\d+/\d+\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)\s*$', t, re.M):
            if z[1] == 'Z0':
                z0 = float(z[2]) / 100
            else:
                w[z[1]] = (float(z[2]) / 100, float(z[3]))
        if z0 is None and am:
            z0 = float(am[1]) / 100
        zr = re.search(r'Harm_?-?(\d{4}-\d{4})', os.path.basename(p))
        aus.append(dict(id=m[1], name=name, lat=lat, lon=lon, zone=int(m[2]), z0=z0, werte=w, zeitraum=zr[1] if zr else '', datei=os.path.basename(p)))
    return aus
