#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Messstationen direkt an Surf-/Kitespots finden (25.11.2026).

Spots: OpenStreetMap sport=kitesurfing|windsurfing (Overpass) + unsere Reviere.
Stationen: offene Netze MIT Archiv (sonst taugt die Station nicht zum Lernen):
  meteofrance  Donnees climatologiques de base horaires (data.gouv.fr, Etalab), stuendlich
  dwd          DWD 10-min-Wind (opendata.dwd.de, frei)
  knmi         KNMI uurgegevens (frei)
  dmi          DMI metObs (opendataapi.dmi.dk, frei)
  coops        NOAA CO-OPS Met (Wind an Pegeln, 6 min)
  ndbc         NOAA NDBC (Bojen/C-MAN)
  geosphere    GeoSphere Austria klima-v2-10min
  meteoschweiz SwissMetNet
  pioupiou     OpenWindMap/Pioupiou (Archiv-API)
  meteotrentino, (weitere werden ergaenzt)
Stationskataloge in quellen/thermik/spotsuche/stationen_<netz>.csv (netz,id,name,lat,lon,alt[,sommer_h,winter_h]).

    venv/bin/python py/spotsuche.py [max_km=3]
      -> harmonics/help/spotsuche_treffer.csv  (je OSM-Spot die naechste Station je Netz <= max_km)
"""
import json
import math
import os
import re
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
S = os.path.join(ROOT, 'quellen', 'thermik', 'spotsuche')
AUS = os.path.join(ROOT, 'harmonics', 'help', 'spotsuche_treffer.csv')


def kataloge():
    k = []
    p = os.path.join(S, 'stationen_meteofrance.csv')
    if os.path.exists(p):
        k.append(pd.read_csv(p, dtype={'id': str}))
    # DWD 10-min-Wind: nur aktive Stationen (bis_datum aktuell)
    z = []
    for l in open(os.path.join(S, 'dwd_10min_wind.txt'), encoding='latin1').readlines()[2:]:
        f = l.split()
        if len(f) > 6 and f[2] >= '2026':
            name = ' '.join(f[6:-2])
            z.append(('dwd', f[0], name, float(f[4]), float(f[5]), float(f[3])))
    k.append(pd.DataFrame(z, columns=['netz', 'id', 'name', 'lat', 'lon', 'alt']))
    z = []
    for l in open(os.path.join(S, 'knmi_hdr.txt')):
        m = re.match(r'#\s+(\d{3})\s+([\d.]+)\s+([\d.]+)\s+(-?[\d.]+)\s+(.+)', l)
        if m:
            z.append(('knmi', m.group(1), m.group(5).strip(), float(m.group(3)), float(m.group(2)), float(m.group(4))))
    k.append(pd.DataFrame(z, columns=['netz', 'id', 'name', 'lat', 'lon', 'alt']))
    z = []
    for f in json.load(open(os.path.join(S, 'dmi_st.json')))['features']:
        p_ = f['properties']
        if p_.get('status') == 'Active' and 'wind_speed' in (p_.get('parameterId') or []) and f.get('geometry'):
            lo, la = f['geometry']['coordinates'][:2]
            z.append(('dmi', p_['stationId'], p_['name'], la, lo, p_.get('stationHeight')))
    k.append(pd.DataFrame(z, columns=['netz', 'id', 'name', 'lat', 'lon', 'alt']))
    z = [('coops', s['id'], s['name'], s['lat'], s['lng'], None)
         for s in json.load(open(os.path.join(S, 'coops_met.json')))['stations']]
    k.append(pd.DataFrame(z, columns=['netz', 'id', 'name', 'lat', 'lon', 'alt']))
    gs = json.load(open(os.path.join(ROOT, 'quellen/thermik/geosphere/meta_10min.json')))['stations']
    k.append(pd.DataFrame([('geosphere', str(s['id']), s['name'], s['lat'], s['lon'], s['altitude'])
                           for s in gs if s['is_active'] and s['type'] == 'INDIVIDUAL'],
                          columns=['netz', 'id', 'name', 'lat', 'lon', 'alt']))
    m = pd.read_csv(os.path.join(S, 'smn_meta.csv'), sep=';', encoding='latin1')
    k.append(pd.DataFrame({'netz': 'meteoschweiz', 'id': m['station_abbr'], 'name': m['station_name'],
                           'lat': m['station_coordinates_wgs84_lat'], 'lon': m['station_coordinates_wgs84_lon'],
                           'alt': m['station_height_masl']}))
    pp = json.load(open(os.path.join(ROOT, 'quellen/thermik/pioupiou/live_all.json')))['data']
    k.append(pd.DataFrame([('pioupiou', str(s['id']), (s['meta'].get('name') or '').strip(), s['location']['latitude'],
                            s['location']['longitude'], None) for s in pp
                           if (s.get('location') or {}).get('latitude') is not None
                           and ((s.get('measurements') or {}).get('date') or '') >= '2026-10'],
                          columns=['netz', 'id', 'name', 'lat', 'lon', 'alt']))
    for extra in ('stationen_weitere.csv',):                      # von Hand/anderen Skripten ergaenzt
        p = os.path.join(S, extra)
        if os.path.exists(p):
            k.append(pd.read_csv(p, dtype={'id': str}))
    return pd.concat(k, ignore_index=True)


def osm_spots():
    out = []
    for e in json.load(open(os.path.join(S, 'osm_spots.json')))['elements']:
        la = e.get('lat') or e.get('center', {}).get('lat')
        lo = e.get('lon') or e.get('center', {}).get('lon')
        t = e.get('tags', {})
        out.append(dict(spot=t.get('name') or t.get('name:en') or '(ohne Namen)', sport=t.get('sport'), lat=la, lon=lo,
                        osm='%s/%s' % (e['type'], e['id'])))
    return pd.DataFrame(out)


def km(la1, lo1, la2, lo2):
    p = math.pi / 180
    a = np.sin((la2 - la1) * p / 2) ** 2 + np.cos(la1 * p) * np.cos(la2 * p) * np.sin((lo2 - lo1) * p / 2) ** 2
    return 12742 * np.arcsin(np.sqrt(a))


def main(argv):
    maxkm = float(argv[0]) if argv else 3.0
    st = kataloge()
    st.to_csv(os.path.join(S, 'stationen_alle.csv'), index=False)
    sp = osm_spots()
    z = []
    for _, s in sp.iterrows():
        d = km(s['lat'], s['lon'], st['lat'].values, st['lon'].values)
        for i in np.where(d <= maxkm)[0]:
            r = st.iloc[i]
            z.append(dict(spot=s['spot'], sport=s['sport'], spot_lat=round(s['lat'], 5), spot_lon=round(s['lon'], 5),
                          osm=s['osm'], netz=r['netz'], station_id=r['id'], station=r['name'], km=round(float(d[i]), 2),
                          alt=r.get('alt'), sommer_h=r.get('sommer_h'), winter_h=r.get('winter_h')))
    t = pd.DataFrame(z).sort_values(['spot', 'km'])
    t.to_csv(AUS, index=False)
    print('%d Stationen in %d Netzen; %d OSM-Spots; %d Spots mit Station <= %.0f km (%d Stationen)'
          % (len(st), st['netz'].nunique(), len(sp), t['osm'].nunique(), maxkm, t[['netz', 'station_id']].drop_duplicates().shape[0]))
    print(t.groupby('netz')['osm'].nunique().sort_values(ascending=False).to_string())
    print('->', os.path.relpath(AUS, ROOT))


if __name__ == '__main__':
    main(sys.argv[1:])
