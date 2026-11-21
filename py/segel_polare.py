#!/usr/bin/env python3
"""
Polaren fuer das Segel-Routing aus ORC-Zertifikaten (data.orc.org, oeffentliche Schnittstelle), 20.11.2026.

Ein ORC-Zertifikat enthaelt unter "Allowances" die Zeit je Seemeile (s/sm) fuer Windstaerken 4–24 kn und
Windwinkel 52–150°, dazu Kreuz-VMG + Wendewinkel (Beat/BeatAngle), Vorwind-VMG + Halsenwinkel (Run/GybeAngle)
und DW165/DW180. Daraus wird eine Tabelle Fahrt durchs Wasser [kn] ueber TWS 0–40 kn x TWA 0–180° (1°-Raster).

ORC rechnet mit Regattacrew; fuer Fahrtensegeln gibt das Routing einen Leistungsfaktor (z. B. 85 %). Ohne Spinnaker:
Non-Spinnaker-Zertifikat der Klasse, wo vorhanden (ohne_spi=True).

    P = polare('bavaria-37', ohne_spi=True)
    P.fahrt(tws_kn, twa_grad)          # vektorisiert, kn; 0 im Wendebereich (TWA < Wendewinkel)
    P.wendewinkel(tws_kn)

Aufruf:  venv/bin/python py/segel_polare.py [boot-id] [nospi]   -> druckt die Polare
"""
import json
import os
import sys

import numpy as np
import requests

BASIS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORDNER = os.path.join(BASIS, "quellen", "routing", "polare", "orc")
KATALOG = os.path.join(BASIS, "quellen", "routing", "orc_katalog.json")
# Jollen (py/jollen_polare.py, 21.11.2026): VPP + Yardstick, gleiches Format wie ein ORC-Zertifikat
JOLLEN_KATALOG = os.path.join(BASIS, "quellen", "routing", "jollen_katalog.json")
JOLLEN_ORDNER = os.path.join(BASIS, "quellen", "routing", "polare", "jollen")
ORC_URL = "https://data.orc.org/public/WPub.dll?action=DownBoatRMS&RefNo={ref}&ext=json"

# Alle Bootsklassen aus ORC (py/orc_katalog.py, 20.11.2026): je Klasse das Zertifikat mit dem mittleren APHD,
# "spi" = ORC Standard (mit Spinnaker), "nospi" = Non-Spinnaker-Zertifikat, wo es eines gibt.
STANDARD = "bavaria-37"
ALT = {"bavaria37": "bavaria-37", "oceanis393": "oceanis-393", "hanse370": "hanse-370", "dehler38": "dehler-38"}
_KAT = {}


def katalog():
    try:
        st = (os.stat(KATALOG).st_mtime, os.stat(JOLLEN_KATALOG).st_mtime if os.path.exists(JOLLEN_KATALOG) else 0)
    except OSError:
        return {}
    if _KAT.get("st") != st:
        with open(KATALOG) as f:
            k = json.load(f)
        boote = {b["id"]: b for b in k["boote"]}
        if os.path.exists(JOLLEN_KATALOG):
            with open(JOLLEN_KATALOG) as f:
                boote.update({b["id"]: b for b in json.load(f)["boote"]})
        _KAT.clear()
        _KAT.update(st=st, boote=boote, stand=k.get("stand"))
    return _KAT["boote"]


def _laden(ref):
    if ref.startswith("jolle-"):                                   # lokal gerechnet, kein Download
        with open(os.path.join(JOLLEN_ORDNER, ref + ".json")) as f:
            return json.load(f)
    os.makedirs(ORDNER, exist_ok=True)
    pfad = os.path.join(ORDNER, ref + ".json")
    if not os.path.exists(pfad):
        r = requests.get(ORC_URL.format(ref=ref), timeout=60)
        r.raise_for_status()
        d = json.loads(r.content.decode("utf-8-sig"))["rms"][0]
        keep = {k: d.get(k) for k in ("YachtName", "Class", "SailNo", "RefNo", "NatAuth", "Family", "IssueDate", "LOA",
                                      "Draft", "Dspl_Sailing", "Builder", "Designer", "Age_Year", "APHD", "Allowances")}
        with open(pfad + ".neu", "w") as f:
            json.dump(keep, f, ensure_ascii=False)
        os.replace(pfad + ".neu", pfad)
    with open(pfad) as f:
        return json.load(f)


class Polare:
    def __init__(self, boot, eintrag, variante):
        self.boot = boot
        self.eintrag = eintrag
        self.variante = variante
        self.daten = d = _laden(eintrag[variante])
        A = d["Allowances"]
        ws = np.array(A["WindSpeeds"], dtype="f8")
        winkel = A["WindAngles"]
        kn = lambda spm: 3600.0 / np.array(spm, dtype="f8")          # noqa: E731  s/sm -> kn
        # je ORC-Windstaerke: Stuetzpunkte (Winkel, Fahrt)
        spalten = []
        for i in range(len(ws)):
            ba = A["BeatAngle"][i]
            pts = [(ba, kn(A["Beat"])[i] / np.cos(np.radians(ba)))]
            pts += [(w, kn(A["R%d" % w])[i]) for w in winkel if w > ba and A.get("R%d" % w)]
            pts += [(a_, kn(A[k_])[i]) for a_, k_ in ((165.0, "DW165"), (180.0, "DW180")) if A.get(k_)]
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
        return {"id": self.boot, "name": self.eintrag["name"], "yacht": d.get("YachtName"),
                "klasse": d.get("Class"), "segelnr": d.get("SailNo"), "loa": d.get("LOA"), "tiefgang": d.get("Draft"),
                "variante": self.variante, "ohne_spi_verfuegbar": bool(self.eintrag.get("nospi")),
                "jolle": bool(d.get("Jolle")),
                "quelle": ("dinghy VPP calibrated to %s, %s" % (d["Jolle"]["quelle_pn"], "no spinnaker" if self.variante == "nospi" else "with spinnaker")
                           if d.get("Jolle") else
                           "ORC %s certificate %s (%s, %s)" % ("non-spinnaker" if self.variante == "nospi" else "standard",
                                                               d.get("RefNo"), d.get("NatAuth"), (d.get("IssueDate") or "")[:10]))}


_CACHE = {}


def polare(boot=STANDARD, ohne_spi=False):
    """ohne_spi=True nimmt das Non-Spinnaker-Zertifikat, wenn die Klasse eins hat (sonst das Standard-Zertifikat)."""
    K = katalog()
    boot = ALT.get(boot, boot)
    if boot not in K:
        boot = STANDARD
    e = K[boot]
    variante = "nospi" if (ohne_spi and e.get("nospi")) or not e.get("spi") else "spi"
    if (boot, variante) not in _CACHE:
        if len(_CACHE) > 50:
            _CACHE.clear()
        _CACHE[(boot, variante)] = Polare(boot, e, variante)
    return _CACHE[(boot, variante)]


def liste():
    """kompakt fuer das Auswahlfeld: [id, Name, LOA, Non-Spinnaker vorhanden, Anzahl Zertifikate]"""
    return [[b["id"], b["name"], b["loa"], 1 if b.get("nospi") else 0, b["anzahl"], 1 if b.get("jolle") else 0]
            for b in katalog().values()]


if __name__ == "__main__":
    for b in ([sys.argv[1]] if len(sys.argv) > 1 else [STANDARD]):
        P = polare(b, ohne_spi=len(sys.argv) > 2)
        print(P.info())
        print("TWS  " + " ".join("%5d" % a for a in (40, 45, 52, 60, 75, 90, 110, 120, 135, 150, 165, 180)) + "   Wende")
        for t in (4, 6, 8, 10, 12, 16, 20, 25):
            print("%3d  " % t + " ".join("%5.2f" % P.fahrt(t, a) for a in (40, 45, 52, 60, 75, 90, 110, 120, 135, 150, 165, 180))
                  + "   %4.1f" % P.wendewinkel(t))
