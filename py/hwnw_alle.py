#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Eigene HW/NW-Rechnung fuer alle deutschen Nordsee-Pegel (Stufe 4, Oliver 4.11.2026).

Je Pegel: Scheitel aus der langen Minutenreihe (Pegelonline-Zip bzw. HPA), Eichung an 2015-2024 und
an 2021-2024 (nach der Elbvertiefung), Pruefung am unabhaengigen Jahr 2025. Je HW und NW gewinnt die
Variante mit dem kleinsten Zeit-RMS (harmonischer Satz | Satz + Ungleichheiten | Mondbasis); eine
eigene Variante nur, wenn sie mindestens 1 min besser ist und die Hoehe nicht um mehr als 3 cm
verschlechtert. Bleiben HW und NW beim Satz, wird kein Modell abgelegt.

Zuordnung Reihe -> Satz ueber die Position (water_levels/Germany/npz_stationen.json, < 1 km; bei zwei
Reihen am selben Satz die naehere), Reihen ohne Position ueber NAMEN.
Ergebnis: harmonics/hwnw/<kurz>.json (mit 'wahl', 'fingerabdruck'), harmonics/help/hwnw_auswahl_<datum>.csv
Scheitel-CSVs: water_levels/Germany/hwnw/<kurz>.csv (vorhandene werden wiederverwendet).

Ausland (--land=be|fr|uk|alle): waterinfo.be, SHOM, BODC; Satz ueber hic_code/shom_code/bodc_code im Kopf.\nUsage: venv/bin/python py/hwnw_alle.py [scheitel|eichen|alles|veraltet] [--land=de] [--nur=kurz,kurz] [--prozesse=4]
"""
from __future__ import annotations

import datetime as dt
import glob
import json
import math
import os
import re
import shutil
import sys
import tempfile
from multiprocessing import Pool

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hwnw_ungleichheiten as HU                                    # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OBS = 'harmonics/utide/harmonics_utide_observations.txt'
GER = os.path.join(ROOT, 'water_levels/Germany')
SCHEITEL = os.path.join(GER, 'hwnw')
FENSTER = [(2015, 2024), (2021, 2024)]
PRUEF = 2025
NAMEN = {'altengamme': 'Altengamme (Elbe), Germany', 'brake': 'Brake (Weser), Germany',
         'dagebll': 'Dageb\xfcll, Germany', 'elsfleth': 'Elsfleth (Weser), Germany',
         'farge': 'Farge (Weser), Germany', 'mellumplate': 'Mellumplate (Jade), Germany',
         'vegesack': 'Vegesack (Weser), Germany'}
HPA = {'stpauli': ('STP', 'Hamburg (St. Pauli), Germany'),
       'hpa_har': ('HAR', 'Hamburg-Harburg (Elbe, Schleuse), Germany'),
       'hpa_ubn': ('UBN', 'Hamburg-Blankenese (Elbe, Unterfeuer), Germany'),
       'hpa_smh': ('SMH', 'Hamburg Seemannsh\xf6ft (Elbe), Germany'),
       'hpa_sps': ('SPS', 'Hamburg Dove-Elbe (Einfahrt), Germany'),
       'hpa_bhs': ('BHS', 'Hamburg-Bunthaus (Elbe), Germany')}
# Harmonischer Satz mit vielen Zusatzscheiteln bei Niedrigwasser (Durme, trockenfallend): die Kurve laesst
# sich nicht auf die Tabelle strecken -> kein Modell (4.11.2026)
OHNE = {'be_04dur04a_1066', 'be_04dur05a_1066'}
SKN_PNP = 3.10          # alle sechs HPA-Pegel: OffsetZuNN + Pegelnull-Hoehe = 3,10 m
ALT = {'cuxhaven': 'cuxhaven_hwnw_2000_2026.csv', 'stpauli': 'stpauli_hwnw_1999_2026.csv',
       'helgolandbinnenhafen': 'helgolandbinnenhafen_hwnw.csv',
       'bhvalterleuchtturm': 'bhvalterleuchtturm_hwnw.csv', 'husum': 'husum_hwnw.csv'}


def kurzname(k):
    k = k.replace('\xfc', 'ue').replace('\xf6', 'oe').replace('\xe4', 'ae').replace('\xdf', 'ss')
    return 'cuxhaven' if k == 'cuxhavensteubenhft' else k


def saetze():
    """-> [(name, lat, lon)] der Pegelonline-/HPA-Saetze in OBS."""
    out, kopf = [], []
    L = open(os.path.join(ROOT, OBS), encoding='latin-1').read().split('\n')
    for i, z in enumerate(L):
        if z.startswith('#'):
            kopf.append(z)
            continue
        if kopf and i + 1 < len(L) and re.match(r'^[+-]\d\d:\d\d', L[i + 1]):
            k = '\n'.join(kopf)
            la, lo = re.search(r'!latitude: (\S+)', k), re.search(r'!longitude: (\S+)', k)
            if la and lo and ('Pegelonline' in k or 'HPA' in k):
                out.append((z, float(la.group(1)), float(lo.group(1))))
        if z:
            kopf = []
    return out


def pegel():
    """-> {kurz: dict(quelle, satz)}; quelle = Zip-Pfad oder ('hpa', KZ)."""
    st = json.load(open(os.path.join(GER, 'npz_stationen.json')))
    S = saetze()
    namen = {s[0] for s in S}
    kand = {}
    for f in sorted(glob.glob(os.path.join(GER, 'pegelonline-*-W-*.zip'))):
        k = os.path.basename(f).split('-W-')[0][len('pegelonline-'):]
        if k in NAMEN:
            if NAMEN[k] in namen:
                kand[kurzname(k)] = (f, NAMEN[k], 0.0)
            continue
        if k not in st:
            continue
        a = st[k]
        b = min(S, key=lambda s: math.hypot(s[1] - a['lat'], (s[2] - a['lon']) * 0.6))
        d = 111 * math.hypot(b[1] - a['lat'], (b[2] - a['lon']) * 0.6)
        if d < 1.0:
            kand[kurzname(k)] = (f, b[0], d)
    beste = {}
    for k, (f, n, d) in kand.items():                 # zwei Reihen am selben Satz: die naehere
        if n not in beste or d < beste[n][2]:
            beste[n] = (k, f, d)
    out = {k: dict(quelle=f, satz=n) for n, (k, f, d) in beste.items()}
    for k, (kz, n) in HPA.items():
        if n in namen:
            out[k] = dict(quelle=('hpa', kz), satz=n)
    return out


UK = os.path.join(ROOT, 'water_levels/UK/bodc_sea_level_2007-2026_values_and_residuals_acd')
AUSLAND = (('hic_code', 'be', lambda c: os.path.join(ROOT, 'water_levels/Belgium_waterinfo', c + '.csv')),
           ('shom_code', 'fr', lambda c: os.path.join(ROOT, 'water_levels/France_SHOM', c + '.csv')),
           ('bodc_code', 'uk', lambda c: glob.glob(os.path.join(UK, f'20??{c}.txt')) and c))


def pegel_ausland():
    """Belgien (waterinfo.be 10 min), Frankreich (SHOM 10 min), UK (BODC 15 min): Satz ueber den Code
    im Satzkopf (hic_code/shom_code/bodc_code), nur Messsaetze aus OBS. -> {kurz: dict(quelle, satz)}"""
    out, kopf = {}, []
    L = open(os.path.join(ROOT, OBS), encoding='latin-1').read().split('\n')
    for i, z in enumerate(L):
        if z.startswith('#'):
            kopf.append(z)
            continue
        if kopf and i + 1 < len(L) and re.match(r'^[+-]\d\d:\d\d', L[i + 1]):
            k = '\n'.join(kopf)
            for feld, land, pfad in AUSLAND:
                m = re.search(rf'^# {feld}: (\S+)', k, re.M)
                if m and 'observed' in k.lower() or m and land == 'uk':
                    q = pfad(m.group(1))
                    if q and (land == 'uk' or os.path.exists(q)):
                        out[f'{land}_{m.group(1).lower().replace("-", "_")}'] = dict(quelle=(land, q), satz=z)
        if z:
            kopf = []
    return out


def lesen_ausland(land, q):
    """-> pd.Series m, UTC-Index"""
    import pandas as pd
    if land in ('be', 'fr'):
        d = pd.read_csv(q)
        t = pd.to_datetime(d.iloc[:, 0], utc=True, format='mixed')
        s = pd.Series(pd.to_numeric(d.iloc[:, 1], errors='coerce').values, index=t)
    else:                   # BODC: Jahresdateien JJJJCODE.txt, ab 2023/25 Monatsdateien CODEJJMM.txt; Flag N = Fehlwert
        zeilen = []
        for f in sorted(glob.glob(os.path.join(UK, f'20??{q}.txt')) + glob.glob(os.path.join(UK, f'{q}[0-9][0-9][0-9][0-9].txt'))):
            for z in open(f, encoding='latin-1'):
                m = re.match(r'^\s*\d+\)\s+(\d{4}/\d\d/\d\d \d\d:\d\d:\d\d)\s+(-?\d+\.\d+)([A-Z]?)', z)
                if m and m.group(3) != 'N' and float(m.group(2)) > -90:
                    zeilen.append((m.group(1), float(m.group(2))))
        d = pd.DataFrame(zeilen, columns=['t', 'h'])
        s = pd.Series(d.h.values, index=pd.to_datetime(d.t, format='%Y/%m/%d %H:%M:%S').dt.tz_localize('UTC'))
    s = s.dropna()
    return s[~s.index.duplicated()].sort_index()


def scheitel_pfad(k):
    a = os.path.join(GER, ALT.get(k, ''))
    return a if k in ALT and os.path.exists(a) else os.path.join(SCHEITEL, k + '.csv')


def scheitel(arg):
    k, q = arg
    ziel = scheitel_pfad(k)
    if os.path.exists(ziel):
        return k, 'vorhanden'
    import contextlib
    import io
    import elbe_scheitel_laden as EL
    os.makedirs(SCHEITEL, exist_ok=True)
    tmp = ziel + '.teil'
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            if isinstance(q, (list, tuple)) and q[0] == 'hpa':
                EL.main(None, tmp, EL.lesen_hpa(q[1], SKN_PNP))
            elif isinstance(q, (list, tuple)):
                EL.main(None, tmp, lesen_ausland(*q))
            else:
                EL.main(q, tmp)
        os.replace(tmp, ziel)
        return k, 'neu'
    except Exception as e:  # noqa: BLE001
        return k, f'Fehler {e}'


def _kennzahlen(mess, pred):
    P = HU.zuordnen(mess, pred)
    out = {}
    for art in 'HN':
        q = P[P.art == art]
        if len(q) < 200:
            out[art] = None
            continue
        dz = (q.t_pred - q.t_mess).values / 60.0
        dh = (q.h_pred - q.h_mess).values
        out[art] = dict(n=len(q), mittel=float(dz.mean()), sd=float(dz.std()), rms=float(np.sqrt((dz ** 2).mean())),
                        h_mittel=float(dh.mean()), h_rms=float(np.sqrt((dh ** 2).mean())))
    return out


def eichen_pruefen(arg):
    """Ein Pegel: beide Fenster eichen, 2025 pruefen. -> (kurz, ergebnis-dict)"""
    k, p, ablage = arg
    import contextlib
    import io
    csv = scheitel_pfad(k)
    if not os.path.exists(csv):
        return k, dict(fehler='keine Scheitel')
    datei = os.path.join(ROOT, OBS)
    jahre = {int(z[:4]) for z in open(csv).read().split('\n')[1:] if z[:4].isdigit()}
    t0 = dt.datetime(PRUEF, 1, 1, tzinfo=dt.timezone.utc).timestamp()
    t1 = dt.datetime(PRUEF + 1, 1, 1, tzinfo=dt.timezone.utc).timestamp()
    mess = HU.scheitel_csv(csv, PRUEF, PRUEF)
    try:
        harm = _kennzahlen(mess, HU.satz_ereignisse(datei, p['satz'], t0 - 86400, t1 + 86400))
    except Exception as e:  # noqa: BLE001
        return k, dict(fehler=f'Satz: {e}')
    erg = dict(satz=p['satz'], harm=harm, fenster={})
    if not harm['H'] or not harm['N']:
        erg['fehler'] = f'zu wenig Scheitel {PRUEF}'
        return k, erg
    for j0, j1 in FENSTER:
        j0 = max(j0, min(jahre))
        if len([j for j in jahre if j0 <= j <= j1]) < 3:
            continue
        HU.ZIEL = os.path.join(ablage, f'{j0}_{j1}')
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                HU.eichen(k, csv, OBS, p['satz'], j0, j1)
                HU.eichen_mond(k, csv, j0, j1)
            erg['fenster'][f'{j0}_{j1}'] = dict(
                satz=_kennzahlen(mess, HU.vorhersage(k, t0 - 86400, t1 + 86400)),
                mond=_kennzahlen(mess, HU.vorhersage_mond(k, t0 - 86400, t1 + 86400)))
        except Exception as e:  # noqa: BLE001
            erg['fenster'][f'{j0}_{j1}'] = dict(fehler=str(e))
    return k, erg


def waehlen(erg):
    """-> (fenster|None, wahl {'H','N'}) nach Zeit-RMS 2025."""
    best = None
    for f, v in erg.get('fenster', {}).items():
        if 'fehler' in v:
            continue
        w, summe = {}, 0.0
        for art in 'HN':
            h = erg['harm'][art]
            opt = [('harm', h['rms'])]
            for var in ('satz', 'mond'):
                x = v[var][art]
                if x and x['rms'] <= h['rms'] - 1.0 and x['h_rms'] <= h['h_rms'] + 0.03:
                    opt.append((var, x['rms']))
            w[art], r = min(opt, key=lambda o: o[1])
            summe += r
        if best is None or summe < best[0]:
            best = (summe, f, w)
    return (best[1], best[2]) if best else (None, {'H': 'harm', 'N': 'harm'})


def main(argv):
    schritt = argv[0] if argv and not argv[0].startswith('--') else 'alles'
    opt = dict(a[2:].split('=', 1) for a in argv if a.startswith('--'))
    P = {}
    if schritt != 'veraltet' and opt.get('land', 'de') in ('de', 'alle'):
        P.update(pegel())
    if schritt != 'veraltet' and opt.get('land', 'de') != 'de':
        P.update({k: v for k, v in pegel_ausland().items() if opt['land'] == 'alle' or k.startswith(opt['land'] + '_')})
    if schritt == 'veraltet':          # nach Neufit/Umbenennung (tcd_bauen.py ruft das auf)
        opt['land'], schritt = 'alle', 'alles'
        P = dict(pegel(), **pegel_ausland())
        D = HU.TR.datei(os.path.join(ROOT, OBS))
        alt = []
        for f in sorted(os.listdir(HU.ZIEL)):
            k = f[:-5]
            E = HU.laden(k)
            s = D.saetze.get(E['satz'])
            if k in P and (s is None or E.get('fingerabdruck') != HU.fingerabdruck(s) or P[k]['satz'] != E['satz']):
                alt.append(k)
        print('HW/NW-Modelle veraltet:', ', '.join(alt) or 'keine', flush=True)
        if not alt:
            return 0
        opt['nur'] = ','.join(alt)
    if opt.get('nur'):
        P = {k: v for k, v in P.items() if k in opt['nur'].split(',')}
    n = int(opt.get('prozesse', 4))
    print(len(P), 'Pegel', flush=True)
    if schritt in ('scheitel', 'alles'):
        with Pool(n) as pool:
            for k, r in pool.imap_unordered(scheitel, [(k, v['quelle']) for k, v in P.items()]):
                print(f'scheitel {k:28} {r}', flush=True)
    if schritt not in ('eichen', 'alles'):
        return 0
    ablage = tempfile.mkdtemp(prefix='hwnw_')
    ergebnisse = {}
    with Pool(n) as pool:
        for k, e in pool.imap_unordered(eichen_pruefen, [(k, v, ablage) for k, v in P.items()]):
            ergebnisse[k] = e
            print(f'geeicht  {k:28} {e.get("fehler", "")}', flush=True)
    zeilen = ['kurz;satz;fenster;wahl_hw;wahl_nw;n_hw;n_nw;harm_rms_hw;harm_rms_nw;neu_rms_hw;neu_rms_nw;'
              'harm_mittel_hw;harm_mittel_nw;neu_mittel_hw;neu_mittel_nw;harm_hrms_hw;harm_hrms_nw;neu_hrms_hw;neu_hrms_nw;bemerkung']
    for k in sorted(ergebnisse):
        e = ergebnisse[k]
        f, w = waehlen(e) if 'fehler' not in e else (None, {'H': 'harm', 'N': 'harm'})
        ziel = os.path.join(HU.ROOT, 'harmonics/hwnw', k + '.json')
        if k in OHNE:
            w = {'H': 'harm', 'N': 'harm'}
            e['fehler'] = 'Satz mit Zusatzscheiteln (OHNE)'
        if f and set(w.values()) != {'harm'}:
            E = json.load(open(os.path.join(ablage, f, k + '.json')))
            E['wahl'] = w
            E['pruefung'] = {art: dict(jahr=PRUEF, harm_rms=e['harm'][art]['rms'],
                                       rms=(e['harm'][art] if w[art] == 'harm' else e['fenster'][f][w[art]][art])['rms'])
                             for art in 'HN'}
            json.dump(E, open(ziel, 'w'), indent=1)
        elif os.path.exists(ziel):
            os.remove(ziel)
        z = [k, e.get('satz', P[k]['satz']), f or '', w['H'], w['N']]
        h = e.get('harm') or {}
        neu = {a: (h.get(a) if w[a] == 'harm' or not f else e['fenster'][f][w[a]][a]) for a in 'HN'}
        for feld, fmt in (('n', '{:d}'), ('rms', '{:.1f}'), ('mittel', '{:+.1f}'), ('h_rms', '{:.3f}')):
            for quelle in ((h,) if feld == 'n' else (h, neu)):
                for a in 'HN':
                    x = quelle.get(a) if quelle else None
                    z.append(fmt.format(x[feld]) if x else '')
        z.append(e.get('fehler', ''))
        zeilen.append(';'.join(str(x) for x in z))
    aus = os.path.join(ROOT, 'harmonics/help', f'hwnw_auswahl_{dt.date.today():%Y%m%d}.csv')
    if os.path.exists(aus):             # Zeilen anderer Pegel (frueherer Lauf desselben Tages) behalten
        alt = open(aus, encoding='utf-8').read().split('\n')[1:]
        zeilen += [z for z in alt if z and z.split(';')[0] not in ergebnisse]
        zeilen = zeilen[:1] + sorted(zeilen[1:])
    open(aus, 'w', encoding='utf-8').write('\n'.join(zeilen) + '\n')
    shutil.rmtree(ablage, ignore_errors=True)
    print('->', aus)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
