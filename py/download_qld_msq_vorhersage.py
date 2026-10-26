#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MSQ-Vorhersagen ("<Pegel> tide gauge -- predicted interval data") vom QLD-Datenportal.

Oliver 26.10.2026: "Ist diese Quelle schon ausgewertet? data.qld.gov.au/dataset/?tags=tides" -> die
Messarchive ja (py/download_qld_msq_archiv.py), die amtlichen Vorhersagen fuer 78 Pegel nicht. Gebraucht
fuer drei Luecken (Boigu, Urangan Fairway Beacon, Tin Can Bay) und als Massstab fuer Altsaetze.

Gleiches Format wie die Archive (Date dd/mm/yyyy, Time, Ind, Reading, 10 min), Zeit AEST -> UTC.
Jahrgaenge JAHRE (Fit auf zwei, Probe am dritten).

Usage: venv/bin/python py/download_qld_msq_vorhersage.py [dataset-name-teil ...]
       -> water_levels/Australia_QLD/msq_vorhersage/<dataset-name>.csv (time_utc, waterlevel_m)
"""
import csv
import datetime as dt
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import download_qld_msq_archiv as A                                # noqa: E402

ZIEL = os.path.join(A.ROOT, 'water_levels/Australia_QLD/msq_vorhersage')
JAHRE = (2025, 2026, 2027)


def datensaetze():
    res = A.api('package_search', fq='tags:tides', q='title:"predicted interval data"', rows=300)['results']
    return [p for p in res if 'predicted interval' in p['title'].lower()]


def main(argv):
    os.makedirs(ZIEL, exist_ok=True)
    for p in sorted(datensaetze(), key=lambda p: p['name']):
        if argv and not any(a in p['name'] for a in argv):
            continue
        pfad = os.path.join(ZIEL, p['name'] + '.csv')
        if os.path.exists(pfad):
            print('%s: vorhanden' % p['name'])
            continue
        res = [r for r in p['resources'] if r.get('datastore_active') and A.jahr(r) in JAHRE]
        werte = {}
        for r in res:
            for z in A.zeilen(r['id']):
                try:
                    v = float(z.get('Reading', ''))
                    t = dt.datetime.strptime('%s %s' % (z['Date'].strip(), z['Time'].strip()), '%d/%m/%Y %H:%M')
                except (ValueError, KeyError, AttributeError):
                    continue
                if -10 < v < 20:
                    werte[t - dt.timedelta(hours=10)] = v
        print('%s: %s -> %d Werte' % (p['name'], sorted(A.jahr(r) for r in res), len(werte)), flush=True)
        if not werte:
            continue
        tmp = '%s.%d.tmp' % (pfad, os.getpid())
        with open(tmp, 'w', newline='') as f:
            w = csv.writer(f)
            w.writerow(['time_utc', 'waterlevel_m'])
            for t in sorted(werte):
                w.writerow([t.strftime('%Y-%m-%d %H:%M'), '%.3f' % werte[t]])
        os.replace(tmp, pfad)


if __name__ == '__main__':
    main(sys.argv[1:])
