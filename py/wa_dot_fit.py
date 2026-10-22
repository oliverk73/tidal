#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Harmonische Saetze aus den DoT-Pegelreihen Westaustralien (py/wa_dot_einlesen.py).

Oliver 22.10.2026 nach Queensland: "Ja" zu WA. Fit wie py/qld_msq_fit.py (Momentanwert zur vollen Stunde, 67 Konst.
+ Obertiden, Rayleigh unter 400 Tagen, Probe am letzten Jahr, Eigenversatz, Plateau-Probe). Je Station ein Einsatz:
der mit den meisten Messtagen in seinen letzten 10 Jahren (bei Gleichstand der juengere).

Bezugshoehe: LAT / Chart Datum / "Lowest Low Tide" gilt als Kartennull (Z0 aus dem Fit, Pruefregel wie QLD);
"Not Known", "Under Review", "not available", LWM Fremantle 1949 -> Z0 aus dem 19-Jahres-Minimum ("approx. LAT").

--vorschlag schreibt harmonics/help/wa_dot_pegel.tsv (Aktion aus dem Bestand bis 1 km: Messsatz -> vergleich,
nur Tafel-/Buchsatz -> ersetzt (ab 1 Jahr), sonst neu); danach von Hand pruefen, dann ohne --vorschlag fitten.
Usage: venv/bin/python py/wa_dot_fit.py --vorschlag
       venv/bin/python py/wa_dot_fit.py [einsatz ...] [--alle] [--schreiben]  -> harmonics_utide_observations.txt
"""
import csv
import datetime as dt
import os
import re
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import health_check as H                                           # noqa: E402
import qld_msq_fit as Q                                            # noqa: E402
import scheitelfit as SF                                           # noqa: E402
import seine_haropa_fit as S                                       # noqa: E402
import xtide_modell as X                                           # noqa: E402
from sicher_schreiben import schreiben                             # noqa: E402

ROOT = S.ROOT
ZIEL = S.ZIEL
REIHEN = os.path.join(ROOT, 'water_levels/Australia_WA/dot')
LISTE = os.path.join(ROOT, 'harmonics/help/wa_dot_pegel.tsv')
ERGEBNIS = os.path.join(ROOT, 'harmonics/help/wa_dot_fit.csv')
MESSUNG = ('harmonics_utide_observations', 'harmonics_ticon4_worldwide')
KARTENNULL = re.compile(r'^(LAT|Chart Datum|Lowest Low Tide)', re.I)
FELDER = ['einsatz', 'name', 'lat', 'lon', 'aktion', 'bemerkung']


def einsaetze():
    return list(csv.DictReader(open(os.path.join(REIHEN, 'einsaetze.csv'), encoding='utf-8')))


def bestand():
    return [r for r in H.load_records() if r['lat'] and -40 < r['lat'] < -10 and 110 < r['lon'] < 130 and not r['current']]


def ortsname(ort):
    ort = re.sub(r'\s+0\d$', '', ort.strip())                       # "Carnarvon 02", "Bunbury Outer Harbour 02"
    return '%s, Western Australia, Australia' % ort


def vorschlag():
    B = bestand()
    # Station = alle Einsaetze bis 1 km (ESESP01/02/03, CNCAR01/02, TRTRK01/02 sind derselbe Ort unter neuem Code)
    gruppen = []
    for e in einsaetze():
        if not e['lat']:
            continue
        p = {'lat': float(e['lat']), 'lon': float(e['lon'])}
        for g in gruppen:
            if any(H.km(p, {'lat': float(x['lat']), 'lon': float(x['lon'])}) <= 1.0 for x in g):
                g.append(e)
                break
        else:
            gruppen.append([e])
    # bester Einsatz: zuerst aktuelle (Ende ab 2023), dann Messtage in den letzten 10 Jahren des Einsatzes (Wyndham: _04 statt _02)
    def schluessel(e):
        bis = dt.date.fromisoformat(e['bis'])
        von = max(dt.date.fromisoformat(e['von']), bis - dt.timedelta(days=3653))
        return (bis.year >= 2023, (bis - von).days * float(e['abdeckung'] or 0), e['bis'])
    wahl = {g[0]['einsatz']: (None, max(g, key=schluessel)) for g in gruppen}
    zeilen = []
    for st, (_, e) in sorted(wahl.items()):
        if not e['lat']:
            continue
        la, lo = float(e['lat']), float(e['lon'])
        nah = sorted(((H.km({'lat': la, 'lon': lo}, r), r) for r in B), key=lambda x: x[0])
        nah = [(k, r) for k, r in nah if k <= 1.0]
        tage = int(e['tage']) * float(e['abdeckung'] or 0)
        bisj = int(e['bis'][:4])
        peel = -32.75 < la < -32.45 and 115.6 < lo < 115.85      # Peel-Harvey-Aestuar: Dawesville Cut 1994 aenderte die Tide
        if tage < 25:
            aktion, bem = 'weg', 'nur %d Messtage' % tage
        elif peel and bisj < 1995:
            aktion, bem = 'weg', 'Peel-Harvey vor dem Dawesville Cut (1994)'
        elif not nah and (bisj < 1985 or tage < 60):
            aktion, bem = 'weg', 'alt oder kurz (bis %d, %d Messtage), Position laut DoT ungefaehr' % (bisj, tage)
        elif any(r['file'].split('/')[-1].startswith(MESSUNG) for _, r in nah):
            aktion, bem = 'vergleich', 'Messsatz bis 1 km'
        elif nah and tage >= 365:
            aktion, bem = 'ersetzt', 'Tafel-/Buchsatz bis 1 km'
        elif nah:
            aktion, bem = 'vergleich', 'kurz (%d Tage), Tafel-/Buchsatz bis 1 km bleibt' % tage
        else:
            aktion, bem = 'neu', ''
        name = nah[0][1]['name'] if nah else ortsname(e['ort'])
        alt = '; '.join('%s [%s] %.2f km' % (r['name'].split(',')[0], r['file'].split('/')[-1][:22], k) for k, r in nah)
        zeilen.append(dict(einsatz=e['einsatz'], name=name, lat=e['lat'], lon=e['lon'], aktion=aktion,
                           bemerkung='; '.join(x for x in (bem, alt, '%s..%s' % (e['von'], e['bis']), e['datum'][:40]) if x)))
    with open(LISTE, 'w', newline='', encoding='utf-8') as f:
        f.write('# DoT-Einsaetze Westaustralien, Vorschlag py/wa_dot_fit.py --vorschlag %s; aktion von Hand pruefen\n' % dt.date.today())
        w = csv.DictWriter(f, fieldnames=FELDER, delimiter='\t')
        w.writeheader()
        w.writerows(zeilen)
    print('%d Stationen -> %s' % (len(zeilen), os.path.relpath(LISTE, ROOT)))
    for a in ('neu', 'ersetzt', 'vergleich', 'weg'):
        print('  %-9s %d' % (a, sum(z['aktion'] == a for z in zeilen)))


def main(argv):
    if '--vorschlag' in argv:
        return vorschlag()
    kopf = X.kopf_lesen(ZIEL)
    namen, speeds, arg, fak = kopf
    voll = SF.konstituenten(namen, SF.CONSTIT_67) + [k for k in S.OBERTIDEN if k in namen]
    L = open(ZIEL, encoding='iso-8859-1').read().rstrip('\n').split('\n')
    heute = dt.date.today().strftime('%Y%m%d')
    wahl = [a for a in argv if not a.startswith('--')]
    meta = {e['einsatz']: e for e in einsaetze()}
    B = bestand()
    zeilen = []
    for z in csv.DictReader((l for l in open(LISTE, encoding='utf-8') if not l.startswith('#')), delimiter='\t'):
        if wahl and not any(a in z['einsatz'] for a in wahl):
            continue
        if z['aktion'] == 'weg' and '--alle' not in argv:
            continue
        e = meta[z['einsatz']]
        d = pd.read_csv(os.path.join(REIHEN, z['einsatz'] + '.csv'), parse_dates=['time_utc']).set_index('time_utc')['waterlevel_m']
        d = d[d.index.minute == 0]
        ab = [w[3:13] for w in (z.get('bemerkung') or '').replace(';', ' ').split() if w.startswith('ab=')]
        if ab:
            d = d[ab[0]:]
        jm = d.groupby(d.index.year).median()
        print('\n== %s [%s] (%s)\n   Jahresmedian: %s' % (z['name'], z['einsatz'], z['aktion'], ' '.join('%d:%.2f' % (j, v) for j, v in jm.items())))
        s = d[d.index >= d.index[-1] - pd.Timedelta(days=3653)]
        if len(s) < 0.5 * (s.index[-1] - s.index[0]).total_seconds() / 3600:
            g = (s.index.to_series().diff() > pd.Timedelta(days=2)).cumsum().values
            s = max((x for _, x in s.groupby(g)), key=len)
            print('   verstreut: nur %s..%s' % (s.index[0].date(), s.index[-1].date()))
        tage = (s.index[-1] - s.index[0]).days
        if len(s) < 24 * 25:
            print('   zu kurz (%d h)' % len(s))
            continue
        nutz = Q.rayleigh(voll, speeds, namen, tage)
        probe = ''
        if tage >= 2 * 365:
            grenze = s.index[-1] - pd.Timedelta(days=365)
            _, _, pz0, pw, _, _ = Q.fit(s[:grenze], nutz, kopf, speeds, arg, fak)
            te = s[grenze:]
            tt = np.array([i.timestamp() for i in te.index])
            rp = te.values - SF.hoehe_und_ableitungen(tt, pz0, pw, kopf)[0]
            rp = rp[np.abs(rp - np.median(rp)) < 5 * np.std(rp)]
            probe = '%.0f' % (100 * np.sqrt(np.mean(rp ** 2)))
        s, t, z0, w, h, aus = Q.fit(s, nutz, kopf, speeds, arg, fak)
        rms = float(np.sqrt(np.mean((s.values - h) ** 2)))
        tief = h <= np.quantile(h, 0.05)
        plateau = float(np.median(s.values[tief] - h[tief]))
        r2 = 1 - np.var(s.values - h) / np.var(s.values)
        sub = slice(None, None, 7)
        eig = min(range(-30, 31), key=lambda m: np.std(s.values[sub] - SF.hoehe_und_ableitungen(t[sub] - 60 * m, z0, w, kopf)[0]))
        tg = np.arange(dt.datetime(2008, 1, 1).timestamp(), dt.datetime(2027, 1, 1).timestamp(), 1800.0)
        lat_kurve = -float(SF.hoehe_und_ableitungen(tg, 0.0, w, kopf)[0].min())
        la, lo = float(z['lat']), float(z['lon'])
        nah = sorted(((H.km({'lat': la, 'lon': lo}, r), r) for r in B), key=lambda x: x[0])
        nah = [(k, r) for i, (k, r) in enumerate(nah) if k <= 6.0 or (i < 3 and k <= 30.0)]
        vgl = ['%s [%s] %.1f km %.0f%%' % (r['name'].split(',')[0], r['file'].split('/')[-1].replace('harmonics', '').replace('.txt', '')[:18],
                                         k, 100 * H.curve_diff(Q.rec(w), r)[1]) for k, r in nah]
        print('   %d h %s..%s (%d d, %d Konst.)  R2 %.3f  RMS %.3f  Probe %s cm  Eigenversatz %+d  M2 %.3f@%.0f  K1 %.3f  Z0 %.2f (LAT-Kurve %.2f)  Plateau %+.0f cm%s' % (
            len(s), s.index[0].date(), s.index[-1].date(), tage, len(nutz), r2, rms, probe or '-', eig, *w['M2'], w['K1'][0], z0, lat_kurve,
            100 * plateau, ('  %d Ausreisser' % aus) if aus else ''))
        for v in vgl:
            print('      ~ ' + v)
        zeilen.append(dict(einsatz=z['einsatz'], name=z['name'], aktion=z['aktion'], von=s.index[0].date(), bis=s.index[-1].date(), tage=tage,
                           konst=len(nutz), r2='%.4f' % r2, rms_cm='%.1f' % (100 * rms), probe_cm=probe, eigenversatz=eig,
                           m2='%.3f' % w['M2'][0], z0='%.2f' % z0, lat_kurve='%.2f' % lat_kurve, plateau_cm='%.0f' % (100 * plateau),
                           datum_dot=e['datum'], nachbarn=' | '.join(vgl)))
        if z['aktion'] not in ('neu', 'ersetzt'):
            continue
        if plateau > 0.15:
            print('   verworfen: Plateau am Niedrigwasser (trockenfallend)')
            continue
        datum = 'LAT'
        if not KARTENNULL.match(e['datum']):
            datum = 'approx. LAT (Z0 aus 19-Jahres-Minimum)'
            print('   DoT-Bezug "%s" -> Z0 = %.2f' % (e['datum'][:40], lat_kurve))
            z0 = lat_kurve
        elif not -0.1 <= z0 - lat_kurve <= 0.4:
            datum = 'approx. LAT (Z0 aus 19-Jahres-Minimum)'
            print('   Pegelnull %.2f m unter LAT-Kurve -> Z0 = %.2f' % (z0 - lat_kurve, lat_kurve))
            z0 = lat_kurve
        blk = ['#', '# ' + z['name'], '# BEGIN HOT COMMENTS', '# country: Australia',
               '# source: WA DoT tide gauge %s, least squares' % z['einsatz'],     # libtcd: Quelle hoechstens 90 Zeichen
               '# note: Department of Transport Western Australia, %s-min recordings (S3 Tide_Packet).' % (
                   ('%g' % float(e['takt'])) if e['takt'] else '?'),
               '# station_id_context: WADOT-%s' % z['einsatz'], '# date_imported: %s' % heute, '# datum: %s' % datum, '# confidence: 7',
               '# utide: pts=%d period=%s..%s r2=%.4f rms=%.4fm const=%d' % (len(s), s.index[0].date(), s.index[-1].date(), r2, rms, len(nutz)),
               '# note: %s Messfit aus der DoT-Reihe (py/wa_dot_fit.py), Oliver. DoT-Bezug: %s.' % (heute, e['datum'][:60]),
               ('# note: Probe am letzten Messjahr %s cm RMS.' % probe) if probe else '# note: Reihe kuerzer als zwei Jahre, keine Probe.',
               '# note: Position DoT-Kopf (GDA2020; bei historischen Stationen laut DoT nur ungefaehr).',
               '# !units: meters', '# !longitude: %.4f' % lo, '# !latitude: %.4f' % la,
               '# state: Western Australia', z['name'], '+00:00 :Australia/Perth', '%.4f meters' % z0]
        blk += ['%-15s %.4f  %.2f' % (c, *w[c]) if c in w and w[c][0] >= 0.00005 else 'x 0 0' for c in namen]
        if z['name'] in L:
            print('   existiert schon in %s' % os.path.basename(ZIEL))
            continue
        L += blk
    if zeilen and not wahl:
        with open(ERGEBNIS, 'w', newline='', encoding='utf-8') as f:
            wr = csv.DictWriter(f, fieldnames=list(zeilen[0]))
            wr.writeheader()
            wr.writerows(zeilen)
    if '--schreiben' in argv:
        schreiben(ZIEL, '\n'.join(L) + '\n')
        print('->', os.path.relpath(ZIEL, ROOT))


if __name__ == '__main__':
    main(sys.argv[1:])
