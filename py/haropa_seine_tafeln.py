#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Liest die Hoch-/Niedrigwassertafeln der Capitainerie de Rouen (HAROPA) fuer die Seine.

Oliver 17.10.2026: https://www.capitainerie-rouen.com/fr/horaires-des-marees-0 -- Monatstafeln 2026-2030 fuer
Saint Leonard, Caudebec-en-Caux, Duclair und Rouen (Ajax /fr/stratis-tides/months?year=&month=). Zeiten in
Ortszeit, die Zelle nennt UT+1 bzw. UT+2; Hoehen in CMH (Cote marine du Havre, 4.38 m unter NGF), also das
Pegelnull der HAROPA-Pegel bei HydroPortail.

Usage: python3 py/haropa_seine_tafeln.py  -> tide_tables/france/haropa_rouen/haropa_hwlw.json  {Ort: [[iso_utc, m], ...]}
"""
import datetime as dt
import glob
import html
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORDNER = os.path.join(ROOT, 'tide_tables/france/haropa_rouen')
ZELLE = re.compile(r'<t([dh])([^>]*)>(.*?)</t[dh]>', re.S)


def text(s):
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', s))).strip()


def main():
    out = {}
    for pfad in sorted(glob.glob(os.path.join(ORDNER, 'haropa_20*.html'))):
        t = open(pfad, encoding='utf-8').read()
        orte = [text(x) for x in re.findall(r'<th colspan="2" scope="colgroup">(.*?)</th>', t)]
        body = t[t.find('<tbody>'):]
        datum = None
        for zeile in re.findall(r'<tr>(.*?)</tr>', body, re.S):
            z = ZELLE.findall(zeile)
            if z and 'rowspan' in z[0][1]:
                datum = dt.datetime.strptime(text(z[0][2]), '%d.%m.%Y')
                z = z[1:]
            z = z[1:]                                    # Koeffizient
            for i, ort in enumerate(orte):
                if 2 * i + 1 >= len(z):
                    break
                roh, hoehe = z[2 * i][2], text(z[2 * i + 1][2])
                m = re.search(r'(\d{1,2})h(\d{2})', text(roh))
                tz = re.search(r'UT\+(\d)', roh)
                if not m or not tz or not re.match(r'^-?\d+\.\d+$', hoehe):
                    continue
                u = datum + dt.timedelta(hours=int(m.group(1)) - int(tz.group(1)), minutes=int(m.group(2)))
                out.setdefault(ort, {})[u.isoformat() + 'Z'] = float(hoehe)
    res = {k: sorted(v.items()) for k, v in out.items()}
    json.dump(res, open(os.path.join(ORDNER, 'haropa_hwlw.json'), 'w'), indent=0)
    for k, v in res.items():
        print('%-18s %5d Scheitel  %s .. %s  %.2f..%.2f m' % (k, len(v), v[0][0][:16], v[-1][0][:16],
                                                         min(h for _, h in v), max(h for _, h in v)))


if __name__ == '__main__':
    main()
