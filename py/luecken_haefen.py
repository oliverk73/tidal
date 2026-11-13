#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Insel- und Hafen-Durchgang der Lueckensuche (Oliver 12./13.11.2026: "vor allem bei Inseln ... Handels-,
Industrie- und Faehrhafen von Bedeutung"; Notiz haefen-vor-orten).

Quelle: OSM weltweit (tide_tables/catalogues/osm_haefen/*.json, Overpass "out center tags"):
  ferry_terminal.json    amenity=ferry_terminal
  industrial_port.json   industrial=port (Handels-/Industriehafen-Flaechen)
  seamark_harbour.json   seamark:type=harbour (Kategorie aus seamark:harbour:category; Marinas/Fischerei raus)
Der NGA World Port Index blockt Skript-Abrufe (13.11.2026), daher nur OSM.

Kandidat, wenn
  * benannt, |Breite| <= 72, Wasser (global_land_mask) in 2 km,
  * kein Satz in LUECKE_KM (Faehre/Handel) -- grosse Orte hat py/luecken_schlau.py schon abgedeckt,
  * Springhub (FES M2+S2) >= MIN_HUB m (Notiz suche-nur-bei-signifikanter-tide),
  * OSM-Kueste (osm_land) hoechstens KUESTE_KM entfernt: Binnenfaehren auf Seen/Fluessen fallen raus,
    Tidefluesse bleiben (die OSM-Kueste reicht bis zur Tidegrenze) und werden als 'fluss?' markiert.
Je CLUSTER_KM bleibt der wichtigste Hafen: Handelshafen > Autofaehre > Faehre; bei Gleichstand der mit Wikidata.
Urteil wie luecken_schlau.py (Mess-/Amtsreferenzen, sonst Einigkeit FES <-> TPXO10).

Schreibt nur die Liste harmonics/help/luecken_haefen.csv. Anlegen nach Olivers Auswahl mit
py/fes_neu_geeicht.py --welt <auswahl.csv> --exakt.

Usage: venv/bin/python py/luecken_haefen.py
"""
import cmath
import collections
import csv
import json
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import health_check as H                                           # noqa: E402
import luecken_fes_welt as LW                                      # noqa: E402
import osm_land                                                    # noqa: E402
import tpxo as T                                                   # noqa: E402

ROOT = LW.ROOT
QUELLE = os.path.join(ROOT, 'tide_tables/catalogues/osm_haefen')
AUS = os.path.join(ROOT, 'harmonics/help/luecken_haefen.csv')
LUECKE_KM, CLUSTER_KM, KUESTE_KM, MIN_HUB, EINIG, ENG_PCT = 10.0, 8.0, 1.0, 1.0, 5.0, 25.0
HANDEL = {'commercial', 'container', 'bulk', 'tanker', 'roro', 'industrial', 'naval', 'ferry', 'ferry_terminal',
          'cargo', 'passenger', 'port', 'harbour_master', 'shipyard'}
RANG = {'handelshafen': 3, 'autofaehre': 2, 'faehre': 1}


def kandidaten():
    out = []

    def lade(datei):
        p = os.path.join(QUELLE, datei)
        return json.load(open(p))['elements'] if os.path.exists(p) else []

    def pos(e):
        return (e['lat'], e['lon']) if 'lat' in e else (e['center']['lat'], e['center']['lon'])

    for e in lade('ferry_terminal.json'):
        t = e.get('tags', {})
        if 'name' in t:
            art = 'autofaehre' if t.get('cargo') in ('vehicle', 'vehicles', 'car', 'cars') or t.get('motor_vehicle') == 'yes' else 'faehre'
            out.append((*pos(e), t['name'], art, t, 'osm:%s/%d' % (e['type'], e['id'])))
    for e in lade('industrial_port.json'):
        t = e.get('tags', {})
        if 'name' in t and ('center' in e or 'lat' in e):
            out.append((*pos(e), t['name'], 'handelshafen', t, 'osm:%s/%d' % (e['type'], e['id'])))
    for e in lade('seamark_harbour.json'):
        t = e.get('tags', {})
        kat = set(t.get('seamark:harbour:category', '').split(';'))
        name = t.get('name') or t.get('seamark:name')
        if name and kat & HANDEL:
            art = 'faehre' if kat & {'ferry', 'ferry_terminal', 'passenger'} and not kat & {'commercial', 'container', 'bulk', 'tanker', 'roro', 'industrial'} else 'handelshafen'
            out.append((*pos(e), name, art, t, 'osm:%s/%d' % (e['type'], e['id'])))
    return out


def main(argv):
    K = kandidaten()
    print('%d benannte Haefen/Faehrterminals' % len(K), flush=True)
    recs = [r for r in H.load_records() if r['lat'] is not None and not r['current']]
    rl, ro = np.radians([r['lat'] for r in recs]), np.radians([r['lon'] for r in recs])

    def naechster(la, lo):
        a, b = math.radians(la), math.radians(lo)
        x = np.sin((rl - a) / 2) ** 2 + np.cos(a) * np.cos(rl) * np.sin((ro - b) / 2) ** 2
        i = int(x.argmin())
        return float(6371 * 2 * np.arcsin(np.sqrt(x[i]))), recs[i]['name']

    import netCDF4 as nc
    F = {k: nc.Dataset(os.path.join(LW.FES_DIR, '%s_fes2022.nc' % k.lower())) for k in LW.K}

    def fes(la, lo):
        out = {}
        for k in LW.K:
            a, g = LW.sample(F[k], la, lo)
            if a:
                out[k] = cmath.rect(a, math.radians(g))
        return out

    # 1. billige Filter: Breite, Luecke, Wasser, Hub
    stufe = []
    for la, lo, name, art, t, oid in K:
        if abs(la) > 72:
            continue
        d, s = naechster(la, lo)
        if d <= LUECKE_KM:
            continue
        mp = LW.meerpunkt(la, lo)
        if not mp:
            continue
        fv = fes(*mp)
        if 'M2' not in fv:
            continue
        hub = 2 * (abs(fv['M2']) + abs(fv.get('S2', 0)))
        if hub < MIN_HUB:
            continue
        stufe.append(dict(name=name, art=art, lat=la, lon=lo, mp=mp, fv=fv, hub=hub, naechster_satz=s, naechster_km=d,
                          wikidata=t.get('wikidata', ''), osm=oid, betreiber=t.get('operator', '')))
    print('%d nach Luecke/Wasser/Hub' % len(stufe), flush=True)
    # 2. Cluster: je CLUSTER_KM der wichtigste
    stufe.sort(key=lambda z: (-RANG[z['art']], -bool(z['wikidata']), -z['naechster_km']))
    wahl = []
    for z in stufe:
        if all(H.km({'lat': z['lat'], 'lon': z['lon']}, {'lat': w['lat'], 'lon': w['lon']}) > CLUSTER_KM for w in wahl):
            wahl.append(z)
    print('%d nach Cluster %.0f km' % (len(wahl), CLUSTER_KM), flush=True)
    # 3. OSM-Kueste (Binnenfaehren raus)
    L = osm_land.Land([(z['lat'], z['lon']) for z in wahl])
    rest = []
    for z in wahl:
        kk = 0.0 if not L.ist_land(z['lat'], z['lon']) else L.kueste_km(z['lat'], z['lon'], rmax=5)
        if kk > KUESTE_KM:
            continue
        z['kueste_km'] = kk
        # Fluss/Kanal-Verdacht: Wasseranteil auf Ringen 3 und 5 km um den Hafen (Hafenbecken hinter Molen sind eng,
        # aber draussen offen; ein Fluss bleibt auf beiden Ringen ueberwiegend Land)
        ring = [(z['lat'] + r / 111.2 * math.cos(math.radians(az)), z['lon'] + r / (111.2 * math.cos(math.radians(z['lat']))) * math.sin(math.radians(az)))
                for r in (3.0, 5.0) for az in range(0, 360, 15)]
        z['wasser_pct'] = 100.0 * sum(not L.ist_land(*q) for q in ring) / len(ring)     # Spalte: Wasseranteil %
        if z['wasser_pct'] < ENG_PCT:
            z['urteil_zusatz'] = 'eng'
        rest.append(z)
    print('%d an der OSM-Kueste' % len(rest), flush=True)
    # 4. Urteil
    refs = []
    for r in recs:
        if 'fes2022' in r['file'] or 'secondary' in r['file'] or not LW.REF_DATEI.search(os.path.basename(r['file'])):
            continue
        fv = fes(r['lat'], r['lon'])
        if 'M2' not in fv or 'K1' not in fv or r['tot'] < 0.15:
            continue
        zz = {k: cmath.rect(abs(r['z'][k]), -cmath.phase(r['z'][k])) for k in LW.K}
        cs = [k for k in LW.K if k in fv]
        refs.append((r['lat'], r['lon'], 100 * math.sqrt(sum(abs(zz[k] - fv[k]) ** 2 for k in cs) / 2) / r['tot']))
    fa, fo, fe = np.radians([x[0] for x in refs]), np.radians([x[1] for x in refs]), np.array([x[2] for x in refs])
    for z in rest:
        mp, fv = z['mp'], z['fv']
        a, b = math.radians(mp[0]), math.radians(mp[1])
        x = np.sin((fa - a) / 2) ** 2 + np.cos(a) * np.cos(fa) * np.sin((fo - b) / 2) ** 2
        er = fe[6371 * 2 * np.arcsin(np.sqrt(x)) <= LW.REF_KM]
        w, _dk = T.konstanten('10', *mp)
        if w and 'M2' in w:
            tz_ = {k: cmath.rect(w[k][0], math.radians(w[k][1])) for k in LW.K if k in w}
            cs = [k for k in LW.K if k in tz_ and k in fv]
            z['fes_tpxo10_pct'] = 100 * math.sqrt(sum(abs(tz_[k] - fv[k]) ** 2 for k in cs) / 2) / max(0.15, sum(abs(fv[k]) for k in cs))
        z['refs'] = len(er)
        z['fes_median_pct'] = float(np.median(er)) if len(er) else None
        einig = z.get('fes_tpxo10_pct') is not None and z['fes_tpxo10_pct'] < EINIG
        if len(er) >= 2 and np.median(er) < LW.GUT and er.max() < LW.SCHLECHT:
            z['urteil'] = 'gut'
        elif len(er) == 1 and er[0] < LW.GUT:
            z['urteil'] = 'einzeln'
        elif len(er) == 0 and einig:
            z['urteil'] = 'modelle_einig'
        else:
            z['urteil'] = 'unsicher'
        if z['urteil'] != 'unsicher' and not einig:
            z['urteil'] += ', modelle_uneins'
        if z.get('urteil_zusatz') and z['urteil'] != 'unsicher':
            z['urteil'] += ', ' + z['urteil_zusatz']     # Fluss/Kanal/enge Bucht: FES dort unzuverlaessig
    feld = ['urteil', 'art', 'name', 'lat', 'lon', 'naechster_satz', 'naechster_km', 'springhub_m', 'refs', 'fes_median_pct',
            'fes_tpxo10_pct', 'kueste_km', 'wasser_pct', 'wikidata', 'betreiber', 'osm']
    rest.sort(key=lambda z: (z['urteil'], -RANG[z['art']], -z['naechster_km']))
    with open(AUS, 'w', newline='', encoding='utf-8') as fh:
        wr = csv.DictWriter(fh, fieldnames=feld)
        wr.writeheader()
        for z in rest:
            wr.writerow(dict(urteil=z['urteil'], art=z['art'], name=z['name'], lat='%.5f' % z['lat'], lon='%.5f' % z['lon'],
                             naechster_satz=z['naechster_satz'], naechster_km='%.1f' % z['naechster_km'], springhub_m='%.1f' % z['hub'],
                             refs=z['refs'], fes_median_pct='' if z['fes_median_pct'] is None else '%.1f' % z['fes_median_pct'],
                             fes_tpxo10_pct='%.1f' % z['fes_tpxo10_pct'] if z.get('fes_tpxo10_pct') is not None else '',
                             kueste_km='%.1f' % z['kueste_km'], wasser_pct='%.0f' % z['wasser_pct'], wikidata=z['wikidata'], betreiber=z['betreiber'], osm=z['osm']))
    print(collections.Counter((z['urteil'], z['art']) for z in rest))
    print('->', os.path.relpath(AUS, ROOT))


if __name__ == '__main__':
    main(sys.argv[1:])
