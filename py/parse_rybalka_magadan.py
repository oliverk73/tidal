#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Parser fuer die Gezeitentabellen von rybalka-magadan.ru (Bucht Gertnera).

Quelle: https://rybalka-magadan.ru/tablica_prilivov_i_otlivov.html
(abgetippte Kolymskoe-UGMS-Tabellen, HW/LW-Zeiten + Hoehen in m,
Magadan-Zeit = UTC+11, kein DST). Spalten je Tag: LW HW LW HW LW.

WICHTIG: Die Tabellen gelten fuer die Bucht Gertnera; laut Korrektur-
tabelle der Seite ist Bezugsort der Poprawki die Bucht Nagaeva mit
Gertnera = -11 min (d.h. Nagaeva = Gertnera + 11 min).

Output: JSON-Liste [{"t": "YYYY-MM-DD HH:MM" (UTC), "h": float, "type": "H"|"L"}]
"""
import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

HTML = Path('/home/oliver/water_levels/RU_magadan/rybalka_tablica_prilivov_2025_2026.html')
OUT = Path('/home/oliver/water_levels/RU_magadan/gertnera_events_utc.json')

MONTHS = {'январ': 1, 'феврал': 2, 'март': 3, 'апрел': 4, 'ма': 5, 'июн': 6,
          'июл': 7, 'август': 8, 'сентябр': 9, 'октябр': 10, 'ноябр': 11, 'декабр': 12}
HEAD_RE = re.compile(r'(Январ|Феврал|Март|Апрел|Ма[йя]|Июн|Июл|Август|Сентябр|Октябр|Ноябр|Декабр)[ьяй]*\s*(20\d\d)')
ROW_RE = re.compile(r'<tr[^>]*>(.*?)</tr>', re.S)
CELL_RE = re.compile(r'<t[dh][^>]*>(.*?)</t[dh]>', re.S)
TIME_RE = re.compile(r'(\d{1,2})[:.](\d{2})\b')
HGT_RE = re.compile(r'\(\s*(-?\d+(?:[.,]\d+)?)\s*\)')
UTC_OFFSET = timedelta(hours=11)

# Manuelle Korrekturen offensichtlicher Tippfehler der Quelle
# (Jahr, Monat, Tag, 'HH:MM'): neue Zeit oder None = Event verwerfen
FIXES = {
    (2025, 8, 31, '17:45'): '07:45',  # Stundendreher: bricht Alternation, 07:45 passt exakt
    (2026, 4, 13, '14:39'): None,     # Geister-HW 2.7m am Nipptag, LW 17:42 waere 3.7m > HW
}
# Typ-Korrekturen: Event steht in falscher Spalte der Quelle
TYPE_FIXES = {
    (2026, 4, 13, '17:42'): 'H',      # 3.7m ist das Abend-HW, stand in LW-Spalte
}


def month_of(name):
    low = name.lower()
    for k, v in MONTHS.items():
        if low.startswith(k) and not (k == 'ма' and low.startswith('март')):
            return v
    raise ValueError(name)


def strip_tags(s):
    return re.sub(r'<[^>]+>', ' ', s)


def parse():
    txt = HTML.read_text(encoding='utf-8')
    heads = [(m.start(), month_of(m.group(1)), int(m.group(2))) for m in HEAD_RE.finditer(txt)]
    tables = [(m.start(), m.group(0)) for m in re.finditer(r'<table.*?</table>', txt, re.S)]

    events = []
    seen_months = set()
    for tpos, ttxt in tables:
        # zugehoerige Ueberschrift: letzte vor der Tabelle
        prior = [h for h in heads if h[0] < tpos]
        if not prior:
            continue
        _, mon, year = prior[-1]
        if (year, mon) in seen_months:
            continue
        rows = ROW_RE.findall(ttxt)
        n_ev = 0
        for row in rows:
            cells = [strip_tags(c) for c in CELL_RE.findall(row)]
            if not cells:
                continue
            mday = re.match(r'\s*(\d{1,2})\b', cells[0])
            if not mday:
                continue
            day = int(mday.group(1))
            # Event-Zellen: Reihenfolge LW HW LW HW LW (Header der Tabelle)
            kinds = ['L', 'H', 'L', 'H', 'L']
            ki = 0
            for c in cells[1:]:
                tm = TIME_RE.search(c)
                hm = HGT_RE.search(c)
                if tm and hm and ki < len(kinds):
                    hh, mi = int(tm.group(1)), int(tm.group(2))
                    key = (year, mon, day, f'{hh:02d}:{mi:02d}')
                    if key in FIXES:
                        if FIXES[key] is None:
                            ki += 1
                            continue
                        hh, mi = map(int, FIXES[key].split(':'))
                    h = float(hm.group(1).replace(',', '.'))
                    dt_loc = datetime(year, mon, day, hh, mi)
                    kind = TYPE_FIXES.get((year, mon, day, f'{hh:02d}:{mi:02d}'), kinds[ki])
                    events.append({'t': (dt_loc - UTC_OFFSET).strftime('%Y-%m-%d %H:%M'),
                                   'h': h, 'type': kind})
                    ki += 1
                    n_ev += 1
                elif re.search(r'-\s*$|^\s*-', c) and not tm:
                    ki += 1  # leerer Slot
        if n_ev:
            seen_months.add((year, mon))
            print(f'{year}-{mon:02d}: {n_ev} Events')

    events.sort(key=lambda e: e['t'])
    # Plausibilitaet: H > L im Mittel, monotone Zeiten, Abstaende 3..9 h
    hs = [e['h'] for e in events if e['type'] == 'H']
    ls = [e['h'] for e in events if e['type'] == 'L']
    print(f'Gesamt: {len(events)} Events, HW mean={sum(hs)/len(hs):.2f} m, LW mean={sum(ls)/len(ls):.2f} m')
    bad = 0
    for a, b in zip(events, events[1:]):
        gap = (datetime.strptime(b['t'], '%Y-%m-%d %H:%M') - datetime.strptime(a['t'], '%Y-%m-%d %H:%M')).total_seconds() / 3600
        if not 2.0 <= gap <= 14.0:
            print('  Luecke/Anomalie:', a['t'], '->', b['t'], f'{gap:.1f}h')
            bad += 1
        if a['type'] == b['type']:
            print('  Doppel-Typ:', a, b)
            bad += 1
    print(f'Anomalien: {bad}')
    OUT.write_text(json.dumps(events, indent=1))
    print('->', OUT)


if __name__ == '__main__':
    parse()
