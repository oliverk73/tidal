#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Welche BIG-Pegel (srgi.big.go.id) haben vollstaendige harmonische Konstanten?

Die Stationsseiten bieten unter "Prediksi Pasut" eine Vorhersage, die BIG live
aus den harmonischen Konstanten des Pegels rechnet ("harmonic_constants_on_the_fly",
Konstanten aus den Messungen 2025). Fuer manche Pegel fehlen sie noch
("Konstanta harmonik stasiun ... belum lengkap"). Diese Umfrage fragt je Pegel
EINEN Tag Vorhersage ab und haelt fest: vorhanden oder nicht, und die
Koordinate, die BIG fuer den Pegel fuehrt (BMKG hat seine Stationspositionen
von hier -- Tangkiang stimmt auf fuenf Stellen).

Rate: der Server sperrt bei einer Anfrage je Sekunde ("Too Many Attempts").
Hier eine Anfrage alle PAUSE Sekunden, bei einer Sperre wachsende Wartezeit.
Vorhandene Ergebnisse werden fortgesetzt; nur Sperr-Fehlschlaege werden
wiederholt.

Ausgabe: harmonics/help/big_pegel.json  {kode: {status, name, lat, lon, source_datum, grund}}

Usage: python3 py/big_pegel_umfrage.py
"""
from __future__ import annotations

import collections
import http.cookiejar
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUS = os.path.join(ROOT, 'harmonics/help/big_pegel.json')
BASIS = 'https://srgi.big.go.id'
UA = 'Mozilla/5.0 (X11; Linux x86_64) Chrome/120'
PAUSE = 12
SPERRE = (120, 300, 600)


class Sitzung:
    def __init__(self):
        jar = http.cookiejar.MozillaCookieJar()
        pfad = os.path.expanduser('~/.srgi_cookies')
        if os.path.exists(pfad):
            jar.load(pfad, ignore_discard=True, ignore_expires=True)
        self.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
        self.tok, self.bis = None, 0

    def oeffnen(self, req, timeout=120):
        for warte in (0,) + SPERRE:
            if warte:
                print(f'  Sperre -- warte {warte} s', flush=True)
                time.sleep(warte)
            try:
                return self.op.open(req, timeout=timeout)
            except urllib.error.HTTPError as e:
                if e.code != 429:
                    raise
        raise RuntimeError('Sperre haelt an')

    def token(self):
        if self.tok and time.time() < self.bis - 20:
            return self.tok
        seite = self.oeffnen(urllib.request.Request(f'{BASIS}/tides/KTPG', headers={'User-Agent': UA})).read().decode('utf-8', 'replace')
        csrf = re.search(r'<meta name="csrf-token" content="([^"]+)"', seite).group(1)
        d = json.load(self.oeffnen(urllib.request.Request(f'{BASIS}/tides/access-token', data=b'{}', method='POST', headers={
            'User-Agent': UA, 'X-CSRF-TOKEN': csrf, 'X-Requested-With': 'XMLHttpRequest',
            'Content-Type': 'application/json', 'Accept': 'application/json'})))
        self.tok, self.bis = d['access_token'], time.time() + int(d['expires_in'])
        return self.tok

    def vorhersage(self, kode, start, ende, intervall=60):
        p = {'station': kode, 'start_date': start, 'end_date': ende, 'timezone': 'UTC', 'datum': 'MSL',
             'source': 'harmonic', 'interval_minutes': intervall}
        req = urllib.request.Request(f'{BASIS}/tides_data/prediksi/query?' + urllib.parse.urlencode(p), headers={
            'User-Agent': UA, 'Authorization': 'Bearer ' + self.token(), 'X-Requested-With': 'XMLHttpRequest',
            'Accept': 'application/json'})
        return json.load(self.oeffnen(req, timeout=300))


def stationsliste(s):
    t = s.oeffnen(urllib.request.Request(f'{BASIS}/tides/KTPG', headers={'User-Agent': UA})).read().decode('utf-8', 'replace')
    return {c.lower(): n.strip() for c, n in re.findall(r'<option[^>]*>\s*([A-Z0-9]{3,5})\s*-\s*([^<]+?)\s*</option>', t)}


def main():
    s = Sitzung()
    namen = stationsliste(s)
    out = json.load(open(AUS, encoding='utf-8')) if os.path.exists(AUS) else {}
    offen = [c for c in sorted(namen) if c not in out or 'Too Many' in out[c].get('grund', '')
             or out[c]['status'] == 'fehler']
    print(f'{len(namen)} Pegel, {len(out)} erfasst, {len(offen)} offen', flush=True)
    for i, c in enumerate(offen):
        try:
            d = s.vorhersage(c, '2026-09-01', '2026-09-01')
            st = d.get('station') or {}
            out[c] = {'status': 'ok', 'name': namen[c], 'lat': st.get('lat'), 'lon': st.get('lon'),
                      'source_datum': d.get('query', {}).get('source_datum')}
        except urllib.error.HTTPError as e:
            out[c] = {'status': 'fehlt', 'name': namen[c], 'grund': e.read()[:160].decode('utf-8', 'replace')}
        except Exception as e:
            out[c] = {'status': 'fehler', 'name': namen[c], 'grund': str(e)[:160]}
        if (i + 1) % 10 == 0 or i + 1 == len(offen):
            json.dump(out, open(AUS, 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
            print(f'  {i + 1}/{len(offen)}  ok {sum(v["status"] == "ok" for v in out.values())}', flush=True)
        time.sleep(PAUSE)
    json.dump(out, open(AUS, 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
    print('fertig:', dict(collections.Counter(v['status'] for v in out.values())))
    print('Gruende:', collections.Counter(re.sub(r'stasiun \w+', 'stasiun X', v.get('grund', ''))[:70]
                                          for v in out.values() if v['status'] != 'ok').most_common(4))


if __name__ == '__main__':
    sys.exit(main())
