#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Nebenachsen fuer die eigenen Stromfits (Stufe 3 der eigenen Tidenrechnung, Oliver 4.11.2026).

Die Saetze in harmonics_utide_current_observations.txt fuehren nur die Hauptachse. Hier wird die
Rohreihe (u, v) noch einmal geholt und
  1. entlang der Hauptachse mit denselben Tiden gefittet -- das muss den Satz wiedergeben
     (M2 innerhalb 15 % und 15 Grad, sonst wird der Satz nur gemeldet). Dabei faellt auch die
     Flutrichtung heraus (die Achse oder die Achse + 180 Grad, je nachdem, welche zur M2-Phase passt).
  2. quer dazu (Flutrichtung + 90 Grad, im Uhrzeigersinn, wie bei NOAA) mit denselben Tiden gefittet.
     Kurze Reihen: K2/P1 (unter 182,6 Tagen) und N2 (unter 27,6 Tagen) quer weggelassen.
Ergebnis: harmonics/ellipsen/eigen.json {datei: {satzname: {azi, neben: {konst: [A, g_GMT]}, ...}}}.
Die Hauptachse liest py/strom_ellipsen.py weiter aus dem Satz selbst.

Rohreihen: BODC (QXF), Rijkswaterstaat (CSV), Marine Data Exchange (Pickles), CMEMS (NetCDF),
CSV time,speed,direction unter currents/ (IMOS, SAEON, MVB, CHS ...), KHOA-Zips.

Usage: venv/bin/python py/strom_ellipsen_eigen.py [--schreiben] [Namensteil ...]
"""
from __future__ import annotations

import glob
import json
import os
import re
import sys
import zipfile

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'rws_currents'))
import health_check as hc                                           # noqa: E402
import stroemung_kopplung_lauf as KL                                # noqa: E402
import xtide_modell as X                                            # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATEIEN = [os.path.join(ROOT, 'harmonics/utide/harmonics_utide_current_observations.txt')]
ZIEL = os.path.join(ROOT, 'harmonics/ellipsen/eigen.json')
MS_KN = 1.94384449
KOPF = X.kopf_lesen(DATEIEN[0])


# ---- Rohreihen ------------------------------------------------------------
def _csv_uv(pfad):
    df = pd.read_csv(pfad, parse_dates=['time'], index_col='time')
    if 'u' in df and 'v' in df:
        return df[['u', 'v']].dropna()
    s, d = df['speed'].values, df['direction'].values
    return pd.DataFrame({'u': s * np.sin(np.radians(d)), 'v': s * np.cos(np.radians(d))}, index=df.index).dropna()


def _cmems(code):
    import cmems_stroemung_nachholen as C
    for d in ('currents/cmems_raw', 'water_levels/CMEMS_currents_neu', 'water_levels/CMEMS_currents_BR'):
        for p in glob.glob(os.path.join(ROOT, d, f'*_MO_{code}.nc')):
            r = C.reihe(p)
            if r:
                return r[0]
    return None


def _code_csv(code):
    hits = [p for p in glob.glob(os.path.join(ROOT, 'currents', '**', f'{code}.csv'), recursive=True)]
    return _csv_uv(hits[0]) if hits else None


def _khoa(kid):
    for z in glob.glob(os.path.join(ROOT, 'currents/korea', f'*_KHOA-{kid}_*.zip')):
        with zipfile.ZipFile(z) as f:
            teile = []
            for n in f.namelist():
                if n.lower().endswith('.csv'):
                    teile.append(n)
            return None if not teile else ('zip', z, teile)
    return None


_BODC = None


def rohreihe(text, name, la, lo):
    global _BODC
    if 'BODC current meter' in text:
        if _BODC is None:
            _BODC = KL.B.metadaten()
        return KL.bodc_reihe(_BODC, text, la, lo)
    if 'Rijkswaterstaat' in text:
        return KL.rws_reihe(text)
    if '# mde_id:' in text:
        return KL.mde_reihe(name)
    m = re.search(r'# cmems_code: (\S+)', text)
    if m:
        return _cmems(m.group(1))
    for feld in ('imos_code', 'saeon_id', 'mvb_id', 'chs_id', 'station_code'):
        m = re.search(rf'# {feld}: (\S+)', text)
        if m:
            df = _code_csv(m.group(1))
            if df is not None:
                return df
    return None


# ---- Fit -----------------------------------------------------------------
def fit_achse(df, achse, tiden):
    """Komponente entlang `achse` (Grad, Richtung 'nach') in Knoten -> {konst: (A, g_GMT)}, Mittel, r2."""
    namen, sp, arg, fak = KOPF
    s = (df['u'].values * np.sin(np.radians(achse)) + df['v'].values * np.cos(np.radians(achse))) * MS_KN
    t = df.index.values.astype('datetime64[s]').astype(np.int64).astype(float)
    tiden = [k for k in tiden if k in sp]
    Cm, Sm, _ = X.matrix(t, tiden, sp, arg, fak)
    M = np.hstack([np.ones((len(t), 1)), Cm, Sm])
    x, *_ = np.linalg.lstsq(M, s, rcond=None)
    n = len(tiden)
    res = s - M @ x
    k = {c: (float(np.hypot(x[1 + j], x[1 + n + j])), float(np.degrees(np.arctan2(x[1 + n + j], x[1 + j])) % 360))
         for j, c in enumerate(tiden)}
    return k, float(x[0]), float(1 - np.var(res) / np.var(s))


def auswerten(text, name, werte, la, lo):
    """-> (Ergebnis-dict, None) oder (None, Grund)."""
    df = rohreihe(text, name, la, lo)
    if df is None or len(df) < 300:
        return None, 'keine Rohreihe'
    p = re.search(r'period=(\d{4}-\d\d-\d\d)\.\.(\d{4}-\d\d-\d\d)', text)
    if p:
        df = df.loc[p.group(1):p.group(2) + ' 23:59']
    if len(df) < 300:
        return None, 'Rohreihe ausserhalb des Satzzeitraums'
    tage = (df.index[-1] - df.index[0]).total_seconds() / 86400
    tiden = [k for k in werte if werte[k][0] > 0]
    if tage < 182.6:
        tiden = [k for k in tiden if k not in ('K2', 'P1')]
    if tage < 27.6:
        tiden = [k for k in tiden if k != 'N2']
    w_, V = np.linalg.eigh(np.cov(np.vstack([df['u'].values, df['v'].values])))
    a = V[:, np.argmax(w_)]
    achse0 = float(np.degrees(np.arctan2(a[0], a[1])) % 180)
    m2 = werte.get('M2')
    if not m2:
        return None, 'kein M2 im Satz'
    best = None
    for achse in (achse0, achse0 + 180):
        k, _mw, r2 = fit_achse(df, achse, tiden)
        d = abs((k['M2'][1] - m2[1] + 180) % 360 - 180)
        if best is None or d < best[0]:
            best = (d, achse % 360, k, r2)
    d, achse, k, r2 = best
    skala = 1.0
    if abs(k['M2'][0] / m2[0] / MS_KN - 1) < 0.1:      # Rohreihe schon in Knoten (CHS IWLS, vgl. CHS-Einheitenfehler 16.10.)
        skala = 1 / MS_KN
        k = {c: (a_ * skala, g) for c, (a_, g) in k.items()}
    amp = abs(k['M2'][0] / m2[0] - 1)
    if amp > 0.15 or d > 15:
        return None, f'Hauptachse passt nicht (M2 {100 * (k["M2"][0] / m2[0] - 1):+.0f} %, {d:.0f} Grad)'
    neben, _mw, r2n = fit_achse(df, achse + 90, tiden)
    neben = {c: (a_ * skala, g) for c, (a_, g) in neben.items()}
    return dict(azi=round(achse, 1), tage=round(tage, 1), m2_haupt=[round(x, 4) for x in k['M2']],
                neben={c: [round(a_, 4), round(g, 2)] for c, (a_, g) in neben.items() if a_ >= 0.0005},
                pruef=dict(m2_amp_prozent=round(100 * (k['M2'][0] / m2[0] - 1), 1), m2_grad=round(d, 1))), None


def saetze(pfad):
    L = open(pfad, encoding='iso-8859-1').read().split('\n')
    st = [k for k in range(len(L) - 1) if L[k] and not L[k].startswith('#') and hc.MERIDIAN.match(L[k + 1])]
    vorher = 0
    for k in st:
        text = '\n'.join(L[vorher:k])
        vorher = k
        yield L[k], text


def main(argv):
    schreiben = '--schreiben' in argv
    filter_ = [a for a in argv if not a.startswith('--')]
    alt = json.load(open(ZIEL)) if os.path.exists(ZIEL) else {}
    zahl, gruende = {'ok': 0}, {}
    for pfad in DATEIEN:
        datei = os.path.basename(pfad)
        aus = alt.setdefault(datei, {})
        for name, text in saetze(pfad):
            if filter_ and not any(f in name for f in filter_):
                continue
            if not name.rstrip().endswith('Current'):
                continue
            la = float(re.search(r'# !latitude: (\S+)', text).group(1))
            lo = float(re.search(r'# !longitude: (\S+)', text).group(1))
            _z0, werte, _e, m = X.satz_lesen(pfad, name)
            werte = {c: (a, X.greenwich(g, KOPF[1][c], m)) for c, (a, g) in werte.items() if c in KOPF[1]}
            try:
                r, grund = auswerten(text, name, werte, la, lo)
            except Exception as e:  # noqa: BLE001
                r, grund = None, f'Fehler {type(e).__name__}: {e}'[:80]
            if r:
                aus[name] = r
                zahl['ok'] += 1
                print(f'ok   {name[:60]:60} azi {r["azi"]:5.1f}  M2 neben {r["neben"].get("M2", [0])[0]:.2f} '
                      f'/ haupt {werte["M2"][0]:.2f} kn  ({r["pruef"]["m2_amp_prozent"]:+.0f} %, {r["pruef"]["m2_grad"]:.0f} Grad)',
                      flush=True)
            else:
                g = grund.split(' (')[0]
                gruende[g] = gruende.get(g, 0) + 1
                print(f'--   {name[:60]:60} {grund}', flush=True)
    print(zahl, gruende)
    if schreiben:
        os.makedirs(os.path.dirname(ZIEL), exist_ok=True)
        json.dump(alt, open(ZIEL, 'w'), ensure_ascii=False, indent=1, sort_keys=True)
        print('geschrieben', ZIEL)


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
