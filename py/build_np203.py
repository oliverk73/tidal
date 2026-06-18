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

 # ---- NP203 Standard Ports S.240 (2015), Mosambik, Zone -0200 -- Classic-only-Upgrades ----
 # Werte aus neuem Flat-Scan 600dpi (2026-06-18); Methode an Nacala 3850 exakt gegen alte Lesung validiert.
 dict(name='Porto de Chinde (NP203), Mozambique', att='3827', lat=-18.5670, lon=36.4500, z0=2.06, conf=6, mer='+02:00', tz='Africa/Maputo', country='Mozambique',
      note='NP203 Part III S.240 (2015), Standardhafen, Zone -0200. N2/K2 inferiert. Nur Classic-1997 vorhanden.', infer=True,
      con={'M2':(1.13,107),'S2':(0.65,154),'K1':(0.03,88),'O1':(0.05,39)}),
 dict(name='Morrubune (NP203), Mozambique', att='3831', lat=-18.0000, lon=36.9670, z0=2.60, conf=5, mer='+02:00', tz='Africa/Maputo', country='Mozambique',
      note='NP203 Part III S.240 (2015), Standardhafen, Zone -0200. N2/K2 inferiert. Nur Classic-1997 vorhanden. Name wie ATT gedruckt.', infer=True,
      con={'M2':(1.17,108),'S2':(0.68,148),'K1':(0.02,84),'O1':(0.05,14)}),
 dict(name='Quelimane (NP203), Mozambique', att='3832', lat=-17.8830, lon=36.8830, z0=2.60, conf=6, mer='+02:00', tz='Africa/Maputo', country='Mozambique',
      note='NP203 Part III S.240 (2015), Standardhafen, Zone -0200. N2/K2 inferiert. Nur Classic-1997 vorhanden.', infer=True,
      con={'M2':(1.25,118),'S2':(0.69,163),'K1':(0.05,38),'O1':(0.05,28)}),
 dict(name='Porto de Pebane (NP203), Mozambique', att='3836', lat=-17.2670, lon=38.1330, z0=2.43, conf=6, mer='+02:00', tz='Africa/Maputo', country='Mozambique',
      note='NP203 Part III S.240 (2015), Standardhafen, Zone -0200. N2/K2 inferiert. Nur Classic-1997 vorhanden.', infer=True,
      con={'M2':(1.16,110),'S2':(0.64,154),'K1':(0.05,71),'O1':(0.06,29)}),
 dict(name='Porto de Angoche (NP203), Mozambique', att='3844', lat=-16.2330, lon=39.9000, z0=2.40, conf=6, mer='+02:00', tz='Africa/Maputo', country='Mozambique',
      note='NP203 Part III S.240 (2015), Standardhafen, Zone -0200. N2/K2 inferiert. Nur Classic-1997 vorhanden.', infer=True,
      con={'M2':(1.17,107),'S2':(0.66,156),'K1':(0.08,56),'O1':(0.09,26)}),
 dict(name='Porto do Ibo (NP203), Mozambique', att='3857', lat=-12.3500, lon=40.5830, z0=2.38, conf=6, mer='+02:00', tz='Africa/Maputo', country='Mozambique',
      note='NP203 Part III S.240 (2015), Standardhafen, Zone -0200. N2/K2 inferiert. Nur Classic-1997 vorhanden.', infer=True,
      con={'M2':(1.14,77),'S2':(0.61,140),'K1':(0.08,76),'O1':(0.08,351)}),
 dict(name='Moc\xedmboa da Praia (NP203), Mozambique', att='3860', lat=-11.3330, lon=40.3670, z0=2.60, conf=6, mer='+02:00', tz='Africa/Maputo', country='Mozambique',
      note='NP203 Part III S.240 (2015), Standardhafen, Zone -0200. N2/K2 inferiert. Nur Classic-1997 vorhanden.', infer=True,
      con={'M2':(1.19,89),'S2':(0.60,132),'K1':(0.14,23),'O1':(0.09,31)}),

 # ---- NP203 Standard Ports S.241-242 (2015), Madagaskar/Ostafrika -- Classic-only-Upgrades ----
 # Koords aus Classic-1997 (regional verifiziert); Werte aus Flat-Scan 600dpi 2026-06-18.
 dict(name='Toamasina (NP203), Madagascar', att='3932', lat=-18.1600, lon=49.4270, z0=0.67, conf=5, mer='+03:00', tz='Indian/Antananarivo', country='Madagascar',
      note='NP203 Part III S.241 (2015), Standardhafen, Zone -0300. Kleiner Hub (M2 0.25 m). N2/K2 inferiert. Nur Classic-1997 vorhanden.', infer=True,
      con={'M2':(0.25,43),'S2':(0.09,45),'K1':(0.02,75),'O1':(0.04,64)}),
 dict(name='Antsiranana (Diego Suarez) (NP203), Madagascar', att='3949', lat=-12.2670, lon=49.2890, z0=1.43, conf=6, mer='+03:00', tz='Indian/Antananarivo', country='Madagascar',
      note='NP203 Part III S.241 (2015), Standardhafen, Zone -0300. N2/K2 inferiert. Nur Classic-1997 vorhanden.', infer=True,
      con={'M2':(0.59,99),'S2':(0.28,142),'K1':(0.11,53),'O1':(0.07,58)}),
 dict(name='Wasini Island (NP203), Kenya', att='4015', lat=-4.6580, lon=39.3660, z0=1.92, conf=6, mer='+03:00', tz='Africa/Nairobi', country='Kenya',
      note='NP203 Part III S.242 (2015), Standardhafen, Zone -0300. N2/K2 inferiert. Nur Classic-1997 vorhanden.', infer=True,
      con={'M2':(1.09,112),'S2':(0.63,153),'K1':(0.17,44),'O1':(0.11,41)}),
 dict(name='Mogadishu (NP203), Somalia', att='4038', lat=2.0330, lon=45.3500, z0=1.63, conf=6, mer='+03:00', tz='Africa/Mogadishu', country='Somalia',
      note='NP203 Part III S.242 (2015), Standardhafen, Zone -0300. N2/K2 inferiert. Nur Classic-1997 vorhanden.', infer=True,
      con={'M2':(0.68,113),'S2':(0.36,152),'K1':(0.21,36),'O1':(0.12,41)}),
 dict(name='Hobyo (NP203), Somalia', att='4043', lat=5.3490, lon=48.5300, z0=0.79, conf=6, mer='+03:00', tz='Africa/Mogadishu', country='Somalia',
      note='NP203 Part III S.242 (2015), Standardhafen, Zone -0300. N2/K2 inferiert. Nur Classic-1997 vorhanden.', infer=True,
      con={'M2':(0.43,108),'S2':(0.37,155),'K1':(0.33,48),'O1':(0.11,34)}),
 dict(name='Berbera (NP203), Somalia', att='4065', lat=10.4410, lon=45.0030, z0=1.56, conf=6, mer='+03:00', tz='Africa/Mogadishu', country='Somalia',
      note='NP203 Part III S.242 (2015), Standardhafen, Zone -0300 (Golf von Aden). N2/K2 inferiert. Nur Classic-1997 vorhanden.', infer=True,
      con={'M2':(0.47,225),'S2':(0.20,247),'K1':(0.46,34),'O1':(0.19,38)}),
 dict(name='Suez (As Suways) (NP203), Egypt', att='4112', lat=29.9360, lon=32.5580, z0=1.14, conf=6, mer='+02:00', tz='Africa/Cairo', country='Egypt',
      note='NP203 Part III S.242 (2015), Standardhafen, Zone -0200 (Golf von Suez). N2/K2 inferiert. Nur Classic-1997 vorhanden.', infer=True,
      con={'M2':(0.56,336),'S2':(0.39,14),'K1':(0.04,184),'O1':(0.01,198)}),

 # ---- NP203 Standard Ports S.243 (2015), Oman-Kueste, Zone -0400 -- GAP (Koords aus Geografie, conf niedriger) ----
 dict(name='Mirbat (Marbat) (NP203), Oman', att='4169', lat=16.9920, lon=54.6910, z0=1.32, conf=5, mer='+04:00', tz='Asia/Muscat', country='Oman',
      note='NP203 Part III S.243 (2015), Standardhafen, Zone -0400. N2/K2 inferiert. GAP (keine andere Quelle); Koord aus Geografie.', infer=True,
      con={'M2':(0.32,260),'S2':(0.14,290),'K1':(0.33,45),'O1':(0.19,41)}),
 dict(name='Al Hallaniyah (NP203), Oman', att='4170', lat=17.5030, lon=56.0130, z0=1.28, conf=4, mer='+04:00', tz='Asia/Muscat', country='Oman',
      note='NP203 Part III S.243 (2015), Standardhafen, Zone -0400 (Khuriya-Muriya-Inseln). N2/K2 inferiert. GAP; Koord aus Geografie (Insel).', infer=True,
      con={'M2':(0.33,263),'S2':(0.14,295),'K1':(0.32,39),'O1':(0.19,38)}),
 dict(name='Ras al Madrakah (NP203), Oman', att='4171', lat=18.9700, lon=57.8400, z0=1.56, conf=4, mer='+04:00', tz='Asia/Muscat', country='Oman',
      note='NP203 Part III S.243 (2015), Standardhafen, Zone -0400. N2/K2 inferiert. GAP; Koord aus Geografie (Kap).', infer=True,
      con={'M2':(0.43,271),'S2':(0.17,302),'K1':(0.39,41),'O1':(0.19,38)}),
 dict(name='Mahawt (NP203), Oman', att='4175', lat=20.4700, lon=58.1100, z0=1.79, conf=4, mer='+04:00', tz='Asia/Muscat', country='Oman',
      note='NP203 Part III S.243 (2015), Standardhafen, Zone -0400 (Masirah-Kanal/Barr al Hikman). N2/K2 inferiert. GAP; Koord aus Geografie.', infer=True,
      con={'M2':(0.63,278),'S2':(0.27,313),'K1':(0.42,43),'O1':(0.20,38)}),
 dict(name='Ras Suwadi (NP203), Oman', att='4188', lat=23.8600, lon=57.7800, z0=1.86, conf=4, mer='+04:00', tz='Asia/Muscat', country='Oman',
      note='NP203 Part III S.243 (2015), Standardhafen, Zone -0400 (Batinah-Kueste). N2/K2 inferiert. GAP; Koord aus Geografie.', infer=True,
      con={'M2':(0.65,274),'S2':(0.23,305),'K1':(0.38,40),'O1':(0.20,37)}),
 dict(name='Al Khaburah (NP203), Oman', att='4189a', lat=23.9700, lon=57.1000, z0=1.90, conf=5, mer='+04:00', tz='Asia/Muscat', country='Oman',
      note='NP203 Part III S.243 (2015), Standardhafen, Zone -0400 (Batinah-Kueste). N2/K2 inferiert. GAP; Koord aus Geografie.', infer=True,
      con={'M2':(0.69,275),'S2':(0.26,307),'K1':(0.40,46),'O1':(0.21,40)}),
 dict(name='Saham (NP203), Oman', att='4189b', lat=24.1700, lon=56.8900, z0=1.90, conf=5, mer='+04:00', tz='Asia/Muscat', country='Oman',
      note='NP203 Part III S.243 (2015), Standardhafen, Zone -0400 (Batinah-Kueste). N2/K2 inferiert. GAP; Koord aus Geografie.', infer=True,
      con={'M2':(0.68,275),'S2':(0.27,308),'K1':(0.45,42),'O1':(0.21,39)}),
 dict(name='Shinas (NP203), Oman', att='4191', lat=24.7400, lon=56.4700, z0=2.10, conf=5, mer='+04:00', tz='Asia/Muscat', country='Oman',
      note='NP203 Part III S.243 (2015), Standardhafen, Zone -0400 (Batinah-Kueste). N2/K2 inferiert. GAP; Koord aus Geografie.', infer=True,
      con={'M2':(0.70,274),'S2':(0.27,307),'K1':(0.41,39),'O1':(0.21,35)}),

 # ---- NP203 Standard Ports S.247 (2015), Gujarat (Golf von Kutch/Kathiawar), Zone -0530, makrotidal ----
 dict(name='Kandla (NP203), India', att='4330', lat=23.0200, lon=70.2200, z0=3.68, conf=6, mer='+05:30', tz='Asia/Kolkata', country='India',
      note='NP203 Part III S.247 (2015), Standardhafen, Zone -0530 (Golf von Kutch). N2/K2 inferiert. Nur Classic-1997 vorhanden.', infer=True,
      con={'M2':(2.34,46),'S2':(0.66,107),'K1':(0.50,88),'O1':(0.24,77)}),
 dict(name='Navlakhi (NP203), India', att='4331', lat=22.9500, lon=70.4500, z0=4.15, conf=6, mer='+05:30', tz='Asia/Kolkata', country='India',
      note='NP203 Part III S.247 (2015), Standardhafen, Zone -0530 (Golf von Kutch). N2/K2 inferiert. Nur Classic-1997 vorhanden.', infer=True,
      con={'M2':(2.48,78),'S2':(0.68,129),'K1':(0.51,98),'O1':(0.24,84)}),
 dict(name='Okha (NP203), India', att='4335', lat=22.4700, lon=69.0800, z0=2.04, conf=6, mer='+05:30', tz='Asia/Kolkata', country='India',
      note='NP203 Part III S.247 (2015), Standardhafen, Zone -0530. N2/K2 inferiert. Nur Classic-1997 vorhanden.', infer=True,
      con={'M2':(1.12,8),'S2':(0.35,41),'K1':(0.43,67),'O1':(0.21,65)}),
 dict(name='Veraval (NP203), India', att='4340', lat=20.9100, lon=70.3700, z0=1.33, conf=6, mer='+05:30', tz='Asia/Kolkata', country='India',
      note='NP203 Part III S.247 (2015), Standardhafen, Zone -0530. N2/K2 inferiert. Nur Classic-1997 vorhanden.', infer=True,
      con={'M2':(0.50,20),'S2':(0.24,61),'K1':(0.44,47),'O1':(0.18,67)}),
 dict(name='Kori Creek Entrance (NP203), India', att='4325', lat=23.6000, lon=68.5000, z0=1.94, conf=5, mer='+05:30', tz='Asia/Kolkata', country='India',
      note='NP203 Part III S.247 (2015), Standardhafen, Zone -0530 (Indien/Pakistan-Grenze). N2/K2 inferiert. GAP; Koord aus Geografie.', infer=True,
      con={'M2':(1.00,100),'S2':(0.64,132),'K1':(0.74,37),'O1':(0.19,74)}),
 dict(name='Mandvi (NP203), India', att='4328', lat=22.8300, lon=69.3500, z0=2.59, conf=5, mer='+05:30', tz='Asia/Kolkata', country='India',
      note='NP203 Part III S.247 (2015), Standardhafen, Zone -0530 (Kutch). N2/K2 inferiert. GAP; Koord aus Geografie.', infer=True,
      con={'M2':(1.24,42),'S2':(0.36,80),'K1':(0.44,75),'O1':(0.22,79)}),
 dict(name='Salaya Harbour (NP203), India', att='4334', lat=22.3100, lon=69.6000, z0=3.11, conf=5, mer='+05:30', tz='Asia/Kolkata', country='India',
      note='NP203 Part III S.247 (2015), Standardhafen, Zone -0530 (Golf von Kutch). N2/K2 inferiert. GAP; Koord aus Geografie.', infer=True,
      con={'M2':(1.86,49),'S2':(0.48,86),'K1':(0.48,77),'O1':(0.25,75)}),

 # ---- NP203 Standard Ports S.248 (2015), Konkan-Kueste (Maharashtra), Zone -0530, makrotidal -- GAP ----
 dict(name='Valsad (NP203), India', att='4355', lat=20.6300, lon=72.9300, z0=3.84, conf=5, mer='+05:30', tz='Asia/Kolkata', country='India',
      note='NP203 Part III S.248 (2015), Standardhafen, Zone -0530. N2/K2 inferiert. GAP; Koord aus Geografie.', infer=True,
      con={'M2':(1.86,68),'S2':(0.72,107),'K1':(0.74,71),'O1':(0.25,65)}),
 dict(name='Dahanu (NP203), India', att='4356', lat=19.9700, lon=72.7100, z0=2.84, conf=5, mer='+05:30', tz='Asia/Kolkata', country='India',
      note='NP203 Part III S.248 (2015), Standardhafen, Zone -0530. N2/K2 inferiert. GAP; Koord aus Geografie.', infer=True,
      con={'M2':(1.45,41),'S2':(0.59,80),'K1':(0.60,53),'O1':(0.25,50)}),
 dict(name='Satpati (NP203), India', att='4357', lat=19.7200, lon=72.6900, z0=3.09, conf=5, mer='+05:30', tz='Asia/Kolkata', country='India',
      note='NP203 Part III S.248 (2015), Standardhafen, Zone -0530. N2/K2 inferiert. GAP; Koord aus Geografie.', infer=True,
      con={'M2':(1.30,16),'S2':(0.51,53),'K1':(0.68,43),'O1':(0.24,21)}),
 dict(name='Vasai (Bassein) (NP203), India', att='4358', lat=19.3300, lon=72.8100, z0=2.53, conf=5, mer='+05:30', tz='Asia/Kolkata', country='India',
      note='NP203 Part III S.248 (2015), Standardhafen, Zone -0530. N2/K2 inferiert. GAP; Koord aus Geografie.', infer=True,
      con={'M2':(1.20,6),'S2':(0.44,45),'K1':(0.48,60),'O1':(0.24,21)}),
 dict(name='Trombay (NP203), India', att='4360', lat=19.0000, lon=72.9500, z0=2.52, conf=4, mer='+05:30', tz='Asia/Kolkata', country='India',
      note='NP203 Part III S.248 (2015), Standardhafen, Zone -0530 (Mumbai-Bucht). N2/K2 inferiert. GAP; Koord aus Geografie.', infer=True,
      con={'M2':(1.34,350),'S2':(0.51,30),'K1':(0.47,64),'O1':(0.18,55)}),
 dict(name='Revadanda (Chaul) (NP203), India', att='4364', lat=18.5500, lon=72.9200, z0=2.41, conf=5, mer='+05:30', tz='Asia/Kolkata', country='India',
      note='NP203 Part III S.248 (2015), Standardhafen, Zone -0530. N2/K2 inferiert. GAP; Koord aus Geografie.', infer=True,
      con={'M2':(1.03,335),'S2':(0.39,12),'K1':(0.45,58),'O1':(0.19,48)}),
 dict(name='Bankot (NP203), India', att='4366', lat=17.9800, lon=73.0500, z0=1.96, conf=5, mer='+05:30', tz='Asia/Kolkata', country='India',
      note='NP203 Part III S.248 (2015), Standardhafen, Zone -0530. N2/K2 inferiert. GAP; Koord aus Geografie.', infer=True,
      con={'M2':(0.84,328),'S2':(0.31,6),'K1':(0.36,56),'O1':(0.17,57)}),

 # ---- NP203 Standard Ports S.248 (2015), Goa/Karnataka/Kerala, Zone -0530 ----
 dict(name='Vijayadurg Harbour (NP203), India', att='4372', lat=16.5700, lon=73.3300, z0=1.37, conf=5, mer='+05:30', tz='Asia/Kolkata', country='India',
      note='NP203 Part III S.248 (2015), Standardhafen, Zone -0530. N2/K2 inferiert. GAP; Koord aus Geografie.', infer=True,
      con={'M2':(0.64,310),'S2':(0.23,346),'K1':(0.39,52),'O1':(0.16,55)}),
 dict(name='Devgarh (NP203), India', att='4373', lat=16.3800, lon=73.3800, z0=1.38, conf=5, mer='+05:30', tz='Asia/Kolkata', country='India',
      note='NP203 Part III S.248 (2015), Standardhafen, Zone -0530. N2/K2 inferiert. GAP; Koord aus Geografie.', infer=True,
      con={'M2':(0.59,310),'S2':(0.23,351),'K1':(0.48,52),'O1':(0.16,49)}),
 dict(name='Malvan (NP203), India', att='4374', lat=16.0600, lon=73.4600, z0=1.17, conf=5, mer='+05:30', tz='Asia/Kolkata', country='India',
      note='NP203 Part III S.248 (2015), Standardhafen, Zone -0530. N2/K2 inferiert. GAP; Koord aus Geografie.', infer=True,
      con={'M2':(0.58,311),'S2':(0.19,350),'K1':(0.32,51),'O1':(0.16,51)}),
 dict(name='Vengurla (NP203), India', att='4375', lat=15.8600, lon=73.6300, z0=1.19, conf=5, mer='+05:30', tz='Asia/Kolkata', country='India',
      note='NP203 Part III S.248 (2015), Standardhafen, Zone -0530. N2/K2 inferiert. GAP; Koord aus Geografie.', infer=True,
      con={'M2':(0.55,311),'S2':(0.19,347),'K1':(0.31,54),'O1':(0.16,51)}),
 dict(name='Betul (NP203), India', att='4378', lat=15.1500, lon=73.9500, z0=1.00, conf=5, mer='+05:30', tz='Asia/Kolkata', country='India',
      note='NP203 Part III S.248 (2015), Standardhafen, Zone -0530 (Goa). N2/K2 inferiert. GAP; Koord aus Geografie.', infer=True,
      con={'M2':(0.49,318),'S2':(0.17,1),'K1':(0.34,59),'O1':(0.15,55)}),
 dict(name='Karwar (NP203), India', att='4379', lat=14.8100, lon=74.1300, z0=1.18, conf=6, mer='+05:30', tz='Asia/Kolkata', country='India',
      note='NP203 Part III S.248 (2015), Standardhafen, Zone -0530. N2/K2 inferiert. Nur Classic-1997 vorhanden.', infer=True,
      con={'M2':(0.52,325),'S2':(0.18,4),'K1':(0.30,61),'O1':(0.15,59)}),
 dict(name='Bhatkal (NP203), India', att='4381', lat=13.9700, lon=74.5500, z0=0.70, conf=5, mer='+05:30', tz='Asia/Kolkata', country='India',
      note='NP203 Part III S.248 (2015), Standardhafen, Zone -0530. N2/K2 inferiert. GAP; Koord aus Geografie.', infer=True,
      con={'M2':(0.36,325),'S2':(0.16,16),'K1':(0.29,48),'O1':(0.08,49)}),
 dict(name='Kasaragod (NP203), India', att='4386', lat=12.5000, lon=74.9900, z0=0.89, conf=5, mer='+05:30', tz='Asia/Kolkata', country='India',
      note='NP203 Part III S.248 (2015), Standardhafen, Zone -0530. N2/K2 inferiert. GAP; Koord aus Geografie.', infer=True,
      con={'M2':(0.35,322),'S2':(0.11,13),'K1':(0.25,54),'O1':(0.13,56)}),
 dict(name='Calicut (Kozhikode) (NP203), India', att='4389', lat=11.2500, lon=75.7700, z0=0.96, conf=5, mer='+05:30', tz='Asia/Kolkata', country='India',
      note='NP203 Part III S.248 (2015), Standardhafen, Zone -0530. N2/K2 inferiert. GAP; Koord aus Geografie.', infer=True,
      con={'M2':(0.32,323),'S2':(0.10,22),'K1':(0.16,49),'O1':(0.10,59)}),
 dict(name='Alleppey (Alappuzha) (NP203), India', att='4394', lat=9.5000, lon=76.3300, z0=0.55, conf=5, mer='+05:30', tz='Asia/Kolkata', country='India',
      note='NP203 Part III S.248 (2015), Standardhafen, Zone -0530. N2/K2 inferiert. GAP; Koord aus Geografie.', infer=True,
      con={'M2':(0.25,339),'S2':(0.10,45),'K1':(0.05,51),'O1':(0.08,50)}),

 # ---- NP203 Standard Ports S.248-249 (2015), Kerala-Sued + SE-Indien/Sri Lanka, Zone -0530 ----
 dict(name='Trivandrum (Vizhinjam) (NP203), India', att='4396', lat=8.4800, lon=76.9200, z0=0.55, conf=5, mer='+05:30', tz='Asia/Kolkata', country='India',
      note='NP203 Part III S.248 (2015), Standardhafen, Zone -0530. N2/K2 inferiert. GAP; Koord aus Geografie.', infer=True,
      con={'M2':(0.21,352),'S2':(0.11,82),'K1':(0.15,55),'O1':(0.07,45)}),
 dict(name='Nagappattinam (NP203), India', att='4447', lat=10.7700, lon=79.8400, z0=0.34, conf=6, mer='+05:30', tz='Asia/Kolkata', country='India',
      note='NP203 Part III S.249 (2015), Standardhafen, Zone -0530. N2/K2 inferiert. Nur Classic-1997 vorhanden.', infer=True,
      con={'M2':(0.20,254),'S2':(0.08,291),'K1':(0.06,351),'O1':(0.03,319)}),
 dict(name='Point Pedro (NP203), Sri Lanka', att='4439', lat=9.8300, lon=80.2300, z0=0.37, conf=4, mer='+05:30', tz='Asia/Colombo', country='Sri Lanka',
      note='NP203 Part III S.249 (2015), Standardhafen, Zone -0530. Kleiner Hub. N2/K2 inferiert. GAP (Sri Lanka, sonst keine Quelle); Koord aus Geografie.', infer=True,
      con={'M2':(0.21,242),'S2':(0.09,270),'K1':(0.07,332),'O1':(0.05,304)}),
 dict(name='Jaffna (NP203), Sri Lanka', att='4440', lat=9.6600, lon=80.0100, z0=0.40, conf=4, mer='+05:30', tz='Asia/Colombo', country='Sri Lanka',
      note='NP203 Part III S.249 (2015), Standardhafen, Zone -0530. Kleiner Hub (M2 0.15). N2/K2 inferiert. GAP; Koord aus Geografie.', infer=True,
      con={'M2':(0.15,79),'S2':(0.05,123),'K1':(0.04,91),'O1':(0.03,43)}),
 dict(name='Porto Novo (Parangipettai) (NP203), India', att='4448', lat=11.4900, lon=79.7600, z0=0.71, conf=4, mer='+05:30', tz='Asia/Kolkata', country='India',
      note='NP203 Part III S.249 (2015), Standardhafen, Zone -0530. N2/K2 inferiert. GAP; Koord aus Geografie.', infer=True,
      con={'M2':(0.20,250),'S2':(0.11,287),'K1':(0.08,343),'O1':(0.05,331)}),

 # ---- NP203 Standard Ports S.249 (2015), Andhra/Odisha/Westbengalen (Bengal-Trichter), Zone -0530 ----
 dict(name='Kakinada (NP203), India', att='4461', lat=16.9400, lon=82.2800, z0=0.87, conf=6, mer='+05:30', tz='Asia/Kolkata', country='India',
      note='NP203 Part III S.249 (2015), Standardhafen, Zone -0530. N2/K2 inferiert. Nur Classic-1997 vorhanden.', infer=True,
      con={'M2':(0.46,248),'S2':(0.20,285),'K1':(0.10,339),'O1':(0.05,328)}),
 dict(name='Bhimunipatnam (NP203), India', att='4464', lat=17.8900, lon=83.4500, z0=1.14, conf=5, mer='+05:30', tz='Asia/Kolkata', country='India',
      note='NP203 Part III S.249 (2015), Standardhafen, Zone -0530. N2/K2 inferiert. GAP; Koord aus Geografie.', infer=True,
      con={'M2':(0.44,239),'S2':(0.20,278),'K1':(0.11,330),'O1':(0.04,325)}),
 dict(name='Kalingapatnam (NP203), India', att='4466', lat=18.3300, lon=84.1300, z0=1.01, conf=5, mer='+05:30', tz='Asia/Kolkata', country='India',
      note='NP203 Part III S.249 (2015), Standardhafen, Zone -0530. N2/K2 inferiert. GAP; Koord aus Geografie.', infer=True,
      con={'M2':(0.48,245),'S2':(0.21,281),'K1':(0.10,347),'O1':(0.05,314)}),
 dict(name='Baruva (NP203), India', att='4468', lat=18.8800, lon=84.5700, z0=1.04, conf=5, mer='+05:30', tz='Asia/Kolkata', country='India',
      note='NP203 Part III S.249 (2015), Standardhafen, Zone -0530. N2/K2 inferiert. GAP; Koord aus Geografie.', infer=True,
      con={'M2':(0.45,244),'S2':(0.19,278),'K1':(0.11,337),'O1':(0.05,308)}),
 dict(name='Chilka Mouth (NP203), India', att='4471', lat=19.6100, lon=85.2100, z0=0.98, conf=5, mer='+05:30', tz='Asia/Kolkata', country='India',
      note='NP203 Part III S.249 (2015), Standardhafen, Zone -0530 (Chilika-Lagune). N2/K2 inferiert. GAP; Koord aus Geografie.', infer=True,
      con={'M2':(0.31,256),'S2':(0.12,302),'K1':(0.05,10),'O1':(0.03,309)}),
 dict(name='Devi River Entrance (NP203), India', att='4473', lat=20.1000, lon=86.3600, z0=1.65, conf=5, mer='+05:30', tz='Asia/Kolkata', country='India',
      note='NP203 Part III S.249 (2015), Standardhafen, Zone -0530. N2/K2 inferiert. GAP; Koord aus Geografie.', infer=True,
      con={'M2':(0.58,245),'S2':(0.22,290),'K1':(0.08,323),'O1':(0.04,332)}),
 dict(name='False Point (NP203), India', att='4474', lat=20.3300, lon=86.7900, z0=1.54, conf=5, mer='+05:30', tz='Asia/Kolkata', country='India',
      note='NP203 Part III S.249 (2015), Standardhafen, Zone -0530. N2/K2 inferiert. GAP; Koord aus Geografie.', infer=True,
      con={'M2':(0.69,255),'S2':(0.31,293),'K1':(0.12,340),'O1':(0.05,325)}),
 dict(name='Shortt Island (NP203), India', att='4475', lat=20.7833, lon=87.0667, z0=1.92, conf=5, mer='+05:30', tz='Asia/Kolkata', country='India',
      note='NP203 Part III S.249 (2015), Standardhafen, Zone -0530. N2/K2 inferiert. GAP; Koord aus Geografie.', infer=True,
      con={'M2':(0.92,262),'S2':(0.42,301),'K1':(0.11,347),'O1':(0.04,328)}),
 dict(name='Sagar Roads (NP203), India', att='4481', lat=21.6500, lon=88.0500, z0=3.00, conf=6, mer='+05:30', tz='Asia/Kolkata', country='India',
      note='NP203 Part III S.249 (2015), Standardhafen, Zone -0530 (Hooghly-Muendung). N2/K2 inferiert. Nur Classic-1997 vorhanden.', infer=True,
      con={'M2':(1.40,275),'S2':(0.66,315),'K1':(0.15,345),'O1':(0.05,327)}),

 # ---- NP203 Standard Ports S.244 (2015), Musandam (Oman) + UAE-Nord, Zone -0400 -- GAP ----
 dict(name='Al Lima (NP203), Oman', att='4194a', lat=25.9500, lon=56.4700, z0=1.84, conf=4, mer='+04:00', tz='Asia/Muscat', country='Oman',
      note='NP203 Part III S.244 (2015), Standardhafen, Zone -0400 (Musandam). N2/K2 inferiert. GAP; Koord aus Geografie.', infer=True,
      con={'M2':(0.70,287),'S2':(0.29,322),'K1':(0.30,46),'O1':(0.19,42)}),
 dict(name='Khasab (NP203), Oman', att='4199', lat=26.1800, lon=56.2400, z0=1.55, conf=5, mer='+04:00', tz='Asia/Muscat', country='Oman',
      note='NP203 Part III S.244 (2015), Standardhafen, Zone -0400 (Musandam). N2/K2 inferiert. GAP; Koord aus Geografie.', infer=True,
      con={'M2':(0.68,309),'S2':(0.26,347),'K1':(0.21,79),'O1':(0.16,63)}),
 dict(name='Bukha (NP203), Oman', att='4199b', lat=26.1500, lon=56.1500, z0=1.46, conf=5, mer='+04:00', tz='Asia/Muscat', country='Oman',
      note='NP203 Part III S.244 (2015), Standardhafen, Zone -0400 (Musandam). N2/K2 inferiert. GAP; Koord aus Geografie.', infer=True,
      con={'M2':(0.64,317),'S2':(0.24,358),'K1':(0.18,91),'O1':(0.15,81)}),
 dict(name='Saqr Port (Mina Saqr) (NP203), United Arab Emirates', att='4200', lat=25.9900, lon=56.0500, z0=1.40, conf=5, mer='+04:00', tz='Asia/Dubai', country='United Arab Emirates',
      note='NP203 Part III S.244 (2015), Standardhafen, Zone -0400. N2/K2 inferiert. GAP; Koord aus Geografie.', infer=True,
      con={'M2':(0.60,325),'S2':(0.24,4),'K1':(0.17,110),'O1':(0.15,75)}),
 dict(name='Ras al Khaymah (NP203), United Arab Emirates', att='4201', lat=25.8000, lon=55.9600, z0=1.37, conf=5, mer='+04:00', tz='Asia/Dubai', country='United Arab Emirates',
      note='NP203 Part III S.244 (2015), Standardhafen, Zone -0400. N2/K2 inferiert. GAP; Koord aus Geografie.', infer=True,
      con={'M2':(0.54,326),'S2':(0.20,11),'K1':(0.13,111),'O1':(0.16,88)}),
 dict(name='Umm al-Qaiwain (NP203), United Arab Emirates', att='4203', lat=25.5700, lon=55.5500, z0=1.10, conf=5, mer='+04:00', tz='Asia/Dubai', country='United Arab Emirates',
      note='NP203 Part III S.244 (2015), Standardhafen, Zone -0400. N2/K2 inferiert. GAP; Koord aus Geografie.', infer=True,
      con={'M2':(0.45,350),'S2':(0.13,32),'K1':(0.19,136),'O1':(0.17,95)}),

 # ---- NP203 Standard Ports S.245 (2015), Qatar-Nord, Zone -0300 -- GAP ----
 dict(name='Jabal al Fuwayrit (NP203), Qatar', att='4243', lat=26.0800, lon=51.3600, z0=0.90, conf=4, mer='+03:00', tz='Asia/Qatar', country='Qatar',
      note='NP203 Part III S.245 (2015), Standardhafen, Zone -0300. N2/K2 inferiert. GAP; Koord aus Geografie.', infer=True,
      con={'M2':(0.42,131),'S2':(0.13,178),'K1':(0.22,100),'O1':(0.12,47)}),
 dict(name="Ar Ru'ays (NP203), Qatar", att='4244', lat=26.1300, lon=51.2200, z0=1.20, conf=4, mer='+03:00', tz='Asia/Qatar', country='Qatar',
      note='NP203 Part III S.245 (2015), Standardhafen, Zone -0300. N2/K2 inferiert. GAP; Koord aus Geografie.', infer=True,
      con={'M2':(0.54,144),'S2':(0.19,196),'K1':(0.15,64),'O1':(0.07,343)}),

 # ---- NP203 Standard Ports S.246 (2015), Kopf des Golfs (Kuwait/Iraq/Iran), makrotidal ----
 dict(name='Mina al Ahmadi (NP203), Kuwait', att='4262', lat=29.0700, lon=48.1300, z0=1.72, conf=6, mer='+03:00', tz='Asia/Kuwait', country='Kuwait',
      note='NP203 Part III S.246 (2015), Standardhafen, Zone -0300. N2/K2 inferiert. Nur Classic-1997 vorhanden.', infer=True,
      con={'M2':(0.66,334),'S2':(0.22,28),'K1':(0.47,305),'O1':(0.32,256)}),
 dict(name='Ash Shuwaykh (Kuwait) (NP203), Kuwait', att='4263', lat=29.3500, lon=47.9300, z0=2.30, conf=5, mer='+03:00', tz='Asia/Kuwait', country='Kuwait',
      note='NP203 Part III S.246 (2015), Standardhafen, Zone -0300 (Kuwait City). N2/K2 inferiert. GAP; Koord aus Geografie.', infer=True,
      con={'M2':(0.95,345),'S2':(0.34,54),'K1':(0.52,310),'O1':(0.33,261)}),
 dict(name='Mina ad Dawhah (Kuwait) (NP203), Kuwait', att='4264', lat=29.3800, lon=47.8300, z0=2.17, conf=4, mer='+03:00', tz='Asia/Kuwait', country='Kuwait',
      note='NP203 Part III S.246 (2015), Standardhafen, Zone -0300. N2/K2 inferiert. GAP; Koord aus Geografie.', infer=True,
      con={'M2':(0.95,341),'S2':(0.33,54),'K1':(0.51,309),'O1':(0.33,267)}),
 dict(name='Hadd Warbah (NP203), Iraq', att='4266', lat=29.9500, lon=48.3000, z0=2.44, conf=4, mer='+03:00', tz='Asia/Baghdad', country='Iraq',
      note='NP203 Part III S.246 (2015), Standardhafen, Zone -0300 (Warbah-Insel). N2/K2 inferiert. GAP; Koord aus Geografie.', infer=True,
      con={'M2':(1.26,343),'S2':(0.43,57),'K1':(0.66,306),'O1':(0.31,264)}),
 dict(name='Shatt al Arab Outer Bar (NP203), Iraq', att='4268', lat=29.7500, lon=48.8000, z0=1.74, conf=4, mer='+03:00', tz='Asia/Baghdad', country='Iraq',
      note='NP203 Part III S.246 (2015), Standardhafen, Zone -0300. N2/K2 inferiert. GAP; Koord aus Geografie.', infer=True,
      con={'M2':(0.84,308),'S2':(0.29,9),'K1':(0.50,295),'O1':(0.30,247)}),
 dict(name='Al Basrah Oil Terminal (ABOT) (NP203), Iraq', att='4268a', lat=29.6800, lon=48.8000, z0=1.77, conf=5, mer='+03:00', tz='Asia/Baghdad', country='Iraq',
      note='NP203 Part III S.246 (2015), Standardhafen, Zone -0300. N2/K2 inferiert. GAP; Koord aus Geografie.', infer=True,
      con={'M2':(0.96,306),'S2':(0.31,7),'K1':(0.61,294),'O1':(0.33,246)}),
 dict(name='Khowr-e Musa Bar (NP203), Iran', att='4277', lat=30.0000, lon=49.0000, z0=2.20, conf=5, mer='+03:30', tz='Asia/Tehran', country='Iran',
      note='NP203 Part III S.246 (2015), Standardhafen, Zone -0330. N2/K2 inferiert. Nur Classic-1997 vorhanden.', infer=True,
      con={'M2':(0.87,314),'S2':(0.31,15),'K1':(0.51,301),'O1':(0.33,270)}),
 dict(name='Bandar Deylam (NP203), Iran', att='4280', lat=30.0500, lon=50.1600, z0=1.45, conf=5, mer='+03:30', tz='Asia/Tehran', country='Iran',
      note='NP203 Part III S.246 (2015), Standardhafen, Zone -0330. N2/K2 inferiert. GAP; Koord aus Geografie.', infer=True,
      con={'M2':(0.65,276),'S2':(0.25,34),'K1':(0.42,290),'O1':(0.33,252)}),
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
