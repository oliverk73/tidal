#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Schlauere Lueckensuche fuer FES-Saetze (Oliver 12.11.2026: "Ja, baue die intelligente Lueckensuche").

Lehren aus py/luecken_fes_welt.py (26.10./11.11.):
  * Puri (200.000 Einw., direkt am Meer) fiel durch: keine Mess-/Tafelreferenz in 150 km -> verworfen.
    Neu: ohne Referenz zaehlt die Einigkeit FES <-> TPXO10 (tpxo_vergleich 12.11.: Abstand < 3 % -> FES-Fehler
    Median 1,8 %). Urteil 'modelle_einig' (FES-TPXO10 < EINIG %), angelegt mit confidence 4.
  * Groessere Orte brauchen einen eigenen Satz auch bei Nachbarn in 15-20 km: Luecke ab luecke_km(einwohner).
  * GeoNames-Punkte ohne Ort (Nzassi, Mambulo, Gadung, Me Taw ...) -> Ort muss per Nominatim als place-Objekt
    gleichen Namens in ORT_KM um den GeoNames-Punkt stehen; dessen Koordinate gilt.
  * Orte im Landesinneren (Buug, Rio Hato, Nandayure) -> OSM-Ort hoechstens KUESTE_KM von der Kueste (osm_land).
  * Grosse Flussstaedte (>= FLUSS_EINW) 2-100 km landeinwaerts -> eigene Liste 'flussstadt' (Muendung von Oliver).
Pier/Hafen: Overpass (harbour/pier/ferry_terminal/marina) bis HAFEN_KM um den OSM-Ort; sonst naechstes Wasser.
Schreibt nur Listen: harmonics/help/luecken_schlau.csv (+ Cache water_levels/luecken_schlau_cache.json).
Anlegen danach mit py/fes_neu_geeicht.py --welt (Spalten land,cc,region,name,einwohner,lat,lon,urteil,fes_median_pct,tz).

Usage: venv/bin/python py/luecken_schlau.py <geonames-ordner> [--orte cities1000.txt] [--min 5000] [--ohne-netz]
"""
import cmath
import collections
import csv
import json
import math
import os
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
import difflib

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import health_check as H                                           # noqa: E402
import luecken_fes_welt as LW                                      # noqa: E402
import osm_land                                                    # noqa: E402
import tpxo as T                                                   # noqa: E402

ROOT = LW.ROOT
AUS = os.path.join(ROOT, 'harmonics/help/luecken_schlau.csv')
CACHE = os.path.join(ROOT, 'water_levels/luecken_schlau_cache.json')
KUESTE_KM, ORT_KM, HAFEN_KM, EINIG, FLUSS_EINW, FLUSS_DEM, MIN_HUB = 2.0, 3.0, 2.0, 5.0, 100000, 15, 1.0
PLACE = {'city', 'town', 'village', 'hamlet', 'suburb', 'quarter', 'neighbourhood', 'locality', 'isolated_dwelling',
         'administrative', 'municipality'}


def luecke_km(einw):
    return 8.0 if einw >= 100000 else (12.0 if einw >= 20000 else (16.0 if einw >= 5000 else 20.0))


def norm(s):
    # Akzente weg, Landesschrift bleibt (frueher ascii-ignore: Arabisch/Hebraeisch wurde leer -> Sousse, Gaza fielen durch)
    s = ''.join(c for c in unicodedata.normalize('NFKD', s or '') if not unicodedata.combining(c)).casefold()
    return ''.join(c for c in s if c.isalnum())


def km(a, b):
    return 6371 * math.hypot(math.radians(a[0] - b[0]), math.radians(((a[1] - b[1] + 180) % 360) - 180) * math.cos(math.radians(a[0])))


def meer_bis(la, lo, rmax):
    """Meer (global_land_mask) innerhalb rmax km? Ringe alle 10 km, 24 Richtungen."""
    for d in np.arange(10.0, rmax + 0.1, 10.0):
        for az in range(0, 360, 15):
            if LW.meer(la + d / 111.2 * math.cos(math.radians(az)),
                       lo + d / (111.2 * max(0.1, math.cos(math.radians(la)))) * math.sin(math.radians(az))):
                return True
    return False


def main(argv):
    gn = argv[0]
    opt = {argv[i]: argv[i + 1] for i in range(1, len(argv) - 1) if argv[i].startswith('--') and not argv[i + 1].startswith('--')}
    ortsdatei = opt.get('--orte', 'cities1000.txt')
    min_einw = int(opt.get('--min', 5000))
    netz = '--ohne-netz' not in argv
    cache = json.load(open(CACHE)) if os.path.exists(CACHE) else {}
    letzte = [0.0]

    def hole(url, daten=None, pause=1.1):
        key = url + (daten or '')
        if key in cache:
            return cache[key]
        if not netz:
            return None
        time.sleep(max(0.0, pause - (time.time() - letzte[0])))
        for versuch in range(3):
            try:
                req = urllib.request.Request(url, data=daten.encode() if daten else None, headers={'User-Agent': 'weather-tides/1.0'})
                cache[key] = json.load(urllib.request.urlopen(req, timeout=90))
                break
            except Exception:                                     # noqa: BLE001
                time.sleep(5 * (versuch + 1))
        letzte[0] = time.time()
        if len(cache) % 20 == 0:
            json.dump(cache, open(CACHE, 'w'))
        return cache.get(key)

    adm = {}
    for l in open(os.path.join(gn, 'admin1CodesASCII.txt'), encoding='utf-8'):
        f = l.rstrip('\n').split('\t')
        adm[f[0]] = f[1]
    land = {}
    for l in open(os.path.join(gn, 'countryInfo.txt'), encoding='utf-8'):
        if not l.startswith('#'):
            f = l.split('\t')
            land[f[0]] = f[4]
    import netCDF4 as nc
    F = {k: nc.Dataset(os.path.join(LW.FES_DIR, '%s_fes2022.nc' % k.lower())) for k in LW.K}

    def fes(la, lo):
        out = {}
        for k in LW.K:
            a, g = LW.sample(F[k], la, lo)
            if a:
                out[k] = cmath.rect(a, math.radians(g))
        return out

    recs = [r for r in H.load_records() if r['lat'] is not None and not r['current']]
    rl = np.radians([r['lat'] for r in recs])
    ro = np.radians([r['lon'] for r in recs])

    def naechster(la, lo):
        a, b = math.radians(la), math.radians(lo)
        x = np.sin((rl - a) / 2) ** 2 + np.cos(a) * np.cos(rl) * np.sin((ro - b) / 2) ** 2
        i = int(x.argmin())
        return float(6371 * 2 * np.arcsin(np.sqrt(x[i]))), recs[i]['name']

    # Referenzurteil wie luecken_fes_welt (vorhandene Datei nutzen: FES-Fehler der Mess-/Amtssaetze)
    refs = []
    for r in recs:
        if 'fes2022' in r['file'] or 'secondary' in r['file'] or not LW.REF_DATEI.search(os.path.basename(r['file'])):
            continue
        fv = fes(r['lat'], r['lon'])
        if 'M2' not in fv or 'K1' not in fv or r['tot'] < 0.15:
            continue
        z = {k: cmath.rect(abs(r['z'][k]), -cmath.phase(r['z'][k])) for k in LW.K}   # Greenwich, a*e^{+ig} wie fes()
        cs = [k for k in LW.K if k in fv]
        refs.append((r['lat'], r['lon'], 100 * math.sqrt(sum(abs(z[k] - fv[k]) ** 2 for k in cs) / 2) / r['tot']))
    fa = np.radians([x[0] for x in refs])
    fo = np.radians([x[1] for x in refs])
    fe = np.array([x[2] for x in refs])
    print('%d Referenzsaetze, FES-Fehler Median %.1f %%' % (len(refs), float(np.median(fe))), flush=True)

    laender = {}

    def L(la, lo):
        k = (math.floor(la), math.floor(lo))
        if k not in laender:
            laender[k] = osm_land.Land([(la, lo)])
        return laender[k]

    zeilen = []
    n = 0
    for l in open(os.path.join(gn, ortsdatei), encoding='utf-8'):
        f = l.rstrip('\n').split('\t')
        name, la, lo, cc, a1, pop, tz, fcode = f[1], float(f[4]), float(f[5]), f[8], f[10], int(f[14] or 0), f[17], f[7]
        dem = int(f[16]) if f[16].lstrip('-').isdigit() else 9999
        alle_namen = {norm(x) for x in [name, f[2]] + f[3].split(',') if x and len(norm(x)) >= 2}
        if pop < min_einw or abs(la) > 72 or fcode in ('PPLX', 'PPLH', 'PPLQ', 'PPLW'):
            continue
        # Vorfilter billig: Meer in 5 km (global_land_mask) oder grosse Stadt bis 100 km (Flussstadt)
        mp = LW.meerpunkt(la, lo)
        fluss = False
        if not mp:
            # Flussstadt: gross, nah am Meer und tief gelegen (SRTM <= FLUSS_DEM m) -- Sao Paulo (760 m) ist keine
            if pop < FLUSS_EINW or dem > FLUSS_DEM or not meer_bis(la, lo, 100.0):
                continue
            fluss = True
        d_satz, s_name = naechster(la, lo)
        if d_satz <= (15.0 if fluss else luecke_km(pop)):         # Flussstadt mit eigenem Satz (Hamburg, Bremen) raus
            continue
        n += 1
        e = dict(land=land.get(cc, cc), cc=cc, region=adm.get('%s.%s' % (cc, a1), ''), name=name, einwohner=pop, tz=tz,
                 gn_lat='%.4f' % la, gn_lon='%.4f' % lo, naechster_satz=s_name, naechster_km='%.1f' % d_satz)
        # OSM-Ort gleichen Namens um den GeoNames-Punkt
        box = '%.4f,%.4f,%.4f,%.4f' % (lo - 0.06, la + 0.05, lo + 0.06, la - 0.05)
        res = hole('https://nominatim.openstreetmap.org/search?' + urllib.parse.urlencode(
            dict(q=name, format='jsonv2', limit=8, viewbox=box, bounded=1)))
        osm = None
        for x in res or []:
            p = (float(x['lat']), float(x['lon']))
            nm = x.get('name') or x['display_name'].split(',')[0]
            # GeoNames-Alternativnamen (Landesschrift: Sousse, Gaza, Holon fielen sonst durch)
            s = max([difflib.SequenceMatcher(None, a, norm(nm)).ratio() for a in alle_namen if norm(nm)] + [0.0])
            if norm(nm) and norm(nm) in alle_namen:
                s = 1.0
            if (x.get('category') in ('place', 'boundary') or x.get('type') in PLACE) and km((la, lo), p) <= ORT_KM and s >= 0.75:
                if osm is None or km((la, lo), p) < km((la, lo), osm[0]):
                    osm = (p, nm, x.get('type'))
        if res is None:
            e['urteil'] = 'ungeprueft (Netz)'
            zeilen.append(e)
            continue
        if not osm:
            e['urteil'] = 'kein OSM-Ort'
            zeilen.append(e)
            continue
        p = osm[0]
        e.update(osm_name=osm[1], osm_typ=osm[2] or '', lat='%.4f' % p[0], lon='%.4f' % p[1])
        lk = L(*p)
        kk = 0.0 if not lk.ist_land(*p) else lk.kueste_km(*p, rmax=100 if fluss else 10)
        e['kueste_km'] = '%.1f' % kk
        if kk > KUESTE_KM:
            e['urteil'] = 'flussstadt' if (pop >= FLUSS_EINW and kk <= 100) else 'landeinwaerts'
            zeilen.append(e)
            continue
        d_satz, s_name = naechster(*p)
        e.update(naechster_satz=s_name, naechster_km='%.1f' % d_satz)
        if d_satz <= luecke_km(pop):
            continue
        mp = LW.meerpunkt(*p) or p
        fv = fes(*mp)
        if 'M2' not in fv:
            e['urteil'] = 'FES leer'
            zeilen.append(e)
            continue
        hub = 2 * (abs(fv['M2']) + abs(fv.get('S2', 0)))
        e['springhub_m'] = '%.1f' % hub
        if hub < MIN_HUB:
            continue
        # Hafen/Pier in der Naehe
        q = '[out:json][timeout:30];(node(around:%d,%.5f,%.5f)[harbour];nwr(around:%d,%.5f,%.5f)[man_made=pier];nwr(around:%d,%.5f,%.5f)[amenity=ferry_terminal];nwr(around:%d,%.5f,%.5f)[leisure=marina];);out center 20;' % (
            (HAFEN_KM * 1000, *p) * 4)
        h = hole('https://overpass-api.de/api/interpreter', 'data=' + urllib.parse.quote(q), pause=2.0)
        if h and h.get('elements'):
            el = min(h['elements'], key=lambda x: km(p, (x.get('lat') or x['center']['lat'], x.get('lon') or x['center']['lon'])))
            hp = (el.get('lat') or el['center']['lat'], el.get('lon') or el['center']['lon'])
            e.update(hafen=el['tags'].get('name', el['tags'].get('man_made', el['tags'].get('leisure', 'harbour'))),
                     hafen_lat='%.4f' % hp[0], hafen_lon='%.4f' % hp[1])
        # GeoNames-Einwohner haengen oft am Verwaltungsbezirk (Barangay, Tambon): Doerfer/Weiler nur mit Hafen (Oliver 12.11.)
        if e.get('osm_typ') in ('village', 'hamlet', 'isolated_dwelling', 'locality') and not e.get('hafen'):
            e['urteil'] = 'dorf ohne hafen'
            zeilen.append(e)
            continue
        # Urteil: Referenzen, sonst Einigkeit FES/TPXO10
        a, b = math.radians(mp[0]), math.radians(mp[1])
        x = np.sin((fa - a) / 2) ** 2 + np.cos(a) * np.cos(fa) * np.sin((fo - b) / 2) ** 2
        er = fe[6371 * 2 * np.arcsin(np.sqrt(x)) <= LW.REF_KM]
        w, _dk = T.konstanten('10', *mp)
        if w and 'M2' in w:
            tz_ = {k: cmath.rect(w[k][0], math.radians(w[k][1])) for k in LW.K if k in w}
            cs = [k for k in LW.K if k in tz_ and k in fv]
            tot = sum(abs(fv[k]) for k in cs)
            e['fes_tpxo10_pct'] = '%.1f' % (100 * math.sqrt(sum(abs(tz_[k] - fv[k]) ** 2 for k in cs) / 2) / max(0.15, tot))
        e['refs'] = len(er)
        e['fes_median_pct'] = '%.1f' % float(np.median(er)) if len(er) else ''
        einig = e.get('fes_tpxo10_pct') and float(e['fes_tpxo10_pct']) < EINIG
        if len(er) >= 2 and np.median(er) < LW.GUT and er.max() < LW.SCHLECHT:
            e['urteil'] = 'gut'
        elif len(er) == 1 and er[0] < LW.GUT:
            e['urteil'] = 'einzeln'
        elif len(er) == 0 and einig:
            e['urteil'] = 'modelle_einig'
        else:
            e['urteil'] = 'unsicher'
        zeilen.append(e)
        if n % 100 == 0:
            print('  %d Kandidaten geprueft' % n, flush=True)
    json.dump(cache, open(CACHE, 'w'))
    feld = ['land', 'cc', 'region', 'name', 'osm_name', 'osm_typ', 'einwohner', 'urteil', 'lat', 'lon', 'gn_lat', 'gn_lon', 'kueste_km',
            'naechster_satz', 'naechster_km', 'springhub_m', 'refs', 'fes_median_pct', 'fes_tpxo10_pct', 'hafen', 'hafen_lat',
            'hafen_lon', 'tz']
    zeilen.sort(key=lambda z: (z['urteil'], z['land'], -z['einwohner']))
    with open(AUS, 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=feld)
        w.writeheader()
        for z in zeilen:
            w.writerow({k: z.get(k, '') for k in feld})
    print(collections.Counter(z['urteil'] for z in zeilen))
    print('->', os.path.relpath(AUS, ROOT))


if __name__ == '__main__':
    main(sys.argv[1:])
