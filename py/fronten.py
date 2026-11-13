#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Objektive Frontenanalyse aus GFS 850 hPa (Oliver 13.11.2026: "Kannst Du dort auch Warm- und Kaltfronten einzeichnen?").

Verfahren (Thermal Front Parameter nach Renard & Clarke 1965 / Hewson 1998):
  theta_e in 850 hPa aus T und relativer Feuchte, geglaettet (GLATT Gitterpunkte),
  TFP = -grad|grad theta_e| . (grad theta_e / |grad theta_e|)   [K / (100 km)^2]
  Front = Nulllinie des TFP, nur wo |grad theta_e| >= MIN_GRAD K/100 km (Frontalzone) und TFP-Maximum davor;
  Linien kuerzer als MIN_KM verworfen.
  Art aus der Advektion quer zur Front: v . n (n = Einheitsvektor zur warmen Seite)
    v.n > +MIN_MS  -> Wind weht von kalt nach warm -> Kaltluftadvektion -> Kaltfront
    v.n < -MIN_MS  -> Warmfront,  sonst quasistationaer.
Ausgabe je Front: {"typ": "kalt"|"warm"|"stationaer", "linie": [[lon, lat], ...], "warm": [Winkel Grad je Punkt]}
"warm" = Richtung zur warmen Seite (rechtweisend), damit die Karte Dreiecke/Halbkreise auf die richtige Seite setzt.

Es ist eine Modellanalyse, keine handgezeichnete Wetterkarte: kleine Wellen, Okklusionen und Fronten ueber hohem
Gelaende (850 hPa unter Gelaende) fehlen oder sind unscharf.
"""
import math

import numpy as np
from scipy import ndimage

GLATT, MIN_GRAD, MIN_KM, MIN_MS, MAX_BREITE = 2.5, 3.0, 500.0, 2.0, 75.0
R_ERDE = 6371.0


def theta_e(t_k, rh):
    """Aequivalent-potentielle Temperatur (K) in 850 hPa (Bolton 1980, vereinfacht)."""
    p = 850.0
    tc = t_k - 273.15
    es = 6.112 * np.exp(17.67 * tc / (tc + 243.5))
    e = np.clip(rh, 1, 100) / 100.0 * es
    r = 0.622 * e / (p - e)                                  # kg/kg
    th = t_k * (1000.0 / p) ** 0.2854
    return th * np.exp(2.5e6 * r / (1004.0 * t_k))


def analyse(t_k, rh, u, v, lats, lons):
    """Felder (ny, nx), lats 90..-90, lons 0..360 -> Liste von Fronten (Laenge -180..180)."""
    import contourpy
    k = int(np.argmin(np.abs(lons - 180.0)))
    roll = lambda a: np.concatenate([a[:, k:], a[:, :k], a[:, k:k + 1]], axis=1)    # noqa: E731
    lo = np.concatenate([lons[k:] - 360.0, lons[:k], [lons[k]]])
    th = ndimage.gaussian_filter(roll(theta_e(t_k, rh)), GLATT, mode=("nearest", "wrap"))
    uu = ndimage.gaussian_filter(roll(u), GLATT, mode=("nearest", "wrap"))
    vv = ndimage.gaussian_filter(roll(v), GLATT, mode=("nearest", "wrap"))
    dlat = abs(lats[1] - lats[0])
    dy = R_ERDE * math.radians(dlat) / 100.0                                       # in 100 km
    dx = (R_ERDE * np.cos(np.radians(lats)) * math.radians(dlat) / 100.0)[:, None]
    dx = np.maximum(dx, 0.05)
    gy, gx = np.gradient(th)
    gx, gy = gx / dx, -gy / dy                                                     # Zeile nach Sueden -> Nord positiv
    betrag = np.hypot(gx, gy)
    ex, ey = gx / np.maximum(betrag, 1e-6), gy / np.maximum(betrag, 1e-6)        # Einheitsvektor zur warmen Seite (Ost, Nord)
    by, bx = np.gradient(betrag)
    bx, by = bx / dx, -by / dy
    tfp = -(bx * ex + by * ey)
    # Nulllinie des TFP nur in Frontalzonen: TFP ausserhalb maskieren
    maske = (betrag < MIN_GRAD) | (np.abs(lats)[:, None] > MAX_BREITE) | (np.abs(lats)[:, None] < 8)
    tfp_m = np.where(maske, np.nan, tfp)
    gen = contourpy.contour_generator(lo, lats, tfp_m, line_type="Separate")
    fronten = []
    for seg in gen.lines(0.0):
        if len(seg) < 4:
            continue
        laenge = sum(R_ERDE * math.radians(math.hypot(seg[i + 1][1] - seg[i][1],
                     (seg[i + 1][0] - seg[i][0]) * math.cos(math.radians(seg[i][1])))) for i in range(len(seg) - 1))
        if laenge < MIN_KM:
            continue
        # Werte entlang der Linie
        jj = np.clip(np.round((seg[:, 0] - lo[0]) / (lo[1] - lo[0])).astype(int), 0, len(lo) - 1)
        ii = np.clip(np.round((lats[0] - seg[:, 1]) / dlat).astype(int), 0, len(lats) - 1)
        exs, eys = ex[ii, jj], ey[ii, jj]
        adv = uu[ii, jj] * exs + vv[ii, jj] * eys                                   # m/s quer zur Front, + = zur warmen Seite
        typ = np.where(adv > MIN_MS, 1, np.where(adv < -MIN_MS, -1, 0))
        winkel = np.degrees(np.arctan2(exs, eys)) % 360
        # in Abschnitte gleicher Art zerlegen (Mindestlaenge 4 Punkte)
        start = 0
        for e in range(1, len(seg) + 1):
            if e == len(seg) or typ[e] != typ[start]:
                if e - start >= 4:
                    t = {1: "kalt", -1: "warm", 0: "stationaer"}[int(typ[start])]
                    s = np.round(seg[start:e], 2)
                    fronten.append({"typ": t, "linie": s.tolist(), "warm": [int(w) for w in winkel[start:e]]})
                start = e
    return fronten
