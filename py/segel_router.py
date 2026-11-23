#!/usr/bin/env python3
"""
Segel-Routing fuer Tagestoerns (20.11.2026): schnellste Route von A nach B ab Startzeit fuer ein Boot (ORC-Polare)
unter Wind, Wellen und Strom (Gezeitenstrom der Karte + optional Copernicus-Ozeanstrom).

Verfahren: zeitabhaengiger Dijkstra auf einem Gitter (bis ~240 x 240 Knoten, 32 Fahrtrichtungen je Knoten).
Anders als Isochronen findet das Gitter auch um Inseln und Landzungen herum. Zustand = Knoten + Bug (Wind von
Steuerbord/Backbord); Bugwechsel kostet die Wendezeit. Je Kante:
  - Wind relativ zum Wasser (Wind - Strom) -> TWA/TWS -> Polare x Leistungsfaktor x Wellenabzug = Fahrt durchs Wasser
  - Vorhaltewinkel gegen den Querstrom, Fahrt ueber Grund = Fahrt laengs + Strom laengs
  - Motor (wahlweise), wenn Segeln langsamer als die Schwelle waere
Daten: Wind Open-Meteo (best_match: ICON-D2/AROME/HARMONIE usw. je Gebiet, stuendlich), Wellen Open-Meteo Marine,
Strom tpxo_strom_karte.feld (TPXO10 + feine Modelle) stuendlich, Land OSM (segel_land).
Tiefe: EMODnet (Europa) auf Seekartennull, Tiefgang aus dem ORC-Zertifikat + Reserve.
Tide bei der Tiefe seit 21.11.2026 (py/segel_tide.py: Pegel im Bestand, auf LAT bezogen).
Seit 21.11.2026 auch: Verkehrstrennungsgebiete (segel_tss), Sperrgebiete (segel_sperr), Wellen per Fetch in
geschuetzten Gewaessern, Nachtabschnitte markiert (Sonne < -6 Grad).
Seit 22.11.2026: Windstau bei der Tiefe (segel_tide + windstau), „Nachtfahrt vermeiden“ (nacht_meiden=True: nur bei
Tageslicht fahren, nachts in Marina/Hafen/Ankerplatz aus OSM (segel_haefen) oder am Start liegen, bei Morgendaemmerung
weiter) und Mehrtagestoerns (bis 1000 km, Zeitfenster bis 7 Tage; Dijkstra-Zustand Knoten+Bug+Tag, damit ein Knoten
am naechsten Morgen erneut erreicht werden kann - die frueheste Ankunft am Abend kann eine Sackgasse sein).

    r = route(start=(lat, lon), ziel=(lat, lon), t0=unix_s, boot='bavaria37', **optionen)
"""
import concurrent.futures as cf
import datetime as dt
import heapq
import math
import os
import sys
import time

import numpy as np
import requests
from scipy import ndimage

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import segel_land  # noqa: E402
import segel_fluesse  # noqa: E402
import segel_tiefe  # noqa: E402
import segel_tide  # noqa: E402
import segel_tss  # noqa: E402
import segel_sperr  # noqa: E402
import segel_polare  # noqa: E402

KN = 1.852                    # km je sm
OM_CACHE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "quellen", "routing", "om_cache")
MAX_KNOTEN = 240              # Gitterknoten je Achse (Tagestoerns bis 300 km)
MAX_KNOTEN_LANG = 360         # Mehrtagestoerns
MAX_KM = 1000.0
MAX_STUNDEN = 168             # Zeitfenster (Open-Meteo-Vorhersage reicht ~7 Tage mit Regionalmodell-Anschluss)
DAEMMERUNG = -6.0             # Sonnenhoehe Ende/Anfang buergerliche Daemmerung
FEIN = 3                      # Landraster feiner als das Gitter (Kantenpruefung)
# 32 Richtungen: (Zeile, Spalte); Zeile waechst nach Sueden
_BASIS = [(1, 0), (1, 1), (2, 1), (3, 1), (3, 2)]
RICHT = sorted({(a * s1, b * s2) for a, b in _BASIS for s1 in (1, -1) for s2 in (1, -1)}
               | {(b * s1, a * s2) for a, b in _BASIS for s1 in (1, -1) for s2 in (1, -1)})
RICHT = [r for r in RICHT if r != (0, 0)]
assert len(RICHT) == 32, len(RICHT)

STANDARD = dict(leistung=0.85, motor=True, motor_kn=5.5, motor_unter=3.0, max_wind=25.0, max_welle=2.5,
                wendezeit_s=60.0, ozean=True, tiefe=True, reserve_m=0.5, ohne_spi=True,
                tide=True, windstau=True, vtg=True, sperr=True, nacht_meiden=False, max_tag_h=0.0)


class Fehler(Exception):
    pass


def _km(la1, lo1, la2, lo2):
    return math.hypot((la2 - la1) * 111.2, (lo2 - lo1) * 111.2 * math.cos(math.radians((la1 + la2) / 2)))


# ---------------------------------------------------------------- Umweltdaten
def _om_gitter(s, n, w, e, max_pkt=10):
    nla = max(3, min(max_pkt, int(math.ceil((n - s) / 0.025)) + 1))
    nlo = max(3, min(max_pkt, int(math.ceil((e - w) / 0.035)) + 1))
    return np.linspace(s, n, nla), np.linspace(w, e, nlo)


def _om_abruf(url, la, lo, variablen, t_von, t_bis, extra):
    LA, LO = np.meshgrid(la, lo, indexing="ij")
    par = dict(latitude=",".join("%.4f" % x for x in LA.ravel()), longitude=",".join("%.4f" % x for x in LO.ravel()),
               hourly=",".join(variablen), timeformat="unixtime",
               start_hour=dt.datetime.fromtimestamp(t_von, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M"),
               end_hour=dt.datetime.fromtimestamp(t_bis, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M"), **extra)
    # Zwischenspeicher 30 min (gleiches Gebiet + Zeitraum, z. B. anderes Boot/andere Optionen): Open-Meteo zaehlt jeden
    # Gitterpunkt als eigene Abfrage (Grenze je Minute/Stunde/Tag), 20.11.2026 nach HTTP 429 bei Testserie.
    import hashlib
    import json as _json
    os.makedirs(OM_CACHE, exist_ok=True)
    schluessel = hashlib.md5((url + _json.dumps(par, sort_keys=True)).encode()).hexdigest()
    pfad = os.path.join(OM_CACHE, schluessel + ".json")
    d = None
    if os.path.exists(pfad) and time.time() - os.path.getmtime(pfad) < 1800:
        with open(pfad) as f:
            d = _json.load(f)
    if d is None:
        for versuch in range(3):
            r = requests.get(url, params=par, timeout=60)
            if r.status_code != 429 or versuch == 2:
                break
            time.sleep(15 * (versuch + 1))
        if r.status_code == 429:
            raise Fehler("Open-Meteo request limit reached (each grid point counts as one request). "
                         "Please try again in a minute.")
        if r.status_code != 200:
            raise Fehler("Open-Meteo: HTTP %d %s" % (r.status_code, r.text[:200]))
        d = r.json()
        with open(pfad + ".neu", "w") as f:
            _json.dump(d, f)
        os.replace(pfad + ".neu", pfad)
        for alt in os.listdir(OM_CACHE):                            # Eintraege aelter als 1 Tag weg
            q = os.path.join(OM_CACHE, alt)
            try:                                                    # Wind- und Wellenabruf raeumen parallel auf (21.11.)
                if time.time() - os.path.getmtime(q) > 86400:
                    os.remove(q)
            except OSError:
                pass
    if isinstance(d, dict):
        d = [d]
    zeiten = np.array(d[0]["hourly"]["time"], dtype="f8")
    aus = {}
    for v in variablen:
        a = np.array([[np.nan if x is None else x for x in p["hourly"][v]] for p in d], dtype="f8")   # (pkt, T)
        aus[v] = a.T.reshape(len(zeiten), len(la), len(lo))
    return zeiten, aus


def _auf_knoten(feld, la_src, lo_src, LAT, LON):
    """(T, nla, nlo) auf regelmaessigem Gitter -> (T, ny, nx) an den Knoten, bilinear; NaN vorher naechstwertig fuellen."""
    feld = feld.copy()
    for k in range(feld.shape[0]):
        f = feld[k]
        m = ~np.isfinite(f)
        if m.all():
            feld[k] = 0.0
        elif m.any():
            idx = ndimage.distance_transform_edt(m, return_distances=False, return_indices=True)
            feld[k] = f[tuple(idx)]
    yi = (LAT - la_src[0]) / (la_src[-1] - la_src[0]) * (len(la_src) - 1)
    xi = (LON - lo_src[0]) / (lo_src[-1] - lo_src[0]) * (len(lo_src) - 1)
    return np.stack([ndimage.map_coordinates(feld[k], [yi, xi], order=1, mode="nearest") for k in range(feld.shape[0])])


def _wind(s, n, w, e, zeiten, LAT, LON):
    la, lo = _om_gitter(s, n, w, e)
    z, d = _om_abruf("https://api.open-meteo.com/v1/forecast", la, lo, ["wind_speed_10m", "wind_direction_10m"],
                     zeiten[0], zeiten[-1], dict(wind_speed_unit="kn", models="best_match"))
    if len(z) < len(zeiten):
        raise Fehler("Wind forecast only reaches %s UTC" % dt.datetime.fromtimestamp(z[-1], dt.timezone.utc).strftime("%d.%m. %H:%M"))
    sp, ri = d["wind_speed_10m"], np.radians(d["wind_direction_10m"])
    ue, vn = -sp * np.sin(ri), -sp * np.cos(ri)                    # Windrichtung = woher -> Vektor wohin
    return _auf_knoten(ue, la, lo, LAT, LON), _auf_knoten(vn, la, lo, LAT, LON)


def _wellen(s, n, w, e, zeiten, LAT, LON):
    la, lo = _om_gitter(s, n, w, e, max_pkt=7)
    try:
        z, d = _om_abruf("https://marine-api.open-meteo.com/v1/marine", la, lo, ["wave_height", "wave_direction"],
                         zeiten[0], zeiten[-1], {})
    except Exception:                                              # noqa: BLE001 - ohne Wellen weiterrechnen
        return None, None
    hs, ri = d["wave_height"], np.radians(d["wave_direction"])
    # Richtung als Vektor mitteln (nicht ueber 360/0 springen)
    hs_k = _auf_knoten(hs, la, lo, LAT, LON)
    se = _auf_knoten(np.where(np.isfinite(ri), np.sin(ri), np.nan), la, lo, LAT, LON)
    cn = _auf_knoten(np.where(np.isfinite(ri), np.cos(ri), np.nan), la, lo, LAT, LON)
    return np.clip(hs_k, 0, None), np.degrees(np.arctan2(se, cn)) % 360


def sonnenhoehe(la, lo, t):
    """Sonnenhoehe in Grad (NOAA-Naeherung, ~0,5 Grad genau) fuer Unix-Zeit t."""
    d = t / 86400.0 + 2440587.5 - 2451545.0
    g = math.radians((357.529 + 0.98560028 * d) % 360)
    q = (280.459 + 0.98564736 * d) % 360
    L_ = math.radians((q + 1.915 * math.sin(g) + 0.020 * math.sin(2 * g)) % 360)
    e = math.radians(23.439 - 0.00000036 * d)
    ra = math.atan2(math.cos(e) * math.sin(L_), math.cos(L_))
    dek = math.asin(math.sin(e) * math.sin(L_))
    gmst = (18.697374558 + 24.06570982441908 * d) % 24
    ha = math.radians(gmst * 15 + lo) - ra
    phi = math.radians(la)
    return math.degrees(math.asin(math.sin(phi) * math.sin(dek) + math.cos(phi) * math.cos(dek) * math.cos(ha)))


def _fetch(land_k, h, offen_km=200.0):
    """Freie Wasserstrecke (km) gegen 16 Richtungen (woher, 0 = N) je Knoten; trifft der Strahl kein Land im
    Gebiet, gilt das Wasser dahinter als offen (offen_km)."""
    ny, nx = land_k.shape
    F = np.full((16, ny, nx), offen_km, np.float32)
    for r in range(16):
        a = math.radians(22.5 * r)
        di, dj = -math.cos(a), math.sin(a)                           # Zeile waechst nach Sueden
        gefunden = land_k.copy()
        F[r][land_k] = 0.0
        for k in range(1, max(ny, nx) + 1):
            oi, oj = int(round(k * di)), int(round(k * dj))
            if abs(oi) >= ny or abs(oj) >= nx:
                break
            treff = np.zeros_like(land_k)
            src = land_k[max(0, oi):ny + min(0, oi), max(0, oj):nx + min(0, oj)]
            treff[max(0, -oi):ny - max(0, oi), max(0, -oj):nx - max(0, oj)] = src
            neu = treff & ~gefunden
            F[r][neu] = k * h
            gefunden |= treff
    return F


def _wellen_fetch(HS, WD, WU, WV, F):
    """Wellenhoehe in geschuetzten Gewaessern (21.11.2026, Olivers Solent-Fund 1,4 m aus dem Kanalmodell): ist der
    Punkt zur Wellenrichtung hin abgeschirmt (< 30 km freies Wasser), gilt nur die Windsee nach JONSWAP
    Hs = 0,0016 U sqrt(F/g) (U m/s, F m) mit der Fetch gegen den Wind."""
    tws = np.hypot(WU, WV) * 0.514444
    woher = np.degrees(np.arctan2(-WU, -WV)) % 360
    rw = (np.round(woher / 22.5).astype(int)) % 16
    rs = (np.round(WD / 22.5).astype(int)) % 16
    ii, jj = np.indices(HS.shape[1:])
    out = HS.copy()
    for k in range(HS.shape[0]):
        f_wind = F[rw[k], ii, jj] * 1000.0
        f_welle = F[rs[k], ii, jj]
        windsee = 0.0016 * tws[k] * np.sqrt(f_wind / 9.81)
        out[k] = np.where(f_welle < 30.0, np.minimum(HS[k], windsee), HS[k])
    return out


def _strom(s, n, w, e, zeiten, LAT, LON, ozean):
    import tpxo_strom_karte as T
    zellen = int(min(300, max(100, LAT.shape[0], LAT.shape[1])))

    def eins(t):
        d = T.feld(s, n, w, e, dt.datetime.fromtimestamp(t, dt.timezone.utc), max_zellen=zellen, ozean=ozean)
        h = d[0]["header"]
        u = np.array([np.nan if x is None else x for x in d[0]["data"]], dtype="f8").reshape(h["ny"], h["nx"])
        v = np.array([np.nan if x is None else x for x in d[1]["data"]], dtype="f8").reshape(h["ny"], h["nx"])
        la = h["la1"] - h["dy"] * np.arange(h["ny"])               # Nord -> Sued
        lo = h["lo1"] + h["dx"] * np.arange(h["nx"])
        lo = np.where(lo < w - 180, lo + 360, lo)
        uk = _auf_knoten(u[::-1][None], la[::-1], lo, LAT, LON)[0]
        vk = _auf_knoten(v[::-1][None], la[::-1], lo, LAT, LON)[0]
        return uk * 1.94384, vk * 1.94384                          # m/s -> kn

    with cf.ThreadPoolExecutor(4) as ex:
        res = list(ex.map(eins, zeiten))
    return np.stack([r[0] for r in res]), np.stack([r[1] for r in res])


# ---------------------------------------------------------------- Route
def _gebiet(la_a, lo_a, la_b, lo_b, rand, max_knoten):
    la0 = (la_a + la_b) / 2
    kx = 111.2 * math.cos(math.radians(la0))
    s, n = min(la_a, la_b) - rand / 111.2, max(la_a, la_b) + rand / 111.2
    w, e = min(lo_a, lo_b) - rand / kx, max(lo_a, lo_b) + rand / kx
    h = max(0.12, max((n - s) * 111.2, (e - w) * kx) / max_knoten)
    return s, n, w, e, h, kx


def _rand_finden(la_a, lo_a, la_b, lo_b, dist, max_knoten):
    """Rand (km) um A und B. 23.11.2026 (Roscoff -> Brest): das Rechteck mit 35 % Rand schnitt die Iroise ab, die
    Rade de Brest lag ohne Verbindung zum Meer -> "more than 10 km from navigable water". Jetzt: Land (OSM + Fluesse)
    auf dem Gitter pruefen und den Rand vergroessern, bis A und B (naechstes Wasser <= 3 km) in derselben Wasserflaeche
    liegen wie die groesste. Tiefe/Sperrgebiete bleiben hier aussen vor (selten trennend, teuer)."""
    versuche = [max(f * dist, km) for f, km in ((0.35, 10.0), (0.6, 25.0), (1.0, 50.0), (1.6, 80.0))]
    for rand in versuche:
        s, n, w, e, h, kx = _gebiet(la_a, lo_a, la_b, lo_b, rand, max_knoten)
        ny, nx = int(math.ceil((n - s) * 111.2 / h)), int(math.ceil((e - w) * kx / h))
        n, e = s + ny * h / 111.2, w + nx * h / kx
        land = segel_land.raster(s, n, w, e, ny * FEIN, nx * FEIN)
        land &= ~segel_fluesse.raster(s, n, w, e, ny * FEIN, nx * FEIN, min_px=FEIN)
        wasser = ~land[FEIN // 2::FEIN, FEIN // 2::FEIN][:ny, :nx]
        teile, anzahl = ndimage.label(wasser, structure=np.ones((3, 3)))
        if anzahl == 0:
            continue
        gr = np.bincount(teile.ravel())
        gr[0] = 0
        gross = int(np.argmax(gr))
        d, idx = ndimage.distance_transform_edt(~wasser, return_indices=True)
        ok, pkt = True, []
        for la, lo in ((la_a, lo_a), (la_b, lo_b)):
            i = min(max(int(round((n - la) * 111.2 / h - 0.5)), 0), ny - 1)
            j = min(max(int(round((lo - w) * kx / h - 0.5)), 0), nx - 1)
            pkt.append(int(idx[0][i, j]) * nx + int(idx[1][i, j]))
            if d[i, j] * h > 3.0 or teile[idx[0][i, j], idx[1][i, j]] != gross:
                ok = False
                break
        if ok:
            return rand, _wasserweg_km(teile == gross, pkt[0], pkt[1], h)
    return versuche[0], dist


def _wasserweg_km(wasser, a, b, h):
    """Kuerzester Weg ueber Wasser (8er-Nachbarschaft) zwischen den Zellen a und b (flacher Index), km."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import dijkstra
    ny, nx = wasser.shape
    nr = np.arange(ny * nx).reshape(ny, nx)
    zeilen, spalten, gew = [], [], []
    for di, dj in ((0, 1), (1, 0), (1, 1), (1, -1)):
        a1 = wasser[max(0, -di):ny - max(0, di), max(0, -dj):nx - max(0, dj)]
        b1 = wasser[max(0, di):, max(0, dj):][:a1.shape[0], :a1.shape[1]] if dj >= 0 else wasser[di:, :nx + dj][:a1.shape[0]]
        na = nr[max(0, -di):ny - max(0, di), max(0, -dj):nx - max(0, dj)]
        nb = nr[max(0, di):, max(0, dj):][:a1.shape[0], :a1.shape[1]] if dj >= 0 else nr[di:, :nx + dj][:a1.shape[0]]
        m = a1 & b1
        zeilen.append(na[m])
        spalten.append(nb[m])
        gew.append(np.full(m.sum(), h * math.hypot(di, dj)))
    G = coo_matrix((np.concatenate(gew), (np.concatenate(zeilen), np.concatenate(spalten))), shape=(ny * nx, ny * nx))
    km = dijkstra(G.tocsr(), directed=False, indices=a)[b]
    return float(km) if np.isfinite(km) else 0.0


def route(start, ziel, t0, boot=segel_polare.STANDARD, **opt):
    o = dict(STANDARD)
    o.update({k: v for k, v in opt.items() if v is not None})
    uhr = time.time()
    P = segel_polare.polare(boot, ohne_spi=o["ohne_spi"])
    la_a, lo_a = start
    la_b, lo_b = ziel
    dist = _km(la_a, lo_a, la_b, lo_b)
    if dist < 0.5:
        raise Fehler("Start and destination are less than 0.5 km apart")
    if dist > MAX_KM:
        raise Fehler("Start and destination must be within %d km (%d nm)" % (MAX_KM, MAX_KM / KN))
    nm = bool(o["nacht_meiden"])
    max_knoten = MAX_KNOTEN if dist <= 300 else int(min(MAX_KNOTEN_LANG, MAX_KNOTEN * dist / 300))
    # Gebiet: Rechteck um A und B mit Rand; gross genug, dass A und B ueber See verbunden sind
    rand, weg_km = _rand_finden(la_a, lo_a, la_b, lo_b, dist, max_knoten)
    la0 = (la_a + la_b) / 2
    kx = 111.2 * math.cos(math.radians(la0))
    s, n = min(la_a, la_b) - rand / 111.2, max(la_a, la_b) + rand / 111.2
    w, e = min(lo_a, lo_b) - rand / kx, max(lo_a, lo_b) + rand / kx
    h = max(0.12, max((n - s) * 111.2, (e - w) * kx) / max_knoten)      # Gitterweite km
    ny, nx = int(math.ceil((n - s) * 111.2 / h)), int(math.ceil((e - w) * kx / h))
    n, e = s + ny * h / 111.2, w + nx * h / kx                         # Rechteck genau auf das Gitter
    LAT = n - (np.arange(ny) + 0.5) * h / 111.2
    LON = w + (np.arange(nx) + 0.5) * h / kx
    LAT2, LON2 = np.meshgrid(LAT, LON, indexing="ij")
    # Zeitfenster: geschaetzte Dauer bei 3 kn ueber Grund x 1,5 (Kreuz gegen Strom braucht Reserve), mind. 12 h;
    # mit „Nachtfahrt vermeiden“ ganze Tage nach Tageslichtdauer + Wartezeit bis zum ersten Morgen
    fahr_h = max(dist, weg_km) / KN / 3.0 * 1.5 + 2       # Wasserweg (23.11.2026: Roscoff -> Brest 50 km Luftlinie, ~130 km See)
    if nm:
        lo0 = (lo_a + lo_b) / 2
        hell = [sonnenhoehe(la0, lo0, t0 + 600.0 * q) >= DAEMMERUNG for q in range(144)]
        tag_h = sum(hell) / 6.0
        if tag_h < 3.0:
            raise Fehler("Only %.1f h of daylight per day here - 'avoid sailing at night' is not possible" % tag_h)
        if o["max_tag_h"] and o["max_tag_h"] > 0:
            tag_h = min(tag_h, max(2.0, float(o["max_tag_h"])))
        fahr_h = math.ceil(fahr_h / tag_h) * 24 + (0 if hell[0] else 12) + 6
    stunden = int(min(MAX_STUNDEN, max(12, math.ceil(fahr_h))))
    T0 = math.floor(t0 / 3600) * 3600
    zeiten = T0 + 3600.0 * np.arange(stunden + 2)

    # Land (fein) und erlaubte Kanten
    land_f = segel_land.raster(s, n, w, e, ny * FEIN, nx * FEIN)
    # Tidefluesse hinter der OSM-Kuestenlinie (23.11.2026: Loire ab Saint-Nazaire, Themse ab Gravesend, Elbe vor
    # Hamburg ... waren "Land"): OSM-Flussflaechen (py/segel_fluesse.py, gespeicherte Kacheln) sind Wasser
    fluss_f = segel_fluesse.raster(s, n, w, e, ny * FEIN, nx * FEIN, min_px=FEIN) & land_f
    land_f = land_f & ~fluss_f
    fluss_info = ("OSM river areas: %.1f %% of the area (depth unknown there, keep to the fairway)" % (100 * fluss_f.mean())
                  if fluss_f.any() else "off")
    land_rein = land_f[FEIN // 2::FEIN, FEIN // 2::FEIN][:ny, :nx].copy()       # nur Kueste (Fetch)
    # Sperrgebiete (OpenSeaMap no_entry / to_be_avoided, 21.11.2026) wie Land; Zutritt mit Auflagen nur als Hinweis
    sperr_info, auflagen = "off", []
    if o["sperr"]:
        sp_f, auflagen = segel_sperr.raster(s, n, w, e, ny * FEIN, nx * FEIN)
        land_f = land_f | sp_f
        sperr_info = "OpenSeaMap: %.1f %% of the area no entry" % (100 * sp_f.mean())
    # Wassertiefe (EMODnet, Seekartennull): gesperrt, wo der flachste Grund hoeher liegt als -(Tiefgang + Reserve).
    # Vorsichtig = wie bei Niedrigwasser Springzeit; Watt und Barren werden immer umfahren (Tide noch nicht beruecksichtigt).
    tiefgang = float(P.info().get("tiefgang") or 2.0)
    tiefe_info = "off"
    stau_info = "off" if not o["windstau"] else "no forecast for the gauges in the area"
    grund_f = None                                   # Grund ueber LAT (m) auf dem feinen Raster, nur bei Tiefendaten
    HT = None                                        # Tidenhoehe ueber LAT [zeit, ny, nx]
    brauch = tiefgang + o["reserve_m"]
    if o["tiefe"]:
        hoehe_f = segel_tiefe.flachstes(s, n, w, e, ny * FEIN, nx * FEIN)
        if hoehe_f is None:
            tiefe_info = "no data (EMODnet covers Europe only)"
        else:
            grund_f = np.nan_to_num(hoehe_f, nan=-999.0).astype(np.float32)
            # EMODnet liefert hinter der Kuestenlinie Fuellwerte/Gelaendehoehen statt Tiefen (Loire 0 m, Nantes 5-13 m)
            # -> dort SHOM-Peilmodelle (23.11.2026: Loire, Seine, Gironde, Schelde ...), sonst keine Tiefe
            grund_f[fluss_f] = -999.0
            if fluss_f.any():
                sh, sh_namen = segel_tiefe.shom(s, n, w, e, ny * FEIN, nx * FEIN)
                mit = fluss_f & np.isfinite(sh)
                grund_f[mit] = sh[mit]
                if mit.any():
                    fluss_info = ("OSM river areas: %.1f %% of the area, depth there from %s for %.0f %% of it "
                                  "(rest unknown, keep to the fairway)" % (100 * fluss_f.mean(), ", ".join(sh_namen),
                                                                         100 * mit.sum() / fluss_f.sum()))
            # Tide (21.11.2026): Flaechen, die bei Hochwasser tief genug sind, nur zeitweise sperren
            HT, n_pegel, stau = (segel_tide.hoehe_ueber_lat(LAT2, LON2, zeiten, windstau=o["windstau"]) if o["tide"]
                                 else (None, 0, None))
            if HT is None:
                HT = np.zeros((len(zeiten), ny, nx), np.float32)
            hw_f = np.repeat(np.repeat(HT.max(0), FEIN, 0), FEIN, 1)[:ny * FEIN, :nx * FEIN]
            land_f = land_f | (grund_f > hw_f - brauch)                      # auch bei Hochwasser zu flach
            if stau:
                stau_info = ("%s run %s, %d of %d gauges, %+.2f to %+.2f m" % (
                    "/".join({"cmems": "Copernicus Marine", "stofs": "NOAA STOFS"}.get(q, q) for q in stau["quellen"]),
                    ", ".join(stau["lauf"]), stau["n"], n_pegel, stau["min"], stau["max"]) + "; raised water only up to 48 h after the model run")
            tiefe_info = ("EMODnet (LAT) + tide height from %d gauges%s, draft %.1f m + %.1f m" % (
                n_pegel, " + storm surge" if stau else "", tiefgang, o["reserve_m"])
                          if n_pegel else "EMODnet, chart datum (LAT), draft %.1f m + %.1f m (no tide gauge nearby)" % (tiefgang, o["reserve_m"]))
    mitte = FEIN // 2
    wasser = ~land_f[mitte::FEIN, mitte::FEIN][:ny, :nx]

    # Zusammenhaengendes Fahrwasser: groesste Wasserflaeche (8er-Nachbarschaft). Haefen hinter schmalen, gebaggerten
    # Rinnen (schmaler als ~1 EMODnet-Zelle) liegen sonst in einer abgeschlossenen Tasche (20.11.2026: Marstal) –
    # Start/Ziel werden dann auf den naechsten Punkt im Fahrwasser gesetzt, der Rest ist gestrichelt.
    teile, anzahl = ndimage.label(wasser, structure=np.ones((3, 3)))
    if anzahl == 0:
        raise Fehler("No navigable water in the area")
    groesse = np.bincount(teile.ravel())
    groesse[0] = 0
    fahrwasser = teile == int(np.argmax(groesse))
    _fern = {}

    def knoten_naechst(la, lo):
        i = int(round((n - la) * 111.2 / h - 0.5))
        j = int(round((lo - w) * kx / h - 0.5))
        i, j = min(max(i, 0), ny - 1), min(max(j, 0), nx - 1)
        if fahrwasser[i, j]:
            return i, j, 0.0
        if "idx" not in _fern:
            _fern["d"], _fern["idx"] = ndimage.distance_transform_edt(~fahrwasser, return_indices=True)
        d = _fern["d"][i, j] * h
        if d > 10.0:
            raise Fehler("Point %.4f, %.4f is more than 10 km from navigable water connected to the open sea (land or "
                         "too shallow at chart datum for %.1f m draft)" % (la, lo, tiefgang))
        return int(_fern["idx"][0][i, j]), int(_fern["idx"][1][i, j]), round(d, 1)


    gueltig = np.zeros((32, ny, nx), dtype=bool)
    kante_grund = np.full((32, ny, nx), -999.0, np.float32) if grund_f is not None else None
    II, JJ = np.meshgrid(np.arange(ny), np.arange(nx), indexing="ij")
    for d, (di, dj) in enumerate(RICHT):
        i2, j2 = II + di, JJ + dj
        ok = wasser & (i2 >= 0) & (i2 < ny) & (j2 >= 0) & (j2 < nx)
        schritte = int(math.ceil(math.hypot(di, dj) * FEIN * 1.5))
        for q in range(0 if grund_f is not None else 1, schritte + 1):
            f = q / schritte
            fi = np.clip(np.round((II + f * di) * FEIN + mitte).astype(int), 0, ny * FEIN - 1)
            fj = np.clip(np.round((JJ + f * dj) * FEIN + mitte).astype(int), 0, nx * FEIN - 1)
            ok &= ~land_f[fi, fj]
            if kante_grund is not None:
                np.maximum(kante_grund[d], grund_f[fi, fj], out=kante_grund[d])
        gueltig[d] = ok
    # Verkehrstrennungsgebiete (21.11.2026): in Fahrstreifen nur mit dem Verkehr oder rechtwinklig queren,
    # Trennzonen nur queren (KVR Regel 10, vereinfacht)
    vtg_info = "off"
    if o["vtg"]:
        T_ = segel_tss.regeln(LAT2, LON2, np.array([math.degrees(math.atan2(dj, -di)) % 360 for di, dj in RICHT]))
        if T_ is None:
            vtg_info = "none in the area"
        else:
            gueltig &= T_[0]
            vtg_info = "OpenSeaMap: %d grid points in lanes/zones" % T_[1]
    # nur Kanten, die irgendwann zu flach sind, brauchen die Zeitpruefung
    tidal = (kante_grund > HT.min(0)[None] - brauch) & gueltig if kante_grund is not None else None
    # Befahrbares Netz: vom offensten Wasserpunkt (groesster Abstand zum Land/Flachen) ueber erlaubte Kanten erreichbare
    # Knoten (zeitfrei). Start und Ziel kommen auf den naechsten davon. Die 8er-Flaechensuche oben laesst diagonale
    # Engstellen durch, die die feine Kantenpruefung sperrt (20.11.2026: Marstal, Lymington).
    tief_innen = ndimage.distance_transform_edt(fahrwasser)
    si, sj = np.unravel_index(int(np.argmax(tief_innen)), tief_innen.shape)
    erreicht = np.zeros((ny, nx), dtype=bool)
    erreicht[si, sj] = True
    front = erreicht.copy()
    while front.any():
        neu = np.zeros_like(erreicht)
        for d, (di, dj) in enumerate(RICHT):
            q = front & gueltig[d]
            if not q.any():
                continue
            qi, qj = np.nonzero(q)
            neu[qi + di, qj + dj] = True
        front = neu & ~erreicht
        erreicht |= front
    fahrwasser = erreicht
    _fern.clear()
    ia, ja, a_versch = knoten_naechst(la_a, lo_a)
    ib, jb, b_versch = knoten_naechst(la_b, lo_b)
    # Liegeplaetze (22.11.2026): Marinas/Haefen/Ankerplaetze (OSM) auf den naechsten befahrbaren Knoten (<= max(3 km,
    # 1,5 Gitterweiten)); dort darf das Boot bei „Nachtfahrt vermeiden“ bis zum Morgen liegen. Der Start zaehlt auch.
    liege = {}
    if nm:
        import segel_haefen
        if "idx" not in _fern:
            _fern["d"], _fern["idx"] = ndimage.distance_transform_edt(~fahrwasser, return_indices=True)
        rang = {"marina": 0, "hafen": 1, "anker": 2}
        for la_, lo_, name_, art_ in segel_haefen.liste(s, n, w, e):
            i_ = int(round((n - la_) * 111.2 / h - 0.5))
            j_ = int(round((lo_ - w) * kx / h - 0.5))
            if not (0 <= i_ < ny and 0 <= j_ < nx):
                continue
            d_ = float(_fern["d"][i_, j_]) * h
            if d_ > max(3.0, 1.5 * h):
                continue
            k_ = int(_fern["idx"][0][i_, j_]) * nx + int(_fern["idx"][1][i_, j_])
            alt = liege.get(k_)
            if alt is None or (rang[art_], name_ == "", d_) < (rang[alt["art"]], alt["name"] == "", alt["km"]):
                liege[k_] = {"name": name_ or {"marina": "marina", "hafen": "harbour", "anker": "anchorage"}[art_],
                             "art": art_, "km": round(d_, 1), "la": la_, "lo": lo_}
        liege[ia * nx + ja] = {"name": "start", "art": "start", "km": a_versch, "la": la_a, "lo": lo_a}
    # Zielmenge: erreichbare Knoten bis 3 km weiter als der naechste; gewaehlt wird der mit der kleinsten Summe aus
    # Ankunft und Reststrecke bei 0,5 kn (20.11.2026: 9 mm weniger Tiefgang machten einen Punkt 0,5 km vor Marstal
    # erreichbar, aber nur ueber 3,6 h Umweg; „zuerst erreicht“ endete vor Helgoland 1,9 km zu frueh, 3 kn 3,2 km, 1 kn 2,1 km)
    ab_ziel = np.hypot((LAT2 - la_b) * 111.2, (LON2 - lo_b) * kx)
    ziel_menge = fahrwasser & (ab_ziel <= ab_ziel[ib, jb] + 3.0)
    rest_s = (ab_ziel / (0.5 * KN) * 3600.0).ravel()                  # Reststrecke zum Ziel bei 0,5 kn (Bewertung)
    ziel_menge_flach = ziel_menge.ravel()
    laenge = np.array([math.hypot(di, dj) * h for di, dj in RICHT])          # km
    peil = np.array([math.degrees(math.atan2(dj, -di)) % 360 for di, dj in RICHT])
    hd = np.radians(peil)
    de, dn = np.sin(hd), np.cos(hd)
    ne_, nn_ = np.cos(hd), -np.sin(hd)                                       # rechts quer

    t_um = time.time()
    with cf.ThreadPoolExecutor(3) as ex:
        f_wind = ex.submit(_wind, s, n, w, e, zeiten, LAT2, LON2)
        f_welle = ex.submit(_wellen, s, n, w, e, zeiten, LAT2, LON2)
        f_strom = ex.submit(_strom, s, n, w, e, zeiten, LAT2, LON2, o["ozean"])
        WU, WV = f_wind.result()
        HS, WD = f_welle.result()
        CU, CV = f_strom.result()
    t_um = time.time() - t_um
    if HS is None:
        HS = np.zeros_like(WU)
        WD = np.zeros_like(WU)
    else:
        HS = _wellen_fetch(HS, WD, WU, WV, _fetch(land_rein, h))
    WU, WV, CU, CV, HS, WD = (np.asarray(A_, np.float32) for A_ in (WU, WV, CU, CV, HS, WD))   # Mehrtagesfenster: Speicher

    def umwelt(i, j, t):
        x = (t - T0) / 3600.0
        k = min(int(x), len(zeiten) - 2)
        f = x - k
        g = lambda A: A[k, i, j] * (1 - f) + A[k + 1, i, j] * f                  # noqa: E731
        wd0, wd1 = WD[k, i, j], WD[k + 1, i, j]
        wd = (wd0 + f * (((wd1 - wd0 + 180) % 360) - 180)) % 360
        return g(WU), g(WV), g(CU), g(CV), g(HS), wd

    leistung, motor, motor_kn, motor_unter = o["leistung"], o["motor"], o["motor_kn"], o["motor_unter"]
    max_wind, max_welle = o["max_wind"], o["max_welle"]
    wende_h = o["wendezeit_s"] / 3600.0

    def stunde(k):
        """Fahrt ueber Grund [32, ny, nx] (kn, -1 = unmoeglich), Bug (0 Stb, 1 Bb, -1 Motor), Steuerkurs – fuer alle
        Knoten zur vollen Stunde zeiten[k]. Zwischen zwei Stunden wird linear gemischt."""
        wu, wv, cu, cv, hs, wd = WU[k], WV[k], CU[k], CV[k], HS[k], np.radians(WD[k])
        we, wn = wu - cu, wv - cv                                         # Wind gegen Wasser
        tws = np.hypot(we, wn)
        woher = np.degrees(np.arctan2(-we, -wn)) % 360
        grenze = (tws > max_wind) | (hs > max_welle)
        H = hd[:, None, None]
        c_quer = cu[None] * ne_[:, None, None] + cv[None] * nn_[:, None, None]
        c_lang = cu[None] * de[:, None, None] + cv[None] * dn[:, None, None]
        h_ = np.broadcast_to(H, c_quer.shape).copy()
        for _ in range(2):
            twa = ((woher[None] - np.degrees(h_) + 180) % 360) - 180
            welle = 1 - hs[None] * (0.02 + 0.06 * (1 + np.cos(wd[None] - h_)) / 2)   # Seegang von vorn bremst am meisten
            V = P.fahrt(np.broadcast_to(tws[None], twa.shape), twa) * leistung * np.clip(welle, 0.3, 1)
            q = np.where(V > 0.1, np.clip(-c_quer / np.maximum(V, 0.1), -0.99, 0.99), 0)
            h_ = H + np.arcsin(q)
        ok = (V > 0.1) & (np.abs(c_quer) < V)
        sog = np.where(ok, V * np.cos(h_ - H) + c_lang, -1.0)
        twa = ((woher[None] - np.degrees(h_) + 180) % 360) - 180
        bug = np.where(twa > 0, 0, 1).astype(np.int8)
        kurs = np.degrees(h_) % 360
        if motor:
            welle_m = np.clip(1 - hs[None] * (0.02 + 0.06 * (1 + np.cos(wd[None] - H)) / 2), 0.3, 1)
            Vm = motor_kn * welle_m
            okm = np.abs(c_quer) < Vm
            hm = H + np.arcsin(np.clip(-c_quer / Vm, -0.99, 0.99))
            sog_m = np.where(okm, Vm * np.cos(hm - H) + c_lang, -1.0)
            nimm = ((V * np.cos(h_ - H) < motor_unter) | ~ok) & (sog_m > 0.05)
            sog = np.where(nimm, sog_m, sog)
            bug = np.where(nimm, -1, bug).astype(np.int8)
            kurs = np.where(nimm, np.degrees(hm) % 360, kurs)
        sog = np.where(grenze[None] | ~gueltig, -1.0, sog)
        return sog.astype(np.float32), bug, kurs.astype(np.float32)

    STUNDE = {}

    def stunde_c(k):
        if k not in STUNDE:
            STUNDE[k] = stunde(k)
            for alt in [x for x in STUNDE if x < k - 1]:              # Dijkstra laeuft vorwaerts in der Zeit
                del STUNDE[alt]
        return STUNDE[k]

    # Dijkstra ueber (Tag, Knoten, Bug); Tag nur bei „Nachtfahrt vermeiden“ (sonst immer 0). Tagesgrenze = mittlere
    # Ortsmitternacht des Gebiets; innerhalb eines Tages bleibt „frueheste Ankunft gewinnt“ richtig.
    N = ny * nx
    lo_m = (w + e) / 2
    T_ref = math.floor((t0 + lo_m * 240.0) / 86400.0) * 86400.0 - lo_m * 240.0         # Ortsmitternacht vor dem Start
    n_tage = int(math.ceil((zeiten[-1] - T_ref) / 86400.0)) + 1 if nm else 1

    def tagnr(t):
        return min(n_tage - 1, int((t - T_ref) // 86400)) if nm else 0

    t_ende = zeiten[-2]

    def suche(t_ab, see_warten):
        """Zeitabhaengiger Dijkstra ab Abfahrt t_ab (>= t0; davor Warten am Start). see_warten: auch unterwegs auf Wetter
        warten (sonst nur am Start/an Liegeplaetzen)."""
        ankunft = np.full(2 * N * n_tage, np.inf)
        vor = np.full(2 * N * n_tage, -1, dtype=np.int64)
        vor_d = np.full(2 * N * n_tage, -1, dtype=np.int8)               # -2 = Nacht am Liegeplatz
        vor_bug = np.zeros(2 * N * n_tage, dtype=np.int8)
        vor_kurs = np.zeros(2 * N * n_tage, dtype=np.float32)
        vor_sog = np.zeros(2 * N * n_tage, dtype=np.float32)
        t_ende = zeiten[-2]
        heap = []
        nacht_gew = set()

        def morgen(la_, lo_, t_):
            """Ende der naechsten (oder laufenden) Nacht in 10-min-Schritten; None ohne Nacht in 30 h."""
            dunkel = sonnenhoehe(la_, lo_, t_) < DAEMMERUNG
            for q in range(1, 181):
                x_ = t_ + 600.0 * q
                if sonnenhoehe(la_, lo_, x_) < DAEMMERUNG:
                    dunkel = True
                elif dunkel:
                    return x_
            return None

        # Hoechstens max_tag_h Stunden unterwegs je Tag (22.11.2026, nur mit nacht_meiden): Tag beginnt bei der
        # Morgendaemmerung (Gebietsmitte), am ersten Tag mit der Abfahrt
        la_m = (s + n) / 2
        tag_ende = [np.inf] * n_tage
        if nm and o["max_tag_h"] and o["max_tag_h"] > 0:
            for d_ in range(n_tage):
                beginn = morgen(la_m, lo_m, T_ref + d_ * 86400.0 - 1800.0)
                if d_ == tagnr(t0):
                    beginn = t0 if sonnenhoehe(la_m, lo_m, t0) >= DAEMMERUNG else (beginn or t0)
                if beginn is not None:
                    tag_ende[d_] = beginn + o["max_tag_h"] * 3600.0
        # Gleichstand beim Uebernachten (22.11.2026: Kiel->Kopenhagen blieb nach 27 min in Probstei): Morgen-Etikett
        # minimal nach Reststrecke (0,1 s/km) und Art (Marina vor Hafen vor Ankerplatz) verschieben -> weiter gefahrene
        # Etappe und bessere Liegeplaetze gewinnen, wenn die Ankunft sonst gleich waere
        STRAFE_ART = {"marina": 0.0, "start": 0.0, "hafen": 60.0, "anker": 300.0}

        for b in (0, 1):
            z0 = (tagnr(t0) * N + ia * nx + ja) * 2 + b
            ankunft[z0] = float(t0)
            heapq.heappush(heap, (float(t_ab), -z0 - 1) if t_ab > t0 else (float(t0), z0))   # spaetere Abfahrt = Warten
        erledigt = np.zeros(2 * N * n_tage, dtype=bool)
        gefunden = None
        pops = 0
        versatz = np.array([di * nx + dj for di, dj in RICHT], dtype=np.int64)
        dauer0 = laenge / KN * 3600.0                                          # s bei 1 kn
        wende_s = wende_h * 3600.0
        t_dij = time.time()
        beste = (np.inf, None)
        gewartet = set()                                                   # Knoten, an denen schon auf Wasser gewartet wurde
        gewartet_w = set()                                                 # ... auf Wetter (Wind/Welle unter der Grenze)

        def wetter_zu(kk, i, j):
            return (math.hypot(WU[kk, i, j] - CU[kk, i, j], WV[kk, i, j] - CV[kk, i, j]) > max_wind
                    or HS[kk, i, j] > max_welle)
        while heap:
            t, z = heapq.heappop(heap)
            if t >= beste[0]:                                             # kein Kandidat kann noch besser werden
                break
            if z < 0:                                                     # Warte-Eintrag: Boot liegt bis t am Knoten (Tide)
                z = -z - 1
            elif erledigt[z]:
                continue
            erledigt[z] = True
            pops += 1
            k, b = divmod(z, 2)
            tg, k = divmod(k, N)
            if ziel_menge_flach[k]:
                # Bewertung = Ankunft + Rest bei 0,5 kn (teurer als fast jeder echte Weg, auch die Kreuz): ein naeherer Punkt gewinnt, wenn der Weg dorthin weniger kostet
                # als die gesparte Reststrecke; weitersuchen, bis keine Ankunft die beste Bewertung noch schlagen kann
                if t + rest_s[k] < beste[0]:
                    beste = (t + rest_s[k], z)
                # weiter ausbauen: naehere Zielpunkte liegen oft nur hinter diesem (Ring um das Ziel)
            if t >= t_ende:
                continue
            i, j = divmod(k, nx)
            if nm:
                # Liegeplatz: Uebernachten anbieten (naechster Morgen, neuer Tag); im Dunkeln nirgends weiterfahren
                if k in liege and z not in nacht_gew:
                    nacht_gew.add(z)
                    tm = morgen(float(LAT[i]), float(LON[j]), t)
                    if tm is not None:
                        tm += STRAFE_ART.get(liege[k]["art"], 0.0) + 0.1 * float(ab_ziel.ravel()[k])
                    if tm is not None and tm < t_ende:
                        zm = (tagnr(tm) * N + k) * 2 + b
                        if zm == z:                                       # Start vor der Daemmerung: gleicher Tag
                            heapq.heappush(heap, (tm, -z - 1))
                        elif tm < ankunft[zm]:
                            ankunft[zm] = tm
                            vor[zm] = z
                            vor_d[zm] = -2
                            heapq.heappush(heap, (tm, int(zm)))
                sh0 = sonnenhoehe(float(LAT[i]), float(LON[j]), t)
                if sh0 < DAEMMERUNG or t >= tag_ende[tg]:
                    continue
                sh1 = sonnenhoehe(float(LAT[i]), float(LON[j]), t + 3600.0)
            x = (t - T0) / 3600.0
            ks = min(int(x), len(zeiten) - 2)
            f = x - ks
            S0, B0, K0 = stunde_c(ks)
            S1 = stunde_c(ks + 1)[0]
            s0, s1 = S0[:, i, j], S1[:, i, j]
            sog = np.where((s0 > 0.05) & (s1 > 0.05), s0 * (1 - f) + s1 * f, np.where(f < 0.5, s0, s1))
            bug = B0[:, i, j] if f < 0.5 else stunde_c(ks + 1)[1][:, i, j]
            kurs = K0[:, i, j] if f < 0.5 else stunde_c(ks + 1)[2][:, i, j]
            # Wind zum tatsaechlichen Zeitpunkt gegen den ORC-Wendewinkel pruefen (20.11.2026: bei schnell drehendem Wind
            # galt ein Kurs der vollen Stunde bis zu 30 min weiter – Boot fuhr 16° am Wind). Bug neu aus dem echten TWA.
            wu, wv, cu, cv, _hs, _wd = umwelt(i, j, t)
            we, wn = wu - cu, wv - cv
            tws = math.hypot(we, wn)
            woher = math.degrees(math.atan2(-we, -wn)) % 360
            twa = ((woher - kurs + 180) % 360) - 180
            if tidal is not None and tidal[:, i, j].any():
                ht = HT[ks, i, j] * (1 - f) + HT[ks + 1, i, j] * f
                zu = tidal[:, i, j] & (kante_grund[:, i, j] > ht - brauch)
                sog = np.where(zu, -1.0, sog)
                # Warten auf Wasser (21.11.2026): naechster Zeitpunkt (10-min-Schritte), zu dem eine gesperrte Kante frei wird
                if zu.any() and z not in gewartet:
                    gewartet.add(z)
                    tt = t + 600.0 * np.arange(1, int((t_ende - t) / 600))
                    if len(tt):
                        xx = (tt - T0) / 3600.0
                        kk = np.minimum(xx.astype(int), len(zeiten) - 2)
                        hh = HT[kk, i, j] * (1 - (xx - kk)) + HT[kk + 1, i, j] * (xx - kk)
                        frei = hh[None, :] - brauch >= kante_grund[zu, i, j][:, None]
                        if frei.any():
                            tw = float(tt[int(np.argmax(frei.any(0)))])
                            # „Nachtfahrt vermeiden“: ausserhalb eines Liegeplatzes nicht ueber Nacht auf Wasser warten
                            if not (nm and k not in liege and any(sonnenhoehe(float(LAT[i]), float(LON[j]), x_) < DAEMMERUNG
                                                                  for x_ in np.arange(t, tw + 1, 1800.0))):
                                heapq.heappush(heap, (tw, -z - 1))
            # Warten auf Wetter (23.11.2026, Roscoff -> Lorient: 2,8-3,1 m Welle bis 25.11. mittags, danach < 2,5 m -> vorher
            # "No route found"): Wind/Welle hier ueber der Grenze -> erste volle Stunde, ab der es zwei Stunden lang passt
            if (see_warten or k == ia * nx + ja or k in liege) and z not in gewartet_w and (
                    wetter_zu(ks, i, j) or wetter_zu(ks + 1, i, j)):
                gewartet_w.add(z)
                for kk in range(ks + 1, len(zeiten) - 2):
                    if not (wetter_zu(kk, i, j) or wetter_zu(kk + 1, i, j)):
                        tw = float(zeiten[kk])
                        if tw < t_ende and not (nm and k not in liege and any(
                                sonnenhoehe(float(LAT[i]), float(LON[j]), x_) < DAEMMERUNG for x_ in np.arange(t, tw + 1, 1800.0))):
                            heapq.heappush(heap, (tw, -z - 1))
                        break
            segel = bug != -1
            if tws > max_wind:
                sog = np.where(segel, -1.0, sog)
            sog = np.where(segel & (np.abs(twa) < P.wendewinkel(tws)), -1.0, sog)
            bug = np.where(segel, np.where(twa > 0, 0, 1), -1)
            mog = sog > 0.05
            if not mog.any():
                continue
            dauer = np.where(mog, dauer0 / np.maximum(sog, 0.05), np.inf)
            nb2 = np.where(bug == -1, b, bug)
            dauer = dauer + np.where((bug != -1) & (bug != b), wende_s, 0.0)
            if nm:                                                        # Ankunft noch vor Ende der Daemmerung
                mog &= sh0 + (sh1 - sh0) * np.where(mog, dauer, 0.0) / 3600.0 >= DAEMMERUNG
                mog &= t + np.where(mog, dauer, 0.0) <= tag_ende[tg]
                if not mog.any():
                    continue
            z2 = (tagnr(t) * N + k + versatz) * 2 + nb2
            t2 = t + dauer
            besser = mog & (t2 < ankunft[np.where(mog, z2, 0)])
            for d in np.nonzero(besser)[0]:
                zz = z2[d]
                if t2[d] < ankunft[zz]:
                    ankunft[zz] = t2[d]
                    vor[zz] = z
                    vor_d[zz] = d
                    vor_bug[zz] = bug[d]
                    vor_kurs[zz] = kurs[d]
                    vor_sog[zz] = sog[d]
                    heapq.heappush(heap, (float(t2[d]), int(zz)))
        t_dij = time.time() - t_dij
        return ankunft, vor, vor_d, vor_bug, vor_kurs, vor_sog, beste, pops, t_dij

    # Warten auf Wetter (23.11.2026): erst ohne Warten auf See; findet sich nichts, mit Warten auf See suchen, die dort
    # gewartete Zeit als spaetere Abfahrt nehmen und erneut ohne Warten auf See suchen (Wartezeit gehoert in den Hafen).
    # Bleibt Warten auf See noetig, wird diese Route genommen und im Hinweis genannt.
    def see_wartezeit(erg):
        ank, vr, vd, vs = erg[0], erg[1], erg[2], erg[5]
        z, summe = erg[6][1], 0.0
        while z is not None and z != -1 and vr[z] != -1:
            zv = int(vr[z])
            kv = (zv // 2) % N
            if vd[z] >= 0 and not (kv == ia * nx + ja or kv in liege):
                fahrt = laenge[int(vd[z])] / KN / max(float(vs[z]), 0.05) * 3600.0
                summe += max(0.0, (ank[z] - ank[zv]) - fahrt)
            z = zv
        return summe

    t_ab = float(t0)
    erg = suche(t_ab, False)
    see_gewartet_h = 0.0
    if erg[6][1] is None:
        for _ in range(4):
            mit = suche(t_ab, True)
            if mit[6][1] is None:
                break
            w_s = see_wartezeit(mit)
            if w_s < 600:
                erg = mit
                break
            t_ab += w_s
            if t_ab >= t_ende:
                erg = mit
                see_gewartet_h = w_s / 3600.0
                break
            neu = suche(t_ab, False)
            if neu[6][1] is not None:
                erg = neu
                break
            erg = mit
            see_gewartet_h = w_s / 3600.0
    ankunft, vor, vor_d, vor_bug, vor_kurs, vor_sog, beste, pops, t_dij = erg
    gefunden = beste[1]
    if gefunden is None and nm:
        raise Fehler("No route found within %d h (%d days): with 'avoid sailing at night'%s each leg must end in a harbour "
                     "or anchorage before dusk; try more hours per day, the engine, or a closer destination"
                     % (stunden, round(stunden / 24), " and max. %g h per day" % o["max_tag_h"] if o["max_tag_h"] else ""))
    if gefunden is None:
        raise Fehler("No route found within %d h (limits wind %.0f kn / waves %.1f m, land in the way, or too "
                     "little wind without engine)" % (stunden, max_wind, max_welle))

    kz = (int(gefunden) // 2) % N  # noqa
    b_versch = round(float(ab_ziel.ravel()[kz]), 1) if ab_ziel.ravel()[kz] > h * 1.5 else 0.0
    # Weg zurueckverfolgen
    kette = []
    z = gefunden
    while z != -1:
        kette.append(z)
        z = vor[z]
    kette.reverse()
    punkte = []
    naechte = []
    for idx, z in enumerate(kette):
        k, b = divmod(int(z), 2)
        k = k % N
        i, j = divmod(k, nx)
        t = float(ankunft[z])
        wu, wv, cu, cv, hs, wd = umwelt(i, j, t)
        tws_g = math.hypot(wu, wv)
        p = {"t": round(t), "la": round(float(LAT[i]), 5), "lo": round(float(LON[j]), 5),
             "tws": round(tws_g, 1), "twd": round(math.degrees(math.atan2(-wu, -wv)) % 360),
             "strom": round(math.hypot(cu, cv), 2), "strom_ri": round(math.degrees(math.atan2(cu, cv)) % 360),
             "hs": round(float(hs), 1), "_k": k}
        p["nacht"] = sonnenhoehe(float(LAT[i]), float(LON[j]), t) < -6.0          # nach buergerlicher Daemmerung
        if grund_f is not None:
            x_ = (t - T0) / 3600.0
            k_ = min(int(x_), len(zeiten) - 2)
            ht_ = HT[k_, i, j] * (1 - (x_ - k_)) + HT[k_ + 1, i, j] * (x_ - k_)
            p["tide"] = round(float(ht_), 1)
            p["tiefe"] = round(float(ht_ - grund_f[i * FEIN + mitte, j * FEIN + mitte]), 1)
        nach = kette[idx + 1] if idx + 1 < len(kette) else None
        if nach is not None and vor_d[nach] == -2:                   # Nacht am Liegeplatz
            lp = liege.get(k, {})
            p.update(kurs_kg=None, steuerkurs=None, sog=0.0, modus="nacht", twa=0, liege=lp.get("name"))
            naechte.append({"name": lp.get("name"), "art": lp.get("art"), "la": lp.get("la"), "lo": lp.get("lo"),
                            "km": lp.get("km"), "an": round(t), "ab": round(float(ankunft[nach]))})
        elif nach is not None:
            d, nb, kurs, sog = int(vor_d[nach]), int(vor_bug[nach]), float(vor_kurs[nach]), float(vor_sog[nach])
            p.update(kurs_kg=round(float(peil[d])), steuerkurs=round(kurs), sog=round(sog, 2),
                     modus="motor" if nb == -1 else ("stb" if nb == 0 else "bb"))
            woher = math.degrees(math.atan2(-(wu - cu), -(wv - cv))) % 360
            p["twa"] = round(((woher - kurs + 180) % 360) - 180)
        punkte.append(p)
    # Wartezeiten auf Wasser (Tide) sichtbar machen: Abfahrt = Ankunft am naechsten Punkt - Fahrzeit der Kante
    a = 0
    while a < len(punkte) - 1:
        p, q = punkte[a], punkte[a + 1]
        if p.get("sog"):
            fahrt = _km(p["la"], p["lo"], q["la"], q["lo"]) / KN / max(p["sog"], 0.05) * 3600.0
            luecke = (q["t"] - p["t"]) - fahrt
            if luecke > 300:
                w_ = dict(p, modus="warten", sog=0.0, kurs_kg=p["kurs_kg"])
                t_ab = round(q["t"] - fahrt)
                if nm and sonnenhoehe(p["la"], p["lo"], (p["t"] + t_ab) / 2) < DAEMMERUNG:      # Start vor Tagesanbruch
                    lp = liege.get(p["_k"], {})
                    w_.update(modus="nacht", kurs_kg=None, steuerkurs=None, twa=0, liege=lp.get("name", "start"))
                    naechte.insert(0, {"name": lp.get("name", "start"), "art": lp.get("art", "start"), "la": lp.get("la", p["la"]),
                                       "lo": lp.get("lo", p["lo"]), "km": lp.get("km", 0), "an": p["t"], "ab": t_ab})
                p["t"] = t_ab
                punkte.insert(a, w_)
                a += 1
        a += 1
    naechte.sort(key=lambda x: x["an"])
    for p in punkte:
        p.pop("_k", None)
    # Start-/Zielpunkte exakt anhaengen (Verbindung zum Gitter)
    punkte[0]["la_eingabe"], punkte[0]["lo_eingabe"] = la_a, lo_a
    punkte[-1]["la_eingabe"], punkte[-1]["lo_eingabe"] = la_b, lo_b

    # Abschnitte: gleicher Modus und aehnlicher Kurs (±20° um den ersten Kurs) zusammenfassen; die Gitterrichtungen
    # (32) erzeugen sonst ein Zickzack 108°/117°/124°. Kurs des Abschnitts = Peilung Anfang -> Ende.
    wenden = halsen = 0
    abschnitte = []
    for a, p in enumerate(punkte[:-1]):
        if (abschnitte and abschnitte[-1]["modus"] == p["modus"] and p["kurs_kg"] is not None and abschnitte[-1]["k0"] is not None
                and abs(((abschnitte[-1]["k0"] - p["kurs_kg"] + 180) % 360) - 180) <= 20):
            abschnitte[-1]["bis"] = a + 1
            continue
        abschnitte.append({"von": a, "bis": a + 1, "modus": p["modus"], "k0": p["kurs_kg"]})
    for ab in abschnitte:
        p0, p1 = punkte[ab.pop("von")], punkte[ab["bis"]]
        ab["von"] = punkte.index(p0)
        ab["kurs_kg"] = round(math.degrees(math.atan2((p1["lo"] - p0["lo"]) * math.cos(math.radians(p0["la"])), p1["la"] - p0["la"])) % 360)
        ab["sm"] = round(_km(p0["la"], p0["lo"], p1["la"], p1["lo"]) / KN, 1)
        teil = punkte[ab["von"]:ab["bis"]]
        ab["sog"] = round(ab["sm"] / max(1e-6, (p1["t"] - p0["t"]) / 3600), 1)
        ab["tws"] = round(sum(q["tws"] for q in teil) / len(teil), 1)
        ab["twa"] = round(sum(abs(q["twa"]) for q in teil) / len(teil))
        ab["strom"] = round(max(q["strom"] for q in teil), 1)
        ab["nacht"] = any(q["nacht"] for q in teil)
        if ab["modus"] == "nacht":
            ab["liege"] = p0.get("liege")
            ab["bis_t"] = p1["t"]
        ab["k0"] = None
        del ab["k0"]
    letzter = None
    for p in punkte[:-1]:
        if p["modus"] in ("stb", "bb"):
            if letzter is not None and p["modus"] != letzter:
                if abs(p["twa"]) < 90:
                    wenden += 1
                else:
                    halsen += 1
            letzter = p["modus"]
    weg_km = sum(_km(punkte[a]["la"], punkte[a]["lo"], punkte[a + 1]["la"], punkte[a + 1]["lo"]) for a in range(len(punkte) - 1))
    warten_h = sum((punkte[a + 1]["t"] - punkte[a]["t"]) for a in range(len(punkte) - 1) if punkte[a]["modus"] == "warten") / 3600
    nacht_h = sum((punkte[a + 1]["t"] - punkte[a]["t"]) for a in range(len(punkte) - 1)
                  if punkte[a]["nacht"] and punkte[a]["modus"] not in ("nacht", "warten")) / 3600
    liege_h = sum((punkte[a + 1]["t"] - punkte[a]["t"]) for a in range(len(punkte) - 1) if punkte[a]["modus"] == "nacht") / 3600
    motor_h = sum((punkte[a + 1]["t"] - punkte[a]["t"]) for a in range(len(punkte) - 1) if punkte[a]["modus"] == "motor") / 3600
    dauer_h = (punkte[-1]["t"] - punkte[0]["t"]) / 3600
    return {
        "boot": P.info(), "optionen": o,
        "start": {"t": int(t0), "la": la_a, "lo": lo_a, "verschoben": a_versch},
        "ziel": {"t": punkte[-1]["t"], "la": la_b, "lo": lo_b, "verschoben": b_versch,
                 "naechst_erreichbar_km": round(float(ab_ziel[ib, jb]), 1)},
        "dauer_h": round(dauer_h, 2), "strecke_sm": round(weg_km / KN, 1), "luftlinie_sm": round(dist / KN, 1),
        "sog_mittel": round(weg_km / KN / dauer_h, 2) if dauer_h > 0 else None,
        "wenden": wenden, "halsen": halsen, "motor_h": round(motor_h, 2), "warten_h": round(warten_h, 2), "nacht_h": round(nacht_h, 2),
        "liege_h": round(liege_h, 2), "fahrt_h": round(dauer_h - liege_h - warten_h, 2), "naechte": naechte,
        "abfahrt": next((q["t"] for q in punkte if q["modus"] not in ("nacht", "warten")), punkte[0]["t"]),
        "punkte": punkte, "abschnitte": abschnitte,
        "gitter": {"km": round(h, 3), "nx": nx, "ny": ny, "s": s, "n": n, "w": w, "e": e},
        "quellen": {"wind": "Open-Meteo best_match (regional models, hourly)", "wellen": "Open-Meteo Marine",
                    "strom": "Tidal current layer (TPXO10 + fine models)" + (" + Copernicus GLO12 ocean current" if o["ozean"] else ""),
                    "land": "OpenStreetMap land polygons", "fluesse": fluss_info, "tiefe": tiefe_info, "windstau": stau_info, "vtg": vtg_info, "sperr": sperr_info, "polare": P.info()["quelle"]},
        "hinweise": ((["Depth = EMODnet (LAT) + predicted tide from nearby gauges at the time of passage"
                       + ("; storm surge forecast included (%s), keep the reserve." % stau_info if stau_info.startswith(("Copernicus", "NOAA"))
                          else "; storm surge NOT included (%s), keep the reserve." % stau_info)] if "tide height" in tiefe_info else
                      ["Shallow water is avoided as at chart datum (lowest tide)."]) if tiefe_info.startswith("EMODnet")
                     else ["Water depth is NOT considered."])
                    + ([("Rivers behind the coastline: depth from SHOM survey models where available, elsewhere "
                         "unknown; keep to the buoyed fairway.") if "SHOM" in fluss_info else
                        "Rivers behind the coastline: depth unknown; keep to the buoyed fairway."] if fluss_info != "off" else [])
                    + (["Departure delayed by %.1f h to wait for wind/waves below your limits (%.0f kn / %.1f m)."
                        % ((t_ab - t0) / 3600.0, max_wind, max_welle)] if t_ab > t0 else [])
                    + (["The route still waits %.1f h at sea for the weather - better choose another day or harbour."
                        % see_gewartet_h] if see_gewartet_h > 0 else [])
                    + (["Traffic separation schemes (OpenSeaMap): lanes only with the traffic or crossing at right angles, "
                        "separation zones only crossed."] if vtg_info.startswith("OpenSeaMap") else [])
                    + (["No-entry areas (OpenSeaMap) are avoided; check notices to mariners for temporary closures."]
                       if sperr_info.startswith("OpenSeaMap") else ["Restricted areas are NOT considered."])
                    + (["Areas with entry restrictions nearby (season/permit): " + ", ".join(auflagen[:6])] if auflagen else []),
        "rechenzeit": {"umwelt_s": round(t_um, 1), "dijkstra_s": round(t_dij, 1), "gesamt_s": round(time.time() - uhr, 1),
                       "schritte": pops},
    }


if __name__ == "__main__":
    import json
    a = [float(x) for x in sys.argv[1:5]]
    t0 = time.time() if len(sys.argv) < 6 else dt.datetime.fromisoformat(sys.argv[5]).replace(tzinfo=dt.timezone.utc).timestamp()
    opt = {}
    for kv in sys.argv[6:]:
        k_, v_ = kv.split("=", 1)
        opt[k_] = v_ == "1" if v_ in ("0", "1") else float(v_)
    r = route((a[0], a[1]), (a[2], a[3]), t0, **opt)
    kurz = {k: v for k, v in r.items() if k not in ("punkte", "abschnitte")}
    print(json.dumps(kurz, indent=1, ensure_ascii=False))
    for ab in r["abschnitte"]:
        p = r["punkte"][ab["von"]]
        print("%s  %-6s KüG %3s°  %4.1f sm  SOG %4.1f  TWS %4.1f TWA %4d  Strom max %.1f %s" % (
            dt.datetime.fromtimestamp(p["t"], dt.timezone.utc).strftime("%d. %H:%M"), ab["modus"], ab["kurs_kg"], ab["sm"],
            ab["sog"], ab["tws"], ab["twa"], ab["strom"], ab.get("liege") or ""))
