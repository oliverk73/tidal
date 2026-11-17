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
    # Seite quer (east_solent_XX.png 1536x786); 1 Grad W bei x=645, 19,4 px/Laengenminute; 50 50 N bei y=148, 30,5 px/Breitenminute
    'east_solent': dict(bezug=V.PORTSMOUTH, atlas='NP337 (East Solent)', land='England, United Kingdom',
                        lat=lambda y: 50 + 50 / 60 - (y - 148) / (30.5 * 60),
                        lon=lambda x: -1 - (645 - x) / (19.4 * 60),
                        weglassen=[(520, 247)],        # Einfahrt Portsmouth = vorhandener Satz Portsmouth Harbour Entrance
                        achse={(504, 188): 350}),      # im Hafen Portsmouth: Fahrwasser N-S, FES-Zelle liegt in Spithead
    # Seite aufrecht (dover_strait_pXX.png 1024x1417), jede Seite auf den Rahmen der HW-Seite normiert (69..929 x 129..1160);
    # Gradnetz: Laenge 1 Grad bei x=147 .. 1 50' bei x=856, Breite 51 20' bei y=252 .. 50 50' bei y=927 (linear, auch darunter)
    'dover_strait': dict(bezug=V.DOVER, atlas='NP233 (Dover Strait)', land='England, United Kingdom',
                         lat=lambda y: float(np.polyval(np.polyfit([252, 478, 704, 927], [51 + 20 / 60, 51 + 10 / 60, 51, 50 + 50 / 60], 1), y)),
                         lon=lambda x: float(np.polyval(np.polyfit([147, 287, 429, 571, 714, 856], [1 + i / 6 for i in range(6)], 1), x))),
    # Seite quer (bristol_channel_pXX.png 1536x1004), auf den Rahmen der HW-Seite normiert (95..1257 x 72..777);
    # Gradnetz: 4 30'W x=265, 4W x=530, 3 30'W x=795, 3W x=1062; 51 30'N y=313, 51N y=727. Bezug HW Dover (Atlas: 5 h nach HW Swansea)
    'bristol_channel': dict(bezug=V.DOVER, atlas='NP258 (Bristol Channel)', land='Wales, United Kingdom',
                            lat=lambda y: 51 + (727 - y) / 828.0,
                            lon=lambda x: float(np.polyval(np.polyfit([265, 530, 795, 1062], [-4.5, -4, -3.5, -3], 1), x)), r=40),
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
    # Verfeinern: je Stunde 1:1-Zuordnung Ablesung <-> Punktmitte (dichte Reihen ~15 px, East Solent 17.11.)
    from scipy.optimize import linear_sum_assignment
    mitten = [(c[0], c[1]) for c in cl]
    for _ in range(3):
        neu = [dict() for _m in mitten]
        for h in sorted({a[0] for a in abl}):
            ah = [a for a in abl if a[0] == h]
            D = np.array([[math.hypot(a[1] - mx, a[2] - my) for mx, my in mitten] for a in ah])
            D = np.where(D < r, D, 1e6)
            ri, ci = linear_sum_assignment(D)
            for i, j in zip(ri, ci):
                if D[i, j] < 1e6:
                    neu[j][h] = ah[i]
        mitten = [(float(np.mean([b[1] for b in n.values()])), float(np.mean([b[2] for b in n.values()]))) if n else m
                  for n, m in zip(neu, mitten)]
    cl = [(m[0], m[1], {h: (b[3], b[4]) for h, b in n.items()}) for m, n in zip(mitten, neu) if n]
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
    gut, schlecht = punkte(abl, r=cfg.get('r', 28.0))
    print('%d Ablesungen -> %d Punkte (>= 10 h), %d verworfen' % (len(abl), len(gut), len(schlecht)))
    gut = [c for c in gut if all(math.hypot(c[0] - a, c[1] - b) > 15 for a, b in cfg.get('weglassen', []))]
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
    alt_atlas = set()                                               # schon geschriebene Saetze dieses Atlas
    try:
        alt_atlas = {r['name'] for r in csv.DictReader(open(os.path.join(ROOT, 'harmonics/help/vmh_%s_punkte.csv' % name), encoding='utf-8'))}
    except FileNotFoundError:
        pass
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
        fest = [f for (ax, ay), f in cfg.get('achse', {}).items() if math.hypot(cx - ax, cy - ay) < 15]
        if fest:                                                    # Achse von Hand (Fahrwasser), Flut = steigendes Wasser
            best = fest[0]
            pm = {h: math.cos(math.radians(om * (h + 3))) for h in range(-6, 7)}
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
        nur = [a for a in argv if a.startswith('--nur=')]
        if nur and not any(math.hypot(cx - float(v.split(',')[0]), cy - float(v.split(',')[1])) < 15
                           for v in nur[0][6:].split(';')):
            continue                                                # nur ausgewaehlte Punkte neu rechnen
        # --nur: eigener frueherer Satz an derselben Stelle (< 0,2 km) wird ersetzt (Name bleibt, auch Olivers Umbenennung)
        selbst = [r for r in R if nur and r['name'] in alt_atlas and H.km(r, {'lat': la, 'lon': lo}) < 0.2]
        nah = min(((H.km(r, {'lat': la, 'lon': lo}), r['name']) for r in R if r not in selbst), default=(99, ''))
        # Name: naechste Landmarke (GeoNames, Banken/Rinnen/Kaps/Orte) + Abstand/Richtung
        lm = min(((V.A.km(la, lo, a, b), n_, _t) for n_, a, b, c, _t in Lgeo if abs(a - la) < 0.3 and abs(b - lo) < 0.5), default=None)
        if lm:
            d, ln, region = lm
            a_, b_ = next((a, b) for n_, a, b, c, _t in Lgeo if n_ == ln and abs(V.A.km(la, lo, a, b) - d) < 1e-6)
            az = math.degrees(math.atan2((lo - b_) * math.cos(math.radians(la)), la - a_)) % 360
            nm = ln if d < 1 else '%s (%d km %s)' % (ln, max(1, round(d)), RICHTUNG[int((az + 11.25) % 360 // 22.5)])
        else:
            nm = '%s %.3f %.3f' % (cfg['atlas'], la, lo)
        nm = '%s, %s Current' % (V.A.re.sub(r'[^\x00-\xff]', '', nm) if hasattr(V.A, 're') else nm,
                                 region if lm and region else cfg['land'])   # Land der Landmarke (Dover: Frankreich)
        if selbst:
            nm = selbst[0]['name']
        k = 2
        basis = nm
        while nm in namen and not selbst:
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
    if any(a.startswith('--nur=') for a in argv):
        aus = aus.replace('.csv', '_nur.csv')                       # Gesamtliste nicht ueberschreiben
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
        zl = T.split('\n')
        anhang = []
        for (nm, *_r), b in zip(bl, neu):                           # vorhandenen Satz gleichen Namens ersetzen
            bz = b.split('\n')
            if nm in zl:
                i = zl.index(nm)
                k = bz.index(nm)
                st = max(j for j in range(i - k - 5, i) if zl[j].startswith('# Harmonic constants derived'))   # Kopf evtl. umbrochen
                zl[st:i + len(bz) - k] = bz
            else:
                anhang.append(b)
        T = '\n'.join(zl)
        schreiben(A.ZIEL, T + ('\n' + '\n'.join(anhang) if anhang else '') + '\n')
        with open(os.path.join(ROOT, 'harmonics/help/neu_pruefen_%s.csv' % dt.date.today().strftime('%Y%m%d')), 'a', encoding='utf-8') as fh:
            for nm, *_r in bl:
                if not any(b.split('\n').count(nm) for b in anhang):
                    continue                                        # ersetzt: steht schon in der Pruefliste
                fh.write('harmonics_utide_current_tables.txt,"%s"\n' % nm)
        print(len(neu), 'Saetze ->', os.path.relpath(A.ZIEL, ROOT))
