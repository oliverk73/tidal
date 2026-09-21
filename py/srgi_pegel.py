#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""BIG-Messpegel (srgi.big.go.id) als Schiedsrichter fuer die Saetze am Ort.

Die Badan Informasi Geospasial betreibt 319 Pegel mit Minutenwerten. Ueber die
Webseite gibt es sie nur angemeldet, mit Zweckangabe, und je Anfrage fuer
hoechstens drei Tage ("lebih dari 3 hari harap hubungi BIG"). Die Datei, die
dann kommt, enthaelt auch nur Ausschnitte -- beim ersten Versuch (BNTN
01.-03.09.2026) fuenf Stuecke von je zehn Minuten, 45 Werte. Fuer einen Fit
reicht das nicht; als Schiedsrichter zwischen widerspruechlichen Saetzen schon:
die Luecken ueberspannen Stunden, und wer die Phase falsch hat, faellt auf.

Verwendet wird die Anmeldung aus Firefox (py/srgi_cookies.py -> ~/.srgi_cookies).
Je Pegel GENAU EINE Anfrage ueber drei Tage -- laengere Reihen gibt es nur
ueber eine direkte Anfrage bei BIG, das Stueckeln waere eine Umgehung.

Zeit: Die Zeitstempel sind UTC. Am BNTN geprueft: mit UTC passen alle
Nachbarsaetze auf 1-3 cm, mit WIB liegen alle bei ~30 cm. Der Nullpunkt der
Messung ist unbekannt; verglichen wird nach Abzug des Mittels.

Ausgabe: water_levels/Indonesia_BIG/<KODE>_<awal>_<akhir>.txt und eine Tabelle
je Pegel: Rest (cm) jedes Satzes bis UMKREIS km gegen die Messung.

Usage: python3 py/srgi_pegel.py BNTN SBGA ... [--awal 2026-09-01] [--nur-vergleich]
"""
from __future__ import annotations

import datetime as dt
import html
import http.cookiejar
import json
import os
import re
import sys
import time
import urllib.request

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import xtide_modell as X                                           # noqa: E402
from health_check import ROOT, km, load_records                    # noqa: E402

BASIS = 'https://srgi.big.go.id'
UA = 'Mozilla/5.0 (X11; Linux x86_64) Chrome/120'
ZIEL = os.path.join(ROOT, 'water_levels/Indonesia_BIG')
UMKREIS = 30.0
ZWECK = 'lainnya'


def oeffner():
    jar = http.cookiejar.MozillaCookieJar(os.path.expanduser('~/.srgi_cookies'))
    jar.load(ignore_discard=True, ignore_expires=True)
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))


def station(op, kode):
    """-> (lat, lon, name, lagebeschreibung) von der oeffentlichen Stationsseite."""
    t = op.open(urllib.request.Request(f'{BASIS}/tides/{kode}', headers={'User-Agent': UA}), timeout=60).read().decode('utf-8', 'replace')
    if 'id="isLoggedIn" value="1"' not in t and not re.search(r'value="1"[^>]*id="isLoggedIn"', t):
        raise SystemExit('Nicht angemeldet -- in Firefox anmelden, dann python3 py/srgi_cookies.py')
    m = re.search(r'pasut_stasiuns_unique="([^"]+)"', t)
    d = json.loads(html.unescape(m.group(1)))
    return float(d['lintang']), float(d['bujur']), d.get('nama_sts', kode), d.get('uraian_lok', '')


def laden(op, kode, awal, akhir):
    ziel = os.path.join(ZIEL, f'{kode}_{awal}_{akhir}.txt')
    if os.path.exists(ziel):
        return ziel
    H = {'User-Agent': UA, 'X-Requested-With': 'XMLHttpRequest', 'Accept': 'application/json',
         'Referer': f'{BASIS}/tides/{kode}'}
    q = f'awal={awal}&akhir={akhir}&pasut_nda_note={ZWECK}'
    r = json.load(op.open(urllib.request.Request(
        f'{BASIS}/tides_data/water-level-download-trigger/csv/{kode.lower()}?{q}', headers=H), timeout=120))
    if r.get('status') != 'success':
        raise RuntimeError(f'{kode}: {r}')
    daten = op.open(urllib.request.Request(f'{BASIS}/tides_data/water-level-download/csv/{kode.lower()}?{q}',
                                           headers={'User-Agent': UA}), timeout=300).read()
    os.makedirs(ZIEL, exist_ok=True)
    open(ziel, 'wb').write(daten)
    return ziel


# Spalten, die keine Wasserstaende sind. KPNG (Kupang) lieferte fuer 09/2026
# NUR Solar und Battery -- ohne diese Liste waere die Solarspannung als Pegel
# durchgegangen (17 m "Tidenhub").
KEIN_PEGEL = {'timestamp', 'solar', 'battery', 'residu', 'residual', 'temp', 'temperature'}
BEVORZUGT = ('ENC', 'RAD1', 'RAD', 'PRS', 'PRS1', 'FLT')


def messung(pfad):
    """-> (t UTC, h, sensor) oder ([], [], None) ohne Pegelspalte."""
    spalten, zeilen = None, []
    for z in open(pfad, encoding='utf-8', errors='replace'):
        f = [x.strip() for x in z.rstrip('\n').split('\t')]
        if f and f[0].lower() == 'timestamp':
            spalten = f
        elif spalten and re.match(r'20\d\d-', f[0]):
            zeilen.append(f)
    if not spalten:
        return np.array([]), np.array([]), None
    pegel = [s for s in spalten if s.lower() not in KEIN_PEGEL and s]
    if not pegel:
        return np.array([]), np.array([]), None
    sensor = next((s for s in BEVORZUGT if s in pegel), pegel[0])
    j = spalten.index(sensor)
    t, h = [], []
    for f in zeilen:
        try:
            v = float(f[j])
        except (ValueError, IndexError):
            continue
        t.append(dt.datetime.fromisoformat(f[0]).replace(tzinfo=dt.timezone.utc).timestamp())
        h.append(v)
    t, h = np.array(t), np.array(h)
    if len(h):
        # Aussetzer und Spruenge: weiter als 6 MAD vom Median weg
        med = np.median(h)
        mad = max(np.median(np.abs(h - med)), 0.01)
        ok = np.abs(h - med) < 6 * mad
        t, h = t[ok], h[ok]
    return t, h, sensor


def vergleich(kode, lat, lon, pfad, recs, kopf):
    namen, speeds, arg, fak = kopf
    t, h, sensor = messung(pfad)
    if len(t) < 10:
        print(f'  {kode}: keine brauchbaren Pegelwerte ({len(t)}; Sensor {sensor or "keiner"} in der Datei)')
        return
    p0 = {'lat': lat, 'lon': lon}
    nah = sorted(((km(p0, r), r) for r in recs if km(p0, r) <= UMKREIS), key=lambda x: x[0])
    stunden = len({int(x // 3600) for x in t})
    print(f'\n{kode}  ({lat:.4f}, {lon:.4f})  Sensor {sensor}, {len(t)} Werte in {stunden} Stunden, '
          f'Spanne {h.max() - h.min():.2f} m')
    zeilen = []
    for d, r in nah:
        try:
            z0, werte, einheit, mer = X.satz_lesen(os.path.join(ROOT, r['file']), r['name'])
        except KeyError:
            continue
        sk = 0.3048 if einheit.startswith('f') else 1.0
        eigen = {k: (a, X.greenwich(kap, speeds[k], mer)) for k, (a, kap) in werte.items() if k in speeds}
        p = X.kurve(t, 0.0, eigen, namen, speeds, arg, fak, sk)
        res = h - p
        res -= res.mean()
        zeilen.append((float(np.sqrt(np.mean(res ** 2))), d, r))
    for rms, d, r in sorted(zeilen, key=lambda x: x[0]):
        print(f'   {rms * 100:5.1f} cm  {d:5.1f} km  {r["name"][:46]:48s} {os.path.basename(r["file"]).replace("harmonics_", "")[:26]}')


def main(argv):
    codes = [a.upper() for a in argv if not a.startswith('--') and not re.match(r'\d{4}-', a)]
    awal = argv[argv.index('--awal') + 1] if '--awal' in argv else '2026-09-01'
    akhir = (dt.date.fromisoformat(awal) + dt.timedelta(days=2)).isoformat()
    op = oeffner()
    recs = [r for r in load_records() if r['lat'] is not None and not r['current']]
    kopf = X.kopf_lesen(os.path.join(ROOT, 'harmonics/utide/harmonics_utide_tidetables.txt'))
    for i, kode in enumerate(codes):
        lat, lon, name, lage = station(op, kode)
        pfad = os.path.join(ZIEL, f'{kode}_{awal}_{akhir}.txt')
        if '--nur-vergleich' not in argv:
            pfad = laden(op, kode, awal, akhir)
            if i + 1 < len(codes):
                time.sleep(3)
        print(f'\n=== {kode} {name}: {lage[:110]}')
        vergleich(kode, lat, lon, pfad, recs, kopf)


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
