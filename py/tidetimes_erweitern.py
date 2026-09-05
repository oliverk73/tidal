#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Verlaengert die tidetimes-Tafeln nach vorn und nach hinten.

Der Versuch an Heysham hat gezeigt, woran die 626 britischen
tidetimes-Anpassungen haengen: nicht an fehlenden Konstituenten, sondern
an der Spanne des Fitfensters. Gegen zwei ausgehaltene Monate BODC
gemessen ergibt eine Anpassung an

     84 Tage Scheitelwerte   176.6 cm
    167 Tage                 120.0 cm
    334 Tage                  67.2 cm

-- eine Halbierung je Verdopplung, und bei 334 Tagen noch nicht
ausgereizt. Die Tafeln auf der Platte decken 458 Tage ab (2025-01-01 bis
etwa 2026-04-19). Geholt wird deshalb ein Jahr davor und alles seither:
das bringt die Spanne auf rund 960 Tage.

Ausgeduennt wird nicht. Der Gedanke lag nahe -- an Heysham war jeder
dritte Tag sogar besser als jeder --, aber an Fishguard und Lerwick
verschlechtert dasselbe Ausduennen den Fit deutlich, und Lerwick springt
unsystematisch. Aus vier Stationen laesst sich keine Regel ableiten; die
Fits sind dafuer zu instabil.

Geholt wird nur fuer Saetze OHNE gemessen besseren Nachbarn. 128 der 626
haben einen -- die verschwinden ohnehin aus dem Bestand, und ihre Tafel
zu verlaengern waere Arbeit fuer nichts. Bleiben 498.

Eine Seite je Station und Tag, mehr gibt die Seite nicht her: es gibt
keine Monats- oder Jahresansicht, und die Tagesseite enthaelt genau vier
Gezeiten. Zwischen zwei Abrufen liegt eine Viertelsekunde, macht rund
1.7 Abrufe je Sekunde. Der Lauf schreibt nach jeder Station eine
Fortschrittsdatei und laesst sich jederzeit fortsetzen; was schon in der
Tafel steht, wird nicht noch einmal geholt.

Usage: python3 py/tidetimes_erweitern.py [--pruefen] [--limit N]
       --pruefen  nur die Stationskennungen pruefen, nichts holen
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import statistics
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from health_check import load_records, km, ROOT                   # noqa: E402
from pegel_dubletten import vermerke                              # noqa: E402
import dubletten_aufraeumen as D                                  # noqa: E402

ORDNER = os.path.join(ROOT, 'water_levels', 'UK_tidetimes')
FORTSCHRITT = os.path.join(ORDNER, 'erweitern_fortschritt.json')
KOPF = {'User-Agent': 'tidal-corpus/1.0 (harmonic constant verification; '
                      'github.com/oliverk73/tidal)'}
PAUSE = 0.25
ZURUECK = (dt.date(2024, 1, 1), dt.date(2024, 12, 31))
MUSTER = re.compile(r'<dt>(High Tide|Low Tide):</dt>\s*<dd>(\d{2}:\d{2})</dd>\s*'
                    r'<dt>Height:</dt>\s*<dd>([\d.]+)m</dd>')


def kennung(name):
    """-> Kennungen, unter denen die Station bei tidetimes stehen koennte."""
    s = name.lower().replace("'", '').replace('’', '')
    s = re.sub(r'[^a-z0-9]+', '-', s).strip('-')
    out = [s]
    ohne = re.sub(r'-*\(.*?\)-*', '-', name.lower().replace("'", ''))
    ohne = re.sub(r'[^a-z0-9]+', '-', ohne).strip('-')
    if ohne != s:
        out.append(ohne)
    return out


def ziele():
    """-> [(Tafelpfad, Stationsname)] fuer Saetze ohne besseren Nachbarn."""
    k = vermerke()
    recs = [r for r in load_records() if r['lat'] is not None and not r['current']]
    tt = [r for r in recs if 'tidetimes.co.uk' in k.get((r['file'], r['line']), '')]
    mess = D.messungen()

    def guete(r):
        m = mess.get((r['name'], os.path.basename(r['file'])), ())
        frei = [x[3] for x in m if not x[6]]
        return statistics.median(frei) if frei else None

    tafeln = {}
    for pfad in sorted(os.listdir(ORDNER)):
        if not pfad.endswith('.json') or pfad.startswith(('missing', 'download',
                                                          'erweitern')):
            continue
        try:
            d = json.load(open(os.path.join(ORDNER, pfad), encoding='utf-8'))
        except Exception:
            continue
        if isinstance(d, dict) and d.get('lat') is not None:
            tafeln[(round(d['lat'], 3), round(d['lon'], 3))] = (
                os.path.join(ORDNER, pfad), d.get('name', ''))
    out, uebersprungen = [], 0
    for r in tt:
        g = guete(r)
        besser = [o for o in recs if o is not r and km(r, o) < 1.0
                  and guete(o) is not None and (g is None or guete(o) < g)]
        if besser:
            uebersprungen += 1
            continue
        t = tafeln.get((round(r['lat'], 3), round(r['lon'], 3)))
        if not t:
            t = min(tafeln.items(),
                    key=lambda kv: km(r, {'lat': kv[0][0], 'lon': kv[0][1]}),
                    default=(None, None))
            if t[0] is None or km(r, {'lat': t[0][0], 'lon': t[0][1]}) > 1.0:
                continue
            t = t[1]
        if t not in out:
            out.append(t)
    print(f'{len(tt)} tidetimes-Saetze, {uebersprungen} mit besserem Nachbarn '
          f'uebersprungen -> {len(out)} Tafeln zu verlaengern', file=sys.stderr)
    return out


def hole(slug, tag):
    u = f'https://www.tidetimes.co.uk/{slug}-tide-times-{tag:%Y%m%d}'
    try:
        with urllib.request.urlopen(urllib.request.Request(u, headers=KOPF),
                                    timeout=20) as r:
            text = r.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        return None if e.code == 404 else []
    except Exception:
        return []
    return [{'date': tag.isoformat(), 'time': m.group(2),
             'height_m': float(m.group(3)),
             'type': 'HW' if m.group(1) == 'High Tide' else 'LW'}
            for m in MUSTER.finditer(text)]


def main(argv):
    nur_pruefen = '--pruefen' in argv
    grenze = int(argv[argv.index('--limit') + 1]) if '--limit' in argv else None
    liste = ziele()
    if grenze:
        liste = liste[:grenze]
    stand = {}
    if os.path.exists(FORTSCHRITT):
        try:
            stand = json.load(open(FORTSCHRITT, encoding='utf-8'))
        except Exception:
            stand = {}
    heute = dt.date.today()
    gesamt_neu = 0
    for nr, (pfad, name) in enumerate(liste, 1):
        if stand.get(pfad) == 'fertig':
            continue
        d = json.load(open(pfad, encoding='utf-8'))
        vorhanden = {e['date'] for e in d.get('entries', ())}
        letzte = max(vorhanden) if vorhanden else '2025-01-01'
        fehlend = []
        tag = ZURUECK[0]
        while tag <= ZURUECK[1]:
            if tag.isoformat() not in vorhanden:
                fehlend.append(tag)
            tag += dt.timedelta(days=1)
        tag = dt.date.fromisoformat(letzte) + dt.timedelta(days=1)
        while tag <= heute:
            fehlend.append(tag)
            tag += dt.timedelta(days=1)
        slugs = kennung(name)
        if nur_pruefen:
            g = hole(slugs[0], dt.date(2026, 9, 1))
            ok = g is not None and len(g) > 0
            if not ok and len(slugs) > 1:
                g = hole(slugs[1], dt.date(2026, 9, 1))
                ok = g is not None and len(g) > 0
            print(f'  {"OK " if ok else "-- "} {name[:30]:30s} {slugs[0][:34]:34s} '
                  f'{len(fehlend)} Tage fehlen')
            time.sleep(PAUSE)
            continue
        neu, slug = [], None
        for kand in slugs:
            probe = hole(kand, fehlend[0] if fehlend else heute)
            time.sleep(PAUSE)
            if probe:
                slug = kand
                neu += probe
                fehlend = fehlend[1:]
                break
        if slug is None:
            stand[pfad] = 'keine Kennung'
            json.dump(stand, open(FORTSCHRITT, 'w'), ensure_ascii=False)
            continue
        for tag in fehlend:
            g = hole(slug, tag)
            time.sleep(PAUSE)
            if g:
                neu += g
        if neu:
            d['entries'] = sorted(d.get('entries', []) + neu,
                                  key=lambda e: (e['date'], e['time']))
            json.dump(d, open(pfad, 'w', encoding='utf-8'), ensure_ascii=False)
            gesamt_neu += len(neu)
        stand[pfad] = 'fertig'
        json.dump(stand, open(FORTSCHRITT, 'w'), ensure_ascii=False)
        print(f'  {nr}/{len(liste)} {name[:28]:28s} +{len(neu):4} Gezeiten '
              f'(gesamt {gesamt_neu})', file=sys.stderr, flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
