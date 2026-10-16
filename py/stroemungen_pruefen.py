#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Pruefliste fuer alle Stroemungsstationen des Bestands (nur lesen).

Oliver 16.10.2026: "Bei den Stroemungsstationen ist die korrekte Position teilweise noch viel
wichtiger, weil die Stroemung an einer Meerenge (Flaschenhals) viel staerker sein kann als auf
dem offenen Meer." Bei den Laenderpruefungen waren die Stroeme zunaechst uebersehen worden.

Befunde je Satz:
  LAND      Position bis 3 km hinter der OSM-Kuestenlinie und keine Stationskette (3+ Saetze in 5 km).
  BINNEN    weiter landeinwaerts ohne Kette: die OSM-Kueste endet an Flussmuendungen, Tidefluesse
            (Hudson, Cape Fear) liegen ausserhalb -- nur Hinweis.
  RASTER    Breite und Laenge auf volle Bogenminuten (Buchwert, ~1.8 km Unsicherheit) und
            Engstelle (Wasserbreite quer zur Hauptrichtung unter 4 km): Position kritisch.
  DUBLETTE  zweite Stroemungsstation aus anderer Datei bis 1 km, gleiche Tiefe/kein Tiefenpaar.
  NAME      nicht nach der Klammer-Regel ("Fort Independence, 0.1 nmi north of") -> Vorschlag.
  RICHTUNG  Flut- und Ebbrichtung nicht rund 180 Grad auseinander (> 45 Grad Abweichung).
  KURVE     Scheintiden (S2 > M2, grosses S4/S1: Feuerschiff-Ablesungen zu festen Uhrzeiten),
            SA/SSA aus Reihen unter 330 Tagen, Restgeschwindigkeit Z0 ueber 1 kn.

Usage: venv/bin/python py/stroemungen_pruefen.py
       Land/Breite mit den OSM-Landpolygonen (py/osm_land.py), sonst grob mit der GLOBE-Maske.
       -> harmonics/help/pruefliste_stroemungen_<datum>.html/.json
"""
import collections
import datetime as dt
import html
import json
import math
import os
import re
import sys

from global_land_mask import globe

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from health_check import load_records, ROOT                      # noqa: E402
import osm_land                                                    # noqa: E402

RICHTUNGEN = {'north': 'N', 'south': 'S', 'east': 'E', 'west': 'W', 'northeast': 'NE', 'northwest': 'NW',
              'southeast': 'SE', 'southwest': 'SW'}


def km(a, b):
    return math.hypot((a[0] - b[0]) * 111.2, (a[1] - b[1]) * 111.2 * math.cos(math.radians(a[0])))


def wasser_abstand(la, lo, rmax=5.0):
    """-> km bis zur naechsten Wasserzelle (0 wenn die Position im Wasser liegt)."""
    if not globe.is_land(la, lo):
        return 0.0
    for r in [x * 0.25 for x in range(1, int(rmax / 0.25) + 1)]:
        for k in range(0, 360, 15):
            a = math.radians(k)
            p = (la + r * math.cos(a) / 111.2, lo + r * math.sin(a) / (111.2 * math.cos(math.radians(la))))
            if not globe.is_land(*p):
                return r
    return rmax + 1


def breite(la, lo, richtung):
    """Wasserbreite quer zur Stroemungsrichtung (Grad) in km, bis zum ersten Land je Seite."""
    if richtung is None:
        return None
    w = 0.0
    for seite in (90, -90):
        a = math.radians(richtung + seite)
        d = 0.0
        while d < 10:
            d += 0.25
            p = (la + d * math.cos(a) / 111.2, lo + d * math.sin(a) / (111.2 * math.cos(math.radians(la))))
            if globe.is_land(*p):
                break
        w += d
    return w


def auf_minuten(x):
    return abs(x * 60 - round(x * 60)) < 0.006


def kopf(texte, r):
    if r['file'] not in texte:
        texte[r['file']] = open(os.path.join(ROOT, r['file']), encoding='iso-8859-1').read().split('\n')
    L = texte[r['file']]
    i = r['line'] if r.get('line') is not None and L[r['line']] == r['name'] else L.index(r['name'])
    j = i
    while j > 0 and L[j - 1].startswith('#'):
        j -= 1
    return L[j:i]


def kern(n):
    """Namenskern: erstes Wort ab 4 Buchstaben, ohne Gattungswoerter."""
    for w in re.findall(r"[A-Za-z']+", n):
        if len(w) >= 4 and w.lower() not in ('point', 'pass', 'bank', 'cape', 'channel', 'entrance', 'harbor', 'island',
                                              'river', 'south', 'north', 'east', 'west', 'light', 'depth', 'inlet'):
            return w.lower()
    return n.lower()


def name_vorschlag(n):
    """NOAA-Altform -> Klammer-Regel. None, wenn der Name schon passt."""
    rumpf, land = n.rsplit(', ', 1) if ', ' in n else (n, '')
    tiefe = re.search(r'\s*\((depth [^)]*)\)\s*$', rumpf)
    if tiefe:
        rumpf = rumpf[:tiefe.start()]
    teile = [t.strip() for t in rumpf.split(',')]
    if len(teile) < 2:
        return None
    vorn, ctx = teile[0], []
    for t in teile[1:]:
        t = re.sub(r'\b(\d[\d.]*)\s*(?:n\.?\s?mi\.?|nmi|miles?)\b', r'\1 mi', t)
        t = re.sub(r'\b(north|south|east|west|northeast|northwest|southeast|southwest)\b(?=\s+of\b)',
                   lambda m: RICHTUNGEN[m.group(1).lower()], t, flags=re.I)
        ctx.append(t)
    if tiefe:
        ctx.append(tiefe.group(1))
    # eine vorhandene Klammer im Kopfteil bleibt Kontext
    m = re.match(r'^(.*?)\s*\((.*)\)$', vorn)
    if m:
        vorn, ctx = m.group(1), [m.group(2)] + ctx
    neu = '%s (%s)' % (vorn, ', '.join(ctx))
    return neu + (', ' + land if land else '')


def main(argv):
    R = [r for r in load_records() if r['lat'] is not None]
    S = [r for r in R if r['current']]
    P = [r for r in R if not r['current']]
    texte = {}
    zelle = collections.defaultdict(list)
    for r in R:
        zelle[(round(r['lat'] * 10), round(r['lon'] * 10))].append(r)

    def nachbarn(r, radius, nur_strom=False):
        out = []
        for a in (-1, 0, 1):
            for b in (-1, 0, 1):
                for x in zelle.get((round(r['lat'] * 10) + a, round(r['lon'] * 10) + b), ()):
                    if x is r or (nur_strom and not x['current']):
                        continue
                    d = km((r['lat'], r['lon']), (x['lat'], x['lon']))
                    if d <= radius:
                        out.append((d, x))
        return sorted(out, key=lambda t: t[0])

    LAND = None
    if os.path.exists(osm_land.SHP):
        print('lade OSM-Landpolygone ...', flush=True)
        LAND = osm_land.Land([(r['lat'], r['lon']) for r in S])
        print(len(LAND.geo), 'Polygone', flush=True)
    zeilen = []
    for r in S:
        k = kopf(texte, r)
        kv = {m.group(1): m.group(2).strip() for m in (re.match(r'# (\w+): (.*)', x) for x in k) if m}
        mx = float(kv['max_direction']) if kv.get('max_direction', '').replace('.', '').isdigit() else None
        mn = float(kv['min_direction']) if kv.get('min_direction', '').replace('.', '').isdigit() else None
        b = []
        if LAND is not None:
            wd = LAND.kueste_km(r['lat'], r['lon']) if LAND.ist_land(r['lat'], r['lon']) else 0.0
        else:
            wd = wasser_abstand(r['lat'], r['lon'])
        if wd > (0.2 if LAND is not None else 1.0):
            nb = nachbarn(r, 5.0)
            ns, npg = sum(1 for _, x in nb if x['current']), sum(1 for _, x in nb if not x['current'])
            quelle = 'OSM-Kueste' if LAND is not None else 'Landmaske 1 km'
            if len(nb) >= 3:
                pass                                      # Kette von Stationen: Tidefluss (Hudson, Cape Fear)
            elif wd < 3.0:
                b.append('LAND: %.1f km hinter der Kueste (%s), in 5 km %d Stroeme, %d Pegel' % (wd, quelle, ns, npg))
            else:
                b.append('BINNEN: %.0f km hinter der Kuestenlinie (%s), keine Stationskette -- Tidefluss pruefen' % (wd, quelle))
        if auf_minuten(r['lat']) and auf_minuten(r['lon']):
            w = LAND.breite_km(r['lat'], r['lon'], mx) if LAND is not None else breite(r['lat'], r['lon'], mx)
            if w is not None and w < 4.0:
                b.append('RASTER: Position auf volle Bogenminuten (~1.8 km unsicher) an Engstelle '
                         '(Wasser quer zur Flutrichtung %.1f km)' % w)
        tf = re.search(r'\(depth ([\d.]+)', r['name'])
        for d, x in nachbarn(r, 1.0, nur_strom=True):
            if x['file'] == r['file']:
                continue
            tx = re.search(r'\(depth ([\d.]+)', x['name'])
            if tf and tx and tf.group(1) != tx.group(1):
                continue
            if (x['file'], x['name']) < (r['file'], r['name']):
                continue                                  # Paar nur einmal melden
            if d > 0.3 and kern(r['name']) != kern(x['name']):
                continue                                  # Nebenstationen liegen absichtlich > 300 m daneben
            b.append('DUBLETTE: "%s" (%s) %.2f km' % (x['name'], os.path.basename(x['file']), d))
        if not re.search(r'[A-Za-z]{3}', r['name'].rsplit(', ', 1)[0]):
            b.append('NAME: kein Ortsname, nur Kennung')
        nv = name_vorschlag(r['name'])
        if nv and nv != r['name']:
            b.append('NAME: Klammer-Regel -> "%s"' % nv)
        if mx is not None and mn is not None:
            diff = abs(((mx - mn) % 360) - 180)
            if diff > 45:
                b.append('RICHTUNG: Flut %.0f, Ebbe %.0f Grad (%.0f Grad neben Gegenrichtung)' % (mx, mn, diff))
        A = {}
        L = texte[r['file']]
        i0 = L.index(r['name'], max(0, (r.get('line') or 0) - 5)) if r['name'] in L else None
        if i0 is not None:
            for x in L[i0 + 3:i0 + 200]:
                mm = re.match(r'^(\S+)\s+([\d.]+)\s+([\d.]+)$', x)
                if mm:
                    A[mm.group(1)] = float(mm.group(2))
                elif x != 'x 0 0':
                    break
            try:
                z0 = float(L[i0 + 2].split()[0])
            except (ValueError, IndexError):
                z0 = 0.0
            m2, s2, s4 = A.get('M2', 0), A.get('S2', 0), A.get('S4', 0)
            s1 = max(A.get('S1', 0), A.get('S1-IOS', 0))
            sa, ssa = max(A.get('SA', 0), A.get('SA-IOS', 0)), A.get('SSA', 0)
            per = re.search(r'period=(\d{4}-\d\d-\d\d)\.\.(\d{4}-\d\d-\d\d)', ' '.join(k))
            tage = (dt.date.fromisoformat(per.group(2)) - dt.date.fromisoformat(per.group(1))).days if per else None
            kb = []
            if s2 > 1.2 * m2 and s2 > 0.2:
                kb.append('S2 %.2f > M2 %.2f' % (s2, m2))
            if s4 > 0.3 * max(m2, 0.01) and s4 > 0.1:
                kb.append('S4 %.2f' % s4)
            if s1 > 0.5 * max(m2, 0.01) and s1 > 0.1:
                kb.append('S1 %.2f' % s1)
            if tage and tage < 330 and (sa > 0.2 or ssa > 0.2):
                kb.append('SA/SSA %.2f/%.2f aus %d Tagen' % (sa, ssa, tage))
            if abs(z0) > 1.0:
                kb.append('Restgeschwindigkeit Z0 %.2f kn' % z0)
            if kb:
                b.append('KURVE: ' + '; '.join(kb))
        zeilen.append(dict(satz=r['name'], datei=r['file'], lat=r['lat'], lon=r['lon'], befunde=b,
                           land=r['name'].rsplit(', ', 1)[-1].replace(' Current', '')))
    heute = dt.date.today().strftime('%Y%m%d')
    stem = os.path.join(ROOT, 'harmonics/help/pruefliste_stroemungen_%s' % heute)
    json.dump(zeilen, open(stem + '.json', 'w'), ensure_ascii=False, indent=0)
    art = collections.Counter(x.split(':')[0] for z in zeilen for x in z['befunde'])
    nach_land = collections.defaultdict(list)
    for z in zeilen:
        if any(not x.startswith('NAME') for x in z['befunde']):
            nach_land[z['land']].append(z)
    teile = ['<!doctype html><html lang="de"><head><meta charset="utf-8">'
             '<meta name="viewport" content="width=device-width,initial-scale=1"><title>Pruefliste Stroemungen</title>'
             '<style>:root{--bg:#fff;--fg:#1d2430;--mut:#5b6575;--li:#d8dee8;--hd:#eef2f7}'
             '@media (prefers-color-scheme:dark){:root{--bg:#14181f;--fg:#e4e8ef;--mut:#9aa4b4;--li:#2c3440;--hd:#1d232c}}'
             'body{background:var(--bg);color:var(--fg);font:14px/1.4 system-ui,sans-serif;margin:0;padding:16px}'
             'table{border-collapse:collapse;width:100%;margin:6px 0 20px}td,th{border:1px solid var(--li);padding:4px 6px;'
             'vertical-align:top;text-align:left}th{background:var(--hd)}small{color:var(--mut)}a{color:inherit}</style></head><body>',
             '<h1>Pruefliste Stroemungen (%s)</h1>' % heute,
             '<p>%d Stroemungssaetze. Befunde: %s. Namensvorschlaege stehen nur in der JSON-Datei '
             'und unten zusammengefasst; geaendert ist nichts.</p>' % (
                 len(zeilen), ', '.join('%s %d' % kv for kv in art.most_common()))]
    for land in sorted(nach_land, key=lambda l: -len(nach_land[l])):
        teile.append('<h2>%s (%d)</h2><table><tr><th>Satz</th><th>Position</th><th>Befunde</th></tr>' % (
            html.escape(land), len(nach_land[land])))
        for z in sorted(nach_land[land], key=lambda z: z['satz']):
            teile.append('<tr><td>%s<br><small>%s</small></td><td><a href="https://www.google.com/maps?q=%.5f,%.5f">'
                         '%.4f / %.4f</a></td><td>%s</td></tr>' % (
                             html.escape(z['satz']), os.path.basename(z['datei']), z['lat'], z['lon'], z['lat'], z['lon'],
                             '<br>'.join(html.escape(x) for x in z['befunde'] if not x.startswith('NAME'))))
        teile.append('</table>')
    nam = [z for z in zeilen if any(x.startswith('NAME') for x in z['befunde'])]
    teile.append('<h2>Namen nach Klammer-Regel (%d Vorschlaege, Auswahl)</h2><table><tr><th>heute</th><th>Vorschlag</th></tr>' % len(nam))
    for z in nam[:150]:
        v = next(x for x in z['befunde'] if x.startswith('NAME'))
        teile.append('<tr><td>%s</td><td>%s</td></tr>' % (html.escape(z['satz']), html.escape(v.split('-> ', 1)[1].strip('"'))))
    teile.append('</table></body></html>')
    open(stem + '.html', 'w', encoding='utf-8').write('\n'.join(teile))
    print(len(zeilen), 'Saetze;', dict(art))
    print(os.path.relpath(stem + '.html', ROOT))


if __name__ == '__main__':
    main(sys.argv[1:])
