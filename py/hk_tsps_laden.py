#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Laedt Stromvorhersagen des Hong Kong Tidal Stream Prediction System (Marine Department).

current.hydro.gov.hk, Quelle data.gov.hk (frei mit Quellenangabe). Je Punkt 15-min-Werte, Mode A =
Tiefenmittel. Auswahl in tide_tables/hongkong_tsps/auswahl.json, ein Abruf je Punkt fuer 2026
(mehrere Punkte ueber laengere Zeit liefern stumm eine leere Datei).

Usage: python3 py/hk_tsps_laden.py
"""
from __future__ import annotations

import json
import os
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORD = os.path.join(ROOT, 'tide_tables/hongkong_tsps')
URL = ('https://current.hydro.gov.hk/data/download_selected_points.php?start_date=2026-01-01'
       '&end_date=2026-12-30&mode=A&point=')
WEG = {'127054', '159051', '154054', '87054'}    # unter ~0,6 kn, keine Navigationshilfe


def main():
    w = [k for k in json.load(open(os.path.join(ORD, 'auswahl.json'))) if k not in WEG]
    for k in w:
        ziel = os.path.join(ORD, f'p{k}.csv')
        if os.path.exists(ziel) and os.path.getsize(ziel) > 1000:
            continue
        req = urllib.request.Request(URL + k, headers={'User-Agent': 'weather-tides/1.0 (private tide research)'})
        b = urllib.request.urlopen(req, timeout=120).read()
        open(ziel, 'wb').write(b)
        print(k, len(b), flush=True)
        time.sleep(2)


if __name__ == '__main__':
    main()
