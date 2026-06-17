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
OUT  = f'{HARM}/att/harmonics_att_np203.txt'

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
 dict(name='Nacala (NP203), Mozambique', att='3850', lat=-14.4667, lon=40.6833, z0=2.25, conf=7, mer='+02:00', tz='Africa/Maputo', country='Mozambique',
      note='NP203 Part III S.240 (2015), Standardhafen, Zone -0200. N2/K2 inferiert. Nur Classic-1997 vorhanden.', infer=True,
      con={'M2':(1.05,86),'S2':(0.54,128),'K1':(0.10,21),'O1':(0.09,36)}),
 dict(name='Mtwara (NP203), Tanzania', att='3985', lat=-10.2667, lon=40.2000, z0=2.0, conf=7, mer='+03:00', tz='Africa/Dar_es_Salaam', country='Tanzania',
      note='NP203 Part III S.241 (2015), Standardhafen, Zone -0300. N2/K2 inferiert. Nur Classic-1997 vorhanden.', infer=True,
      con={'M2':(1.09,113),'S2':(0.52,156),'K1':(0.17,31),'O1':(0.11,49)}),
 dict(name='Mahajanga (NP203), Madagascar', att='3881', lat=-15.7270, lon=46.3148, z0=2.93, conf=7, mer='+03:00', tz='Indian/Antananarivo', country='Madagascar',
      note='NP203 Part III S.241 (2015), Standardhafen, Zone -0300. N2/K2 inferiert. Bisher nur FES2022-Modell.', infer=True,
      con={'M2':(1.26,113),'S2':(0.65,164),'K1':(0.14,55),'O1':(0.07,52)}),
 dict(name='Sharjah (NP203), United Arab Emirates', att='4205', lat=25.3667, lon=55.3833, z0=1.18, conf=7, mer='+04:00', tz='Asia/Dubai', country='United Arab Emirates',
      note='NP203 Part III S.244 (2015), Standardhafen, Zone -0400. N2/K2 inferiert. Nur Classic-1997 vorhanden.', infer=True,
      con={'M2':(0.44,17),'S2':(0.16,63),'K1':(0.18,165),'O1':(0.15,108)}),
 dict(name='Dubai (NP203), United Arab Emirates', att='4206a', lat=25.2667, lon=55.2833, z0=1.03, conf=7, mer='+04:00', tz='Asia/Dubai', country='United Arab Emirates',
      note='NP203 Part III S.244 (2015), Standardhafen, Zone -0400. N2/K2 inferiert. Nur Classic-1997 vorhanden.', infer=True,
      con={'M2':(0.44,353),'S2':(0.16,41),'K1':(0.23,151),'O1':(0.16,97)}),
 dict(name='Mina Zayid (Abu Dhabi) (NP203), United Arab Emirates', att='4210', lat=24.5167, lon=54.3833, z0=1.42, conf=7, mer='+04:00', tz='Asia/Dubai', country='United Arab Emirates',
      note='NP203 Part III S.244 (2015), Standardhafen, Zone -0400. N2/K2 inferiert. Nur Classic-1997 vorhanden.', infer=True,
      con={'M2':(0.42,19),'S2':(0.18,72),'K1':(0.32,162),'O1':(0.18,108)}),
 dict(name='Bushehr (NP203), Iran', att='4283', lat=28.9190, lon=50.8040, z0=0.76, conf=7, mer='+03:30', tz='Asia/Tehran', country='Iran',
      note='NP203 Part III S.246 (2015), Standardhafen, Zone -0330. N2/K2 inferiert. Nur Classic-1997 vorhanden.', infer=True,
      con={'M2':(0.34,211),'S2':(0.12,265),'K1':(0.31,280),'O1':(0.20,238)}),
 dict(name='Al Basrah (NP203), Iraq', att='4271', lat=30.5167, lon=47.8500, z0=1.49, conf=6, mer='+03:00', tz='Asia/Baghdad', country='Iraq',
      note='NP203 Part III S.246 (2015), Standardhafen, Zone -0300. N2/K2 inferiert. Nur Classic-1997 vorhanden. Koord ~Basra-Stadt (Shatt al Arab).', infer=True,
      con={'M2':(0.33,84),'S2':(0.10,166),'K1':(0.21,28),'O1':(0.12,351)}),
 dict(name='Bandar-e Shahid Rajai (NP203), Iran', att='4303', lat=27.1100, lon=56.0800, z0=2.19, conf=6, mer='+03:30', tz='Asia/Tehran', country='Iran',
      note='NP203 Part III S.246 (2015), Standardhafen, Zone -0330. N2/K2 + M4/M6 (Flachwasser f4/f6). Nur Classic-1997 (Bandar Abbas) vorhanden.', infer=True,
      con={'M2':(1.10,302),'S2':(0.41,341),'K1':(0.35,70),'O1':(0.23,58),'M4':(0.025,246),'M6':(0.003,326)}),

 # ---- NP203 Standard Ports Batch 2 (Golf/Rotes Meer/Indien), offizielle Koords ----
 dict(name='Rabigh (NP203), Saudi Arabia', att='4133', lat=22.7986, lon=38.9803, z0=0.8, conf=4, mer='+03:00', tz='Asia/Riyadh', country='Saudi Arabia',
      note='NP203 Part III S.242 (2015), Standardhafen, Zone -0300. MIKROTIDAL (M2=0.13 m, Rotes Meer). N2/K2 inferiert.', infer=True,
      con={'M2':(0.13,197),'S2':(0.04,222),'K1':(0.04,202),'O1':(0.02,204)}),
 dict(name='Fujairah (NP203), United Arab Emirates', att='4191a', lat=25.1645, lon=56.3470, z0=1.74, conf=7, mer='+04:00', tz='Asia/Dubai', country='United Arab Emirates',
      note='NP203 Part III S.243 (2015), Standardhafen, Zone -0400 (Golf von Oman). N2/K2 inferiert.', infer=True,
      con={'M2':(0.67,278),'S2':(0.26,315),'K1':(0.39,40),'O1':(0.20,40)}),
 dict(name='Khawr Fakkan (NP203), United Arab Emirates', att='4192', lat=25.3513, lon=56.3597, z0=1.73, conf=7, mer='+04:00', tz='Asia/Dubai', country='United Arab Emirates',
      note='NP203 Part III S.243 (2015), Standardhafen, Zone -0400 (Golf von Oman). N2/K2 inferiert.', infer=True,
      con={'M2':(0.66,278),'S2':(0.27,312),'K1':(0.35,40),'O1':(0.19,42)}),
 dict(name='Ajman (NP203), United Arab Emirates', att='4204', lat=25.4052, lon=55.4694, z0=1.17, conf=7, mer='+04:00', tz='Asia/Dubai', country='United Arab Emirates',
      note='NP203 Part III S.244 (2015), Standardhafen, Zone -0400. N2/K2 inferiert.', infer=True,
      con={'M2':(0.43,4),'S2':(0.13,61),'K1':(0.17,163),'O1':(0.15,106)}),
 dict(name='Khalifa Port (NP203), United Arab Emirates', att='4208b', lat=24.8200, lon=54.6450, z0=1.32, conf=7, mer='+04:00', tz='Asia/Dubai', country='United Arab Emirates',
      note='NP203 Part III S.244 (2015), Standardhafen, Zone -0400 (Abu Dhabi/Taweelah). N2/K2 inferiert.', infer=True,
      con={'M2':(0.42,2),'S2':(0.17,54),'K1':(0.30,156),'O1':(0.19,100)}),
 dict(name='Halat al Mubarraz (NP203), United Arab Emirates', att='4214', lat=24.4667, lon=53.3500, z0=1.21, conf=5, mer='+04:00', tz='Asia/Dubai', country='United Arab Emirates',
      note='NP203 Part III S.244 (2015), Standardhafen, Zone -0400. Offshore-Oelterminal, Koord ungefaehr. N2/K2 inferiert.', infer=True,
      con={'M2':(0.29,17),'S2':(0.12,77),'K1':(0.43,158),'O1':(0.22,113)}),
 dict(name='Mesaieed (NP203), Qatar', att='4236', lat=24.9800, lon=51.6050, z0=1.17, conf=7, mer='+03:00', tz='Asia/Qatar', country='Qatar',
      note='NP203 Part III S.244 (2015), Standardhafen, Zone -0300 (Qatar-Subblock, korrigiert). N2/K2 inferiert.', infer=True,
      con={'M2':(0.29,152),'S2':(0.11,183),'K1':(0.43,124),'O1':(0.19,71)}),
 dict(name='Doha (NP203), Qatar', att='4239', lat=25.3000, lon=51.5167, z0=0.88, conf=7, mer='+03:00', tz='Asia/Qatar', country='Qatar',
      note='NP203 Part III S.244 (2015), Standardhafen, Zone -0300. N2/K2 inferiert. Nur Classic-1997 vorhanden.', infer=True,
      con={'M2':(0.32,139),'S2':(0.11,172),'K1':(0.37,120),'O1':(0.17,66)}),
 dict(name='Ras Laffan (NP203), Qatar', att='4242', lat=25.9167, lon=51.5667, z0=0.89, conf=7, mer='+03:00', tz='Asia/Qatar', country='Qatar',
      note='NP203 Part III S.245 (2015), Standardhafen, Zone -0300. N2/K2 inferiert.', infer=True,
      con={'M2':(0.36,122),'S2':(0.11,165),'K1':(0.25,102),'O1':(0.12,47)}),
 dict(name='Ad Dammam (K.A.A.P.) (NP203), Saudi Arabia', att='4253f', lat=26.5000, lon=50.2100, z0=1.43, conf=5, mer='+03:00', tz='Asia/Riyadh', country='Saudi Arabia',
      note='NP203 Part III S.245 (2015), Standardhafen, Zone -0300. S2 in NP203 als "v" (variabel) -> aus Nachbarn Mina Salman/Ra\'s Tanura geschaetzt (H=0.215 g=195). M4/M6 (f4/f6). N2/K2 inferiert.', infer=True,
      con={'M2':(0.63,137),'S2':(0.215,195),'K1':(0.13,345),'O1':(0.11,286),'M4':(0.073,345),'M6':(0.019,305)}),
 dict(name='Umm Qasr (NP203), Iraq', att='4267', lat=30.0300, lon=47.9300, z0=2.89, conf=7, mer='+03:00', tz='Asia/Baghdad', country='Iraq',
      note='NP203 Part III S.246 (2015), Standardhafen, Zone -0300. N2/K2 inferiert.', infer=True,
      con={'M2':(1.43,1),'S2':(0.44,74),'K1':(0.57,321),'O1':(0.27,270)}),
 dict(name='Al Faw (NP203), Iraq', att='4269', lat=29.9742, lon=48.4733, z0=1.88, conf=7, mer='+03:00', tz='Asia/Baghdad', country='Iraq',
      note='NP203 Part III S.246 (2015), Standardhafen, Zone -0300 (Shatt al Arab). N2/K2 inferiert.', infer=True,
      con={'M2':(0.82,337),'S2':(0.25,39),'K1':(0.44,315),'O1':(0.25,268)}),
 dict(name='Bandar-e Mahshahr (NP203), Iran', att='4279', lat=30.4700, lon=49.1600, z0=3.24, conf=7, mer='+03:30', tz='Asia/Tehran', country='Iran',
      note='NP203 Part III S.246 (2015), Standardhafen, Zone -0330. Grosser Hub. N2/K2 inferiert.', infer=True,
      con={'M2':(1.54,343),'S2':(0.53,51),'K1':(0.53,314),'O1':(0.31,270)}),
 dict(name='Al Jubayl (NP203), Saudi Arabia', att='4255', lat=27.0133, lon=49.6581, z0=0.82, conf=7, mer='+03:00', tz='Asia/Riyadh', country='Saudi Arabia',
      note='NP203 Part III S.245 (2015), Standardhafen, Zone -0300. N2/K2 inferiert.', infer=True,
      con={'M2':(0.45,124),'S2':(0.18,181),'K1':(0.19,319),'O1':(0.14,275)}),
 dict(name='Sultanpur (Sartanpar) (NP203), India', att='4344', lat=21.298532, lon=72.106395, z0=4.13, conf=6, mer='+05:30', tz='Asia/Kolkata', country='India',
      note='NP203 Part III S.247 (2015), Standardhafen, Zone -0530 (Gujarat/Golf von Khambhat, Zone korrigiert). K1 nicht gefuehrt. M4 (f4). N2/K2 inferiert.', infer=True,
      con={'M2':(2.12,110),'S2':(0.82,147),'O1':(0.30,52),'M4':(0.024,214)}),
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
