#!/usr/bin/env python3
"""
Qualitaetspruefung der aus SHELDA erzeugten israelischen Stationen.

Vier unabhaengige Tests, bevor das 15,8-GB-Archiv geloescht wird:

1. SHELDA-Residuum   SHELDA liefert neben dem Pegel seine EIGENE entgezeitete
                     Reihe mit.  Wenn mein utide-Fit den Tidenanteil genauso
                     gut trifft, muss mein Residuum dieselbe Streuung haben
                     wie ihres.  Das ist der schaerfste Test, weil er gegen
                     eine fremde, unabhaengige Analyse derselben Daten prueft.
2. Split-half        Erste gegen zweite Haelfte der Reihe getrennt gerechnet.
                     Grosse Abweichung = Reihe instabil (Pegelversatz, Drift).
3. Hadera-Paar       hade (2010-2018) und hade2 (2018-2020): andere Geraete,
                     andere Epoche, 2 km auseinander.  Muessen uebereinstimmen.
4. Raeumlich         M2-Phase muss entlang der Kueste monoton laufen, nicht
                     springen.
"""
import sys
sys.path.insert(0, '/home/oliver/weather/py')

from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import netCDF4
import utide

NC = Path("/home/oliver/weather/scratchpad/shelda/nc")
CONST = ['M2', 'S2', 'N2', 'K2', 'K1', 'O1', 'P1', 'Q1']
STATIONS = [('haif', 'Haifa', 32.822454), ('hade', 'Hadera', 32.470530),
            ('hade2', 'Hadera Port', 32.472330), ('ashd1', 'Ashdod Marina', 31.796269)]


def load(code):
    with netCDF4.Dataset(NC / f"{code}.nc") as ds:
        t = ds.variables['time']
        times = netCDF4.num2date(t[:], t.units, only_use_cftime_datetimes=False,
                                 only_use_python_datetimes=True)
        lev = np.ma.filled(ds.variables['sea_level_qc'][:].astype('f8'), np.nan)
        res = np.ma.filled(ds.variables['residual'][:].astype('f8'), np.nan)
        flg = np.ma.filled(ds.variables['qc_flags'][:], 2).astype('i2')
    ok = (flg == 1) & np.isfinite(lev)
    times = np.asarray([x.replace(tzinfo=timezone.utc) for x in times])
    return times[ok], lev[ok], res[ok]


def hourly(times, vals):
    ep = np.array([t.timestamp() for t in times])
    h = np.floor(ep / 3600.0).astype('int64')
    u, inv = np.unique(h, return_inverse=True)
    m = np.bincount(inv, weights=vals) / np.bincount(inv)
    return np.array([datetime.fromtimestamp(x * 3600, tz=timezone.utc) for x in u]), m


def solve(dts, lev, lat):
    return utide.solve(dts, lev, lat=lat, nodal=True, trend=False, method='ols',
                       conf_int='none', verbose=False, constit='auto')


def harm(coef):
    out = {}
    for i, n in enumerate(coef['name']):
        n = n.strip()
        if n in CONST:
            out[n] = (coef['A'][i], coef['g'][i] % 360)
    return out


def main():
    res_all = {}
    print("=" * 78)
    print("TEST 1 + 2  --  Fit gegen SHELDAs eigenes Residuum, und Split-half")
    print("=" * 78)
    for code, name, lat in STATIONS:
        times, lev, shelda_res = load(code)
        dts, h = hourly(times, lev)
        _, hres = hourly(times, shelda_res)

        coef = solve(dts, h, lat)
        rec = utide.reconstruct(dts, coef, verbose=False)
        my_res = h - rec['h']

        # SHELDAs Residuum enthaelt noch das Mittel; fuer den Vergleich der
        # Streuung ist nur die Standardabweichung relevant.
        print(f"\n{name} ({code})  {len(dts)} Stundenwerte")
        print(f"  Streuung meines Residuums : {np.std(my_res):.4f} m")
        print(f"  Streuung SHELDA-Residuum  : {np.nanstd(hres):.4f} m")
        d = (np.std(my_res) - np.nanstd(hres)) / np.nanstd(hres) * 100
        print(f"  Abweichung                : {d:+.1f} %"
              f"   {'OK' if abs(d) < 10 else 'PRUEFEN'}")

        half = len(dts) // 2
        try:
            a, b = harm(solve(dts[:half], h[:half], lat)), harm(solve(dts[half:], h[half:], lat))
            print(f"  Split-half ({dts[0]:%Y-%m} | {dts[half]:%Y-%m} | {dts[-1]:%Y-%m}):")
            for c in ('M2', 'S2', 'K1', 'O1'):
                if c in a and c in b:
                    da = (b[c][0] - a[c][0]) * 1000
                    dg = (b[c][1] - a[c][1] + 180) % 360 - 180
                    print(f"    {c:3s} dAmp {da:+6.1f} mm   dPhase {dg:+6.2f}°")
        except Exception as e:
            print(f"  Split-half fehlgeschlagen: {e}")

        res_all[code] = harm(coef)

    print("\n" + "=" * 78)
    print("TEST 3 + 4  --  Stationsvergleich (Greenwich-Phasen)")
    print("=" * 78)
    print(f"\n{'':14s} " + "  ".join(f"{c:>14s}" for c in ('M2', 'S2', 'K1', 'O1')))
    for code, name, _ in STATIONS:
        r = res_all[code]
        cells = []
        for c in ('M2', 'S2', 'K1', 'O1'):
            cells.append(f"{r[c][0]:.4f}/{r[c][1]:6.2f}" if c in r else " " * 14)
        print(f"{name:14s} " + "  ".join(cells))

    a, b = res_all['hade'], res_all['hade2']
    print("\nHadera vs Hadera Port (verschiedene Geraete, verschiedene Epochen):")
    for c in ('M2', 'S2', 'N2', 'K1', 'O1'):
        if c in a and c in b:
            da = (b[c][0] - a[c][0]) / a[c][0] * 100
            dg = (b[c][1] - a[c][1] + 180) % 360 - 180
            print(f"  {c:3s}  Amp {a[c][0]:.4f} vs {b[c][0]:.4f} ({da:+.1f}%)   "
                  f"Phase {a[c][1]:6.2f} vs {b[c][1]:6.2f} ({dg:+.2f}°)")


if __name__ == '__main__':
    main()
