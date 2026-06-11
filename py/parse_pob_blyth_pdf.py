#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Port-of-Blyth-Tidenkalender (POB Tide Table Booklet) -> HW/LW-JSON.

Layout: 1 Seite/Monat, Zeile = '<d> <Day> <HWam> <HWpm> <d> <Day> <LWam> <LWpm>',
fehlende Events als '--:-- - - -'. Zeiten GMT GANZJAEHRIG (Booklet-Fussnote:
"TO OBTAIN B.S.T., ONE HOUR SHOULD BE ADDED") -> direkt UTC.
Hoehen in m ueber LAT (= Blyth CD, 2.60 m unter ODN).
Vorhersagen: Proudman Oceanographic Laboratory.

Usage: python3 py/parse_pob_blyth_pdf.py <booklet.pdf> <jahr> <out.json>
"""
import json
import re
import sys

import pdfplumber

MONTHS = ['JANUARY', 'FEBRUARY', 'MARCH', 'APRIL', 'MAY', 'JUNE', 'JULY',
          'AUGUST', 'SEPTEMBER', 'OCTOBER', 'NOVEMBER', 'DECEMBER']
DAY = r'(?:[A-Z][a-z]{2,5})'
HALF = r'((?:\d{2}:\d{2} \d+\.\d+|MISS)(?: (?:\d{2}:\d{2} \d+\.\d+|MISS))?)'
LINE = re.compile(rf'^(\d{{1,2}}) {DAY} {HALF} (\d{{1,2}}) {DAY} {HALF}\s*$')
EVENT = re.compile(r'(\d{2}:\d{2}) (\d+\.\d+)')


def parse(pdf_path, year):
    entries = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ''
            if 'ESTIMATED HEIGHT OF TIDE' not in text:
                continue
            m_mon = next((i for i, m in enumerate(MONTHS)
                          if f'{m} {year}' in text), None)
            if m_mon is None:
                continue
            month = m_mon + 1
            for line in text.split('\n'):
                norm = re.sub(r'--:--[ -]+', 'MISS ', line.strip()).rstrip()
                m = LINE.match(norm)
                if not m:
                    continue
                d_hw, hw_part, d_lw, lw_part = m.groups()
                for typ, day, part in (('HW', d_hw, hw_part), ('LW', d_lw, lw_part)):
                    for t, h in EVENT.findall(part):
                        entries.append({
                            'date': f'{year}-{month:02d}-{int(day):02d}',
                            'time': t, 'height_m': float(h), 'type': typ,
                        })
    entries.sort(key=lambda e: (e['date'], e['time']))
    return entries


def main():
    pdf_path, year, out = sys.argv[1], int(sys.argv[2]), sys.argv[3]
    entries = parse(pdf_path, year)
    n_hw = sum(1 for e in entries if e['type'] == 'HW')
    data = {
        'name': 'Blyth', 'lat': 55.1165, 'lon': -1.4868,
        'timezone': 'UTC',  # Booklet ganzjaehrig GMT
        'datum': 'LAT (Blyth CD, 2.60 m unter ODN)',
        'source': f'Port of Blyth Tide Table Booklet {year} (Proudman/POL)',
        'entries': entries,
    }
    with open(out, 'w') as f:
        json.dump(data, f)
    print(f'{len(entries)} Events ({n_hw} HW, {len(entries)-n_hw} LW) -> {out}')
    # Plausibilitaet: Events/Monat
    from collections import Counter
    print(dict(sorted(Counter(e['date'][:7] for e in entries).items())))


if __name__ == '__main__':
    main()
