#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Menai Strait: Stromsaetze aus den Bangor-University-Profilen (13.11.2026, Oliver: hochaufloesende Quellen
rund um die Britischen Inseln ausschoepfen).

Quelle: https://cams.bangor.ac.uk/realtime/local_forecasts/tide_tables/currentindex.htm (current0-2.pdf):
"Mean spring tidal conditions in the Menai Straits", Laengsprofil Fort Belan -> Puffin Island je Stunde
HW Liverpool -6 .. +5, Geschwindigkeit in kn (+ = Richtung Puffin). "Flows at neap tides are about half those shown."
Vektor-PDF: die grau gefuellte Flaeche ist Kurve + Nulllinie -> Kurve = Eckpunkt mit groesstem Abstand zur Nulllinie
je 1-pt-Spalte. Achse: Beschriftungen 4 / -4 links. Ort entlang der Strasse: Beschriftungen C, PD, MB, B (die
x-Achse ist NICHT laengentreu, daher nur Punkte an den Marken bzw. am Profilmaximum der Swellies).
Spring/Nipp nach dem Hub von Liverpool interpoliert (Nipp = 0,5 x Spring), wie py/hafenatlas_stroeme.reihe_sn.

Usage: venv/bin/python py/menai_stroeme.py [--schreiben]
"""
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cmems_stroemung_nachholen as C                               # noqa: E402
import hafenatlas_stroeme as HA                                     # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PDF = os.path.join(ROOT, 'currents/Menai/current%d.pdf')
HAFEN = 'Liverpool (Gladstone Dock), England, United Kingdom'
HD = os.path.join(ROOT, 'harmonics/classic/harmonics-dwf-20100529-nonfree_mod.txt')
KONTEXT = 'BANGOR-MENAI-PROFILE'
# Name, lat, lon (Fahrwasser, OSM-Kueste geprueft), x im Profil (pt) oder 'swellies', Achse Richtung Puffin (rw. Grad)
PUNKTE = [
    ('Belan Narrows (Menai Strait)', 53.1250, -4.3350, 128.0, None),
    ('Caernarfon (Menai Strait)', 53.1425, -4.2815, 179.2, None),
    ('Port Dinorwic (Menai Strait)', 53.1865, -4.2145, 236.6, None),
    ('The Swellies (Menai Strait)', 53.2205, -4.1768, 'swellies', 72.0),    # Britannia -> Suspension Bridge
    ('Bangor (Menai Strait)', 53.2400, -4.1225, 432.2, None),
    ('Beaumaris (Menai Strait)', 53.2585, -4.0880, 462.0, None),
]
# Mittellinie Belan -> Puffin fuer die Stromachse
LINIE = [(53.1250, -4.3350), (53.1425, -4.2815), (53.1865, -4.2145), (53.2157, -4.1874), (53.2205, -4.1630),
         (53.2400, -4.1225), (53.2585, -4.0880), (53.3160, -4.0320)]


def peilung(a, b):
    dy = b[0] - a[0]
    dx = (b[1] - a[1]) * math.cos(math.radians((a[0] + b[0]) / 2))
    return math.degrees(math.atan2(dx, dy)) % 360


def achse(la, lo):
    """Richtung der Mittellinie am naechsten Linienpunkt (Mittel der Nachbarsegmente)."""
    i = min(range(len(LINIE)), key=lambda k: (LINIE[k][0] - la) ** 2 + ((LINIE[k][1] - lo) * 0.6) ** 2)
    a, b = LINIE[max(0, i - 1)], LINIE[min(len(LINIE) - 1, i + 1)]
    return peilung(a, b)


def profile():
    """-> {Stunde rel. HW Liverpool: (x-Array pt, kn-Array)}"""
    import fitz
    out = {}
    for n in range(3):
        p = fitz.open(PDF % n)[0]
        W = p.get_text('words')
        for f in (d for d in p.get_drawings() if d.get('fill') is not None):
            r = f['rect']
            pts = [it[1] for it in f['items'] if it[0] == 'l'] + [it[2] for it in f['items'] if it[0] == 'l']
            y0 = f['items'][0][1].y                              # Start auf der Nulllinie am linken Rand
            lab = [w for w in W if w[4].startswith('HW') and r.y0 - 80 < w[3] < r.y0 + 5]
            lab = min(lab, key=lambda w: abs(w[3] - r.y0))[4]
            h = 0 if lab == 'HW' else int(lab[2:])
            yy = {w[4]: (w[1] + w[3]) / 2 for w in W if w[0] < 120 and w[4] in ('4', '-4') and abs((w[1] + w[3]) / 2 - y0) < 60}
            pt_kn = (yy['-4'] - yy['4']) / 8.0
            spalten = {}
            for q in pts:
                k = int(round(q.x))
                if k not in spalten or abs(q.y - y0) > abs(spalten[k] - y0):
                    spalten[k] = q.y
            xs = np.array(sorted(spalten))
            out[h] = (xs, np.array([(y0 - spalten[x]) / pt_kn for x in xs]))
    return out


def main(argv):
    import xtide_modell as X
    P = profile()
    assert sorted(P) == list(range(-6, 6)), sorted(P)
    _z0, w, e, _m = X.satz_lesen(HD, HAFEN)
    f = 0.3048 if e.startswith('f') else 1.0
    hub_s, hub_n = 2 * (w['M2'][0] + w['S2'][0]) * f, 2 * (w['M2'][0] - w['S2'][0]) * f
    # Swellies: Profilmaximum zwischen PD und MB im staerksten Bild
    xs, v = P[-5]
    m = (xs > 300) & (xs < 357)
    x_sw = float(xs[m][np.argmax(np.abs(v[m]))])
    vorhanden = set(open(HA.ZIEL, encoding='iso-8859-1').read().split('\n'))
    bl, namen = [], []
    for name, la, lo, x, az in PUNKTE:
        x = x_sw if x == 'swellies' else x
        az = az or achse(la, lo)
        werte = {h: float(np.interp(x, *P[h])) for h in P}
        werte[6] = werte[-6]
        sp = {h: (s * math.sin(math.radians(az)), s * math.cos(math.radians(az))) for h, s in werte.items()}
        ni = {h: (0.5 * a, 0.5 * b) for h, (a, b) in sp.items()}
        r = C.analyse(HA.reihe_sn(sp, ni, HAFEN, HD, hub_s, hub_n), la, C.KONST)
        voll = '%s, Wales, United Kingdom Current' % name
        print('%-34s x %5.1f  Achse %3.0f  Spring %s' % (name, x, az, ' '.join('%+.1f' % werte[h] for h in range(-6, 6))))
        print('%34s M2 %.2f kn  S2 %.2f  max %.1f kn  R2 %.3f  Achse(Fit) %.0f' % ('', r['m2'], r['s2'], r['smax'], r['r2'], r['achse']))
        if voll in vorhanden:
            print('   schon vorhanden')
            continue
        bl.append(HA.block(voll, r, la, lo,
                           'Bangor University Menai Strait mean spring current profiles (hourly HW Liverpool -6..+5)',
                           'hours from HW Liverpool, profile read at x=%.0f pt, neap = 0.5 x spring (source note), '
                           'interpolated by range (spring %.2f m, neap %.2f m)' % (x, hub_s, hub_n),
                           'Bangor University SOS', KONTEXT).replace('# country: United Kingdom', '# country: United Kingdom\n# note: Bangor: near shore slower, around rocks and in narrows (Suspension Bridge) faster than shown'))
        namen.append(voll)
    if '--schreiben' in argv and bl:
        import csv
        import datetime as dt
        from sicher_schreiben import schreiben
        T = open(HA.ZIEL, encoding='iso-8859-1').read().rstrip('\n')
        schreiben(HA.ZIEL, T + '\n' + '\n'.join(bl) + '\n')
        p = os.path.join(ROOT, 'harmonics/help/neu_pruefen_%s.csv' % dt.date.today().strftime('%Y%m%d'))
        with open(p, 'a', newline='', encoding='utf-8') as fh:
            for n in namen:
                csv.writer(fh).writerow([os.path.basename(HA.ZIEL), n])
        print(len(bl), 'Saetze ->', os.path.relpath(HA.ZIEL, ROOT))


def rohreihe(text, name, la, lo):
    """synthetische Jahresreihe (u, v m/s) fuer die Strom-Ellipse"""
    import xtide_modell as X
    if KONTEXT not in text:
        return None
    P = profile()
    _z0, w, e, _m = X.satz_lesen(HD, HAFEN)
    f = 0.3048 if e.startswith('f') else 1.0
    import re
    x = float(re.search(r'profile read at x=(\d+)', text).group(1))
    kurz = name.split(', Wales')[0]
    az = next((a or achse(la, lo)) for n, _la, _lo, _x, a in PUNKTE if n == kurz)   # Profilachse (+ = Richtung Puffin),
    # nicht der Kopf: flutrichtung_pruefen dreht dort Achse und Phasen um 180 Grad
    werte = {h: float(np.interp(x, *P[h])) for h in P}
    werte[6] = werte[-6]
    sp = {h: (s * math.sin(math.radians(az)), s * math.cos(math.radians(az))) for h, s in werte.items()}
    ni = {h: (0.5 * a, 0.5 * b) for h, (a, b) in sp.items()}
    return HA.reihe_sn(sp, ni, HAFEN, HD, 2 * (w['M2'][0] + w['S2'][0]) * f, 2 * (w['M2'][0] - w['S2'][0]) * f)


if __name__ == '__main__':
    main(sys.argv[1:])
