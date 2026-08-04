#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""NP203 Ausgabe 2002, Part-II-Transfers des suedchinesischen Gebiets.

Leitet die Sekundaerhaefen ab, die in Part III KEINE eigenen Konstanten haben.
Quelle: harmonics/help/np203_2002_part2_scs_transfer.tsv (alle 29 Part-II-Seiten
einzeln vom Scan gelesen, PDF 117-145 = Buch 281-309).

ZWEI HOEHENREGIME, nicht drei
-----------------------------
Die TSV kennt drei Typen S/D/M, aber M und D unterscheiden sich nur in der
Beschriftung der beiden ZEITspalten (M: "MHW/LLW", D: "HHW/LLW"). Die
Hoehenspalten sind bei beiden MHHW/MLHW/MHLW/MLLW, und beide Zeitdifferenzen
werden ohnehin zu einer mittleren Verzoegerung gemittelt. Fuer die Rechnung
zaehlt also nur, welche vier Hoehen gemeint sind:

  S  -> MHWS MHWN MLWN MLWS   (Spring/Nipp, wie im uebrigen NP203)
  D/M -> MHHW MLHW MHLW MLLW  (hoehere/niedrigere Hoch- und Niedrigwasser)

Regime S: wie py/rebuild_np203_transfer.py -- Spring- und Nippfaktor gegen die
publizierten Pegel des Bezugshafens, daraus M2 und S2 getrennt.

Regime D/M: die vier Pegel zerlegen sich bei gemischter Tide als
    MHHW = Z + H + D      MLHW = Z + H - D
    MHLW = Z - H + D      MLLW = Z - H - D
mit H = halbtaegigem und D = ganztaegigem Anteil. Daraus unmittelbar
    A = MHHW - MLLW = 2H + 2D        B = MLHW - MHLW = 2H - 2D
    H = (A + B) / 4                  D = (A - B) / 4
Der Transfer bildet A und B am Bezugshafen und am Sekundaerhafen und skaliert
die halbtaegigen Konstituenten mit H'/H, die ganztaegigen mit D'/D.

Faellt B weg -- das Buch druckt in den Spalten MLHW/MHLW ein Dreieck ("Tide is
usually diurnal") oder einen Kreis (No data) -- ist die Zerlegung nicht bildbar.
Dann bleibt ein EINZIGER Faktor A'/A fuer alles. Das ist kein Notbehelf: bei
rein ganztaegiger Tide ist B = 0, und dann liefert die Zerlegung ohnehin
H'/H = D'/D = A'/A. Betrifft 5111, 4990, 7000, 7002 und 6917.

Anders als bei Regime S laesst sich hier M2 und S2 nicht trennen -- Spring und
Nipp stehen in diesen Spalten nicht. Beide bekommen denselben Faktor. Das ist
die Grenze der Quelle, nicht der Rechnung.

Zonenversatz: die Zeitdifferenzen des Buches enthalten den Zonensprung. Fuer die
Phasen wird er wieder herausgerechnet, dt_UT = dt_Buch + (Zone_Bezug - Zone_Sek).

Aufruf: venv/bin/python py/build_np203_scs_transfer.py [--write]
"""
from __future__ import annotations
import os
import re
import sys

HARM = '/home/oliver/weather/harmonics'
LIT = f'{HARM}/classic/harmonics_literature.txt'
P3 = f'{HARM}/help/np203_2002_part3_scs.tsv'
P2POS = f'{HARM}/help/np203_2002_part2_scs_pos.tsv'
TRANS = f'{HARM}/help/np203_2002_part2_scs_transfer.tsv'
OUT = f'{HARM}/att/harmonics_att_np203_scs_secondary.txt'

SPEED = {
    'M2': 28.9841042, 'S2': 30.0, 'N2': 28.4397295, 'K2': 30.0821373,
    'K1': 15.0410686, 'O1': 13.9430356, 'M4': 57.9682084, 'M6': 86.9523127,
}
SEMI = {'M2', 'S2', 'N2', 'K2'}
DIUR = {'K1', 'O1'}
SHALLOW = {'M4': 2, 'M6': 3}

# Publizierte Pegel der Bezugshaefen aus den Gruppenkoepfen von Part II.
# Reihenfolge S: MHWS MHWN MLWN MLWS -- D/M: MHHW MLHW MHLW MLLW.
# None = im Buch ein Dreieck (Tide is usually diurnal).
BEZUG = {
    '4496': ('S', (2.8, 2.1, 1.2, 0.6)),   # Pussur River Entrance
    '4512': ('S', (4.4, 3.2, 1.5, 0.7)),   # Chittagong
    '4539': ('S', (2.4, 1.8, 1.1, 0.4)),   # Bassein River Entrance
    '4547': ('S', (6.6, 4.9, 2.5, 0.8)),   # Elephant Point
    '4574': ('S', (5.4, 3.6, 2.0, 0.1)),   # Mergui
    '4663': ('S', (2.5, 1.8, 1.3, 0.6)),   # Pinang
    '4686': ('S', (5.3, 3.9, 2.5, 1.1)),   # Pelabuhan Klang
    '4704': ('S', (2.7, 1.9, 1.1, 0.3)),   # Kuala Batu Pahat
    '4718': ('S', (2.8, 2.2, 1.2, 0.5)),   # Singapore
    '5032': ('S', (1.5, 1.0, 0.4, 0.0)),   # Legaspi
    '4738': ('D', (2.2, 2.1, 1.3, 0.6)),   # Horsburgh Lighthouse
    '4901': ('D', (2.1, 1.5, 1.5, 0.8)),   # Chendering
    '4987': ('D', (1.0, 0.5, 0.3, 0.0)),   # Manila
    '5115': ('D', (1.9, 1.2, 0.9, 0.4)),   # Sandakan
    '5137': ('D', (2.1, 1.6, 1.5, 0.8)),   # Labuan
    '5147': ('D', (1.6, None, None, 0.7)),  # Miri
    '6996': ('D', (2.9, None, None, 0.9)),  # Cua Cam
    '5172': ('M', (4.6, 4.4, 2.3, 1.2)),   # Sungai Sarawak (Pulau Lakei)
    '6938': ('M', (3.5, 3.3, 2.2, 0.9)),   # Mui Vung Tau
}

# Stationen mit belegtem Widerspruch gegen unabhaengige Messungen.
WARNUNG = {
    '4911': ['4911 Geting weicht in der M2-Phase um 92 Grad von einer gemessenen',
             'TICON4-Station 1.6 km entfernt ab (py/check_np203_scs_transfer_extern.py).',
             'Das bestaetigt die "t"-Markierung des Buches: die Zeitdifferenz',
             '+0350/+0340 passt nicht zu Tumpat 8 km weiter mit +0026/+0013.',
             'Fuer Navigation unbrauchbar, nur als Buchwiedergabe zu verstehen.'],
}

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_np203_scs import kopf, tsv, land_zone, inferenz  # noqa: E402


def zahl(s):
    """'+0.3' -> 0.3 ; '-' (No data) -> None ; '~' (Dreieck) -> None."""
    return None if s in ('-', '~') else float(s)


def minuten(s):
    """'+0235' -> 155 Minuten ; '-0059' -> -59 ; '-' -> None."""
    if s == '-':
        return None
    m = re.match(r'^([+-])(\d{2})(\d{2})$', s)
    if not m:
        raise ValueError(s)
    v = int(m.group(2)) * 60 + int(m.group(3))
    return -v if m.group(1) == '-' else v


def ref_konstanten():
    """Konstituenten der Bezugshaefen -- genau wie build_np203_scs sie bildet."""
    out = {}
    for r in tsv(P3):
        att = r[0]
        if att not in BEZUG:
            continue
        con = {}
        for k, gi, hi in (('M2', 4, 5), ('S2', 6, 7), ('K1', 8, 9), ('O1', 10, 11)):
            if r[gi] != '-' and float(r[hi]) > 0:
                con[k] = (float(r[hi]), float(r[gi]))
        for k, gi, hi in (('M4', 12, 13), ('M6', 14, 15)):
            if r[gi] != '-':
                con[k] = (float(r[hi]), float(r[gi]))
        if 'M2' in con and 'S2' in con:
            con['N2'], con['K2'] = inferenz(con['M2'], con['S2'])
        out[att] = (con, r[2])          # r[2] = Buchzone des Bezugshafens
    return out


def faktoren_S(pegel, dh):
    """Spring- und Nippfaktor; gibt (f_semi_spring, f_semi_nipp, f_diurn)."""
    MHWS, MHWN, MLWN, MLWS = pegel
    SR, NR = MHWS - MLWS, MHWN - MLWN
    dS = (dh[0] if dh[0] is not None else 0.0) - (dh[3] if dh[3] is not None else 0.0)
    dN = ((dh[1] if dh[1] is not None else dh[0] or 0.0)
          - (dh[2] if dh[2] is not None else dh[3] or 0.0))
    fS = (SR + dS) / SR if SR > .01 else 1.0
    fN = (NR + dN) / NR if NR > .01 else fS
    return fS, fN, .5 * (fS + fN)


def faktoren_D(pegel, dh):
    """Zerlegung in halb- und ganztaegigen Anteil; gibt (f_semi, f_diurn, wie)."""
    MHHW, MLHW, MHLW, MLLW = pegel
    A = MHHW - MLLW
    dA = (dh[0] if dh[0] is not None else 0.0) - (dh[3] if dh[3] is not None else 0.0)
    As = A + dA
    voll = (MLHW is not None and MHLW is not None
            and dh[1] is not None and dh[2] is not None)
    if not voll:
        f = As / A if A > .01 else 1.0
        return f, f, 'einfach (B nicht bildbar)'
    B = MLHW - MHLW
    Bs = B + (dh[1] - dh[2])
    H, D = (A + B) / 4.0, (A - B) / 4.0
    Hs, Ds = (As + Bs) / 4.0, (As - Bs) / 4.0
    f_semi = Hs / H if H > .005 else 1.0
    f_diur = Ds / D if D > .005 else f_semi
    return f_semi, f_diur, 'zerlegt'


def main():
    schreiben = '--write' in sys.argv
    HEADER, ORDER = kopf()
    refs = ref_konstanten()
    pos_p3 = {r[0] for r in tsv(P3)}

    zeilen, bloecke = [], []
    uebersprungen = []
    for r in tsv(TRANS):
        (att, name, ref, zone, typ, lag, lam, ns, log, lom, ew,
         t1, t2, h1, h2, h3, h4, mls, flags) = r
        assert att not in pos_p3, f'{att} hat eigene Konstanten'

        dt1, dt2 = minuten(t1), minuten(t2)
        dh = [zahl(x) for x in (h1, h2, h3, h4)]
        ml = zahl(mls)
        if dt1 is None or dt2 is None or dh[0] is None or dh[3] is None or ml is None:
            uebersprungen.append(att)
            continue
        if ref not in refs:
            uebersprungen.append(att)
            continue

        ref_con, ref_zone = refs[ref]
        regime, pegel = BEZUG[ref]
        if regime == 'S':
            f_semi, f_nipp, f_diur = faktoren_S(pegel, dh)
            wie = 'Spring/Nipp'
        else:
            f_semi, f_diur, wie = faktoren_D(pegel, dh)
            f_nipp = None

        for f in (f_semi, f_diur):
            assert 0.02 < f < 5.0, f'{att}: Faktor {f:.2f} unplausibel'

        # Verzoegerung in Weltzeit
        dz = (-int(ref_zone[:3]) - -int(zone[:3])) + (int(ref_zone[3:]) - int(zone[3:])) / 60.0
        dt = (dt1 + dt2) / 2.0 / 60.0 - dz

        con = {}
        for c, (a, g) in ref_con.items():
            if c in SEMI:
                na = a * f_semi
            elif c in DIUR:
                na = a * f_diur
            elif c in SHALLOW:
                na = a * f_semi ** SHALLOW[c]
            else:
                na = a * f_semi
            con[c] = (round(na, 4), round((g + SPEED.get(c, 0.0) * dt) % 360, 2))
        # Bei Regime S M2/S2 aus Spring und Nipp trennen
        if regime == 'S' and 'M2' in ref_con and 'S2' in ref_con:
            M2, S2 = ref_con['M2'][0], ref_con['S2'][0]
            su, di = f_semi * (M2 + S2), f_nipp * (M2 - S2)
            con['M2'] = (round(max(0, .5 * (su + di)), 4), con['M2'][1])
            con['S2'] = (round(max(0, .5 * (su - di)), 4), con['S2'][1])

        lat = (int(lag) + int(lam) / 60.0) * (-1 if ns == 'S' else 1)
        lon = (int(log) + int(lom) / 60.0) * (-1 if ew == 'W' else 1)
        land, tz = land_zone(att, zone)
        mer = f'{-int(zone[:3]):+03d}:{zone[3:]}'
        # Das Buch markiert unsichere Zeitdifferenzen mit "t". Die Phase haengt
        # allein daran, deshalb solche Stationen niedriger einstufen.
        unsicher = 't' in flags
        conf = 3 if unsicher else 4
        warnung = WARNUNG.get(att)
        b = ['# BEGIN HOT COMMENTS',
             f'# country: {land}',
             '# source: ADMIRALTY Tide Tables Vol.3 (NP203, Ausgabe 2002), Part II Transfer',
             f'# att_number: {att}',
             f'# note: NP203 Part II (2002), Zone {zone}. Kein eigener Konstantensatz im',
             f'# note: Buch -- abgeleitet vom Bezugshafen {ref} ueber die publizierten',
             f'# note: Pegel des Gruppenkopfs. Regime {regime} ({wie}).',
             f'# note: f_semi={f_semi:.3f} f_diurn={f_diur:.3f} dt={dt * 60:+.0f}min',
             '# note: Die Ausgabe 2015 fuehrt dieses Gebiet nicht mehr.']
        if unsicher:
            b.append('# note: ACHTUNG -- das Buch markiert die Zeitdifferenzen dieser'
                     ' Station mit "t" (approximate). Die Phase haengt allein daran.')
        if warnung:
            b += ['# note: ' + z for z in warnung]
        b += [ '# date_imported: 20260804',
             '# datum: Chart Datum (Z0 = mean level above CD)',
             f'# confidence: {conf}',
             '# !units: meters',
             f'# !longitude: {lon:.4f}',
             f'# !latitude: {lat:.4f}',
             f'{name}, {land}' if not name.endswith(land) else name,
             f'{mer} :{tz}',
             f'{ml:.4f} meters']
        for c in ORDER:
            b.append(f'{c:<15s} {con[c][0]:.4f}  {con[c][1]:.2f}' if c in con else 'x 0 0')
        bloecke.append(b)
        zeilen.append((att, name, ref, regime, wie, f_semi, f_diur, dt * 60, con['M2'][0]))

    print(f'{"att":7s} {"Station":32s} {"Bez":5s} {"Reg":3s} {"f_semi":>7s} '
          f'{"f_diur":>7s} {"dt/min":>7s} {"M2":>7s}  Zerlegung')
    for z in zeilen:
        print(f'{z[0]:7s} {z[1][:32]:32s} {z[2]:5s} {z[3]:3s} {z[5]:7.3f} '
              f'{z[6]:7.3f} {z[7]:+7.0f} {z[8]:7.4f}  {z[4]}')
    print(f'\n{len(bloecke)} Transfers gerechnet, {len(uebersprungen)} uebersprungen '
          f'(Buch ohne die noetigen Werte):')
    print('  ' + ' '.join(uebersprungen))

    if schreiben:
        txt = '\n'.join(HEADER) + '\n' + '\n'.join('\n'.join(b) for b in bloecke) + '\n'
        open(OUT, 'w', encoding='iso-8859-1').write(txt)
        os.chmod(OUT, 0o600)
        print(f'\ngeschrieben: {OUT}')
    else:
        print('\n(Probelauf -- mit --write schreiben)')


if __name__ == '__main__':
    main()
