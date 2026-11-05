#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Bore-Ereignisse (Flutwelle in Fluessen): Ankunftszeit und Groessenklasse (Oliver 5.11.2026).

Quelle: CHS IWLS, Zeitreihe wlp-bores (amtliche Vorhersage der Bore-Ankunft, Wert = Groessenklasse
1 klein .. 4 gross) und wlp-hilo (HW/NW-Vorhersage) an den sechs kanadischen Bore-Stationen der Fundy-Bucht.
Bei der Harmonics-Erzeugung waren diese Stationen ausgelassen worden (download_chs_ns_annual.py: "bore station").

Schritte:
  laden   wlp-bores und wlp-hilo 2020-2027 -> water_levels/Canada_CHS_bore/<code>_bores.csv, <code>_hilo.csv
  eichen  Bore-Zeit = HW des Stationssatzes + Korrektur aus astronomischen Gliedern (wie hwnw_ungleichheiten),
          Groessenklasse = Regression auf dieselben Glieder; Eichung 2020-2024, Pruefung 2025-2027
          -> harmonics/bore/<code>.json
Usage: venv/bin/python py/bore_ereignisse.py laden|eichen [--nur=00175]
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
import time
import urllib.request

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hwnw_ungleichheiten as HU                                    # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATEN = os.path.join(ROOT, 'water_levels/Canada_CHS_bore')
API = 'https://api-iwls.dfo-mpo.gc.ca/api/v1'
# code: (Zeitzone, Anzeigename) -- Name mit 'Tidal Bore', damit er nicht mit einem Pegel verwechselt wird
STATIONEN = {
    '00175': ('America/Moncton', 'Moncton Tidal Bore (Petitcodiac River), New Brunswick, Canada'),
    '00265': ('America/Halifax', 'Truro Tidal Bore (Salmon River), Nova Scotia, Canada'),
    '00210': ('America/Halifax', 'Maccan Tidal Bore (Maccan River), Nova Scotia, Canada'),
    '00211': ('America/Halifax', 'River Hebert Tidal Bore, Nova Scotia, Canada'),
    '00267': ('America/Halifax', 'Maitland Tidal Bore (Shubenacadie River), Nova Scotia, Canada'),
    '00281': ('America/Halifax', 'Tidal View Farm Tidal Bore, Nova Scotia, Canada'),
}
GROESSE = {1: 'small', 2: 'moderate', 3: 'large', 4: 'very large'}
JAHRE = range(2020, 2028)


def _json(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'tiden-pruefung/1.0'})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)


def stationen():
    """Code -> IWLS-Stationseintrag (mit id, Position)."""
    d = _json(f'{API}/stations?time-series-code=wlp-bores')
    return {s['code']: s for s in d if s['code'] in STATIONEN}


def laden(nur=None):
    os.makedirs(DATEN, exist_ok=True)
    S = stationen()
    json.dump(S, open(os.path.join(DATEN, 'stationen.json'), 'w'), indent=1)
    for code, s in S.items():
        if nur and code not in nur:
            continue
        for reihe in ('wlp-bores', 'wlp-hilo'):
            ziel = os.path.join(DATEN, f"{code}_{reihe.split('-')[1]}.csv")
            zeilen = []
            for j in JAHRE:
                for m0 in (1, 4, 7, 10):
                    a = dt.datetime(j, m0, 1, tzinfo=dt.timezone.utc)
                    b = dt.datetime(j + (m0 == 10), 1 if m0 == 10 else m0 + 3, 1, tzinfo=dt.timezone.utc)
                    url = (f"{API}/stations/{s['id']}/data?time-series-code={reihe}"
                           f"&from={a:%Y-%m-%dT%H:%M:%SZ}&to={b:%Y-%m-%dT%H:%M:%SZ}")
                    try:
                        d = _json(url)
                    except Exception as e:  # noqa: BLE001
                        print(code, reihe, a.date(), 'Fehler', e)
                        d = []
                    zeilen += [f"{x['eventDate'][:16].replace('T', ' ')},{x['value']}" for x in d]
                    time.sleep(0.3)
            zeilen = sorted(set(zeilen))
            open(ziel, 'w').write('utc,wert\n' + '\n'.join(zeilen) + '\n')
            print(f"{code} {s['officialName']:18} {reihe:10} {len(zeilen):6} Eintraege "
                  f"{zeilen[0][:10] if zeilen else ''} .. {zeilen[-1][:10] if zeilen else ''}", flush=True)


BEZUG_DATEI = 'harmonics/utide/harmonics_utide_tidetables.txt'
BEZUG_KAND = ('Saint John, New Brunswick, Canada', 'Burntcoat Head, Nova Scotia, Canada',
              'Hopewell Cape, New Brunswick, Canada')
EICH, PRUEF = (2020, 2024), (2025, 2026)   # 2027 vorlaeufig (CHS: nach dem laufenden Jahr ungeprueft; Tidal View dort anders)
ZIEL = os.path.join(ROOT, 'harmonics/bore')


def _ts(s):
    return np.array([x.replace(tzinfo=dt.timezone.utc).timestamp() for x in s])


def _merkmale(ref, tb, versatz):
    """Je Bore: zugehoeriges HW des Bezugs (t, Hoehe), Hub zum NW davor und danach."""
    ev = HU.satz_ereignisse(os.path.join(ROOT, BEZUG_DATEI), ref, tb.min() - 2 * 86400, tb.max() + 2 * 86400)
    H = np.array([(t, h) for t, h, a in ev if a == 'H'])
    N = np.array([(t, h) for t, h, a in ev if a == 'N'])
    i = np.array([np.argmin(np.abs(H[:, 0] + versatz * 60 - t)) for t in tb])
    th, hh = H[i, 0], H[i, 1]
    j = np.clip(np.searchsorted(N[:, 0], th) - 1, 0, len(N) - 2)
    return th, hh, hh - N[j, 1], hh - N[j + 1, 1]


def _x(th, hh, hv, hn):
    return np.column_stack([HU.matrix(th, HU.GLIEDER), hh, hv, hn])


def vorhersage(code, t0, t1):
    """-> [(t, klasse)] Bore-Ankuenfte aus dem Modell harmonics/bore/<code>.json."""
    E = json.load(open(os.path.join(ZIEL, code + '.json')))
    ev = HU.satz_ereignisse(os.path.join(ROOT, E['datei']), E['bezug'], t0 - 6 * 3600 - 86400, t1 + 86400)
    H = [(t, h) for t, h, a in ev if a == 'H']
    N = [(t, h) for t, h, a in ev if a == 'N']
    out = []
    for t, h in H:
        vor = [x for x in N if x[0] < t]
        nach = [x for x in N if x[0] > t]
        if not vor or not nach:
            continue
        x = _x(np.array([t]), np.array([h]), np.array([h - vor[-1][1]]), np.array([h - nach[0][1]]))[0]
        tb = t + (E['versatz'] + float(x @ np.array(E['zeit']))) * 60
        z = float(x @ np.array(E['klasse']))
        k = 1 + sum(z > g for g in E['schwellen'])
        if t0 <= tb <= t1:
            out.append((tb, int(k)))
    return out


def eichen(nur=None):
    os.makedirs(ZIEL, exist_ok=True)
    S = json.load(open(os.path.join(DATEN, 'stationen.json')))
    for code, (_, name) in STATIONEN.items():
        if nur and code not in nur:
            continue
        b = pd.read_csv(os.path.join(DATEN, f'{code}_bores.csv'), parse_dates=['utc'])
        tb, kl = _ts(b.utc), b.wert.values.astype(int)
        jahr = b.utc.dt.year.values
        e = (jahr >= EICH[0]) & (jahr <= EICH[1])
        # Bezug: kleinste Streuung des Abstands Bore - HW
        best = None
        for ref in BEZUG_KAND:
            ev = HU.satz_ereignisse(os.path.join(ROOT, BEZUG_DATEI), ref, tb[e].min() - 86400, tb[e].min() + 400 * 86400)
            pt = np.array([t for t, h, a in ev if a == 'H'])
            tt = tb[e][tb[e] < pt.max()]
            d = np.array([(t - pt[np.argmin(np.abs(pt - t))]) / 60 for t in tt])
            if best is None or d.std() < best[0]:
                best = (d.std(), ref, float(np.median(d)))
        _, ref, versatz = best
        th, hh, hv, hn = _merkmale(ref, tb, versatz)
        X = _x(th, hh, hv, hn)
        y = (tb - th) / 60 - versatz
        bz, sd, anteil = HU._fit(X[e], y[e])
        # Klasse: lineare Punktzahl, Schwellen auf beste Trefferquote im Eichzeitraum
        bk, *_ = np.linalg.lstsq(X[e], kl[e].astype(float), rcond=None)
        z = X @ bk
        schw = []
        for k in range(1, kl.max()):
            c = np.quantile(z[e], np.linspace(0.02, 0.98, 400))
            schw.append(float(max(c, key=lambda g: np.mean(((z[e] > g) == (kl[e] > k))))))
        kv = 1 + sum(z > g for g in schw)
        p = (jahr >= PRUEF[0]) & (jahr <= PRUEF[1])
        rest = y - X @ bz
        roh = (tb - th) / 60 - versatz
        print(f"{code} {name:30} Bezug {ref.split(',')[0]:15} Versatz {versatz:+5.0f} min | Zeit-Streuung roh "
              f"{roh[p].std():4.1f} -> Modell {np.sqrt(np.mean(rest[p] ** 2)):4.1f} min (Pruefjahre, max {np.abs(rest[p]).max():.0f}) | "
              f"Klasse richtig {100 * np.mean(kv[p] == kl[p]):.1f} %, um 1 daneben {100 * np.mean(np.abs(kv[p] - kl[p]) == 1):.1f} %",
              flush=True)
        s = S[code]
        json.dump(dict(code=code, name=name, lat=s['latitude'], lon=s['longitude'], bezug=ref, datei=BEZUG_DATEI,
                       versatz=versatz, zeit=bz.tolist(), klasse=bk.tolist(), schwellen=schw,
                       pruefung=dict(jahre=list(PRUEF), zeit_rms=float(np.sqrt(np.mean(rest[p] ** 2))),
                                     klasse_richtig=float(np.mean(kv[p] == kl[p]))),
                       quelle='CHS IWLS wlp-bores 2020-2024'),
                  open(os.path.join(ZIEL, code + '.json'), 'w'), indent=1)


def modelle():
    """-> [Modell-dict] aller geeichten Bore-Stationen (fuer Karte und App)."""
    import glob
    return [json.load(open(f)) for f in sorted(glob.glob(os.path.join(ZIEL, '*.json')))]


def seite(name, tage=7, jetzt=None):
    """Fuer die App: -> dict(name, lat, lon, zone, zeilen=[(datum, uhrzeit, klasse, wort)], pruefung) oder None."""
    from zoneinfo import ZoneInfo
    E = next((m for m in modelle() if m['name'] == name), None)
    if E is None:
        return None
    z = ZoneInfo(STATIONEN[E['code']][0])
    jetzt = jetzt or time.time()
    t0 = dt.datetime.fromtimestamp(jetzt, z).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    zeilen = []
    for t, k in vorhersage(E['code'], t0, t0 + tage * 86400):
        d = dt.datetime.fromtimestamp(t, z)
        zeilen.append((d.strftime('%a %Y-%m-%d'), d.strftime('%H:%M %Z'), k, GROESSE.get(k, '')))
    return dict(name=name, code=E['code'], lat=E['lat'], lon=E['lon'], zone=STATIONEN[E['code']][0],
                bezug=E['bezug'], zeilen=zeilen, pruefung=E['pruefung'])


def main(argv):
    schritt = argv[0] if argv else 'laden'
    opt = dict(a[2:].split('=', 1) for a in argv if a.startswith('--'))
    nur = opt.get('nur', '').split(',') if opt.get('nur') else None
    if schritt == 'laden':
        laden(nur)
    elif schritt == 'eichen':
        eichen(nur)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
