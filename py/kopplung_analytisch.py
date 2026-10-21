#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Kurzreihen-Kopplung ohne Rohdaten: K2 aus S2 (P1 aus K1) herausrechnen (Oliver 21.10.2026).

Ein Fit ueber ein Fenster unter 182,6 Tagen ohne K2 liefert fuer S2 die komplexe Amplitude
    Z' = Z_S2 * (1 + r * fK2/fS2 * W),   W = Mittel ueber das Fenster von exp(i*(d - (V_K2 - V_S2)(t)))
(r, d = Amplitudenverhaeltnis und Phasenabstand K2/S2 vom Pegel, V = Gleichgewichtsargument im
XTide-Modell, Phasen in Greenwich). Aufgeloest: Z_S2 = Z' / (1 + r fK2/fS2 W), K2 = r * Z_S2 * e^{id}.
Ebenso P1 aus K1. Geprueft an 180 Stroemungssaetzen gegen den Neufit aus den Rohreihen (20.10.).

Usage: als Modul -- korrigiere(konst, t0, t1, ratio, schritt_h=1)
"""
from __future__ import annotations

import datetime as dt

import numpy as np

import xtide_modell as X

PAARE = [('S2', 'K2'), ('K1', 'P1')]


def _w(KOPF, haupt, partner, t0, t1, d):
    """Mittel ueber [t0, t1] von f_p/f_h * exp(i*(d - (V_p - V_h)))."""
    namen, sp, arg, fak = KOPF
    t = np.arange(t0, t1, 3600.0)
    Cm, Sm, _w_ = X.matrix(t, [haupt, partner], sp, arg, fak)
    zh = Cm[:, 0] + 1j * Sm[:, 0]                # f_h e^{iV_h}
    zp = Cm[:, 1] + 1j * Sm[:, 1]                # f_p e^{iV_p}
    return np.mean((np.abs(zp) / np.abs(zh)) * np.exp(1j * (np.radians(d) - (np.angle(zp) - np.angle(zh)))))


def korrigiere(KOPF, konst, t0, t1, ratio, paare=PAARE):
    """konst {name: (A, kappa_greenwich)}; t0/t1 UNIX-Sekunden; ratio {partner: (r, d_grad)} -> neues konst."""
    neu = dict(konst)
    for h, p in paare:
        if h not in konst or p in konst or p not in ratio:
            continue
        r, d = ratio[p]
        W = _w(KOPF, h, p, t0, t1, d)
        A, k = konst[h]
        z = A * np.exp(1j * np.radians(k)) / (1 + r * W)
        neu[h] = (float(abs(z)), float(np.degrees(np.angle(z)) % 360))
        neu[p] = (float(abs(z) * r), float((np.degrees(np.angle(z)) + d) % 360))
    return neu


def unix(datum):
    return dt.datetime.fromisoformat(datum).replace(tzinfo=dt.timezone.utc).timestamp()
