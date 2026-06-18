#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ADMIRALTY NP203 (Indian Ocean) Part II -> XTide-Harmonics (Sekundaerhafen-Transfer).

Sekundaerhaefen aus NP203 Part II (Seiten 222-237, 2015 ed.) visuell gelesen.
Pro Hafen: Zeit-/Hoehendifferenzen + Standardhafen-Referenz + ML/Z0.

TRANSFER (Admiralty-Methode):
  Standardhafen-Konstituenten aus Live-DB (classic/ticon/att/utide) aufgeloest.
  Spring-Range  SR_S = 2*(M2+S2);  Neap-Range NR_S = 2*(M2-S2)   (aus Konstituenten)
  SR_sec = SR_S + (dMHWS-dMLWS);   NR_sec = NR_S + (dMHWN-dMLWN)  (Part-II-Hoehendiff)
  fS = SR_sec/SR_S ; fN = NR_sec/NR_S ; fD=(fS+fN)/2
  M2' = 0.5*(fS*(M2+S2)+fN*(M2-S2)) ;  S2' = 0.5*(fS*(M2+S2)-fN*(M2-S2))
  N2~M2, K2~S2, Diurnale ~fD, Flachwasser ~fS^2.
  Phase: g' = g + speed * mean(dt_HW,dt_LW)      (Zone-Zeit-Versatz)
  Z0' = Part-II ML-Spalte ; Meridian/TZ vom Referenzhafen geerbt.

Nur ECHTE Luecken (>6 km vom naechsten Bestand), M2'>=0.30 m (mikrotidal raus).
Schreibt harmonics/att/harmonics_att_np203_secondary.txt (ISO-8859-1).
Marker-Gruppe: NP203 (gleiche source-Kennung wie Part III).
"""
import os, re, math, sys, json

HARM = os.path.expanduser('~/harmonics')
LIT  = f'{HARM}/literature/harmonics_literature.txt'
OUT  = f'{HARM}/att/harmonics_att_np203_secondary.txt'

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
HEADER, ORDER, SPEED_H = read_header()

# ===== Part II secondary-port data (read visually from scans) =====
# NP203 Part II secondary ports — read visually from compressed scans (pages 222-238).
# fields: att, name, lat(+N/-S decimal), lon(+E/-W decimal), std_ref, region,
#         tHW, tLW (minutes), dMHWS,dMHWN,dMLWN,dMLWS (m), ml(Z0), note
# Only coords + identity needed for gap-check; diffs recorded where legible for transfer.
def dm(d,m,neg=False):
    v=d+m/60.0
    return -v if neg else v

SEC=[]
def P(att,name,lat,lon,std,region,**kw):
    SEC.append(dict(att=att,name=name,lat=lat,lon=lon,std=std,region=region,**kw))

# ---- page 222: South Africa + sub-Antarctic islands ----
# remote islands (low value, microtidal/remote) — recorded but flagged skip
P('2001','Breivika',dm(70,20,1),dm(24,36),'Durban','Antarctica',skip=1)
P('2002','Marion Island',dm(46,53,1),dm(37,51),'Durban','Prince Edward Is',ml=0.40)
P('2004',"Baie de l'Oiseau",dm(48,41,1),dm(69,2),'Durban','Kerguelen',ml=0.6,skip=1)
P('2005','Anse Betsy',dm(49,9,1),dm(70,12),'Durban','Kerguelen',ml=0.9,skip=1)
P('2006','Port-aux-Francais',dm(49,21,1),dm(70,13),'Sagar Roads','Kerguelen',ml=1.22)
P('2006a','Baie Norvegienne',dm(49,21,1),dm(70,21),'Sagar Roads','Kerguelen',skip=1)
P('2007','Port Jeanne d Arc',dm(49,33,1),dm(69,49),'Sagar Roads','Kerguelen',skip=1)
P('2007a','Baie Larose',dm(49,35,1),dm(69,18),'Sagar Roads','Kerguelen',skip=1)
P('2008','St Paul Island',dm(38,43,1),dm(77,32),'Sagar Roads','Indian Ocean',skip=1)
P('2009','Mawson',dm(67,36,1),dm(62,52),'Kochi','Antarctica',ml=0.81,skip=1)
P('2010','Heard Island',dm(53,1,1),dm(73,23),'Kochi','Indian Ocean',ml=0.71,skip=1)
P('2011','Davis Islands',dm(68,0,1),dm(78,30),'Kochi','Antarctica',ml=0.95,skip=1)
# South Africa mainland (Cape Town/Mossel Bay/Port Elizabeth/Durban refs)
P('3773','Port Nolloth',dm(29,15,1),dm(16,52),'Cape Town','South Africa',ml=1.09)
P('3777','Lamberts Bay',dm(32,5,1),dm(18,18),'Cape Town','South Africa',ml=0.85)
P('3778','St Helena Bay',dm(32,44,1),dm(17,59),'Cape Town','South Africa',ml=0.95)
P('3779','Saldanha Bay',dm(33,1,1),dm(17,57),'Cape Town','South Africa',ml=0.99)
P('3780','Schrywers Hoek',dm(33,11,1),dm(18,5),'Cape Town','South Africa',ml=0.98)
P('3783',"Simon's Town",dm(34,11,1),dm(18,26),'Cape Town','South Africa',ml=1.02)
P('3785','Hermanus',dm(34,25,1),dm(19,14),'Cape Town','South Africa',ml=1.00)
P('3787','Cape Agulhas',dm(34,50,1),dm(20,1),'Cape Town','South Africa',ml=1.1)
P('3788','Port Beaufort',dm(34,24,1),dm(20,49),'Cape Town','South Africa',ml=1.1)
P('3790','Knysna',dm(34,4,1),dm(23,3),'Mossel Bay','South Africa',ml=1.06)
P('3791','Plettenberg Bay',dm(34,3,1),dm(23,23),'Mossel Bay','South Africa',ml=1.1)
P('3792','Cape St Francis',dm(34,10,1),dm(24,52),'Mossel Bay','South Africa',ml=1.1)
P('3794','Port Alfred',dm(33,36,1),dm(26,54),'Port Elizabeth','South Africa',ml=1.0)


# ---- page 223: SA east coast + Mozambique (ref Beira MHWS6.5/Z0~3.56, Maputo) ----
# t=(tHW,tLW) min, h=(dMHWS,dMHWN,dMLWN,dMLWS)
def Q(att,name,lat,lon,std,region,ml,t=None,h=None,skip=0):
    SEC.append(dict(att=att,name=name,lat=lat,lon=lon,std=std,region=region,ml=ml,t=t,h=h,skip=skip))
Q('3797',"Port St John's",-(31+37/60),29+33/60,'East London','South Africa',1.1,(-2,None))
Q('3802','Kosi River Entrance',-(26+53/60),32+54/60,'Durban','South Africa',1.1,(0,0))
Q('3803','Baixos da Inhaca',-(25+53/60),32+54/60,'Maputo','Mozambique',2.00,None,(-3.3,-2.1,-1.1,0.0))
Q('3805','Matola',-(25+58/60),32+30/60,'Maputo','Mozambique',2.00,(15,-2),(-2.9,-2.0,-1.2,-0.3))
Q('3806','Limpopo River Bar',-(25+12/60),33+31/60,'Beira','Mozambique',1.0,(-2,-32),(-4.9,-3.2,-2.0,-0.4))
Q('3807','Inhampura',-(25+11/60),33+32/60,'Beira','Mozambique',1.0,(-2,-32),(-3.2,-1.9,None,-0.3))
Q('3811','Linga-Linga',-(23+44/60),35+24/60,'Beira','Mozambique',1.93,(-10,-10),(-3.4,-2.2,-1.1,-0.1))
Q('3812','Inhambane',-(23+52/60),35+23/60,'Beira','Mozambique',1.93,(23,23),(-3.2,-2.1,-1.3,-0.2))
Q('3815','Pomene',-(21+39/60),35+26/60,'Beira','Mozambique',2.41,(-33,-33),(-2.2,-1.6,-0.8,-0.3))
Q('3816','Porto de Bartolomeu Dias',-(21+7/60),35+4/60,'Beira','Mozambique',2.40,(-16,-16),(-2.3,-1.5,-0.9,-0.2))
Q('3818','Porto de Chiloane',-(20+37/60),34+53/60,'Beira','Mozambique',3.49,(-25,-25),(-0.4,-0.1,-0.1,0.1))
Q('3820','Porto de Sofala',-(20+11/60),34+45/60,'Beira','Mozambique',3.2,(-15,None),(-0.9,-0.6,None,None))
Q('3822','Pungue River Bar',-(20+0/60),34+58/60,'Beira','Mozambique',None,(-40,None))
Q('3826','Inhamissengo Entrance',-(18+54/60),36+12/60,'Beira','Mozambique',2.0,(-30,None),(-2.9,-1.9,None,None))
Q('3831','Morrubune',-(18+0/60),36+53/60,'Beira','Mozambique',2.60,(-34,-42),(-2.0,-1.3,-0.7,-0.1))
Q('3833','Macuse',-(17+43/60),37+11/60,'Beira','Mozambique',2.3,(-40,-55),(-2.4,-1.7,-1.0,-0.3))
Q('3834','Maquival',-(17+44/60),37+10/60,'Beira','Mozambique',2.4,(-10,-25),(-1.9,-1.5,-0.8,-0.3))
Q('3836','Porto de Pebane',-(17+16/60),38+8/60,'Beira','Mozambique',2.43,(-25,-45),(-2.2,-1.4,-0.9,-0.2))
Q('3838','Porto de Moebase',-(17+6/60),38+43/60,'Beira','Mozambique',2.1,(-25,-45),(-3.1,-2.1,None,None))
Q('3841','Moma',-(16+45/60),39+14/60,'Beira','Mozambique',2.00,(12,12),(-3.1,-2.1,-1.1,-0.2))
Q('3843','Angoche (Canal do Sul)',-(16+15/60),40+1/60,'Beira','Mozambique',None,(-50,None),(-2.4,-1.6,None,None))
Q('3847','Mocambo',-(15+8/60),40+32/60,'Beira','Mozambique',2.3,(-100,None),(-2.4,-1.6,None,None))
Q('3848','Porto de Mocambique',-(15+2/60),40+44/60,'Beira','Mozambique',2.26,(-50,-110),(-2.4,-1.6,-1.1,-0.4))

# ---- page 224: end Mozambique (Nacala/Pemba/Ibo/Mocimboa/Palma already built) + Madagascar ----
# W Madagascar macrotidal (ref Mahajanga MHWS~5.9), E Madagascar microtidal (skip)
Q('3853','Port Simuco',-(13+59/60),40+36/60,'Nacala','Mozambique',2.25,(-25,None))
# Madagascar N/NW (ref Antsiranana 2.3/1.8/1.1/0.5)
Q('3864','Baie Ambavanibe',-(12+4/60),49+10/60,'Antsiranana','Madagascar',1.71,(23,None),(1.2,0.7,0.6,0.4))
Q('3865','Baie du Courrier',-(12+11/60),49+8/60,'Antsiranana','Madagascar',1.80,(30,None),(0.9,0.4,0.4,0.2))
Q('3866','Nosy Misio',-(12+54/60),48+37/60,'Antsiranana','Madagascar',2.22,(13,None),(1.7,0.9,0.6,0.1))
Q('3871','Andoany (Hellville)',-(13+24/60),48+18/60,'Antsiranana','Madagascar',2.31,(41,41),(1.7,1.0,0.7,0.1))
Q('3873','Anarontsangana',-(13+55/60),47+56/60,'Antsiranana','Madagascar',2.0,(15,None),(1.0,0.9,None,None))
Q('3876','Nosy Lava',-(14+32/60),47+35/60,'Antsiranana','Madagascar',2.54,(13,None),(2.0,1.3,1.0,0.4))
Q('3878','Pointe Ambararata',-(15+12/60),46+57/60,'Antsiranana','Madagascar',2.57,(23,None),(2.3,1.7,0.9,0.5))
Q('3879','Nosy Longany',-(15+19/60),47+6/60,'Antsiranana','Madagascar',3.0,(21,None),(2.7,2.0,1.0,0.6))
# ref Mahajanga
Q('3880','Marosakoa',-(15+26/60),46+37/60,'Mahajanga','Madagascar',2.35,(23,None),(2.0,1.5,0.9,0.4))
Q('3885','Nosy Makamby',-(15+48/60),45+55/60,'Mahajanga','Madagascar',2.61,(11,None),(1.3,1.5,0.5,0.5))
Q('3886','Baie de Baly',-(16+5/60),45+16/60,'Mahajanga','Madagascar',2.52,(26,None),(1.2,1.7,1.1,0.7))
Q('3888','Cap Saint Andre',-(16+12/60),44+29/60,'Mahajanga','Madagascar',2.93,(31,None),(2.6,1.8,1.3,0.8))
Q('3891','Ile Juan de Nova',-(17+3/60),42+43/60,'Mahajanga','Madagascar',3.00,None,(2.7,2.0,1.1,0.5))
Q('3894','Maintirano',-(18+3/60),44+1/60,'Mahajanga','Madagascar',2.39,(122,None),(2.1,1.3,0.4,0.0))
Q('3895','Nosy Maroantaly',-(18+25/60),43+55/60,'Mahajanga','Madagascar',2.58,(122,None),(2.1,1.3,0.7,0.2))
Q('3899','Morondava',-(20+17/60),44+16/60,'Mahajanga','Madagascar',2.1,(51,58),(1.7,1.0,0.6,0.2))
Q('3906','Morombe',-(21+45/60),43+21/60,'Mahajanga','Madagascar',2.60,(135,None),(2.1,1.4,1.0,0.5))
Q('3910','Ile Europa',-(22+19/60),40+20/60,'Mahajanga','Madagascar',2.20,None,(1.6,1.0,0.4,0.2))
Q('3912','Toliara',-(23+23/60),43+40/60,'Mahajanga','Madagascar',2.10,(148,148),(1.1,0.7,0.6,0.3))
Q('3913','St Augustine Bay',-(23+35/60),43+43/60,'Mahajanga','Madagascar',2.20,(140,155),(1.0,0.6,0.5,0.3))
Q('3916','Androka',-(24+3/60),44+7/60,'Mahajanga','Madagascar',2.19,(213,200),(1.0,0.7,0.5,0.3))
# E Madagascar microtidal -> skip
for nm,la,lo,ml in [('Fort-Dauphin',-(25+2/60),47+0/60,None),('Manakara',-(22+8/60),48+3/60,0.33),
    ('Farafangana',-(22+49/60),47+50/60,0.30),('Vatomandry',-(19+19/60),49+0/60,0.52),
    ('Fenerive',-(17+23/60),49+24/60,0.62),('Mananara',-(16+10/60),49+46/60,0.64),
    ('Maroantsetra',-(15+26/60),49+44/60,0.71),('Vohemar',-(13+21/60),50+1/60,0.96)]:
    Q('-',nm,la,lo,'Toamasina','Madagascar-E',ml,None,None,skip=1)

# ---- page 225: ALL microtidal Indian Ocean islands (Reunion/Mauritius/Rodrigues/Seychelles/Amirantes) -> skip ----
# ---- page 226: Comoros + Tanzania + start Kenya (ref Dar es Salaam 3.6/2.5/1.5/0.4, Mtwara, Kilindini) ----
Q('3978','Aldabra Islands',-(9+23/60),46+16/60,'Port Victoria','Seychelles',2.0,(-31,-39),(1.8,1.2,0.7,0.1),skip=1)
Q('3980','Dzaoudzi (Mayotte)',-(12+47/60),45+15/60,'Dar es Salaam','Comoros',2.03,(-1,9),(0.4,0.2,-0.1,0.0))
Q('3981','Mutsamudu (Anjouan)',-(12+10/60),44+24/60,'Dar es Salaam','Comoros',2.4,(-40,None),(0.5,0.6,0.2,0.0))
Q('3982','Fomboni (Moheli)',-(12+17/60),43+46/60,'Dar es Salaam','Comoros',2.3,(10,None),(0.3,0.5,0.1,0.0))
Q('3983','Moroni (Grande Comore)',-(11+42/60),43+15/60,'Dar es Salaam','Comoros',2.7,(35,None),(1.0,1.0,0.4,0.0))
Q('3984','Ruvuma Bay',-(10+24/60),40+27/60,'Mtwara Bay','Tanzania',1.8,(10,None),(0.1,-0.1,None,None))
Q('3986','Lindi',-(10+0/60),39+43/60,'Mtwara Bay','Tanzania',1.9,(5,None),(-0.1,-0.1,None,None))
Q('3988','Kiswere Haven',-(9+25/60),39+38/60,'Mtwara Bay','Tanzania',1.9,(-10,None),(-0.1,-0.1,None,None))
Q('3990','Kilwa Masoko',-(8+54/60),39+30/60,'Mtwara Bay','Tanzania',2.0,(-10,0),(-0.1,-0.1,None,None))
Q('3993','Chole Bay (Mafia)',-(7+57/60),39+45/60,'Dar es Salaam','Tanzania',2.0,(25,30),None)
Q('4002','Bagamoyo',-(6+26/60),38+55/60,'Dar es Salaam','Tanzania',2.6,(-10,None),(0.9,0.8,0.5,0.3))
Q('4006','Zanzibar',-(6+9/60),39+11/60,'Dar es Salaam','Tanzania',2.48,(1,2),(0.7,0.6,0.4,0.2))
Q('4007','Mkokotoni Harbour',-(5+50/60),39+16/60,'Dar es Salaam','Tanzania',2.35,(-4,4),(0.4,0.4,None,None))
Q('4008','Pangani Bay',-(5+26/60),39+0/60,'Dar es Salaam','Tanzania',2.2,None,None)
Q('4010','Mkoani (Pemba)',-(5+21/60),39+38/60,'Dar es Salaam','Tanzania',2.16,(-3,3),(0.2,0.2,0.1,0.1))

# ---- page 227: Kenya/Somalia/Socotra/Djibouti (ref Kilindini 3.5/2.4/1.3/0.3, Aden) + Eritrea(skip micro) ----
Q('4022','Kilifi',-(3+39/60),39+52/60,'Kilindini','Kenya',1.8,(-5,None),(-0.2,-0.1,0.0,0.0))
Q('4024','Malindi',-(3+13/60),40+8/60,'Kilindini','Kenya',1.90,(-6,None),(-0.2,0.0,0.1,0.2))
Q('4028','Shela (Lamu)',-(2+18/60),40+55/60,'Kilindini','Kenya',1.85,(7,2),(-0.2,0.0,0.0,0.1))
Q('4031','Kiunga',-(1+45/60),41+30/60,'Kilindini','Kenya',1.59,(0,0),(-0.3,-0.2,-0.1,0.0))
Q('4033','Buur Gaabo',-(1+14/60),41+51/60,'Kilindini','Somalia',1.4,(0,None),(-0.8,-0.6,-0.4,-0.3))
Q('4034','Kismaayo',-(0+22/60),42+33/60,'Kilindini','Somalia',1.4,(-4,-4),None)
Q('4036','Barawe (Brava)',1+6/60,44+2/60,'Kilindini','Somalia',1.1,(-3,None),(-1.3,-1.0,None,None))
Q('4037','Marka',1+43/60,44+47/60,'Kilindini','Somalia',1.0,(-3,None),(-1.5,-1.2,None,None))
Q('4038','Muqdisho (Mogadishu)',2+2/60,45+21/60,'Kilindini','Somalia',1.63,(-6,-3),(-0.8,-0.5,0.0,0.3))
Q('4065','Berbera',10+26/60,45+0/60,'Aden','Somalia',1.56,(5,5),(0.2,0.2,0.2,0.2),skip=1) # built P3
Q('4067','Saylac (Zeila)',11+22/60,43+28/60,'Aden','Somalia',1.6,(15,20),(0.2,0.2,0.2,0.2))
Q('4068','Djibouti',11+35/60,43+9/60,'Aden','Djibouti',1.87,(30,31),(0.4,0.4,0.5,0.5))

# ---- page 228: entire Red Sea + Gulf of Suez/Aqaba (Sudan/Egypt/Israel/Jordan/Saudi/Yemen) -> ALL microtidal, skip ----
# ---- page 229: Gulf of Aden (Yemen) + Oman S + Gulf of Oman (ref Aden 2.0/1.8/1.3/0.5, Salalah, Port Sultan Qaboos 2.6/2.5/1.7/0.9) ----
Q('4156','Shuqra',13+22/60,45+41/60,'Aden','Yemen',1.1,(-5,None),(-0.4,-0.3,None,None))
Q('4160','Balhaf',13+58/60,48+11/60,'Aden','Yemen',1.28,(30,30),(-0.3,-0.1,0.0,-0.1))
Q('4162','Al Mukalla',14+32/60,49+8/60,'Aden','Yemen',1.22,(17,16),(-0.3,-0.2,0.0,0.0))
Q('4171a','Duqm',19+40/60,57+42/60,'Port Sultan Qaboos','Oman',1.74,(9,None),(-0.3,-0.3,-0.1,-0.1))
Q('4179','Al Ashkhara',21+51/60,59+34/60,'Port Sultan Qaboos','Oman',1.73,(21,21),(-0.1,-0.1,None,None))
Q('4180','Ras al Hadd',22+32/60,59+48/60,'Port Sultan Qaboos','Oman',1.6,(10,None),(-0.3,-0.3,None,None))
Q('4182','Sur',22+34/60,59+32/60,'Port Sultan Qaboos','Oman',1.77,(13,13),(-0.2,-0.1,-0.2,-0.1))
Q('4184','Quryat',23+16/60,58+54/60,'Port Sultan Qaboos','Oman',1.89,(0,None),(-0.1,-0.1,None,None))
Q('4186b','Mina al Fahl',23+38/60,58+31/60,'Port Sultan Qaboos','Oman',1.89,(3,3),(0.0,0.0,-0.1,0.0))
Q('4187','As Sib',23+41/60,58+11/60,'Port Sultan Qaboos','Oman',1.5,(10,10),(-0.4,-0.4,-0.5,-0.1))

# ---- page 230: Oman GoO (Sohar) + UAE (Musandam->Abu Dhabi). UAE inner Gulf microtidal/diurnal oilfields + many STANDARD ports -> skip ----
Q('4190','Suhar (Sohar)',24+23/60,56+44/60,'Majis (Sohar)','Oman',1.5,(10,None),(-0.4,-0.4,None,None))
Q('4189a','Al Khaburah',23+58/60,57+8/60,'Port Sultan Qaboos','Oman',1.90,(2,0),(0.0,0.1,-0.1,-0.1))

# ---- page 231: Persian Gulf Qatar/Bahrain -> ALL microtidal/diurnal, skip ----
# ---- page 232: Saudi Gulf (Aramco-covered, micro) + Kuwait/Iraq head (built std / river points), skip ----
# ---- page 233: Iran (ref Khowr-e Musa 3.4/2.8/1.7/0.9, Bushehr, Karachi 2.4/2.3/1.1/0.4, Bandar Shahid Rajai 3.7/2.9/1.5/0.6) ----
Q('4280','Bandar Deylam',30+4/60,50+6/60,'Khowr-e Musa Bar','Iran',1.59,(117,54),(0.4,0.5,0.0,-0.1))
Q('4302','Laft (Qeshm)',26+56/60,55+54/60,'Shatt al Arab Outer Bar','Iran',2.5,(-110,None),(1.1,1.0,0.3,0.5))
Q('4303b','Bandar Abbas',27+10/60,56+17/60,'Bandar-e Shahid Rajai','Iran',2.00,(-10,-6),(-0.3,-0.3,0.0,0.2))
Q('4307','Bandar-e Sirik',26+31/60,57+5/60,'Karachi','Iran',1.78,(-37,-29),(0.4,0.3,0.2,0.1))
Q('4310','Khalij-e Jask',25+39/60,57+46/60,'Karachi','Iran',1.37,(-131,-131),(-0.2,-0.2,-0.1,-0.1))
Q('4314','Chah Bahar',25+19/60,60+37/60,'Karachi','Iran',1.75,(-138,-138),(0.1,0.1,0.4,0.3))
Q('4315','Gwatar Bay',25+4/60,61+25/60,'Karachi','Iran',1.8,(-111,-113),(0.2,0.1,0.4,0.4))

# ---- page 234: Pakistan Indus + Gujarat (ref Karachi 2.4/2.3/1.1/0.4, Mumbai 4.4/3.3/1.9/0.8, Okha 3.5/3.0/1.2/0.4, Bhavnagar 10.2/8.3/3.5/1.4) ----
Q('4321','Sonmiani Harbour',25+23/60,66+33/60,'Karachi','Pakistan',1.5,(-45,None),(0.1,0.1,0.1,0.1))
Q('4322b','Port Qasim Entrance',24+42/60,67+8/60,'Karachi','Pakistan',1.73,(5,5),(0.3,0.3,0.2,0.1))
Q('4324','Sir Mouth',23+40/60,68+7/60,'Karachi','Pakistan',2.0,(10,None),(0.6,0.6,None,None))
Q('4326','Lakhpat',23+50/60,68+48/60,'Mumbai','India','2.53',(144,None),(-0.2,0.0,-0.2,-0.1))
Q('4329','Navinal Point (Mundra)',22+44/60,69+43/60,'Mumbai','India',3.88,(200,155),(1.4,1.3,0.2,0.2),skip=1) # Mundra built
Q('4332','Hansthal Creek',22+56/60,70+21/60,'Mumbai','India',3.4,(237,315),(1.7,1.6,-0.1,-0.1))
Q('4333','Rozi',22+34/60,70+2/60,'Mumbai','India',3.56,(211,228),(1.5,2.1,0.0,0.0))
Q('4333a','Sikka',22+26/60,69+49/60,'Mumbai','India',3.62,(202,209),(1.0,0.9,0.0,0.0))
Q('4336','Dwarka (Rupen Bandar)',22+16/60,68+57/60,'Okha','India',2.16,(-119,-126),(-0.3,-0.1,0.5,0.5))
Q('4338','Porbandar',21+38/60,69+36/60,'Okha','India',1.82,(-139,-145),(-0.6,-0.4,0.3,0.4),skip=1) # have (SoI)
Q('4341','Nawabandar',20+45/60,71+5/60,'Okha','India',1.70,(40,10),(-1.1,-1.0,0.4,0.5))
Q('4342','Jafarabad',20+52/60,71+23/60,'Okha','India',1.85,(145,110),(-0.7,-0.6,0.4,0.4))
Q('4343','Pipavav Bandar',20+57/60,71+32/60,'Okha','India',1.76,(210,200),(-0.3,-0.6,0.0,0.1))
Q('4345','Piram Island',21+36/60,72+21/60,'Bhavnagar','India',5.2,(-40,None),(-1.3,-1.0,None,None))
Q('4348','Khambhat (Cambay)',22+17/60,72+37/60,'Bhavnagar','India',4.2,(100,None),(-2.1,0.0,0.0,0.0))
Q('4349','Dahej Bandar',21+42/60,72+33/60,'Bhavnagar','India',4.90,(-25,-110),(-2.3,-2.2,0.5,1.8))

# ---- page 235: India W coast Maharashtra(macro)->Konkan/Goa->Kerala(micro,skip) (ref Mumbai 4.4/3.3/1.9/0.8) ----
Q('4355','Valsad',20+38/60,72+53/60,'Mumbai','India',3.84,(244,300),(1.9,1.7,0.1,0.4),skip=1) # built P3 S248
Q('4356a','Tarapur',19+52/60,72+41/60,'Mumbai','India',2.84,None,(0.4,0.4,None,None))
Q('4357','Satpati',19+43/60,72+42/60,'Mumbai','India',3.09,(56,113),(0.5,0.6,0.4,0.4))
Q('4362','Nava (Karanja)',18+55/60,72+56/60,'Mumbai','India',2.59,(10,0),(0.0,0.1,None,None))
Q('4364','Revadanda (Chaul)',18+33/60,72+56/60,'Mumbai','India',2.41,(56,33),(1.2,1.0,0.6,0.6))
Q('4365','Murud-Janjira',18+19/60,72+56/60,'Mumbai','India',2.16,(39,36),(0.9,0.7,0.5,0.6))
Q('4366','Bankot',17+58/60,73+3/60,'Mumbai','India',1.98,(42,43),(0.5,0.4,0.4,0.4))
Q('4367','Port Dabhol',17+35/60,73+11/60,'Mumbai','India',1.68,(29,33),(0.3,0.4,0.1,0.2))
Q('4377','Mormugao (Goa)',15+25/60,73+48/60,'Mumbai','India',1.30,(11,None),(-0.3,-0.5,None,None))

# ---- page 236: Lakshadweep/Maldives/Chagos/India-S/Sri Lanka -> ALL microtidal, skip ----
# ---- page 237: India E coast (ref Chennai 1.1/0.8/0.4/0.1, Bassein 2.4/1.8/1.1/0.4, Sagar Roads 5.2/3.8/2.2/0.9) ----
Q('4473','Devi River Entrance',19+57/60,86+22/60,'Bassein','India',1.65,(-115,None),(0.0,0.2,0.2,0.5))
Q('4473a','Paradip',20+16/60,86+42/60,'Bassein','India',1.66,(-124,-122),(0.2,0.2,0.2,0.5))
Q('4474','False Point',20+25/60,86+47/60,'Bassein','India',1.54,(-54,-54),(0.1,0.2,0.1,0.1))
Q('4476','Chandbali',20+46/60,86+44/60,'Sagar Roads','India',1.77,(117,207),(-2.4,-1.5,-0.9,None))
Q('4482a','Haldia',22+2/60,88+6/60,'Sagar Roads','India',3.23,(51,136),(0.5,0.5,-0.1,-0.1))
Q('4484','Diamond Harbour',22+12/60,88+12/60,'Sagar Roads','India',3.30,(147,241),(0.7,0.6,0.0,0.0))
Q('4488','Kolkata (Garden Reach)',22+33/60,88+18/60,'Sagar Roads','India',3.19,(340,445),(0.3,0.3,-0.2,-0.1))
Q('4491','Canning Town',22+18/60,88+40/60,'Sagar Roads','India',3.2,(200,238),(0.6,0.7,None,None))


# ===== INDIA VOLLSTÄNDIG (Nachtrag 2026-06-18, alle Part-II-Zeilen S.234-237) =====
def IN(att,name,lat,lon,std,ml,t,h,skip=0):
    SEC.append(dict(att=att,name=name,lat=lat,lon=lon,std=std,region='India',ml=ml,t=t,h=h,skip=skip))
# -- Gujarat Kutch (ref Mumbai) --
IN('4325','Kori Creek Entrance',23+30/60,68+27/60,'Mumbai',1.9,(-5,20),(-1.4,-0.5,None,None))
IN('4325a','Koteshwar',23+41/60,68+49/60,'Mumbai',2.47,(39,108),(-0.4,-0.1,-0.2,0.1))
IN('4327','Godia Creek',23+15/60,68+36/60,'Mumbai',1.90,(-16,21),(-1.4,-0.7,-0.5,-0.2))
# -- Saurashtra (ref Okha) --
IN('4337','Miyani',21+50/60,69+23/60,'Okha',1.01,(-100,-104),(-2.0,-1.6,-0.5,0.0))
IN('4339','Veraval',20+54/60,70+22/60,'Okha',1.0,(-100,-105),(-1.0,-1.4,-1.2,-0.1))
IN('4340a','Diu Head',20+41/60,70+50/60,'Okha',1.3,(-105,None),(-1.3,-1.1,0.2,0.3))
# -- Gulf of Khambhat / Narmada (ref Bhavnagar) --
IN('4350','Ambheta',21+41/60,72+36/60,'Bhavnagar',4.22,(-21,-17),(-2.7,-2.2,-1.2,-0.7))
IN('4351','Mahegam',21+40/60,72+46/60,'Bhavnagar',3.9,(10,25),(-5.6,-5.4,-3.1,-1.3))
IN('4352','Bharuch',21+41/60,72+59/60,'Bhavnagar',None,(210,525),(-7.4,-6.9,-3.2,-0.6))
# -- Maharashtra Mumbai-Umfeld (ref Mumbai) --
IN('4357a','Arnalapada',19+27/60,72+45/60,'Mumbai',2.70,(29,42),(0.0,0.1,0.0,0.2))
IN('4358a','Bandra',19+2/60,72+49/60,'Mumbai',2.53,(1,3),(-0.3,-0.1,-0.1,0.1))
IN('4360','Trombay',19+2/60,72+57/60,'Mumbai',2.52,(11,None),(0.0,0.1,-0.2,-0.1))
IN('4361','Thana',19+12/60,72+59/60,'Mumbai',2.1,(210,None),(-0.8,-0.6,None,None))
IN('4363','Rewas Bandar',18+49/60,72+57/60,'Mumbai',2.64,(2,-3),(0.1,0.1,0.0,0.2))
# -- Konkan/Goa/Karnataka (ref Karachi) --
IN('4370','Musakazi Point',16+37/60,73+20/60,'Karachi',1.37,(6,5),(-0.3,-0.4,-0.1,0.0))
IN('4373','Devgarh',16+23/60,73+23/60,'Karachi',1.38,(3,3),(-0.3,-0.4,0.0,0.0))
IN('4374','Malvan',16+3/60,73+28/60,'Karachi',1.17,(9,5),(-0.6,-0.6,-0.1,-0.1))
IN('4375','Vengurla',15+51/60,73+37/60,'Karachi',1.19,(6,5),(-0.6,-0.6,-0.1,-0.1))
IN('4378','Betul',15+8/60,73+57/60,'Karachi',1.0,(30,30),(-0.8,-0.3,-0.1,0.0))
IN('4380','Kumta',14+25/60,74+23/60,'Karachi',1.16,(25,35),(-0.6,-0.7,-0.2,0.0))
IN('4381','Bhatkal',13+58/60,74+32/60,'Karachi',0.70,(45,30),(-1.3,-1.3,-0.5,-0.3))
IN('4382','Coondapoor',13+37/60,74+41/60,'Mumbai',1.52,(15,None),(None,None,None,None))
IN('4383','Malpe',13+21/60,74+41/60,'Mumbai',1.04,(25,20),(-0.8,-0.9,-0.3,-0.1))
# -- Mangalore/Malabar (ref Mumbai bis Cannanore) --
IN('4385','New Mangalore',12+55/60,74+48/60,'Mumbai',0.95,(40,40),(-0.8,-1.0,-0.4,-0.1))
IN('4385a','Mangalore',12+51/60,74+50/60,'Mumbai',1.0,(None,None),(-1.0,-1.0,-0.4,-0.1))
IN('4386','Kasaragod',12+28/60,74+59/60,'Mumbai',0.89,(27,None),(-1.1,-1.1,-0.3,0.0))
IN('4387','Cannanore',11+51/60,75+22/60,'Mumbai',1.02,(40,30),(-1.0,-1.2,-0.2,0.0))
# -- Kerala (ref Kochi Willingdon) --
IN('4390','Beypore',11+10/60,75+49/60,'Kochi',0.88,(-14,-13),(0.4,0.3,0.1,0.0))
IN('4391','Ponnani',10+47/60,75+54/60,'Kochi',0.71,(-9,-10),(0.2,0.1,-0.1,0.0))
IN('4394','Alleppey',9+29/60,76+19/60,'Kochi',0.55,(0,None),(0.0,-0.1,-0.2,-0.2))
IN('4395','Quilon',8+53/60,76+34/60,'Kochi',0.67,(35,-45),(0.0,0.0,0.0,0.0))
IN('4396','Trivandrum',8+28/60,76+56/60,'Kochi',0.55,(26,20),(-0.1,-0.1,-0.2,-0.1))
IN('4397','Muttam Point',8+7/60,77+19/60,'Kochi',0.49,(28,19),(-0.2,-0.2,-0.1,-0.1))
# -- Gulf of Mannar (ref Colombo) --
IN('4422','Kulasekarapatnam',8+24/60,78+3/60,'Colombo',0.60,(-4,0),(0.2,0.1,0.2,0.0))
IN('4423','Tuticorin',8+45/60,78+12/60,'Colombo',0.64,(2,6),(0.3,0.2,0.3,0.2))
IN('4425','Pamban Pass',9+16/60,79+12/60,'Colombo',0.41,(8,12),(0.0,0.0,None,None))
# -- E-Küste Tamil Nadu/Andhra (ref Trincomalee / Chennai) --
IN('4446','Kottaippattanam',9+59/60,79+11/60,'Trincomalee',0.4,(240,None),(-0.1,-0.1,None,None))
IN('4447','Nagapattinam',10+46/60,79+51/60,'Chennai',0.34,(26,45),(-0.5,-0.3,-0.2,-0.1))
IN('4449','Cuddalore',11+43/60,79+47/60,'Chennai',0.70,(5,-5),(-0.1,0.0,0.2,0.2))
IN('4450','Pondicherry',11+56/60,79+50/60,'Chennai',0.88,(-8,-9),(0.2,0.2,0.3,0.2))
IN('4453','Pulicat',13+27/60,80+19/60,'Chennai',0.50,(None,None),(-0.3,-0.2,0.0,0.1))
IN('4455','Vadarevu',15+48/60,80+25/60,'Chennai',0.59,(None,None),(0.4,0.3,0.3,0.3))
IN('4456','Nizampatam',15+53/60,80+40/60,'Chennai',0.9,(10,None),(0.4,0.4,0.3,0.3))
IN('4457','Machilipatnam',16+11/60,81+12/60,'Chennai',1.1,(20,20),(0.4,0.4,0.5,0.5))
IN('4459','Sacramento Shoal',16+36/60,82+19/60,'Chennai',0.76,(24,5),(0.1,0.2,0.1,0.1))
# -- N-Andhra/Odisha (ref Bassein=Pathein/Myanmar) --
IN('4464','Bhimunipatnam',17+54/60,83+27/60,'Bassein',1.14,(-127,-126),(-0.6,-0.4,None,None))
IN('4465','Kalingapatnam',18+21/60,84+8/60,'Bassein',1.01,(-131,-103),(-0.7,-0.7,None,None))
IN('4468','Baruva',18+52/60,84+36/60,'Bassein',1.0,(-127,-108),(-0.7,-0.5,None,None))
IN('4469','Gopalpur',19+16/60,84+55/60,'Bassein',1.11,(-108,-1),(-0.8,-0.5,-0.2,0.1))
IN('4471','Chilka Mouth',19+43/60,85+37/60,'Bassein',0.98,(-52,-52),(-1.0,-0.6,-0.3,0.1))
IN('4472','Kushabhadra River',19+51/60,86+3/60,'Bassein',1.16,(-105,-43),(-0.5,-0.3,-0.2,-0.2))
IN('4473','Devi River Entrance',19+57/60,86+22/60,'Bassein',1.65,(-115,None),(0.0,0.2,0.2,0.5))
IN('4474','False Point',20+25/60,86+47/60,'Bassein',1.54,(-54,-54),(0.1,0.2,0.1,0.1))
# -- Hooghly (ref Sagar Roads) --
IN('4482','Gangra Semaphore',21+57/60,88+11/60,'Sagar Roads',3.16,(5,10),(0.4,0.3,-0.1,-0.1))
IN('4483','Balari Semaphore',22+5/60,88+11/60,'Sagar Roads',3.16,(122,216),(0.0,0.0,None,None))
IN('4485','Hugli Point Semaphore',22+13/60,88+4/60,'Sagar Roads',3.30,(217,311),(0.0,0.0,None,None))
IN('4486','Moyapur',22+26/60,88+8/60,'Sagar Roads',3.2,(244,None),(0.0,0.0,None,None))
IN('4490','Sandhead',20+58/60,88+35/60,'Sagar Roads',1.8,(-22,-42),(-2.4,-1.8,None,None))

# ----- reference resolver (live harmonics files) -----
import glob
FILES = (glob.glob(f'{HARM}/classic/*.txt')+glob.glob(f'{HARM}/ticon/*.txt')
       + glob.glob(f'{HARM}/att/*.txt')+glob.glob(f'{HARM}/utide/*.txt')
       + glob.glob(f'{HARM}/literature/*.txt'))
FILES=[x for x in FILES if 'np203_secondary' not in x]
_MER=re.compile(r'^([+-]\d{2}:\d{2})\s*:(\S+)')
_CON=re.compile(r'^([A-Za-z][A-Za-z0-9]*)\s+([\-\d.]+)\s+([\-\d.]+)\s*$')
_ZL =re.compile(r'^([\-\d.]+)\s+meters')
def _blocks(path):
    try: L=open(path,encoding='iso-8859-1').read().split('\n')
    except: return
    i=0;n=len(L)
    while i<n:
        m=_MER.match(L[i])
        if m and i>0:
            name=L[i-1].strip(); mer,tz=m.group(1),m.group(2)
            z0=None;con={};k=i+1
            zm=_ZL.match(L[k]) if k<n else None
            if zm: z0=float(zm.group(1)); k+=1
            while k<n:
                if _MER.match(L[k]) or L[k].startswith('#'): break
                cm=_CON.match(L[k])
                if cm and cm.group(1)!='x': con[cm.group(1)]=(float(cm.group(2)),float(cm.group(3)))
                k+=1
            yield name,dict(con=con,z0=z0,mer=mer,tz=tz); i=k; continue
        i+=1
_IDX=None
def _index():
    global _IDX
    if _IDX is None:
        _IDX={}
        for f in FILES:
            for n,r in _blocks(f): _IDX.setdefault(n,r)
    return _IDX
def find(q):
    idx=_index()
    if q in idx and idx[q]['con'].get('M2'): return q,idx[q]
    ql=q.lower()
    cand=[(n,r) for n,r in idx.items() if ql in n.lower() and r['con'].get('M2')]
    if not cand: cand=[(n,r) for n,r in idx.items() if all(w in n.lower() for w in ql.split()) and r['con'].get('M2')]
    if cand: cand.sort(key=lambda x:len(x[0])); return cand[0]
    return None,None

REFMAP={
 'Beira':'Beira','Maputo':'Maputo','Nacala':'Nacala (NP203)','Mahajanga':'Mahajanga',
 'Antsiranana':'Antsiranana (Diego','Dar es Salaam':'Dar Es Salaam','Mtwara Bay':'Mtwara (NP203)',
 'Kilindini':'Mombasa (Kilindini','Aden':'Aden','Port Sultan Qaboos':'Muscat (Sultan Qaboos',
 'Majis (Sohar)':'Muscat (Sultan Qaboos','Khowr-e Musa Bar':'Khowr-e Musa',
 'Bandar-e Shahid Rajai':'Bandar-e Shahid Rajai (NP203','Shatt al Arab Outer Bar':'Khowr-e Musa',
 'Karachi':'Karachi','Mumbai':'Mumbai (Colaba','Okha':'Okha (NP203','Bhavnagar':'Bhavnagar',
 'Sagar Roads':'Sagar Roads (NP203','Bassein':'Pathein (Bassein River)',
 'Chennai':'Chennai, Tamil Nadu','Trincomalee':'Trincomalee','Colombo':'Colombo','Kochi':'Kochi (Willingdon Island)',
 'Cape Town':'Cape Town','Mossel Bay':'Mossel Bay','Port Elizabeth':'Port Elizabeth',
 'East London':'East London','Durban':'Durban'}

ISO={'Mozambique':'Mozambique','Madagascar':'Madagascar','Tanzania':'Tanzania','Kenya':'Kenya',
 'Somalia':'Somalia','Comoros':'Comoros','Yemen':'Yemen','Djibouti':'Djibouti','Oman':'Oman',
 'Iran':'Iran','Pakistan':'Pakistan','India':'India','South Africa':'South Africa'}

def transfer(s,rr):
    con=rr['con']; M2=con.get('M2',(0,0))[0]; S2=con.get('S2',(0,0))[0]
    if M2<=0: return None
    SR=2*(M2+S2); NR=2*(M2-S2); h=s.get('h')
    if not h or h[0] is None: return None
    dMHWS,dMHWN,dMLWN,dMLWS=h
    if dMLWS is None: dMLWS=0.0
    if dMHWN is None: dMHWN=dMHWS
    if dMLWN is None: dMLWN=dMLWS
    SRs=SR+(dMHWS-dMLWS); NRs=NR+(dMHWN-dMLWN)
    if SRs<=0: return None
    fS=max(.05,min(3.,SRs/SR)); fN=max(.05,min(3.,NRs/NR)) if NR>.01 else fS
    su=fS*(M2+S2); di=fN*(M2-S2); M2n=max(0,.5*(su+di)); S2n=max(0,.5*(su-di)); fD=.5*(fS+fN)
    t=s.get('t'); dt=0.0
    if t:
        v=[x for x in t if x is not None]
        if v: dt=sum(v)/len(v)/60.0
    rM=M2n/M2 if M2>0 else fS; rS=S2n/S2 if S2>0 else fS
    out={}
    for c,(a,g) in con.items():
        if a<=0: continue
        if c=='M2': na=M2n
        elif c=='S2': na=S2n
        elif c in ('N2','2N2','NU2','MU2','L2','T2','R2'): na=a*rM
        elif c=='K2': na=a*rS
        elif c in ('M4','MS4','M6','MN4','2MS6','MK3'): na=a*rM*rM
        elif c in ('K1','O1','P1','Q1','J1','M1','OO1','2Q1','SO1','RHO1','PHI1','PSI1','S1'): na=a*fD
        elif c in ('SA','SSA','MM','MF','MSF','MSQM','MTM'): na=a
        else: na=a*fD
        sp=SPEED_H.get(c)
        out[c]=(round(na,4), round((g+(sp*dt if sp else 0))%360,2))
    return dict(con=out,mer=rr['mer'],tz=rr['tz'],M2n=M2n,S2n=S2n,fS=fS,fN=fN,dt=dt)

# ----- gap check vs live DB + Part III -----
def _hav(a,b,c,d):
    R=6371;p=math.pi/180
    return 2*R*math.asin(math.sqrt(math.sin((c-a)*p/2)**2+math.cos(a*p)*math.cos(c*p)*math.sin((d-b)*p/2)**2))
def _refpts():
    pts=[]
    for f in (glob.glob(f'{HARM}/classic/*.txt')+glob.glob(f'{HARM}/ticon/*.txt')
             +glob.glob(f'{HARM}/att/*.txt')+glob.glob(f'{HARM}/utide/*.txt')
             +glob.glob(f'{HARM}/literature/*.txt')+glob.glob(f'{HARM}/fes2022/*.txt')):
        if 'np203_secondary' in f: continue
        t=open(f,encoding='iso-8859-1').read()
        for la,lo in zip(re.findall(r'# !latitude:\s*([\-\d.]+)',t),re.findall(r'# !longitude:\s*([\-\d.]+)',t)):
            pts.append((float(la),float(lo)))
    return pts
PTS=_refpts()
def isgap(s): return min(_hav(s['lat'],s['lon'],a,b) for a,b in PTS)>6.0

def conf_of(tr,s):
    c=5
    if tr['fS']>1.6 or tr['fS']<0.55: c=4
    if abs(tr['dt'])>1.5: c=min(c,4)
    if s['h'][2] is None or s['h'][3] is None: c=min(c,4)
    if tr['M2n']<0.50: c=min(c,3)
    return c

def block(s,tr):
    name=f"{s['name']} (NP203), {ISO.get(s['region'],s['region'])}"
    conf=conf_of(tr,s); z0=s.get('ml')
    if z0 is None: z0=round(tr['M2n']+tr['S2n'],2)
    z0=float(z0)
    note=(f"NP203 Part II Sekundaerhafen-Transfer von {tr.get('refname','?')} "
          f"(att {s['att']}). fS={tr['fS']:.2f} fN={tr['fN']:.2f} dt={tr['dt']*60:+.0f}min. "
          f"Zeit-/Hoehendiff. aus ATT Vol.3 (2015).")
    out=['# BEGIN HOT COMMENTS', f'# country: {ISO.get(s["region"],s["region"])}',
         '# source: ADMIRALTY Tide Tables Vol.3 (NP203), Part II Secondary Port Transfer',
         f'# att_number: {s["att"]}', f'# note: {note}', '# date_imported: 20260618',
         '# datum: Chart Datum (Z0 = mean level above CD)', f'# confidence: {conf}',
         '# !units: meters', f'# !longitude: {s["lon"]:.4f}', f'# !latitude: {s["lat"]:.4f}',
         name, f'{tr["mer"]} :{tr["tz"]}', f'{z0:.4f} meters']
    con=tr['con']
    for c in ORDER:
        if c in con: a,g=con[c]; out.append(f'{c:<16}{a:.4f}  {g:.2f}')
        else: out.append('x 0 0')
    return out,name,conf

def main():
    built=[]
    for s in SEC:
        if s.get('skip'): continue
        if not isgap(s): continue
        q=REFMAP.get(s['std'],'__NONE__')
        if q is None or q=='__NONE__': continue
        rn,rr=find(q)
        if not rr: continue
        tr=transfer(s,rr)
        if not tr or tr['M2n']<0.05: continue
        tr['refname']=rn
        built.append((s,tr))
    lines=list(HEADER)
    names=[]
    for s,tr in built:
        b,nm,cf=block(s,tr); lines+=b; names.append((nm,cf,tr['M2n']))
    open(OUT,'w',encoding='iso-8859-1').write('\n'.join(lines)+'\n')
    print(f'wrote {len(built)} stations -> {OUT}')
    for nm,cf,m2 in sorted(names,key=lambda x:-x[2]):
        print(f'  conf{cf} M2={m2:.2f}  {nm}')

if __name__=='__main__':
    main()
