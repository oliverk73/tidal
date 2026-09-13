#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Harmonische Saetze fuer BSH-Orte, die im Bestand noch fehlen.

Das BSH (gezeiten.bsh.de) fuehrt 172 deutsche Orte. 54 davon hatten am
13.09.2026 keinen Satz im Umkreis von 1.5 km -- darunter Nortmoor (Altarm
Juemme), Westringaburg (Leda), Detern, Augustfehn, Barssel, Arngast und die
Vareler Schleuse. Die Daten liegen in tide_tables/germany_bsh/ (JSON je Ort
mit Vorhersagen 2026 und 2027, Kennwerten und Bezugspegel; 10-Minuten-Kurven
fuer die Hauptpegel).

Drei Faelle, je nach dem, was das BSH liefert:

  A  Kurve       UTide auf die 10-Minuten-Kurve 2026. Die sauberste Quelle.
  B  Hoehen      Hoch- und Niedrigwasser mit Zeit und Hoehe, keine Kurve.
                 Ausgangspunkt ist der Satz eines Bezugspegels (der Pegel,
                 den das BSH nennt, sonst der naechste BSH-Pegel mit Kurve und
                 Satz im Bestand), zeitlich verschoben und im Hub skaliert.
                 Dann: Kurve waagerecht zu den BSH-Zeiten, BSH-Hoehe zu den
                 BSH-Zeiten, Konstanten nahe am Ausgangspunkt (Ridge).
                 Ein reiner Scheitelfit waere zwischen den Scheiteln frei
                 (py/scheitelfit.py: Bridgwater 5.6 m daneben); der
                 Bezugspegel gibt die Form vor.
  C  nur Zeiten  Wie B, aber die Hoehen kommen vom Bezugspegel (skaliert mit
                 dem mittleren Tidenhub, wo das BSH ihn nennt). Die BSH
                 rechnet solche Orte selbst "im festen Zeitunterschied" zum
                 Bezugspegel -- das Verfahren folgt ihr.

Geprueft wird auf 2027, das nicht im Fit steckt: Scheitelzeiten (Median und
Streuung), bei A der RMS gegen die Kurve, bei B der RMS der Scheitelhoehen.

Hoehen in Seekartennull (SKN): PNP-Werte minus "SKN ueber PNP". Wo das BSH
kein Datum nennt (nur Zeiten), bleibt Z0 das des Bezugspegels, und der
Vermerk sagt es.

Trockenfallende Orte (NW fehlt): der Satz folgt dem Hochwasser; das
Niedrigwasser eines harmonischen Satzes liegt dort unter der Wattkante.

Usage: venv/bin/python3 py/bsh_saetze.py [BSH-Nr ...] [--schreiben]
"""
from __future__ import annotations

import csv
import datetime as dt
import glob
import json
import math
import os
import re
import statistics
import sys
import warnings

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scheitelfit as SF                                           # noqa: E402
import xtide_modell as X                                           # noqa: E402
from health_check import km, load_records                          # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BSH = os.path.join(ROOT, 'tide_tables/germany_bsh')
AUS_TXT = os.path.join(ROOT, 'harmonics/bsh/harmonics_bsh_germany.txt')
AUS_CSV = os.path.join(ROOT, 'harmonics/help/bsh_saetze.csv')
KOPFQUELLE = os.path.join(ROOT, 'harmonics/utide/harmonics_utide_tidetables.txt')
FEHLT_KM = 1.5
MEZ = dt.timezone(dt.timedelta(hours=1))
GEW_HOEHE, GEW_STEIG, LAMBDA = 1.0, 3.0, 1e-2   # Steigung 3: Arngast HW-Streuung 51 -> 28 min
NAMENSMAP = {'SA': 'SA-IOS', 'S1': 'S1-IOS'}
# Binnenlage im BSH-Namen: Siel, Sperrwerk, Schleuse oder ein Flussname
BINNEN = re.compile(r'siel|sperrwerk|schleuse|\b(elbe|weser|ems|st\u00f6r|oste|leda|j\u00fcmme|schwinge|'
                    r'hunte|ochtum|lesum|eider|pinnau|kr\u00fcckau|este|l\u00fche|soeste|aper tief)\b', re.I)


# ---------------------------------------------------------------- BSH-Daten
def orte():
    d = json.load(open(os.path.join(BSH, 'json/tides_overview.json'), encoding='utf-8'))
    return d if isinstance(d, list) else next(v for v in d.values() if isinstance(v, list))


def ort_json(nr):
    return json.load(open(os.path.join(BSH, f'json/DE_{nr.rjust(5, "_")}_tides.json'), encoding='utf-8'))


def jahr_daten(d, jahr):
    for y in d.get('years', []):
        if jahr in y:
            return y[jahr]
    return None


def skn_versatz_cm(v, level):
    """cm, die von einem Wert im Niveau `level` abzuziehen sind, um SKN zu erhalten."""
    if level == 'SKN':
        return 0.0
    if level == 'PNP' and v.get('SKN (ueber PNP)') is not None:
        return float(v['SKN (ueber PNP)'])
    return None


def scheitel(v):
    """-> {'H': (zeiten, hoehen_skn_m oder None), 'N': ...} aus der JSON-Vorhersage."""
    pred = v.get('hwnw_prediction') or {}
    level = pred.get('level') or v.get('level_tidalvalues')
    level = level.upper() if level else None
    vers = skn_versatz_cm(v, level)
    out = {}
    for art, typ in (('H', 'HW'), ('N', 'NW')):
        ev = [e for e in pred.get('data', []) if e.get('type') == typ]
        t = np.array([dt.datetime.fromisoformat(e['timestamp']).timestamp() for e in ev])
        if ev and all(e.get('height') is not None for e in ev) and vers is not None:
            h = np.array([(e['height'] - vers) / 100.0 for e in ev])
        else:
            h = None
        out[art] = (t, h)
    return out


def kurve(nr, jahr):
    """-> (zeiten, hoehen_skn_m) aus der 10-Minuten-Kurve, oder None."""
    pfad = os.path.join(BSH, f'kurve/DE__{nr}{jahr}.txt')
    if not os.path.exists(pfad):
        return None
    skn = None
    t, h = [], []
    for z in open(pfad, encoding='iso-8859-1'):
        if z.startswith('D03#'):
            skn = float(z.split('#')[2].replace(' ', ''))
        elif z.startswith('VB2#'):
            f = z.split('#')
            tg, mo, jr = [int(x) for x in re.findall(r'\d+', f[5])]
            hh, mm = [int(x) for x in f[6].strip().split(':')]
            try:
                h.append(float(f[7]))
            except ValueError:
                continue
            t.append(dt.datetime(jr, mo, tg, hh, mm, tzinfo=MEZ).timestamp())
    if not t or skn is None:
        return None
    return np.array(t), np.array(h) - skn


def bezugsname(v):
    for n in v.get('notice', []):
        m = re.search(r'Zeitunterschied\s+zu\s+(.+?)\s+erstellt', n)
        if m:
            return m.group(1).strip()
    return None


def satzname(bsh_name):
    teile = [t.strip() for t in bsh_name.split(',')]
    if len(teile) == 1:
        return f'{teile[0]}, Germany'
    return f'{teile[0]} ({", ".join(teile[1:])}), Germany'


# ---------------------------------------------------------------- Modell
def konst(r, speeds):
    z0, rw, e, mer = X.satz_lesen(r['file'], r['name'])
    sk = 0.3048 if e.startswith('f') else 1.0
    return z0 * sk, {k: (a * sk, X.greenwich(kap, speeds[k], mer))
                     for k, (a, kap) in rw.items() if k in speeds and a > 0}


def scheitelhoehe(z0, g, t, kopf):
    h, h1, h2 = SF.hoehe_und_ableitungen(t, z0, g, kopf)
    return h - np.where(h2 != 0, h1 ** 2 / (2 * np.where(h2 != 0, h2, 1)), 0)


def versatz_min(z0, g, t, kopf):
    """Modellscheitel minus Tafelzeit in Minuten (Newton-Schritt)."""
    h, h1, h2 = SF.hoehe_und_ableitungen(t, z0, g, kopf)
    d = np.where(h2 != 0, -h1 / np.where(h2 != 0, h2, 1), 0) * 60
    return d[np.abs(d) < 180]


def verschieben(g, minuten, speeds):
    """Kurve um `minuten` spaeter legen."""
    return {k: (a, kap + speeds[k] * minuten / 60.0) for k, (a, kap) in g.items()}


def zeitguete(z0, g, sch, kopf):
    out = {}
    for art in ('H', 'N'):
        t, _h = sch[art]
        if len(t):
            d = versatz_min(z0, g, t, kopf)
            if len(d):
                out[art] = (float(statistics.median(d)), float(np.percentile(d, 90) - np.percentile(d, 10)))
    return out


def fit_mit_bezug(z0r, gr, sch, kopf, hoehen_ziel=None):
    """Konstanten nahe am Bezug: waagerecht zu den BSH-Zeiten, Hoehen wie Ziel."""
    namen, speeds, arg, fak = kopf
    nutz = [k for k in namen if k in gr]
    n = len(nutz)
    zeilen_A, zeilen_b = [], []
    for art in ('H', 'N'):
        t, h = sch[art]
        if not len(t):
            continue
        C, S, w = X.matrix(t, nutz, speeds, arg, fak)
        zeilen_A.append(GEW_STEIG * np.hstack([np.zeros((len(t), 1)), -w * S, w * C]))
        zeilen_b.append(np.zeros(len(t)))
        ziel = h if h is not None else (hoehen_ziel[art] if hoehen_ziel else None)
        if ziel is not None:
            zeilen_A.append(GEW_HOEHE * np.hstack([np.ones((len(t), 1)), C, S]))
            zeilen_b.append(GEW_HOEHE * ziel)
    a = np.array([gr[k][0] for k in nutz])
    kap = np.radians([gr[k][1] for k in nutz])
    x0 = np.concatenate([[z0r], a * np.cos(kap), a * np.sin(kap)])
    zeilen_A.append(math.sqrt(LAMBDA) * np.eye(2 * n + 1))
    zeilen_b.append(math.sqrt(LAMBDA) * x0)
    x, *_ = np.linalg.lstsq(np.vstack(zeilen_A), np.concatenate(zeilen_b), rcond=None)
    c, d = x[1:1 + n], x[1 + n:]
    return float(x[0]), {k: (float(np.hypot(c[j], d[j])), float(np.degrees(np.arctan2(d[j], c[j])) % 360))
                         for j, k in enumerate(nutz)}


# ---------------------------------------------------------------- Bezug
def bester_satz_am_ort(recs, lat, lon, nr, kopf):
    """Der Satz im Bestand, der die BSH-Vorhersage dieses Orts am besten trifft."""
    kand = [r for r in recs if km(r, {'lat': lat, 'lon': lon}) <= FEHLT_KM]
    if not kand:
        return None, None
    ku = kurve(nr, '2026')
    v = jahr_daten(ort_json(nr), '2026') or {}
    sch = scheitel(v)
    wert = []
    for r in kand:
        try:
            z0, g = konst(r, kopf[1])
        except (KeyError, IndexError, ValueError):
            continue
        if ku is not None:
            hm = X.kurve(ku[0][::6], z0, g, *kopf)
            d = ku[1][::6] - hm
            wert.append((float(np.sqrt(np.mean((d - d.mean()) ** 2))), r))
        else:
            zg = zeitguete(z0, g, sch, kopf)
            if zg:
                wert.append((sum(abs(m) + s / 2 for m, s in zg.values()) / 100.0, r))
    if not wert:
        return None, None
    wert.sort(key=lambda x: x[0])
    return wert[0][1], wert[0][0]


# ---------------------------------------------------------------- Faelle
def utide_kurve(t, h, lat, kopf):
    import utide
    zeit = np.array([dt.datetime.fromtimestamp(x, dt.timezone.utc).replace(tzinfo=None) for x in t])
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        c = utide.solve(zeit, h, lat=lat, method='ols', conf_int='none', trend=False,
                        nodal=True, constit='auto', verbose=False)
    g = {}
    for n, a, gg in zip(c['name'], c['A'], c['g']):
        k = NAMENSMAP.get(str(n), str(n))
        if k in kopf[1]:
            g[k] = (float(a), float(gg) % 360.0)
    return float(c['mean']), g


def erzeuge(o, recs, fehlend, kopf, bezug_nr=None):
    nr = o['bshnr']
    d = ort_json(nr)
    v26, v27 = jahr_daten(d, '2026') or {}, jahr_daten(d, '2027') or {}
    ku26, ku27 = kurve(nr, '2026'), kurve(nr, '2027')
    sch26, sch27 = scheitel(v26), scheitel(v27)
    hinweise = [n for n in v26.get('notice', []) if n]
    ergebnis = dict(bshnr=nr, bsh_name=o['station_name'], satz=satzname(o['station_name']),
                    lat=o['latitude'], lon=o['longitude'], hinweise=' / '.join(hinweise))
    if ku26 is not None and len(ku26[0]) > 20000:
        z0_1, g_1 = utide_kurve(ku26[0], ku26[1], o['latitude'], kopf)
        ergebnis['bezug'] = ''
        # Regel (Oliver, 13.09.2026): Ein harmonischer Satz kann an Sielen,
        # Sperrwerken und in Fluessen nicht zugleich die BSH-Kurve und die
        # BSH-Scheitel treffen -- das BSH rechnet dort nicht harmonisch (HDdU mit
        # mittlerer beobachteter Tidenkurve). Gezaehlt wird, was eine Anzeige
        # zeigt: dort die Scheitel (streng, Ridge 1.0; Schluettsiel NW -15 ->
        # 0 min, Kurve dazwischen 16 -> 36 cm). An offener See und Inseln passt
        # der reine Kurvenfit (Westerland 11.6 cm, Fino 3 9.3 cm).
        binnen = bool(BINNEN.search(o['station_name']) or
                      any(re.search(r'Siel|Sperrwerk|Schleuse|trocken', n) for n in hinweise))
        z0, g = z0_1, g_1
        ergebnis['fall'] = 'A Kurve'
        ergebnis['ziel'] = 'Kurve'
        if binnen and len(sch26['H'][0]) and len(sch26['N'][0]):
            alt_gs, alt_lam = globals()['GEW_STEIG'], globals()['LAMBDA']
            globals()['GEW_STEIG'], globals()['LAMBDA'] = 3.0, 1.0
            try:
                zz, gg = fit_mit_bezug(z0_1, g_1, sch26, kopf)
            finally:
                globals()['GEW_STEIG'], globals()['LAMBDA'] = alt_gs, alt_lam
            ext = scheitelhoehe(zz, gg, np.concatenate([sch26['H'][0], sch26['N'][0]]), kopf)
            if np.all(np.isfinite(ext)) and np.max(np.abs(ext - zz)) < 10:
                z0, g = zz, gg
                ergebnis['fall'] = 'A Kurve + Scheitel'
                ergebnis['ziel'] = 'Scheitel'
        if ku27 is not None:
            hm = X.kurve(ku27[0], z0, g, *kopf)
            ergebnis['test_rms_cm'] = round(float(np.sqrt(np.mean((ku27[1] - hm) ** 2))) * 100, 1)
    else:
        name_bezug = bezugsname(v26)
        bezug_ort = next((x for x in orte() if x['bshnr'] == bezug_nr), None) if bezug_nr else None
        if bezug_ort is None and name_bezug:
            bezug_ort = next((x for x in orte() if x['station_name'] == name_bezug), None)
        if bezug_ort is None:
            # naechster BSH-Pegel mit Kurve und Satz im Bestand
            kand = [x for x in orte() if x['bshnr'] not in fehlend and kurve(x['bshnr'], '2026') is not None]
            kand.sort(key=lambda x: km({'lat': x['latitude'], 'lon': x['longitude']},
                                       {'lat': o['latitude'], 'lon': o['longitude']}))
            bezug_ort = kand[0] if kand else None
        if bezug_ort is None:
            ergebnis['fall'] = 'kein Bezug'
            return ergebnis, None
        r, guete = bester_satz_am_ort(recs, bezug_ort['latitude'], bezug_ort['longitude'], bezug_ort['bshnr'], kopf)
        if r is None:
            ergebnis['fall'] = 'kein Bezugssatz'
            return ergebnis, None
        z0r, gr = konst(r, kopf[1])
        ergebnis['bezug'] = f'{bezug_ort["station_name"]} -> {r["name"]} [{os.path.basename(r["file"])}]'
        # Zeitlich an die BSH-Zeiten heranschieben
        ds = np.concatenate([versatz_min(z0r, gr, sch26[a][0], kopf) for a in ('H', 'N') if len(sch26[a][0])])
        schub = -float(np.median(ds)) if len(ds) else 0.0
        gr = verschieben(gr, schub, kopf[1])
        hat_hoehen = sch26['H'][1] is not None
        if hat_hoehen:
            ergebnis['fall'] = 'B Hoehen'
            # Hub grob skalieren, wo HW und NW Hoehen haben
            if sch26['N'][1] is not None:
                hub_bsh = float(sch26['H'][1].mean() - sch26['N'][1].mean())
                hh = scheitelhoehe(z0r, gr, sch26['H'][0], kopf).mean() - scheitelhoehe(z0r, gr, sch26['N'][0], kopf).mean()
                if hh > 0.05 and hub_bsh > 0.05:
                    f = hub_bsh / hh
                    gr = {k: (a * f, p) for k, (a, p) in gr.items()}
            z0, g = fit_mit_bezug(z0r, gr, sch26, kopf)
        else:
            ergebnis['fall'] = 'C nur Zeiten'
            f = 1.0
            mth = v26.get('MTH')
            if mth:
                hh = scheitelhoehe(z0r, gr, sch26['H'][0], kopf).mean() - scheitelhoehe(z0r, gr, sch26['N'][0], kopf).mean() \
                    if len(sch26['N'][0]) else None
                if hh and hh > 0.05:
                    f = (mth / 100.0) / hh
            gr = {k: (a * f, p) for k, (a, p) in gr.items()}
            ziel = {a: scheitelhoehe(z0r, gr, sch26[a][0], kopf) for a in ('H', 'N') if len(sch26[a][0])}
            z0, g = fit_mit_bezug(z0r, gr, sch26, kopf, hoehen_ziel=ziel)
            vers = skn_versatz_cm(v26, (v26.get('level_tidalvalues') or '').upper())
            if v26.get('MHW') is not None and v26.get('MNW') is not None and vers is not None:
                z0 = ((v26['MHW'] + v26['MNW']) / 2.0 - vers) / 100.0
                ergebnis['z0_quelle'] = 'BSH-Kennwerte (MHW+MNW)/2'
            else:
                ergebnis['z0_quelle'] = 'Bezugssatz (Datum unsicher)'
        ergebnis['bezug_guete'] = round(guete * 100, 1) if guete is not None else ''
    zg26 = zeitguete(z0, g, sch26, kopf)
    wert26 = sum(abs(m) + sp / 2 for m, sp in zg26.values())
    for art in ('H', 'N'):
        t, h = sch26[art]
        if h is not None and len(t):
            wert26 += float(np.sqrt(np.mean((scheitelhoehe(z0, g, t, kopf) - h) ** 2))) * 100
    ergebnis['passung_2026'] = round(wert26, 1)
    zg = zeitguete(z0, g, sch27, kopf)
    for art, lab in (('H', 'hw'), ('N', 'nw')):
        if art in zg:
            ergebnis[f'test_{lab}_min'] = round(zg[art][0], 1)
            ergebnis[f'test_{lab}_streuung'] = round(zg[art][1], 1)
        t, h = sch27[art]
        if h is not None and len(t):
            ergebnis[f'test_{lab}_hoehe_cm'] = round(float(np.sqrt(np.mean((scheitelhoehe(z0, g, t, kopf) - h) ** 2))) * 100, 1)
    ergebnis['M2'] = round(g.get('M2', (0, 0))[0], 3)
    ergebnis['S2'] = round(g.get('S2', (0, 0))[0], 3)
    return ergebnis, (z0, g)


# ---------------------------------------------------------------- Schreiben
def satzblock(e, z0, g, namen):
    heute = dt.date.today().strftime('%Y%m%d')
    zeilen = ['# BEGIN HOT COMMENTS', '# country: Germany',
              # libtcd erlaubt fuer source hoechstens 90 Zeichen (ONELINER_LENGTH)
              f'# source: BSH gezeiten.bsh.de, Ort {e["bshnr"]}, {e["fall"]}'[:90],
              f'# note: BSH-Ort "{e["bsh_name"]}".',
              f'# date_imported: {heute}', '# datum: SKN (Seekartennull)' if e.get('z0_quelle', '').startswith('BSH') or e['fall'] != 'C nur Zeiten'
              else '# datum: wie Bezugssatz (BSH nennt kein Datum)', '# confidence: 6']
    if e['fall'].startswith('A'):
        zeilen.append('# note: UTide (OLS, Rayleigh-Auswahl) auf die BSH-10-Minuten-Kurve 2026 in SKN'
                      + (', danach an die BSH-Scheitel 2026 angepasst.' if 'Scheitel' in e['fall'] else '.'))
        if e.get('ziel') == 'Scheitel':
            zeilen.append('# note: Ziel Scheitel (Siel/Sperrwerk/Fluss): HW/NW nach BSH, die Kurve dazwischen')
            zeilen.append('# note: weicht ab -- das BSH rechnet hier nicht harmonisch (HDdU).')
        teile = [f'Kurve {e.get("test_rms_cm")} cm'] if e.get('test_rms_cm') is not None else []
        for lab, txt in (('hw', 'HW'), ('nw', 'NW')):
            if e.get(f'test_{lab}_min', '') != '':
                teile.append(f'{txt} {e[f"test_{lab}_min"]:+.0f} min (Streuung {e[f"test_{lab}_streuung"]:.0f})')
        zeilen.append('# note: Pruefung gegen BSH 2027: ' + '; '.join(teile) + '.')
    else:
        zeilen.append(f'# note: Ausgangspunkt Bezugssatz {e["bezug"]},')
        zeilen.append('# note: zeitlich verschoben und im Hub skaliert, dann an die BSH-Scheitel 2026')
        zeilen.append('# note: angepasst (waagerecht zur BSH-Zeit' + (', BSH-Hoehe' if e['fall'].startswith('B') else '') + ').')
        teile = []
        for lab, txt in (('hw', 'HW'), ('nw', 'NW')):
            if e.get(f'test_{lab}_min', '') != '':
                s = f'{txt} {e[f"test_{lab}_min"]:+.0f} min (Streuung {e[f"test_{lab}_streuung"]:.0f})'
                if e.get(f'test_{lab}_hoehe_cm', '') != '':
                    s += f', Hoehe {e[f"test_{lab}_hoehe_cm"]} cm'
                teile.append(s)
        if teile:
            zeilen.append('# note: Pruefung gegen die BSH-Scheitel 2027: ' + '; '.join(teile) + '.')
    if e.get('hinweise'):
        zeilen.append(f'# note: BSH: {e["hinweise"]}')
    zeilen += ['# !units: meters', f'# !longitude: {e["lon"]:.4f}', f'# !latitude: {e["lat"]:.4f}',
               e['satz'], '+00:00 :Europe/Berlin', f'{z0:.4f} meters']
    for k in namen:
        if k in g and g[k][0] > 0.0001:
            zeilen.append(f'{k:<16}{g[k][0]:.4f}  {g[k][1] % 360.0:.2f}')
        else:
            zeilen.append('x 0 0')
    return zeilen


def dateikopf():
    zeilen = open(KOPFQUELLE, encoding='iso-8859-1').read().split('\n')
    # Nur Zeilen, die genau *END* sind -- das Wort steht auch im Kommentar
    # "DO NOT REMOVE THE *END* AT THE END" (13.09.2026: Knotenfaktoren fehlten).
    ende = [i for i, z in enumerate(zeilen) if z.strip() == '*END*'][1]
    # build_tide_db verlangt danach den Block "End congen output" (sonst
    # Assertion string[0] == '#' in ProcessHarmonicsFile).
    doku = next(i for i in range(ende, len(zeilen)) if 'FITNESS FOR A PARTICULAR PURPOSE' in zeilen[i])
    return zeilen[:doku + 3]


def main(argv):
    kopf = X.kopf_lesen(KOPFQUELLE)
    namen = kopf[0]
    recs = [r for r in load_records() if r['lat'] is not None and not r['current']
            and 53 < r['lat'] < 55.5 and 6 < r['lon'] < 14.8
            and 'harmonics_bsh_germany' not in r['file']]
    alle = orte()
    fehlend = {o['bshnr'] for o in alle
               if min(km(r, {'lat': o['latitude'], 'lon': o['longitude']}) for r in recs) > FEHLT_KM}
    wahl = [a for a in argv if not a.startswith('--')]
    ziel = [o for o in alle if (o['bshnr'] in wahl if wahl else o['bshnr'] in fehlend)]
    print(f'{len(fehlend)} BSH-Orte ohne Satz im Umkreis von {FEHLT_KM} km; bearbeitet werden {len(ziel)}')
    kurvenorte = [x for x in alle if x['bshnr'] not in fehlend and kurve(x['bshnr'], '2026') is not None]
    zeilen_csv, bloecke = [], []
    for o in ziel:
        # Bezugswahl (13.09.2026): der vom BSH genannte Pegel und die vier naechsten
        # Kurvenpegel mit Satz im Bestand. Die Zeitstreuung haengt kaum am Bezug,
        # Hoehen und Zeit-Orte schon (Detern NW-Hoehe 39.7 cm mit Dreyschloot,
        # 8.2 cm mit dem Leda-Sperrwerk; Suedwesthoern Streuung 40 min mit
        # Helgoland, 12 mit Wyk). Gewaehlt wird nach der Passung an 2026.
        kandidaten = [None]
        if not (B_kurve := kurve(o['bshnr'], '2026')) or len(B_kurve[0]) <= 20000:
            nahe = sorted(kurvenorte, key=lambda x: km({'lat': x['latitude'], 'lon': x['longitude']},
                                                       {'lat': o['latitude'], 'lon': o['longitude']}))[:4]
            kandidaten += [x['bshnr'] for x in nahe]
        versuche = []
        for b in kandidaten:
            try:
                e, kg = erzeuge(o, recs, fehlend, kopf, bezug_nr=b)
            except Exception as ex:                               # noqa: BLE001
                e, kg = dict(bshnr=o['bshnr'], bsh_name=o['station_name'], fall=f'Fehler: {ex}'), None
            if kg is not None:
                versuche.append((e.get('passung_2026', 1e9), e, kg))
        if versuche:
            versuche.sort(key=lambda x: x[0])
            _p, e, kg = versuche[0]
            e['bezug_kandidaten'] = '; '.join(f"{x[1].get('bezug', '').split(' -> ')[0]} {x[0]}" for x in versuche)
        else:
            kg = None
        zeilen_csv.append(e)
        txt = e.get('fall', '')
        if 'test_rms_cm' in e:
            txt += f"  Kurve 2027 {e['test_rms_cm']} cm"
        for lab in ('hw', 'nw'):
            if f'test_{lab}_min' in e:
                txt += f"  {lab.upper()} {e[f'test_{lab}_min']:+.0f}/{e[f'test_{lab}_streuung']:.0f}"
                if f'test_{lab}_hoehe_cm' in e:
                    txt += f" h{e[f'test_{lab}_hoehe_cm']}"
        print(f"  {o['bshnr']:6} {o['station_name'][:32]:32} {txt}  {e.get('bezug', '')[:60]}", flush=True)
        if kg:
            bloecke.append(satzblock(e, kg[0], kg[1], namen))
    felder = sorted({k for z in zeilen_csv for k in z}, key=lambda k: (k not in ('bshnr', 'bsh_name', 'satz', 'fall'), k))
    with open(AUS_CSV, 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=felder)
        w.writeheader()
        w.writerows(zeilen_csv)
    print('->', os.path.relpath(AUS_CSV, ROOT))
    if '--schreiben' in argv and bloecke:
        os.makedirs(os.path.dirname(AUS_TXT), exist_ok=True)
        text = dateikopf()
        for b in bloecke:
            text += b
        open(AUS_TXT, 'w', encoding='iso-8859-1').write('\n'.join(text) + '\n')
        print(f'-> {os.path.relpath(AUS_TXT, ROOT)}: {len(bloecke)} Saetze')


if __name__ == '__main__':
    main(sys.argv[1:])
