#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Harmonische Konstanten aus den Pushidrosal-Stundentafeln (41 Marinehaefen).

Eingang: tide_tables/indonesia/pushidrosal_berichte_2026.json
(py/pushidrosal_laden.py + py/pushidrosal_berichte.py: Monatstafeln 05/2024-08/2026).

Gerechnet wird wie bei den BMKG-Saetzen (py/build_bmkg_indonesia.py): UTide,
OLS, nodal, feste Partialtidenliste, Greenwich-Phasen. Geprueft am 21.09.2026:

  Zeit     Spalte k der Tafel ist k Uhr Ortszeit (Zone steht bei jedem Hafen).
           Gegen die acht Messreihen-Saetze in der Naehe (TICON, UHSLC-Fits)
           liegen die Phasen im Median bei M2 +2, S2 +3, K1 -5 min.
  Lang     SA, SSA, MM, MF enthalten die Tafeln nicht (SA 0.0-0.3 cm ueber
           28 Monate); Z0 ist eine runde Zahl, Pushidrosal setzt sie fest.
           Flachwassertiden ueber die 18 hinaus bringen <= 0.1 cm.
  Rest     2.9 cm, also genau das Rundungsrauschen einer 0.1-m-Tafel. Das misst
           die Treue zur Tafel, nicht die Guete der Tafel.

MODELLWECHSEL. Pushidrosal hat die Tafeln nicht durchgehend gleich gerechnet:
26 Haefen folgen 28 Monate lang einem Modell, zehn wurden zwischendurch neu
gerechnet (Sabang, Tarempa, Tanjung Perak, Tanjung Wangi, Pontianak zum
Jahreswechsel 2026; Semarang, Dabo, Tanjung Uban, Pulau Nipa, Kendari frueher),
und einzelne Monate tragen eine falsche Tafel (Belawan 01/2026: 25 cm Rest).
Alles zusammen gefittet mischt zwei Modelle. Deshalb je Hafen: Fit auf die
juengsten sechs Monate, dann alle Monate behalten, deren Rest unter GRENZE
liegt, neu fitten, wiederholen. Das Ergebnis ist der AKTUELLE Stand.

Dass der aktuelle Stand der bessere ist, ist an Messungen belegt: Sabang neu
3.2 % gegen alt 10.9 %, Tanjung Perak 3.7 gegen 7.0, Semarang 6.5 gegen 10.7
(Kurvenunterschied zum Messreihen-Satz). Kendari war vorher fast 180 Grad
verdreht.

Usage: python3 py/fit_pushidrosal_berichte.py            Pruefbericht
       python3 py/fit_pushidrosal_berichte.py --saetze   Saetze nach harmonics/help/pushidrosal_saetze.txt
"""
from __future__ import annotations

import cmath
import collections
import csv
import datetime as dt
import json
import math
import os
import sys
import warnings

import numpy as np
import utide

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import region_felder_fuellen as RF                                 # noqa: E402
import xtide_modell as X                                           # noqa: E402
from health_check import MAIN, ROOT, curve_diff, km, load_records  # noqa: E402

warnings.filterwarnings('ignore')
EIN = os.path.join(ROOT, 'tide_tables/indonesia/pushidrosal_berichte_2026.json')
SAETZE = os.path.join(ROOT, 'harmonics/help/pushidrosal_saetze.txt')
BERICHT = os.path.join(ROOT, 'harmonics/help/pushidrosal_vergleich.csv')
KOPF = os.path.join(ROOT, 'harmonics/utide/harmonics_utide_tidetables.txt')
HEUTE = dt.date.today().strftime('%Y%m%d')

CONSTIT = ['M2', 'S2', 'N2', 'K2', 'K1', 'O1', 'P1', 'Q1', '2N2', 'NU2', 'MU2',
           'L2', 'T2', 'M4', 'MS4', 'MN4', 'M6', '2MS6']
GRENZE = 0.040          # Monatsrest in m, ab dem ein Monat nicht zum Modell gehoert
START_MONATE = 6        # damit beginnt die Suche (>= 182.6 d fuer K1/P1 und S2/K2)
ZONE = {7: 'Asia/Jakarta', 8: 'Asia/Makassar', 9: 'Asia/Jayapura'}
MESSUNG = ('harmonics_utide_observations.txt', 'harmonics_ticon4_worldwide.txt')

# Tafeln, deren Konstantensatz nachweislich falsch ist -- sie werden nicht gefittet.
# Belege in harmonics/help/loeschen_<datum>_pushidrosal_*.csv, Satz im Archiv.
AUSSCHLUSS = {
    # M2 0.110@56 statt ~0.21@359: halbe Amplitude, fast 2 h Versatz, O1 7 h.
    # BMKG Cilegon (0.7 km) und alle Nachbarn der Sunda-Strasse stimmen
    # untereinander (5-11 %), gegen diese Tafel 36-49 %. Pruefung 21.09.2026.
    # Bestaetigt durch den BIG-Messpegel BNTN (Pel. Ciwandan, py/srgi_pegel.py):
    # Rest gegen die Messung BMKG 3.2 cm, Cikoneng 0.9, diese Tafel 18.6 cm.
    'Ciwandan',
}

# Pushidrosal-Namen in der Form des Bestands
NAME = {'Batu Ampar/Batam': 'Batu Ampar (Batam)',
        'Pulau Bai Bengkulu': 'Pulau Baai (Bengkulu)',
        'Panjang Lampung': 'Panjang (Lampung)',
        'Penagi Ranai': 'Penagi (Ranai, Natuna)',
        'Dabo Singkep': 'Dabo (Pulau Singkep)',
        'Tarempa': 'Tarempa (Anambas)'}


def reihe(s):
    t, h = [], []
    for d, w in sorted(s['tage'].items()):
        d0 = dt.datetime.fromisoformat(d)
        for k, v in enumerate(w, start=1):
            t.append(d0 + dt.timedelta(hours=k - s['tz']))
            h.append(v)
    return np.array(t), np.array(h)


def loesen(t, h, lat):
    return utide.solve(t, h, lat=lat, nodal=True, trend=False, method='ols',
                       conf_int='none', constit=CONSTIT, verbose=False)


def monatsrest(t, h, c):
    res = h - utide.reconstruct(t, c, verbose=False).h
    m = collections.defaultdict(list)
    for ti, r in zip(t, res):
        m[ti.strftime('%Y-%m')].append(r)
    return {k: float(np.sqrt(np.mean(np.square(v)))) for k, v in m.items()}, res


def aktuelles_modell(s):
    """-> (coef, gewaehlte Monate, verworfene Monate, Rest, n, t0, t1)."""
    t, h = reihe(s)
    monat = np.array([x.strftime('%Y-%m') for x in t])
    alle = sorted(set(monat))
    wahl = alle[-START_MONATE:]
    for _ in range(4):
        c = loesen(t[np.isin(monat, wahl)], h[np.isin(monat, wahl)], s['lat'])
        mr, _ = monatsrest(t, h, c)
        neu = [m for m in alle if mr[m] <= GRENZE]
        if neu == wahl:
            break
        wahl = neu
    sel = np.isin(monat, wahl)
    c = loesen(t[sel], h[sel], s['lat'])
    _mr, res = monatsrest(t, h, c)
    weg = [m for m in alle if m not in wahl]
    return c, wahl, weg, float(np.sqrt(np.mean(res[sel] ** 2))), int(sel.sum()), t[sel][0], t[sel][-1]


def als_record(c, lat, lon):
    k = {n: (a, g) for n, a, g in zip(c.name, c.A, c.g)}
    z = {x: cmath.rect(k.get(x, (0, 0))[0], -math.radians(k.get(x, (0, 0))[1])) for x in MAIN}
    return dict(z=z, tot=sum(abs(v) for v in z.values()), lat=lat, lon=lon), k


def provinz(p, recs, polys):
    """Provinz des naechsten Bestandssatzes bis 40 km -- Natural Earth kennt die
    Neugliederung von 2022 nicht (Papua Selatan, Papua Barat Daya)."""
    nah = sorted(((km(p, r), i) for i, r in enumerate(recs)
                  if r['name'].endswith(', Indonesia') and km(p, r) < 40))
    if nah:
        return recs[nah[0][1]]['name'].split(',')[-2].strip()
    w = RF.welches(p['lon'], p['lat'], polys) or RF.naechstes(p['lon'], p['lat'], polys, 60)
    return w[1] if w else ''


def kurz(monate):
    if not monate:
        return ''
    # zusammenhaengende Laeufe "2024-05..2025-12"
    laeufe, a = [], monate[0]
    for x, y in zip(monate, monate[1:] + [None]):
        if y is None or (int(y[:4]) * 12 + int(y[5:])) - (int(x[:4]) * 12 + int(x[5:])) != 1:
            laeufe.append(a if a == x else f'{a}..{x}')
            a = y
    return ', '.join(laeufe)


def main(argv):
    P = json.load(open(EIN, encoding='utf-8'))
    recs = [r for r in load_records() if r['lat'] is not None and not r['current']]
    polys = RF.polygone()
    namen, _sp, _a, _f = X.kopf_lesen(KOPF)
    zeilen, bloecke = [], []
    for roh, s in sorted(P.items(), key=lambda x: x[1]['nr']):
        if roh in AUSSCHLUSS:
            print(f'  ausgeschlossen: {roh}')
            continue
        c, wahl, weg, rms, n, t0, t1 = aktuelles_modell(s)
        weg = [m for m in weg if m >= '2024-05']          # 2024-04 = die ersten Stunden in UTC
        neu, k = als_record(c, s['lat'], s['lon'])
        prov = provinz(neu, recs, polys)
        name = f'{NAME.get(roh, roh)}, {prov}, Indonesia'
        nah = sorted(((km(neu, r), i) for i, r in enumerate(recs) if km(neu, r) <= 15.0))
        wechsel = weg and weg[-1] > wahl[0]              # verworfene Monate VOR dem aktuellen Modell
        z = dict(nr=s['nr'], name=name, lat=s['lat'], lon=s['lon'], tz=s['tz'],
                 tage=round(n / 24), von=f'{t0:%Y-%m}', bis=f'{t1:%Y-%m}', verworfen=kurz(weg),
                 z0=round(float(c.mean), 3), rms_cm=round(rms * 100, 2),
                 M2=round(k['M2'][0], 3), F=round((k['K1'][0] + k['O1'][0]) / max(1e-6, k['M2'][0] + k['S2'][0]), 2),
                 messung='', messung_pct='', unter_3km='')
        mess = [(d, recs[i]) for d, i in nah if os.path.basename(recs[i]['file']) in MESSUNG]
        if mess:
            z.update(messung=f"{mess[0][1]['name'].split(',')[0]} ({mess[0][0]:.1f} km)",
                     messung_pct=round(curve_diff(neu, mess[0][1])[1] * 100, 1))
        z['unter_3km'] = '; '.join(
            f"{recs[i]['name'].split(',')[0]} [{os.path.basename(recs[i]['file']).replace('harmonics_', '').replace('.txt', '')}] "
            f"{curve_diff(neu, recs[i])[1] * 100:.1f}%" for d, i in nah if d <= 3.0)
        zeilen.append(z)

        vermerk = [f'# note: Aktuelles Pushidrosal-Modell {t0:%Y-%m}..{t1:%Y-%m} ({n / 24:.0f} Tage).']
        if weg:
            vermerk.append(f'# note: Verworfen (Rest > {GRENZE * 100:.0f} cm gegen dieses Modell): {kurz(weg)}.')
        if wechsel:
            vermerk.append('# note: Pushidrosal hat die Tafel davor anders gerechnet; py/fit_pushidrosal_berichte.py.')
        kopf = (['# BEGIN HOT COMMENTS', '# country: Indonesia', f'# state: {prov}',
                 '# source: Pushidrosal (TNI AL) Prediksi Pasut di Fasilitas Labuh TNI AL, hourly tide tables',
                 f'# station_id_context: Pushidrosal-Labuh-{s["nr"]:02d}',
                 '# note: Vorhersagetafel (kein Rohmesswert), 0.1 m gerundet, aus den taeglichen',
                 '# note: Lageberichten (py/pushidrosal_laden.py, py/pushidrosal_berichte.py).',
                 '# note: Zeit gegen acht Messreihen geprueft (M2 +2 min); SA/SSA/MM/MF fehlen in den Tafeln.']
                + vermerk +
                [f'# date_imported: {HEUTE}', '# datum: Chart Datum (Pushidrosal)', '# confidence: 6',
                 f'# utide: period={t0:%Y-%m-%d}..{t1:%Y-%m-%d}(1h) constit={len(CONSTIT)} n={n}; '
                 f'rms={rms * 100:.1f}cm (Rundung der Tafel)',
                 '# !units: meters', f'# !longitude: {s["lon"]:.4f}', f'# !latitude: {s["lat"]:.4f}',
                 name, f'+00:00 :{ZONE.get(s["tz"], "UTC")}', f'{float(c.mean):.4f} meters'])
        for x in namen:
            if x in k and k[x][0] >= 0.00005:
                kopf.append(f'{x:<16}{k[x][0]:.4f}  {k[x][1] % 360:.2f}')
            else:
                kopf.append('x 0 0')
        bloecke.append('\n'.join(kopf))

    with open(BERICHT, 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=list(zeilen[0]))
        w.writeheader()
        w.writerows(zeilen)
    print(f'-> {os.path.relpath(BERICHT, ROOT)}')
    print(f"{'nr':>2} {'Name':46s} {'Tage':>4} {'Zeitraum':15s} {'rms':>4} {'Mess.':>5}  bis 3 km im Bestand")
    for z in zeilen:
        print(f"{z['nr']:2d} {z['name'][:46]:46s} {z['tage']:4d} {z['von']}..{z['bis'][2:]} {z['rms_cm']:4.1f} "
              f"{(str(z['messung_pct']) + '%') if z['messung'] else '':>5}  {z['unter_3km'][:95] or '(nichts)'}")
    if '--saetze' in argv:
        open(SAETZE, 'w', encoding='iso-8859-1').write('\n'.join(bloecke) + '\n')
        print(f'-> {os.path.relpath(SAETZE, ROOT)}  ({len(bloecke)} Saetze, noch NICHT im Bestand)')


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
