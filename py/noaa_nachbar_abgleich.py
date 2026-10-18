#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""NOAA-Buchsaetze gegen geprueften Bestand (Oliver 18.10.2026).

Oliver hat die ganze Welt auf Name und Position geprueft -- ausser den
NOAA-Buchsaetzen (harmonics/noaa/*tt, pacif, carib, censam), die am
1./2.07.2026 dazukamen. Ungeprueft heisst hier: NOAA-Satz, den
positions_locked.csv nicht als 'manual' fuehrt. Geprueft ist jeder andere
Gezeitensatz (auch NOAA 'manual').

Fuer jeden ungeprueften Satz der naechste gepruefte Nachbar, Abstand,
Kurvenabstand (health_check.curve_diff) und M2-Vergleich.

Schreibt harmonics/help/noaa_nachbar_abgleich_<datum>.csv. Aendert nichts.
Usage: python3 py/noaa_nachbar_abgleich.py
"""
import cmath
import csv
import glob
import math
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from health_check import load_records, km                          # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOAA = ('amtt', 'eutt', 'cptt', 'pacif', 'carib', 'censam')


def ist_noaa_buch(f):
    return any(f.endswith('harmonics_noaa_%s.txt' % t) for t in NOAA)


def uebernommene_namen():
    """Namen gepruefter Saetze, die archiviert wurden und deren Name ein NOAA-Satz traegt.

    Beim Tausch (FES oder Messprobe spricht fuer NOAA) uebernimmt der NOAA-Satz Name und
    Position des geprueften Satzes. Sein Fingerabdruck ist neu, positions_locked fuehrt ihn
    deshalb als 'source' -- geprueft ist er trotzdem.
    """
    out = set()
    for f in glob.glob(os.path.join(ROOT, 'harmonics/help/*_loeschen.csv')):
        for z in csv.DictReader(open(f, encoding='utf-8')):
            if z.get('datei') and not ist_noaa_buch(z['datei']):
                out.add(z['name'])
    return out


def ungeprueft(recs, prov=None):
    """NOAA-Buchsaetze ohne Olivers Pruefung.

    Massgeblich ist der Stand vom Morgen des 18.10.2026 (harmonics/help/noaa_ungeprueft_20261018.csv,
    Fingerabdruck = Konstituentenblock, aendert sich bei Umbenennung/Verschiebung nicht).
    positions_locked.csv taugt dafuer nicht mehr: jede automatische Verschiebung macht dort
    aus 'source' ein 'manual'. prov wird nur noch fuer alte Aufrufe angenommen.
    """
    fp = {z['fingerprint'] for z in csv.DictReader(open(os.path.join(ROOT, 'harmonics/help/noaa_ungeprueft_20261018.csv'),
                                                         encoding='utf-8'))}
    uebern = uebernommene_namen()
    return [r for r in recs if ist_noaa_buch(r['file']) and r['fp'] in fp and r['name'] not in uebern]


def main():
    prov = {}
    for r in csv.DictReader(open(os.path.join(ROOT, 'harmonics/help/positions_locked.csv'), encoding='utf-8')):
        prov[(r['fingerprint'], r['name'])] = r['provenance']
    recs = [r for r in load_records() if not r['current'] and r['lat'] is not None]
    offen = ungeprueft(recs, prov)
    ids = {id(r) for r in offen}
    gep = [r for r in recs if id(r) not in ids]
    gep.sort(key=lambda r: r['lat'])
    lats = [r['lat'] for r in gep]
    import bisect
    out = []
    for r in offen:
        i = bisect.bisect_left(lats, r['lat'] - 0.5)
        j = bisect.bisect_right(lats, r['lat'] + 0.5)
        kand = sorted(((km(r, g), g) for g in gep[i:j]), key=lambda x: x[0])
        if not kand:
            out.append(dict(datei=r['file'], name=r['name'], lat=r['lat'], lon=r['lon'], km='', partner='', pdatei='',
                            plat='', plon='', kurve_cm='', kurve_rel='', m2='', m2_partner='', dphi_min=''))
            continue
        d, g = kand[0]
        a2, b2 = r['z']['M2'], g['z']['M2']
        dk = math.sqrt(sum(abs(r['z'][x] - g['z'][x]) ** 2 for x in r['z']) / 2)
        dphi = ((math.degrees(cmath.phase(a2 / b2)) + 180) % 360 - 180) / 28.984104 * 60 if abs(a2) and abs(b2) else 0
        out.append(dict(datei=r['file'], name=r['name'], lat=r['lat'], lon=r['lon'], km=round(d, 2), partner=g['name'],
                        pdatei=g['file'], plat=g['lat'], plon=g['lon'], kurve_cm=round(100 * dk, 1),
                        kurve_rel=round(dk / max(abs(b2), 0.01), 3), m2=round(abs(a2), 3), m2_partner=round(abs(b2), 3),
                        dphi_min=round(dphi)))
    out.sort(key=lambda o: (o['km'] == '', o['km'] if o['km'] != '' else 0))
    ziel = os.path.join(ROOT, 'harmonics/help/noaa_nachbar_abgleich_%s.csv' % date.today().strftime('%Y%m%d'))
    with open(ziel, 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=list(out[0])); w.writeheader(); w.writerows(out)
    print(len(offen), 'ungepruefte NOAA-Saetze ->', ziel)


if __name__ == '__main__':
    main()
