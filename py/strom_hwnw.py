#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Strom-Kenter und -Maxima aus Messungen korrigieren (Oliver 6.11.2026) -- Gegenstueck zu hwnw_alle.py fuer Stroeme.

Messung: NOAA CO-OPS PORTS (product=currents, 6 min, cm/s und Richtung), 2016-2025, Cache
water_levels/USA_COOPS_currents/<station>_<bin>.csv. Projektion auf die Flutrichtung des Satzes (max_direction im
Kopf): u > 0 Flut, u < 0 Ebbe. Ereignisse: Kenter (Nulldurchgang, SF = Flut beginnt, SE = Ebbe beginnt) und Maxima
(groesster |u| zwischen zwei Kentern, MF/ME). Vorhersage: dieselben vier Arten aus dem harmonischen Satz.
Korrektur je Art: Zeitabstand Messung - Satz = astronomische Glieder (wie hwnw_ungleichheiten) + Satzstaerke;
Eichung 2016-2024, Pruefung 2025.

Modelle: harmonics/strom_hwnw/<station>.json (nur Arten mit >= 1 min Gewinn im Pruefjahr), korrigieren() fuer die App.
Usage: venv/bin/python py/strom_hwnw.py laden|probe|alle [--nur=n03020_7,...]
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys
import time
import urllib.request

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hwnw_ungleichheiten as HU                                    # noqa: E402
import tiden_rechnung as TR                                         # noqa: E402

ROOT = HU.ROOT
DWF = os.path.join(ROOT, 'harmonics/classic/harmonics-dwf-20251228-free.txt')
CACHE = os.path.join(ROOT, 'water_levels/USA_COOPS_currents')
TEST = ('ca0101_8', 'cb0102_9', 'cb1301_4', 'db0301_22', 'g06010_1', 'jx0501_4', 'kb0102_4', 'n03020_7',
        'nl0101_9', 'pm0101_4', 's08010_4', 't01010_3')
JAHRE = range(2016, 2026)
EICH, PRUEF = (2016, 2024), 2025
KN = 51.4444                     # cm/s je Knoten
ARTEN = {'Max Flood': 'MF', 'Max Ebb': 'ME', 'Slack, Flood Begins': 'SF', 'Slack, Ebb Begins': 'SE'}


def saetze():
    """noaa_station_id -> (Satzname, Flutrichtung) fuer Stromsaetze in DWF."""
    out, kopf = {}, []
    L = open(DWF, encoding='latin-1').read().split('\n')
    for i, z in enumerate(L):
        if z.startswith('#'):
            kopf.append(z)
            continue
        if kopf and z.endswith('Current'):
            k = '\n'.join(kopf)
            m, f = re.search(r'^# noaa_station_id: (\S+)', k, re.M), re.search(r'^# max_direction: (\d+)', k, re.M)
            if m and f:
                out[m.group(1)] = (z, float(f.group(1)))
        if z:
            kopf = []
    return out


def laden(sid):
    os.makedirs(CACHE, exist_ok=True)
    p = os.path.join(CACHE, sid + '.csv')
    if os.path.exists(p):
        return p
    st, b = sid.rsplit('_', 1)
    zeilen = []
    for j in JAHRE:
        for m in range(1, 13):
            a = dt.date(j, m, 1)
            e = (dt.date(j + (m == 12), 1 if m == 12 else m + 1, 1) - dt.timedelta(days=1))
            url = ('https://api.tidesandcurrents.noaa.gov/api/prod/datagetter?product=currents'
                   f'&station={st}&bin={b}&begin_date={a:%Y%m%d}&end_date={e:%Y%m%d}&units=metric&time_zone=gmt'
                   '&format=json&application=tiden_pruefung')
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'tiden-pruefung/1.0'}),
                                            timeout=120) as r:
                    d = json.load(r)
                zeilen += [f"{x['t']},{x['s']},{x['d']}" for x in (d.get('data') or []) if x.get('s') not in (None, '')]
            except Exception as ex:  # noqa: BLE001
                print(sid, a, ex, flush=True)
            time.sleep(1.5)
    open(p, 'w').write('t,s,d\n' + '\n'.join(zeilen) + '\n')
    return p


def mess_ereignisse(p, flut):
    """-> [(t, wert_kn, art)] aus der Messreihe (art MF/ME/SF/SE)."""
    d = pd.read_csv(p)
    t = pd.to_datetime(d.t, utc=True)
    u = pd.Series(pd.to_numeric(d.s, errors='coerce').values / KN
                  * np.cos(np.radians(pd.to_numeric(d.d, errors='coerce').values - flut)), index=t)
    u = u[~u.index.duplicated()].sort_index().dropna()
    u = u.resample('6min').mean().interpolate(limit=5, limit_area='inside')
    u = u.rolling(5, center=True, min_periods=3).mean()          # 30 min glaetten
    tt = ((u.index - pd.Timestamp('1970-01-01', tz='UTC')) / pd.Timedelta(seconds=1)).values.astype(float)   # einheitenfest (us/ns)
    v = u.values
    ok = np.isfinite(v)
    ev = []
    # Kenter: Vorzeichenwechsel zwischen Abschnitten mit |u| > 0.1 kn (Hysterese gegen Rauschen um Null)
    sig = np.where(v > 0.1, 1, np.where(v < -0.1, -1, 0))
    letzte = None
    for i in np.nonzero(sig)[0]:
        if letzte is not None and sig[i] != sig[letzte] and i - letzte < 30 and ok[letzte:i + 1].all():
            seg = v[letzte:i + 1]
            j = letzte + int(np.argmin(np.abs(seg)))
            k = j if (j + 1 > i or np.sign(v[j]) != np.sign(v[j + 1])) else j
            # Nulldurchgang linear zwischen k und k+1 (falls vorhanden)
            if k + 1 <= i and v[k] != v[k + 1] and np.sign(v[k]) != np.sign(v[k + 1]):
                tz = tt[k] + (tt[k + 1] - tt[k]) * v[k] / (v[k] - v[k + 1])
            else:
                tz = tt[j]
            ev.append((tz, 0.0, 'SF' if sig[i] > 0 else 'SE'))
        letzte = i
    # Maxima zwischen zwei Kentern
    kt = [e[0] for e in ev]
    for a, b in zip(kt, kt[1:]):
        if b - a < 2 * 3600:
            continue
        m = (tt > a) & (tt < b) & ok
        if m.sum() < 10:
            continue
        idx = np.nonzero(m)[0]
        j = idx[int(np.argmax(np.abs(v[idx])))]
        if abs(v[j]) < 0.2 or j in (idx[0], idx[-1]):
            continue
        y0, y1, y2 = v[j - 1], v[j], v[j + 1]          # Parabel durch drei Punkte
        nenner = y0 - 2 * y1 + y2
        dx = 0.5 * (y0 - y2) / nenner if nenner else 0.0
        ev.append((tt[j] + dx * 360.0, float(y1), 'MF' if y1 > 0 else 'ME'))
    return sorted(ev)


def satz_ereignisse(D, name, t0, t1):
    return [(t, v, ARTEN[a]) for t, v, a in D.ereignisse(name, t0, t1) if a in ARTEN]


def paaren(mess, pred, art, max_h=2.5):
    pt = np.array([e[0] for e in pred if e[2] == art])
    pv = np.array([e[1] for e in pred if e[2] == art])
    out = []
    for t, v, a in mess:
        if a != art or not len(pt):
            continue
        j = int(np.argmin(np.abs(pt - t)))
        if abs(pt[j] - t) <= max_h * 3600:
            out.append((t, pt[j], pv[j]))
    return np.array(out)


def jahr(j0, j1):
    return (dt.datetime(j0, 1, 1, tzinfo=dt.timezone.utc).timestamp(),
            dt.datetime(j1 + 1, 1, 1, tzinfo=dt.timezone.utc).timestamp())


def probe(nur):
    D = TR.datei(DWF)
    S = saetze()
    zeilen = []
    for sid in nur:
        if sid not in S:
            print(sid, 'kein Satz'); continue
        name, flut = S[sid]
        p = laden(sid)
        mess = [x for x in mess_ereignisse(p, flut) if np.isfinite(x[0])]
        if len(mess) < 500:
            print(f'{sid:12} zu wenig Messereignisse ({len(mess)})'); continue
        a, b = jahr(*EICH)
        c, e = jahr(PRUEF, PRUEF)
        pred = satz_ereignisse(D, name, a - 86400, e + 86400)
        z = [sid, name[:50]]
        txt = []
        for art in ('SF', 'MF', 'SE', 'ME'):
            P = paaren(mess, pred, art)
            if len(P) < 200:
                z += ['', '', '']; txt.append(f'{art} --'); continue
            y = (P[:, 0] - P[:, 1]) / 60.0
            gut = np.abs(y - np.median(y)) < 120                 # grobe Fehlzuordnungen (> 2 h) raus
            P, y = P[gut], y[gut]
            X = np.column_stack([HU.matrix(P[:, 1], HU.GLIEDER), np.abs(P[:, 2])])
            ei = (P[:, 0] >= a) & (P[:, 0] < b)
            pr = (P[:, 0] >= c) & (P[:, 0] < e)
            if ei.sum() < 200 or pr.sum() < 50:
                z += ['', '', '']; txt.append(f'{art} wenig'); continue
            beta, sd, _ = HU._fit(X[ei], y[ei])
            roh = np.sqrt(np.mean(y[pr] ** 2))
            neu = np.sqrt(np.mean((y[pr] - X[pr] @ beta) ** 2))
            z += [f'{roh:.1f}', f'{neu:.1f}', str(int(pr.sum()))]
            txt.append(f'{art} {roh:4.0f}->{neu:4.0f} ({np.mean(y[pr]):+.0f})')
        zeilen.append(';'.join(z))
        print(f'{sid:12} {name[:38]:38} ' + ' | '.join(txt), flush=True)
    aus = os.path.join(ROOT, 'harmonics/help', f'strom_hwnw_probe_{dt.date.today():%Y%m%d}.csv')
    open(aus, 'w', encoding='utf-8').write('station;satz;' + ';'.join(f'{a}_roh;{a}_neu;{a}_n' for a in ('SF', 'MF', 'SE', 'ME'))
                                           + '\n' + '\n'.join(zeilen) + '\n')
    print('->', aus)


ZIEL = os.path.join(ROOT, 'harmonics/strom_hwnw')


def auswahl():
    """Je PORTS-Station (CO-OPS mdapi, ohne Grosse Seen) der Satz mit Tiefe am naechsten an 20 ft."""
    S = saetze()
    st = {}
    for sid, (name, flut) in S.items():
        m = re.search(r'depth (\d+) ft', name)
        if '_' not in sid or not m:
            continue
        stn = sid.rsplit('_', 1)[0]
        d = abs(int(m.group(1)) - 20)
        if stn not in st or d < st[stn][0]:
            st[stn] = (d, sid)
    ports = json.load(open(os.path.join(CACHE, 'ports_stationen.json')))
    return sorted(sid for stn, (d, sid) in st.items() if stn in ports)


def eichen(sid, D, S):
    """Modell je Ereignisart (Eichung 2016-2024, Pruefung 2025); nur Arten mit >= 1 min Gewinn."""
    name, flut = S[sid]
    mess = [x for x in mess_ereignisse(laden(sid), flut) if np.isfinite(x[0])]
    a, b = jahr(*EICH)
    c, e = jahr(PRUEF, PRUEF)
    pred = satz_ereignisse(D, name, a - 86400, e + 86400)
    modell = dict(satz=name, datei=os.path.relpath(DWF, ROOT), station=sid, flut=flut,
                  fingerabdruck=HU.fingerabdruck(D.saetze[name]), arten={}, pruefung={})
    for art in ('SF', 'MF', 'SE', 'ME'):
        P = paaren(mess, pred, art)
        if len(P) < 200:
            continue
        y = (P[:, 0] - P[:, 1]) / 60.0
        gut = np.abs(y - np.median(y)) < 120
        P, y = P[gut], y[gut]
        X = np.column_stack([HU.matrix(P[:, 1], HU.GLIEDER), np.abs(P[:, 2])])
        ei = (P[:, 0] >= a) & (P[:, 0] < b)
        pr = (P[:, 0] >= c) & (P[:, 0] < e)
        if ei.sum() < 200 or pr.sum() < 50:
            continue
        beta, sd, _ = HU._fit(X[ei], y[ei])
        roh = float(np.sqrt(np.mean(y[pr] ** 2)))
        neu = float(np.sqrt(np.mean((y[pr] - X[pr] @ beta) ** 2)))
        modell['pruefung'][art] = dict(jahr=PRUEF, roh=roh, neu=neu, n=int(pr.sum()))
        if neu <= roh - 1.0:
            modell['arten'][art] = beta.tolist()
    return modell


def alle(nur=None):
    os.makedirs(ZIEL, exist_ok=True)
    D = TR.datei(DWF)
    S = saetze()
    for sid in (nur or auswahl()):
        try:
            m = eichen(sid, D, S)
        except Exception as e:  # noqa: BLE001
            print(f'{sid:12} Fehler {e}', flush=True)
            continue
        p = os.path.join(ZIEL, sid + '.json')
        if m['arten']:
            json.dump(m, open(p, 'w'), indent=1)
        elif os.path.exists(p):
            os.remove(p)
        print(f"{sid:12} {m['satz'][:40]:40} " + ' | '.join(
            f"{a} {v['roh']:4.0f}->{v['neu']:4.0f}{'*' if a in m['arten'] else ' '}" for a, v in m['pruefung'].items()), flush=True)


def korrigieren(ev, modell):
    """[(t, wert, label)] des Satzes -> korrigierte Zeiten fuer Arten mit Modell (App). Reihenfolge bleibt erhalten:
    eine Korrektur, die ein Ereignis an seinem Nachbarn vorbeischieben wuerde, entfaellt."""
    out = []
    for t, v, lab in ev:
        art = ARTEN.get(lab)
        if art in modell['arten']:
            x = np.concatenate([HU.matrix(np.array([t]), HU.GLIEDER)[0], [abs(v)]])
            t = t + float(x @ np.array(modell['arten'][art])) * 60.0
        out.append((t, v, lab))
    for i in range(1, len(out) - 1):
        if not (out[i - 1][0] < out[i][0] < out[i + 1][0]):
            out[i] = ev[i]
    return out


def main(argv):
    schritt = argv[0] if argv else 'probe'
    opt = dict(x[2:].split('=', 1) for x in argv if x.startswith('--'))
    nur = opt['nur'].split(',') if opt.get('nur') else list(TEST)
    if schritt == 'laden':
        for sid in nur:
            print(sid, laden(sid), flush=True)
    elif schritt == 'alle':
        alle(opt['nur'].split(',') if opt.get('nur') else None)
    else:
        probe(nur)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
