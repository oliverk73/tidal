#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Stroemungskonstanten aus den brasilianischen "Cartas de Correntes de Maré" (CHM/DHN, Oliver 25.10.2026).

Die Hefte (currents/brazil/ccm-*.pdf, von Oliver im Browser geladen) zeigen je Kartensatz 13
Stundenkarten von 6 h vor bis 6 h nach der Preamar eines Bezugshafens, mittlere Springtide,
Geschwindigkeit in Knoten. Die PDFs sind Vektorgrafik:
  - Pfeil = roter Strich (Schaft) + rote Flaeche (Spitze),
  - Geschwindigkeit = roter Text "0,8" neben dem Pfeil (nicht jeder Pfeil hat eine Zahl),
  - Gradnetz-Beschriftung schwarz am Kartenrand (Grad/Minuten, Sued/West).

Umrechnung wie bei den SHOM-Atlanten (shom_atlas_stroemung.py):
  1. Pfeile mit Zahl ueber die 13 Karten zu Punkten verbinden (Zuordnung nach Lage),
  2. Preamar/Baixa-mar des Bezugshafens fuer ein Jahr aus unserem Satz vorausrechnen,
  3. Strom zur Zeit t = Kartenwert zur Stunde (t - PM), mal Faktor aus dem Tidenhub der Tide
     (Tabelle bzw. Abakus des Hefts),
  4. die Jahresreihe wie eine Messreihe fitten (cmems_stroemung_nachholen.analyse).

Schreibt nur nach harmonics/help/ (Bestand bleibt unberuehrt):
  chm_ccm_<heft>_<datum>.csv / .txt
Usage: venv/bin/python py/chm_ccm_stroemung.py HEFT [--nur-punkte]
       HEFT = Kurzname aus HEFTE (z.B. sao-marcos)
"""
from __future__ import annotations

import csv
import datetime as dt
import math
import os
import re
import sys

import fitz
import numpy as np
import pandas as pd
from scipy.optimize import linear_sum_assignment

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cmems_stroemung_nachholen as C                               # noqa: E402
import shom_atlas_stroemung as S                                    # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PDF = os.path.join(ROOT, 'currents/brazil')
HILFE = os.path.join(ROOT, 'harmonics/help')
MS_KN = C.MS_KN


def _dunkel(c):
    # Schrift des Gradnetzes: schwarz bis dunkelgrau (0x231f20, 0x434244 ...)
    r, g, b = c >> 16, (c >> 8) & 255, c & 255
    return max(r, g, b) < 0x70


def _roetlich(c):
    # Geschwindigkeiten: rot (0xef4035)
    r, g, b = c >> 16, (c >> 8) & 255, c & 255
    return r > 0xb0 and g < 0x80 and b < 0x80


def faktor_sao_marcos(hub, dauer):
    # Tabelle im Heft: Hub 2,0..6,5 m -> 0,5..1,4, also 0,2*Hub + 0,1 (exakt an allen 10 Stuetzstellen)
    return 0.2 * hub + 0.1


def faktor_salvador(hub, dauer):
    # Stufenskala im Heft (S. 4): Faktor 0,5..1,1 nach mittlerem Tidenhub. Stufengrenzen aus den
    # Strichen der Vektorgrafik: 0,735 / 1,036 / 1,399 / 1,791 / 2,225 / 2,701 m (Beispiel 1,5 m -> 0,8).
    # Stetig: an jeder Grenze der Mittelwert der beiden Stufen, dazwischen linear.
    grenzen = np.array([0.735, 1.036, 1.399, 1.791, 2.225, 2.701])
    werte = np.array([0.55, 0.65, 0.75, 0.85, 0.95, 1.05])
    steig = 0.1 / np.diff(grenzen).mean()
    h = np.asarray(hub, float)
    return np.where(h < grenzen[0], werte[0] + (h - grenzen[0]) * steig,
                    np.where(h > grenzen[-1], werte[-1] + (h - grenzen[-1]) * steig, np.interp(h, grenzen, werte)))


class Abaco:
    """Faktor-Abakus (Santos, Guanabara, Paranagua) ueber Tidenhub (oben, m) und Dauer PM<->BM (links, h).
    Die Linien sind Grenzen zwischen Faktorstufen: die Zahlen 0,1 .. 1,3 stehen ZWISCHEN den 12 Linien
    (0,1 links der ersten, 1,3 rechts der letzten). Linie k entspricht also 0,1*k + 0,05; so treffen alle
    drei Rechenbeispiele (Santos 1,3, Paranagua 0,9, Guanabara 0,4). Ausgewertet wird stetig: je Dauer
    der Hub jeder Linie, dazwischen linear, ausserhalb mit der Randsteigung."""

    def __init__(self, pdf, seite):
        p = fitz.open(pdf)[seite - 1]
        m = _dreh(p)
        kurven = []
        for g in p.get_drawings():
            # Kurven bzw. Geraden: dunkle Striche ab 0,5 pt, schraeg (Rahmen und Gitter laufen achsparallel)
            r = g['rect']
            if 's' in g['type'] and g.get('color') and max(g['color']) < 0.3 and (g.get('width') or 0) > 0.5 \
                    and r.width > 5 and r.height > 5 and all(it[0] in ('c', 'l') for it in g['items']):
                pts = []
                for it in g['items']:
                    if it[0] == 'c':
                        a, b, c, d = it[1:]
                        for t in np.linspace(0, 1, 30):
                            pts.append(((1 - t) ** 3 * a.x + 3 * (1 - t) ** 2 * t * b.x + 3 * (1 - t) * t ** 2 * c.x + t ** 3 * d.x,
                                        (1 - t) ** 3 * a.y + 3 * (1 - t) ** 2 * t * b.y + 3 * (1 - t) * t ** 2 * c.y + t ** 3 * d.y))
                    else:
                        a, b = it[1], it[2]
                        pts += [(a.x + (b.x - a.x) * t, a.y + (b.y - a.y) * t) for t in np.linspace(0, 1, 30)]
                kurven.append(np.array([tuple(fitz.Point(x, y) * m) for x, y in pts]))
        oben, links = [], []
        for b in p.get_text('dict')['blocks']:
            for l in b.get('lines', []):
                t = ''.join(s['text'] for s in l['spans']).strip()
                x0, y0, x1, y1 = _rect(p, l['bbox'])
                if _richtung(p, l['dir']) != (1.0, 0.0):
                    continue
                if re.fullmatch(r'\d,\d', t):
                    oben.append(((x0 + x1) / 2, (y0 + y1) / 2, float(t.replace(',', '.'))))
                elif re.fullmatch(r'\d{1,2}', t):
                    links.append(((y0 + y1) / 2, float(t)))
        # Hub-Achse: die waagrechte Zahlenreihe mit den meisten Eintraegen
        zeilen = {}
        for x, y, v in oben:
            zeilen.setdefault(round(y), []).append((x, v))
        oben = max(zeilen.values(), key=len)
        bx, ax = np.polyfit([x for x, _ in oben], [v for _, v in oben], 1)
        by, ay = np.polyfit([y for y, _ in links], [v for _, v in links], 1)
        kurven.sort(key=lambda c: c[:, 0].min() + c[:, 0].max())
        self.n = len(kurven)
        # Tabelle: fuer Dauer 1..10 h den Hub jeder Linie (NaN, wo die Linie nicht hinreicht)
        self.dauer = np.arange(1.0, 10.01, 0.05)
        self.hub = np.full((len(self.dauer), len(kurven)), np.nan)
        for k, c in enumerate(kurven):
            A = ax + bx * c[:, 0]
            T = ay + by * c[:, 1]
            o = np.argsort(T)
            ok = (self.dauer >= T.min()) & (self.dauer <= T.max())
            self.hub[ok, k] = np.interp(self.dauer[ok], T[o], A[o])
        self.wert = 0.1 * np.arange(1, len(kurven) + 1) + 0.05

    def _eins(self, hub, dauer):
        # Dauer ausserhalb des Diagramms (gemischte Tiden): auf den Rand des Diagramms setzen
        gueltig = np.where((~np.isnan(self.hub)).sum(axis=1) >= 2)[0]
        i = int(np.clip(round((dauer - 1.0) / 0.05), gueltig[0], gueltig[-1]))
        z = self.hub[i]
        ok = ~np.isnan(z)
        x, f = z[ok], self.wert[ok]
        if len(x) < 2:
            return np.nan
        if hub <= x[0]:
            return max(0.0, f[0] + (hub - x[0]) * (f[1] - f[0]) / (x[1] - x[0]))
        if hub >= x[-1]:
            return f[-1] + (hub - x[-1]) * (f[-1] - f[-2]) / (x[-1] - x[-2])
        return float(np.interp(hub, x, f))

    def __call__(self, hub, dauer):
        hub, dauer = np.broadcast_arrays(np.atleast_1d(hub).astype(float), np.atleast_1d(dauer).astype(float))
        return np.array([self._eins(h, d) for h, d in zip(hub, dauer)])

    def __repr__(self):
        return 'Abakus mit %d Stufengrenzen (%.2f .. %.2f)' % (self.n, self.wert[0], self.wert[-1])


class Korrektur:
    """Additive Korrekturtabellen (Vitoria, Madre de Deus): je Gebiet eine Tabelle Knoten nach
    Tidenhub a (cm, Zeilen) und Stunde zur PM (Spalten). Gelesen wird in den rohen Seiten-
    koordinaten, die Ausrichtung der Tabelle wird aus der Lage der Hub-Beschriftung bestimmt.
    farbe: 'rot' oder 'blau' (Vitoria: blau = 5 m Tiefgang, rot = 11 m)."""

    def __init__(self, pdf, seiten, farbe='rot'):
        self.tab = {}
        d = fitz.open(pdf)
        test = _roetlich if farbe == 'rot' else _blaeulich
        for gebiet, seite in seiten.items():
            p = d[seite - 1]
            hub, kopf, werte, pm = [], [], [], []
            antes = depois = None
            for b in p.get_text('dict')['blocks']:
                for l in b.get('lines', []):
                    for sp in l['spans']:
                        t = sp['text'].strip()
                        x0, y0, x1, y1 = sp['bbox']
                        c = ((x0 + x1) / 2, (y0 + y1) / 2)
                        if _dunkel(sp['color']):
                            if re.fullmatch(r'\d{2,3}', t):
                                hub.append((c, int(t)))
                            elif re.fullmatch(r'[1-6]', t):
                                kopf.append((c, int(t)))
                            elif t.startswith('Horas antes'):
                                antes = c
                            elif t.startswith('Horas depois'):
                                depois = c
                            elif t == 'Preamar':
                                pm = c
                        elif test(sp['color']):
                            m = re.fullmatch(r'\(?([+\u2013-]?)(\d),(\d)\)?', t.replace(' ', ''))
                            if m:
                                v = int(m.group(2)) + int(m.group(3)) / 10
                                werte.append((c, -v if m.group(1) in ('\u2013', '-') else v))
                            elif re.fullmatch(r'\(?0\)?', t):
                                werte.append((c, 0.0))
            # Zeilenachse = Achse, entlang der sich die Hub-Beschriftung verteilt
            hx = np.ptp([c[0] for c, _ in hub])
            hy = np.ptp([c[1] for c, _ in hub])
            za, sa = (1, 0) if hy > hx else (0, 1)
            spalten = [(pm[sa], 0)]
            for c, k in kopf:
                vor = abs(c[sa] - antes[sa]) < abs(c[sa] - depois[sa])
                spalten.append((c[sa], -k if vor else k))
            hubs = sorted(set(v for _, v in hub))
            T = np.full((len(hubs), 13), np.nan)
            for c, v in werte:
                zi = min(hub, key=lambda q: abs(q[0][za] - c[za]))
                if abs(zi[0][za] - c[za]) > 14:
                    continue
                st = min(spalten, key=lambda q: abs(q[0] - c[sa]))
                T[hubs.index(zi[1]), st[1] + 6] = v
            lu = [(hubs[i], j - 6) for i, j in zip(*np.where(np.isnan(T)))]
            if len(lu) > 4:
                raise ValueError('Tabelle %s Seite %d unvollstaendig: %s' % (gebiet, seite, lu))
            for i, j in zip(*np.where(np.isnan(T))):
                # einzelne Zelle fehlt im Druck (Vitoria 160 cm, -6/-5 h): aus den Nachbarzeilen
                spalte = T[:, j]
                ok = ~np.isnan(spalte)
                T[i, j] = np.interp(hubs[i], np.array(hubs)[ok], spalte[ok])
            if lu:
                print('  Tabelle %s Seite %d: %d Zelle(n) aus Nachbarzeilen ergaenzt %s' % (gebiet, seite, len(lu), lu))
            self.tab[gebiet] = (np.array(hubs, float), T)

    def __call__(self, gebiet, hub_cm, tau_h):
        """Korrektur in Knoten; Hub: naechste Zeile (das Heft: 'keine Interpolation'), Stunde linear."""
        hubs, T = self.tab[gebiet]
        i = np.abs(hubs[None, :] - np.atleast_1d(hub_cm)[:, None]).argmin(axis=1)
        tau = np.atleast_1d(tau_h)
        k0 = np.clip(np.floor(tau).astype(int) + 6, 0, 12)
        k1 = np.clip(k0 + 1, 0, 12)
        w = np.clip(tau + 6 - k0, 0, 1)
        return T[i, k0] * (1 - w) + T[i, k1] * w


_ABACI = {}


def abaco(pdfname, seite):
    k = (pdfname, seite)
    if k not in _ABACI:
        _ABACI[k] = Abaco(os.path.join(PDF, pdfname), seite)
    return _ABACI[k]


# Kurzname -> (PDF, Bezugshafen in unserer Datei, Faktor(Hub, Dauer))
HEFTE = {
    'sao-marcos': dict(pdf='ccm-baia-sao-marcos.pdf', hafen=(S.TAFELN, 'Sao Luis, Maranh\u00e3o, Brazil'),
                       faktor=faktor_sao_marcos),
    'guanabara': dict(pdf='ccm-baia-de-guanabara.pdf', hafen=(S.OBS, 'Ilha Fiscal, Rio de Janeiro, Brazil'),
                      faktor=lambda h, d: abaco('ccm-baia-de-guanabara.pdf', 5)(h, d)),
    'santos': dict(pdf='ccm-porto-de-santos.pdf', hafen=(S.TAFELN, 'Santos (Macuco), S\u00e3o Paulo, Brazil'),
                   faktor=lambda h, d: abaco('ccm-porto-de-santos.pdf', 5)(h, d)),
    'paranagua': dict(pdf='ccm-porto-de-paranagua.pdf', hafen=(S.TAFELN, 'Paranagu\u00e1 (Cais Oeste), Paran\u00e1, Brazil'),
                      faktor=lambda h, d: abaco('ccm-porto-de-paranagua.pdf', 4)(h, d)),
    'salvador': dict(pdf='ccm-porto-de-salvador.pdf',
                     hafen=(os.path.join(ROOT, 'harmonics/ticon/harmonics_ticon4_worldwide.txt'), 'Salvador (Porto), Bahia, Brazil'),
                     faktor=faktor_salvador),
    'santos': dict(pdf='ccm-porto-de-santos.pdf', hafen=(S.TAFELN, 'Santos (Macuco), S\u00e3o Paulo, Brazil'),
                   faktor=lambda h, d: abaco('ccm-porto-de-santos.pdf', 5)(h, d)),
    'paranagua': dict(pdf='ccm-porto-de-paranagua.pdf', hafen=(S.TAFELN, 'Paranagu\u00e1 (Cais Oeste), Paran\u00e1, Brazil'),
                      faktor=lambda h, d: abaco('ccm-porto-de-paranagua.pdf', 4)(h, d)),
    'salvador': dict(pdf='ccm-porto-de-salvador.pdf',
                     hafen=(os.path.join(ROOT, 'harmonics/ticon/harmonics_ticon4_worldwide.txt'), 'Salvador (Porto), Bahia, Brazil'),
                     faktor=faktor_salvador),
    # Vitoria: blaue Zahlen = 5 m Tiefgang (oberflaechennah); Tabelle I westlich, II oestlich der
    # gestrichelten Linie bei der Ilha das Cobras. Bezug PM Vitoria (Ilha do Urubu).
    'vitoria': dict(pdf='ccm-porto-de-vitoria.pdf', hafen=(S.TAFELN, 'Vit\u00f3ria (Porto), Esp\u00edrito Santo, Brazil'),
                    farbe='blau', korrektur={'I': 5, 'II': 7}),
    # Madre de Deus: Tabelle I Area Norte, II Area Sul (gestrichelte Linie); Mittel 0-8 m.
    'madre-de-deus': dict(pdf='ccm-porto-de-madre-de-deus.pdf', hafen=(S.TAFELN, 'Madre de Deus, Bahia, Brazil'),
                          korrektur={'I': 5, 'II': 7},
                          # Randbeschriftung mit Sekunden ("30”", aber "12º 45”" = 12°45'): von Hand, Massstab geprueft
                          gitter=(((284.0, 12 + 45 / 60), (498.0, 12 + 45.5 / 60)),
                                  ((275.0, 38 + 38 / 60), (488.5, 38 + 37.5 / 60)))),
}


def teilung(pdf):
    """Gestrichelte rote Trennlinie der Tabellen-Gebiete (angezeigte Lage) -> Funktion (x, y) -> 'I'/'II'.
    Senkrechte Linie: links = I; waagrechte Linie: oben = I."""
    d = fitz.open(pdf)
    for p in d:
        if stunde(p) is None:
            continue
        m = _dreh(p)
        for g in p.get_drawings():
            if g['type'] == 's' and _rot(g.get('color')) and g.get('dashes') not in (None, '[] 0'):
                r = g['rect'] * m
                if max(r.width, r.height) > 60:
                    if r.height > r.width:
                        xm = (r.x0 + r.x1) / 2
                        return lambda x, y: 'I' if x < xm else 'II'
                    ym = (r.y0 + r.y1) / 2
                    return lambda x, y: 'I' if y < ym else 'II'
    raise ValueError('keine Trennlinie in %s' % pdf)


# Vorgeschlagene Namen je Punkt (Satz.Nr wie im Lauf; Punkte ohne Namen werden nicht als Block geschrieben).
# Ortsnamen aus der Karte bzw. wie bei Google Maps (Portugiesisch).
NAMEN = {
    'sao-marcos': {
        '1.10': 'Baía de São Marcos (Farol Itacolomi)',
        '2.1': 'Baía de São Marcos (Banco da Cerca)',
        '2.2': 'Baía de São Marcos (Rota Aconselhada)',
        '2.3': 'Banco do Cotovelo (Baía de São Marcos)',
        '2.4': "Ponta d'Areia (Baía de São Marcos)",
        '2.5': 'Pedra do Severino (Baía de São Marcos)',
        '2.6': 'Ilha do Medo (Baía de São Marcos)',
        '2.7': 'Canal do Boqueirão (Baía de São Marcos)',
        '2.8': "Farol de Ponta d'Areia (São Luís)",
        '2.9': 'Banco da Minerva (São Luís)',
        '2.11': 'Rio Anil (São Luís)',
        '2.12': 'Cabeço Mearim (Baía de São Marcos)',
        '2.13': 'Porto do Itaqui',
    },
    'guanabara': {
        '1.3': 'Entrada da Baía de Guanabara',
        '1.9': 'Baía de Guanabara (Ilha de Villegagnon)',
        '1.2': 'Baía de Guanabara (Ponte Rio-Niterói)',
    },
    'vitoria': {
        '1.4': 'Baixio do Tagano (Porto de Vitória)',
        '1.6': 'Porto de Vitória (Canal de Acesso)',
        '1.3': 'Ilha do Urubu (Porto de Vitória)',
        '1.7': 'Cais da Usiminas (Porto de Vitória)',
    },
    'santos': {
        '1.2': 'Ponta da Praia (Canal do Porto de Santos)',
        '1.3': 'Canal do Porto de Santos (Macuco)',
        '1.4': 'Canal do Porto de Santos (Ilha Barnabé)',
    },
    'paranagua': {
        '1.3': 'Baía de Paranaguá (Ilha do Mel)',
        '1.2': 'Porto de Paranaguá',
    },
    'salvador': {
        '1.1': 'Entrada da Baía de Todos os Santos',
        '1.2': 'Banco da Panela (Baía de Todos os Santos)',
    },
    'madre-de-deus': {
        '1.9': 'Madre de Deus (Praia do Loreto)',
        '1.2': 'Terminal de Madre de Deus (Posto S-2)',
        '1.12': 'Terminal de Madre de Deus (Norte)',
    },
}
HEFT_TITEL = {'sao-marcos': 'DG 10-V-1 Proximidades da Baía de São Marcos / Portos de São Luís e Itaqui',
              'guanabara': 'Baía de Guanabara',
              'vitoria': 'Pôrto de Vitória (blue values, ships of 5 m draft)',
              'madre-de-deus': 'Porto de Madre de Deus (layer 0-8 m)',
              'santos': 'Porto de Santos', 'paranagua': 'Porto de Paranaguá', 'salvador': 'Porto de Salvador'}
REGION = {'sao-marcos': 'Maranh\u00e3o, Brazil', 'guanabara': 'Rio de Janeiro, Brazil',
          'vitoria': 'Esp\u00edrito Santo, Brazil', 'madre-de-deus': 'Bahia, Brazil',
          'santos': 'S\u00e3o Paulo, Brazil', 'paranagua': 'Paran\u00e1, Brazil', 'salvador': 'Bahia, Brazil'}
REGEL = {'guanabara': 'speed factor from the booklet abacus (tidal range and PM-BM duration)',
         'santos': 'speed factor from the booklet abacus (tidal range and PM-BM duration)',
         'paranagua': 'speed factor from the booklet abacus (tidal range and PM-BM duration)',
         'salvador': 'speed factor from the booklet scale (mean tidal range)',
         'vitoria': 'additive speed corrections from the booklet tables I/II (tidal range, hour)',
         'madre-de-deus': 'additive speed corrections from the booklet tables I/II (tidal range, hour)'}


def block(kurz, pdfname, hafen, zeile, r, name):
    from cmems_stroemung_nachholen import CONSTITUENTS_175, utide
    L = ['# Harmonic constants derived from the CHM/DHN tidal stream charts "Cartas de Correntes de Mare"',
         '# %s (%s), point %s, mean spring values' % (HEFT_TITEL[kurz], pdfname, zeile['punkt']),
         '# Chart rule: hours from HW %s (13 charts HW-6..HW+6), %s,'
         % (hafen[1].split(',')[0], REGEL.get(kurz, 'speed factor from tidal range (booklet table)')),
         '# one synthetic year 2026; no time correction%s'
         % ('; charts include the mean wind drift (NE trade)' if kurz == 'sao-marcos' else ''),
         '# Chart values (kn@deg, HW-6..HW+6): %s' % zeile['werte'],
         '# (UTide v%s, principal-axis projection)' % utide.__version__,
         '# %d 10-minute samples, surface' % r['n'],
         '# from %s to %s' % (r['t0'].strftime('%Y-%m-%d'), r['t1'].strftime('%Y-%m-%d')),
         '# R^2 = %.4f, RMS error = %.4f knots' % (r['r2'], r['rms']),
         '# Major axis: %.1f deg true' % r['achse'], '#',
         '# BEGIN HOT COMMENTS',
         '# country: Brazil',
         '# source: CHM/DHN Cartas de Correntes de Mare (charts), UTide analysis',
         '# station_id_context: CHM-CCM-%s-%s' % (kurz.upper(), zeile['punkt']),
         '# institution: Centro de Hidrografia da Marinha (DHN)',
         '# datum: n/a', '# station_type: current',
         '# major_axis_deg_true: %.1f' % r['achse'],
         '# confidence: 5',
         '# chm_ccm: %s point %s' % (pdfname, zeile['punkt']),
         '# time_correction_min: 0',
         '# utide: period=%s..%s const=%d' % (r['t0'].strftime('%Y-%m-%d'), r['t1'].strftime('%Y-%m-%d'), len(r['konst'])),
         '# !units: knots', '# !longitude: %.4f' % zeile['lon'], '# !latitude: %.4f' % zeile['lat'],
         '%s, %s Current' % (name, REGION[kurz]), '+00:00 :UTC', '%.4f knots' % r['mean']]
    for k, _sp in CONSTITUENTS_175:
        a = r['konst'].get(k)
        L.append('%-15s %.4f  %.2f' % (k, a[0], a[1]) if a and a[0] >= 0.00005 else 'x 0 0')
    return '\n'.join(L)


def _rot(c):
    return bool(c) and c[0] > 0.8 and c[1] < 0.4 and c[2] < 0.4


def _punkte(g):
    out = []
    for it in g['items']:
        out += [q for q in it[1:] if hasattr(q, 'x')]
    return out


def _dreh(p):
    """PyMuPDF liefert Zeichnungen und Text im ungedrehten Seitensystem; quer liegende Hefte
    (Vitoria, Madre de Deus: /Rotate 90) erst in die angezeigte Lage bringen."""
    return p.rotation_matrix


def _rect(p, bbox):
    return fitz.Rect(bbox) * _dreh(p)


def _richtung(p, d):
    m = _dreh(p)
    x, y = d[0] * m.a + d[1] * m.c, d[0] * m.b + d[1] * m.d
    return (round(x, 3), round(y, 3))


def pfeile(p):
    """-> Liste dict(x, y = Pfeilfuss, mx, my = Pfeilmitte, dir) in PDF-Punkten; dir = wohin, Grad (Kartennord oben)."""
    schaefte, spitzen = [], []
    m = _dreh(p)
    for g in p.get_drawings():
        if g.get('dashes') not in (None, '[] 0'):
            continue                                    # gestrichelte Trennlinie der Tabellen-Gebiete
        if g['type'] == 's' and _rot(g.get('color')):
            schaefte.append([q * m for q in _punkte(g)])
        elif g['type'] == 'f' and _rot(g.get('fill')):
            spitzen.append([q * m for q in _punkte(g)])
    out = []
    frei = list(range(len(schaefte)))
    for h in spitzen:
        cx = sum(q.x for q in h) / len(h)
        cy = sum(q.y for q in h) / len(h)
        best = None
        for k in frei:
            s = schaefte[k]
            for a, b in ((s[0], s[-1]), (s[-1], s[0])):
                d = math.hypot(b.x - cx, b.y - cy)
                if best is None or d < best[0]:
                    best = (d, a, k)
        if best is None or best[0] > 15:
            continue
        _, fuss, k = best
        frei.remove(k)
        spitze = max(h, key=lambda q: math.hypot(q.x - fuss.x, q.y - fuss.y))
        rw = math.degrees(math.atan2(spitze.x - fuss.x, -(spitze.y - fuss.y))) % 360
        # Der Messpunkt ist der Fuss des Pfeils: der bleibt in allen 13 Karten liegen
        out.append(dict(x=fuss.x, y=fuss.y, mx=(fuss.x + spitze.x) / 2, my=(fuss.y + spitze.y) / 2, dir=rw))
    return out


def _blaeulich(c):
    # Vitoria: blaue Zahlen (0x00aeef) = Wirkung auf Schiffe mit 5 m Tiefgang
    r, g, b = c >> 16, (c >> 8) & 255, c & 255
    return b > 0xb0 and r < 0x60


def zahlen(p, farbe='rot'):
    test = _roetlich if farbe == 'rot' else _blaeulich
    out = []
    for b in p.get_text('dict')['blocks']:
        for l in b.get('lines', []):
            for s in l['spans']:
                t = s['text'].strip()
                if test(s['color']) and re.fullmatch(r'\d,\d', t):
                    x0, y0, x1, y1 = _rect(p, s['bbox'])
                    out.append(dict(x=(x0 + x1) / 2, y=(y0 + y1) / 2, v=float(t.replace(',', '.'))))
    return out


def stunde(p):
    """'6 HORAS ANTES DA PREAMAR ...' -> -6, 'PREAMAR ...' -> 0; None wenn keine Stundenkarte."""
    for b in p.get_text('dict')['blocks']:
        for l in b.get('lines', []):
            t = ''.join(s['text'] for s in l['spans']).strip().upper()
            m = re.match(r'^(\d+) HORAS? (ANTES|DEPOIS) DA PREAMAR', t)
            if m:
                return int(m.group(1)) * (-1 if m.group(2) == 'ANTES' else 1)
            if re.match(r'^PREAMAR( (DE|EM|NO|NA) [^.]*)?$', t):
                return 0
    return None


_GRAD = re.compile(r"^(\d{1,3})\s*[º°]\s*(?:(\d{1,2})\s*['’])?$")
_MIN = re.compile(r"^(\d{1,2})\s*['’]$")


def gradnetz(p):
    """Lineare Abbildung PDF -> (lat, lon) aus der Randbeschriftung. Sued und West negativ."""
    W, H = p.rect.width, p.rect.height
    oben, links, rechts = [], [], []
    for b in p.get_text('dict')['blocks']:
        for l in b.get('lines', []):
            spans = [s for s in l['spans'] if _dunkel(s['color'])]
            t = ''.join(s['text'] for s in spans).strip()
            if not t or _richtung(p, l['dir']) != (1.0, 0.0):
                continue
            x0, y0, x1, y1 = _rect(p, l['bbox'])
            m = _GRAD.match(t)
            n = _MIN.match(t)
            if not (m or n):
                continue
            wert = (int(m.group(1)), int(m.group(2) or 0)) if m else (None, int(n.group(1)))
            if x1 < 0.13 * W:
                # Breitenspalte links vom Kartenrahmen (die Laengen-Eckmarke sitzt weiter rechts)
                links.append(((y0 + y1) / 2, wert))
            elif x0 > 0.87 * W:
                rechts.append(((y0 + y1) / 2, wert))
            elif y1 < 0.2 * H:
                oben.append(((x0 + x1) / 2, wert))
    return _achse(links if len(links) >= len(rechts) else rechts, False), _achse(oben, True)


def _achse(lab, lon):
    """Beschriftung entlang einer Achse -> (a, b) mit Grad = a + b*Position (Betrag)."""
    lab = sorted(lab)
    # Doppelte (Grad-Zeile + Minuten-Zeile eng beieinander) zusammenfassen
    merged = []
    for pos, (g, m) in lab:
        # "44º" und "20'" als getrennte Zeilen: zusammen "44º 20'", Linie in der Mitte
        if merged and g is None and pos - merged[-1][0] < 16 and merged[-1][1][0] is not None \
                and merged[-1][1][1] == 0:
            pg, (gg, _mm) = merged[-1]
            merged[-1] = ((pg + pos) / 2, (gg, m))
            continue
        merged.append((pos, (g, m)))
    # Eckbeschriftung der anderen Achse sitzt dicht neben der ersten/letzten Marke: weg damit
    while len(merged) > 3:
        gaps = np.diff([q for q, _ in merged])
        med = np.median(gaps)
        if gaps[0] < 0.5 * med:
            merged.pop(1 if merged[0][1][0] is not None and merged[1][1][0] is None else 0)
        elif gaps[-1] < 0.5 * med:
            merged.pop(-2 if merged[-1][1][0] is not None and merged[-2][1][0] is None else -1)
        else:
            break
    anker =[i for i, (_, (g, _m)) in enumerate(merged) if g is not None]
    if not anker:
        raise ValueError('keine Grad-Beschriftung')
    i0 = anker[0]
    werte = [None] * len(merged)
    werte[i0] = merged[i0][1][0] + merged[i0][1][1] / 60
    # Richtung aus zwei Ankern oder aus den Minuten-Nachbarn ableiten: von i0 aus abwickeln
    for rng in (range(i0 + 1, len(merged)), range(i0 - 1, -1, -1)):
        prev = i0
        for i in rng:
            g, m = merged[i][1]
            if g is not None:
                werte[i] = g + m / 60
            else:
                pm = round((werte[prev] % 1) * 60)
                d = (m - pm + 30) % 60 - 30
                if d == -30:
                    d = 30
                werte[i] = werte[prev] + d / 60
            prev = i
    pos = np.array([q for q, _ in merged])
    w = np.array(werte)
    b, a = np.polyfit(pos, w, 1)
    rest = w - (a + b * pos)
    if np.abs(rest).max() > 0.3 / 60 * max(1, np.ptp(w) * 2):
        raise ValueError('Gradnetz unstimmig: %s' % list(zip(pos.round(), (w * 60).round(1))))
    return a, b


def kartensaetze(pdf, farbe='rot', gitter=None):
    """-> Liste von Saetzen; Satz = dict(stunde -> (page, pfeile_mit_v, (lat_ab, lon_ab)))."""
    d = fitz.open(pdf)
    saetze, aktuell = [], None
    for i in range(d.page_count):
        p = d[i]
        if len(p.get_drawings()) < 20:
            continue
        h = stunde(p)
        if h is None:
            continue
        P, Z = pfeile(p), zahlen(p, farbe)
        if len(P) < 3:
            continue                                # Tabellenseite mit dem Wort "Preamar"
        if h == -6 or aktuell is None or h in aktuell:
            aktuell = {}
            saetze.append(aktuell)
        # Zahl -> Pfeil (Abstand Textmitte - Pfeilmitte, hoechstens 22 pt)
        mit = []
        if P and Z:
            M = np.array([[math.hypot(a['mx'] - z['x'], a['my'] - z['y']) for z in Z] for a in P])
            r, c = linear_sum_assignment(M)
            for ri, ci in zip(r, c):
                if M[ri, ci] <= 22:
                    mit.append(dict(P[ri], v=Z[ci]['v']))
        lat_ab, lon_ab = gitter if gitter else gradnetz(p)
        aktuell[h] = (i + 1, mit, (lat_ab, lon_ab), len(P), len(Z))
    return saetze


def spuren(satz, anker='fuss', max_pt=20):
    """Pfeile ueber die Stunden verbinden -> Liste von {stunde: pfeil}.

    anker: 'fuss' (Messpunkt am Pfeilfuss, Sao Marcos) oder 'mitte' (Stroemungsbild mit
    Pfeilen um eine feste Mitte, Guanabara). Verglichen wird mit der zuletzt gesehenen Lage
    jeder Spur, damit eine Stunde ohne zugeordnete Zahl die Spur nicht zerreisst.
    """
    kx, ky = ('x', 'y') if anker == 'fuss' else ('mx', 'my')
    if anker == 'mitte':
        return _gruppen(satz)
    sp = []
    for h in sorted(satz):
        B = satz[h][1]
        if not B:
            continue
        genutzt = set()
        if sp:
            letzte = [s[max(s)] for s in sp]
            M = np.array([[math.hypot(a[kx] - b[kx], a[ky] - b[ky]) for b in B] for a in letzte])
            r, c = linear_sum_assignment(M)
            for ri, ci in zip(r, c):
                if M[ri, ci] <= max_pt:
                    sp[ri][h] = B[ci]
                    genutzt.add(ci)
        for k, b in enumerate(B):
            if k not in genutzt:
                sp.append({h: b})
    return sp


def _gruppen(satz, abstand_pt=28):
    """Stroemungsbild: beschriftete Pfeile aller Stunden nach Lage der Pfeilmitte gruppieren
    (die Pfeile stehen nur ungefaehr an derselben Stelle). Je Stunde zaehlt der Pfeil, der der
    Gruppenmitte am naechsten liegt."""
    from scipy.cluster.hierarchy import fcluster, linkage
    alle = [(h, a) for h in sorted(satz) for a in satz[h][1]]
    if len(alle) < 2:
        return []
    xy = np.array([[a['mx'], a['my']] for _, a in alle])
    lab = fcluster(linkage(xy, 'average'), abstand_pt, 'distance')
    sp = []
    for g in sorted(set(lab)):
        idx = np.where(lab == g)[0]
        mx, my = xy[idx].mean(axis=0)
        s = {}
        for i in sorted(idx, key=lambda i: math.hypot(xy[i, 0] - mx, xy[i, 1] - my)):
            h, a = alle[i]
            s.setdefault(h, a)
        sp.append(s)
    sp.sort(key=lambda s: (-len(s), min(s)))
    return sp


PERIODE_H = 12.42                       # M2: -6 h und +6 h liegen einen Zyklus auseinander


def luecke_max(s):
    """Groesste Luecke (h) zwischen belegten Stunden, ueber den Zyklus herum gerechnet."""
    std = sorted(s)
    gaps = np.diff(std + [std[0] + PERIODE_H])
    return float(gaps.max())


def zyklus_aus(s):
    """Spur -> Array (13, 2) u, v in Knoten; fehlende Stunden linear in u/v aufgefuellt, ueber den
    Zyklus herum (Vitoria zeigt manche Punkte nur jede zweite Stunde)."""
    std = sorted(s)
    uv = np.array([[s[h]['v'] * math.sin(math.radians(s[h]['dir'])),
                    s[h]['v'] * math.cos(math.radians(s[h]['dir']))] for h in std])
    x = np.array(std, float)
    x = np.concatenate([x - PERIODE_H, x, x + PERIODE_H])
    uv = np.vstack([uv, uv, uv])
    alle = np.arange(-6, 7)
    return np.column_stack([np.interp(alle, x, uv[:, 0]), np.interp(alle, x, uv[:, 1])])


def lage(satz, s, anker='fuss'):
    """Mittlere Position der Spur in Grad (S/W negativ)."""
    kx, ky = ('x', 'y') if anker == 'fuss' else ('mx', 'my')
    la, lo = [], []
    for h, a in s.items():
        (aa, ab), (oa, ob) = satz[h][2]
        la.append(-(aa + ab * a[ky]))
        lo.append(-(oa + ob * a[kx]))
    return float(np.mean(la)), float(np.mean(lo))


def reihe(hafen, faktor, zyklus, jahr=2026, schritt_min=10, korrektur=None, gebiet=None):
    """zyklus: Array (13, 2) u, v in Knoten fuer -6..+6 h -> DataFrame u, v in m/s.

    faktor(Hub m, Dauer h) multipliziert; korrektur(gebiet, Hub cm, Stunde) addiert Knoten zum
    Betrag (Richtung bleibt, nicht unter 0)."""
    pfad, name = hafen
    t0 = dt.datetime(jahr, 1, 1, tzinfo=dt.timezone.utc).timestamp()
    t = np.arange(t0 - 2 * 86400, t0 + 367 * 86400, 120.0)
    h = S.gezeit(pfad, name, t)
    tp, hp = S.scheitel(t, h, True)
    tl, hl = S.scheitel(t, h, False)
    hub = hp - np.interp(tp, tl, hl)
    # Dauer PM<->BM: Mittel aus fallender und steigender Haelfte um die PM
    j = np.clip(np.searchsorted(tl, tp), 1, len(tl) - 1)
    dauer = ((tp - tl[j - 1]) + (tl[j] - tp)) / 2 / 3600.0
    ts = np.arange(t0, t0 + 365 * 86400, schritt_min * 60.0)
    k = np.clip(np.searchsorted(tp, ts), 1, len(tp) - 1)
    k -= (ts - tp[k - 1]) < (tp[k] - ts)
    tau = np.clip((ts - tp[k]) / 3600.0, -6, 6)
    knoten = np.arange(-6, 7)
    u = np.interp(tau, knoten, zyklus[:, 0])
    v = np.interp(tau, knoten, zyklus[:, 1])
    if faktor is not None:
        fak = faktor(hub, dauer)
        u, v = u * fak[k], v * fak[k]
    if korrektur is not None:
        betrag = np.hypot(u, v)
        neu = np.maximum(betrag + korrektur(gebiet, hub[k] * 100.0, tau), 0.0)
        q = np.where(betrag > 1e-6, neu / np.maximum(betrag, 1e-6), 0.0)
        u, v = u * q, v * q
    return pd.DataFrame({'u': u / MS_KN, 'v': v / MS_KN}, index=pd.to_datetime(ts, unit='s')), \
        float(np.mean(hub)), float(np.percentile(hub, 90))


def main(argv):
    kurz = argv[1]
    cfg = HEFTE[kurz]
    pdfname, hafen, faktor = cfg['pdf'], cfg['hafen'], cfg.get('faktor')
    gitter = None
    if cfg.get('gitter'):
        # feste Stuetzpunkte (angezeigte Lage): ((y1, lat1), (y2, lat2)), ((x1, lon1), (x2, lon2)) in Grad (Betrag)
        (ya, la), (yb, lb) = cfg['gitter'][0]
        (xa, oa), (xb, ob) = cfg['gitter'][1]
        gitter = ((la - ya * (lb - la) / (yb - ya), (lb - la) / (yb - ya)),
                  (oa - xa * (ob - oa) / (xb - xa), (ob - oa) / (xb - xa)))
    saetze = kartensaetze(os.path.join(PDF, pdfname), cfg.get('farbe', 'rot'), gitter)
    korr = Korrektur(os.path.join(PDF, pdfname), cfg['korrektur'], cfg.get('farbe', 'rot')) if cfg.get('korrektur') else None
    gebiet_von = teilung(os.path.join(PDF, pdfname)) if korr else None
    heute = dt.date.today().strftime('%Y%m%d')
    zeilen, bloecke = [], []
    for si, satz in enumerate(saetze, 1):
        stunden = sorted(satz)
        print('Satz %d: Stunden %s, Seiten %s' % (si, stunden, [satz[h][0] for h in stunden]))
        for h in stunden:
            pg, mit, _, nP, nZ = satz[h]
            if len(mit) != nZ:
                print('  Seite %d: %d Zahlen, nur %d einem Pfeil zugeordnet' % (pg, nZ, len(mit)))
        voll = lambda sp: sum(1 for t in sp if len(t) >= 12)
        anker = max(('fuss', 'mitte'), key=lambda a: voll(spuren(satz, a)))
        print('  Anker: Pfeil%s' % anker)
        for pi, s in enumerate(spuren(satz, anker), 1):
            fehlt = [h for h in range(-6, 7) if h not in s]
            if len(s) < 6 or luecke_max(s) > 2.5:
                print('  Punkt %d.%d unvollstaendig (%d Stunden) bei %s' % (si, pi, len(s), lage(satz, s, anker)))
                continue
            lat, lon = lage(satz, s, anker)
            z = zyklus_aus(s)
            # Plausibilitaet: groesster Richtungssprung zwischen Nachbarstunden bei kraeftigem Strom
            std = sorted(s)
            spr = 0.0
            for h0, h1 in zip(std, std[1:]):
                if min(s[h0]['v'], s[h1]['v']) >= 0.5:
                    d = abs((s[h1]['dir'] - s[h0]['dir'] + 180) % 360 - 180)
                    spr = max(spr, d)
            h0 = 0 if 0 in s else 1
            pos = 'seite %d x %.0f y %.0f' % (satz[h0][0], s[h0]['x'], s[h0]['y'])
            zeile = dict(punkt='%d.%d' % (si, pi), lat=round(lat, 4), lon=round(lon, 4),
                         vmax=max(s[h]['v'] for h in s), sprung=round(spr), fehlt=' '.join(map(str, fehlt)),
                         pdf=pos, werte=' '.join('%g@%03.0f' % (s[h]['v'], s[h]['dir']) if h in s else '-'
                                                 for h in range(-6, 7)))
            if '--nur-punkte' not in argv:
                geb = gebiet_von(s[h0]['x'], s[h0]['y']) if gebiet_von else None
                zeile['gebiet'] = geb or ''
                df, hub_m, _ = reihe(hafen, faktor, z, korrektur=korr, gebiet=geb)
                r = C.analyse(df, lat, S.KONST)
                zeile.update(achse=round(r['achse'], 1), r2=round(r['r2'], 4), m2=round(r['m2'], 3),
                             s2=round(r['s2'], 3), m2_phase=round(r['konst'].get('M2', (0, 0))[1], 1),
                             mean=round(r['mean'], 3), hub_mittel=round(hub_m, 2))
                bloecke.append((zeile, r))
            zeilen.append(zeile)
            print('  %s' % {k: zeile[k] for k in zeile if k != 'werte'})
    os.makedirs(HILFE, exist_ok=True)
    out = os.path.join(HILFE, 'chm_ccm_%s_%s' % (kurz, heute))
    with open(out + '.csv', 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=list(zeilen[0].keys()) if zeilen else ['punkt'])
        w.writeheader()
        for z in zeilen:
            w.writerow(z)
    print('->', out + '.csv', len(zeilen), 'Punkte')
    namen = NAMEN.get(kurz, {})
    txt = [block(kurz, pdfname, hafen, z, r, namen[z['punkt']]) for z, r in bloecke if z['punkt'] in namen]
    if txt:
        with open(out + '.txt', 'w', encoding='iso-8859-1') as f:
            f.write('\n\n'.join(txt) + '\n')
        print('->', out + '.txt', len(txt), 'Bloecke')


if __name__ == '__main__':
    main(sys.argv)
