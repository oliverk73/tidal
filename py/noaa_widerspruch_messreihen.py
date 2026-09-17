#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Dritte Quelle fuer die strittigen NOAA-Faelle: die Pegelreihen im Haus.

py/noaa_guete_probelauf.py laesst 94 Faelle offen, in denen ein NOAA-Satz
und ein Klasse-A-Satz am selben Ort verschieden sagen (Widerspruch,
glatter Stundenversatz, verdaechtiger A-Satz). Wer recht hat, entscheidet
dort niemand: Der A-Satz gilt, weil er gemessene Konstanten hat. Oliver
15.09.2026: erst gegen Messreihen pruefen.

Gemessen wird wie in py/messreihe_qualitaet.py -- Reihe lesen, beide
Saetze darauf vorhersagen, RMS um den Mittelwert und Zeitversatz. Anders
ist nur zweierlei:

  Die Vorhersage kommt aus py/xtide_modell.py, nicht aus den TCD. Die
  Textdateien sind der heutige Stand; eine TCD kann von gestern sein.

  Gesucht wird ueber die Lage, nicht ueber eine Kennung: jede Reihe im
  Umkreis von UMKREIS_KM um den strittigen Ort zaehlt.

Wo ein Satz AUS der Reihe gefittet ist (Spalte eigen), beweist sein
Sieg nichts -- er hat darauf trainiert. Solche Zeilen stehen mit
Urteil "blind" da.

Usage: python3 py/noaa_widerspruch_messreihen.py [--km 8] [--tage 365]
"""
from __future__ import annotations

import csv
import datetime as dt
import os
import re
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import messreihe_qualitaet as M                                    # noqa: E402
import xtide_modell as X                                           # noqa: E402
from health_check import ROOT, km, load_records                    # noqa: E402

HELP = os.path.join(ROOT, 'harmonics/help')
QUELLE = os.path.join(HELP, 'noaa_guete_probelauf.csv')
AUS = os.path.join(HELP, 'noaa_widerspruch_messreihen.csv')
LISTEN = ('loeschen:widerspruch', 'pruefen:stunde', 'bleibt:A_verdaechtig')
UMKREIS_KM = 8.0
TAGE = 365
SCHRITT = 600                      # 10 min, wie messreihe_qualitaet


_KOPF = {}
def modellkurve(r, von, bis, schritt=SCHRITT):
    """-> (unixzeiten, hoehen) eines Satzes aus seiner Textdatei."""
    pfad = os.path.join(ROOT, r['file'])
    if pfad not in _KOPF:
        _KOPF[pfad] = X.kopf_lesen(pfad)
    namen, speeds, arg, fak = _KOPF[pfad]
    z0, werte, einheit, meridian = X.satz_lesen(pfad, r['name'])
    skala = 0.3048 if einheit.startswith('f') else 1.0
    # Greenwich-Phasen fuer kurve(); ohne das ist jeder Satz um seinen Meridian
    # verschoben (die RMS-Urteile blieben richtig, weil messe() den Versatz
    # sucht -- die ausgewiesenen Zeitversaetze waren es nicht).
    werte = {k: (a, X.greenwich(kap, speeds[k], meridian)) for k, (a, kap) in werte.items() if k in speeds}
    t = np.arange(von, bis, schritt, dtype=float)
    jahre = {dt.datetime.fromtimestamp(x, dt.timezone.utc).year for x in (t[0], t[-1])}
    if not jahre <= set(arg):
        return None, None
    return t, X.kurve(t, z0, werte, namen, speeds, arg, fak, skala)


def fenster(obs, tage=TAGE, mind=M.MIND_PUNKTE):
    """Juengstes Fenster mit genug Werten -> (zeiten, hoehen) oder None."""
    if len(obs) < mind:
        return None
    ende = obs[-1][0]
    while True:
        start = ende - tage * 86400
        paare = [(t, h) for t, h in obs if start <= t <= ende]
        if len(paare) >= mind:
            return (np.array([p[0] for p in paare]), np.array([p[1] for p in paare]))
        frueher = [t for t, _h in obs if t < start]
        if not frueher:
            return None
        ende = frueher[-1]


def eigen(r, anbieter, kopf, pfad, alle, ankersatz):
    """Stammt der Satz aus dieser Reihe?

    Drei Wege, und alle drei werden gebraucht: der Satz IST der Anker
    (Vergleich ueber Datei und Zeile -- die Objekte stammen aus zwei
    load_records-Laeufen und sind nie dieselben), seine Kennung zeigt auf
    dieselbe Datei, oder der Anbietername steht in seiner Quellenzeile.
    Ohne den Kennungsweg galten die eigenen Fits von Queule, Nikolskoe und
    Hao als unabhaengige Sieger.
    """
    if ankersatz is not None and (r['file'], r['line']) == (ankersatz.get('file'), ankersatz.get('line')):
        return 1
    sid, _fit, quelle = kopf.get((r['file'], r['line']), (None, None, ''))
    if sid:
        try:
            if M.kennung_zur_reihe(sid, alle) == pfad:
                return 1
        except Exception:
            pass
    text = (quelle or '').lower()
    teile = [t for t in re.split(r'[_\-\s]', anbieter or '') if len(t) >= 3]
    if any(t.lower() in text for t in teile):
        return 1
    # Letzter Weg ueber die Lage: ein eigener UTide-Fit aus einer Messreihe,
    # der keine 500 m neben dieser Reihe steht, ist fast sicher aus ihr
    # gefittet. Toenning nennt als Kennung nur "WSV" -- zu unspezifisch fuer
    # die Zuordnung --, und die Quelle heisst "Pegelonline", der Ordner
    # "Germany". Ohne diese Regel galt der Satz als unabhaengiger Sieger
    # gegen genau die Reihe, auf der er trainiert hat.
    if 'utide' in text and ankersatz is not None and km(r, ankersatz) <= 0.5:
        return 1
    return 0


def main(argv):
    umkreis = float(argv[argv.index('--km') + 1]) if '--km' in argv else UMKREIS_KM
    tage = int(argv[argv.index('--tage') + 1]) if '--tage' in argv else TAGE

    recs = load_records()
    nach_name = {(os.path.basename(r['file']), r['name']): r for r in recs}
    faelle = []
    for z in csv.DictReader(open(QUELLE, encoding='utf-8')):
        if z['liste'] not in LISTEN:
            continue
        n = nach_name.get((z['datei'], z['name']))
        a = nach_name.get((z['naechster_a_datei'], z['naechster_a']))
        if n and a:
            faelle.append((z, n, a))
    print(f'{len(faelle)} strittige Faelle', file=sys.stderr)

    kopf, _recs, anker = M.alle_anker(None)
    alle = M.reihendateien_alle(None)
    print(f'{len(anker)} Reihen mit Position', file=sys.stderr)

    # Je Fall die naechstliegenden Reihen
    zuordnung = {}
    for i, (_z, n, _a) in enumerate(faelle):
        nah = sorted(((km(n, ank[0]), ank) for ank in anker if abs(ank[0]['lat'] - n['lat']) < 0.2
                      and abs(ank[0]['lon'] - n['lon']) < 0.4), key=lambda p: p[0])
        zuordnung[i] = [(d, ank) for d, ank in nah if d <= umkreis][:2]
    offen = sum(1 for v in zuordnung.values() if v)
    print(f'{offen} Faelle mit Reihe im Umkreis {umkreis:.0f} km', file=sys.stderr)

    out = []
    for i, (z, n, a) in enumerate(faelle):
        for d, (ankersatz, pfad, _fit, anbieter) in zuordnung[i]:
            mind = M.MIND_PUNKTE_TAFEL if any(t in pfad for t in M.TAFELREIHEN) else M.MIND_PUNKTE
            try:
                obs = M.lies(pfad)
            except Exception as e:
                print(f'  {os.path.basename(pfad)}: {e}', file=sys.stderr)
                continue
            w = fenster(obs, tage, mind)
            if w is None:
                continue
            obs_t, obs_h = w
            zeile = dict(liste=z['liste'], noaa=z['name'], noaa_datei=z['datei'],
                         a_satz=z['naechster_a'], a_datei=z['naechster_a_datei'],
                         abw_pct=z['abw_pct'], zeit_min=z['zeit_min'],
                         reihe=os.path.relpath(pfad, os.path.join(ROOT, 'water_levels')),
                         reihe_km=f'{d:.1f}', jahr=dt.datetime.fromtimestamp(
                             obs_t[-1], dt.timezone.utc).strftime('%Y-%m'))
            gut = True
            for satz, marke in ((n, 'noaa'), (a, 'a')):
                vt, vh = modellkurve(satz, obs_t[0] - 7200, obs_t[-1] + 7200)
                if vt is None:
                    gut = False
                    break
                g = M.messe(obs_t, obs_h, vt, vh, mind)
                if not g:
                    gut = False
                    break
                anz, rms, gross, versatz, off, hub = g
                zeile[f'n_{marke}'] = anz
                zeile[f'rms_{marke}'] = round(rms, 4)
                zeile[f'zeit_{marke}'] = versatz
                zeile[f'eigen_{marke}'] = eigen(satz, anbieter, kopf, pfad, alle, ankersatz)
            if not gut:
                continue
            if zeile['eigen_noaa'] or zeile['eigen_a']:
                zeile['urteil'] = 'blind (Satz aus dieser Reihe gefittet)'
            elif zeile['rms_noaa'] <= 0.8 * zeile['rms_a']:
                zeile['urteil'] = 'NOAA besser'
            elif zeile['rms_a'] <= 0.8 * zeile['rms_noaa']:
                zeile['urteil'] = 'A besser'
            else:
                zeile['urteil'] = 'gleichauf'
            out.append(zeile)
            print(f"  {z['name'][:34]:34} {zeile['reihe'][:34]:34} "
                  f"NOAA {zeile['rms_noaa']:.3f} ({zeile['zeit_noaa']:+4d} min)  "
                  f"A {zeile['rms_a']:.3f} ({zeile['zeit_a']:+4d} min)  {zeile['urteil']}",
                  flush=True)

    felder = ['liste', 'noaa', 'noaa_datei', 'a_satz', 'a_datei', 'abw_pct', 'zeit_min',
              'reihe', 'reihe_km', 'jahr', 'n_noaa', 'rms_noaa', 'zeit_noaa', 'eigen_noaa',
              'n_a', 'rms_a', 'zeit_a', 'eigen_a', 'urteil']
    with open(AUS, 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=felder)
        w.writeheader()
        w.writerows(out)
    print(f'\n{len(out)} Messungen zu {len({z["noaa"] for z in out})} Faellen -> '
          f'{os.path.relpath(AUS, ROOT)}')


if __name__ == '__main__':
    main(sys.argv[1:])
