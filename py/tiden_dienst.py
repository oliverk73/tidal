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
    s = D.saetze[name]
    iana = zonenname(float(s.hot['!latitude']), float(s.hot['!longitude']))
    return ZoneInfo(iana) if iana else None


def zonenname(lat, lon):
    """IANA-Zone der Position. Auf See die Zone der naechsten Kueste (bis ~300 km), nicht die nautische
    Etc/GMT-Zone -- sonst stand z. B. die Boje Estaca de Bares auf UTC-1 statt Madrid (4.11.2026)."""
    import math
    global _tzf
    if _tzf is None:
        from timezonefinder import TimezoneFinder
        _tzf = TimezoneFinder()
    z = _tzf.timezone_at_land(lat=lat, lng=lon)
    if z:
        return z
    for r in (0.05, 0.1, 0.2, 0.35, 0.5, 0.75, 1.0, 1.5, 2.0, 2.7):
        for w in range(0, 360, 15):
            la = lat + r * math.cos(math.radians(w))
            lo = lon + r * math.sin(math.radians(w)) / max(0.2, math.cos(math.radians(lat)))
            if -90 < la < 90:
                z = _tzf.timezone_at_land(lat=la, lng=(lo + 180) % 360 - 180)
                if z:
                    return z
    return _tzf.timezone_at(lat=lat, lng=lon)


def svg(name, source, tag, einheit='m', utc=False):
    """Kurve; Saetze mit ':UTC' zeigt sie (ausser bei utc=True) in der Ortszeit der Position,
    passend zur Ereignistabelle der App (4.11.2026, vorher stand die Grafik in UTC)."""
    D, name = finden(name, source)
    z = None
    if not utc and D.saetze[name].zone.lstrip(':').upper() == 'UTC':
        z = ortszone(D, name)
    return G.svg(D, name, tag, einheit, utc, zone=z, modell=_grafik_modell(D, name))


def _grafik_modell(D, name):
    """Eigene HW/NW-Rechnung auch in der Kurve: Scheitel und Zettel wie in der Tabelle."""
    hw = _hwnw_modell(D, name)
    if not hw:
        return None
    import hwnw_ungleichheiten as HU

    def ereig(t0, t1):
        ev = [e for e in D.ereignisse(name, t0, t1) if e[2] not in ('High Tide', 'Low Tide')]
        ev += [(t, h, 'High Tide' if a == 'H' else 'Low Tide') for t, h, a in HU.vorhersage_kombi(hw, t0, t1)]
        return sorted(ev, key=lambda e: e[0])
    return (lambda t: HU.kurve(hw, D, name, t)), ereig


def _strom_zone(D, name, utc):
    if not utc and D.saetze[name].zone.lstrip(':').upper() == 'UTC':
        return ortszone(D, name) or dt.timezone.utc
    return zone(D, name, utc)


SPD_FAKTOR = {'kn': (1.0, 'kn'), 'ms': (0.514444, 'm/s'), 'kmh': (1.852, 'km/h')}


def strom_rose(name, source, utc=False, spd='kn', jetzt=None):
    """SVG der Strom-Rose (Stufe 3, 4.11.2026) oder None, wenn keine Ellipsenkonstanten vorliegen."""
    import time
    import strom_ellipsen as E
    D, name = finden(name, source)
    if not D.saetze[name].strom:
        return None
    f, wort = SPD_FAKTOR.get(spd, SPD_FAKTOR['kn'])
    return E.rose_svg(D, name, time.time() if jetzt is None else jetzt, _strom_zone(D, name, utc), f, wort)


def strom_richtungen(name, source, zeiten, utc=False):
    """zeiten: ['YYYY-MM-DD HH:MM'] in der Zeit, in der text() ausgibt -> [Grad rechtweisend] oder None."""
    import strom_ellipsen as E
    D, name = finden(name, source)
    if not D.saetze[name].strom or E.fuer_satz(D, name) is None:
        return None
    z = zone(D, name, utc)
    t = [dt.datetime.strptime(x, '%Y-%m-%d %H:%M').replace(tzinfo=z).timestamp() for x in zeiten]
    return [float(r) for r in E.vektor(D, name, t)[1]]


def info(name, source):
    D, name = finden(name, source)
    zeilen = T.info(D, name)
    tcd = os.path.join('/usr/share/xtide', os.path.basename(D.pfad)[:-4] + '.tcd')
    return [(k, [tcd] if k == 'In file' else v) for k, v in zeilen]


def koordinaten(D, name):
    s = D.saetze[name]
    la, lo = round(float(s.hot['!latitude']) * 1e5) / 1e5, round(float(s.hot['!longitude']) * 1e5) / 1e5
    return f"{abs(la):.4f}° {'N' if la >= 0 else 'S'}, {abs(lo):.4f}° {'E' if lo >= 0 else 'W'}"


def hwnw_hinweis(name, source):
    """Fuer die Seite (5.11.2026): ist an diesem Satz die eigene HW/NW-Rechnung aktiv, dann
    dict(jahre=(j0, j1), H=(harm_rms, rms) oder None, N=...) aus harmonics/hwnw/<kurz>.json, sonst None."""
    try:
        import hwnw_ungleichheiten as HU
        D, name = finden(name, source)
        k = _hwnw_modell(D, name)
        if not k:
            return None
        E = HU.laden(k)
        w, p = E.get('wahl', {}), E.get('pruefung', {})
        aus = {a: (p[a]['harm_rms'], p[a]['rms']) if w.get(a, 'harm') != 'harm' and a in p else None for a in 'HN'}
        if not aus['H'] and not aus['N']:
            return None
        return dict(jahre=tuple(E['jahre']), pruefjahr=next(iter(p.values()))['jahr'], **aus)
    except Exception:  # noqa: BLE001 -- Hinweis ist Zusatz, nie die Seite verlieren
        return None


def _hwnw_modell(D, name):
    try:
        import hwnw_ungleichheiten as HU
        return HU.modell_fuer(D.pfad, name, D.saetze[name])
    except Exception:  # noqa: BLE001 -- Modell fehlt oder kaputt: harmonische Scheitel
        return None


def ereignisse(name, source, beginn, ende, einheit='m', utc=False, astro_auch=True):
    """beginn/ende: 'YYYY-MM-DD HH:MM' in Stationszeit (bzw. UTC). -> [(datetime_lokal, wert|None, art)]"""
    D, name = finden(name, source)
    s = D.saetze[name]
    z = zone(D, name, utc)
    t0 = dt.datetime.strptime(beginn, '%Y-%m-%d %H:%M').replace(tzinfo=z).timestamp()
    t1 = dt.datetime.strptime(ende, '%Y-%m-%d %H:%M').replace(tzinfo=z).timestamp()
    fk = 1.0 if s.strom or einheit != 'ft' else 1 / T.FUSS
    ev = [(t, h * fk, a) for t, h, a in D.ereignisse(name, t0, t1)]
    hw = _hwnw_modell(D, name)
    if hw:      # eigene HW/NW-Rechnung (Stufe 4, py/hwnw_ungleichheiten.py), die Kurve bleibt harmonisch
        import hwnw_ungleichheiten as HU
        ev = [e for e in ev if e[2] not in ('High Tide', 'Low Tide')]
        ev += [(t, h * fk, 'High Tide' if a == 'H' else 'Low Tide') for t, h, a in HU.vorhersage_kombi(hw, t0, t1)]
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
