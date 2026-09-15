#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Pruefstand fuer die NOAA-Table-2-Uebertragungen (eutt, ectt/wctt = amtt, cptt).

Warum: Die Bauskripte py/build_noaa_{eutt,amtt,cptt}.py sind drei auseinander-
gelaufene Kopien, und ihre Fehler wurden bisher einzeln gefunden (Zonen,
Bezugsort-Verwechslung, Springhub, Faktor CAL ...). Hier wird das Verfahren
Schritt fuer Schritt an einer Wahrheit gemessen: an jedem Buchort, an dem ein
unabhaengiger Satz aus kontinuierlichen amtlichen Vorhersagen oder Messungen
steht (Klasse A), ist bekannt, was herauskommen muss.

Teile:
  bezugssaetze()  je (Band, Bezugsort im Buch) der benutzte Bezugssatz, dazu
                  sein Abstand zur Buchposition des Bezugsorts ("Daily
                  predictions"-Zeile)
  wahrheit()      je Buchzeile der naechste Klasse-A-Satz unter KM_WAHR km
  uebertragen()   der Uebertragungskern mit Schaltern (siehe VARIANTEN)
  messen()        Kurvenabstand, M2-Zeit/Amplitude, S2/M2, HW/NW-Zeiten

Usage: python3 py/noaa_pruefstand.py --hubprobe     Buchhube gegen den Bezugsort (Druckfehler im Bezug)
       python3 py/noaa_pruefstand.py --bezug        Bezugssaetze pruefen
       python3 py/noaa_pruefstand.py --wahrheit     Abdeckung der Wahrheit
       python3 py/noaa_pruefstand.py --varianten    alle Varianten messen
"""
from __future__ import annotations

import collections
import csv
import json
import math
import os
import re
import statistics
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import xtide_modell as X                                           # noqa: E402
from health_check import load_records, km                          # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HELP = os.path.join(ROOT, 'harmonics/help')
KOPF = X.kopf_lesen(os.path.join(ROOT, 'harmonics/utide/harmonics_utide_tidetables.txt'))
SP = KOPF[1]
FT = 0.3048
KM_WAHR = 3.0

BAENDER = {'eutt': ('eutt2020', 'harmonics_noaa_eutt.txt'),
           'ectt': ('ectt2020', 'harmonics_noaa_amtt.txt'),
           'wctt': ('wctt2020', 'harmonics_noaa_amtt.txt'),
           'cptt': ('cptt2018', 'harmonics_noaa_cptt.txt')}

DIURN = {'K1', 'O1', 'P1', 'Q1', 'J1', 'M1', 'OO1', '2Q1', 'SO1', 'RHO1', 'PHI1', 'PSI1', 'S1',
         'SIG1', 'TAU1', 'CHI1', 'THE1', 'BET1', 'UPS1', 'NO1', 'ALP1', 'PI1'}
LANG = {'SA', 'SSA', 'MM', 'MF', 'MSF', 'MSQM', 'MTM', 'MSM', 'SM', 'Z0'}
SHAL = {'M4', 'MS4', 'M6', 'MN4', '2MS6', 'MK3', '2MK3', 'S4', 'S6', 'SK3', 'M8', '3MK7', 'MK4',
        'SK4', '2SM6', 'MSN6', '2MN6', 'M3', 'SO3', 'MO3', '2MK5', '2SK5', 'MK6', 'MSK6', '3MN8',
        'M10', 'M12', 'MNK6', '2MN2', 'MNS2', 'SN4', '3MS4', 'MSK2'}

# Quellen, die als Wahrheit taugen: kontinuierliche amtliche Vorhersagen oder Messungen.
# Nicht: Uebertragungen (ATT secondary, NOAA), Fits auf Hoch-/Niedrigwassertafeln
# (Kosinus-Interpolation: tidetimes, CHS HW/LW, SHN/DHN-Tafeln), Modelle (FES).
KLASSE_A_DATEI = ('harmonics_utide_observations.txt', 'harmonics_ticon4_worldwide.txt',
                  'harmonics_puertos_spain.txt', 'harmonics-dwf-20251228-free.txt',
                  'harmonics-1997-05-25_mod.txt', 'harmonics-2004-06-14_mod.txt',
                  'harmonics-dwf-20100529-nonfree_mod.txt', 'harmonics-dwf-20070318_mod.txt')
KLASSE_A_QUELLE = re.compile(r'reverse-engineered|1y hourly|SHOM tide predictions|KHOA|NAMRIA|CWA tide|'
                             r'BMKG|JMA|Hidronav|SEMAR|CICESE|10-min|hourly', re.I)
NICHT_QUELLE = re.compile(r'HW/LW|tidetimes|HW predictions|transfer|secondary|FES|SHN Argentina|'
                          r'Marinha do Brasil|IHM tide predictions', re.I)


def buch():
    """{(band, no): zeile} aller Baender, dazu zonen {(band, no): (zone, ref)} und refzonen."""
    zeilen, zonen, refz = {}, {}, {}
    from noaa_referenz_verwechslung import REF_BUCHFEHLER, POS_LESEFEHLER
    for band, (j, _d) in BAENDER.items():
        for z in json.load(open(os.path.join(HELP, f'{j}_table2_full.json'), encoding='utf-8')):
            if (band, z['no']) in REF_BUCHFEHLER and not z.get('daily'):
                z = dict(z, ref=REF_BUCHFEHLER[(band, z['no'])], ref_druck=z['ref'])
            if (band, z['no']) in POS_LESEFEHLER:
                z = dict(z, lat=POS_LESEFEHLER[(band, z['no'])][0], lon=POS_LESEFEHLER[(band, z['no'])][1])
            zeilen[(band, z['no'])] = z
        zj = json.load(open(os.path.join(HELP, f'zonen_{j}.json'), encoding='utf-8'))
        for k, v in zj['stationen'].items():
            zonen[(band, int(k.split('-')[-1]))] = tuple(v)
        refz[band] = zj['referenzen']
    return zeilen, zonen, refz


def norm(s):
    return re.sub(r'[^a-z0-9]', '', s.lower())


_VERM = None
def vermerk(r):
    global _VERM
    if _VERM is None:
        import pegel_dubletten
        _VERM = pegel_dubletten.vermerke()
    return _VERM.get((r['file'], r['line']), '')


def band_und_nummer(r):
    v = vermerk(r)
    u = re.search(r'noaa_uid: (\w+)-(\d+)', v)
    if u:
        return u.group(1), int(u.group(2))
    n = re.search(r'noaa_number: (\d+)', v)
    if not n:
        return None, None
    b = 'cptt' if 'cptt' in r['file'] else ('eutt' if 'eutt' in r['file'] else None)
    return b, int(n.group(1))


_SATZ = {}
def satz(r):
    """(z0 m, {c: (amp m, G Greenwich)}) eines Satzes."""
    key = (r['file'], r['name'], r['line'])
    if key not in _SATZ:
        z0, w, e, mer = X.satz_lesen(os.path.join(ROOT, r['file']), r['name'])
        sk = FT if e.startswith('f') else 1.0
        _SATZ[key] = (z0 * sk, {c: (a * sk, X.greenwich(g, SP[c], mer) % 360.0)
                                for c, (a, g) in w.items() if c in SP and a > 0})
    return _SATZ[key]


def klasse(r):
    f = os.path.basename(r['file'])
    v = vermerk(r)
    src = ' '.join(re.findall(r'# source: (.*)', v))
    if '/noaa/' in r['file'] or 'secondary' in f or 'current' in f.lower() or 'fes' in f:
        return None
    if NICHT_QUELLE.search(src):
        return 'B'
    if f in KLASSE_A_DATEI or KLASSE_A_QUELLE.search(src):
        return 'A'
    if f.startswith('harmonics_att_np2') or 'lavergne' in f:
        return 'A'
    return 'B'


def bezugssaetze(recs, zeilen):
    """{(band, ref): (satz-record, abstand km zur Buchposition, stimmen)}."""
    daily = {}
    for (band, no), z in zeilen.items():
        if z.get('daily'):
            daily.setdefault((band, norm(z['name'].split(',')[0].strip(' }'))), z)
    benutzt = collections.defaultdict(collections.Counter)
    for r in recs:
        if '/noaa/' not in r['file']:
            continue
        m = re.search(r'transfer from (.+?) \(no\.(\d+)\)', vermerk(r))
        band, no = band_und_nummer(r)
        if not m or (band, no) not in zeilen:
            continue
        benutzt[(band, zeilen[(band, no)]['ref'])][m.group(1)] += 1
    nach_name = collections.defaultdict(list)
    for r in recs:
        if '/noaa/' not in r['file'] and 'current' not in r['file'].lower():
            nach_name[r['name']].append(r)
    out = {}
    for (band, ref), cnt in benutzt.items():
        name, n = cnt.most_common(1)[0]
        kand = nach_name.get(name, [])
        d = None
        for (b2, nn), z in daily.items():
            if b2 == band and (nn.startswith(norm(ref)[:8]) or norm(ref).startswith(nn[:8])):
                d = z
                break
        if kand and d:
            kand = sorted(kand, key=lambda q: km(q, {'lat': d['lat'], 'lon': d['lon']}))
        out[(band, ref)] = (kand[0] if kand else None, name,
                            None if not (kand and d) else km(kand[0], {'lat': d['lat'], 'lon': d['lon']}),
                            d, sum(cnt.values()), len(cnt))
    return out


# ---------------------------------------------------------------- Kern
_T = np.arange(0, 60 * 24, 1 / 6.0)                     # 60 Tage, 10 min (Stunden)
_NAMEN = [c for c in KOPF[0] if c in SP]
_W = np.radians(np.array([SP[c] for c in _NAMEN]))
_COS = np.cos(np.outer(_T, _W)); _SIN = np.sin(np.outer(_T, _W))
_IX = {c: i for i, c in enumerate(_NAMEN)}


def kurve(con):
    """Knotenfreie Synthese; con {c: (amp, G)} -> h(_T) ohne Mittel."""
    a = np.zeros(len(_NAMEN)); c_ = np.zeros(len(_NAMEN))
    for c, (amp, g) in con.items():
        if c in _IX and c not in LANG:
            i = _IX[c]; a[i] = amp * math.cos(math.radians(g)); c_[i] = amp * math.sin(math.radians(g))
    return _COS @ a + _SIN @ c_


def scheitel(h, fenster=True):
    """Indizes der Hoch- und Niedrigwasser."""
    if not fenster:
        d = h[1:-1]
        return (np.where((d >= h[:-2]) & (d > h[2:]))[0] + 1, np.where((d <= h[:-2]) & (d < h[2:]))[0] + 1)
    per = 360.0 / SP['M2'] * 6                              # Schritte je M2-Periode
    n = int(len(h) // per)
    gr = [int(round(i * per)) for i in range(n + 1)]
    hi = np.array([gr[i] + int(np.argmax(h[gr[i]:gr[i + 1]])) for i in range(n)])
    lo = np.array([gr[i] + int(np.argmin(h[gr[i]:gr[i + 1]])) for i in range(n)])
    return hi, lo


def hube(con, ext='fenster', spring='phase', grad=30):
    """(Mittelhub, Springhub, grosser Tageshub) der Synthese."""
    h = kurve(con)
    hi, lo = scheitel(h, ext == 'fenster')
    if len(hi) < 5 or len(lo) < 5:
        return 0.0, 0.0, 0.0
    mittel = h[hi].mean() - h[lo].mean()
    if spring == 'p92' or 'S2' not in con or 'M2' not in con:
        sp = np.percentile(h[hi], 92) - np.percentile(h[lo], 8)
    else:
        phi = ((SP['S2'] - SP['M2']) * _T - (con['S2'][1] - con['M2'][1]) + 180) % 360 - 180
        shi, slo = hi[np.abs(phi[hi]) <= grad], lo[np.abs(phi[lo]) <= grad]
        sp = h[shi].mean() - h[slo].mean() if len(shi) >= 3 and len(slo) >= 3 else mittel
    tag = (_T // 24).astype(int)
    hh = [h[hi][tag[hi] == k].max() for k in range(60) if (tag[hi] == k).any()]
    ll = [h[lo][tag[lo] == k].min() for k in range(60) if (tag[lo] == k).any()]
    gt = float(np.mean(hh) - np.mean(ll)) if hh and ll else sp
    return float(mittel), float(sp), gt


STANDARD = dict(cal=1.10, ext='naiv', spring='phase', shallow='lisboa', dt='mittel', zone='buch')


def uebertragen(s, ref_con, ref_name, zn, zb, v, refbuch=None):
    """Buchzeile s + Bezugskonstanten (Greenwich) -> Konstanten (Greenwich) oder None.

    v['k'] == 'buch': Hubverhaeltnis Neben/Bezug direkt aus dem Buch (Daily-predictions-Zeile
    des Bezugsorts), sonst synthetisch gemessener Hub des Bezugssatzes.
    """
    con = ref_con
    if con.get('M2', (0, 0))[0] <= 0:
        return None
    if v.get('k') == 'buch' and refbuch:
        kb = buch_faktoren(s, refbuch)
        if kb:
            return _anwenden(con, ref_name, s, zn, zb, v, *kb)
    Mn, Sr, Gt = hube(con, v['ext'], 'phase' if v['spring'] == 'analytisch' else v['spring'], v.get('spring_grad', 30))
    mean, spring, diu, trop = s.get('mean_ft'), s.get('spring_ft'), s.get('diurnal_ft'), s.get('tropic_ft')
    if diu is not None and diu <= 0.05:
        diu = None
    cal = v['cal']
    if mean is not None and Mn > 0.02:
        k = cal * mean * FT / Mn
    elif diu is not None and Gt > 0.02:
        k = cal * diu * FT / Gt
    elif trop is not None and Gt > 0.02:
        k = cal * 0.92 * trop * FT / Gt
    else:
        return None
    k = min(max(k, 0.05), 8.0)
    sS = 1.0
    if v['spring'] == 'analytisch' and spring is not None and mean and con.get('S2', (0, 0))[0] > 0:
        # Springhub = 2(M2+S2), Mittelhub = 2 M2  ->  S2/M2 = Springhub/Mittelhub - 1
        sS = min(max((spring / mean - 1.0) * con['M2'][0] / con['S2'][0], 0.1), 6.0)
    elif spring is not None and mean is not None:
        cur, tgt = k * (Sr - Mn), cal * (spring - mean) * FT
        if cur > 0.02 and tgt > 0:
            sS = min(max(tgt / cur, 0.1), 6.0)
    sD = 1.0
    if diu is not None and mean is not None and Gt > Mn:
        cur, tgt = k * (Gt - Mn), (diu - mean) * FT * (cal if v.get('cal_d') else 1.0)
        if cur > 0.02 and tgt > 0:
            sD = min(max(tgt / cur, 0.1), 6.0)
    return _anwenden(con, ref_name, s, zn, zb, v, k, sS, sD)


def buch_faktoren(s, rb):
    """(k, sS, sD) aus den Buchhuben von Neben- und Bezugsort, oder None."""
    m, sp, d = s.get('mean_ft'), s.get('spring_ft'), s.get('diurnal_ft')
    mr, spr, dr = rb.get('mean_ft'), rb.get('spring_ft'), rb.get('diurnal_ft')
    if m and mr:
        k = m / mr
        sS = ((sp - m) / (spr - mr)) / k if (sp and spr and sp > m and spr > mr) else 1.0
        sD = ((d - m) / (dr - mr)) / k if (d and dr and d > m and dr > mr) else 1.0
    elif d and dr:
        k, sS, sD = d / dr, 1.0, 1.0
    else:
        return None
    k = k * FT / FT
    return min(max(k, 0.05), 8.0), min(max(sS, 0.1), 6.0), min(max(sD, 0.1), 6.0)


def _anwenden(con, ref_name, s, zn, zb, v, k, sS, sD):
    ts = {'mittel': [t for t in (s.get('dtHW'), s.get('dtLW')) if t is not None],
          'hw': [s['dtHW']] if s.get('dtHW') is not None else [t for t in (s.get('dtLW'),) if t is not None],
          'lw': [s['dtLW']] if s.get('dtLW') is not None else [t for t in (s.get('dtHW'),) if t is not None]}[v['dt']]
    dt = (sum(ts) / len(ts) / 60.0) if ts else 0.0
    if v['zone'] == 'buch' and zn is not None and zb is not None:
        dt += zb - zn
    out = {}
    for c, (a, g) in con.items():
        if c in SHAL:
            if v['shallow'] == 'weg' or (v['shallow'] == 'lisboa' and ref_name.startswith('Lisboa (Alc')):
                continue
            na = a * k * k if v['shallow'] == 'k2' else a * k
        elif c in ('S2', 'K2'):
            na = a * k * sS
        elif c in DIURN:
            na = a * k * sD
        elif c in LANG:
            na = a
        else:
            na = a * k
        out[c] = (na, (g + SP[c] * dt) % 360.0)
    if v.get('asym') and s.get('dtHW') is not None and s.get('dtLW') is not None and 'M2' in out:
        # Ungleiche HW/NW-Differenzen des Buchs als M4-Zusatz: fuer h = A cos(t) + B cos(2t - phi)
        # verschiebt phi = +90 Grad das HW um +2B/A und das NW um -2B/A (Bogenmass der M2-Phase).
        a_min = (s['dtHW'] - s['dtLW']) / 2.0 * v['asym']
        A, g2 = out['M2']
        B = A * abs(a_min) * math.radians(SP['M2'] / 60.0) / 2.0
        phase = (2 * g2 + (90.0 if a_min > 0 else -90.0)) % 360.0
        a4, g4 = out.get('M4', (0.0, 0.0))
        z = complex(a4 * math.cos(math.radians(g4)), a4 * math.sin(math.radians(g4))) + \
            complex(B * math.cos(math.radians(phase)), B * math.sin(math.radians(phase)))
        out['M4'] = (abs(z), math.degrees(math.atan2(z.imag, z.real)) % 360.0)
    return out


def messen(con, wahr):
    """Kennzahlen von con gegen wahr (beide Greenwich)."""
    h, w = kurve(con), kurve(wahr)
    hub = float(np.ptp(w))
    def fein(x, ix):
        # Parabel durch die drei Punkte um den Rasterscheitel -> Zeit in Minuten
        ix = ix[(ix > 0) & (ix < len(x) - 1)]
        y0, y1, y2 = x[ix - 1], x[ix], x[ix + 1]
        den = y0 - 2 * y1 + y2
        off = np.where(den != 0, 0.5 * (y0 - y2) / np.where(den != 0, den, 1), 0.0)
        return (ix + off) * 10.0
    hi, lo = scheitel(h); whi, wlo = scheitel(w)
    def dtext(a, b):
        n = min(len(a), len(b))
        dd = a[:n] - b[:n]
        dd = dd[np.abs(dd) < 360]
        return float(np.median(dd)) if len(dd) else float('nan')
    hi, lo, whi, wlo = fein(h, hi), fein(h, lo), fein(w, whi), fein(w, wlo)
    def ph(c):
        if c not in con or c not in wahr or wahr[c][0] < 0.03:
            return float('nan'), float('nan')
        return ((con[c][1] - wahr[c][1] + 180) % 360 - 180) / SP[c] * 60, con[c][0] / wahr[c][0]
    m2t, m2a = ph('M2'); s2t, s2a = ph('S2'); k1t, k1a = ph('K1'); o1t, o1a = ph('O1')
    return dict(kurve_pct=float(np.sqrt(np.mean((h - w) ** 2)) / hub * 100) if hub > 0 else float('nan'),
                kurve_cm=float(np.sqrt(np.mean((h - w) ** 2)) * 100), hub=hub,
                m2_min=m2t, m2_amp=m2a, s2_min=s2t, s2_amp=s2a, k1_min=k1t, k1_amp=k1a, o1_min=o1t, o1_amp=o1a,
                hw_min=dtext(hi, whi), nw_min=dtext(lo, wlo))


# ---------------------------------------------------------------- Zuordnung
def daily_zeile(zeilen, band, ref):
    nr = norm(ref)
    best = None
    for (b, no), z in zeilen.items():
        if b != band or not z.get('daily'):
            continue
        nz = norm(z['name'].replace('}', ''))
        if nz.startswith(nr[:10]) or nr.startswith(nz[:10]) or nr in nz:
            if best is None or len(nz) < len(norm(best['name'])):
                best = z
    return best


def bezug_waehlen(recs_ab, benutzt, zeilen, band, ref):
    """-> (record, weg): Klasse-A-Satz nahe der Buchposition des Bezugsorts, sonst der benutzte."""
    d = daily_zeile(zeilen, band, ref)
    if d:
        nah = [(km(r, {'lat': d['lat'], 'lon': d['lon']}), r) for r in recs_ab
               if abs(r['lat'] - d['lat']) < 0.3 and klasse(r) == 'A']
        nah = sorted([x for x in nah if x[0] <= 10.0], key=lambda x: x[0])
        if nah:
            return nah[0][1], f"A {nah[0][0]:.1f} km vom Buchort"
    if benutzt:
        return benutzt, 'wie beim Bau'
    return None, 'kein Bezug'


def wahrheit_fuer(recs_ab, lat, lon):
    nah = [(km(r, {'lat': lat, 'lon': lon}), r) for r in recs_ab
           if abs(r['lat'] - lat) < 0.05 and klasse(r) == 'A']
    nah = sorted([x for x in nah if x[0] <= KM_WAHR], key=lambda x: x[0])
    return nah[0] if nah else (None, None)


_TZF = None
def ortszone(lat, lon):
    global _TZF
    from zoneinfo import ZoneInfo
    import datetime as _d
    if _TZF is None:
        from timezonefinder import TimezoneFinder
        _TZF = TimezoneFinder()
    z = _TZF.timezone_at(lat=lat, lng=((lon + 180) % 360) - 180)
    if not z:
        return round(lon / 15.0)
    try:
        return round(ZoneInfo(z).utcoffset(_d.datetime(1980, 1, 15, 12)).total_seconds() / 1800.0) / 2.0
    except Exception:
        return None


def faelle(recs, alle=False):
    """Buchzeilen mit Wahrheit (alle=True: auch ohne, sofern es einen heutigen NOAA-Satz gibt):
    dict mit s, band, no, zn, zb, ref, wahr, heute (heutiger NOAA-Satz)."""
    zeilen, zonen, refz = buch()
    recs_ab = [r for r in recs if '/noaa/' not in r['file'] and not r.get('current')
               and 'current' not in r['file'].lower()]
    heute = {}
    for r in recs:
        if '/noaa/' in r['file']:
            b, n = band_und_nummer(r)
            if b:
                heute[(b, n)] = r
    B = bezugssaetze(recs, zeilen)
    import noaa_referenz_verwechslung as V
    import noaa_buch_zonen as NBZ
    bezug_cache = {}
    out = []
    for (band, no), s in zeilen.items():
        if s.get('daily'):
            continue
        r_heute = heute.get((band, no))
        lat, lon = (r_heute['lat'], r_heute['lon']) if r_heute else (s['lat'], s['lon'])
        d, wahr = wahrheit_fuer(recs_ab, lat, lon)
        if wahr is None and not (alle and r_heute is not None):
            continue
        key = (band, s['ref'])
        if key not in bezug_cache:
            benutzt = B.get(key, (None,))[0]
            bezug_cache[key] = bezug_waehlen(recs_ab, benutzt, zeilen, band, s['ref'])
        ref, weg = bezug_cache[key]
        if ref is None:
            continue
        zn = V.ZONE_BUCHFEHLER.get((band, no), zonen.get((band, no), (None, None))[0])
        zb = NBZ.suche(refz[band], s['ref'])
        if not isinstance(zn, (int, float)):
            # 'local' (Buch nennt keinen Meridian, arktisches Kanada): Standardzone des Orts
            zn = ortszone(lat, lon)
        if not isinstance(zb, (int, float)):
            zb = ortszone(ref['lat'], ref['lon']) if ref.get('lat') is not None else None
        out.append(dict(band=band, no=no, s=s, zn=zn, zb=zb, ref=ref, ref_weg=weg, wahr=wahr, wahr_km=d,
                        refbuch=daily_zeile(zeilen, band, s['ref']),
                        heute=r_heute))
    return out


VARIANTEN = {
    'Bau heute':            dict(STANDARD),
    'CAL 1.0':              {**STANDARD, 'cal': 1.0},
    'CAL 1.0 Spring 45':    {**STANDARD, 'cal': 1.0, 'spring_grad': 45},
    'Buchquotient':         {**STANDARD, 'cal': 1.0, 'spring_grad': 45, 'k': 'buch'},
    'Buchquotient Flach weg': {**STANDARD, 'cal': 1.0, 'spring_grad': 45, 'k': 'buch', 'shallow': 'weg'},
    'Buchquotient HW/NW':   {**STANDARD, 'cal': 1.0, 'spring_grad': 45, 'k': 'buch', 'asym': 1.0},
    'CAL 1.0 Fenster S45':  {**STANDARD, 'cal': 1.0, 'spring_grad': 45, 'ext': 'fenster'},
    'CAL 1.04 Fenster S45': {**STANDARD, 'cal': 1.04, 'spring_grad': 45, 'ext': 'fenster'},
}


def varianten(recs, argv):
    F = faelle(recs)
    print(f'{len(F)} Buchzeilen mit Klasse-A-Wahrheit unter {KM_WAHR} km')
    zeilen = []
    for f in F:
        _z, wahr = satz(f['wahr'])
        _zr, refc = satz(f['ref'])
        basis = dict(band=f['band'], no=f['no'], name=f['s']['name'], typ=f['s'].get('coltype'),
                     wahr=f"{f['wahr']['name']} [{os.path.basename(f['wahr']['file'])}]", wahr_km=round(f['wahr_km'], 2),
                     bezug=f"{f['ref']['name']} [{os.path.basename(f['ref']['file'])}]", bezug_weg=f['ref_weg'],
                     form=round((wahr.get('K1', (0, 0))[0] + wahr.get('O1', (0, 0))[0])
                                / max(1e-6, wahr.get('M2', (0, 0))[0] + wahr.get('S2', (0, 0))[0]), 2))
        if f['heute'] is not None:
            try:
                zeilen.append({**basis, 'variante': 'Bestand', **messen(satz(f['heute'])[1], wahr)})
            except (KeyError, ValueError):
                pass
        for name, v in VARIANTEN.items():
            con = uebertragen(f['s'], refc, f['ref']['name'], f['zn'], f['zb'], v, f.get('refbuch'))
            if con:
                zeilen.append({**basis, 'variante': name, **messen(con, wahr)})
    ziel = os.path.join(HELP, 'noaa_pruefstand.csv')
    with open(ziel, 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=list(zeilen[0].keys()))
        w.writeheader(); w.writerows(zeilen)
    auswerten(zeilen)
    paarweise(zeilen, 'Bestand')
    paarweise(zeilen, 'Bau heute')


def paarweise(zeilen, basis='Bestand'):
    nach = collections.defaultdict(dict)
    for z in zeilen:
        nach[(z['band'], z['no'])][z['variante']] = z
    namen = sorted({z['variante'] for z in zeilen})
    print(f"\nPaarweise gegen '{basis}' (nur Zeilen mit beiden): Median Kurve % und Anteil besser")
    for v in namen:
        if v == basis:
            continue
        paare = [(d[basis]['kurve_pct'], d[v]['kurve_pct']) for d in nach.values() if basis in d and v in d]
        if not paare:
            continue
        a = statistics.median(p[0] for p in paare); b = statistics.median(p[1] for p in paare)
        besser = sum(1 for p in paare if p[1] < p[0] - 0.1); schlechter = sum(1 for p in paare if p[1] > p[0] + 0.1)
        print(f"  {v:24} n={len(paare):5d}  {a:5.2f} -> {b:5.2f} %   besser {besser:5d}  schlechter {schlechter:5d}")


def auswerten(zeilen):
    import math as _m
    def med(xs):
        xs = [x for x in xs if x == x]
        return statistics.median(xs) if xs else float('nan')
    gruppen = collections.defaultdict(list)
    for z in zeilen:
        gruppen[z['variante']].append(z)
    # nur Buchzeilen, die in allen Varianten vorkommen
    print(f"{'Variante':24} {'n':>5} {'Kurve %':>8} {'Kurve cm':>9} {'|M2| min':>9} {'M2 amp':>7} {'S2 amp':>7} "
          f"{'|K1| min':>9} {'K1 amp':>7} {'|HW| min':>9} {'|NW| min':>9}")
    for name, zs in gruppen.items():
        print(f"{name:24} {len(zs):5d} {med(z['kurve_pct'] for z in zs):8.2f} {med(z['kurve_cm'] for z in zs):9.1f} "
              f"{med(abs(z['m2_min']) for z in zs):9.1f} {med(z['m2_amp'] for z in zs):7.3f} {med(z['s2_amp'] for z in zs):7.3f} "
              f"{med(abs(z['k1_min']) for z in zs):9.1f} {med(z['k1_amp'] for z in zs):7.3f} "
              f"{med(abs(z['hw_min']) for z in zs):9.1f} {med(abs(z['nw_min']) for z in zs):9.1f}")


# ---------------------------------------------------------------- Gruppenwahl
GRUNDV = {**STANDARD, 'cal': 1.0, 'spring_grad': 45, 'k': 'buch'}
EINSTELLUNGEN = {'Flach behalten': {}, 'Flach weg': {'shallow': 'weg'},
                 'Flach weg + HW/NW': {'shallow': 'weg', 'asym': 1.0}, 'Flach behalten + HW/NW': {'asym': 1.0}}


def kandidaten_bezug(recs_ab, benutzt, rb):
    out = []
    if benutzt is not None:
        out.append((benutzt, 'wie beim Bau'))
    if rb:
        nah = sorted([(km(r, {'lat': rb['lat'], 'lon': rb['lon']}), r) for r in recs_ab
                      if abs(r['lat'] - rb['lat']) < 0.2 and r.get('lat') is not None], key=lambda x: x[0])
        for d, r in nah:
            if d > 10.0 or len(out) >= 6:
                break
            if klasse(r) is None or any(r is o[0] for o in out):
                continue
            try:
                if satz(r)[1].get('M2', (0, 0))[0] <= 0:
                    continue
            except (KeyError, ValueError, IndexError):
                continue
            out.append((r, f'{klasse(r)} {d:.1f} km vom Buchort'))
    return out


def teilgruppe(f):
    """Raeumliche Teilgruppe: das Buch benutzt einen Bezugsort fuer weit getrennte Gegenden
    (Paramushiru Island fuer die Kurilen UND den Golf von Tonkin). Raster 5 Grad reicht, um
    solche Gegenden zu trennen, und haelt zusammenhaengende Kuesten meist beisammen."""
    s = f['s']
    lat = f['heute']['lat'] if f.get('heute') else s['lat']
    lon = f['heute']['lon'] if f.get('heute') else s['lon']
    return f"{int(math.floor(lat / 5.0)) * 5:+d}{int(math.floor(lon / 5.0)) * 5:+d}"


def gruppen(recs):
    zeilen, zonen, refz = buch()
    F = faelle(recs)
    recs_ab = [r for r in recs if '/noaa/' not in r['file'] and 'current' not in r['file'].lower()]
    B = bezugssaetze(recs, zeilen)
    nach = collections.defaultdict(list)
    for f in F:
        if f['heute'] is not None:                 # ersetzt wird nur, was es gibt
            nach[(f['band'], f['s']['ref'], teilgruppe(f))].append(f)
    ergebnis = []
    for (band, ref, tg), fs in sorted(nach.items()):
        rb = daily_zeile(zeilen, band, ref)
        kands = kandidaten_bezug(recs_ab, B.get((band, ref), (None,))[0], rb)
        bestand = [messen(satz(f['heute'])[1], satz(f['wahr'])[1])['kurve_pct'] for f in fs if f['heute'] is not None]
        tab = []
        for r, weg in kands:
            refc = satz(r)[1]
            for ename, e in EINSTELLUNGEN.items():
                v = {**GRUNDV, **e}
                werte = []
                m2 = []
                for f in fs:
                    con = uebertragen(f['s'], refc, r['name'], f['zn'], f['zb'], v, rb)
                    if con:
                        m = messen(con, satz(f['wahr'])[1])
                        werte.append(m['kurve_pct']); m2.append(abs(m['m2_min']) if m['m2_min'] == m['m2_min'] else 0)
                if len(werte) >= max(1, len(fs) // 2):
                    tab.append((statistics.median(werte), statistics.median(m2), r, weg, ename, len(werte)))
        if not tab:
            continue
        tab.sort(key=lambda x: (round(x[0], 1), x[1]))
        best = tab[0]
        bau = [t for t in tab if t[3] == 'wie beim Bau' and t[4] == 'Flach behalten']
        ergebnis.append(dict(band=band, ref=ref, teilgruppe=tg, n=len(fs),
                             bestand_pct=round(statistics.median(bestand), 2) if bestand else '',
                             bau_neu_pct=round(bau[0][0], 2) if bau else '',
                             best_pct=round(best[0], 2), best_m2_min=round(best[1], 1),
                             bezug=f"{best[2]['name']} [{os.path.basename(best[2]['file'])}]", bezug_weg=best[3],
                             einstellung=best[4], kandidaten=len(kands)))
        e = ergebnis[-1]
        print(f"{band} {ref[:18]:18} {tg:>9} n={len(fs):3d} Bestand {str(e['bestand_pct']):>6} | Bau-Bezug neu {str(e['bau_neu_pct']):>6} | "
              f"bester {e['best_pct']:6.2f} %  {e['einstellung']:22} {e['bezug'][:55]} ({e['bezug_weg']})", flush=True)
    ziel = os.path.join(HELP, 'noaa_pruefstand_gruppen.csv')
    with open(ziel, 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=list(ergebnis[0].keys()))
        w.writeheader(); w.writerows(ergebnis)
    print('->', os.path.relpath(ziel, ROOT))


def hubprobe(zeilen, schwelle=(0.8, 1.25)):
    """Prueft jede Buchzeile gegen ihren Bezugsort: der gedruckte Hub muss aus dem Hub des Bezugsorts
    und den Hoehendifferenzen folgen (Faktor = Reihe/Erwartung). Unstimmig und zugleich passend zu
    einer anderen Tagesstation bis 800 km: Verdacht auf falsche Bezugsueberschrift im Buch.

    Anlass 15.09.2026: Golf von Tonkin "on Paramushiru" (richtig Do Son), Bay of Fundy "on Halifax"
    (Saint John), Pakistan/Iran "on Colombo" (Karachi) -- siehe noaa_referenz_verwechslung.REF_BUCHFEHLER.
    Liste harmonics/help/noaa_hubprobe.csv."""
    def hub(z):
        return z.get('diurnal_ft') or z.get('mean_ft')
    daily = {b: [z for (bb, _), z in zeilen.items() if bb == b and z.get('daily')] for b in BAENDER}
    out = []
    for (band, no), z in sorted(zeilen.items()):
        if z.get('daily') or z.get('hHW') is None or z.get('hLW') is None or not hub(z):
            continue
        rb = daily_zeile(zeilen, band, z['ref'])
        if not rb or not hub(rb):
            continue
        def erwartet(q):
            if z['hHW_kind'] == 'ratio':
                return hub(q) * (z['hHW'] + z['hLW']) / 2.0
            if z.get('hLW_kind') == 'offset':
                return hub(q) + z['hHW'] - z['hLW']
            return None
        e = erwartet(rb)
        if not e or e <= 0.05:
            continue
        f = hub(z) / e
        if schwelle[0] <= f <= schwelle[1]:
            continue
        alt = None
        for q in daily[band]:
            if q is rb or not hub(q) or km(q, z) > 800:
                continue
            e2 = erwartet(q)
            if e2 and e2 > 0.05 and abs(math.log(hub(z) / e2)) < 0.1 and (alt is None or km(q, z) < km(alt, z)):
                alt = q
        out.append(dict(band=band, no=no, name=z['name'], ref=z['ref'], ref_druck=z.get('ref_druck', ''),
                        faktor=round(f, 2), passt_zu=alt['name'] if alt else '', passt_km=round(km(alt, z)) if alt else ''))
    with open(os.path.join(HELP, 'noaa_hubprobe.csv'), 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=list(out[0]) if out else ['band'])
        w.writeheader(); w.writerows(out)
    return out


def main(argv):
    recs = [r for r in load_records() if r['lat'] is not None]
    zeilen, zonen, refz = buch()
    if '--hubprobe' in argv:
        out = hubprobe(zeilen)
        c = collections.Counter((o['band'], o['ref']) for o in out if o['passt_zu'])
        print(len(out), 'unstimmige Zeilen,', sum(c.values()), 'mit passender anderer Tagesstation')
        for (b, r), n in c.most_common(15):
            print(f'  {b:5} {r[:30]:30} {n}')
        return
    if '--bezug' in argv:
        B = bezugssaetze(recs, zeilen)
        print(f"{'Band':5} {'Buch-Bezugsort':28} {'benutzter Satz':48} {'Datei':30} {'km':>7} {'Kl':2} n  Varianten")
        for (band, ref), (r, name, d, dz, n, nvar) in sorted(B.items(), key=lambda x: -(x[1][2] or 0)):
            f = os.path.basename(r['file']) if r else 'FEHLT'
            print(f"{band:5} {ref[:28]:28} {name[:48]:48} {f[:30]:30} {('%.1f' % d) if d is not None else '?':>7} "
                  f"{(klasse(r) or '-') if r else '-':2} {n:3d} {nvar}")
        return
    if '--gruppen' in argv:
        gruppen(recs)
        return
    if '--varianten' in argv:
        varianten(recs, argv)
        return
    print(__doc__)


if __name__ == '__main__':
    main(sys.argv[1:])
