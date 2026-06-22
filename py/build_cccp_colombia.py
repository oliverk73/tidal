#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CCCP/DIMAR Colombia Pazifik-Tidetafeln (HW/LW) -> UTide-TC-Harmonics.

Datenbasis: CCCP (Centro de Investigaciones Oceanograficas e Hidrograficas del
Pacifico, DIMAR) Mareas-Portal, Jahres-CSV 2026 (Fecha;Hora;Valor;Clasificacion,
P=Pleamar/HW B=Bajamar/LW, Hoehe in m ueber Chart Datum, Zeit LOKAL COT=UTC-5).
Quelle: https://cccp.dimar.mil.co/sites/default/MAREAS/Mareas/datos/<Name>.csv

Neue Pazifik-Stationen: Bahia Malaga, Juanchaco (IOC bmal leer / juac nur 2024),
Bahia Solano (ersetzt reines FES-Modell durch offizielle DIMAR-Vorhersage).
Tumaco/Buenaventura werden mitgefittet als VALIDIERUNG gegen TICON4 (UHSLC).

Fit: feste Konstituentenliste auf HW/LW-Extrema, ein volles Jahr -> S2/K2 & K1/P1
getrennt, SA/SSA aufloesbar. Lokalzeit +5h -> UTC (Greenwich-Phasen). Z0 = Fit-Mittel
ueber Chart Datum (CCCP). Validierung gegen IOC-Messung (sola 2023, juac 2024) prueft
Amplituden UND Zeitzonen-Annahme. Koordinaten von ioc-sealevelmonitoring.org.

Output (--write): haengt neue Stationen an harmonics/utide/harmonics_utide_tidetables.txt
(Gruppe "UTide TC"), Dublettenschutz ueber station_id_context. Danach TCD neu bauen.
Ohne --write: nur QA + Validierung.
"""
import os, re, sys, json, glob
import numpy as np
from datetime import datetime, timedelta
import utide
import matplotlib.dates as mdates
try:
    import requests
except ImportError:
    requests = None
    import urllib.request

HARM = os.path.expanduser('~/harmonics')
COL = os.path.expanduser('~/annual_predictions/colombia/2026')
HDRSRC = f'{HARM}/att/harmonics_att_np203.txt'   # 175-Konstituenten-Order
OUT = f'{HARM}/utide/harmonics_utide_tidetables.txt'

# Fit-Liste: Haupttiden + wichtigste Flachwasser/langperiodisch. Ein volles Jahr
# HW/LW erlaubt die S2/K2- und K1/P1-Trennung sowie SA/SSA. Konservativ gehalten
# (HW/LW-only -> keine exotischen Flachwasser-Cluster, vgl. shoa constit-Bug).
CONSTIT = ['M2', 'S2', 'N2', 'K2', 'K1', 'O1', 'P1', 'Q1', '2N2', 'NU2', 'MU2',
           'L2', 'T2', 'M4', 'MS4', 'MN4', 'M6', '2MS6', 'SA', 'SSA', 'MM', 'MF']

# Koordinaten von ioc-sealevelmonitoring.org (feedback_ioc_coordinates).
# region/datum gleich fuer alle (Costa Pacifica, Chart Datum CCCP).
STATIONS = {
    # key: (name, lat, lon, station_id, is_new)
    'Malaga':       ('Bahía Málaga',            3.972964, -77.327669, 'CCCP-MALAGA',       True),
    'Juanchaco':    ('Juanchaco',               3.915000, -77.359170, 'CCCP-JUANCHACO',    True),
    'Solano':       ('Bahía Solano',            6.232778, -77.411940, 'CCCP-SOLANO',       True),
    # Validierungs-Stationen (existieren bereits via TICON4/UHSLC) — nicht schreiben:
    'Tumaco':       ('Tumaco',                  1.820000, -78.728700, 'CCCP-TUMACO',       False),
    'Buenaventura': ('Buenaventura',            3.890600, -77.080800, 'CCCP-BUENAVENTURA', False),
}

IOC_VALID = {  # code -> (jahr-fenster) fuer Messdaten-Cross-Check
    'Solano':    ('sola', '2023-01-01', '2024-01-01'),
    'Juanchaco': ('juac', '2024-01-01', '2025-01-01'),
}

# TICON4-Referenz (M2,S2,K1,O1 A/g) fuer Tumaco/Buenaventura
TICON_REF = {
    'Buenaventura': {'M2': (1.4967, 254.86), 'S2': (0.4021, 314.49),
                     'K1': (0.1149, 62.69), 'O1': (0.0256, 72.86)},
    'Tumaco':       {'M2': (1.1982, 249.97), 'S2': (0.3204, 306.69),
                     'K1': (0.1072, 56.94), 'O1': (0.0216, 58.27)},
}


def parse_csv(key):
    """CCCP-CSV -> sortierte Liste (datetime_UTC, hoehe_m)."""
    fn = f'{COL}/{key}.csv'
    ser = []
    for ln in open(fn, encoding='utf-8').read().splitlines()[1:]:
        p = ln.split(';')
        if len(p) < 4:
            continue
        d, mon, yr = map(int, p[0].split('/'))
        hh, mi, ss = map(int, p[1].split(':'))
        h = float(p[2])
        loc = datetime(yr, mon, d, hh, mi, ss)
        ser.append((loc + timedelta(hours=5), h))   # COT -> UTC
    return sorted(ser)


def fit_extrema(ser, lat):
    t = mdates.date2num([x[0] for x in ser])
    h = np.array([x[1] for x in ser])
    coef = utide.solve(t, h, lat=lat, epoch='1970-01-01', nodal=True, trend=False,
                       method='ols', conf_int='none', constit=CONSTIT, verbose=False)
    res = {n: (A, g) for n, A, g in zip(coef['name'], coef['A'], coef['g'])}
    return coef, res, float(coef['mean']), len(h)


def oow_test(coef, ser):
    """Rueck-Vorhersage an den Extrema-Zeitpunkten -> RMS/R2 als Stabilitaetstest."""
    t = mdates.date2num([x[0] for x in ser])
    h = np.array([x[1] for x in ser])
    rec = utide.reconstruct(t, coef, epoch='1970-01-01', min_SNR=0, verbose=False).h
    rms = float(np.sqrt(np.mean((h - rec) ** 2)))
    ss = 1 - np.sum((h - rec) ** 2) / np.sum((h - h.mean()) ** 2)
    return rms, float(ss)


def fetch_ioc(code, t0, t1):
    """IOC service.php in Monatschunks (Jahres-Request ist zu gross -> Timeout)."""
    import pandas as pd
    out = []
    months = pd.date_range(t0, t1, freq='MS')
    for i in range(len(months) - 1):
        a = months[i].strftime('%Y-%m-%d')
        b = months[i + 1].strftime('%Y-%m-%d')
        url = (f'https://www.ioc-sealevelmonitoring.org/service.php?query=data'
               f'&code={code}&format=json&timestart={a}&timestop={b}')
        try:
            if requests:
                d = requests.get(url, timeout=120).json()
            else:
                with urllib.request.urlopen(url, timeout=120) as r:
                    d = json.load(r)
            if isinstance(d, list):
                out += d
        except Exception:
            pass
    return out


def fit_ioc(code, t0, t1, lat):
    """IOC 1-min Rohdaten -> stuendlich gemittelt -> UTide SL-Fit (Validierung)."""
    data = fetch_ioc(code, t0, t1)
    # haeufigsten Sensor waehlen (gemischte Sensoren -> Datum-Offsets)
    from collections import Counter
    if data:
        top = Counter(r.get('sensor') for r in data).most_common(1)[0][0]
        data = [r for r in data if r.get('sensor') == top]
    rows = [(r['stime'], r['slevel']) for r in data if r.get('slevel') not in (None, '')]
    if len(rows) < 2000:
        return None
    times = np.array([datetime.strptime(r[0], '%Y-%m-%d %H:%M:%S') for r in rows])
    vals = np.array([float(r[1]) for r in rows])
    # auf volle Stunde binnen (resample 1h-Mittel) -> bin-shift-Bug vermeiden
    import pandas as pd
    s = pd.Series(vals, index=pd.DatetimeIndex(times)).sort_index()
    s = s[(s > s.quantile(0.001)) & (s < s.quantile(0.999))]   # Ausreisser
    s = s.resample('1h').mean().dropna()
    if len(s) < 1500:
        return None
    t = mdates.date2num(s.index.to_pydatetime())
    coef = utide.solve(t, s.values, lat=lat, epoch='1970-01-01', nodal=True,
                       trend=False, method='ols', conf_int='none',
                       constit=CONSTIT, verbose=False)
    return {n: (A, g) for n, A, g in zip(coef['name'], coef['A'], coef['g'])}, len(s)


def read_header_order():
    lines = open(HDRSRC, encoding='iso-8859-1').read().splitlines()
    order, in_s = [], False
    for l in lines:
        if l.startswith('# Constituent speeds'):
            in_s = True
            continue
        if in_s:
            if l.startswith('#') or not l.strip():
                continue
            m = re.match(r'^(\S+)\s+[\d.]+\s*$', l.strip())
            if m:
                order.append(m.group(1))
                if len(order) == 175:
                    break
    assert len(order) == 175, len(order)
    return order


ORDER = read_header_order()


def block(key):
    name, lat, lon, sid, _ = STATIONS[key]
    res = RESULTS[key]['res']
    z0 = RESULTS[key]['z0']
    n = RESULTS[key]['n']
    rms, r2 = RESULTS[key]['oow']
    fullname = f'{name}, Colombia'
    out = ['# BEGIN HOT COMMENTS',
           '# country: Colombia',
           '# region: Costa Pacífica',
           '# source: CCCP/DIMAR Pacifico, Tabla de Mareas HW/LW 2026',
           f'# station_id_context: {sid}',
           '# date_imported: 20260622',
           '# datum: Chart Datum (CCCP, nivel de reduccion)',
           '# confidence: 5',
           f'# utide: period=2026 (1yr HW/LW) constit={len(CONSTIT)} n={n}; '
           f'OOW RMS={rms*100:.1f}cm R2={r2:.3f}',
           '# !units: meters',
           f'# !longitude: {lon:.4f}',
           f'# !latitude: {lat:.4f}',
           fullname,
           '+00:00 :UTC',
           f'{z0:.4f} meters']
    for c in ORDER:
        if c in res:
            A, g = res[c]
            out.append(f'{c:<16}{A:.4f}  {g % 360:.2f}')
        else:
            out.append('x 0 0')
    return '\n'.join(out)


RESULTS = {}


def main():
    write = '--write' in sys.argv
    do_ioc = '--ioc' in sys.argv or write

    # 1) Fit aller Stationen aus Kalender
    for key, (name, lat, lon, sid, isnew) in STATIONS.items():
        ser = parse_csv(key)
        coef, res, z0, n = fit_extrema(ser, lat)
        rms, r2 = oow_test(coef, ser)
        RESULTS[key] = {'res': res, 'z0': z0, 'n': n, 'oow': (rms, r2),
                        'lat': lat, 'isnew': isnew}

    # 2) QA-Tabelle
    print(f"{'Station':<14}{'lat':>7}  {'M2_A':>6}{'M2_g':>7}  {'S2_A':>6}{'S2_g':>7}"
          f"  {'K1_A':>6}{'K1_g':>7}  {'O1_A':>6}  {'Z0':>6}  {'F':>5}  {'R2':>5}{'RMS':>6}")
    for key in STATIONS:
        r = RESULTS[key]['res']
        m2a, m2g = r['M2']; s2a, s2g = r['S2']; k1a, k1g = r['K1']; o1a, o1g = r['O1']
        F = (k1a + o1a) / (m2a + s2a)
        rms, r2 = RESULTS[key]['oow']
        tag = '*' if RESULTS[key]['isnew'] else ' '
        print(f"{tag}{key:<13}{RESULTS[key]['lat']:>7.3f}  {m2a:>6.3f}{m2g:>7.1f}"
              f"  {s2a:>6.3f}{s2g:>7.1f}  {k1a:>6.3f}{k1g:>7.1f}  {o1a:>6.3f}"
              f"  {RESULTS[key]['z0']:>6.3f}  {F:>5.2f}  {r2:>5.3f}{rms*100:>5.1f}cm")

    # 3) Validierung gegen TICON4 (Tumaco/Buenaventura)
    print("\n=== Validierung vs TICON4 (UHSLC) — Tumaco/Buenaventura ===")
    for key in ('Buenaventura', 'Tumaco'):
        r = RESULTS[key]['res']
        print(f"  {key}:")
        for c in ('M2', 'S2', 'K1', 'O1'):
            ca, cg = r[c]; ra, rg = TICON_REF[key][c]
            dg = ((cg - rg + 180) % 360) - 180
            print(f"    {c}: CCCP {ca:.3f}/{cg:6.1f}  TICON4 {ra:.3f}/{rg:6.1f}"
                  f"  dA={100*(ca-ra)/ra:+5.1f}%  dg={dg:+5.1f}°")

    # 4) Validierung gegen IOC-Messung (Solano/Juanchaco)
    if do_ioc:
        print("\n=== Validierung vs IOC-Messung (gemessen, UTide SL) ===")
        for key, (code, t0, t1) in IOC_VALID.items():
            try:
                out = fit_ioc(code, t0, t1, RESULTS[key]['lat'])
            except Exception as e:
                print(f"  {key} ({code}): IOC-Fehler {e}")
                continue
            if not out:
                print(f"  {key} ({code}): zu wenig Daten")
                continue
            ires, ni = out
            r = RESULTS[key]['res']
            print(f"  {key} (IOC {code}, n={ni}h):")
            for c in ('M2', 'S2', 'K1', 'O1'):
                if c not in ires:
                    continue
                ca, cg = r[c]; ia, ig = ires[c]
                dg = ((cg - ig + 180) % 360) - 180
                print(f"    {c}: CCCP {ca:.3f}/{cg:6.1f}  IOC {ia:.3f}/{ig:6.1f}"
                      f"  dA={100*(ca-ia)/ia:+5.1f}%  dg={dg:+5.1f}°")

    # 5) Schreiben
    if not write:
        print("\n(QA-Modus — mit --write werden NEUE Stationen angehaengt)")
        return
    blocks = [block(k) for k in STATIONS if RESULTS[k]['isnew']]
    existing = open(OUT, encoding='iso-8859-1').read()
    if not existing.endswith('\n'):
        existing += '\n'
    new = [b for b in blocks
           if f"station_id_context: {b.splitlines()[4].split(': ', 1)[1]}" not in existing]
    skipped = len(blocks) - len(new)
    with open(OUT, 'w', encoding='iso-8859-1') as f:
        f.write(existing + ('\n'.join(new) + '\n' if new else ''))
    print(f"\nAngehaengt an {OUT}: {len(new)} neu, {skipped} uebersprungen."
          f"\n-> danach: build_tide_db harmonics/binary/harmonics_utide_tidetables.tcd {OUT}")


if __name__ == '__main__':
    main()
