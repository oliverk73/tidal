#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Luecken aus dem UKHO-Index (help/ukho_index_abgleich.csv, Status 'luecke') mit amtlichen Vorhersagestationen
schliessen, Oliver 21.11.2026 ("Ja" zu: freie Quellen jetzt, China/Russland/Karibik/SO-Asien spaeter per ATT).

NOAA: Vorhersageorte (mdapi type=tidepredictions; meist Nebenorte 'S', die NOAA nur als HW/NW vorhersagt) bis 6 km
mit gleichem Namen (bzw. derselben Bucht). CHS: IWLS wlp-hilo. Je Ort HW/NW 2025+2026 laden, Scheitelfit
(py/scheitelfit.py, 67 Tiden), Probe Fit 2025 gegen 2026, Bandbreitenpruefung (keine erfundenen Scheitel).
Saetze -> harmonics_utide_tidetables.txt, alle in help/neu_pruefen_<datum>.csv.

Usage: venv/bin/python py/luecken_amtlich.py [--alle | --band MIN MAX --ziel DATEI --ohne-pruefliste] [--schreiben]
"""
import csv
import datetime as dt
import json
import os
import sys
import time
import urllib.request

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import noaa_hwnw_scheitelfit as NH                                  # noqa: E402
import scheitelfit as SF                                            # noqa: E402
import xtide_modell as X                                            # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ZIEL = os.path.join(ROOT, 'harmonics/utide/harmonics_utide_tidetables.txt')
PRUEF = os.path.join(ROOT, 'harmonics/help/neu_pruefen_%s.csv' % dt.date.today().strftime('%Y%m%d'))
CHS_CACHE = os.path.join(ROOT, 'quellen/tide_tables/CHS_hilo')
STAATEN = {'ME': ('Maine', 'America/New_York'), 'MD': ('Maryland', 'America/New_York'), 'FL': ('Florida', 'America/New_York'),
           'OR': ('Oregon', 'America/Los_Angeles'), 'CA': ('California', 'America/Los_Angeles'),
           'WA': ('Washington', 'America/Los_Angeles'), 'AK': ('Alaska', 'America/Anchorage'),
           'AL': ('Alabama', 'America/Chicago'), 'CT': ('Connecticut', 'America/New_York'), 'DE': ('Delaware', 'America/New_York'),
           'LA': ('Louisiana', 'America/Chicago'), 'MA': ('Massachusetts', 'America/New_York'),
           'NC': ('North Carolina', 'America/New_York'), 'NJ': ('New Jersey', 'America/New_York'),
           'SC': ('South Carolina', 'America/New_York'), 'VA': ('Virginia', 'America/New_York')}
# NOAA-Metadaten ohne Staat (21.11.): US-Orte zugeordnet; Ausland (Fidschi, Niue, Tonga, Ecuador, Mexiko) weggelassen --
# dort stimmen die NOAA-Koordinaten teils nicht (Neiafu Laenge 6,0 statt -174,0; Fidschi/Niue Vorzeichen vertauscht)
OHNE_STAAT = {'8723667': 'FL', 'TWC0959': 'WA', 'TWC1579': 'AK', 'TWC2021': 'AK', 'TWC2023': 'AK', 'TWC2025': 'AK',
              'TWC2321': 'AK', 'TWC2423': 'AK'}
PROVINZ = {'NL': 'Newfoundland and Labrador', 'NS': 'Nova Scotia', 'NB': 'New Brunswick', 'PE': 'Prince Edward Island',
           'QC': 'Québec', 'ON': 'Ontario', 'MB': 'Manitoba', 'BC': 'British Columbia', 'NU': 'Nunavut',
           'NT': 'Northwest Territories', 'YT': 'Yukon'}
TZ_PROV = {'NL': 'America/St_Johns', 'NS': 'America/Halifax', 'NB': 'America/Moncton', 'PE': 'America/Halifax',
           'QC': 'America/Toronto', 'MB': 'America/Winnipeg', 'BC': 'America/Vancouver', 'NU': 'America/Iqaluit',
           'NT': 'America/Yellowknife', 'YT': 'America/Whitehorse', 'ON': 'America/Toronto'}
# (UKHO-Indexname, NOAA-Id, Staat, unser Name) -- Zuordnung 21.11.2026 (Name gleich, <= 6 km; drei mit anderem
# Stationsnamen in derselben Bucht: Deadman Bay, Olga Bay, Gnat Cove)
NOAA = [
    ('Belfast', '8415191', 'ME', 'Belfast'), ('Blue Hill Harbour', '8414112', 'ME', 'Blue Hill Harbor'),
    ('Matinicus Harbour', '8414876', 'ME', 'Matinicus Harbor (Wheaton Island)'), ('Piney Point', '8578240', 'MD', 'Piney Point'),
    ('Deadman Bay', '8727695', 'FL', 'Steinhatchee River entrance (Deadman Bay)'),
    ('Bandon', '9432373', 'OR', 'Bandon (Coquille River)'), ('Bechers Bay', '9410962', 'CA', 'Bechers Bay (Santa Rosa Island)'),
    ('Prisoners Harbour', '9410971', 'CA', 'Prisoners Harbor (Santa Cruz Island)'), ('Trinidad Head', '9419059', 'CA', 'Trinidad Harbor'),
    ('Dungeness Bay', '9444471', 'WA', 'Dungeness'),
    ('Boca de Quadra', '9450305', 'AK', 'Boca de Quadra'), ('DRIFT RIVER TERMINAL', '9455741', 'AK', 'Drift River Terminal'),
    ('Gambier Bay', '9451909', 'AK', 'Good Island (Gambier Bay)'), ('Kimshan Cove', '9452583', 'AK', 'Kimshan Cove (Ogden Passage)'),
    ('Lancaster Cove', '9450373', 'AK', 'Lancaster Cove (Cholmondeley Sound)'), ('Lituya Bay', '9452928', 'AK', 'Lituya Bay'),
    ('Macleod Harbour', '9454674', 'AK', 'MacLeod Harbor'), ('Naha Bay', '9450624', 'AK', 'Loring (Naha Bay)'),
    ('Otter Point', '9462465', 'AK', 'Otter Point (Umnak Island)'), ('Port Chalmers', '9454511', 'AK', 'Port Chalmers'),
    ('Port Chatham', '9455428', 'AK', 'Port Chatham'), ('Port Protection', '9451095', 'AK', 'Port Protection (Prince of Wales Island)'),
    ('Ratz Harbour', '9450815', 'AK', 'Ratz Harbor (Prince of Wales Island)'), ('Steamboat Bay', '9450578', 'AK', 'Steamboat Bay (Noyes Island)'),
    ('Two Arm Bay', '9455217', 'AK', 'Two Arm Bay (Harris Bay)'), ('Unalga Island', 'TWC2175', 'AK', 'Malga Bay (Unalga Island)'),
    ('Olga Bay', '9457798', 'AK', 'Olga Bay (A. P. A. Cannery)'), ('Gnat Cove', '9450483', 'AK', 'Mop Point (Thorne Arm)'),
]
CHS = [('Mink Trap Bay', '09180', 'Patterson Inlet (Mink Trap Bay)', 'British Columbia', 'America/Vancouver')]
# Truro (Minas Basin, CHS 00265) geprueft 21.11.: CHS liefert dort nur Bore-Ankunftszeiten (wlp-bores), keine HW/NW-Hoehen


def noaa_station(sid=None, name=None):
    d = json.load(open(os.path.join(ROOT, 'quellen/tide_tables/NOAA_hilo/mdapi_tidepredictions.json')))['stations']
    if sid:
        return next(s for s in d if s['id'] == sid)
    return next(s for s in d if s['name'].startswith(name))


def chs_hilo(code):
    """IWLS wlp-hilo 2025+2026 (monatsweise), Cache."""
    os.makedirs(CHS_CACHE, exist_ok=True)
    st = json.load(open(os.path.join(ROOT, 'quellen/tide_tables/CHS_hilo/stations.json')))
    s = next(x for x in st if x['code'] == code)
    pfad = os.path.join(CHS_CACHE, '%s_2025_2026.json' % code)
    if not os.path.exists(pfad):
        ev = []
        for j in (2025, 2026):
            for m in range(1, 13):
                a = dt.date(j, m, 1)
                b = dt.date(j + (m == 12), m % 12 + 1, 1)
                u = ('https://api-iwls.dfo-mpo.gc.ca/api/v1/stations/%s/data?time-series-code=wlp-hilo&from=%sT00:00:00Z'
                     '&to=%sT00:00:00Z' % (s['id'], a.isoformat(), b.isoformat()))
                d = json.load(urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': 'weather-tides/1.0'}), timeout=60))
                ev += [(x['eventDate'], x['value']) for x in d]
                time.sleep(0.5)
        json.dump(ev, open(pfad, 'w'))
    ev = sorted(set(tuple(x) for x in json.load(open(pfad))))
    t = np.array([dt.datetime.strptime(a[:19], '%Y-%m-%dT%H:%M:%S').replace(tzinfo=dt.timezone.utc).timestamp() for a, _ in ev])
    return s, t, np.array([b for _, b in ev])


# Namen, denen der NOAA-Text den Ortsbezug nicht mitgibt oder die Fuellwoerter tragen (21.11.2026, Gewaesser per OSM)
NAME_FIX = {'8537535': 'Mad Horse Creek (1 n.mi. above entrance)', '8666659': 'Combahee River (U.S. 17 bridge)',
            '8669072': 'New River (SC 170 bridge)', '8722472': 'Boy Scout Dock (Loxahatchee River)',
            '8534043': 'Wading River', '8660275': 'Conway (railroad bridge)', '8665257': 'Canaday Landing (Edisto River)',
            '8666017': 'Penny Creek (Edisto River)', '9450244': 'Menefee Anchorage (Prince of Wales Island)',
            '9450817': 'Tuxekan (0.5 mi S)', '8723667': 'Key Largo (South Sound)'}


def noaa_name(n):
    """'Steinhatchee River ent., Deadman Bay' -> 'Steinhatchee River entrance (Deadman Bay)'; Staatskuerzel am Ende weg."""
    import re
    n = re.sub(r',\s*(Md|Va|Del|N\.\s?J|N\.\s?C|S\.\s?C|Conn|Mass|Fla|La|Ala|Wash|Calif|Ore|Me)\.?$', '', n.strip())
    n = re.sub(r'\bent\.', 'entrance', n)
    teile = [t.strip() for t in n.split(',') if t.strip()]
    return glaetten(teile[0] + (' (%s)' % ', '.join(teile[1:]) if len(teile) > 1 else ''))


def glaetten(n):
    """NOAA-Abkuerzungen und Fuellwoerter (21.11.2026, Nebenorte 5-15 km)."""
    import re
    n = re.sub(r'\s*\((Oreg|Wash|Calif|Fla|Md|Va|Del|Mass|Conn|Ala|La|Me|N\.\s?J|N\.\s?C|S\.\s?C)\.\)', '', n)
    n = re.sub(r'\s*\((south|north|east|west) of\)', '', n)
    n = re.sub(r'\s*\(town\)', '', n)
    n = re.sub(r'(\d+(?:\.\d+)?)\s*miles? (north|south|east|west) of', lambda m: '%s mi %s of' % (m.group(1), m.group(2)[0].upper()), n)
    n = re.sub(r'\((\d+(?:\.\d+)?) mi ([NSEW]) of\)', r'(\1 mi \2)', n)
    n = re.sub(r'(\d)mi ([NSEW])\. of', r'\1 mi \2 of', n)
    for a_, b_ in (('Riv.', 'River'), ('Hwy.', 'Highway'), ('Fla. Bay', 'Florida Bay'), (' I. Bay', ' Island Bay'), ('Rt. ', 'Route ')):
        n = n.replace(a_, b_)
    return re.sub(r'\s+', ' ', n).strip()


def auto_kandidaten(band=None):
    """--alle (Oliver 21.11.): NOAA-Nebenorte > 15 km und CHS-HW/NW-Stationen > 10 km vom naechsten Gezeitensatz.
    band=(min_km, max_km): nur NOAA-Nebenorte in diesem Abstand (Oliver 21.11.: die 5-15-km-Orte, eigene Kartengruppe)."""
    import math
    import health_check as H
    from scipy.spatial import cKDTree
    R = [r for r in H.load_records() if r['lat'] is not None and not r['current']]

    def xyz(la, lo):
        return (math.cos(math.radians(la)) * math.cos(math.radians(lo)),
                math.cos(math.radians(la)) * math.sin(math.radians(lo)), math.sin(math.radians(la)))
    T = cKDTree([xyz(r['lat'], r['lon']) for r in R])

    def abst(la, lo):
        return T.query(xyz(la, lo))[0] * 6371
    gew, noaa, chs = [], [], []
    for st in json.load(open(os.path.join(ROOT, 'quellen/tide_tables/NOAA_hilo/mdapi_tidepredictions.json')))['stations']:
        staat = st.get('state') or OHNE_STAAT.get(st['id'])
        d_ = abst(st['lat'], st['lng'])
        if st['type'] != 'S' or staat not in STAATEN or (d_ <= 15 if band is None else not band[0] < d_ <= band[1]):
            continue
        if any(math.hypot(st['lat'] - a, (st['lng'] - b) * math.cos(math.radians(a))) * 111.2 < (0.5 if band else 3) for a, b in gew):
            continue
        gew.append((st['lat'], st['lng']))
        noaa.append(('auto', st['id'], staat, NAME_FIX.get(st['id'], noaa_name(st['name']))))
    for st in ([] if band else json.load(open(os.path.join(ROOT, 'quellen/tide_tables/CHS_hilo/stations.json')))):
        if not any(t['code'] == 'wlp-hilo' for t in st.get('timeSeries', [])) or abst(st['latitude'], st['longitude']) <= 10:
            continue
        pc = st.get('provinceCode') or ('BC' if st['longitude'] < -120 else 'NU')
        chs.append(('auto', st['code'], st['officialName'], PROVINZ.get(pc, pc), TZ_PROV.get(pc, 'America/Toronto')))
    return noaa, chs


def main(argv):
    global ZIEL
    if '--ziel' in argv:                                           # eigene Datei (21.11.: NOAA-Nebenorte 5-15 km)
        ZIEL = os.path.join(ROOT, argv[argv.index('--ziel') + 1])
        if not os.path.exists(ZIEL):
            q = open(os.path.join(ROOT, 'harmonics/utide/harmonics_utide_tidetables.txt'), encoding='iso-8859-1').read().split('\n')
            # ganzer Kopf bis zum ersten Satz: build_tide_db braucht auch den Kommentarblock nach "End congen output"
            kopf_ = q[:q.index('# BEGIN HOT COMMENTS')]
            open(ZIEL, 'w', encoding='iso-8859-1').write('\n'.join(kopf_) + '\n')
    band = (float(argv[argv.index('--band') + 1]), float(argv[argv.index('--band') + 2])) if '--band' in argv else None
    kopf = X.kopf_lesen(ZIEL)
    namen, speeds, arg, fak = kopf
    nutz = SF.konstituenten(namen, SF.CONSTIT_67)
    heute = dt.date.today().strftime('%Y%m%d')
    grenze = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc).timestamp()
    import health_check as H
    bestand = set(open(ZIEL, encoding='iso-8859-1').read().split('\n')) | {r['name'] for r in H.load_records()}
    neu, liste = [], []
    faelle = []
    liste_noaa, liste_chs = (auto_kandidaten(band) if ('--alle' in argv or band) else (NOAA, CHS))
    print('%d NOAA-, %d CHS-Kandidaten' % (len(liste_noaa), len(liste_chs)), flush=True)
    for idx, sid, st, unser in liste_noaa:
        s = noaa_station(sid)
        NH.laden(s['id'])
        t, h = NH.scheitel(s['id'])
        faelle.append((idx, 'NOAA %s (%s)' % (s['id'], 'Nebenort' if s['type'] == 'S' else 'Bezugsort'), '%s, %s' % (unser, STAATEN[st][0]),
                       'United States', STAATEN[st][0], STAATEN[st][1], s['lat'], s['lng'], t, h, 'MLLW',
                       'NOAA CO-OPS tide predictions (station %s), high/low waters 2025-2026' % s['id']))
    for idx, code, unser, prov, tz in liste_chs:
        s, t, h = chs_hilo(code)
        faelle.append((idx, 'CHS %s' % code, '%s, %s, Canada' % (unser, prov), 'Canada', prov, tz, s['latitude'], s['longitude'],
                       t, h, 'Chart Datum', 'CHS tide predictions (IWLS station %s), high/low waters 2025-2026' % code))
    for idx, quelle, name, land, prov, tz, la, lo, t, h, datum, src in faelle:
        if name in bestand and idx == 'auto' and band:             # gleichnamiger NOAA-Nebenort im selben Staat
            k = 2
            while name.replace(', ', ' (%d), ' % k, 1) in bestand:
                k += 1
            name = name.replace(', ', ' (%d), ' % k, 1)
        if name in bestand:
            print('%-45s schon im Bestand' % name)
            continue
        if len(t) < 600:
            print('%-45s nur %d Scheitel -> uebersprungen' % (name, len(t)))
            continue
        lern, test = t < grenze, t >= grenze
        if lern.sum() < 100 or test.sum() < 100:                   # CHS liefert nur das laufende Jahr: Halbjahresprobe
            lern, test = t < np.median(t), t >= np.median(t)
        z1, w1 = SF.fit(t[lern], h[lern], nutz, speeds, arg, fak)
        r_pr, t_pr, _ = SF.guete(t[test], h[test], z1, w1, kopf, versatz=False)
        z0, w = SF.fit(t, h, nutz, speeds, arg, fak)
        r, tf, _ = SF.guete(t, h, z0, w, kopf, versatz=False)
        lo_, hi_ = SF.bandbreite(t, h, z0, w, kopf)
        ok = lo_ >= h.min() - 0.15 and hi_ <= h.max() + 0.15 and r_pr < 0.05
        print('%-45s %-20s %4d Sch. Fit %.1f cm %2.0f min  Probe26 %.1f cm  M2 %.3f K1 %.3f  %s' % (
            name[:45], quelle, len(t), 100 * r, tf, 100 * r_pr, w['M2'][0], w['K1'][0], 'ok' if ok else 'ABGELEHNT (Bandbreite/Probe)'))
        if not ok:
            continue
        blk = ['#', '# ' + name, '# BEGIN HOT COMMENTS', '# country: %s' % land, '# source: %s' % src[:88],
               '# date_imported: %s' % heute, '# datum: %s' % datum, '# confidence: 7', '# !units: meters',
               '# !longitude: %.4f' % lo, '# !latitude: %.4f' % la, '# province: %s' % prov,
               '# note: %s Scheitelfit an %s HW/NW %s (%.1f cm / %.0f min, Probe %.1f cm); %s' % (
                   heute, quelle, '2025-2026' if t.min() < grenze - 86400 else '2026', 100 * r, tf, 100 * r_pr,
                   ('fuellt UKHO-Index-Luecke "%s"' % idx) if idx != 'auto' else
                   ('NOAA-Nebenort, naechster Satz %g-%g km' % band if band else 'fuellt Luecke (naechster Satz > 15 km, CHS > 10 km)')),
               '# note: py/luecken_amtlich.py', name, '+00:00 :%s' % tz, '%.4f meters' % z0]
        blk += ['%-15s %.4f  %.2f' % (c, *w[c]) if c in w and w[c][0] >= 0.00005 else 'x 0 0' for c in namen]
        assert '\n'.join(blk).encode('latin-1')
        neu += blk
        liste.append(name)
        bestand.add(name)
    print('%d neue Saetze' % len(liste))
    if '--schreiben' in argv and neu:
        from sicher_schreiben import schreiben
        T = open(ZIEL, encoding='iso-8859-1').read().rstrip('\n').split('\n')
        schreiben(ZIEL, '\n'.join(T + neu) + '\n')
        if '--ohne-pruefliste' in argv:
            print('->', os.path.relpath(ZIEL, ROOT), '(ohne Pruefliste)')
            return
        frisch = not os.path.exists(PRUEF)
        with open(PRUEF, 'a', newline='', encoding='utf-8') as fh:
            w_ = csv.writer(fh)
            if frisch:
                w_.writerow(['datei', 'name'])
            for n in liste:
                w_.writerow([os.path.basename(ZIEL), n])
        print('->', os.path.relpath(ZIEL, ROOT), '+', os.path.relpath(PRUEF, ROOT))


if __name__ == '__main__':
    main(sys.argv[1:])
