#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""M4/M6 aus den ATT-S.W.-Corrections berichtigen (7.11.2026).

Die Druckwerte f4/F4, f6/F6 sind FAKTOREN: H4 = F4*H_M2^2, g4 = 2*g_M2 + f4,
H6 = F6*H_M2^3, g6 = 3*g_M2 + f6 (py/build_np208.py swcorr, Bugfix 02.07.2026).
build_np203_scs.py (03.08.), build_np203_scs_transfer.py und build_np208_currents.py
haben sie dennoch direkt als Amplitude/Phase eingetragen.

Berichtigt wird an Ort und Stelle (Dateien sind seitdem von Hand bearbeitet):
  1. harmonics_att_np203_scs.txt: Saetze, deren M4/M6 noch genau (F4, f4) bzw. (F6, f6)
     traegt (FES-ergaenzte M4 bleiben unberuehrt).
  2. harmonics_att_np203_scs_secondary.txt: Uebertragungen (linear: Amplitude x f_semi^k,
     Phase + k*w*dt) -> neu = alt * Hrichtig/Hfalsch, Phase + (grichtig - gfalsch);
     nur wenn der alte Wert genau zur alten Formel passt.
  3. harmonics_att_np208_currents.txt: Messina N/S (M4 = (0.021, 184)).

Usage: venv/bin/python py/fix_att_m4_faktor.py [--schreiben]
"""
import os
import re
import shutil
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ATT = os.path.join(ROOT, 'harmonics/att')
TSV = os.path.join(ROOT, 'harmonics/help/np203_2002_part3_scs.tsv')
SPEED = {'M4': 57.9682084, 'M6': 86.9523127}
K = {'M4': 2, 'M6': 3}


def tsv():
    out = {}
    for l in open(TSV, encoding='utf-8'):
        if l.startswith('#') or not l.strip():
            continue
        r = l.rstrip('\n').split('\t')
        if r[4] == '-' or r[5] in ('-', ''):
            continue
        H, g = float(r[5]), float(r[4])
        sw = {}
        for k, gi, hi in (('M4', 12, 13), ('M6', 14, 15)):
            if len(r) > hi and r[gi] not in ('-', ''):
                sw[k] = (float(r[hi]), float(r[gi]))     # (F, f) = so steht es falsch im Bestand
        if sw:
            out[r[0]] = (H, g, sw)
    return out


def richtig(H, g, k, F, f):
    return F * H ** K[k], (K[k] * g + f) % 360


def bloecke(L):
    """[(start, ende, name_index)] je Satz: Hot-Comment-Block bis zur naechsten Leer-/BEGIN-Zeile."""
    out, i = [], 0
    while i < len(L):
        if L[i].startswith('# BEGIN HOT COMMENTS'):
            j = i + 1
            while j < len(L) and L[j].startswith('#'):
                j += 1
            k = j + 3
            while k < len(L) and L[k].strip() and not L[k].startswith('#'):
                k += 1
            out.append((i, k, j))
            i = k
        else:
            i += 1
    return out


def hot(L, a, b, key):
    for l in L[a:b]:
        m = re.match(r'#\s*' + re.escape(key) + r':\s*(.*)$', l)
        if m:
            return m.group(1).strip()
    return None


ZEILE = re.compile(r'^(\S+\s+)(\d+\.\d+)(\s+)(\d+\.\d+)\s*$')


def ersetzen(L, a, b, k, H, g):
    for i in range(a, b):
        m = ZEILE.match(L[i])
        if m and L[i].split()[0] == k:
            L[i] = f'{m.group(1)}{H:.4f}{m.group(3)}{g:.2f}\n'
            return True
    return False


def wert(L, a, b, k):
    for i in range(a, b):
        m = ZEILE.match(L[i])
        if m and L[i].split()[0] == k:
            return float(m.group(2)), float(m.group(4))
    return None


NOTIZ = '# note: 20261107 {k} berichtigt: S.W.-Correction ist Faktor (H=F*H_M2^n, g=n*g_M2+f), war als Amplitude eingetragen\n'


def notiz(L, j, ks):
    L.insert(j, NOTIZ.format(k='/'.join(ks)))


def standard(T, schreiben):
    p = os.path.join(ATT, 'harmonics_att_np203_scs.txt')
    L = open(p, encoding='iso-8859-1').readlines()
    korr = {}                       # att -> {k: (Hfalsch, gfalsch, Hrichtig, grichtig)}
    for a, b, j in reversed(bloecke(L)):
        att = hot(L, a, j, 'att_number')
        if att not in T:
            continue
        H, g, sw = T[att]
        ks = []
        for k, (F, f) in sw.items():
            alt = wert(L, j, b, k)
            Hr, gr = richtig(H, g, k, F, f)
            korr.setdefault(att, {})[k] = (F, f, Hr, gr)
            if alt and abs(alt[0] - F) < 6e-5 and abs(alt[1] - f) < 0.006:
                ersetzen(L, j, b, k, Hr, gr); ks.append(k)
            elif alt:
                print(f'  {att} {k}: Bestand {alt} != Druck ({F}, {f}) -> unberuehrt (FES/Hand?)')
        if ks:
            notiz(L, j, ks)
            print(f'  {att:6} {L[j + 1].strip()[:45]:45} ' + '  '.join(
                f'{k} {sw[k][0]:.4f}/{sw[k][1]:.0f} -> {korr[att][k][2]:.4f}/{korr[att][k][3]:.0f}' for k in ks))
    n = sum(1 for l in L if l.startswith('# note: 20261107'))
    print(f'Standard: {n} Saetze berichtigt')
    if schreiben:
        sichern_schreiben(p, L)
    return korr


def nebenhaefen(T, schreiben):
    # Bezug aus dem Buch (TSV), auch wenn der Bezugshafen inzwischen ersetzt/archiviert ist
    korr = {att: {k: (F, f, *richtig(H, g, k, F, f)) for k, (F, f) in sw.items()}
            for att, (H, g, sw) in T.items()}
    p = os.path.join(ATT, 'harmonics_att_np203_scs_secondary.txt')
    L = open(p, encoding='iso-8859-1').readlines()
    n = 0
    for a, b, j in reversed(bloecke(L)):
        text = ''.join(L[a:j])
        m = re.search(r'Bezugshafen (\w+)', text)
        f = re.search(r'f_semi=([\d.]+).*?dt=([+-]?\d+)min', text)
        if not m or m.group(1) not in korr or not f:
            continue
        ref, fs, dt = m.group(1), float(f.group(1)), int(f.group(2)) / 60.0
        ks = []
        for k, (F, f0, Hr, gr) in korr[ref].items():
            alt = wert(L, j, b, k)
            if not alt:
                continue
            erw = (F * fs ** K[k], (f0 + SPEED[k] * dt) % 360)
            if abs((alt[1] - erw[1] + 180) % 360 - 180) < 1.5:
                ersetzen(L, j, b, k, alt[0] * Hr / F, (alt[1] + gr - f0) % 360); ks.append(k)
            else:
                print(f'  Neben {L[j].strip()[:40]} {k}: {alt} passt nicht zu {erw} -> unberuehrt')
        if ks:
            notiz(L, j, ks); n += 1
    print(f'Nebenhaefen: {n} Saetze berichtigt')
    if schreiben:
        sichern_schreiben(p, L)


def messina(schreiben):
    p = os.path.join(ATT, 'harmonics_att_np208_currents.txt')
    L = open(p, encoding='iso-8859-1').readlines()
    n = 0
    for a, b, j in reversed(bloecke(L)):
        if not L[j].startswith('Stretto di Messina'):
            continue
        m2 = wert(L, j, b, 'M2'); alt = wert(L, j, b, 'M4')
        if alt and abs(alt[0] - 0.021) < 1e-6 and abs(alt[1] - 184) < 0.01:
            Hr, gr = richtig(m2[0], m2[1], 'M4', 0.021, 184)
            ersetzen(L, j, b, 'M4', Hr, gr); notiz(L, j, ['M4']); n += 1
            print(f'  {L[j + 1].strip()}: M4 0.0210/184 -> {Hr:.4f}/{gr:.0f}')
    print(f'NP208-Stroeme: {n} Saetze berichtigt')
    if schreiben:
        sichern_schreiben(p, L)


def sichern_schreiben(p, L):
    ziel = os.path.join(ROOT, 'harmonics/backup', os.path.basename(p) + time.strftime('.vor_m4faktor_%Y%m%d'))
    shutil.copy(p, ziel)
    open(p, 'w', encoding='iso-8859-1').writelines(L)
    print(f'  geschrieben: {p} (Sicherung {ziel})')


def main(argv):
    s = '--schreiben' in argv
    T = tsv()
    standard(T, s)
    nebenhaefen(T, s)
    messina(s)


if __name__ == '__main__':
    main(sys.argv[1:])
