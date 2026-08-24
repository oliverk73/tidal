#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sucht zu falsch verknuepften NOAA-Uebertragungen die richtige Referenz.

Eine Table-2-Uebertragung ist die Referenzstation mal Faktor k, zeitlich um
dt verschoben. Faktor und Zeitversatz stehen in der gedruckten Tafel und
gehoeren der Station -- falsch ist bei den auffaelligen Saetzen nur, auf
welche Referenz sie angewandt wurden. Also laesst sich die richtige suchen:
k und dt auf jede in Frage kommende Referenzstation anwenden und schauen,
welche Kombination zu den unabhaengigen Nachbarn am Ort passt.

Das Vorzeichen der Zeitverschiebung wird nicht geraten, sondern an den
unauffaelligen Uebertragungen geeicht.

Usage: python3 py/noaa_referenz_finden.py [--eichen] [--csv <datei>]
"""
from __future__ import annotations

import cmath
import collections
import csv
import math
import os
import re
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from health_check import km, MERIDIAN, ROOT                        # noqa: E402

DATEI = os.path.join(ROOT, 'harmonics/noaa/harmonics_noaa_cptt.txt')
NAH_KM = 200.0       # so nah gilt eine Referenz als unverdaechtig (zum Eichen)


def speeds(pfad):
    """Konstituentengeschwindigkeiten aus dem congen-Kopf der Datei."""
    out = {}
    an = False
    for z in open(pfad, encoding='iso-8859-1'):
        if z.startswith('# Constituent speeds'):
            an = True
            continue
        if an:
            if z.startswith('#'):
                continue
            p = z.split()
            if len(p) != 2:
                break
            try:
                out[p[0]] = float(p[1])
            except ValueError:
                break
    return out


def lies(pfad, sp):
    """-> Liste von Saetzen mit allen Konstituenten als Greenwich-Zeiger."""
    l = open(pfad, encoding='iso-8859-1').read().split('\n')
    recs = []
    lat = lon = units = None
    for k, z in enumerate(l):
        if z.startswith('# !latitude:'):
            lat = float(z.split(':', 1)[1])
        elif z.startswith('# !longitude:'):
            lon = float(z.split(':', 1)[1])
        elif z.startswith('# !units:'):
            units = z.split(':', 1)[1].strip()
        elif (z and not z.startswith('#') and k + 1 < len(l)
              and MERIDIAN.match(l[k + 1])):
            mer = l[k + 1].split()[0]
            vz = -1.0 if mer[0] == '-' else 1.0
            hh, mm = mer.lstrip('+-').split(':')
            h = vz * (int(hh) + int(mm) / 60.0)
            skala = 0.3048 if (units or '').startswith('f') else 1.0
            z_ = {}
            j = k + 3
            while j < len(l) and l[j].strip() and not l[j].startswith('#'):
                p = l[j].split()
                if p and p[0] != 'x' and p[0] in sp:
                    try:
                        a, g = float(p[1]), float(p[2])
                    except (ValueError, IndexError):
                        j += 1
                        continue
                    if a > 0:
                        z_[p[0]] = cmath.rect(
                            skala * a, -math.radians((g - sp[p[0]] * h) % 360))
                j += 1
            recs.append(dict(name=z, lat=lat, lon=lon, z=z_,
                             file=os.path.basename(pfad)))
    return recs


def notizen(pfad):
    """-> {Name: (Referenzname, k, dt_min)}"""
    l = open(pfad, encoding='iso-8859-1').read().split('\n')
    out = {}
    for k, x in enumerate(l):
        if 'Table 2 transfer from' not in x:
            continue
        m = re.search(r'k=([\d.]+) dt=([+-]\d+)min', x)
        if not m:
            continue
        ref = x.split('transfer from ', 1)[1].split(' (no.')[0].strip()
        i = k
        while i < len(l) and not (l[i] and not l[i].startswith('#')
                                  and i + 1 < len(l) and MERIDIAN.match(l[i + 1])):
            i += 1
        if i < len(l):
            out[l[i]] = (ref, float(m.group(1)), int(m.group(2)))
    return out


def uebertrage(ref, k, dt_min, sp, vz):
    """Referenz mal k, um dt verschoben. vz eicht das Vorzeichen der Phase."""
    dt_h = dt_min / 60.0
    return {c: w * k * cmath.exp(1j * vz * math.radians(sp[c] * dt_h))
            for c, w in ref['z'].items() if c in sp}


def abstand(z1, z2):
    """Relative Abweichung zweier Zeigersaetze, wie curve_diff."""
    c = set(z1) | set(z2)
    d = math.sqrt(sum(abs(z1.get(x, 0) - z2.get(x, 0)) ** 2 for x in c) / 2)
    t1 = sum(abs(z1.get(x, 0)) for x in ('M2', 'S2', 'N2', 'K1', 'O1'))
    t2 = sum(abs(z2.get(x, 0)) for x in ('M2', 'S2', 'N2', 'K1', 'O1'))
    return d / max(0.15, (t1 + t2) / 2)
