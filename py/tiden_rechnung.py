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
    hot: dict = field(default_factory=dict)      # letzter Wert je Schluessel
    hot_liste: list = field(default_factory=list)  # [(schluessel, wert)] in Dateireihenfolge
    kommentar: list = field(default_factory=list)  # freie Kommentarzeilen vor dem Satz

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
        """Saetze samt Kommentaren. Wie build_tide_db: freie Kommentarzeilen seit der letzten
        Nicht-Kommentarzeile gehoeren zum naechsten Satz ('#' allein = Leerzeile), Hot Comments
        ab BEGIN HOT COMMENTS als 'schluessel: wert'. Doppelte Namen: der erste gilt (wie XTide)."""
        hot, frei = [], []
        kopf = False        # nach *END*: Kopfkommentare bis 'FITNESS FOR A PARTICULAR PURPOSE' bzw. Leerzeile verwerfen
        i, n = 0, len(L)
        while i < n:
            z = L[i].rstrip('\r')
            if z.strip() == '*END*':
                kopf = True
            elif not z.strip():
                kopf = False
            if z.startswith('#'):
                # build_tide_db: '# schluessel: wert' gilt ueberall als Hot Comment (auch ohne BEGIN),
                # '#' und '# ' sind Leerzeilen.
                m = re.match(r'# (!?[A-Za-z_][A-Za-z0-9_]*):(?=\s|$)\s*(.*)$', z)
                if 'BEGIN HOT COMMENTS' in z or 'END HOT COMMENTS' in z:
                    pass
                elif m:
                    hot.append((m.group(1).lower(), m.group(2).strip()))
                    if m.group(1).lower() not in HOT_FELD and not m.group(1).startswith('!'):
                        frei.append(z[2:])   # unbekannt -> Comments, an Ort und Stelle, wie geschrieben
                elif kopf:
                    # Standardkopf nach *END* endet mit dem Gewaehrleistungsausschluss
                    kopf = 'FITNESS FOR A PARTICULAR PURPOSE' not in z
                else:
                    frei.append(z[2:] if z.startswith('# ') else z[1:])
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
                if z not in self.saetze:
                    while frei and not frei[0].strip():
                        frei.pop(0)
                    while frei and not frei[-1].strip():
                        frei.pop()
                    self.saetze[z] = Satz(z, mer, m.group(4) or ':UTC', float(f0[0]),
                                          f0[1] if len(f0) > 1 else 'meters', werte, dict(hot), hot, frei)
                hot, frei, kopf = [], [], False
                i = j
                continue
            frei, hot = [], []
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


HOT_FELD = {'station_id_context': 'Station ID context', 'station_id': 'Station ID', 'country': 'Country',
            'source': 'Source', 'restriction': 'Restriction', 'datum': 'Datum', 'confidence': 'Confidence',
            'date_imported': 'Date imported', 'months_on_station': 'Months on station',
            'last_date_on_station': 'Last date on station', 'max_direction': 'Flood direction',
            'min_direction': 'Ebb direction', 'note': 'Notes', 'expiration_date': 'Expiration',
            'expiration': 'Expiration', 'used_until': 'Expiration'}
# Ohne 'restriction:' setzt build_tide_db je nach TCD einen anderen Wert (empirisch, 3.11.2026).
RESTRICTION_VORGABE = {'harmonics_bsh_germany.txt': 'Public Domain', 'harmonics_ih_tabelas.txt': 'Public Domain'}
INFO_FOLGE = ['Name', 'In file', 'Station ID context', 'Station ID', 'Date imported', 'Coordinates', 'Country',
              'Time zone', 'Native units', 'Flood direction', 'Ebb direction', 'Source', 'Restriction',
              'Comments', 'Notes', 'Type', 'Meridian', 'Datum', 'Expiration', 'Months on station', 'Last date on station',
              'Confidence']


def _datum8(v):
    return f'{v[:4]}-{v[4:6]}-{v[6:8]}' if re.fullmatch(r'\d{8}', v) else v


def info(D, name):
    """Infoblock wie `tide -m a`: [(feld, [zeilen])] in XTide-Reihenfolge."""
    s = D.saetze[name]
    f = {'Name': [name], 'In file': [D.pfad]}
    kom = list(s.kommentar)
    for k, v in s.hot_liste:
        if k in HOT_FELD:
            feld = HOT_FELD[k]
            if feld == 'Notes':
                f.setdefault('Notes', []).append(v)
            elif feld in ('Date imported', 'Last date on station', 'Expiration'):
                f[feld] = [_datum8(v)]
            elif feld in ('Flood direction', 'Ebb direction'):
                f[feld] = [f'{v}\u00b0 true']
            else:
                f[feld] = [v]
    lat, lon = s.hot.get('!latitude'), s.hot.get('!longitude')
    if lat is not None and lon is not None:
        la, lo = round(float(lat) * 1e5) / 1e5, round(float(lon) * 1e5) / 1e5   # TCD speichert 1e-5 Grad
        f['Coordinates'] = [f"{abs(la):.4f}\u00b0 {'N' if la >= 0 else 'S'}, {abs(lo):.4f}\u00b0 {'E' if lo >= 0 else 'W'}"]
    f['Time zone'] = [s.zone]
    f['Native units'] = [s.einheit]
    f.setdefault('Country', ['Unknown'])
    f.setdefault('Restriction', [RESTRICTION_VORGABE.get(os.path.basename(D.pfad), 'Non-commercial use only')])
    if kom:
        f['Comments'] = kom
    f['Type'] = ['Reference station, ' + ('current' if s.strom else 'tide')]
    h, m = divmod(round(abs(s.meridian) * 60), 60)
    f['Meridian'] = [('-' if s.meridian < 0 else '+' if s.meridian > 0 else '') + f'{h}:{m:02d}']
    if s.strom:
        f.pop('Datum', None)
    f.setdefault('Confidence', ['10'])
    return [(k, f[k]) for k in INFO_FOLGE if k in f]


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
