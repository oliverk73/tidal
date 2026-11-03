#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sonnen- und Mondereignisse fuer die eigene Tidenrechnung (Ersatz fuer XTide, Stufe 2).

Rechnet mit Skyfield und der JPL-Ephemeride DE421 (tide_models/ephemeriden/de421.bsp,
gueltig 1900-2050). Versuch 3.11.2026 mit den Low-precision-Formeln (lpsun/lpmoon):
Sonne +-1 min, Mond in Reykjavik bis 8 min daneben -- XTide selbst liegt gegen DE421
bei +-1 min, also braucht es eine genaue Mondtheorie.

Ereignisse wie XTide: Sunrise, Sunset, Moonrise, Moonset, New Moon, First Quarter,
Full Moon, Last Quarter.

Usage: venv/bin/python py/astro.py --pruefen      (Gegenprobe gegen `tide -m p`)
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EPHEMERIDE = os.path.join(ROOT, 'tide_models/ephemeriden/de421.bsp')
PHASEN = ['New Moon', 'First Quarter', 'Full Moon', 'Last Quarter']

_sky = {}


def _laden():
    if not _sky:
        from skyfield.api import Loader
        lade = Loader(os.path.dirname(EPHEMERIDE), verbose=False)
        _sky['ts'] = lade.timescale(builtin=True)
        _sky['eph'] = lade(os.path.basename(EPHEMERIDE))
    return _sky['ts'], _sky['eph']


def ereignisse(lat, lon, t0, t1):
    """-> [(unix_t, art)] zwischen t0 und t1 (Unix-Sekunden), sortiert."""
    from skyfield import almanac
    from skyfield.api import wgs84
    ts, eph = _laden()
    a, b = ts.from_datetimes([__import__('datetime').datetime.fromtimestamp(x, __import__('datetime').timezone.utc)
                              for x in (t0, t1)])
    beob = eph['earth'] + wgs84.latlon(lat, lon)
    ev = []
    for koerper, auf, ab in ((eph['sun'], 'Sunrise', 'Sunset'), (eph['moon'], 'Moonrise', 'Moonset')):
        for f, art in ((almanac.find_risings, auf), (almanac.find_settings, ab)):
            tt, ok = f(beob, koerper, a, b)
            ev += [(x.utc_datetime().timestamp(), art) for x, o in zip(tt, ok) if o]
    tt, ph = almanac.find_discrete(a, b, almanac.moon_phases(eph))
    ev += [(x.utc_datetime().timestamp(), PHASEN[int(p)]) for x, p in zip(tt, ph)]
    return sorted(e for e in ev if t0 <= e[0] < t1)


def sonne_oben(lat, lon, t):
    """Sonne ueber -0,8333 Grad (XTide Skycal::sunIsUp)."""
    import datetime as dt
    from skyfield.api import wgs84
    ts, eph = _laden()
    z = ts.from_datetime(dt.datetime.fromtimestamp(t, dt.timezone.utc))
    alt = (eph['earth'] + wgs84.latlon(lat, lon)).at(z).observe(eph['sun']).apparent().altaz()[0].degrees
    return alt >= -0.8333


def pruefen():
    import datetime as dt
    import subprocess
    import numpy as np
    orte = [('harmonics_bsh_germany.tcd', 'Amrum Odde (Amrum), Germany'),
            ('harmonics_noaa_currents.tcd', 'Kanmon Kaikyo (Hayatomo Seto), Yamaguchi, Japan Current'),
            ('harmonics_ticon4_worldwide.tcd', 'Reykjavik, Iceland')]
    for tcd, name in orte + [tuple(x.split('|')) for x in sys.argv[2:]]:
        env = dict(os.environ, HFILE_PATH='/usr/share/xtide/' + tcd)
        a = subprocess.run(['tide', '-l', name, '-m', 'a'], env=env, capture_output=True, text=True).stdout
        f = [z for z in a.split('\n') if z.startswith('Coordinates')][0][14:].replace('°', '').replace(',', '').split()
        lat = float(f[0]) * (-1 if f[1] == 'S' else 1)
        lon = float(f[2]) * (-1 if f[3] == 'W' else 1)
        out = subprocess.run(['tide', '-l', name, '-b', '2026-11-01 00:00', '-e', '2027-03-01 00:00', '-f', 'c',
                              '-m', 'p', '-z', '-df', '%Y-%m-%d', '-tf', '%H:%M'], env=env,
                             capture_output=True, text=True).stdout
        xt = []
        for z in out.split('\n'):
            p = z.rsplit(',', 4)
            if len(p) == 5 and not p[3]:
                t = dt.datetime.strptime(p[1] + ' ' + p[2].replace(' UTC', ''), '%Y-%m-%d %H:%M')
                xt.append((t.replace(tzinfo=dt.timezone.utc).timestamp(), p[4]))
        t0 = dt.datetime(2026, 11, 1, tzinfo=dt.timezone.utc).timestamp()
        t1 = dt.datetime(2027, 3, 1, tzinfo=dt.timezone.utc).timestamp()
        mein = ereignisse(lat, lon, t0, t1)
        gl = sum(1 for t, a in xt if any(m[1] == a and m[0] // 60 * 60 == t for m in mein))
        d, fehl = {}, 0
        for t, art in xt:
            k = [m for m in mein if m[1] == art and abs(m[0] - t) < 3 * 3600]
            if not k:
                fehl += 1
                continue
            m = min(k, key=lambda m: abs(m[0] - t))
            d.setdefault(art, []).append(m[0] // 60 * 60 / 60 - t / 60)
        print(f'{name} ({lat:.2f}, {lon:.2f}): XTide {len(xt)}, eigen {len(mein)}, ohne Partner {fehl}, '
              f'minutengleich {gl}')
        for art, v in d.items():
            v = np.array(v)
            print(f'   {art:14s} n={len(v):3d}  |max| {abs(v).max():.0f} min, gleich {np.mean(v == 0) * 100:.0f} %')


if __name__ == '__main__':
    if '--pruefen' in sys.argv:
        pruefen()
    else:
        print(__doc__)
