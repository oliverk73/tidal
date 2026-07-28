#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ersetzt Sekundaerhafen-Bloecke in harmonics_att_np203_secondary.txt durch die
GEMESSENEN Konstanten aus ATT NP203 Table V (Part III).

Warum: Table V enthaelt fuer die meisten Sekundaerhaefen eigene harmonische
Konstanten. Beim Import 2026-06 wurden daraus nur die 107 Standardhaefen
uebernommen (-> harmonics_att_np203.txt); alle uebrigen Zeilen blieben liegen,
und die Stationen wurden stattdessen aus den Part-II-Differenzen abgeleitet.
Der Transfer erbt Phasen vom Bezugshafen und schrumpft bei grossen negativen
Hoehendifferenzen den Hub zusammen -- Table V hat pro Station eigene Phasen.

Uebernommen werden Z0 (ML), M2, S2, K1, O1 aus dem Buch, N2/K2 nach den
Gleichgewichtsverhaeltnissen ergaenzt (wie py/build_np203.py), M4/M6 aus den
S.W.-Korrekturen f4/F4 und f6/F6, falls angegeben.

Position, Name, Land und Zeitzone bleiben aus dem Bestand -- die sind aus
Part II und von Oliver kuratiert. Der Meridian wird auf die Buchzone gesetzt.

Aufruf: python3 py/build_np203_tablev.py            # dry-run
        python3 py/build_np203_tablev.py --write
"""
from __future__ import annotations
import os
import re
import shutil
import sys
from datetime import datetime

TXT = '/home/oliver/weather/harmonics/att/harmonics_att_np203_secondary.txt'
STD = '/home/oliver/weather/harmonics/att/harmonics_att_np203.txt'   # Standardhaefen
HARM = '/home/oliver/weather/harmonics'
V = None      # "v" im Buch = kein Wert angegeben

# ATT NP203 Part III (harmonische Konstanten), am 20260728 aus dem Scan gelesen.
# att: (ML, M2(g,H), S2(g,H), K1(g,H), O1(g,H), M4(f4,F4), M6(f6,F6), Meridian)
PAGES = {
 245: {
    '4243':  (0.90, (131, 0.42), (178, 0.13), (99, 0.20), (42, 0.09), None, None, '+03:00'),
    '4244':  (1.20, (144, 0.54), (196, 0.19), (64, 0.15), (343, 0.07), (305, 0.077), None, '+03:00'),
    '4245':  (1.26, (142, 0.58), (200, 0.19), (51, 0.11), (339, 0.06), (287, 0.050), (132, 0.018), '+03:00'),
    '4246':  (0.82, (159, 0.42), (218, 0.11), (61, 0.07), (343, 0.04), None, None, '+03:00'),
    '4247':  (0.30, (209, 0.17), (271, 0.04), (99, 0.04), (34, 0.02), None, None, '+03:00'),
    '4247b': (0.34, (344, 0.16), (14, 0.04), (129, 0.10), (46, 0.02), None, None, '+03:00'),
    '4247c': (0.30, (283, 0.18), (339, 0.04), (117, 0.03), (58, 0.02), None, None, '+03:00'),
    '4247d': (0.30, (281, 0.22), (342, 0.05), (109, 0.05), (67, 0.02), None, None, '+03:00'),
    '4247e': (0.40, (259, 0.21), (337, 0.08), (177, 0.02), (20, 0.04), (67, 0.304), (234, 2.303), '+03:00'),
    '4247f': (0.40, (280, 0.23), (344, 0.04), (199, 0.02), (70, 0.05), (357, 0.591), None, '+03:00'),
    '4248':  (0.34, (206, 0.15), (257, 0.04), (100, 0.05), (4, 0.02), (352, 1.049), (123, 2.225), '+03:00'),
    '4249':  (0.15, (268, 0.05), (343, 0.01), (93, 0.02), (56, 0.01), None, None, '+03:00'),
    '4249a': (0.30, (240, 0.09), (289, 0.03), (103, 0.03), (32, 0.03), None, None, '+03:00'),
    '4250':  (0.36, (238, 0.11), (309, 0.04), (131, 0.04), (15, 0.03), None, None, '+03:00'),
    '4250a': (0.50, (183, 0.16), (243, 0.06), (106, 0.04), (28, 0.03), (311, 0.337), (202, 1.472), '+03:00'),
    '4250b': (0.40, (193, 0.17), (255, 0.06), (93, 0.04), (32, 0.04), (317, 0.777), (143, 2.109), '+03:00'),
    '4250c': (0.50, (172, 0.27), (229, 0.09), (75, 0.06), (7, 0.04), None, None, '+03:00'),
    '4250d': (1.34, (150, 0.58), (208, 0.20), (53, 0.10), (330, 0.07), (261, 0.034), (91, 0.014), '+03:00'),
    '4250e': (1.25, (141, 0.63), (192, 0.20), (55, 0.09), (310, 0.07), None, None, '+03:00'),
    '4250f': (1.45, (146, 0.65), (204, 0.22), (40, 0.11), (325, 0.07), (274, 0.022), (77, 0.008), '+03:00'),
    '4251':  (1.44, (150, 0.64), (213, 0.21), (49, 0.10), (331, 0.08), (250, 0.034), (19, 0.033), '+03:00'),
    '4253':  (1.55, (147, 0.61), (214, 0.23), (18, 0.10), (311, 0.08), (296, 0.096), (142, 0.044), '+03:00'),
    '4253a': (1.39, (151, 0.55), (201, 0.17), (5, 0.09), (302, 0.07), (298, 0.079), (117, 0.024), '+03:00'),
    '4253b': (1.00, (159, 0.37), (200, 0.17), (16, 0.05), (315, 0.05), (332, 0.209), (141, 0.085), '+03:00'),
    '4253c': (0.63, (159, 0.28), (218, 0.11), (10, 0.05), (326, 0.02), (352, 0.332), None, '+03:00'),
    '4253d': (0.32, (252, 0.08), (308, 0.02), (108, 0.02), (30, 0.02), None, None, '+03:00'),
    '4253e': (0.82, (146, 0.31), (190, 0.09), (15, 0.08), (330, 0.05), None, None, '+03:00'),
    '4253g': (1.10, (139, 0.54), (204, 0.17), (347, 0.12), (302, 0.09), (306, 0.169), None, '+03:00'),
    '4254a': (1.10, (130, 0.52), (188, 0.18), (331, 0.09), (272, 0.09), (333, 0.051), None, '+03:00'),
    '4254b': (0.94, (131, 0.51), (183, 0.18), (322, 0.14), (265, 0.11), None, None, '+03:00'),
    '4254c': (1.04, (126, 0.50), (184, 0.17), (325, 0.16), (272, 0.13), None, None, '+03:00'),
 },
 246: {   # Saudi/Kuwait/Irak Zone -0300, ab 4276b Iran Zone -0330
    '4255a': (1.02, (132, 0.46), (192, 0.16), (323, 0.18), (272, 0.14), (328, 0.063), (324, 0.023), '+03:00'),
    '4255b': (1.00, (124, 0.41), (184, 0.16), (305, 0.15), (269, 0.12), None, None, '+03:00'),
    '4256':  (0.82, (138, 0.35), (196, 0.13), (294, 0.19), (249, 0.14), (328, 0.044), (359, 0.003), '+03:00'),
    '4257':  (0.84, (100, 0.22), (167, 0.08), (316, 0.31), (267, 0.21), None, None, '+03:00'),
    '4257a': (1.06, (94, 0.20), (163, 0.08), (314, 0.32), (267, 0.21), None, None, '+03:00'),
    '4258':  (0.97, (15, 0.25), (76, 0.07), (311, 0.39), (263, 0.25), None, None, '+03:00'),
    '4259':  (1.00, (3, 0.25), (65, 0.08), (304, 0.38), (263, 0.21), None, None, '+03:00'),
    '4260':  (0.77, (209, 0.05), (247, 0.03), (297, 0.32), (251, 0.21), None, None, '+03:00'),
    '4260a': (0.72, (145, 0.08), (209, 0.04), (299, 0.30), (253, 0.20), (81, 1.138), (67, 0.400), '+03:00'),
    '4260b': (0.68, (340, 0.10), (31, 0.02), (296, 0.36), (250, 0.22), None, None, '+03:00'),
    '4260c': (0.82, (342, 0.17), (36, 0.05), (303, 0.36), (255, 0.24), None, None, '+03:00'),
    '4260d': (0.90, (335, 0.22), (34, 0.07), (300, 0.40), (265, 0.24), None, None, '+03:00'),
    '4260e': (1.00, (322, 0.26), (20, 0.08), (298, 0.41), (264, 0.24), None, None, '+03:00'),
    '4260f': (1.11, (344, 0.33), (42, 0.10), (307, 0.42), (258, 0.27), None, None, '+03:00'),
    '4260g': (1.21, (333, 0.34), (19, 0.11), (310, 0.41), (250, 0.27), None, None, '+03:00'),
    '4261a': (1.31, (323, 0.37), (18, 0.13), (298, 0.44), (254, 0.31), None, None, '+03:00'),
    '4261b': (1.54, (324, 0.54), (19, 0.15), (305, 0.40), (249, 0.28), None, None, '+03:00'),
    '4261c': (1.35, (336, 0.51), (52, 0.11), (312, 0.53), (261, 0.27), None, None, '+03:00'),
    '4262a': (1.70, (334, 0.66), (32, 0.23), (305, 0.47), (257, 0.29), None, None, '+03:00'),
    '4262b': (1.82, (326, 0.71), (26, 0.23), (305, 0.48), (254, 0.32), None, None, '+03:00'),
    '4264':  (2.17, (341, 0.99), (54, 0.33), (309, 0.51), (267, 0.33), None, None, '+03:00'),
    '4265':  (2.16, (330, 0.90), (33, 0.33), (304, 0.53), (255, 0.37), None, None, '+03:00'),
    '4266':  (2.44, (343, 1.26), (57, 0.43), (306, 0.66), (264, 0.31), None, None, '+03:00'),
    '4266a': (2.69, (345, 1.32), (51, 0.50), (311, 0.65), (262, 0.32), None, None, '+03:00'),
    '4268a': (1.77, (306, 0.96), (7, 0.31), (294, 0.61), (246, 0.33), None, None, '+03:00'),
    '4276b': (1.82, (306, 0.58), (352, 0.23), (298, 0.45), (258, 0.30), None, None, '+03:30'),
    '4280':  (1.45, (276, 0.65), (334, 0.26), (290, 0.42), (252, 0.30), None, None, '+03:30'),
    '4283a': (0.98, (195, 0.37), (249, 0.13), (268, 0.32), (226, 0.20), None, None, '+03:30'),
    '4285':  (1.14, (169, 0.50), (222, 0.18), (262, 0.25), (220, 0.18), None, None, '+03:30'),
    '4285a': (0.93, (160, 0.22), (215, 0.10), (313, 0.27), (267, 0.20), None, None, '+03:30'),
    '4288':  (1.00, (120, 0.51), (162, 0.17), (168, 0.24), (138, 0.12), None, None, '+03:30'),
    '4290':  (1.18, (73, 0.33), (111, 0.12), (145, 0.30), (114, 0.16), None, None, '+03:30'),
    '4295':  (1.07, (357, 0.42), (42, 0.14), (134, 0.35), (96, 0.20), None, None, '+03:30'),
    '4296':  (1.06, (351, 0.39), (39, 0.14), (137, 0.24), (87, 0.18), None, None, '+03:30'),
    '4297':  (1.52, (346, 0.60), (27, 0.23), (127, 0.33), (89, 0.22), None, None, '+03:30'),
    '4298':  (1.77, (329, 0.54), (17, 0.20), (122, 0.25), (78, 0.20), None, None, '+03:30'),
    '4299':  (1.42, (306, 0.74), (352, 0.25), (81, 0.29), (63, 0.20), None, None, '+03:30'),
    '4301':  (1.66, (339, 0.80), (32, 0.33), (109, 0.39), (101, 0.25), None, None, '+03:30'),
    '4303a': (2.20, (298, 1.08), (341, 0.38), (63, 0.36), (53, 0.25), (241, 0.022), (161, 0.006), '+03:30'),
    '4303b': (2.00, (298, 1.00), (334, 0.36), (64, 0.34), (52, 0.21), (299, 0.037), None, '+03:30'),
    '4307':  (1.78, (286, 0.90), (329, 0.33), (68, 0.37), (62, 0.27), None, None, '+03:30'),
    '4308':  (1.68, (286, 0.85), (331, 0.21), (65, 0.28), (55, 0.18), None, None, '+03:30'),
    '4309':  (1.39, (263, 0.74), (297, 0.29), (32, 0.39), (37, 0.22), None, None, '+03:30'),
 },
 244: {   # Musandam/VAE Zone -0400, ab 4233 Katar Zone -0300
    '4194':  (1.80, (281, 0.68), (314, 0.26), (39, 0.34), (38, 0.19), None, None, '+04:00'),
    '4194a': (1.84, (287, 0.70), (322, 0.29), (46, 0.30), (42, 0.19), None, None, '+04:00'),
    '4195':  (1.78, (288, 0.73), (335, 0.27), (43, 0.34), (41, 0.18), None, None, '+04:00'),
    '4196':  (1.83, (290, 0.72), (322, 0.27), (41, 0.31), (49, 0.19), None, None, '+04:00'),
    '4197':  (1.80, (299, 0.76), (335, 0.29), (57, 0.29), (55, 0.20), None, None, '+04:00'),
    '4198':  (1.49, (306, 0.70), (347, 0.25), (66, 0.23), (62, 0.16), None, None, '+04:00'),
    '4199':  (1.55, (309, 0.68), (347, 0.26), (79, 0.21), (63, 0.18), None, None, '+04:00'),
    '4199a': (1.48, (316, 0.67), (4, 0.25), (78, 0.22), (70, 0.16), None, None, '+04:00'),
    '4199b': (1.46, (317, 0.64), (358, 0.24), (91, 0.18), (81, 0.15), None, None, '+04:00'),
    '4200':  (1.40, (325, 0.60), (4, 0.24), (110, 0.17), (75, 0.15), None, None, '+04:00'),
    '4201':  (1.37, (326, 0.54), (11, 0.20), (111, 0.13), (88, 0.16), None, None, '+04:00'),
    '4203':  (1.10, (350, 0.45), (32, 0.13), (136, 0.19), (95, 0.17), None, None, '+04:00'),
    '4206':  (1.09, (5, 0.47), (57, 0.17), (157, 0.23), (107, 0.17), None, None, '+04:00'),
    '4208':  (0.92, (19, 0.41), (78, 0.15), (165, 0.26), (112, 0.15), None, None, '+04:00'),
    '4208a': (0.88, (8, 0.36), (72, 0.14), (164, 0.26), (115, 0.13), None, None, '+04:00'),
    '4209':  (1.23, (80, 0.45), (80, 0.12), (235, 0.24), (166, 0.24), None, None, '+04:00'),
    '4210a': (1.30, (14, 0.44), (68, 0.16), (157, 0.35), (104, 0.20), None, None, '+04:00'),
    '4210b': (1.36, (17, 0.46), (57, 0.17), (165, 0.37), (108, 0.21), None, None, '+04:00'),
    '4210c': (0.90, (75, 0.27), (156, 0.08), (204, 0.24), (184, 0.14), None, None, '+04:00'),
    '4211':  (1.12, (14, 0.37), (65, 0.15), (149, 0.28), (96, 0.17), None, None, '+04:00'),
    '4212':  (1.28, (45, 0.37), (103, 0.15), (180, 0.30), (137, 0.19), None, None, '+04:00'),
    '4213':  (1.40, (19, 0.45), (90, 0.14), (162, 0.43), (100, 0.22), None, None, '+04:00'),
    '4213a': (1.42, (18, 0.26), (92, 0.09), (168, 0.40), (113, 0.22), None, None, '+04:00'),
    '4215':  (1.20, (16, 0.26), (67, 0.12), (153, 0.34), (100, 0.18), None, None, '+04:00'),
    '4219':  (0.96, (22, 0.11), (97, 0.04), (156, 0.36), (117, 0.16), None, None, '+04:00'),
    '4220':  (1.00, (40, 0.10), (90, 0.05), (152, 0.35), (100, 0.17), None, None, '+04:00'),
    '4221':  (0.97, (72, 0.07), (143, 0.05), (149, 0.34), (111, 0.16), None, None, '+04:00'),
    '4221a': (0.90, (140, 0.08), (181, 0.05), (152, 0.38), (106, 0.21), None, None, '+04:00'),
    '4221b': (1.07, (292, 0.09), (305, 0.04), (179, 0.44), (105, 0.24), None, None, '+04:00'),
    '4222':  (1.07, (272, 0.10), (256, 0.03), (163, 0.46), (108, 0.22), None, None, '+04:00'),
    '4223':  (1.07, (263, 0.11), (235, 0.04), (156, 0.48), (109, 0.24), None, None, '+04:00'),
    '4223a': (1.00, (245, 0.13), (238, 0.06), (161, 0.45), (107, 0.23), None, None, '+04:00'),
    '4224':  (1.05, (211, 0.06), (230, 0.04), (153, 0.40), (110, 0.18), None, None, '+04:00'),
    '4228':  (1.07, (237, 0.17), (259, 0.08), (161, 0.47), (108, 0.19), None, None, '+04:00'),
    '4229':  (1.18, (231, 0.14), (236, 0.05), (157, 0.46), (121, 0.22), None, None, '+04:00'),
    '4230':  (1.00, (232, 0.22), (256, 0.09), (159, 0.51), (113, 0.26), None, None, '+04:00'),
    '4231':  (1.20, (227, 0.24), (250, 0.09), (157, 0.49), (123, 0.23), None, None, '+04:00'),
    '4232':  (1.35, (220, 0.34), (250, 0.15), (160, 0.54), (106, 0.20), None, None, '+04:00'),
    '4233':  (1.01, (151, 0.15), (170, 0.06), (141, 0.48), (83, 0.19), None, None, '+03:00'),
    '4234':  (0.95, (102, 0.21), (135, 0.07), (126, 0.30), (76, 0.15), None, None, '+03:00'),
    '4235':  (1.30, (185, 0.31), (218, 0.14), (141, 0.47), (77, 0.25), None, None, '+03:00'),
    '4235a': (1.30, (179, 0.30), (209, 0.13), (137, 0.50), (90, 0.27), None, None, '+03:00'),
    '4237':  (1.28, (174, 0.27), (204, 0.12), (140, 0.46), (88, 0.20), None, None, '+03:00'),
    '4238':  (0.90, (153, 0.27), (192, 0.06), (126, 0.37), (68, 0.15), None, None, '+03:00'),
    '4239a': (0.90, (128, 0.33), (163, 0.10), (118, 0.34), (59, 0.15), None, None, '+03:00'),
    '4240':  (0.90, (124, 0.34), (157, 0.11), (109, 0.34), (59, 0.15), None, None, '+03:00'),
    '4241':  (0.90, (115, 0.31), (198, 0.09), (119, 0.35), (54, 0.16), None, None, '+03:00'),
 },
}


BOOKNAME = {
 '4255a': 'Abu Ali',
 '4255b': 'Jazirat al Jurayd',
 '4256': 'Al Arabiyah',
 '4257': 'Manifah',
 '4257a': 'Tanajib Pier',
 '4258': 'Ras as Saffaniyah',
 '4259': "Mina Ras Mish'ab",
 '4260': 'Marjan Oilfield',
 '4260a': 'Lawhah Oilfield',
 '4260b': 'Zuluf Oilfield',
 '4260c': 'Saffaniyah Oilfield',
 '4260d': 'Khafji Oilfield',
 '4260e': 'Hout Oilfield',
 '4260f': 'Ras al Khafji',
 '4260g': 'Jazirat Umm al Maradim',
 '4261a': 'Jazirat Qaru',
 '4261b': 'Jazirat Kubbar',
 '4261c': "Ras al Qulay'ah",
 '4262a': 'Al Fintas',
 '4262b': 'Jazirat Awhah',
 '4264': 'Mina ad Dawhah',
 '4265': 'Ras al Barshah (Beacon No. 2)',
 '4266': 'Hadd Warbah',
 '4266a': 'Umm Al-Aseed (Beacon No. 15)',
 '4268a': 'Al Basrah (Al Bakr) Terminal',
 '4276b': 'Khowr-e Musa Approaches',
 '4280': 'Bandar Deylam',
 '4283a': 'Halileh',
 '4285': 'Lavar-e Saheli',
 '4285a': 'Al Farisiyah',
 '4288': 'Asaluyeh',
 '4290': 'Jazireh-ye-Lavan',
 '4295': 'Jazireh-ye Forur',
 '4296': 'Jazireh-ye Sirri',
 '4297': 'Bandar-e Lengeh',
 '4298': 'Jazireh-ye Tonb-e Bozorg',
 '4299': 'Jazireh-ye Hengam',
 '4301': "Basa'idu",
 '4303a': 'Bandar-e Shahid Bahonar',
 '4303b': 'Bandar Abbas',
 '4307': 'Bandar-e Sirik',
 '4308': 'Gonari Creek',
 '4309': 'Ras al Kuh',
 '4194': 'Mina Diba', '4194a': 'Al Lima', '4195': 'Khawr Habalayn', '4196': 'Ras Dillah',
 '4197': 'Didamar', '4198': 'Khawr al Quway', '4199': 'Khasab', '4199a': 'Ghubbat Dabshun',
 '4199b': 'Bukha', '4200': 'Saqr Port (Mina Saqr)', '4201': 'Ras al Khaymah',
 '4203': 'Umm al-Qaiwain', '4206': 'Dubai (Al Maktoum Bridge)', '4208': 'Khawr Ghanadah',
 '4208a': 'Khawr Ghurabi', '4209': "Khawr Sa'diyat", '4210a': 'Umm ad Dalkh',
 '4210b': 'Mina Zayid Approaches', '4210c': 'Sas an Nakhl', '4211': "Sir Abu Nu'ayr",
 '4212': 'Ras al Ghaf', '4213': 'Abu al Abyad', '4213a': 'Fasht al Bazam',
 '4215': 'Zaqqum Oilfield (Platform Zws)', '4219': 'Zirku', '4220': 'Zirku Terminal',
 '4221': 'Jazirat Das', '4221a': 'El Bunduq Oilfield', '4221b': "Ar Ru'ays",
 '4222': 'Jabal az Zannah', '4223': 'Sir Bani Yas', '4223a': 'Ghasha Light Buoy',
 '4224': 'Jazirat Arzanah', '4228': 'Jazirat Shuwayhat', '4229': 'Jazirat Dalma',
 '4230': 'Jazair al Yasat', '4231': 'Umm al Hatab', '4232': 'Jazair Ghaghah',
 '4233': "Jazirat Shara'iwah", '4234': 'Jazirat Halul', '4235': 'Ras Abu Qumayyis',
 '4235a': 'Khawr al Udayd', '4237': "Mesaieed (Musay'id)", '4238': 'Al Wakrah',
 '4239a': 'Al Jazirah al Aliyah', '4240': 'Sumaysimah', '4241': 'Khawr Shaqiq',
 '4243': 'Jabal al Fuwayrit', '4244': "Ar Ru'ays", '4245': 'Fasht al Dibal',
 '4246': "Ras ' Ushayriq", '4247': 'Nagiyah', '4247b': 'Zikrit', '4247c': 'Dukhan',
 '4247d': 'Umm Bab', '4247e': 'Al Khraij', '4247f': 'Ghar al Buraid',
 '4248': 'Hawar Island (North East)', '4249': 'Az Zallaq', '4249a': 'Mutarid',
 '4250': 'Ras al Jamal', '4250a': 'Bahrain Yacht Club (Sitrah)', '4250b': 'Umm Jalid',
 '4250c': 'Umais', '4250d': 'Ne Fasht al Adhm', '4250e': 'Bahrain Approach Buoy',
 '4250f': 'Khalifa Bin Salman Port', '4251': 'Sitrah (Bapco Causeway)',
 '4253': 'Mina al Manama', '4253a': 'Khawr Fasht', '4253b': 'Al Budayyi',
 '4253c': 'Al Jasser Island', '4253d': 'Qurayyah Pier', '4253e': 'Al Khubar',
 '4253g': 'Dawhat at Tarut', '4254a': "Abu Sa'fah", '4254b': 'Fasht Gharibah',
 '4254c': "Ju'aymah Boat Pier",
}


def order(L):
    """Konstituenten-Reihenfolge aus dem Dateikopf."""
    i = next(k for k, l in enumerate(L) if l.startswith('# Constituent speeds'))
    out = []
    for l in L[i:]:
        m = re.match(r'^(\S+)\s+[\d.]+\s*$', l)
        if m:
            out.append(m.group(1))
        elif out and l.startswith('#'):
            break
    return out


STOP = {'mina', 'al', 'ad', 'as', 'an', 'ar', 'el', 'island', 'islands', 'port', 'oilfield',
        'terminal', 'buoy', 'light', 'pier', 'jazirat', 'jazireh', 'ras', 'khawr', 'khor',
        'bay', 'the', 'de', 'creek', 'platform'}


def _norm(name):
    import unicodedata
    n = unicodedata.normalize('NFKD', name.split(',')[0])
    n = ''.join(c for c in n if not unicodedata.combining(c)).lower().replace("'", '')
    return re.sub(r'[^a-z0-9 ]', ' ', n)


def tokens(name):
    return {t for t in _norm(name).split() if len(t) >= 4 and t not in STOP}


def name_matches(book, file_name):
    """Buchname gegen Dateiname. Olivers Umbenennungen (Zusaetze in Klammern,
    andere Transliteration) sollen durchgehen, ein anderer Ort nicht."""
    from difflib import SequenceMatcher
    ALIAS = {('zikrit', 'zekreet')}
    if not book:
        return True
    if (tokens(book) and tokens(file_name)
            and (min(tokens(book)), min(tokens(file_name))) in ALIAS):
        return True
    a, b = tokens(book), tokens(file_name)
    if a & b:
        return True
    for x in a:                                   # aehnliches Token (Transliteration)
        for y in b:
            if SequenceMatcher(None, x, y).ratio() >= 0.75:
                return True
    return SequenceMatcher(None, _norm(book), _norm(file_name)).ratio() >= 0.7


def constituents(row):
    ml, m2, s2, k1, o1, m4, m6, zone = row
    con = {}
    for name, v in (('M2', m2), ('S2', s2), ('K1', k1), ('O1', o1)):
        if v:
            con[name] = (v[1], float(v[0]))
    if 'M2' in con and 'S2' in con:                     # N2/K2 wie in build_np203.py
        aM2, gM2 = con['M2']; aS2, gS2 = con['S2']
        con['N2'] = (round(0.19 * aM2, 4), (gM2 - 0.536 * (gS2 - gM2)) % 360)
        con['K2'] = (round(0.27 * aS2, 4), gS2 % 360)
    if 'M2' in con:                                     # S.W.-Korrekturen -> M4/M6
        H, g = con['M2']
        if m4:
            f4, F4 = m4
            con['M4'] = (round(F4 * H * H, 4), round((2 * g + f4) % 360, 2))
        if m6:
            f6, F6 = m6
            con['M6'] = (round(F6 * H ** 3, 4), round((3 * g + f6) % 360, 2))
    return con


def main():
    write = '--write' in sys.argv
    L = open(TXT, encoding='iso-8859-1').read().split('\n')
    ORDER = order(L)
    assert 'M2' in ORDER and len(ORDER) >= 170, len(ORDER)

    # Bloecke finden
    blocks = {}
    att = None
    for i, l in enumerate(L):
        if l.startswith('# att_number:'):
            att = l.split(': ')[1].strip()
        elif re.match(r'^[+-]\d\d:\d\d :', l) and att:
            s = max(k for k in range(i) if L[k] == '# BEGIN HOT COMMENTS')
            e = i
            while e < len(L) and not L[e].startswith('#'):
                e += 1
            blocks[att] = (s, i - 1, e)
            att = None

    S = open(STD, encoding='iso-8859-1').read().split('\n')
    elsewhere = {}
    att2 = None
    for i, l in enumerate(S):
        if l.startswith('# att_number:'):
            att2 = l.split(': ')[1].strip()
        elif re.match(r'^[+-]\d\d:\d\d :', l) and att2:
            elsewhere[att2] = S[i - 1].strip(); att2 = None
    print(f'{"att":7s} {"Station":34s} {"M2 alt":>14s} {"M2 Table V":>14s} {"Z0":>11s}')
    todo = []
    TABLEV = {a: r for pg in sorted(PAGES) for a, r in PAGES[pg].items()}
    SEITE = {a: pg for pg in sorted(PAGES) for a in PAGES[pg]}
    for a, row in sorted(TABLEV.items()):
        if a not in blocks:
            wo = elsewhere.get(a)
            print(f'{a:7s} {"-- steht als Standardhafen in np203.txt: " + wo if wo else "-- fehlt in der Sammlung --"}')
            continue
        s, ni, e = blocks[a]
        name = L[ni].strip()
        if not name_matches(BOOKNAME.get(a, ''), name):
            print(f'{a:7s} {name[:34]:34s} NAME WEICHT AB -- Buch: {BOOKNAME.get(a,"?")}  -> uebersprungen')
            continue
        con = constituents(row)
        old = {x.split()[0]: (float(x.split()[1]), float(x.split()[2]))
               for x in L[ni + 2:e] if re.match(r'^[A-Z][A-Z0-9]*\s+[\d.]+\s+[\d.]+$', x)}
        z0_old = float(L[ni + 2].split()[0])
        oM2 = old.get('M2', (0, 0))
        print(f'{a:7s} {name[:34]:34s} {oM2[0]:6.3f}@{oM2[1]:6.1f} {con["M2"][0]:6.3f}@{con["M2"][1]:6.1f} '
              f'{z0_old:5.2f}->{row[0]:5.2f}')
        todo.append((a, s, ni, e, name, con, row[0], row[7], SEITE[a]))

    if not write:
        print(f'\n{len(todo)} Stationen. (Dry-run. --write zum Schreiben.)')
        return

    shutil.copy(TXT, f'{HARM}/backup/harmonics_att_np203_secondary_pre_partIII_{datetime.now():%Y%m%d}.txt')
    for a, s, ni, e, name, con, ml, zone, seite in sorted(todo, key=lambda x: -x[1]):
        head = L[s:ni]
        head = [x for x in head if not x.startswith('# note:')]
        for k, x in enumerate(head):
            if x.startswith('# source:'):
                head[k] = '# source: ADMIRALTY Tide Tables Vol.3 (NP203), Table V (Part III)'
            elif x.startswith('# confidence:'):
                head[k] = '# confidence: 7'
            elif x.startswith('# date_imported:'):
                head[k] = f'# date_imported: {datetime.now():%Y%m%d}'
        j = next(k for k, x in enumerate(head) if x.startswith('# att_number:')) + 1
        head[j:j] = [f'# note: NP203 Part III S.{seite} (2015), Meridian {zone}. Gemessene',
                     '# note: Konstanten statt Part-II-Transfer. N2/K2 inferiert, M4/M6 aus f4/f6.',
                     f'# note: Ersetzt am {datetime.now():%Y%m%d} den Sekundaerhafen-Transfer.']
        tz = L[ni + 1].split(' :', 1)[1]
        body = [name, f'{zone} :{tz}', f'{ml:.4f} meters']
        for c in ORDER:
            body.append(f'{c:<16}{con[c][0]:.4f}  {con[c][1]:.2f}' if c in con else 'x 0 0')
        L[s:e] = head + body
    open(TXT, 'w', encoding='iso-8859-1').write('\n'.join(L))
    os.chmod(TXT, 0o600)
    print(f'\n{len(todo)} Stationen ersetzt. Datei: {sum(1 for l in L if l.startswith("# !latitude:"))} Stationen')


if __name__ == '__main__':
    main()
