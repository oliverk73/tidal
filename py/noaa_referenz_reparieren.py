#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Baut NOAA-Table-2-Saetze mit korrigierter Referenzstation neu.

Wo mein Parser einen Ueberschriftenwechsel uebersehen hat, haengen ganze
Bloecke an einer falschen Referenz. Die Zahlen der Zeilen -- Tidenhuebe und
Zeitdifferenzen -- sind richtig, nur auf die falsche Station angewandt.

Repariert wird chirurgisch: nur der Konstituentenblock, die Meridianzeile
und Z0 werden ersetzt. Name, Position, Land, Zeitzone und alle Notizen
bleiben stehen, damit Handkorrekturen nicht verlorengehen.

Die Rechnung ist aus build_noaa_cptt.py nachgebaut (das laesst sich hier
nicht importieren, es braucht numpy und timezonefinder). Deshalb prueft
--probe zuerst, ob der Nachbau die unveraenderten Saetze reproduziert.

Usage: python3 py/noaa_referenz_reparieren.py --probe
       python3 py/noaa_referenz_reparieren.py [--schreiben]
       python3 py/noaa_referenz_reparieren.py --alle-zeilen   (nicht benutzen,
              siehe Kommentar in repariere(): die Regel allein taugt nicht)
"""
from __future__ import annotations

import collections
import csv
import datetime as dt
import json
import math
import os
import re
import shutil
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from health_check import km, MERIDIAN, ROOT                        # noqa: E402

# Genau das Muster des Erzeugers. Es beginnt mit [A-Za-z], laesst also
# Konstituenten wie 2N2 und 2Q1 fallen -- wer sie mitnimmt, misst den
# Referenzhub rund 2 % zu gross und bekommt einen entsprechend zu kleinen
# Faktor k.
_CON = re.compile(r'^([A-Za-z][A-Za-z0-9]*)\s+([\-\d.]+)\s+([\-\d.]+)\s*$')

TXT = os.path.join(ROOT, 'harmonics/noaa/harmonics_noaa_cptt.txt')
JSON = os.path.join(ROOT, 'harmonics/help/cptt2018_table2_full.json')
ABGLEICH = os.path.join(ROOT, 'harmonics/help/noaa_referenz_abgleich.csv')
GEPRUEFT = os.path.join(ROOT, 'harmonics/help/noaa_referenz_vorschlag.csv')
BACKUP = os.path.join(ROOT, 'harmonics/backup')

FT = 0.3048
DIURN = {'K1', 'O1', 'P1', 'Q1', 'J1', 'M1', 'OO1', '2Q1', 'SO1', 'RHO1',
         'PHI1', 'PSI1', 'S1', 'SIG1', 'TAU1', 'CHI1', 'THE1', 'BET1', 'UPS1'}
LONGP = {'SA', 'SSA', 'MM', 'MF', 'MSF', 'MSQM', 'MTM', 'MSM', 'SM', 'MS0',
         'MF1', 'NODE', 'Z0'}
CAL = 1.10


def clamp(x, lo, hi):
    return max(lo, min(hi, x))


def latin1(t):
    """Text nach ISO-8859-1 zwingen.

    Die Referenznamen der Tafel enthalten typografische Zeichen -- "Ch'ang
    Chiang Approach" mit U+2019. Ohne Ersetzung bricht das Schreiben mitten
    in der Datei ab.
    """
    for a, b in (('\u2019', "'"), ('\u2018', "'"), ('\u201c', '"'),
                 ('\u201d', '"'), ('\u2013', '-'), ('\u2014', '-')):
        t = t.replace(a, b)
    return unicodedata.normalize('NFC', t).encode('iso-8859-1', 'replace').decode('iso-8859-1')


def kopf(pfad):
    """Reihenfolge und Geschwindigkeiten der Konstituenten aus dem congen-Kopf."""
    ordnung, sp = [], {}
    an = False
    for z in open(pfad, encoding='iso-8859-1'):
        if z.startswith('# Constituent speeds'):
            an = True
            continue
        if an:
            if z.startswith('#'):
                continue
            p = z.split()
            if len(p) != 2:
                break
            try:
                sp[p[0]] = float(p[1])
            except ValueError:
                break
            ordnung.append(p[0])
    return ordnung, sp


# ---- Tidenhuebe messen, knotenfrei, wie im Erzeuger ----
_T = [k * 0.5 for k in range(0, 60 * 24 * 2)]        # 60 Tage, 30-Minuten-Schritt
_DAY = [int(t // 24) for t in _T]


def _perzentil(v, p):
    """Lineare Interpolation wie numpy.percentile."""
    s = sorted(v)
    if len(s) == 1:
        return s[0]
    x = (len(s) - 1) * p / 100.0
    i = int(x)
    return s[i] + (s[min(i + 1, len(s) - 1)] - s[i]) * (x - i)


def messe(items):
    """-> (mittlerer, Spring-, grosser taeglicher Hub) in Metern."""
    h = [0.0] * len(_T)
    for sp, a, g in items:
        w, ph = math.radians(sp), math.radians(g)
        for i, t in enumerate(_T):
            h[i] += a * math.cos(w * t - ph)
    hi = [i for i in range(1, len(h) - 1) if h[i] >= h[i - 1] and h[i] > h[i + 1]]
    lo = [i for i in range(1, len(h) - 1) if h[i] <= h[i - 1] and h[i] < h[i + 1]]
    if len(hi) < 5 or len(lo) < 5:
        return (0.0, 0.0, 0.0)
    HW = [h[i] for i in hi]
    LW = [h[i] for i in lo]
    mean_r = sum(HW) / len(HW) - sum(LW) / len(LW)
    spring_r = _perzentil(HW, 92) - _perzentil(LW, 8)
    dh = collections.defaultdict(list)
    dl = collections.defaultdict(list)
    for i in hi:
        dh[_DAY[i]].append(h[i])
    for i in lo:
        dl[_DAY[i]].append(h[i])
    mhhw = [max(v) for k, v in sorted(dh.items()) if k < 60]
    mllw = [min(v) for k, v in sorted(dl.items()) if k < 60]
    gt = (sum(mhhw) / len(mhhw) - sum(mllw) / len(mllw)) if mhhw and mllw else spring_r
    return (mean_r, spring_r, gt)


def uebertrage(s, con, sp):
    """Konstituenten der Referenz auf die Nebenstation umrechnen."""
    M2r = con.get('M2', (0, 0))[0]
    S2r = con.get('S2', (0, 0))[0]
    if M2r <= 0:
        return None
    Mn, Sr, Gt = messe([(sp[c], a, g) for c, (a, g) in con.items()
                        if c in sp and a > 0])
    mean, spring = s.get('mean_ft'), s.get('spring_ft')
    diu, trop = s.get('diurnal_ft'), s.get('tropic_ft')
    if diu is not None and diu <= 0.05:
        diu = None
    ts = [t for t in (s.get('dtHW'), s.get('dtLW')) if t is not None]
    dt_h = (sum(ts) / len(ts) / 60.0) if ts else 0.0
    if mean is not None and Mn > 0.02:
        k = clamp(CAL * mean * FT / Mn, 0.05, 8.0)
    elif diu is not None and Gt > 0.02:
        k = clamp(CAL * diu * FT / Gt, 0.05, 8.0)
    elif trop is not None and Gt > 0.02:
        k = clamp(CAL * 0.92 * trop * FT / Gt, 0.05, 8.0)
    else:
        return None
    sS = 1.0
    if spring is not None and mean is not None:
        cur, tgt = k * (Sr - Mn), (spring - mean) * FT
        if cur > 0.02 and tgt > 0:
            sS = clamp(tgt / cur, 0.1, 6.0)
    sD = 1.0
    if diu is not None and mean is not None and Gt > Mn:
        cur, tgt = k * (Gt - Mn), (diu - mean) * FT
        if cur > 0.02 and tgt > 0:
            sD = clamp(tgt / cur, 0.1, 6.0)
    out = {}
    for c, (a, g) in con.items():
        if a <= 0:
            continue
        if c in ('S2', 'K2'):
            na = a * k * sS
        elif c in DIURN:
            na = a * k * sD
        elif c in LONGP:
            na = a
        else:
            na = a * k
        v = sp.get(c)
        out[c] = (round(na, 4), round((g + (v * dt_h if v else 0)) % 360, 2))
    K1r = con.get('K1', (0, 0))[0]
    O1r = con.get('O1', (0, 0))[0]
    return dict(con=out, k=k, sS=sS, sD=sD, dt=dt_h,
                M2=M2r * k, S2=S2r * k * sS,
                refF=(K1r + O1r) / (M2r + S2r + 1e-9))


def konfidenz(tr, s):
    c = 5
    if tr['k'] > 2.0 or tr['k'] < 0.4:
        c = 4
    if abs(tr['dt']) > 1.5:
        c = min(c, 4)
    if s.get('mtl_ft') is None:
        c = min(c, 4)
    if s.get('spring_ft') is None and s.get('diurnal_ft') is None:
        c = min(c, 4)
    if tr['M2'] < 0.30 and tr['refF'] < 1.0:
        c = min(c, 3)
    return c


def quellen():
    """Dateien, aus denen der Erzeuger seine Referenzstationen nimmt."""
    aus = []
    for u in ('classic', 'ticon', 'att', 'utide'):
        d = os.path.join(ROOT, 'harmonics', u)
        if os.path.isdir(d):
            aus += [os.path.join(d, n) for n in sorted(os.listdir(d))
                    if n.endswith('.txt') and 'noaa_cptt' not in n]
    return aus


def bloecke(pfad):
    """-> [(Name, {'con':..., 'mer':..., 'lat':..., 'lon':...})]"""
    l = open(pfad, encoding='iso-8859-1').read().split('\n')
    aus, lat, lon, units = [], None, None, None
    for k, z in enumerate(l):
        if z.startswith('# !latitude:'):
            lat = float(z.split(':', 1)[1])
        elif z.startswith('# !longitude:'):
            lon = float(z.split(':', 1)[1])
        elif z.startswith('# !units:'):
            units = z.split(':', 1)[1].strip()
        elif z and not z.startswith('#') and k + 1 < len(l) and MERIDIAN.match(l[k + 1]):
            # Bewusst keine Fuss-Umrechnung: der Erzeuger nimmt die Werte roh,
            # und der Faktor k wird aus derselben Konstituentenmenge bestimmt.
            # Mit Umrechnung nur an einer Stelle waere die Rechnung inkonsistent.
            con, j = {}, k + 3
            while j < len(l) and l[j].strip() and not l[j].startswith('#'):
                m = _CON.match(l[j])
                if m and m.group(1) != 'x':
                    con[m.group(1)] = (float(m.group(2)), float(m.group(3)))
                j += 1
            aus.append((z, dict(con=con, mer=l[k + 1].split()[0],
                                lat=lat, lon=lon, datei=os.path.basename(pfad))))
    return aus


def index():
    idx = collections.defaultdict(list)
    for f in quellen():
        for n, r in bloecke(f):
            if r['con'].get('M2', (0, 0))[0] > 0:
                idx[n].append(r)
    return idx


def cptt():
    """-> [(Startzeile, Namenszeile, Endzeile, Notiz, no)] fuer jeden Satz."""
    l = open(TXT, encoding='iso-8859-1').read().split('\n')
    aus = []
    for k, z in enumerate(l):
        if z and not z.startswith('#') and k + 1 < len(l) and MERIDIAN.match(l[k + 1]):
            a = k
            while a > 0 and (l[a - 1].startswith('#') or not l[a - 1].strip()):
                a -= 1
            b = k + 3
            while b < len(l) and l[b].strip() and not l[b].startswith('#'):
                b += 1
            note = next((y for y in l[a:k] if 'transfer from' in y), '')
            m = re.search(r'\(no\.(\d+)\)', note)
            aus.append((a, k, b, note, int(m.group(1)) if m else None))
    return l, aus


def probe():
    ordnung, sp = kopf(TXT)
    idx = index()
    full = {r['no']: r for r in json.load(open(JSON))}
    l, saetze = cptt()
    verdacht = {int(r['no']) for r in csv.DictReader(open(ABGLEICH, encoding='utf-8'))}
    gut = schlecht = ohne = 0
    abweichung = []
    for a, k, b, note, no in saetze:
        if no is None or no in verdacht or no not in full:
            continue
        ref = note.split('transfer from ', 1)[1].split(' (no.')[0].strip()
        kand = idx.get(ref)
        if not kand:
            ohne += 1
            continue
        ist = {}
        for z in l[k + 3:b]:
            p = z.split()
            if p and p[0] != 'x':
                try:
                    ist[p[0]] = (float(p[1]), float(p[2]))
                except (ValueError, IndexError):
                    pass
        best = None
        for rr in kand:
            tr = uebertrage(full[no], rr['con'], sp)
            if not tr:
                continue
            d = max((abs(tr['con'][c][0] - ist[c][0])
                     for c in ('M2', 'S2', 'K1', 'O1') if c in tr['con'] and c in ist),
                    default=9.9)
            if best is None or d < best:
                best = d
        if best is None:
            ohne += 1
        elif best < 0.0006:
            gut += 1
        else:
            schlecht += 1
            abweichung.append((best, l[k]))
    print(f'Probe an den unverdaechtigen Saetzen:')
    print(f'   {gut:5} exakt reproduziert (Amplituden auf 0.0006 m genau)')
    print(f'   {schlecht:5} weichen ab')
    print(f'   {ohne:5} Referenz nicht auffindbar')
    for d, n in sorted(abweichung, reverse=True)[:10]:
        print(f'      {d:.4f} m  {n[:56]}')
    return 0



def repariere(schreiben=False, alle_zeilen=False):
    ordnung, sp = kopf(TXT)
    idx = index()
    full = {r['no']: r for r in json.load(open(JSON))}
    l, saetze = cptt()

    # gedruckter Referenzname -> aufgeloester Satz, aus den Notizzeilen
    paare = collections.defaultdict(collections.Counter)
    for _a, _k, _b, note, no in saetze:
        if no and no in full and full[no].get('ref') and 'transfer from' in note:
            paare[full[no]['ref']][note.split('transfer from ', 1)[1].split(' (no.')[0].strip()] += 1
    aufgeloest = {g: c.most_common(1)[0][0] for g, c in paare.items()}

    # Nur was einzeln belegt ist. Der Abgleich allein reicht nicht: die
    # Regel "naechste Referenzstation" trifft zwar bei nahen Referenzen fast
    # immer, aber das ist zirkulaer -- bei ferner gedruckter Referenz ist sie
    # oft trotzdem richtig. Blind angewandt hat sie 199 von 254 Saetzen
    # verschlechtert (Median 24.9 % -> 55.3 % Abweichung vom Nachbarn).
    quelle = GEPRUEFT if not alle_zeilen else ABGLEICH
    plan = {}
    for r in csv.DictReader(open(quelle, encoding='utf-8')):
        if quelle is GEPRUEFT and not r.get('urteil','').startswith('reparierbar'):
            continue
        neu = aufgeloest.get(r['vorschlag'])
        if neu and neu in idx:
            plan[int(r['no'])] = (r['vorschlag'], neu, r['gedruckt'])

    gebaut, fehlt, unveraendert = [], [], 0
    for a, k, b, note, no in saetze:
        if no not in plan:
            continue
        gedruckt_neu, refname, alt = plan[no]
        kand = idx[refname]
        rr = min(kand, key=lambda x: len(x['datei']))
        tr = uebertrage(full[no], rr['con'], sp)
        if not tr:
            fehlt.append((no, l[k], 'Uebertragung nicht moeglich'))
            continue
        gebaut.append((a, k, b, no, l[k], alt, gedruckt_neu, refname, rr, tr))
    print(f'{len(plan)} Zeilen im Plan, {len(gebaut)} Saetze im Bestand gefunden, '
          f'{len(fehlt)} nicht baubar')

    # Neue Bloecke bauen
    neu_zeilen = {}
    for a, k, b, no, name, alt, gedruckt_neu, refname, rr, tr in gebaut:
        s_ = full[no]
        # Die Zeitzone gehoert der Station und bleibt; der Meridian kommt von
        # der Referenz, weil die Phasen in deren Rahmen stehen.
        teile = l[k + 1].split()
        tz = teile[1].lstrip(':') if len(teile) > 1 else 'UTC'
        z0 = s_.get('mtl_ft')
        z0 = z0 * FT if z0 is not None else round(tr['M2'] + tr['S2'], 3)
        notiz = latin1(
            f"# note: NOAA Tide Tables (C&GS/NOS) Pacific+Indian 2018 Table 2 transfer from "
            f"{refname} (no.{no}). M2={tr['M2']:.2f} S2={tr['S2']:.2f} "
            f"k={tr['k']:.2f} dt={tr['dt']*60:+.0f}min.")
        kopfz = []
        for z in l[a:k]:
            if z.startswith('# note:') and 'transfer from' in z:
                kopfz.append(notiz)
            elif z.startswith('# confidence:'):
                kopfz.append(f'# confidence: {konfidenz(tr, s_)}')
            elif z.startswith('# reparatur:'):
                continue
            else:
                kopfz.append(z)
        kopfz.insert(1, latin1(f'# reparatur: Referenz {alt} -> {gedruckt_neu} '
                               f'(Ueberschrift in NP-Table-2 uebersprungen), '
                               f'{dt.date.today()}'))
        block = kopfz + [name, f"{rr['mer']} :{tz}", f"{float(z0):.4f} meters"]
        for c in ordnung:
            if c in tr['con']:
                aa, gg = tr['con'][c]
                block.append(f"{c:<16}{aa:.4f}  {gg:.2f}")
            else:
                block.append('x 0 0')
        neu_zeilen[(a, b)] = block

    print(f'\n{len(neu_zeilen)} Saetze werden neu gebaut. Beispiele:\n')
    for (a, b), blk in list(sorted(neu_zeilen.items()))[:6]:
        name = next(z for z in blk if not z.startswith('#'))
        rep = next(z for z in blk if z.startswith('# reparatur:'))
        print(f'   {name[:50]:50} {rep[13:100]}')

    if not schreiben:
        print('\n(Probelauf -- nichts geschrieben)')
        return 0
    shutil.copy2(TXT, os.path.join(
        BACKUP, f'harmonics_noaa_cptt.txt.vor_referenzreparatur_'
                f'{dt.datetime.now():%Y%m%d_%H%M}'))
    for (a, b), blk in sorted(neu_zeilen.items(), reverse=True):
        l[a:b] = blk
    # Erst vollstaendig danebenschreiben, dann umbenennen. Ein Abbruch mitten
    # im Schreiben hat die Datei sonst schon auf null Bytes gekuerzt.
    tmp = TXT + '.neu'
    with open(tmp, 'w', encoding='iso-8859-1') as fh:
        fh.write('\n'.join(l))
    os.replace(tmp, TXT)
    n = sum(1 for i, z in enumerate(l)
            if z and not z.startswith('#') and i + 1 < len(l) and MERIDIAN.match(l[i + 1]))
    print(f'\ngeschrieben, {n} Saetze in der Datei')
    return 0


if __name__ == '__main__':
    if '--probe' in sys.argv:
        sys.exit(probe())
    sys.exit(repariere('--schreiben' in sys.argv, '--alle-zeilen' in sys.argv))
