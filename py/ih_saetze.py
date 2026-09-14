#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Saetze aus den Gezeitentafeln des Instituto Hidrográfico (Portugal).

Quellen (tide_tables/Portugal/):
  TabelaMare_I_2026_signed.pdf        Vol. I  Portugal, Madeira, Azoren
  TabMares_I_2025_completa_signed-1.pdf  Vol. I 2025
  TabelaMare_II_2026_signed.pdf       Vol. II Kap Verde, Guinea-Bissau, Sao Tome,
                                      Angola, Mocambique
Gelesen mit py/ih_portugal_tafel.py.

Standardhafen aus IH-Konstanten: M2, S2, K1, O1 wie gedruckt (Phasenbezug je
Hafen: UT, bei Porto Grande und den Azoren Ortszone UT-1), N2/K2/P1/Q1 nach
der ueblichen Admiralty-Naeherung abgeleitet. Geprueft gegen die IH-Hoch- und
Niedrigwassertafel desselben Hafens.

Schreibt harmonics/ih/harmonics_ih_tabelas.txt (ISO-8859-1).
Usage: python3 py/ih_saetze.py [--schreiben]
"""
from __future__ import annotations

import datetime as dt
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ih_portugal_tafel as IH                                     # noqa: E402
import scheitelfit as S                                            # noqa: E402
import xtide_modell as X                                           # noqa: E402
from bsh_saetze import dateikopf                                   # noqa: E402
from sicher_schreiben import schreiben                             # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUS = os.path.join(ROOT, 'harmonics/ih/harmonics_ih_tabelas.txt')
KOPF = X.kopf_lesen(S.KOPFQUELLE)
SP = KOPF[1]

# Standardhaefen, fuer die ein Satz aus den IH-Konstanten entsteht:
# (Tafelname, Konstantenschluessel, Zone der Phasen, Satzname, Land, Zeitzone, ML ueber ZH, Band, Hinweis)
STANDARD = [
    ('Praia (Ilha de Santiago)', 'PRAIA', 0.0, 'Praia (Santiago), Cape Verde', 'Cape Verde',
     'Atlantic/Cape_Verde', 0.80, IH.PDF_II,
     'IH-Analyse aus Pegelbeobachtungen 09.10.1984-10.10.1985 (Pegel heute ausser Betrieb).'),
]


def konst(pdf, schluessel):
    for k, v in IH.konstanten(pdf).items():
        if k.split(' .')[0].strip() == schluessel:
            return v
    raise KeyError(schluessel)


def ih_satz(kc, zone):
    """IH-Konstanten (Phasen in Zone) -> Greenwich-Satz mit abgeleiteten N2/K2/P1/Q1."""
    g = {c: (a, (p - SP[c] * zone) % 360.0) for c, (a, p) in kc.items()}
    m2, s2, k1, o1 = g['M2'], g['S2'], g['K1'], g['O1']
    d = (s2[1] - m2[1] + 180) % 360 - 180
    g['N2'] = (0.19 * m2[0], (m2[1] - 0.536 * d) % 360)
    g['K2'] = (0.27 * s2[0], s2[1])
    g['P1'] = (0.33 * k1[0], k1[1])
    g['Q1'] = (0.19 * o1[0], (o1[1] - 0.536 * ((k1[1] - o1[1] + 180) % 360 - 180)) % 360)
    return g


def tafelprobe(hafen, pdf, z0, g):
    s = IH.scheitel(hafen, pdf)
    t = np.array([x[0] for x in s]); h = np.array([x[1] for x in s])
    hm, h1, h2 = S.hoehe_und_ableitungen(t, z0, g, KOPF)
    off = float(np.mean(h - hm)); rms = float(np.sqrt(np.mean((hm + off - h) ** 2)))
    dtm = np.clip(np.where(h2 != 0, -h1 / np.where(h2 != 0, h2, 1), 0) * 60, -120, 120)
    hw = h > np.median(h)
    return rms * 100, float(np.median(dtm[hw])), float(np.median(dtm[~hw])), len(s)


def block(name, land, tz, lat, lon, z0, g, noten):
    heute = dt.date.today().strftime('%Y%m%d')
    z = ['# BEGIN HOT COMMENTS', f'# country: {land}',
         '# source: Instituto Hidrografico (PT), Tabela de Mares 2026, Constantes harmonicas',
         f'# date_imported: {heute}', '# datum: Zero Hidrografico (ZH)', '# confidence: 7']
    z += [f'# note: {n}' for n in noten]
    z += ['# !units: meters', f'# !longitude: {lon:.4f}', f'# !latitude: {lat:.4f}',
          name, f'+00:00 :{tz}', f'{z0:.4f} meters']
    for k in KOPF[0]:
        if k in g and g[k][0] > 0.0001:
            z.append(f'{k:<16}{g[k][0]:.4f}  {g[k][1] % 360.0:.2f}')
        else:
            z.append('x 0 0')
    return z


def main(argv):
    zeilen = list(dateikopf())
    for hafen, key, zone, name, land, tz, ml, pdf, hinweis in STANDARD:
        la, lo = IH.haefen(pdf)[hafen]
        g = ih_satz(konst(pdf, key), zone)
        rms, hw, nw, n = tafelprobe(hafen, pdf, ml, g)
        print(f'{name:40} Tafel {n} Scheitel: {rms:.1f} cm, HW {hw:+.1f}, NW {nw:+.1f} min')
        noten = [hinweis,
                 f'M2/S2/K1/O1 aus der IH-Tabelle der Konstanten (Phasen UT{zone:+.0f}), N2/K2/P1/Q1 abgeleitet.',
                 f'Gegen die IH-Tafel 2026 ({n} Scheitel): Hoehe {rms:.1f} cm, HW {hw:+.1f} / NW {nw:+.1f} min.']
        zeilen += block(name, land, tz, la, lo, ml, g, noten)
    if '--schreiben' in argv:
        schreiben(AUS, '\n'.join(zeilen) + '\n')
        print('->', os.path.relpath(AUS, ROOT))


if __name__ == '__main__':
    main(sys.argv[1:])
