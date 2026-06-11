#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""NCHMF-10-Tage-Tidenbulletins (Wayback-PDFs) -> HW/LW-JSON je Station.

Bulletin: 'Bản tin dự báo thủy triều 10 ngày', 15 Stationen, je Tag
1 Hmax (Nước lớn) + 1 Hmin (Nước ròng) mit Zeit (Ortszeit UTC+7, cm).
Block-Layout im extract_text:
    Hmax (cm) v1..v10 / Nước lớn / Time_max t1..t10 / STATIONSNAME /
    Hmin (cm) v1..v10 / Nước ròng / Time_min t1..t10
Datumszeile: '10/01 11/01 ...' + Jahr aus Titel '(từ DD/MM/YYYY ...'.
Ueberlappende Bulletins: erster Wert gewinnt (astronomische Vorhersagen,
Konflikte minimal).

Usage: python3 py/parse_nchmf_bulletins.py  ->  water_levels/VN_nchmf/<station>.json
"""
import json
import re
import sys
from pathlib import Path

import pdfplumber

DIR = Path('/home/oliver/water_levels/VN_nchmf')
WANted = None  # alle Stationen


def parse_pdf(path):
    """-> dict station -> {date_iso: {'HW': (hh:mm, cm), 'LW': (...)}}"""
    out = {}
    with pdfplumber.open(path) as pdf:
        year = None
        dates = None
        for page in pdf.pages:
            txt = page.extract_text() or ''
            lines = [l.strip() for l in txt.split('\n') if l.strip()]
            m = re.search(r'từ (\d{1,2})/(\d{1,2})/(\d{4})', txt)
            if m:
                year = int(m.group(3))
                start_dm = (int(m.group(1)), int(m.group(2)))
            # Datumszeile (10 Spalten D/M, teils einstellig: '20/2');
            # pro Seite frisch suchen — stale Vorseiten-Daten verschieben sonst
            # alle Werte um Tage (Con-Dao-Bug 2026-06-11)
            for l in lines:
                if 'từ' in l or re.search(r'\d{1,2}/\d{1,2}/\d{4}', l):
                    continue
                dm = re.findall(r'(?<![\d/])(\d{1,2})/(\d{1,2})(?![\d/])', l)
                if len(dm) >= 8:
                    dates = dm
                    break
            if not dates or year is None:
                continue
            # Jahreswechsel innerhalb des Fensters
            isodates = []
            y = year
            prev_m = int(dates[0][1])
            for d, mo in dates:
                if int(mo) < prev_m:
                    y += 1
                prev_m = int(mo)
                isodates.append(f'{y}-{int(mo):02d}-{int(d):02d}')
            i = 0
            while i < len(lines):
                if lines[i].startswith('Hmax'):
                    try:
                        hmax = [int(x) for x in re.findall(r'-?\d+', lines[i])][:10]
                        tmax = re.findall(r'(\d{1,2})h(\d{2})', lines[i + 2])
                        name = lines[i + 3].strip().replace('Ƣ','Ư').replace('ƣ','ư')
                        hmin = [int(x) for x in re.findall(r'-?\d+', lines[i + 4])][:10]
                        tmin = re.findall(r'(\d{1,2})h(\d{2})', lines[i + 6])
                    except (IndexError, ValueError):
                        i += 1
                        continue
                    if not re.match(r'^[A-ZÀ-Ỹ][A-ZÀ-Ỹ \-]{1,30}$', name):
                        i += 1
                        continue
                    st = out.setdefault(name, {})
                    for k, date in enumerate(isodates):
                        rec = st.setdefault(date, {})
                        if k < len(hmax) and k < len(tmax):
                            rec['HW'] = (f'{int(tmax[k][0]):02d}:{tmax[k][1]}', hmax[k])
                        if k < len(hmin) and k < len(tmin):
                            rec['LW'] = (f'{int(tmin[k][0]):02d}:{tmin[k][1]}', hmin[k])
                    i += 7
                else:
                    i += 1
    return out


def main():
    merged = {}
    pdfs = sorted(DIR.glob('*.pdf'))
    for p in pdfs:
        try:
            data = parse_pdf(p)
        except Exception as e:
            print(f'  {p.name}: FEHLER {e}', file=sys.stderr)
            continue
        for st, days in data.items():
            tgt = merged.setdefault(st, {})
            for d, rec in days.items():
                tgt.setdefault(d, rec)  # erster gewinnt
    print(f'{len(pdfs)} PDFs, {len(merged)} Stationen')
    for st, days in sorted(merged.items()):
        fn = DIR / (re.sub(r'[^A-Z]+', '_', st).strip('_').lower() + '.json')
        json.dump(days, open(fn, 'w'), ensure_ascii=False)
        d0, d1 = min(days), max(days)
        print(f'  {st:16s} {len(days):4d} Tage {d0}..{d1} -> {fn.name}')


if __name__ == '__main__':
    main()
