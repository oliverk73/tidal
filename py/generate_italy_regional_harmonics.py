#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Regionale italienische Pegel (water_levels/Italy) -> UTide-Harmonische -> XTide.

STATUS 2026-07-23: Die zwei Records (Cetraro, Pozzallo) wurden in
harmonics/utide/harmonics_utide_observations.txt EINGEMERGT (Oliver-Entscheid).
Dieser Generator dient nur noch der Reproduktion/Inspektion und schreibt in
harmonics/help/ (KEINE deploybare Band-Datei mehr). Bei Bedarf neu ableiten und
die zwei Bloecke manuell in die Observations-Datei uebernehmen.

Rohdaten: 10-min-Pegelzeitreihen (ISPRA/regional). Zeitstempel sind UTC
(empirisch verifiziert: Cetraro-HW deckt sich auf 8 min mit Nachbar Palinuro/ticon4,
78 km; die 'lokale Zeit'-Annahme laege ~1,5 h daneben).

Nur Stationen mit ausreichender Laenge UND plausibler Phase gegen Nachbarn werden
geschrieben:
  Cetraro   358 d, R2~0.75  -> conf 6 (gut)
  Pozzallo  121 d, R2~0.18  -> conf 5 (grenzwertig, seiche-dominiert, Phase ~30-55min
                                       Streuung gg. Catania; als 'usable-with-caveat')
Verworfen:
  Marettimo  R2~0.03 (lueckenhafte Event-Stichprobe, 5060 Pkt/4.7 J)
  Marzamemi  nur 16 d -> Konstituenten nicht aufloesbar, verzerrte Overtones

MSL-Datum: 30-Tage-Rolling-Median-Detrend entfernt Sturmflut-/Meteo-Drift; die
Harmonische beschreiben die astronomische Tide um MSL.
"""
import sys, math
from pathlib import Path
from datetime import datetime
import numpy as np
import pandas as pd
import utide

sys.path.insert(0, str(Path(__file__).parent))
from generate_south_africa_harmonics import (
    harmonic_analysis_utide, read_header_from_template
)

DATA = Path('/home/oliver/weather/water_levels/Italy')
OUT  = Path('/home/oliver/weather/harmonics/help/italy_regional_derived.txt')  # nur Inspektion; Records leben in harmonics_utide_observations.txt
TEMPLATE = Path('/home/oliver/weather/harmonics/utide/harmonics_utide_observations.txt')

STATIONS = [
    dict(name='Cetraro',  file='CETRARO.csv',  lat=39.527645, lon=15.916924, conf=6,
         caveat=''),
    dict(name='Pozzallo', file='POZZALLO.csv', lat=36.720245, lon=14.827313, conf=5,
         caveat=' seiche-dominiert; Phase grob (~30-55min gg. Catania)'),
]

def load_it_utc(path, detrend_days=30):
    df = pd.read_csv(path, sep=';', dtype=str)
    lvlcol = [c for c in df.columns if 'LIVELLO' in c][0]
    dt = pd.to_datetime(df['DATA'] + ' ' + df['ORA'], format='%Y-%m-%d %H:%M', errors='coerce')
    lvl = pd.to_numeric(df[lvlcol].str.replace(',', '.', regex=False), errors='coerce')
    ok = dt.notna() & lvl.notna()
    dt, lvl = dt[ok].reset_index(drop=True), lvl[ok].to_numpy()
    med = np.median(lvl); keep = np.abs(lvl - med) < 3.0
    dt, lvl = dt[keep].reset_index(drop=True), lvl[keep]
    if detrend_days > 0:
        s = pd.Series(lvl, index=pd.DatetimeIndex(dt))
        roll = s.rolling(f'{detrend_days}D', center=True, min_periods=24).median()
        lvl = (s - roll).to_numpy()
        keep2 = ~np.isnan(lvl)
        dt, lvl = dt[keep2].reset_index(drop=True), lvl[keep2]
    dts = np.array([pd.Timestamp(t).to_pydatetime() for t in dt])
    return dts, lvl

def format_block(st, res, npts, start, end):
    full = f"{st['name']}, Italy"
    L = []
    L.append('# BEGIN HOT COMMENTS')
    L.append('# country: Italy')
    L.append('# source: Regionaler Pegel (water_levels/Italy, 10-min, UTC); UTide-Harmonische Analyse')
    L.append(f'# date_imported: {datetime.now().strftime("%Y%m%d")}')
    L.append('# datum: MSL (30d-rolling-median detrended)')
    L.append(f'# confidence: {st["conf"]}')
    L.append(f'# utide: pts={npts} period={start:%Y-%m-%d}..{end:%Y-%m-%d} '
             f'r2={res["r_squared"]:.4f} rms={res["rms_error"]:.4f}m const={res["n_analyzed"]}{st["caveat"]}')
    L.append('# !units: meters')
    L.append(f'# !longitude: {st["lon"]:.6f}')
    L.append(f'# !latitude: {st["lat"]:.6f}')
    L.append(full)
    L.append('+00:00 :Europe/Rome')
    L.append(f'{res["mean"]:.4f} meters')
    for c in res['constituents']:
        if c.get('not_analyzed') or c['amplitude'] < 0.00005:
            L.append('x 0 0')
        else:
            L.append(f'{c["name"]:15s} {c["amplitude"]:.4f}  {c["phase"]:.2f}')
    return '\n'.join(L)

def main():
    header = read_header_from_template(TEMPLATE)
    blocks = []
    for st in STATIONS:
        dts, lvl = load_it_utc(DATA / st['file'])
        res = harmonic_analysis_utide(dts, lvl, st['lat'])
        if res is None:
            print(f"-- {st['name']}: Fit fehlgeschlagen"); continue
        m2 = next((c for c in res['constituents'] if c['name'] == 'M2'), None)
        print(f"{st['name']:10s} n={len(dts):6d} R2={res['r_squared']:.3f} "
              f"RMS={res['rms_error']:.3f}m M2={m2['amplitude']*100:.1f}cm conf={st['conf']}")
        blocks.append(format_block(st, res, len(dts), dts[0], dts[-1]))
    with open(OUT, 'w', encoding='iso-8859-1') as f:
        f.write(header)
        for b in blocks:
            f.write('\n' + b + '\n')
    # Encoding-Kontrolle
    raw = open(OUT, 'rb').read()
    assert b'\xc3' not in raw and b'\x00' not in raw
    raw.decode('iso-8859-1')
    print(f"Wrote {len(blocks)} Stationen -> {OUT}")

if __name__ == '__main__':
    main()
