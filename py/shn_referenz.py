#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Liest die Gezeitentafeln des argentinischen SHN.

Der Bestand unter tide_tables/argentina/shn/parsed/ ist schon geparst: je
Station eine JSON-Datei mit Position, Zonenversatz und den Hoch- und
Niedrigwassern von 2024 und 2025. Damit ist Argentinien die bequemste
Quelle im ganzen Bestand -- nichts zu lesen, nichts zu erraten.

Zwei Dinge sind zu richten:

Die Namen stehen als UTF-8, das einmal als Latin-1 gelesen wurde
("BAHÃ\x8dA" statt "BAHÍA"). Das laesst sich sauber zurueckdrehen; wo es
nicht aufgeht, bleibt der Name stehen, wie er ist.

Die Zeiten sind Ortszeit. Der Versatz steht in tz_offset_h (durchweg -3);
UTC ist also Ortszeit plus drei Stunden. Argentinien hat seit 2009 keine
Sommerzeit, der Versatz gilt das ganze Jahr.

Verglichen wird der Juli 2025 -- der letzte volle Juli der Reihe. Fuer
einen Neufit steht ein ganzes Jahr zur Verfuegung (2025), was noetig ist:
ein Monat mit 120 Extremwerten trennt K2 nicht von S2.

Usage: python3 py/shn_referenz.py                 Uebersicht
       python3 py/shn_referenz.py <name|code>     eine Station zeigen
"""
from __future__ import annotations

import datetime as dt
import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PARSED = os.path.join(ROOT, 'tide_tables/argentina/shn/parsed')

# Vergleichsmonat und Fit-Jahr.
VON = dt.datetime(2025, 7, 1)
BIS = dt.datetime(2025, 8, 1)
JAHR = 2025


def _text(s):
    """UTF-8, das als Latin-1 gelesen wurde, zurueckdrehen."""
    try:
        return s.encode('latin-1').decode('utf-8')
    except (UnicodeEncodeError, UnicodeDecodeError):
        return s


def _lade(pfad):
    d = json.load(open(pfad, encoding='utf-8'))
    m = d.get('meta') or {}
    return {
        'code': d.get('code') or os.path.basename(pfad)[:-5],
        'name': _text(d.get('name') or ''),
        'lat': m.get('lat'), 'lon': m.get('lon'),
        'tz': m.get('tz_offset_h'),
        'regimen': _text(m.get('regimen') or ''),
        'entries': d.get('entries') or [],
    }


def stationen():
    """Alle SHN-Stationen mit Position und Reihe."""
    aus = []
    for p in sorted(glob.glob(os.path.join(PARSED, '*.json'))):
        s = _lade(p)
        if s['lat'] is None or s['lon'] is None or not s['entries']:
            continue
        aus.append(s)
    return aus


def reihe(st, von=None, bis=None):
    """-> [(datetime UTC, hoehe_m)], nach Zeit sortiert.

    tz_offset_h ist der Versatz der Ortszeit gegen UTC (-3). UTC ist also
    Ortszeit minus diesem Versatz, hier: plus drei Stunden.
    """
    versatz = dt.timedelta(hours=st['tz'] or 0)
    aus = []
    for z, h in st['entries']:
        try:
            t = dt.datetime.strptime(z, '%Y-%m-%dT%H:%M:%S') - versatz
        except (TypeError, ValueError):
            continue
        if von and t < von:
            continue
        if bis and t >= bis:
            continue
        aus.append((t, float(h)))
    return sorted(set(aus))



def _extrema(reihe, schritt_h=1.0):
    """Hoch- und Niedrigwasser aus einer stuendlichen Reihe.

    28 der 66 Stationen liefern nicht die Kenterpunkte, sondern den
    Wasserstand zu jeder vollen Stunde (17 544 Werte fuer zwei Jahre).
    Der hoechste Stundenwert ist aber nicht das Hochwasser: bei
    halbtaegiger Tide liegt der Scheitel im Mittel eine Viertelstunde
    neben der vollen Stunde. Darum wird durch die Werte um jeden
    Umkehrpunkt eine Parabel gelegt und deren Scheitel genommen.

    Auf Gleichstand zu achten ist dabei nicht Feinschliff, sondern die
    halbe Ernte: die Reihe ist auf Zentimeter gerundet, und um den
    Scheitel aendert sich in einer Stunde oft nichts mehr. In Atalaya
    stehen um 18 und 19 Uhr beide 0.51 m. Wer den Umkehrpunkt mit
    strengem Groesser-als sucht, uebersieht dort 28 von 44 Ereignissen.
    Ein solches Plateau wird als Ganzes genommen und sein Scheitel in
    die Mitte gelegt.

    Luecken werden uebersprungen: gezaehlt wird nur, was lueckenlos von
    beiden Seiten eingerahmt ist.
    """
    aus = []
    n = len(reihe)
    i = 1
    while i < n - 1:
        h0 = reihe[i - 1][1]
        j = i
        while j + 1 < n and reihe[j + 1][1] == reihe[i][1]:
            j += 1              # Plateau gleicher Werte
        if j + 1 >= n:
            break
        h1, h2 = reihe[i][1], reihe[j + 1][1]
        hoch = h1 > h0 and h1 > h2
        tief = h1 < h0 and h1 < h2
        if not (hoch or tief):
            i = j + 1
            continue
        # Lueckenlos? Der Abstand muss ueberall der Schritt sein.
        soll = dt.timedelta(hours=schritt_h)
        if any(reihe[k + 1][0] - reihe[k][0] != soll for k in range(i - 1, j + 1)):
            i = j + 1
            continue
        # Scheitel: Parabel durch die drei Punkte um die Plateaumitte.
        # Vor und nach der Mitte liegt derselbe Abstand, sobald das
        # Plateau symmetrisch eingerahmt ist -- das ist es hier immer,
        # weil h0 und h2 die ersten abweichenden Werte sind.
        breite = (j - i) / 2.0 + 1.0            # in Schritten
        mitte = reihe[i][0] + dt.timedelta(hours=(j - i) / 2.0 * schritt_h)
        nenner = h0 - 2 * h1 + h2
        if abs(nenner) < 1e-9:
            z, h = mitte, h1
        else:
            d = 0.5 * (h0 - h2) / nenner        # in Einheiten von breite
            d = max(-0.5, min(0.5, d))
            z = mitte + dt.timedelta(hours=d * breite * schritt_h)
            h = h1 - 0.25 * (h0 - h2) * d
        aus.append((z, h, 'High' if hoch else 'Low'))
        i = j + 1
    return aus


def _schritt(reihe):
    """Haeufigster Zeitabstand der Reihe in Stunden."""
    import collections
    c = collections.Counter((b[0] - a[0]).total_seconds() / 3600.0
                            for a, b in zip(reihe, reihe[1:]))
    return c.most_common(1)[0][0] if c else 0.0


def stuendlich(st):
    """Liefert die Station Stundenwerte statt Kenterpunkte?"""
    r = st.get('_schritt')
    if r is None:
        r = st['_schritt'] = _schritt(reihe(st)[:400])
    return 0.0 < r <= 1.5


def ereignisse(st, von=None, bis=None):
    """-> [(zeit UTC, hoehe, 'High'|'Low')] -- einheitlich fuer beide Arten.

    Bei den Kenterpunkt-Stationen wird die Art aus den Nachbarwerten
    bestimmt, bei den stuendlichen aus der Parabel um den Umkehrpunkt.
    Ein Rand geht dabei jeweils verloren; deshalb wird bei den
    stuendlichen etwas grosszuegiger gelesen und danach beschnitten.
    """
    import dhn_qualitaet
    if not stuendlich(st):
        return dhn_qualitaet.art_bestimmen(reihe(st, von, bis))
    rand = dt.timedelta(hours=3)
    roh = reihe(st, von - rand if von else None, bis + rand if bis else None)
    ev = _extrema(roh, _schritt(roh) or 1.0)
    return [e for e in ev
            if (not von or e[0] >= von) and (not bis or e[0] < bis)]


def vorhersage(st):
    """Der Vergleichsmonat, als Hoch- und Niedrigwasser."""
    return ereignisse(st, VON, BIS)


def jahresreihe(st):
    """Ein volles Jahr fuer den Neufit, als (zeit, hoehe).

    Die stuendlichen Stationen werden dabei nicht auf ihre Scheitel
    eingedampft: utide kommt mit der vollen Reihe besser zurecht als mit
    den daraus abgeleiteten Extremwerten, und sie ist ohnehin da.
    """
    return reihe(st, dt.datetime(JAHR, 1, 1), dt.datetime(JAHR + 1, 1, 1))


def main(argv):
    nur = next((a for a in argv if not a.startswith('--')), None)
    st = stationen()
    if not nur:
        print(f'{len(st)} Stationen unter {os.path.relpath(PARSED, ROOT)}')
        zonen = sorted({s['tz'] for s in st})
        print(f'Zonenversaetze: {zonen}')
        for s in st:
            v = vorhersage(s)
            print(f"  {s['code']:5} {s['name'][:40]:40} {s['lat']:9.4f} "
                  f"{s['lon']:9.4f}  {'stuendlich' if stuendlich(s) else 'HW/NW':10} "
                  f"{len(v):3} Ereignisse im Juli")
        return 0
    for s in st:
        if nur.lower() not in s['name'].lower() and nur.upper() != s['code']:
            continue
        v = vorhersage(s)
        print(f"{s['name']} ({s['code']})  {s['lat']:.4f} {s['lon']:.4f}  "
              f"UTC{s['tz']:+d}  {s['regimen']}")
        print(f"  {len(v)} Ereignisse im Vergleichsmonat, "
              f"{len(jahresreihe(s))} im Jahr {JAHR}")
        for z, h, a in v[:4]:
            print(f'   {z:%Y-%m-%d %H:%M} UTC  {h:6.3f} m  {a}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
