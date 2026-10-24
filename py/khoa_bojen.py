#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""KHOA-Messbojen (Badanuri, 해양관측부이): Stroemungsfits aus den Jahres-ZIPs (Oliver 24.10.2026).

Oliver laedt je Boje alle Jahre als ZIP (해양정보 다운로드 -> 관측자료 / 년별 / 해양관측부이) nach
currents/korea/*.zip. Jede ZIP wird in einen eigenen Ordner currents/korea/_arbeit/<zip>/ entpackt.
Dateien: Kopf 관측소명/위도/경도, dann Tabulator-Spalten; 유속 in cm/s, 유향 in Grad (wohin).
Zeit: KST (UTC+9), bis 2021 30 min, ab 2022 10 min. In Wando liegt die M2-Phase 2015-2024
auf +-3 Grad, also kein Zeitsprung beim Formatwechsel.

Je Jahr ein Fit (Hauptachse, UTide wie py/cmems_stroemung_nachholen.analyse). Gute Jahre:
r2 >= max(0.6, 0.85 * bestes r2) und M2 hoechstens 15 % neben dem Median dieser Jahre
(Wando 2023/24: Phase gleich, M2 nur noch 0.7-0.8 kn -- Sensor). Daraus der Gesamtfit.
Verworfen: kein gutes Jahr oder M2 < 0.2 kn (Gamcheon: 0.04 kn, r2 0.2).

Schreibt harmonics/help/khoa_bojen_<datum>.csv und ..._<datum>.txt (Bloecke), traegt nichts ein.
Usage: venv/bin/python py/khoa_bojen.py
"""
import csv
import glob
import os
import sys
import zipfile
from datetime import date

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cmems_stroemung_nachholen as C                               # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QUELLE = os.path.join(ROOT, 'currents/korea')
ARBEIT = os.path.join(QUELLE, '_arbeit')
MIN_WERTE_JAHR = 30 * 48
MIN_M2_KN = 0.2

# Name im Bestand nach dem Schema der koreanischen Pegel (Wando-hang, South Korea)
NAMEN = {
    '완도항': ('WANDO', 'Wando-hang'), '인천항': ('INCHEON', 'Incheon-hang'),
    '경인항': ('GYEONGIN', 'Gyeongin-hang'), '평택당진항': ('IPPADO', 'Pyeongtaek-Dangjin-hang (Ippado)'),
    '태안항': ('TAEAN', 'Taean-hang'), '군산항': ('GUNSAN', 'Gunsan-hang'),
    '상왕등도': ('SANGWANG', 'Sangwangdeungdo'), '우이도': ('UIDO', 'Uido'),
    '생일도': ('SAENGIL', 'Saengildo'), '광양항': ('GWANGYANG', 'Gwangyang-hang'),
    '여수항': ('YEOSU', 'Yeosu-hang'), '통영항': ('TONGYEONG', 'Tongyeong-hang'),
    '감천항': ('GAMCHEON', 'Gamcheon-hang'), '마산항': ('MASAN', 'Masan-hang'),
    '부산항': ('BUSAN', 'Busan-hang'), '부산항신항': ('BUSANNEW', 'Busan Sinhang'),
    '제주해협': ('KG_0028', 'Jeju Strait'), '대한해협': ('KG_0024', 'Korea Strait'),
    '남해동부': ('KG_0025', 'Namhae East'), '제주남부': ('KG_0021', 'Jeju South'),
    '대천해수욕장': ('DAECHEON', 'Daecheon Beach'), '중문해수욕장': ('JUNGMUN', 'Jungmun Beach'),
}


def entpacken(z):
    ziel = os.path.join(ARBEIT, os.path.splitext(os.path.basename(z))[0])
    os.makedirs(ziel, exist_ok=True)
    with zipfile.ZipFile(z) as f:
        for i, info in enumerate(f.infolist()):
            if info.filename.lower().endswith('.txt'):
                with open(os.path.join(ziel, 'jahr_%02d.txt' % i), 'wb') as fh:
                    fh.write(f.read(info))
    return ziel


def lesen(ordner):
    teile, kopf = [], None
    for p in sorted(glob.glob(os.path.join(ordner, '*.txt'))):
        raw = open(p, 'rb').read()
        try:
            t = raw.decode('utf-8-sig')
        except UnicodeDecodeError:
            t = raw.decode('cp949')
        L = t.splitlines()
        name, lat, lon = (L[k].split(':', 1)[1].strip() for k in range(3))
        h = L[3].split('\t')
        sp_n = '유속(cm/s)' if '유속(cm/s)' in h else '표층유속(cm/s)'      # Hochseebojen: 표층 = Oberflaeche
        iv, idg = h.index(sp_n), h.index(sp_n.replace('속(cm/s)', '향(deg)'))
        z = [l.split('\t') for l in L[4:] if l.strip()]
        df = pd.DataFrame([(r[0], r[iv].strip(), r[idg].strip()) for r in z], columns=['t', 'sp', 'dg'])
        df = df[~df.sp.isin(['-', '']) & ~df.dg.isin(['-', ''])]
        if df.empty:
            continue
        zeit = pd.to_datetime(df.t.str.replace('/', '-')) - pd.Timedelta(hours=9)
        sp, dg = df.sp.astype(float).values / 100, np.radians(df.dg.astype(float).values)
        teile.append(pd.DataFrame({'u': sp * np.sin(dg), 'v': sp * np.cos(dg)}, index=zeit.values))
        if kopf is None or zeit.iloc[-1] > kopf[3]:                 # juengste Position
            kopf = (name, float(lat), float(lon), zeit.iloc[-1])
    df = pd.concat(teile).sort_index()
    return kopf, df[~df.index.duplicated()]


def auswahl(df, lat):
    jahre = {}
    for y, g in df.groupby(df.index.year):
        if len(g) >= MIN_WERTE_JAHR:
            r = C.analyse(g, lat)
            jahre[y] = (r['r2'], r['m2'], r['konst'].get('M2', (0, 0))[1], len(g))
    if not jahre:
        return jahre, []
    grenze = max(0.6, 0.85 * max(v[0] for v in jahre.values()))
    gut = [y for y, v in jahre.items() if v[0] >= grenze]
    if gut:
        med = np.median([jahre[y][1] for y in gut])
        gut = [y for y in gut if abs(jahre[y][1] / med - 1) <= 0.15]
    return jahre, sorted(gut)


def main():
    tag = date.today().strftime('%Y%m%d')
    zeilen, bloecke, gesehen = [], [], {}
    for z in sorted(glob.glob(os.path.join(QUELLE, '*.zip'))):
        (name, lat, lon, _), df = lesen(entpacken(z))
        if name in gesehen:                      # dieselbe Boje unter anderem Dateinamen
            print('%-28s doppelt, schon in %s' % (os.path.basename(z), gesehen[name]))
            continue
        gesehen[name] = os.path.basename(z)
        code, ort = NAMEN.get(name, (name, name))
        jahre, gut = auswahl(df, lat)
        info = ' '.join('%d:%.2f/%.2fkn/%.0f%s' % (y, v[0], v[1], v[2], '*' if y in gut else '')
                        for y, v in sorted(jahre.items()))
        zeile = dict(zip=os.path.basename(z), station=name, code=code, name=ort, lat=lat, lon=lon,
                     jahre=info, gut='%d-%d' % (gut[0], gut[-1]) if gut else '', urteil='verworfen')
        if gut:
            r = C.analyse(df[df.index.year.isin(gut)], lat)
            zeile.update(r2=round(r['r2'], 3), m2_kn=round(r['m2'], 3), s2_kn=round(r['s2'], 3),
                         k1_kn=round(r['k1'], 3), v95_kn=round(r['smax'], 2), achse=round(r['achse']))
            if r['m2'] >= MIN_M2_KN:
                zeile['urteil'] = 'eintragen'
                k = dict(code='KHOA-%s' % code, inst='KHOA (Korea Hydrographic and Oceanographic Agency)')
                b = C.block(k, r, lat, lon, float('nan'))
                b = b.replace('# Harmonic constants derived from CMEMS in-situ',
                              '# Harmonic constants derived from KHOA ocean observation buoy %s' % code)
                b = b.replace('hourly samples', 'samples (30/10 min, years %s)' % ','.join(map(str, gut)))
                b = b.replace(', depth -1 m', ', surface')
                b = b.replace('# source: CMEMS in-situ, UTide analysis',
                              '# source: KHOA Badanuri ocean observation buoy (surface current), UTide analysis\n'
                              '# note: times KST in the files, converted to UTC; direction = towards')
                b = b.replace('station_id_context: CMEMS-KHOA-', 'station_id_context: KHOA-TW-')
                b = b.replace('# cmems_code: KHOA-%s' % code, '# khoa_id: %s' % code)
                b = b.replace('KHOA-%s Current' % code, '%s (KHOA buoy), South Korea Current' % ort)
                bloecke.append(b)
        zeilen.append(zeile)
        print('%-28s %-12s %-10s %s' % (ort, zeile['gut'] or '-', zeile['urteil'], info))
    felder = ['zip', 'station', 'code', 'name', 'lat', 'lon', 'gut', 'urteil', 'r2', 'm2_kn', 's2_kn',
              'k1_kn', 'v95_kn', 'achse', 'jahre']
    with open(os.path.join(ROOT, 'harmonics/help/khoa_bojen_%s.csv' % tag), 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=felder, restval='')
        w.writeheader()
        w.writerows(zeilen)
    with open(os.path.join(ROOT, 'harmonics/help/khoa_bojen_%s.txt' % tag), 'w', encoding='iso-8859-1') as fh:
        fh.write('\n'.join(bloecke) + '\n')
    print(len(bloecke), 'Saetze zum Eintragen von', len(zeilen))


if __name__ == '__main__':
    main()
