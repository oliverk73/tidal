#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Norwegische Luecken aus dem BSH-Abgleich (py/bsh_gt_abgleich.py, 13.11.2026) mit Kartverket-Fits fuellen (Oliver: "Ja").

Je Ort: Position = Hafen/Anleger/Faehrterminal (Overpass, <= 2 km um den OSM-Ort), sonst der OSM-Ort selbst;
zwei Jahre (2026-27) stuendliche Kartverket-Punktvorhersage dort, Fit wie py/kartverket_ersetzen.py
(Rayleigh nach Laenge + SA; Kontrolle der Methode 11.11.: 1,6 cm gegen Messsaetze).
Ausgelassen: 412a "Ulvik (Tjeldsund)" -- Ort am Tjeldsund nicht eindeutig (Nominatim fand Ulvika bei Kjoepsvik).
Neue Saetze -> harmonics/utide/harmonics_utide_tidetables.txt und harmonics/help/neu_pruefen_20261113.csv.

Usage: venv/bin/python py/kartverket_bsh_luecken.py [--schreiben]
"""
import datetime as dt
import json
import os
import sys
import time
import urllib.parse
import urllib.request

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kartverket_ersetzen as KE                                   # noqa: E402
import qld_msq_fit as Q                                            # noqa: E402
import xtide_modell as X                                           # noqa: E402
from ukho_index_abgleich import km                                 # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ZIEL = KE.ZIEL
NEU = os.path.join(ROOT, 'harmonics/help/neu_pruefen_20261113.csv')
CACHE = os.path.join(ROOT, 'water_levels/kartverket_bsh_luecken.json')
# BSH-Nr., Name im Satz, Nominatim-Suche (Ort, Kommune), Fylke
ORTE = [('370', 'Kvalsund', 'Kvalsund, Hammerfest', 'Finnmark'),
        ('372', 'Neverfjord', 'Neverfjord, Hammerfest', 'Finnmark'),
        ('383a', 'Dåfjord', 'Dåfjord, Karlsøy', 'Troms'),
        ('405', 'Ramberg (Flakstadøya)', 'Ramberg, Flakstad', 'Nordland'),
        ('415', 'Bogen (Ofotfjorden)', 'Bogen, Evenes', 'Nordland'),
        ('434', 'Myken', 'Myken, Rødøy', 'Nordland'),
        ('435a', 'Sleneset', 'Sleneset, Lurøy', 'Nordland'),
        ('451', 'Sistranda (Frøya)', 'Sistranda, Frøya', 'Trøndelag'),
        ('452', 'Titran (Frøya)', 'Titran, Frøya', 'Trøndelag'),
        ('466', 'Torvikbukt', 'Torvikbukt, Gjemnes', 'Møre og Romsdal'),
        ('489', 'Årdalstangen', 'Årdalstangen, Årdal', 'Vestland'),
        ('505', 'Osøyro', 'Osøyro, Bjørnafjorden', 'Vestland'),
        ('522a', 'Forsand (Høgsfjorden)', 'Forsand, Sandnes', 'Rogaland'),
        ('523', 'Lysebotn', 'Lysebotn, Sandnes', 'Rogaland'),
        ('530', 'Lillesand', (58.2490, 8.3779), 'Agder')]  # Nominatim gab 58.116/8.440 (15 km suedlich)


def hole(url, daten=None, pause=1.1):
    c = json.load(open(CACHE)) if os.path.exists(CACHE) else {}
    k = url + '|' + (daten or '')
    if k not in c:
        urls = [url] + (['https://overpass.kumi.systems/api/interpreter'] if 'overpass' in url else [])
        for versuch in range(4):
            time.sleep(pause * (1 + 5 * versuch))
            rq = urllib.request.Request(urls[versuch % len(urls)], data=daten.encode() if daten else None,
                                        headers={'User-Agent': 'weather-tides/1.0'})
            try:
                c[k] = json.load(urllib.request.urlopen(rq, timeout=90))
                break
            except Exception as e:                                  # noqa: BLE001
                print('   Abruf-Fehler', e, flush=True)
        else:
            raise RuntimeError('Abruf gescheitert: ' + url)
        json.dump(c, open(CACHE, 'w'))
    return c[k]


def position(suche):
    if isinstance(suche, tuple):
        r = [dict(lat=suche[0], lon=suche[1])]
    else:
        r = hole('https://nominatim.openstreetmap.org/search?' + urllib.parse.urlencode(
            dict(q=suche + ', Norway', format='jsonv2', limit=1)))
    if not r:
        return None, None, ''
    p = (float(r[0]['lat']), float(r[0]['lon']))
    q = ('[out:json][timeout:30];(node(around:2000,%.5f,%.5f)[harbour];nwr(around:2000,%.5f,%.5f)[man_made=pier];'
         'nwr(around:2000,%.5f,%.5f)[amenity=ferry_terminal];nwr(around:2000,%.5f,%.5f)[leisure=marina];);out center 20;' % (p * 4))
    h = hole('https://overpass-api.de/api/interpreter', 'data=' + urllib.parse.quote(q), pause=2.0)
    if h.get('elements'):
        el = min(h['elements'], key=lambda x: km(p, (x.get('lat') or x['center']['lat'], x.get('lon') or x['center']['lon'])))
        hp = (el.get('lat') or el['center']['lat'], el.get('lon') or el['center']['lon'])
        t = el['tags']
        art = t.get('amenity') or t.get('man_made') or t.get('leisure') or 'harbour'
        return p, hp, ('%s %s' % (art, t.get('name', ''))).strip()
    return p, p, 'Ortspunkt'


def main(argv):
    kopf = X.kopf_lesen(ZIEL)
    namen, speeds, arg, fak = kopf
    heute = dt.date.today().strftime('%Y%m%d')
    T = open(ZIEL, encoding='iso-8859-1').read().rstrip('\n').split('\n')
    neu, liste = [], []
    for nr, name, suche, fylke in ORTE:
        voll = '%s, Norway' % name
        if voll in T:
            print('%-5s %-28s schon im Bestand' % (nr, voll))
            continue
        ort, p, art = position(suche)
        if p is None:
            print('%-5s %-28s nicht gefunden' % (nr, voll))
            continue
        d = KE.abruf(*p)
        if not d or len(d['h']) < 17000:
            print('%-5s %-28s zu wenig Kartverket-Daten' % (nr, voll))
            continue
        s = pd.Series(d['h'], index=pd.to_datetime(d['t'], utc=True))
        tage = (s.index[-1] - s.index[0]).days
        nutz = Q.rayleigh([k for k in namen if k in speeds], speeds, namen, tage)
        if 'SA' not in nutz:
            nutz.insert(0, 'SA')
        _s, _t, z0, w, h, _n = Q.fit(s, nutz, kopf, speeds, arg, fak)
        rms = float(np.sqrt(np.mean((_s.values - h) ** 2)))
        mx = max(a for a, g in w.values())
        if mx > 3 * w['M2'][0] + 0.5 or rms > 0.02:
            print('%-5s %-28s Fit verdaechtig (max %.2f, RMS %.1f cm)' % (nr, voll, mx, 100 * rms))
            continue
        bezug = d['code'] + ((' x ' + d['faktor']) if d['faktor'] and d['faktor'] != '1.00' else '') + \
            ((' %+d min' % int(d['delay'])) if d['delay'] not in ('', '0') else '')
        print('%-5s %-28s %.4f %.4f (%s, %.1f km vom Ort) Bezug %s, Fit %.2f cm, M2 %.3f/%.0f' % (
            nr, voll, p[0], p[1], art, km(ort, p), bezug, 100 * rms, *w['M2']))
        neu += ['#', '# ' + voll, '# BEGIN HOT COMMENTS', '# country: Norway',
                '# source: Kartverket tide predictions (vannstand.kartverket.no)',
                '# date_imported: %s' % heute, '# datum: Chart Datum', '# confidence: 7',
                '# !units: meters', '# !longitude: %.4f' % p[1], '# !latitude: %.4f' % p[0], '# province: %s' % fylke,
                '# note: %s Fit %d Tage Kartverket-Punktvorhersage (%.1f cm), Bezug %s; Position %s'
                % (heute, tage, 100 * rms, bezug, art[:40]),
                '# note: BSH-Gezeitentafeln 2027 Nr. %s (Luecke im Bestand), py/kartverket_bsh_luecken.py' % nr,
                voll, '+00:00 :Europe/Oslo', '%.4f meters' % z0]
        neu += ['%-15s %.4f  %.2f' % (c, *w[c]) if c in w and w[c][0] >= 0.00005 else 'x 0 0' for c in namen]
        liste.append(voll)
    print(len(liste), 'neue Saetze')
    if '--schreiben' in argv and liste:
        from sicher_schreiben import schreiben
        T = open(ZIEL, encoding='iso-8859-1').read().rstrip('\n').split('\n')   # frisch lesen
        '\n'.join(neu).encode('latin-1')
        schreiben(ZIEL, '\n'.join(T + neu) + '\n')
        with open(NEU, 'a', encoding='utf-8') as fh:
            for n in liste:
                fh.write('harmonics_utide_tidetables.txt,"%s"\n' % n)
        print('->', os.path.relpath(ZIEL, ROOT))


if __name__ == '__main__':
    main(sys.argv[1:])
