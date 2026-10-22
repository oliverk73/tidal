#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Harmonische Saetze aus den MSQ-Archivreihen Queensland (py/download_qld_msq_archiv.py).

Oliver 22.10.2026: "Gibt es hier brauchbare Tidendaten: data.qld.gov.au ... tags=tides" -> "Ja" (neue Messpegel fitten).
Vorbild py/fluss_hydroportail_fit.py: kleinste Quadrate auf Stundenwerte (Momentanwert zur vollen Stunde, kein
resample-Mittel -> Stundenstempel-Falle), 67 UTide-Konstituenten + Obertiden, bei Reihen unter 400 Tagen nur, was das
Rayleigh-Kriterium (1/T) trennt (K2/P1 koppelt danach py/pegel_kopplung_lauf.py). Reihe hoechstens 10 Jahre; Pegelnull
an den Jahresmedianen von Hand pruefen (--spruenge schneidet automatisch, verwechselt aber ENSO-Mittelwasser im Golf
mit Spruengen: Amrun 2024/25). Probe: Fit ohne das letzte Jahr gegen das letzte Jahr. Eigenversatz muss 0 sein.
Pegelnull der MSQ-Reihen ist LAT -> Z0 direkt aus dem Fit (zur Kontrolle: tiefster Wert der 19-Jahres-Kurve).
Vergleich: Kurvenabstand (health_check.curve_diff) zu allen Bestandssaetzen bis 6 km (mindestens den drei naechsten bis 30 km).

Liste: harmonics/help/qld_msq_pegel.tsv (aktion neu/ersetzt werden geschrieben, vergleich nur gemessen, weg uebersprungen)
Usage: venv/bin/python py/qld_msq_fit.py [datei-teil ...] [--alle] [--spruenge] [--schreiben]  -> harmonics_utide_observations.txt
"""
import cmath
import csv
import datetime as dt
import math
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fluss_hydroportail_fit as F                                 # noqa: E402
import health_check as H                                           # noqa: E402
import scheitelfit as SF                                           # noqa: E402
import seine_haropa_fit as S                                       # noqa: E402
import xtide_modell as X                                           # noqa: E402
from sicher_schreiben import schreiben                             # noqa: E402

ROOT = S.ROOT
ZIEL = S.ZIEL
LISTE = os.path.join(ROOT, 'harmonics/help/qld_msq_pegel.tsv')
REIHEN = os.path.join(ROOT, 'water_levels/Australia_QLD/msq')
ERGEBNIS = os.path.join(ROOT, 'harmonics/help/qld_msq_fit.csv')


def liste():
    return list(csv.DictReader((z for z in open(LISTE, encoding='utf-8') if not z.startswith('#')), delimiter='\t'))


def rayleigh(nutz, speeds, namen, tage):
    """Konstituenten in Prioritaetsfolge, die sich ueber die Reihenlaenge von allen schon gewaehlten trennen."""
    if tage >= 400:
        return nutz
    grenze = 360.0 / (tage * 24.0)                                    # Grad/Stunde
    sp = speeds
    out = []
    vorrang = ['M2', 'S2', 'K1', 'O1', 'N2', 'K2', 'P1', 'Q1', 'M4', 'MS4', 'M6', 'MK3', 'MN4', 'L2', 'NU2', 'J1', 'M3', '2N2', 'MU2', 'OO1', 'SN4']
    for k in [k for k in vorrang if k in nutz] + [k for k in nutz if k not in vorrang]:
        if sp[k] < grenze:                                           # SA/SSA bei kurzen Reihen in Z0
            continue
        if all(abs(sp[k] - sp[j]) >= grenze for j in out):
            out.append(k)
    return out


def abschnitt(s):
    """Juengster Abschnitt ohne Pegelnull-Sprung. 12-Monats-Mediane vor/nach jedem Monat (der Jahresgang im Golf von
    Carpentaria erreicht 0,5 m und loeste die 6-Monats-Regel von fluss_hydroportail_fit aus), Sprung ab 0,15 m."""
    m = s.resample('MS').median().dropna()
    start = s.index[0]
    for i in range(12, len(m) - 12):
        vor, nach = m.iloc[i - 12:i].median(), m.iloc[i:i + 12].median()
        if abs(nach - vor) > 0.15 and abs(m.iloc[i:].median() - m.iloc[:i].median()) > 0.15:
            start = m.index[i]
    return s[start:], start


def rec(w):
    """Pseudo-Bestandssatz fuer health_check.curve_diff (Phasen schon UTC)."""
    z = {x: cmath.rect(w.get(x, (0.0, 0.0))[0], -math.radians(w.get(x, (0.0, 0.0))[1])) for x in H.MAIN}
    return dict(z=z, tot=sum(abs(z[x]) for x in H.MAIN))


def fit(s, nutz, kopf, speeds, arg, fak):
    t = np.array([i.timestamp() for i in s.index])
    z0, w = S.kq(t, s.values, nutz, speeds, arg, fak)
    h = SF.hoehe_und_ableitungen(t, z0, w, kopf)[0]
    r = s.values - h
    gut = np.abs(r - np.median(r)) < 5 * np.std(r)
    if (~gut).sum():
        s, t = s[gut], t[gut]
        z0, w = S.kq(t, s.values, nutz, speeds, arg, fak)
        h = SF.hoehe_und_ableitungen(t, z0, w, kopf)[0]
    return s, t, z0, w, h, int((~gut).sum())


def main(argv):
    kopf = X.kopf_lesen(ZIEL)
    namen, speeds, arg, fak = kopf
    voll = SF.konstituenten(namen, SF.CONSTIT_67) + [k for k in S.OBERTIDEN if k in namen]
    L = open(ZIEL, encoding='iso-8859-1').read().rstrip('\n').split('\n')
    heute = dt.date.today().strftime('%Y%m%d')
    wahl = [a for a in argv if not a.startswith('--')]
    bestand = [r for r in H.load_records() if r['lat'] and -30 < r['lat'] < -8 and 137 < r['lon'] < 155 and not r['current']]
    zeilen = []
    for z in liste():
        if wahl and not any(a in z['datei'] for a in wahl):
            continue
        if z['aktion'] == 'weg' and '--alle' not in argv:
            continue
        pfad = os.path.join(REIHEN, z['datei'] + '.csv')
        if not os.path.exists(pfad):
            print('%s: keine Reihe' % z['datei'])
            continue
        d = pd.read_csv(pfad, parse_dates=['time_utc']).set_index('time_utc')['waterlevel_m'].dropna()
        d = d[d.index.minute == 0]                                   # Momentanwert zur vollen Stunde
        jm = d.groupby(d.index.year).median()
        print('\n== %s (%s)\n   Jahresmedian: %s' % (z['name'], z['aktion'], ' '.join('%d:%.2f' % (j, v) for j, v in jm.items())))
        # Tide hat sich geaendert (Military Jetty: Bribie-Durchbruch 01/2022, M2 0.21 -> 0.39 m, 75 min frueher): 'ab=JJJJ-MM-TT' in der Bemerkung
        ab = [w[3:13] for w in (z.get('bemerkung') or '').replace(';', ' ').split() if w.startswith('ab=')]
        if ab:
            d = d[ab[0]:]
            print('   Reihe ab %s (Bemerkung)' % ab[0])
        s, start = abschnitt(d) if '--spruenge' in argv else (d, d.index[0])
        if start != d.index[0]:
            print('   Pegelnull-Sprung: Reihe ab %s' % start.date())
        s = s[s.index >= s.index[-1] - pd.Timedelta(days=3653)]
        # Verstreute Kampagnen (Red Island 1995/2002, Skardon 1998-2002): Luecken machen die Rayleigh-Pruefung blind und den
        # Fit instabil (M2 14 m) -> bei weniger als halber Abdeckung nur das laengste zusammenhaengende Stueck (Luecke > 2 Tage trennt)
        if len(s) < 0.5 * (s.index[-1] - s.index[0]).total_seconds() / 3600:
            g = (s.index.to_series().diff() > pd.Timedelta(days=2)).cumsum().values
            s = max((x for _, x in s.groupby(g)), key=len)
            print('   verstreute Kampagnen: nur %s..%s' % (s.index[0].date(), s.index[-1].date()))
        tage = (s.index[-1] - s.index[0]).days
        if len(s) < 24 * 25:
            print('   zu kurz (%d h)' % len(s))
            continue
        nutz = rayleigh(voll, speeds, namen, tage)
        # Probe: ohne das letzte Jahr fitten, am letzten Jahr messen
        probe = ''
        if tage >= 2 * 365:
            grenze = s.index[-1] - pd.Timedelta(days=365)
            _, _, pz0, pw, _, _ = fit(s[:grenze], nutz, kopf, speeds, arg, fak)
            te = s[grenze:]
            tt = np.array([i.timestamp() for i in te.index])
            rp = te.values - SF.hoehe_und_ableitungen(tt, pz0, pw, kopf)[0]
            rp = rp[np.abs(rp - np.median(rp)) < 5 * np.std(rp)]
            probe = '%.0f' % (100 * np.sqrt(np.mean(rp ** 2)))
        s, t, z0, w, h, aus = fit(s, nutz, kopf, speeds, arg, fak)
        rms = float(np.sqrt(np.mean((s.values - h) ** 2)))
        # Trockenfallen: in den tiefsten 5 % der Modellkurve liegt die Messung systematisch darueber (Plateau am Grund)
        tief = h <= np.quantile(h, 0.05)
        plateau = float(np.median(s.values[tief] - h[tief]))
        r2 = 1 - np.var(s.values - h) / np.var(s.values)
        sub = slice(None, None, 7)
        eig = min(range(-30, 31), key=lambda m: np.std(s.values[sub] - SF.hoehe_und_ableitungen(t[sub] - 60 * m, z0, w, kopf)[0]))
        tg = np.arange(dt.datetime(2008, 1, 1).timestamp(), dt.datetime(2027, 1, 1).timestamp(), 1800.0)
        lat_kurve = -float(SF.hoehe_und_ableitungen(tg, 0.0, w, kopf)[0].min())
        la, lo = float(z['lat']), float(z['lon'])
        nah = sorted(((H.km({'lat': la, 'lon': lo}, r), r) for r in bestand), key=lambda x: x[0])
        nah = [(k, r) for i, (k, r) in enumerate(nah) if k <= 6.0 or (i < 3 and k <= 30.0)]
        vgl = ['%s [%s] %.1f km %.0f%%' % (r['name'].split(',')[0], r['file'].split('/')[-1].replace('harmonics', '').replace('.txt', '')[:18],
                                         k, 100 * H.curve_diff(rec(w), r)[1]) for k, r in nah]
        print('   %d h %s..%s (%d d, %d Konst.)  R2 %.3f  RMS %.3f  Probe %s cm  Eigenversatz %+d  M2 %.3f@%.0f  K1 %.3f  Z0 %.2f (LAT-Kurve %.2f)  Plateau %+.0f cm%s' % (
            len(s), s.index[0].date(), s.index[-1].date(), tage, len(nutz), r2, rms, probe or '-', eig, *w['M2'], w['K1'][0], z0, lat_kurve, 100 * plateau,
            ('  %d Ausreisser' % aus) if aus else ''))
        for v in vgl:
            print('      ~ ' + v)
        zeilen.append(dict(datei=z['datei'], name=z['name'], aktion=z['aktion'], von=s.index[0].date(), bis=s.index[-1].date(), tage=tage,
                           konst=len(nutz), r2='%.4f' % r2, rms_cm='%.1f' % (100 * rms), probe_cm=probe, eigenversatz=eig,
                           m2='%.3f' % w['M2'][0], z0='%.2f' % z0, lat_kurve='%.2f' % lat_kurve, plateau_cm='%.0f' % (100 * plateau), nachbarn=' | '.join(vgl)))
        if z['aktion'] not in ('neu', 'ersetzt'):
            continue
        # Trockenfallende Pegel nicht aufnehmen (fluss_hydroportail_fit: Etaples/Cabourg, Schein-Hochwasser bei XTide)
        if plateau > 0.15:
            print('   verworfen: Plateau am Niedrigwasser (trockenfallend)')
            continue
        # Pegelnull nicht LAT (Flusspegel wie Mossman, +0.61 m): Z0 aus dem 19-Jahres-Minimum wie fluss_hydroportail_fit.
        # Normal liegt Z0 0.1-0.3 m ueber der LAT-Kurve (MSQ-LAT von 1992, Meeresspiegel seither gestiegen; Amrun +0.28).
        datum = 'LAT'
        if not -0.1 <= z0 - lat_kurve <= 0.4:
            datum = 'approx. LAT (Z0 aus 19-Jahres-Minimum)'
            print('   Pegelnull %.2f m unter LAT-Kurve -> Z0 = %.2f' % (z0 - lat_kurve, lat_kurve))
            z0 = lat_kurve
        code = z['datei'].replace('-tide-gauge-archived-interval-recordings', '')
        blk = ['#', '# ' + z['name'], '# BEGIN HOT COMMENTS', '# country: Australia',
               '# source: MSQ tide gauge %s, least squares' % code,                  # libtcd: Quelle hoechstens 90 Zeichen
               '# note: Maritime Safety Queensland, archived 10-min recordings, data.qld.gov.au, CC-BY 4.0.',
               '# station_id_context: MSQ-%s' % code, '# date_imported: %s' % heute, '# datum: %s' % datum, '# confidence: 7',
               '# utide: pts=%d period=%s..%s r2=%.4f rms=%.4fm const=%d' % (len(s), s.index[0].date(), s.index[-1].date(), r2, rms, len(nutz)),
               '# note: %s Messfit aus der MSQ-Archivreihe (py/qld_msq_fit.py), Oliver.' % heute,
               ('# note: Probe am letzten Messjahr %s cm RMS.' % probe) if probe else '# note: Reihe kuerzer als zwei Jahre, keine Probe.',
               '# note: Position %s%s.' % (z['posquelle'], ('; ' + z['bemerkung']) if z.get('bemerkung') else ''),
               '# !units: meters', '# !longitude: %.4f' % lo, '# !latitude: %.4f' % la,
               '# state: Queensland', z['name'], '+00:00 :Australia/Brisbane', '%.4f meters' % z0]
        blk += ['%-15s %.4f  %.2f' % (c, *w[c]) if c in w and w[c][0] >= 0.00005 else 'x 0 0' for c in namen]
        if z['name'] in L:
            print('   existiert schon in %s' % os.path.basename(ZIEL))
            continue
        L += blk
    if zeilen and not wahl:
        with open(ERGEBNIS, 'w', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=list(zeilen[0]))
            w.writeheader()
            w.writerows(zeilen)
    if '--schreiben' in argv:
        schreiben(ZIEL, '\n'.join(L) + '\n')
        print('->', os.path.relpath(ZIEL, ROOT))


if __name__ == '__main__':
    main(sys.argv[1:])
