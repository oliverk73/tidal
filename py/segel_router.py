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
NICHT beruecksichtigt (Stand 20.11.): Tide bei der Tiefe (Watt bei Hochwasser), Verkehrstrennungsgebiete, Sperrgebiete, Nacht.

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
import segel_tiefe  # noqa: E402
import segel_polare  # noqa: E402

KN = 1.852                    # km je sm
OM_CACHE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "quellen", "routing", "om_cache")
MAX_KNOTEN = 240              # Gitterknoten je Achse
FEIN = 3                      # Landraster feiner als das Gitter (Kantenpruefung)
# 32 Richtungen: (Zeile, Spalte); Zeile waechst nach Sueden
_BASIS = [(1, 0), (1, 1), (2, 1), (3, 1), (3, 2)]
RICHT = sorted({(a * s1, b * s2) for a, b in _BASIS for s1 in (1, -1) for s2 in (1, -1)}
               | {(b * s1, a * s2) for a, b in _BASIS for s1 in (1, -1) for s2 in (1, -1)})
RICHT = [r for r in RICHT if r != (0, 0)]
assert len(RICHT) == 32, len(RICHT)

STANDARD = dict(leistung=0.85, motor=True, motor_kn=5.5, motor_unter=3.0, max_wind=25.0, max_welle=2.5,
                wendezeit_s=60.0, ozean=True, tiefe=True, reserve_m=0.5, ohne_spi=True)


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
    if dist > 300:
        raise Fehler("Day-trip router: start and destination must be within 300 km (160 nm)")
    # Gebiet: Rechteck um A und B mit Rand
    rand = max(0.35 * dist, 10.0)
    la0 = (la_a + la_b) / 2
    kx = 111.2 * math.cos(math.radians(la0))
    s, n = min(la_a, la_b) - rand / 111.2, max(la_a, la_b) + rand / 111.2
    w, e = min(lo_a, lo_b) - rand / kx, max(lo_a, lo_b) + rand / kx
    h = max(0.12, max((n - s) * 111.2, (e - w) * kx) / MAX_KNOTEN)      # Gitterweite km
    ny, nx = int(math.ceil((n - s) * 111.2 / h)), int(math.ceil((e - w) * kx / h))
    n, e = s + ny * h / 111.2, w + nx * h / kx                         # Rechteck genau auf das Gitter
    LAT = n - (np.arange(ny) + 0.5) * h / 111.2
    LON = w + (np.arange(nx) + 0.5) * h / kx
    LAT2, LON2 = np.meshgrid(LAT, LON, indexing="ij")

    # Land (fein) und erlaubte Kanten
    land_f = segel_land.raster(s, n, w, e, ny * FEIN, nx * FEIN)
    # Wassertiefe (EMODnet, Seekartennull): gesperrt, wo der flachste Grund hoeher liegt als -(Tiefgang + Reserve).
    # Vorsichtig = wie bei Niedrigwasser Springzeit; Watt und Barren werden immer umfahren (Tide noch nicht beruecksichtigt).
    tiefgang = float(P.info().get("tiefgang") or 2.0)
    tiefe_info = "off"
    if o["tiefe"]:
        hoehe_f = segel_tiefe.flachstes(s, n, w, e, ny * FEIN, nx * FEIN)
        if hoehe_f is None:
            tiefe_info = "no data (EMODnet covers Europe only)"
        else:
            flach = np.nan_to_num(hoehe_f, nan=-999.0) > -(tiefgang + o["reserve_m"])
            land_f = land_f | flach
            tiefe_info = "EMODnet, chart datum (LAT), draft %.1f m + %.1f m" % (tiefgang, o["reserve_m"])
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
    II, JJ = np.meshgrid(np.arange(ny), np.arange(nx), indexing="ij")
    for d, (di, dj) in enumerate(RICHT):
        i2, j2 = II + di, JJ + dj
        ok = wasser & (i2 >= 0) & (i2 < ny) & (j2 >= 0) & (j2 < nx)
        schritte = int(math.ceil(math.hypot(di, dj) * FEIN * 1.5))
        for q in range(1, schritte + 1):
            f = q / schritte
            fi = np.clip(np.round((II + f * di) * FEIN + mitte).astype(int), 0, ny * FEIN - 1)
            fj = np.clip(np.round((JJ + f * dj) * FEIN + mitte).astype(int), 0, nx * FEIN - 1)
            ok &= ~land_f[fi, fj]
        gueltig[d] = ok
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

    # Zeitfenster: geschaetzte Dauer bei 3 kn ueber Grund x 1,5, 12–36 h
    stunden = int(min(36, max(12, math.ceil(dist / KN / 3.0 * 1.5) + 2)))       # Kreuz gegen Strom braucht Reserve
    T0 = math.floor(t0 / 3600) * 3600
    zeiten = T0 + 3600.0 * np.arange(stunden + 2)
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

    # Dijkstra ueber (Knoten, Bug)
    N = ny * nx
    ankunft = np.full(2 * N, np.inf)
    vor = np.full(2 * N, -1, dtype=np.int64)
    vor_d = np.full(2 * N, -1, dtype=np.int8)
    vor_bug = np.zeros(2 * N, dtype=np.int8)
    vor_kurs = np.zeros(2 * N, dtype=np.float32)
    vor_sog = np.zeros(2 * N, dtype=np.float32)
    t_ende = zeiten[-2]
    heap = []
    for b in (0, 1):
        z0 = (ia * nx + ja) * 2 + b
        ankunft[z0] = float(t0)
        heapq.heappush(heap, (float(t0), z0))
    erledigt = np.zeros(2 * N, dtype=bool)
    gefunden = None
    pops = 0
    versatz = np.array([di * nx + dj for di, dj in RICHT], dtype=np.int64)
    dauer0 = laenge / KN * 3600.0                                          # s bei 1 kn
    wende_s = wende_h * 3600.0
    t_dij = time.time()
    beste = (np.inf, None)
    while heap:
        t, z = heapq.heappop(heap)
        if t >= beste[0]:                                             # kein Kandidat kann noch besser werden
            break
        if erledigt[z]:
            continue
        erledigt[z] = True
        pops += 1
        k, b = divmod(z, 2)
        if ziel_menge_flach[k]:
            # Bewertung = Ankunft + Rest bei 0,5 kn (teurer als fast jeder echte Weg, auch die Kreuz): ein naeherer Punkt gewinnt, wenn der Weg dorthin weniger kostet
            # als die gesparte Reststrecke; weitersuchen, bis keine Ankunft die beste Bewertung noch schlagen kann
            if t + rest_s[k] < beste[0]:
                beste = (t + rest_s[k], z)
            # weiter ausbauen: naehere Zielpunkte liegen oft nur hinter diesem (Ring um das Ziel)
        if t >= t_ende:
            continue
        i, j = divmod(k, nx)
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
        z2 = (k + versatz) * 2 + nb2
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
    gefunden = beste[1]
    if gefunden is None:
        raise Fehler("No route found within %d h (limits wind %.0f kn / waves %.1f m, land in the way, or too "
                     "little wind without engine)" % (stunden, max_wind, max_welle))

    kz = int(gefunden) // 2  # noqa
    b_versch = round(float(ab_ziel.ravel()[kz]), 1) if ab_ziel.ravel()[kz] > h * 1.5 else 0.0
    # Weg zurueckverfolgen
    kette = []
    z = gefunden
    while z != -1:
        kette.append(z)
        z = vor[z]
    kette.reverse()
    punkte = []
    for idx, z in enumerate(kette):
        k, b = divmod(int(z), 2)
        i, j = divmod(k, nx)
        t = float(ankunft[z])
        wu, wv, cu, cv, hs, wd = umwelt(i, j, t)
        tws_g = math.hypot(wu, wv)
        p = {"t": round(t), "la": round(float(LAT[i]), 5), "lo": round(float(LON[j]), 5),
             "tws": round(tws_g, 1), "twd": round(math.degrees(math.atan2(-wu, -wv)) % 360),
             "strom": round(math.hypot(cu, cv), 2), "strom_ri": round(math.degrees(math.atan2(cu, cv)) % 360),
             "hs": round(float(hs), 1)}
        nach = kette[idx + 1] if idx + 1 < len(kette) else None
        if nach is not None:
            d, nb, kurs, sog = int(vor_d[nach]), int(vor_bug[nach]), float(vor_kurs[nach]), float(vor_sog[nach])
            p.update(kurs_kg=round(float(peil[d])), steuerkurs=round(kurs), sog=round(sog, 2),
                     modus="motor" if nb == -1 else ("stb" if nb == 0 else "bb"))
            woher = math.degrees(math.atan2(-(wu - cu), -(wv - cv))) % 360
            p["twa"] = round(((woher - kurs + 180) % 360) - 180)
        punkte.append(p)
    # Start-/Zielpunkte exakt anhaengen (Verbindung zum Gitter)
    punkte[0]["la_eingabe"], punkte[0]["lo_eingabe"] = la_a, lo_a
    punkte[-1]["la_eingabe"], punkte[-1]["lo_eingabe"] = la_b, lo_b

    # Abschnitte: gleicher Modus und aehnlicher Kurs (±20° um den ersten Kurs) zusammenfassen; die Gitterrichtungen
    # (32) erzeugen sonst ein Zickzack 108°/117°/124°. Kurs des Abschnitts = Peilung Anfang -> Ende.
    wenden = halsen = 0
    abschnitte = []
    for a, p in enumerate(punkte[:-1]):
        if abschnitte and abschnitte[-1]["modus"] == p["modus"] and abs(((abschnitte[-1]["k0"] - p["kurs_kg"] + 180) % 360) - 180) <= 20:
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
    motor_h = sum((punkte[a + 1]["t"] - punkte[a]["t"]) for a in range(len(punkte) - 1) if punkte[a]["modus"] == "motor") / 3600
    dauer_h = (punkte[-1]["t"] - punkte[0]["t"]) / 3600
    return {
        "boot": P.info(), "optionen": o,
        "start": {"t": int(t0), "la": la_a, "lo": lo_a, "verschoben": a_versch},
        "ziel": {"t": punkte[-1]["t"], "la": la_b, "lo": lo_b, "verschoben": b_versch,
                 "naechst_erreichbar_km": round(float(ab_ziel[ib, jb]), 1)},
        "dauer_h": round(dauer_h, 2), "strecke_sm": round(weg_km / KN, 1), "luftlinie_sm": round(dist / KN, 1),
        "sog_mittel": round(weg_km / KN / dauer_h, 2) if dauer_h > 0 else None,
        "wenden": wenden, "halsen": halsen, "motor_h": round(motor_h, 2),
        "punkte": punkte, "abschnitte": abschnitte,
        "gitter": {"km": round(h, 3), "nx": nx, "ny": ny, "s": s, "n": n, "w": w, "e": e},
        "quellen": {"wind": "Open-Meteo best_match (regional models, hourly)", "wellen": "Open-Meteo Marine",
                    "strom": "Tidal current layer (TPXO10 + fine models)" + (" + Copernicus GLO12 ocean current" if o["ozean"] else ""),
                    "land": "OpenStreetMap land polygons", "tiefe": tiefe_info, "polare": P.info()["quelle"]},
        "hinweise": (["Shallow water is avoided as at chart datum (lowest tide); passages over flats at high water are not "
                      "considered yet."] if tiefe_info.startswith("EMODnet") else ["Water depth is NOT considered."])
                    + ["Traffic separation schemes and restricted areas are NOT considered."],
        "rechenzeit": {"umwelt_s": round(t_um, 1), "dijkstra_s": round(t_dij, 1), "gesamt_s": round(time.time() - uhr, 1),
                       "schritte": pops},
    }


if __name__ == "__main__":
    import json
    a = [float(x) for x in sys.argv[1:5]]
    t0 = time.time() if len(sys.argv) < 6 else dt.datetime.fromisoformat(sys.argv[5]).replace(tzinfo=dt.timezone.utc).timestamp()
    r = route((a[0], a[1]), (a[2], a[3]), t0)
    kurz = {k: v for k, v in r.items() if k not in ("punkte", "abschnitte")}
    print(json.dumps(kurz, indent=1, ensure_ascii=False))
    for ab in r["abschnitte"]:
        p = r["punkte"][ab["von"]]
        print("%s  %-5s KüG %3d°  %4.1f sm  SOG %4.1f  TWS %4.1f TWA %4d  Strom max %.1f" % (
            dt.datetime.fromtimestamp(p["t"], dt.timezone.utc).strftime("%H:%M"), ab["modus"], ab["kurs_kg"], ab["sm"],
            ab["sog"], ab["tws"], ab["twa"], ab["strom"]))
