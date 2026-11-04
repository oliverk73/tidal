#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Schnittstelle der eigenen Tidenrechnung fuer app.py (Stufe 2, Oliver 3.11.2026).

Liefert, was die App bisher von XTide holte -- direkt aus den Harmonics-Dateien:
  svg(...)        Kurve wie `tide -m g -f v -gw 3200` (py/tiden_grafik.py)
  info(...)       Infoblock wie `tide -m a`, aber als [(Feld, [Zeilen])]
  text(...)       Ereignisliste im Textformat von `tide -f t -m p -df %Y-%m-%d -tf %H:%M`
                  (Kopf: Name, Koordinaten, "Note:" nur mit der ersten Notizzeile)

Dateien werden einmal gelesen und neu geladen, sobald sich ihre Aenderungszeit aendert
(die App schreibt Namen/Positionen selbst um). Quelle = TCD-Name wie in der App
(z. B. harmonics_bsh_germany.tcd) -> gleichnamige .txt unter harmonics/.
"""
from __future__ import annotations

import datetime as dt
import os
import sys
import threading
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import astro                                                        # noqa: E402
import tiden_grafik as G                                            # noqa: E402
import tiden_rechnung as T                                          # noqa: E402

ROOT = T.ROOT
_sperre = threading.Lock()
_cache = {}            # pfad -> (mtime, Datei)
EINHEIT_WORT = {'m': 'meters', 'ft': 'feet'}


def _aktive():
    from health_check import active_files
    return [os.path.join(ROOT, f) for f in active_files() if f.endswith('.txt') and 'coordinates' not in f]


def datei(pfad):
    m = os.path.getmtime(pfad)
    with _sperre:
        c = _cache.get(pfad)
        if c and c[0] == m:
            return c[1]
    D = T.Datei(pfad)
    with _sperre:
        _cache[pfad] = (m, D)
    return D


def txt_fuer(source):
    stem = os.path.splitext(os.path.basename(source))[0]
    for p in _aktive():
        if os.path.basename(p)[:-4] == stem:
            return p
    return None


def finden(name, source=None):
    """-> (Datei, name) oder KeyError."""
    pfade = [txt_fuer(source)] if source else _aktive()
    for p in pfade:
        if p and os.path.exists(p):
            D = datei(p)
            if name in D.saetze:
                return D, name
    raise KeyError(f'{name} [{source}]')


def zone(D, name, utc):
    return dt.timezone.utc if utc else ZoneInfo(D.saetze[name].zone.lstrip(':'))


_tzf = None


def ortszone(D, name):
    """IANA-Zone aus der Position -- fuer Saetze mit ':UTC' (UTide-Fits), deren Tabelle die App
    ebenfalls so in Ortszeit umrechnet (app.py, timezonefinder). None, wenn nichts gefunden."""
    global _tzf
    s = D.saetze[name]
    if _tzf is None:
        from timezonefinder import TimezoneFinder
        _tzf = TimezoneFinder()
    iana = _tzf.timezone_at(lat=float(s.hot['!latitude']), lng=float(s.hot['!longitude']))
    return ZoneInfo(iana) if iana else None


def svg(name, source, tag, einheit='m', utc=False):
    """Kurve; Saetze mit ':UTC' zeigt sie (ausser bei utc=True) in der Ortszeit der Position,
    passend zur Ereignistabelle der App (4.11.2026, vorher stand die Grafik in UTC)."""
    D, name = finden(name, source)
    z = None
    if not utc and D.saetze[name].zone.lstrip(':').upper() == 'UTC':
        z = ortszone(D, name)
    return G.svg(D, name, tag, einheit, utc, zone=z)


def info(name, source):
    D, name = finden(name, source)
    zeilen = T.info(D, name)
    tcd = os.path.join('/usr/share/xtide', os.path.basename(D.pfad)[:-4] + '.tcd')
    return [(k, [tcd] if k == 'In file' else v) for k, v in zeilen]


def koordinaten(D, name):
    s = D.saetze[name]
    la, lo = round(float(s.hot['!latitude']) * 1e5) / 1e5, round(float(s.hot['!longitude']) * 1e5) / 1e5
    return f"{abs(la):.4f}° {'N' if la >= 0 else 'S'}, {abs(lo):.4f}° {'E' if lo >= 0 else 'W'}"


def ereignisse(name, source, beginn, ende, einheit='m', utc=False, astro_auch=True):
    """beginn/ende: 'YYYY-MM-DD HH:MM' in Stationszeit (bzw. UTC). -> [(datetime_lokal, wert|None, art)]"""
    D, name = finden(name, source)
    s = D.saetze[name]
    z = zone(D, name, utc)
    t0 = dt.datetime.strptime(beginn, '%Y-%m-%d %H:%M').replace(tzinfo=z).timestamp()
    t1 = dt.datetime.strptime(ende, '%Y-%m-%d %H:%M').replace(tzinfo=z).timestamp()
    fk = 1.0 if s.strom or einheit != 'ft' else 1 / T.FUSS
    ev = [(t, h * fk, a) for t, h, a in D.ereignisse(name, t0, t1)]
    if astro_auch:
        ev += [(t, None, a) for t, a in astro.ereignisse(float(s.hot['!latitude']), float(s.hot['!longitude']), t0, t1)]
    ev.sort(key=lambda e: e[0])
    return D, name, [(dt.datetime.fromtimestamp(int(t), z), h, a) for t, h, a in ev]


def text(name, source, beginn, ende, einheit='m', utc=False, astro_auch=True):
    """Ausgabe wie `tide -f t -m p -df %Y-%m-%d -tf %H:%M` (Minute abgeschnitten wie XTide)."""
    D, name, ev = ereignisse(name, source, beginn, ende, einheit, utc, astro_auch)
    s = D.saetze[name]
    wort = 'knots' if s.strom else EINHEIT_WORT.get(einheit, 'meters')
    out = [name, koordinaten(D, name)]
    noten = [v for k, v in s.hot_liste if k == 'note']
    if noten:
        out.append('Note:  ' + noten[0])
    out.append('')
    for d, h, a in ev:
        if h is None:
            out.append(f'{d:%Y-%m-%d %H:%M}   {a}')
        else:
            out.append(f'{d:%Y-%m-%d %H:%M}  {h:5.2f} {wort}  {a}')
    return '\n'.join(out) + '\n'


if __name__ == '__main__':
    n, q = sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None
    print(text(n, q, '2026-11-03 00:00', '2026-11-05 00:00'))
    for k, v in info(n, q):
        print(f'{k:20s} {v[0]}' + ''.join(f'\n{"":20s} {x}' for x in v[1:]))
