#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Das Vorhersagemodell von XTide, nachgerechnet in Python.

Gebraucht fuer den Scheitelfit (py/scheitelfit.py): wer Konstanten aus
Hoch- und Niedrigwasserzeiten ableiten will, muss die Kurve als Funktion
der Konstanten schreiben koennen -- und zwar genau so, wie XTide sie
spaeter auswertet, sonst passt der Satz nachher nicht zur Datenbank.

XTide rechnet je Kalenderjahr:

    h(t) = Z0 + SUMME_k  A_k * f_k(Jahr) * cos(E_k(Jahr) + w_k * s - kappa_k)

mit s = Stunden seit Jahresbeginn (UT), w_k der Winkelgeschwindigkeit in
Grad je Stunde, E_k dem Gleichgewichtsargument zu Jahresbeginn fuer den
Meridian von Greenwich und f_k dem Knotenfaktor des Jahres. Alle drei
Tabellen stehen im Kopf jeder Harmonics-Datei.

Die Gegenprobe gegen das Programm selbst steht in pruefe(): Satz lesen,
Kurve rechnen, mit `tide -m r` vergleichen.
"""
from __future__ import annotations

import datetime as dt
import math
import os
import sys

import numpy as np


def kopf_lesen(pfad):
    """-> (namen, speeds, {jahr: args}, {jahr: faktoren}) aus dem Dateikopf."""
    zeilen = open(pfad, encoding='iso-8859-1').read().split('\n')
    i = 0

    def naechste_zahl():
        nonlocal i
        while True:
            z = zeilen[i].strip()
            i += 1
            if z and not z.startswith('#'):
                return z

    anzahl = int(naechste_zahl())
    namen, speeds = [], []
    for _ in range(anzahl):
        f = naechste_zahl().split()
        namen.append(f[0])
        speeds.append(float(f[1]))
    start = int(naechste_zahl())          # erstes Jahr der Tabellen

    def tabelle():
        """Liest eine Tabelle: je Konstituente Name + jahre Werte, bis *END*."""
        nonlocal i
        jahre = int(naechste_zahl())
        werte = {}
        for name in namen:
            zeile = naechste_zahl()
            f = zeile.split()
            assert f[0] == name, (f[0], name)
            zahlen = [float(x) for x in f[1:]]
            while len(zahlen) < jahre:
                zahlen += [float(x) for x in naechste_zahl().split()]
            werte[name] = zahlen
        while '*END*' not in zeilen[i]:
            i += 1
            if i >= len(zeilen):
                raise ValueError('kein *END*')
        i += 1
        return jahre, werte

    jahre_a, args = tabelle()
    _jahre_f, fakt = tabelle()
    arg = {start + n: {k: v[n] for k, v in args.items()} for n in range(jahre_a)}
    fak = {start + n: {k: v[n] for k, v in fakt.items()} for n in range(jahre_a)}
    return namen, dict(zip(namen, speeds)), arg, fak


_ZEILEN = {}


def _datei(pfad):
    """Zeilen einer Harmonics-Datei, gemerkt -- sie sind bis 100 MB gross."""
    if pfad not in _ZEILEN:
        _ZEILEN[pfad] = open(pfad, encoding='iso-8859-1').read().split('\n')
    return _ZEILEN[pfad]


def satz_lesen(pfad, name):
    """-> (Z0, {konstituente: (Amplitude, kappa)}, einheit, meridian_h)."""
    zeilen = _datei(pfad)
    for k, z in enumerate(zeilen):
        if z.strip() == name:
            break
    else:
        raise KeyError(name)
    mer = zeilen[k + 1].split()[0]
    vz = -1.0 if mer[0] == '-' else 1.0
    hh, mm = mer.lstrip('+-').split(':')
    meridian = vz * (int(hh) + int(mm) / 60.0)
    # Zeile k+2 traegt Z0 und Einheit zusammen: "2.7802 meters"
    f0 = zeilen[k + 2].split()
    z0 = float(f0[0])
    einheit = f0[1] if len(f0) > 1 else 'meters'
    werte = {}
    j = k + 3
    while j < len(zeilen) and zeilen[j].strip() and not zeilen[j].startswith('#'):
        f = zeilen[j].split()
        if len(f) < 3:
            break
        # "x 0 0" steht fuer eine ausgelassene Konstituente.
        try:
            if f[0] != 'x':
                werte[f[0]] = (float(f[1]), float(f[2]))
        except ValueError:
            break
        j += 1
    return z0, werte, einheit, meridian


def jahresbeginn(jahr):
    return dt.datetime(jahr, 1, 1, tzinfo=dt.timezone.utc).timestamp()


def matrix(zeiten, namen, speeds, arg, fak):
    """-> (cosE*f, sinE*f, w) je Zeitpunkt und Konstituente (Grad-Argumente)."""
    t = np.asarray(zeiten, dtype=float)
    jahre = np.array([dt.datetime.fromtimestamp(x, dt.timezone.utc).year for x in t])
    E = np.empty((len(t), len(namen)))
    F = np.empty((len(t), len(namen)))
    for jahr in np.unique(jahre):
        m = jahre == jahr
        s = (t[m] - jahresbeginn(int(jahr))) / 3600.0
        for j, k in enumerate(namen):
            E[m, j] = arg[int(jahr)][k] + speeds[k] * s
            F[m, j] = fak[int(jahr)][k]
    rad = np.radians(E)
    w = np.array([math.radians(speeds[k]) for k in namen])
    return F * np.cos(rad), F * np.sin(rad), w


def kurve(zeiten, z0, werte, namen, speeds, arg, fak, skala=1.0):
    """-> Hoehen zu den Zeiten aus Amplituden und kappa (wie XTide)."""
    nutz = [k for k in namen if k in werte and werte[k][0]]
    C, S, _w = matrix(zeiten, nutz, speeds, arg, fak)
    a = np.array([werte[k][0] for k in nutz]) * skala
    kap = np.radians([werte[k][1] for k in nutz])
    return z0 * skala + C @ (a * np.cos(kap)) + S @ (a * np.sin(kap))


def pruefe(argv):
    """Gegenprobe gegen `tide -m r` fuer einen Satz."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import messreihe_qualitaet as M
    pfad = argv[0]
    name = argv[1]
    namen, speeds, arg, fak = kopf_lesen(pfad)
    z0, werte, einheit, meridian = satz_lesen(pfad, name)
    skala = 0.3048 if einheit.startswith('f') else 1.0
    tcd = os.path.basename(pfad)[:-4] + '.tcd'
    vt, vh = M.vorhersage(tcd, name, '2026-03-01 00:00', '2026-03-08 00:00')
    if not len(vt):
        print('keine XTide-Vorhersage')
        return
    # XTide rechnet kappa im Meridian des Satzes: G = kappa + speed*meridian
    eigen = {k: (a, kap + speeds[k] * meridian) for k, (a, kap) in werte.items()}
    mein = kurve(vt, z0, eigen, namen, speeds, arg, fak, skala)
    d = mein - vh
    print(f'{name}: {len(vt)} Punkte, Abweichung zu XTide max {abs(d).max() * 100:.3f} cm, '
          f'RMS {np.sqrt((d ** 2).mean()) * 100:.3f} cm')


if __name__ == '__main__':
    pruefe(sys.argv[1:])
