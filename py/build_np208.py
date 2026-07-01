#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ADMIRALTY NP208 (ATT Vol.8, 2026) Part III -> XTide-Harmonics.

SO-Atlantik / Westafrika / Mittelmeer. Standard-Port-Werte visuell aus den
Part-III-Scans gelesen (OCR unzuverlaessig). Simplified Harmonic Method:
Z0/M2/S2/K1/O1 + SW-Korrekturen f4/F4 (->M4) und f6/F6 (->M6). N2/K2 bei
makrotidalen Stationen inferiert (NP208 fuehrt sie nicht).

Zone->Meridian: mer = -(ATT-Zone). Zone -0100 -> +01:00; Zone UT(GMT) -> +00:00;
Zone +0100 (Azoren/Kap Verde) -> -01:00; Zone -0200 -> +02:00.

BATCH 1: Westafrika-Kueste + Atlantik-Inseln (Ersatz fuer classic-1997/FES2022).
Scan-Index: harmonics/help/np208_scan_index.md

Schreibt harmonics/att/harmonics_att_np208.txt (ISO-8859-1).
"""
import os, re

HARM = os.path.expanduser('~/harmonics')
LIT  = f'{HARM}/classic/harmonics_literature.txt'
OUT  = f'{HARM}/att/harmonics_att_np208.txt'

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

def infer_n2k2(con):
    out=dict(con)
    if 'M2' in con and 'S2' in con:
        aM2,gM2=con['M2']; aS2,gS2=con['S2']
        if 'N2' not in out: out['N2']=(round(0.19*aM2,4),(gM2-0.536*(gS2-gM2))%360)
        if 'K2' not in out: out['K2']=(round(0.27*aS2,4),gS2%360)
    return out

# con: {Konstituente: (Amplitude m, Phase g in Zonenzeit)}. M4=(F4,f4), M6=(F6,f6).
STATIONS = [
 # ===== Atlantik-Inseln (Seite 299) =====
 dict(name='Vila do Porto, Santa Maria, Açores, Portugal', att='3469', lat=36.950, lon=-25.150, z0=1.00, conf=6,
      mer='-01:00', tz='Atlantic/Azores', country='Portugal', infer=False,
      note='NP208 Part III S.299, Standardhafen, Zone +0100 (Azoren). Ersetzt classic-1997.',
      con={'M2':(0.48,35),'S2':(0.19,54),'K1':(0.03,51),'O1':(0.03,295)}),
 dict(name='Mindelo (Porto Grande Bay), São Vicente, Cape Verde', att='3492', lat=16.887, lon=-24.993, z0=0.80, conf=6,
      mer='-01:00', tz='Atlantic/Cape_Verde', country='Cape Verde', infer=False,
      note='NP208 Part III S.299 (Porto Grande de S. Vicente), Zone +0100. Ersetzt classic-1997.',
      con={'M2':(0.31,224),'S2':(0.12,280),'K1':(0.05,336),'O1':(0.04,229)}),

 # ===== Marokko (Seite 300, Zone -0100) =====
 dict(name='Rabat, Morocco', att='3509', lat=34.036, lon=-6.836, z0=2.17, conf=7,
      mer='+01:00', tz='Africa/Casablanca', country='Morocco', infer=True,
      note='NP208 Part III S.300, Standardhafen, Zone -0100. N2/K2 inferiert. Ersetzt classic-1997.',
      con={'M2':(0.88,88),'S2':(0.35,113),'K1':(0.06,73),'O1':(0.04,318)}),
 dict(name='Casablanca (Port), Morocco', att='3511', lat=33.607, lon=-7.617, z0=2.24, conf=7,
      mer='+01:00', tz='Africa/Casablanca', country='Morocco', infer=True,
      note='NP208 Part III S.300, Standardhafen, Zone -0100. M4 (f4). N2/K2 inferiert. Ersetzt classic-1997.',
      con={'M2':(1.00,82),'S2':(0.36,109),'K1':(0.07,64),'O1':(0.06,321),'M4':(0.011,52)}),
 dict(name='Agadir, Morocco', att='3518', lat=30.421, lon=-9.638, z0=2.17, conf=7,
      mer='+01:00', tz='Africa/Casablanca', country='Morocco', infer=True,
      note='NP208 Part III S.300, Standardhafen, Zone -0100. N2/K2 inferiert. Ersetzt classic-1997.',
      con={'M2':(0.92,71),'S2':(0.35,94),'K1':(0.06,49),'O1':(0.05,316)}),

 # ===== Westsahara / Mauretanien / Senegambien (Seite 300, Zone UT(GMT)) =====
 dict(name='Boujdour, Western Sahara', att='3524', lat=26.116, lon=-14.497, z0=1.17, conf=6,
      mer='+00:00', tz='Africa/El_Aaiun', country='Western Sahara', infer=True,
      note='NP208 Part III S.300 (Cabo Bojador), Zone UT(GMT). N2/K2 inferiert. Ersetzt classic-1997.',
      con={'M2':(0.61,19),'S2':(0.25,49),'K1':(0.05,32),'O1':(0.04,285)}),
 dict(name='Dakhla, Western Sahara', att='3526', lat=23.662, lon=-15.941, z0=1.28, conf=6,
      mer='+00:00', tz='Africa/El_Aaiun', country='Western Sahara', infer=True,
      note='NP208 Part III S.300 (Ad-Dakhla, Villa Cisneros Bar), Zone UT(GMT). M4 (f4). N2/K2 inferiert. Ersetzt classic-1997.',
      con={'M2':(0.67,11),'S2':(0.27,43),'K1':(0.06,34),'O1':(0.04,266),'M4':(0.064,13)}),
 dict(name='Nouadhibou, Mauritania', att='3529', lat=20.905, lon=-17.043, z0=1.32, conf=7,
      mer='+00:00', tz='Africa/Nouakchott', country='Mauritania', infer=True,
      note='NP208 Part III S.300, Standardhafen, Zone UT(GMT). N2/K2 inferiert. Ersetzt classic-1997.',
      con={'M2':(0.55,341),'S2':(0.24,28),'K1':(0.06,14),'O1':(0.02,323)}),
 dict(name='Saint-Louis, Senegal', att='3534', lat=16.026, lon=-16.510, z0=1.03, conf=6,
      mer='+00:00', tz='Africa/Dakar', country='Senegal', infer=True,
      note='NP208 Part III S.300 (St. Louis), Zone UT(GMT). N2/K2 inferiert. Ersetzt classic-1997.',
      con={'M2':(0.39,283),'S2':(0.16,320),'K1':(0.06,353),'O1':(0.04,270)}),
 dict(name='Banjul, Gambia', att='3544', lat=13.444, lon=-16.572, z0=0.98, conf=7,
      mer='+00:00', tz='Africa/Banjul', country='Gambia', infer=True,
      note='NP208 Part III S.300, Standardhafen, Zone UT(GMT). N2/K2 inferiert. Ersetzt classic-1997.',
      con={'M2':(0.54,288),'S2':(0.18,327),'K1':(0.06,13),'O1':(0.04,269)}),
 dict(name='Diogué (Casamance), Senegal', att='3552', lat=12.571, lon=-16.742, z0=1.02, conf=6,
      mer='+00:00', tz='Africa/Dakar', country='Senegal', infer=True,
      note='NP208 Part III S.300 (Pointe de Diogue), Zone UT(GMT). N2/K2 inferiert. Ersetzt classic-1997.',
      con={'M2':(0.49,269),'S2':(0.17,305),'K1':(0.07,2),'O1':(0.03,250)}),
 dict(name='Cacheu, Guinea-Bissau', att='3557', lat=12.279, lon=-16.165, z0=1.60, conf=6,
      mer='+00:00', tz='Africa/Bissau', country='Guinea-Bissau', infer=True,
      note='NP208 Part III S.300, Zone UT(GMT). M4 (f4). N2/K2 inferiert. Ersetzt classic-1997.',
      con={'M2':(0.92,322),'S2':(0.24,5),'K1':(0.08,15),'O1':(0.04,292),'M4':(0.105,183)}),
 dict(name='Caio, Guinea-Bissau', att='3559', lat=11.923, lon=-16.214, z0=1.90, conf=6,
      mer='+00:00', tz='Africa/Bissau', country='Guinea-Bissau', infer=True,
      note='NP208 Part III S.300 (Ilheu de Caio), Zone UT(GMT). N2/K2 inferiert. Ersetzt classic-1997.',
      con={'M2':(1.00,302),'S2':(0.28,339),'K1':(0.09,6),'O1':(0.04,267)}),
 dict(name='Bissau, Guinea-Bissau', att='3561', lat=11.858, lon=-15.577, z0=2.89, conf=7,
      mer='+00:00', tz='Africa/Bissau', country='Guinea-Bissau', infer=True,
      note='NP208 Part III S.300, Standardhafen, Zone UT(GMT). M4 (f4). N2/K2 inferiert. Ersetzt classic-1997.',
      con={'M2':(1.81,343),'S2':(0.49,27),'K1':(0.12,34),'O1':(0.05,281),'M4':(0.036,242)}),
 dict(name='Bolama, Guinea-Bissau', att='3567', lat=11.579, lon=-15.471, z0=2.88, conf=6,
      mer='+00:00', tz='Africa/Bissau', country='Guinea-Bissau', infer=True,
      note='NP208 Part III S.300, Zone UT(GMT). M4 (f4). N2/K2 inferiert. Ersetzt classic-1997.',
      con={'M2':(1.76,317),'S2':(0.50,359),'K1':(0.17,24),'O1':(0.05,286),'M4':(0.019,174)}),
 dict(name='Bubaque, Guinea-Bissau', att='3568', lat=11.300, lon=-15.826, z0=2.54, conf=6,
      mer='+00:00', tz='Africa/Bissau', country='Guinea-Bissau', infer=True,
      note='NP208 Part III S.300, Zone UT(GMT). M4 (f4). N2/K2 inferiert. Ersetzt classic-1997.',
      con={'M2':(1.45,294),'S2':(0.40,336),'K1':(0.10,6),'O1':(0.05,261),'M4':(0.019,214)}),
 dict(name='Port Kamsar, Guinea', att='3571', lat=10.650, lon=-14.617, z0=3.03, conf=7,
      mer='+00:00', tz='Africa/Conakry', country='Guinea', infer=True,
      note='NP208 Part III S.300, Standardhafen, Zone UT(GMT). M4/M6 (f4/f6). N2/K2 inferiert. Bezugshafen fuer Part-II-Transfer.',
      con={'M2':(1.65,260),'S2':(0.54,299),'K1':(0.11,5),'O1':(0.03,276),'M4':(0.022,226),'M6':(0.001,176)}),
 dict(name='Conakry, Guinea', att='3575', lat=9.502, lon=-13.715, z0=2.18, conf=7,
      mer='+00:00', tz='Africa/Conakry', country='Guinea', infer=True,
      note='NP208 Part III S.300, Standardhafen, Zone UT(GMT). N2/K2 inferiert. Ersetzt classic-1997.',
      con={'M2':(1.12,231),'S2':(0.39,265),'K1':(0.12,352),'O1':(0.03,271)}),
 dict(name='Freetown, Sierra Leone', att='3580', lat=8.492, lon=-13.275, z0=1.76, conf=7,
      mer='+00:00', tz='Africa/Freetown', country='Sierra Leone', infer=True,
      note='NP208 Part III S.300, Standardhafen, Zone UT(GMT). M4/M6 (f4/f6). N2/K2 inferiert. Ersetzt classic-1997.',
      con={'M2':(0.98,226),'S2':(0.33,255),'K1':(0.11,360),'O1':(0.03,252),'M4':(0.014,267),'M6':(0.013,120)}),
 dict(name='Monrovia, Liberia', att='3595', lat=6.333, lon=-10.800, z0=0.90, conf=7,
      mer='+00:00', tz='Africa/Monrovia', country='Liberia', infer=True,
      note='NP208 Part III S.300, Standardhafen, Zone UT(GMT). M4 (f4). N2/K2 inferiert. Ersetzt classic-1997.',
      con={'M2':(0.40,191),'S2':(0.13,222),'K1':(0.08,352),'O1':(0.02,265),'M4':(0.034,138)}),

 # ===== Côte d'Ivoire / Ghana Bezugshäfen (Seiten 300/301, Zone UT(GMT)) =====
 dict(name='Abidjan (Canal de Vridi), Côte d\'Ivoire', att='3615', lat=5.250, lon=-4.000, z0=0.72, conf=7,
      mer='+00:00', tz='Africa/Abidjan', country="Côte d'Ivoire", infer=True,
      note='NP208 Part III S.300, Standardhafen, Zone UT(GMT). N2/K2 inferiert. Bezugshafen.',
      con={'M2':(0.29,140),'S2':(0.13,169),'K1':(0.09,343),'O1':(0.01,321)}),
 dict(name='Takoradi, Ghana', att='3621', lat=4.883, lon=-1.750, z0=0.76, conf=7,
      mer='+00:00', tz='Africa/Accra', country='Ghana', infer=True,
      note='NP208 Part III S.300, Standardhafen, Zone UT(GMT). M4/M6 (f4/f6). N2/K2 inferiert. Bezugshafen.',
      con={'M2':(0.44,114),'S2':(0.14,143),'K1':(0.11,354),'O1':(0.03,316),'M4':(0.007,133),'M6':(0.004,167)}),
 dict(name='Tema, Ghana', att='3627', lat=5.633, lon=0.017, z0=0.88, conf=7,
      mer='+00:00', tz='Africa/Accra', country='Ghana', infer=True,
      note='NP208 Part III S.301, Standardhafen, Zone UT(GMT). M4 (f4). N2/K2 inferiert. Bezugshafen.',
      con={'M2':(0.49,107),'S2':(0.17,135),'K1':(0.13,354),'O1':(0.03,329),'M4':(0.004,94)}),

 # ===== Togo / Nigeria / Kamerun / Äq.-Guinea (Seite 301) =====
 dict(name='Lomé, Togo', att='3630', lat=6.135, lon=1.286, z0=1.15, conf=7,
      mer='+00:00', tz='Africa/Lome', country='Togo', infer=True,
      note='NP208 Part III S.301, Standardhafen, Zone UT(GMT). N2/K2 inferiert. Ersetzt classic-1997.',
      con={'M2':(0.50,108),'S2':(0.16,143),'K1':(0.18,352),'O1':(0.02,340)}),
 dict(name='Akassa, Nigeria', att='3654', lat=4.317, lon=6.067, z0=0.98, conf=6,
      mer='+01:00', tz='Africa/Lagos', country='Nigeria', infer=True,
      note='NP208 Part III S.301, Zone -0100. M4 (f4). N2/K2 inferiert. Ersetzt classic-1997.',
      con={'M2':(0.53,146),'S2':(0.16,180),'K1':(0.12,28),'O1':(0.03,314),'M4':(0.151,168)}),
 dict(name='Bonny, Nigeria', att='3662', lat=4.450, lon=7.167, z0=1.46, conf=7,
      mer='+01:00', tz='Africa/Lagos', country='Nigeria', infer=True,
      note='NP208 Part III S.301 (Bonny Town), Standardhafen, Zone -0100. M4/M6 (f4/f6). N2/K2 inferiert. Ersetzt classic-1997.',
      con={'M2':(0.71,149),'S2':(0.23,187),'K1':(0.13,18),'O1':(0.02,343),'M4':(0.086,175),'M6':(0.003,316)}),
 dict(name='Apapa (Lagos), Nigeria', att='3636', lat=6.450, lon=3.383, z0=0.88, conf=7,
      mer='+01:00', tz='Africa/Lagos', country='Nigeria', infer=True,
      note='NP208 Part III S.301, Standardhafen, Zone -0100. M4/M6 (f4/f6). N2/K2 inferiert. Bezugshafen.',
      con={'M2':(0.24,151),'S2':(0.07,181),'K1':(0.07,31),'O1':(0.01,12),'M4':(0.067,53),'M6':(0.150,342)}),
 dict(name='Warri, Nigeria', att='3648', lat=5.517, lon=5.733, z0=1.04, conf=7,
      mer='+01:00', tz='Africa/Lagos', country='Nigeria', infer=True,
      note='NP208 Part III S.301, Standardhafen, Zone -0100. M4/M6 (f4/f6). N2/K2 inferiert. Bezugshafen.',
      con={'M2':(0.42,252),'S2':(0.09,296),'K1':(0.11,75),'O1':(0.03,293),'M4':(0.555,171),'M6':(0.398,15)}),
 dict(name="Man O' War Bay, Cameroon", att='3680', lat=3.961, lon=9.219, z0=1.2, conf=5,
      mer='+01:00', tz='Africa/Douala', country='Cameroon', infer=True,
      note='NP208 Part III S.301, Zone -0100. N2/K2 inferiert. Ersetzt classic-1997.',
      con={'M2':(0.56,130),'S2':(0.19,161),'K1':(0.11,10),'O1':(0.03,318)}),
 dict(name='Douala, Cameroon', att='3684', lat=4.041, lon=9.676, z0=1.62, conf=7,
      mer='+01:00', tz='Africa/Douala', country='Cameroon', infer=True,
      note='NP208 Part III S.301, Standardhafen, Zone -0100. M4/M6 (f4/f6). N2/K2 inferiert. Ersetzt classic-1997.',
      con={'M2':(0.79,167),'S2':(0.24,211),'K1':(0.14,30),'O1':(0.01,344),'M4':(0.139,212),'M6':(0.029,69)}),
 dict(name='Luba (Bioko), Equatorial Guinea', att='3691', lat=3.461, lon=8.555, z0=1.02, conf=6,
      mer='+01:00', tz='Africa/Malabo', country='Equatorial Guinea', infer=True,
      note='NP208 Part III S.301 (Bahia de Luba, San Carlos), Zone -0100. M4 (f4). N2/K2 inferiert. Ersetzt classic-1997.',
      con={'M2':(0.52,131),'S2':(0.19,165),'K1':(0.11,14),'O1':(0.03,328),'M4':(0.098,162)}),
 dict(name='Bata, Equatorial Guinea', att='3698', lat=1.873, lon=9.771, z0=1.02, conf=7,
      mer='+01:00', tz='Africa/Malabo', country='Equatorial Guinea', infer=True,
      note='NP208 Part III S.301, Standardhafen, Zone -0100. N2/K2 inferiert. Ersetzt classic-1997.',
      con={'M2':(0.49,124),'S2':(0.18,155),'K1':(0.10,13),'O1':(0.06,280)}),

 # ===== Gabun / Angola (Seite 302) =====
 dict(name='Cogo (Puerto Iradier), Equatorial Guinea', att='3701', lat=1.083, lon=9.694, z0=1.49, conf=6,
      mer='+01:00', tz='Africa/Malabo', country='Equatorial Guinea', infer=True,
      note='NP208 Part III S.302 (Cogo), Zone -0100. M4 (f4). N2/K2 inferiert. Ersetzt classic-1997.',
      con={'M2':(0.76,148),'S2':(0.27,184),'K1':(0.12,18),'O1':(0.02,347),'M4':(0.171,193)}),
 dict(name='Libreville, Gabon', att='3705', lat=0.401, lon=9.433, z0=1.29, conf=7,
      mer='+01:00', tz='Africa/Libreville', country='Gabon', infer=True,
      note='NP208 Part III S.302, Standardhafen, Zone -0100. M4 (f4). N2/K2 inferiert. Ersetzt classic-1997.',
      con={'M2':(0.60,146),'S2':(0.19,179),'K1':(0.13,21),'O1':(0.02,325),'M4':(0.080,159)}),
 dict(name='Soyo, Angola', att='3720', lat=-6.120, lon=12.364, z0=1.10, conf=6,
      mer='+01:00', tz='Africa/Luanda', country='Angola', infer=True,
      note='NP208 Part III S.302, Zone -0100. N2/K2 inferiert. Ersetzt classic-1997.',
      con={'M2':(0.49,117),'S2':(0.16,146),'K1':(0.09,20),'O1':(0.01,292)}),
 dict(name='Luanda, Angola', att='3736', lat=-8.786, lon=13.235, z0=1.10, conf=7,
      mer='+01:00', tz='Africa/Luanda', country='Angola', infer=True,
      note='NP208 Part III S.302 (Porto de Luanda), Standardhafen, Zone -0100. M4 (f4). N2/K2 inferiert. Ersetzt classic-1997.',
      con={'M2':(0.48,107),'S2':(0.16,136),'K1':(0.08,20),'O1':(0.01,264),'M4':(0.018,38)}),

 # ===== Weitere Bezugs-Standardhäfen (Seite 302) für Part-II-Transfer =====
 dict(name='Pointe Owendo, Gabon', att='3706', lat=0.283, lon=9.500, z0=1.56, conf=7,
      mer='+01:00', tz='Africa/Libreville', country='Gabon', infer=True,
      note='NP208 Part III S.302, Standardhafen, Zone -0100. N2/K2 inferiert. Bezugshafen.',
      con={'M2':(0.74,149),'S2':(0.28,197),'K1':(0.12,15),'O1':(0.02,357)}),
 dict(name='Cap Lopez, Gabon', att='3709', lat=-0.617, lon=8.700, z0=1.21, conf=7,
      mer='+01:00', tz='Africa/Libreville', country='Gabon', infer=True,
      note='NP208 Part III S.302, Standardhafen, Zone -0100. N2/K2 inferiert. Bezugshafen.',
      con={'M2':(0.55,129),'S2':(0.21,153),'K1':(0.12,7),'O1':(0.02,302)}),
 dict(name='Pointe-Noire, Congo', att='3716', lat=-4.783, lon=11.833, z0=0.96, conf=7,
      mer='+01:00', tz='Africa/Brazzaville', country='Congo', infer=True,
      note='NP208 Part III S.302, Standardhafen, Zone -0100. N2/K2 inferiert. Bezugshafen.',
      con={'M2':(0.52,113),'S2':(0.17,143),'K1':(0.10,15),'O1':(0.01,302)}),
 dict(name='Enseada de Cabinda, Angola', att='3718', lat=-5.550, lon=12.200, z0=1.10, conf=7,
      mer='+01:00', tz='Africa/Luanda', country='Angola', infer=True,
      note='NP208 Part III S.302, Standardhafen, Zone -0100. N2/K2 inferiert. Bezugshafen.',
      con={'M2':(0.52,115),'S2':(0.19,140),'K1':(0.09,14),'O1':(0.02,306)}),
 dict(name='Porto do Lobito, Angola', att='3743', lat=-12.333, lon=13.567, z0=1.10, conf=7,
      mer='+01:00', tz='Africa/Luanda', country='Angola', infer=True,
      note='NP208 Part III S.302, Standardhafen, Zone -0100. N2/K2 inferiert. Bezugshafen.',
      con={'M2':(0.45,102),'S2':(0.15,128),'K1':(0.06,26),'O1':(0.01,227)}),
 dict(name='Walvis Bay, Namibia', att='3761', lat=-22.950, lon=14.500, z0=0.98, conf=7,
      mer='+02:00', tz='Africa/Windhoek', country='Namibia', infer=True,
      note='NP208 Part III S.302, Standardhafen, Zone -0200. M4/M6 (f4/f6). N2/K2 inferiert. Bezugshafen.',
      con={'M2':(0.50,98),'S2':(0.18,116),'K1':(0.05,90),'O1':(0.02,235),'M4':(0.036,70),'M6':(0.022,259)}),
 dict(name='Ascension Island', att='3770', lat=-7.917, lon=-14.417, z0=0.7, conf=6,
      mer='+00:00', tz='Atlantic/St_Helena', country='Saint Helena, Ascension and Tristan da Cunha', infer=False,
      note='NP208 Part III S.302, Standardhafen, Zone UT(GMT). Mikrotidal.',
      con={'M2':(0.33,178),'S2':(0.12,201),'K1':(0.05,326),'O1':(0.03,194)}),
 dict(name='St. Helena Island', att='3771', lat=-15.917, lon=-5.700, z0=0.55, conf=6,
      mer='+00:00', tz='Atlantic/St_Helena', country='Saint Helena, Ascension and Tristan da Cunha', infer=False,
      note='NP208 Part III S.302, Standardhafen, Zone UT(GMT). Mikrotidal.',
      con={'M2':(0.32,80),'S2':(0.10,99),'K1':(0.03,349),'O1':(0.02,188)}),

 # ===== Insel-Bezugs-Standardhäfen (Seite 299) für Part-II-Transfer =====
 dict(name='Ponta Delgada, São Miguel, Açores, Portugal', att='3467', lat=37.733, lon=-25.667, z0=1.00, conf=7,
      mer='-01:00', tz='Atlantic/Azores', country='Portugal', infer=False,
      note='NP208 Part III S.299, Standardhafen, Zone +0100. Bezugshafen.',
      con={'M2':(0.48,33),'S2':(0.17,53),'K1':(0.04,52),'O1':(0.03,307)}),
 dict(name='Funchal, Madeira, Portugal', att='3470', lat=32.650, lon=-16.917, z0=1.40, conf=7,
      mer='+00:00', tz='Atlantic/Madeira', country='Portugal', infer=False,
      note='NP208 Part III S.299, Standardhafen, Zone UT(GMT). Bezugshafen.',
      con={'M2':(0.72,46),'S2':(0.27,67),'K1':(0.06,47),'O1':(0.05,305)}),
 dict(name='Puerto de la Luz (Gran Canaria), Spain', att='3485', lat=28.150, lon=-15.417, z0=1.42, conf=7,
      mer='+00:00', tz='Atlantic/Canary', country='Spain', infer=False,
      note='NP208 Part III S.299, Standardhafen, Zone UT(GMT). Bezugshafen.',
      con={'M2':(0.77,28),'S2':(0.29,51),'K1':(0.06,39),'O1':(0.05,293)}),
]

def block(s):
    con = infer_n2k2(s['con']) if s.get('infer') else s['con']
    out=['# BEGIN HOT COMMENTS',
         f'# country: {s.get("country","")}',
         '# source: ADMIRALTY Tide Tables Vol.8 (NP208, 2026), Simplified Harmonic Method',
         f'# att_number: {s["att"]}',
         f'# note: {s["note"]}',
         '# date_imported: 20260701',
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
    print(f'  {s["att"]:6} {s["name"][:44]:44} Z0={s["z0"]} mer={s["mer"]}')
