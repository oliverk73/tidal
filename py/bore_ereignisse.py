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
Weitere Bores (5.11.2026): Kalender (Severn/Minsterworth von tides.today, Dordogne/Saint-Pardon aus dem
Mascaret-Kalender der Peniche) -> Modell mit Klasse 0 = keine Bore; Regel (Turnagain Arm: NW Anchorage + 75 min,
mit der HW/NW-Rechnung us_9455920).
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
KAL = os.path.join(ROOT, 'water_levels/bore_kalender')
OBS = 'harmonics/utide/harmonics_utide_observations.txt'
TAB = 'harmonics/utide/harmonics_utide_tidetables.txt'

# Kalender-Bores (5.11.2026): Ereignisse aus veroeffentlichten Bore-Kalendern, Bezug = bester nahe Satz
KALENDER = {
    'severn_minsterworth': dict(
        name='Minsterworth Tidal Bore (River Severn), England, United Kingdom', zone='Europe/London',
        lat=51.8547, lon=-2.3262, kand=[('harmonics/ticon/harmonics_ticon4_worldwide.txt', 'Avonmouth (Port of Bristol), England, United Kingdom'),
                                        (TAB, 'Sharpness Dock, England, United Kingdom'), (OBS, 'Prince of Wales Bridge, England, United Kingdom')],
        woerter={1: '1 star', 2: '2 stars', 3: '3 stars', 4: '4 stars', 5: '5 stars'},
        quelle='tides.today Severn-Bore-Kalender 2025/2026 (Minsterworth, Sterne 1-5; nur Bores ab 1 Stern)',
        text='Derived from the published Severn Bore timetables (Minsterworth, rated 1 to 5 stars); tides without a listed bore are '
             'left out. Stonebench is about 15 minutes and Over Bridge about 35 minutes later.'),
    'dordogne_saint_pardon': dict(
        name='Saint-Pardon Tidal Bore (Mascaret, Dordogne), France', zone='Europe/Paris',
        lat=44.93127, lon=-0.32077, laufzeit_min=14.4,
        kand=[(OBS, 'Libourne (Isle / Dordogne), France'), (OBS, 'Bordeaux, France'),
                                        (OBS, 'Bassens (Garonne), France'), (OBS, 'Ambès, France'),
                                        (OBS, 'Trompeloup (Pauillac), France')],
        woerter={1: 'small', 2: 'moderate', 3: 'large'},
        quelle='Calendrier du mascaret 2026, La Péniche du Mascaret (Saint-Pardon); Klasse aus dem Koeffizienten (<80, <95, >=95)',
        text='Derived from the 2026 mascaret calendar of La Péniche du Mascaret. Its times apply about 2 km downstream of the '
             'Péniche (0.3744° W); for the Impasse du Mascaret at Saint-Pardon, 4.3 km further upstream along the river, we add '
             '14 minutes at the calendar\'s mean wave speed of 18 km/h. The size follows the French tidal coefficient (small below 80, '
             'moderate below 95, large from 95). The mascaret only forms on larger tides.'),
}
QT_KAND = [(TAB, 'Ganpu (Hangzhou Wan), Zhejiang, China'), (TAB, 'Zhapu (Hangzhou Wan), Zhejiang, China'),
           ('harmonics/noaa/harmonics_noaa_cptt.txt', 'Haining (Qiantang Jiang), Zhejiang, China')]
QT_TEXT = ('Derived from the official Qiantang bore forecast of the Zhejiang provincial government ("Smart Qiantang Tide"), '
           'rated from no bore to 5 stars, with the expected bore height. ')
QT_ALIAS = {'观潮城(仓前)': ('观潮城(萧山仓前)',)}       # Ort heisst 2026 anders
QT_STERNE = {'无': 0, '一星': 1, '二星': 2, '三星': 3, '四星': 4, '五星': 5}
for _code, _stnm, _name, _lat, _lon in (
        ('qiantang_yanguan', '大江东八工段（盐官）', 'Yanguan Tidal Bore (Qiantang River), Zhejiang, China', 30.4024, 120.5520),
        ('qiantang_guanchaocheng', '观潮城(仓前)', 'Guanchaocheng Tidal Bore (Qiantang River, Xiaoshan), Zhejiang, China', 30.2806, 120.4021),
        ('qiantang_chengshi_yangtai', '城市阳台(奥体)', 'Hangzhou City Balcony Tidal Bore (Qiantang River), Zhejiang, China', 30.2442, 120.2125)):
    KALENDER[_code] = dict(name=_name, zone='Asia/Shanghai', lat=_lat, lon=_lon, kand=QT_KAND, stnm=_stnm,
                           woerter={1: '1 star', 2: '2 stars', 3: '3 stars', 4: '4 stars', 5: '5 stars'},
                           quelle=f'Zhejiang "Smart Qiantang Tide" (ueber chinaviki.com tide-proxy), Ort {_stnm}, 2024-2026',
                           text=QT_TEXT)
# Regel-Bores: feste Faustregel auf einen Bezugsort (mit eigener HW/NW-Rechnung, falls vorhanden)
REGELN = {
    'turnagain_beluga_point': dict(
        name='Beluga Point Tidal Bore (Turnagain Arm), Alaska', zone='America/Anchorage', lat=60.9989, lon=-149.6889,
        datei='harmonics/classic/harmonics-dwf-20251228-free.txt', bezug='Anchorage (Knik Arm, Cook Inlet), Alaska',
        hwnw='us_9455920', art='N', versatz=75.0, hub=[8.2, 8.8, 9.4], woerter={1: 'small', 2: 'moderate', 3: 'large'},
        quelle='Faustregel NWS/Alaska-Fuehrer: Beluga Point ~1:15 h nach NW Anchorage, Bore ab ~27 ft (8,2 m) Hub',
        text='Rule of thumb used by the US National Weather Service and local guides: the bore passes Beluga Point about '
             '1 hour 15 minutes after low water at Anchorage, on tides with a range of about 8.2 m (27 ft) or more. '
             'Expect it within roughly 15 to 30 minutes of the time shown.'),
}


KORREKTUR = os.path.join(ZIEL, 'korrekturen.json')   # Olivers Karten-Korrekturen (Position, Name), ueberleben Neueichung


def _korrekturen():
    return json.load(open(KORREKTUR, encoding='utf-8')) if os.path.exists(KORREKTUR) else {}


def _mit_korrektur(code, d):
    k = _korrekturen().get(code, {})
    return dict(d, **{f: k[f] for f in ('name', 'lat', 'lon') if f in k})


def _korrigieren(name, **felder):
    """Fuer die Karte (app.py): Bore-Station `name` verschieben/umbenennen. -> True, wenn gefunden."""
    for f in sorted(os.listdir(ZIEL)):
        if not f.endswith('.json') or f == os.path.basename(KORREKTUR):
            continue
        p = os.path.join(ZIEL, f)
        E = json.load(open(p, encoding='utf-8'))
        if E.get('name') != name:
            continue
        E.update(felder)
        json.dump(E, open(p, 'w'), indent=1, ensure_ascii=False)
        K = _korrekturen()
        K.setdefault(E['code'], {}).update(felder)
        json.dump(K, open(KORREKTUR, 'w'), indent=1, ensure_ascii=False)
        return True
    return False


def position_setzen(name, lat, lon):
    return _korrigieren(name, lat=round(float(lat), 5), lon=round(float(lon), 5))


def umbenennen(alt, neu):
    return _korrigieren(alt, name=neu)


def _ts(s):
    return np.array([x.replace(tzinfo=dt.timezone.utc).timestamp() for x in s])


def _ereignisse(datei, ref, t0, t1, hwnw=None):
    if hwnw:
        return HU.vorhersage_kombi(hwnw, t0, t1)
    return HU.satz_ereignisse(os.path.join(ROOT, datei), ref, t0, t1)


def _hw_tabelle(datei, ref, t0, t1):
    """-> Array (n, 4): t_HW, Hoehe, Hub zum NW davor, Hub zum NW danach."""
    ev = _ereignisse(datei, ref, t0 - 86400, t1 + 86400)
    H = [(t, h) for t, h, a in ev if a == 'H']
    N = np.array([(t, h) for t, h, a in ev if a == 'N'])
    out = []
    for t, h in H:
        j = np.searchsorted(N[:, 0], t)
        if 0 < j < len(N) and t0 <= t <= t1:
            out.append((t, h, h - N[j - 1, 1], h - N[j, 1]))
    return np.array(out)


def _x(th, hh, hv, hn, klein=False):
    if klein:                                    # wenige Termine (Kalender): nur Hoehe/Hub und Halbmonat
        A = HU.argumente(th)
        w = np.radians(2 * (A[:, 1] - A[:, 2]))
        j = np.radians(A[:, 2])                  # Jahresgang (Sonnenlaenge h): Severn-Sterne haengen an der HW-Hoehe
        return np.column_stack([np.ones(len(th)), hh, hv, hn, np.cos(w), np.sin(w), np.cos(j), np.sin(j),
                                np.cos(2 * j), np.sin(2 * j)])
    return np.column_stack([HU.matrix(th, HU.GLIEDER), hh, hv, hn])


def _schwellen(z, kl, kmin, kmax):
    """Je Klassengrenze die beste Schwelle; die Grenze 0/1 (Bore ja/nein) nach F1 der Bores: Trefferquote allein
    verschluckt seltene Bores (Severn 32 %), Youden meldet zu viele (Severn Okt-Dez 31 statt 11) -- 5.11.2026."""
    schw = []
    for k in range(kmin, kmax):
        c = np.quantile(z, np.linspace(0.01, 0.99, 500))
        if k == 0:                               # F1 der Bores: Treffer gegen Fehlalarme, ohne die vielen Nicht-Bores
            def f1(g):
                tp = np.sum((z > g) & (kl > 0))
                return 2 * tp / max(np.sum(z > g) + np.sum(kl > 0), 1)
            schw.append(float(max(c, key=f1)))
        else:
            schw.append(float(max(c, key=lambda g: np.mean((z > g) == (kl > k)))))
    return schw


def _eichen_allgemein(code, meta, tb, kl, eich, pruef, kand, mit_null, klein, quelle, hb=None):
    """tb/kl: Bore-Zeiten (UTC) und Klassen; eich/pruef: (t0, t1) Zeitraeume.
    mit_null: Kalender listet nur Tiden MIT Bore -> jede Bezugs-HW ohne Bore im Zeitraum = Klasse 0."""
    best = None
    for datei, ref in kand:
        try:
            T = _hw_tabelle(datei, ref, eich[0], eich[1])
        except Exception:  # noqa: BLE001
            continue
        m = (tb >= eich[0]) & (tb <= eich[1])
        d = np.array([(t - T[np.argmin(np.abs(T[:, 0] - t)), 0]) / 60 for t in tb[m]])
        # Versatz kann > halbe Tide sein: Streuung um den Median auf 745 min falten
        md = np.median(d)
        sd = np.std((d - md + 372) % 745 - 372)
        if best is None or sd < best[0]:
            best = (sd, datei, ref, float(md))
    _, datei, ref, versatz = best
    zeilen = {}
    for name_z, (a, b) in (('eich', eich), ('pruef', pruef)):
        T = _hw_tabelle(datei, ref, a, b)
        tz = T[:, 0] + versatz * 60
        m = (tb >= a - 3600) & (tb <= b + 3600)
        k = np.zeros(len(T), int)
        y = np.full(len(T), np.nan)
        hh_ = np.full(len(T), np.nan)
        hbm = hb[m] if hb is not None else np.zeros(m.sum())
        for t, c, h in zip(tb[m], kl[m], hbm):
            i = int(np.argmin(np.abs(tz - t)))
            if abs(tz[i] - t) < 120 * 60:
                k[i], y[i], hh_[i] = c, (t - T[i, 0]) / 60 - versatz, h
        zeilen[name_z] = (T, k, y, hh_)
    T, k, y, hh_ = zeilen['eich']
    X = _x(T[:, 0], T[:, 1], T[:, 2], T[:, 3], klein)
    hat = k > 0
    bz, sd, _ = HU._fit(X[hat], y[hat])
    bk, *_ = np.linalg.lstsq(X if mit_null else X[hat], (k if mit_null else k[hat]).astype(float), rcond=None)
    bh = np.linalg.lstsq(X[hat], hh_[hat], rcond=None)[0].tolist() if hb is not None else None
    kmin = 0 if mit_null else 1
    schw = _schwellen(X @ bk if mit_null else X[hat] @ bk, k if mit_null else k[hat], kmin, int(k.max()))
    T, k, y, hh_ = zeilen['pruef']
    X = _x(T[:, 0], T[:, 1], T[:, 2], T[:, 3], klein)
    kv = kmin + sum((X @ bk) > g for g in schw)
    hat = k > 0
    rest = y[hat] - X[hat] @ bz
    erg = dict(zeit_rms=float(np.sqrt(np.mean(rest ** 2))), zeit_max=float(np.abs(rest).max()),
               klasse_richtig=float(np.mean(kv[hat] == k[hat])), n=int(hat.sum()))
    if hb is not None:
        erg['hoehe_rms'] = float(np.sqrt(np.mean((hh_[hat] - X[hat] @ np.array(bh)) ** 2)))
    if mit_null:
        erg['bore_erkannt'] = float(np.mean(kv[hat] > 0))
        erg['falsch_alarm'] = float(np.mean(kv[~hat] > 0)) if (~hat).any() else 0.0
    print(f"{code:24} Bezug {ref.split(',')[0][:22]:22} Versatz {versatz:+5.0f} | Pruefung n={erg['n']}: Zeit {erg['zeit_rms']:4.1f} min "
          f"(max {erg['zeit_max']:.0f}) | Klasse {100 * erg['klasse_richtig']:.0f} %"
          + (f" | Hoehe {erg['hoehe_rms']:.2f} m" if hb is not None else '')
          + (f" | Bore erkannt {100 * erg['bore_erkannt']:.0f} %, Fehlalarm {100 * erg['falsch_alarm']:.0f} %" if mit_null else ''),
          flush=True)
    os.makedirs(ZIEL, exist_ok=True)
    json.dump(_mit_korrektur(code, dict(code=code, name=meta['name'], lat=meta['lat'], lon=meta['lon'], zone=meta['zone'], typ='modell',
                   bezug=ref, datei=datei, versatz=versatz, klein=klein, mit_null=mit_null, zeit=bz.tolist(),
                   klasse=bk.tolist(), schwellen=schw, hoehe=bh, woerter=meta['woerter'], text=meta['text'],
                   pruefung=erg, quelle=quelle)), open(os.path.join(ZIEL, code + '.json'), 'w'), indent=1, ensure_ascii=False)


def _kalender_severn():
    """tides.today-Seiten (water_levels/bore_kalender/severn_<jahr>.html): Minsterworth, Ortszeit, Sterne."""
    import glob
    import re
    from zoneinfo import ZoneInfo
    z = ZoneInfo('Europe/London')
    out = []
    for f in sorted(glob.glob(os.path.join(KAL, 'severn_*.html'))):
        L = [x.strip() for x in re.sub(r'<[^>]*>', '\n', open(f, encoding='utf-8').read()).split('\n') if x.strip()]
        i = next(n for n, x in enumerate(L) if re.match(r'Severn Bore \d{4} - Minsterworth$', x))
        for n in range(i + 1, len(L) - 2):
            if re.match(r'Severn Bore \d{4} - ', L[n]):
                break
            m = re.match(r'(?:[A-Z][a-z]+day )?(\d{1,2})(?:st|nd|rd|th)? ([A-Z][a-z]+) (\d{4})$', L[n])
            if m and re.match(r'\d\d:\d\d$', L[n + 1]):     # 2025: '01 February 2025', 2026: 'Monday 5th January 2026'
                d = dt.datetime.strptime(f'{m.group(1)} {m.group(2)} {m.group(3)} {L[n + 1]}', '%d %B %Y %H:%M').replace(tzinfo=z)
                out.append((d.timestamp(), L[n + 2].count('\u2b50')))
    return out


def _kalender_qiantang(stnm):
    """-> [(t_utc, sterne, bore_hoehe_m)] aus water_levels/bore_kalender/qiantang/<datum>.json (Zeiten Beijing)."""
    import glob
    from zoneinfo import ZoneInfo
    z = ZoneInfo('Asia/Shanghai')
    out = {}
    for f in sorted(glob.glob(os.path.join(KAL, 'qiantang', '*.json'))):
        for x in json.load(open(f, encoding='utf-8')).get('items', []):
            if x.get('STNM') not in (stnm, *QT_ALIAS.get(stnm, ())):
                continue
            for i in '12':
                t = x.get('YC' + i)
                if t:
                    tt = dt.datetime.strptime(t, '%Y-%m-%d %H:%M:%S').replace(tzinfo=z).timestamp()
                    out[tt] = (tt, QT_STERNE.get(x.get('RANK' + i), 0), float(x.get('YG' + i) or 0))
    return sorted(out.values())


def _kalender_dordogne():
    from zoneinfo import ZoneInfo
    z = ZoneInfo('Europe/Paris')
    out = []
    for m in json.load(open(os.path.join(ROOT, 'tide_tables/mascaret_peniche/calendrier_mascaret_2026.json'))):
        for r in m['rows']:
            for i, feld in enumerate(('mat', 'soir')):
                v = r.get(feld)
                if not v or ':' not in str(v):
                    continue
                umst = (m['month'], r['day'], feld) == (10, 25, 'mat') and v == '3:52'
                if umst:                         # Quellfehler Zeitumstellung (fit_mascaret_peniche.py): 2:52 der
                    v = '2:52'                   # zweiten Stunde, also schon MEZ (fold=1), sonst 58 min daneben
                hh, mm = map(int, str(v).split(':'))
                co = r['coeff'][min(i, len(r['coeff']) - 1)]
                d = dt.datetime(2026, m['month'], r['day'], hh, mm, tzinfo=z, fold=1 if umst else 0)
                out.append((d.timestamp(), 1 if co < 80 else 2 if co < 95 else 3))
    return out


QT_URL = 'https://www.chinaviki.com/qiantangjiang-dachaol/tide-proxy.php?date={}'   # Quelle: Zhejiang "Smart Qiantang Tide"


def laden_qiantang(von='2024-01-01', bis='2026-12-31'):
    """Amtliche Qiantang-Vorhersage je Tag (alle Orte) -> water_levels/bore_kalender/qiantang/<datum>.json."""
    ziel = os.path.join(KAL, 'qiantang')
    os.makedirs(ziel, exist_ok=True)
    d, ende = dt.date.fromisoformat(von), dt.date.fromisoformat(bis)
    while d <= ende:
        f = os.path.join(ziel, f'{d}.json')
        if not os.path.exists(f):
            try:
                p = _json(QT_URL.format(d))
                if p.get('items'):
                    json.dump(p, open(f, 'w'), ensure_ascii=False)
            except Exception as e:  # noqa: BLE001
                print(d, 'Fehler', e, flush=True)
            time.sleep(1.5)
        d += dt.timedelta(days=1)


def _jahr(j0, j1):
    return (dt.datetime(j0, 1, 1, tzinfo=dt.timezone.utc).timestamp(),
            dt.datetime(j1 + 1, 1, 1, tzinfo=dt.timezone.utc).timestamp())


def eichen_kalender(nur=None):
    for code, meta in KALENDER.items():
        if nur and code not in nur:
            continue
        if code.startswith('qiantang'):
            ev = _kalender_qiantang(meta['stnm'])
        else:
            ev = sorted(_kalender_severn() if code.startswith('severn') else _kalender_dordogne())
        if not ev:
            print(code, 'keine Daten'); continue
        tb, kl = np.array([e[0] for e in ev]), np.array([e[1] for e in ev])
        # Kalenderpunkt != Stationsort: Wellenlaufzeit entlang des Flusses (Dordogne 5.11.2026: Vorhersagepunkt
        # 0.3744 W, Flusskm 27,8 nach OSM; Impasse du Mascaret Flusskm 23,5 -> 4,3 km / 18 km/h = 14,4 min)
        tb = tb + meta.get('laufzeit_min', 0.0) * 60
        hb = np.array([e[2] for e in ev]) if code.startswith('qiantang') else None
        if code.startswith('qiantang'):          # Eichung 2024-2025, Pruefung 2026
            eich, pruef = _jahr(2024, 2025), _jahr(2026, 2026)
        elif code.startswith('severn'):            # Eichung 2025, Pruefung 2026
            eich, pruef = _jahr(2025, 2025), _jahr(2026, 2026)
        else:                                     # nur 2026: Jan-Aug eichen, Sep-Dez pruefen
            eich = (_jahr(2026, 2026)[0], dt.datetime(2026, 9, 1, tzinfo=dt.timezone.utc).timestamp())
            pruef = (eich[1], _jahr(2026, 2026)[1])
        if ((tb >= pruef[0]) & (tb < pruef[1])).sum() < 20 or ((tb >= eich[0]) & (tb < eich[1])).sum() < 40:
            print(code, 'zu wenig Daten fuer Eichung/Pruefung -- uebersprungen'); continue
        klein = not code.startswith('qiantang')  # Qiantang: ~1400 Tiden/Jahr, volle Glieder
        _eichen_allgemein(code, meta, tb, kl, eich, pruef, meta['kand'], True, klein, meta['quelle'], hb)
        # endgueltig ueber den ganzen Zeitraum eichen (Pruefwerte aus dem Lauf oben bleiben stehen)
        E = json.load(open(os.path.join(ZIEL, code + '.json')))
        _eichen_allgemein(code, meta, tb, kl, (tb.min() - 86400, tb.max() + 86400), pruef,
                          [(E['datei'], E['bezug'])], True, klein, meta['quelle'], hb)
        F = json.load(open(os.path.join(ZIEL, code + '.json')))
        F['pruefung'] = E['pruefung']
        F['pruefung']['hinweis'] = 'Pruefwerte aus getrennter Eichung; Modell danach ueber den ganzen Kalender geeicht'
        json.dump(F, open(os.path.join(ZIEL, code + '.json'), 'w'), indent=1, ensure_ascii=False)


def regeln_schreiben():
    for code, r in REGELN.items():
        json.dump(_mit_korrektur(code, dict(code=code, typ='regel', **{k: v for k, v in r.items()}, pruefung={})),
                  open(os.path.join(ZIEL, code + '.json'), 'w'), indent=1, ensure_ascii=False)
        print(code, 'Regel geschrieben')


def vorhersage(code, t0, t1):
    """-> [(t, klasse)] Bore-Ankuenfte aus dem Modell harmonics/bore/<code>.json."""
    E = json.load(open(os.path.join(ZIEL, code + '.json')))
    if E.get('typ') == 'regel':
        ev = _ereignisse(E['datei'], E['bezug'], t0 - 86400, t1 + 86400, E.get('hwnw'))
        out = []
        for i, (t, h, a) in enumerate(ev):
            if a != E['art']:
                continue
            hub = max([abs(h - ev[j][1]) for j in (i - 1, i + 1) if 0 <= j < len(ev) and ev[j][2] != a] or [0])
            k = sum(hub >= g for g in E['hub'])
            tb = t + E['versatz'] * 60
            if k and t0 <= tb <= t1:
                out.append((tb, int(k), None))
        return out
    T = _hw_tabelle(E['datei'], E['bezug'], t0 - E['versatz'] * 60 - 86400, t1 - E['versatz'] * 60 + 86400)
    X = _x(T[:, 0], T[:, 1], T[:, 2], T[:, 3], E.get('klein', False))
    kmin = 0 if E.get('mit_null') else 1
    kv = kmin + sum((X @ np.array(E['klasse'])) > g for g in E['schwellen'])
    tb = T[:, 0] + (E['versatz'] + X @ np.array(E['zeit'])) * 60
    hh = X @ np.array(E['hoehe']) if E.get('hoehe') else [None] * len(tb)
    return [(float(t), int(k), None if h is None else max(float(h), 0.0))
            for t, k, h in zip(tb, kv, hh) if k > 0 and t0 <= t <= t1]


def eichen(nur=None):
    """CHS-Stationen (alle Tiden mit Bore, Klasse 1-4)."""
    S = json.load(open(os.path.join(DATEN, 'stationen.json')))
    for code, (zone, name) in STATIONEN.items():
        if nur and code not in nur:
            continue
        b = pd.read_csv(os.path.join(DATEN, f'{code}_bores.csv'), parse_dates=['utc'])
        tb, kl = _ts(b.utc), b.wert.values.astype(int)
        meta = dict(name=name, zone=zone, lat=S[code]['latitude'], lon=S[code]['longitude'], woerter=GROESSE,
                    text='Derived from the bore predictions of the Canadian Hydrographic Service (CHS).')
        _eichen_allgemein(code, meta, tb, kl, _jahr(*EICH), _jahr(*PRUEF), [(BEZUG_DATEI, r) for r in BEZUG_KAND],
                          False, False, 'CHS IWLS wlp-bores 2020-2024')


def modelle():
    """-> [Modell-dict] aller Bore-Stationen (fuer Karte und App)."""
    import glob
    return [json.load(open(f)) for f in sorted(glob.glob(os.path.join(ZIEL, '*.json'))) if f != KORREKTUR]


def seite(name, tage=7, jetzt=None):
    """Fuer die App: -> dict(name, lat, lon, zone, zeilen=[(datum, uhrzeit, klasse, wort)], text, pruefung) oder None."""
    from zoneinfo import ZoneInfo
    E = next((m for m in modelle() if m['name'] == name), None)
    if E is None:
        return None
    z = ZoneInfo(E['zone'])
    jetzt = jetzt or time.time()
    t0 = dt.datetime.fromtimestamp(jetzt, z).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    w = {int(k): v for k, v in E.get('woerter', GROESSE).items()}
    zeilen = []
    ev = vorhersage(E['code'], t0, t0 + tage * 86400 + 7200)   # +2 h: Tag 7 nicht durch die Sommerzeit kuerzen
    tage_liste = []
    d0 = dt.datetime.fromtimestamp(t0, z).date()
    for i in range(tage):                    # jeder Tag eine Zeile, auch ohne Bore (sonst wirkt die Woche kuerzer)
        tag = d0 + dt.timedelta(days=i)
        tage_liste.append(tag)
        hier = [x for x in ev if dt.datetime.fromtimestamp(x[0], z).date() == tag]
        if not hier:
            zeilen.append((tag.strftime('%a %Y-%m-%d'), '—', 0, 'no bore expected'))
        for t, k, h in hier:
            d = dt.datetime.fromtimestamp(t, z)
            zeilen.append((d.strftime('%a %Y-%m-%d'), d.strftime('%H:%M %Z'), k, w.get(k, '')
                           + (f' · about {h:.1f} m' if h is not None and h >= 0.05 else '')))
    return dict(name=name, code=E['code'], lat=E['lat'], lon=E['lon'], zone=E['zone'], typ=E.get('typ', 'modell'),
                bezug=E['bezug'], text=E.get('text', ''), zeilen=zeilen, pruefung=E.get('pruefung', {}),
                kmax=max(w))


def main(argv):
    schritt = argv[0] if argv else 'laden'
    opt = dict(a[2:].split('=', 1) for a in argv if a.startswith('--'))
    nur = opt.get('nur', '').split(',') if opt.get('nur') else None
    if schritt == 'laden':
        laden(nur)
    elif schritt == 'laden_qiantang':
        laden_qiantang()
    elif schritt == 'eichen':
        eichen(nur)
        eichen_kalender(nur)
        regeln_schreiben()
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
