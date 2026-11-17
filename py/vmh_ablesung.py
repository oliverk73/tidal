#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Alle gedruckten Atlas-Raten eines visitMyHarbour-Atlas zu Stromsaetzen (Oliver 17.11.2026: "jeden Satz eintragen,
den es gibt -- Stroemung aendert sich kleinraeumig").

Eingabe: quellen/tidal_streams/visitmyharbour/ablesung/<atlas>.txt, je Zeile "stunde x y nipp,spring" (Pixel im
Stundenbild, von Hand abgelesen mit Gitter). Ablauf:
  1. Ablesungen gleicher Lage (< 28 px) ueber die 13 Stunden zu Punkten zusammenfassen (je Stunde die naechste).
  2. Nur Punkte mit >= 10 Stunden; fehlende Stunden aus den Nachbarstunden.
  3. Richtung: Achse aus FES2014 (M2-Ellipse); Vorzeichen wechselt nur an den Kenterminima der Atlasreihe,
     welche Haelfte Flut ist, entscheidet die Korrelation mit FES2014 (HW Bezugshafen -> Modellstrom).
  4. Lage gegen OSM-Landmaske, Abstand zu vorhandenen Saetzen; Satz wie vmh_atlas (Nipp/Spring nach Hub).

  venv/bin/python py/vmh_ablesung.py thames [--schreiben]
"""
import cmath
import csv
import math
import os
import re
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fes2014_strom as F                                            # noqa: E402
import hafenatlas_stroeme as A                                       # noqa: E402
import health_check as H                                             # noqa: E402
import osm_land as OL                                                # noqa: E402
import vmh_atlas as V                                                # noqa: E402
import xtide_modell as X                                             # noqa: E402

ROOT = V.ROOT
ABL = os.path.join(ROOT, 'quellen/tidal_streams/visitmyharbour/ablesung')
RICHTUNG = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE', 'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW']


def _interp(ticks, v):
    t = sorted(ticks)
    return float(np.interp(v, [a for a, _ in t], [b for _, b in t]))


ATLAS = {
    # Seite aufrecht (thames_estuary_XX.png 1024x1030); Gradnetz am Rand abgelesen, an Margate/Herne Bay geprueft
    'thames': dict(bezug=V.SHEERNESS, atlas='NP249 (Thames Estuary)', land='England, United Kingdom',
                   lat=lambda y: _interp([(180, 52.0), (390, 51 + 50 / 60), (587, 51 + 40 / 60), (787, 51.5), (983, 51 + 20 / 60)], y),
                   lon=lambda x: 1 + (x - 357) / 729.0),
}


def lesen(name):
    out = []
    for z in open(os.path.join(ABL, name + '.txt'), encoding='utf-8'):
        z = z.split('#')[0].split()
        if len(z) == 4:
            n, s = z[3].split(',')
            out.append((int(z[0]), float(z[1]), float(z[2]), int(n) / 10, int(s) / 10))
    return out


def punkte(abl, r=28.0, min_h=10):
    """Zusammenfassen: Startpunkte aus der Stunde mit den meisten Ablesungen, dann iterativ Mittelpunkt."""
    rest = list(abl)
    cl = []
    while rest:
        # Saat: Ablesung mit den meisten Nachbarn
        saat = max(rest, key=lambda a: sum(1 for b in rest if math.hypot(a[1] - b[1], a[2] - b[2]) < r))
        cx, cy = saat[1], saat[2]
        for _ in range(3):
            je = {}
            for b in rest:
                d = math.hypot(b[1] - cx, b[2] - cy)
                if d < r and (b[0] not in je or d < je[b[0]][0]):
                    je[b[0]] = (d, b)
            cx = float(np.mean([b[1] for _, b in je.values()]))
            cy = float(np.mean([b[2] for _, b in je.values()]))
        for _, b in je.values():
            rest.remove(b)
        cl.append((cx, cy, {h: (b[3], b[4]) for h, (_, b) in je.items()}))
    return [c for c in cl if len(c[2]) >= min_h], [c for c in cl if len(c[2]) < min_h]


def vorzeichen(werte, p_model):
    """werte {h: spring}; p_model {h: Modell entlang Achse}. Vorzeichen wechselt an den zwei tiefsten Minima."""
    hs = list(range(-6, 7))
    s = np.array([werte.get(h, np.nan) for h in hs], float)
    ok = ~np.isnan(s)
    s = np.interp(np.arange(13), np.arange(13)[ok], s[ok])
    # Minima: tiefste Stelle, dann tiefste Stelle >= 4 h entfernt
    m1 = int(np.argmin(s))
    kand = [i for i in range(13) if min(abs(i - m1), 12.42 - abs(i - m1)) >= 4]   # -6 und +6 sind dieselbe Tidenphase
    m2 = min(kand, key=lambda i: s[i])
    a, b = sorted((m1, m2))
    seg = np.array([1 if a < i <= b else -1 for i in range(13)], float)
    # Werte genau am Minimum: Vorzeichen egal (klein)
    pm = np.array([p_model[h] for h in hs])
    vz = 1.0 if np.sum(seg * s * pm) >= 0 else -1.0
    return {h: vz * seg[i] for i, h in enumerate(hs)}, s


def main(argv):
    name = argv[0]
    cfg = ATLAS[name]
    abl = lesen(name)
    gut, schlecht = punkte(abl)
    print('%d Ablesungen -> %d Punkte (>= 10 h), %d verworfen' % (len(abl), len(gut), len(schlecht)))
    P = [(cfg['lat'](cy), cfg['lon'](cx), cx, cy, w) for cx, cy, w in gut]
    # Modell
    zl = F.zellen([(p[0], p[1]) for p in P])
    st = F.stroeme(zl, ks=['M2'])
    hafen, rel = cfg['bezug']
    kopf = X.kopf_lesen(os.path.join(ROOT, rel))
    _z, wb, _e, mer = X.satz_lesen(os.path.join(ROOT, rel), hafen)
    gS = X.greenwich(wb['M2'][1], kopf[1]['M2'], mer)
    om = kopf[1]['M2']
    R = [r for r in H.load_records() if r['current'] and r['lat'] is not None]
    LM = OL.Land([(p[0], p[1]) for p in P])
    Lgeo = __import__('json').load(open(os.path.join(ROOT, 'quellen/tidal_streams/strom_landmarken_geonames.json'), encoding='utf-8'))
    zeilen, bl = [], []
    namen = {r['name'] for r in H.load_records()}
    for idx, (la, lo, cx, cy, w) in enumerate(P):
        uv = st['M2'][idx]
        if uv is None:
            print('  kein Modell', la, lo)
            continue
        U, Vv = uv
        # Hauptachse der M2-Ellipse
        best = max(range(0, 180, 2), key=lambda t: abs(F.proj((U, Vv), t)))
        pm = {h: (cmath.exp(1j * math.radians(gS + om * h)) * (U * math.sin(math.radians(best)) + Vv * math.cos(math.radians(best)))).real
              for h in range(-6, 7)}
        sg, sfill = vorzeichen({h: v[1] for h, v in w.items()}, pm)
        werte = {}
        for i, h in enumerate(range(-6, 7)):
            if h in w:
                n, s = w[h]
            else:                                                   # Luecke: Nachbarn, Nipp im Verhaeltnis
                s = sfill[i]
                q = [w[k][0] / w[k][1] for k in w if w[k][1] > 0]
                n = s * (np.median(q) if q else 0.6)
            werte[h] = (n, s, best if sg[h] > 0 else (best + 180) % 360)
        an_land = LM.ist_land(la, lo)
        kue = LM.kueste_km(la, lo)
        nah = min(((H.km(r, {'lat': la, 'lon': lo}), r['name']) for r in R), default=(99, ''))
        # Name: naechste Landmarke (GeoNames, Banken/Rinnen/Kaps/Orte) + Abstand/Richtung
        lm = min(((V.A.km(la, lo, a, b), n_, c) for n_, a, b, c, _t in Lgeo if abs(a - la) < 0.3 and abs(b - lo) < 0.5), default=None)
        if lm:
            d, ln, _c = lm
            a_, b_ = next((a, b) for n_, a, b, c, _t in Lgeo if n_ == ln and abs(V.A.km(la, lo, a, b) - d) < 1e-6)
            az = math.degrees(math.atan2((lo - b_) * math.cos(math.radians(la)), la - a_)) % 360
            nm = ln if d < 1 else '%s (%d km %s)' % (ln, max(1, round(d)), RICHTUNG[int((az + 11.25) % 360 // 22.5)])
        else:
            nm = 'Thames Estuary %.3f %.3f' % (la, lo)
        nm = '%s, %s Current' % (V.A.re.sub(r'[^\x00-\xff]', '', nm) if hasattr(V.A, 're') else nm, cfg['land'])
        k = 2
        basis = nm
        while nm in namen:
            nm = basis.replace(' Current', ' (%d) Current' % k)
            k += 1
        namen.add(nm)
        z = dict(name=nm, lat=round(la, 4), lon=round(lo, 4), x=round(cx), y=round(cy), stunden=len(w), achse=best,
                 spring_max=max(v[1] for v in werte.values()), land=int(an_land), kueste_km=round(kue, 2),
                 naechster_km=round(nah[0], 1), naechster=nah[1])
        zeilen.append(z)
        if an_land or nah[0] < 1.0:
            continue
        r, hs, hn = V.satz(werte, la, cfg['bezug'])
        bl.append((nm, r, la, lo, hs, hn))
    aus = os.path.join(ROOT, 'harmonics/help/vmh_%s_punkte.csv' % name)
    with open(aus, 'w', newline='', encoding='utf-8') as fh:
        wr = csv.DictWriter(fh, fieldnames=list(zeilen[0]))
        wr.writeheader()
        wr.writerows(zeilen)
    print('->', os.path.relpath(aus, ROOT), '|', len(bl), 'schreibbar')
    for z in zeilen:
        print('%-62s %3d h  %5.1f kn  %s%s  naechster %.1f km %s' % (z['name'][:62], z['stunden'], z['spring_max'],
              'LAND ' if z['land'] else '', 'kueste %.1f' % z['kueste_km'], z['naechster_km'], z['naechster'][:40]))
    return bl, cfg


if __name__ == '__main__':
    bl, cfg = main(sys.argv[1:])
    if '--schreiben' in sys.argv and bl:
        import datetime as dt
        from sicher_schreiben import schreiben
        hafen = cfg['bezug'][0].split(',')[0]
        T = open(A.ZIEL, encoding='iso-8859-1').read().rstrip('\n')
        neu = [A.block(nm, r, la, lo,
                       'Admiralty %s tidal stream atlas via visitmyharbour.com (members, hourly HW %s -6..+6, every printed rate, read by hand)' % (cfg['atlas'], hafen),
                       'hours from HW %s, neap/spring interpolated by range (spring %.2f m, neap %.2f m); direction axis FES2014, sign from slack pattern' % (hafen, hs, hn),
                       'UKHO %s via visitMyHarbour' % cfg['atlas'].split()[0], '%s-VISITMYHARBOUR' % cfg['atlas'].split()[0])
               for nm, r, la, lo, hs, hn in bl]
        schreiben(A.ZIEL, T + '\n' + '\n'.join(neu) + '\n')
        with open(os.path.join(ROOT, 'harmonics/help/neu_pruefen_%s.csv' % dt.date.today().strftime('%Y%m%d')), 'a', encoding='utf-8') as fh:
            for nm, *_r in bl:
                fh.write('harmonics_utide_current_tables.txt,"%s"\n' % nm)
        print(len(neu), 'Saetze ->', os.path.relpath(A.ZIEL, ROOT))
