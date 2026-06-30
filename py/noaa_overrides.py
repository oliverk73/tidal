#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Persistenter Override-Layer fuer die NOAA-Band-Generatoren (Koordinaten UND Namen).

Problem: Die Web-Frontend-App schreibt manuelle Koordinaten-Korrekturen (update_coords_in_txt)
und Namens-Korrekturen (update_station_name) DIREKT in die generierte harmonics_*.txt.
Ein Rebuild aus dem Roh-Parse wuerde diese ueberschreiben.

Loesung (Mirror-Semantik): Vor jedem Rebuild wird die bestehende OUT-.txt gelesen. Je Station
(Key = NOAA-Nummer bzw. uid) spiegelt der Override die AKTUELLE Abweichung der .txt:
  - Koordinate weicht vom Roh-Parse ab        -> Override speichert .txt-Koordinate
  - Name weicht vom generierten Namen ab      -> Override speichert .txt-Namen
  - keine Abweichung mehr (Revert)            -> Override-Feld wird geloescht
Beim Schreiben werden Overrides IMMER zuletzt angewandt -> Frontend-Edits ueberleben jeden
Rebuild, und ein Revert im Frontend wird ebenfalls korrekt uebernommen.

Override-JSON liegt in harmonics/ (git-getrackt), damit Korrekturen Rebuilds/Crashes ueberleben.
"""
import os, re, json

HARM = os.path.expanduser('~/harmonics')
EPS = 0.0008   # ~90 m: groesser als 4-Dezimal-Rundung, kleiner als jede echte Korrektur

def _path(band):
    return f'{HARM}/overrides_{band}.json'

def load(band):
    p = _path(band)
    return json.load(open(p, encoding='utf-8')) if os.path.exists(p) else {}

def save(band, ov):
    # leere Eintraege entfernen, damit die Datei sauber bleibt
    ov = {k: v for k, v in ov.items() if v}
    p = _path(band)
    if ov:
        json.dump(ov, open(p, 'w', encoding='utf-8'), ensure_ascii=False, indent=0, sort_keys=True)
    elif os.path.exists(p):
        os.remove(p)

def parse_existing(out_path):
    """Liest die bestehende OUT-.txt: Key (aus '# noaa_uid:' bzw. '# noaa_number:') ->
    (lat, lon, name)."""
    res = {}
    if not os.path.exists(out_path):
        return res
    L = open(out_path, encoding='iso-8859-1').read().split('\n')
    mer = re.compile(r'^[+-]\d\d:\d\d :')
    no = lat = lon = None
    for i, ln in enumerate(L):
        m = re.match(r'# noaa_uid:\s*(\S+)', ln)
        if m: no = m.group(1)
        elif re.match(r'# noaa_number:\s*(\S+)', ln): no = re.match(r'# noaa_number:\s*(\S+)', ln).group(1)
        m = re.match(r'# !latitude:\s*([\-\d.]+)', ln)
        if m: lat = float(m.group(1))
        m = re.match(r'# !longitude:\s*([\-\d.]+)', ln)
        if m: lon = float(m.group(1))
        if ln and not ln.startswith('#') and i + 1 < len(L) and mer.match(L[i + 1]):
            if no is not None and lat is not None and lon is not None:
                res[str(no)] = (lat, lon, ln.strip())
            no = lat = lon = None
    return res

def capture_coords(ov, existing, raw_by_key):
    """Spiegelt manuelle Koordinaten-Abweichungen (.txt vs Roh-Parse) in ov. raw_by_key MUSS
    die Koordinate sein, die der Generator OHNE Overrides erzeugen wuerde (Roh-Parse incl.
    statischer COORD_OVERRIDE). Mutiert ov in-place; gibt Anzahl Captures zurueck."""
    n = 0
    for key, (elat, elon, ename) in existing.items():
        raw = raw_by_key.get(key)
        if not raw:
            continue
        rlat, rlon, _ = raw
        e = ov.get(key, {})
        deviates = abs(elat - rlat) > EPS or abs(elon - rlon) > EPS
        if deviates:
            if e.get('lat') != round(elat, 4) or e.get('lon') != round(elon, 4):
                e['lat'] = round(elat, 4); e['lon'] = round(elon, 4)
                e['_why'] = 'frontend coord edit (auto-captured)'
                n += 1
        elif 'lat' in e:  # Revert auf Roh-Parse -> Override entfernen
            e.pop('lat', None); e.pop('lon', None); e.pop('_why', None); n += 1
        ov[key] = e
    return n

def apply_coord(ov, key, lat, lon):
    e = ov.get(str(key))
    if e and 'lat' in e and 'lon' in e:
        return e['lat'], e['lon']
    return lat, lon

def resolve_name(ov, key, would_be, existing):
    """Spiegelt manuelle Namens-Abweichungen (.txt vs generierter Name) und gibt den final zu
    schreibenden Namen zurueck. Mutiert ov in-place. `existing` = parse_existing-Dict."""
    key = str(key)
    e = ov.get(key, {})
    ex_name = existing.get(key, (None, None, None))[2]
    if ex_name and ex_name != would_be:
        if e.get('name') != ex_name:
            e['name'] = ex_name
            e['_why_name'] = 'frontend name edit (auto-captured)'
        ov[key] = e
        return ex_name
    # keine Abweichung (oder Revert auf generierten Namen) -> evtl. Namens-Override loeschen
    if 'name' in e:
        e.pop('name', None); e.pop('_why_name', None)
        ov[key] = e
    return e.get('name', would_be)
