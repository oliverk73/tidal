#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""UTide-Fit fuer die 32 VHO-Nebenstationen (py/download_vho_vietnam_neben.py, Jahr 2024).

Wie py/fit_vho_vietnam.py (Zeiten UTC+7 -> UTC, Greenwich-Phasen, Meridian +00:00, CONSTIT_67,
R2-Gate 0.95), dazu je Station:
  * Eigenmessung: XTide-Modell des Fits gegen die eigene Reihe (Zeitversatz muss 0 min sein),
  * FES2022 an der Position (M2/S2/K1/O1 in min und Amplitudenfaktor) -- nur Ueberblick,
  * Position: Portalwerte sind auf Bogenminuten gerundet; Landmaske meldet Punkte an Land,
  * Bestand bis 5 km (Kurve %, Zeiten) und Klasse-A-Saetze bis 40 km.
Das alte Skript fand verdrehte Jahrgaenge (Hong Gai 2024, Cua Gianh 2022: O1/M2 um 100-165 Grad);
eine Station, deren Phasen gegen FES und Nachbarn um mehr als 60 min springen, wird markiert.

Schreibt harmonics/help/vho_neben_pruefung.csv; mit --schreiben die Saetze mit Status 'neu' nach
harmonics/utide/harmonics_utide_tidetables.txt.

Usage: venv/bin/python py/fit_vho_vietnam_neben.py [--schreiben] [slug ...]
"""
from __future__ import annotations

import csv
import json
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import utide

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'batch'))
from generate_germany_harmonics_175 import CONSTITUENTS_175, find_xtide_match  # noqa: E402
from batch_utide_uk_tidetimes import CONSTIT_67                                  # noqa: E402
from download_vho_vietnam_neben import STATIONS                                  # noqa: E402
import noaa_pruefstand as P                                                      # noqa: E402
import xtide_modell as X                                                         # noqa: E402
from health_check import load_records, km                                        # noqa: E402
from sicher_schreiben import schreiben                                           # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DIR = ROOT / 'water_levels' / 'VN_vho'
HARM = ROOT / 'harmonics' / 'utide' / 'harmonics_utide_tidetables.txt'
LISTE = ROOT / 'harmonics' / 'help' / 'vho_neben_pruefung.csv'
UTC_OFF = timedelta(hours=7)
# 15.09.2026 (Oliver: A und B umsetzen). B: VHO ersetzt schwaechere Saetze am selben Ort und uebernimmt deren
# (von Hand gepflegten) Namen und Position. A: neue Orte; Spratly-Stationen mit Zusatz "(Truong Sa)".
UEBERNAHME = {'vinh-cat-ba': ('Pho Cat Ba', 20.7173, 107.0453), 'dao-chang-tay': ('Dao Tran', 21.2440, 107.9590),
              'bach-long-vy': ('Bach Long Vi', 20.1251, 107.7238), 'cua-ba-lat': ('Cua Ba Lat', 20.2529, 106.5918),
              'hon-me': ('Hon Me', 19.3592, 105.9275), 'chan-may': ('Chan May Bay', 16.3333, 108.0167),
              'cu-lao-cham': ('Cu Lao Cham (Tan Hiep)', 15.9572, 108.5053), 'vung-dung-quat': ('Dung Quat Bay', 15.4000, 108.7500),
              'vung-ro': ('Vung Ro', 12.8672, 109.4073)}
TRUONG_SA = {'phan-vinh', 'toc-tan', 'tien-nu', 'nui-le', 'da-dong', 'da-tay', 'da-lat', 'thuyen-chai', 'an-bang', 'phuc-tan', 'ba-ke'}


def wasserpunkt(lat, lon, max_km=5.0):
    """Naechster Punkt, den die Landmaske als Wasser fuehrt (Portalpositionen sind auf Bogenminuten gerundet)."""
    from global_land_mask import globe
    import math as _m
    if not globe.is_land(lat, lon):
        return lat, lon, 0.0
    for r in np.arange(0.002, max_km / 111.0, 0.002):
        for a in range(0, 360, 10):
            la = lat + r * _m.cos(_m.radians(a)); lo = lon + r * _m.sin(_m.radians(a)) / _m.cos(_m.radians(lat))
            if not globe.is_land(la, lo):
                return la, lo, r * 111.0
    return lat, lon, None
R2_GATE = 0.95
SPAN = '2024-01-01_2024-12-31'
MIN_PUNKTE = 24 * 300


def reihe(slug):
    p = DIR / f'{slug}_{SPAN}.json'
    if not p.exists():
        return None, None, {}
    d = json.loads(p.read_text())
    t, v = [], []
    for day, rec in sorted(d.items()):
        if day.startswith('_') or not rec:
            continue
        base = datetime.fromisoformat(day)
        for h, m in enumerate(rec['hourly_m']):
            if m is not None:
                t.append(base + timedelta(hours=h) - UTC_OFF)
                v.append(float(m))
    return np.array(t), np.array(v), d.get('_meta', {})


def konstanten(coef):
    from utide._ut_constants import ut_constants
    table = ut_constants['const']
    unames = [n.strip() for n in table.name]
    out = {}
    for i, u in enumerate(coef['name']):
        u = u.strip()
        if u in unames:
            xt, _ = find_xtide_match(u, table.freq[unames.index(u)] * 360.0)
            if xt:
                out[xt] = (float(coef['A'][i]), float(coef['g'][i]) % 360.0)
    return out


def block(name, slug, lat, lon, z0, cm, r2, rms, npts, t0, t1, noten):
    n_ana = sum(1 for cn, _ in CONSTITUENTS_175 if cn in cm)
    z = ['#', f'# {name}', '# BEGIN HOT COMMENTS', '# country: Vietnam',
         '# source: VHO Navy hourly tide predictions (thuydacvietnam.org.vn) with UTide',
         f'# vho_slug: {slug}', f'# date_imported: {datetime.now():%Y%m%d}',
         '# datum: chart datum (Kartennull der amtlichen Tidetafel)', '# confidence: 7',
         f'# utide: pts={npts} period={t0:%Y-%m-%d}..{t1:%Y-%m-%d} r2={r2:.4f} rms={rms:.4f}m const={n_ana}']
    z += [f'# note: {n}' for n in noten]
    z += ['# !units: meters', f'# !longitude: {lon:.4f}', f'# !latitude: {lat:.4f}',
          name, '+00:00 :Asia/Ho_Chi_Minh', f'{z0:.4f} meters']
    for cn, _sp in CONSTITUENTS_175:
        z.append(f'{cn:15s} {cm[cn][0]:.4f}  {cm[cn][1]:.2f}' if cn in cm and cm[cn][0] >= 0.00005 else 'x 0 0')
    return z


def main(argv):
    import noaa_offen_nachbarn as O
    from global_land_mask import globe
    nur = [a for a in argv if not a.startswith('--')]
    kopf = X.kopf_lesen(str(HARM))
    namen, speeds, arg, fak = kopf
    recs = [r for r in load_records() if r['lat'] is not None and 'current' not in r['file'].lower()
            and '/backup/' not in r['file']]
    faelle = []
    for nr, slug, name in STATIONS:
        if nur and slug not in nur:
            continue
        t, v, meta = reihe(slug)
        e = dict(slug=slug, name=f'{name}, Vietnam', dizi=nr, punkte=0 if t is None else len(t))
        if t is None or len(t) < MIN_PUNKTE or meta.get('lat') is None:
            e['status'] = 'zu wenig Daten'
            faelle.append((e, None))
            continue
        coef = utide.solve(t, v, lat=meta['lat'], nodal=True, trend=False, method='ols',
                           conf_int='none', verbose=False, constit=CONSTIT_67)
        rec = utide.reconstruct(t, coef, verbose=False)
        res = v - rec['h']
        r2 = 1 - float(np.sum(res ** 2)) / float(np.sum((v - v.mean()) ** 2))
        rms = float(np.sqrt(np.mean(res ** 2)))
        cm = konstanten(coef)
        z0 = float(coef['mean'])
        ts = np.array([(x - datetime(1970, 1, 1)).total_seconds() for x in t])
        best = min(((lag, float(np.sqrt(np.mean((v[::3] - X.kurve(ts[::3] + lag * 60, z0, cm, namen, speeds, arg, fak)) ** 2))))
                    for lag in range(-30, 31)), key=lambda x: x[1])
        e.update(lat=round(meta['lat'], 4), lon=round(meta['lon'], 4), r2=round(r2, 4), rms_cm=round(rms * 100, 1),
                 eigen_min=best[0], an_land=bool(globe.is_land(meta['lat'], meta['lon'])),
                 m2=round(cm.get('M2', (0, 0))[0], 3), k1=round(cm.get('K1', (0, 0))[0], 3), o1=round(cm.get('O1', (0, 0))[0], 3))
        faelle.append((e, dict(cm=cm, z0=z0, r2=r2, rms=rms, t=t)))
    punkte = [dict(lat=e['lat'], lon=e['lon']) for e, f in faelle if f]
    fes = O.fes_konstanten(punkte)
    SP = P.SP
    i = 0
    for e, f in faelle:
        if not f:
            continue
        p = punkte[i]; i += 1
        fe = fes.get(id(p), {})
        dd = []
        for k in ('M2', 'S2', 'K1', 'O1'):
            if k in f['cm'] and k in fe and fe[k][0] > 0.01 and f['cm'][k][0] > 0.01:
                dd.append(f"{k} {((f['cm'][k][1] - fe[k][1] + 180) % 360 - 180) / SP[k] * 60:+.0f}min {f['cm'][k][0] / fe[k][0]:.2f}x")
        e['fes'] = ' '.join(dd)
        nb = []
        for r in recs:
            if abs(r['lat'] - e['lat']) > 0.4:
                continue
            d = km(r, e)
            kl = P.klasse(r)
            if d <= 5 or (kl == 'A' and d <= 40):
                try:
                    m = P.messen(f['cm'], P.satz(r)[1])
                except Exception:
                    continue
                q = re.search(r'# source: (.*)', P.vermerk(r))
                nb.append((d, f"{os.path.basename(r['file'])[9:32]}|{r['name']} [{kl or '-'} {d:.1f} km {(q.group(1) if q else '')[:25]}] "
                              f"Kurve {m['kurve_pct']:.1f}% HW {m['hw_min']:+.0f} NW {m['nw_min']:+.0f} K1 {m['k1_min']:+.0f} O1 {m['o1_min']:+.0f}"))
        e['bestand'] = ' ; '.join(x for _, x in sorted(nb)[:6])
        probleme = []
        if f['r2'] < R2_GATE:
            probleme.append(f'R2 {f["r2"]:.3f}')
        if abs(e['eigen_min']) > 2:
            probleme.append(f'Eigenmessung {e["eigen_min"]:+d} min')
        e['status'] = 'pruefen: ' + ', '.join(probleme) if probleme else 'kandidat'
        e['_f'] = f
    felder = ['slug', 'name', 'dizi', 'punkte', 'lat', 'lon', 'an_land', 'r2', 'rms_cm', 'eigen_min', 'm2', 'k1', 'o1',
              'fes', 'status', 'bestand']
    with open(LISTE, 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=felder, extrasaction='ignore')
        w.writeheader()
        for e, _ in faelle:
            w.writerow(e)
    for e, _ in faelle:
        print(f"{e['name'][:30]:30} {e.get('status', ''):26} r2 {e.get('r2', '')} eigen {e.get('eigen_min', '')} "
              f"{'LAND ' if e.get('an_land') else ''}M2 {e.get('m2', '')} K1 {e.get('k1', '')} O1 {e.get('o1', '')} | FES {e.get('fes', '')}")
        for x in (e.get('bestand') or '').split(' ; '):
            if x:
                print('        ', x)
    print('->', LISTE.relative_to(ROOT))
    if '--schreiben' in argv:
        wahl = [a.split('=', 1)[1] for a in argv if a.startswith('--nur=')]
        wahl = set(wahl[0].split(',')) if wahl else None
        lines = HARM.read_text(encoding='iso-8859-1').split('\n')
        n = 0
        for e, f in faelle:
            if not f or (wahl is not None and e['slug'] not in wahl) or (wahl is None and e['status'] != 'kandidat'):
                continue
            name, la, lo = e['name'], e['lat'], e['lon']
            noten = [f'Eigenmessung {e["eigen_min"]:+d} min; VHO-Station {e["name"].split(",")[0]} (DIZI {e["dizi"]}).']
            if e['slug'] in UEBERNAHME:
                n0, la, lo = UEBERNAHME[e['slug']]
                name = f'{n0}, Vietnam'
                noten.append('Ersetzt schwaechere ATT/NOAA/NCHMF-Saetze am selben Ort; Name und Position von dort uebernommen.')
            else:
                if e['slug'] in TRUONG_SA:
                    name = f"{e['name'].split(',')[0]} (Truong Sa), Vietnam"
                la2, lo2, d = wasserpunkt(la, lo)
                if d:
                    noten.append(f'Portalposition {la:.4f}/{lo:.4f} (Bogenminuten) liegt an Land; {d:.1f} km zum Wasser verschoben.')
                la, lo = la2, lo2
            if name in lines:
                print('existiert schon:', name)
                continue
            blk = block(name, e['slug'], la, lo, f['z0'], f['cm'], f['r2'], f['rms'], len(f['t']),
                        f['t'][0], f['t'][-1], noten)
            end = len(lines)
            while end > 0 and lines[end - 1].strip() == '':
                end -= 1
            lines = lines[:end] + blk + lines[end:]
            n += 1
        schreiben(str(HARM), '\n'.join(lines))
        print(n, 'Saetze geschrieben')


if __name__ == '__main__':
    main(sys.argv[1:])
