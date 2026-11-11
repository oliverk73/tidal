#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Korea: Gezeitenkonstanten aus Umweltgutachten (vadahub.go.kr, 해역이용협의DB_해양물리 / 조화상수_조석), 11.11.2026.

Quelle: vadahub.go.kr -> 해역이용협의DB_해양물리 -> 조화상수_조석 (tb_hidcnst_ebbf, 425 Zeilen, 2013-2021). Die Seite
sperrt Skripte; im Browser (Claude in Chrome) geladen und als tide_tables/korea/vadahub/khoa_haeyeok_조석.json
gespeichert. Je Messpunkt eine Zeile 지각 (Phase kappa) und eine Amplitudenzeile (진폭/반조차 in cm, 반조차(m) in m)
fuer M2 S2 K1 O1; meist ein Monat Messung.
Phase: kappa in KST -> Greenwich g = kappa - 9 h * Geschwindigkeit (an 36 Punkten mit Messsatz <= 3 km geprueft:
M2 -99, S2 -92, K1 +134, O1 +126 Grad Median = 9 h * speed).

Satzbau: M2/S2/K1/O1 aus dem Gutachten (mehrere Messungen am selben Ort komplex gemittelt), alle anderen Tiden vom
naechsten Mess-/Tafelsatz (REF) nach Gruppen uebertragen: halbtaegig wie M2 (S2-Gruppe K2/T2/R2 wie S2), eintaegig
wie K1 (O1-Gruppe Q1/2Q1/RHO1/SIGMA1 wie O1), Flachwasser M_n wie M2^n, Langperiode unveraendert. Faktor
= Amplitudenverhaeltnis, Phase = Phasendifferenz (Greenwich).
Pruefung (--pruefen): an Punkten mit Messsatz <= 3 km Kurvenabstand neu gegen Messsatz, Vergleich mit dem naechsten
Satz ausserhalb 3 km (= was man ohne Gutachten haette).

Auswahl (--schreiben, Oliver 11.11.2026 "ja"): kein Satz in 10 km, Messpunkt <= 3 km vor der Kueste und nicht an Land,
M2 >= 0,1 m, und Nachbarregel: Abstand (4 Tiden) zum aehnlichsten der 3 naechsten Mess-/Tafelsaetze <= 15 %. An den
30 Kontrollpunkten erkennt die Regel 5 von 6 grob falschen Gutachtenwerten (Tando, Boryeong, Mokpo Bukhang, Haeundae,
Wolmido) und verwirft 1 von 24 guten (Ulsan). Mit Nachbar < 10 km ist der Nachbar besser (Median 3,2 gegen 4,0 %).

Usage: venv/bin/python py/khoa_vadahub.py --pruefen | --schreiben
"""
import cmath
import collections
import datetime as dt
import json
import math
import os
import re
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import health_check as H                                           # noqa: E402
import qld_msq_fit as Q                                            # noqa: E402
import scheitelfit as SF                                           # noqa: E402
import xtide_modell as X                                           # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QUELLE = os.path.join(ROOT, 'tide_tables/korea/vadahub/khoa_haeyeok_조석.json')
ZIEL = os.path.join(ROOT, 'harmonics/utide/harmonics_utide_tidetables.txt')
K4 = ['M2', 'S2', 'K1', 'O1']
REF_DATEI = re.compile(r'utide_observations|ticon|utide_tidetables|khoa')
S2_GRUPPE = {'K2', 'T2', 'R2'}
O1_GRUPPE = {'Q1', '2Q1', 'RHO1', 'SIGMA1'}


def punkte(speeds):
    """-> Liste dict(lat, lon, w={M2:(A,g)...}, n, von, bis, doku) je Ort (Mehrfachmessungen gemittelt)"""
    R = json.load(open(QUELLE, encoding='utf-8'))
    mess = collections.defaultdict(lambda: collections.defaultdict(list))
    for r in R:
        if r['staLa'] is None:
            continue
        k = (r['docSno'], r['staNo'], r['staLa'], r['staLo'], r['strYr'], r['strMnth'], r['strDd'])
        mess[k]['r'] = r
        mess[k][r['hidcnstSeNm']].append([r['m2'], r['s2'], r['k1'], r['o1']])
    einzeln = {}
    for k, v in mess.items():
        r = v['r']
        if len(v['지각']) != 1:
            continue
        amp = None
        for a in ('진폭', '반조차', '반조차(cm)'):
            if len(v[a]) == 1:
                amp = [x / 100.0 for x in v[a][0]]
        if len(v['반조차(m)']) == 1:
            amp = list(v['반조차(m)'][0])
        if amp is None or None in amp or None in v['지각'][0]:
            continue
        if amp[0] > 8:                                               # cm unter falschem Etikett
            amp = [x / 100.0 for x in amp]
        g = [(kap - 9 * speeds[c]) % 360 for kap, c in zip(v['지각'][0], K4)]
        # gleiche Messung in mehreren Gutachten -> einmal
        sk = (round(r['staLa'], 3), round(r['staLo'], 3), r['strYr'], r['strMnth'], r['strDd'])
        einzeln[sk] = dict(lat=r['staLa'], lon=r['staLo'], z={c: cmath.rect(a, math.radians(gg)) for c, a, gg in zip(K4, amp, g)},
                           von='%s-%s-%s' % (r['strYr'], r['strMnth'], r['strDd']), bis='%s-%s-%s' % (r['endYr'], r['endMnth'], r['endDd']),
                           doku=r['evlDocNm'], dokno=r['docSno'], sta=r['staNo'])
    orte = collections.defaultdict(list)
    for e in einzeln.values():
        orte[(round(e['lat'], 3), round(e['lon'], 3))].append(e)
    out = []
    for es in orte.values():
        z = {c: sum(e['z'][c] for e in es) / len(es) for c in K4}
        out.append(dict(lat=es[0]['lat'], lon=es[0]['lon'], w={c: (abs(z[c]), math.degrees(cmath.phase(z[c])) % 360) for c in K4},
                        n=len(es), von=min(e['von'] for e in es), bis=max(e['bis'] for e in es), doku=es[0]['doku'], dokno=es[0]['dokno'], sta=es[0]['sta'],
                        streu=max(abs(e['z']['M2'] - z['M2']) / abs(z['M2']) for e in es)))
    return out


def greenwich_satz(r, speeds):
    _z, w, e, mer = X.satz_lesen(r['file'], r['name'])
    f = 0.3048 if e.startswith('f') else 1.0
    return {c: (a * f, X.greenwich(g, speeds[c], mer)) for c, (a, g) in w.items() if c in speeds and a > 0}


def gruppe(c, speeds):
    if c in K4:
        return c
    if c in S2_GRUPPE:
        return 'S2'
    if c in O1_GRUPPE:
        return 'O1'
    s = speeds[c]
    if s < 5:
        return None                                                  # Langperiode unveraendert
    if s < 20:
        return 'K1'
    if s < 35:
        return 'M2'
    return 'M%d' % round(s / speeds['M2'])                           # Flachwasser ~ M2^n


def uebertragen(p, ref, speeds):
    """vier Gutachten-Tiden + Nebentiden des Referenzsatzes nach Gruppen"""
    fak = {}
    for c in K4:
        if c in ref and ref[c][0] > 0.002:
            fak[c] = (p['w'][c][0] / ref[c][0], p['w'][c][1] - ref[c][1])
        else:
            fak[c] = (1.0, 0.0)
    for n in range(2, 9):
        fa, dg = fak['M2']
        fak['M%d' % (2 * n)] = (fa ** n, n * dg)
    w = {}
    for c, (a, g) in ref.items():
        if c in K4:
            continue
        gr = gruppe(c, speeds)
        if gr is None:
            w[c] = (a, g)
        elif gr in fak:
            fa, dg = fak[gr]
            w[c] = (a * fa, (g + dg) % 360)
        else:
            w[c] = (a, g)
    w.update({c: p['w'][c] for c in K4})
    return w


# Namen (Gutachtentitel + OSM, 11.11.2026): (lat, lon) -> (Name, Provinz)
NAMEN = {
    (33.4931, 126.4005): ('Hagwi-hang (Jeju-do)', 'Jeju'),
    (33.5649, 126.8260): ('Haengwon-ri (Jeju-do)', 'Jeju'),
    (34.1972, 126.5184): ('Solji-hang (Nohwado)', 'South Jeolla'),
    (34.2148, 126.7596): ('Moseo-hang (Cheongsando)', 'South Jeolla'),
    (34.2589, 127.0072): ('Deogu-hang (Saengildo)', 'South Jeolla'),
    (34.3936, 126.6474): ('Daldo (Wando)', 'South Jeolla'),
    (34.4683, 126.9756): ('Noryeok-hang (Jangheung)', 'South Jeolla'),
    (34.5309, 126.7763): ('Gangjin-man (Sin-gi-ri)', 'South Jeolla'),
    (34.5839, 127.7212): ('Wolhodo (Yeosu)', 'South Jeolla'),
    (34.5864, 127.6550): ('Jedo (Yeosu)', 'South Jeolla'),
    (34.5953, 127.0992): ('Deungnyangdo (Goheung)', 'South Jeolla'),
    (34.5956, 127.0992): ('Deungnyangdo (Goheung)', 'South Jeolla'),
    (34.6118, 127.7214): ('Dolsan-hang (Yeosu)', 'South Jeolla'),
    (34.6375, 127.0867): ('Gunhak-hang (3 km ESE, Boseong)', 'South Jeolla'),
    (34.7552, 126.0690): ('Hanun-ri (Anjwado)', 'South Jeolla'),
    (34.8703, 127.5131): ('Nongju-ri (Suncheon-man)', 'South Jeolla'),
    (34.9206, 126.3772): ('Guro-ri (Muan)', 'South Jeolla'),
    (34.9294, 126.2717): ('Maehwado (3 km ENE, Aphaedo)', 'South Jeolla'),
    (34.9605, 126.2960): ('Sinwol-hang (Muan)', 'South Jeolla'),
    (34.9861, 126.3050): ('Nae-ri (Unnam, Muan)', 'South Jeolla'),
    (35.2704, 126.1612): ('Songi-do (Yeonggwang)', 'South Jeolla'),
    (35.3847, 129.3677): ('Jinha (Ulsan)', 'Ulsan'),
    (35.5774, 126.5103): ('Mohang-hang (Buan)', 'North Jeolla'),
    (35.5849, 126.6132): ('Gomso-hang (Buan)', 'North Jeolla'),
    (36.5235, 126.4452): ('Jukdo (Hongseong)', 'South Chungcheong'),
    (36.5885, 126.4374): ('Gungni-hang (Hongseong)', 'South Chungcheong'),
    (36.8341, 126.3214): ('Gudo-hang (Seosan)', 'South Chungcheong'),
    (36.8833, 126.3513): ('Hori-hang (3 km NNE, Seosan)', 'South Chungcheong'),
    (36.9971, 125.9953): ('Uldo (3 km S, Ongjin)', 'Incheon'),
    (37.0195, 126.7220): ('Goon-hang (3 km SW, Hwaseong)', 'Gyeonggi'),
    (37.0266, 126.6249): ('Dangjin-hang (Songak)', 'South Chungcheong'),
}


def auswahl(P, recs, refs, speeds):
    import osm_land
    L = osm_land.Land([(p['lat'], p['lon']) for p in P])
    v4 = lambda w: Q.rec({c: v for c, v in w.items() if c in K4})   # noqa: E731
    out = []
    for p in P:
        if min(H.km(p, r) for r in recs) <= 10:
            continue
        if L.kueste_km(p['lat'], p['lon'], rmax=10) > 3 or L.ist_land(p['lat'], p['lon']) or p['w']['M2'][0] < 0.1:
            continue
        nb = sorted((H.km(p, r), i) for i, r in enumerate(refs))[:3]
        en = [100 * H.curve_diff(v4(p['w']), v4(greenwich_satz(refs[i], speeds)))[1] for _km, i in nb]
        if min(en) <= 15:
            p['nachbarn'] = ', '.join('%s %.0f km %.0f %%' % (refs[i]['name'].split(',')[0], km, e) for (km, i), e in zip(nb, en))
            p['ref'] = refs[nb[0][1]]
            p['ref_km'] = nb[0][0]
            out.append(p)
    return out


def main(argv):
    kopf = X.kopf_lesen(ZIEL)
    namen, speeds, arg, fak = kopf
    P = punkte(speeds)
    recs = [r for r in H.load_records() if r['lat'] is not None and not r['current']]
    refs = [r for r in recs if REF_DATEI.search(os.path.basename(r['file']))]
    print('%d Orte (%d Messungen), Streuung M2 zwischen Mehrfachmessungen max %.0f %%' % (
        len(P), sum(p['n'] for p in P), 100 * max(p['streu'] for p in P)))
    if '--pruefen' in argv:
        neu_f, nach_f = [], []
        for p in P:
            d = sorted((H.km(p, r), i) for i, r in enumerate(refs))
            if d[0][0] > 3:
                continue
            mess = refs[d[0][1]]
            weiter = [(km, i) for km, i in d if km > 3][0]
            ref = greenwich_satz(refs[weiter[1]], speeds)
            w = uebertragen(p, ref, speeds)
            e1 = 100 * H.curve_diff(Q.rec(w), mess)[1]
            e2 = 100 * H.curve_diff(Q.rec(ref), mess)[1]
            neu_f.append(e1)
            nach_f.append(e2)
            print('  %-40s %4.1f km | Gutachten+Uebertragung %5.1f %% | Nachbar %-30s %4.1f km %5.1f %%' % (
                mess['name'][:40], d[0][0], e1, refs[weiter[1]]['name'][:30], weiter[0], e2))
        print('Median: Gutachten %.1f %%, Nachbar ohne Gutachten %.1f %% (n=%d)' % (np.median(neu_f), np.median(nach_f), len(neu_f)))
    if '--schreiben' not in argv:
        return
    from sicher_schreiben import schreiben
    A = auswahl(P, recs, refs, speeds)
    heute = dt.date.today().strftime('%Y%m%d')
    tg = np.arange(dt.datetime(2008, 1, 1).timestamp(), dt.datetime(2027, 1, 1).timestamp(), 3600.0)
    T = open(ZIEL, encoding='iso-8859-1').read().rstrip('\n').split('\n')        # frisch lesen, nur anhaengen
    vorhanden = set(T)
    neu, namen_neu = [], []
    for p in sorted(A, key=lambda p: (p['lat'], p['lon'])):
        k = (round(p['lat'], 4), round(p['lon'], 4))
        if k not in NAMEN:
            print('  ohne Namen:', k, p['doku'])
            continue
        ort, prov = NAMEN[k]
        name = ort + ', South Korea'
        if name in vorhanden or name in namen_neu:
            continue
        ref = greenwich_satz(p['ref'], speeds)
        w = uebertragen(p, ref, speeds)
        z0 = -float(SF.hoehe_und_ableitungen(tg, 0.0, w, kopf)[0].min())
        neu += ['#', '# ' + name, '# BEGIN HOT COMMENTS', '# country: South Korea',
                '# source: Korean sea-area-use assessments (vadahub.go.kr)',
                '# date_imported: %s' % heute, '# datum: approx. LAT (Z0 = -Minimum der 19-Jahres-Kurve)', '# confidence: 5',
                '# !units: meters', '# !longitude: %.4f' % p['lon'], '# !latitude: %.4f' % p['lat'], '# province: %s' % prov,
                ('# note: %s Gutachten %s, Messung %s..%s (%d), Punkt %s; Nebentiden von %s (%.0f km)' % (
                    heute, p['dokno'], p['von'], p['bis'], p['n'], p['sta'], p['ref']['name'].split(',')[0], p['ref_km']))[:190],
                ('# note: Nachbarprobe (4 Tiden): %s; py/khoa_vadahub.py' % p['nachbarn'])[:190],
                name, '+00:00 :Asia/Seoul', '%.4f meters' % z0]
        neu += ['%-15s %.4f  %.2f' % (c, *w[c]) if c in w and w[c][0] >= 0.00005 else 'x 0 0' for c in namen]
        namen_neu.append(name)
        print('  neu: %-40s M2 %.3f/%.0f  Z0 %.2f' % (name, *w['M2'], z0))
    schreiben(ZIEL, '\n'.join(T + neu) + '\n')
    aus = os.path.join(ROOT, 'harmonics/help/neu_pruefen_%s.csv' % heute)
    vorher = open(aus, encoding='utf-8').read() if os.path.exists(aus) else 'datei,name\n'
    with open(aus, 'w', encoding='utf-8') as fh:
        fh.write(vorher + ''.join('harmonics_utide_tidetables.txt,"%s"\n' % n for n in namen_neu))
    print('-> %d Saetze, %s' % (len(namen_neu), os.path.relpath(aus, ROOT)))


if __name__ == '__main__':
    main(sys.argv[1:])
