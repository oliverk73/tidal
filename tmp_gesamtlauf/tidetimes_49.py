#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Die 49 nachgeholten tidetimes-Tafeln (grosse Haefen) gegen den Bestand.

Je Tafel: Kosinus+UTide-Fit wie bei den 675 alten (feste BST), Fit auf
2025-06..2026-06, Tafeltreue auf dem Rest (Juli-Sept. 2026).
Schiedsrichter ist nicht die Tafel, sondern:
  1. eine echte Messreihe unter 3 km (Saetze, die auf genau dieser Reihe
     gefittet sind, messen sich selbst -> 'eigen', zaehlen nicht),
  2. sonst der Konsens der unabhaengigen Nachbarn (wie nachbarprobe).
Schreibt nur eine Vorschlagsliste, nichts in den Bestand.
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import os
import sys

import numpy as np
import utide

ROOT = '/home/oliver/weather'
sys.path.insert(0, os.path.join(ROOT, 'py'))
import scheitelfit as S                                            # noqa: E402
import xtide_modell as X                                           # noqa: E402
from batch_utide_uk_tidetimes import CONSTIT_67, cosine_interpolate  # noqa: E402
from generate_germany_harmonics_175 import find_xtide_match        # noqa: E402
from health_check import km, load_records                          # noqa: E402

LISTE = os.path.join(ROOT, 'water_levels/UK_tidetimes/uebersprungen_20260913.json')
AUS = os.path.join(ROOT, 'harmonics/help/tidetimes_grosshaefen.csv')
GRENZE = dt.datetime(2026, 7, 1, tzinfo=dt.timezone.utc).timestamp()
UMKREIS_BESTAND, UMKREIS_REIHE = 3.0, 5.0


def eigen_saetze():
    """{(reihe-datei, satz, datei)} -- Saetze, die auf dieser Reihe gefittet sind."""
    out = set()
    for name in ('bodc_qualitaet.csv', 'ea_qualitaet.csv', 'messreihe_qualitaet_alle.csv'):
        p = os.path.join(ROOT, 'harmonics/help', name)
        if os.path.exists(p):
            for z in csv.DictReader(open(p, encoding='utf-8')):
                if z.get('eigen') in ('1', 'ja'):
                    out.add((z['station'], z['satz'], z['datei']))
    return out


def utide_fit(t, h, lat):
    hw_lw = [(dt.datetime.fromtimestamp(a, dt.timezone.utc).replace(tzinfo=None), b)
             for a, b in zip(t, h)]
    dts, lev = cosine_interpolate(hw_lw)
    coef = utide.solve(dts, lev, lat=lat, nodal=True, trend=False, method='ols',
                       conf_int='none', verbose=False, constit=CONSTIT_67)
    from utide._ut_constants import ut_constants
    ct = ut_constants['const']
    alle = [x.strip() for x in ct.name]
    werte = {}
    for i, u in enumerate(coef['name']):
        u = u.strip()
        if u in alle:
            xn, _ = find_xtide_match(u, ct.freq[alle.index(u)] * 360.0)
            if xn:
                werte[xn] = (float(coef['A'][i]), float(coef['g'][i]) % 360.0)
    return float(coef['mean']), werte


def gegen_reihe(pfad_reihe, zeitraum, z0, werte, kopf):
    """Wie scheitelfit.gegen_reihe, aber Versatz bis +-3 h (Portland lag am Rand)."""
    import messreihe_qualitaet as M
    obs = M.lies(pfad_reihe)
    if len(obs) < 2000:
        return None
    ot = np.array([x[0] for x in obs]); oh = np.array([x[1] for x in obs])
    m = (ot >= zeitraum[0]) & (ot <= zeitraum[1])
    if m.sum() >= 2000:
        ot, oh = ot[m], oh[m]
    if len(ot) > 30000:
        ot, oh = ot[-30000:], oh[-30000:]
    best = None
    for v in range(-180, 181, 5):
        hv = S.hoehe_und_ableitungen(ot + v * 60, z0, werte, kopf)[0]
        d = oh - hv
        rms = float(np.sqrt(np.mean((d - d.mean()) ** 2)))
        if best is None or rms < best[0]:
            best = (rms, v)
    return best


def satz_greenwich(r, speeds):
    z0, w, einheit, mer = X.satz_lesen(r['file'], r['name'])
    sk = 0.3048 if einheit.startswith('f') else 1.0
    return z0 * sk, {k: (a * sk, X.greenwich(kap, speeds[k], mer))
                     for k, (a, kap) in w.items() if k in speeds}


def main():
    kopf = X.kopf_lesen(S.KOPFQUELLE)
    speeds = kopf[1]
    recs = load_records()
    reihen = S.echte_reihen()
    # Reihen, an denen kein einziger Satz unter 20 cm bleibt, taugen nicht als
    # Schiedsrichter (rloi3289 Chesil Cove: alle Saetze -190..-230 min, 46-70 cm).
    beste = {}
    for n in ('bodc_qualitaet.csv', 'ea_qualitaet.csv'):
        for z in csv.DictReader(open(os.path.join(ROOT, 'harmonics/help', n), encoding='utf-8')):
            if z['rms_m']:
                beste[z['station']] = min(beste.get(z['station'], 9.0), float(z['rms_m']))
    reihen = {p: v for p, v in reihen.items() if beste.get(os.path.basename(p), 9.0) <= 0.20}
    eigen = eigen_saetze()
    zeilen = []
    for st in json.load(open(LISTE, encoding='utf-8')):
        pfad = os.path.join(ROOT, 'water_levels/UK_tidetimes', st['name'].replace(' ', '_') + '.json')
        if not os.path.exists(pfad):
            kand = [p for p in os.listdir(os.path.join(ROOT, 'water_levels/UK_tidetimes'))
                    if p.lower().startswith(st['slug'].split('-')[0])]
            print('fehlt', st['name'], kand[:3])
            continue
        t, h, name, lat, lon = S.tafel(pfad)
        if t is None or len(t) < 500:
            print('zu kurz', st['name'])
            continue
        fit_m = t < GRENZE
        z0, werte = utide_fit(t[fit_m], h[fit_m], lat)
        test = ~fit_m
        hier = {'lat': lat, 'lon': lon}
        kandidaten = [('NEU tidetimes-Fit', '(neu)', z0, werte, 0.0)]
        for r in recs:
            d = km(r, hier)
            if d <= UMKREIS_BESTAND and 'current' not in r['file'].lower():
                try:
                    rz0, rw = satz_greenwich(r, speeds)
                except (KeyError, IndexError, ValueError):
                    continue
                kandidaten.append((r['name'], os.path.basename(r['file']), rz0, rw, d))
        nah = sorted(((p, km(hier, {'lat': a, 'lon': b})) for p, (a, b) in reihen.items()),
                     key=lambda x: x[1])
        reihe = nah[0][0] if nah and nah[0][1] <= UMKREIS_REIHE else None
        for nm, datei, kz0, kw, d in kandidaten:
            rms_t, dt_t, _o = S.guete(t[test], h[test], kz0, kw, kopf)
            echt = gegen_reihe(reihe, (t[0], t[-1]), kz0, kw, kopf) if reihe else None
            ist_eigen = reihe is not None and (os.path.basename(reihe), nm, datei) in eigen
            z = dict(tafel=name, satz=nm, datei=datei, km=round(d, 2),
                     tafel_test_cm=round(rms_t * 100, 1), tafel_dt_min=round(dt_t, 1),
                     reihe=os.path.basename(reihe) if reihe else '',
                     reihe_km=round(nah[0][1], 2) if reihe else '',
                     echt_cm='' if not echt else round(echt[0] * 100, 1),
                     echt_versatz_min='' if not echt else echt[1],
                     eigen='ja' if ist_eigen else '', nachbar_pct='', empfehlung='')
            zeilen.append(z)
        # Nachbarkonsens fuer neu und den besten Bestandssatz (Tafeltest)
        block = [z for z in zeilen if z['tafel'] == name]
        alt = [z for z in block if z['datei'] != '(neu)']
        neu = block[0]
        if alt:
            if reihe:
                fair = [z for z in alt if z['echt_cm'] != '' and not z['eigen']]
                bester = min(fair, key=lambda z: z['echt_cm']) if fair else None
            else:
                bester = min(alt, key=lambda z: z['tafel_test_cm'])
            if not bester and any(z['eigen'] for z in alt):
                neu['empfehlung'] = 'nicht aufnehmen (Bestand aus Messung an diesem Pegel)'
            if bester:
                na, nn = S.nachbar_urteil(recs, lat, lon, (bester['satz'], bester['datei']),
                                          z0, werte, speeds)
                bester['nachbar_pct'] = '' if na is None else round(na, 1)
                neu['nachbar_pct'] = '' if nn is None else round(nn, 1)
                if any(z['eigen'] for z in alt):
                    neu['empfehlung'] = 'nicht aufnehmen (Bestand aus Messung an diesem Pegel)'
                elif reihe and neu['echt_cm'] != '':
                    if neu['echt_cm'] < bester['echt_cm'] - 1.0 and abs(neu['echt_versatz_min']) <= 5:
                        neu['empfehlung'] = f'besser am Pegel als {bester["satz"]}'
                    else:
                        neu['empfehlung'] = 'nicht aufnehmen (Pegel)'
                elif na is not None:
                    neu['empfehlung'] = ('Nachbarn fuer neu' if nn < na - 2.0 else
                                         'nicht aufnehmen (Nachbarn)' if nn > na + 2.0 else
                                         'nicht aufnehmen (unentschieden)')
                else:
                    neu['empfehlung'] = 'offen'
        else:
            neu['empfehlung'] = 'kein Bestand im Umkreis'
        print(f"{name[:28]:28} neu Tafel {neu['tafel_test_cm']:5.1f} echt {neu['echt_cm']!s:>5} "
              f"({neu['echt_versatz_min']!s:>3})  Bestand {len(alt)}  -> {neu['empfehlung']}", flush=True)
    with open(AUS, 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=list(zeilen[0].keys()))
        w.writeheader()
        w.writerows(zeilen)
    print('->', AUS)


if __name__ == '__main__':
    main()
