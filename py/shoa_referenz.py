#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Liest die gespeicherten Gezeitentafeln des chilenischen SHOA.

Der SHOA veroeffentlicht seine Tafeln nur ueber ein Formular
(www.shoa.cl/php/mareas.php, POST mit local/mes/ano). Jeder Abruf aus
einem Skript beantwortet die Seite mit 405 und einer
Human-Verification-Seite -- auch mit Browser-Kopfzeilen, auch per GET.
Das ist der ausdrueckliche Wille der Seite; sie wird nicht umgangen.
Verarbeitet wird deshalb nur, was unter tide_tables/chile/ von Hand
gespeichert wurde: 20 Orte mit je drei Monaten (Mai bis Juli 2026).

Zwei Dinge macht der SHOA angenehm einfach. Die Seite nennt ihre
Zeitzone selbst und ohne Ausnahmen: UTC-4 fuer Kontinentalchile
EINSCHLIESSLICH der Region Magallanes und der Antarktis, UTC-6 nur fuer
die Osterinsel. Damit entfaellt die uebliche Sorge um Sommerzeit und um
das abweichende Magallanes. Und die Hoehen sind mit B (bajamar) und P
(pleamar) beschriftet, die Art muss also nicht aus den Nachbarwerten
erschlossen werden.

Die Position steht nicht in der Tafel. Sie wird aus dem Bestand
genommen, wo jeder dieser Orte einen gleichnamigen Satz hat (ORTE).
Das ist kein Zirkelschluss: gemessen wird die Kurve, nicht die Lage.

Usage: python3 py/shoa_referenz.py             Uebersicht
       python3 py/shoa_referenz.py <text>      einen Ort zeigen
"""
from __future__ import annotations

import datetime as dt
import glob
import os
import re
import sys
import unicodedata

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHILE = os.path.join(ROOT, 'tide_tables/chile')

# Ordner- bzw. Dateikuerzel -> (Name im Bestand, Zonenversatz)
# Der Versatz ist ueberall -4; nur die Osterinsel haette -6, von ihr
# liegt aber keine Tafel vor.
ORTE = {
    'angostura inglesa canal messier':
        ('Angostura Inglesa, Canal Messier, Chile', -4),
    'bahia cumberland isla robinson crusoe':
        ('Bahía Cumberland (Isla Robinson Crusoe), Chile', -4),
    'base frei bahia fildes isla rey jorge':
        ('Base Frei (Bahía Fildes, Isla Rey Jorge), Chile', -4),
    "base gonzalez videla bahia paraiso peninsula tierra o higgins":
        ('Base González Videla (Bahía Paraíso), Chile', -4),
    "base o higgins rada covadonga peninsula tierra o higgins":
        ("Base O'Higgins (Rada Covadonga), Chile", -4),
    'base prat bahia chile isla greenwich':
        ('Base Prat (Bahía Chile, Isla Greenwich), Chile', -4),
    'base risopatron caleta cooper mine isla robert':
        ('Base Risopatrón (Caleta Cooper Mine, Isla Robert), Chile', -4),
    'base yelcho bahia sur isla doumer':
        ('Base Yelcho (Bahía Sur, Isla Doumer), Chile', -4),
    'caleta balleneros isla decepcion':
        ('Caleta Balleneros (Isla Decepción), Chile', -4),
    'caleta meteoro estrecho de magallanes':
        ('Caleta Meteoro, Estrecho de Magallanes, Chile', -4),
    'caleta percy bahia gente grande':
        ('Caleta Percy, Bahía Gente Grande, Chile', -4),
    'caleta snow isla snow': ('Caleta Snow (Isla Snow), Chile', -4),
    'constitucion': ('Constitución, Río Maule entrance, Chile', -4),
    'corral': ('Corral, Bahía Corral, Chile', -4),
    'mejillones del sur': ('Mejillones del Sur, Chile', -4),
    'puerto chacao': ('Puerto Chacao, Chile', -4),
    'puerto natales': ('Puerto Natales, Chile', -4),
    'punta delgada estrecho de magallanes':
        ('Punta Delgada, Estrecho de Magallanes, Chile', -4),
    'quintero': ('Quintero, Chile', -4),
    'valdivia rio calle calle': ('Valdivia (Río Calle-Calle), Chile', -4),
}

ZEILE = re.compile(r'<tr[^>]*>(.*?)</tr>', re.S | re.I)
ZELLE = re.compile(r'<t[dh][^>]*>(.*?)</t[dh]>', re.S | re.I)
DATUM = re.compile(r'^(\d{2})/(\d{2})/(\d{4})$')
UHR = re.compile(r'^(\d{1,2}):(\d{2})$')
HOEHE = re.compile(r'^(-?\d+[.,]\d+)\s*([BP])$')


def _sl(s):
    t = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode().lower()
    return re.sub(r'[^a-z0-9]+', ' ', t).strip()


def _schluessel(pfad):
    """Ortskuerzel aus dem Pfad -- die Tafel selbst nennt ihn nicht.

    Die gespeicherte Seite enthaelt die ganze Ortsliste des Formulars,
    aber ohne Markierung, welcher Ort gewaehlt war. Der Ordner- bzw.
    Dateiname traegt ihn.
    """
    d = os.path.basename(os.path.dirname(pfad))
    if d != 'chile':
        return _sl(d)
    n = os.path.splitext(os.path.basename(pfad))[0]
    n = re.sub(r'_\d{4}-\d{2}$', '', n)
    n = re.sub(r'^shoa_', '', n)
    n = re.sub(r'^Shoa __ Pron.*?Mareas_?', '', n)
    return _sl(n)


def _ereignisse(pfad, versatz):
    """-> [(datetime UTC, hoehe, 'High'|'Low')]"""
    h = open(pfad, encoding='utf-8', errors='replace').read()
    aus = []
    for z in ZEILE.findall(h):
        z = [re.sub(r'<[^>]+>', '', c).replace('&nbsp;', ' ').strip()
             for c in ZELLE.findall(z)]
        if not z:
            continue
        m = DATUM.match(z[0])
        if not m:
            continue
        tag = dt.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        for i in range(1, len(z) - 1, 2):
            u, w = UHR.match(z[i]), HOEHE.match(z[i + 1])
            if not (u and w):
                continue
            t = dt.datetime.combine(tag, dt.time(int(u.group(1)), int(u.group(2))))
            aus.append((t - dt.timedelta(hours=versatz),
                        float(w.group(1).replace(',', '.')),
                        'High' if w.group(2) == 'P' else 'Low'))
    return aus


def stationen():
    """-> [{'code','name','lat','lon','tz','dateien'}] mit Position."""
    import health_check
    # Mehrere Dateien fuehren denselben Namen. Damit die Position
    # reproduzierbar ist und nicht davon abhaengt, welche Datei zuletzt
    # gelesen wurde, gilt die Reihenfolge in VORRANG.
    VORRANG = ('harmonics_utide_tidetables.txt', 'harmonics_utide_chile_shoa.txt',
               'harmonics_utide_observations.txt')
    recs = {}
    for r in health_check.load_records():
        if r['lat'] is None or r['current']:
            continue
        d = os.path.basename(r['file'])
        rang = VORRANG.index(d) if d in VORRANG else len(VORRANG)
        vor = recs.get(r['name'])
        if vor is None or rang < vor[0]:
            recs[r['name']] = (rang, r)
    recs = {k: v[1] for k, v in recs.items()}
    nach = {}
    for p in glob.glob(os.path.join(CHILE, '**', '*.htm*'), recursive=True):
        if '_files' in p:
            continue
        nach.setdefault(_schluessel(p), []).append(p)
    aus = []
    for k, ps in sorted(nach.items()):
        if k not in ORTE:
            continue
        name, tz = ORTE[k]
        r = recs.get(name)
        if r is None:
            continue
        aus.append({'code': k, 'name': name, 'lat': r['lat'], 'lon': r['lon'],
                    'tz': tz, 'dateien': sorted(ps)})
    return aus


def vorhersage(st):
    """Alle Ereignisse aller Monate dieses Orts, in UTC."""
    ev = []
    for p in st['dateien']:
        ev += _ereignisse(p, st['tz'])
    return sorted(set(ev))


def main(argv):
    nur = next((a for a in argv if not a.startswith('--')), None)
    st = stationen()
    fehlend = set(ORTE) - {s['code'] for s in st}
    if not nur:
        print(f'{len(st)} Orte mit Tafeln')
        for s in st:
            v = vorhersage(s)
            spanne = (f'{min(z for z, _h, _a in v):%Y-%m-%d} bis '
                      f'{max(z for z, _h, _a in v):%Y-%m-%d}') if v else '-'
            print(f'  {s["name"][:48]:48} {s["lat"]:8.4f} {s["lon"]:9.4f}  '
                  f'{len(v):4} Ereignisse  {spanne}')
        if fehlend:
            print(f'\nohne Position im Bestand: {sorted(fehlend)}')
        return 0
    for s in st:
        if _sl(nur) not in s['code'] and nur.lower() not in s['name'].lower():
            continue
        v = vorhersage(s)
        print(f'{s["name"]}  {s["lat"]:.4f} {s["lon"]:.4f}  UTC{s["tz"]:+d}  '
              f'{len(v)} Ereignisse')
        for z, h, a in v[:4]:
            print(f'   {z:%Y-%m-%d %H:%M} UTC  {h:6.2f} m  {a}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
