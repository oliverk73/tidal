#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Schifffahrtskanaele fuer das Segel-Routing (23.11.2026, Oliver: Kanalregeln auch fuer Suez, Panama usw.).

Je Kanal: Mittellinie aus OSM (waterway=canal, Name), Regeln fuer Sportboote:
    motor      nur unter Motor (Segeln verboten bzw. im Kanal nicht moeglich)
    max_kn     Hoechstgeschwindigkeit durchs Wasser (kn)
    luecke_km  OSM-Linie hat Luecken (Caledonian: Loch Lochy/Oich/Ness sind Seen) -> freie Enden bis zu dieser
               Entfernung gerade verbinden
    tiefe_m    Solltiefe der Rinne (m, Seekartennull); ersetzt dort EMODnet (zu grob: Korinth-Einfahrten "trocken")
    warte_h    pauschale Zeit fuer Schleusen / Konvoi / Uebernachtung je ganze Durchfahrt; der Router verteilt sie
               auf die Kanallaenge laenge_km (Start/Ziel im Kanal, Teilstrecken, kein Doppelzaehlen bei Wiedereinfahrt)
    nur_tag    Sportboote nur bei Tag (NOK: SeeSchStrO; Schleusen Caledonian/Crinan nur tagsueber) -> nachts im Kanal
               bis zum Morgen liegen (Liegestellen), nachts keine Einfahrt
    hinweis    Anmeldung, Lotse, Sperrzeiten (Text fuer die Routeninfo)
Die Werte sind Richtwerte fuer die Planung (Quellen im Kommentar), keine Revierauskunft.

Die Mittellinie wird als Wasser erzwungen (Panama: Gatunsee ist in den OSM-Landpolygonen Land und kein Flussgebiet),
in einer Zone von ZONE_KM um die Linie gelten die Regeln.

    laden                       Mittellinien von Overpass holen -> quellen/routing/kanaele.json
    raster(s, n, w, e, ny, nx, breite_px) -> (wasser bool, zone int8: 0 = kein Kanal, sonst 1 + Index in KANAELE)
"""
import json
import math
import os
import sys
import time

import numpy as np
from PIL import Image, ImageDraw

BASIS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATEI = os.path.join(BASIS, "quellen", "routing", "kanaele.json")
ZONE_KM = 0.8
ENDE_KM = 1.2          # echte Kanalenden verlaengern (OSM-Linie endet vor dem offenen Wasser, Korinth ~150 m)

# (Kuerzel, Name, Rechteck s, w, n, e, Namensmuster OSM, Regeln)
KANAELE = [
    # SeeSchStrO §§ 42 ff.: Sportboote nur unter Motor, 15 km/h; Schleusen Brunsbuettel/Kiel-Holtenau je ~1 h Wartezeit
    ("nok", "Kiel Canal (Nord-Ostsee-Kanal)", (53.85, 9.10, 54.40, 10.20), "Kiel Canal|Nord-Ostsee",
     dict(motor=True, max_kn=8.1, warte_h=2.0, tiefe_m=11.0, laenge_km=98, nur_tag=True,
          hinweis="Kiel Canal: engine only, max 15 km/h (8.1 kn), locks at Brunsbuettel and Kiel-Holtenau (about 1 h "
                  "each included), daylight only for pleasure craft (night at a canal berth), canal fee.")),
    # Suez: Yachten mit Lotse und Agent, zwei Tage mit Uebernachtung in Ismailia (Noonsite)
    ("suez", "Suez Canal", (29.85, 32.25, 31.30, 32.62), "Suez Canal|السويس",
     dict(motor=True, max_kn=7.5, warte_h=14.0, tiefe_m=20.0, laenge_km=193,
          hinweis="Suez Canal: agent, pilot and booking required; yachts transit in two days with a night stop at "
                  "Ismailia (about 14 h included).")),
    # Panama: Advisor, Linehandler, Buchung; Yachten meist zwei Tage mit Nacht an der Boje im Gatunsee
    ("panama", "Panama Canal", (8.85, -80.0, 9.42, -79.5), "Panama",
     dict(motor=True, max_kn=7.0, warte_h=16.0, tiefe_m=12.8, laenge_km=82,
          hinweis="Panama Canal: booking, advisor and line handlers required; locks and usually a night at a "
                  "mooring in Gatun Lake (about 16 h included). Admeasurement days before.")),
    # Korinth: max 6 kn, Wartezeit je nach Verkehr, Kanal di 06-18 geschlossen (Noonsite, CruisersWiki)
    ("korinth", "Corinth Canal", (37.90, 22.94, 37.96, 23.02), "Corinth|Κορίνθου",
     dict(motor=True, max_kn=6.0, warte_h=1.0, tiefe_m=8.0, laenge_km=6.4,
          hinweis="Corinth Canal: engine only, max 6 kn, call Corinth Canal Control VHF 11 one hour before; "
                  "closed Tuesdays 06:00-18:00 (not modelled), toll.")),
    # Cape Cod: Durchfahrt unter Motor, 10 mph ueber Grund (Coast Pilot / Waterway Guide), starker Strom
    ("capecod", "Cape Cod Canal", (41.72, -70.65, 41.79, -70.48), "Cape Cod",
     dict(motor=True, max_kn=8.7, warte_h=0.0, tiefe_m=9.7, laenge_km=11.3,
          hinweis="Cape Cod Canal: transit under power, max 10 mph (8.7 kn), strong tidal current, no stopping.")),
    # C&D: 33 CFR 162.40(f): Fahrt unter Segeln zwischen Reedy Point und Welch Point verboten
    ("cd", "Chesapeake and Delaware Canal", (39.48, -75.80, 39.60, -75.55), "Chesapeake and Delaware Canal$",
     dict(motor=True, max_kn=None, warte_h=0.0, tiefe_m=10.7, laenge_km=22.5,
          hinweis="Chesapeake and Delaware Canal: no sailing between Reedy Point and Welch Point (33 CFR 162.40).")),
    # Noordzeekanaal: Segeln nur mit sofort einsatzbereitem Motor (Besluit CNB 2024) -> nur Motor angenommen;
    # Schleuse IJmuiden
    ("nzk", "Noordzeekanaal", (52.36, 4.50, 52.45, 4.95), "Noordzeekanaal",
     dict(motor=True, max_kn=None, warte_h=1.0, tiefe_m=15.0, laenge_km=27,
          hinweis="Noordzeekanaal: sailing only with engine running (planned under engine), lock at IJmuiden "
                  "(about 1 h included).")),
    # Caledonian: 29 Schleusen, 5 mph in den Kanalstrecken, Schleusen nur tagsueber -> meist 2-3 Tage
    ("caledonian", "Caledonian Canal", (56.80, -5.15, 57.50, -4.20), "Caledonian",
     dict(motor=True, max_kn=4.3, warte_h=8.0, tiefe_m=4.1, laenge_km=97, luecke_km=40, nur_tag=True,
          hinweis="Caledonian Canal: 29 locks, daytime only, 5 mph in the cuts; usually 2-3 days (about 8 h for "
                  "the locks included, nights at canal berths); planned under engine also on the lochs.")),
    # Crinan: 15 Schleusen, 4 mph
    ("crinan", "Crinan Canal", (56.00, -5.60, 56.10, -5.40), "Crinan",
     dict(motor=True, max_kn=3.5, warte_h=4.0, tiefe_m=2.9, laenge_km=14, nur_tag=True,
          hinweis="Crinan Canal: 15 locks, daytime only, 4 mph (about 4 h for the locks included, nights at canal berths).")),
]
_L = {}


def laden(argv=()):
    import requests
    api = os.environ.get("OVERPASS_API", "https://overpass-api.de/api/interpreter")
    alt = json.load(open(DATEI)) if os.path.exists(DATEI) else {}
    for kurz, name, (s, w, n, e), muster, _ in KANAELE:
        if alt.get(kurz) and "--neu" not in argv:
            continue
        bb = "%s,%s,%s,%s" % (s, w, n, e)
        q = ('[out:json][timeout:90];(way["waterway"="canal"]["name"~"%s"](%s);way["waterway"="canal"]["name:en"~"%s"]'
             '(%s););out geom;' % (muster, bb, muster, bb))
        for versuch in range(8):
            try:
                r = requests.post(api, data={"data": q}, timeout=120, headers={"User-Agent": "tide-research-script"})
                if r.status_code == 200 and r.text.lstrip().startswith("{"):
                    alt[kurz] = [[[round(p["lon"], 6), round(p["lat"], 6)] for p in x["geometry"]]
                                 for x in r.json()["elements"] if x.get("geometry")]
                    print(kurz, len(alt[kurz]), "Linien", flush=True)
                    break
                print(kurz, "HTTP", r.status_code, flush=True)
            except Exception as ex:                                  # noqa: BLE001
                print(kurz, str(ex)[:100], flush=True)
            time.sleep(20)
        json.dump(alt, open(DATEI, "w"), separators=(",", ":"))
        time.sleep(3)


def _linien():
    if "l" not in _L:
        roh = json.load(open(DATEI)) if os.path.exists(DATEI) else {}
        _L["l"] = [[np.asarray(x, float) for x in roh.get(k[0], [])] for k in KANAELE]
    return _L["l"]


def _frei(L):
    zaehl = {}
    for g in L:
        for p in (g[0], g[-1]):
            key = (round(p[0], 5), round(p[1], 5))
            zaehl[key] = zaehl.get(key, 0) + 1
    return [np.asarray(k) for k, v in zaehl.items() if v == 1]


def _luecken(L, max_km):
    """Freie Enden verschiedener Linienzuege (naechste zuerst) gerade verbinden, solange naeher als max_km; die zwei am
    weitesten auseinanderliegenden freien Enden (die echten Kanalenden) bleiben frei."""
    L = list(L)
    key = lambda p: (round(p[0], 5), round(p[1], 5))                 # noqa: E731
    eltern = list(range(len(L)))

    def wurzel(x):
        while eltern[x] != x:
            eltern[x] = eltern[eltern[x]]
            x = eltern[x]
        return x
    an = {}
    for x, g in enumerate(L):
        for p in (g[0], g[-1]):
            an.setdefault(key(p), []).append(x)
    for xs in an.values():
        for y in xs[1:]:
            eltern[wurzel(y)] = wurzel(xs[0])
    frei = [(np.asarray(k), v[0]) for k, v in an.items() if len(v) == 1]
    if len(frei) <= 2:
        return L
    km = lambda a, b: math.hypot((a[0] - b[0]) * 111.2 * math.cos(math.radians(a[1])), (a[1] - b[1]) * 111.2)  # noqa
    ia, ib = max(((x, y) for x in range(len(frei)) for y in range(x + 1, len(frei))),
                 key=lambda xy: km(frei[xy[0]][0], frei[xy[1]][0]))
    rest = [f for z, f in enumerate(frei) if z not in (ia, ib)]
    paare = sorted((km(a[0], b[0]), x, y) for x, a in enumerate(rest) for y, b in enumerate(rest) if x < y)
    benutzt = set()
    for d, x, y in paare:
        if d > max_km or x in benutzt or y in benutzt:
            continue
        rx, ry = wurzel(rest[x][1]), wurzel(rest[y][1])
        if rx == ry:
            continue
        L.append(np.vstack([rest[x][0], rest[y][0]]))
        eltern.append(len(eltern))
        eltern[ry] = rx
        eltern[len(eltern) - 1] = rx
        benutzt |= {x, y}
    return L


def _enden(L):
    """Linien mit verlaengerten echten Enden (Endpunkte, die keine andere Linie beruehrt)."""
    if not L:
        return L
    zaehl = {}
    for g in L:
        for p in (g[0], g[-1]):
            key = (round(p[0], 5), round(p[1], 5))
            zaehl[key] = zaehl.get(key, 0) + 1
    aus = []
    for g in L:
        g = g.copy()
        if len(g) >= 2:
            for a, b in ((0, 1), (-1, -2)):
                if zaehl[(round(g[a][0], 5), round(g[a][1], 5))] == 1:
                    c = math.cos(math.radians(g[a][1]))
                    dx, dy = (g[a][0] - g[b][0]) * c, g[a][1] - g[b][1]
                    lg = math.hypot(dx, dy) * 111.2
                    if lg > 0:
                        neu = g[a] + np.array([dx / c, dy]) / lg * ENDE_KM
                        g = np.vstack([neu[None], g]) if a == 0 else np.vstack([g, neu[None]])
        aus.append(g)
    return aus


def raster(s, n, w, e, ny, nx, breite_px=1, zone_km=None):
    """(wasser, zone): wasser = Mittellinien (breite_px Pixel breit), zone = 1 + Kanalindex im Umkreis ZONE_KM."""
    wasser = np.zeros((ny, nx), bool)
    zone = np.zeros((ny, nx), np.int8)
    sx, sy = nx / (e - w), ny / (n - s)
    km_px = max((n - s) * 111.2 / ny, (e - w) * 111.2 * math.cos(math.radians((s + n) / 2)) / nx)
    zb = max(breite_px, int(round(2 * (zone_km or ZONE_KM) / km_px)) + 1)
    for idx, (kurz, _, (ks, kw, kn, ke), _, _) in enumerate(KANAELE):
        if ks > n or kn < s or kw > e or ke < w:
            continue
        L = _linien()[idx]
        if L and KANAELE[idx][4].get("luecke_km"):
            L = _luecken(L, KANAELE[idx][4]["luecke_km"])
        L = _enden(L)
        if not L:
            continue
        iw, iz = Image.new("1", (nx, ny), 0), Image.new("1", (nx, ny), 0)
        dw, dz = ImageDraw.Draw(iw), ImageDraw.Draw(iz)
        for g in L:
            px = list(zip(((g[:, 0] - w) * sx).tolist(), ((n - g[:, 1]) * sy).tolist()))
            if len(px) < 2:
                continue
            dw.line(px, fill=1, width=max(1, breite_px))
            dz.line(px, fill=1, width=zb)
        wasser |= np.array(iw, bool)
        zone[np.array(iz, bool) & (zone == 0)] = idx + 1
    return wasser, zone


_GRAPH = {}


def _graph(idx):
    """Mittellinien des Kanals idx als Graph: Punkte alle <= 100 m, Kanten laengs der Linien, Kettenenden mit dem
    naechsten Punkt einer anderen Kette verbunden (<= 400 m). -> (pts [n,2] lon/lat, csr-Matrix km)."""
    if idx in _GRAPH:
        return _GRAPH[idx]
    from scipy.sparse import coo_matrix
    L = _linien()[idx]
    if L and KANAELE[idx][4].get("luecke_km"):
        L = _luecken(L, KANAELE[idx][4]["luecke_km"])
    L = _enden(L)
    pts, kanten, kette, enden = [], [], [], []
    for c, g in enumerate(L):
        dicht = [np.asarray(g[0], dtype="f8")]
        for q in np.asarray(g[1:], dtype="f8"):
            vorher = dicht[-1]
            n_ = max(1, int(math.ceil(_km_ll(vorher, q) / 0.1)))
            for f in np.arange(1, n_ + 1) / n_:
                dicht.append(vorher * (1 - f) + q * f)
        o = len(pts)
        pts += [np.asarray(x, dtype="f8") for x in dicht]
        kette += [c] * len(dicht)
        kanten += [(o + i, o + i + 1) for i in range(len(dicht) - 1)]
        enden += [o, o + len(dicht) - 1]
    P = np.array(pts)
    K = np.array(kette)
    for e_ in enden:
        d = _km_arr(P[e_], P)
        d[K == K[e_]] = np.inf
        j = int(np.argmin(d))
        if d[j] <= 0.4:
            kanten.append((e_, j))
    a_, b_ = np.array(kanten).T
    w_ = np.maximum(_km_arr2(P[a_], P[b_]), 1e-4)
    M = coo_matrix((np.r_[w_, w_], (np.r_[a_, b_], np.r_[b_, a_])), shape=(len(P), len(P))).tocsr()
    _GRAPH[idx] = (P, M)
    return _GRAPH[idx]


def _km_ll(a, b):
    return math.hypot((b[1] - a[1]) * 111.2, (b[0] - a[0]) * 111.2 * math.cos(math.radians((a[1] + b[1]) / 2)))


def _km_arr(p, P):
    return np.hypot((P[:, 1] - p[1]) * 111.2, (P[:, 0] - p[0]) * 111.2 * math.cos(math.radians(p[1])))


def _km_arr2(A, B):
    return np.hypot((B[:, 1] - A[:, 1]) * 111.2, (B[:, 0] - A[:, 0]) * 111.2 * np.cos(np.radians(A[:, 1])))


def abstand_km(nr, la, lo):
    """Abstand (km) des Punkts zur Mittellinie des Kanals nr (1 + Index)."""
    P, _ = _graph(nr - 1)
    return float(_km_arr((lo, la), P).min())


def pfad(nr, a, b):
    """Weg laengs der Mittellinie von Punkt a nach b ((la, lo)) im Kanal nr -> [(la, lo), ...] inkl. der beiden
    Fusspunkte, None ohne Verbindung (24.11.2026: Route im Kanal auf die Rinne statt aufs 0,6-km-Raster)."""
    from scipy.sparse.csgraph import dijkstra
    P, M = _graph(nr - 1)
    da, db = _km_arr((a[1], a[0]), P), _km_arr((b[1], b[0]), P)
    # Fusspunkte: nah am Punkt UND auf kurzem Weg zum anderen Ende (sonst rastet ein Punkt zwischen zwei Linien auf
    # einer Nebenlinie ein, z. B. dem alten franzoesischen Kanal bei Gatun, und der Weg macht eine Schleife)
    d_b = dijkstra(M, indices=int(np.argmin(db)))
    i = int(np.argmin(np.where(da <= da.min() + 1.0, d_b + 3 * da, np.inf)))
    d, vor = dijkstra(M, indices=i, return_predecessors=True)
    j = int(np.argmin(np.where(db <= db.min() + 1.0, d + 3 * db, np.inf)))
    if i == j:
        return [(float(P[i, 1]), float(P[i, 0]))]
    if not np.isfinite(d[j]):
        return None
    weg = [j]
    while weg[-1] != i:
        weg.append(int(vor[weg[-1]]))
    return [(float(P[k, 1]), float(P[k, 0])) for k in reversed(weg)]


def regeln(nr):
    """nr = Wert aus zone (1 + Index) -> (Name, Regeln)."""
    k = KANAELE[nr - 1]
    return k[1], k[4]


if __name__ == "__main__":
    if sys.argv[1:2] == ["laden"]:
        laden(sys.argv[2:])
    else:
        print(__doc__)
