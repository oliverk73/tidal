#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AHO-Tafelfits (PNG, Timor-Leste) ueber mehrere Ausgaben neu fitten (10.11.2026).

Anlass Salomonen (py/aho_salomonen.py --jahre): Einjahres-Scheitelfits an 0,1-m-gerundeten Tafeln streuen
zwischen den Jahren 1-15 %, AHO rechnet aber jahrelang mit denselben Konstanten -> Mehrjahres-Fit.
Ausgaben aus dem Webarchiv (hydro.gov.au/prodserv/publications/*NTT_<jahr>.pdf; Schnappschuesse ueber 5 MiB
sind dort teils abgeschnitten, PNGNTT_2024 und frueher TLNTT_2023 fehlen deshalb).

Ablauf je Hafen: Einjahres-Fits, Gegenprobe (2026-Fit sagt die anderen Jahrgaenge voraus; deutlich schlechter
als der eigene Fit = AHO hat die Grundlage gewechselt -> Jahrgang ausgelassen), gemeinsamer Fit ueber die
stimmigen Jahrgaenge. Ziel: die Saetze in harmonics_utide_tidetables.txt mit Quellzeile "AHO <Land> National
Tide Tables 2026", Zuordnung ueber die naechste Buchposition (<= 15 km). Ersetzt werden nur Z0, Tidenzeilen
und source/note/utide-Zeilen; Name, Position und uebrige Kopfzeilen (Olivers Korrekturen) bleiben.

Usage: venv/bin/python py/aho_mehrjahr.py png|timor [--schreiben]
"""
import datetime as dt
import os
import re
import sys

import numpy as np
import pdfplumber

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import health_check as H                                           # noqa: E402
import qld_msq_fit as Q                                            # noqa: E402
import scheitelfit as SF                                           # noqa: E402
import xtide_modell as X                                           # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ZIEL = os.path.join(ROOT, 'harmonics/utide/harmonics_utide_tidetables.txt')
MONATE = ['JANUARY', 'FEBRUARY', 'MARCH', 'APRIL', 'MAY', 'JUNE', 'JULY', 'AUGUST', 'SEPTEMBER', 'OCTOBER', 'NOVEMBER', 'DECEMBER']
T = os.path.join(ROOT, 'tide_tables')
REGION = {
    'png': dict(kopf=re.compile(r'(?:PAPUA NEW GUINEA|AUSTRALIA, QUEENSLAND) - (.+)'),
                pdfs=[f'{T}/png_aho/PNGNTT_2023_wb.pdf', f'{T}/png_aho/PNGNTT_2025_wb.pdf', f'{T}/png_aho/All_data_2026_png.pdf'],
                quelle='AHO Papua New Guinea National Tide Tables 2026', buch='Papua New Guinea National Tide Tables'),
    'timor': dict(kopf=re.compile(r'TIMOR-LESTE - (.+)'),
                  pdfs=[f'{T}/timor_leste/TLNTT_2024_wb.pdf', f'{T}/timor_leste/TLNTT_2025_wb.pdf', f'{T}/timor_leste/TLNTT_2026_wb.pdf'],
                  quelle='AHO Timor-Leste National Tide Tables 2026', buch='Timor-Leste National Tide Tables'),
}


def lesen(pdf, kopfre):
    """-> {(Buchname, Jahr): dict(lat, lon, zone, t, h)}"""
    orte = {}
    for p in pdfplumber.open(pdf).pages:
        text = p.extract_text() or ''
        m = kopfre.search(text)
        if not m or 'HIGH AND LOW WATERS' not in text:
            continue
        name = m.group(1).strip()
        jahr = int(re.search(r'YEAR (\d{4})', text).group(1))
        g = re.search(r'LAT (\d+)° (\d+)´ ([NS])\s+LONG (\d+)° (\d+)´ ([EW])', text)
        lat = (int(g.group(1)) + int(g.group(2)) / 60) * (-1 if g.group(3) == 'S' else 1)
        lon = (int(g.group(4)) + int(g.group(5)) / 60) * (-1 if g.group(6) == 'W' else 1)
        zone = int(re.search(r'TIME ZONE ([+-]\d{4})', text).group(1)) // 100
        o = orte.setdefault((name, jahr), dict(lat=lat, lon=lon, zone=zone, t=[], h=[]))
        w = p.extract_words()
        kopf = sorted((x['x0'], MONATE.index(x['text'])) for x in w if x['text'] in MONATE)
        zeitx = sorted({round(x['x0']) for x in w if x['text'] == 'Time'})
        hoehen = [x for x in w if re.fullmatch(r'-?\d\.\d', x['text'])]
        tage = [x for x in w if re.fullmatch(r'\d{1,2}', x['text'])]
        for x in w:
            if not re.fullmatch(r'\d{4}', x['text']) or x['top'] < 115:
                continue
            k = min(range(len(zeitx)), key=lambda i: abs(zeitx[i] - x['x0']))
            if abs(zeitx[k] - x['x0']) > 4:
                continue
            monat = kopf[k // 2][1] + 1
            tag = max((d for d in tage if zeitx[k] - 22 < d['x0'] < zeitx[k] - 3 and d['top'] <= x['top'] + 1),
                      key=lambda d: d['top'])
            hh = [y for y in hoehen if abs(y['top'] - x['top']) < 1.5 and 15 < y['x0'] - x['x0'] < 35]
            if len(hh) != 1:
                continue
            hm = int(x['text'])
            t = dt.datetime(jahr, monat, int(tag['text']), hm // 100, hm % 100, tzinfo=dt.timezone.utc) + dt.timedelta(hours=zone)
            o['t'].append(t.timestamp())
            o['h'].append(float(hh[0]['text']))
    return orte


def main(argv):
    reg = REGION[argv[0]]
    schreib = '--schreiben' in argv
    kopf = X.kopf_lesen(ZIEL)
    namen, speeds, arg, fak = kopf
    nutz = SF.konstituenten(namen, SF.CONSTIT_67)
    daten = {}
    for pdf in reg['pdfs']:
        for k, v in lesen(pdf, reg['kopf']).items():
            daten[k] = v
    jahre = sorted({j for _n, j in daten})
    haefen = sorted({n for n, _j in daten})
    print('Jahrgaenge', jahre, '-', len(haefen), 'Haefen')
    ziele = [r for r in H.load_records() if not r['current'] and r['lat'] is not None and r['file'].endswith('harmonics_utide_tidetables.txt')]
    L = open(ZIEL, encoding='iso-8859-1').read().rstrip('\n').split('\n')
    mit_quelle = set()
    for i, z in enumerate(L):
        if z.startswith('# source: ' + reg['quelle']):
            e = i
            while L[e].startswith('#'):
                e += 1
            mit_quelle.add(L[e])
    ziele = [r for r in ziele if r['name'] in mit_quelle]
    heute = dt.date.today().strftime('%Y%m%d')
    ersatz = {}
    for r in ziele:
        kand = [(H.km(r, {'lat': daten[(n, 2026)]['lat'], 'lon': daten[(n, 2026)]['lon']}), n) for n in haefen if (n, 2026) in daten]
        # zuerst ueber den Namen (Oliver verschiebt Saetze auf der Karte: Mantarlido (Buku Seritutun) lag Hera Offshore naeher)
        wort = lambda s: {w for w in re.split(r'[^a-z]+', s.lower()) if len(w) > 3}          # noqa: E731
        nk = [k for k in kand if wort(k[1].split('(')[0]) & wort(r['name'].split(',')[0]) and k[0] <= 15]
        km, buch = min(nk or kand)
        if km > 15:
            print('  %-40s kein Buchhafen in 15 km (%.0f km %s)' % (r['name'][:40], km, buch))
            continue
        fit = {}
        for j in jahre:
            if (buch, j) not in daten:
                continue
            d = daten[(buch, j)]
            t, h = np.array(d['t']), np.array(d['h'])
            o = np.argsort(t)
            fit[j] = (t[o], h[o], *SF.fit(t[o], h[o], nutz, speeds, arg, fak))
        t26, h26, z26, w26 = fit[2026]
        eigen = SF.guete(t26, h26, z26, w26, kopf, versatz=False)[0]
        gut, probe = [], []
        for j, (t, h, _z, _w) in sorted(fit.items()):
            rj = SF.guete(t, h, z26, w26, kopf, versatz=False)[0]
            probe.append('%d %.1f' % (j, rj * 100))
            if rj <= max(1.6 * eigen, eigen + 0.01):
                gut.append(j)
        t = np.concatenate([fit[j][0] for j in gut])
        h = np.concatenate([fit[j][1] for j in gut])
        z0, w = SF.fit(t, h, nutz, speeds, arg, fak)
        rr, tm, _ = SF.guete(t, h, z0, w, kopf, versatz=False)
        dneu = 100 * H.curve_diff(Q.rec(w), r)[1]
        streu = max(100 * H.curve_diff(Q.rec(fit[a][3]), Q.rec(fit[b][3]))[1] for a in fit for b in fit) if len(fit) > 1 else 0
        print('  %-40s <- %-22s %4.1f km | Gegenprobe cm %s | Jahre %s | Treue %.1f cm/%2.0f min | neu vs. Bestand %4.1f %%, Einjahres-Streuung %4.1f %%' % (
            r['name'][:40], buch[:22], km, ', '.join(probe), gut, rr * 100, tm, dneu, streu))
        ersatz[r['name']] = (
            ['# source: AHO %s %d-%d, HW/LW, Scheitelfit' % (reg['buch'], gut[0], gut[-1]),
             '# note: %s Tafelfit %d-%d (py/aho_mehrjahr.py): %d Scheitel, Treue %.1f cm / %.0f min; ersetzt den Einjahres-Fit 2026.'
             % (heute, gut[0], gut[-1], len(t), rr * 100, tm),
             '# utide: pts=%d period=%d-01-01..%d-12-31 const=%d' % (len(t), gut[0], gut[-1], len(nutz))],
            '%.4f meters' % z0,
            ['%-15s %.4f  %.2f' % (c, *w[c]) if c in w and w[c][0] >= 0.00005 else 'x 0 0' for c in namen])
    if not schreib:
        return
    from sicher_schreiben import schreiben
    L = open(ZIEL, encoding='iso-8859-1').read().rstrip('\n').split('\n')     # frisch lesen
    for name, (noten, z0z, tz) in ersatz.items():
        k = [i for i, x in enumerate(L) if x == name and i + 1 < len(L) and L[i + 1].startswith(('+', '-')) and ':' in L[i + 1]]
        assert len(k) == 1, (name, k)
        e = k[0]
        a = e
        while L[a - 1].startswith('#') and L[a - 1] != '#':
            a -= 1
        kopfz = [x for x in L[a:e] if not x.startswith(('# source:', '# utide:'))
                 and not (x.startswith('# note:') and ('Tafelfit' in x or 'Scheitel' in x))]
        pos = next(n for n, x in enumerate(kopfz) if x.startswith('# country:')) + 1
        kopfz = kopfz[:pos] + noten + kopfz[pos:]
        assert L[e + 2].endswith('meters'), (name, L[e:e + 3])
        L[a:e + 3 + len(tz)] = kopfz + [L[e], L[e + 1], z0z] + tz
    schreiben(ZIEL, '\n'.join(L) + '\n')
    print('->', len(ersatz), 'Saetze aktualisiert')


if __name__ == '__main__':
    main(sys.argv[1:])
