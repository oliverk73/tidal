#!/usr/bin/env python3
"""
Alle Bootsklassen aus ORC (data.orc.org) fuer den Routenplaner laden (Oliver 20.11.2026).

1. ActiveCerts (alle Laender, ~15 000 Zertifikate) -> nach Klasse gruppieren (Grossschreibung/Leerzeichen vereinheitlicht);
   allgemeine Klassen ohne Bootstyp (ONE OFF, CUSTOM, PROTOTYPE, leer) entfallen.
2. Je Klasse das Zertifikat mit dem mittleren APHD (Median) – getrennt fuer
     spi   = ORC Standard (Familie 1; sonst Double Handed 3, Multihull 4, Light 6, Super Yacht 2)
     nospi = Non Spinnaker (Familie 5), wo vorhanden
3. Jedes gewaehlte Zertifikat einmal laden, kompakt speichern: quellen/routing/polare/orc/<RefNo>.json
   (Allowances + Kopf). Bereits geladene werden uebersprungen; Pause zwischen Abrufen (Server schonen).
Katalog: quellen/routing/orc_katalog.json

Aufruf:  venv/bin/python py/orc_katalog.py [--nur-katalog] [--pause 0.5]
"""
import argparse
import collections
import json
import os
import re
import statistics
import time
import xml.etree.ElementTree as ET

import requests

BASIS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORDNER = os.path.join(BASIS, "quellen", "routing")
POLARE = os.path.join(ORDNER, "polare", "orc")
KATALOG = os.path.join(ORDNER, "orc_katalog.json")
URL_LISTE = "https://data.orc.org/public/WPub.dll?action=ActiveCerts&ext=json"
URL_CERT = "https://data.orc.org/public/WPub.dll?action=DownBoatRMS&RefNo={ref}&ext=json"
ALLGEMEIN = re.compile(r"^(|-+|\?+|N/?A|ONE[ -]?OFF|CUSTOM|CUSTOM ONE[ -]?OFF|PROTOTYPE|PROTO|UNKNOWN|OTHER|SPECIAL|"
                       r"HALF TON ONE[ -]?OFF|ONE[ -]?OFF .*|.* ONE[ -]?OFF)$")
SPI_FAMILIEN = ["1", "3", "4", "6", "2"]                      # Reihenfolge der Bevorzugung
KOPF = ("YachtName", "Class", "SailNo", "RefNo", "NatAuth", "Family", "IssueDate", "LOA", "Draft", "Dspl_Sailing",
        "Builder", "Designer", "Age_Year", "APHD", "Allowances")


def norm(c):
    return re.sub(r"\s+", " ", (c or "").strip().upper())


def slug(c):
    return re.sub(r"[^a-z0-9]+", "-", c.lower()).strip("-")


def katalog_bauen(sitzung):
    r = sitzung.get(URL_LISTE, timeout=300)
    r.raise_for_status()
    rows = ET.fromstring(r.content).findall(".//ROW")
    klassen = collections.defaultdict(list)
    schreibweise = collections.defaultdict(collections.Counter)
    for x in rows:
        c = x.findtext("Class")
        k = norm(c)
        if ALLGEMEIN.match(k):
            continue
        try:
            aphd = float(x.findtext("APHD") or "nan")
        except ValueError:
            continue
        if not aphd == aphd or aphd <= 0:
            continue
        klassen[k].append({"ref": x.findtext("RefNo"), "fam": x.findtext("Family"), "aphd": aphd,
                           "loa": float(x.findtext("LOA") or 0), "land": x.findtext("CountryId")})
        schreibweise[k][c.strip()] += 1

    def median_cert(lst):
        lst = sorted(lst, key=lambda z: z["aphd"])
        return lst[len(lst) // 2]

    aus = []
    for k, lst in klassen.items():
        spi = None
        for f in SPI_FAMILIEN:
            teil = [z for z in lst if z["fam"] == f]
            if teil:
                spi = median_cert(teil)
                break
        ns = [z for z in lst if z["fam"] == "5"]
        nospi = median_cert(ns) if ns else None
        if spi is None and nospi is None:
            continue
        loa = statistics.median([z["loa"] for z in lst if z["loa"]] or [0])
        aus.append({"id": slug(k), "klasse": k, "name": schreibweise[k].most_common(1)[0][0],
                    "anzahl": len(lst), "loa": round(loa, 2), "multi": any(z["fam"] == "4" for z in lst),
                    "spi": spi and spi["ref"], "nospi": nospi and nospi["ref"]})
    # doppelte ids (verschiedene Klassen mit gleichem slug) eindeutig machen
    gesehen = collections.Counter()
    for b in sorted(aus, key=lambda b: -b["anzahl"]):
        gesehen[b["id"]] += 1
        if gesehen[b["id"]] > 1:
            b["id"] += "-%d" % gesehen[b["id"]]
    aus.sort(key=lambda b: b["name"].upper())
    os.makedirs(ORDNER, exist_ok=True)
    with open(KATALOG + ".neu", "w") as f:
        json.dump({"stand": time.strftime("%Y-%m-%d"), "zertifikate": len(rows), "boote": aus}, f, ensure_ascii=False)
    os.replace(KATALOG + ".neu", KATALOG)
    return aus


def cert_laden(sitzung, ref):
    pfad = os.path.join(POLARE, ref + ".json")
    if os.path.exists(pfad):
        return False
    r = sitzung.get(URL_CERT.format(ref=ref), timeout=120)
    r.raise_for_status()
    d = json.loads(r.content.decode("utf-8-sig"))["rms"][0]
    if not d.get("Allowances"):
        raise ValueError("ohne Allowances")
    with open(pfad + ".neu", "w") as f:
        json.dump({k: d.get(k) for k in KOPF}, f, ensure_ascii=False)
    os.replace(pfad + ".neu", pfad)
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--nur-katalog", action="store_true")
    ap.add_argument("--pause", type=float, default=0.5)
    a = ap.parse_args()
    s = requests.Session()
    s.headers["User-Agent"] = "tide-research-routing/1.0"
    boote = katalog_bauen(s)
    refs = sorted({b[v] for b in boote for v in ("spi", "nospi") if b[v]})
    print("Katalog: %d Klassen, %d Zertifikate zu laden" % (len(boote), len(refs)), flush=True)
    if a.nur_katalog:
        return
    os.makedirs(POLARE, exist_ok=True)
    neu = fehler = 0
    for n, ref in enumerate(refs, 1):
        try:
            if cert_laden(s, ref):
                neu += 1
                time.sleep(a.pause)
        except Exception as e:                                # noqa: BLE001
            fehler += 1
            print("  %s: %s" % (ref, str(e)[:120]), flush=True)
            time.sleep(5)
        if n % 200 == 0:
            print("  %d/%d (neu %d, Fehler %d)" % (n, len(refs), neu, fehler), flush=True)
    print("Fertig: %d neu, %d Fehler, %d vorhanden" % (neu, fehler, len(refs) - neu - fehler), flush=True)


if __name__ == "__main__":
    main()
