#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Parse NOAA 'Tide Tables Central & Western Pacific + Indian Ocean' (2018) Table 2.

Table 2 = tidal differences and other constants (subordinate stations, ATT-style).
Each data row:  No  Name .... LatDeg° LatMin'  LonDeg° LonMin'  dtHW dtLW  hHW hLW  Mean Spring [Diurnal] MTL
- Reference station set by lines 'on <Name>, p.NNN' (applies until next such line) OR
  by the reference station's own row carrying 'Daily predictions'.
- Hemisphere set by 'North/South East/West' header tokens (streamed state).
- Height columns: ratio '*0.89' OR offset '+0.2' / '0.0' / '-0.1'.
- Range columns: Mean, Spring, Diurnal, MTL; missing shown as '-'.

Writes JSON list of station dicts to scratchpad/t2_full.json.
"""
import pypdf, re, json, sys, os

PDF = sys.argv[1] if len(sys.argv) > 1 else '/tmp/claude-1000/-home-oliver/99a597f4-8599-48bf-9982-0299f605aaa8/scratchpad/cptt2018.pdf'
OUT = sys.argv[2] if len(sys.argv) > 2 else '/tmp/claude-1000/-home-oliver/99a597f4-8599-48bf-9982-0299f605aaa8/scratchpad/t2_full.json'

coordpat = re.compile(r"(\d[\d ]*)\s*°\s*(\d[\d ]*)'")
hemipat  = re.compile(r"\b(North|South)\b.*?\b(East|West)\b")
refpat   = re.compile(r"\bon\s+([A-Z][A-Za-z'’\.\-\(\) ]+?),\s*p\.?\s*\d+")
# token after coords: time diffs are "<sign>D MM" (two ints), height "*0.89" or "+0.2"/"0.0"
fx = lambda s: s.replace(' ', '')

def parse_time(tok):
    # tok like '-0 15' '+0 24' '+1 42'  -> minutes (signed)
    m = re.match(r"([+-])\s*(\d+)\s+(\d+)", tok)
    if not m: return None
    sign = -1 if m.group(1) == '-' else 1
    return sign * (int(m.group(2)) * 60 + int(m.group(3)))

def main():
    r = pypdf.PdfReader(PDF)
    idx_start = None
    for i in range(391, len(r.pages)):
        if 'INDEX TO STATIONS' in (r.pages[i].extract_text() or '').upper():
            idx_start = i; break
    ns, ew = 'North', 'East'
    ref = None
    coltype = 'MS'           # range-column header: MS=Mean/Spring DT=Diurnal/Tropic MD=Mean/Diurnal MT=Mean/Tropic
    rows = []
    COLTAGS = [('Diurnal Tropic', 'DT'), ('Mean Diurnal', 'MD'),
               ('Mean Tropic', 'MT'), ('Mean Spring', 'MS')]
    for i in range(390, idx_start):
        for line in (r.pages[i].extract_text() or '').splitlines():
            ls = line.strip()
            if not ls: continue
            hm = hemipat.search(ls)
            if hm: ns, ew = hm.group(1), hm.group(2)
            for tag, code in COLTAGS:
                if tag in ls: coltype = code; break
            rm = refpat.search(ls)
            if rm: ref = rm.group(1).strip()
            m = re.match(r"^(\d+)\s+(.*)", ls)
            cs = list(coordpat.finditer(ls))
            if not (m and len(cs) >= 2): continue
            try:
                lat = int(fx(cs[0].group(1))) + int(fx(cs[0].group(2))) / 60.0
                lon = int(fx(cs[1].group(1))) + int(fx(cs[1].group(2))) / 60.0
            except ValueError:
                continue
            if ns == 'South': lat = -lat
            if ew == 'West':  lon = -lon
            no = int(m.group(1))
            name = re.sub(r"[\.]{2,}.*$", "", ls[m.end(1):cs[0].start()]).replace('. . .', '').strip(' .')
            tail = ls[cs[1].end():].strip()
            # detect a reference (self) row
            daily = 'Daily predictions' in tail or 'daily prediction' in tail.lower()
            # Consume the two leading TIME columns (signed "D MM").  Heights start after.
            timepat = re.compile(r"[+-]\s*\d+\s+\d+")
            tms = list(timepat.finditer(tail))
            dtHW = parse_time(tms[0].group()) if len(tms) >= 1 else None
            dtLW = parse_time(tms[1].group()) if len(tms) >= 2 else None
            rest = tail[tms[1].end():].strip() if len(tms) >= 2 else (
                   tail[tms[0].end():].strip() if len(tms) == 1 else tail)
            # rest = [HEIGHT(s)] [range columns...] [MTL]
            toks = rest.split()
            hHW = hLW = None; hHW_kind = hLW_kind = None
            mtl = mean_r = spring_r = diurnal_r = tropic_r = None
            # ---- consume the height correction column(s) ----
            #  '(*0.59+1.5)' = ONE combined token (applies to both HW & LW);
            #  '*0.89 *0.89' / '+0.2 0.0' / '+1.0 -0.2' = TWO tokens (HW, LW).
            if daily:
                rngtoks = toks
            elif toks and toks[0].startswith('(*'):
                m = re.match(r'\(\*([\d.]+)([+\-][\d.]+)?\)', toks[0])
                if m:
                    hHW = hLW = float(m.group(1)); hHW_kind = hLW_kind = 'ratio'
                rngtoks = toks[1:]
            else:
                def ash(t):
                    if re.fullmatch(r"\*\d+\.?\d*", t): return ('ratio', float(t[1:]))
                    if re.fullmatch(r"[+-]?\d+\.?\d*", t): return ('offset', float(t))
                    if t in ('-', '–'): return ('dash', None)
                    return ('none', None)
                if len(toks) >= 1: hHW_kind, hHW = ash(toks[0])
                if len(toks) >= 2: hLW_kind, hLW = ash(toks[1])
                rngtoks = toks[2:]
            # ---- range columns: leading '-' = empty Mean; last number = MTL ----
            leading_dash = bool(rngtoks) and rngtoks[0] in ('-', '–')
            vals = [float(t) for t in rngtoks if re.fullmatch(r"[+-]?\d+\.?\d*", t)]
            if vals:
                mtl = vals[-1]; rv = vals[:-1]
                if coltype == 'MS':
                    if leading_dash:
                        spring_r = rv[0] if rv else None
                    else:
                        mean_r = rv[0] if len(rv) > 0 else None
                        spring_r = rv[1] if len(rv) > 1 else None
                elif coltype == 'MD':
                    if leading_dash:
                        diurnal_r = rv[0] if rv else None
                    else:
                        mean_r = rv[0] if len(rv) > 0 else None
                        diurnal_r = rv[1] if len(rv) > 1 else None
                elif coltype == 'DT':
                    diurnal_r = rv[0] if len(rv) > 0 else None
                    tropic_r = rv[1] if len(rv) > 1 else None
                elif coltype == 'MT':
                    mean_r = rv[0] if len(rv) > 0 else None
                    tropic_r = rv[1] if len(rv) > 1 else None
            rows.append(dict(no=no, name=name, lat=round(lat,4), lon=round(lon,4),
                             ref=ref, coltype=coltype, dtHW=dtHW, dtLW=dtLW, daily=daily,
                             hHW=hHW, hHW_kind=hHW_kind, hLW=hLW, hLW_kind=hLW_kind,
                             mean_ft=mean_r, spring_ft=spring_r, diurnal_ft=diurnal_r,
                             tropic_ft=tropic_r, mtl_ft=mtl, pdfpage=i+1))
    json.dump(rows, open(OUT, 'w'))
    print('parsed', len(rows), '->', OUT)

if __name__ == '__main__':
    main()
