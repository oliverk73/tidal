#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Messfits fuer ungenutzte IOC- und UHSLC-Pegel (Lueckensuche 02.11.2026, Oliver).

Kandidaten: Kennung in keinem aktiven Satz, Springhub (FES, 2*(M2+S2)) >= 0,2 m, kein Messsatz
unter 1 km (dort ist es meist dasselbe Geraet ueber eine andere Quelle).

Pruefung wie py/ioc_russland_fit.py: je Monat Versatz gegen FES (|dt| <= 30 min, r > 0.3, kein
Pegelnull-Sprung), Pegelnull-Stufen ausgeglichen, Eigenprobe 0 min. Guete: mindestens 2000 h;
R2 >= 0.85, bei kleinem Hub (< 0,6 m) R2 >= 0.5 (das Wetter ueberdeckt dort einen Teil der Tide).
Position: Katalogkoordinate, liegt sie an Land, das naechste Wasser bis 1 km (OSM).

Eingabe: JSON-Liste mit Eintraegen {q, code, name, region, lat, lon, hub, csv}
  csv: Zeitreihe (Zeit UTC, Wasserstand m), z. B. water_levels/Russia_IOC/ioc_<code>_monate.csv
Usage: venv/bin/python py/messpegel_luecken.py liste.json [--schreiben] [--nur code,code]
Ausgabe: Protokoll je Pegel und eine Ergebnis-JSON neben der Liste (<liste>.ergebnis.json).
"""
import contextlib
import datetime as dt
import io
import json
import math
import os
import sys

import numpy as np
import pandas as pd
import utide

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ioc_russland_fit as R                                       # noqa: E402
import xtide_modell as X                                           # noqa: E402
from ioc_luecken_fit import wasser                                 # noqa: E402
from sicher_schreiben import schreiben                             # noqa: E402

ROOT = R.ROOT
ZIEL = R.ZIEL


def reihe(pfad):
    d = pd.read_csv(os.path.join(ROOT, pfad))
    s = pd.Series(pd.to_numeric(d.iloc[:, 1], errors='coerce').values,
                  index=pd.to_datetime(d.iloc[:, 0], utc=True)).dropna()
    s = s[~s.index.duplicated()].sort_index()
    return s[(s - s.median()).abs() < 6 * s.std()] if len(s) else s


def fitten(e, namen, speeds, arg, fak, protokoll):
    s = reihe(e['csv'])
    if len(s) < 24 * 60:
        protokoll.append('   zu wenig Daten (%d h)' % len(s))
        return None
    tag = s.resample('D').mean()
    sprung = tag.rolling(7, center=True, min_periods=4).median().diff().abs() > 0.4
    f = pd.Series(R.fes_kurve(s.index, e['lat'], e['lon'], namen, speeds, arg, fak), index=s.index)
    gut = []
    for m, g in s.groupby(s.index.tz_convert(None).to_period('M')):
        if len(g) < 24 * 20:
            continue
        reg = g.reindex(pd.date_range(g.index[0], g.index[-1], freq='h')).interpolate(limit=3).dropna()
        ff = f.reindex(reg.index).interpolate()
        if len(reg) < 24 * 20 or ff.isna().any():
            continue
        lg = R.lag_min(reg.values, ff.values)
        r = np.corrcoef(reg.values, ff.values)[0, 1]
        spr = bool(sprung[str(m)].any()) if str(m) in sprung else False
        ok = abs(lg) <= 30 and r > 0.3 and not spr
        protokoll.append('   %s  %4d h  Versatz %+5.0f min  r %.2f %s' % (m, len(g), lg, r, '' if ok else ' <- raus'))
        if ok:
            gut.append(g)
    stufen, basis, vor = [], None, None
    for g in gut:
        m = g.median()
        if vor is not None and abs(m - vor) > 0.5:
            protokoll.append('   Pegelnull-Sprung %+.2f m ab %s' % (m - vor, g.index[0].date()))
            basis = None
        if basis is None:
            basis = m - (stufen[0][1] if stufen else m)
        stufen.append((g - basis, m - basis))
        vor = m
    if not stufen:
        protokoll.append('   keine gueltigen Monate')
        return None
    s = pd.concat([g for g, _ in stufen])
    t = s.index.tz_convert(None).to_pydatetime()
    with contextlib.redirect_stdout(io.StringIO()):
        co = utide.solve(t, s.values, lat=e['lat'], method='ols', conf_int='none', trend=False, nodal=True,
                         verbose=False)
        rec = utide.reconstruct(t, co, verbose=False)['h']
        tt = [dt.datetime(2007, 1, 1) + dt.timedelta(hours=h) for h in range(0, 19 * 8766, 1)]
        lat_min = float(utide.reconstruct(tt, co, verbose=False)['h'].min())
    res = s.values - rec
    r2 = 1 - np.sum(res ** 2) / np.sum((s.values - s.values.mean()) ** 2)
    rms = float(np.sqrt(np.mean(res ** 2)))
    k = {n.strip(): (float(a), float(g) % 360) for n, a, g in zip(co['name'], co['A'], co['g'])}
    eig = R.lag_min(rec[:24 * 30], s.values[:24 * 30])
    protokoll.append('   Fit: %d h %s..%s  R2 %.3f  RMS %.3f m  Eigenversatz %+.0f min' % (
        len(s), s.index[0].date(), s.index[-1].date(), r2, rms, eig))
    protokoll.append('   ' + '  '.join('%s %.3f@%.0f' % (c, *k[c]) for c in ('M2', 'S2', 'K1', 'O1') if c in k))
    return dict(s=s, k=k, z0=float(co['mean']) - lat_min, r2=float(r2), rms=rms, eig=float(eig),
                pts=len(s), von=str(s.index[0].date()), bis=str(s.index[-1].date()))


def main(argv):
    import osm_land
    from timezonefinder import TimezoneFinder
    liste = json.load(open(argv[0]))
    if '--nur' in argv:
        nur = set(argv[argv.index('--nur') + 1].split(','))
        liste = [e for e in liste if e['code'] in nur]
    tf = TimezoneFinder()
    Lnd = osm_land.Land([(e['lat'], e['lon']) for e in liste])
    namen, speeds, arg, fak = X.kopf_lesen(ZIEL)
    L = open(ZIEL, encoding='iso-8859-1').read().rstrip('\n').split('\n')
    heute = dt.date.today().strftime('%Y%m%d')
    ergebnis = []
    for e in liste:
        prot = ['== %s [%s %s] Hub %.2f m' % (e['name'], e['q'], e['code'], e['hub'])]
        try:
            fit = fitten(e, namen, speeds, arg, fak, prot)
        except Exception as ex:                                     # einzelne kaputte Reihe nicht alles abbrechen
            prot.append('   FEHLER %s' % ex)
            fit = None
        grenze = 0.85 if e['hub'] >= 0.6 else 0.5
        ok = bool(fit) and fit['pts'] >= 2000 and fit['r2'] >= grenze and abs(fit['eig']) <= 10
        if fit and not ok:
            prot.append('   verworfen (Grenze R2 %.2f, mind. 2000 h)' % grenze)
        print('\n'.join(prot), flush=True)
        r = dict(e, ok=ok)
        if fit:
            r.update({k: fit[k] for k in ('r2', 'rms', 'eig', 'pts', 'von', 'bis')})
            r['M2'] = fit['k'].get('M2')
        ergebnis.append(r)
        if not ok:
            continue
        nla, nlo, d = wasser(e['lat'], e['lon'], Lnd)
        tz = tf.timezone_at(lat=e['lat'], lng=e['lon']) or 'UTC'
        posnote = ('%s %.4f/%.4f' % (e['q'], e['lat'], e['lon'])
                   + ('' if d == 0 else (' an Land, %.0f m ins Wasser' % d if d > 0 else ' an Land, kein Wasser bis 1 km'))
                   + '; Name aus Katalog/OSM, bitte pruefen')
        if e['q'] == 'IOC':
            quelle = ['# source: IOC Sea Level Monitoring gauge measurements with UTide',
                      '# station_id_context: IOC-%s' % e['code'], '# ioc_code: %s' % e['code']]
        else:
            quelle = ['# source: Derived from UHSLC hourly data with UTide harmonic analysis',
                      '# station_id_context: UHSLC-%s' % e['code'], '# uhslc_id: %s' % e['code']]
        k = fit['k']
        blk = (['#', '# ' + e['name'], '# BEGIN HOT COMMENTS', '# country: ' + e['name'].split(',')[-1].strip()]
               + quelle +
               ['# date_imported: ' + heute, '# datum: Chart Datum (approx., CD~LAT from constituents)',
                '# confidence: 7',
                '# utide: pts=%d period=%s..%s r2=%.4f rms=%.4fm const=%d' % (
                    fit['pts'], fit['von'], fit['bis'], fit['r2'], fit['rms'], sum(1 for n in k if n in namen)),
                '# note: %s Lueckensuche IOC/UHSLC: Monate mit Versatz > 30 min oder Datumssprung verworfen; %s.' % (
                    heute, posnote),
                '# !units: meters', '# !longitude: %.4f' % nlo, '# !latitude: %.4f' % nla])
        if e.get('region'):
            blk.append('# region: ' + e['region'])
        blk += [e['name'], '+00:00 :' + tz, '%.4f meters' % fit['z0']]
        for c in namen:
            blk.append('%-15s %.4f  %.2f' % (c, *k[c]) if c in k and k[c][0] >= 0.00005 else 'x 0 0')
        if e['name'] in L:
            print('   Name existiert schon -- nicht geschrieben')
            r['ok'] = False
            continue
        L += blk
    json.dump(ergebnis, open(argv[0].replace('.json', '') + '.ergebnis.json', 'w'), ensure_ascii=False, indent=1,
              default=str)
    if '--schreiben' in argv:
        schreiben(ZIEL, '\n'.join(L) + '\n')
        print('->', os.path.relpath(ZIEL, ROOT))


if __name__ == '__main__':
    main(sys.argv[1:])
