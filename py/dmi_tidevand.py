#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Gezeitentafeln des DMI fuer Groenland (und die Faeroeer) laden und fitten.

Das Daenische Meteorologische Institut veroeffentlicht jedes Jahr Tafeln fuer
213 Orte: 106 in Daenemark, 96 in Groenland, 11 auf den Faeroeern. Grundlage
sind harmonische Konstanten aus eigenen Pegelreihen (der Dateikopf nennt sie:
"Data series: 06/1992 - 06/2001 : 2610 uniq days"). Groenland hat bei uns 27
Uebertragungen ohne Messung im Umkreis von 50 km -- dort ist das die beste
frei zugaengliche Quelle.

Quelle: https://ocean.dmi.dk/Tides/<jahr>/  (Verzeichnis frei auflistbar)
  <Ort>.t.txt   Kopf mit Position, Zeitzone, Bezugsniveau, Messzeitraum;
                darunter Hoch- und Niedrigwasser "yyyymmddHHMM<TAB>cm"
                in der ORTSZEIT des Kopfes, Hoehen ueber LAT.

Ablage: tide_tables/dmi/<jahr>/<Ort>.t.txt  (Tidenkalender gehoeren nach
tide_tables/, Olivers Regel). Eine Anfrage je Sekunde, ehrlicher User-Agent.

Fit wie bei den uebrigen Tafeln (py/fit_svalbard_longyearbyen.py): Scheitel mit
halber Kosinuswelle verbinden, UTide mit 68 Konstituenten. Klasse B.

Usage: python3 py/dmi_tidevand.py --laden [--jahre 2026,2027]
       python3 py/dmi_tidevand.py --pruefen [--land Greenland]
       python3 py/dmi_tidevand.py --schreiben [--land Greenland]
"""
from __future__ import annotations

import collections
import csv
import datetime as dt
import os
import re
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from health_check import ROOT, curve_diff, km, load_records          # noqa: E402

BASIS = 'https://ocean.dmi.dk/Tides'
UA = 'oliver-weather-tides/1.0 (private tide research; oliver.k73@gmail.com)'
ABLAGE = os.path.join(ROOT, 'tide_tables', 'dmi')
ZIEL = os.path.join(ROOT, 'harmonics/utide/harmonics_utide_tidetables.txt')
PROBE = os.path.join(ROOT, 'harmonics/help/dmi_tidevand_probe.csv')


def hole(url):
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=90) as r:
        d = r.read()
    time.sleep(1.0)
    return d


def laden(jahre):
    for jahr in jahre:
        ziel = os.path.join(ABLAGE, str(jahr))
        os.makedirs(ziel, exist_ok=True)
        liste = hole(f'{BASIS}/{jahr}/').decode('utf-8', errors='replace')
        namen = sorted(set(re.findall(r'href="([^"/]+\.t\.txt)"', liste)))
        print(f'{jahr}: {len(namen)} Tafeln', flush=True)
        for n in namen:
            pfad = os.path.join(ziel, urllib.request.url2pathname(n))
            if os.path.exists(pfad) and os.path.getsize(pfad) > 0:
                continue
            try:
                daten = hole(f'{BASIS}/{jahr}/{n}')
            except Exception as e:
                print(f'  {n}: {e}', flush=True)
                continue
            with open(pfad + '.teil', 'wb') as fh:
                fh.write(daten)
            os.replace(pfad + '.teil', pfad)
        print(f'  -> {os.path.relpath(ziel, ROOT)}', flush=True)


def kopf_und_scheitel(pfad):
    """-> (kopf dict, [(datetime UTC, meter)])."""
    kopf, scheitel = {}, []
    stunden = None
    for z in open(pfad, encoding='utf-8', errors='replace'):
        if z.startswith('#'):
            m = re.match(r'#\s*([A-Za-z. ]+?):\s*(.*)$', z.rstrip())
            if m:
                kopf[m.group(1).strip()] = m.group(2).strip()
            continue
        p = z.split()
        if len(p) == 2 and re.fullmatch(r'\d{12}', p[0]):
            if stunden is None:
                zm = re.search(r'UTC\s*([+-])\s*(\d+(?:\.\d+)?)\s*hour', kopf.get('Time Zone', ''))
                stunden = (float(zm.group(2)) * (1 if zm.group(1) == '+' else -1)) if zm else 0.0
            ortszeit = dt.datetime.strptime(p[0], '%Y%m%d%H%M')
            scheitel.append((ortszeit - dt.timedelta(hours=stunden), float(p[1]) / 100.0))
    for feld in ('Latitude', 'Longitude'):
        m = re.search(r'=\s*(-?\d+(?:\.\d+)?)', kopf.get(feld, ''))
        kopf[feld.lower()] = float(m.group(1)) if m else None
    kopf['utc_stunden'] = stunden
    return kopf, scheitel


def stationen(land):
    """-> {Ort: (kopf, scheitel ueber alle Jahrgaenge)} eines Landes."""
    out = {}
    if not os.path.isdir(ABLAGE):
        return out
    for jahr in sorted(os.listdir(ABLAGE)):
        verz = os.path.join(ABLAGE, jahr)
        for f in sorted(os.listdir(verz)):
            if not f.endswith('.t.txt'):
                continue
            kopf, sch = kopf_und_scheitel(os.path.join(verz, f))
            if land and kopf.get('Country', '') != land:
                continue
            name = kopf.get('Station') or f[:-6]
            if name in out:
                out[name] = (out[name][0], out[name][1] + sch)
            else:
                out[name] = (kopf, sch)
    return out


def fit(scheitel, lat):
    import numpy as np
    import utide
    from batch_utide_uk_tidetimes import CONSTIT_67, cosine_interpolate
    t, v = cosine_interpolate(sorted(set(scheitel)))
    if t is None:
        return None
    coef = utide.solve(t, v, lat=lat, nodal=True, trend=False, method='ols',
                       conf_int='none', verbose=False, constit=CONSTIT_67)
    rec = utide.reconstruct(t, coef, verbose=False)
    resid = v - rec['h']
    return dict(coef=coef, t=t, v=v, rms=float(np.sqrt(np.mean(resid ** 2))),
                r2=1 - float(np.sum(resid ** 2)) / float(np.sum((v - v.mean()) ** 2)),
                z0=float(np.mean(v)))


def werte_aus(coef):
    from add_uhslc_harmonics import find_xtide_match
    from utide._ut_constants import ut_constants
    tab = ut_constants['const']
    unamen = [n.strip() for n in tab.name]
    werte = {}
    for i, u in enumerate(coef['name']):
        u = u.strip()
        if u in unamen:
            xt, _ = find_xtide_match(u, tab.freq[unamen.index(u)] * 360.0)
            if xt:
                werte[xt] = (float(coef['A'][i]), float(coef['g'][i]) % 360.0)
    return werte


def als_satz(name, kopf, werte, f, land):
    """Satz im Bestandsformat -- mit z-Vektor fuer curve_diff."""
    import cmath
    import math
    from health_check import MAIN
    z = {c: cmath.rect(werte.get(c, (0.0, 0.0))[0], -math.radians(werte.get(c, (0.0, 0.0))[1])) for c in MAIN}
    return dict(name=name, lat=kopf['latitude'], lon=kopf['longitude'], z=z,
                tot=sum(abs(z[c]) for c in MAIN), werte=werte, fit=f, kopf=kopf)


def satzname(ort, land):
    land_en = {'Greenland': 'Greenland', 'Faroe Islands': 'Faroe Islands', 'Denmark': 'Denmark'}.get(land, land)
    return f'{ort}, {land_en}'


def main(argv):
    land = argv[argv.index('--land') + 1] if '--land' in argv else 'Greenland'
    if '--laden' in argv:
        jahre = [int(j) for j in (argv[argv.index('--jahre') + 1] if '--jahre' in argv else '2026,2027').split(',')]
        laden(jahre)
        return 0
    st = stationen(land)
    print(f'{len(st)} DMI-Stationen in {land}', flush=True)
    recs = [r for r in load_records() if r['lat'] is not None and not r['current']]
    import noaa_pruefstand as P
    zeilen, saetze = [], []
    for ort, (kopf, sch) in sorted(st.items()):
        if kopf.get('latitude') is None or len(sch) < 600:
            continue
        f = fit(sch, kopf['latitude'])
        if not f:
            continue
        werte = werte_aus(f['coef'])
        s = als_satz(satzname(ort, land), kopf, werte, f, land)
        nah = sorted(((km(s, r), r) for r in recs if abs(r['lat'] - s['lat']) < 1 and abs(r['lon'] - s['lon']) < 3),
                     key=lambda p: p[0])[:3]
        vergleich = '; '.join(f"{r['name'][:30]} [{P.klasse(r) or 'U'}] {d:.1f} km {curve_diff(s, r)[1] * 100:.0f}%"
                              for d, r in nah)
        a_nah = min((d for d, r in nah if P.klasse(r) == 'A'), default=None)
        # Doppelt neben gutem Satz? Dann nicht anlegen. Uebertragungen daneben
        # kommen auf die Loeschliste (Freigabe durch Oliver).
        s['doppelt'] = next((r['name'] for d, r in nah if d <= 3.0 and P.klasse(r) == 'A'
                             and curve_diff(s, r)[1] <= 0.10), None)
        s['uebertragungen'] = [(r, d, curve_diff(s, r)[1]) for d, r in nah if d <= 3.0 and P.klasse(r) is None]
        zeilen.append(dict(ort=ort, lat=f"{s['lat']:.4f}", lon=f"{s['lon']:.4f}",
                           zeitzone=kopf.get('Time Zone', ''), messreihe=kopf.get('Data series', ''),
                           scheitel=len(sch), r2=round(f['r2'], 4), rms_cm=round(f['rms'] * 100, 1),
                           m2=round(werte.get('M2', (0, 0))[0], 3),
                           naechster_a_km='' if a_nah is None else round(a_nah, 1),
                           nachbarn=vergleich))
        saetze.append(s)
        print(f"  {ort[:28]:28} r2 {f['r2']:.4f}  M2 {werte.get('M2', (0, 0))[0]:.3f} m  | {vergleich[:80]}", flush=True)
    with open(PROBE, 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=['ort', 'lat', 'lon', 'zeitzone', 'messreihe', 'scheitel', 'r2',
                                           'rms_cm', 'm2', 'naechster_a_km', 'nachbarn'])
        w.writeheader()
        w.writerows(zeilen)
    print(f'\n{len(zeilen)} gefittet -> {os.path.relpath(PROBE, ROOT)}')
    if '--schreiben' not in argv:
        print('(nur Probe; mit --schreiben werden die Saetze angelegt)')
        return 0
    neu = [x for x in saetze if not x['doppelt']]
    print(f"{len(saetze) - len(neu)} uebersprungen (Klasse-A-Satz daneben stimmt), {len(neu)} anzulegen")
    loeschliste(neu)
    return schreiben(neu, land)


def loeschliste(saetze):
    """Uebertragungen neben neuen DMI-Saetzen -> Loeschvorschlag (nicht ausfuehren)."""
    aus = os.path.join(ROOT, 'harmonics/help/loeschen_dmi_groenland_vorschlag.csv')
    with open(aus, 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=['datei', 'name', 'fehler_prozent', 'begruendung'])
        w.writeheader()
        n = 0
        for s in saetze:
            for r, d, diff in s['uebertragungen']:
                w.writerow(dict(datei=r['file'], name=r['name'], fehler_prozent=round(diff * 100, 1),
                                begruendung=(f"Uebertragung {d:.1f} km neben der amtlichen DMI-Tafel "
                                             f"\"{s['name']}\" (Konstanten aus Pegelreihe "
                                             f"{s['kopf'].get('Data series', '?')}); Kurvenunterschied "
                                             f"{diff * 100:.0f} %.")))
                n += 1
    print(f'{n} Uebertragungen auf der Loeschliste (nur Vorschlag) -> {os.path.relpath(aus, ROOT)}')


def schreiben(saetze, land):
    import sicher_schreiben
    from add_uhslc_harmonics import CONSTITUENTS_175
    text = open(ZIEL, encoding='iso-8859-1').read()
    neu = []
    for s in saetze:
        if s['name'] in text:
            print(f"  schon vorhanden: {s['name']}")
            continue
        k, f, w = s['kopf'], s['fit'], s['werte']
        n_ana = sum(1 for cn, _ in CONSTITUENTS_175 if cn in w)
        L = ['#', f"# {s['name']}", '# BEGIN HOT COMMENTS', f'# country: {land}',
             '# source: DMI tide tables (ocean.dmi.dk/Tides) with UTide',
             f"# station_id_context: DMI-{k.get('Stat. number', '')}",
             f'# date_imported: {dt.datetime.now():%Y%m%d}',
             '# datum: Lowest Astronomical Tide (LAT)',
             '# confidence: 6',
             f"# utide: pts={len(f['t'])} period={f['t'][0]:%Y-%m-%d}..{f['t'][-1]:%Y-%m-%d} "
             f"r2={f['r2']:.4f} rms={f['rms']:.4f}m const={n_ana}",
             f"# note: DMI-Tafel; Konstanten des DMI aus Pegelreihe {k.get('Data series', '?')}.",
             f"# note: Zeitzone der Tafel {k.get('Time Zone', '?')}, nach UTC umgerechnet.",
             '# !units: meters', f"# !longitude: {s['lon']:.4f}", f"# !latitude: {s['lat']:.4f}",
             s['name'], '+00:00 :America/Nuuk' if land == 'Greenland' else '+00:00 :UTC',
             f"{f['z0']:.4f} meters"]
        for cn, _sp in CONSTITUENTS_175:
            L.append(f'{cn:15s} {w[cn][0]:.4f}  {w[cn][1]:.2f}' if cn in w and w[cn][0] >= 0.00005 else 'x 0 0')
        neu.extend(L)
    if neu:
        sicher_schreiben.schreiben(ZIEL, text.rstrip('\n') + '\n' + '\n'.join(neu) + '\n')
    print(f'{sum(1 for z in neu if z.startswith("# BEGIN HOT"))} Saetze geschrieben')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
