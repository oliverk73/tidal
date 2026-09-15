#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Nebenhaefen aus den Konkordanztabellen des Instituto Hidrográfico.

Quellen:
  harmonics/help/ih_konkordanzen_I_2026.tsv   Vol. I, S. 3-2/3-3, vom Seitenbild abgelesen
  Vol. II, S. 3-3/3-4 direkt aus dem PDF (nur Zeitkorrektur PM/BM und Relacao de amplitude)

Verfahren je Nebenhafen:
  1. Grundsatz = der Bestandssatz am Standardhafen (<= 3 km), der die IH-Tafel 2026 dieses
     Hafens am besten trifft (Hoehe an den Scheiteln + Scheitelzeit); die IH-Konstanten
     selbst sind ebenfalls Kandidat.
  2. Kunstscheitel: jede Hoch-/Niedrigwasserzeile der IH-Tafel des Standardhafens wird nach
     IH-Regel umgerechnet. Zeit- und Hoehenkorrektur werden zwischen Nipp (AM) und Spring
     (AV) nach dem Hub der jeweiligen Tide gewichtet. Ohne Hoehenkorrektur gilt die
     Amplitudenrelation: h' = NM' + r (h - NM).
  3. Uebertragung des Grundsatzes (Hubfaktoren Spring/Nipp wie bei ATT, mittlere
     Zeitkorrektur als Phasendrehung, Seichtwasser mit rM^2).
  4. Nachfuehrung: gedaempftes Ausgleichsproblem gegen die Kunstscheitel (Hoehe und
     waagerechte Tangente, py/scheitelfit.py), frei sind Z0 und wenige Tiden; jede
     Aenderung kostet (Vorwissen = Uebertragung), damit die Kurve zwischen den Scheiteln
     nicht davonlaeuft.

Usage: python3 py/ih_nebenhaefen.py [--probe] [--liste] [Name ...]
  --probe   Verfahren am Standardhafen Praia pruefen (Konkordanz zu Porto Grande)
  --liste   harmonics/help/ih_nebenhaefen.csv schreiben
"""
from __future__ import annotations

import collections
import csv
import math
import os
import re
import subprocess
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ih_portugal_tafel as IH                                     # noqa: E402
import ih_saetze as IS                                             # noqa: E402
import noaa_pruefstand as P                                        # noqa: E402
import scheitelfit as S                                            # noqa: E402
from health_check import km, load_records                          # noqa: E402

ROOT = IS.ROOT
KOPF = IS.KOPF
SP = IS.SP
TSV_I = os.path.join(ROOT, 'harmonics/help/ih_konkordanzen_I_2026.tsv')
LISTE = os.path.join(ROOT, 'harmonics/help/ih_nebenhaefen.csv')

SEMI = ('M2', 'N2', '2N2', 'MU2', 'NU2', 'LDA2', 'L2', 'T2', 'R2', 'MKS2', '2SM2', 'MNS2', 'MSN2', 'EPS2', 'OQ2', 'LAM2')
S_FAM = ('S2', 'K2')
DIURN = ('K1', 'O1', 'P1', 'Q1', '2Q1', 'M1', 'J1', 'OO1', 'S1', 'RHO1', 'SIG1', 'TAU1', 'CHI1', 'PHI1', 'THE1',
         'PI1', 'PSI1', 'NO1', 'SO1', 'MP1')
FREI = ('M2', 'S2', 'N2', 'K2', 'K1', 'O1', 'M4', 'MS4', 'MN4', 'M6', '2MS6', 'M8', 'SA', 'SSA')
# SA/SSA: die IH-Tafeln der Flusshaefen enthalten den jahreszeitlichen Wasserstand
# (Ponta Tangalane: 20 cm SA; ohne sie 16.6 cm, mit 3.0 cm)
SIGMA = {'SA': 0.20, 'SSA': 0.10, 'M2': 0.10, 'S2': 0.06, 'N2': 0.04, 'K2': 0.02, 'K1': 0.03, 'O1': 0.03,
         'M4': 0.10, 'MS4': 0.06, 'MN4': 0.04, 'M6': 0.04, '2MS6': 0.03, 'M8': 0.02}
RAUSCHEN = 0.05          # m: Tafelhoehen auf 0.1 m gerundet

# Konkordanz-Bezug -> Tafelname des Standardhafens
VOL_II_BEZUG = {'MORRUBUNE': 'Ponta Tangalane (Barra de Quelimane)'}
LAND_II = {'PORTO GRANDE': 'Cape Verde', 'CACHEU': 'Guinea-Bissau', 'CAIÓ': 'Guinea-Bissau',
           'BUBAQUE': 'Guinea-Bissau', 'ANA CHAVES': 'São Tomé and Príncipe',
           'SANTO ANTÓNIO': 'São Tomé and Príncipe', 'SOYO': 'Angola', 'LUANDA': 'Angola',
           'LOBITO': 'Angola', 'NAMIBE': 'Angola'}
TZ_LAND = {'Cape Verde': 'Atlantic/Cape_Verde', 'Guinea-Bissau': 'Africa/Bissau',
           'São Tomé and Príncipe': 'Africa/Sao_Tome', 'Angola': 'Africa/Luanda',
           'Mozambique': 'Africa/Maputo'}
# offensichtliche Druckfehler in Vol. II
KOORD_II = {'Água Izé': (0.2183, 6.7333),          # gedruckt 6 44.0 W; Sao Tome liegt oestlich
            # gedruckt 13 32.6 E = 110 km im Landesinneren; Cabo/Farol de Santa Maria (OSM) liegt auf
            # 13.4226 S 12.5343 E, die Breite 13 25.4 S stimmt -> Gradzahl verdruckt, 12 32.6 E
            'Santa Maria': (-13.4233, 12.5433),
            # Oliver 14.09.2026: das Buch nennt die Orte, nicht die Buchten. Santa Marta gedruckt 13 52.4 S
            # 12 29.1 E liegt an Land westlich der Baía das Luciras; der Ort liegt ~0.7 km vom Kap (Farol OSM
            # 13.878 S 12.423 E) wie ATT/NOAA. Baía dos Tigres gedruckt 16 36.1 S 11 49.3 E liegt in der Bucht;
            # der Ort (São Martinho dos Tigres) liegt auf der Insel wie ATT/NOAA.
            'Santa Marta': (-13.8772, 12.4327), 'Baía dos Tigres': (-16.5990, 11.7238),
            # Oliver 15.09.2026: auf die Position der Namensvettern (ATT)
            # Ibo gedruckt 12 11.8 S = 16 km noerdlich des Ortes an Land; ATT-Standardhafen/1997/NOAA am Ort
            'Ibo': (-12.3457, 40.5808),
            # Moma gedruckt 16 47.4 S 39 16.0 E = 5.6 km suedoestlich im Wasser; ATT "Moma (Rio Liganha)" am Ort
            'Moma': (-16.7672, 39.2214),
            # Sofala gedruckt 20 08.4 S 34 46.9 E; ATT 5 km suedwestlich
            'Sofala': (-20.1575, 34.7373),
            # Bazaruto gedruckt 21 31.8 S 35 29.9 E (Nordspitze der Insel); ATT/NOAA an der Westkueste
            'Bazaruto': (-21.6500, 35.4330)}
AUSLASSEN_II = {'Aproximação ao porto': 'Laenge 37 18.0 E liegt 250 km vor Beira (Druckfehler)',
                'Porto Gole': 'Canal do Geba, eigene Tabelle (siehe GEBA_ORTE)'}


def zahl(s):
    s = s.strip()
    return float(s) if s not in ('', '-', '–') else None


def nivel_medio(pdf):
    """{Tafelname: NM ueber ZH}: 'Nivel medio: 2,00 m' (Vol. I) bzw. 'x m abaixo do nivel medio' (Vol. II)."""
    L = IH.text(pdf)
    out, offen = {}, None
    for l in L:
        m = re.search(r'N[íi]vel m[ée]dio:\s*([\d,]+)\s*m', l) or re.search(r'([\d,]+)\s*m abaixo do n[íi]vel m[ée]dio', l)
        if m:
            offen = float(m.group(1).replace(',', '.'))
        elif offen is not None and l.strip().startswith('Porto de '):
            out.setdefault(l.strip()[9:], offen)
            offen = None
    return out


def _norm(s):
    return re.sub(r'[^A-Z]', '', s.upper().replace('Ç', 'C').replace('Ã', 'A').replace('Õ', 'O')
                  .replace('Ó', 'O').replace('Í', 'I').replace('É', 'E').replace('Ú', 'U').replace('Á', 'A')
                  .replace('Â', 'A').replace('Ê', 'E').replace('Ô', 'O'))


def tafelname(bezug, pdf):
    if bezug in VOL_II_BEZUG:
        return VOL_II_BEZUG[bezug]
    n = _norm(bezug)
    for h in IH.haefen(pdf):
        if _norm(h).startswith(n):
            return h
    raise KeyError(bezug)


def konstanten_zu(hafen, pdf):
    n = _norm(hafen.split('(')[0])
    alias = {'VILAREALDESANTOANTONIO': 'VILAREALDESTOANTONIO', 'PONTATANGALANE': 'QUELIMANE',
             'ANGOCHE': 'ANTONIOENES', 'SOYO': None, 'NAMIBE': 'NAMIBE'}
    n = alias.get(n, n)
    for k, v in IH.konstanten(pdf).items():
        kk = _norm(k.split(' .')[0])
        if n and (kk == n or n.startswith(kk) and len(kk) >= 5):
            return v
    return None


# ------------------------------------------------------------------ Konkordanzen lesen
# Vol. I: Porto Moniz gedruckt 17 19.9 W = 15 km westlich im Meer; FCUL und ATT (NP208) stehen auf
# 32.8664 N 17.1654 W (= 17 09.9 W) -- Anweisung Oliver 14.09.2026
KOORD_I = {'Porto Moniz': (32.8664, -17.1654)}


def konkordanzen_I():
    zeilen = []
    for l in open(TSV_I, encoding='utf-8'):
        if l.startswith('#') or l.startswith('typ\t'):
            continue
        f = l.rstrip('\n').split('\t'); f += [''] * (16 - len(f))
        la, lo = KOORD_I.get(f[2], (float(f[3]), float(f[4]))) if f[0] == 'SEC' else (float(f[3]), float(f[4]))
        zeilen.append(dict(typ=f[0], bezug=f[1], name=f[2], lat=la, lon=lo, nm=zahl(f[5]),
                           t=[zahl(x) for x in f[6:10]], h=[zahl(x) for x in f[10:14]],
                           r=[zahl(x) for x in f[14:16]], pdf=IH.PDF))
    return zeilen


def konkordanzen_II():
    txt = subprocess.run(['pdftotext', '-f', '173', '-l', '174', '-layout', IH.PDF_II, '-'],
                         capture_output=True, text=True).stdout
    out, ref, hemi = [], None, ('N', 'W')
    for l in txt.splitlines():
        l = l.replace('\t', ' ')
        m = re.match(r'^\s*(?:(?P<ref>[A-ZÇÃÁÉÍÓÚÔÊ][A-ZÇÃÁÉÍÓÚÔÊ ]+[A-ZÇÃÁÉÍÓÚÔÊ])(?: \.)*\s{2,})?\s*(?P<name>\S.*?)\s*(?: ?\.)+\s+'
                     r'(?P<lat>\d+ \d\d\.\d)\s*(?P<ns>[NS])?\s+(?P<lon>\d+ \d\d\.\d)\s*(?P<ew>[EW])?\s*(?P<rest>.*)$', l)
        if not m:
            continue
        if m['ref']:
            ref = m['ref'].strip()
        if m['ns']:
            hemi = (m['ns'], m['ew'])
        name = re.sub(r'^[. ]+', '', re.sub(r'^\(Barra de Quelimane\)\s+', '', m['name'])).strip()
        name = name.replace('llha', 'Ilha')
        g, mi = m['lat'].split(); la = (int(g) + float(mi) / 60) * (1 if hemi[0] == 'N' else -1)
        g, mi = m['lon'].split(); lo = (int(g) + float(mi) / 60) * (1 if hemi[1] == 'E' else -1)
        la, lo = KOORD_II.get(name, (la, lo))
        rest = m['rest'].replace('–', '-')
        if not re.match(r'^[-\d .]*$', rest):
            continue
        r = re.findall(r'\d\.\d\d', rest)
        zeit = re.sub(r'\d\.\d\d', '', rest)
        werte = [(-1 if s else 1) * (int(a) * 60 + int(b) if b else int(a))
                 for s, a, b in re.findall(r'(-)?\s*(\d+)(?:\s(\d\d)(?!\d))?', zeit)]
        if len(werte) != 2:
            continue
        pm, bm = werte
        out.append(dict(typ='SEC', bezug=ref, name=name, lat=la, lon=lo, nm=None, t=[pm, pm, bm, bm],
                        h=[None] * 4, r=[float(r[0])] * 2 if r else [None, None], pdf=IH.PDF_II))
    return out


# ------------------------------------------------------------------ Standardhafen
class Standard:
    def __init__(self, hafen, pdf, recs, pegel=None, nm=None):
        self.hafen, self.pdf = hafen, pdf
        self.lat, self.lon = IH.haefen(pdf)[hafen]
        self.scheitel = IH.scheitel(hafen, pdf)
        self.nm = nm if nm is not None else nivel_medio(pdf).get(hafen)
        if self.nm is None:
            self.nm = float(np.mean([h for _, h in self.scheitel]))
        kc = konstanten_zu(hafen, pdf)
        self.ihk = kc
        self.kandidaten = self._kandidaten(recs, kc)
        self.grund = min(self.kandidaten, key=lambda k: k['wert']) if self.kandidaten else None
        if self.grund and self.grund['rms'] > GRUND_NACHFUEHREN_CM:
            t = np.array([x[0] for x in self.scheitel]); h = np.array([x[1] for x in self.scheitel])
            z2, c2 = nachfuehren(self.grund['z0'], self.grund['con'], t, h)
            rms, hw, nw = scheitelguete(z2, c2, t, h)
            if rms < self.grund['rms']:
                self.grund = dict(self.grund, name=self.grund['name'] + ' (an die IH-Tafel nachgefuehrt)',
                                  z0=z2, con=c2, rms=rms, hw=hw, nw=nw, wert=rms + 0.3 * (abs(hw) + abs(nw)))
        if pegel is None:
            q = kc or (self.grund['con'] if self.grund else None)
            m2, s2 = q['M2'][0], q['S2'][0]
            pegel = [self.nm + m2 - s2, self.nm + m2 + s2, self.nm - m2 + s2, self.nm - m2 - s2]
        self.pegel = pegel                      # PMAM PMAV BMAM BMAV

    def _kandidaten(self, recs, kc):
        t = np.array([x[0] for x in self.scheitel]); h = np.array([x[1] for x in self.scheitel])
        out = []
        roh = []
        for r in recs:
            if r['lat'] is None or abs(r['lat'] - self.lat) > 0.05 or km(r, dict(lat=self.lat, lon=self.lon)) > 3.0:
                continue
            try:
                z0, con = P.satz(r)
            except Exception:
                continue
            roh.append((f"{os.path.basename(r['file'])}|{r['name']}", z0, con))
        if kc:
            roh.append(('IH-Konstanten', self.nm, IS.ih_satz(kc, 0.0)))
        for name, z0, con in roh:
            if 'M2' not in con:
                continue
            hm, h1, h2 = S.hoehe_und_ableitungen(t, z0, con, KOPF)
            off = float(np.mean(h - hm)); rms = float(np.sqrt(np.mean((hm + off - h) ** 2))) * 100
            dtm = np.clip(np.where(h2 != 0, -h1 / np.where(h2 != 0, h2, 1), 0) * 60, -120, 120)
            hw = h > np.median(h)
            ahw, anw = float(np.median(dtm[hw])), float(np.median(dtm[~hw]))
            out.append(dict(name=name, z0=z0 + off, con=con, rms=rms, hw=ahw, nw=anw,
                            wert=rms + 0.3 * (abs(ahw) + abs(anw))))
        return out


# ------------------------------------------------------------------ Umrechnung
def kunstscheitel(std, k):
    """IH-Regel auf jede Scheitelzeile der Standardtafel -> (Zeiten, Hoehen, Gewichte w)."""
    t = np.array([x[0] for x in std.scheitel]); h = np.array([x[1] for x in std.scheitel])
    pmam, pmav, bmam, bmav = std.pegel
    NR, SR = pmam - bmam, pmav - bmav
    nachbar = np.convolve(h, [0.5, 0, 0.5], mode='same'); nachbar[0], nachbar[-1] = h[1], h[-2]
    R = np.abs(h - nachbar)
    w = np.clip((R - NR) / (SR - NR), -0.25, 1.25) if SR - NR > 0.02 else np.full(len(h), 0.5)
    hw = h > nachbar
    if k.get('geba'):
        (ap, bp), (ab, bb) = k['hoehe']
        uhr = ((t / 3600.0 + GEBA_UHR_H) % 12.0)
        x = np.arange(13)
        rp = np.interp(uhr, x, GEBA_R_PM[k['name']] + GEBA_R_PM[k['name']][:1])
        rb = np.interp(uhr, x, GEBA_R_BM[k['name']] + GEBA_R_BM[k['name']][:1])
        tn = t + 60.0 * np.where(hw, rp, rb)
        hn = np.where(hw, ap * h + bp, ab * h + bb)
        o = np.argsort(tn)
        return tn[o], hn[o]
    ta = np.where(hw, k['t'][0], k['t'][2]); tv = np.where(hw, k['t'][1], k['t'][3])
    tn = t + 60.0 * (ta + w * (tv - ta))
    if k['h'][0] is not None:
        ha = np.where(hw, k['h'][0], k['h'][2]); hv = np.where(hw, k['h'][1], k['h'][3])
        hn = h + ha + w * (hv - ha)
    else:
        r = k['r'][0] + np.clip(w, 0, 1) * (k['r'][1] - k['r'][0])
        nm2 = k['nm'] if k['nm'] is not None else std.nm
        hn = nm2 + r * (h - std.nm)
    o = np.argsort(tn)
    return tn[o], hn[o]


def pegel_neben(std, k):
    p = std.pegel
    if k.get('geba'):
        (ap, bp), (ab, bb) = k['hoehe']
        return [ap * p[0] + bp, ap * p[1] + bp, ab * p[2] + bb, ab * p[3] + bb]
    if k['h'][0] is not None:
        return [p[0] + k['h'][0], p[1] + k['h'][1], p[2] + k['h'][2], p[3] + k['h'][3]]
    nm2 = k['nm'] if k['nm'] is not None else std.nm
    ra, rv = k['r']
    return [nm2 + ra * (p[0] - std.nm), nm2 + rv * (p[1] - std.nm), nm2 + ra * (p[2] - std.nm), nm2 + rv * (p[3] - std.nm)]


def uebertragen(std, k):
    g = std.grund
    p, q = std.pegel, pegel_neben(std, k)
    NR, SR = p[0] - p[2], p[1] - p[3]
    fS = max(0.02, (q[1] - q[3]) / SR); fN = max(0.02, (q[0] - q[2]) / NR) if NR > 0.02 else fS
    M2, S2 = g['con']['M2'][0], g['con'].get('S2', (0.0, 0.0))[0]
    su, di = fS * (M2 + S2), fN * (M2 - S2)
    M2n, S2n = max(0.0, 0.5 * (su + di)), max(0.0, 0.5 * (su - di))
    rM = M2n / M2; rS = S2n / S2 if S2 > 0 else fS; fD = 0.5 * (fS + fN)
    dt = float(np.mean(k['t'])) / 60.0
    out = {}
    for c, (a, G) in g['con'].items():
        if c == 'M2':
            na = M2n
        elif c == 'S2':
            na = S2n
        elif c in SEMI:
            na = a * rM
        elif c in S_FAM:
            na = a * rS
        elif c in DIURN:
            na = a * fD
        elif SP[c] < 5:
            na = a
        else:
            na = a * rM * rM
        out[c] = (na, (G + SP[c] * dt) % 360.0)
    z0 = g['z0'] + float(np.mean(q)) - float(np.mean(p))
    return z0, out


def nachfuehren(z0, con, t, h):
    """Gedaempfter Ausgleich gegen die Kunstscheitel (Aenderungen gegen die Uebertragung).

    Die Tangentengleichung wird so gewichtet, dass 5 min Scheitelfehler so viel zaehlen wie
    5 cm Hoehe (bei kleinen Tiden sonst wertlos: die Tafelhoehen sind auf 0.1 m gerundet).
    """
    frei = [c for c in FREI if c in SP]
    hm, h1, _ = S.hoehe_und_ableitungen(t, z0, con, KOPF)
    C, Sn, w = S.X.matrix(t, frei, KOPF[1], KOPF[2], KOPF[3])
    n = len(frei)
    A = np.zeros((2 * len(t) + 2 * n, 1 + 2 * n)); b = np.zeros(2 * len(t) + 2 * n)
    A[:len(t), 0] = 1.0; A[:len(t), 1:1 + n] = C; A[:len(t), 1 + n:] = Sn; b[:len(t)] = h - hm
    m2 = max(0.15, con['M2'][0])
    gw = min(10.0, max(1.0, 2.3 / m2))
    A[len(t):2 * len(t), 1:1 + n] = -gw * w * Sn; A[len(t):2 * len(t), 1 + n:] = gw * w * C
    b[len(t):2 * len(t)] = -gw * h1
    for j, c in enumerate(frei):
        lam = RAUSCHEN / SIGMA[c] * math.sqrt(len(t) / 50.0)
        A[2 * len(t) + j, 1 + j] = lam; A[2 * len(t) + n + j, 1 + n + j] = lam
    x, *_ = np.linalg.lstsq(A, b, rcond=None)
    neu = dict(con)
    for j, c in enumerate(frei):
        a0, g0 = con.get(c, (0.0, 0.0))
        z = a0 * complex(math.cos(math.radians(g0)), math.sin(math.radians(g0))) + complex(x[1 + j], x[1 + n + j])
        neu[c] = (abs(z), math.degrees(math.atan2(z.imag, z.real)) % 360.0)
    return z0 + float(x[0]), neu


def scheitelguete(z0, con, t, h, versatz=False):
    """-> (RMS cm, Median-Zeitfehler HW min, NW min) des Satzes an den Scheiteln (+ = Satz spaeter)."""
    hm, h1, h2 = S.hoehe_und_ableitungen(t, z0, con, KOPF)
    if versatz:
        hm = hm + float(np.mean(h - hm))
    rms = float(np.sqrt(np.mean((hm - h) ** 2))) * 100
    dtm = np.clip(np.where(h2 != 0, -h1 / np.where(h2 != 0, h2, 1), 0) * 60, -180, 180)
    hw = np.convolve(h, [0.5, 0, 0.5], mode='same') < h
    return rms, float(np.median(dtm[hw])), float(np.median(dtm[~hw]))


def wert(g):
    return g[0] + 0.5 * (abs(g[1]) + abs(g[2]))


def bauen(std, k):
    t, h = kunstscheitel(std, k)
    z1, c1 = uebertragen(std, k)
    z2, c2 = nachfuehren(z1, c1, t, h)
    g1, g2 = scheitelguete(z1, c1, t, h), scheitelguete(z2, c2, t, h)
    nach = wert(g2) < wert(g1) - 0.5
    return dict(t=t, h=h, z0=z2 if nach else z1, con=c2 if nach else c1, art='nachgefuehrt' if nach else 'uebertragen',
                g_ueb=g1, g_nach=g2, guete=g2 if nach else g1)


# Vol. II S. 3-5..3-7 "Mares do Canal do Geba": Tabela I (Hoehen PM/BM gegen Caió), Tabela II (Retardos
# nach der Uhrzeit des Scheitels in Caió). Die Uhrzeit ist die von 1969 (UT-1): das Buchbeispiel
# 1.10.1969 PM 00:37 liegt 50-57 min vor dem heutigen Caió-Satz. Porto Gole gedruckt 12 57.6 N (Senegal),
# gemeint 11 57.6 N (ATT Porto Gole 2.3 km). Buch: Abweichungen bis 0.5 m und 50 min moeglich.
GEBA_ORTE = {'Biombo': (11 + 44.0 / 60, -(15 + 57.2 / 60)), 'Bissau': (11 + 51.5 / 60, -(15 + 34.6 / 60)),
             'Jabadá': (11 + 53.5 / 60, -(15 + 20.9 / 60)), 'Porto Gole': (11 + 57.6 / 60, -(15 + 7.8 / 60))}
GEBA_H_CAIO_PM = [2.3 + 0.1 * i for i in range(12)]
GEBA_H_PM = {'Biombo': [3.1, 3.2, 3.3, 3.5, 3.6, 3.7, 3.8, 4.0, 4.1, 4.2, 4.3, 4.5],
             'Bissau': [3.8, 4.0, 4.2, 4.3, 4.5, 4.7, 4.9, 5.0, 5.2, 5.4, 5.6, 5.7],
             'Jabadá': [4.9, 5.0, 5.1, 5.3, 5.4, 5.5, 5.7, 5.8, 5.9, 6.1, 6.2, 6.3],
             'Porto Gole': [5.3, 5.5, 5.8, 5.8, 6.0, 6.1, 6.3, 6.5, 6.6, 6.8, 7.0, 7.1]}
GEBA_H_CAIO_BM = [0.3 + 0.1 * i for i in range(12)]
GEBA_H_BM = {'Biombo': [0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3],
             'Bissau': [0.1, 0.2, 0.3, 0.4, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.4],
             'Jabadá': [0.4, 0.8, 0.7, 0.8, 0.9, 1.0, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7],
             'Porto Gole': [0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 1.0, 1.1, 1.2, 1.3, 1.4, 1.5]}
GEBA_R_PM = {'Biombo': [25, 18, 12, 6, 3, 9, 18, 28, 34, 37, 35, 32],
             'Bissau': [68, 64, 58, 56, 55, 65, 70, 75, 77, 79, 78, 75],
             'Jabadá': [117, 112, 108, 105, 103, 102, 104, 110, 117, 120, 121, 120],
             'Porto Gole': [150, 144, 134, 122, 115, 115, 120, 133, 142, 148, 150, 150]}
GEBA_R_BM = {'Biombo': [31, 41, 50, 53, 56, 55, 53, 45, 35, 26, 24, 23],
             'Bissau': [101, 111, 121, 127, 125, 123, 117, 99, 92, 84, 83, 88],
             'Jabadá': [149, 161, 171, 177, 179, 179, 177, 170, 160, 149, 134, 139],
             'Porto Gole': [184, 198, 213, 226, 231, 233, 232, 225, 215, 201, 192, 188]}
GEBA_UHR_H = -1.0


def geba_konkordanzen():
    out = []
    for n, (la, lo) in GEBA_ORTE.items():
        ap, bp = np.polyfit(GEBA_H_CAIO_PM, GEBA_H_PM[n], 1)
        ab, bb = np.polyfit(GEBA_H_CAIO_BM, GEBA_H_BM[n], 1)
        k = dict(typ='SEC', bezug='CAIÓ', name=n, lat=la, lon=lo, nm=None, pdf=IH.PDF_II, geba=True,
                 hoehe=((ap, bp), (ab, bb)), r=[None, None], h=[0.0] * 4,
                 t=[float(np.mean(GEBA_R_PM[n]))] * 2 + [float(np.mean(GEBA_R_BM[n]))] * 2)
        out.append(k)
    return out


# Vol. II S. 3-8..3-10 Rio Zaire: r, Retardos und Mittelwasser haengen vom Flusspegel an der Pedra do
# Feitiço ab. Nur Lucala ist davon wenig abhaengig (r 0.85-0.95); Medianwerte ueber Pegel 1.0-3.0 m.
# Ponta Quiombe (r 0.28-0.65), Camões, Pedra do Feitiço, Boma (r <= 0.47) bleiben weg.
ZAIRE = [dict(typ='SEC', bezug='SOYO', name='Lucala (Rio Zaire)', lat=-(6 + 2.1 / 60), lon=12 + 41.6 / 60,
              nm=1.35, t=[20.0, 35.0, 20.0, 20.0], h=[None] * 4, r=[0.93, 0.93], pdf=IH.PDF_II, zaire=True)]


def alle_konkordanzen():
    return [k for k in konkordanzen_I() if k['typ'] == 'SEC'] + konkordanzen_II() + geba_konkordanzen() + ZAIRE


def verwendbar(k):
    if k['name'] in AUSLASSEN_II and k['pdf'] == IH.PDF_II and not k.get('geba'):
        return AUSLASSEN_II[k['name']]
    if any(x is None for x in k['t']):
        return 'Zeitkorrektur fehlt'
    if k['h'][0] is None and k['r'][0] is None:
        return ('nur Zeitkorrektur, Amplitude unbekannt (r=1 angenommen trifft Bolama auf 4-8 min, '
                'aber 18 % zu kleiner Hub)')
    if k['h'][0] is not None and any(x is None for x in k['h']):
        return 'Hoehenkorrektur unvollstaendig'
    return None


# Konkordanzen, die unabhaengige Daten widerlegen (Probe 14.09.2026)
WIDERLEGT = {
    'PORTO GRANDE': 'Kap Verde: an beiden pruefbaren Orten 25-35 min falsch (Palmeira: TICON und UHSLC 235 treffen '
                    'die IH-Tafel Palmeira auf +2..+10 min, die Konkordanz +51 min liegt 25-35 min daneben; Praia: '
                    'Konkordanz -17 min, IH-Tafel Praia -38 min); fuer die uebrigen 8 Orte gibt es keine Messung',
    ('SOYO', 'Cabinda'): 'ATT-Standardhafen Cabinda (NP208) 38-40 min frueher; +32 min gegen Soyo (Kongomuendung) '
                         'waere Luanda +56 min an offener Kueste, Luanda-Lobito sind 11 min',
    **{('CAIÓ', n): 'Canal-do-Geba-Tabellen (1969, laut IH bis 0.5 m/50 min ungenau): Zeit und Springhub stimmen '
                    'mit den harmonischen Saetzen (ATT/1997 Bissau, ATT Biombo/Jabadá/Porto Gole) ueberein, der '
                    'Nipphub nicht (S2/M2 0.19 statt 0.27, Rundung der Hoehentabelle) -- keine Verbesserung'
       for n in GEBA_ORTE},
    ('LAGOS', 'Albufeira'): 'Messung Albufeira (IOC) 26-29 min frueher; sie liegt gleichauf mit den Messungen Lagos '
                            'und Sagres (0-2 min)',
}
GRUND_MAX_CM = 8.0
GRUND_NACHFUEHREN_CM = 6.0   # schwaecherer Grundsatz wird erst an die eigene Standardtafel nachgefuehrt
SCHEITEL_MAX_MIN = 10.0
SCHEITEL_MAX_CM = 8.0
GLEICH_MIN = 7.0        # Bestandssatz gilt als gleichwertig bis zu diesem Scheitelfehler

ANZEIGE = {
    ('AVEIRO', 'S. Jacinto'): 'São Jacinto (Ria de Aveiro)', ('AVEIRO', 'Cais Comercial'): 'Cais Comercial (Aveiro)',
    ('AVEIRO', 'Miradouro'): 'Miradouro (Ria de Aveiro)', ('AVEIRO', 'Lota'): 'Lota (Aveiro)',
    ('AVEIRO', 'Terminal de Líquidos'): 'Terminal de Líquidos (Aveiro)', ('AVEIRO', 'Ponte Cais n.º 2'): 'Ponte Cais n.º 2 (Aveiro)',
    ('AVEIRO', 'Boco'): 'Boco (Canal de Ílhavo)', ('AVEIRO', 'Costa Nova'): 'Costa Nova (Canal de Mira)',
    ('AVEIRO', 'Vagueira'): 'Vagueira (Canal de Mira)', ('AVEIRO', 'Parrachil'): 'Parrachil (Rio Vouga)',
    ('AVEIRO', 'Rio Novo'): 'Rio Novo (Rio Vouga)', ('AVEIRO', 'Cacia'): 'Cacia (Rio Vouga)',
    ('SETÚBAL (TROIA)', 'Cais Comercial'): 'Cais Comercial (Setúbal)', ('SETÚBAL (TROIA)', 'Baliza 4'): 'Baliza 4 (Rio Sado)',
    ('SETÚBAL (TROIA)', 'Desmagnetização'): 'Desmagnetização (Setúbal)', ('SETÚBAL (TROIA)', 'Outão'): 'Outão (Setúbal)',
    ('LISBOA', 'Carregado – terra'): 'Carregado (Rio Tejo)', ('LISBOA', 'VALORSUL'): 'Valorsul (Bobadela)',
    ('LISBOA', 'CIMPOR'): 'CIMPOR (Alhandra)', ('LISBOA', 'Cais da Matinha'): 'Cais da Matinha (Lisboa)',
    ('LISBOA', 'Cabo Ruivo'): 'Cabo Ruivo (Lisboa)', ('LISBOA', 'Ponta da Erva'): 'Ponta da Erva (Rio Tejo)',
    ('LEIXÕES', 'Capitania do Douro'): 'Capitania do Douro (Porto)', ('LEIXÕES', 'Crestuma'): 'Crestuma (Rio Douro)',
    ('INHAMBANE', 'Bóia de espera'): 'Bóia de espera (Inhambane)', ('INHAMBANE', 'Farol da Barra'): 'Farol da Barra (Inhambane)',
    ('INHAMBANE', 'Pedestal'): 'Pedestal (Inhambane)', ('BEIRA', 'Pilotos da Beira'): 'Pilotos da Beira',
    ('BEIRA', 'Sofala'): 'Sofala', ('ANGOCHE', 'Moma'): 'Moma (Rio Liganha)', ('CACHEU', 'Foz do Rio Cacheu'): 'Foz do Rio Cacheu',
    ('CAIÓ', 'Bóia de aterragem'): 'Bóia de aterragem (Caió)', ('CAIÓ', 'Jabadá'): 'Jabadá (Rio Geba)',
    ('CAIÓ', 'Porto Gole'): 'Porto Gole (Rio Geba)', ('CAIÓ', 'Biombo'): 'Biombo',
    ('MORRUBUNE', 'Bóia de espera'): 'Bóia de espera (Barra de Quelimane)', ('MORRUBUNE', 'Barra'): 'Barra de Quelimane',
    ('MORRUBUNE', 'Salinas'): 'Salinas (Rio dos Bons Sinais)', ('MORRUBUNE', 'Ponta Olinda'): 'Ponta Olinda (Quelimane)', ('ILHA DE MOÇAMBIQUE', 'Mocambo'): 'Mocambo',
}
MADEIRA = ('FUNCHAL',)
ACORES = ('ANGRA DO HEROÍSMO', 'HORTA', 'LAJES DAS FLORES')
LAND_MZ = ('MAPUTO', 'INHAMBANE', 'BEIRA', 'CHINDE', 'MORRUBUNE', 'PEBANE', 'ANGOCHE', 'ILHA DE MOÇAMBIQUE',
           'PEMBA', 'MOCÍMBOA DA PRAIA')


def satzname(k):
    n = ANZEIGE.get((k['bezug'], k['name']), k['name'])
    if k['pdf'] == IH.PDF:
        if k['bezug'] in MADEIRA:
            return f'{n}, Madeira, Portugal', 'Europe/Lisbon', 'Portugal'
        if k['bezug'] in ACORES:
            return f'{n}, Açores, Portugal', 'Atlantic/Azores', 'Portugal'
        return f'{n}, Portugal', 'Europe/Lisbon', 'Portugal'
    land = 'Mozambique' if k['bezug'] in LAND_MZ else LAND_II[k['bezug']]
    return f'{n}, {land}', TZ_LAND[land], land


def _worte(s):
    stopp = {'DE', 'DO', 'DA', 'DOS', 'DAS', 'RIO', 'PORTO', 'CAIS', 'BARRA', 'ILHA', 'BAIA', 'PONTA', 'CANAL', 'S', 'SAO'}
    return {w for w in re.findall(r'[A-Z]{3,}', _norm_leer(s)) if w not in stopp}


def _norm_leer(s):
    import unicodedata
    return unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode().upper()


# Namensvettern, die trotz Abstand > 3 km verglichen werden (Oliver 15.09.2026)
NAMENSVETTERN = {('LISBOA', 'Montijo'): ('Montijo, Portugal',),
                 ('MOCÍMBOA DA PRAIA', 'Palma'): ('Palma (Baía de Tungue), Mozambique',)}


def gleicher_ort(k, r, d, punkte=()):
    """Bestandssatz r gehoert zum Konkordanzort k: nah (Name oder <= 1 km) und kein anderer Ort naeher."""
    if r['name'] in NAMENSVETTERN.get((k['bezug'], k['name']), ()) and d <= 15.0:
        return True
    if d > 3.0:
        return False
    if any(km(r, q) < d - 0.05 for q in punkte if q is not k):
        return False
    if d <= 1.0:
        return True
    if d > 3.0:
        return False
    a, b = _worte(k['name']), _worte(r['name'].split(',')[0])
    return any(x == y or (len(x) >= 5 and (x.startswith(y) or y.startswith(x))) for x in a for y in b)


def probe(recs):
    """Praia ist Standardhafen UND Konkordanz zu Porto Grande (-17 min, r 1.28)."""
    pg = Standard('Porto Grande (Ilha de S. Vicente)', IH.PDF_II, recs)
    pr = Standard('Praia (Ilha de Santiago)', IH.PDF_II, recs)
    k = [x for x in konkordanzen_II() if x['name'] == 'Praia (Santiago)'][0]
    print('Porto Grande Grundsatz:', pg.grund['name'], f"{pg.grund['rms']:.1f} cm HW {pg.grund['hw']:+.0f} NW {pg.grund['nw']:+.0f}")
    b = bauen(pg, k)
    t = np.array([x[0] for x in pr.scheitel]); h = np.array([x[1] for x in pr.scheitel])
    rms, hw, nw = scheitelguete(b['z0'], b['con'], t, h)
    wahr = [x for x in pr.kandidaten if x['name'] == 'IH-Konstanten'][0]
    m = P.messen(b['con'], wahr['con'])
    print(f"  {b['art']:13} gegen Praia-Tafel: {rms:.1f} cm HW {hw:+.0f} NW {nw:+.0f} | gegen IH-Konstanten Praia: "
          f"Kurve {m['kurve_pct']:.1f} %  HW {m['hw_min']:+.0f} NW {m['nw_min']:+.0f}")
    for x in sorted(pr.kandidaten, key=lambda x: x['wert']):
        print(f"  Bestand {x['name'][:60]:60} {x['rms']:.1f} cm HW {x['hw']:+.0f} NW {x['nw']:+.0f}")


FES_MAX_MIN = 12.0
# FES gegen die IH-Tafeln benachbarter Standardhaefen (14.09.2026): Luanda-Lobito +3, Lobito-Namibe -5,
# Angoche-Ilha +5, Ilha-Nacala +4, Nacala-Pemba +2 min. Sonst 16-30 min (Kap Verde, Sao Tome,
# Mocimboa, Pebane) oder unbrauchbar (Maputo bis Quelimane, Guinea-Bissau).
FES_GEPRUEFT = ('LUANDA', 'LOBITO', 'NAMIBE', 'ILHA DE MOÇAMBIQUE', 'PEMBA')


def fes_probe(ks):
    """Vol. II: {id(k): (Buchzeit, FES-Zeit, Urteil)} aus dem M2-Phasenunterschied Nebenhafen - Standardhafen."""
    import noaa_offen_nachbarn as O
    std, pts = {}, []
    for k in ks:
        if k['pdf'] != IH.PDF_II or verwendbar(k):
            continue
        h = tafelname(k['bezug'], k['pdf'])
        la, lo = IH.haefen(k['pdf'])[h]
        k['_std'] = std.setdefault(h, dict(lat=la, lon=lo))
        pts.append(k)
    f = O.fes_konstanten(list(std.values()) + pts)
    out = {}
    for k in pts:
        a, b = f.get(id(k), {}), f.get(id(k['_std']), {})
        buch = sum(k['t']) / 4.0
        if 'M2' not in a or 'M2' not in b:
            out[id(k)] = (buch, None, 'FES ohne Wert')
            continue
        d = ((a['M2'][1] - b['M2'][1] + 180) % 360 - 180) / SP['M2'] * 60
        r = a['M2'][0] / b['M2'][0]
        if k['bezug'] not in FES_GEPRUEFT or abs(d) > 90 or not 0.6 <= r <= 1.5:
            out[id(k)] = (buch, d, 'FES hier nicht brauchbar')
        elif abs(buch - d) <= FES_MAX_MIN:
            out[id(k)] = (buch, d, 'bestaetigt')
        else:
            out[id(k)] = (buch, d, f'FES widerspricht ({buch:+.0f} gegen {d:+.0f} min)')
    return out


def main(argv):
    recs = [r for r in load_records() if r['lat'] is not None and 'current' not in r['file'].lower()
            and '/backup/' not in r['file'] and '/bak' not in r['file']]
    namen = [a for a in argv if not a.startswith('--')]
    stds, zeilen, neue = {}, [], []
    alle = alle_konkordanzen()
    fes = fes_probe(alle)
    for k in alle:
        if namen and k['name'] not in namen:
            continue
        e = dict(name=k['name'], bezug=k['bezug'], lat=round(k['lat'], 4), lon=round(k['lon'], 4))
        zeilen.append(e)
        grund = verwendbar(k) or WIDERLEGT.get(k['bezug']) or WIDERLEGT.get((k['bezug'], k['name']))
        if grund:
            e['entscheidung'], e['grund'] = 'nicht', grund
            continue
        hafen = tafelname(k['bezug'], k['pdf'])
        if hafen not in stds:
            pegel = None
            if k['pdf'] == IH.PDF:
                pegel = [x for x in konkordanzen_I() if x['typ'] == 'STD' and x['bezug'] == k['bezug']][0]['h']
            stds[hafen] = Standard(hafen, k['pdf'], recs, pegel=pegel)
            g = stds[hafen].grund
            print(f"{hafen:40} Grundsatz {g['name'][:70]:70} {g['rms']:.1f} cm HW {g['hw']:+.0f} NW {g['nw']:+.0f}", flush=True)
        std = stds[hafen]
        b = bauen(std, k)
        name, tz, land = satzname(k)
        e.update(satzname=name, standard=hafen, grundsatz=std.grund['name'], grund_cm=round(std.grund['rms'], 1),
                 art=b['art'], cm=round(b['guete'][0], 1), hw=round(b['guete'][1]), nw=round(b['guete'][2]))
        # Bestand am selben Ort
        am_ort, besser = [], []
        for r in recs:
            if abs(r['lat'] - k['lat']) > 0.05 or '/ih/' in r['file']:
                continue
            d = km(r, k)
            if not gleicher_ort(k, r, d, alle):
                continue
            try:
                zr, cr = P.satz(r)
                gr = scheitelguete(zr, cr, b['t'], b['h'], versatz=True)
                m = P.messen(b['con'], cr)
            except Exception:
                continue
            x = dict(r=r, km=d, klasse=P.klasse(r) or '-', guete=gr, kurve=m['kurve_pct'],
                     text=f"{os.path.basename(r['file'])}|{r['name']} [{P.klasse(r) or '-'} {d:.1f} km] "
                          f"Tafel {gr[0]:.1f} cm {gr[1]:+.0f}/{gr[2]:+.0f}, Kurve {m['kurve_pct']:.1f} %")
            am_ort.append(x)
            if x['klasse'] == 'A' or (gr[0] <= b['guete'][0] + 2.5 and max(abs(gr[1]), abs(gr[2])) <= GLEICH_MIN):
                besser.append(x)
        e['bestand'] = ' ; '.join(x['text'] for x in am_ort)
        fp = fes.get(id(k))
        k['_fes'] = fp
        if fp:
            e['fes'] = f"Buch {fp[0]:+.0f} / FES {fp[1]:+.0f} min: {fp[2]}" if fp[1] is not None else fp[2]
        stuetze = [x for x in am_ort if abs(x['guete'][1]) <= 8 and abs(x['guete'][2]) <= 8]
        trivial = all(v == 0 for v in k['t']) and (k['h'][0] is None and k['r'] == [1.0, 1.0]
                                                  or k['h'][0] is not None and all(v == 0 for v in k['h']))
        if std.grund['rms'] > GRUND_MAX_CM:
            e['entscheidung'], e['grund'] = 'nicht', f"kein guter Grundsatz am Standardhafen ({std.grund['rms']:.1f} cm)"
        elif b['guete'][0] > SCHEITEL_MAX_CM or max(abs(b['guete'][1]), abs(b['guete'][2])) > SCHEITEL_MAX_MIN:
            e['entscheidung'], e['grund'] = 'nicht', 'Konkordanz harmonisch nicht darstellbar (Scheitel)'
        elif trivial and km(k, dict(lat=std.lat, lon=std.lon)) < 5.0:
            e['entscheidung'], e['grund'] = 'nicht', 'gleich dem Standardhafen'
        elif fp and fp[2].startswith('FES widerspricht'):
            e['entscheidung'] = 'nicht'
            e['grund'] = 'Vol. II: ' + fp[2] + '; FES trifft an dieser Kueste die IH-Standardtafeln auf 2-5 min'
        elif besser:
            e['entscheidung'] = 'nicht'
            e['grund'] = 'Bestand am Ort gleichwertig: ' + besser[0]['text'].split(' [')[0]
        else:
            e['entscheidung'], e['grund'] = 'neu', ''
            e['loeschen'] = ' ; '.join(x['text'] for x in am_ort)
            e['loeschen_n'] = len(am_ort)
            neue.append((k, b, name, tz, land, std, am_ort))
        print(f"   {e['entscheidung']:5} {k['name'][:28]:28} {e.get('art', ''):12} {e.get('cm', '')} cm "
              f"{e.get('hw', '')}/{e.get('nw', '')}  {e['grund'][:90]}", flush=True)
        for x in am_ort:
            print('           ', x['text'])
    print(collections.Counter((z['entscheidung'], z['grund'].split(':')[0][:60]) for z in zeilen).most_common())
    if '--liste' in argv or '--schreiben' in argv:
        felder = list(dict.fromkeys(f for z in zeilen for f in z))
        with open(LISTE, 'w', newline='', encoding='utf-8') as fh:
            w = csv.DictWriter(fh, fieldnames=felder); w.writeheader(); w.writerows(zeilen)
        print('->', os.path.relpath(LISTE, ROOT))
    if '--schreiben' in argv:
        schreiben_datei(neue)


def bestand_der_datei():
    """{erste IH-Konkordanz-Notiz: [(Name, lat, lon)]} aus der vorhandenen Datei.

    Namen und Positionen koennen dort nachtraeglich gesetzt worden sein (etwa Name und Position eines
    geloeschten Vorgaengers) -- ein neuer Lauf darf sie nicht zuruecksetzen.
    """
    out = collections.defaultdict(list)
    if not os.path.exists(IS.AUS):
        return out
    L = open(IS.AUS, encoding='iso-8859-1').read().split('\n')
    notiz = None
    for i, l in enumerate(L):
        if l.startswith('# BEGIN HOT COMMENTS'):
            notiz = None
        elif l.startswith('# note: IH-Konkordanz') and notiz is None:
            notiz = l
        elif l.startswith('# !latitude') and notiz:
            out[notiz].append((L[i + 1], float(l.split()[-1]), float(L[i - 1].split()[-1])))
    return out


def schreiben_datei(neue):
    alt = bestand_der_datei()
    zeilen = IS.standard_zeilen()
    for k, b, name, tz, land, std, am_ort in neue:
        buch = 'Vol. I 2026, S. 3-2/3-3' if k['pdf'] == IH.PDF else 'Vol. II 2026, S. 3-3/3-4'
        if k.get('geba'):
            regel = (f"Tabelas I/II Canal do Geba gegen Caió, Verspaetung PM {min(GEBA_R_PM[k['name']])}-"
                     f"{max(GEBA_R_PM[k['name']])}, BM {min(GEBA_R_BM[k['name']])}-{max(GEBA_R_BM[k['name']])} min "
                     f"nach Uhrzeit in Caió; laut IH Abweichungen bis 0.5 m und 50 min moeglich")
        elif k.get('zaire'):
            regel = "Quadro Lucala: PM +20/+35, BM +20 min, r 0.93, Mittelwasser 1.35 m"
        elif k['h'][0] is not None:
            regel = (f"Zeit PM {k['t'][0]:+.0f}/{k['t'][1]:+.0f}, BM {k['t'][2]:+.0f}/{k['t'][3]:+.0f} min (Nipp/Spring), "
                     f"Hoehe PM {k['h'][0]:+.2f}/{k['h'][1]:+.2f}, BM {k['h'][2]:+.2f}/{k['h'][3]:+.2f} m")
        else:
            regel = (f"Zeit PM {k['t'][0]:+.0f}/{k['t'][1]:+.0f}, BM {k['t'][2]:+.0f}/{k['t'][3]:+.0f} min, "
                     f"Amplitudenrelation {k['r'][0]:.2f}/{k['r'][1]:.2f}")
        noten = [f"IH-Konkordanz ({buch}) zum Standardhafen {std.hafen}: {regel}.",
                 f"Grundsatz {std.grund['name'].replace('|', ': ')} (gegen die IH-Tafel {std.grund['rms']:.1f} cm).",
                 f"Uebertragen mit Hubfaktoren und mittlerer Zeitkorrektur"
                 + ("; Seichtwasser gegen die umgerechneten Tafelscheitel nachgefuehrt." if b['art'] == 'nachgefuehrt' else '.'),
                 f"Gegen die umgerechnete IH-Tafel 2026 ({len(b['t'])} Scheitel): {b['guete'][0]:.1f} cm, "
                 f"HW {b['guete'][1]:+.0f} / NW {b['guete'][2]:+.0f} min."]
        if k['pdf'] == IH.PDF and k['name'] in KOORD_I:
            noten.append('Position berichtigt: gedruckt 17 19.9 W (15 km im Meer), wie FCUL/ATT 17 09.9 W.')
        if k.get('zaire'):
            noten.append('Werte als Median ueber Flusspegel Pedra do Feitiço 1.0-3.0 m; tatsaechlich vom Flusspegel abhaengig.')
        if k.get('geba') and k['name'] == 'Porto Gole':
            noten.append('Position berichtigt: gedruckt 12 57.6 N (Senegal), gemeint 11 57.6 N.')
        if k['pdf'] == IH.PDF_II and k['name'] in KOORD_II:
            noten.append({'Santa Maria': 'Position berichtigt: gedruckt 13 32.6 E (110 km im Landesinneren), '
                                         'Cabo de Santa Maria liegt auf 12 32 E.',
                          'Água Izé': 'Position berichtigt: gedruckt 6 44.0 W, Sao Tome liegt oestlich (6 44.0 E).',
                          'Santa Marta': 'Position auf den Ort am Kap gelegt (wie ATT/NOAA); gedruckt 13 52.4 S 12 29.1 E an Land.',
                          'Baía dos Tigres': 'Position auf den Ort auf der Insel gelegt (wie ATT/NOAA); gedruckt 16 36.1 S 11 49.3 E.',
                          'Ibo': 'Position auf den Ort gelegt (wie ATT/1997/NOAA); gedruckt 12 11.8 S 40 33.6 E (16 km noerdlich, an Land).',
                          'Moma': 'Position auf den Ort gelegt (wie ATT); gedruckt 16 47.4 S 39 16.0 E.',
                          'Sofala': 'Position wie ATT gelegt; gedruckt 20 08.4 S 34 46.9 E.',
                          'Bazaruto': 'Position wie ATT/NOAA gelegt; gedruckt 21 31.8 S 35 29.9 E (Nordspitze).'}[k['name']])
        fp = k.get('_fes')
        if fp and fp[2] == 'bestaetigt':
            noten.append(f"Zeitkorrektur von FES2022 bestaetigt (Buch {fp[0]:+.0f}, FES {fp[1]:+.0f} min).")
        elif k['pdf'] == IH.PDF_II:
            noten.append('Zeitkorrektur nicht unabhaengig geprueft: Vol.-II-Konkordanzen lagen andernorts 20-40 min daneben.')
        la, lo = k['lat'], k['lon']
        kand = [v for v in alt.get(f'# note: {noten[0]}', []) if km(dict(lat=la, lon=lo), dict(lat=v[1], lon=v[2])) <= 3.0]
        vorher = min(kand, key=lambda v: km(dict(lat=la, lon=lo), dict(lat=v[1], lon=v[2]))) if kand else None
        if vorher and (vorher[0] != name or km(dict(lat=la, lon=lo), dict(lat=vorher[1], lon=vorher[2])) > 0.01):
            print(f'   behalte aus der Datei: {vorher[0]} {vorher[1]:.4f} {vorher[2]:.4f} (Lauf: {name})')
            name, la, lo = vorher
        lang = [n for n in noten if len(n) > 180]
        if lang:
            raise SystemExit(f'Notiz zu lang fuer build_tide_db ({name}): {lang[0][:60]}...')
        zeilen += IS.block(name, land, tz, la, lo, b['z0'], b['con'], noten,
                           quelle='Instituto Hidrografico (PT), Tabela de Mares 2026, Concordancias de mares')
    from sicher_schreiben import schreiben
    schreiben(IS.AUS, '\n'.join(zeilen) + '\n')
    print('->', os.path.relpath(IS.AUS, ROOT), len(neue) + len(IS.STANDARD), 'Saetze')


if __name__ == '__main__':
    main(sys.argv[1:])
