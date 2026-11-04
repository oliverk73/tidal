#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SVG-Tidenkurve wie `tide -m g -f v` (XTide 2.15.5 Graph.cc + SVGGraph.cc, nachgebaut).

Stufe 2 der eigenen Tidenrechnung (Oliver 3.11.2026). Gleiche Geometrie und Farben wie
XTide, damit die Seiten gleich aussehen; Unterschiede: UTF-8 statt ISO-8859-1, Sonne/Mond
aus DE421 (py/astro.py).

Ablauf wie Graph::drawTides: Wertebereich = Z0 +- Summe der 6 groessten A*f (bestes Jahr der
Tabelle), 10 % Rand oben/unten, 180 s je Pixel bei 312 px Hoehe, Start = Beginn - 180 s *
(Beschriftungsbreite + 8). Tag/Nacht-Flaechen, Flut/Ebbe-Polygone, Tiefenlinien, Stunden-
und Tagesmarken, Titel, HW/NW-Zettel oben, Mond/Kenter-Zettel unten, X = jetzt.

Usage: venv/bin/python py/tiden_grafik.py <datei.txt> "<Name>" YYYY-MM-DD [m|ft] [--utc] > kurve.svg
"""
from __future__ import annotations

import datetime as dt
import math
import os
import sys
import time
from zoneinfo import ZoneInfo

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import astro                                                        # noqa: E402
import tiden_rechnung as T                                          # noqa: E402

BREITE, HOEHE = 3200, 312
GLYPH_B, GLYPH_H, OUGHT_H = 7, 12, 9
FARBEN = [('bg', '#ffffff'), ('fg', '#000000'), ('mc', '#ff0000'), ('bc', '#cccccc'), ('dc', '#87ceeb'),
          ('nc', '#00bfff'), ('fc', '#0000ff'), ('ec', '#2e8b57'), ('Dc', '#ffffff'), ('Mc', '#ffff00'),
          ('tc', '#ff0000'), ('cc', '#00a000')]
KURZ = {'Slack, Flood Begins': 'Slack', 'Slack, Ebb Begins': 'Slack', 'Moonrise': 'Mrise', 'Moonset': 'Mset',
        'New Moon': 'New', 'First Quarter': '1st/4', 'Full Moon': 'Full', 'Last Quarter': '3rd/4'}
UNTEN = set(KURZ)


def f(x):
    return '%f' % x


def amplituden_heuristik(D, name):
    """ConstituentSet: max ueber alle Tabellenjahre der Summe der 6 groessten A*f (Meter/Knoten)."""
    z0, nutz, ac, as_, _w = D.koeffizienten(name)
    A = np.hypot(ac, as_)
    best = 0.0
    for jahr in D.fak:
        a = np.sort(A * np.array([D.fak[jahr][k] for k in nutz]))[::-1]
        best = max(best, float(a[:6].sum()))
    return z0, best


class Grafik:
    def __init__(self, D, name, beginn, einheit='m', utc=False, jetzt=None, zone=None, modell=None):
        self.D, self.name, self.s = D, name, D.saetze[name]
        self.modell = modell        # (wert(t), ereignisse(t0, t1)) der eigenen HW/NW-Rechnung oder None
        self.strom = self.s.strom
        self.zone = zone or (dt.timezone.utc if utc else ZoneInfo(self.s.zone.lstrip(':')))
        self.faktor = 1.0 if self.strom or einheit != 'ft' else 1 / T.FUSS
        self.einheit = 'kt' if self.strom else einheit
        self.beginn = beginn                    # Unix-Sekunden, nominaler Start
        self.jetzt = time.time() if jetzt is None else jetzt
        self.out = []

    # ---- Zeichenprimitive (SVGGraph) ----
    def box(self, x1, x2, y1, y2, c):
        x1, x2 = sorted((x1, x2))
        y1, y2 = sorted((y1, y2))
        self.out.append(f'<rect stroke-width="0" x="{f(x1)}" y="{f(y1)}" width="{f(x2 - x1)}" '
                        f'height="{f(y2 - y1)}" class="{c}"/>')

    def vlinie(self, x, y1, y2, c):
        self.out.append(f'<line x1="{f(x)}" y1="{f(y1)}" x2="{f(x)}" y2="{f(y2)}" class="{c}" stroke-width="1"/>')

    def hlinie(self, xlo, xhi, y, c):
        if xlo <= xhi:
            self.out.append(f'<line x1="{f(xlo)}" y1="{f(y)}" x2="{f(xhi)}" y2="{f(y)}" class="{c}" '
                            f'stroke-width="1"/>')

    @staticmethod
    def esc(s):
        return s.replace('&', '&amp;').replace('<', '&lt;')

    def text_mitte(self, x, y, s):
        self.out.append(f'<text x="{f(x)}" y="{f(y + GLYPH_H)}" text-anchor="middle">{self.esc(s)}</text>')

    def text_rechts(self, x, y, s):
        self.out.append(f'<text x="{f(x)}" y="{f(y + GLYPH_H)}" text-anchor="end">{self.esc(s)}</text>')

    def zeile(self, x, line, s):
        y = line * GLYPH_H if line >= 0 else HOEHE + GLYPH_H * line - 8 - 2
        self.text_mitte(x, y, s)

    def stundenmarke(self, x, c, dick=False):
        if dick:
            self.box(x - 1.5, x + 1.5, HOEHE, HOEHE - 8, c)
        else:
            self.vlinie(x, HOEHE, HOEHE - 8, c)

    # ---- Zeitformate (XTide: df %Y-%m-%d, tf %l:%M %p %Z, hf %l) ----
    def lokal(self, t):
        return dt.datetime.fromtimestamp(t, self.zone)

    def zeit(self, t):
        d = self.lokal(int(t))
        return f'{d.hour % 12 or 12}:{d.minute:02d} {"AM" if d.hour < 12 else "PM"} {d.tzname()}'

    def datum(self, t):
        return self.lokal(int(t)).strftime('%Y-%m-%d')

    # ---- Wertebereich und Beschriftung (Graph::figureLabels/checkDepth) ----
    def xlate(self, v):
        return self.ymax + (v - self.valmin) / (self.valmax - self.valmin) * (self.ymin - self.ymax)

    def tiefenlabel(self, depth, step):
        s = '-' if depth < 0 else ''
        d = abs(depth)
        s += str(d // 10)
        if step < 10:
            s += '.' + str(d % 10)
        return s + ' ' + self.einheit

    def beschriftung(self):
        step = 10
        yz = self.xlate(0)
        prev_step, prev_mult = step, 10
        while yz - self.xlate(0.1 * step) < OUGHT_H + 1:
            if prev_mult == 10:
                prev_mult = 2
                step = prev_step * 2
            elif prev_mult == 2:
                prev_mult = 5
                step = prev_step * 5
            else:
                prev_mult = 10
                prev_step = step = prev_step * 10
        lo, hi = math.inf, -math.inf
        unten = HOEHE - GLYPH_H * 3 - 8 - 2
        depth = 0
        while depth <= self.valmax * 10:
            y = self.xlate(0.1 * depth)
            if y - GLYPH_H / 2 - 2 <= GLYPH_H * 3:
                break
            if not y + GLYPH_H / 2 + 2 >= unten:
                hi = depth
                lo = min(lo, depth)
            depth += step
        depth = -step
        while depth >= self.valmin * 10:
            y = self.xlate(0.1 * depth)
            if y - GLYPH_H / 2 - 2 <= GLYPH_H * 3:
                depth -= step
                continue
            if y + GLYPH_H / 2 + 2 >= unten:
                break
            lo = depth
            hi = max(hi, depth)
            depth -= step
        breite = rechts = 0
        if lo <= hi:
            breite = max(len(self.tiefenlabel(lo, step)), len(self.tiefenlabel(hi, step))) * GLYPH_B
            rechts = breite + 2
            breite = rechts + 2
        return step, breite, rechts, lo, hi

    # ---- Kollisionen der Zettel (Graph::fixEventBlurbCollisions) ----
    @staticmethod
    def zettel_ordnen(z):
        for _ in range(20):
            kol = False
            for i in range(1, len(z)):
                p, c = z[i - 1], z[i]
                if p['x'] > c['x']:
                    p['x'], c['x'] = c['x'], p['x']
                w = int((p['x'] + p['dr']) - (c['x'] + c['dl']) + 1)
                if w > 0:
                    kol = True
                    links = -int(w / 2)
                    p['x'] += links
                    c['x'] += w + links
            if not kol:
                break

    @staticmethod
    def zettel(x, l1, l2):
        w = max(len(l1), len(l2)) * GLYPH_B + 2
        dl = -(w // 2)
        return dict(x=x, l1=l1, l2=l2, dl=dl, dr=w + dl - 1)

    # ---- Hauptlauf (Graph::drawTides) ----
    def svg(self):
        D, name = self.D, self.name
        z0, amp = amplituden_heuristik(D, name)
        self.valmin = (z0 - amp) * self.faktor
        self.valmax = (z0 + amp) * self.faktor
        self.ymin = 0.1 * HOEHE
        self.ymax = HOEHE - self.ymin
        step, lbreite, lrechts, lo, hi = self.beschriftung()
        inc = max(1, math.floor(56160.0 / HOEHE / 1.0 + 0.5))
        start = self.beginn - inc * (lbreite + 8)
        ende = start + inc * BREITE

        # Ereignisse: Beginn - 1 Tag bis Ende + 1 Tag, wie predictTideEvents(noFilter)
        ev = [(t, h * self.faktor, a) for t, h, a in
              (self.modell[1] if self.modell else lambda a, b: D.ereignisse(name, a, b))(start - 86400, ende + 86400)]
        wert = self.modell[0] if self.modell else (lambda t: D.wert(name, t))
        lat, lon = float(self.s.hot['!latitude']), float(self.s.hot['!longitude'])
        ev += [(t, None, a) for t, a in astro.ereignisse(lat, lon, start - 86400, ende + 86400)]
        ev.sort(key=lambda e: e[0])

        kopf = ['<?xml version="1.0" encoding="utf-8" standalone="no"?>',
                '<!DOCTYPE svg PUBLIC "-//W3C//DTD SVG 1.1//EN" "http://www.w3.org/Graphics/SVG/1.1/DTD/svg11.dtd">',
                f'<svg width="{BREITE}px" height="{HOEHE}px" viewBox="0 0 {BREITE} {HOEHE}" '
                'xmlns="http://www.w3.org/2000/svg" version="1.1" xmlns:xlink="http://www.w3.org/1999/xlink">',
                '<defs>\n\t<style type="text/css">\n\t\t<![CDATA[']
        for k, c in FARBEN:
            kopf.append(f'\t\t\t.{k} {{fill:{c};stroke:{c}}}')
            kopf.append(f'\t\t\t.{k}nf {{fill:none;stroke:{c}}}')
        kopf += ['\t\t]]>\n\t</style>\n</defs>',
                 f'<defs>\n\t<clipPath id="clipBox">\n\t\t<rect x="0" y="0" width="{BREITE}" height="{HOEHE}"/>'
                 '\n\t</clipPath>\n</defs>',
                 f'<g clip-path="url(#clipBox)" font-family="Liberation Mono, Courier New" font-size="{GLYPH_H}">']
        self.out = kopf

        # Tag/Nacht (Graph::clearGraph)
        sonne = [(t, a) for t, _h, a in ev if a in ('Sunrise', 'Sunset')]
        oben = astro.sonne_oben(lat, lon, start)
        lt, i = start, 0
        while lt < ende:
            while i < len(sonne) and sonne[i][0] <= lt:
                i += 1
            if i < len(sonne):
                nxt = sonne[i][0]
                oben = sonne[i][1] == 'Sunset'
            else:
                nxt = ende + 86400
                oben = not oben
            self.box((lt - start) / inc, min(float(BREITE), (nxt - start) / inc), 0, HOEHE, 'dc' if oben else 'nc')
            lt = nxt

        # Tiefenlinien (tl = n: vor der Kurve)
        for d in range(lo, hi + 1, step) if lo <= hi else []:
            self.hlinie(float(lbreite), float(BREITE - 1 + 1), self.xlate(0.1 * d), 'fg')

        # Kurve (SVGGraph::drawLevels, Stil d)
        tt = start - inc + inc * np.arange(BREITE + 3)
        val = wert(tt) * self.faktor
        y = [self.xlate(v) for v in val]
        yz = self.xlate(0)
        teile, c = [], 'fc'
        for x in range(BREITE + 1):
            prevc = c
            if self.strom:
                c = 'fc' if val[x + 1] > 0 else 'ec'
            else:
                c = 'fc' if val[x] < val[x + 1] else 'ec'
            if prevc != c or not x:
                xadj = x - 1
                if self.strom and ((c == 'fc' and y[x] > yz) or (c == 'ec' and y[x] < yz)):
                    xadj = xadj + (yz - y[x]) / (y[x + 1] - y[x]) * (x - xadj)
                if x:
                    teile.append(f' {f(xadj)} {f(yz) if self.strom else HOEHE}"/>\n')
                teile.append(f'<polygon class="{c}" stroke-width="0" points="')
                if self.strom:
                    teile.append(f'{f(xadj)} {f(yz)}')
                else:
                    teile.append(f'{x - 1} {HOEHE} {x - 1} {f(y[x])}')
            teile.append(f' {x} {f(y[x + 1])}')
        teile.append(f' {BREITE} {f(yz) if self.strom else HOEHE}"/>')
        self.out.append(''.join(teile))

        # Hoehenachse
        for d in range(lo, hi + 1, step) if lo <= hi else []:
            adj = OUGHT_H / 2.0 + GLYPH_H - OUGHT_H
            self.text_rechts(float(lrechts), self.xlate(0.1 * d) - adj, self.tiefenlabel(d, step))

        # Zeitachse: volle Ortsstunden, dicke Marken um Mitternacht
        tstep = 1
        for k in (2, 3, 4, 6, 12, 24):
            if 3600 * tstep / inc < 2 * GLYPH_B:
                tstep = k
        stop = ende + 3600 * tstep
        kand = np.arange(math.floor((start - 3600) / 900) * 900, stop, 900)
        stunden = [int(t) for t in kand if self.lokal(int(t)).minute == 0]
        stunden = [t for t in stunden if t >= max(s for s in stunden if s <= start)]
        for t in stunden:
            if self.lokal(t).hour % tstep == 0:
                x = (t - start) / inc
                self.stundenmarke(x, 'fg')
                self.zeile(x, -1, str(self.lokal(t).hour % 12 or 12))
        tag0 = self.lokal(int(start)).replace(hour=0, minute=0, second=0, microsecond=0)
        tage = [int(t) for t in kand if self.lokal(int(t)).hour == 0 and self.lokal(int(t)).minute == 0]
        tage = [int(tag0.timestamp())] + [t for t in tage if t > tag0.timestamp()]
        for t in tage:
            self.stundenmarke((t - start) / inc, 'fg', True)

        # Titel und Zettel
        self.zeile(BREITE / 2.0, 0, name)
        top, bot = [], []
        for t, h, a in ev:
            x = (t - start) / inc
            if a in ('High Tide', 'Low Tide', 'Max Flood', 'Max Ebb', 'Min Flood', 'Min Ebb'):
                top.append(self.zettel(x, self.datum(t), self.zeit(t)))
            elif a in UNTEN:
                self.stundenmarke(x, 'mc')
                l2 = self.zeit(t)
                l1 = a if len(a) <= len(l2) else KURZ[a]
                bot.append(self.zettel(x, l1, l2))
        for liste, linie in ((top, 1), (bot, -3)):
            self.zettel_ordnen(liste)
            for z in liste:
                self.zeile(z['x'], linie, z['l1'])
                self.zeile(z['x'], linie + 1, z['l2'])

        # X = jetzt
        if start <= self.jetzt < ende:
            x = (self.jetzt - start) / inc
            yv = self.xlate(float(wert(self.jetzt)[0]) * self.faktor)
            self.vlinie(x, yv - 4, yv + 4, 'fg')
            self.hlinie(x - 4, x + 4, yv, 'fg')
        self.out.append('</g>\n</svg>\n')
        return '\n'.join(self.out)


def svg(D, name, tag, einheit='m', utc=False, jetzt=None, zone=None, modell=None):
    """tag = 'YYYY-MM-DD' -> SVG-Text (Beginn 00:00 in Stationszeit bzw. UTC)."""
    s = D.saetze[name]
    zone = zone or (dt.timezone.utc if utc else ZoneInfo(s.zone.lstrip(':')))
    b = dt.datetime.strptime(tag, '%Y-%m-%d').replace(tzinfo=zone).timestamp()
    return Grafik(D, name, b, einheit, utc, jetzt, zone, modell).svg()


if __name__ == '__main__':
    a = [x for x in sys.argv[1:] if not x.startswith('--')]
    if len(a) < 3:
        print(__doc__)
        sys.exit(1)
    sys.stdout.write(svg(T.datei(a[0]), a[1], a[2], a[3] if len(a) > 3 else 'm', '--utc' in sys.argv))
