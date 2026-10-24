#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""KHOA-Wasserstaende (Badanuri): Messfits aus den Jahres-ZIPs (Oliver 24.10.2026).

ZIPs liegen in water_levels/Korea_KHOA/*.zip (Pegel 조위관측소, Forschungsplattformen 해양과학기지).
Wasserstand: Spalte 조위(cm) oder Range_조위(cm) (Radar auf den Plattformen), Zeit KST (UTC+9),
Momentanwert zur vollen Stunde. Bezugssprung (Gageocho 2019 und 2022: Mittel 5.0 -> 3.1 -> 1.3 m)
schneidet abschnitt() aus py/qld_msq_fit.py ab; Fit, Ausreisser und Probe am letzten Jahr ebenfalls
von dort. Gageocho: M2 0.745 m/114 Grad, FES 0.731/112 -- Zeitbasis KST bestaetigt.

Usage: venv/bin/python py/khoa_pegel_fit.py [--schreiben]   (haengt neue Saetze an harmonics_utide_observations.txt)
"""
import datetime as dt
import glob
import json
import os
import sys
import zipfile

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import health_check as H                                           # noqa: E402
import qld_msq_fit as Q                                             # noqa: E402
import scheitelfit as SF                                            # noqa: E402
import xtide_modell as X                                            # noqa: E402
from sicher_schreiben import schreiben                             # noqa: E402

ROOT = Q.ROOT
QUELLE = os.path.join(ROOT, 'water_levels/Korea_KHOA')
ZIEL = Q.ZIEL
# Pegelliste (getObsStation.json obsType=DT) fuer die Position, die 조석 성과-Dateien nicht mitbringen
STATIONEN = json.load(open(os.path.join(QUELLE, 'khoa_stationen_DT.json'), encoding='utf-8'))['data']

# Hangul -> (Name im Bestand, Region); Klammer-Regel: Suchwort vor der Klammer
NAMEN = {
    '신안가거초': ('Gageocho (Ocean Research Station), South Korea', 'South Jeolla'),
    '옹진소청초': ('Socheongcho (Ocean Research Station), South Korea', 'Incheon'),
    '이어도': ('Ieodo (Ocean Research Station), South Korea', 'Jeju'),
    '거제도': ('Gujora (Geojedo), South Korea', 'South Gyeongsang'),
    '소무의도': ('Somuuido (Muuido), South Korea', 'Incheon'),
    '어청도': ('Eocheongdo, South Korea', 'North Jeolla'),
    '여호항': ('Yeoho-hang, South Korea', 'South Jeolla'),
    '장항': ('Janghang, South Korea', 'South Chungcheong'),
    '진도': ('Geumgap-ri (Jindo), South Korea', 'South Jeolla'),
    '향화도': ('Hyanghwado-hang (Hampyeong-man), South Korea', 'South Jeolla'),
    '후포': ('Hupo-hang, South Korea', 'North Gyeongsang'),
    '서거차도': ('Seogeochado, South Korea', 'South Jeolla'),
}


def lesen(z):
    teile, kopf = [], None
    with zipfile.ZipFile(z) as f:
        for i in f.infolist():
            raw = f.read(i)
            try:
                t = raw.decode('utf-8-sig')
            except UnicodeDecodeError:
                t = raw.decode('cp949')
            L = t.splitlines()
            name, lat, lon = (L[k].split(':', 1)[1].strip() for k in range(3))
            if L[0].startswith('대상조위관측소'):
                # 조석 성과 / 1시간 조위: volles Jahr "JJJJ/MM/TT HH:MM cm", Luecken interpoliert und im
                # Anhang *결측 구간* noch einmal aufgefuehrt -> diese Stunden fliegen raus. Ohne Position im Kopf.
                k = next((n for n, l in enumerate(L) if '결측 구간' in l), len(L))
                zeilen = [l.split() for l in L[4:k] if l[:2] == '20']
                lueck = {' '.join(l.split()[:2]) for l in L[k:] if l[:2] == '20'}
                d = pd.DataFrame([(a + ' ' + b, v) for a, b, v in zeilen if a + ' ' + b not in lueck], columns=['t', 'h'])
                teile.append(pd.Series(d.h.astype(float).values / 100, index=pd.to_datetime(d.t.str.replace('/', '-')) - pd.Timedelta(hours=9)))
                p = next(x for x in STATIONEN if x['obs_post_name'] == name)
                kopf = (name, p['obs_lat'], p['obs_lon'])
                continue
            h = L[3].split('\t')
            j = h.index('조위(cm)') if '조위(cm)' in h else h.index('Range_조위(cm)')
            z_ = [l.split('\t') for l in L[4:] if l[14:19] == '00:00']
            d = pd.DataFrame([(r[0][:19], r[j].strip()) for r in z_], columns=['t', 'h'])
            d = d[~d.h.isin(['-', ''])]
            teile.append(pd.Series(d.h.astype(float).values / 100, index=pd.to_datetime(d.t.str.replace('/', '-')) - pd.Timedelta(hours=9)))
            kopf = (name, float(lat), float(lon))
    s = pd.concat(teile).sort_index()
    return kopf, s[~s.index.duplicated()]


def main(argv):
    kopf = X.kopf_lesen(ZIEL)
    namen, speeds, arg, fak = kopf
    voll = SF.konstituenten(namen, SF.CONSTIT_67) + [k for k in Q.S.OBERTIDEN if k in namen]
    L = open(ZIEL, encoding='iso-8859-1').read().rstrip('\n').split('\n')
    neu = []
    heute = dt.date.today().strftime('%Y%m%d')
    bestand = [r for r in H.load_records() if r['lat'] and 31 < r['lat'] < 39 and 123 < r['lon'] < 132 and not r['current']]
    for z in sorted(glob.glob(os.path.join(QUELLE, '*.zip'))):
        (hname, la, lo), d = lesen(z)
        name, region = NAMEN.get(hname, (None, None))
        print('\n== %s (%s)  Jahresmedian: %s' % (name or hname, os.path.basename(z),
                                                   ' '.join('%d:%.2f' % (j, v) for j, v in d.groupby(d.index.year).median().items())))
        if not name:
            print('   kein Name in NAMEN')
            continue
        s, start = Q.abschnitt(d)
        if start != d.index[0]:
            print('   Bezugssprung: Reihe ab %s' % start.date())
        tage = (s.index[-1] - s.index[0]).days
        nutz = Q.rayleigh(voll, speeds, namen, tage)
        probe = ''
        if tage >= 2 * 365:
            grenze = s.index[-1] - pd.Timedelta(days=365)
            _, _, pz0, pw, _, _ = Q.fit(s[:grenze], nutz, kopf, speeds, arg, fak)
            te = s[grenze:]
            rp = te.values - SF.hoehe_und_ableitungen(np.array([i.timestamp() for i in te.index]), pz0, pw, kopf)[0]
            rp = rp[np.abs(rp - np.median(rp)) < 5 * np.std(rp)]
            probe = '%.0f' % (100 * np.sqrt(np.mean(rp ** 2)))
        s, t, z0, w, h, aus = Q.fit(s, nutz, kopf, speeds, arg, fak)
        rms = float(np.sqrt(np.mean((s.values - h) ** 2)))
        r2 = 1 - np.var(s.values - h) / np.var(s.values)
        sub = slice(None, None, 7)
        eig = min(range(-30, 31), key=lambda m: np.std(s.values[sub] - SF.hoehe_und_ableitungen(t[sub] - 60 * m, z0, w, kopf)[0]))
        tg = np.arange(dt.datetime(2008, 1, 1).timestamp(), dt.datetime(2027, 1, 1).timestamp(), 1800.0)
        lat_kurve = -float(SF.hoehe_und_ableitungen(tg, 0.0, w, kopf)[0].min())
        nah = sorted(((H.km({'lat': la, 'lon': lo}, r), r) for r in bestand), key=lambda x: x[0])[:3]
        print('   %d h %s..%s (%d d, %d Konst.)  R2 %.3f  RMS %.3f  Probe %s cm  Eigenversatz %+d  M2 %.3f@%.1f  K1 %.3f  Z0 %.2f (LAT-Kurve %.2f)%s' % (
            len(s), s.index[0].date(), s.index[-1].date(), tage, len(nutz), r2, rms, probe or '-', eig, *w['M2'], w['K1'][0], z0, lat_kurve,
            ('  %d Ausreisser' % aus) if aus else ''))
        for k, r in nah:
            print('      ~ %s [%s] %.1f km %.0f%%' % (r['name'], r['file'].split('/')[-1], k, 100 * H.curve_diff(Q.rec(w), r)[1]))
        # Amtliche Pegel messen gegen das koreanische Kartennull (ALLW) wie die KHOA-Tafelsaetze -> Z0 bleibt.
        # Plattformen (Radar) haben ein willkuerliches Null mit Spruengen -> LAT-Kurve.
        datum = 'ALLW (KHOA chart datum)'
        if not hname.endswith('초') and hname != '이어도':
            print('   Pegelnull %+.2f m gegen LAT-Kurve, Z0 bleibt (KHOA-Kartennull)' % (z0 - lat_kurve))
        elif not -0.1 <= z0 - lat_kurve <= 0.4:
            datum = 'approx. LAT (Z0 aus 19-Jahres-Minimum)'
            print('   Pegelnull %.2f m neben LAT-Kurve -> Z0 = %.2f' % (z0 - lat_kurve, lat_kurve))
            z0 = lat_kurve
        if name in L:
            print('   existiert schon')
            continue
        blk = ['#', '# ' + name, '# BEGIN HOT COMMENTS', '# country: South Korea',
               '# source: KHOA Badanuri observation series, least squares',
               '# note: KHOA (Badanuri) downloaded observation data, KST converted to UTC, hourly instantaneous values.',
               '# station_id_context: KHOA-%s' % os.path.basename(z).split('_')[1].replace('KHOA-', ''),
               '# date_imported: %s' % heute, '# datum: %s' % datum, '# confidence: 8',
               '# utide: pts=%d period=%s..%s r2=%.4f rms=%.4fm const=%d' % (len(s), s.index[0].date(), s.index[-1].date(), r2, rms, len(nutz)),
               '# note: %s Messfit aus der KHOA-Reihe (py/khoa_pegel_fit.py), Oliver.' % heute,
               ('# note: Probe am letzten Messjahr %s cm RMS.' % probe) if probe else '# note: Reihe kuerzer als zwei Jahre, keine Probe.',
               '# !units: meters', '# !longitude: %.4f' % lo, '# !latitude: %.4f' % la,
               '# region: %s' % region, name, '+00:00 :Asia/Seoul', '%.4f meters' % z0]
        blk += ['%-15s %.4f  %.2f' % (c, *w[c]) if c in w and w[c][0] >= 0.00005 else 'x 0 0' for c in namen]
        neu += blk
    if '--schreiben' in argv and neu:
        # frisch lesen: Oliver bearbeitet die Datei parallel, der Fit dauert Minuten (24.10.: Umbenennung ueberschrieben)
        frisch = open(ZIEL, encoding='iso-8859-1').read().rstrip('\n')
        schreiben(ZIEL, frisch + '\n' + '\n'.join(neu) + '\n')
        print('->', os.path.relpath(ZIEL, ROOT))


if __name__ == '__main__':
    main(sys.argv[1:])
