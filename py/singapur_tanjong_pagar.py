#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tanjong Pagar (Singapur): TICON-Satz hat falsche Tagestiden -> Messfit aus UHSLC 699 (11.11.2026).

Anlass: Oliver legte die MSS-Monatsseiten 12/2025-12/2026 ab (tide_tables/singapore/*.html, HW/NW von der MPA,
SGT = UTC+8, 0,1 m). Scheitelfit daraus: M2 wie TICON, aber K1/O1/P1 11-13 Grad frueher (~45 min).
UHSLC-Stundenwerte 699 (1984-2023) bestaetigen die Tafel, auch fuer 1985 und 1988/89 -- also im TICON-Zeitraum
(1981-1990) -- der TICON-4-Satz ist falsch, nicht die Tide veraendert:
             K1          O1          P1
  Messung    0.31/351    0.30/306    0.096/343
  MSS-Tafel  0.29/351    0.29/306    0.087/342
  TICON      0.275/3     0.262/317   0.084/354

Ablauf: UTide (robust, auto) auf 2014-2021, Probe auf 2022-2023 (ungesehen) fuer neu, TICON und MSS-Scheitelfit;
geschrieben wird der Fit ueber 2014-2023. Der TICON-Satz wird vorher per py/saetze_loeschen.py archiviert.

Usage: venv/bin/python py/singapur_tanjong_pagar.py <h699.csv> [--schreiben]
       (h699.csv: https://uhslc.soest.hawaii.edu/data/csv/fast/hourly/h699.csv)
"""
import datetime as dt
import glob
import html
import os
import re
import sys
import warnings

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import health_check as H                                           # noqa: E402
import qld_msq_fit as Q                                            # noqa: E402
import scheitelfit as SF                                           # noqa: E402
import xtide_modell as X                                           # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ZIEL = os.path.join(ROOT, 'harmonics/utide/harmonics_utide_observations.txt')
NAME, LAT, LON = 'Tanjong Pagar, Singapore', 1.2615, 103.8521


def reihe(pfad):
    d = pd.read_csv(pfad, header=None, names=['year', 'month', 'day', 'h', 'v'])
    d = d[d.v > -30000]
    idx = pd.to_datetime(d[['year', 'month', 'day']]) + pd.to_timedelta(d.h, 'h')
    return pd.Series(d.v.values / 1000.0, index=idx.dt.tz_localize('UTC'))


def utide_fit(s):
    import utide
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        c = utide.solve(s.index.tz_convert(None).to_pydatetime(), s.values, lat=LAT, method='robust',
                        conf_int='none', trend=False, nodal=True, constit='auto', Rayleigh_min=0.95, verbose=False)
    # UTide-SA ist h - p' (Perihel) = XTide SA-IOS; Bestand macht es genauso (add_uhslc_harmonics.py). Unter
    # dem Namen SA waere die Phase 77 Grad falsch (11.11.2026 synthetisch geprueft).
    um = {'SA': 'SA-IOS', 'S1': 'S1-IOS'}
    return float(c['mean']), {um.get(str(n), str(n)): (float(a), float(g) % 360.0) for n, a, g in zip(c['name'], c['A'], c['g'])}


def mss_scheitel():
    ent = []
    for f in sorted(glob.glob(os.path.join(ROOT, 'tide_tables/singapore/20*.html'))):
        j, m = map(int, os.path.basename(f)[:7].split('-'))
        t = open(f, encoding='utf-8').read()
        t = re.sub(r'<script.*?</script>|<style.*?</style>', '', t, flags=re.S)
        t = re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', t)))
        t = t[t.index('Height H/L') + 10:t.index('The tidal information')]
        for b in re.split(r' (?=\d{1,2} \d{1,2}\.\d{2} am \d{1,2}\.\d{2} pm )', ' ' + t):
            if not b.strip():
                continue
            d = int(b.split()[0])
            for hh, mi, ap, h, _hl in re.findall(r'(\d{1,2})\.(\d{2}) (am|pm) (-?\d+\.\d) m ([HL])', b):
                zeit = dt.datetime(j, m, d, int(hh) % 12 + (12 if ap == 'pm' else 0), int(mi)) - dt.timedelta(hours=8)
                ent.append((zeit.replace(tzinfo=dt.timezone.utc).timestamp(), float(h)))
    ent.sort()
    return np.array([e[0] for e in ent]), np.array([e[1] for e in ent])


def rms(s, z0, w, kopf):
    t = np.array([i.timestamp() for i in s.index])
    d = s.values - SF.hoehe_und_ableitungen(t, z0, w, kopf)[0]
    return float(np.sqrt(np.mean((d - d.mean()) ** 2)))


def main(argv):
    kopf = X.kopf_lesen(ZIEL)
    namen, speeds, arg, fak = kopf
    s = reihe(argv[0])
    lern, probe = s['2014':'2021'], s['2022':'2023']
    z0, w = utide_fit(lern)
    w = {k: v for k, v in w.items() if k in speeds}
    alt = [r for r in H.load_records() if r['name'] == NAME and 'ticon' in r['file']]
    tz0, tw, _e, mer = X.satz_lesen(alt[0]['file'], NAME) if alt else (0, {}, 0, 0)
    tw = {k: (a, X.greenwich(g, speeds[k], mer)) for k, (a, g) in tw.items() if k in speeds}
    mt, mh = mss_scheitel()
    nutz = SF.konstituenten(namen, SF.CONSTIT_67)
    mz0, mw = SF.fit(mt, mh, nutz, speeds, arg, fak)
    print('Probe 2022-2023 (%d Stundenwerte), RMS nach Mittelabzug:' % len(probe))
    print('  neu (UTide 2014-2021) %.1f cm | TICON %.1f cm | MSS-Tafelfit %.1f cm' % (
        100 * rms(probe, z0, w, kopf), 100 * rms(probe, tz0, tw, kopf), 100 * rms(probe, mz0, mw, kopf)))
    z0, w = utide_fit(s['2014':'2023'])
    w = {k: v for k, v in w.items() if k in speeds}
    neu = Q.rec(w)
    print('  Fit 2014-2023: %d Tiden; gegen TICON %.1f %%, gegen MSS-Tafel %.1f %%' % (
        len(w), 100 * H.curve_diff(neu, alt[0])[1] if alt else 0, 100 * H.curve_diff(neu, Q.rec(mw))[1]))
    print('  ' + ', '.join('%s %.3f/%.0f' % (k, *w[k]) for k in ('M2', 'S2', 'N2', 'K2', 'K1', 'O1', 'P1') if k in w))
    if '--schreiben' not in argv:
        return
    assert not alt, 'TICON-Satz erst archivieren (py/saetze_loeschen.py)'
    from sicher_schreiben import schreiben
    heute = dt.date.today().strftime('%Y%m%d')
    x = s['2014':'2023']
    L = open(ZIEL, encoding='iso-8859-1').read().rstrip('\n').split('\n')    # frisch lesen, nur anhaengen
    assert NAME not in L
    L += ['#', '# ' + NAME, '# BEGIN HOT COMMENTS', '# country: Singapore', '# water_body: Singapore Strait',
          '# source: Derived from UHSLC hourly data (ID=699) with UTide harmonic analysis',
          '# station_id_context: UHSLC-699', '# date_imported: %s' % heute, '# datum: Chart Datum',
          '# note: Z0 = Mittel der MSS/MPA-Tafel 12/2025-12/2026 ueber Chart Datum (UHSLC-Null willkuerlich)', '# confidence: 7',
          '# uhslc_id: 699', '# ssc_id: SSC-tanjo', '# ioc_code: tanjo', '# gloss_id: 44',
          '# utide: pts=%d period=%s..%s const=%d' % (len(x), x.index[0].date(), x.index[-1].date(), len(w)),
          '# note: %s ersetzt TICON-4-Satz (K1/O1/P1 11-12 Grad spaet, Amplituden 10 %% klein); bestaetigt durch'
          ' MSS/MPA-Tafel 2026 und UHSLC 1985/1988 (py/singapur_tanjong_pagar.py)' % heute,
          '# !units: meters', '# !longitude: %.4f' % LON, '# !latitude: %.4f' % LAT, '# region: South West',
          NAME, '+00:00 :Asia/Singapore', '%.4f meters' % mz0]   # UHSLC-Null ist willkuerlich
    L += ['%-15s %.4f  %.2f' % (c, *w[c]) if c in w and w[c][0] >= 0.00005 else 'x 0 0' for c in namen]
    schreiben(ZIEL, '\n'.join(L) + '\n')
    print('->', os.path.relpath(ZIEL, ROOT))


if __name__ == '__main__':
    main(sys.argv[1:])
