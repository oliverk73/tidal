#!/usr/bin/env python3
"""Positionsvorschlaege aus GeoNames fuer die Saetze eines Landes.

Fuer jeden Satz wird der Ortsname (Teil vor dem ersten Komma, Klammerzusatz
getrennt) in GeoNames gesucht -- in Haupt- und Alternativnamen, ohne
Diakritika, Apostrophe, Bindestriche und Gross/Klein. Treffer bis MAX_KM um
die bisherige Position zaehlen. Bevorzugt werden Objekte, die zum Namen
passen: "-do"/"Dao"/"Island" -> Insel, "Gang/Hang/Port" -> Hafen,
"Got/Gap/Cape" -> Kap, "Man/Wan/Bay" -> Bucht, sonst Hafen vor Ort.

Ausgabe: harmonics/help/positionen_<land>_<datum>.csv mit Vorschlag und
Abstand; es wird nichts an den Saetzen geaendert.

    python3 py/positionen_geonames.py "South Korea" KR
"""
import csv
import os
import re
import sys
import unicodedata
import zipfile
import io
import urllib.request
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from health_check import load_records, km, auf_raster, ROOT  # noqa: E402

MAX_KM = 12.0
CACHE = os.path.join(ROOT, 'harmonics/help/geonames')


def norm(s):
    s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode().lower()
    return re.sub(r'[^a-z0-9]', '', s)


def geonames(cc):
    os.makedirs(CACHE, exist_ok=True)
    pfad = os.path.join(CACHE, cc + '.txt')
    if not os.path.exists(pfad):
        z = urllib.request.urlopen('https://download.geonames.org/export/dump/%s.zip' % cc, timeout=120).read()
        with zipfile.ZipFile(io.BytesIO(z)) as zf:
            open(pfad, 'wb').write(zf.read(cc + '.txt'))
    out = []
    for l in open(pfad, encoding='utf-8'):
        f = l.rstrip('\n').split('\t')
        try:
            lat, lon = float(f[4]), float(f[5])
        except (ValueError, IndexError):
            continue
        namen = {norm(f[1]), norm(f[2])} | {norm(a) for a in f[3].split(',') if a}
        out.append(dict(name=f[1], lat=lat, lon=lon, fcl=f[6], fcode=f[7], namen=namen - {''}))
    return out


# Gattungswoerter, die am Namen haengen oder fehlen duerfen
GATTUNG = r'(do|to|som|seom|dao|island|ri|ni|li|dong|tong|hang|gang|kang|port|harbou?r|got|kot|gap|kap|' \
          r'cape|dan|tan|man|wan|bay|po|p.o)$'


def varianten(teil):
    v = {norm(teil)}
    for t in re.split(r'[/()]', teil):
        t = t.strip()
        if t:
            v.add(norm(t))
            v.add(re.sub(GATTUNG, '', norm(t)))
    return {x for x in v if len(x) >= 3}


def bevorzugt(name, g):
    n = name.lower()
    if re.search(r"\b(do|to|dao|island|islands|som|seom)\b|-do\b|-to\b|do$", n):
        return g['fcl'] == 'T' and g['fcode'].startswith('ISL')
    if re.search(r'\b(gang|hang|port|harbou?r)\b|hang\b', n):
        return g['fcode'] in ('PRT', 'HBR') or g['fcl'] == 'L'
    if re.search(r'\b(got|kot|gap|cape|dan|point)\b|-got\b|-dan\b', n):
        return g['fcode'] in ('CAPE', 'PT', 'PTS')
    if re.search(r'\b(man|wan|bay)\b|-man\b', n):
        return g['fcode'] in ('BAY', 'BAYS', 'COVE', 'INLT')
    return g['fcode'] in ('PRT', 'HBR', 'PPL', 'PPLA', 'PPLA2', 'PPLA3', 'PPLA4', 'PPLC', 'PPLX')


def main(argv):
    land, cc = argv[1], argv[2]
    gn = geonames(cc)
    rs = [r for r in load_records() if r['name'].endswith(land) and not r['current']]
    zeilen = []
    for r in sorted(rs, key=lambda r: r['name']):
        teil = r['name'].rsplit(',', 1)[0]
        teil = re.sub(r',.*', '', teil)
        var = varianten(teil)
        kand = []
        for g in gn:
            d = km(r, g)
            if d > MAX_KM:
                continue
            treffer = any(v in g['namen'] or any(n.startswith(v) and len(n) - len(v) <= 5 for n in g['namen'])
                          for v in var)
            if treffer:
                kand.append((0 if bevorzugt(teil, g) else 1, d, g))
        kand.sort(key=lambda t: (t[0], t[1]))
        z = dict(satz=r['name'], datei=os.path.basename(r['file']), lat=r['lat'], lon=r['lon'],
                 raster='ja' if auf_raster(r['lat'], r['lon']) else '')
        if kand:
            p, d, g = kand[0]
            z.update(gn_name=g['name'], gn_art=g['fcode'], gn_lat=round(g['lat'], 4),
                     gn_lon=round(g['lon'], 4), abstand_km=round(d, 2),
                     passend='ja' if p == 0 else 'nein', weitere=len(kand) - 1)
        zeilen.append(z)
    aus = os.path.join(ROOT, 'harmonics/help/positionen_%s_%s.csv'
                       % (re.sub(r'\W+', '_', land.lower()), date.today().strftime('%Y%m%d')))
    felder = ['satz', 'datei', 'lat', 'lon', 'raster', 'gn_name', 'gn_art', 'gn_lat', 'gn_lon',
              'abstand_km', 'passend', 'weitere']
    with open(aus, 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=felder)
        w.writeheader()
        w.writerows(zeilen)
    mit = sum(1 for z in zeilen if z.get('gn_name'))
    print('%d Saetze, %d mit GeoNames-Treffer, Tabelle %s' % (len(zeilen), mit, os.path.relpath(aus, ROOT)))


if __name__ == '__main__':
    main(sys.argv)
