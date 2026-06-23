#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""BMKG Indonesien Batch 2: 7 Stationen, Upgrade FES2022 -> BMKG-Vorhersage.

Aus der Dishidros-2023-Gap-Analyse: diese 7 waren nur durch FES2022 abgedeckt
(bzw. Pantoloan/Palu nur FES) und sind ueber die saubere BMKG-API verfuegbar
-> zuverlaessiger Upgrade ohne OCR. Die zugehoerigen FES-Bloecke werden separat
aus harmonics_fes2022.txt entfernt (siehe remove_fes_batch2()).

Aufruf: python3 py/build_bmkg_batch2.py          # QA
        python3 py/build_bmkg_batch2.py --write  # tidetables anhaengen + FES entfernen
"""
import sys, json
sys.path.insert(0, '/home/oliver/py')
import build_bmkg_indonesia as b

OUT = b.OUT
FES = '/home/oliver/harmonics/utide/harmonics_fes2022.txt'
META = b.META

# BMKG-Lokasi -> Blockname
TARGETS = {
    'Panjang':     'Pelabuhan Panjang (Lampung)',
    'Cilegon':     'Cilegon (Ciwandan)',
    'Probolinggo': 'Probolinggo',
    'Kendari':     'Kendari',
    'Jayapura':    'Jayapura',
    'Sorong':      'Sorong',
    'Palu':        'Pantoloan (Palu)',
}


def main():
    write = '--write' in sys.argv
    meta = {s['Lokasi']: s for s in json.load(open(META))}
    blocks = []
    print(f"{'Station':26s}{'M2_A':>7}{'M2_g':>6}{'Z0':>7}{'R2':>7}{'RMS':>7}{'n':>8}")
    for lok, nm in TARGETS.items():
        s = meta[lok]
        r = b.fit_station(s['ID'], s['Lat'])
        if not r:
            print(f"{lok}: zu wenig Daten"); continue
        res, z0, n, r2, rms = r
        blk = b.block(nm, s['Provinsi'], s['Lat'], s['Lon'], s['ID'], res, z0, n, r2, rms, upgrade=True)
        blocks.append((blk, lok, nm))
        print(f"{nm[:25]:26s}{res['M2'][0]:>7.3f}{res['M2'][1]:>6.0f}{z0:>7.3f}{r2:>7.3f}{rms*100:>6.1f}c{n:>8}")
    if not write:
        print(f"\n(QA, {len(blocks)} Stationen. --write zum Schreiben.)")
        return
    txt = open(OUT, encoding='iso-8859-1').read()
    if not txt.endswith('\n'): txt += '\n'
    added = 0
    for blk, lok, nm in blocks:
        sidc = blk.splitlines()[4].split(': ', 1)[1]
        if f'station_id_context: {sidc}' in txt:
            print(f"  SKIP existiert: {nm}"); continue
        txt += blk + '\n'; added += 1
    open(OUT, 'w', encoding='iso-8859-1').write(txt)
    print(f"\nAngehaengt: {added} BMKG-Stationen -> tidetables ({txt.count('# BEGIN HOT COMMENTS')} Bloecke)")


if __name__ == '__main__':
    main()
