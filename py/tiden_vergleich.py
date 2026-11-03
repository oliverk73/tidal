#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Vergleich py/tiden_rechnung.py gegen XTide (`tide -m p`) ueber den ganzen Bestand.

Je Satz zwei Fenster: Jahreswechsel 20.12.2026-10.01.2027 und 01.-08.03.2031.
Jedes XTide-Ereignis sucht sein Gegenstueck gleicher Art (naechste Zeit);
gemeldet: fehlende/ueberzaehlige Ereignisse, groesste Zeit- und Wertabweichung.
Eigene Zeit auf die Minute gerundet; XTide sucht selbst nur auf ~1 min genau (Abweichung 1 min = gleich).

Usage: venv/bin/python py/tiden_vergleich.py [datei-filter] [--max N]
Ausgabe: harmonics/help/tiden_vergleich_<datum>.csv
"""
from __future__ import annotations

import csv
import datetime as dt
import multiprocessing as mp
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tiden_rechnung as T                                          # noqa: E402
from health_check import active_files                               # noqa: E402

FENSTER = [('2026-12-20', '2027-01-10'), ('2031-03-01', '2031-03-08')]
TCD = '/usr/share/xtide'
BLOCK = 80


def utc(s):
    return dt.datetime.strptime(s, '%Y-%m-%d').replace(tzinfo=dt.timezone.utc).timestamp()


def xtide(tcd, namen, b, e):
    """-> {name: [(t, wert, art)]}"""
    # Mehrere -l in einem Aufruf: XTide laesst ab dem zweiten Ort das erste Ereignis weg
    # -> einen Tag frueher anfangen und auf das Fenster zuschneiden.
    t0, t1 = utc(b), utc(e)
    vor = dt.datetime.fromtimestamp(t0 - 86400, dt.timezone.utc).strftime('%Y-%m-%d')
    cmd = ['tide', '-b', vor + ' 00:00', '-e', e + ' 00:00', '-f', 'c', '-m', 'p', '-em', 'pSsMm', '-z',
           '-u', 'm', '-df', '%Y-%m-%d', '-tf', '%H:%M']
    for n in namen:
        cmd += ['-l', n]
    r = subprocess.run(cmd, env=dict(os.environ, HFILE_PATH=tcd), capture_output=True,
                       encoding='iso-8859-1', errors='replace')
    nach = {n.replace(',', '|'): n for n in namen}
    out = {n: [] for n in namen}
    for z in r.stdout.split('\n'):
        f = z.rsplit(',', 4)
        if len(f) != 5 or f[0] not in nach:
            continue
        t = dt.datetime.strptime(f[1] + ' ' + f[2].replace(' UTC', ''), '%Y-%m-%d %H:%M')
        t = t.replace(tzinfo=dt.timezone.utc).timestamp()
        if t0 <= t < t1:
            out[nach[f[0]]].append((t, float(f[3].split()[0]), f[4].replace('|', ',')))
    return out


def vergleich(eig, xt, t0, t1):
    """-> (fehlend, ueberzaehlig, max dt min, max dh); Ereignisse < 2 min am Fensterrand zaehlen nicht"""
    rand = lambda t: t < t0 + 120 or t >= t1 - 120
    eig = [e for e in eig if not rand(e[0])]
    xt = [e for e in xt if not rand(e[0])]
    frei = list(eig)
    fehl, dtm, dh = 0, 0.0, 0.0
    for t, h, art in xt:
        kand = [e for e in frei if e[2] == art and abs(e[0] - t) < 3 * 3600]
        if not kand:
            fehl += 1
            continue
        e = min(kand, key=lambda e: abs(e[0] - t))
        frei.remove(e)
        dtm = max(dtm, abs((round(e[0] / 60) * 60 - t) / 60))
        if not art.startswith('Slack'):
            dh = max(dh, abs(round(e[1], 2) - h))
    return fehl, len(frei), dtm, dh


def datei_pruefen(args):
    rel, maxn = args
    try:
        D = T.datei(rel)
    except Exception as ex:                                       # noqa: BLE001
        return [dict(datei=rel, name='', fehler=f'Kopf: {ex}')]
    tcd = os.path.join(TCD, os.path.basename(rel)[:-4] + '.tcd')
    namen = list(D.saetze)[:maxn] if maxn else list(D.saetze)
    zeilen = []
    for b, e in FENSTER:
        for i in range(0, len(namen), BLOCK):
            teil = namen[i:i + BLOCK]
            xt = xtide(tcd, teil, b, e)
            for n in teil:
                try:
                    eig = D.ereignisse(n, utc(b), utc(e))
                except Exception as ex:                           # noqa: BLE001
                    zeilen.append(dict(datei=rel, name=n, fenster=b, fehler=str(ex)))
                    continue
                f, u, dtm, dh = vergleich(eig, xt[n], utc(b), utc(e))
                zeilen.append(dict(datei=rel, name=n, fenster=b, n_xtide=len(xt[n]), n_eigen=len(eig),
                                   fehlend=f, ueberzaehlig=u, max_dt_min=round(dtm, 1), max_dh=round(dh, 3),
                                   fehler=''))
    print(f'{os.path.basename(rel)}: {len(namen)} Saetze', flush=True)
    return zeilen


def main(argv):
    filt = [a for a in argv if not a.startswith('--') and not a.isdigit()]
    maxn = int(argv[argv.index('--max') + 1]) if '--max' in argv else 0
    dateien = [f for f in active_files() if f.endswith('.txt') and (not filt or any(x in f for x in filt))]
    with mp.Pool(10) as p:
        alle = [z for zs in p.imap_unordered(datei_pruefen, [(f, maxn) for f in dateien]) for z in zs]
    ziel = os.path.join(T.ROOT, 'harmonics/help', f'tiden_vergleich_{dt.date.today():%Y%m%d}.csv')
    felder = ['datei', 'name', 'fenster', 'n_xtide', 'n_eigen', 'fehlend', 'ueberzaehlig', 'max_dt_min', 'max_dh', 'fehler']
    with open(ziel, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, felder)
        w.writeheader()
        w.writerows(alle)
    ok = [z for z in alle if not z.get('fehler')]
    schlecht = [z for z in ok if z['fehlend'] or z['ueberzaehlig'] or z['max_dt_min'] > 1.5 or z['max_dh'] > 0.011]
    print(f'{len(ok)} Vergleiche, {len(alle) - len(ok)} Fehler, {len(schlecht)} mit Abweichung -> {ziel}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
