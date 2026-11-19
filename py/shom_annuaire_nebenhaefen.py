#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ports rattaches aus dem SHOM-Annuaire des marees Tome 1 (2023) per Uebertragung, mit Eichung (Oliver 19.11.2026).

Tabellen "Ports rattaches": je Nebenhafen Zeitunterschiede PM VE/PM ME/BM ME/BM VE und Hoehenunterschiede
PM VE/PM ME/BM ME/BM VE zum Bezugshafen (Kopf: Uhrzeiten UTC+1 und Hoehen am Bezugshafen). SHOM-Regel:
Zeitunterschied nach der Uhrzeit des Scheitels am Bezugshafen interpoliert (12-h-periodisch), Hoehenunterschied
nach der Scheitelhoehe. Bezugskurve = unser Satz des Bezugshafens; die uebertragene Kurve wird harmonisch
gefittet (wie py/pla_nebenorte.py).

Eichung: an allen Nebenhaefen mit eigenem Bestandssatz <= 3 km die uebertragenen HW/NW gegen die Scheitel
dieses Satzes (2026). Usage:
  venv/bin/python py/shom_annuaire_nebenhaefen.py eichen
  venv/bin/python py/shom_annuaire_nebenhaefen.py neu [--schreiben]
"""
import math
import os
import re
import subprocess
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import health_check as H                                        # noqa: E402
import pla_nebenorte as P                                       # noqa: E402
import xtide_modell as X                                        # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PDF = os.path.join(ROOT, 'quellen/tide_tables/France_SHOM_2026/SHOM_annuaire_des_marees_tome1_2023.pdf')
BEZUG = {'Dunkerque': 'Dunkerque, France', 'Calais': 'Calais, France', 'Boulogne-sur-Mer': 'Boulogne-sur-Mer, France',
         'Dieppe': 'Dieppe, France', 'Fécamp': 'Fécamp, France', 'Le Havre': 'Le Havre (Marégraphe), France',
         'Cherbourg': 'Cherbourg-en-Cotentin, France', 'Saint-Malo': 'Saint-Malo, France', 'Paimpol': 'Paimpol, France',
         'Roscoff': 'Roscoff, France', 'Brest': 'Brest (Estuaire Penfeld), France', 'Concarneau': 'Concarneau, France',
         'Port-Tudy': 'Port Tudy (Île de Groix), France', 'Port-Navalo': 'Port-Navalo, France',
         'Saint-Nazaire': 'Saint-Nazaire, France', 'Les Sables d’Olonne': "Les Sables-d'Olonne, France",
         'La Rochelle - La Pallice': 'La Rochelle (La Pallice), France', 'Pointe de Grave': 'Port-Bloc (La Pointe de Grave), France',
         'Bordeaux': 'Bordeaux, France', 'Arcachon': "Arcachon (Jetée d'Eyrac), France",
         'Saint-Jean-de-Luz': 'Saint-Jean-de-Luz (Socoa), France'}
NEU = {  # Annuaire-Name: (unser Name, lat, lon, Lage) - Annuaire gibt nur Bogenminuten; Position am Hafen/Steg
    'Landerneau': ('Landerneau, France', 48.4507, -4.2515, 'Kai am Pont de Rohan (Annuaire 48 27 N 04 15 W)'),
    'Le Grand Piquey': ("Le Grand Piquey (Bassin d'Arcachon), France", 44.7057, -1.2205, 'Steg Le Grand Piquey (Annuaire 44 43 N 01 13 W)')}
FIT_MAX = 0.15     # m: Rest des harmonischen Fits an der uebertragenen Kurve (trockenfallende Flusskoepfe)
T_RE = r'([+-]\d\d \d\d)'
H_RE = r'([+-]?\d+,\d\d)'
ZEILE = re.compile(r'^(\S.*?)\s{2,}(\d{1,2}) (\d\d) ([NS])\s+(\d{1,3}) (\d\d) ([EW])\s+(?:\d+,\d\d)?\s*' +
                   r'\s+'.join([T_RE] * 4) + r'\s+' + r'\s+'.join([H_RE] * 4) + r'\s*$')


def _min(s):
    v = int(s[1:3]) * 60 + int(s[4:6])
    return -v if s[0] == '-' else v


def lesen():
    txt = subprocess.run(['pdftotext', '-layout', PDF, '-'], capture_output=True, text=True).stdout.split('\n')
    out, ref = [], None
    for n, z in enumerate(txt):
        # Kopf: Zeile mit "UTC +1h" (Name) - davor Morgen-Zeiten, danach Abend-Zeiten und Hoehen
        if ' UTC +1h' in z:
            name = z.split(' UTC +1h')[0].strip()
            vor = re.findall(r'\d\d \d\d', txt[n - 1])
            hoeh = None
            for k in range(n + 1, n + 4):
                hh = re.findall(r'\d+,\d\d', txt[k])
                if len(hh) == 4:
                    hoeh = [float(x.replace(',', '.')) for x in hh]
            if name in BEZUG and len(vor) == 4 and hoeh:
                t = [int(x[:2]) * 60 + int(x[3:]) for x in vor]          # PM VE, PM ME, BM ME, BM VE (UTC+1, min)
                ref = dict(name=name, satz=BEZUG[name], t=t, h=hoeh)
            continue
        m = ZEILE.match(z)
        if m and ref:
            la = (int(m[2]) + int(m[3]) / 60) * (-1 if m[4] == 'S' else 1)
            lo = (int(m[5]) + int(m[6]) / 60) * (-1 if m[7] == 'W' else 1)
            out.append(dict(name=m[1].strip(), lat=la, lon=lo, dt=[_min(m[8 + i]) for i in range(4)],
                            dh=[float(m[12 + i].replace(',', '.')) for i in range(4)], ref=ref))
    return out


def _zeit_interp(tloc, t_ve, t_me, d_ve, d_me):
    """Zeitunterschied nach Uhrzeit (Minuten seit Mitternacht, 12-h-periodisch) zwischen VE- und ME-Zeitpunkt."""
    p = 720.0
    a = (tloc - t_ve) % p
    b = (t_me - t_ve) % p
    if a <= b:
        w = a / b
        return d_ve + w * (d_me - d_ve)
    w = (a - b) / (p - b)
    return d_me + w * (d_ve - d_me)


def _hoehe_interp(h, h_ve, h_me, d_ve, d_me):
    if abs(h_ve - h_me) < 1e-6:
        return d_ve
    return d_me + (h - h_me) * (d_ve - d_me) / (h_ve - h_me)


def uebertragen(neb, zeiten):
    ref = neb['ref']
    h = satz_kurve(ref['satz'], zeiten)
    ex, cs = P.scheitel(zeiten, h)
    et, es, ek = [], [], []
    for t, hh, art in ex:
        tloc = ((t / 60.0) + 60.0) % 1440.0                          # UTC+1, Minuten des Tages
        if art == 'H':
            d = _zeit_interp(tloc, ref['t'][0], ref['t'][1], neb['dt'][0], neb['dt'][1])
            k = _hoehe_interp(hh, ref['h'][0], ref['h'][1], neb['dh'][0], neb['dh'][1])
        else:
            d = _zeit_interp(tloc, ref['t'][3], ref['t'][2], neb['dt'][3], neb['dt'][2])
            k = _hoehe_interp(hh, ref['h'][3], ref['h'][2], neb['dh'][3], neb['dh'][2])
        et.append(t)
        es.append(d * 60.0)
        ek.append(k)
    et, es, ek = map(np.array, (et, es, ek))
    fein = np.arange(et[0], et[-1], 600.0)
    return fein + np.interp(fein, et, es), cs(fein) + np.interp(fein, et, ek), [(t + s, hh + k, a) for (t, hh, a), s, k in zip(ex, es, ek)]


_REC, _KOPF = {}, {}


def satz_kurve(name, zeiten):
    """Wie pla_nebenorte.satz_kurve, aber Bestand und Dateikoepfe nur einmal lesen."""
    if not _REC:
        _REC.update({r['name']: r for r in H.load_records() if not r['current']})
    r = _REC.get(name)
    if r is None:
        return None
    pfad = os.path.join(ROOT, r['file'])
    if pfad not in _KOPF:
        _KOPF[pfad] = X.kopf_lesen(pfad)
    kopf = _KOPF[pfad]
    z0, werte, einheit, mer = X.satz_lesen(pfad, name)
    sk = 0.3048 if einheit.startswith('f') else 1.0
    g = {k: (a * sk, X.greenwich(kap, kopf[1][k], mer)) for k, (a, kap) in werte.items() if k in kopf[1]}
    return X.kurve(zeiten, z0 * sk, g, [k for k in kopf[0] if k in g], kopf[1], kopf[2], kopf[3])


def satz_scheitel(name, zeiten):
    h = satz_kurve(name, zeiten)
    return P.scheitel(zeiten, h)[0] if h is not None else None


def vergleich(a, b):
    """Scheitel a gegen b (gleiche Art, naechster in 3 h) -> (median |dt| min, median |dh| m, n)."""
    bt = np.array([x[0] for x in b])
    dts, dhs = [], []
    for t, hh, art in a:
        j = int(np.argmin(np.abs(bt - t)))
        if abs(bt[j] - t) < 3 * 3600 and b[j][2] == art:
            dts.append((t - bt[j]) / 60.0)
            dhs.append(hh - b[j][1])
    if not dts:
        return None
    dts, dhs = np.array(dts), np.array(dhs)
    # Hoehe: Mittelabzug (Bezugsniveau der Bestandssaetze verschieden)
    return float(np.median(np.abs(dts))), float(np.median(np.abs(dhs - np.median(dhs)))), len(dts), float(np.median(dts))


def eichen(nur=None):
    from scipy.spatial import cKDTree
    N = [n for n in lesen() if not nur or n['ref']['name'] in nur]
    print(len(N), 'Nebenhaefen mit vollstaendigen Korrekturen')
    R = [r for r in H.load_records() if not r['current'] and r['lat'] is not None and 40 < r['lat'] < 53 and -8 < r['lon'] < 4]
    bez = set(BEZUG.values())
    T = cKDTree(np.array([(r['lon'] * 111 * math.cos(math.radians(r['lat'])), r['lat'] * 111) for r in R]))
    t0 = 1767225600.0                                                  # 2026-01-01 UTC
    zeiten = np.arange(t0, t0 + 60 * 86400, 600.0)                     # 2 Monate reichen fuer Scheitelstatistik
    erg = []
    for nb in N:
        d, i = T.query((nb['lon'] * 111 * math.cos(math.radians(nb['lat'])), nb['lat'] * 111))
        r = R[i]
        if d > 3 or r['name'] in bez or r['name'] == nb['ref']['satz']:
            continue
        tt, th, ue = uebertragen(nb, zeiten)
        sb = satz_scheitel(r['name'], zeiten)
        if not sb:
            continue
        v = vergleich(ue, sb)
        if not v:
            continue
        # ohne Uebertragung (Bezugshafen selbst) als Vergleich
        v0 = vergleich(satz_scheitel(nb['ref']['satz'], zeiten), sb)
        erg.append((nb['name'], r['name'], d, v[0], v[1], v0[0] if v0 else np.nan, v0[1] if v0 else np.nan, v[3]))
    e = np.array([x[3:] for x in erg], float)
    print('%d Nebenhaefen mit Bestandssatz <= 3 km' % len(erg))
    print('Uebertragung: Scheitelzeit Median %.1f min (P75 %.1f), Hoehe %.2f m (P75 %.2f)' %
          (np.median(e[:, 0]), np.percentile(e[:, 0], 75), np.median(e[:, 1]), np.percentile(e[:, 1], 75)))
    print('Bezugshafen ohne Korrektur: Zeit %.1f min, Hoehe %.2f m' % (np.nanmedian(e[:, 2]), np.nanmedian(e[:, 3])))
    for x in sorted(erg, key=lambda x: -x[3])[:15 if not nur else 99]:
        print('  %-34s ~ %-38s %.1f km  dt %5.1f min (sys %+.0f)  dh %.2f m | ohne %5.1f min' % (x[0][:34], x[1][:38], x[2], x[3], x[7], x[4], x[5]))
    return erg


def neu(argv):
    import datetime as _d
    heute = _d.date.today().strftime('%Y%m%d')
    t0 = 1767225600.0
    zeiten = np.arange(t0 - 86400, t0 + 366 * 86400, 600.0)
    bloecke, namen = [], []
    for nb in lesen():
        if nb['name'] not in NEU:
            continue
        name, la, lo, lage = NEU[nb['name']]
        tt, th, _ue = uebertragen(nb, zeiten)
        z0, w, kopf, rms = P.fit_kurve(tt, th)
        print('%-52s Bezug %-28s Z0 %.2f  M2 %.3f@%.0f  Fit-Rest %.3f m' % (name, nb['ref']['name'], z0, w['M2'][0], w['M2'][1], rms))
        if rms > FIT_MAX:
            print('   -> Fit-Rest > %.2f m, entfaellt' % FIT_MAX)
            continue
        z = ['#', '# BEGIN HOT COMMENTS', '# country: France',
             '# source: SHOM Annuaire des marees 2023, ports rattaches (%s)' % nb['ref']['name'][:30],
             '# note: Uebertragung von %s: PM %+d/%+d min, BM %+d/%+d min (VE/ME), Hoehen %+.2f/%+.2f/%+.2f/%+.2f m; '
             % (nb['ref']['satz'], nb['dt'][0], nb['dt'][1], nb['dt'][3], nb['dt'][2], *nb['dh']),
             '# note: SHOM-Regel (Zeit nach Uhrzeit, Hoehe nach Scheitelhoehe), Jahr 2026 harmonisch gefittet, Rest %.3f m;' % rms,
             '# note: Eichung an 217 Nebenhaefen mit Bestandssatz: Scheitel 4,4 min / 0,06 m (Brest-Gruppe 2-4 min).',
             '# note: Position: %s. py/shom_annuaire_nebenhaefen.py' % lage,
             '# date_imported: %s' % heute, '# datum: Zero hydrographique (SHOM)', '# confidence: 6',
             '# !units: meters', '# !longitude: %.5f' % lo, '# !latitude: %.5f' % la,
             name, '+00:00 :Europe/Paris', '%.4f meters' % z0]
        for k in kopf[0]:
            z.append('%-16s%.4f  %.2f' % (k, w[k][0], w[k][1]) if k in w and w[k][0] >= 0.00005 else 'x 0 0')
        bloecke.append('\n'.join(z))
        namen.append(name)
    if '--schreiben' not in argv or not bloecke:
        return
    import csv
    from sicher_schreiben import schreiben as sch
    t = open(P.DATEI, encoding='iso-8859-1').read()
    for n in namen:
        assert '\n' + n + '\n' not in t, n
    sch(P.DATEI, t.rstrip('\n') + '\n' + '\n'.join(bloecke) + '\n')
    with open(os.path.join(ROOT, 'harmonics/help/neu_pruefen_%s.csv' % heute), 'a', newline='', encoding='utf-8') as fh:
        csv.writer(fh).writerows([('harmonics_utide_tidetables.txt', n) for n in namen])
    print('->', P.DATEI)


if __name__ == '__main__':
    if sys.argv[1:2] == ['neu']:
        neu(sys.argv[2:])
    elif sys.argv[1:2] == ['eichen']:
        eichen(sys.argv[2:])
    else:
        print(__doc__)
