#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Namen der St.-Lorenz-Atlas-Stromsaetze neu (Oliver 21.11.2026).

Befund Oliver: Bezugsorte oft weiter weg als kleine Inseln direkt daneben (Madame Reef, St. Thomas Point,
Kamouraska ...), Île Rouge statt der viel naeheren Île Verte, Trois Pistoles statt Île aux Basques; in Québec
franzoesische Namen.
Ursache: name_fuer() in stlorenz_atlas nahm Inseln nur bis 1 km zum Mittelpunkt (grosse Inseln fielen immer
heraus) und GeoNames (alte englische Seekartennamen).

Neu: CGNDB (amtlich, Québec franzoesisch; quellen/.../cgndb_stlorenz.json), Inseln mit Abstand zur Kueste (OSM-
Landpolygon, das den Inselpunkt enthaelt; Richtung vom naechsten Uferpunkt). Reihenfolge:
  1. Rinne/Passe (CHAN) bis 2 km -> "Chenal X (Bezug)"
  2. naechstes Kap/Pointe (CAPE), Untiefe/Recif (SHL) oder Insel (ISL); Ort (VILG/TOWN/CITY/UNP) nur, wenn er
     hoechstens halb so weit ist
  3. "Name" unter 1 km, sonst "Name (d km RICHTUNG)".
Nur Kartenpunkte (CHS-ATLAS-STL-S*), deren Name noch der urspruengliche ist (stlorenz_atlas_punkte.csv) --
Olivers Umbenennungen bleiben. Zieht eigen.json (Kompass) und help/neu_pruefen_*.csv nach.

Usage: venv/bin/python py/stlorenz_namen.py [--schreiben]
"""
import csv
import glob
import json
import math
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ZIEL = os.path.join(ROOT, 'harmonics/utide/harmonics_utide_current_tables.txt')
CGNDB = os.path.join(ROOT, 'quellen/tidal_streams/Canada_CHS_atlas/cgndb_stlorenz.json')
EIGEN = os.path.join(ROOT, 'harmonics/ellipsen/eigen.json')
RICHTUNG = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE', 'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW']
ORT = {'VILG', 'TOWN', 'CITY'}                                     # UNP = Ortsteile (Parc-Belvedere, Lauzon)
FELS_KM = 1.5
# englische Altnamen (GeoNames/alte CHS-Karten) werden immer ersetzt
ENGLISCH = re.compile(r'\b(Point|Reef|Bank|Shoals?|Island|Rock|Pillar|Patch|Cape|Light|Ste?\.)\b|^Trois Pistoles')


def km(a, b, c, d):
    return math.hypot((a - c) * 111.2, (b - d) * 111.2 * math.cos(math.radians((a + c) / 2)))


def ri(la, lo, a, b):
    az = math.degrees(math.atan2((lo - b) * math.cos(math.radians(la)), la - a)) % 360
    return RICHTUNG[int((az + 11.25) % 360 // 22.5)]


class Namen:
    def __init__(self, punkte):
        import osm_land
        from shapely.geometry import Point
        self.P = Point
        G = json.load(open(CGNDB, encoding='utf-8'))
        self.G = [(n, a, b, c) for n, a, b, c, _p in G if c in {'CAPE', 'SHL', 'ISL', 'CHAN'} | ORT
                  and not n.startswith(('Archipel', 'Circonscription', 'District'))]
        self.L = osm_land.Land(punkte + [(a, b) for n, a, b, c in self.G if c == 'ISL'])
        self.insel = {}
        for n, a, b, c in self.G:
            if c != 'ISL':
                continue
            p = Point(b, a)
            treff = [g for g in self.L._treffer(p.buffer(0.004)) if g.distance(p) < 0.004]
            treff = [g for g in treff if g.area * 111.2 ** 2 * math.cos(math.radians(a)) < 400]   # Festlandsteile weg
            if treff:
                self.insel[(n, a, b)] = min(treff, key=lambda g: g.distance(p))

    def flaeche(self, n, la, lo):
        g = next((v for (n2, a, b), v in self.insel.items() if n2 == n and abs(a - la) < 0.3 and abs(b - lo) < 0.45), None)
        return 0 if g is None else g.area * 111.2 ** 2 * math.cos(math.radians(la))

    def abstand(self, la, lo, n, a, b, c):
        """(km, Bezugspunkt lat, lon) -- Insel: naechster Uferpunkt."""
        g = self.insel.get((n, a, b)) if c == 'ISL' else None
        if g is None:
            return km(la, lo, a, b), a, b
        from shapely.ops import nearest_points
        q = nearest_points(self.P(lo, la), g.exterior if g.geom_type == 'Polygon' else g)[1]
        if g.contains(self.P(lo, la)):
            return 0.0, la, lo
        return km(la, lo, q.y, q.x), q.y, q.x

    @staticmethod
    def art(n, c):
        """INSEL (Abstand zur Kueste), KAP, FELS (Fels/Caye/Bank: nur bis FELS_KM) oder None (Poulier, Langue de terre ...)."""
        if c == 'ISL' and re.search(r'(^|\s)(Île|Îlet|Îles|Îlets)(\s|$)', n):
            return 'INSEL'
        if c == 'CAPE':
            return 'KAP' if re.match(r"(Cap|Pointe|Gros cap|Petit cap|Grand cap|Bec)\b", n) else None
        if c in ('ISL', 'SHL') and not re.match(r'(Poulier|Barre|Batture|Plateau)\b', n):
            return 'FELS'
        return None

    def name(self, la, lo, fels_km=FELS_KM):
        """(Name, km) -- km = Abstand zum Bezug."""
        nah = [(km(la, lo, a, b), n, a, b, c) for n, a, b, c in self.G if abs(a - la) < 0.3 and abs(b - lo) < 0.45]
        mar = []
        for d0, n, a, b, c in nah:
            t = self.art(n, c)
            if t and d0 < 30:
                d, qa, qb = self.abstand(la, lo, n, a, b, c)
                if t != 'FELS' or d <= fels_km:
                    mar.append((d + (1.5 if t == 'FELS' else 0.0), d, n, qa, qb, c))
        mar = [x[1:] for x in sorted(mar)]   # Kap/Insel vor Fels, solange <= 1,5 km weiter
        # grosse Insel (> 20 km2, z. B. Île aux Coudres, Île Verte): ein Kap bis 2,5 km sagt genauer, wo
        if mar and mar[0][4] == 'ISL' and self.flaeche(*mar[0][1:2], la, lo) > 20:
            kap = [x for x in mar if x[4] == 'CAPE' and x[0] <= 2.5]
            if kap:
                d, n, a, b, c = kap[0]
                ins = mar[0][1]
                return ('%s (%s), Québec, Canada Current' % (n, ins) if d < 1 else '%s (%d km %s, %s), Québec, Canada Current' % (
                    n, max(1, round(d)), ri(la, lo, a, b), ins)), d
        orte = sorted(x for x in nah if x[4] in ORT)
        rinne = sorted(x for x in nah if x[4] == 'CHAN' and x[0] <= 2.0)

        def fmt(d, n, a, b):
            return n if d < 1 else '%s %d km %s' % (n, round(d), ri(la, lo, a, b))
        if rinne and mar and mar[0][0] <= 15:
            return '%s (%s), Québec, Canada Current' % (rinne[0][1], fmt(*mar[0][:4])), mar[0][0]
        best = mar[0] if mar else None
        if orte and (best is None or orte[0][0] <= best[0] / 2):
            best = orte[0]
        if best is None:
            return None, None
        d, n, a, b = best[:4]
        return (('%s, Québec, Canada Current' % n) if d < 1 else '%s (%d km %s), Québec, Canada Current' % (
            n, max(1, round(d)), ri(la, lo, a, b))), d


def main(argv):
    from sicher_schreiben import schreiben
    T = open(ZIEL, encoding='iso-8859-1').read().split('\n')
    ursprung = {r['name'] for r in csv.DictReader(open(os.path.join(ROOT, 'harmonics/help/stlorenz_atlas_punkte.csv'), encoding='utf-8'))}
    saetze = []                                         # (zeile, name, lat, lon)
    for i, z in enumerate(T):
        if z.startswith('# station_id_context: CHS-ATLAS-STL-S'):
            j = i
            while T[j].startswith('#'):
                j += 1
            kopf = T[i:j]
            la = float(next(x for x in kopf if x.startswith('# !latitude:')).split()[-1])
            lo = float(next(x for x in kopf if x.startswith('# !longitude:')).split()[-1])
            saetze.append((j, T[j], la, lo))
    alle = set(z for z in T if z and not z.startswith('#'))
    N = Namen([(la, lo) for _j, _n, la, lo in saetze])
    paare, frei = [], set()
    for j, alt, la, lo in saetze:
        if alt not in ursprung:
            print('  %-60s (umbenannt von Oliver, bleibt)' % alt)
            continue
        m_ = re.search(r'\((\d+(?:\.\d+)?) km', alt)
        d_alt = float(m_.group(1)) if m_ else 0.5
        englisch = bool(ENGLISCH.search(alt.split(',')[0]))
        # englischer Altname: Felsen/Baenke bis zum alten Abstand zulassen (Neptune Rock -> Rocher de Neptune)
        neu, d_neu = N.name(la, lo, fels_km=max(FELS_KM, d_alt + 0.6) if englisch else FELS_KM)
        if not neu:
            continue
        if not englisch and d_neu > 0.6 * d_alt:
            continue
        basis, k = neu, 2
        while (neu in alle and neu != alt) or neu in frei:
            neu = basis.replace(' Current', ' (%d) Current' % k)
            k += 1
        frei.add(neu)
        if neu != alt:
            paare.append((j, alt, neu))
            print('%-58s -> %s' % (alt[:58], neu))
    print('%d von %d Saetzen umbenannt' % (len(paare), len(saetze)))
    if '--schreiben' not in argv or not paare:
        return
    for j, alt, neu in paare:
        assert T[j] == alt
        T[j] = neu
    s = '\n'.join(T)
    s.encode('latin-1')
    schreiben(ZIEL, s)
    E = json.load(open(EIGEN, encoding='utf-8'))
    d = E[os.path.basename(ZIEL)]
    for _j, alt, neu in paare:
        if alt in d:
            d[neu] = d.pop(alt)
    json.dump(E, open(EIGEN, 'w', encoding='utf-8'), ensure_ascii=False, indent=1, sort_keys=True)
    m = {alt: neu for _j, alt, neu in paare}
    for p in glob.glob(os.path.join(ROOT, 'harmonics/help/neu_pruefen_*.csv')):
        Z = list(csv.reader(open(p, encoding='utf-8')))
        if any(len(r) > 1 and r[1] in m for r in Z):
            Z = [[r[0], m.get(r[1], r[1])] + r[2:] if len(r) > 1 else r for r in Z]
            with open(p, 'w', newline='', encoding='utf-8') as fh:
                csv.writer(fh).writerows(Z)
            print('  Pruefliste', os.path.basename(p))
    with open(os.path.join(ROOT, 'harmonics/help/stlorenz_atlas_punkte.csv'), encoding='utf-8') as fh:
        R = list(csv.DictReader(fh))
    for r in R:
        r['name'] = m.get(r['name'], r['name'])
    with open(os.path.join(ROOT, 'harmonics/help/stlorenz_atlas_punkte.csv'), 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=list(R[0]))
        w.writeheader()
        w.writerows(R)


if __name__ == '__main__':
    main(sys.argv[1:])
