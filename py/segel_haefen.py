#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Liegeplaetze fuer das Segel-Routing (22.11.2026): Uebernachten bei „Nachtfahrt vermeiden“ und Mehrtagestoerns.

Daten: OSM/OpenSeaMap, Overpass 22.11.2026 (je Abfrage einzeln, die Sammelabfrage lief in den Timeout):
  nwr[leisure=marina]; nwr[seamark:type=harbour]; nwr[seamark:type=anchorage]; out center tags
-> quellen/routing/haefen_osm.json  [[lat, lon, name, art], ...]  art = marina | hafen | anker
Handels-/Marinehaefen ohne Marina-/Fischerei-Kategorie (container, bulk, tanker, naval, roro, cargo, shipyard ...)
fallen weg: dort darf eine Yacht nicht festmachen. Punkte naeher als 300 m werden zusammengefasst (Marina vor Hafen
vor Ankerplatz, benannt vor unbenannt).

    aufbauen(roh_json_dateien)            -> schreibt DATEI
    liste(s, n, w, e)                      -> [(lat, lon, name, art)]
"""
import json
import math
import os
import sys

import numpy as np

BASIS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATEI = os.path.join(BASIS, "quellen", "routing", "haefen_osm.json")
HANDEL = ("container", "bulk", "tanker", "naval", "roro", "cargo", "shipyard", "offshore", "port_support", "service_repair",
          "seaplane", "timber", "hydrocarbon", "lng", "oil")
RANG = {"marina": 0, "hafen": 1, "anker": 2}
_D = {}


def _art(t):
    if t.get("leisure") == "marina":
        return "marina"
    st = t.get("seamark:type")
    if st == "anchorage":
        return "anker"
    if st == "harbour":
        kat = t.get("seamark:harbour:category", "").lower()
        if "marina" in kat:
            return "marina"
        if "fishing" in kat:
            return "hafen"
        if any(x in kat for x in HANDEL):
            return None
        return "hafen"
    return None


def aufbauen(dateien):
    roh = []
    for f in dateien:
        for e in json.load(open(f))["elements"]:
            t = e.get("tags", {})
            art = _art(t)
            if art is None:
                continue
            if e["type"] == "node":
                la, lo = e.get("lat"), e.get("lon")
            else:
                c = e.get("center") or {}
                la, lo = c.get("lat"), c.get("lon")
            if la is None:
                continue
            name = (t.get("name") or t.get("seamark:name") or t.get("name:en") or "").strip()
            roh.append((round(la, 5), round(lo, 5), name, art))
    # zusammenfassen (300 m), bester zuerst
    roh.sort(key=lambda r: (RANG[r[3]], r[2] == ""))
    behalten = []
    zellen = {}
    for r in roh:
        ci, cj = int(r[0] / 0.01), int(r[1] / 0.01)
        nah = False
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                for q in zellen.get((ci + di, cj + dj), ()):
                    if 111.2 * math.hypot(q[0] - r[0], (q[1] - r[1]) * math.cos(math.radians(r[0]))) < 0.3:
                        nah = True
                        break
        if nah:
            continue
        behalten.append(list(r))
        zellen.setdefault((ci, cj), []).append(r)
    json.dump(behalten, open(DATEI, "w"), ensure_ascii=False, separators=(",", ":"))
    return len(roh), len(behalten)


def _alle():
    if "a" not in _D:
        a = json.load(open(DATEI)) if os.path.exists(DATEI) else []
        _D["a"] = a
        _D["la"] = np.array([x[0] for x in a]) if a else np.zeros(0)
        _D["lo"] = np.array([x[1] for x in a]) if a else np.zeros(0)
    return _D


def liste(s, n, w, e):
    D = _alle()
    m = (D["la"] >= s) & (D["la"] <= n) & (D["lo"] >= w) & (D["lo"] <= e)
    return [tuple(D["a"][i]) for i in np.nonzero(m)[0]]


if __name__ == "__main__":
    print("roh %d, behalten %d -> %s" % (aufbauen(sys.argv[1:]) + (DATEI,)))
