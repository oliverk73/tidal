#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Persistenter Override-Layer fuer die NOAA-Band-Generatoren.

Problem: Die Web-Frontend-App schreibt manuelle Koordinaten-/Namens-Korrekturen via
update_coords_in_txt()/update_station_name() DIREKT in die generierte harmonics_*.txt.
Ein Rebuild aus dem Roh-Parse wuerde diese ueberschreiben.

Loesung (Auto-Capture):
  Vor jedem Rebuild wird die bestehende OUT-.txt gelesen und je Station (Key = NOAA-Nummer
  bzw. uid) mit dem Wert verglichen, den der Generator OHNE neue Overrides erzeugen wuerde
  (raw-Parse-Koordinate / raw-Name). Weicht die .txt ab, ist das eine manuelle Korrektur ->
  sie wird in eine git-getrackte JSON gesichert und beim Schreiben IMMER zuletzt angewandt.

Die Override-JSON liegt in harmonics/ (getrackt, NICHT in help/), damit Korrekturen
Rebuilds, Loeschungen und Crashes ueberleben.
"""
import os, re, json

HARM = os.path.expanduser('~/harmonics')
EPS = 0.0008   # ~90 m: groesser als 4-Dezimal-Rundung, kleiner als jede echte Korrektur

def _path(band):
    return f'{HARM}/overrides_{band}.json'

def load(band):
    p = _path(band)
    if os.path.exists(p):
        return json.load(open(p, encoding='utf-8'))
    return {}

def save(band, ov):
    json.dump(ov, open(_path(band), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=0, sort_keys=True)

def _parse_existing(out_path):
    """Liest die bestehende OUT-.txt: Key(NOAA-Nr aus '# noaa_number:') -> (lat, lon, name).
    Key wird aus dem '# noaa_number:'-Kommentar gebildet; bei Mehr-Band-Dateien (amtt) kann
    der Aufrufer stattdessen per (vol,no) keyen -- hier reicht die Nummer, weil je Band/Datei
    eindeutig."""
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
        if ln and not ln.startswith('#') and i+1 < len(L) and mer.match(L[i+1]):
            if no is not None and lat is not None and lon is not None:
                res[str(no)] = (lat, lon, ln.strip())
            no = lat = lon = None
    return res

def capture(band, out_path, raw_by_key):
    """Vergleicht bestehende OUT-.txt mit raw_by_key {key: (raw_lat, raw_lon, raw_name)} und
    erweitert die Override-JSON um neue manuelle Abweichungen. raw_by_key MUSS die Koordinate
    sein, die der Generator OHNE Overrides erzeugen wuerde (also Roh-Parse). Gibt das
    aktualisierte Override-Dict zurueck."""
    ov = load(band)
    existing = _parse_existing(out_path)
    changed = 0
    for key, (elat, elon, ename) in existing.items():
        raw = raw_by_key.get(key)
        if not raw:
            continue
        rlat, rlon, rname = raw
        entry = ov.get(key, {})
        # Koordinate: .txt weicht vom Roh-Parse ab UND ist nicht schon als Override bekannt
        if abs(elat - rlat) > EPS or abs(elon - rlon) > EPS:
            if entry.get('lat') != round(elat, 4) or entry.get('lon') != round(elon, 4):
                entry['lat'] = round(elat, 4); entry['lon'] = round(elon, 4)
                entry.setdefault('_why', 'frontend coord edit (auto-captured)')
                changed += 1
        if entry:
            ov[key] = entry
    if changed:
        save(band, ov)
        print(f'[overrides:{band}] {changed} manuelle Koordinaten-Korrektur(en) gesichert -> {_path(band)}')
    return ov

def apply_coord(ov, key, lat, lon):
    """Gibt (lat, lon) zurueck, ueberschrieben durch Override falls vorhanden."""
    e = ov.get(str(key))
    if e and 'lat' in e and 'lon' in e:
        return e['lat'], e['lon']
    return lat, lon
