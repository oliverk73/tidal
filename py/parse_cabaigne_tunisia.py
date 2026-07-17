#!/usr/bin/env python3
"""
Parse cabaigne.net Tunisia tide HTML files (saved offline) for a station and
year. Returns a list of HW/LW events (datetime in station local time, height
in metres, type 'H'/'L').
"""
from __future__ import annotations
import re
from pathlib import Path
from datetime import datetime
from bs4 import BeautifulSoup

FR_MONTHS = {
    'janvier': 1, 'février': 2, 'fevrier': 2, 'mars': 3, 'avril': 4,
    'mai': 5, 'juin': 6, 'juillet': 7, 'août': 8, 'aout': 8,
    'septembre': 9, 'octobre': 10, 'novembre': 11, 'décembre': 12, 'decembre': 12,
}

DAY_RE = re.compile(r'\w+\s+(\d{1,2})\s+(\w+)\s+(\d{4})', re.IGNORECASE | re.UNICODE)
TIME_RE = re.compile(r'(\d{1,2}):(\d{2})')
HEIGHT_RE = re.compile(r'([\d.]+)\s*m')


def parse_day_header(text: str):
    m = DAY_RE.search(text)
    if not m:
        return None
    day = int(m.group(1))
    mon_name = m.group(2).lower()
    mon = FR_MONTHS.get(mon_name)
    year = int(m.group(3))
    if mon is None:
        return None
    return year, mon, day


def parse_file(path: Path):
    soup = BeautifulSoup(open(path, encoding='utf-8'), 'html.parser')
    events = []
    for h3 in soup.find_all('h3'):
        ymd = parse_day_header(h3.get_text(strip=True))
        if not ymd:
            continue
        year, mon, day = ymd
        table = h3.find_next('table')
        if not table:
            continue
        for tr in table.find_all('tr'):
            cells = tr.find_all('td')
            if len(cells) < 3:
                continue
            kind_text = cells[0].get_text(strip=True).lower()
            time_text = cells[1].get_text(strip=True)
            height_text = cells[2].get_text(strip=True)
            tmatch = TIME_RE.search(time_text)
            hmatch = HEIGHT_RE.search(height_text)
            if not tmatch or not hmatch:
                continue
            hh, mm = int(tmatch.group(1)), int(tmatch.group(2))
            height = float(hmatch.group(1))
            if 'haute' in kind_text:
                kind = 'H'
            elif 'basse' in kind_text:
                kind = 'L'
            else:
                continue
            dt = datetime(year, mon, day, hh, mm)
            events.append((dt, height, kind))
    return events


def parse_station(directory: Path, station_name: str):
    files = sorted(directory.glob(f"{station_name} _*.htm"))
    all_events = []
    for f in files:
        evs = parse_file(f)
        all_events.extend(evs)
        print(f"  {f.name}: {len(evs)} events")
    all_events.sort(key=lambda x: x[0])
    return all_events


if __name__ == '__main__':
    import sys
    station = sys.argv[1] if len(sys.argv) > 1 else 'Sfax'
    d = Path('/home/oliver/weather/tide_tables/Tunisia')
    evs = parse_station(d, station)
    print(f"\nTotal: {len(evs)} events for {station}")
    if evs:
        print(f"From {evs[0][0]} to {evs[-1][0]}")
        heights = [e[1] for e in evs]
        print(f"Range: {min(heights):.2f} to {max(heights):.2f} m")
        # quick HW/LW count
        hw = sum(1 for e in evs if e[2] == 'H')
        lw = sum(1 for e in evs if e[2] == 'L')
        print(f"HW: {hw}, LW: {lw}")
