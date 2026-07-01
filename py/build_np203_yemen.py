#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Pilot: Jemen + Socotra aus ADMIRALTY NP203 (2002) Part III -> XTide-Harmonics.

- 5 direkte Konstanten-Stationen (amtliche M2/S2/K1/O1 + ggf. M4/M6), visuell aus
  Seite 152 (Somalia–Oman) verifiziert. Zone -0300 -> Meridian +03:00.
- 2 Socotra-Sekundärhäfen via Aden-Transfer: reine Zeitverschiebung der Aden-Kurve
  (Δt aus Part-II-HW-Offset) + Niveau (Z0 aus Part II). g_neu = g_Aden + speed·Δt.

Schreibt harmonics/utide/harmonics_admiralty_np203.txt (ISO-8859-1).
"""
import os, re

HARM = os.path.expanduser('~/harmonics')
LIT  = f'{HARM}/classic/harmonics_literature.txt'
OUT  = f'{HARM}/utide/harmonics_admiralty_np203.txt'

# ---- Konstituenten-Geschwindigkeiten (°/Sonnenstunde) aus Header lesen ----
def read_speeds_and_header():
    lines = open(LIT, encoding='iso-8859-1').read().splitlines()
    # Header = bis einschließlich erster "# ------------- End congen output -------------"
    end = max(i for i,l in enumerate(lines) if 'End congen output' in l)
    header = lines[:end+1]
    # Konstituenten-Reihenfolge + speeds aus dem Speeds-Block
    order=[]; speed={}
    in_speeds=False
    for l in lines:
        if l.startswith('# Constituent speeds'): in_speeds=True; continue
        if in_speeds:
            if l.startswith('# Starting year') or l.startswith('*END*'): break
            m=re.match(r'^(\S+)\s+([\d.]+)\s*$', l.strip())
            if m:
                order.append(m.group(1)); speed[m.group(1)]=float(m.group(2))
    return header, order, speed

HEADER, ORDER, SPEED = read_speeds_and_header()
assert 'M2' in SPEED and len(ORDER)>=170, f'Speed-Parse fehlgeschlagen ({len(ORDER)})'

# ---- Aden-Referenz (Part III, p152, Zone -0300) ----
ADEN = {'M2':(0.47,223),'S2':(0.21,245),'K1':(0.40,34),'O1':(0.20,34)}
ADEN_Z0 = 1.39

def transfer(dt_min, z0):
    """Aden-Kurve um dt_min (Minuten, neg=früher) zeitverschieben."""
    dt_h = dt_min/60.0
    con={}
    for c,(amp,g) in ADEN.items():
        con[c]=(amp, (g + SPEED[c]*dt_h) % 360)
    return con, z0

# ---- Stationsdefinitionen ----
# con: {Konstituente: (Amplitude_m, Phase_grad_in_Zonenzeit)}
STATIONS = [
 dict(name='Kamaran, Yemen', att='4145', lat=15.333, lon=42.600, z0=0.78, conf=6,
      note='NP203 Part III. Mikro-diurnal; M2 dominiert.',
      con={'M2':(0.32,44),'S2':(0.09,72),'K1':(0.01,188),'O1':(0.01,140)}),
 dict(name='Al Hudaydah, Yemen', att='4146', lat=14.833, lon=42.933, z0=1.22, conf=7,
      note='NP203 Part III inkl. Flachwasser (M4/M6).',
      con={'M2':(0.31,29),'S2':(0.08,61),'K1':(0.02,66),'O1':(0.01,134),
           'M4':(0.017,153),'M6':(0.017,249)}),
 dict(name='Ras al Katib, Yemen', att='4146a', lat=14.917, lon=42.900, z0=1.09, conf=6,
      note='NP203 Part III. ~4 km N von Al Hudaydah.',
      con={'M2':(0.26,24),'S2':(0.07,66),'K1':(0.04,114),'O1':(0.01,124)}),
 dict(name='Al Mukha (Mocha), Yemen', att='4151', lat=13.317, lon=43.250, z0=0.50, conf=4,
      note='NP203 Part III. MIKROTIDAL (M2=0.11 m), diurnal-dominiert; Koord. geografisch (kein Part-II-Eintrag).',
      con={'M2':(0.11,325),'S2':(0.05,275),'K1':(0.20,33),'O1':(0.09,38)}),
 dict(name='Mukalla, Yemen', att='4162', lat=14.533, lon=49.133, z0=1.22, conf=7,
      note='NP203 Part III.',
      con={'M2':(0.40,223),'S2':(0.12,254),'K1':(0.34,33),'O1':(0.24,36)}),
]
# Socotra-Sekundärhäfen (Transfer von Aden)
_rq_con,_=transfer(-110, 1.5)
STATIONS.append(dict(name='Ras Qalansiyah (Socotra), Yemen', att='4051', lat=12.700, lon=53.483,
    z0=1.5, conf=4, con=_rq_con,
    note='Socotra. NP203 Part II Sekundaerhafen zu Aden: HW -0110, ML 1.5 m. Aden-Kurve zeitverschoben.'))
_gn_con,_=transfer(-130, 1.2)
STATIONS.append(dict(name='Ghubbat di-Net (Socotra), Yemen', att='4052', lat=12.450, lon=53.467,
    z0=1.2, conf=4, con=_gn_con,
    note='Socotra Suedkueste. NP203 Part II Sekundaerhafen zu Aden: HW -0130, ML 1.2 m. Aden-Kurve zeitverschoben.'))

# ---- Stationsblock generieren ----
def block(s):
    out=[]
    out.append('# BEGIN HOT COMMENTS')
    out.append('# country: Yemen')
    out.append('# source: ADMIRALTY Tide Tables Vol.3 (NP203), 2002 ed., Simplified Harmonic Method')
    out.append(f'# att_number: {s["att"]}')
    out.append(f'# note: {s["note"]}')
    out.append('# date_imported: 20260614')
    out.append('# datum: Chart Datum (Z0 = mean level above CD)')
    out.append(f'# confidence: {s["conf"]}')
    out.append('# !units: meters')
    out.append(f'# !longitude: {s["lon"]:.4f}')
    out.append(f'# !latitude: {s["lat"]:.4f}')
    out.append(s['name'])
    out.append('+03:00 :Asia/Aden')
    out.append(f'{s["z0"]:.4f} meters')
    for c in ORDER:
        if c in s['con']:
            amp,g = s['con'][c]
            out.append(f'{c:<16}{amp:.4f}  {g:.2f}')
        else:
            out.append('x 0 0')
    return out

lines = list(HEADER)
for s in STATIONS:
    lines += block(s)
lines.append('# END')

with open(OUT,'w',encoding='iso-8859-1') as f:
    f.write('\n'.join(lines)+'\n')
print(f'Geschrieben: {OUT}')
print(f'Stationen: {len(STATIONS)}, Konstituenten/Station: {len(ORDER)}')
for s in STATIONS:
    cons=','.join(f'{k} {v[0]}/{v[1]:.0f}' for k,v in s['con'].items())
    print(f'  {s["att"]:6} {s["name"][:34]:34} Z0={s["z0"]}  {cons}')
