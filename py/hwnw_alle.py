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

Ausland (--land=be|fr|uk|hp|us|alle): waterinfo.be, SHOM, BODC, HydroPortail (Stundenwerte, franz. Fluesse); Satz ueber hic_code/shom_code/bodc_code/station_id_context im Kopf.
USA (--land=us, 5.11.2026): gemessene HW/NW direkt aus NOAA CO-OPS (Produkt high_low, MLLW, metrisch, UTC), Saetze aus
harmonics-dwf (noaa_station_id im Kopf); Stationsliste USA.
Nach jeder Eichung: plausibel (Modelle mit > MAX_VERLETZT unpassenden Scheiteln 2026 werden geloescht).
Usage: venv/bin/python py/hwnw_alle.py [scheitel|eichen|alles|veraltet|plausibel] [--land=de] [--nur=kurz,kurz] [--prozesse=4]
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
TAB = 'harmonics/utide/harmonics_utide_tidetables.txt'
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
OHNE = {'be_04dur04a_1066', 'be_04dur05a_1066', 'uk_wey', 'hp_h514011001'}   # Weymouth doppeltes NW, Tancarville HW-Stand
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


DWF = 'harmonics/classic/harmonics-dwf-20251228-free.txt'
# USA-Test 5.11.2026: flache Aestuare, an denen der harmonische Satz die verzerrte Tide am schlechtesten trifft
# 5.11.2026: Test an 10 Aestuaren klar positiv (Delaware HW 16->11, NW 23->14 min) -> alle Saetze mit
# noaa_station_id; ohne MLLW-HW/NW bei CO-OPS (Flusspegel mit eigenem Bezug) bricht laden_usa ab.
USA = set(json.load(open(os.path.join(ROOT, 'water_levels/USA_COOPS/wasserstand_stationen.json'))))   # CO-OPS mdapi type=waterlevels, tidal
USA_TEST = ('8545240', '8540433', '8551910', '8573927', '8574680', '8518995', '8658120', '9440083', '9440422', '9455920')
COOPS = ('https://api.tidesandcurrents.noaa.gov/api/prod/datagetter?product=high_low&station={}&begin_date={}0101'
         '&end_date={}1231&datum=MLLW&units=metric&time_zone=gmt&format=csv&application=tiden_pruefung')
JAHRE_US = range(2014, PRUEF + 1)


def pegel_usa():
    """-> {us_<id>: dict(quelle=('us', id), satz, datei)} fuer die Stationen in USA mit Satz in DWF."""
    out, kopf = {}, []
    L = open(os.path.join(ROOT, DWF), encoding='latin-1').read().split('\n')
    for i, z in enumerate(L):
        if z.startswith('#'):
            kopf.append(z)
            continue
        if kopf and i + 1 < len(L) and re.match(r'^[+-]\d\d:\d\d', L[i + 1]) and 'Current' not in z:
            m = re.search(r'^# noaa_station_id: (\d+)', '\n'.join(kopf), re.M)
            if m and (USA is None or m.group(1) in USA):
                out['us_' + m.group(1)] = dict(quelle=('us', m.group(1)), satz=z, datei=DWF)
        if z:
            kopf = []
    return out


def laden_usa(nr, ziel):
    """CO-OPS high_low je Jahr -> Scheitel-CSV (utc,hoehe_m,art); H/HH -> H, L/LL -> N."""
    import time
    import urllib.request
    zeilen = []
    for j in JAHRE_US:
        req = urllib.request.Request(COOPS.format(nr, j, j), headers={'User-Agent': 'tiden-pruefung/1.0'})
        with urllib.request.urlopen(req, timeout=120) as r:
            for z in r.read().decode().split('\n')[1:]:
                t = [x.strip() for x in z.split(',')]
                if len(t) >= 3 and t[1] and t[2] in ('H', 'HH', 'L', 'LL'):
                    zeilen.append(f"{t[0]},{float(t[1]):.3f},{'H' if t[2].startswith('H') else 'N'}")
        time.sleep(1.5)                 # 5.11.2026: 4 parallele Abrufe ohne Pause -> CO-OPS 403; nur mit --prozesse=1 laden
    if len(zeilen) < 1000:
        raise RuntimeError(f'nur {len(zeilen)} Scheitel')
    open(ziel, 'w').write('utc,hoehe_m,art\n' + '\n'.join(sorted(set(zeilen))) + '\n')


# Niederlande (5.11.2026): gemessene Getijextreme von Rijkswaterstaat (DDL v2, Groepering GETETM2, NAP, cm),
# Typ hoogwater/laagwater aus der Begleitreihe Grootheid NVT. Orte: water_levels/Netherlands_RWS_extremen/stationen.json
RWS = 'https://ddapi20-waterwebservices.rijkswaterstaat.nl/ONLINEWAARNEMINGENSERVICES/OphalenWaarnemingen'
NL_DIR = os.path.join(ROOT, 'water_levels/Netherlands_RWS_extremen')
NL_TEST = None          # z. B. {'hoekvanholland', ...} fuer einen Probelauf


def pegel_nl():
    """RWS-Orte mit GETETM2 -> naechster NAP-Satz in OBS (< 1 km). -> {nl_<code>: dict(quelle=('nl', code), satz)}"""
    orte = {c: (n, la, lo) for c, n, la, lo in json.load(open(os.path.join(NL_DIR, 'stationen.json')))}
    S, kopf = [], []
    L = open(os.path.join(ROOT, OBS), encoding='latin-1').read().split('\n')
    for i, z in enumerate(L):
        if z.startswith('#'):
            kopf.append(z)
            continue
        if kopf and i + 1 < len(L) and re.match(r'^[+-]\d\d:\d\d', L[i + 1]) and z.endswith('Netherlands'):
            k = '\n'.join(kopf)
            la, lo = re.search(r'!latitude: (\S+)', k), re.search(r'!longitude: (\S+)', k)
            if la and lo and re.search(r'^# datum: NAP', k, re.M):
                S.append((z, float(la.group(1)), float(lo.group(1))))
        if z:
            kopf = []
    beste = {}
    for c, (n, la, lo) in orte.items():
        if NL_TEST and c not in NL_TEST:
            continue
        b = min(S, key=lambda s: math.hypot(s[1] - la, (s[2] - lo) * 0.62))
        d = 111 * math.hypot(b[1] - la, (b[2] - lo) * 0.62)
        if d < 1.0 and (b[0] not in beste or d < beste[b[0]][1]):
            beste[b[0]] = (c, d)
    return {'nl_' + c.replace('.', '_'): dict(quelle=('nl', c), satz=n) for n, (c, d) in beste.items()}


def _rws(code, grootheid, j, groep='GETETM2', von='01-01T00:00:00', bis='12-31T23:59:59'):
    import urllib.request
    meta = {'Grootheid': {'Code': grootheid}, 'Groepering': {'Code': groep}}
    if not groep:                        # 10-min-Messung: nur NAP, geprueft vor ungeprueft
        meta['Hoedanigheid'] = {'Code': 'NAP'}
    q = {'Locatie': {'Code': code}, 'AquoPlusWaarnemingMetadata': {'AquoMetadata': meta},
         'Periode': {'Begindatumtijd': f'{j}-{von}.000+00:00', 'Einddatumtijd': f'{j}-{bis}.000+00:00'}}
    req = urllib.request.Request(RWS, data=json.dumps(q).encode(), headers={'Content-Type': 'application/json',
                                                                            'User-Agent': 'tiden-pruefung/1.0'})
    with urllib.request.urlopen(req, timeout=180) as r:
        d = json.load(r)
    if not groep:
        out = {}
        for w in sorted(d.get('WaarnemingenLijst', []), key=lambda w: w['MetingenLijst'][0]['WaarnemingMetadata']
                        .get('Statuswaarde') == 'Gecontroleerd' if w['MetingenLijst'] else False):
            out.update({m['Tijdstip']: m['Meetwaarde'] for m in w['MetingenLijst']})   # Gecontroleerd zuletzt = gewinnt
        return out
    return {m['Tijdstip']: m['Meetwaarde'] for w in d.get('WaarnemingenLijst', []) for m in w['MetingenLijst']}


def _scheitel_aus_10min(code, j):
    import contextlib
    import io
    import pandas as pd
    import elbe_scheitel_laden as EL
    r = {}
    for von, bis in (('01-01T00:00:00', '03-31T23:59:59'), ('04-01T00:00:00', '06-30T23:59:59'),
                     ('07-01T00:00:00', '09-30T23:59:59'), ('10-01T00:00:00', '12-31T23:59:59')):
        try:                             # ganzes Jahr auf einmal ist RWS zu gross (5.11.2026): quartalsweise
            r.update(_rws(code, 'WATHTE', j, groep='', von=von, bis=bis))
        except Exception as e:  # noqa: BLE001
            print(code, j, von[:5], 'Fehler', e, flush=True)
    w = {ts: m.get('Waarde_Numeriek') for ts, m in r.items()}
    w = {ts: v for ts, v in w.items() if v is not None and abs(v) < 2000}
    if len(w) < 20000:
        return []
    s = pd.Series([v / 100 for v in w.values()], index=pd.to_datetime(list(w.keys()), utc=True)).sort_index()
    tmp = os.path.join(tempfile.mkdtemp(prefix='nl_'), 'x.csv')
    with contextlib.redirect_stdout(io.StringIO()):
        EL.main(None, tmp, s)
    out = [z for z in open(tmp).read().split('\n')[1:] if z.startswith(str(j))]
    shutil.rmtree(os.path.dirname(tmp), ignore_errors=True)
    return out


def laden_nl(code, ziel):
    import time
    zeilen = []
    for j in JAHRE_US:
        try:
            h, t = _rws(code, 'WATHTE', j), _rws(code, 'NVT', j)
        except Exception as e:  # noqa: BLE001  -- Jahr ohne Extreme (2025: leere Antwort) -> unten aus 10 min
            if 'HTTP Error 204' not in str(e) and 'Expecting value' not in str(e):
                print(code, j, e, flush=True)
            h, t = {}, {}
        for ts, w in h.items():
            typ = (t.get(ts) or {}).get('Waarde_Alfanumeriek', '')
            v = w.get('Waarde_Numeriek')
            if v is None or abs(v) > 2000 or typ not in ('hoogwater', 'laagwater', 'laagwater 1', 'laagwater 2'):
                continue
            u = dt.datetime.fromisoformat(ts).astimezone(dt.timezone.utc)
            zeilen.append(f"{u:%Y-%m-%d %H:%M},{v / 100:.3f},{'H' if typ == 'hoogwater' else 'N'}")
        time.sleep(0.5)
        if sum(z.startswith(str(j)) for z in zeilen) < 1300:   # Extreme fehlen/unvollstaendig (2025 noch nicht abgeleitet):
            eigen = _scheitel_aus_10min(code, j)                  # ganzes Jahr selbst aus 10 min, nur EINE Quelle je Jahr
            if len(eigen) > sum(z.startswith(str(j)) for z in zeilen):
                zeilen = [z for z in zeilen if not z.startswith(str(j))] + eigen
    if len(zeilen) < 1000:
        raise RuntimeError(f'nur {len(zeilen)} Scheitel')
    open(ziel, 'w').write('utc,hoehe_m,art\n' + '\n'.join(sorted(set(zeilen))) + '\n')


# Kanada (5.11.2026): CHS IWLS wlo (3-min-Messung, Kartennull, ab ~10/2019, hoechstens 7 Tage je Abruf);
# Saetze aus TAB ueber '# chs_id:' im Kopf.
CA_DIR = os.path.join(ROOT, 'water_levels/Canada_CHS_wlo')
CA_TEST = None          # 5.11.2026 Test an 9 Orten positiv -> Auswahl per --nur (Aestuare, Fluesse)


def pegel_ca():
    st = json.load(open(os.path.join(CA_DIR, 'stationen.json')))
    out, kopf = {}, []
    L = open(os.path.join(ROOT, TAB), encoding='latin-1').read().split('\n')
    for i, z in enumerate(L):
        if z.startswith('#'):
            kopf.append(z)
            continue
        if kopf and i + 1 < len(L) and re.match(r'^[+-]\d\d:\d\d', L[i + 1]) and 'Current' not in z:
            m = re.search(r'^# chs_id: (\d+)', '\n'.join(kopf), re.M)
            if m and m.group(1) in st and (CA_TEST is None or m.group(1) in CA_TEST):
                out['ca_' + m.group(1)] = dict(quelle=('ca', m.group(1)), satz=z, datei=TAB)
        if z:
            kopf = []
    return out


def lesen_ca(code):
    """3-min-Reihe wochenweise laden (Cache water_levels/Canada_CHS_wlo/<code>.csv) -> pd.Series (m, UTC)."""
    import time
    import urllib.request
    import pandas as pd
    cache = os.path.join(CA_DIR, code + '.csv')
    if not os.path.exists(cache):
        sid = json.load(open(os.path.join(CA_DIR, 'stationen.json')))[code]['id']
        zeilen, fehl = [], 0
        a = dt.datetime(2019, 10, 1, tzinfo=dt.timezone.utc)
        while a < dt.datetime(PRUEF + 1, 1, 1, tzinfo=dt.timezone.utc):
            b = a + dt.timedelta(days=7)
            url = (f'https://api-iwls.dfo-mpo.gc.ca/api/v1/stations/{sid}/data?time-series-code=wlo'
                   f'&from={a:%Y-%m-%dT%H:%M:%SZ}&to={b:%Y-%m-%dT%H:%M:%SZ}')
            for versuch in range(5):     # 5.11.2026: 3 parallele Laeufe -> Ablehnungen; nacheinander, mehr Geduld
                try:
                    with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'tiden-pruefung/1.0'}),
                                                timeout=120) as r:
                        zeilen += [f"{x['eventDate'][:19]},{x['value']}" for x in json.load(r) if x.get('value') is not None]
                    break
                except Exception:  # noqa: BLE001
                    time.sleep(15 * (versuch + 1))
            else:
                fehl += 1
            time.sleep(1.0)
            a = b
        if fehl:
            print(code, f'{fehl} Wochen ohne Antwort', flush=True)
        open(cache, 'w').write('utc,h\n' + '\n'.join(sorted(set(zeilen))) + '\n')
    d = pd.read_csv(cache)
    s = pd.Series(d.h.values, index=pd.to_datetime(d.utc, utc=True))
    return s[~s.index.duplicated()].sort_index()


# Irland (5.11.2026): Marine-Institute-Reihen, die schon fuer die Fits geladen waren
# (water_levels/Ireland_MI/npz/*.npz, 5 min, 2007-2025, LAT); Satz = naechster irischer Satz in OBS (< 1 km)
IE_DIR = os.path.join(ROOT, 'water_levels/Ireland_MI/npz')


def pegel_ie():
    S, kopf = [], []
    L = open(os.path.join(ROOT, OBS), encoding='latin-1').read().split('\n')
    for i, z in enumerate(L):
        if z.startswith('#'):
            kopf.append(z)
            continue
        if kopf and i + 1 < len(L) and re.match(r'^[+-]\d\d:\d\d', L[i + 1]) and z.endswith(', Ireland'):
            k = '\n'.join(kopf)
            la, lo = re.search(r'!latitude: (\S+)', k), re.search(r'!longitude: (\S+)', k)
            if la and lo and re.search(r'^# datum: LAT', k, re.M):
                S.append((z, float(la.group(1)), float(lo.group(1))))
        if z:
            kopf = []
    out = {}
    for f in sorted(glob.glob(os.path.join(IE_DIR, '*.npz'))):
        d = np.load(f, allow_pickle=True)
        la, lo = float(d['latitude']), float(d['longitude'])
        b = min(S, key=lambda s: math.hypot(s[1] - la, (s[2] - lo) * 0.6))
        if 111 * math.hypot(b[1] - la, (b[2] - lo) * 0.6) < 1.0:
            out['ie_' + os.path.basename(f)[:-4].lower().replace('-', '_')] = dict(quelle=('ie', f), satz=b[0])
    return out


def lesen_ie(f):
    import pandas as pd
    d = np.load(f, allow_pickle=True)
    s = pd.Series(d['levels_m'], index=pd.to_datetime(d['datetimes_utc']).tz_localize('UTC')).dropna()
    return s[~s.index.duplicated()].sort_index()


UK = os.path.join(ROOT, 'water_levels/UK/bodc_sea_level_2007-2026_values_and_residuals_acd')
AUSLAND = (('hic_code', 'be', lambda c: os.path.join(ROOT, 'water_levels/Belgium_waterinfo', c + '.csv')),
           ('shom_code', 'fr', lambda c: os.path.join(ROOT, 'water_levels/France_SHOM', c + '.csv')),
           ('bodc_code', 'uk', lambda c: glob.glob(os.path.join(UK, f'20??{c}.txt')) and c),
           ('station_id_context', 'hp', lambda c: c.startswith('HydroPortail-') and os.path.join(
               ROOT, 'water_levels/France_HydroPortail', 'hp_' + c.split('-', 1)[1] + '.csv')))


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
                if m and (land in ('uk', 'hp') or 'observed' in k.lower()):
                    q = pfad(m.group(1))
                    if q and (land == 'uk' or os.path.exists(q)):
                        code = m.group(1).split('-', 1)[1] if land == 'hp' else m.group(1)
                        out[f'{land}_{code.lower().replace("-", "_")}'] = dict(quelle=(land, q), satz=z)
        if z:
            kopf = []
    return out


def lesen_ausland(land, q):
    """-> pd.Series m, UTC-Index"""
    import pandas as pd
    if land in ('be', 'fr', 'hp'):
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


def auf_satzbezug(s, satz):
    """HydroPortail-Saetze liegen auf ~LAT (Z0 aus dem 19-Jahres-Minimum), die Reihe auf dem Pegelnull:
    Reihe so verschieben, dass ihr Mittel 2016-2025 = Z0 des Satzes ist (sonst stellte die eigene Rechnung
    die Hoehen still auf den Pegelnull um)."""
    z0 = HU.TR.datei(os.path.join(ROOT, OBS)).saetze[satz].z0
    return s + (z0 - s['2016':'2025'].mean())


def scheitel(arg):
    k, q, satz = arg
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
            if isinstance(q, (list, tuple)) and q[0] == 'us':
                laden_usa(q[1], tmp)
            elif isinstance(q, (list, tuple)) and q[0] == 'nl':
                laden_nl(q[1], tmp)
            elif isinstance(q, (list, tuple)) and q[0] == 'ca':
                EL.main(None, tmp, lesen_ca(q[1]))
            elif isinstance(q, (list, tuple)) and q[0] == 'ie':
                EL.main(None, tmp, lesen_ie(q[1]))
            elif isinstance(q, (list, tuple)) and q[0] == 'hpa':
                EL.main(None, tmp, EL.lesen_hpa(q[1], SKN_PNP))
            elif isinstance(q, (list, tuple)) and q[0] == 'hp':
                EL.main(None, tmp, auf_satzbezug(lesen_ausland(*q), satz))
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
    datei = os.path.join(ROOT, p.get('datei', OBS))
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
                HU.eichen(k, csv, p.get('datei', OBS), p['satz'], j0, j1, glieder=HU.GLIEDER_MOND)   # Versuch 4.11.: HW 12,74 -> 12,36 min
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


MAX_VERLETZT = 6      # 5.11.2026: mehr unpassende Scheitel je Jahr (HW <= NW daneben, < 30 min) -> kein Modell


def unplausibel_zahl(k, jahr=PRUEF + 1):
    """Unpassende Scheitel des Modells k im Jahr `jahr` (vor der Reparatur in HU.vorhersage_kombi), ABZUEGLICH
    derer, die schon der harmonische Satz hat (echte Doppel-NW wie Hoek van Holland, 5.11.2026)."""
    t0 = dt.datetime(jahr, 1, 1, tzinfo=dt.timezone.utc).timestamp()
    E = HU.laden(k)
    satz = len(HU.verletzungen(HU.satz_ereignisse(os.path.join(ROOT, E['datei']), E['satz'], t0, t0 + 365 * 86400)))
    return max(len(HU.verletzungen(HU.vorhersage_kombi(k, t0, t0 + 365 * 86400, reparieren=False))) - satz, 0)


def _plausibel_eins(k):
    try:
        return k, unplausibel_zahl(k)
    except Exception as e:  # noqa: BLE001
        return k, f'Fehler {e}'


def plausibel(nur=None, n=4):
    """Alle (oder nur `nur`) Modelle pruefen; mit mehr als MAX_VERLETZT unpassenden Scheiteln loeschen.
    -> {kurz: zahl}; Liste harmonics/help/hwnw_unplausibel_<datum>.csv"""
    ks = [f[:-5] for f in sorted(os.listdir(HU.ZIEL)) if f.endswith('.json') and (not nur or f[:-5] in nur)]
    erg = {}
    with Pool(n) as pool:
        for k, z in pool.imap_unordered(_plausibel_eins, ks):
            erg[k] = z
    weg = sorted(k for k, z in erg.items() if isinstance(z, int) and z > MAX_VERLETZT)
    zeilen = ['kurz;satz;verletzungen;aktion']
    for k in sorted(erg):
        if erg[k] == 0:
            continue
        satz = HU.laden(k)['satz']
        zeilen.append(f"{k};{satz};{erg[k]};{'geloescht' if k in weg else 'repariert zur Laufzeit'}")
    for k in weg:
        os.remove(os.path.join(HU.ZIEL, k + '.json'))
    aus = os.path.join(ROOT, 'harmonics/help', f'hwnw_unplausibel_{dt.date.today():%Y%m%d}.csv')
    open(aus, 'w', encoding='utf-8').write('\n'.join(zeilen) + '\n')
    print(f'{len(erg)} Modelle, {len(zeilen) - 1} mit unpassenden Scheiteln, {len(weg)} geloescht (> {MAX_VERLETZT}) -> {aus}')
    return erg


def main(argv):
    schritt = argv[0] if argv and not argv[0].startswith('--') else 'alles'
    opt = dict(a[2:].split('=', 1) for a in argv if a.startswith('--'))
    if schritt == 'plausibel':
        plausibel(opt['nur'].split(',') if opt.get('nur') else None, int(opt.get('prozesse', 4)))
        return 0
    P = {}
    if schritt != 'veraltet' and opt.get('land', 'de') in ('de', 'alle'):
        P.update(pegel())
    if schritt != 'veraltet' and opt.get('land', 'de') != 'de':
        P.update({k: v for k, v in dict(pegel_ausland(), **pegel_usa(), **pegel_nl(), **pegel_ca(), **pegel_ie()).items()
                  if opt['land'] == 'alle' or k.startswith(opt['land'] + '_')})
    if schritt == 'veraltet':          # nach Neufit/Umbenennung (tcd_bauen.py ruft das auf)
        opt['land'], schritt = 'alle', 'alles'
        P = dict(pegel(), **pegel_ausland(), **pegel_usa(), **pegel_nl(), **pegel_ca(), **pegel_ie())
        alt = []
        for f in sorted(os.listdir(HU.ZIEL)):
            k = f[:-5]
            E = HU.laden(k)
            s = HU.TR.datei(os.path.join(ROOT, E['datei'])).saetze.get(E['satz'])
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
            for k, r in pool.imap_unordered(scheitel, [(k, v['quelle'], v['satz']) for k, v in P.items()]):
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
    plausibel([k for k in ergebnisse if os.path.exists(os.path.join(HU.ZIEL, k + '.json'))], n)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
