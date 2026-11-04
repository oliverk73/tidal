#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Eigene HW/NW-Rechnung nach Art der BSH-HDdU (Stufe 4, Oliver 4.11.2026).

Geruest: HW/NW unseres harmonischen Satzes (py/tiden_rechnung.py). Die Abweichung jedes gemessenen
Scheitels davon -- Zeit dt und Hoehe dh, getrennt fuer HW und NW -- wird als Reihe in den
astronomischen Argumenten dargestellt (harmonische Darstellung der Ungleichheiten):
  tau = Mondstundenwinkel, s/h/p/N = mittlere Laengen von Mond, Sonne, Mondperigaeum, Mondknoten
  halbmonatlich 2(s-h), 4(s-h), 6(s-h) | Parallaxe s-p, 2(s-p) und Mischglieder mit 2(s-h)
  Deklination 2s, 4s, 2h | Jahresgang h, 2h | taeglich tau+s, tau-s, tau+s-2h, tau-2s+p
Kein Nodalglied: das tragen f/u des Satzes, frei gefittet faengt es bei 10 Jahren den Meeresspiegeltrend.
Fit: kleinste Quadrate, zweimal mit Ausschluss > 3 Sigma (Sturmfluten, Oberwasser).

Ergebnis: harmonics/hwnw/<kurz>.json {art: {'dt': {glied: [c, s]}, 'dh': ...}, 'satz', 'jahre'}.
Dazu (E['mond']) die reine Mondbasis; die App nimmt HW aus der Mondbasis, NW aus Satz + Ungleichheiten
(vorhersage_kombi, eingebunden in py/tiden_dienst.ereignisse).
Usage: venv/bin/python py/hwnw_ungleichheiten.py eichen   KURZ SCHEITEL.csv SATZDATEI "SATZ" J0 J1
       venv/bin/python py/hwnw_ungleichheiten.py pruefen  KURZ SCHEITEL.csv J0 J1
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tiden_rechnung as TR                                         # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ZIEL = os.path.join(ROOT, 'harmonics/hwnw')

# Glied: (tau, s, h, p, N)
GLIEDER = {
    '2(s-h)': (0, 2, -2, 0, 0), '4(s-h)': (0, 4, -4, 0, 0), '6(s-h)': (0, 6, -6, 0, 0),
    's-p': (0, 1, 0, -1, 0), '2(s-p)': (0, 2, 0, -2, 0),
    '3s-2h-p': (0, 3, -2, -1, 0), 's-2h+p': (0, 1, -2, 1, 0),
    '2s': (0, 2, 0, 0, 0), '4s': (0, 4, 0, 0, 0), '2s-2p': (0, 2, 0, -2, 0),
    'h': (0, 0, 1, 0, 0), '2h': (0, 0, 2, 0, 0),
    'tau+s': (1, 1, 0, 0, 0), 'tau-s': (1, -1, 0, 0, 0), 'tau+s-2h': (1, 1, -2, 0, 0),
    'tau-2s+p': (1, -2, 0, 1, 0), 'tau+3s-2h': (1, 3, -2, 0, 0), 'tau-3s+2h': (1, -3, 2, 0, 0),
}
GLIEDER.pop('2s-2p')                    # = 2(s-p)


def argumente(t):
    """Unix-Zeiten -> Array (n, 5) tau, s, h, p, N in Grad."""
    t = np.asarray(t, float)
    T = (t / 86400.0 + 2440587.5 - 2451545.0) / 36525.0
    s = 218.3165 + 481267.8813 * T
    h = 280.4665 + 36000.7698 * T
    p = 83.3532 + 4069.0137 * T
    N = 125.0445 - 1934.1363 * T
    ut = (t % 86400) / 3600.0
    tau = 15.0 * ut + 180.0 + h - s
    return np.column_stack([tau, s, h, p, N])


# Mondbasis (HW): mehr Glieder, Mischglieder Halbmonat x Jahr/Parallaxe/taeglich (py/hwnw_mondbasis.py)
GLIEDER_MOND = {k: v for k, v in GLIEDER.items() if k != 'tau+3s-2h'}
GLIEDER_MOND.update({
    '8(s-h)': (0, 8, -8, 0, 0), '4s-2h': (0, 4, -2, 0, 0), '3(s-p)': (0, 3, 0, -3, 0),
    '2(s-h)+h': (0, 2, -1, 0, 0), '2(s-h)-h': (0, 2, -3, 0, 0), '2(s-h)+2h': (0, 2, 0, 0, 0),
    '2(s-h)-2h': (0, 2, -4, 0, 0), 'tau+s+(s-p)': (1, 2, 0, -1, 0), 'tau+s-(s-p)': (1, 0, 0, 1, 0),
    'tau-s+(s-p)': (1, 0, 0, -1, 0), 'tau-s-(s-p)': (1, -2, 0, 1, 0), 'tau+s-2(s-h)': (1, -1, 2, 0, 0),
    'tau-s-2(s-h)': (1, -3, 2, 0, 0), '4(s-h)+(s-p)': (0, 5, -4, -1, 0), '4(s-h)-(s-p)': (0, 3, -4, 1, 0),
    '3h': (0, 0, 3, 0, 0), '4h': (0, 0, 4, 0, 0), 'tau+s+2(s-h)': (1, 3, -2, 0, 0)})
GLIEDER_MOND = {k: v for k, v in GLIEDER_MOND.items() if v not in [GLIEDER_MOND[j] for j in list(GLIEDER_MOND)[:list(GLIEDER_MOND).index(k)]]}
PHASE = {'H': 0.0, 'N': 90.0}          # Mondstundenwinkel des Grundtermins (mod 180)


def matrix(t, glieder=None):
    A = argumente(t)
    sp = [np.ones(len(A))]
    for k in (glieder or GLIEDER).values():
        w = np.radians(A @ np.array(k, float))
        sp += [np.cos(w), np.sin(w)]
    return np.column_stack(sp)


def zuordnen(mess, pred, max_h=3.0):
    """-> DataFrame t_mess, t_pred, h_mess, h_pred, art fuer Paare gleicher Art innerhalb max_h."""
    zeilen = []
    for art in 'HN':
        p = [(t, h) for t, h, a in pred if a == art]
        pt = np.array([x for x, _ in p])
        for t, h, a in mess:
            if a != art:
                continue
            j = int(np.argmin(np.abs(pt - t)))
            if abs(pt[j] - t) <= max_h * 3600:
                zeilen.append((t, pt[j], h, p[j][1], art))
    return pd.DataFrame(zeilen, columns=['t_mess', 't_pred', 'h_mess', 'h_pred', 'art'])


def scheitel_csv(pfad, j0, j1):
    d = pd.read_csv(pfad)
    t = pd.to_datetime(d.utc, utc=True)
    m = (t.dt.year >= j0) & (t.dt.year <= j1)
    return [(ts.timestamp(), h, a) for ts, h, a in zip(t[m], d.hoehe_m[m], d.art[m])]


def satz_ereignisse(datei, name, t0, t1):
    D = TR.datei(datei)
    return [(t, h, 'H' if 'High' in a else 'N') for t, h, a in D.ereignisse(name, t0, t1)
            if 'High' in a or 'Low' in a]


def _fit(M, y):
    ok = np.ones(len(y), bool)
    for _ in range(3):
        x, *_ = np.linalg.lstsq(M[ok], y[ok], rcond=None)
        r = y - M @ x
        sd = r[ok].std()
        ok = np.abs(r) < 3 * sd
    return x, sd, ok.mean()


def fingerabdruck(satz):
    """Kurzer Hash ueber Z0, Meridian und Konstanten: die Korrektur gilt nur fuer genau diesen Satz."""
    import hashlib
    t = f'{satz.z0:.4f}|{satz.meridian}|' + '|'.join(f'{k}:{a:.4f}:{g:.2f}' for k, (a, g) in sorted(satz.werte.items()))
    return hashlib.sha1(t.encode()).hexdigest()[:12]


def eichen(kurz, csv, datei, name, j0, j1):
    t0 = dt.datetime(j0, 1, 1, tzinfo=dt.timezone.utc).timestamp() - 86400
    t1 = dt.datetime(j1 + 1, 1, 1, tzinfo=dt.timezone.utc).timestamp() + 86400
    P = zuordnen(scheitel_csv(csv, j0, j1), satz_ereignisse(datei, name, t0, t1))
    aus = dict(satz=name, datei=os.path.relpath(datei, ROOT) if os.path.isabs(datei) else datei,
               jahre=[j0, j1], glieder=GLIEDER, fingerabdruck=fingerabdruck(TR.datei(datei).saetze[name]))
    for art in 'HN':
        q = P[P.art == art]
        M = matrix(q.t_pred.values)
        e = {}
        for groesse, y in (('dt', (q.t_mess - q.t_pred).values / 60.0), ('dh', (q.h_mess - q.h_pred).values)):
            x, sd, anteil = _fit(M, y)
            vor = (y - x[0]).std()
            e[groesse] = dict(mittel=float(x[0]), koeff=x[1:].tolist(), rest_sd=float(sd), anteil=float(anteil))
            print(f'{art}W {groesse}: n={len(y)}  Mittel {x[0]:+.3f}  Streuung vorher {np.std(y):.3f}  '
                  f'nachher {sd:.3f}  ({100 * anteil:.1f} % im Fit)')
            # groesste Glieder
            amp = [(np.hypot(x[1 + 2 * i], x[2 + 2 * i]), g) for i, g in enumerate(GLIEDER)]
            print('    ', ', '.join(f'{g} {a:.3f}' for a, g in sorted(amp, reverse=True)[:6]))
        aus[art] = e
    os.makedirs(ZIEL, exist_ok=True)
    json.dump(aus, open(os.path.join(ZIEL, kurz + '.json'), 'w'), indent=1)
    print('->', os.path.join(ZIEL, kurz + '.json'))


def laden(kurz):
    return json.load(open(os.path.join(ZIEL, kurz + '.json')))


def vorhersage(kurz, t0, t1):
    """-> [(t, h, 'H'/'N')] korrigierte Scheitel."""
    E = laden(kurz)
    roh = satz_ereignisse(os.path.join(ROOT, E['datei']), E['satz'], t0 - 6 * 3600, t1 + 6 * 3600)
    t = np.array([x[0] for x in roh])
    M = matrix(t, E.get('glieder'))
    out = []
    for (tt, h, a), m in zip(roh, M):
        e = E[a]
        kt = e['dt']['mittel'] + m[1:] @ np.array(e['dt']['koeff'])
        kh = e['dh']['mittel'] + m[1:] @ np.array(e['dh']['koeff'])
        tn = tt + 60.0 * kt
        if t0 <= tn <= t1:
            out.append((tn, h + kh, a))
    return out


def grundtermine(t0, t1, phase):
    """Zeiten, zu denen der Mondstundenwinkel tau = phase (mod 180) ist (M2-Durchgang)."""
    t = np.arange(t0, t1, 600.0)
    x = (U_tau(t) - phase) % 180.0
    i = np.nonzero(np.diff(x) < 0)[0]
    return t[i] + (180.0 - x[i]) / (x[i + 1] + 180.0 - x[i]) * 600.0


def U_tau(t):
    return argumente(t)[:, 0]


def eichen_mond(kurz, csv, j0, j1):
    """HW/NW-Zeit und -Hoehe direkt ueber dem Mondgang; schreibt E['mond'] in die vorhandene JSON."""
    E = laden(kurz)
    mess = scheitel_csv(csv, j0, j1)
    t0 = dt.datetime(j0, 1, 1, tzinfo=dt.timezone.utc).timestamp() - 2 * 86400
    t1 = dt.datetime(j1 + 1, 1, 1, tzinfo=dt.timezone.utc).timestamp() + 2 * 86400
    E['mond'] = dict(jahre=[j0, j1], glieder=GLIEDER_MOND)
    for art in 'HN':
        tb = grundtermine(t0, t1, PHASE[art])
        tm = np.array([e[0] for e in mess if e[2] == art])
        hm = np.array([e[1] for e in mess if e[2] == art])
        j = np.clip(np.searchsorted(tb, tm), 1, len(tb) - 1)
        j -= (tm - tb[j - 1]) < (tb[j] - tm)
        M = matrix(tb[j], GLIEDER_MOND)
        xt, sdt, _ = _fit(M, (tm - tb[j]) / 60.0)
        xh, sdh, _ = _fit(M, hm)
        E['mond'][art] = dict(phase=PHASE[art], dt=xt.tolist(), dh=xh.tolist(), rest_sd=[float(sdt), float(sdh)])
        print(f'Mond {art}W: n={len(tm)}  Rest Zeit {sdt:.1f} min, Hoehe {100 * sdh:.0f} cm')
    json.dump(E, open(os.path.join(ZIEL, kurz + '.json'), 'w'), indent=1)


def vorhersage_mond(kurz, t0, t1, arten='HN'):
    E = laden(kurz)['mond']
    out = []
    for art in arten:
        e = E[art]
        tb = grundtermine(t0 - 86400, t1 + 86400, e['phase'])
        M = matrix(tb, E['glieder'])
        for t, d, h in zip(tb, M @ np.array(e['dt']), M @ np.array(e['dh'])):
            if t0 <= t + 60 * d <= t1:
                out.append((t + 60 * d, float(h), art))
    return sorted(out)


WAHL = {'cuxhaven': {'H': 'mond', 'N': 'satz'},      # Pruefung 2025 + Jan/Okt 2026 (4.11.2026)
        'stpauli': {'H': 'satz', 'N': 'satz'}}


def wahl(kurz):
    """{'H'/'N': 'mond'|'satz'|'harm'}: aus der Modelldatei (hwnw_alle.py), sonst WAHL, sonst HW Mond/NW Satz."""
    return laden(kurz).get('wahl') or WAHL.get(kurz, {'H': 'mond', 'N': 'satz'})


def vorhersage_kombi(kurz, t0, t1):
    """App-Weg: je Station und Art die bessere Variante; 'harm' = Scheitel des harmonischen Satzes."""
    w = wahl(kurz)
    out = []
    if 'harm' in w.values():
        E = laden(kurz)
        out += [e for e in satz_ereignisse(os.path.join(ROOT, E['datei']), E['satz'], t0, t1) if w[e[2]] == 'harm']
    if 'mond' in w.values():
        out += [e for e in vorhersage_mond(kurz, t0, t1) if w[e[2]] == 'mond']
    if 'satz' in w.values():
        out += [e for e in vorhersage(kurz, t0, t1) if w[e[2]] == 'satz']
    return sorted(out)


_INDEX = {}


def modell_fuer(datei, satz, s=None):
    """-> Kurzname des HW/NW-Modells fuer (Dateiname, Satzname) oder None. Mit dem Satz s: nur, wenn sein
    Fingerabdruck noch dem geeichten entspricht (Satz neu gefittet -> wieder harmonische Scheitel)."""
    if not _INDEX:
        for p in sorted(os.listdir(ZIEL)) if os.path.isdir(ZIEL) else []:
            if p.endswith('.json'):
                E = json.load(open(os.path.join(ZIEL, p)))
                if 'mond' in E and set((E.get('wahl') or {'H': 'x'}).values()) != {'harm'}:
                    _INDEX[(os.path.basename(E['datei']), E['satz'])] = (p[:-5], E.get('fingerabdruck'))
        _INDEX.setdefault(None, None)
    m = _INDEX.get((os.path.basename(datei), satz))
    if not m:
        return None
    if s is not None and m[1] and m[1] != fingerabdruck(s):
        return None
    return m[0]


def statistik(mess, pred, titel):
    P = zuordnen(mess, pred)
    for art in 'HN':
        q = P[P.art == art]
        dz = (q.t_pred - q.t_mess).values / 60.0
        dh = (q.h_pred - q.h_mess).values
        print(f'  {titel:22} {art}W n={len(q):5d}  Zeit {dz.mean():+5.1f} min  sd {dz.std():4.1f}  '
              f'|90%| {np.percentile(np.abs(dz), 90):4.0f}   Hoehe {100 * dh.mean():+4.0f} cm  sd {100 * dh.std():3.0f}  '
              f'Median|dh| {100 * np.median(np.abs(dh - dh.mean())):3.0f} cm')


def pruefen(kurz, csv, j0, j1):
    E = laden(kurz)
    t0 = dt.datetime(j0, 1, 1, tzinfo=dt.timezone.utc).timestamp()
    t1 = dt.datetime(j1 + 1, 1, 1, tzinfo=dt.timezone.utc).timestamp()
    mess = scheitel_csv(csv, j0, j1)
    statistik(mess, satz_ereignisse(os.path.join(ROOT, E['datei']), E['satz'], t0 - 86400, t1 + 86400), 'harmonischer Satz')
    statistik(mess, vorhersage(kurz, t0 - 86400, t1 + 86400), 'Satz + Ungleichheiten')
    if 'mond' in E:
        statistik(mess, vorhersage_mond(kurz, t0 - 86400, t1 + 86400), 'Mond + Ungleichheiten')
        statistik(mess, vorhersage_kombi(kurz, t0 - 86400, t1 + 86400), 'Kombination (App)')


if __name__ == '__main__':
    a = sys.argv[1:]
    if a[0] == 'eichen':
        eichen(a[1], a[2], a[3], a[4], int(a[5]), int(a[6]))
        eichen_mond(a[1], a[2], int(a[5]), int(a[6]))
    else:
        pruefen(a[1], a[2], int(a[3]), int(a[4]))
