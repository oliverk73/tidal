#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ATT-Nebenhaefen in Norwegen durch Fits aus Kartverket-Punktvorhersagen ersetzen (Oliver 11.11.2026: "Ja").

Anlass: py/kartverket_pruefen.py -- die 140 ATT-NP202-Nebenhaefen weichen von Kartverket median 7,8 cm ab, im Norden
systematisch 15-25 min zu spaet (Buch-Zeitdifferenzen; Beweis Svolvaer 4 km neben Messpegel Kabelvaag). Kartverket
rechnet jeden Kuestenpunkt vom naechsten festen Pegel (Faktor + Zeitversatz), Kontrolle an den Messsaetzen 1,6 cm.
Je Satz: zwei Jahre (2026-27) stuendliche Kartverket-Vorhersage an der Satzposition, Fit mit Rayleigh nach echter
Laenge (+SA), Name/Position/Region bleiben. Ausgenommen: Saltstraumen (Satz in der Stromenge, Seite unklar).
Alte Saetze -> harmonics/help/norwegen_att_20261111_loeschen.csv (py/saetze_loeschen.py).

Usage: venv/bin/python py/kartverket_ersetzen.py [--schreiben]
"""
import csv
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
import kartverket_pruefen as KP                                    # noqa: E402
import qld_msq_fit as Q                                            # noqa: E402
import xtide_modell as X                                           # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ZIEL = os.path.join(ROOT, 'harmonics/utide/harmonics_utide_tidetables.txt')
PRUEF = os.path.join(ROOT, 'harmonics/help/kartverket_pruefung.csv')
LOESCH = os.path.join(ROOT, 'harmonics/help/norwegen_att_20261111_loeschen.csv')
NEU = os.path.join(ROOT, 'harmonics/help/neu_pruefen_20261111.csv')
CACHE = os.path.join(ROOT, 'water_levels/Norway_Kartverket_punkte_2j')
API = 'https://vannstand.kartverket.no/tideapi.php'
AUSNAHMEN = {'Saltstraumen, Norway'}
EXTRA = {'Stjørdalshalsen, Trøndelag, Norway'}                      # FES 12,9 cm


def abruf(la, lo):
    os.makedirs(CACHE, exist_ok=True)
    f = os.path.join(CACHE, '%.4f_%.4f.json' % (la, lo))
    if os.path.exists(f):
        return json.load(open(f))
    u = ('%s?tide_request=locationdata&lat=%.6f&lon=%.6f&fromtime=2026-01-01T00:00&totime=2028-01-01T00:00'
         '&datatype=pre&refcode=cd&lang=en&interval=60&dst=0&tzone=0' % (API, la, lo))
    for _ in range(3):
        try:
            x = urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': 'weather-tides/1.0'}),
                                       timeout=400).read().decode()
            break
        except Exception as e:                                      # noqa: BLE001
            print('   Abruf-Fehler', e)
            time.sleep(30)
    else:
        return None
    m = re.search(r'<location ([^>]*?)/?>', x)
    a = dict(re.findall(r'(\w+)="([^"]*)"', m.group(1))) if m else {}
    pts = re.findall(r'value="(-?[\d.]+)" time="([^"]+)" flag="pre"', x)
    d = dict(name=a.get('name', ''), code=a.get('code', ''), faktor=a.get('factor', ''), delay=a.get('delay', ''),
             t=[b for v, b in pts], h=[float(v) / 100 for v, b in pts])
    json.dump(d, open(f, 'w'))
    return d


def kopf_alt(pfad, zeile):
    return KP.kopfzeilen(pfad, zeile)


def main(argv):
    import health_check as H
    kopf = X.kopf_lesen(ZIEL)
    namen, speeds, arg, fak = kopf
    pr = {r['name']: r for r in csv.DictReader(open(PRUEF, encoding='utf-8'))}
    recs = {r['name']: r for r in H.load_records() if not r['current']}
    wahl = [n for n, r in pr.items() if r['rms_cm'] and n not in AUSNAHMEN
            and (r['quelle'].startswith('ADMIRALTY Tide Tables Vol.2 (NP202), Part II ') or n in EXTRA)]
    print(len(wahl), 'Saetze')
    heute = dt.date.today().strftime('%Y%m%d')
    neu, loesch, liste = [], [], []
    for i, name in enumerate(wahl):
        r, p = recs[name], pr[name]
        d = abruf(r['lat'], r['lon'])
        if not d or len(d['h']) < 17000:
            print('%3d %-45s zu wenig Daten' % (i, name))
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
            print('%3d %-45s Fit verdaechtig (max %.2f, RMS %.1f cm) -- uebersprungen' % (i, name, mx, 100 * rms))
            continue
        alt = kopf_alt(os.path.join(ROOT, r['file']), r['line'])
        prov = alt.get('province') or alt.get('region') or alt.get('state') or ''
        bezug = d['code'] + ((' x ' + d['faktor']) if d['faktor'] and d['faktor'] != '1.00' else '') + \
            ((' %+d min' % int(d['delay'])) if d['delay'] not in ('', '0') else '')
        quelle_alt = 'ATT NP202 Nr. %s' % alt.get('att_number', '?') if 'att_number' in alt else 'FES2022'
        print('%3d %-45s %s, Fit %.2f cm, Z0 %.2f, M2 %.3f/%.0f (alt %s cm, %s min)' % (
            i, name, bezug, 100 * rms, z0, *w['M2'], p['rms_cm'], p['versatz_min']))
        neu += ['#', '# ' + name, '# BEGIN HOT COMMENTS', '# country: Norway',
                '# source: Kartverket tide predictions (vannstand.kartverket.no)',
                '# date_imported: %s' % heute, '# datum: Chart Datum', '# confidence: 7',
                '# !units: meters', '# !longitude: %.4f' % r['lon'], '# !latitude: %.4f' % r['lat']]
        if prov:
            neu.append('# province: %s' % prov)
        neu += ['# note: %s Fit %d Tage Kartverket-Punktvorhersage (%.1f cm), Bezug %s; ersetzt %s (%s cm, %+d min daneben)'
                % (heute, tage, 100 * rms, bezug, quelle_alt, p['rms_cm'], int(p['versatz_min'])),
                '# note: py/kartverket_ersetzen.py',
                name, '+00:00 :Europe/Oslo', '%.4f meters' % z0]
        neu += ['%-15s %.4f  %.2f' % (c, *w[c]) if c in w and w[c][0] >= 0.00005 else 'x 0 0' for c in namen]
        loesch.append(dict(datei=r['file'], name=name, fehler_prozent='-',
                           begruendung='gegen Kartverket %s cm/%+d min; ersetzt durch Kartverket-Fit (%s), '
                                       'py/kartverket_ersetzen.py, 11.11.2026' % (p['rms_cm'], int(p['versatz_min']), bezug)))
        liste.append(name)
    print(len(liste), 'ersetzbar')
    if '--schreiben' in argv:
        with open(LOESCH, 'w', newline='', encoding='utf-8') as fh:
            wr = csv.DictWriter(fh, fieldnames=['datei', 'name', 'fehler_prozent', 'begruendung'])
            wr.writeheader()
            wr.writerows(loesch)
        import subprocess
        subprocess.run([sys.executable, os.path.join(ROOT, 'py/saetze_loeschen.py'), LOESCH, '--schreiben'], check=True)
        from sicher_schreiben import schreiben
        T = open(ZIEL, encoding='iso-8859-1').read().rstrip('\n').split('\n')
        assert not any(n in T for n in liste), 'alte Saetze noch im Ziel'
        '\n'.join(neu).encode('latin-1')
        schreiben(ZIEL, '\n'.join(T + neu) + '\n')
        with open(NEU, 'a', encoding='utf-8') as fh:
            for n in liste:
                fh.write('harmonics_utide_tidetables.txt,"%s"\n' % n)
        print('->', os.path.relpath(ZIEL, ROOT))


if __name__ == '__main__':
    main(sys.argv[1:])
