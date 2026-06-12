#!/usr/bin/env python3
"""BIG Model Pasut 2024 (srgi.big.go.id) an einem Punkt abfragen.

Liefert 9 Konstituenten (M2,S2,N2,K2,K1,O1,P1,M4,MS4) mit Amplitude+Phase
plus Niveaus (HAT/MHWS/MSL/MLWS/LAT relativ MSL) aus dem amtlichen
indonesischen Gezeitenmodell (Badan Informasi Geospasial).

Quellen je Punkt:
- POST api/pasutv2/getvalue selected=amplitudo_all  (8 Amplituden, HTML)
- POST api/pasutv2/getvalue selected=msl            (HAT/MHWS/MSL/MLWS/LAT)
- WMS GetFeatureInfo pasut_raster:<c>_phase_2024    (Phasen, Grad)
- WMS GetFeatureInfo pasut_raster:{m4,ms4}_amplitude_2024
Q1: nur Amplitude verfuegbar (kein Phasenraster) -> ausgelassen.
Phasenkonvention: gegen Messfits verifizieren (siehe Vergleich sema)!

Usage: python3 py/big_model_pasut.py LAT LON [NAME]
"""
from __future__ import annotations
import json
import re
import ssl
import sys
import urllib.parse
import urllib.request

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

BASE = 'https://srgi.big.go.id'
PHASE_CONSTS = ['m2', 's2', 'n2', 'k2', 'k1', 'o1', 'p1', 'm4', 'ms4']


def _post(url, data):
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(url, data=body, headers={
        'User-Agent': 'Mozilla/5.0', 'X-Requested-With': 'XMLHttpRequest'})
    with urllib.request.urlopen(req, timeout=60, context=CTX) as r:
        return r.read().decode()


def _wms_value(layer, lat, lon):
    bbox = f'{lon-0.1},{lat-0.1},{lon+0.1},{lat+0.1}'
    url = (f'{BASE}/spatial_service/pasut_raster/wms?SERVICE=WMS&VERSION=1.1.1'
           f'&REQUEST=GetFeatureInfo&LAYERS=pasut_raster:{layer}'
           f'&QUERY_LAYERS=pasut_raster:{layer}&SRS=EPSG:4326&BBOX={bbox}'
           f'&WIDTH=101&HEIGHT=101&X=50&Y=50&INFO_FORMAT=application/json')
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=60, context=CTX) as r:
        d = json.loads(r.read().decode())
    feats = d.get('features')
    if not feats:
        return None
    v = feats[0]['properties'].get('GRAY_INDEX')
    # GeoServer nodata
    if v is None or v < -1e6 or v > 1e6:
        return None
    return float(v)


def query_point(lat, lon):
    out = {'lat': lat, 'lon': lon, 'amp': {}, 'phase': {}, 'levels': {}}

    html = _post(f'{BASE}/api/pasutv2/getvalue',
                 {'lat': lat, 'lon': lon, 'selected': 'amplitudo_all', 'byclick': 'false'})
    if html.strip() != 'N/A':
        for c, v in re.findall(r'id="pasut-([a-z0-9]+)">([0-9.eE-]+)<', html):
            out['amp'][c] = float(v)

    html = _post(f'{BASE}/api/pasutv2/getvalue',
                 {'lat': lat, 'lon': lon, 'selected': 'msl', 'byclick': 'false'})
    if html.strip() != 'N/A':
        for k, v in re.findall(r'id="pasut-([a-z]+)">([0-9.eE-]+)<', html):
            out['levels'][k] = float(v)

    for c in PHASE_CONSTS:
        v = _wms_value(f'{c}_phase_2024', lat, lon)
        if v is not None:
            out['phase'][c] = v % 360.0
    for c in ('m4', 'ms4'):
        if c not in out['amp']:
            v = _wms_value(f'{c}_amplitude_2024', lat, lon)
            if v is not None:
                out['amp'][c] = v
    return out


def main():
    lat, lon = float(sys.argv[1]), float(sys.argv[2])
    name = sys.argv[3] if len(sys.argv) > 3 else f'{lat},{lon}'
    r = query_point(lat, lon)
    print(f'# {name}')
    print(f"Niveaus (rel. MSL): {r['levels']}")
    print(f"{'const':6s} {'Amp[m]':>8s} {'Phase[deg]':>10s}")
    for c in ['m2', 's2', 'n2', 'k2', 'k1', 'o1', 'p1', 'q1', 'm4', 'ms4']:
        a = r['amp'].get(c)
        g = r['phase'].get(c)
        if a is not None or g is not None:
            print(f'{c.upper():6s} {a if a is not None else float("nan"):8.4f} '
                  f'{g if g is not None else float("nan"):10.2f}')


if __name__ == '__main__':
    main()
