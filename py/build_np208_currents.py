#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ADMIRALTY NP208 (ATT Vol.8, 2026) Part IIIa — Tidal Stream Harmonic
Constants -> XTide Current-Stationen (Knoten).

Nur Seite 304 gescannt: 4 reversierende Stroeme (Strait of Messina x2,
Venezia x2). Seite 305+ (weitere Tidal Streams) NICHT gescannt.

Format wie build_np203_currents.py, aber ATT-Namen OHNE NP-Suffix
([[feedback_att_no_np_suffix]]) — Name endet auf ' Current' (is_current-Erkennung).
M4=(F4,f4) aus SW-Korrektur. N2/K2 inferiert. Zone -0100 -> Meridian +01:00.

Schreibt harmonics/att/harmonics_att_np208_currents.txt (ISO-8859-1).
"""
import os, re

HARM = os.path.expanduser('~/harmonics')
HDR  = f'{HARM}/classic/harmonics_literature.txt'  # sauberer congen-Header (keine Stationen)
OUT  = f'{HARM}/att/harmonics_att_np208_currents.txt'

def read_header():
    lines = open(HDR, encoding='iso-8859-1').read().splitlines()
    end = max(i for i,l in enumerate(lines) if 'End congen output' in l)
    header = lines[:end+1]
    order=[]; in_s=False
    for l in lines:
        if l.startswith('# Constituent speeds'): in_s=True; continue
        if in_s:
            if l.startswith('# Starting year') or l.startswith('*END*'): break
            m=re.match(r'^(\S+)\s+([\d.]+)\s*$', l.strip())
            if m: order.append(m.group(1))
    return header, order

HEADER, ORDER = read_header()

def dm(d,m): return d + m/60.0

def infer_n2k2(con):
    out=dict(con)
    if 'M2' in con and 'S2' in con:
        aM2,gM2=con['M2']; aS2,gS2=con['S2']
        if 'N2' not in out: out['N2']=(round(0.19*aM2,4),(gM2-0.536*(gS2-gM2))%360)
        if 'K2' not in out: out['K2']=(round(0.27*aS2,4),gS2%360)
    return out

# con: {Konstituente: (Amplitude Kn, Phase g)}. M4=(F4,f4).
STATIONS = [
 dict(name='Strait of Messina (N) Current', att='186', lat=dm(38,15.0), lon=dm(15,37.0),
      flood=70, ebb=250, z0=-0.17, mer='+01:00', tz='Europe/Rome', country='Italy',
      con={'M2':(2.6,129),'S2':(0.7,147),'K1':(0.7,73),'O1':(0.3,56),'M4':(0.021,184)}),
 dict(name='Strait of Messina (S) Current', att='186a', lat=dm(38,14.0), lon=dm(15,38.0),
      flood=60, ebb=240, z0=-0.70, mer='+01:00', tz='Europe/Rome', country='Italy',
      con={'M2':(3.2,129),'S2':(0.9,147),'K1':(0.8,73),'O1':(0.4,56),'M4':(0.021,184)}),
 dict(name='Venezia (Lido) Current', att='189', lat=dm(45,25.4), lon=dm(12,25.6),
      flood=300, ebb=120, z0=0.00, mer='+01:00', tz='Europe/Rome', country='Italy',
      con={'M2':(0.96,231),'S2':(0.57,240),'K1':(0.45,14),'O1':(0.12,4)}),
 dict(name='Venezia (Malamocco) Current', att='189a', lat=dm(45,20.0), lon=dm(12,20.0),
      flood=285, ebb=105, z0=0.00, mer='+01:00', tz='Europe/Rome', country='Italy',
      con={'M2':(1.27,200),'S2':(0.76,209),'K1':(0.55,350),'O1':(0.15,342)}),
]

def block(s):
    con=infer_n2k2(s['con'])
    out=['# BEGIN HOT COMMENTS',
         f'# country: {s["country"]}',
         '# source: ADMIRALTY Tide Tables Vol.8 (NP208, 2026), Part IIIa Tidal Stream Harmonic Constants',
         '# station_type: current',
         f'# att_number: {s["att"]}',
         '# stream_type: reversing',
         f'# flood_dir: {s["flood"]:03d}',
         f'# ebb_dir: {s["ebb"]:03d}',
         '# inferred: N2 (0.19*M2), K2 (0.27*S2) - NP208 fuehrt nur M2/S2/K1/O1',
         '# datum: Z0 residual current (knots)',
         '# !units: knots',
         f'# !longitude: {s["lon"]:.6f}',
         f'# !latitude: {s["lat"]:.6f}',
         s['name'],
         f'{s["mer"]} :{s["tz"]}',
         f'{s["z0"]:.4f} knots']
    for c in ORDER:
        if c in con: H,g=con[c]; out.append(f'{c:<12} {H:.4f}  {g:.2f}')
        else: out.append(f'{c:<12} x 0 0')
    return out

lines=list(HEADER)
for s in STATIONS: lines+=block(s)
lines.append('# END')
open(OUT,'w',encoding='iso-8859-1').write('\n'.join(lines)+'\n')
print(f'Geschrieben: {OUT} | {len(STATIONS)} Current-Stationen')
for s in STATIONS: print(f'  {s["att"]:5} {s["name"]}  Z0={s["z0"]} Kn, Flut {s["flood"]}°')
