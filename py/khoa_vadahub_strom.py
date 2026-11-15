#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Korea: Gezeitenstrom-Konstanten aus Umweltgutachten (vadahub.go.kr, 조화상수_조류, tb_hidcnst_tdcr), Oliver 14.11.2026.

Quelle: quellen/tide_tables/korea/vadahub/khoa_haeyeok_조류.json (1826 Zeilen, 236 Messpunkte, 2013-2021, meist 15 Tage).
Brauchbar sind nur Punkte mit Ost- (동방) und Nordkomponente (북방), je Amplitude (진폭, cm/s) und Phase (지각) fuer
M2 S2 K1 O1 an der Oberflaeche (표층): 64 Punkte; die uebrigen haben nur Phasen ohne Amplituden.
Phase wie beim Gezeitenteil (py/khoa_vadahub.py, an 36 Pegeln geprueft): kappa in KST -> g = kappa - 9 h * speed.
Satz: Hauptachse aus der M2-Ellipse; die vier Tiden auf die Achse projiziert (Knoten). Uebrige Tiden nach Gruppen vom
naechsten Mess-/Tafelpegel (khoa_vadahub.gruppe/REF_DATEI): halbtaegig wie M2 bzw. S2-Gruppe wie S2, eintaegig wie K1
bzw. O1-Gruppe wie O1 (Verhaeltnis und Phasenabstand des Wasserstands); Flachwasser und Langperiode nicht (ortsabhaengig).
Pruefung: Phase M2 Oberflaeche gegen mittlere Tiefe (중층) <= 30 Grad (Gezeitenstrom ist ueber die Tiefe fast gleichphasig,
grobe Tippfehler fallen so auf); mehrere Gutachten am selben Ort komplex gemittelt.
Ergebnis: quellen/tidal_streams/korea_vadahub/stationen.json (fuer Rohreihe/Kompass) + harmonics/help/khoa_vadahub_strom.csv.

Usage: venv/bin/python py/khoa_vadahub_strom.py
"""
import cmath
import collections
import csv
import datetime as dt
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import health_check as H                                            # noqa: E402
import khoa_vadahub as KV                                           # noqa: E402
import stroemung_kopplung as K                                      # noqa: E402
import xtide_modell as X                                            # noqa: E402

ROOT = K.ROOT
QUELLE = os.path.join(ROOT, 'quellen/tide_tables/korea/vadahub/khoa_haeyeok_조류.json')
D = os.path.join(ROOT, 'quellen/tidal_streams/korea_vadahub')
K4 = ['M2', 'S2', 'K1', 'O1']
CMS_KN = 0.0194384449


def punkte():
    namen, sp, arg, fak = K.KOPF
    R = json.load(open(QUELLE, encoding='utf-8'))
    st = collections.defaultdict(dict)
    meta = {}
    for r in R:
        k = (r['docSno'], r['staNo'])
        st[k][(r['wtchWtdpSeNm'], r['tdcrDrcSeNm'], r['tdcrIemSeNm'])] = r
        meta[k] = r
    out = []
    for k, v in st.items():
        def vek(tiefe):
            if not all((tiefe, d, i) in v for d in ('동방', '북방') for i in ('지각', '진폭')):
                return None
            z = {}
            for c in K4:
                kc = c.lower()
                try:
                    ue = v[(tiefe, '동방', '진폭')][kc] * cmath.exp(-1j * math.radians(v[(tiefe, '동방', '지각')][kc] - 9 * sp[c]))
                    un = v[(tiefe, '북방', '진폭')][kc] * cmath.exp(-1j * math.radians(v[(tiefe, '북방', '지각')][kc] - 9 * sp[c]))
                except TypeError:
                    return None
                z[c] = (ue, un)                                     # cm/s, Greenwich, z = A e^(-ig)
            return z
        o, m = vek('표층'), vek('중층')
        if not o:
            continue
        r = meta[k]
        try:
            t0 = dt.date(int(r['strYr']), int(r['strMnth']), int(r['strDd']))
            t1 = dt.date(int(r['endYr']), int(r['endMnth']), int(r['endDd']))
        except (TypeError, ValueError):
            t0 = t1 = None
        out.append(dict(doc=k[0], sta=k[1], titel=r['evlDocNm'], lat=r['staLa'], lon=r['staLo'], ob=o, mi=m, t0=t0, t1=t1))
    return out


def achse(z):
    """Hauptachse (Grad rechtweisend, 0-180) der M2-Ellipse."""
    ue, un = z['M2']
    best = max(range(0, 180), key=lambda t: abs(ue * math.sin(math.radians(t)) + un * math.cos(math.radians(t))))
    return float(best)


def projiziert(z, th):
    s, c = math.sin(math.radians(th)), math.cos(math.radians(th))
    return {k: ue * s + un * c for k, (ue, un) in z.items()}


def main(argv):
    namen, sp, arg, fak = K.KOPF
    P = punkte()
    print(len(P), 'Punkte mit Oberflaeche Ost/Nord')
    # gleicher Ort (<= 200 m) aus mehreren Gutachten: komplex mitteln
    gr = []
    for p in P:
        for g in gr:
            if abs(g[0]['lat'] - p['lat']) < 0.002 and abs(g[0]['lon'] - p['lon']) < 0.0025:
                g.append(p)
                break
        else:
            gr.append([p])
    recs = H.load_records()
    refs = [r for r in recs if not r['current'] and r['lat'] and KV.REF_DATEI.search(os.path.basename(r['file']))]
    zeilen, stationen = [], {}
    for g in gr:
        p = g[0]
        z = {c: (sum(q['ob'][c][0] for q in g) / len(g), sum(q['ob'][c][1] for q in g) / len(g)) for c in K4}
        th = achse(z)
        pr = projiziert(z, th)
        tief_ok = True
        if p['mi']:
            pm = projiziert(p['mi'], th)['M2']
            d = abs((math.degrees(cmath.phase(pr['M2']) - cmath.phase(pm)) + 180) % 360 - 180)
            tief_ok = d <= 30 or abs(pm) < 0.3 * abs(pr['M2'])
        ref = min(refs, key=lambda r: H.km({'lat': p['lat'], 'lon': p['lon']}, r))
        rkm = H.km({'lat': p['lat'], 'lon': p['lon']}, ref)
        _z0, rw, re_, mer = X.satz_lesen(ref['file'], ref['name'])
        rsp = X.kopf_lesen(ref['file'])[1]
        rg = {c: (a, X.greenwich(g_, rsp[c], mer)) for c, (a, g_) in rw.items() if c in rsp and a > 0}
        konst = {c: (abs(pr[c]) * CMS_KN, (-math.degrees(cmath.phase(pr[c]))) % 360) for c in K4}
        for c, (a, g_) in rg.items():
            if c in K4:
                continue
            basis = KV.gruppe(c, sp)
            if basis not in K4 or basis not in rg or rg[basis][0] <= 0.002:
                continue
            if not (sp[c] > 10):                                    # nur ein-/halbtaegig, keine Langperiode
                continue
            if c.startswith(('M4', 'M6', 'M8', 'MS', 'MN', 'MK', 'SK', '2M', '3M', '2S', 'S4', 'S6')):
                continue
            fa = a / rg[basis][0]
            konst[c] = (konst[basis][0] * fa, (konst[basis][1] + g_ - rg[basis][1]) % 360)
        m2, s2 = konst['M2'][0], konst['S2'][0]
        k1, o1 = konst['K1'][0], konst['O1'][0]
        tage = (p['t1'] - p['t0']).days if p['t0'] else None
        key = '%s/%s' % (p['doc'], p['sta'])
        stationen[key] = dict(lat=p['lat'], lon=p['lon'], achse=th, titel=p['titel'],
                              ob={c: [[z[c][0].real, z[c][0].imag], [z[c][1].real, z[c][1].imag]] for c in K4},
                              konst={c: list(v) for c, v in konst.items()}, ref=ref['name'], ref_km=round(rkm, 1),
                              t0=str(p['t0']), t1=str(p['t1']), anzahl=len(g), tiefe_ok=tief_ok)
        zeilen.append(dict(key=key, lat=p['lat'], lon=p['lon'], tage=tage, anzahl=len(g), achse=th, m2_kn=round(m2, 3),
                           s2_kn=round(s2, 3), k1_kn=round(k1, 3), o1_kn=round(o1, 3), tiefe_ok=tief_ok,
                           ref=ref['name'], ref_km=round(rkm, 1), titel=p['titel']))
        print('%-22s %8.4f %9.4f %3s T  M2 %.2f S2 %.2f K1 %.2f O1 %.2f kn  Achse %3.0f  Tiefe %s  Ref %4.1f km' % (
            key, p['lat'], p['lon'], tage, m2, s2, k1, o1, th, 'ok' if tief_ok else 'ABWEICHUNG', rkm))
    os.makedirs(D, exist_ok=True)
    json.dump(stationen, open(os.path.join(D, 'stationen.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
    with open(os.path.join(ROOT, 'harmonics/help/khoa_vadahub_strom.csv'), 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=list(zeilen[0]))
        w.writeheader()
        w.writerows(zeilen)
    print(len(zeilen), 'Orte')


if __name__ == '__main__':
    main(sys.argv[1:])
