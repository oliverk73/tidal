#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""BMKG Maritim Indonesien -> UTide-TC-Harmonics.

Quelle: maritim.bmkg.go.id Tide-API (harmonische Vorhersage, 10-min). Pro Station
volles Kalenderjahr 2026 (52560 pts) -> UTide-Fit auf 'lt'-Feld (Wasserstand ueber
LAT) => Z0 = mean(lt) ueber Chart Datum (LAT). Greenwich-Phasen (Daten in UTC).

Baut: 48 neue Stationen + Upgrade Tarakan/Kupang (bisher BIG/FES-Modell). Drei der
48 sind Classic-1997-Duplikate (Belawan/Manado/Paotere) -> BMKG ersetzt DWF-1997.
Output -> harmonics/utide/harmonics_utide_tidetables.txt (Gruppe "UTide TC").

Aufruf: python3 py/build_bmkg_indonesia.py            # QA
        python3 py/build_bmkg_indonesia.py --write    # an tidetables.txt anhaengen
"""
import sys, json, re, ssl, urllib.request, unicodedata
import numpy as np
import utide
import matplotlib.dates as mdates
from datetime import datetime

sys.path.insert(0, '/home/oliver/py')
import build_dhn_peru as dhn   # fuer ORDER (175 Konstituenten)

OUT = '/home/oliver/harmonics/utide/harmonics_utide_tidetables.txt'
META = '/home/oliver/annual_predictions/pasut_meta.json'
YEAR_START, YEAR_END = '20260101', '20261231'
CONSTIT = ['M2', 'S2', 'N2', 'K2', 'K1', 'O1', 'P1', 'Q1', '2N2', 'NU2', 'MU2',
           'L2', 'T2', 'M4', 'MS4', 'MN4', 'M6', '2MS6', 'SA', 'SSA', 'MM', 'MF']
ORDER = dhn.ORDER

_ctx = ssl.create_default_context(); _ctx.check_hostname = False; _ctx.verify_mode = ssl.CERT_NONE
_HDR = {'User-Agent': 'Mozilla/5.0 Chrome/120',
        'Referer': 'https://maritim.bmkg.go.id/cuaca/pasut'}
def fetch(url):
    return json.load(urllib.request.urlopen(urllib.request.Request(url, headers=_HDR),
                                            timeout=180, context=_ctx))

# zu bauende Stationen: 48 neue (Lokasi-Namen) + 2 Upgrades
NEW48 = [
    'Bakauheni','Banyuwangi','Maumere','Pontianak','Paotere','Kep. Seribu','Kota Baru',
    'Belinyu','Tj Balai Karimun','Pemenang','Bau Bau','Batam','Nunukan','Ternate',
    'Gilimanuk','Padangbai','Pangkalan Bun','Stasiun Maritim Ambon','Samarinda',
    'Palembang','Patimban','Kuala Tanjung','Kijing','Biak','Labuan Bajo','Malang',
    'Natuna','Meulaboh','Rembang','Belawan','Likupang','Kuala Tungkal, Jambi','Bajoe',
    'Larantuka','Karimunjawa','Paciran','Manokwari','Bira','Tidore','Manado','Torobulu',
    'Kayangan, Lombok','Luwuk','Rote','Tual','Garongkong','Merauke','Belangbelang',
]
UPGRADE = ['Tarakan', 'Kupang']   # bisher BIG/FES-Modell

# BMKG-Metadaten-Koord fehlerhaft -> reale Pegelposition (geprueft):
COORD_OVERRIDE = {'Palembang': (-2.9900, 104.7650)}  # Boom Baru, Musi (BMKG-Meta 91km daneben)


def clean_name(lokasi):
    # "Kuala Tungkal, Jambi" -> "Kuala Tungkal"; Provinz kommt separat ins state-Feld
    return lokasi.split(',')[0].strip()


def fit_station(sid, lat):
    d = fetch(f'https://maritim.bmkg.go.id/pasut/data/UTC/{sid}/{YEAR_START}/{YEAR_END}')
    if not d or len(d) < 10000:
        return None
    t = np.array([mdates.date2num(datetime.strptime(x['t'][:16], '%Y-%m-%dT%H:%M')) for x in d])
    h = np.array([float(x['lt']) for x in d])   # Wasserstand ueber LAT
    coef = utide.solve(t, h, lat=lat, epoch='1970-01-01', nodal=True, trend=False,
                       method='ols', conf_int='none', constit=CONSTIT, verbose=False)
    res = {n: (A, g) for n, A, g in zip(coef['name'], coef['A'], coef['g'])}
    rec = utide.reconstruct(t, coef, epoch='1970-01-01', min_SNR=0, verbose=False).h
    r2 = 1 - np.sum((h - rec) ** 2) / np.sum((h - h.mean()) ** 2)
    rms = float(np.sqrt(np.mean((h - rec) ** 2)))
    z0 = float(coef['mean'])
    return res, z0, len(h), r2, rms


def block(name, prov, lat, lon, sid, res, z0, n, r2, rms, upgrade=False):
    sidc = f'BMKG-{sid}'
    note = ('# note: ersetzt bisherige Modell-Quelle (BIG/FES) durch BMKG-Vorhersage'
            if upgrade else
            '# note: BMKG harmonische Vorhersage (kein Rohmesswert)')
    out = ['# BEGIN HOT COMMENTS', '# country: Indonesia', f'# state: {prov}',
           '# source: BMKG Maritim (maritim.bmkg.go.id) tide prediction, 10-min',
           f'# station_id_context: {sidc}', note,
           '# date_imported: 20260622',
           '# datum: Chart Datum (LAT, BMKG)', '# confidence: 5',
           f'# utide: period=2026(10min) constit={len(CONSTIT)} n={n}; '
           f'OOW RMS={rms*100:.1f}cm R2={r2:.3f}',
           '# !units: meters', f'# !longitude: {lon:.4f}', f'# !latitude: {lat:.4f}',
           f'{name}, Indonesia', '+00:00 :UTC', f'{z0:.4f} meters']
    for c in ORDER:
        if c in res:
            A, g = res[c]
            out.append(f'{c:<16}{A:.4f}  {g % 360:.2f}')
        else:
            out.append('x 0 0')
    return '\n'.join(out)


def main():
    write = '--write' in sys.argv
    meta = {s['Lokasi']: s for s in json.load(open(META))}
    targets = [(l, False) for l in NEW48] + [(l, True) for l in UPGRADE]
    blocks = []
    print(f"{'Station':24s}{'Prov':16s}{'M2_A':>7}{'M2_g':>6}{'Z0':>7}{'R2':>7}{'RMS':>7}{'n':>7}")
    for lok, upg in targets:
        s = meta.get(lok)
        if not s:
            print(f"{lok}: NICHT in metadata -> SKIP"); continue
        try:
            r = fit_station(s['ID'], s['Lat'])
        except Exception as e:
            print(f"{lok}: FEHLER {e}"); continue
        if not r:
            print(f"{lok}: zu wenig Daten"); continue
        res, z0, n, r2, rms = r
        la2,lo2 = COORD_OVERRIDE.get(lok,(s['Lat'],s['Lon']))
        nm = clean_name(lok)
        blk = block(nm, s['Provinsi'], la2, lo2, s['ID'], res, z0, n, r2, rms, upg)
        blocks.append((blk, upg, lok))
        tag = 'U' if upg else ' '
        print(f"{tag}{nm[:23]:23s}{s['Provinsi'][:15]:15s}{res['M2'][0]:>7.3f}"
              f"{res['M2'][1]:>6.0f}{z0:>7.3f}{r2:>7.3f}{rms*100:>6.1f}c{n:>7}")
    if not write:
        print(f"\n(QA, {len(blocks)} Stationen. --write zum Anhaengen.)")
        return
    txt = open(OUT, encoding='iso-8859-1').read()
    if not txt.endswith('\n'):
        txt += '\n'
    added = 0
    for blk, upg, lok in blocks:
        sidc = blk.splitlines()[4].split(': ', 1)[1]
        if f'station_id_context: {sidc}' in txt:
            print(f"  SKIP (existiert): {lok}"); continue
        txt += blk + '\n'; added += 1
    open(OUT, 'w', encoding='iso-8859-1').write(txt)
    print(f"\nAngehaengt: {added} BMKG-Stationen. Bloecke gesamt: {txt.count('# BEGIN HOT COMMENTS')}")
    print("-> TCD neu bauen; alte Tarakan/Kupang-Modellbloecke separat entfernen.")


if __name__ == '__main__':
    main()
