#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Extrahiert Table-1-Tagesvorhersagen (Slack/Max) der Referenz-STROMstationen
aus den NOAA Tidal Current Tables 2020 (acct/pcct Full-Book-PDF).

Ausgabe: JSON {station: {'events': [[iso_local, v_knots], ...]}} — Slack v=0,
Maxima v=+speed (Flood) / -speed (Ebb). Zeiten in Stations-LST (Meridian separat).
"""
import pypdf, re, json, sys

PDF = sys.argv[1]
OUT = sys.argv[2]

MONTHS = {m: i+1 for i, m in enumerate(
    ['January','February','March','April','May','June',
     'July','August','September','October','November','December'])}
WD = {'M','Tu','W','Th','F','Sa','Su'}
T = re.compile(r'^\d{4}$')
SPD = re.compile(r'^\d{1,2}\.\d$')

def parse(pdf):
    r = pypdf.PdfReader(pdf)
    data = {}
    station = None; month = None; day = None
    for pi in range(len(r.pages)):
        try: txt = r.pages[pi].extract_text() or ''
        except Exception: continue
        if 'Slack Maximum' not in txt[:200]: continue
        m = re.search(r'([A-Z][^\n]{4,70}?), 2020', txt)
        if m: station = m.group(1).strip()
        if not station: continue
        st = data.setdefault(station, {})
        for line in txt.split('\n'):
            toks = line.split()
            if not toks: continue
            if toks[0] in MONTHS: month = MONTHS[toks[0]]; continue
            if month is None: continue
            # Tageszeile beginnt mit Tagesnummer; Folgezeile mit Wochentag
            k = 0
            if re.fullmatch(r'\d{1,2}', toks[0]) and int(toks[0]) <= 31 and (
                    len(toks) == 1 or T.match(toks[1]) or toks[1] in WD):
                day = int(toks[0]); k = 1
            if k < len(toks) and toks[k] in WD: k += 1
            if day is None: continue
            ev = st.setdefault((month, day), [])
            i = k
            while i < len(toks):
                if T.match(toks[i]):
                    # HHMM: Slack (naechster auch HHMM oder Zeilenende/kein speed) oder Max
                    if i+1 < len(toks) and T.match(toks[i+1]):
                        ev.append((toks[i], 0.0))          # slack
                        i += 1; continue
                    if i+2 < len(toks) and SPD.match(toks[i+1]) and toks[i+2] in ('F','E'):
                        v = float(toks[i+1])
                        ev.append((toks[i], v if toks[i+2]=='F' else -v))
                        i += 3; continue
                    ev.append((toks[i], 0.0)); i += 1; continue
                i += 1
    # in flache Event-Listen
    out = {}
    for stn, days in data.items():
        evs = []
        for (mo, dy), lst in sorted(days.items()):
            for hhmm, v in lst:
                evs.append([f'2020-{mo:02d}-{dy:02d} {hhmm[:2]}:{hhmm[2:]}', v])
        out[stn] = evs
    return out

if __name__ == '__main__':
    out = parse(PDF)
    json.dump(out, open(OUT, 'w'), ensure_ascii=False)
    for k, v in out.items():
        print(f'{len(v):5d} Events  {k}')
