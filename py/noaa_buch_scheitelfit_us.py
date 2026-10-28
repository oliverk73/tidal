#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""US-Table-2-Saetze (harmonics_noaa_amtt) per Scheitelfit an NOAAs eigene HW/NW-Vorhersage am selben Ort (28.10.2026).

Anlass: py/noaa_buch_coops_probe.py -- 170 Buchsaetze in Alaska/Kalifornien/Oregon/Washington haben eine CO-OPS-Station
bis 2 km. Zeiten meist 0-2 min, aber Gruppen um Unalaska (bis 84 min), Attu (64), Sand Point (33), Sweeper Cove (24),
dazu Hub oft 3-10 % zu gross (Uebertragung mit einem Hubfaktor; NOAA rechnet HW und NW getrennt).
Wie py/noaa_hwnw_scheitelfit.py (Pazifik 27.10.): HW/NW 2025+2026 (MLLW, GMT), Probe Fit 2025 gegen 2026, Endfit beide Jahre.
Geschrieben wird, wenn der Endfit die Scheitel deutlich besser trifft (mind. 1 cm und um ein Drittel, oder die Zeit um
mind. 5 min) und die Probe 2026 nicht schlechter ist als der alte Satz. Phasen werden in den Meridian des Satzes gerechnet.

Usage: venv/bin/python py/noaa_buch_scheitelfit_us.py [--schreiben] [name ...]
"""
import datetime as dt
import json
import os
import sys
import time
import urllib.request

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import health_check as H                                           # noqa: E402
import noaa_buch_coops_probe as P                                  # noqa: E402
import scheitelfit as SF                                           # noqa: E402
import xtide_modell as X                                           # noqa: E402

URL25 = P.URL.replace('20260101', '20250101').replace('20261231', '20251231')


def scheitel(sid):
    pfad = os.path.join(P.CACHE, '%s_2025.json' % sid)
    if not os.path.exists(pfad):
        for k in range(4):
            try:
                d = json.load(urllib.request.urlopen(URL25 % sid, timeout=180))
                json.dump(d.get('predictions', []), open(pfad, 'w'))
                break
            except Exception:                                          # noqa: BLE001 (504 der API)
                time.sleep(10 * (k + 1))
        time.sleep(0.5)
    t26, h26 = P.scheitel(sid)
    ev = set(zip(t26.tolist(), h26.tolist()))
    if os.path.exists(pfad):
        ev |= {(dt.datetime.strptime(x['t'], '%Y-%m-%d %H:%M').replace(tzinfo=dt.timezone.utc).timestamp(), float(x['v']))
               for x in json.load(open(pfad)) if x.get('v') not in (None, '')}
    ev = sorted(ev)
    return np.array([a for a, _ in ev]), np.array([b for _, b in ev])


def main(argv):
    nur = [a for a in argv if not a.startswith('--')]
    kopf = X.kopf_lesen(P.DATEI)
    namen, speeds, arg, fak = kopf
    nutz = SF.konstituenten(namen, SF.CONSTIT_67)
    S = [(s['id'], s['name'], s['lat'], s['lng']) for s in P.stationen()]
    buch = [r for r in H.load_records() if 'harmonics_noaa_amtt' in r['file'] and not r['current'] and r['name'].endswith(P.US)
            and (not nur or r['name'] in nur)]
    grenze = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc).timestamp()
    heute = dt.date.today().strftime('%Y%m%d')
    n_schreiben = 0
    for r in buch:
        km, sid, cname = min((H.km(r, dict(lat=la, lon=lo)), sid, n) for sid, n, la, lo in S)
        if km > 2:
            continue
        t, h = scheitel(sid)
        if len(t) < 600 or (t < grenze).sum() < 300:
            print('%-46s %s: nur %d Scheitel' % (r['name'][:46], sid, len(t)))
            continue
        z_alt, w_alt, _, mer = X.satz_lesen(P.DATEI, r['name'])
        wg_alt = {k: (a, X.greenwich(g, speeds[k], mer)) for k, (a, g) in w_alt.items() if k in speeds}
        r_alt, t_alt, _ = SF.guete(t, h, z_alt, wg_alt, kopf, versatz=False)
        lern, test = t < grenze, t >= grenze
        z1, w1 = SF.fit(t[lern], h[lern], nutz, speeds, arg, fak)
        r_pr, t_pr, _ = SF.guete(t[test], h[test], z1, w1, kopf, versatz=False)
        r_at, t_at, _ = SF.guete(t[test], h[test], z_alt, wg_alt, kopf, versatz=False)
        z0, w = SF.fit(t, h, nutz, speeds, arg, fak)
        r_neu, t_neu, _ = SF.guete(t, h, z0, w, kopf, versatz=False)
        lo, hi = SF.bandbreite(t, h, z0, w, kopf)
        besser = ((r_alt - r_neu >= 0.01 and r_neu <= 2 * r_alt / 3) or (t_alt - t_neu >= 5 and r_neu <= r_alt)) and r_pr <= r_at
        urteil = 'schreiben' if besser and lo >= h.min() - 0.15 and hi <= h.max() + 0.15 else 'bleibt'
        print('%-46s %-8s %4d Sch. alt %5.1f cm %3.0f min | Probe26 alt %5.1f neu %5.1f | Endfit %4.1f cm %2.0f min  %s' % (
            r['name'][:46], sid, len(t), r_alt * 100, t_alt, r_at * 100, r_pr * 100, r_neu * 100, t_neu, urteil), flush=True)
        if '--schreiben' in argv and urteil == 'schreiben':
            n_schreiben += 1
            wm = {k: (a, g + speeds[k] * mer) for k, (a, g) in w.items()}          # Greenwich -> Meridian des Satzes
            SF.satz_schreiben(P.DATEI, r['name'], z0, wm, namen, [
                '%s Scheitelfit an NOAA-HW/NW 2025-2026 der CO-OPS-Station %s (%s, %.1f km) statt Table-2-Uebertragung' % (heute, sid, cname[:30], km),
                '-- (py/noaa_buch_scheitelfit_us.py): %.1f cm / %.0f min (vorher %.1f cm / %.0f min), Probe 2026 %.1f cm.' % (
                    r_neu * 100, t_neu, r_alt * 100, t_alt, r_pr * 100)])
    print('%d geschrieben' % n_schreiben)


if __name__ == '__main__':
    main(sys.argv[1:])
