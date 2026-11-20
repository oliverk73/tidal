#!/usr/bin/env python3
"""
Polaren fuer das Segel-Routing aus ORC-Zertifikaten (data.orc.org, oeffentliche Schnittstelle), 20.11.2026.

Ein ORC-Zertifikat enthaelt unter "Allowances" die Zeit je Seemeile (s/sm) fuer Windstaerken 4–24 kn und
Windwinkel 52–150°, dazu Kreuz-VMG + Wendewinkel (Beat/BeatAngle), Vorwind-VMG + Halsenwinkel (Run/GybeAngle)
und DW165/DW180. Daraus wird eine Tabelle Fahrt durchs Wasser [kn] ueber TWS 0–40 kn x TWA 0–180° (1°-Raster).

ORC rechnet mit Regattacrew und Spinnaker; fuer Fahrtensegeln gibt das Routing einen Leistungsfaktor (z. B. 85 %).

    P = polare('bavaria37')
    P.fahrt(tws_kn, twa_grad)          # vektorisiert, kn; 0 im Wendebereich (TWA < Wendewinkel)
    P.wendewinkel(tws_kn)

Aufruf:  venv/bin/python py/segel_polare.py [boot]   -> laedt fehlende Zertifikate, druckt die Polare
"""
import json
import os
import sys

import numpy as np
import requests

BASIS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORDNER = os.path.join(BASIS, "quellen", "routing", "polare")
ORC_URL = "https://data.orc.org/public/WPub.dll?action=DownBoatRMS&RefNo={ref}&ext=json"

# Je Klasse das ORC-Standard-Zertifikat mit dem mittleren APHD der aktiven Zertifikate (20.11.2026)
BOOTE = {
    "bavaria37": {"name": "Bavaria Cruiser 37", "ref": "03510004WCD"},     # BAS TARD (ESP), Median von 11
    "oceanis393": {"name": "Beneteau Oceanis 393", "ref": "03420004LJ1"},  # PENY LANE (GRE), Median von 12
    "hanse370": {"name": "Hanse 370", "ref": "03440004N9R"},               # Rabagast (NOR), Median von 16
    "dehler38": {"name": "Dehler 38", "ref": "04310004K36"},               # IJsvogel (NED), Median von 49
}
STANDARD = "bavaria37"


def _laden(boot):
    os.makedirs(ORDNER, exist_ok=True)
    pfad = os.path.join(ORDNER, boot + ".json")
    if not os.path.exists(pfad):
        r = requests.get(ORC_URL.format(ref=BOOTE[boot]["ref"]), timeout=60)
        r.raise_for_status()
        d = json.loads(r.content.decode("utf-8-sig"))["rms"][0]
        keep = {k: d.get(k) for k in ("YachtName", "Class", "SailNo", "RefNo", "IssueDate", "LOA", "Draft",
                                      "Dspl_Sailing", "Builder", "Designer", "Allowances")}
        with open(pfad, "w") as f:
            json.dump(keep, f, indent=1)
    with open(pfad) as f:
        return json.load(f)


class Polare:
    def __init__(self, boot):
        self.boot = boot
        self.daten = d = _laden(boot)
        A = d["Allowances"]
        ws = np.array(A["WindSpeeds"], dtype="f8")
        winkel = A["WindAngles"]
        kn = lambda spm: 3600.0 / np.array(spm, dtype="f8")          # noqa: E731  s/sm -> kn
        # je ORC-Windstaerke: Stuetzpunkte (Winkel, Fahrt)
        spalten = []
        for i in range(len(ws)):
            ba = A["BeatAngle"][i]
            pts = [(ba, kn(A["Beat"])[i] / np.cos(np.radians(ba)))]
            pts += [(w, kn(A["R%d" % w])[i]) for w in winkel if w > ba]
            pts += [(165.0, kn(A["DW165"])[i]), (180.0, kn(A["DW180"])[i])]
            pts.sort()
            spalten.append((ba, pts))
        self.tws = np.arange(0, 41, 1.0)
        self.twa = np.arange(0, 181, 1.0)
        tab_orc = np.zeros((len(ws), 181))
        wende_orc = np.zeros(len(ws))
        for i, (ba, pts) in enumerate(spalten):
            a, v = zip(*pts)
            z = np.interp(self.twa, a, v)
            z[self.twa < ba] = 0.0
            tab_orc[i] = z
            wende_orc[i] = ba
        tab = np.zeros((len(self.tws), 181))
        wende = np.zeros(len(self.tws))
        for k, t in enumerate(self.tws):
            if t <= ws[0]:                                   # unter 4 kn: linear gegen 0
                tab[k] = tab_orc[0] * (t / ws[0])
                wende[k] = wende_orc[0]
            elif t >= ws[-1]:                                # ueber 24 kn: konstant (Grenzwind regelt das Routing)
                tab[k] = tab_orc[-1]
                wende[k] = wende_orc[-1]
            else:
                j = np.searchsorted(ws, t) - 1
                f = (t - ws[j]) / (ws[j + 1] - ws[j])
                tab[k] = (1 - f) * tab_orc[j] + f * tab_orc[j + 1]
                wende[k] = (1 - f) * wende_orc[j] + f * wende_orc[j + 1]
                tab[k][self.twa < wende[k]] = 0.0
        self.tab = tab
        self.wende = wende

    def fahrt(self, tws, twa):
        """Fahrt durchs Wasser [kn], bilinear in TWS/TWA (TWA 0–180, Betrag)."""
        tws = np.clip(np.asarray(tws, dtype="f8"), 0, 40)
        twa = np.clip(np.abs(np.asarray(twa, dtype="f8")), 0, 180)
        i = np.minimum(tws.astype(int), 39)
        fi = tws - i
        j = np.minimum(twa.astype(int), 179)
        fj = twa - j
        T = self.tab
        v0 = T[i, j] * (1 - fj) + T[i, j + 1] * fj
        v1 = T[i + 1, j] * (1 - fj) + T[i + 1, j + 1] * fj
        v = v0 * (1 - fi) + v1 * fi
        # im Wendebereich hart 0 (nicht ueber die Kante mitteln)
        return np.where(twa < np.interp(tws, self.tws, self.wende), 0.0, v)

    def wendewinkel(self, tws):
        return np.interp(tws, self.tws, self.wende)

    def info(self):
        d = self.daten
        return {"id": self.boot, "name": BOOTE[self.boot]["name"], "yacht": d.get("YachtName"),
                "klasse": d.get("Class"), "segelnr": d.get("SailNo"), "loa": d.get("LOA"), "tiefgang": d.get("Draft"),
                "quelle": "ORC certificate %s (%s)" % (d.get("RefNo"), (d.get("IssueDate") or "")[:10])}


_CACHE = {}


def polare(boot=STANDARD):
    if boot not in BOOTE:
        boot = STANDARD
    if boot not in _CACHE:
        _CACHE[boot] = Polare(boot)
    return _CACHE[boot]


def liste():
    return [{"id": k, "name": v["name"]} for k, v in BOOTE.items()]


if __name__ == "__main__":
    for b in ([sys.argv[1]] if len(sys.argv) > 1 else BOOTE):
        P = polare(b)
        print(P.info())
        print("TWS  " + " ".join("%5d" % a for a in (40, 45, 52, 60, 75, 90, 110, 120, 135, 150, 165, 180)) + "   Wende")
        for t in (4, 6, 8, 10, 12, 16, 20, 25):
            print("%3d  " % t + " ".join("%5.2f" % P.fahrt(t, a) for a in (40, 45, 52, 60, 75, 90, 110, 120, 135, 150, 165, 180))
                  + "   %4.1f" % P.wendewinkel(t))
