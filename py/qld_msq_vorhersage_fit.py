#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MSQ-Vorhersagen (py/download_qld_msq_vorhersage.py): Luecken schliessen, Altsaetze messen (Oliver 26.10.2026).

Je Pegel kleinste Quadrate (wie py/qld_msq_fit.py) auf die Stundenwerte 2026, Probe an 2027, Endfit 2026+2027.
Die Ausgabe 2025 ist an manchen Pegeln mit anderen Konstanten gerechnet (Sweers Island Hub 3,3 statt 5,7 m,
Mossman Mittel 1,97 statt 1,42 m) -- wie bei den BOM-Tafeln, siehe py/bom_scheitelfit.py. Jeder
Bestandssatz bis UMKREIS km wird am selben Probejahr gemessen (RMS nach Hoehenversatz, wie scheitelfit.guete).

Urteil:
  neu       kein Satz im Umkreis -> neuer Satz (harmonics_utide_tidetables.txt)
  ersetzen  bester Bestandssatz ist Alt-/Buch-/Tafelsatz und trifft die amtliche Vorhersage um
            FAKTOR schlechter und mehr als MIND_CM -> neuer Satz unter dessen Namen/Position, alter archiviert
  bleibt    sonst; Messsaetze (utide_observations, TICON) werden nie durch einen Vorhersagefit ersetzt
Achtung: RMS gegen eine Vorhersage misst die Naehe zur amtlichen Rechnung, nicht die Natur -- deshalb nur
gegen Saetze ohne eigene Messung ([[tafelfit-misst-die-tafel]]).

Position: Archiv-Liste harmonics/help/qld_msq_pegel.tsv (gleicher Pegel), sonst POSITION unten.
Usage: venv/bin/python py/qld_msq_vorhersage_fit.py [datei-teil ...] [--schreiben]
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
import xtide_modell as X                                           # noqa: E402
from sicher_schreiben import schreiben                             # noqa: E402

ROOT = H.ROOT
REIHEN = os.path.join(ROOT, 'water_levels/Australia_QLD/msq_vorhersage')
ZIEL = os.path.join(ROOT, 'harmonics/utide/harmonics_utide_tidetables.txt')
ERGEBNIS = os.path.join(ROOT, 'harmonics/help/qld_msq_vorhersage.csv')
UMKREIS, FAKTOR, MIND_CM = 3.0, 2.0, 3.0
# Gegen MSQ-Messreihen geprueft (26.10.2026): MSQ-Fit besser bei Lizard, Kubin, Sweers, Red Island; bei Dauan der
# BOM-Satz knapp besser (11,6 gegen 12,5 cm) -> bleibt. Skardon River: Fluss, Probe 11,7 cm -> kein Satz.
AUSNAHMEN = {'dauan-island': 'bleibt (BOM-Satz trifft die Messung 2011/12 besser)',
             'skardon-river': 'kein Satz (Fluss, Probe 11,7 cm)'}
LOESCHLISTE = os.path.join(ROOT, 'harmonics/help/qld_msq_vorhersage_loeschen.csv')
MESSUNG = ('harmonics_utide_observations.txt', 'harmonics_ticon4_worldwide.txt')
# Pegel ohne Eintrag in der Archiv-Liste: (Name, lat, lon, Quelle)
# Zahl = Koordinaten aus dem CDS-Echtzeit-Feed (4 Stellen), Text = gepruefter Bestandssatz am selben Pegel.
POSITION = {
    'boigu-island': ("Boigu Island, Queensland, Australia", -9.2293, 142.2209, 'CDS-Feed boigultg'),
    'bundaberg': ("Bundaberg (Port), Queensland, Australia", -24.7704, 152.3819, 'CDS-Feed'),
    'cairns': ("Cairns, Queensland, Australia", -16.9277, 145.7788, 'CDS-Feed'),
    'cardwell': ("Cardwell, Queensland, Australia", -18.2637, 146.0262, 'CDS-Feed'),
    'coconut-island-poruma': ("Coconut Island (Poruma), Queensland, Australia", -10.0493, 143.0639, 'CDS-Feed'),
    'cooktown': ("Cooktown, Queensland, Australia", -15.4595, 145.2498, 'CDS-Feed'),
    'karumba': ("Karumba, Queensland, Australia", -17.4883, 140.8347, 'CDS-Feed'),
    'kubin-moa-island': ("Kubin (Moa Island), Queensland, Australia", -10.2360, 142.2145, 'CDS-Feed'),
    'mooloolaba': ("Mooloolaba, Queensland, Australia", -26.6843, 153.1334, 'CDS-Feed'),
    'mourilyan': ("Mourilyan Harbour, Queensland, Australia", -17.6012, 146.1238, 'CDS-Feed'),
    'st-pauls-moa-island': ("St Pauls (Moa Island), Queensland, Australia", -10.1957, 142.3341, 'CDS-Feed'),
    'stephens-island-ugar': ("Stephens Island (Ugar), Queensland, Australia", -9.5049, 143.5468, 'CDS-Feed'),
    'sue-island-warraber': ("Sue Island (Warraber), Queensland, Australia", -10.2042, 142.8222, 'CDS-Feed'),
    'townsville': ("Townsville, Queensland, Australia", -19.2518, 146.8304, 'CDS-Feed'),
    'urangan': ("Urangan, Queensland, Australia", -25.2962, 152.9105, 'CDS-Feed'),
    'urangan-fairway-beacon': ("Urangan (Fairway Beacon), Queensland, Australia", -25.1333, 152.8167, 'Oliver (Karte)'),
    'yam-island-iama': ("Yam Island (Iama), Queensland, Australia", -9.8992, 142.7660, 'CDS-Feed'),
    'badu-island': 'Badu Island, Queensland, Australia',
    'booby-island': 'Booby Island, Queensland, Australia',
    'bugatti-reef-outer': 'Bugatti Reef, Queensland, Australia',
    'darnley-island-erub': 'Darnley Island (Torres Strait), Queensland, Australia',
    'fisherman-s-landing': "Fisherman's Landing, Queensland, Australia",
    'golding-reciprocal-f-l-gladstone': 'Golding Channel (Tannum Sands), Queensland, Australia',
    'goods-island': 'Goods Island (Torres Strait), Queensland, Australia',
    'leggatt-island': 'Leggatt Island, Queensland, Australia',
    'mabuiag-island': 'Mabuiag Island Barge, Queensland, Australia',
    'mackay': 'Mackay Outer Harbour, Queensland, Australia',
    'murray-island-meer': 'Meer Island Barge, Queensland, Australia',
    'no-2-beacon-weipa': 'number-2-beacon-weipa',
    'north-cardinal-beacon-townsville': 'Magnetic Island (North Cardinal Beacon), Queensland, Australia',
    'saibai-island': 'Saibai Island (Torres Strait), Queensland, Australia',
    'southport': 'Southport, Queensland, Australia',
    'tangalooma': 'Tangalooma Jetty, Queensland, Australia',
    'twin-island': 'Twin Island (Torres Strait), Queensland, Australia',
    'weipa': 'Weipa, Queensland, Australia',
    'yorke-island-masig': 'Yorke Island Barge, Queensland, Australia',
}


def position(datei, tsv, bestand):
    code = datei.replace('-tide-gauge-predicted-interval-data', '').replace('-predicted-interval-data', '')
    p = POSITION.get(code)
    if isinstance(p, str):
        if p.endswith('weipa'):
            code = p
        else:
            r = next((r for r in bestand if r['name'] == p), None)
            return (p, r['lat'], r['lon'], 'Bestandssatz am Pegel') if r else None
    elif p:
        return p
    for z in tsv:
        if z['datei'].startswith(code + '-tide-gauge') or z['datei'].startswith(code + '-archived'):
            return z['name'], float(z['lat']), float(z['lon']), 'Archivliste (%s)' % z['posquelle']
    return None


def main(argv):
    kopf = X.kopf_lesen(ZIEL)
    namen, speeds, arg, fak = kopf
    voll = SF.konstituenten(namen, SF.CONSTIT_67) + [k for k in Q.S.OBERTIDEN if k in namen]
    tsv = Q.liste()
    wahl = [a for a in argv if not a.startswith('--')]
    bestand = [r for r in H.load_records() if r['lat'] and -30 < r['lat'] < -8 and 137 < r['lon'] < 155 and not r['current']]
    zeilen, auftraege = [], []
    for f in sorted(os.listdir(REIHEN)):
        if not f.endswith('.csv') or (wahl and not any(a in f for a in wahl)):
            continue
        datei = f[:-4]
        pos = position(datei, tsv, bestand)
        d = pd.read_csv(os.path.join(REIHEN, f), parse_dates=['time_utc']).set_index('time_utc')['waterlevel_m']
        d = d[d.index.minute == 0]
        lern, test = d[d.index.year == 2026], d[d.index.year == 2027]
        d = d[d.index.year >= 2026]
        if pos is None or pos[1] is None or len(lern) < 24 * 300 or len(test) < 24 * 300:
            print('%s: %s' % (datei, 'keine Position' if not pos or pos[1] is None else 'zu kurz'))
            zeilen.append(dict(datei=datei, name=pos[0] if pos else '', urteil='keine Position' if not pos or pos[1] is None else 'zu kurz'))
            continue
        name, la, lo, pq = pos
        _s, _t, z0, w, _h, _a = Q.fit(lern, voll, kopf, speeds, arg, fak)
        tt = np.array([i.timestamp() for i in test.index])
        probe, _dtm, _off = SF.guete(tt, test.values, z0, w, kopf)
        nah = sorted(((H.km({'lat': la, 'lon': lo}, r), r) for r in bestand), key=lambda x: x[0])
        nah = [(k, r) for k, r in nah if k <= UMKREIS]
        mess = []
        for k, r in nah:
            g = SF.bestand([r], r['lat'], r['lon'], kopf, tt, test.values, umkreis=0.01)
            if g:
                mess.append((g[0][2], k, r))
        mess.sort(key=lambda x: x[0])
        code = re.sub(r'-(tide-gauge-)?predicted-interval-data$', '', datei)
        if code in AUSNAHMEN:
            urteil = AUSNAHMEN[code]
        elif not mess:
            urteil = 'neu'
        else:
            best, k, r = mess[0]
            alt = os.path.basename(r['file']) not in MESSUNG
            urteil = 'ersetzen' if alt and best > FAKTOR * probe and best * 100 > MIND_CM else 'bleibt'
        print('%-62s Probe %.1f cm | %s -> %s' % (name[:62], probe * 100,
              '; '.join('%s [%s] %.1f km %.1f cm' % (r['name'].split(',')[0][:28], os.path.basename(r['file'])[9:24], k, b * 100)
                        for b, k, r in mess[:3]) or 'kein Satz', urteil))
        zeilen.append(dict(datei=datei, name=name, lat=la, lon=lo, posquelle=pq, probe_cm='%.1f' % (probe * 100),
                           bestand=' | '.join('%s [%s] %.1f km %.1f cm' % (r['name'], os.path.basename(r['file']), k, b * 100) for b, k, r in mess),
                           urteil=urteil, m2='%.3f@%.0f' % w['M2'], z0='%.3f' % z0))
        if urteil in ('neu', 'ersetzen'):
            auftraege.append((datei, code, urteil, name, la, lo, pq, probe, d, mess[0] if mess else None))
    heute = dt.date.today().strftime('%Y%m%d')
    if '--schreiben' in argv:
        # Altsaetze zuerst archivieren (auch in derselben Datei), dann die neuen Saetze unter deren Name/Position
        weg = [(m[2], 'MSQ-Vorhersage %s trifft 2027 auf %.1f cm, dieser Satz auf %.1f cm -> MSQ-Fit (Oliver %s)' % (
            c, p_ * 100, m[0] * 100, heute)) for _d, c, u, _n, _la, _lo, _pq, p_, _dd, m in auftraege if u == 'ersetzen']
        if weg:
            with open(LOESCHLISTE, 'w', newline='', encoding='utf-8') as fh:
                wr = csv.writer(fh)
                wr.writerow(['datei', 'name', 'fehler_prozent', 'begruendung'])
                for r, b in weg:
                    wr.writerow([os.path.relpath(r['file'], ROOT), r['name'], '', b])
            import subprocess
            subprocess.run([sys.executable, os.path.join(ROOT, 'py/saetze_loeschen.py'), LOESCHLISTE, '--schreiben'], check=True, cwd=ROOT)
    for datei, code, urteil, name, la, lo, pq, probe, d, m in auftraege:
        if '--schreiben' in argv:
            ziel_name = name if urteil == 'neu' else m[2]['name']
            _s, _t, z0, w, _h, _a = Q.fit(d, voll, kopf, speeds, arg, fak)
            if urteil == 'ersetzen':
                la, lo = m[2]['lat'], m[2]['lon']
            blk = ['#', '# ' + ziel_name, '# BEGIN HOT COMMENTS', '# country: Australia',
                   '# source: MSQ tide predictions %s, least squares' % code,
                   '# note: Maritime Safety Queensland, predicted interval data 2025-2027, data.qld.gov.au, CC-BY 4.0.',
                   '# station_id_context: MSQ-PRED-%s' % code, '# date_imported: %s' % heute, '# datum: LAT', '# confidence: 6',
                   '# note: %s Fit auf die amtlichen MSQ-Vorhersagen (py/qld_msq_vorhersage_fit.py), Probe 2027 %.1f cm. Oliver.' % (heute, probe * 100)]
            if urteil == 'ersetzen':
                blk.append('# note: Ersetzt %s-Satz (archiviert), der die Vorhersage 2027 auf %.1f cm traf.' % (
                    os.path.basename(m[2]['file']), m[0] * 100))
            blk += ['# note: Position %s.' % pq if urteil == 'neu' else '# note: Position vom ersetzten Satz.',
                    '# !units: meters', '# !longitude: %.4f' % lo, '# !latitude: %.4f' % la, '# state: Queensland',
                    ziel_name, '+00:00 :Australia/Brisbane', '%.4f meters' % z0]
            blk += ['%-15s %.4f  %.2f' % (c, *w[c]) if c in w and w[c][0] >= 0.00005 else 'x 0 0' for c in namen]
            L = open(ZIEL, encoding='iso-8859-1').read().rstrip('\n').split('\n')
            if urteil == 'neu' and ziel_name in L:
                print('   existiert schon')
                continue
            schreiben(ZIEL, '\n'.join(L + blk) + '\n')
            print('   geschrieben: %s' % ziel_name)
    with open(ERGEBNIS, 'w', newline='', encoding='utf-8') as fh:
        wr = csv.DictWriter(fh, fieldnames=['datei', 'name', 'lat', 'lon', 'posquelle', 'probe_cm', 'bestand', 'urteil', 'm2', 'z0'])
        wr.writeheader()
        wr.writerows(zeilen)
    print('->', os.path.relpath(ERGEBNIS, ROOT))


if __name__ == '__main__':
    main(sys.argv[1:])
