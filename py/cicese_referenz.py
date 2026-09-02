#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Liest die Gezeitenvorhersagen des CICESE (Mexiko).

Das Centro de Investigacion Cientifica y de Educacion Superior de
Ensenada rechnet fuer eine Reihe mexikanischer Haefen und stellt je
Hafen und Monat ein PDF bereit. Unter tide_tables/mexico_cicese/ liegen
15 Orte fuer das ganze Jahr 2026 (drei weitere Ordner sind leer).

Diese Quelle ist bequemer als die SEMAR-Tafeln, weil sie alles selbst
mitliefert, was sonst zu erraten waere: die Position steht als
"(18 47 N, 095 46 W)" im Kopf, der Bezugsmeridian als "90 W.G.", und das
Bezugsniveau als "BMI" (bajamar media inferior).

Sie ist aber schwerer zu lesen, denn die Seite ist kein Tabellenwerk,
sondern ein Kalender mit eingezeichneter Tidekurve:

  Zeile mit Wochentagen
  Zeile mit den Tagesnummern der Woche      <- sieben Spalten, Abstand 84
  ... Kurvenbild mit Achsenbeschriftung ...
  Zeile mit den Uhrzeiten aller sieben Tage
  Zeile mit den zugehoerigen Hoehen in cm
  Zeile mit den Tagesnummern der naechsten Woche

Die Werte stehen also UNTER ihrer Tagesnummer, und dazwischen liegt das
Kurvenbild, dessen Achsen- und Streuziffern genauso aussehen wie Daten.
Das Zeilenpaar wird darum nicht ueber seine Lage gesucht, sondern ueber
seinen Inhalt: die obere Zeile muss durchweg gueltige Uhrzeiten
enthalten, die untere ebenso viele Zahlen, und beide muessen sich Spalte
fuer Spalte decken.

Usage: python3 py/cicese_referenz.py             Uebersicht
       python3 py/cicese_referenz.py <text>      einen Ort zeigen
"""
from __future__ import annotations

import collections
import datetime as dt
import glob
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CICESE = os.path.join(ROOT, 'tide_tables/mexico_cicese')

SPALTEN = 7
MONATE = ['ENERO', 'FEBRERO', 'MARZO', 'ABRIL', 'MAYO', 'JUNIO', 'JULIO',
          'AGOSTO', 'SEPTIEMBRE', 'OCTUBRE', 'NOVIEMBRE', 'DICIEMBRE']
# El Sauzal schreibt die Position ohne Komma zwischen Breite und
# Laenge -- das Trennzeichen ist deshalb wahlfrei.
POS = re.compile(r'\((\d{1,3})\s+(\d{1,2})\s*([NS]),?\s*(\d{1,3})\s+(\d{1,2})\s*([EW])\)')
MERID = re.compile(r'\b(\d{1,3})\s*([EW])\.\s*G\.', re.I)
UHR = re.compile(r'^([01]?\d|2[0-3])([0-5]\d)$')
HOEHE = re.compile(r'^-?\d{1,3}$')
TAGNR = re.compile(r'^([1-9]|[12]\d|3[01])$')

VON = dt.datetime(2026, 7, 1)
BIS = dt.datetime(2026, 8, 1)
JAHR = 2026


def _zeilen(seite):
    z = collections.defaultdict(list)
    for x0, y0, _x1, _y1, t, *_ in seite.get_text('words'):
        t = t.strip()
        if t:
            z[round(y0, 1)].append((x0, t))
    return {y: sorted(set(v)) for y, v in z.items()}


def _spalten(zeilen):
    """x-Anfaenge der sieben Tagesspalten aus der Wochentagszeile."""
    for _y, ws in sorted(zeilen.items()):
        tage = sorted(x for x, t in ws
                      if t in ('Dom', 'Lun', 'Mar', 'Mie', 'Jue', 'Vie', 'Sab'))
        if len(tage) == SPALTEN:
            # Die Wochentage stehen mittig ueber der Spalte, die Werte
            # linksbuendig darin. Der Versatz ist gleichmaessig; als
            # Spaltenanfang genuegt die Mitte zwischen zwei Kopfzeilen.
            pitch = (tage[-1] - tage[0]) / (SPALTEN - 1)
            return [t - pitch * 0.38 for t in tage], pitch
    return None, None


def _tagzeilen(zeilen, anfang, pitch):
    """[(y, {spalte: tag})] -- die Zeilen mit den Tagesnummern."""
    aus = []
    for y, ws in sorted(zeilen.items()):
        treffer = {}
        for x, t in ws:
            if not TAGNR.match(t):
                continue
            for i, a in enumerate(anfang):
                if -4 <= x - a <= 6:
                    treffer[i] = int(t)
        if not treffer:
            continue
        # Eine echte Tagreihe steigt von Spalte zu Spalte um genau eins.
        # Das Kurvenbild liefert Zeilen mit ebenso vielen Zahlen an
        # ebenso vielen Spalten -- im Oktober 2026 eine mit fuenf --,
        # aber ihre Werte fallen oder springen. Ohne diese Pruefung
        # verdirbt so eine Zeile das Raster, und von fuenf Wochen
        # bleiben zwei.
        sp = sorted(treffer)
        werte = [treffer[k] for k in sp]
        if sp != list(range(sp[0], sp[0] + len(sp))):
            continue
        if werte != list(range(werte[0], werte[0] + len(werte))):
            continue
        aus.append((y, treffer))
    # Im Kurvenbild stehen Ziffern, die zufaellig wie eine Tagesnummer an
    # einer Spaltenposition aussehen -- in Cozumel eine "11" dicht ueber
    # der echten Reihe mit dem 11. Ein Filter, der nur die Zahlenfolge
    # prueft, schluckt so einen Fund und bringt alles Weitere aus dem
    # Takt: dort blieben von fuenf Wochen zwei uebrig.
    #
    # Die echten Reihen liegen dagegen in festem senkrechtem Abstand
    # (76.4 Punkte, ueber alle Orte und Monate gleich). Massgebend sind
    # die Reihen mit mindestens fuenf Nummern -- die kann das Kurvenbild
    # nicht vortaeuschen --, und daraus ergibt sich das Raster, auf dem
    # die uebrigen liegen muessen.
    voll = [(y, tr) for y, tr in aus if len(tr) >= 5]
    if not voll:
        return []
    if len(voll) >= 2:
        abstaende = [b[0] - a[0] for a, b in zip(voll, voll[1:])]
        schritt = min(abstaende)
        for d in abstaende:
            # Bei einer ausgelassenen Woche ist der Abstand ein Vielfaches.
            k = round(d / schritt)
            if k and abs(d / k - schritt) < 2:
                schritt = min(schritt, d / k)
    else:
        schritt = 76.4
    anker = voll[0][0]
    raster = [(y, tr) for y, tr in aus
              if abs((y - anker) / schritt - round((y - anker) / schritt)) * schritt < 2.5]
    gut, erwartet = [], 1
    for y, tr in raster:
        werte = [tr[k] for k in sorted(tr)]
        if werte and werte[0] == erwartet and werte == list(
                range(werte[0], werte[0] + len(werte))):
            gut.append((y, tr))
            erwartet = werte[-1] + 1
    return gut


def _paare(zeilen, y_von, y_bis, anfang, pitch):
    """Alle (x, Uhrzeit, Hoehe) eines Wochenbands.

    Gepaart wird ueber die Lage, nicht ueber ganze Zeilen: ein Band kann
    mehrere Wertezeilen tragen (wo ein Tag mehr Ereignisse hat als die
    anderen, steht das zusaetzliche Paar allein weiter oben), und im
    Kurvenbild liegen Streuziffern, die wie Hoehen aussehen. Eine
    Uhrzeit gilt darum nur als Ereignis, wenn genau unter ihr -- fuenf
    bis neun Punkte tiefer, hoechstens sechs Punkte seitlich versetzt --
    eine Zahl steht.

    Ohne das fehlte dem 7. Januar in Alvarado das Hochwasser um 03:30:
    sein Paar steht als einziges in einer eigenen Zeile, in der zwei
    Streuziffern aus der Kurve mitschwimmen, und ein Vergleich ganzer
    Zeilenlaengen verwirft es.
    """
    innen = [(y, [(x, t) for x, t in ws
                  if anfang[0] - 6 <= x <= anfang[-1] + pitch])
             for y, ws in sorted(zeilen.items()) if y_von < y < y_bis]
    hoehen = [(y, x, t) for y, ws in innen for x, t in ws if HOEHE.match(t)]
    aus = []
    for y, ws in innen:
        for x, t in ws:
            if not UHR.match(t):
                continue
            partner = [(abs(xh - x), h) for yh, xh, h in hoehen
                       if 3 <= yh - y <= 9 and abs(xh - x) <= 6]
            if not partner:
                continue
            aus.append((x, t, int(min(partner)[1])))
    return aus


def _seite(seite):
    """-> (jahr, monat, [(tag, 'HHMM', hoehe_cm)], meridian, position)"""
    text = seite.get_text()
    zeilen = _zeilen(seite)
    anfang, pitch = _spalten(zeilen)
    if not anfang:
        return None
    mon = next((i for i, n in enumerate(MONATE, 1) if n in text.upper()), None)
    j = re.search(r'\b(20\d\d)\b', text.split('\n')[1] if '\n' in text else '')
    jahr = int(j.group(1)) if j else None
    # Der Meridian steht als "90 W.G." irgendwo im Text, weit weg von
    # seiner Beschriftung "Hora del Meridiano:" -- die beiden stehen
    # zwar nebeneinander auf dem Papier, aber nicht im Textfluss.
    m = MERID.search(text.replace('\n', ' '))
    md = int(m.group(1)) * (-1 if m.group(2).upper() == 'W' else 1) if m else None
    p = POS.search(text.replace('\n', ' '))
    pos = None
    if p:
        lat = int(p.group(1)) + int(p.group(2)) / 60.0
        lon = int(p.group(4)) + int(p.group(5)) / 60.0
        pos = (lat * (-1 if p.group(3).upper() == 'S' else 1),
               lon * (-1 if p.group(6).upper() == 'W' else 1))
    if not (mon and jahr):
        return None
    tz = _tagzeilen(zeilen, anfang, pitch)
    aus = []
    for k, (y, tr) in enumerate(tz):
        y_bis = tz[k + 1][0] if k + 1 < len(tz) else max(zeilen) + 1
        for x, t, h in _paare(zeilen, y, y_bis, anfang, pitch):
            sp = max(i for i, a in enumerate(anfang) if x >= a - 6)
            if sp not in tr:
                continue
            aus.append((tr[sp], t, h))
    return jahr, mon, aus, md, pos


def _datei_lesen(pfad):
    import pymupdf
    ev, md, pos = [], None, None
    with pymupdf.open(pfad) as d:
        for s in d:
            r = _seite(s)
            if not r:
                continue
            jahr, mon, werte, m, p = r
            if m is not None:
                md = m
            if p is not None:
                pos = p
            for tag, hhmm, h in werte:
                mm = UHR.match(hhmm)
                try:
                    z = dt.datetime(jahr, mon, tag, int(mm.group(1)), int(mm.group(2)))
                except (ValueError, AttributeError):
                    continue
                ev.append((z, h / 100.0))
    if md is None:
        return [], None, None
    # "Hora del Meridiano: 90 W.G." heisst UTC-6.
    versatz = dt.timedelta(hours=-md / 15.0)
    return sorted(set((z + versatz, h) for z, h in ev)), md, pos


_PUFFER = {}


def datei(pfad):
    if pfad not in _PUFFER:
        _PUFFER[pfad] = _datei_lesen(pfad)
    return _PUFFER[pfad]


def _kopfname(pfad):
    import pymupdf
    with pymupdf.open(pfad) as d:
        w = d[0].get_text('words')
    oben = [t for _x, y, _a, _b, t, *_ in sorted(w, key=lambda q: q[0])
            if y < 40]
    return ' '.join(oben).strip()


def stationen():
    aus = []
    for ordner in sorted(os.listdir(CICESE)):
        ps = sorted(glob.glob(os.path.join(CICESE, ordner, '*.pdf')))
        if not ps:
            continue
        ev, md, pos = datei(ps[0])
        aus.append({'code': ordner, 'tafel': _kopfname(ps[0]),
                    'lat': pos[0] if pos else None,
                    'lon': pos[1] if pos else None,
                    'meridian': md, 'dateien': ps})
    return aus


def ereignisse(st, von=None, bis=None):
    import dhn_qualitaet
    ev = []
    for p in st['dateien']:
        e, _md, _pos = datei(p)
        ev += [(z, h) for z, h in e
               if (not von or z >= von) and (not bis or z < bis)]
    return dhn_qualitaet.art_bestimmen(sorted(set(ev)))


def vorhersage(st):
    return ereignisse(st, VON, BIS)


def jahresreihe(st):
    ev = []
    for p in st['dateien']:
        e, _md, _pos = datei(p)
        ev += [(z, h) for z, h in e
               if dt.datetime(JAHR, 1, 1) <= z < dt.datetime(JAHR + 1, 1, 1)]
    return sorted(set(ev))


def main(argv):
    nur = next((a for a in argv if not a.startswith('--')), None)
    st = stationen()
    if not nur:
        print(f'{len(st)} Orte')
        for s in st:
            j = jahresreihe(s)
            tage = len({z.date() for z, _h in j})
            ort = (f'{s["lat"]:8.4f} {s["lon"]:9.4f}' if s['lat'] is not None
                   else '   (keine Position)')
            print(f'  {s["code"]:6} {s["tafel"][:30]:30} {ort}  '
                  f'{str(s["meridian"]):>4}  '
                  f'{len(j):5} Ereignisse an {tage:3} Tagen  '
                  f'({len(s["dateien"])} Monate)')
        return 0
    for s in st:
        if nur.lower() not in s['code'] and nur.lower() not in s['tafel'].lower():
            continue
        j = jahresreihe(s)
        print(f'{s["tafel"]}  {s["lat"]:.4f} {s["lon"]:.4f}  '
              f'Meridian {s["meridian"]}  {len(j)} Ereignisse')
        for z, h in j[:6]:
            print(f'   {z:%Y-%m-%d %H:%M} UTC  {h:6.2f} m')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
