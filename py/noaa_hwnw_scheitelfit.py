#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""NOAA-Saetze aus HW/NW-Vorhersagen: Scheitelfit statt UTide auf die Scheitelwerte (27.10.2026).

116 Saetze in harmonics_noaa_{pacif,carib,censam}.txt tragen die Notiz "UTide-Fit auf NOAA-HW/NW-Vorhersagen":
UTide wurde direkt auf die Scheitelhoehen gesetzt, ohne Bedingung, dass die Kurve dort waagerecht ist. Fanning
Island (TPT2743): 4.2 cm RMS an den eigenen Scheiteln, Scheitelfit (py/scheitelfit.py) 0.6 cm bei gleichem K1.
Hier: NOAA-hilo 2025+2026 neu laden (CO-OPS datagetter, MLLW, GMT), Probe Fit 2025 gegen 2026, Endfit beide Jahre.
Geschrieben wird nur, wenn der Endfit die Scheitel deutlich besser trifft (mindestens 1 cm und um ein Drittel, oder
die Scheitelzeit um mindestens 5 min) und die Probe 2026 nicht schlechter ist als der alte Satz.
Erster Lauf 27.10.: 114 von 116 besser, Median 4.2 cm / 12 min -> 0.1 cm / 1 min, Probe 2026 Median 0.2 cm.
Bleiben: Howland (Probe schlechter, auch der Endfit nur 5.7 cm / 22 min: NOAAs Scheitel folgen keiner harmonischen Kurve).
28.10.: Arno Atoll (NOAA liefert fuer 2026 keine Vorhersage) mit Probe zweite Haelfte 2025 gegen Fit der ersten.

Usage: venv/bin/python py/noaa_hwnw_scheitelfit.py [--laden] [--schreiben] [noaa_id ...]
"""
import datetime as dt
import json
import os
import re
import sys
import time
import urllib.request

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import health_check as H                                           # noqa: E402
import scheitelfit as SF                                           # noqa: E402
import xtide_modell as X                                           # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATEIEN = ['harmonics/noaa/harmonics_noaa_%s.txt' % t for t in ('pacif', 'carib', 'censam')]
CACHE = os.path.join(ROOT, 'water_levels/NOAA_hilo')
URL = ('https://api.tidesandcurrents.noaa.gov/api/prod/datagetter?product=predictions&station=%s&begin_date=%d0101'
       '&end_date=%d1231&datum=MLLW&time_zone=gmt&units=metric&interval=hilo&format=json')
JAHRE = (2025, 2026)


def saetze():
    """-> [(datei, name, noaa_id)] aller Saetze mit HW/NW-UTide-Notiz."""
    out = []
    for d in DATEIEN:
        kopf = []
        for z in open(os.path.join(ROOT, d), encoding='iso-8859-1').read().split('\n'):
            if z.startswith('#'):
                kopf.append(z)
                continue
            if kopf and z and not re.match(r'^[+-]?\d', z):
                k = '\n'.join(kopf)
                m = re.search(r'# noaa_id:\s*(\S+)', k)
                if m and 'UTide-Fit auf NOAA-HW/NW' in k:
                    out.append((d, z, m.group(1)))
            kopf = []
    return out


def laden(sid):
    os.makedirs(CACHE, exist_ok=True)
    for j in JAHRE:
        pfad = os.path.join(CACHE, '%s_%d.json' % (sid, j))
        if os.path.exists(pfad):
            continue
        for k in range(4):
            try:
                d = json.load(urllib.request.urlopen(URL % (sid, j, j), timeout=180))
                if 'predictions' in d:
                    json.dump(d['predictions'], open(pfad, 'w'))
                else:
                    print('%s %d: %s' % (sid, j, str(d)[:100]))
                break
            except Exception:                                          # noqa: BLE001 (504 der API)
                time.sleep(10 * (k + 1))
        time.sleep(1)


def scheitel(sid):
    ev = []
    for j in JAHRE:
        pfad = os.path.join(CACHE, '%s_%d.json' % (sid, j))
        if os.path.exists(pfad):
            ev += [(dt.datetime.strptime(x['t'], '%Y-%m-%d %H:%M').replace(tzinfo=dt.timezone.utc).timestamp(), float(x['v']))
                   for x in json.load(open(pfad)) if x.get('v') not in (None, '')]
    ev = sorted(set(ev))
    return np.array([a for a, _ in ev]), np.array([b for _, b in ev])


def main(argv):
    nur = [a for a in argv if not a.startswith('--')]
    liste = [s for s in saetze() if not nur or s[2] in nur]
    print('%d Saetze' % len(liste))
    if '--laden' in argv:
        for _, _, sid in liste:
            laden(sid)
    heute = dt.date.today().strftime('%Y%m%d')
    grenze = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc).timestamp()
    zeilen = []
    for datei, name, sid in liste:
        pfad = os.path.join(ROOT, datei)
        kopf = X.kopf_lesen(pfad)
        namen, speeds, arg, fak = kopf
        nutz = SF.konstituenten(namen, SF.CONSTIT_67)
        t, h = scheitel(sid)
        if len(t) < 600:
            print('%-50s %s: nur %d Scheitel' % (name[:50], sid, len(t)))
            continue
        z_alt, w_alt, _, mer = X.satz_lesen(pfad, name)
        if mer:
            print('%-50s Meridian %+g, uebersprungen' % (name[:50], mer))
            continue
        r_alt, t_alt, _ = SF.guete(t, h, z_alt, w_alt, kopf, versatz=False)
        lern, test = t < grenze, t >= grenze
        if test.sum() < 100:                                       # kein 2026 (Arno): Probe an der zweiten Jahreshaelfte
            lern, test = t < np.median(t), t >= np.median(t)
        z1, w1 = SF.fit(t[lern], h[lern], nutz, speeds, arg, fak)
        r_pr, t_pr, _ = SF.guete(t[test], h[test], z1, w1, kopf, versatz=False)
        r_at, t_at, _ = SF.guete(t[test], h[test], z_alt, w_alt, kopf, versatz=False)
        z0, w = SF.fit(t, h, nutz, speeds, arg, fak)
        r_neu, t_neu, _ = SF.guete(t, h, z0, w, kopf, versatz=False)
        lo, hi = SF.bandbreite(t, h, z0, w, kopf)
        besser = ((r_alt - r_neu >= 0.01 and r_neu <= 2 * r_alt / 3) or (t_alt - t_neu >= 5 and r_neu <= r_alt)) and r_pr <= r_at
        urteil = 'schreiben' if besser and lo >= h.min() - 0.15 and hi <= h.max() + 0.15 else 'bleibt'
        print('%-50s %-8s %4d Sch.  alt %5.1f cm %3.0f min | Probe26 alt %5.1f neu %5.1f | Endfit %5.1f cm %3.0f min  K1 %.3f->%.3f  M2 %.3f->%.3f  %s' % (
            name[:50], sid, len(t), r_alt * 100, t_alt, r_at * 100, r_pr * 100, r_neu * 100, t_neu,
            w_alt.get('K1', (0, 0))[0], w['K1'][0], w_alt.get('M2', (0, 0))[0], w['M2'][0], urteil))
        zeilen.append((datei, name, urteil))
        if '--schreiben' in argv and urteil == 'schreiben':
            SF.satz_schreiben(pfad, name, z0, w, namen, [
                '%s Scheitelfit an NOAA-HW/NW %s (py/noaa_hwnw_scheitelfit.py) statt UTide auf die Scheitelwerte:' % (
                    heute, '2025-2026' if t.max() >= grenze else '2025'),
                'Scheiteltreue %.1f cm / %.0f min (vorher %.1f cm / %.0f min), Probe %s %.1f cm.' % (
                    r_neu * 100, t_neu, r_alt * 100, t_alt, '2026' if t.max() >= grenze else '2. Halbjahr', r_pr * 100)])
    print('\n%d schreiben, %d bleiben' % (sum(u == 'schreiben' for *_, u in zeilen), sum(u == 'bleibt' for *_, u in zeilen)))


if __name__ == '__main__':
    main(sys.argv[1:])
