#!/usr/bin/env python3
# -*- coding: iso-8859-1 -*-
"""Baut XTide-Current-Stationen aus NP203 Vol.3 Part IIIa (Tidal Stream
Harmonic Constants, PDF 177-179) -> harmonics/utide/harmonics_att_np203_currents.txt

Zwei Quell-Formate:
  * reversing: eine Zeile mit Dir(+)/Dir(-) -> 1D direkt, Flutrichtung = Dir(+)
  * rotary:    N/E-Komponenten -> Tiden-Ellipse, Projektion auf M2-Hauptachse

Phasen g in lokaler Zonenzeit (Zone -HHMM => Meridian +HH:MM), je Station
einzeln (mehrere Zonen pro Seite!). Amplituden H in Knoten. Z0 = Reststrom
(bei rotary als N/E-Vektor -> auf Hauptachse projiziert).

Werte visuell aus dem gerenderten PDF gelesen (OCR der Zahlen unzuverlaessig).
ACHTUNG: handtranskribiert -> vor Deploy Stichprobe gegen Part Ia / Quelle.
"""
import cmath
import math
import os
import re
import subprocess

ROOT = os.path.expanduser("~")
HEADER_SRC = os.path.join(ROOT, "harmonics/utide/harmonics_utide_current_tables.txt")
OUT = os.path.join(ROOT, "harmonics/utide/harmonics_att_np203_currents.txt")
TCD = os.path.join(ROOT, "harmonics/binary/harmonics_att_np203_currents.tcd")
SOURCE = "Admiralty Tide Tables NP203 Vol.3 (2002), Part IIIa Tidal Stream Harmonic Constants"


def dm(d, m):
    return d + m / 60.0


def mer_from_zone(zone):
    """'-0400' -> '+04:00' (Meridian = ost-positiv = negierte Zone)."""
    sign = "+" if zone[0] == "-" else "-"
    return f"{sign}{zone[1:3]}:{zone[3:5]}"


def _cd(m2, s2, k1, o1):
    out = {}
    for name, val in zip(("M2", "S2", "K1", "O1"), (m2, s2, k1, o1)):
        if val is not None:
            out[name] = val
    return out


def R(no, name, lat, lon, flood, ebb, m2, s2, k1, o1, zone, tz, country, z0=0.0):
    return {"no": no, "name": name, "lat": lat, "lon": lon, "zone": zone,
            "meridian": mer_from_zone(zone), "tzfile": tz, "country": country,
            "z0": z0, "type": "reversing", "flood": flood, "ebb": ebb,
            "const": _cd(m2, s2, k1, o1)}


def ROT(no, name, lat, lon, n, e, zone, tz, country, z0n=0.0, z0e=0.0):
    return {"no": no, "name": name, "lat": lat, "lon": lon, "zone": zone,
            "meridian": mer_from_zone(zone), "tzfile": tz, "country": country,
            "z0n": z0n, "z0e": z0e, "type": "rotary", "n": _cd(*n), "e": _cd(*e)}


# Kuerzel fuer tz-Files
MUS, DUB, QAT, BAH, KUW, BAG = ("Asia/Muscat", "Asia/Dubai", "Asia/Qatar",
                                "Asia/Bahrain", "Asia/Kuwait", "Asia/Baghdad")
TEH, SIN, JKT, MKS = "Asia/Tehran", "Asia/Singapore", "Asia/Jakarta", "Asia/Makassar"
KUL, MNL, KCH, JAY = "Asia/Kuala_Lumpur", "Asia/Manila", "Asia/Kuching", "Asia/Jayapura"

STATIONS = [
    # ===== PDF 177  -  Oman / Strait of Hormuz / The Gulf  (Zone -0400) =====
    R(418, "Masirah, Oman (NP203 418) Current", dm(20, 41.9), dm(58, 51.9), 210, 30,
      (202, 1.46), (239, 0.54), (309, 0.41), (316, 0.22), "-0400", MUS, "Oman"),
    R(419, "Off Muscat, Oman (NP203 419) Current", dm(23, 37.9), dm(58, 35.4), 277, 77,
      (172, 0.28), (207, 0.10), (175, 0.16), (170, 0.08), "-0400", MUS, "Oman"),
    ROT(420, "Strait of Hormuz (NP203 420) Current", dm(26, 22.2), dm(56, 41.7),
        ((296, 0.44), (332, 0.17), (88, 0.64), (84, 0.34)),
        ((81, 0.10), (117, 0.04), (159, 0.05), (155, 0.03)), "-0400", MUS, "Oman"),
    ROT(4201, "Khawr Quway (NP203 420a) Current", dm(26, 21.7), dm(56, 21.8),
        ((110, 0.63), (148, 0.23), (221, 0.75), (218, 0.46)),
        ((127, 0.32), (165, 0.12), (198, 0.27), (195, 0.17)), "-0400", DUB, "United Arab Emirates"),
    ROT(421, "The Gulf (NP203 421) Current", dm(24, 51.8), dm(53, 42.3),
        ((98, 0.45), (166, 0.18), (216, 0.23), (216, 0.10)),
        ((212, 0.23), (268, 0.10), (236, 0.19), (309, 0.01)), "-0400", DUB, "United Arab Emirates"),
    ROT(4211, "The Gulf (NP203 421a) Current", dm(25, 18.0), dm(54, 14.0),
        ((129, 0.20), (184, 0.08), (258, 0.25), (212, 0.15)),
        ((238, 0.32), (293, 0.12), (351, 0.32), (305, 0.19)), "-0400", DUB, "United Arab Emirates"),
    ROT(4212, "The Gulf (NP203 421b) Current", dm(25, 13.0), dm(54, 17.0),
        ((135, 0.27), (190, 0.10), (255, 0.28), (209, 0.17)),
        ((226, 0.15), (281, 0.06), (299, 0.23), (253, 0.14)), "-0400", DUB, "United Arab Emirates"),
    R(422, "The Gulf (NP203 422) Current", dm(24, 23.3), dm(52, 38.3), 310, 130,
      (85, 0.59), (163, 0.34), (253, 0.27), (301, 0.14), "-0400", DUB, "United Arab Emirates"),
    ROT(4221, "The Gulf (NP203 422a) Current", dm(24, 39.2), dm(52, 34.7),
        ((273, 0.12), (333, 0.04), (229, 0.35), (226, 0.24)),
        ((261, 0.42), (321, 0.14), (253, 0.23), (250, 0.16)), "-0400", DUB, "United Arab Emirates"),
    ROT(4222, "The Gulf (NP203 422b) Current", dm(24, 49.3), dm(52, 56.2),
        ((317, 0.21), (17, 0.07), (251, 0.59), (248, 0.41)),
        ((275, 0.33), (335, 0.11), (276, 0.24), (273, 0.17)), "-0400", DUB, "United Arab Emirates"),
    ROT(4223, "The Gulf (NP203 422c) Current", dm(24, 56.3), dm(52, 57.3),
        ((255, 0.02), None, (291, 0.44), (268, 0.21)),
        ((290, 0.28), (344, 0.13), (315, 0.25), (293, 0.12)), "-0400", DUB, "United Arab Emirates"),
    ROT(4224, "The Gulf (NP203 422d) Current", dm(25, 6.0), dm(52, 37.0),
        ((319, 0.15), (322, 0.07), (253, 0.33), (202, 0.15)),
        ((285, 0.29), (315, 0.18), (284, 0.23), (238, 0.11)), "-0400", DUB, "United Arab Emirates"),
    ROT(424, "The Gulf (NP203 424) Current", dm(25, 13.1), dm(51, 44.5),
        ((357, 0.37), (336, 0.17), (267, 0.51), (222, 0.13)),
        ((346, 0.14), (332, 0.06), (292, 0.23), (224, 0.12)), "-0400", QAT, "Qatar"),
    ROT(4241, "The Gulf (NP203 424a) Current", dm(25, 21.6), dm(52, 0.7),
        ((355, 0.28), (6, 0.03), (225, 0.25), (187, 0.06)),
        ((277, 0.22), (307, 0.13), (255, 0.15), (32, 0.04)), "-0400", QAT, "Qatar"),
    R(4242, "The Gulf (NP203 424b) Current", dm(24, 52.1), dm(51, 42.6), 220, 40,
      (193, 0.87), (137, 0.57), (92, 0.85), (77, 0.29), "-0400", QAT, "Qatar"),
    ROT(4243, "The Gulf (NP203 424c) Current", dm(26, 10.8), dm(51, 52.0),
        ((113, 0.18), (174, 0.05), (251, 0.54), (221, 0.30)),
        ((272, 0.36), (333, 0.09), (17, 0.28), (347, 0.15)), "-0400", BAH, "Bahrain"),
    ROT(4244, "The Gulf (NP203 424d) Current", dm(25, 17.6), dm(51, 47.0),
        ((356, 0.18), (29, 0.06), (271, 0.49), (222, 0.13)),
        ((282, 0.06), (315, 0.02), (321, 0.39), (272, 0.18)), "-0400", QAT, "Qatar"),
    ROT(4245, "The Gulf (NP203 424e) Current", dm(25, 46.4), dm(52, 2.4),
        ((184, 0.08), (226, 0.02), (223, 0.34), (167, 0.16)),
        ((267, 0.33), (309, 0.10), (324, 0.09), (268, 0.04)), "-0400", QAT, "Qatar"),
    R(4246, "The Gulf (NP203 424f) Current", dm(26, 17.2), dm(52, 24.0), 110, 300,
      (274, 0.33), (316, 0.10), (69, 0.26), (20, 0.12), "-0400", BAH, "Bahrain"),
    R(4247, "The Gulf (NP203 424g) Current", dm(25, 29.8), dm(53, 45.1), 110, 290,
      (264, 0.41), (307, 0.16), (340, 0.24), (298, 0.13), "-0400", DUB, "United Arab Emirates"),

    # ===== PDF 178  -  N Gulf (Kuwait) / Iran / Singapore Strait =====
    # Zone -0300 (Kuwait/Iraq)
    ROT(426, "NW Persian Gulf (NP203 426a) Current", dm(28, 27.1), dm(48, 35.7),
        ((208, 0.28), (265, 0.09), (170, 0.18), (135, 0.03)),
        ((39, 0.21), (94, 0.06), (317, 0.18), (336, 0.03)), "-0300", KUW, "Kuwait"),
    ROT(4262, "NW Persian Gulf (NP203 426b) Current", dm(28, 28.5), dm(48, 56.2),
        ((211, 0.27), (293, 0.07), (220, 0.24), (158, 0.11)),
        ((55, 0.37), (131, 0.11), (8, 0.21), (290, 0.12)), "-0300", KUW, "Kuwait"),
    ROT(4263, "Khawr Abd Allah (NP203 426c) Current", dm(29, 56.8), dm(49, 7.6),
        ((194, 0.44), (241, 0.17), (205, 0.11), (133, 0.10)),
        ((51, 0.41), (88, 0.17), (10, 0.15), (0, 0.10)), "-0300", BAG, "Iraq"),
    # Zone -0330 (Iran)
    ROT(429, "Off Bushehr, Iran (NP203 429) Current", dm(27, 26.9), dm(51, 25.1),
        ((137, 0.14), (192, 0.05), (225, 0.38), (220, 0.27)),
        ((343, 0.27), (38, 0.09), (31, 0.51), (26, 0.37)), "-0330", TEH, "Iran"),
    # Zone -0400 (Iranian Hormuz approaches)
    ROT(4291, "S Iran, Hormuz approaches (NP203 429a) Current", dm(26, 35.0), dm(53, 25.0),
        ((77, 0.20), (115, 0.07), (255, 0.31), (224, 0.01)),
        ((237, 0.35), (275, 0.13), (2, 0.52), (331, 0.02)), "-0400", DUB, "Iran"),
    # Singapore Strait  -  Zone -0800
    R(470, "Singapore Strait (NP203 470) Current", dm(1, 14.0), dm(103, 19.0), 300, 120,
      (130, 0.57), (180, 0.17), (244, 0.21), (98, 0.27), "-0800", SIN, "Singapore", z0=0.08),
    ROT(471, "Singapore Strait (NP203 471) Current", dm(1, 8.2), dm(103, 36.6),
        ((179, 0.49), (210, 0.09), (270, 0.34), (181, 0.26)),
        ((357, 0.33), (49, 0.20), (235, 0.13), (229, 0.29)), "-0800", SIN, "Singapore",
        z0n=0.23, z0e=0.03),
    ROT(4711, "Singapore Strait (NP203 471a) Current", dm(1, 7.3), dm(103, 43.0),
        ((126, 0.35), (193, 0.13), (224, 0.26), (133, 0.26)),
        ((24, 0.18), (49, 0.17), (285, 0.13), (218, 0.28)), "-0800", SIN, "Singapore",
        z0n=-0.14, z0e=-0.29),
    # Zone -0700 (Riau side)
    R(4712, "Singapore Strait, Riau (NP203 471b) Current", dm(1, 0.0), dm(103, 34.0), 158, 338,
      (328, 1.05), (21, 0.39), (55, 0.53), (320, 0.46), "-0700", JKT, "Indonesia"),
    # Zone -0800
    R(472, "Singapore Strait (NP203 472) Current", dm(1, 5.7), dm(103, 43.8), 206, 26,
      (308, 0.70), (341, 0.21), (73, 1.10), (22, 0.88), "-0800", SIN, "Singapore"),
    R(4721, "Singapore Strait (NP203 472a) Current", dm(1, 14.0), dm(103, 48.9), 125, 305,
      (77, 0.46), (95, 0.25), (262, 0.85), (211, 0.81), "-0800", SIN, "Singapore"),
    R(4722, "Singapore Strait (NP203 472b) Current", dm(1, 9.9), dm(103, 48.0), 65, 245,
      (100, 0.35), (100, 0.18), (258, 0.57), (212, 0.62), "-0800", SIN, "Singapore", z0=-0.25),
    ROT(4724, "Singapore Strait (NP203 472d) Current", dm(1, 15.0), dm(103, 49.2),
        ((222, 0.18), (263, 0.09), (62, 0.28), (10, 0.25)),
        ((40, 0.31), (84, 0.22), (240, 0.36), (198, 0.44)), "-0800", SIN, "Singapore",
        z0n=0.06, z0e=-0.11),
    ROT(4725, "Singapore Strait (NP203 472e) Current", dm(1, 14.6), dm(103, 51.0),
        ((43, 0.26), (89, 0.16), (231, 0.32), (181, 0.27)),
        ((33, 0.37), (86, 0.24), (242, 0.47), (187, 0.41)), "-0800", SIN, "Singapore",
        z0n=0.01, z0e=0.10),
    ROT(4726, "Singapore Strait (NP203 472f) Current", dm(1, 14.4), dm(103, 55.0),
        ((91, 0.26), (119, 0.12), (263, 0.40), (213, 0.43)),
        ((87, 0.39), (114, 0.19), (256, 0.62), (206, 0.64)), "-0800", SIN, "Singapore",
        z0n=-0.04, z0e=-0.11),
    R(473, "Singapore Strait E (NP203 473) Current", dm(1, 17.4), dm(104, 9.8), 258, 78,
      (256, 0.81), (302, 0.32), (76, 0.79), (31, 0.74), "-0800", SIN, "Singapore", z0=0.02),
    R(4731, "Singapore Strait (NP203 473a) Current", dm(1, 12.9), dm(103, 57.2), 85, 265,
      (65, 0.68), (99, 0.35), (241, 0.80), (202, 0.75), "-0800", SIN, "Singapore", z0=-0.55),
    R(4732, "Singapore Strait (NP203 473b) Current", dm(1, 11.7), dm(103, 52.6), 238, 58,
      (263, 1.09), (289, 0.43), (77, 1.67), (31, 1.63), "-0800", SIN, "Singapore"),
    R(4733, "Singapore Strait E (NP203 473c) Current", dm(1, 20.0), dm(104, 20.0), 56, 236,
      (79, 1.09), (121, 0.43), (254, 0.89), (196, 0.72), "-0800", SIN, "Singapore"),
    # Zone -0700 (Riau Archipelago)
    R(4734, "Riau Archipelago (NP203 473d) Current", dm(1, 0.0), dm(104, 12.0), 0, 180,
      (120, 1.15), (183, 0.37), (216, 1.60), (145, 1.01), "-0700", JKT, "Indonesia"),
    R(474, "Riau Archipelago (NP203 474) Current", dm(0, 37.0), dm(104, 25.0), 60, 240,
      (126, 0.51), (182, 0.18), (264, 0.82), (195, 0.56), "-0700", JKT, "Indonesia"),
    R(4741, "Riau Archipelago (NP203 474a) Current", dm(0, 48.0), dm(104, 37.3), 100, 280,
      (32, 0.64), (78, 0.25), (202, 0.46), (145, 0.35), "-0700", JKT, "Indonesia"),

    # ===== PDF 179  -  Indonesia / Malaysia / Philippines / Borneo / Irian Jaya =====
    # Zone -0700, Suedhalbkugel (S)
    R(475, "Karimata approaches (NP203 475) Current", -dm(0, 17.0), dm(105, 10.0), 22, 202,
      (182, 0.30), (275, 0.10), (250, 1.96), (183, 1.57), "-0700", JKT, "Indonesia"),
    R(4751, "Berhala Strait (NP203 475a) Current", -dm(0, 52.0), dm(104, 22.0), 293, 113,
      (321, 0.90), (7, 0.26), (124, 0.55), (56, 0.41), "-0700", JKT, "Indonesia"),
    R(476, "Berhala Strait (NP203 476) Current", -dm(0, 40.0), dm(103, 42.0), 0, 180,
      (174, 1.46), (237, 0.56), (232, 0.51), (115, 0.45), "-0700", JKT, "Indonesia"),
    R(485, "Bangka Strait (NP203 485) Current", -dm(1, 24.0), dm(105, 10.0), 45, 225,
      (232, 0.15), (342, 0.07), (257, 0.55), (189, 0.37), "-0700", JKT, "Indonesia"),
    R(4851, "Bangka Strait (NP203 485a) Current", -dm(2, 13.0), dm(105, 15.0), 113, 293,
      (86, 0.43), (279, 0.05), (82, 0.43), (41, 0.40), "-0700", JKT, "Indonesia"),
    R(4852, "Gaspar Strait (NP203 485b) Current", -dm(2, 53.0), dm(106, 0.0), 135, 315,
      (270, 0.51), (300, 0.20), (226, 0.14), (147, 0.50), "-0700", JKT, "Indonesia"),
    # Zone -0800
    R(490, "E Malaysia coast (NP203 490) Current", dm(3, 57.2), dm(103, 27.5), 30, 210,
      (15, 0.27), (101, 0.07), (194, 0.22), (118, 0.14), "-0800", KUL, "Malaysia"),
    R(496, "Philippine Islands (NP203 496) Current", dm(10, 41.0), dm(122, 35.0), 45, 220,
      (243, 1.54), (300, 0.87), (241, 0.37), (204, 0.34), "-0800", MNL, "Philippines"),
    R(497, "Philippine Islands (NP203 497) Current", dm(10, 17.0), dm(123, 54.0), 80, 250,
      (219, 0.71), (279, 0.47), (266, 0.10), (209, 0.12), "-0800", MNL, "Philippines"),
    R(503, "San Bernardino Strait (NP203 503) Current", dm(12, 30.0), dm(124, 7.0), 225, 45,
      (232, 3.05), (257, 1.42), (223, 1.78), (184, 1.38), "-0800", MNL, "Philippines", z0=1.16),
    R(504, "Philippine Islands (NP203 504) Current", dm(11, 16.0), dm(125, 0.0), 290, 115,
      (209, 0.39), (164, 0.35), (219, 0.39), (164, 0.30), "-0800", MNL, "Philippines"),
    R(5041, "Philippine Islands (NP203 504a) Current", dm(11, 22.0), dm(124, 59.0), 80, 255,
      (209, 1.40), (258, 0.75), (205, 0.35), (162, 0.40), "-0800", MNL, "Philippines"),
    R(506, "Basilan Strait (NP203 506) Current", dm(6, 54.0), dm(122, 4.0), 270, 90,
      (221, 2.46), (267, 1.35), (215, 0.92), (185, 0.80), "-0800", MNL, "Philippines", z0=-0.50),
    R(511, "Off Borneo (NP203 511) Current", dm(5, 49.9), dm(118, 7.2), 60, 240,
      (41, 0.66), (101, 0.41), (51, 0.34), (343, 0.32), "-0800", KCH, "Malaysia"),
    ROT(514, "Off Borneo (NP203 514) Current", dm(5, 15.1), dm(115, 8.0),
        ((69, 0.10), (183, 0.06), (21, 0.03), (219, 0.07)),
        ((231, 0.32), (265, 0.14), (232, 0.18), (160, 0.13)), "-0800", KCH, "Malaysia"),
    R(5141, "Off Borneo (NP203 514a) Current", dm(5, 13.6), dm(115, 9.4), 320, 140,
      (37, 0.24), (58, 0.07), (49, 0.08), (14, 0.06), "-0800", KCH, "Malaysia"),
    R(532, "Sulawesi (NP203 532) Current", -dm(1, 26.2), dm(125, 11.5), 90, 270,
      (54, 0.56), (71, 0.35), (278, 0.49), (160, 0.18), "-0800", MKS, "Indonesia"),
    R(5321, "Sulawesi (NP203 532a) Current", -dm(1, 48.0), dm(125, 20.0), 0, 180,
      (36, 4.70), (99, 1.40), (27, 1.70), (0, 1.60), "-0800", MKS, "Indonesia"),
    # Zone -0700
    R(535, "Sunda Strait (NP203 535) Current", -dm(5, 58.0), dm(105, 55.0), 35, 215,
      (275, 0.50), None, (11, 1.10), (351, 0.60), "-0700", JKT, "Indonesia"),
    R(537, "Madura Strait (NP203 537) Current", -dm(7, 6.0), dm(112, 40.0), 0, 180,
      (14, 1.82), (11, 0.62), (235, 0.35), (33, 0.08), "-0700", JKT, "Indonesia", z0=0.15),
    # Zone -0800  -  Lombok (saisonaler Z0 'v' -> Jahresmittel ~0, Throughflow)
    R(538, "Lombok Strait (NP203 538) Current", -dm(8, 45.0), dm(115, 45.0), 0, 180,
      (357, 1.6), (16, 1.4), (192, 1.4), (180, 0.6), "-0800", MKS, "Indonesia"),
    # Zone -0900  -  Irian Jaya
    R(550, "Irian Jaya (NP203 550) Current", -dm(1, 24.0), dm(130, 58.0), 45, 225,
      (84, 1.22), (137, 0.43), (30, 0.63), (350, 0.40), "-0900", JAY, "Indonesia", z0=0.15),
    R(551, "Irian Jaya (NP203 551) Current", -dm(2, 13.6), dm(133, 38.6), 70, 250,
      (116, 1.22), (204, 0.47), (254, 0.17), (226, 0.15), "-0900", JAY, "Indonesia"),
]

# Saisonale Z0-Anmerkung fuer Lombok 538 (kann XTide nicht modellieren)
SEASONAL_NOTE = {538: "Z0 stark saisonal (Throughflow): Jan +1.7 .. Jul -2.1 .. Dez +0.5 kn; "
                      "hier Jahresmittel ~0 angesetzt"}


def phasor(H, g_deg):
    return H * cmath.exp(-1j * math.radians(g_deg))


def from_phasor(P):
    return abs(P), (-math.degrees(cmath.phase(P))) % 360.0


def project_rotary(n, e):
    """N/E -> 1D entlang M2-Hauptachse. -> (flood_compass, {c:(g,H)}, ellipticity)."""
    gN, HN = n["M2"]; gE, HE = e["M2"]
    Ux = phasor(HE, gE); Uy = phasor(HN, gN)
    Wp = (Ux + 1j * Uy) / 2.0
    Wm = (Ux.conjugate() + 1j * Uy.conjugate()) / 2.0
    semi_major = abs(Wp) + abs(Wm)
    ellipticity = (abs(Wp) - abs(Wm)) / semi_major if semi_major else 0.0
    theta = (cmath.phase(Wp) + cmath.phase(Wm)) / 2.0
    D0 = (90.0 - math.degrees(theta)) % 360.0
    sinD = math.sin(math.radians(D0)); cosD = math.cos(math.radians(D0))
    out = {}
    for c in list(n.keys()) + [c for c in e if c not in n]:
        gNc, HNc = n.get(c, (0.0, 0.0)); gEc, HEc = e.get(c, (0.0, 0.0))
        H, g = from_phasor(phasor(HEc, gEc) * sinD + phasor(HNc, gNc) * cosD)
        out[c] = (g, H)
    return D0, out, ellipticity


def load_header_and_order():
    with open(HEADER_SRC, encoding="iso-8859-1") as f:
        lines = f.readlines()
    cut = next(i for i, l in enumerate(lines)
               if l.startswith("# UTide harmonic analysis") or "BEGIN HOT COMMENTS" in l)
    header = lines[:cut]
    order, in_speeds = [], False
    for l in lines:
        if l.startswith("# Constituent speeds"):
            in_speeds = True; continue
        if in_speeds:
            if l.startswith("#") or not l.strip():
                continue
            m = re.match(r"^(\S+)\s+[\d.]+\s*$", l)
            if m:
                order.append(m.group(1))
                if len(order) == 175:
                    break
    assert len(order) == 175, f"erwartet 175, gefunden {len(order)}"
    return header, order


def station_block(st, order, diag):
    ref = re.search(r"\(NP203 (\w+)\)", st["name"]).group(1)
    out = []
    a = out.append
    a(f"# country: {st['country']}\n")
    a(f"# source: {SOURCE}\n")
    a(f"# station_type: current\n")
    a(f"# np203_no: {ref}\n")
    a(f"# np203_zone: {st['zone']}\n")
    a(f"# stream_type: {st['type']}\n")
    if st["type"] == "reversing":
        a(f"# flood_dir: {st['flood']:03d}\n")
        a(f"# ebb_dir: {st['ebb']:03d}\n")
        const = st["const"]; datum = st["z0"]
    else:
        flood, const, ell = project_rotary(st["n"], st["e"])
        D0 = math.radians(flood)
        datum = st["z0e"] * math.sin(D0) + st["z0n"] * math.cos(D0)  # Reststrom-Vektor projiziert
        a(f"# flood_dir: {round(flood):03d}\n")
        a(f"# ebb_dir: {round((flood + 180) % 360):03d}\n")
        a(f"# ellipticity_m2: {ell:+.3f}\n")
        if abs(ell) > 0.25:
            a("# rotary_caveat: strongly rotary (|e|>0.25) - 1D major-axis "
              "underrepresents speed and shows false slacks\n")
        diag.append((st["name"], ell, flood))
    if st["no"] in SEASONAL_NOTE:
        a(f"# seasonal_note: {SEASONAL_NOTE[st['no']]}\n")
    a(f"# datum: Z0 residual current (knots)\n")
    a(f"# !units: knots\n")
    a(f"# !longitude: {st['lon']:.6f}\n")
    a(f"# !latitude: {st['lat']:.6f}\n")
    a(f"{st['name']}\n")
    a(f"{st['meridian']} :{st['tzfile']}\n")
    a(f"{datum:.4f} knots\n")
    for c in order:
        if c in const:
            g, H = const[c]
            a(f"{c:<12} {H:.4f}  {g:.2f}\n")
        else:
            a(f"{c:<12} x 0 0\n")
    return out


def main():
    header, order = load_header_and_order()
    out = list(header)
    diag = []
    for st in STATIONS:
        out.extend(station_block(st, order, diag))
    with open(OUT, "w", encoding="iso-8859-1") as f:
        f.writelines(out)
    rev = sum(1 for s in STATIONS if s["type"] == "reversing")
    print(f"geschrieben: {OUT}  ({len(STATIONS)} Stationen: {rev} reversing, "
          f"{len(STATIONS) - rev} rotary)")
    strong = [(n, e) for n, e, _ in diag if abs(e) > 0.25]
    print(f"stark rotierend (|e|>0.25): {len(strong)}")
    for n, e in sorted(strong, key=lambda x: -abs(x[1])):
        print(f"   {e:+.3f}  {n}")
    if os.path.exists(TCD):
        os.unlink(TCD)
    subprocess.run(["build_tide_db", TCD, OUT], check=True,
                   stdout=subprocess.DEVNULL)
    print(f"TCD: {TCD}")


if __name__ == "__main__":
    main()
