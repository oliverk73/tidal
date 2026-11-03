#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Eigene Tiden- und Stromrechnung ohne XTide (Stufe 1, Oliver 3.11.2026).

Liest die Harmonics-Dateien direkt (keine TCD) und liefert
  - die Kurve h(t) bzw. den Strom v(t)
  - die Ereignisse: High/Low Tide, Max/Min Flood/Ebb, Slack
genau wie `tide -m p`. Das Rechenmodell ist das von XTide
(py/xtide_modell.py): je Kalenderjahr
    h(t) = Z0 + SUMME A_k f_k cos(E_k + w_k s - G_k),  G = kappa - w * Meridian
Ereignisse: Nullstellen der Ableitung (Scheitel) und bei Stroemen von v (Kenter),
grob im 10-min-Raster gesucht, dann mit brentq auf < 1 s genau.

Stufe 1 ist reine Pruefung: py/tiden_vergleich.py laesst beides ueber den ganzen
Bestand laufen. Die App ruft weiter XTide auf.

Usage: venv/bin/python py/tiden_rechnung.py <datei.txt> "<Name>" [YYYY-MM-DD [Tage]]
"""
from __future__ import annotations

import datetime as dt
import math
import os
import re
import sys
from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import brentq

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import xtide_modell as X                                            # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MERIDIAN = re.compile(r'^([+-]?)(\d{1,2}):(\d\d)(?:\s+(\S+))?')
FUSS = 0.3048
RASTER = 60.0           # s, Grobsuche (XTide meldet Doppelscheitel 3 min auseinander)
BLEND = 3600.0          # s, Ueberblendung am Jahreswechsel (XTide)


@dataclass
class Satz:
    name: str
    meridian: float               # Stunden
    zone: str                     # ':Europe/Berlin'
    z0: float
    einheit: str                  # meters | feet | knots
    werte: dict                   # {konst: (A, kappa)} im Satzmeridian
    hot: dict = field(default_factory=dict)

    @property
    def strom(self):
        return self.einheit.startswith('knot')


class Datei:
    """Eine Harmonics-Datei: Kopf + alle Saetze, einmal gelesen."""

    def __init__(self, pfad, kodierung='iso-8859-1'):
        self.pfad = pfad
        self.namen, self.speeds, self.arg, self.fak = X.kopf_lesen(pfad)
        self.saetze = {}
        self._lesen(open(pfad, encoding=kodierung).read().split('\n'))
        self._koef = {}

    def _lesen(self, L):
        hot, im_hot = {}, False
        i, n = 0, len(L)
        while i < n:
            z = L[i]
            if z.startswith('#'):
                if 'BEGIN HOT COMMENTS' in z:
                    hot, im_hot = {}, True
                elif im_hot:
                    m = re.match(r'#\s*(!?[^:\s]+):\s?(.*)$', z)
                    if m:
                        hot[m.group(1)] = m.group(2).strip()
                i += 1
                continue
            if z.strip() and i + 2 < n and MERIDIAN.match(L[i + 1]):
                m = MERIDIAN.match(L[i + 1])
                mer = (-1 if m.group(1) == '-' else 1) * (int(m.group(2)) + int(m.group(3)) / 60)
                f0 = L[i + 2].split()
                werte = {}
                j = i + 3
                while j < n and L[j].strip() and not L[j].startswith('#'):
                    f = L[j].split()
                    if len(f) < 3:
                        break
                    try:
                        if f[0] != 'x' and f[1] != 'x':
                            werte[f[0]] = (float(f[1]), float(f[2]))
                    except ValueError:
                        break
                    j += 1
                name = z.rstrip('\r')
                self.saetze[name] = Satz(name, mer, m.group(4) or ':UTC', float(f0[0]),
                                         f0[1] if len(f0) > 1 else 'meters', werte, hot)
                hot, im_hot = {}, False
                i = j
                continue
            i += 1

    # ---- Rechnung -------------------------------------------------------
    def koeffizienten(self, name):
        """-> (z0, konst-Liste, a*cos G, a*sin G, w[rad/h]) in Meter bzw. Knoten."""
        if name not in self._koef:
            s = self.saetze[name]
            sk = FUSS if s.einheit.startswith('f') else 1.0
            nutz = [k for k in self.namen if k in s.werte and s.werte[k][0]]
            a = np.array([s.werte[k][0] for k in nutz]) * sk
            G = np.radians([X.greenwich(s.werte[k][1], self.speeds[k], s.meridian) for k in nutz])
            w = np.radians([self.speeds[k] for k in nutz])
            self._koef[name] = (s.z0 * sk, nutz, a * np.cos(G), a * np.sin(G), w)
        return self._koef[name]

    def _jahr(self, name, jahr):
        """Je Konstituente Amplitude*f und Phase E0-G zu Jahresbeginn."""
        z0, nutz, ac, as_, w = self.koeffizienten(name)
        E = np.radians([self.arg[jahr][k] for k in nutz])
        F = np.array([self.fak[jahr][k] for k in nutz])
        A = F * np.hypot(ac, as_)
        P = E - np.arctan2(as_, ac)
        return z0, A, P, w

    def _mit_jahr(self, name, t, jahr, abl):
        """Kurve (abl=0) oder Ableitung je Stunde (abl=1) mit den Tabellen EINES Jahres."""
        z0, A, P, w = self._jahr(name, jahr)
        ph = P[None, :] + np.outer((t - X.jahresbeginn(jahr)) / 3600.0, w)
        return z0 + np.cos(ph) @ A if abl == 0 else -np.sin(ph) @ (A * w)

    def wert(self, name, t, abl=0):
        """h(t) (abl=0) oder dh/dt je Stunde (abl=1); t = Unix-Sekunden (Array).

        Am Jahreswechsel blendet XTide (wie schon Version 1) ueber +-1 h zwischen den
        Tabellen beider Jahre: w(x) = 1/2 + (15x - 10x^3 + 3x^5)/16, x = (t - B)/1 h.
        Ohne das sprang die Kurve um bis zu 2 cm und XTide fand andere Scheitel (Makarov 20 min).
        """
        t = np.atleast_1d(np.asarray(t, dtype=float))
        out = np.empty_like(t)
        jahr = np.array([dt.datetime.fromtimestamp(x, dt.timezone.utc).year for x in t])
        for j in np.unique(jahr):
            m = jahr == j
            out[m] = self._mit_jahr(name, t[m], int(j), abl)
        for j in np.unique(jahr):
            for B in (X.jahresbeginn(int(j)), X.jahresbeginn(int(j) + 1)):
                m = np.abs(t - B) < BLEND
                if not m.any():
                    continue
                jr = dt.datetime.fromtimestamp(B, dt.timezone.utc).year
                x = (t[m] - B) / BLEND
                g = 0.5 + (15 * x - 10 * x ** 3 + 3 * x ** 5) / 16
                hl = self._mit_jahr(name, t[m], jr - 1, 0)
                hr = self._mit_jahr(name, t[m], jr, 0)
                if abl == 0:
                    out[m] = hl + g * (hr - hl)
                else:
                    dg = 15 * (1 - x ** 2) ** 2 / 16 / (BLEND / 3600.0)
                    out[m] = (self._mit_jahr(name, t[m], jr - 1, 1) * (1 - g)
                              + self._mit_jahr(name, t[m], jr, 1) * g + dg * (hr - hl))
        return out

    # ---- Ereignisse -----------------------------------------------------
    def ereignisse(self, name, t0, t1):
        """-> [(t, wert, art)] zwischen t0 und t1 (Unix-Sekunden), zeitlich sortiert."""
        s = self.saetze[name]
        t = np.arange(t0 - RASTER, t1 + 2 * RASTER, RASTER)
        d = self.wert(name, t, 1)
        f = lambda x: float(self.wert(name, x, 1)[0])
        ev = []
        for i in np.nonzero(np.sign(d[:-1]) * np.sign(d[1:]) <= 0)[0]:
            if d[i] == 0 and i > 0 and d[i - 1] == 0:
                continue
            x = t[i] if d[i] == 0 else brentq(f, t[i], t[i + 1], xtol=0.5)
            h = float(self.wert(name, x)[0])
            hoch = d[i] > 0 or (d[i] == 0 and d[i + 1] < 0)
            if s.strom:
                art = ('Max Flood' if h > 0 else 'Min Ebb') if hoch else ('Max Ebb' if h < 0 else 'Min Flood')
            else:
                art = 'High Tide' if hoch else 'Low Tide'
            ev.append((x, h, art))
        if s.strom:
            v = self.wert(name, t)
            g = lambda x: float(self.wert(name, x)[0])
            for i in np.nonzero(np.sign(v[:-1]) * np.sign(v[1:]) < 0)[0]:
                x = brentq(g, t[i], t[i + 1], xtol=0.5)
                ev.append((x, 0.0, 'Slack, Flood Begins' if v[i] < 0 else 'Slack, Ebb Begins'))
        return sorted(e for e in ev if t0 <= e[0] < t1)


_DATEIEN = {}


def datei(pfad):
    pfad = pfad if os.path.isabs(pfad) else os.path.join(ROOT, pfad)
    if pfad not in _DATEIEN:
        _DATEIEN[pfad] = Datei(pfad)
    return _DATEIEN[pfad]


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 1
    D = datei(argv[0])
    tag = dt.datetime.strptime(argv[2], '%Y-%m-%d') if len(argv) > 2 else dt.datetime.utcnow()
    t0 = tag.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=dt.timezone.utc).timestamp()
    tage = float(argv[3]) if len(argv) > 3 else 2
    s = D.saetze[argv[1]]
    e = 'knots' if s.strom else 'meters'
    for x, h, art in D.ereignisse(argv[1], t0, t0 + tage * 86400):
        print(dt.datetime.fromtimestamp(round(x / 60) * 60, dt.timezone.utc).strftime('%Y-%m-%d %H:%M UTC'),
              f'{h:6.2f} {e}  {art}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
