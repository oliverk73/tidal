#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ergaenzt die zwei Part-IIIa-Stroemungsstationen, die uns fehlten.

Unsere 68 Stroemungsstationen stammen aus ATT NP203 Ausgabe 2002. Der Abgleich
gegen den 2015er Scan (Part IIIa, S.252/253) am 20260801 ergab: 28 der 30
Buchstationen im NP203-Gebiet liegen bei uns, auf 0.25 km genau, und die Werte
stimmen ueberein. Es fehlen 426c und 426d.

(Die uebrigen 40 Stationen der Datei liegen in Fernost -- Singapur, Riau,
Bangka, Philippinen, Sulawesi. Sie sind korrekt etikettiert: die Ausgabe 2002
hiess "Indian Ocean AND SOUTH CHINA SEA" und fuehrte in Part IIIa auf S.340-342
die Nummern 415 bis 551. Die Ausgabe 2015 ist auf den Indischen Ozean
zurueckgeschnitten und endet bei 429a.)

Rechenweg, aus der bestehenden Datei rekonstruiert und an 421a, 421b und 422b
in allen vier Konstituenten exakt nachgerechnet:

  1. Aus den N- und E-Zeilen von M2 die Stromellipse bilden:
         W+ = 0.5*(Ae*e^-ige + i*An*e^-ign)
         W- = 0.5*(Ae*e^+ige + i*An*e^+ign)
     Hauptachsenwinkel theta = 0.5*(arg W+ + arg W-), Peilung = 90-theta.
     Elliptizitaet = (|W+|-|W-|) / (|W+|+|W-|).
  2. ALLE Konstituenten auf diese eine Achse projizieren:
         z = cos(theta)*Ae*e^-ige + sin(theta)*An*e^-ign
         Amplitude = |z|,  Phase = -arg(z)
     Das ergibt die eindimensionale Darstellung, die XTide braucht.
  3. N2 = 0.19*M2, K2 = 0.27*S2 (NP203 fuehrt nur M2/S2/K1/O1).

Aufruf: python3 py/add_np203_part3a_fehlende.py [--write]
"""
from __future__ import annotations
import cmath
import math
import os
import re
import shutil
import sys
from datetime import datetime

TXT = '/home/oliver/weather/harmonics/att/harmonics_att_np203_currents.txt'
HARM = '/home/oliver/weather/harmonics'
r = math.radians

# ATT NP203 Part IIIa S.253 (2015), Zone -0300. Je Konstituente (H, g) fuer die
# E- und die N-Zeile; Z0 ist der Reststrom derselben Zeilen.
NEU = [
    dict(no='426c', name='Khafji N, Saudi Arabia Current', land='Kuwait',
         lat=28 + 31.5 / 60, lon=48 + 44.0 / 60, tz='Asia/Riyadh', zone='-0300',
         z0=(0.05, 0.05),
         con={'M2': ((0.67, 42), (0.19, 164)), 'S2': ((0.25, 98), (0.08, 228)),
              'K1': ((0.29, 11), (0.06, 93)), 'O1': ((0.13, 342), (0.07, 52))}),
    dict(no='426d', name='Khafji NE, Saudi Arabia Current', land='Kuwait',
         lat=28 + 36.1 / 60, lon=48 + 59.9 / 60, tz='Asia/Kuwait', zone='-0300',
         z0=(0.00, -0.01),
         con={'M2': ((0.41, 51), (0.37, 209)), 'S2': ((0.15, 111), (0.14, 266)),
              'K1': ((0.20, 24), (0.18, 188)), 'O1': ((0.10, 3), (0.08, 149))}),
]


def achse(m2):
    """Hauptachsenwinkel (math, rad) und Elliptizitaet aus den M2-Komponenten."""
    (Ae, ge), (An, gn) = m2
    Wp = 0.5 * (Ae * cmath.exp(-1j * r(ge)) + 1j * An * cmath.exp(-1j * r(gn)))
    Wm = 0.5 * (Ae * cmath.exp(1j * r(ge)) + 1j * An * cmath.exp(1j * r(gn)))
    th = 0.5 * (cmath.phase(Wp) + cmath.phase(Wm))
    M = abs(Wp) + abs(Wm)
    return th, (abs(Wp) - abs(Wm)) / M if M else 0.0


def projiziere(komp, th):
    (Ae, ge), (An, gn) = komp
    z = math.cos(th) * Ae * cmath.exp(-1j * r(ge)) + math.sin(th) * An * cmath.exp(-1j * r(gn))
    return abs(z), (-math.degrees(cmath.phase(z))) % 360


def order(L):
    i = next(k for k, l in enumerate(L) if l.startswith('# Constituent speeds'))
    out = []
    for l in L[i:]:
        m = re.match(r'^(\S+)\s+[\d.]+\s*$', l)
        if m:
            out.append(m.group(1))
        elif out and l.startswith('#'):
            break
    return out


def main():
    write = '--write' in sys.argv
    L = open(TXT, encoding='iso-8859-1').read().split('\n')
    ORDER = order(L)
    vorhanden = {l.split(': ')[1].strip() for l in L if l.startswith('# np203_no:')}

    bloecke = []
    for s in NEU:
        if s['no'] in vorhanden:
            print(f'{s["no"]}: steht bereits in der Datei.'); continue
        th, ell = achse(s['con']['M2'])
        peil = (90 - math.degrees(th)) % 360
        con = {}
        for k, komp in s['con'].items():
            A, g = projiziere(komp, th)
            con[k] = (round(A, 4), round(g, 2))
        con['N2'] = (round(0.19 * con['M2'][0], 4),
                     (con['M2'][1] - 0.536 * (con['S2'][1] - con['M2'][1])) % 360)
        con['K2'] = (round(0.27 * con['S2'][0], 4), con['S2'][1])
        # Reststrom auf dieselbe Achse projizieren
        ze, zn = s['z0']
        z0 = math.cos(th) * ze + math.sin(th) * zn
        rot = abs(ell) > 0.25
        kopf = ['# country: ' + s['land'],
                '# source: Admiralty Tide Tables NP203 Vol.3 (2015), Part IIIa Tidal Stream '
                'Harmonic Constants',
                '# station_type: current', f'# np203_no: {s["no"]}',
                f'# np203_zone: {s["zone"]}',
                '# stream_type: ' + ('rotary' if rot else 'reversing'),
                f'# flood_dir: {peil:.0f}', f'# ebb_dir: {(peil + 180) % 360:.0f}',
                f'# ellipticity_m2: {ell:+.3f}']
        if rot:
            kopf.append('# rotary_caveat: strongly rotary (|e|>0.25) - 1D major-axis '
                        'underrepresents speed and shows false slacks')
        kopf += ['# inferred: N2 (0.19*M2), K2 (0.27*S2) - NP203 fuehrt nur M2/S2/K1/O1',
                 f'# note: {datetime.now():%Y%m%d} aus dem 2015er Scan S.253 ergaenzt -- '
                 'fehlte in der Ausgabe 2002.',
                 '# note: Das Buch nennt fuer Part IIIa keine Ortsnamen, nur Nummer und '
                 'Position; der Name ist beschreibend.',
                 '# datum: Z0 residual current (knots)', '# !units: knots',
                 f'# !longitude: {s["lon"]:.6f}', f'# !latitude: {s["lat"]:.6f}']
        body = [s['name'], f'+03:00 :{s["tz"]}', f'{z0:.4f} knots']
        body += [f'{c:<13}{con[c][0]:.4f}  {con[c][1]:.2f}' if c in con else f'{c:<13}x 0 0'
                 for c in ORDER]
        print(f'{s["no"]:6s} {s["name"][:36]:36s} Achse {peil:3.0f}/{(peil+180)%360:3.0f}  '
              f'e={ell:+.3f}  M2 {con["M2"][0]:.3f}@{con["M2"][1]:6.2f}  Z0 {z0:+.3f} kn')
        bloecke.append((s['no'], kopf + body))

    if not write:
        print(f'\n{len(bloecke)} Stationen. (Dry-run. --write zum Schreiben.)')
        return

    shutil.copy(TXT, f'{HARM}/backup/harmonics_att_np203_currents_pre_2015_'
                     f'{datetime.now():%Y%m%d}.txt')
    # hinter 426b einfuegen, also vor dem Block von 426e
    i = next(k for k, l in enumerate(L) if l.strip() == '# np203_no: 426e')
    pos = next(k for k in range(i, 0, -1) if L[k].startswith('# country:'))
    for no, blk in reversed(bloecke):
        L[pos:pos] = blk
    open(TXT, 'w', encoding='iso-8859-1').write('\n'.join(L))
    os.chmod(TXT, 0o600)
    print(f'\n{len(bloecke)} Stationen angelegt. Datei: '
          f'{sum(1 for l in L if l.startswith("# !latitude:"))} Stationen')


if __name__ == '__main__':
    main()
