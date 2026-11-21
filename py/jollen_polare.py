#!/usr/bin/env python3
"""
Polaren fuer Jollen (Oliver 21.11.2026: ILCA, 470er u. a. fehlten im Routenplaner – ORC vermisst nur Kielboote).

Verfahren: vereinfachtes Jollen-VPP nach Day et al. 2017 ("Performance prediction for sailing dinghies", Ocean
Engineering; strathprints 59980), je Windstaerke und Kurs Gleichgewicht Vortrieb = Widerstand:
  * Segel: ORC-aehnliche Auftriebs-/Widerstandsbeiwerte ueber dem scheinbaren Windwinkel, induzierter Widerstand,
    Spinnaker (symmetrisch ab AWA 60°) bzw. Gennaker (ab 50°) zusaetzlich, wo die Klasse einen hat;
  * Abflachen: Auftrieb wird so weit reduziert, dass das Kraengungsmoment das Aufrichtmoment der Crew
    (Ausreiten / Trapez / Doppeltrapez, Hebel aus Breite) nicht uebersteigt;
  * Rumpf: Reibung (ITTC) + Restwiderstand mit Gleitbuckel (Fn 0,55; nur ueberwindbar, wenn der Vortrieb reicht),
    Schwert: induzierter Widerstand aus der Querkraft.
Eichung: (1) global am ILCA 7 mit 80-kg-Segler (Day 2017 Abb. 8: VMG amwind/vorm Wind 6–16 kn, gegen Messungen
Binns et al. 2002 geprueft); (2) je Klasse ein Widerstandsfaktor, so dass die Kurszeit (Up-and-Down + Raum, Wind
6/10/14 kn) im Verhaeltnis zum ILCA 7 der Yardstick-Zahl entspricht (RYA PN 2026; fehlende aus der deutschen
Yardstick-Skala ueber die gemeinsamen Klassen umgerechnet).
Amwindwinkel = Winkel des besten VMG je Windstaerke (Laser laut Day 2017: 40–46° in glattem Wasser).

Ausgabe: quellen/routing/polare/jollen/<id>.json im Format eines ORC-Zertifikats ("Allowances": s/sm), dazu
quellen/routing/jollen_katalog.json; segel_polare.py liest beides.

Aufruf: venv/bin/python py/jollen_polare.py [--eichen] [klasse ...]
"""
import json
import math
import os
import sys

import numpy as np
from scipy.optimize import minimize

BASIS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORDNER = os.path.join(BASIS, "quellen", "routing", "polare", "jollen")
KATALOG = os.path.join(BASIS, "quellen", "routing", "jollen_katalog.json")
RHO_W, RHO_L, G, NU = 1025.0, 1.225, 9.81, 1.19e-6
KN = 0.514444

# id, Name, Crew, Trapez (0, 1 = einer im Trapez, 2 = alle), LOA m, Breite m (Hebel; 49er mit Fluegeln),
# Masse segelfertig kg, Amwind-Segelflaeche m², Spi-Art, Spi m², RYA-PN (None -> aus YS), YS (deutsch), Crewgewicht kg, Tiefgang m
# Quellen: Wikipedia-Infoboxen (en/de, 21.11.2026), RYA PN List 2026 (Version 2), Forggensee-Yardstick 2019, DSV-YS (Pirat/Korsar lt. de.wikipedia)
KLASSEN = [
    ("ilca-4", "ILCA 4 / Laser 4.7", 1, 0, 4.20, 1.39, 70, 4.70, None, 0, 1218, 125, 60, 0.85),
    ("ilca-6", "ILCA 6 / Laser Radial", 1, 0, 4.20, 1.39, 70, 5.76, None, 0, 1156, 114, 70, 0.85),
    ("ilca-7", "ILCA 7 / Laser Standard", 1, 0, 4.20, 1.39, 70, 7.06, None, 0, 1103, 113, 82, 0.85),
    ("finn", "Finn", 1, 0, 4.50, 1.47, 120, 10.6, None, 0, 1049, 110, 95, 0.85),
    ("ok-jolle", "OK-Jolle / OK Dinghy", 1, 0, 4.00, 1.42, 82, 8.95, None, 0, 1092, None, 85, 0.85),
    ("europe", "Europe", 1, 0, 3.35, 1.38, 60, 7.0, None, 0, 1140, 116, 65, 0.85),
    ("contender", "Contender", 1, 1, 4.88, 1.50, 95, 10.8, None, 0, 973, 105, 80, 0.95),
    ("rs-aero-7", "RS Aero 7", 1, 0, 4.00, 1.40, 40, 7.4, None, 0, 1062, None, 75, 0.85),
    ("optimist", "Optimist", 1, 0, 2.31, 1.13, 45, 3.3, None, 0, 1629, 173, 42, 0.75),
    ("topper", "Topper", 1, 0, 3.40, 1.20, 51, 5.2, None, 0, 1369, None, 55, 0.80),
    ("musto-skiff", "Musto Performance Skiff", 1, 1, 4.55, 1.35, 60, 11.08, "asym", 15.5, 830, 93, 80, 1.0),
    ("solo", "Solo", 1, 0, 3.78, 1.55, 78, 8.36, None, 0, 1139, None, 80, 0.85),
    ("420", "420er", 2, 1, 4.20, 1.63, 100, 10.25, "sym", 8.83, 1110, 115, 115, 0.97),
    ("470", "470er", 2, 1, 4.70, 1.69, 140, 12.7, "sym", 13.0, 973, 103, 130, 0.97),
    ("29er", "29er", 2, 1, 4.45, 1.77, 85, 12.5, "asym", 16.2, 900, 95, 120, 1.0),
    ("49er", "49er", 2, 2, 4.88, 2.90, 119, 21.2, "asym", 38.0, None, 81, 150, 1.45),
    ("505", "505er", 2, 1, 5.05, 1.88, 147, 17.3, "sym", 27.0, 892, 95, 155, 1.0),
    ("flying-dutchman", "Flying Dutchman", 2, 1, 6.05, 1.80, 155, 17.0, "sym", 21.0, None, 94, 160, 1.1),
    ("fireball", "Fireball", 2, 1, 4.93, 1.37, 94, 11.43, "sym", 13.0, 960, None, 140, 1.0),
    ("snipe", "Snipe", 2, 0, 4.72, 1.52, 172, 11.8, None, 0, 1104, None, 140, 1.0),
    ("pirat", "Pirat", 2, 0, 5.00, 1.61, 218, 10.0, None, 0, None, 110, 150, 1.05),
    ("korsar", "Korsar", 2, 1, 5.00, 1.70, 150, 14.7, "sym", 14.8, None, 103, 150, 1.0),
    ("rs200", "RS200", 2, 0, 4.00, 1.83, 93, 11.6, "asym", 10.0, 1053, None, 125, 1.0),
    ("rs400", "RS400", 2, 0, 4.52, 1.84, 142, 14.8, "asym", 13.9, 945, None, 150, 1.0),
    ("rs-feva-xl", "RS Feva XL", 2, 0, 3.64, 1.42, 73, 7.3, "asym", 6.8, 1248, None, 95, 0.9),
    ("laser-2000", "Laser 2000", 2, 0, 4.44, 1.77, 112, 11.7, "asym", 10.12, 1122, 108, 140, 1.0),
    ("wayfarer", "Wayfarer", 2, 0, 4.83, 1.86, 184, 11.6, "sym", 13.5, 1107, None, 160, 1.1),
    ("enterprise", "Enterprise", 2, 0, 4.04, 1.60, 106, 10.5, None, 0, 1137, None, 140, 1.0),
    ("gp14", "GP14", 2, 0, 4.27, 1.53, 144, 12.8, "sym", 8.4, 1145, None, 145, 1.0),
    ("albacore", "Albacore", 2, 0, 4.57, 1.55, 121, 11.61, None, 0, 1037, None, 150, 1.0),
    ("cadet", "Cadet", 2, 0, 3.22, 1.38, 62, 5.16, "sym", 4.25, 1455, None, 85, 0.9),
    ("mirror", "Mirror", 2, 0, 3.30, 1.39, 56, 6.5, "sym", 4.4, 1364, None, 110, 0.9),
    ("scorpion", "Scorpion", 2, 0, 4.27, 1.45, 93, 9.95, "sym", 11.14, 1042, None, 135, 1.0),
    ("national-12", "National 12", 2, 0, 3.66, 1.98, 78, 10.4, None, 0, 1070, None, 125, 1.0),
    ("lark", "Lark", 2, 0, 4.07, 1.64, 105, 9.75, "sym", 7.4, 1060, None, 130, 1.0),
    ("laser-vago", "Laser Vago", 2, 0, 4.20, 1.56, 110, 10.34, "asym", 10.85, 1074, None, 140, 1.0),
    ("streaker", "Streaker", 1, 0, 3.90, 1.40, 58, 7.0, None, 0, 1121, None, 80, 0.85),
]
FELDER = ("id", "name", "crew", "trapez", "loa", "breite", "masse", "sa", "spi_art", "spi", "pn", "ys", "crew_kg", "tiefgang")

# Segelbeiwerte Gross+Fock (ORC-aehnlich, ohne induzierten Anteil) ueber AWA
AWA = np.array([0, 15, 20, 25, 28, 32, 40, 50, 60, 70, 80, 90, 100, 110, 120, 140, 160, 180.0])
CL = np.array([0, 0.00, 0.40, 1.00, 1.25, 1.38, 1.42, 1.43, 1.43, 1.42, 1.40, 1.35, 1.25, 1.10, 0.95, 0.60, 0.30, 0.10])   # < 20° AWA killt das Vorliek (Day: AWA 27–33°)
CD = np.array([0.04, 0.04, 0.05, 0.06, 0.07, 0.08, 0.10, 0.14, 0.20, 0.28, 0.38, 0.50, 0.62, 0.74, 0.86, 1.08, 1.25, 1.35])   # 180°: ORC 1,345 (Day 2017)
SPI_AWA = np.array([40, 50, 55, 75, 90, 110, 130, 150, 180.0])
SPI_CL = np.array([0, 0.0, 0.9, 1.45, 1.45, 1.30, 1.05, 0.75, 0.45])
SPI_CD = np.array([0.2, 0.25, 0.3, 0.45, 0.6, 0.8, 0.95, 1.05, 1.10])
FN = np.array([0, 0.2, 0.3, 0.35, 0.4, 0.45, 0.5, 0.55, 0.65, 0.8, 1.0, 1.4, 2.0, 3.0])
GFN = np.array([0, 0.03, 0.10, 0.20, 0.38, 0.60, 0.85, 1.0, 0.95, 0.82, 0.72, 0.70, 0.75, 0.85])

# Anker ILCA 7, 80 kg (Day 2017 Abb. 8, abgelesen): TWS -> (VMG amwind, VMG vorm Wind) kn
ANKER = {6: (2.7, 3.0), 8: (3.3, 3.85), 10: (3.65, 4.55), 12: (3.75, 5.2), 14: (3.8, 5.95), 16: (3.85, 6.75)}
GLOBAL = {"cl": 1.0, "rpeak": 0.10, "ar": 3.0}          # durch --eichen ersetzt (EICHUNG unten)
EICHUNG = os.path.join(BASIS, "quellen", "routing", "jollen_eichung.json")
WIND = [4, 6, 8, 10, 12, 14, 16, 20, 24]
WINKEL = [52, 60, 75, 90, 110, 120, 135, 150]


def klasse(kid):
    return dict(zip(FELDER, next(k for k in KLASSEN if k[0] == kid)))


class Boot:
    def __init__(self, k, glob, kfak=1.0):
        self.k, self.g, self.kfak = k, glob, kfak
        self.lwl = 0.93 * k["loa"]
        self.delta = k["masse"] + k["crew_kg"] + 5
        self.sw = 0.62 * self.lwl * min(k["breite"], 1.9)
        self.hce = 0.85 * math.sqrt(k["sa"]) + 0.4 + 0.3
        n = k["crew"]
        per = k["crew_kg"] / n
        heb = []
        for i in range(n):
            trapez = k["trapez"] == 2 or (k["trapez"] == 1 and i == n - 1)
            heb.append(0.5 * k["breite"] + (0.95 if trapez else 0.35))
        self.rm = G * per * sum(heb) + G * k["masse"] * 0.06 * k["breite"]
        c = self.delta / (RHO_W * self.lwl ** 3)
        self.rpeak = glob["rpeak"] * (c / 0.0026) ** 0.6
        # Gleitfaehigkeit nach dem Buckel (21.11.: Opti/Pirat glitten sonst wie ein Laser): Laser/Skiff (c <= 0,0026)
        # voll, ab c = 0,0045 gar nicht (Widerstand steigt hinter dem Buckel weiter: Wellenwand)
        self.gleit = float(np.clip((0.0045 - c) / (0.0045 - 0.0026), 0, 1))

    def widerstand(self, v, quer):
        if v <= 0:
            return 0.0
        re_ = max(v * self.lwl / NU, 1e4)
        cf = 0.075 / (math.log10(re_) - 2) ** 2
        rf = 0.5 * RHO_W * v * v * (self.sw * 1.1 + 0.5) * cf
        fn = v / math.sqrt(G * self.lwl)
        g_ = np.interp(fn, FN, GFN)
        if fn > 0.55:                                          # hinter dem Buckel: gleiten oder Wellenwand
            g_ = self.gleit * g_ + (1 - self.gleit) * (1.0 + 2.5 * (fn - 0.55))
        rr = self.delta * G * self.rpeak * g_
        span = self.k["tiefgang"] * 0.9
        ri = quer ** 2 / (0.5 * RHO_W * v * v * math.pi * span ** 2)
        return self.kfak * (rf + rr) + ri

    def aero(self, v, tws, twa, spi):
        """-> (Vortrieb, Querkraft) N bei Bootsfahrt v (m/s), Abflachen so weit, dass Moment <= Aufrichtmoment."""
        tw = tws * KN
        a = math.radians(twa)
        ax, ay = tw * math.cos(a) + v, tw * math.sin(a)
        aws = math.hypot(ax, ay)
        awa = math.degrees(math.atan2(ay, ax))
        q = 0.5 * RHO_L * aws * aws
        cl = np.interp(awa, AWA, CL) * self.g["cl"]
        cd = np.interp(awa, AWA, CD)
        sa = self.k["sa"]
        if spi and self.k["spi"]:
            ab = 50 if self.k["spi_art"] == "asym" else 60
            if awa >= ab:
                f_ = 1.0 if self.k["spi_art"] == "sym" or awa <= 150 else 0.8
                cs, ds = np.interp(awa, SPI_AWA, SPI_CL) * f_, np.interp(awa, SPI_AWA, SPI_CD) * f_
                cl = (cl * sa + cs * self.k["spi"]) / sa
                cd = (cd * sa + ds * self.k["spi"]) / sa
        b = math.radians(awa)
        best = None
        for fl in np.linspace(1.0, 0.05, 39):
            cl_ = cl * fl
            cdi = cl_ * cl_ / (math.pi * self.g["ar"])
            # amwind (AWA <= 45°): Twist zum Entlasten kostet Formwiderstand; raumschots: Schot fieren senkt Auftrieb
            # UND Formwiderstand (21.11.: sonst blieb der ILCA bei 24 kn halbwind am Gleitbuckel haengen)
            cd_ = (cd * (0.85 + 0.15 * fl) if awa <= 45 else cd * (0.25 + 0.75 * fl)) + cdi
            lift, drag = q * sa * cl_, q * sa * cd_
            vor = lift * math.sin(b) - drag * math.cos(b)
            quer = lift * math.cos(b) + drag * math.sin(b)
            if quer * (self.hce + 0.4) <= self.rm or fl <= 0.06:
                if best is None or vor > best[0]:
                    best = (vor, quer)
                break
        return best

    def fahrt(self, tws, twa):
        """kn; erste Nullstelle von Vortrieb - Widerstand von unten (Gleitbuckel ist eine echte Schwelle)."""
        out = 0.0
        for spi in ([False, True] if self.k["spi"] else [False]):
            # Start bei 1/4 Windgeschwindigkeit: darunter macht das Boot Abdrift statt Fahrt (der induzierte
            # Schwertwiderstand ~ 1/v² waere sonst eine kuenstliche Sperre); der Gleitbuckel darueber bleibt Schwelle
            v, dv = max(0.1, 0.25 * tws * KN), 0.05
            vor, quer = self.aero(v, tws, twa, spi)
            if vor - self.widerstand(v, quer) <= 0:                 # schon am Start zu wenig Vortrieb: abwaerts suchen
                while v > 0.1:
                    v -= dv
                    vor, quer = self.aero(v, tws, twa, spi)
                    if vor - self.widerstand(v, quer) > 0:
                        break
            else:
                while v < 15:
                    vor, quer = self.aero(v, tws, twa, spi)
                    if vor - self.widerstand(v, quer) <= 0:
                        break
                    v += dv
            out = max(out, v / KN)
        return out

    def vmg(self, tws):
        up = max(((self.fahrt(tws, a) * math.cos(math.radians(a)), a) for a in range(32, 66, 2)))
        dn = max(((-self.fahrt(tws, a) * math.cos(math.radians(a)), a) for a in range(110, 181, 5)))
        return up, dn


def kurszeit(b, winde=(6, 10, 14)):
    """Stunden fuer einen Kurs: 2 sm Kreuz + 1 sm halber Wind + 1 sm raumschots (135°) + 2 sm Vorwind (VMG)."""
    t = 0.0
    for w in winde:
        (vu, _a), (vd, _b) = b.vmg(w)
        t += 2 / vu + 1 / b.fahrt(w, 90) + 1 / b.fahrt(w, 135) + 2 / vd
    return t


def eichen():
    k = klasse("ilca-7")

    def fehler(x):
        g = {"cl": x[0], "rpeak": x[1], "ar": x[2]}
        if min(x) <= 0:
            return 99
        b = Boot(k, g)
        e = 0.0
        for w, (u, d) in ANKER.items():
            (vu, _), (vd, _) = b.vmg(w)
            e += (vu - u) ** 2 + 0.5 * (vd - d) ** 2
        return e
    r = minimize(fehler, [1.0, 0.10, 3.0], method="Nelder-Mead", options={"xatol": 1e-3, "fatol": 1e-4, "maxiter": 200})
    g = {"cl": float(r.x[0]), "rpeak": float(r.x[1]), "ar": float(r.x[2]), "rest": float(r.fun)}
    json.dump(g, open(EICHUNG, "w"), indent=1)
    return g


def pn_aus_ys():
    """Lineare Umrechnung deutsche Yardstick-Zahl -> RYA-PN ueber Klassen mit beiden Werten."""
    p = [(k[11], k[10]) for k in KLASSEN if k[10] and k[11]]
    x, y = np.array(p, dtype=float).T
    a, c = np.polyfit(x, y, 1)
    return lambda ys: a * ys + c, len(p)


def tabelle(b):
    """ORC-Allowances-Format: s/sm je Windstaerke."""
    A = {"WindSpeeds": WIND, "WindAngles": WINKEL, "Beat": [], "BeatAngle": [], "DW165": [], "DW180": [],
         "Run": [], "GybeAngle": []}
    for w in WINKEL:
        A["R%d" % w] = []
    # Amwindwinkel: VMG-Optimum in 1°-Schritten ist flach und springt -> ueber die Windstaerken glaetten (gleitendes
    # Mittel aus 3), nicht unter 36° (Laser 40–46° lt. Day 2017; < 36° waere Kneifen)
    roh = []
    for w in WIND:
        roh.append(max(((b.fahrt(w, a) * math.cos(math.radians(a)), a) for a in range(34, 56)))[1])
    glatt = [max(36.0, float(np.mean(roh[max(0, i - 1):i + 2]))) for i in range(len(roh))]
    for i, w in enumerate(WIND):
        au = round(glatt[i])
        vu = b.fahrt(w, au) * math.cos(math.radians(au))
        _u, (vd, ad) = b.vmg(w)
        A["Beat"].append(round(3600 / vu, 1))
        A["BeatAngle"].append(float(au))
        A["Run"].append(round(3600 / vd, 1))
        A["GybeAngle"].append(float(ad))
        for a in WINKEL:
            A["R%d" % a].append(round(3600 / max(b.fahrt(w, a), 0.05), 1))
        A["DW165"].append(round(3600 / max(b.fahrt(w, 165), 0.05), 1))
        A["DW180"].append(round(3600 / max(b.fahrt(w, 180), 0.05), 1))
    return A


def main(argv):
    os.makedirs(ORDNER, exist_ok=True)
    g = eichen() if "--eichen" in argv or not os.path.exists(EICHUNG) else json.load(open(EICHUNG))
    print("Eichung ILCA 7: Auftrieb x%.3f, Gleitbuckel %.3f, Seitenverhaeltnis %.2f (Rest %.3f)" % (
        g["cl"], g["rpeak"], g["ar"], g.get("rest", 0)))
    b0 = Boot(klasse("ilca-7"), g)
    for w in sorted(ANKER):
        (vu, au), (vd, ad) = b0.vmg(w)
        print("  ILCA 7 %2d kn: VMG amwind %.2f (Anker %.2f) bei %d°, vorm Wind %.2f (Anker %.2f) bei %d°" % (
            w, vu, ANKER[w][0], au, vd, ANKER[w][1], ad))
    umr, n = pn_aus_ys()
    t0, pn0 = kurszeit(b0), klasse("ilca-7")["pn"]
    wahl = [a for a in argv if not a.startswith("--")]
    katalog = []
    for kt in KLASSEN:
        k = dict(zip(FELDER, kt))
        if wahl and k["id"] not in wahl:
            continue
        pn = k["pn"] or round(umr(k["ys"]))
        ziel = t0 * pn / pn0
        lo, hi = 0.2, 5.0                                       # Widerstandsfaktor per Bisektion auf die Kurszeit
        for _ in range(22):
            m = math.sqrt(lo * hi)
            if kurszeit(Boot(k, g, m)) < ziel:
                lo = m
            else:
                hi = m
        kf = math.sqrt(lo * hi)
        b = Boot(k, g, kf)
        A = tabelle(b)
        quelle = "PN %d (%s)" % (pn, "RYA 2026" if k["pn"] else "aus Yardstick %s" % k["ys"])
        d = {"YachtName": k["name"], "Class": k["name"], "RefNo": "jolle-" + k["id"], "NatAuth": "VPP",
             "IssueDate": "2026-11-21", "LOA": k["loa"], "Draft": k["tiefgang"], "Dspl_Sailing": k["masse"] + k["crew_kg"],
             "Allowances": A, "Jolle": {**k, "widerstandsfaktor": round(kf, 3), "pn_benutzt": pn, "quelle_pn": quelle}}
        with open(os.path.join(ORDNER, "jolle-%s.json" % k["id"]), "w") as f:
            json.dump(d, f, ensure_ascii=False)
        nospi = None
        if k["spi"]:                                            # Variante ohne Spinnaker (gleiche Eichung)
            k2 = dict(k, spi=0, spi_art=None)
            d2 = dict(d, RefNo="jolle-%s-nospi" % k["id"], Allowances=tabelle(Boot(k2, g, kf)))
            with open(os.path.join(ORDNER, "jolle-%s-nospi.json" % k["id"]), "w") as f:
                json.dump(d2, f, ensure_ascii=False)
            nospi = "jolle-%s-nospi" % k["id"]
        katalog.append({"id": "jolle-" + k["id"], "klasse": k["name"].upper(), "name": k["name"] + " (dinghy)",
                        "anzahl": 0, "loa": k["loa"], "multi": False, "jolle": True,
                        "spi": "jolle-" + k["id"], "nospi": nospi})
        print("%-26s PN %4d  Faktor %.2f  Wende %s  VMG amwind %s" % (
            k["name"], pn, kf, "/".join("%d" % a for a in A["BeatAngle"][1:7]),
            "/".join("%.1f" % (3600 / s) for s in A["Beat"][1:7])), flush=True)
    if not wahl:
        json.dump({"stand": "2026-11-21", "ys_umrechnung_klassen": n, "boote": katalog}, open(KATALOG, "w"),
                  ensure_ascii=False, indent=1)
        print("->", os.path.relpath(KATALOG, BASIS), len(katalog), "Klassen")


if __name__ == "__main__":
    main(sys.argv[1:])
