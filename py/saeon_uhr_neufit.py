#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SAEON-ADCP-Stromsaetze mit der am Drucksensor gemessenen Geraeteuhr neu fitten (16.11.2026).

Anlass: Zeitprobe der Stromsaetze gegen FES2014/TPXO10 (Walters Shoal +33/+45 min, Kenton-on-Sea -106/-112 min).
Beweis ueber die RDI-Rohdateien (quellen/tidal_streams/South_Africa_SAEON/raw/*.zip, *.000): der Drucksensor misst die
Wasserstands-Tide, FES2022 trifft sie an der Kueste auf wenige Minuten. Kreuzkorrelation Druck gegen FES-Vorhersage
(r = 0,97-0,998, Hub x1,00) ergibt je Auslegung einen festen Versatz ohne Drift:
  UTC-Uhr + Mittel am Intervallanfang gestempelt: Cape Recife +32/+34, Walters Shoal +24/+32 (Druck dort durch
  Verankerungsauslenkung gestoert, r 0,55, gleiche Richtung)
  Suedafrikanische Zeit (UTC+2) + Mittelstempel: Algoa Bay -86..-88, Port St. Johns -88, Kenton PA02 -88/-90,
  Kenton PA01 (Halbstundenmittel) -102; PA02 springt am 18.06.2005 05:00 um 1 h 04,5 min vor -> -150/-148.
Versatz = Minuten, um die die Stempel zu verschieben sind (wahre UTC-Zeit = Stempel + Versatz).
Zeitraeume ohne Druckbeleg (PA01 Auslegung 1/2, Port St. Johns Auslegung 1) fallen weg.

Usage: venv/bin/python py/saeon_uhr_neufit.py [--schreiben]
"""
import datetime as dt
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cmems_stroemung_nachholen as C                              # noqa: E402
import health_check as H                                           # noqa: E402
import strom_ellipsen_eigen as E                                   # noqa: E402
import xtide_modell as X                                           # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P = os.path.join(ROOT, 'harmonics/utide/harmonics_utide_current_observations.txt')

# saeon_id: [(von, bis (einschliesslich), Versatz min)], Stempel der verarbeiteten CSV (quellen/tidal_streams/South_Africa_SAEON)
UHR = {
    'ABay01': [('2013-12-06', '2014-12-08', -88)],
    'ABay02': [('2013-12-06', '2014-12-08', -86)],
    'ABay03': [('2013-12-06', '2014-12-08', -88)],
    'ABay04': [('2013-12-06', '2014-07-03', -88)],     # Druck gestoert (r 0,70), Versatz wie ABay01-03 derselben Auslegung
    'CR01':   [('2013-06-25', '2013-12-01 07:00', 32), ('2013-12-01 08:00', '2015-12-20', 34)],
    'PJ':     [('2013-12-03 08:00', '2014-09-27', -88)],
    'PA02':   [('2005-05-06', '2005-06-18 05:00', -88), ('2005-06-18 07:00', '2005-09-06', -150),
               ('2005-09-09 15:00', '2005-12-11', -148), ('2005-12-14', '2006-04-07', -90)],
    'PA01':   [('2005-12-14', '2006-04-07', -102)],
    'WSN01':  [('2014-05-25', '2015-08-03', 32)],
    'WSS01':  [('2014-05-29', '2015-08-03', 24)],
}


def main(argv):
    E.KOPF = X.kopf_lesen(P)
    kopf_namen, speeds = E.KOPF[0], E.KOPF[1]
    R = {r['name']: r for r in H.load_records()}
    txt = {n: t for n, t in E.saetze(P)}
    L = open(P, encoding='iso-8859-1').read().split('\n')
    heute = dt.date.today().strftime('%Y%m%d')
    for name, t in txt.items():
        if 'SAEON' not in t:
            continue
        sid = next((z.split(': ')[1].strip() for z in t.split('\n') if z.startswith('# saeon_id: ')), None)
        if sid not in UHR:
            continue
        r = R[name]
        roh = E.rohreihe(t, name, r['lat'], r['lon'])          # gleiche Aufbereitung wie beim ersten Fit (u/v aus speed/direction)
        neu = []
        for (von, bis, vs) in UHR[sid]:
            s = roh.loc[von:bis].copy()
            s.index = s.index + pd.Timedelta(minutes=vs)
            neu.append(s)
        roh = pd.concat(neu).sort_index()
        _z0, alt, _e, mer = X.satz_lesen(P, name)
        res = C.analyse(roh, r['lat'], C.KONST)
        k = res['konst']
        g_alt = X.greenwich(alt['M2'][1], speeds['M2'], mer)
        d0 = abs((k['M2'][1] - g_alt + 180) % 360 - 180)
        d1 = abs((k['M2'][1] + 180 - g_alt + 180) % 360 - 180)
        vz = 1 if d0 <= d1 else -1
        if vz < 0:
            k = {c: (a, (g + 180) % 360) for c, (a, g) in k.items()}
        dm = ((k['M2'][1] - g_alt + 180) % 360 - 180) / speeds['M2'] * 60
        mean = res['mean'] * vz
        zr = '%s..%s' % (roh.index[0].strftime('%Y-%m-%d'), roh.index[-1].strftime('%Y-%m-%d'))
        vs_txt = '/'.join('%+d' % v for _a, _b, v in UHR[sid])
        print('%-44s %-6s n=%5d  M2 %.3f -> %.3f kn  Phase %+5.0f min  Uhr %s  %s' % (
            name[:44], sid, len(roh), alt['M2'][0], k['M2'][0], dm, vs_txt, zr))
        if '--schreiben' not in argv:
            continue
        i = L.index(name)
        assert L[i + 1].split()[0] == '+00:00'
        L[i + 2] = '%.4f knots' % mean
        j = i + 3
        for c in kopf_namen:
            a = k.get(c)
            L[j] = '%-15s %.4f  %.2f' % (c, a[0], a[1]) if a and a[0] >= 0.00005 else 'x 0 0'
            j += 1
        a = i
        while L[a - 1].startswith('#'):
            a -= 1
        for q in range(a, i):
            if L[q].startswith('# utide: period='):
                L[q] = '# utide: period=%s const=%d' % (zr, len(k))
        L.insert(i, '# note: %s Geraeteuhr per Drucksensor gegen FES2022 bestimmt (Rohdatei RDI), Stempel %s min verschoben, '
                    'neu gefittet (Phasen %+.0f min; py/saeon_uhr_neufit.py)' % (heute, vs_txt, dm))
    if '--schreiben' in argv:
        from sicher_schreiben import schreiben
        schreiben(P, '\n'.join(L))
        print('->', os.path.relpath(P, ROOT))


if __name__ == '__main__':
    main(sys.argv[1:])
