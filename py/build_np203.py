#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ADMIRALTY NP203 (Indian Ocean) Part III -> XTide-Harmonics.

Konsolidiert: Yemen/Socotra-Pilot (2002 ed.) + NP203 Standard Ports (2015 ed.).
Standard-Port-Werte visuell aus Part-III-Scans gelesen (OCR der Zahlen unzuverlaessig).

VERBESSERUNG (Oliver 2026-06-15, an Pemba validiert): bei makrotidalen Stationen
N2/K2 inferieren, da NP203 Part III sie nicht publiziert -> sonst HW ~15-20 min zu
frueh / ~0.1 m zu niedrig. Equilibrium-Verhaeltnisse:
  N2: amp=0.19*M2, g = g_M2 - 0.536*(g_S2-g_M2)
  K2: amp=0.27*S2, g = g_S2
(Pemba-Check vs TICON4: N2 65.5 vs 63.5 inferiert; K2 128.7 vs 128).

Schreibt harmonics/utide/harmonics_admiralty_np203.txt (ISO-8859-1).
"""
import os, re

HARM = os.path.expanduser('~/harmonics')
LIT  = f'{HARM}/literature/harmonics_literature.txt'
OUT  = f'{HARM}/utide/harmonics_admiralty_np203.txt'

def read_header():
    lines = open(LIT, encoding='iso-8859-1').read().splitlines()
    end = max(i for i,l in enumerate(lines) if 'End congen output' in l)
    header = lines[:end+1]
    order=[]; speed={}; in_s=False
    for l in lines:
        if l.startswith('# Constituent speeds'): in_s=True; continue
        if in_s:
            if l.startswith('# Starting year') or l.startswith('*END*'): break
            m=re.match(r'^(\S+)\s+([\d.]+)\s*$', l.strip())
            if m: order.append(m.group(1)); speed[m.group(1)]=float(m.group(2))
    return header, order, speed

HEADER, ORDER, SPEED = read_header()
assert 'M2' in SPEED and len(ORDER)>=170

# ---- Aden-Referenz (Part III 2002, Zone -0300) fuer Socotra-Transfer ----
ADEN = {'M2':(0.47,223),'S2':(0.21,245),'K1':(0.40,34),'O1':(0.20,34)}
def transfer(dt_min):
    return {c:(amp,(g+SPEED[c]*dt_min/60.0)%360) for c,(amp,g) in ADEN.items()}

def infer_n2k2(con):
    """N2/K2 aus M2/S2 ergaenzen, falls nicht vorhanden (makrotidal)."""
    out=dict(con)
    if 'M2' in con and 'S2' in con:
        aM2,gM2=con['M2']; aS2,gS2=con['S2']
        if 'N2' not in out:
            out['N2']=(round(0.19*aM2,4), (gM2-0.536*(gS2-gM2))%360)
        if 'K2' not in out:
            out['K2']=(round(0.27*aS2,4), gS2%360)
    return out

# con: {Konstituente: (Amplitude, Phase_in_Zonenzeit)}; infer=True -> N2/K2 ergaenzen
STATIONS = [
 # ---- Yemen/Socotra-Pilot (2002 ed., Zone -0300/+03:00) -- validiert, NICHT infern ----
 dict(name='Kamaran, Yemen', att='4145', lat=15.333, lon=42.600, z0=0.78, conf=6, mer='+03:00', tz='Asia/Aden',
      note='NP203 Part III (2002). Mikro-diurnal; M2 dominiert.', infer=False,
      con={'M2':(0.32,44),'S2':(0.09,72),'K1':(0.01,188),'O1':(0.01,140)}),
 dict(name='Al Hudaydah, Yemen', att='4146', lat=14.833, lon=42.933, z0=1.22, conf=7, mer='+03:00', tz='Asia/Aden',
      note='NP203 Part III (2002) inkl. Flachwasser (M4/M6).', infer=False,
      con={'M2':(0.31,29),'S2':(0.08,61),'K1':(0.02,66),'O1':(0.01,134),'M4':(0.017,153),'M6':(0.017,249)}),
 dict(name='Ras al Katib, Yemen', att='4146a', lat=14.917, lon=42.900, z0=1.09, conf=6, mer='+03:00', tz='Asia/Aden',
      note='NP203 Part III (2002). ~4 km N von Al Hudaydah.', infer=False,
      con={'M2':(0.26,24),'S2':(0.07,66),'K1':(0.04,114),'O1':(0.01,124)}),
 dict(name='Al Mukha (Mocha), Yemen', att='4151', lat=13.317, lon=43.250, z0=0.50, conf=4, mer='+03:00', tz='Asia/Aden',
      note='NP203 Part III (2002). MIKROTIDAL (M2=0.11 m), diurnal-dominiert.', infer=False,
      con={'M2':(0.11,325),'S2':(0.05,275),'K1':(0.20,33),'O1':(0.09,38)}),
 dict(name='Mukalla, Yemen', att='4162', lat=14.533, lon=49.133, z0=1.22, conf=7, mer='+03:00', tz='Asia/Aden',
      note='NP203 Part III (2002).', infer=False,
      con={'M2':(0.40,223),'S2':(0.12,254),'K1':(0.34,33),'O1':(0.24,36)}),
 dict(name='Ras Qalansiyah (Socotra), Yemen', att='4051', lat=12.700, lon=53.483, z0=1.5, conf=4, mer='+03:00', tz='Asia/Aden',
      note='Socotra. NP203 Part II Sekundaerhafen zu Aden: HW -0110, ML 1.5 m.', infer=False, con=transfer(-110)),
 dict(name='Ghubbat di-Net (Socotra), Yemen', att='4052', lat=12.450, lon=53.467, z0=1.2, conf=4, mer='+03:00', tz='Asia/Aden',
      note='Socotra Suedkueste. NP203 Part II Sekundaerhafen zu Aden: HW -0130, ML 1.2 m.', infer=False, con=transfer(-130)),

 # ---- NP203 Standard Ports (2015 ed.) -- Luecken, N2/K2 inferiert ----
 dict(name='Nacala (NP203), Mozambique', att='3850', lat=-14.4667, lon=40.6833, z0=2.25, conf=7, mer='+02:00', tz='Africa/Maputo',
      note='NP203 Part III S.240 (2015), Standardhafen, Zone -0200. N2/K2 inferiert. Nur Classic-1997 vorhanden.', infer=True,
      con={'M2':(1.05,86),'S2':(0.54,128),'K1':(0.10,21),'O1':(0.09,36)}),
]

def block(s):
    con = infer_n2k2(s['con']) if s.get('infer') else s['con']
    out=['# BEGIN HOT COMMENTS',
         f'# country: {s.get("country","")}',
         '# source: ADMIRALTY Tide Tables Vol.3 (NP203), Simplified Harmonic Method',
         f'# att_number: {s["att"]}',
         f'# note: {s["note"]}',
         '# date_imported: 20260615',
         '# datum: Chart Datum (Z0 = mean level above CD)',
         f'# confidence: {s["conf"]}',
         '# !units: meters',
         f'# !longitude: {s["lon"]:.4f}',
         f'# !latitude: {s["lat"]:.4f}',
         s['name'],
         f'{s["mer"]} :{s["tz"]}',
         f'{s["z0"]:.4f} meters']
    for c in ORDER:
        if c in con:
            amp,g=con[c]; out.append(f'{c:<16}{amp:.4f}  {g:.2f}')
        else: out.append('x 0 0')
    return out

lines=list(HEADER)
for s in STATIONS: lines+=block(s)
lines.append('# END')
with open(OUT,'w',encoding='iso-8859-1') as f: f.write('\n'.join(lines)+'\n')
print(f'Geschrieben: {OUT} | Stationen: {len(STATIONS)}')
for s in STATIONS:
    c=infer_n2k2(s['con']) if s.get('infer') else s['con']
    extra=' +N2/K2' if s.get('infer') else ''
    print(f'  {s["att"]:6} {s["name"][:38]:38} Z0={s["z0"]}{extra}')
