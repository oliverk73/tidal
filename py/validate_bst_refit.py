#!/usr/bin/env python3
"""Januar+Juli-Validierung des BST-Refits gegen PLA und obs-Doppelstationen.
Usage: python3 validate_refit.py <pfad_zur_test_tcd>"""
import csv, io, subprocess, statistics, os, sys
from datetime import datetime

TEST_TCD = sys.argv[1]
OBS = '/usr/share/xtide/harmonics_utide_observations.tcd'

def ev(station, hfile, b, e, typ_filter=None):
    env = os.environ.copy(); env['HFILE_PATH'] = hfile
    r = subprocess.run(['tide','-l',station,'-b',b,'-e',e,'-f','c','-m','p','-em','pSsMm','-z'],
                       capture_output=True, text=True, env=env)
    out = []
    for p in csv.reader(r.stdout.splitlines()):
        if len(p) >= 5 and 'Tide' in p[4]:
            t = p[2].replace(' UTC','').strip()
            try: dt = datetime.strptime(p[1]+' '+t, '%Y-%m-%d %I:%M %p')
            except ValueError: continue
            out.append((dt, 'H' if 'High' in p[4] else 'L'))
    return out

def comp(a, b_):
    dts = []
    for adt, aty in a:
        best = None
        for bdt, bty in b_:
            if bty != aty: continue
            d = abs((bdt-adt).total_seconds())
            if best is None or d < best[0]: best = (d, bdt)
        if best and best[0] <= 10800: dts.append((best[1]-adt).total_seconds()/60)
    return (statistics.median(dts), statistics.pstdev(dts), len(dts)) if dts else (None, None, 0)

MONTHS = [("Jan27","2027-01-01 00:00","2027-02-01 00:00"), ("Jul27","2027-07-01 00:00","2027-08-01 00:00")]

print("== vs PLA (GMT-Wahrheit) ==")
for code, st in [('0103','Margate, England, United Kingdom'),
                 ('0110A','Coryton, England, United Kingdom'),
                 ('0129','Walton-On-The-Naze, England, United Kingdom')]:
    f = f'/tmp/pla/cache/events2027_{code}.csv'
    if not os.path.exists(f): continue
    pla = []
    for txt in open(f).read().split('\x00'):
        for row in csv.reader(io.StringIO(txt)):
            if len(row) >= 6 and row[5] in 'HL':
                pla.append((datetime.strptime(row[0]+' '+row[3],'%Y-%m-%d %H:%M'), row[5]))
    for label, b, e in MONTHS:
        mine = ev(st, TEST_TCD, b, e)
        sub = [p for p in pla if p[0].month == (1 if label=='Jan27' else 7)]
        m, s, n = comp(sub, mine)
        print(f"  {st.split(',')[0]:18s} {label}: dt_med={m:+6.1f} sigma={s:5.1f} n={n}")

print("== vs Messdaten-Fits (observations) ==")
for st in ['Arbroath, Scotland, United Kingdom','Deal, England, United Kingdom',
           'Dundee, Scotland, United Kingdom','Cromarty, Scotland, United Kingdom',
           'Buckie, Scotland, United Kingdom','Howth, Ireland']:
    line = f"  {st.split(',')[0]:18s}"
    for label, b, e in MONTHS:
        obs = ev(st, OBS, b, e)
        mine = ev(st, TEST_TCD, b, e)
        m, s, n = comp(obs, mine)
        line += f" {label}: {m:+6.1f}min(s{s:.0f},n{n})" if m is not None else f" {label}: n/a"
    print(line)

print("== Transfer-Stationen vs EasyTide (Juni 2026, UTC) ==")
import json
et = json.load(open('/tmp/easytide_porthmadog.json'))
hw = [(datetime.fromisoformat(x['dateTime'].split('.')[0]), 'H') for x in et['tidalEventList'] if x['eventType'] == 0]
mine = ev('Porthmadog, Wales, United Kingdom', TEST_TCD, '2026-06-09 00:00', '2026-06-16 00:00')
m, s, n = comp(hw, [x for x in mine if x[1]=='H'])
print(f"  Porthmadog Jun26: dt_med={m:+6.1f} sigma={s:5.1f} n={n}  (vorher +60.1)")
