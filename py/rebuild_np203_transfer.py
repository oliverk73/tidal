#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Leitet Part-II-Sekundaerhaefen neu ab -- mit dem richtigen Bezugshafen und
den PUBLIZIERTEN Pegeln aus dem Gruppenkopf.

Zwei Fehler des Imports von 2026-06 werden hier behoben:

1. Falscher Bezugshafen. In ATT gilt der eingerahmte Standardhafen ueber einer
   Gruppe bis zum naechsten eingerahmten Kopf. Ein Standardhafen, der INNERHALB
   der Liste an seiner geografischen Stelle steht, ist nur ein Eintrag. Der alte
   Import hat ab jedem solchen Eintrag den Bezug gewechselt -- auf Seite 224 also
   ab Mahajanga und ab Toamasina, obwohl die ganze Madagaskar-Liste unter
   Antsiranana steht.

2. Gerechneter statt publizierter Bezugshub. Der Skalierungsfaktor muss gegen
   den im Buch gedruckten Hub des Bezugshafens gebildet werden, nicht gegen den
   aus seinen Konstituenten gerechneten:

       SR_pub = MHWS - MLWS          NR_pub = MHWN - MLWN
       fS = (SR_pub + dMHWS - dMLWS) / SR_pub
       fN = (NR_pub + dMHWN - dMLWN) / NR_pub

   Bei Antsiranana sind das 1.80 m statt 1.74 m Spring- und 0.70 m statt 0.62 m
   Nipphub. Der Nippfaktor lag dadurch systematisch 13 % zu hoch.

3. Zonenversatz in der Zeitdifferenz. Die Differenzen in Part II werden auf die
   Zeit des Standardhafens IN DESSEN ZONE addiert und ergeben die Zeit des
   Sekundaerhafens in DESSEN Zone (die "Zone -0xx00"-Zwischenueberschrift). Sie
   enthalten also den Zonensprung mit. Fuer die Phasenverschiebung brauchen wir
   aber die echte Verzoegerung in Weltzeit:

       dt_UT = dt_Buch + (Zone_Bezug - Zone_Sekundaer)

   Bei Madagaskar faellt das weg (beide -0300), deshalb ist es bisher nicht
   aufgefallen. Kerguelen unter Durban sind aber 3 h Unterschied -- in M2 sind
   das 87 Grad Phasenfehler.

Ausserdem: Phantomstationen loeschen (Nummern, die es im Buch nicht gibt) und
Koordinaten aus dem Scan richtigstellen.

Aufruf: python3 py/rebuild_np203_transfer.py [--write]
"""
from __future__ import annotations
import json
import math
import os
import re
import shutil
import sys
from datetime import datetime

TXT = '/home/oliver/weather/harmonics/att/harmonics_att_np203_secondary.txt'
STD = '/home/oliver/weather/harmonics/att/harmonics_att_np203.txt'
GRUPPEN = '/home/oliver/weather/harmonics/help/np203_part2_bezugshaefen.json'
BEZUG = '/home/oliver/weather/harmonics/help/np203_bezugshafen_konstanten.json'
HARM = '/home/oliver/weather/harmonics'

SPEED = {
    'M2': 28.9841042, 'S2': 30.0, 'N2': 28.4397295, 'K2': 30.0821373, 'K1': 15.0410686,
    'O1': 13.9430356, 'P1': 14.9589314, 'Q1': 13.3986609, 'M4': 57.9682084, 'M6': 86.9523127,
    'MS4': 58.9841042, 'MN4': 57.4238337, 'J1': 15.5854433, 'M1': 14.4966939, 'OO1': 16.1391017,
    'RHO1': 13.4715145, 'L2': 29.5284789, 'T2': 29.9589333, 'R2': 30.0410667, 'LDA2': 29.4556253,
    'MU2': 27.9682084, 'NU2': 28.5125831, '2N2': 27.8953548, 'S1': 15.0, 'S4': 60.0,
    'M3': 43.4761563, 'M8': 115.9364169, 'MK3': 44.0251729, 'SA': 0.0410686, 'SSA': 0.0821373,
    'MM': 0.5443747, 'MF': 1.0980331, 'MSF': 1.0158958, 'MKS2': 29.0662415, 'EPS2': 27.4238337,
    'N4': 56.8794590,
}

DIURNAL = {'K1', 'O1', 'P1', 'Q1', 'J1', 'M1', 'OO1', '2Q1', 'SO1', 'RHO1', 'PHI1', 'PSI1', 'S1'}
SEMI_M = {'N2', '2N2', 'NU2', 'MU2', 'L2', 'T2', 'R2', 'LDA2', 'EPS2', 'MKS2'}
SHALLOW = {'M4', 'MS4', 'M6', 'MN4', '2MS6', 'MK3', 'S4', 'M8', 'M3', 'N4'}
LANGZEIT = {'SA', 'SSA', 'MM', 'MF', 'MSF', 'MSQM', 'MTM'}


def dm(g, m):
    return g + m / 60.0


# ---------------------------------------------------------------- Buchdaten
# ATT NP203 Part II, aus den Scans gelesen.
# att: (Name im Buch, lat, lon, tMHW, tMLW, (dMHWS,dMHWN,dMLWN,dMLWS), ML[, Zone])
# Zeiten in Minuten, None = Kreis-Symbol (no data). Suedbreite negativ.
# Zone = Stunden oestlich (ATT "Zone -0300" -> +3.0); fehlt sie, gilt ZONE_SEITE.
#
# Zone des jeweiligen Standardhafens, Stunden oestlich. Die Zeitdifferenzen in
# Part II werden auf seine Ortszeit addiert, deshalb muss sie bekannt sein.
ZONE_STD = {
    '3782': 2.0,    # Cape Town
    '3800': 2.0,    # Durban
    '3823': 2.0,    # Beira
    '3850': 2.0,    # Nacala
    '3881': 3.0,    # Mahajanga
    '3932': 3.0,    # Toamasina
    '3948': 3.0,    # Antsiranana
    '3967': 4.0,    # Port Victoria (Seychellen)
    '3985': 3.0,    # Mtwara
    '4001': 3.0,    # Dar es Salaam
    '4017': 3.0,    # Kilindini (Mombasa)
    '4112': 2.0,    # Suez
    '4133': 3.0,    # Rabigh
    '4155': 3.0,    # Aden
    '4168': 4.0,    # Salalah
    '4186a': 4.0,   # Port Sultan Qaboos
    '4207': 4.0,    # Jebel Ali
    '4210': 4.0,    # Mina Zayid
    '4236': 3.0,    # Mesaieed
    '4252': 3.0,    # Mina Salman
    '4262': 3.0,    # Mina Al Ahmadi
    '4268': 3.0,    # Shatt al Arab Outer Bar (Irak)
    '4277': 3.5,    # Khowr-e Musa Bar (Iran)
    '4282': 3.5,    # Jazireh-ye Khark
    '4283': 3.5,    # Bushehr
    '4303': 3.5,    # Bandar-e Shahid Rajai
    '4322': 5.0,    # Karachi
    '4335': 5.5,    # Okha
    '4346': 5.5,    # Bhavnagar
    '4359': 5.5,    # Mumbai
    '4393': 5.5,    # Kochi
    '4428': 5.5,    # Colombo
    '4437': 5.5,    # Trincomalee
    '4452': 5.5,    # Chennai
    '4481': 5.5,    # Sagar Roads
    '4539': 6.5,    # Bassein River Entrance (Myanmar)
}

# Vorherrschende Zone je Part-II-Seite (Zwischenueberschrift "Zone -0xx00").
ZONE_SEITE = {222: 2.0, 223: 2.0, 224: 3.0, 225: 4.0, 226: 3.0, 227: 3.0,
              228: 3.0, 229: 4.0, 230: 4.0, 233: 3.5, 234: 5.5, 235: 5.5,
              236: 5.5, 237: 5.5}
S224 = {
 '3864': ('Baie Ambavanibe',    -dm(12, 4), dm(49, 10),   42,   23, (1.2, 0.7, 0.6, 0.4), 1.71),
 '3865': ('Baie du Courrier',   -dm(12, 11), dm(49, 8),    38,   30, (0.9, 0.4, 0.4, 0.1), 1.80),
 '3868': ('Nosy Mitsio',        -dm(12, 54), dm(48, 37),   13,   21, (1.7, 0.9, 0.6, 0.1), 2.22),
 '3871': ('Andoany (Hellville)', -dm(13, 24), dm(48, 18),  41,   41, (1.7, 1.0, 0.7, 0.1), 2.31),
 '3873': ('Anarontsangana',     -dm(13, 55), dm(47, 56),   31, None, (1.0, 0.9, None, None), None),
 '3876': ('Nosy Lava',          -dm(14, 32), dm(47, 35),   13, None, (2.0, 1.3, 1.0, 0.4), 2.54),
 '3877': ('Baie de Moramba',    -dm(14, 53), dm(47, 20),  -14, None, (1.1, 0.9, 0.1, 0.0), 2.32),
 '3878': ('Pointe Ambararata',  -dm(15, 12), dm(46, 57),   23, None, (2.3, 1.7, 0.9, 0.5), 2.57),
 '3879': ('Nosy Longany',       -dm(15, 19), dm(47, 6),    21, None, (2.7, 2.0, 1.0, 0.5), 3.00),
 '3880': ('Marosakoa',          -dm(15, 26), dm(46, 37),   23, None, (2.0, 1.5, 0.9, 0.4), 2.35),
 '3882': ('Pointe Maroloha',    -dm(15, 54), dm(46, 16),   43, None, (3.4, 2.5, 1.7, 0.7), 3.44),
 '3883': ('Maravoai',           -dm(16, 7), dm(46, 40),   176, None, (None, None, None, None), None),
 '3884': ('Nosy Makamby',       -dm(15, 48), dm(45, 55),   11, None, (1.3, 1.5, 1.1, 0.5), 2.61),
 '3886': ('Baie de Baly',       -dm(16, 5), dm(45, 16),    26, None, (1.2, 1.7, 1.1, 0.7), 2.52),
 '3888': ('Cap Saint Andre',    -dm(16, 12), dm(44, 29),   31, None, (2.6, 1.8, 1.3, 0.6), 2.93),
 '3891': ('Ile Juan de Nova',   -dm(17, 3), dm(42, 43),  None, None, (2.7, 2.0, 1.1, 0.5), 3.00),
 '3894': ('Maintirano',         -dm(18, 3), dm(44, 1),     82,   95, (2.1, 1.3, 0.7, 0.2), 2.39),
 '3895': ('Nosy Maroantaly',    -dm(18, 25), dm(43, 55),   82,   95, (2.1, 1.3, 0.7, 0.2), 2.39),
 '3898': ('Ilot Indien',        -dm(19, 48), dm(44, 23),   75, None, (1.7, 1.2, -0.1, -0.1), 2.10),
 '3899': ('Morondava',          -dm(20, 17), dm(44, 16),   51,   58, (1.7, 1.0, 0.5, 0.1), 2.30),
 '3900': ('Cap Ankarana',       -dm(20, 29), dm(44, 7),   128,  128, (1.8, 1.1, 0.6, 0.1), 2.38),
 '3902': ('Nosy Andriangory',   -dm(20, 50), dm(43, 46),   79, None, (2.4, 2.3, None, None), 2.65),
 '3903': ('Nosy Andriamitaroka', -dm(21, 6), dm(43, 42),   90, None, (2.1, 1.4, 1.0, 0.5), 2.60),
 '3904': ('Baie de Ampasilava', -dm(21, 17), dm(43, 45),   79, None, (2.2, 1.3, 0.0, None), 2.44),
 '3906': ('Morombe',            -dm(21, 45), dm(43, 21),   95, None, (2.1, 1.4, 1.0, 0.5), 2.60),
 '3907': ('Nosy Andrahombava',  -dm(21, 58), dm(43, 11),   91, None, (1.9, 1.2, None, None), 2.50),
 '3909': ('Nosy Hao',           -dm(22, 4), dm(43, 14),    95, None, (1.9, 1.3, 1.0, 0.6), 2.54),
 '3910': ('Ile Europa',         -dm(22, 19), dm(40, 20), None, None, (1.6, 1.0, 0.4, 0.2), 2.20),
 '3912': ('Toliara',            -dm(23, 23), dm(43, 40),  108,  108, (1.1, 0.7, 0.6, 0.3), 2.10),
 '3913': ('St. Augustine Bay',  -dm(23, 35), dm(43, 43),  100,  115, (1.0, 0.6, 0.5, 0.3), 2.00),
 '3916': ('Androka',            -dm(25, 3), dm(44, 7),    133,  120, (1.0, 0.7, 0.7, 0.5), 2.19),
 '3917': ('Cap Ste. Marie',     -dm(25, 39), dm(45, 6),    56, None, (-0.1, None, None, None), None),
 '3919': ('Fort-Dauphin',       -dm(25, 2), dm(47, 0),    308,  333, (-1.9, -1.5, -0.8, -0.3), 0.30),
 '3920': ('Ste. Luce',          -dm(24, 46), dm(47, 12), None, None, (-1.9, None, None, None), None),
 '3923': ('Farafangana',        -dm(22, 49), dm(47, 50), None, None, (-1.9, None, None, None), 0.30),
 '3925': ('Manakara',           -dm(22, 8), dm(48, 3),   None, None, (-1.8, -1.4, -0.8, -0.3), 0.33),
 '3930': ('Vatomandry',         -dm(19, 19), dm(49, 0),    39, None, (0.1, None, None, None), 0.52),
 '3932': ('Toamasina',          -dm(18, 8), dm(49, 26), -103, -103, (-1.3, -1.0, -0.5, -0.1), 0.67),
 '3934': ('Fenerive',           -dm(17, 23), dm(49, 24),  -90, -118, (-0.9, -0.7, -0.3, 0.1), 0.92),
 '3937': ('Baie de Tintingue',  -dm(16, 42), dm(49, 44),  -71, None, (-1.3, -1.0, -0.5, 0.0), 0.76),
 '3938': ('Mananara',           -dm(16, 10), dm(49, 46), None, None, (-1.4, -1.0, -0.5, -0.3), 0.64),
 '3939': ('Maroantsetra',       -dm(15, 26), dm(49, 44),  -24, None, (-1.2, -0.9, -0.5, -0.2), 0.71),
 '3941': ("Rade d'Angontsy",    -dm(15, 16), dm(50, 29),  -24, None, (-1.1, -0.8, -0.4, -0.2), 0.76),
 '3942': ("Rade d'Antalaha",    -dm(14, 54), dm(50, 17),  -28,  -22, (-1.0, -0.8, -0.6, -0.3), 0.75),
 '3944': ('Vohemar',            -dm(13, 21), dm(50, 1),   -31,  -32, (-0.7, -0.5, -0.2, -0.1), 0.95),
 '3945': ('Port Leven',         -dm(12, 48), dm(49, 49),  -20,  -40, (-0.3, 0.0, -0.1, 0.1), 1.24),
 '3946': ('Baie de Rigny',      -dm(12, 25), dm(49, 32),    6, None, (0.1, -0.1, -0.1, -0.1), 1.30),
}

# ATT NP203 Part II S.222/223/225/226/228/229/233/235, am 20260801 gelesen.
# Nur die Zeilen, deren Bezugshafen der alte Import verwechselt hatte.
S222 = {
 '2004': ("Baie de l'Oiseau",   -dm(48, 41), dm(69,  2), 1050, None, (-1.0, -0.8, None, None), 0.6, 5.0),
 '2006a': ('Baie Norvegienne',  -dm(49, 22), dm(70, 21),  147,  129, (-3.3, -2.3, -1.3, -0.4), 1.22, 5.0),
 '2007': ("Port Jeanne d'Arc",  -dm(49, 33), dm(69, 49),  140, None, (-3.2, -2.3, None, None), 1.1,  5.0),
 '2007a': ('Baie Larose',       -dm(49, 35), dm(69, 18),   52,   39, (-3.8, -2.7, -1.6, -0.5), 0.89, 5.0),
 '3787': ('Cape Agulhas',       -dm(34, 50), dm(20,  1),    5, None, ( 0.2,  0.0, None, None), 1.1),
 '3788': ('Port Beaufort',      -dm(34, 24), dm(20, 49),   70, None, ( 0.2,  0.0, None, None), 1.1),
 '3791': ('Plettenberg Bay',    -dm(34,  3), dm(23, 23),    2, None, (-0.1,  0.0, None, None), 1.1),
 '3792': ('Cape St. Francis',   -dm(34, 10), dm(24, 52),    2, None, (-0.1,  0.0, None, None), 1.1),
}
S223 = {
 '3797': ("Port St. John's",    -dm(31, 37), dm(29, 33),   -2, None, (-0.1,  0.0, None, None), 1.1),
 '3802': ('Kosi River Entrance', -dm(26, 53), dm(32, 54),   0, None, ( 0.0,  0.0, None, None), 1.1),
 '3806': ('Limpopo River Bar',  -dm(25, 12), dm(33, 31),  -32,  -32, (-4.9, -3.2, -2.0, -0.4), 1.0),
 '3820': ('Porto de Sofala',    -dm(20, 11), dm(34, 45),  -15, None, (-0.9, -0.6, None, None), 3.2),
 '3822': ('Pungue River Bar',   -dm(20,  0), dm(34, 58),  -40, None, (None, None, None, None), None),
 '3824': ('Mapanda',            -dm(19, 23), dm(34, 29),  310, None, (None, None, None, None), None),
 '3826': ('Inhamissengo Entrance', -dm(18, 54), dm(36, 12), -30, None, (-2.9, -1.9, None, None), 2.0),
 '3833': ('Macuse',             -dm(17, 43), dm(37, 11),  -40,  -55, (-2.4, -1.7, -1.0, -0.3), 2.3),
 '3834': ('Maquivale',          -dm(17, 44), dm(37,  5),  -10,  -25, (-1.9, -1.5, -0.8, -0.3), 2.4),
 '3838': ('Porto de Moebase',   -dm(17,  6), dm(38, 43),  -45,  -45, (-3.1, -2.1, None, None), 2.1),
 '3843': ('Angoche (Canal do Sul)', -dm(16, 15), dm(40, 1), -50, None, (-2.4, -1.6, None, None), 2.3),
 '3847': ('Mocambo',            -dm(15,  8), dm(40, 32),  -60, None, (-2.4, -1.6, None, None), 2.3),
}
S227 = {
 '4026': ('Mwamba Wa Ziwaiu',   -dm( 2, 37), dm(40, 35),  -15,  -15, (-0.5, -0.3, -0.3, -0.2), 1.6),
 '4027': ('Ziwa La Juu',        -dm( 2, 28), dm(40, 47),   -5,   -5, (-0.3, -0.2, -0.1, -0.1), 1.7),
 '4032': ('Buur Gaabo',         -dm( 1, 14), dm(41, 51),    0, None, (-0.8, -0.6, -0.4, -0.3), 1.4),
 '4036': ('Baraawe (Brava)',     dm( 1,  6), dm(44,  2),   -3, None, (-1.3, -1.0, None, None), 1.1),
 '4037': ('Marka',               dm( 1, 43), dm(44, 47),   -3, None, (-1.5, -1.2, None, None), 1.0),
 '4040': ('Cadale (Itala)',      dm( 2, 45), dm(46, 20), None, None, (-1.7, -1.2, None, None), 0.9),
 '4048': ('Raas Xaafuun',        dm(10, 28), dm(51, 22), None, None, (-1.8, -1.3, None, None), 0.9),
 '4052': ('Ghubbah di-Net',      dm(12, 27), dm(53, 28),  -90, None, (-0.2, -0.2, None, None), 1.2),
 '4055': ('Kal Farun',           dm(12, 30), dm(52, 10),   -5, None, (-0.5, -0.4, None, None), 1.0),
 '4056': ('Raas Caseyr',         dm(11, 50), dm(51, 16), -100, None, ( 0.0, -0.4, None, None), 1.2),
 '4057': ('Caluula',             dm(11, 58), dm(50, 46),   25,   25, ( 0.0, -0.2, -0.1,  0.0), 1.3),
 '4060': ('Laasqoray',           dm(11, 10), dm(48, 13),  -50, None, ( 0.1, -0.1, None, None), 1.4),
 '4062': ('Xiis',                dm(10, 54), dm(46, 55),  -30, None, ( 0.2,  0.0, None, None), 1.5),
 '4069': ('Ghoubbet Kharab',     dm(11, 33), dm(42, 34),   20, None, (-0.7, -0.6, None, None), 0.9),
 '4070': ('Obock',               dm(11, 57), dm(43, 17),   40, None, (-0.4, -0.2, None, None), 1.1),
 '4074': ('Ed',                  dm(13, 56), dm(41, 42),  100, None, (-1.0, -0.9, None, None), 0.5),
 '4076': ('Anfile Bay',          dm(14, 47), dm(40, 44),  140, None, (-1.0, -0.9, None, None), 0.5),
}
S230 = {
 '4190': ('Suhar',               dm(24, 23), dm(56, 44),   10,   10, (-0.4, -0.4, -0.5, -0.3), 1.5),
 '4202': ('Al Jazeera Port',     dm(25, 43), dm(55, 47),  -50, None, ( 0.1,  0.3, None, None), 1.1),
}
S234 = {
 '4321': ('Sonmiani Harbour',    dm(25, 23), dm(66, 33),  -45, None, ( 0.1,  0.1, None, None), 1.6, 5.0),
 '4324': ('Sir Mouth',           dm(23, 40), dm(68,  7),   10, None, ( 0.6,  0.6, None, None), 2.0, 5.0),
 '4340a': ('Diu Head',           dm(20, 41), dm(70, 50), None, None, (-1.3, -1.1,  0.2,  0.3), 1.50),
 '4345': ('Piram Island',        dm(21, 36), dm(72, 21),  -40, None, (-1.3, -1.0, None, None), 5.2),
 '4348': ('Khambhat (Cambay)',   dm(22, 17), dm(72, 37),   60, None, (-2.1, None, None, None), None),
 '4351': ('Mehegam',             dm(21, 40), dm(72, 46),   10,  145, (-5.6, -5.4, -3.1, -1.3), None),
 '4352': ('Bharuch',             dm(21, 41), dm(72, 59),  130,  325, (-7.4, -6.9, -3.2, -0.6), None),
}
S236 = {
 '4399': ('Cherbaniani Reef',    dm(12, 21), dm(71, 53),  -50, None, ( 0.7,  0.7, None, None), 1.2),
 '4400': ('Kadmat',              dm(11, 13), dm(72, 46),    0, None, ( 0.5,  0.4, None, None), 1.0),
 '4400a': ('Androth Island',     dm(10, 49), dm(73, 41), None, None, ( 0.4,  0.3,  0.2,  0.1), 0.9),
 '4406': ('Vattaru',             dm( 3, 15), dm(73, 24),   60, None, ( 0.1,  0.1, None, None), 0.7, 5.0),
 '4407': ('Hadhdunmathi Atoll',  dm( 1, 55), dm(73, 25),  290, None, ( 0.0,  0.0, None, None), 0.7, 5.0),
 '4408': ('North Huvadhu',       dm( 0, 53), dm(73, 19),  310, None, ( 0.0,  0.0, None, None), 0.7, 5.0),
 '4432': ('Hambantota',          dm( 6,  7), dm(81,  8),   30, None, (-0.1, -0.1, None, None), 0.4),
 '4435': ('Batticaloa Roads',    dm( 7, 46), dm(81, 41),  155, None, ( 0.0,  0.1, None, None), 0.5),
}
S237 = {
 '4446': ('Kottaippattanam',     dm( 9, 59), dm(79, 11),  160, None, (-0.1,  0.0, -0.1,  0.0), 0.4),
 '4453': ('Pulicat',             dm(13, 27), dm(80, 19), None, None, (-0.3, -0.2,  0.0,  0.1), 0.50),
 '4455': ('Vadarevu',            dm(15, 48), dm(80, 25), None, None, ( 0.4,  0.3,  0.3,  0.3), 0.9),
 '4456': ('Nizampatam',          dm(15, 53), dm(80, 38),   10, None, ( 0.2,  0.3, None, None), 0.7),
 '4457': ('Machilipatnam',       dm(16, 11), dm(81, 12),   20,   20, ( 0.5,  0.5,  0.5,  0.5), 1.1),
 '4482': ('Gangra Semaphore',    dm(21, 57), dm(88,  1),   35,   70, ( 0.4,  0.3, -0.1, -0.1), 3.16),
 '4482a': ('Haldia',             dm(22,  2), dm(88,  6),   51,   96, ( 0.5,  0.5, -0.1, -0.1), 3.23),
 '4483': ('Balari Semaphore',    dm(22,  5), dm(88, 11),   82,  136, (None, None, None, None), None),
 '4485': ('Hugli Point Semaphore', dm(22, 13), dm(88, 4), 137,  191, (None, None, None, None), None),
 '4486': ('Moyapur',             dm(22, 26), dm(88,  8),  194,  279, ( 0.3,  0.2, -0.4,  0.0), 3.00),
 '4490': ('Sandhead',            dm(20, 58), dm(88, 35),  -22,  -42, (-2.4, -1.8, None, None), 1.8),
 '4491': ('Canning Town',        dm(22, 18), dm(88, 40),  120,  158, ( 0.6,  0.7, None, None), 3.2),
}
S224b = {
 '3852': ('Port Simuco',        -dm(13, 59), dm(40, 36),  -25, None, ( 0.3,  0.3, None, None), 2.2, 2.0),
}
S225 = {
 '3951': ('St. Leu',            -dm(21,  9), dm(55, 17), -190, -200, (-0.9, -0.7, -0.4, -0.3), 0.51),
 '3952': ('St. Pierre',         -dm(21, 20), dm(55, 29), -235, -245, (-0.9, -0.7, -0.4, -0.3), 0.50),
 '3957': ('Vieux Grand Port',   -dm(20, 22), dm(57, 43), -195, None, (-0.9, -0.6, None, None), 0.5),
 '3960': ('Cargados Carajos',   -dm(15, 41), dm(59, 30), -110, None, (-0.6, -0.4, None, None), 0.6),
 '3963': ('Ile aux Vaches',     -dm( 3, 43), dm(55, 13),   15,    5, (-0.3, -0.3, -0.2, -0.2), 0.82),
 '3965': ('Baie Curieuse',      -dm( 4, 17), dm(55, 43),    5,   -5, (-0.2, -0.2, -0.1, -0.1), 0.90),
}
S226 = {
 '3973': ('St. Pierre Island',  -dm( 9, 19), dm(50, 43),   55, None, ( 0.8, None, None, None), None, 4.0),
 '3976': ('Cosmoledo Islands',  -dm( 9, 41), dm(47, 32),  -65, None, ( 0.8,  0.2, None, None), None),
 '3977': ('Assomption Island',  -dm( 9, 44), dm(46, 30),  -60, None, ( 1.4,  0.8, None, None), 1.1),
 '3979': ('Iles Glorieuses',    -dm(11, 30), dm(47, 22),   20, None, (-0.2, -0.1,  0.0,  0.2), 2.00),
 '3980a': ('Mtiti',             -dm(12, 55), dm(45,  4),   -1,    9, ( 0.1,  0.3, -0.1,  0.0), 2.10),
 '3981': ('Mutsamudu',          -dm(12, 10), dm(44, 24),  -40, None, ( 0.5,  0.6,  0.2,  0.3), 2.4),
 '3982': ('Fomboni',            -dm(12, 17), dm(43, 46),   10, None, ( 0.3,  0.5,  0.1,  0.3), 2.3),
 '3983': ('Moroni',             -dm(11, 42), dm(43, 15),   35, None, ( 1.0,  1.0,  0.4,  0.4), 2.7),
 '3984': ('Ruvuma Bay',         -dm(10, 24), dm(40, 27),   10, None, ( 0.1, -0.1, None, None), 1.8),
 '3986': ('Lindi',              -dm(10,  0), dm(39, 43),   -5,    5, (-0.1, -0.1, -0.2, -0.1), 1.9),
 '3988': ('Kiswere Haven',      -dm( 9, 25), dm(39, 38),  -10,    0, ( 0.1,  0.1, -0.1, -0.1), 2.0),
 '3990': ('Kilwa Masoko',       -dm( 8, 54), dm(39, 30),  -10,    0, ( 0.0,  0.0, -0.1, -0.1), 2.0),
 '3996': ('Salale',             -dm( 7, 51), dm(39, 20),   15, None, ( 0.4,  0.2, None, None), 2.1),
 '3997': ('Batja',              -dm( 7, 56), dm(39, 19),  135, None, (-1.2, None, None, None), None),
 '3998': ('Usimbe',             -dm( 8,  1), dm(38, 18),  195, None, (-2.7, None, None, None), None),
 '4000': ('Latham Island',      -dm( 6, 54), dm(39, 56),  -60, None, ( 0.5,  0.3, None, None), 2.2),
 '4002': ('Bagamoyo',           -dm( 6, 26), dm(38, 55),  -10,    0, ( 0.9,  0.8,  0.5,  0.3), 2.6),
 '4005': ('Ras Kizimkazi',      -dm( 6, 28), dm(39, 30),   -5, None, ( 0.6,  0.6, None, None), 2.5),
 '4008': ('Pangani Bay',        -dm( 5, 26), dm(39,  0),   -3,    7, ( 0.3,  0.4,  0.3,  0.3), 2.3),
 '4009': ('Mchengangazi Pass',  -dm( 5,  6), dm(39, 52),    0, None, ( 0.2,  0.2, None, None), 2.2),
 '4013': ('Msuka Bay',          -dm( 4, 54), dm(39, 42),    0, None, ( 0.5,  0.6, None, None), 2.4),
 '4014': ('Tanga Bay',          -dm( 5,  4), dm(39,  7),   -3,    7, ( 0.1,  0.2,  0.1,  0.1), 2.1),
}
S228 = {
 '4094': ("Marsa Sha'b",         dm(22, 51), dm(35, 47), -345, None, (-1.4, -1.2, None, None), 0.3, 2.0),
 '4095': ('Barnis (Berenice)',   dm(23, 56), dm(35, 29), -330, None, (-1.3, -1.1, None, None), 0.4, 2.0),
 '4100': ('Hurghada (Al Ghardaqah)', dm(27, 13), dm(33, 51), -340, None, (-1.0, -0.8, None, None), 0.6, 2.0),
 '4115': ('Sharm Ash Shaykh',    dm(27, 51), dm(34, 17), -330, -330, (-0.7, -0.5, -0.3, -0.1), 0.8, 2.0),
 '4117': ('Khalij al Qarah (Dahab)', dm(28, 28), dm(34, 30), -300, None, (-0.8, -0.6, None, None), 0.8, 2.0),
 '4118': ('Eilat',               dm(29, 33), dm(34, 57), -300, None, (-1.1, -0.9, -0.5, -0.4), 0.4, 2.0),
 '4120': ('Humaydah',            dm(29, 15), dm(34, 56), -220, None, (-0.8, -0.6, None, None), 0.8),
 '4122': ('Jazirat Tiran',       dm(28,  0), dm(34, 30), -280, None, (-0.7, -0.5, None, None), 0.9),
 '4125': ("Sharm an Nu'man",     dm(27,  6), dm(35, 45), -270, None, (-1.2, -1.0, None, None), 0.5),
 '4127': ('Mardunah',            dm(26,  4), dm(36, 28), -310, None, (-1.2, -1.0, None, None), 0.5),
 '4129': ('Al Hasani',           dm(24, 58), dm(37,  5), -285, None, (-1.2, -1.0, None, None), 0.5),
 '4138': ('Sanak Island',        dm(19, 43), dm(40, 38),  130, None, (-1.2, -0.9, None, None), 0.5),
 '4140': ('Hadarah Island',      dm(18, 26), dm(41, 13),  145, None, (-1.1, -0.9, None, None), 0.5),
 '4144': ('Tiqfash',             dm(15, 42), dm(42, 30),  140, None, (-0.7, -0.6, None, None), 0.8),
 '4147': ('Ras Mujamila',        dm(14, 36), dm(42, 54),  120, None, (-0.9, -0.7, None, None), 0.6),
}
S229 = {
 '4156': ('Shuqra',              dm(13, 22), dm(45, 41),   -5, None, (-0.4, -0.3, None, None), 1.1, 3.0),
 '4157': ('Magatinal Saghir',    dm(13, 24), dm(46, 26),   20, None, (-0.4, -0.3, None, None), 1.1, 3.0),
 '4159': ('Ras Safwan',          dm(13, 48), dm(47, 34),   20,   20, (-0.3, -0.3, -0.2, -0.2), 1.12, 3.0),
 '4160': ('Balhaf',              dm(13, 58), dm(48, 11),   30,   30, (-0.1, -0.1,  0.0, -0.1), 1.28, 3.0),
 '4163': ('Ras Sharmah',         dm(14, 49), dm(50,  2),   35, None, ( 0.1,  0.3, None, None), 1.5, 3.0),
 '4165': ('Qishn',               dm(15, 25), dm(51, 41),   30, None, (-0.2,  0.0, None, None), 1.3, 3.0),
 '4166': ('Nishtun',             dm(15, 49), dm(52, 12),   30,   30, (-0.2, -0.2, -0.1,  0.0), 1.1, 3.0),
 '4187': ('Sib',                 dm(23, 41), dm(58, 11),   10,   10, (-0.4, -0.4, -0.5, -0.3), 1.5),
 '4170a': ('Ash Shuwaymiyah',    dm(17, 49), dm(55, 27),  -11,  -12, (-0.7, -0.7, -0.4, -0.3), 1.15),
 '4172': ('Hamr an Nafur',       dm(19, 48), dm(57, 49),   10, None, ( 0.0,  0.0, None, None), 1.8),
 '4174': ('Ghubbat Hashish',     dm(20, 28), dm(58, 10),   30, None, ( 0.0, -0.1, None, None), 1.8),
 '4178': ('Ras Sheiblah',        dm(20, 58), dm(58, 48),   30, None, ( 0.0, -0.1, None, None), 1.8),
 '4180': ('Ras al Hadd',         dm(22, 32), dm(59, 48),   10, None, (-0.3, -0.3, None, None), 1.6),
}
S233 = {
 '4284': ('Bandar-e Ameri',      dm(28, 30), dm(51,  5), None, None, (-0.2,  0.0, -0.1, -0.1), 1.13),
 '4285b': ('Bordekhun',          dm(28,  0), dm(51, 23), None, None, (-0.1,  0.2, -0.3, -0.1), 1.17),
 '4286': ('Nakhilu',             dm(27, 49), dm(51, 28),  -80, None, ( 0.0,  0.1, None, None), 1.2),
 '4293': ('Jazireh-ye Qeys',     dm(26, 33), dm(54,  1), -640, None, (-1.1, -0.9, None, None), 1.2),
 '4302': ('Laft',                dm(26, 56), dm(55, 44), -710, None, ( 1.1,  1.0,  0.3,  0.5), 2.5),
 '4311': ('Gugsar',              dm(25, 32), dm(58, 50),  -91,  -89, (-0.1,  0.0,  0.2,  0.2), 1.60),
}
S235 = {
 '4356a': ('Tarapur',            dm(19, 52), dm(72, 41), None, None, ( 0.4,  0.4,  0.1,  0.1), 2.84),
 '4361': ('Thana',               dm(19, 12), dm(72, 59),  130, None, (-0.8, -0.6, None, None), 2.1),
 '4385a': ('Mangalore',          dm(12, 51), dm(74, 50), None, None, (-1.0, -1.0, -0.2,  0.0), 1.0),
}

BUCH = {222: S222, 223: S223, 224: {**S224, **S224b}, 225: S225, 226: S226,
        227: S227, 228: S228, 229: S229, 230: S230, 233: S233, 234: S234,
        235: S235, 236: S236, 237: S237}

# Nummern, die es im Buch nicht gibt -- Duplikate ihres Nachbarn.
PHANTOM = {
    '3866': 'Kopie von 3868 Nosy Mitsio (Name, Position und Z0 identisch); S.224 kennt keine 3866',
    '3885': 'Kopie von 3884 Nosy Makamby (Name, Position und Z0 identisch); S.224 kennt keine 3885',
    '4033': 'Kopie von 4032 Buur Gaabo (Name, Position und Z0 identisch); S.227 fuehrt '
            'nur 4032 Buur Gaabo und 4034 Qooriga Kismaayo',
}


# ---------------------------------------------------------------- Hilfsmittel
def key(att):
    m = re.match(r'(\d+)(.*)', att)
    return (int(m.group(1)), m.group(2))


def lies(path):
    """att -> dict(start, name_idx, ende, name, con, mer, tz, z0, quelle)."""
    L = open(path, encoding='iso-8859-1').read().split('\n')
    out, att = {}, None
    for i, l in enumerate(L):
        if l.startswith('# att_number:'):
            att = l.split(': ')[1].strip()
        elif re.match(r'^[+-]\d\d:\d\d :', l) and att:
            s = max(k for k in range(i) if L[k] == '# BEGIN HOT COMMENTS')
            e = i + 2
            while e < len(L) and not L[e].startswith('#'):
                e += 1
            con = {}
            for x in L[i + 2:e]:
                m = re.match(r'^([A-Z][A-Z0-9]*)\s+([\d.]+)\s+([\d.]+)$', x)
                if m and float(m.group(2)) > 0:
                    con[m.group(1)] = (float(m.group(2)), float(m.group(3)))
            out[att] = dict(start=s, ni=i - 1, ende=e, name=L[i - 1].strip(), con=con,
                            mer=l.split(' :')[0], tz=l.split(' :', 1)[1],
                            z0=float(L[i + 1].split()[0]),
                            quelle=next((x for x in L[s:i] if x.startswith('# source:')), ''))
            att = None
    return L, out


def lies_extern():
    """Bezugshaefen aus fremden Sammlungen holen -- att -> dict(name, con, mer, tz).

    ATT druckt fuer Standardhaefen keine Konstanten (die haben Part I). Welche
    Quelle je Bezugshafen gewaehlt wurde und warum, steht in BEZUG.
    """
    B = json.load(open(BEZUG))['bezug']
    nach_datei = {}
    for att, d in B.items():
        nach_datei.setdefault(d['datei'], []).append((att, d['station']))

    out = {}
    for datei, wanted in nach_datei.items():
        L = open(f'{HARM}/{datei}', encoding='iso-8859-1').read().split('\n')
        gesucht = dict((n, a) for a, n in wanted)
        for i, l in enumerate(L):
            if not re.match(r'^[+-]\d\d:\d\d ', l) or not i:
                continue
            name = L[i - 1].strip()
            if name not in gesucht:
                continue
            e, con = i + 2, {}
            while e < len(L) and not L[e].startswith('#') and L[e].strip():
                m = re.match(r'^([A-Z][A-Z0-9]*)\s+([\d.]+)\s+([\d.]+)$', L[e])
                if m and float(m.group(2)) > 0:
                    con[m.group(1)] = (float(m.group(2)), float(m.group(3)))
                e += 1
            att = gesucht.pop(name)
            out[att] = dict(name=B[att]['name'], con=con, mer=l.split(' :')[0],
                            tz=l.split(' :', 1)[1], quelle=datei, station=name)
        for name, att in gesucht.items():
            print(f'ACHTUNG: Bezug {att} "{name}" nicht in {datei} gefunden')
    return out


def transfer(ref_con, pegel, h, t, dz=0.0, ml=None):
    """Skalierung gegen die PUBLIZIERTEN Pegel des Bezugshafens.

    dz = Zone_Bezug - Zone_Sekundaer in Stunden. Die Zeitdifferenzen des Buches
    enthalten den Zonensprung; fuer die Phasen brauchen wir die Verzoegerung in
    Weltzeit. Fehlt die Zeitdifferenz ganz (Kreis-Symbol), bleibt es bei dt=0 --
    dann ist die Verzoegerung schlicht unbekannt, und auch die Zonenkorrektur
    allein waere geraten.
    """
    MHWS, MHWN, MLWN, MLWS = pegel
    SR, NR = MHWS - MLWS, MHWN - MLWN
    dMHWS, dMHWN, dMLWN, dMLWS = h
    if dMHWS is None:
        # Buch gibt gar keine Hoehendifferenz (Kreis-Symbol in allen vier
        # Spalten). Dann gilt derselbe Hub wie am Bezugshafen -- genau das
        # meint ATT damit, und genauso werden die drei anderen Spalten schon
        # behandelt. Nur der Zeitversatz wirkt.
        dMHWS = 0.0
    if dMLWS is None:
        dMLWS = 0.0
    if dMHWN is None:
        dMHWN = dMHWS
    if dMLWN is None:
        dMLWN = dMLWS
    # Fehlen die Niedrigwasserspalten (Kreis-Symbol), ist der Hub nicht bildbar.
    # "Niedrigwasser wie am Bezugshafen" anzunehmen sprengt den Faktor, sobald
    # der Nipphub klein ist -- Cherbaniani Reef kam so auf fN=4.5. Dann lieber
    # den Faktor gegen das MITTELWASSER bilden; das steht im Buch (Spalte ML)
    # und der Bezugswert folgt aus dem Gruppenkopf als (MHWS+MLWS)/2.
    # Wo beide Spalten da sind, liefern beide Regeln dasselbe (Al Qusayr 0.40),
    # deshalb greift die ML-Regel nur in der Luecke.
    MLref = 0.5 * (MHWS + MLWS)
    lw_fehlt = h[3] is None and ml is not None and MHWS > MLref + .01
    if lw_fehlt:
        fS = (MHWS + h[0] - ml) / (MHWS - MLref)
        fN = ((MHWN + (h[1] if h[1] is not None else h[0]) - ml) / (MHWN - MLref)
              if MHWN > MLref + .01 else fS)
    else:
        SRs = SR + (dMHWS - dMLWS)
        NRs = NR + (dMHWN - dMLWN)
        if SRs <= 0:
            SRs = max(0.10, 0.10 * SR)
        fS = SRs / SR
        fN = NRs / NR if NR > .01 else fS
    fS = max(.05, min(3., fS))
    fN = max(.05, min(3., fN))
    fD = .5 * (fS + fN)

    M2, S2 = ref_con.get('M2', (0, 0))[0], ref_con.get('S2', (0, 0))[0]
    if M2 <= 0:
        return None
    su, di = fS * (M2 + S2), fN * (M2 - S2)
    M2n, S2n = max(0, .5 * (su + di)), max(0, .5 * (su - di))
    rM = M2n / M2 if M2 > 0 else fS
    rS = S2n / S2 if S2 > 0 else fS

    v = [x for x in t if x is not None]
    dt = (sum(v) / len(v) / 60.0 + dz) if v else 0.0

    out = {}
    for c, (a, g) in ref_con.items():
        if c == 'M2':
            na = M2n
        elif c == 'S2':
            na = S2n
        elif c in SEMI_M:
            na = a * rM
        elif c == 'K2':
            na = a * rS
        elif c in SHALLOW:
            na = a * rM * rM
        elif c in DIURNAL:
            na = a * fD
        elif c in LANGZEIT:
            na = a
        else:
            na = a * fD
        sp = SPEED.get(c, 0.0)
        out[c] = (round(na, 4), round((g + sp * dt) % 360, 2))
    return dict(con=out, fS=fS, fN=fN, dt=dt, M2n=M2n, S2n=S2n)


def order(L):
    i = next(k for k, l in enumerate(L) if l.startswith('# Constituent speeds'))
    out = []
    for l in L[i:]:
        m = re.match(r'^(\S+)\s+[\d.]+\s*$', l)
        if m:
            out.append(m.group(1))
        elif out and l.startswith('#'):
            break
    return out


def gruppe(att, gruppen):
    k = key(att)
    for g in gruppen:
        if key(g['von']) <= k <= key(g['bis']):
            return g
    return None


# ---------------------------------------------------------------- Hauptlauf
def main():
    write = '--write' in sys.argv
    gruppen = json.load(open(GRUPPEN))['gruppen']
    L, SEC = lies(TXT)
    _, STDD = lies(STD)
    ORDER = order(L)
    # Reihenfolge: eigene ATT-Dateien zuerst, externe Bezugshaefen ueberschreiben
    # nichts -- sie fuellen nur die Luecken, die ATT gar nicht drucken kann.
    ref_by_att = {**SEC, **STDD}
    for att, r in lies_extern().items():
        ref_by_att.setdefault(att, r)

    todo, geloescht = [], []
    print(f'{"att":7s} {"Station":34s} {"fS alt":>7s} {"fS neu":>7s} {"M2 alt":>7s} {"M2 neu":>7s}  Bezug')
    print('-' * 104)

    for seite, rows in sorted(BUCH.items()):
        for att, row in sorted(rows.items(), key=lambda x: key(x[0])):
            bname, lat, lon, tH, tL, h, ml = row[:7]
            zone = row[7] if len(row) > 7 else ZONE_SEITE[seite]
            if att not in SEC:
                print(f'{att:7s} -- nicht in der Datei --'); continue
            b = SEC[att]
            if 'Part III' in b['quelle'] or 'Table V' in b['quelle']:
                continue                                   # laeuft auf gemessenen Konstanten
            g = gruppe(att, gruppen)
            if g is None:
                print(f'{att:7s} {b["name"][:34]:34s} keine Gruppe'); continue
            r = ref_by_att.get(g['ref'])
            if r is None:
                print(f'{att:7s} {b["name"][:34]:34s} Bezug {g["ref"]} nicht gefunden'); continue
            if g['ref'] not in ZONE_STD:
                print(f'{att:7s} {b["name"][:34]:34s} Zone des Bezugs {g["ref"]} unbekannt'); continue
            tr = transfer(r['con'], g['pegel'], h, (tH, tL),
                          ZONE_STD[g['ref']] - zone, ml)
            if tr is None:
                print(f'{att:7s} {b["name"][:34]:34s} keine Hoehendifferenz -- uebersprungen'); continue
            alt = b['con'].get('M2', (0, 0))[0]
            m = re.search(r'fS=([\d.]+)', ' '.join(L[b['start']:b['ni']]))
            print(f'{att:7s} {b["name"][:34]:34s} {m.group(1) if m else "-":>7s} {tr["fS"]:7.2f} '
                  f'{alt:7.3f} {tr["M2n"]:7.3f}  {g["name"][:26]} (S.{g["seite"]})')
            todo.append((att, b, tr, g, r, ml, lat, lon, seite, bname))

    for att, grund in sorted(PHANTOM.items(), key=lambda x: key(x[0])):
        if att in SEC:
            geloescht.append((att, SEC[att], grund))
            print(f'{att:7s} {SEC[att]["name"][:34]:34s} PHANTOM -> loeschen ({grund[:40]}...)')

    # Koordinaten nur pruefen, nicht ueberschreiben -- viele sind von Hand verfeinert.
    print('\nKoordinaten gegen das Buch (nur Meldung, es wird nichts geaendert):')
    weit = 0
    for att, b, tr, g, r, ml, lat, lon, seite, bname in todo:
        h = [x for x in L[b['start']:b['ni']]]
        flat = float(next(x for x in h if x.startswith('# !latitude:')).split(': ')[1])
        flon = float(next(x for x in h if x.startswith('# !longitude:')).split(': ')[1])
        d = 6371 * math.acos(max(-1, min(1, math.sin(math.radians(lat)) * math.sin(math.radians(flat))
                                         + math.cos(math.radians(lat)) * math.cos(math.radians(flat))
                                         * math.cos(math.radians(lon - flon)))))
        if d > 3.0:
            weit += 1
            print(f'  {att:7s} {b["name"][:34]:34s} Datei {flat:8.4f}/{flon:8.4f}  '
                  f'Buch {lat:8.4f}/{lon:8.4f}  {d:5.1f} km')
    if not weit:
        print('  keine Abweichung ueber 3 km')

    if not write:
        print(f'\n{len(todo)} neu abgeleitet, {len(geloescht)} Phantome. (Dry-run. --write zum Schreiben.)')
        return

    shutil.copy(TXT, f'{HARM}/backup/harmonics_att_np203_secondary_pre_bezug_{datetime.now():%Y%m%d}.txt')
    # von hinten nach vorn, damit die Indizes gueltig bleiben
    aktionen = ([('del', a, b, None, None, None, None, None, None, None) for a, b, _ in geloescht]
                + [('set',) + t for t in todo])
    for akt in sorted(aktionen, key=lambda x: -x[2]['start']):
        if akt[0] == 'del':
            b = akt[2]
            L[b['start']:b['ende']] = []
            continue
        _, att, b, tr, g, r, ml, lat, lon, seite, bname = akt
        head = [x for x in L[b['start']:b['ni']] if not x.startswith('# note:')]
        for k, x in enumerate(head):
            if x.startswith('# source:'):
                head[k] = '# source: ADMIRALTY Tide Tables Vol.3 (NP203), Part II Secondary Port Transfer'
            elif x.startswith('# date_imported:'):
                head[k] = f'# date_imported: {datetime.now():%Y%m%d}'
        # Koordinaten bleiben unangetastet -- viele sind von Hand verfeinert.
        # Abweichungen zum Buch werden nur gemeldet (siehe --write-Ausgabe).
        j = next(k for k, x in enumerate(head) if x.startswith('# att_number:')) + 1
        head[j:j] = [
            f'# note: NP203 Part II Sekundaerhafen-Transfer von {r["name"]} (att {g["ref"]}).',
            f'# note: fS={tr["fS"]:.2f} fN={tr["fN"]:.2f} dt={tr["dt"]*60:+.0f}min, skaliert gegen die',
            f'# note: publizierten Pegel {g["pegel"]} aus dem Gruppenkopf S.{g["seite"]}.',
            f'# note: {datetime.now():%Y%m%d} neu abgeleitet -- vorher falscher Bezugshafen bzw.',
            '# note: gerechneter statt publizierter Bezugshub. Zeit-/Hoehendiff. aus Part II '
            f'S.{seite} (Buch: {bname}).',
        ]
        if r.get('quelle', '').endswith('.txt'):
            head[j + 5:j + 5] = [
                f'# note: Konstituenten des Bezugshafens aus {r["quelle"]} '
                f'("{r["station"]}") --',
                '# note: ATT druckt fuer Standardhaefen keine Konstanten. '
                'Wahl siehe np203_bezugshafen_konstanten.json.']
        z0 = ml if ml is not None else b['z0']
        body = [b['name'], f'{r["mer"]} :{b["tz"]}', f'{z0:.4f} meters']
        for c in ORDER:
            body.append(f'{c:<16}{tr["con"][c][0]:.4f}  {tr["con"][c][1]:.2f}'
                        if c in tr['con'] else 'x 0 0')
        L[b['start']:b['ende']] = head + body

    open(TXT, 'w', encoding='iso-8859-1').write('\n'.join(L))
    os.chmod(TXT, 0o600)
    n = sum(1 for l in L if l.startswith('# !latitude:'))
    print(f'\n{len(todo)} neu abgeleitet, {len(geloescht)} geloescht. Datei: {n} Stationen')


if __name__ == '__main__':
    main()
