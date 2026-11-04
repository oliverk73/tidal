#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Strom-Ellipsen: Stromvektor (Staerke + Richtung) statt nur Flut/Ebbe entlang einer Achse.

Stufe 3 der eigenen Tidenrechnung (Oliver 4.11.2026). Die Harmonics-Saetze kennen nur die Hauptachse;
hier kommt die Nebenachse dazu. Erste Quelle: NOAA CO-OPS harcon (water_levels/NOAA_current_harcon/,
py/noaa_strom_ellipsen_laden.py) mit majorAmplitude/majorPhaseGMT, minorAmplitude/minorPhaseGMT und
Achsrichtung azi (Grad rechtweisend) je Konstituente, Geschwindigkeit in cm/s.

Rechnung im XTide-Modell der Datei (gleiche V0+u- und f-Tabellen wie die Kurve):
  s_haupt(t) = sum f A_maj cos(E(t) - g_maj)      entlang azi (positiv = Flutrichtung)
  s_neben(t) = sum f A_min cos(E(t) - g_min)      entlang azi + NEBEN_DREH Grad
  Vektor = s_haupt * e(azi) + s_neben * e(azi + NEBEN_DREH)
Die Hauptachse muss den Harmonics-Satz selbst ergeben (Probe: probe()).

Usage: venv/bin/python py/strom_ellipsen.py "<Satzname>" [YYYY-MM-DD]
"""
from __future__ import annotations

import datetime as dt
import json
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tiden_rechnung as T                                          # noqa: E402
import xtide_modell as X                                            # noqa: E402

ROOT = T.ROOT
NOAA = os.path.join(ROOT, 'water_levels/NOAA_current_harcon')
CMS_KN = 1 / 51.4444            # cm/s -> Knoten
NEBEN_DREH = 90.0               # Nebenachse liegt 90 Grad rechts (im Uhrzeigersinn) von der Hauptachse;
                                # gegen NOAA-PORTS-Messungen 20.-30.10.2026 geprueft: Querstrom korreliert
                                # mit +90 an cb0201 +0.49, cb0301 +0.62, db0502 +0.36, cb1202 +0.27, n07010 +0.39


def noaa_konstanten(station_bin):
    """-> {'azi': Grad, 'k': {konst: (A_maj, g_maj, A_min, g_min)}} in Knoten/Grad GMT, oder None."""
    pfad = os.path.join(NOAA, station_bin + '.json')
    if not os.path.exists(pfad):
        return None
    d = json.load(open(pfad))
    hc = d.get('HarmonicConstituents') or []
    if not hc:
        return None
    k = {c['constituentName']: (c['majorAmplitude'] * CMS_KN, c['majorPhaseGMT'],
                                c['minorAmplitude'] * CMS_KN, c['minorPhaseGMT']) for c in hc}
    return {'azi': float(hc[0]['azi']), 'k': k}


EIGEN = os.path.join(ROOT, 'harmonics/ellipsen/eigen.json')
_eigen = {'mtime': None, 'd': {}}


def eigen_konstanten(D, name):
    """Eigene Fits: Hauptachse aus dem Satz, Nebenachse aus harmonics/ellipsen/eigen.json
    (py/strom_ellipsen_eigen.py). -> wie noaa_konstanten oder None."""
    if not os.path.exists(EIGEN):
        return None
    m = os.path.getmtime(EIGEN)
    if _eigen['mtime'] != m:
        _eigen['d'], _eigen['mtime'] = json.load(open(EIGEN, encoding='utf-8')), m
    r = _eigen['d'].get(os.path.basename(D.pfad), {}).get(name)
    if not r:
        return None
    s = D.saetze[name]
    k = {}
    for c, (a, kap) in s.werte.items():
        if a and c in D.speeds:
            n = r['neben'].get(c, (0.0, 0.0))
            k[c] = (a, X.greenwich(kap, D.speeds[c], s.meridian), n[0], n[1])
    return {'azi': float(r['azi']), 'k': k}


def fuer_satz(D, name):
    """Ellipsenkonstanten zum Satz (NOAA harcon oder eigene Nebenachsen-Fits) oder None."""
    s = D.saetze[name]
    sid = s.hot.get('noaa_station_id')
    if sid:
        e = noaa_konstanten(sid)
        if e:
            return e
    return eigen_konstanten(D, name)


def _summe(D, werte, t):
    """sum f A cos(E - g) fuer {konst: (A, g_GMT)} zu Unix-Zeiten t (ohne Jahreswechsel-Ueberblendung)."""
    t = np.atleast_1d(np.asarray(t, dtype=float))
    out = np.zeros_like(t)
    jahr = np.array([dt.datetime.fromtimestamp(x, dt.timezone.utc).year for x in t])
    nutz = [k for k in werte if k in D.speeds]
    A = np.array([werte[k][0] for k in nutz])
    G = np.radians([werte[k][1] for k in nutz])
    w = np.radians([D.speeds[k] for k in nutz])
    for j in np.unique(jahr):
        m = jahr == j
        E0 = np.radians([D.arg[int(j)][k] for k in nutz])
        F = np.array([D.fak[int(j)][k] for k in nutz])
        ph = (E0 - G)[None, :] + np.outer((t[m] - X.jahresbeginn(int(j))) / 3600.0, w)
        out[m] = np.cos(ph) @ (F * A)
    return out


def vektor(D, name, t, e=None):
    """-> (staerke_kn, richtung_grad_rechtweisend, haupt_kn, neben_kn) zu Unix-Zeiten t."""
    e = e or fuer_satz(D, name)
    if e is None:
        raise KeyError(f'keine Ellipsenkonstanten fuer {name}')
    haupt = _summe(D, {k: (v[0], v[1]) for k, v in e['k'].items()}, t)
    neben = _summe(D, {k: (v[2], v[3]) for k, v in e['k'].items() if v[2]}, t)
    a, b = math.radians(e['azi']), math.radians(e['azi'] + NEBEN_DREH)
    ost = haupt * math.sin(a) + neben * math.sin(b)
    nord = haupt * math.cos(a) + neben * math.cos(b)
    return np.hypot(ost, nord), np.degrees(np.arctan2(ost, nord)) % 360, haupt, neben


def ellipse(e, konst='M2', n=73):
    """Punkte (ost, nord) in Knoten der Ellipse einer Konstituente (f=1) -- fuer die Grafik."""
    A1, g1, A2, g2 = e['k'][konst]
    ph = np.linspace(0, 2 * np.pi, n)
    haupt = A1 * np.cos(ph - math.radians(g1))
    neben = A2 * np.cos(ph - math.radians(g2))
    a, b = math.radians(e['azi']), math.radians(e['azi'] + NEBEN_DREH)
    return haupt * math.sin(a) + neben * math.sin(b), haupt * math.cos(a) + neben * math.cos(b)


def probe(D, name, tage=30):
    """Hauptachse gegen den Harmonics-Satz: max. Abweichung in Knoten (ohne Z0/Mittelstrom)."""
    t = X.jahresbeginn(2026) + np.arange(0, tage * 86400, 600.0)
    e = fuer_satz(D, name)
    if e is None:
        return None
    h = _summe(D, {k: (v[0], v[1]) for k, v in e['k'].items()}, t)
    z0 = D.saetze[name].z0
    s = D.wert(name, t) - z0
    return float(np.max(np.abs(h - s)))


def main(argv):
    name = argv[0]
    tag = argv[1] if len(argv) > 1 else dt.date.today().isoformat()
    D = T.datei(os.path.join(ROOT, 'harmonics/classic/harmonics-dwf-20251228-free.txt'))
    e = fuer_satz(D, name)
    print(name, 'azi', e['azi'], 'Probe Hauptachse max', f'{probe(D, name):.3f} kn')
    t0 = dt.datetime.fromisoformat(tag).replace(tzinfo=dt.timezone.utc).timestamp()
    t = t0 + np.arange(0, 86400, 3600.0)
    st, ri, ha, ne = vektor(D, name, t, e)
    for x, a, b, c, d in zip(t, st, ri, ha, ne):
        print(f'{dt.datetime.fromtimestamp(x, dt.timezone.utc):%H:%M}Z  {a:5.2f} kn  {b:5.1f}°   (haupt {c:+.2f}, neben {d:+.2f})')


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))


# ---- Grafik: Strom-Rose ------------------------------------------------
def rose_svg(D, name, jetzt, zone, faktor=1.0, einheit='kn', stunden=25, groesse=380):
    """Kompassrose mit M2-Ellipse (gestrichelt), dem Stromweg der naechsten `stunden` Stunden
    (Spitze des Stromvektors, Punkte je Stunde, Uhrzeit alle 3 h) und dem Pfeil fuer jetzt."""
    import html
    e = fuer_satz(D, name)
    if e is None:
        return None
    t = jetzt + np.arange(0, stunden * 3600 + 1, 600.0)
    st, ri, _h, _n = vektor(D, name, t, e)
    ost, nord = st * np.sin(np.radians(ri)) * faktor, st * np.cos(np.radians(ri)) * faktor
    me, mn = ellipse(e) if 'M2' in e['k'] else (np.array([0.0]), np.array([0.0]))
    me, mn = me * faktor, mn * faktor
    vmax = max(float(np.max(st)) * faktor, float(np.max(np.hypot(me, mn))), 0.1)
    # runde Ringteilung
    schritt = next(s for s in (0.1, 0.2, 0.25, 0.5, 1, 2, 2.5, 5, 10) if vmax / s <= 5)
    ringe = int(math.ceil(vmax / schritt))
    R = groesse / 2 - 34
    k = R / (ringe * schritt)
    c = groesse / 2
    X_ = lambda x: c + x * k                                         # noqa: E731
    Y_ = lambda y: c - y * k                                         # noqa: E731
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{groesse}" height="{groesse}" '
         f'viewBox="0 0 {groesse} {groesse}" font-family="sans-serif" font-size="11">',
         f'<title>{html.escape(name)} – tidal current rose</title>',
         f'<rect width="{groesse}" height="{groesse}" fill="white"/>']
    for i in range(1, ringe + 1):
        o.append(f'<circle cx="{c}" cy="{c}" r="{i * schritt * k:.1f}" fill="none" stroke="#ddd"/>')
        a = math.radians(135)                                        # Ringbeschriftung nach SO, weg von der Nordlinie
        o.append(f'<text x="{c + math.sin(a) * i * schritt * k + 2:.1f}" y="{c - math.cos(a) * i * schritt * k + 10:.1f}" '
                 f'fill="#999">{i * schritt:g} {einheit}</text>')
    for w, txt in ((0, 'N'), (90, 'E'), (180, 'S'), (270, 'W')):
        a = math.radians(w)
        o.append(f'<line x1="{c}" y1="{c}" x2="{X_(math.sin(a) * ringe * schritt):.1f}" '
                 f'y2="{Y_(math.cos(a) * ringe * schritt):.1f}" stroke="#eee"/>')
        o.append(f'<text x="{c + math.sin(a) * (R + 14):.1f}" y="{c - math.cos(a) * (R + 14) + 4:.1f}" '
                 f'text-anchor="middle" font-weight="bold" fill="#555">{txt}</text>')
    o.append('<polyline fill="none" stroke="#999" stroke-dasharray="4 3" points="'
             + ' '.join(f'{X_(x):.1f},{Y_(y):.1f}' for x, y in zip(me, mn)) + '"/>')
    o.append('<polyline fill="none" stroke="#1565c0" stroke-width="1.6" points="'
             + ' '.join(f'{X_(x):.1f},{Y_(y):.1f}' for x, y in zip(ost, nord)) + '"/>')
    voll = (math.floor(jetzt / 3600) + 1) * 3600                    # volle Stunden (UTC = Ortszeit bis auf halbe Zonen)
    th = np.arange(voll, t[-1] + 1, 3600.0)
    sh, rh = vektor(D, name, th, e)[:2]
    for x, a, b in zip(th, sh * faktor, rh):
        px, py = X_(a * math.sin(math.radians(b))), Y_(a * math.cos(math.radians(b)))
        o.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="2" fill="#1565c0"/>')
        d = dt.datetime.fromtimestamp(x, zone)
        if d.hour % 3 == 0:                                          # alle 3 h die Uhrzeit
            o.append(f'<text x="{px + 4:.1f}" y="{py - 3:.1f}" fill="#1565c0">{d:%H:%M}</text>')
    # Pfeil jetzt
    x1, y1 = X_(ost[0]), Y_(nord[0])
    ang = math.atan2(y1 - c, x1 - c)
    spitze = [(x1, y1), (x1 - 9 * math.cos(ang - 0.4), y1 - 9 * math.sin(ang - 0.4)),
              (x1 - 9 * math.cos(ang + 0.4), y1 - 9 * math.sin(ang + 0.4))]
    o.append(f'<line x1="{c}" y1="{c}" x2="{x1:.1f}" y2="{y1:.1f}" stroke="#c62828" stroke-width="2.5"/>')
    o.append('<polygon fill="#c62828" points="' + ' '.join(f'{x:.1f},{y:.1f}' for x, y in spitze) + '"/>')
    d0 = dt.datetime.fromtimestamp(t[0], zone)
    o.append(f'<text x="8" y="16" fill="#c62828" font-weight="bold">now {d0:%H:%M}: '
             f'{st[0] * faktor:.1f} {einheit} towards {ri[0]:03.0f}°</text>')
    o.append(f'<text x="8" y="{groesse - 22}" fill="#1565c0">— next {stunden} h (dot = 1 h)</text>')
    o.append(f'<text x="8" y="{groesse - 8}" fill="#999">- - M2 tidal ellipse</text>')
    o.append('</svg>')
    return '\n'.join(o)
