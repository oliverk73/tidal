#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ersatz fuer das verlorene Modul gleichen Namens.

py/refit_tidetimes_bst.py und py/fit_icoe_vietnam.py holten sich von hier
die Konstituentenliste und die Interpolation. Das Original lag in
/home/oliver/batch, das es nicht mehr gibt -- damit liefen beide Skripte
ueberhaupt nicht mehr.

Zurueckgewonnen ist die Liste aus dem Bestand selbst: von den 624
Saetzen in harmonics_utide_tidetables.txt, die aus tidetimes.co.uk
stammen, tragen 525 exakt dieselben 68 Konstituenten. Das ist keine
Schaetzung, sondern das, womit tatsaechlich gefittet wurde. Zwei Namen
darin sind XTide-Schreibweisen (S1-IOS, SA-IOS); UTide kennt sie als S1
und SA, die Umsetzung macht find_xtide_match beim Schreiben.

Die Interpolation ist NICHT zurueckgewonnen, sondern neu geschrieben:
zwischen zwei aufeinanderfolgenden Extrema liegt eine halbe Kosinuswelle

    h(t) = h1 + (h2 - h1) * (1 - cos(pi * f)) / 2,   f = (t-t1)/(t2-t1)

Das ist das uebliche Verfahren, um aus Hoch- und Niedrigwasserzeiten
eine Kurve zu machen, aber ob das Original genau so rechnete, weiss
niemand mehr. Deshalb gilt: ein damit erzeugter Satz ist erst dann gut,
wenn er sich an den Tafeln misst -- py/messreihe_qualitaet.py sagt es.

Ueber Luecken wird nicht interpoliert: fehlt ein Tag, stuende sonst eine
erfundene Kurve in den Daten. Abstaende ueber LUECKE_H Stunden trennen
die Reihe.
"""
from __future__ import annotations

import datetime as dt
import math

SCHRITT_MIN = 10
LUECKE_H = 18.0

# Aus dem Bestand zurueckgewonnen (525 uebereinstimmende Saetze), in
# UTide-Schreibweise: S1-IOS -> S1, SA-IOS -> SA.
CONSTIT_67 = [
    '2MK5', '2MK6', '2MN6', '2MS6', '2N2', '2Q1', '2SK5', '2SM2', '3MS4',
    'ALP1', 'BET1', 'CHI1', 'EPS2', 'ETA2', 'H1', 'H2', 'J1', 'K1', 'K2',
    'L2', 'LDA2', 'M2', 'M3', 'M4', 'M6', 'M8', 'MF', 'MK3', 'MK4', 'MKS2',
    'MM', 'MN4', 'MO3', 'MS4', 'MSF', 'MSK6', 'MSM', 'MU2', 'N2', 'N4',
    'NO1', 'NO3', 'NU2', 'O1', 'OO1', 'OP2', 'P1', 'PHI1', 'PI1', 'PSI1',
    'Q1', 'R2', 'RHO1', 'S1', 'S2', 'S4', 'SA', 'SIG1', 'SK3', 'SKM2',
    'SN4', 'SO1', 'SO3', 'SSA', 'T2', 'TAU1', 'THE1', 'UPS1',
]


def cosine_interpolate(hw_lw, schritt_min=SCHRITT_MIN, luecke_h=LUECKE_H):
    """-> (Zeiten, Hoehen) aus einer Folge von Hoch- und Niedrigwassern.

    hw_lw ist [(datetime, hoehe), ...]; die Reihenfolge wird erzwungen.
    Rueckgabe sind numpy-Arrays, wie utide.solve sie erwartet, oder
    (None, None), wenn zu wenig zusammenhaengende Punkte bleiben.
    """
    import numpy as np
    punkte = sorted((t, float(h)) for t, h in hw_lw if t is not None)
    if len(punkte) < 4:
        return None, None
    schritt = dt.timedelta(minutes=schritt_min)
    zeiten, hoehen = [], []
    for (t1, h1), (t2, h2) in zip(punkte, punkte[1:]):
        spanne = (t2 - t1).total_seconds()
        if spanne <= 0 or spanne > luecke_h * 3600:
            continue
        t = t1
        while t < t2:
            f = (t - t1).total_seconds() / spanne
            zeiten.append(t)
            hoehen.append(h1 + (h2 - h1) * (1 - math.cos(math.pi * f)) / 2)
            t += schritt
    if len(zeiten) < 100:
        return None, None
    zeiten.append(punkte[-1][0])
    hoehen.append(punkte[-1][1])
    return np.array(zeiten), np.array(hoehen)
