#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""FES2022, TPXO10, TPXO9 und unser Satz direkt gegen Messreihen (Oliver 12.11.2026: Gegenprobe zum Konstantenvergleich).

py/tpxo_vergleich.py misst die Modelle an unseren Messfits. Hier dieselbe Frage an den Rohreihen: Zuordnung Satz <-> Reihe
aus py/messreihe_qualitaet.py (alle_anker), nur Ordner mit echten Messungen (keine JMA-/tidetimes-/LINZ-/DMI-Tafeln).
Je Reihe die letzten <= 2 Jahre, Werte zur vollen Stunde. Vorhersage mit allen Konstituenten des Modells ausser den
langperiodischen (SA, SSA, MF, MM, MSF ...); vom Rest (Messung - Vorhersage) wird der gleitende 30-Tage-Mittelwert
abgezogen (Jahresgang, Wetterlagen). Was bleibt: Tidenfehler + kurzfristiges Wetter (Sturm, Seiches).
  rms_*      RMS dieses Rests in cm
  tide_*     geschaetzter reiner Tidenfehler sqrt(rms_modell^2 - rms_satz^2): unser Satz ist an der Reihe gefittet und
             enthaelt fast nur noch Wetter -> der Ueberschuss des Modells ist Tide. (Satz = "eigen", kein Wettbewerber.)
  m2_jahr_*  Streuung von M2 bei Einzeljahr-Fits (Amplitude mm, Phase min): wie viel Wetter/Messfehler in Konstanten steckt.
Schreibt harmonics/help/modell_reihen_vergleich.csv.
Usage: venv/bin/python py/modell_reihen_vergleich.py [--max N] [--fes15]
--fes15: FES nur mit den 15 TPXO10-Konstituenten (trennt Modellguete von Konstituentenzahl).
"""
import cmath
import csv
import math
import os
import sys

import netCDF4 as nc
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fes_kuestentyp as F                                         # noqa: E402
import health_check as H                                           # noqa: E402
import messreihe_qualitaet as M                                    # noqa: E402
import qld_msq_fit as Q                                            # noqa: E402
import scheitelfit as SF                                           # noqa: E402
import seine_haropa_fit as S                                       # noqa: E402
import tpxo as T                                                   # noqa: E402
import xtide_modell as X                                           # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUS = os.path.join(ROOT, 'harmonics/help/modell_reihen_vergleich%s.csv' % ('_fes15' if '--fes15' in sys.argv else ''))
MESS = ('UHSLC', 'IOC', 'France_SHOM', 'Germany', 'Netherlands', 'Belgium', 'ea', 'UK', 'Ireland_MI', 'Denmark_DMI',
        'Australia_QLD', 'Australia_BOM', 'Canada_CHS_wlo', 'Sweden_SMHI', 'Portugal_CMEMS', 'Chile_IOC', 'Russia_IOC')
NICHT = ('UK_tidetimes', 'Denmark_DMI_vorhersage', 'JMA', 'LINZ', 'HydroPortail', 'RWS_platforms')
LANG = {'SA', 'SSA', 'MF', 'MM', 'MSF', 'MSM', 'MSQM', 'MTM', 'SA-IOS', 'MF-IOS', 'NODAL'}
FESNAME = {'LAMBDA2': 'LDA2'}
PRO_ORDNER = 8


def fes_voll(recs, namen):
    """Alle FES-Konstituenten an der Zelle aus fes_dazu (r['ij'])."""
    for f in sorted(os.listdir(F.FES)):
        if not f.endswith('_fes2022.nc') or f.startswith('mask'):
            continue
        k = f.split('_')[0].upper()
        k = FESNAME.get(k, k)
        if k not in namen or k in LANG:
            continue
        d = nc.Dataset(os.path.join(F.FES, f))
        am, ph = d['amplitude'], d['phase']
        for r in recs:
            i, j = r['ij']
            a = float(am[i, j])
            if np.isfinite(a):
                r.setdefault('fesw', {})[k] = (a / 100.0, float(ph[i, j]) % 360)
        d.close()


def satz_w(r, speeds):
    """Satzkonstanten -> Greenwich-Phasen, Meter (wie health_check.load_records)."""
    mer = None
    L = open(os.path.join(ROOT, r['file']), encoding='iso-8859-1').read().split('\n')
    mer = L[r['line']].split()[0]
    vz = -1.0 if mer[0] == '-' else 1.0
    hh, mm = mer.lstrip('+-').split(':')
    h = vz * (int(hh) + int(mm) / 60.0)
    return {k: (r['scale'] * a, (g - speeds[k] * h) % 360) for k, (a, g) in r['amp'].items() if k in speeds and k not in LANG}


def rest_rms(t, y, w, kopf):
    p = SF.hoehe_und_ableitungen(t, 0.0, w, kopf)[0]
    d = pd.Series(y - p, index=pd.to_datetime(t, unit='s'))
    d = d - d.rolling('30D', center=True, min_periods=24 * 5).mean()
    d = d.dropna()
    return float(np.sqrt(np.mean(d.values ** 2))), d


def jahresfits(s, kopf, voll):
    namen, speeds, arg, fak = kopf
    nutz = Q.rayleigh(voll, speeds, namen, 365)
    out = []
    a = s.index[0]
    while a + pd.Timedelta(days=365) <= s.index[-1] + pd.Timedelta(days=1):
        blk = s[a:a + pd.Timedelta(days=365)]
        a += pd.Timedelta(days=365)
        if len(blk) < 0.8 * 8760:
            continue
        _, _, _, w, _, _ = Q.fit(blk, nutz, kopf, speeds, arg, fak)
        out.append(w['M2'])
    return out[-6:]


def main(argv):
    kopf = X.kopf_lesen(Q.ZIEL)
    namen, speeds, arg, fak = kopf
    voll = SF.konstituenten(namen, SF.CONSTIT_67) + [k for k in S.OBERTIDEN if k in namen]
    _, recs, anker = M.alle_anker()
    nach = {}
    for r, pfad, fit, _x in anker:
        ordner = os.path.relpath(pfad, M.REIHEN).split(os.sep)[0]
        if not any(k in ordner for k in MESS) or any(k in pfad for k in NICHT):
            continue
        if not r.get('file') or r['line'] == 0 or 'amp' not in r or r.get('current') or r.get('tot', 0) < 0.1:
            continue
        nach.setdefault(pfad, (r, ordner, fit))
    je = {}
    wahl = []
    for pfad, (r, ordner, fit) in sorted(nach.items()):
        if je.get(ordner, 0) < PRO_ORDNER:
            je[ordner] = je.get(ordner, 0) + 1
            wahl.append((pfad, r, ordner, fit))
    if '--max' in argv:
        wahl = wahl[:int(argv[argv.index('--max') + 1])]
    print('%d Reihen aus %d Ordnern' % (len(wahl), len(je)), flush=True)
    F.fes_dazu([r for _p, r, _o, _f in wahl])
    fes_voll([r for _p, r, _o, _f in wahl], namen)
    zeilen = []
    for n, (pfad, r, ordner, fit) in enumerate(wahl):
        try:
            obs = M.lies(pfad)
        except Exception as e:                                    # noqa: BLE001
            print('  %s: nicht lesbar (%s)' % (os.path.relpath(pfad, M.REIHEN), e))
            continue
        if len(obs) < 2000:
            continue
        s = pd.Series([h for _t, h in obs], index=pd.to_datetime([t for t, _h in obs], unit='s')).sort_index()
        s.index = s.index.round("1min")                               # UHSLC-Stempel 16:59:59
        s = s[~s.index.duplicated()]
        voll_s = s[s.index.minute == 0] if (s.index.minute == 0).sum() >= 2000 else s      # Momentanwert zur vollen Stunde
        s2 = voll_s[voll_s.index >= voll_s.index[-1] - pd.Timedelta(days=730)]
        if len(s2) < 24 * 120:
            continue
        t = np.array([i.timestamp() for i in s2.index])
        y = s2.values
        e = dict(ordner=ordner, reihe=os.path.basename(pfad), satz=r['name'], datei=os.path.basename(r['file']),
                 lat='%.4f' % r['lat'], lon='%.4f' % r['lon'], typ=F.typ(r), von=s2.index[0].date(), bis=s2.index[-1].date(),
                 stunden=len(s2), fes_km='%.1f' % max(r['fes_wasser_km'], r['fes_ersatz_km']))
        w_s = satz_w(r, speeds)
        rs, d = rest_rms(t, y, w_s, kopf)
        # Ausreisser (Sensorspitzen) gemeinsam fuer alle Modelle entfernen
        gut = np.ones(len(t), bool)
        idx = pd.to_datetime(t, unit='s')
        dd = d.reindex(idx)
        gut &= ~(np.abs(dd.values) > 5 * np.nanstd(dd.values))
        t, y = t[gut], y[gut]
        e['rms_satz'] = 100 * rest_rms(t, y, w_s, kopf)[0]
        for m, w in (('fes', r.get('fesw')), ('tpxo10', T.konstanten('10', r['lat'], r['lon'])[0]),
                     ('tpxo9', T.konstanten('9', r['lat'], r['lon'])[0])):
            w = {k: v for k, v in (w or {}).items() if k in namen and k not in LANG}
            if '--fes15' in argv and m == 'fes':                   # fair: nur die Konstituenten, die TPXO10 auch hat
                w = {k: v for k, v in w.items() if k in T.konstituenten('10')}
            if 'M2' not in w or w['M2'][0] == 0:
                e['rms_' + m] = e['tide_' + m] = None
                continue
            e['rms_' + m] = 100 * rest_rms(t, y, w, kopf)[0]
            e['tide_' + m] = math.sqrt(max(0.0, e['rms_' + m] ** 2 - e['rms_satz'] ** 2))
        jf = jahresfits(voll_s, kopf, voll)
        if len(jf) >= 2:
            a = np.array([x[0] for x in jf])
            g = np.array([x[1] for x in jf])
            g = (g - g[0] + 180) % 360 - 180
            e['m2_jahre'] = len(jf)
            e['m2_jahr_amp_mm'] = 1000 * float(np.std(a, ddof=1))
            e['m2_jahr_phase_min'] = float(np.std(g, ddof=1)) / H.SPEED['M2'] * 60
        zeilen.append(e)
        print('  %3d %-22s %-38s Satz %5.1f  FES %5s  T10 %5s  T9 %5s cm  M2-Jahre %s' % (
            n, ordner[:22], r['name'][:38], e['rms_satz'],
            *('%.1f' % e['rms_' + m] if e.get('rms_' + m) is not None else '-' for m in ('fes', 'tpxo10', 'tpxo9')),
            ('%d: %.1f mm / %.1f min' % (e['m2_jahre'], e['m2_jahr_amp_mm'], e['m2_jahr_phase_min'])) if 'm2_jahre' in e else '-'),
            flush=True)
    feld = ['ordner', 'reihe', 'satz', 'datei', 'lat', 'lon', 'typ', 'von', 'bis', 'stunden', 'fes_km', 'rms_satz', 'rms_fes',
            'rms_tpxo10', 'rms_tpxo9', 'tide_fes', 'tide_tpxo10', 'tide_tpxo9', 'm2_jahre', 'm2_jahr_amp_mm', 'm2_jahr_phase_min']
    with open(AUS, 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=feld)
        w.writeheader()
        for z in zeilen:
            w.writerow({k: ('%.1f' % v if isinstance(v, float) else ('' if v is None else v)) for k, v in ((k, z.get(k)) for k in feld)})
    Z = [z for z in zeilen if all(z.get('rms_' + m) is not None for m in ('fes', 'tpxo10', 'tpxo9'))]

    def tab(titel, schl):
        print('\n%s\n%-12s %4s | %-23s | %-23s | %s' % (titel, '', 'n', 'RMS Median: Satz FES T10 T9', 'Tidenfehler: FES T10 T9', 'bester FES/T10/T9'))
        G = {}
        for z in Z:
            G.setdefault(schl(z), []).append(z)
        for g in sorted(G, key=lambda g: -len(G[g])):
            zs = G[g]
            med = lambda k: float(np.median([z[k] for z in zs]))
            best = [min(('fes', 'tpxo10', 'tpxo9'), key=lambda m: z['rms_' + m]) for z in zs]
            print('%-12s %4d | %5.1f %5.1f %5.1f %5.1f | %6.1f %6.1f %6.1f    | %3.0f%% %3.0f%% %3.0f%%' % (
                g[:12], len(zs), med('rms_satz'), med('rms_fes'), med('rms_tpxo10'), med('rms_tpxo9'),
                med('tide_fes'), med('tide_tpxo10'), med('tide_tpxo9'), *(100 * best.count(m) / len(best) for m in ('fes', 'tpxo10', 'tpxo9'))))
    tab('Alle (cm)', lambda z: 'alle')
    tab('Kuestentyp', lambda z: z['typ'])
    J = [z for z in zeilen if 'm2_jahre' in z]
    if J:
        print('\nM2-Streuung zwischen Einzeljahren (%d Reihen mit >= 2 vollen Jahren): Amplitude Median %.1f mm (P90 %.1f), Phase Median %.1f min (P90 %.1f)' % (
            len(J), np.median([z['m2_jahr_amp_mm'] for z in J]), np.percentile([z['m2_jahr_amp_mm'] for z in J], 90),
            np.median([z['m2_jahr_phase_min'] for z in J]), np.percentile([z['m2_jahr_phase_min'] for z in J], 90)))
    print('->', os.path.relpath(AUS, ROOT))


if __name__ == '__main__':
    main(sys.argv[1:])
