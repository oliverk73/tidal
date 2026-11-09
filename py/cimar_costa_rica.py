#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Costa Rica: Tidenkalender 2026 des UCR-CIMAR (Modulo de Informacion Oceanografica) lesen und pruefen (9.11.2026).

Quelle: tide_tables/costa_rica/Tabla_Mareas_<Ort>_2026.pdf (LaTeX, Text auslesbar), HW/NW, Ortszeit UTC-6,
Bezug "promedio de las mareas bajas" (>= 20 Jahre). Je Seite drei Monate, je Monat zwei Spalten (1.-16., 17.-31.).
Gelesen ueber pdftotext -bbox: jede Uhrzeit, rechts daneben die Hoehe; Tag = letzte Tageszahl links darueber.

BEFUND 9.11.2026 -- nichts uebernommen:
- Alle acht Pazifik-Tafeln sind Uebertragungen von Puntarenas: feste Zeitdifferenz je HW/NW, fester Hubfaktor,
  Streuung 0 (Culebra/Santa Elena -2 min x1,00, Herradura -6/-1, Golfito -13/+2 x1,03, Quepos -13/-4 x0,91,
  Uvita -25/-20 x1,00, Isla del Coco -25 x0,93). Eigene Information nur in Puntarenas (trifft TICON 3 %, 3 min).
- Unsere Messsaetze schlagen die Uebertragungen: Marina Papagayo, Cuajiniquil, Flamingo 23-27 % kleiner als die
  Culebra/Santa-Elena-Tafel (SINAMOT Nacascolo bestaetigt die Messung, Hub 0,97); Herradura 13 %, Coco 12 %/16 min.
- NOAA "Golfo Elena" und "Bahia Uvita" sind dieselben Puntarenas-Uebertragungen (gegen die Tafel 0,3 cm, 0 min):
  M2 28 % bzw. 12 % zu gross -> FES geeicht (harmonics/help/fes_ersetzen_20261109_costa_rica.csv), NOAA archiviert.
- Limon (Karibik, Mikrotide): Tafel selbst mit vertauschten Zeiten, unbrauchbar.
SINAMOT (UNA, "Mareas <Ort> 2026.pdf", Fuss, Ortszeit): eigene Vorhersagen, Puntarenas/Nacascolo bestaetigen den
Bestand (Kurve 2 %/4 %). Rincon de Osa (kein Satz): Tafelfit M2 1,03@237 gegen Golfito-Messung 1,10@247 und FES im
ganzen Golfo Dulce 1,11@245 -- 8 % kleiner, 20 min frueher, nicht uebernommen.

SINAMOT-Webdienst (Oliver 9.11.2026, sinamot.una.ac.cr -> Predicciones de Marea): unacostasegura.una.ac.cr/webServices/
mareas_detalle.php?id=..&cod=..&fecha_inicio=..&fecha_final=.. liefert HW/NW (m, Ortszeit) fuer frei waehlbare Zeitraeume;
Cache water_levels/Costa_Rica_SINAMOT/<cod>_2026.html. Tafelfit gegen unsere Messsaetze: Puntarenas 2 %, Quepos 1 %,
Nacascolo/Papagayo 4 %; Isla del Coco 14 % (K1 0,03 statt 0,09) und Rincon de Osa 9 % daneben. Hoehenbezug der Webtafel
weicht von den PDF-Tafeln ab (Puntarenas Z0 2,31 gegen 1,41 m) -> Z0 wie bei FES = -Minimum der 19-Jahres-Kurve.
Eingetragen nur TAMBOR (Bahia Ballena, kein Satz in 35 km): M2 0,965@241 gegen FES 0,972@244. Moin liegt 6 km neben
Limon (Messung, Mikrotide) -> nicht noetig.

Usage: venv/bin/python py/cimar_costa_rica.py [--sinamot [--schreiben]]
"""
import datetime as dt
import glob
import html
import os
import re
import subprocess
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QUELLE = os.path.join(ROOT, 'tide_tables/costa_rica')
MONATE = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 'Julio', 'Agosto', 'Septiembre', 'Octubre',
          'Noviembre', 'Diciembre']
WORT = re.compile(r'<word xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">([^<]*)</word>')
UTC_VERSATZ_H = -6


def woerter(pdf, seite):
    out = subprocess.run(['pdftotext', '-bbox', '-f', str(seite), '-l', str(seite), pdf, '-'],
                         capture_output=True, text=True).stdout
    return [(float(a), float(b), float(c), float(d), html.unescape(w)) for a, b, c, d, w in WORT.findall(out)]


def lesen(pdf, jahr=2026):
    """-> (Ereignisse [(datetime UTC, Hoehe m)], Kopf {name, lat, lon})."""
    kopf, ev = {}, []
    seiten = int(re.search(r'Pages:\s+(\d+)', subprocess.run(['pdfinfo', pdf], capture_output=True, text=True).stdout)[1])
    for s in range(1, seiten + 1):
        w = woerter(pdf, s)
        txt = ' '.join(x[4] for x in w)
        m = re.search(r'Latitud\s+(-?[\d.]+)°([NS]),\s+Longitud\s+(-?[\d.]+)°W', txt)
        if m and not kopf:
            la = float(m[1]) * (1 if m[2] == 'N' else -1)
            lo = -abs(float(m[3]))
            kopf = dict(lat=la, lon=lo, name=re.split(r'\s+Latitud', txt)[0].strip())
        koepfe = [(x[0], MONATE.index(x[4]) + 1) for x in w if x[4] in MONATE]
        if not koepfe:
            continue
        zeiten = [x for x in w if re.fullmatch(r'\d\d:\d\d', x[4])]
        hoehen = [x for x in w if re.fullmatch(r'-?\d+\.\d\d', x[4])]
        tage = [x for x in w if re.fullmatch(r'\d\d', x[4]) and 1 <= int(x[4]) <= 31]
        for tx, ty, txe, tye, tw in zeiten:
            hs = [h for h in hoehen if abs(h[1] - ty) < 1.0 and 0 < h[0] - txe < 40]
            if not hs:
                raise ValueError(f'{pdf} S.{s}: keine Hoehe zu {tw} bei x={tx:.0f} y={ty:.0f}')
            hoehe = float(min(hs, key=lambda h: h[0])[4])
            ds = [d for d in tage if 8 < tx - d[2] < 30 and d[1] <= ty + 3.5]
            if not ds:
                raise ValueError(f'{pdf} S.{s}: kein Tag zu {tw} bei x={tx:.0f} y={ty:.0f}')
            tag = int(max(ds, key=lambda d: d[1])[4])
            monat = min(koepfe, key=lambda k: abs(k[0] - (tx + 20)))[1]
            hh, mm = map(int, tw.split(':'))
            t = dt.datetime(jahr, monat, tag, hh, mm, tzinfo=dt.timezone.utc) - dt.timedelta(hours=UTC_VERSATZ_H)
            ev.append((t, hoehe))
    ev.sort()
    return ev, kopf


def pruefen(ev):
    """Plausibilitaet: Abstaende 2-9 h (Tagestide bis 15 h), HW/NW im Wechsel."""
    t = np.array([e[0].timestamp() for e in ev]) / 3600
    h = np.array([e[1] for e in ev])
    d = np.diff(t)
    wechsel = np.sign(np.diff(h))
    nicht = int((wechsel[1:] == wechsel[:-1]).sum())
    return dict(n=len(ev), min_h=round(float(d.min()), 2), max_h=round(float(d.max()), 2), kein_wechsel=nicht,
                tage=len({e[0].date() for e in ev}))


SINAMOT_URL = ('https://unacostasegura.una.ac.cr/webServices/mareas_detalle.php?id=%s&cod=%s&estacion=%s'
               '&fecha_inicio=2026-01-01&fecha_final=2026-12-31')
SINAMOT_CACHE = os.path.join(ROOT, 'water_levels/Costa_Rica_SINAMOT')
# cod -> (id, Webname, Satzname, Breite, Laenge, Provinz); Position Tambor: Wasser vor dem Muelle (osm_land, 0,15 km)
SINAMOT_NEU = {'926': ('12', 'Tambor', 'Tambor (Bahía Ballena), Puntarenas, Costa Rica', 9.7150, -85.0150, 'Puntarenas')}
ZIEL = os.path.join(ROOT, 'harmonics/utide/harmonics_utide_tidetables.txt')


def sinamot_lesen(cod, ident, web):
    import urllib.request
    pfad = os.path.join(SINAMOT_CACHE, '%s_2026.html' % cod)
    if not os.path.exists(pfad):
        os.makedirs(SINAMOT_CACHE, exist_ok=True)
        req = urllib.request.Request(SINAMOT_URL % (ident, cod, web), headers={'User-Agent': 'Mozilla/5.0'})
        open(pfad, 'wb').write(urllib.request.urlopen(req, timeout=180).read())
    t = open(pfad, encoding='utf-8').read()
    ev, tag = [], None
    for m in re.finditer(r'(\d\d-\d\d-\d{4})|<td>(\d\d:\d\d)</td>\s*<td><strong>(-?[\d.]+) m</strong>', t):
        if m[1]:
            tag = m[1]
            continue
        ev.append((dt.datetime.strptime(tag + ' ' + m[2], '%d-%m-%Y %H:%M').replace(tzinfo=dt.timezone.utc)
                   - dt.timedelta(hours=UTC_VERSATZ_H), float(m[3])))
    return np.array([e[0].timestamp() for e in ev]), np.array([e[1] for e in ev])


def sinamot(argv):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import health_check as H
    import qld_msq_fit as Q
    import scheitelfit as SF
    import xtide_modell as X
    from sicher_schreiben import schreiben
    kopf = X.kopf_lesen(ZIEL)
    namen, speeds, arg, fak = kopf
    nutz = Q.rayleigh(SF.konstituenten(namen, SF.CONSTIT_67), speeds, namen, 365)
    heute = dt.date.today().strftime('%Y%m%d')
    tg = np.arange(dt.datetime(2008, 1, 1).timestamp(), dt.datetime(2027, 1, 1).timestamp(), 3600.0)
    bestand = [r for r in H.load_records() if r['lat'] and not r['current']]
    neu = []
    for cod, (ident, web, name, la, lo, prov) in SINAMOT_NEU.items():
        t, h = sinamot_lesen(cod, ident, web)
        z_tafel, w = SF.fit(t, h, nutz, speeds, arg, fak)
        rms, tf, _ = SF.guete(t, h, z_tafel, w, kopf, versatz=False)
        z0 = -float(SF.hoehe_und_ableitungen(tg, 0.0, w, kopf)[0].min())
        nb = min(bestand, key=lambda r: H.km({'lat': la, 'lon': lo}, r))
        print('%-36s %d Scheitel, Fit %.1f cm %.0f min, M2 %.3f@%.1f K1 %.3f@%.1f Z0 %.2f | %s %.0f km Kurve %.0f%%' % (
            name, len(t), rms * 100, tf, *w['M2'], *w['K1'], z0, nb['name'][:30], H.km({'lat': la, 'lon': lo}, nb),
            100 * H.curve_diff(Q.rec(w), nb)[1]))
        blk = ['#', '# %s' % name, '# BEGIN HOT COMMENTS', '# country: Costa Rica',
               '# source: SINAMOT/UNA tide predictions (unacostasegura.una.ac.cr), fit to table',
               '# station_id_context: SINAMOT-%s' % cod, '# date_imported: %s' % heute,
               '# datum: approx. LAT (Z0 = -Minimum der 19-Jahres-Kurve)', '# confidence: 6',
               '# note: %s Scheitelfit an SINAMOT-HW/NW 2026 (py/cimar_costa_rica.py --sinamot), %d Scheitel, %.1f cm / %.0f min.' % (
                   heute, len(t), rms * 100, tf),
               '# note: Keine Messreihe; SINAMOT trifft Messsaetze Puntarenas/Quepos/Papagayo 1-4 %, FES hier M2 1 %, 5 min.',
               '# !units: meters', '# !longitude: %.4f' % lo, '# !latitude: %.4f' % la, '# province: %s' % prov,
               name, '+00:00 :America/Costa_Rica', '%.4f meters' % z0]
        blk += ['%-15s %.4f  %.2f' % (c, *w[c]) if c in w and w[c][0] >= 0.00005 else 'x 0 0' for c in namen]
        neu.append((name, blk))
    if '--schreiben' in argv:
        L = open(ZIEL, encoding='iso-8859-1').read().rstrip('\n').split('\n')     # frisch lesen, nur anhaengen
        for name, blk in neu:
            if name in L:
                print('   existiert schon:', name)
                continue
            L += blk
        for z in L:
            z.encode('iso-8859-1')
        schreiben(ZIEL, '\n'.join(L) + '\n')
        print('->', os.path.relpath(ZIEL, ROOT), len(neu), 'Saetze')
    return 0


def main(argv):
    if '--sinamot' in argv:
        return sinamot(argv)
    for pdf in sorted(glob.glob(os.path.join(QUELLE, 'Tabla_Mareas_*_2026.pdf'))):
        ev, kopf = lesen(pdf)
        print('%-22s %-45s %7.3f %8.3f %s' % (os.path.basename(pdf)[13:-9], kopf.get('name', '')[:45], kopf['lat'],
                                            kopf['lon'], pruefen(ev)))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
