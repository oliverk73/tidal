#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""KPCL-Krishnapatnam-Tidetafeln (Wayback) -> UTide -> Harmonics-Block.

Quelle: krishnapatnamport.com (alte KPCL-Site, via web.archive.org),
amtliche SoI-Daten ("Reproduced from Tide Table for the Port of
Krishnapatnam ... Surveyor General of India"). Kalenderlayout, 4 HW/NW-
Events/Tag, IST (+0530), Meter ueber Kartennull.
2013+2017 als Monats-HTML (tp_<mon><yy>.html), 2018+2019 als Monats-PDF
(kp_<jahr>_<monat>.pdf) in ~/annual_predictions/india_krishnapatnam/.

Usage: python3 py/fit_krishnapatnam_tides.py [--holdout-2019] > block.txt
"""
from __future__ import annotations
import glob
import os
import re
import sys
from datetime import datetime, timedelta

import numpy as np
import pdfplumber
import utide

sys.path.insert(0, '/home/oliver/py')
sys.path.insert(0, '/home/oliver/batch')
from generate_germany_harmonics_175 import CONSTITUENTS_175, find_xtide_match
from batch_utide_uk_tidetimes import cosine_interpolate, CONSTIT_67

DIR = '/home/oliver/annual_predictions/india_krishnapatnam'
UTC_OFF = timedelta(hours=5, minutes=30)
MONTHS_L = ['january', 'february', 'march', 'april', 'may', 'june', 'july',
            'august', 'september', 'october', 'november', 'december']
MON3 = {m[:3]: i + 1 for i, m in enumerate(MONTHS_L)}
LAT, LON = 14.2500, 80.1330
NAME = 'Krishnapatnam Port, Andhra Pradesh, India'


def parse_html(path):
    m = re.match(r'tp_([a-z]{3})(\d{2})\.html', os.path.basename(path))
    month, year = MON3[m.group(1)], 2000 + int(m.group(2))
    h = open(path, encoding='utf-8', errors='replace').read()
    txt = re.sub(r'<[^>]+>', ' ', h)
    txt = txt.replace('&nbsp;', ' ')
    txt = re.sub(r'\s+', ' ', txt)
    i0 = txt.find('SUN Time Height')
    i1 = txt.find('Time: IST')
    assert i0 > 0 and i1 > i0, f'{path}: Marker fehlen'
    toks = txt[i0 + 15:i1].split()
    days = {}
    day = None
    i = 0
    while i < len(toks):
        t = toks[i]
        if re.match(r'^\d{1,2}$', t) and 1 <= int(t) <= 31:
            day = int(t)
            assert day not in days, f'{path}: Tag {day} doppelt'
            days[day] = []
            i += 1
        elif re.match(r'^\d{4}$', t) and i + 1 < len(toks) and \
                re.match(r'^-?\d\.\d{1,2}$', toks[i + 1]) and day:
            days[day].append((t, float(toks[i + 1])))
            i += 2
        else:
            i += 1
    return month, year, days


def parse_pdf(path):
    events_by_day = {}
    with pdfplumber.open(path) as pdf:
        page = pdf.pages[0]
        txt = page.extract_text() or ''
        if not txt:
            print(f'# {os.path.basename(path)}: kein Textlayer (Scan) -> uebersprungen',
                  file=sys.stderr)
            return None, None, {}
        head = txt.split('\n')[1]
        m = re.search(r'TIDE CHART\s*-\s*([A-Z]+)\s+(\d{4})', head)
        month, year = MONTHS_L.index(m.group(1).lower()) + 1, int(m.group(2))
        words = page.extract_words()
        lines = {}
        for w in words:
            lines.setdefault(round(w['top'] / 4), []).append(w)
        day_lines = []   # (y, [(x, day)])
        ev_lines = []    # (y, [(x, time, height)])
        for top in sorted(lines):
            ws = sorted(lines[top], key=lambda w: w['x0'])
            dd = [(w['x0'], int(w['text'])) for w in ws
                  if re.match(r'^\d{1,2}$', w['text']) and 1 <= int(w['text']) <= 31]
            evs = []
            for i, w in enumerate(ws):
                if re.match(r'^\d{4}$', w['text']) and i + 1 < len(ws) and \
                        re.match(r'^-?\d\.\d{1,2}$', ws[i + 1]['text']):
                    evs.append((w['x0'], w['text'], float(ws[i + 1]['text'])))
            if dd and not evs:
                day_lines.append((top, dd))
            elif evs:
                ev_lines.append((top, evs))
        assert day_lines, f'{path}: keine Tageszeilen'
        # zersplitterte Tagesnummern-Zeilen verschmelzen (z.B. "9..13" und
        # "14 15" in zwei y-Clustern) — sonst kollabieren ganze Wochenspalten
        day_lines.sort()
        merged = [list(day_lines[0])]
        for y, dd in day_lines[1:]:
            if y - merged[-1][0] <= 3:      # top/4-Einheiten = 12pt
                merged[-1][1] = merged[-1][1] + dd
            else:
                merged.append([y, dd])
        day_lines = [(y, dd) for y, dd in merged]
        for y, evs in ev_lines:
            dy, anchors = min(day_lines, key=lambda dl: abs(dl[0] - y))
            if abs(dy - y) > 15:    # gehoert zu keinem Wochenblock (Kopf etc.)
                continue
            for x, tstr, hgt in evs:
                _, day = min(anchors, key=lambda a: abs(a[0] - x))
                events_by_day.setdefault(day, []).append((y, tstr, hgt))
    days = {}
    for day, lst in events_by_day.items():
        days[day] = [(t, h) for _, t, h in sorted(lst)]
    return month, year, days


def collect_events():
    events = []
    files = sorted(glob.glob(f'{DIR}/tp_*.html')) + sorted(glob.glob(f'{DIR}/kp_*.pdf'))
    for f in files:
        month, year, days = parse_html(f) if f.endswith('.html') else parse_pdf(f)
        if not days:
            continue
        import calendar
        ndays = calendar.monthrange(year, month)[1]
        missing = [d for d in range(1, ndays + 1) if d not in days]
        if missing:
            print(f'# {os.path.basename(f)}: Tage fehlen: {missing}', file=sys.stderr)
        n_ev = sum(len(v) for v in days.values())
        bad = [d for d, v in days.items() if not 2 <= len(v) <= 4]
        if bad:
            print(f'# {os.path.basename(f)}: Tage mit !=2-4 Events: '
                  f'{[(d, len(days[d])) for d in bad]}', file=sys.stderr)
        for day, lst in days.items():
            for tstr, hgt in lst:
                hh, mi = int(tstr[:2]), int(tstr[2:])
                if hh > 23 or mi > 59:
                    print(f'# {os.path.basename(f)}: Zeit kaputt {day}. {tstr}', file=sys.stderr)
                    continue
                events.append((datetime(year, month, day, hh, mi) - UTC_OFF, hgt))
    events.sort(key=lambda e: e[0])
    out = [events[0]]
    for e in events[1:]:
        if e[0] > out[-1][0]:
            out.append(e)
    return out


def drop_alternation_breakers(events):
    """Events, die die HW/NW-Alternation brechen (Quell-Tippfehler), entfernen."""
    keep = list(events)
    changed = True
    n_drop = 0
    while changed:
        changed = False
        for i in range(1, len(keep) - 1):
            p, c, n = keep[i - 1][1], keep[i][1], keep[i + 1][1]
            g1 = (keep[i][0] - keep[i - 1][0]).total_seconds()
            g2 = (keep[i + 1][0] - keep[i][0]).total_seconds()
            if g1 > 16 * 3600 or g2 > 16 * 3600:
                continue
            if not ((c > p and c > n) or (c < p and c < n)):
                # weder lokales Max noch Min -> c oder Nachbar kaputt; das
                # Element mit der kleinsten Abweichung vom Mittel der
                # uebernaechsten Nachbarn ist meist OK -> droppe c
                print(f'# Alternationsbruch: {keep[i][0]} {c} '
                      f'(Nachbarn {p}/{n}) -> verworfen', file=sys.stderr)
                del keep[i]
                n_drop += 1
                changed = True
                break
    print(f'# {n_drop} Alternationsbrecher verworfen', file=sys.stderr)
    return keep


def interp_segments(events, gap_h=16):
    """Segmentweise Cosinus-Interpolation (Jahresluecken nicht ueberbruecken).
    gap_h: max. Eventabstand innerhalb eines Segments (mikrotidale Tafeln mit
    2-Event-Tagen brauchen ~26h)."""
    segs = [[events[0]]]
    for e in events[1:]:
        if (e[0] - segs[-1][-1][0]).total_seconds() > gap_h * 3600:
            segs.append([])
        segs[-1].append(e)
    T, V = [], []
    for s in segs:
        if len(s) < 8:
            print(f'# Mini-Segment ({len(s)} Events ab {s[0][0]}) verworfen', file=sys.stderr)
            continue
        t, v = cosine_interpolate(list(s))
        if t is None:
            continue
        T.extend(t)
        V.extend(list(v))
    print(f'# {len(segs)} Segmente -> {len(T)} 15-min-Punkte', file=sys.stderr)
    return np.array(T), np.array(V)


def fit(t, v):
    coef = utide.solve(t, v, lat=LAT, nodal=True, trend=False, method='ols',
                       conf_int='none', verbose=False, constit=CONSTIT_67)
    rec = utide.reconstruct(t, coef, verbose=False)
    resid = v - rec['h']
    r2 = 1 - float(np.sum(resid ** 2)) / float(np.sum((v - v.mean()) ** 2))
    rms = float(np.sqrt(np.mean(resid ** 2)))
    return coef, r2, rms


def main():
    holdout = '--holdout-2019' in sys.argv
    ev = collect_events()
    print(f'# {len(ev)} Events {ev[0][0]:%Y-%m-%d}..{ev[-1][0]:%Y-%m-%d}', file=sys.stderr)
    ev = drop_alternation_breakers(ev)

    if holdout:
        ev_fit = [e for e in ev if e[0].year < 2019]
        ev_oos = [e for e in ev if e[0].year >= 2019]
        t, v = interp_segments(ev_fit)
        coef, r2, rms = fit(t, v)
        print(f'# FIT 2013-2018: pts={len(t)} r2={r2:.4f} rms={rms:.4f}', file=sys.stderr)
        to = np.array([e[0] for e in ev_oos])
        vo = np.array([e[1] for e in ev_oos])
        ro = utide.reconstruct(to, coef, verbose=False)
        d = vo - ro['h']
        print(f'# OOS 2019 an {len(to)} Events: bias={d.mean():+.3f} rms={np.sqrt((d**2).mean()):.3f}',
              file=sys.stderr)
        return

    t, v = interp_segments(ev)
    coef, r2, rms = fit(t, v)
    # Event-Level-Residuen je Jahr (Konsistenz der 4 Jahrgaenge)
    for yr in sorted({e[0].year for e in ev}):
        ey = [e for e in ev if e[0].year == yr]
        ty = np.array([e[0] for e in ey])
        vy = np.array([e[1] for e in ey])
        ry = utide.reconstruct(ty, coef, verbose=False)
        d = vy - ry['h']
        print(f'# {yr}: {len(ey)} Events, bias={d.mean():+.3f} rms={np.sqrt((d**2).mean()):.3f}',
              file=sys.stderr)
    print(f'# GESAMT r2={r2:.4f} rms={rms:.4f}', file=sys.stderr)

    from utide._ut_constants import ut_constants
    table = ut_constants['const']
    unames = [n.strip() for n in table.name]
    cm = {}
    for i, u in enumerate(coef['name']):
        u = u.strip()
        if u not in unames:
            continue
        xt, _ = find_xtide_match(u, table.freq[unames.index(u)] * 360.0)
        if xt:
            cm[xt] = (float(coef['A'][i]), float(coef['g'][i]) % 360.0)
    z0 = float(coef['mean'])
    m2, s2, k1, o1 = (cm.get(c, (0, 0)) for c in ('M2', 'S2', 'K1', 'O1'))
    print(f'# Z0={z0:.3f} M2={m2[0]:.3f}@{m2[1]:.0f} S2={s2[0]:.3f}@{s2[1]:.0f} '
          f'K1={k1[0]:.3f}@{k1[1]:.0f} O1={o1[0]:.3f}@{o1[1]:.0f}', file=sys.stderr)
    n_ana = sum(1 for cn, _ in CONSTITUENTS_175 if cn in cm)
    L = [
        "#", f"# {NAME}", "# BEGIN HOT COMMENTS", "# country: India",
        "# state: Andhra Pradesh",
        "# source: KPCL monthly tide tables (Survey of India data) with UTide",
        "# note: Source: krishnapatnamport.com via web.archive.org, 37 monthly tables",
        "# note: (2013, 2017, Jan 2018, 2019), 'Reproduced from Tide Table for the Port",
        "# note: of Krishnapatnam ... Surveyor General of India', 4 HW/LW events/day,",
        "# note: IST (+0530). 2018 Feb-Dec are scans without text layer (skipped).",
        f"# date_imported: {datetime.now():%Y%m%d}",
        "# datum: chart datum (port tide table)",
        "# confidence: 7",
        f"# utide: events={len(ev)} hwlw period=2013+2017+2018+2019 r2={r2:.4f} rms={rms:.4f}m const={n_ana}",
        "# !units: meters", f"# !longitude: {LON:.4f}", f"# !latitude: {LAT:.4f}",
        NAME, '+00:00 :Asia/Kolkata', f"{z0:.4f} meters",
    ]
    for cn, _sp in CONSTITUENTS_175:
        if cn in cm and cm[cn][0] >= 0.00005:
            L.append(f"{cn:15s} {cm[cn][0]:.4f}  {cm[cn][1]:.2f}")
        else:
            L.append("x 0 0")
    print('\n'.join(L))


if __name__ == '__main__':
    main()
