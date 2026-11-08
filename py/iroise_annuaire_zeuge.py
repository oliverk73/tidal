#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Zeugenprobe: Annuaire des marees 2026 (Parc naturel marin d'Iroise / OFB, SHOM-Autorisation 2025-295).

Das Heft enthaelt die SHOM-Vorhersage Brest 2026 (PM/BM, heure legale, Koeffizient) und eine Korrekturtabelle
fuer 8 Haefen (Zeit/Hoehe fuer PM/BM bei Koeffizient 95 und 45). Geprueft wird, ob unsere Saetze an diesen
Haefen gegenueber der Brest-Tafel dieselben Unterschiede zeigen.

Verfahren: PM/BM unserer Saetze mit `tide` (UTC) -> Europe/Paris; jedem Ereignis das gleichartige Brest-Ereignis
der Tafel (+-3 h) zuordnen; Koeffizient = der Brest-PM (bei BM die naechste PM). Klassen 95 = Koeff. 88-102,
45 = 38-52. Median von dt und dh je Klasse; zusaetzlich Tidenhub-Unterschied (PM-BM), der vom Kartennull
unabhaengig ist. Auch die beiden Brest-Saetze werden gegen die Tafel gemessen (Erwartung 0).

Usage: venv/bin/python py/iroise_annuaire_zeuge.py
"""
import datetime as dt
import os
import re
import statistics as st
import subprocess
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PDF = os.path.join(ROOT, 'tide_tables/france/AnnuaireMaree2026_WEB_PAGE.pdf')
PARIS, UTC = ZoneInfo('Europe/Paris'), dt.timezone.utc
MONATE = ['JANVIER', 'FÉVRIER', 'MARS', 'AVRIL', 'MAI', 'JUIN', 'JUILLET', 'AOÛT', 'SEPTEMBRE', 'OCTOBRE',
          'NOVEMBRE', 'DÉCEMBRE']
# Tabelle S. 3: PM95 PM45 BM45 BM95 (min) | PM95 PM45 BM45 BM95 (cm)
TAB = {
    'Camaret-sur-Mer, France': ((-10, -10, -10, -15), (-45, -35, -25, -15), 'Camaret-sur-Mer'),
    'Morgat, France': ((-5, -10, -10, -20), (-40, -30, -15, -10), 'Morgat'),
    "L'Aber Ildut, France": ((15, 10, 15, 15), (30, 25, -5, -15), "L'Aber Ildut"),
    'Le Conquet, France': ((0, 0, 5, 5), (-20, -15, -10, -5), 'Le Conquet'),
    'Douarnenez, France': ((-10, -10, -10, -20), (-50, -45, -25, -20), 'Douarnenez'),
    'Île-Molène, France': ((10, 15, 20, 20), (25, 30, 15, 10), 'Île de Molène'),
    "Baie du Stiff (Île d'Ouessant), France": ((15, 15, 20, 15), (10, 15, -5, -15), 'Baie du Stiff'),
    "Baie de Lampaul (Île d'Ouessant), France": ((15, 15, 20, 15), (10, 15, -5, -15), 'Stiff-Werte (Lampaul 4 km)'),
    'Île de Sein, France': ((-5, -10, -5, -15), (-85, -65, -35, -20), 'Île de Sein'),
    'Brest (Estuaire Penfeld), France': ((0, 0, 0, 0), (0, 0, 0, 0), 'Brest Messung'),
    'Brest (Moulin Blanc), France': ((0, 0, 0, 0), (0, 0, 0, 0), 'Brest Tafel'),
}
ZEILE = re.compile(r'^\s*(\d{1,2})[LMJVSD]\s+(.*)$')


def brest_tafel():
    txt = subprocess.run(['pdftotext', '-layout', PDF, '-'], capture_output=True, text=True).stdout
    ev, monat = [], None
    for l in txt.split('\n'):
        if 'Brest (Finist' in l:
            m = [x for x in MONATE if re.search(r'\b%s\b' % x, l)]
            if m:
                monat = MONATE.index(m[0]) + 1
            continue
        z = ZEILE.match(l)
        if not monat or not z:
            continue
        tag, rest = int(z.group(1)), z.group(2).split()
        # PM: (h, hoehe, coef) x2, BM: (h, hoehe) x2  -- fehlende als --:-- / ---
        if len(rest) < 10:
            continue
        pm = [(rest[0], rest[1], rest[2]), (rest[3], rest[4], rest[5])]
        bm = [(rest[6], rest[7]), (rest[8], rest[9])]
        for h, hh, c in pm:
            if ':' in h and '-' not in h:
                t = dt.datetime(2026, monat, tag, int(h[:2]), int(h[3:]), tzinfo=PARIS)
                ev.append(('H', t, float(hh), int(c)))
        for h, hh in bm:
            if ':' in h and '-' not in h:
                t = dt.datetime(2026, monat, tag, int(h[:2]), int(h[3:]), tzinfo=PARIS)
                ev.append(('L', t, float(hh), None))
    ev.sort(key=lambda e: e[1])
    pms = [e for e in ev if e[0] == 'H']
    out = []
    for e in ev:
        c = e[3] if e[0] == 'H' else min(pms, key=lambda p: abs((p[1] - e[1]).total_seconds()))[3]
        out.append((e[0], e[1], e[2], c))
    return out


def unsere(name):
    r = subprocess.run([b'tide', b'-l', name.encode('iso-8859-1'), b'-z', b'-f', b'c', b'-m', b'p',
                        b'-b', b'2026-01-01 00:00', b'-e', b'2027-01-01 00:00'],
                       capture_output=True).stdout.decode('iso-8859-1')   # TCD-Namen sind Latin-1
    ev = []
    for l in r.split('\n'):
        p = l.split(',')
        if len(p) >= 5 and p[4].strip() in ('High Tide', 'Low Tide'):
            t = dt.datetime.strptime(p[1] + ' ' + p[2].replace(' UTC', ''), '%Y-%m-%d %I:%M %p').replace(tzinfo=UTC)
            ev.append(('H' if p[4].startswith('High') else 'L', t.astimezone(PARIS), float(p[3].split()[0])))
    return ev


def main():
    B = brest_tafel()
    print('Brest-Tafel: %d PM, %d BM' % (sum(e[0] == 'H' for e in B), sum(e[0] == 'L' for e in B)))
    print('%-42s %-6s %18s %18s %18s %18s   Hub95 Hub45' % ('Satz', '', 'PM95', 'PM45', 'BM45', 'BM95'))
    for name, (tz, hz, quelle) in TAB.items():
        U = unsere(name)
        if not U:
            print('%-42s nicht gefunden' % name)
            continue
        kl = {('H', 95): [], ('H', 45): [], ('L', 45): [], ('L', 95): []}
        for typ, t, h in U:
            kand = [b for b in B if b[0] == typ and abs((b[1] - t).total_seconds()) < 3 * 3600]
            if not kand:
                continue
            b = min(kand, key=lambda b: abs((b[1] - t).total_seconds()))
            k = 95 if 88 <= b[3] <= 102 else 45 if 38 <= b[3] <= 52 else None
            if k:
                kl[(typ, k)].append(((t - b[1]).total_seconds() / 60, 100 * (h - b[2])))
        reihe = [('H', 95), ('H', 45), ('L', 45), ('L', 95)]
        zel = []
        med = {}
        for i, key in enumerate(reihe):
            v = kl[key]
            if not v:
                zel.append('%18s' % '-')
                continue
            mdt, mdh = st.median(x[0] for x in v), st.median(x[1] for x in v)
            med[key] = (mdt, mdh)
            zel.append('%+4.0f(%+3d)m %+4.0f(%+3d)cm' % (mdt, tz[i], mdh, hz[i]))
        hub = []
        for k in (95, 45):
            if ('H', k) in med and ('L', k) in med:
                ist = med[('H', k)][1] - med[('L', k)][1]
                soll = hz[reihe.index(('H', k))] - hz[reihe.index(('L', k))]
                hub.append('%+4.0f(%+3d)' % (ist, soll))
        print('%-42s %-6s %s   %s   [%s]' % (name[:42], '', ' '.join(zel), ' '.join(hub), quelle))
    print('\nFormat: unser Median (Tabelle). Zeiten in min, Hoehen in cm; Hub = (PM-BM)-Unterschied, nullpunktfrei.')


if __name__ == '__main__':
    main()
