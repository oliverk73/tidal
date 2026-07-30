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
# ATT NP203 Part II S.224, am 20260730 aus dem Scan gelesen.
# att: (Name im Buch, lat, lon, tMHW, tMLW, (dMHWS,dMHWN,dMLWN,dMLWS), ML)
# Zeiten in Minuten, None = Kreis-Symbol (no data). Suedbreite negativ.
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

BUCH = {224: S224}

# Nummern, die es im Buch nicht gibt -- Duplikate ihres Nachbarn.
PHANTOM = {
    '3866': 'Kopie von 3868 Nosy Mitsio (Name, Position und Z0 identisch); S.224 kennt keine 3866',
    '3885': 'Kopie von 3884 Nosy Makamby (Name, Position und Z0 identisch); S.224 kennt keine 3885',
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


def transfer(ref_con, pegel, h, t):
    """Skalierung gegen die PUBLIZIERTEN Pegel des Bezugshafens."""
    MHWS, MHWN, MLWN, MLWS = pegel
    SR, NR = MHWS - MLWS, MHWN - MLWN
    dMHWS, dMHWN, dMLWN, dMLWS = h
    if dMHWS is None:
        return None
    if dMLWS is None:
        dMLWS = 0.0
    if dMHWN is None:
        dMHWN = dMHWS
    if dMLWN is None:
        dMLWN = dMLWS
    SRs = SR + (dMHWS - dMLWS)
    NRs = NR + (dMHWN - dMLWN)
    if SRs <= 0:
        SRs = max(0.10, 0.10 * SR)
    fS = max(.05, min(3., SRs / SR))
    fN = max(.05, min(3., NRs / NR)) if NR > .01 else fS
    fD = .5 * (fS + fN)

    M2, S2 = ref_con.get('M2', (0, 0))[0], ref_con.get('S2', (0, 0))[0]
    if M2 <= 0:
        return None
    su, di = fS * (M2 + S2), fN * (M2 - S2)
    M2n, S2n = max(0, .5 * (su + di)), max(0, .5 * (su - di))
    rM = M2n / M2 if M2 > 0 else fS
    rS = S2n / S2 if S2 > 0 else fS

    v = [x for x in t if x is not None]
    dt = (sum(v) / len(v) / 60.0) if v else 0.0

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
    refs = {**STDD, **SEC}
    ref_by_att = {a: r for a, r in refs.items()}

    todo, geloescht = [], []
    print(f'{"att":7s} {"Station":34s} {"fS alt":>7s} {"fS neu":>7s} {"M2 alt":>7s} {"M2 neu":>7s}  Bezug')
    print('-' * 104)

    for seite, rows in sorted(BUCH.items()):
        for att, (bname, lat, lon, tH, tL, h, ml) in sorted(rows.items(), key=lambda x: key(x[0])):
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
            tr = transfer(r['con'], g['pegel'], h, (tH, tL))
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
