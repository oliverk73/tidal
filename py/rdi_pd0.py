#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Minimaler Leser fuer RDI-ADCP-Rohdaten (PD0, *.000) (Oliver 20.10.2026).

Liest je Ensemble Zeit (Variable Leader), Koordinatensystem/Zellen (Fixed Leader) und
Geschwindigkeiten (ID 0x0100, mm/s, -32768 = ungueltig) und Echo (ID 0x0300, Mittel der Strahlen). Erd-Koordinaten
(EX-Bits 3-4 = 11): Spalten Ost, Nord, Vertikal, Fehler. Strahl-Koordinaten (00, z. B. Kyle Rhea 2012) werden mit
Kurs/Neigung/Rollwinkel des Variable Leader nach RDI (Coordinate Transformation Manual) in Ost/Nord umgerechnet.
Usage: lesen(pfad) -> dict(t, u, v, echo, tiefe (Wandler, m), tiefe_zellen, coord, bin1, zelle, n_zellen, oben)
       nutzbar(r) -> Index der obersten Zelle unterhalb der Seitenkeulen-Stoerung (nach oben schauend)
"""
import datetime as dt
import struct

import numpy as np


def lesen(pfad):
    b = open(pfad, 'rb').read()
    n = len(b)
    T, U, V, E, P, HPR = [], [], [], [], [], []
    fix = None
    i = 0
    while i < n - 6:
        if b[i] != 0x7F or b[i + 1] != 0x7F:
            i = b.find(b'\x7f\x7f', i + 1)
            if i < 0:
                break
            continue
        nbytes = struct.unpack_from('<H', b, i + 2)[0]
        if i + nbytes + 2 > n or nbytes < 20:
            break
        if (sum(b[i:i + nbytes]) & 0xFFFF) != struct.unpack_from('<H', b, i + nbytes)[0]:
            i += 2
            continue
        nd = b[i + 5]
        offs = struct.unpack_from('<%dH' % nd, b, i + 6)
        t = vel = echo = None
        for o in offs:
            p = i + o
            idn = struct.unpack_from('<H', b, p)[0]
            if idn == 0x0000:
                ncell, = struct.unpack_from('<B', b, p + 9)
                zelle, = struct.unpack_from('<H', b, p + 12)
                ex = b[p + 25]
                bin1, = struct.unpack_from('<H', b, p + 32)
                fix = dict(n_zellen=ncell, zelle=zelle / 100, bin1=bin1 / 100, coord=(ex >> 3) & 3,
                           sysconf=struct.unpack_from('<H', b, p + 4)[0])
            elif idn == 0x0080:
                yy, mo, dd, hh, mi, ss, hs = b[p + 4:p + 11]
                try:
                    t = dt.datetime(2000 + yy if yy < 80 else 1900 + yy, mo, dd, hh, mi, ss, hs * 10000)
                except ValueError:
                    t = None
                dep = struct.unpack_from('<H', b, p + 16)[0] / 10          # Tiefe des Wandlers (dm), aus dem Drucksensor
                hpr = (struct.unpack_from('<H', b, p + 18)[0] / 100, *(x / 100 for x in struct.unpack_from('<hh', b, p + 20)))
            elif idn == 0x0100 and fix:
                vel = np.frombuffer(b, '<i2', fix['n_zellen'] * 4, p + 2).reshape(fix['n_zellen'], 4).astype(float)
            elif idn == 0x0300 and fix:
                echo = np.frombuffer(b, 'u1', fix['n_zellen'] * 4, p + 2).reshape(fix['n_zellen'], 4).mean(axis=1)
        if t is not None and vel is not None:
            vel[vel == -32768] = np.nan
            if fix['coord'] == 0:
                vel = vel.astype(np.float32)
                U.append(vel / 1000); V.append(None); HPR.append(hpr)
            else:
                U.append(vel[:, 0] / 1000); V.append(vel[:, 1] / 1000)
            T.append(t)
            E.append(echo if echo is not None else np.full(fix['n_zellen'], np.nan))
            P.append(dep)
        i += nbytes + 2
    if not fix:
        return None
    fix['oben'] = bool(fix['sysconf'] & 0x80)          # Bit 7: 1 = nach oben schauend
    fix['tiefe_zellen'] = fix['bin1'] + fix['zelle'] * np.arange(fix['n_zellen'])   # Abstand vom Geraet
    if fix['coord'] == 0:
        U, V = strahl_zu_erde(np.array(U), np.array(HPR), fix)
    return dict(t=np.array(T, dtype='datetime64[ms]'), u=np.array(U), v=np.array(V), echo=np.array(E), tiefe=np.array(P), **fix)


def strahl_zu_erde(B, hpr, fix):
    """B (Ensembles, Zellen, 4 Strahlen) m/s, hpr (Ensembles, 3) Grad -> (Ost, Nord). Janus, 4 Strahlen."""
    th = np.radians({0: 15, 1: 20, 2: 30}.get((fix['sysconf'] >> 8) & 3, 20))
    c = 1.0 if fix['sysconf'] & 0x08 else -1.0                 # Bit 3: konvex
    a, bb = 1 / (2 * np.sin(th)), 1 / (4 * np.cos(th))
    x = c * a * (B[..., 0] - B[..., 1])
    y = c * a * (B[..., 3] - B[..., 2])
    z = bb * (B[..., 0] + B[..., 1] + B[..., 2] + B[..., 3])
    H, P, R = (np.radians(hpr[:, k])[:, None] for k in range(3))
    if fix['sysconf'] & 0x80:                                   # nach oben schauend
        R = R + np.pi
    P = np.arctan(np.tan(P) * np.cos(R))
    CH, SH, CP, SP, CR, SR = np.cos(H), np.sin(H), np.cos(P), np.sin(P), np.cos(R), np.sin(R)
    ost = (CH * CR + SH * SP * SR) * x + SH * CP * y + (CH * SR - SH * SP * CR) * z
    nord = (-SH * CR + CH * SP * SR) * x + CH * CP * y + (-SH * SR - CH * SP * CR) * z
    return ost.astype(float), nord.astype(float)


def nutzbar(r, anteil=0.85):
    """Oberflaeche = Zelle mit dem staerksten Echo (Median ueber alle Ensembles, nur obere 2/3).
    Nutzbar bis anteil * Abstand Oberflaeche (Seitenkeulen bei 20 Grad Strahlwinkel: cos 20 = 0,94),
    abzueglich einer Zelle. -> (Index, Abstand Oberflaeche vom Geraet in m) oder (None, nan)."""
    e = r['echo']
    if not np.isfinite(e).any():
        return None, float('nan')
    n = r['n_zellen']
    lo = n // 3
    k = lo + np.nanargmax(e[:, lo:], axis=1)
    flaeche = float(np.median(r['tiefe_zellen'][k]))
    if k.max() == n - 1 and np.median(k) >= n - 2:            # Oberflaeche ausserhalb der Zellen
        flaeche = float('nan')
    grenze = (anteil * flaeche if np.isfinite(flaeche) else r['tiefe_zellen'][-1]) - r['zelle']
    j = [i for i in range(n) if r['tiefe_zellen'][i] <= grenze and np.isfinite(r['u'][:, i]).mean() >= 0.8]
    return (max(j) if j else None), flaeche


if __name__ == '__main__':
    import sys
    r = lesen(sys.argv[1])
    print({k: r[k] for k in ('n_zellen', 'zelle', 'bin1', 'coord', 'oben')}, r['t'][[0, -1]], r['u'].shape, nutzbar(r))
