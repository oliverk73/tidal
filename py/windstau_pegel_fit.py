#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Messfits fuer Ostsee- und Schwarzmeerpegel ohne Satz (8.11.2026, Oliver: Windstau macht Mikrotide-Orte relevant).

Bisher fehlten sie, weil die Tide dort nur wenige Zentimeter betraegt (z.B. py/pegelonline_ostsee_fit.py: Bodden-
pegel mit M2 < 0.5 cm nicht eingetragen). Mit der Wetterkurve (py/windstau_cmems.py) zaehlt der Wasserstand, und
der Ort braucht einen Satz. Oliver: wo es echte Messungen gibt, nicht FES.

Inventar: harmonics/help/pegel_ostsee_schwarz_20261108.csv (CMEMS INSITU_GLO_PHY_SSH_DISCRETE_MY_013_053 + IOC-Liste,
kein Satz <= 3 km). Weggelassen: Miinisadam (= Hafen Tallinn, Satz 3,2 km), Stockholm (Satz Stockholm (Loudden) 3,7 km),
IOC-Duplikate von CMEMS-Pegeln.
Fit wie py/cmems_tg_fit.py: hoechstens die letzten 10 Jahre, juengster Abschnitt ohne Pegelnull-Sprung, 67 Konstituenten
+ Obertiden (Rayleigh), Probe am letzten Jahr, Eigenversatz. Position: CMEMS-Koordinate, an Land -> naechstes
Wasser bis 1 km (OSM). Namen nur ISO-8859-1 (sonst transliteriert sicher_schreiben die ganze Datei).

Usage: venv/bin/python py/windstau_pegel_fit.py [--laden] [--schreiben] [Name ...]   -> harmonics_utide_observations.txt
"""
import csv
import datetime as dt
import os
import sys
import urllib.request

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cmems_tg_fit as C                                           # noqa: E402
import health_check as H                                           # noqa: E402
import ioc_luecken_fit as I                                        # noqa: E402
import qld_msq_fit as Q                                            # noqa: E402
import scheitelfit as SF                                           # noqa: E402
import seine_haropa_fit as S                                       # noqa: E402
import xtide_modell as X                                           # noqa: E402
from sicher_schreiben import schreiben                             # noqa: E402

ROOT = S.ROOT
ZIEL = S.ZIEL
INDEX = os.path.join(ROOT, 'water_levels/CMEMS_tg_index/index_history.txt')
BASIS = 'https://s3.waw3-1.cloudferro.com/mdl-native-03/native/'
DE, DK, SE, FI, EE, LV, BG, RO, TR, UA = (('Germany', 'Europe/Berlin'), ('Denmark', 'Europe/Copenhagen'),
                                          ('Sweden', 'Europe/Stockholm'), ('Finland', 'Europe/Helsinki'),
                                          ('Estonia', 'Europe/Tallinn'), ('Latvia', 'Europe/Riga'),
                                          ('Bulgaria', 'Europe/Sofia'), ('Romania', 'Europe/Bucharest'),
                                          ('Turkey', 'Europe/Istanbul'), ('Ukraine', 'Europe/Simferopol'))
# CMEMS-Kennung -> (Name ohne Land, Region, (Land, Zeitzone))
PEGEL = {
    'NO_TS_TG_UeckermuendeTG': ('Ueckermünde (Stettiner Haff)', 'Mecklenburg-Vorpommern', DE),
    'NO_TS_TG_WolgastTG': ('Wolgast (Peenestrom)', 'Mecklenburg-Vorpommern', DE),
    'BO_TS_TG_Althagen': ('Althagen (Saaler Bodden)', 'Mecklenburg-Vorpommern', DE),
    'BO_TS_TG_Barhoeft': ('Barhöft', 'Mecklenburg-Vorpommern', DE),
    'BO_TS_TG_Sassnitz': ('Sassnitz (Rügen)', 'Mecklenburg-Vorpommern', DE),
    'NO_TS_TG_WittowerFaehreTG': ('Wittower Fähre (Rügen)', 'Mecklenburg-Vorpommern', DE),
    'BO_TS_TG_Ronne': ('Rønne (Bornholm)', 'Hovedstaden', DK),
    'BO_TS_TG_Tejn': ('Tejn (Bornholm)', 'Hovedstaden', DK),
    'BO_TS_TG_Simrishamn': ('Simrishamn', 'Skåne', SE),
    'BO_TS_TG_Ahus': ('Åhus', 'Skåne', SE),
    'BO_TS_TG_Kungsholmsfort': ('Kungsholmsfort (Karlskrona)', 'Blekinge', SE),
    'BO_TS_TG_Karlshamn': ('Karlshamn', 'Blekinge', SE),
    'BO_TS_TG_Angelholm': ('Ängelholm (Skälderviken)', 'Skåne', SE),
    'BO_TS_TG_Kalmar': ('Kalmar', 'Kalmar', SE),
    'BO_TS_TG_Lielupe': ('Lielupe (Jurmala)', 'Jurmala', LV),
    'BO_TS_TG_Daugavgriva': ('Daugavgriva (Riga)', 'Riga', LV),
    'BO_TS_TG_Oskarshamn': ('Oskarshamn', 'Kalmar', SE),
    'BO_TS_TG_Skulte': ('Skulte', 'Limbazi', LV),
    'BO_TS_TG_Mersrags': ('Mersrags', 'Talsi', LV),
    'BO_TS_TG_OlandsNorraUdde': ('Ölands norra udde (Öland)', 'Kalmar', SE),
    'BO_TS_TG_Ventspils': ('Ventspils', 'Ventspils', LV),
    'BO_TS_TG_Simpevarp': ('Simpevarp', 'Kalmar', SE),
    'BO_TS_TG_Roja': ('Roja', 'Talsi', LV),
    'BO_TS_TG_Visby': ('Visby (Gotland)', 'Gotland', SE),
    'BO_TS_TG_Kolka': ('Kolka', 'Talsi', LV),
    'BO_TS_TG_Vastervik': ('Västervik', 'Kalmar', SE),
    'BO_TS_TG_Salacgriva': ('Salacgriva', 'Limbazi', LV),
    'BO_TS_TG_Munalaiu': ('Munalaiu', 'Pärnumaa', EE),
    'BO_TS_TG_Parnu': ('Pärnu', 'Pärnumaa', EE),
    'BO_TS_TG_Arko': ('Arkö', 'Östergötland', SE),
    'BO_TS_TG_Marviken': ('Marviken', 'Östergötland', SE),
    'BO_TS_TG_Kuivastu': ('Kuivastu (Muhu)', 'Saaremaa', EE),
    'BO_TS_TG_Virtsu': ('Virtsu', 'Pärnumaa', EE),
    'BO_TS_TG_OxelosundVinterklasen': ('Oxelösund (Vinterklasen)', 'Södermanland', SE),
    'BO_TS_TG_NynasFiskehamn': ('Nynäshamn (Fiskehamn)', 'Stockholm', SE),
    'BO_TS_TG_Vahemadal': ('Vahemadal (Tallinna laht)', 'Harjumaa', EE),
    'BO_TS_TG_Leppneeme': ('Leppneeme', 'Harjumaa', EE),
    'BO_TS_TG_Eisma': ('Eisma', 'Lääne-Virumaa', EE),
    'BO_TS_TG_Kelnase': ('Kelnase (Prangli)', 'Harjumaa', EE),
    'BO_TS_TG_Tallinnamadal': ('Tallinnamadal (Leuchtturm)', 'Harjumaa', EE),
    'BO_TS_TG_Degerby': ('Degerby (Föglö, Åland)', 'Åland', FI),
    'BO_TS_TG_Porvoo': ('Porvoo (Emäsalo)', 'Uusimaa', FI),
    'BO_TS_TG_Forsmark': ('Forsmark', 'Uppsala', SE),
    'BO_TS_TG_Bonan': ('Bönan (Gävle)', 'Gävleborg', SE),
    'BO_TS_TG_Rauma': ('Rauma', 'Satakunta', FI),
    'BO_TS_TG_LjusneLotsstation': ('Ljusne', 'Gävleborg', SE),
    'BO_TS_TG_Pori': ('Pori (Mäntyluoto)', 'Satakunta', FI),
    'BO_TS_TG_Kaskinen': ('Kaskinen', 'Pohjanmaa', FI),
    'BO_TS_TG_Spikarna': ('Spikarna (Sundsvall)', 'Västernorrland', SE),
    'BO_TS_TG_Lunde': ('Lunde (Ångermanälven)', 'Västernorrland', SE),
    'BO_TS_TG_Vaasa': ('Vaasa', 'Pohjanmaa', FI),
    'BO_TS_TG_Skagsudde': ('Skagsudde (Örnsköldsvik)', 'Västernorrland', SE),
    'BO_TS_TG_Holmsund': ('Holmsund (Umeå)', 'Västerbotten', SE),
    'BO_TS_TG_Pietarsaari': ('Pietarsaari (Jakobstad)', 'Pohjanmaa', FI),
    'BO_TS_TG_Raahe': ('Raahe', 'Pohjois-Pohjanmaa', FI),
    'BO_TS_TG_Furuogrund': ('Furuögrund (Skellefteå)', 'Västerbotten', SE),
    'BO_TS_TG_Oulu': ('Oulu (Toppila)', 'Pohjois-Pohjanmaa', FI),
    'BO_TS_TG_Stromoren': ('Strömören (Luleå)', 'Norrbotten', SE),
    'BO_TS_TG_Kemi': ('Kemi (Ajos)', 'Lappi', FI),
    'BO_TS_TG_KalixStoron': ('Kalix (Storön)', 'Norrbotten', SE),
    'BO_TS_TG_Haparanda': ('Haparanda', 'Norrbotten', SE),
    'BO_TS_TG_KalixKarlsborg': ('Karlsborg (Kalix)', 'Norrbotten', SE),
    # Schwarzes Meer und Marmarameer (TUDES ueber IOC/CMEMS)
    'BS_TS_TG_IOC-yalo': ('Yalova', 'Yalova', TR),
    'BS_TS_TG_IOC-maer': ('Marmara Ereglisi', 'Tekirdag', TR),
    'BS_TS_TG_IOC-ista': ('Istanbul (Bogazici)', 'Istanbul', TR),
    'BS_TS_TG_IOC-sile': ('Sile', 'Istanbul', TR),
    'BS_TS_TG_IOC-sams': ('Samsun', 'Samsun', TR),
    'BS_TS_TG_IOC-amas': ('Amasra', 'Bartin', TR),
    'BS_TS_TG_IOC-igne': ('Igneada', 'Kirklareli', TR),
    'BS_TS_TG_IOC-sino': ('Sinop', 'Sinop', TR),
    # verworfen 8.11.: BS_TS_TG_BurgasSouth (Pegelsprung 2016, Probe 49 cm; Satz Burgas 6 km),
    #                  BS_TS_TG_IOC-kaci Katsiveli (R2 1.00 bei 1 mm Rest: kuenstlich glatte Reihe, 1,3 Jahre)
    'BS_TS_TG_Pomorie': ('Pomorie', 'Burgas', BG),
    'BS_TS_TG_IOC-mang': ('Mangalia', 'Constanta', RO),
    'BS_TS_TG_IOC-csta2': ('Constanta', 'Constanta', RO),
}
# Sensornull willkuerlich (TUDES ~2 m, Constanta/Mangalia ~-7.7 m): Z0 wie bei FES = -Minimum der 19-Jahres-Kurve (~LAT).
# Ostsee: nationaler Hoehenbezug (~Mittelwasser), Z0 = Mittel darueber wie die amtlichen Pegelstaende.
SENSORNULL = {k for k in PEGEL if k.startswith('BS_TS_TG_IOC-')}


def index():
    out = {}
    for l in open(INDEX, encoding='utf-8', errors='replace'):
        if l.startswith('#'):
            continue
        f = l.split(',')
        k = f[1].split('/')[-1].replace('_60minute.nc', '')
        if k in PEGEL:
            out[k] = (f[1], float(f[2]), float(f[4]))
    return out


def main(argv):
    import osm_land
    idx = index()
    fehlt = [k for k in PEGEL if k not in idx]
    if fehlt:
        print('nicht im Index:', fehlt)
    os.makedirs(C.REIHEN, exist_ok=True)
    if '--laden' in argv:
        for k, (pfad, _la, _lo) in idx.items():
            ziel = os.path.join(C.REIHEN, os.path.basename(pfad))
            if not os.path.exists(ziel):
                urllib.request.urlretrieve(BASIS + pfad, ziel)
                print('geladen', os.path.basename(pfad))
    kopf = X.kopf_lesen(ZIEL)
    namen, speeds, arg, fak = kopf
    voll = SF.konstituenten(namen, SF.CONSTIT_67) + [k for k in S.OBERTIDEN if k in namen]
    L = open(ZIEL, encoding='iso-8859-1').read().rstrip('\n').split('\n')
    heute = dt.date.today().strftime('%Y%m%d')
    bestand = [r for r in H.load_records() if r['lat'] and not r['current']]
    LM = osm_land.Land([(v[1], v[2]) for v in idx.values()])
    nur = [a for a in argv if not a.startswith('--')]
    zeilen, neu = [], []
    for k, (pfad, la0, lo0) in idx.items():
        ort, region, (land, tz) = PEGEL[k]
        name = '%s, %s' % (ort, land)
        if nur and name not in nur and k not in nur:
            continue
        datei = os.path.basename(pfad)
        if not os.path.exists(os.path.join(C.REIHEN, datei)):
            print('== %s: Reihe fehlt (--laden)' % name)
            continue
        roh = C.reihe(datei, None)
        if len(roh) < 24 * 300:
            print('== %s: zu kurz (%d h)' % (name, len(roh)))
            continue
        s, start = Q.abschnitt(roh)
        tage = (s.index[-1] - s.index[0]).days
        if tage < 365:
            print('== %s: juengster Abschnitt ohne Sprung nur %d Tage' % (name, tage))
            continue
        nutz = Q.rayleigh(voll, speeds, namen, tage)
        grenze = s.index[-1] - pd.Timedelta(days=365)
        probe = '-'
        if (grenze - s.index[0]).days >= 300:
            _, _, pz0, pw, _, _ = Q.fit(s[:grenze], nutz, kopf, speeds, arg, fak)
            te = s[grenze:]
            rp = te.values - SF.hoehe_und_ableitungen(np.array([i.timestamp() for i in te.index]), pz0, pw, kopf)[0]
            rp = rp[np.abs(rp - np.median(rp)) < 5 * np.std(rp)]
            probe = '%.0f' % (100 * np.sqrt(np.mean(rp ** 2)))
            if float(probe) > 100:
                probe = '-'                                         # Teilfit entartet (Luecke), keine Aussage
        s, t, z0, w, h, aus = Q.fit(s, nutz, kopf, speeds, arg, fak)
        rms = float(np.sqrt(np.mean((s.values - h) ** 2)))
        r2 = 1 - np.var(s.values - h) / np.var(s.values)
        sub = slice(None, None, 7)
        eig = min(range(-30, 31), key=lambda m: np.std(s.values[sub] - SF.hoehe_und_ableitungen(t[sub] - 60 * m, z0, w, kopf)[0]))
        datum = 'CMEMS SLEV'                                         # nur bestehende Datum-Namen: TCD-Tabelle voll, <= 70 Zeichen
        dnote = 'Hoehenbezug der Reihe = nationales Hoehensystem (~Mittelwasser), Z0 = Mittel darueber.'
        if k in SENSORNULL:
            tg = np.arange(dt.datetime(2008, 1, 1).timestamp(), dt.datetime(2027, 1, 1).timestamp(), 3600.0)
            z0 = -float(SF.hoehe_und_ableitungen(tg, 0.0, w, kopf)[0].min())
            datum = 'approx. LAT (Z0 = -Minimum der 19-Jahres-Kurve)'
            dnote = 'Sensornull der Reihe willkuerlich, daher Z0 wie bei FES-Saetzen.'
        la, lo, verschoben = I.wasser(la0, lo0, LM)
        if verschoben == -1:                                        # kein Wasser <= 1 km (Fluss? Landmaske kennt nur Kueste)
            print('   %s: CMEMS-Position an Land, kein Wasser <= 1 km -- von Hand setzen' % name)
            verschoben = 0
        nb = min(bestand, key=lambda r: H.km({'lat': la, 'lon': lo}, r))
        print('== %-44s %s..%s R2 %.2f RMS %.3f Probe %s cm Eigenv %+d  M2 %.3f@%.0f K1 %.3f@%.0f O1 %.3f@%.0f  Z0 %.2f  %s  Nachbar %s %.0f km %.0f%%' % (
            name, s.index[0].date(), s.index[-1].date(), r2, rms, probe, eig, *w['M2'], *w['K1'], *w['O1'], z0,
            ('verschoben %.0f m' % verschoben) if verschoben else 'Position CMEMS', nb['name'][:22], H.km({'lat': la, 'lon': lo}, nb),
            100 * H.curve_diff(Q.rec(w), nb)[1]))
        zeilen.append(dict(kennung=k, name=name, von=s.index[0].date(), bis=s.index[-1].date(), r2='%.3f' % r2,
                           rms='%.3f' % rms, probe_cm=probe, eigenversatz=eig, m2='%.3f' % w['M2'][0], k1='%.3f' % w['K1'][0],
                           lat='%.4f' % la, lon='%.4f' % lo, verschoben_m='%.0f' % (verschoben or 0)))
        kenn = k.replace('_TS_TG_', ' ').split(' ')[-1]
        blk = ['#', '# %s (CMEMS %s)' % (ort, kenn), '# BEGIN HOT COMMENTS', '# country: %s' % land,
               '# source: CMEMS in-situ %s, least squares' % k,
               '# note: CMEMS INSITU_GLO_PHY_SSH_DISCRETE_MY_013_053, Stundenwerte SLEV (QC 1/2), UTC.',
               '# station_id_context: CMEMS-%s' % k, '# date_imported: %s' % heute, '# datum: %s' % datum, '# note: %s' % dnote, '# confidence: 8',
               '# utide: pts=%d period=%s..%s r2=%.4f rms=%.4fm const=%d' % (len(s), s.index[0].date(), s.index[-1].date(), r2, rms, len(nutz)),
               '# note: %s Messfit (py/windstau_pegel_fit.py): Mikrotide-Pegel, Wasserstand vom Wetter bestimmt (Windstau-Kurve).' % heute,
               '# note: Probe am letzten Messjahr %s cm RMS (ueberwiegend Wetter, kein Tidenfehler).' % probe]
        if verschoben:
            blk.append('# note: CMEMS-Position %.4f/%.4f liegt laut OSM an Land, %.0f m ins Wasser gelegt.' % (la0, lo0, verschoben))
        blk += ['# !units: meters', '# !longitude: %.4f' % lo, '# !latitude: %.4f' % la, '# region: %s' % region,
                name, '+00:00 :%s' % tz, '%.4f meters' % z0]
        blk += ['%-15s %.4f  %.2f' % (c, *w[c]) if c in w and w[c][0] >= 0.00005 else 'x 0 0' for c in namen]
        if name in L:
            print('   existiert schon in %s' % os.path.basename(ZIEL))
            continue
        neu.append((name, blk))
    if zeilen:
        with open(os.path.join(ROOT, 'harmonics/help/windstau_pegel_fit_20261108.csv'), 'w', encoding='utf-8', newline='') as fh:
            wr = csv.DictWriter(fh, fieldnames=list(zeilen[0]))
            wr.writeheader()
            wr.writerows(zeilen)
    if '--schreiben' in argv:
        # frisch lesen und nur anhaengen: Oliver bearbeitet die Datei parallel (Notiz skripte-frisch-lesen-vor-schreiben)
        L = open(ZIEL, encoding='iso-8859-1').read().rstrip('\n').split('\n')
        for name, blk in neu:
            if name not in L:
                L += blk
        for z in L:
            z.encode('iso-8859-1')                                  # bricht ab statt zu transliterieren
        schreiben(ZIEL, '\n'.join(L) + '\n')
        print('->', os.path.relpath(ZIEL, ROOT))


if __name__ == '__main__':
    main(sys.argv[1:])
