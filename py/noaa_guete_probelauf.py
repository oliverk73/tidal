#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Probelauf: ungenaue NOAA-Saetze ausserhalb der USA finden -- statt Dubletten einzeln.

Olivers Umstellung (15.09.2026): Nicht mehr jede Dublette von Hand
vergleichen, sondern generell ungenaue Saetze finden und loeschen; die
schlechteren Dubletten fallen dabei mit weg. Dazu nachweislich falsche
Positionen und veraltete oder falsche Namen berichtigen.

Wahrheit sind nur Klasse-A-Saetze (noaa_pruefstand.klasse: Messungen und
kontinuierliche amtliche Vorhersagen). Wie weit zwei gute Saetze
voneinander abweichen duerfen, misst das Skript selbst an allen
A-A-Paaren, getrennt nach Abstand (Grundrauschen, p90/p95).

Guete-Listen (Spalte liste):
  loeschen:schlecht      mind. zwei Klasse-A-Orte bis 25 km sind sich einig,
                         der NOAA-Satz weicht von allen deutlich ab
  loeschen:neben_A       Klasse-A-Satz bis 3 km, NOAA stimmt im Rahmen des
                         Grundrauschens -- eine Dublette des besseren Satzes
  pruefen:widerspruch    Klasse-A-Satz bis 3 km, NOAA weicht deutlich ab,
                         aber kein zweiter A-Ort bestaetigt den A-Satz; die
                         uebrigen Nachbarn (jede Klasse, fremde Abstammung)
                         entscheiden als Schiedsrichter
  loeschen:widerspruch   ... ohne Schiedsspruch: der A-Satz (gemessene Konstanten)
                         schlaegt die HW/NW-Uebertragung
  pruefen:stunde         ... ohne Schiedsspruch, aber glatter Stundenversatz bei
                         gleicher Amplitude: Zonenfehler, unklar bei wem
  pruefen:ein_zeuge      nur ein A-Ort (3-10 km), NOAA weicht sehr deutlich ab
  bleibt:A_verdaechtig   Widerspruch, aber die uebrigen Nachbarn geben NOAA recht
  bleibt:bestaetigt      A-Nachbarn bestaetigen den Satz
  bleibt:ungeklaert      A-Nachbarn da, aber kein klares Urteil
  bleibt:ohne_zeugen     kein Klasse-A-Satz bis 25 km

Zusatzspalten (unabhaengig von der Guete):
  land        Land im Namen passt nicht zur Position (land_gegen_position)
  buchpos     Buchposition springt gegen die Nachbarzeilen (Lesefehler?)
  an_land     Position laut Landmaske an Land, Abstand zum Wasser
  namenspos   GeoNames kennt den Namen, aber weit weg -> dortige Position
  name        GeoNames kennt den Namen nicht bis 50 km, oder nur als
              Alternativname -> Vorschlag aus GeoNames (Hauptname)

Nichts wird geschrieben ausser harmonics/help/noaa_guete_probelauf.csv.

Usage: python3 py/noaa_guete_probelauf.py
"""
from __future__ import annotations

import collections
import csv
import math
import os
import re
import statistics
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import noaa_pruefstand as P                                          # noqa: E402
import region_felder_fuellen as RF                                   # noqa: E402
from health_check import ROOT, curve_diff, km, load_records          # noqa: E402
from nachbarprobe import massstab, sippe, versatz_min                # noqa: E402

HELP = os.path.join(ROOT, 'harmonics/help')
AUS = os.path.join(HELP, 'noaa_guete_probelauf.csv')
GEONAMES = os.path.join(ROOT, 'tide_tables/catalogues/geonames/umfeld.tsv')
LANDLISTE = os.path.join(HELP, 'land_gegen_position2.csv.neu')
LANDENTSCHEIDUNG = os.path.join(HELP, 'land_gegen_position_Edit.csv')

UMKREIS = 25.0
NAH = 3.0
ORT_KM = 0.5
P_FLUSS = re.compile(r'\b(river|reka|rio|rivi[eè]re|creek|estuary|gulf|guba|jiang|he|kou|sungai|kuala|muara|song|yenisey|ob|lena|amur)\b', re.I)
BINS = [(0.0, 1.0), (1.0, 3.0), (3.0, 6.0), (6.0, 12.0), (12.0, 25.0)]

GENERISCH = {
    'island', 'islands', 'isla', 'islas', 'ile', 'iles', 'ilha', 'ilhas', 'isola', 'insel', 'pulau',
    'bay', 'baia', 'bahia', 'baie', 'harbor', 'harbour', 'port', 'porto', 'puerto', 'point', 'pointe',
    'punta', 'ponta', 'cape', 'cabo', 'cap', 'river', 'rio', 'riviere', 'entrance', 'anchorage',
    'roads', 'road', 'pier', 'wharf', 'mouth', 'head', 'light', 'lighthouse', 'reef', 'cay', 'cays',
    'bank', 'channel', 'strait', 'sound', 'inlet', 'creek', 'lagoon', 'gulf', 'the', 'of', 'de',
    'da', 'do', 'del', 'la', 'le', 'el', 'north', 'south', 'east', 'west', 'n', 's', 'e', 'w',
    'upper', 'lower', 'outer', 'inner', 'new', 'old', 'saint', 'st', 'san', 'santa', 'sao',
    'village', 'town', 'jetty', 'dock', 'docks', 'basin', 'landing', 'station', 'marina',
    'kang', 'dao', 'wan', 'jiao', 'shima', 'jima', 'ko', 'misaki', 'zaki', 'saki', 'hang', 'man',
    'teluk', 'tanjung', 'tg', 'selat', 'muara', 'kuala', 'sungai', 'hon', 'cua', 'mui', 'vinh',
    'guba', 'bukhta', 'zaliv', 'mys', 'ostrov', 'proliv', 'reka', 'port', 'fjord', 'fiord',
    # 21.09.2026 aus der Gattungswort-Analyse der name:unbekannt-Faelle: nur Orts- und
    # Anlagenbezeichnungen, keine Eigennamen (Weser, Plata, Hope ... bleiben draussen)
    'bridge', 'beach', 'barra', 'bar', 'jazirat', 'beacon', 'ferry', 'terminal', 'bandar', 'breakwater',
    'sperrwerk', 'cove', 'islet', 'islets', 'ilet', 'offshore', 'approaches', 'off', 'area', 'barge',
    'fishing', 'arsenal', 'refinery', 'uscg', 'institute', 'office', 'airport', 'kyst', 'brug', 'kap',
    'pass', 'passage', 'bayou', 'causeway', 'pont', 'viaduc', 'anse', 'bouee', 'buoy', 'lough', 'loch',
    'quay', 'slip', 'banc', 'banco', 'ostrova', 'archipel', 'roca', 'fondeadero', 'mouillage', 'hakuchi',
    'faro', 'leuchtturm', 'semaphore', 'heads', 'ness', 'bight', 'sandspit', 'shoal', 'flats', 'marsh',
    'gully', 'cliffs', 'sill', 'seaway', 'canal', 'lagon', 'laguna', 'foz', 'estuary', 'slough', 'lock',
    'locks', 'sluis', 'sluice', 'hafen', 'haven', 'hamn', 'minato', 'gyoko', 'hama', 'gawa', 'gang',
    'shuidao', 'myeon', 'pantai', 'batang', 'tanjong', 'pelabuhan', 'pasar', 'mina', 'sebkhat',
    'presqu', 'entree', 'pilotos', 'yacht', 'boat', 'base', 'historical', 'outside', 'buiten', 'binnen',
    'noord', 'vieux', 'upon', 'al', 'te', 'ne', 'nw', 'se', 'southeast', 'southwest', 'southern',
    'kepulauan', 'gosong',
}


# ------------------------------------------------------------------ Hilfen
def flach(s):
    s = unicodedata.normalize('NFKD', s)
    s = ''.join(c for c in s if not unicodedata.combining(c))
    return re.sub(r'[^a-z0-9]+', ' ', s.lower()).strip()


def kern(s):
    return ' '.join(w for w in flach(s).split() if w not in GENERISCH)


QUELLE_DATEI = [
    ('harmonics_ticon4_worldwide', 'TICON-4 (Messreihen)'),
    ('harmonics_puertos_spain', 'Puertos del Estado'),
    ('harmonics_fes2022', 'FES2022b (Modell)'),
    ('harmonics_ih_tabelas', 'IH Tabela de Mares'),
    ('harmonics_bsh_germany', 'BSH'),
    ('harmonics_literature', 'Literatur'),
    ('harmonics-1997-05-25', 'XTide-Bestand 1997'),
    ('harmonics-2004-06-14', 'XTide-Bestand 2004'),
    ('harmonics-dwf-20251228', 'NOAA CO-OPS (US)'),
    ('harmonics-dwf-', 'XTide-Bestand (dwf)'),
    ('harmonics-pierre-lavergne', 'Lavergne-Bestand'),
]
QUELLE_ORG = re.compile(r'Derived from (.+?)(?: observed| measured| astronomical| hourly| tide| HW/LW|'
                        r' predictions| data|,| with)|^([A-Za-z0-9/.\- ]{2,40}?)(?: data| tide| sea level|'
                        r' gauge| Sea Level|;| tide tables| hourly| predictions| monthly)')


def quelle_kurz(r):
    """Woher der Vergleichssatz stammt, in drei bis vier Worten."""
    f = os.path.basename(r['file'])
    src = ' '.join(re.findall(r'# source: (.*)', P.vermerk(r)))
    if '/noaa/' in r['file']:
        return 'NOAA CO-OPS' if 'CO-OPS' in src else 'NOAA Table 2 (Uebertragung)'
    if f.startswith('harmonics_att_'):
        band = (re.search(r'np(\d+)', f) or [None, '?'])[1]
        # "Part III Harmonic Constants" enthaelt "Part II" als Teilzeichenkette --
        # damit galten die NP207-Konstanten als Uebertragung.
        if 'secondary' in f or re.search(r'Part II\b', src):
            return f'ATT NP{band} Part II (Uebertragung)'
        return f'ATT NP{band} Konstanten'
    for kopf, text in QUELLE_DATEI:
        if f.startswith(kopf):
            return text + (' / JODC' if 'JODC' in src else '')
    m = QUELLE_ORG.search(src)
    org = (m.group(1) or m.group(2)).strip() if m else src.split(',')[0][:28]
    if 'utide_observations' in f:
        return f'Messreihe {org}' if org else 'Messreihe'
    if 'utide_tidetables' in f:
        return f'Tafel/Vorhersage {org}' if org else 'Amtliche Tafel'
    return org or f


def us_satz(r):
    land = (re.search(r'# country: (.*)', P.vermerk(r)) or [None, ''])[1].strip()
    return RF._flach(land) in RF.US_STAATEN or RF._flach(land) in ('united states', 'united states of america')


def ortsname(name):
    """Namensteile ohne Land/Provinz: 'Cone Island, Vietnam' -> ['Cone Island']."""
    teil = name.split(',')[0]
    teile = [teil]
    for m in re.findall(r'[(\[]([^)\]]+)[)\]]', teil):
        teile.append(m)
    teile[0] = re.sub(r'\s*[(\[][^)\]]*[)\]]', '', teile[0])
    return [t.strip() for t in teile if t.strip()]


def schwellen(recs_a):
    """{bin: (p50, p90, p95)} der Kurvenunterschiede aller A-A-Paare verschiedener Orte."""
    nb = P_nachbarn(recs_a, recs_a, UMKREIS)
    werte = collections.defaultdict(list)
    for r in recs_a:
        for x, d in nb[id(r)]:
            if id(x) <= id(r) or d < 0.3 or x['fp'] == r['fp']:
                continue
            werte[bin_von(d)].append(curve_diff(r, x)[1] * 100)
    out = {}
    for b, w in werte.items():
        w.sort()
        out[b] = (w[len(w) // 2], w[int(len(w) * 0.90)], w[int(len(w) * 0.95)], len(w))
    return out


def bin_von(d):
    for i, (a, b) in enumerate(BINS):
        if d < b:
            return i
    return len(BINS) - 1


def P_nachbarn(recs, kandidaten, umkreis):
    """{id(r): [(x, km), ...]} ueber ein Gitter."""
    gitter = collections.defaultdict(list)
    gr = umkreis / 111.2
    for x in kandidaten:
        gitter[(int(x['lat'] // gr), int(x['lon'] // gr))].append(x)
    out = {}
    for r in recs:
        a, b = int(r['lat'] // gr), int(r['lon'] // gr)
        spalten = max(1, int(math.ceil(1 / max(0.02, math.cos(math.radians(r['lat']))))))
        liste = []
        for da in (-1, 0, 1):
            for db in range(-spalten, spalten + 1):
                bb = b + db
                for x in gitter.get((a + da, bb), ()):
                    if x is r:
                        continue
                    d = km(r, x)
                    if d <= umkreis:
                        liste.append((x, d))
        out[id(r)] = liste
    return out


def orte(paare):
    gruppen = []
    for x, d in sorted(paare, key=lambda p: p[1]):
        for g in gruppen:
            if km(g[0][0], x) <= ORT_KM:
                g.append((x, d))
                break
        else:
            gruppen.append([(x, d)])
    return gruppen


# ------------------------------------------------------------------ Guete
def guete(r, a_nb, sw):
    """-> (liste, befund dict)."""
    if not a_nb:
        return 'bleibt:ohne_zeugen', {}
    gruppen = orte(a_nb)
    je_ort = []
    for g in gruppen:
        best = min(g, key=lambda p: curve_diff(r, p[0])[1])
        dd = curve_diff(r, best[0])[1] * 100
        p50, p90, p95, _ = sw[bin_von(best[1])]
        je_ort.append(dict(x=best[0], km=best[1], pct=dd, p90=p90, p95=p95, z=dd / p90))
    nah = [o for o in je_ort if o['km'] <= NAH]
    # Sind die A-Orte untereinander einig?
    einig = []
    for i, o in enumerate(je_ort):
        for q in je_ort[i + 1:]:
            d = km(o['x'], q['x'])
            einig.append(curve_diff(o['x'], q['x'])[1] * 100 <= sw[bin_von(d)][1] * 1.2)
    a_einig = len(je_ort) >= 2 and sum(einig) >= len(einig) * 0.67
    zeiten = [t for t in (versatz_min(o['x'], r) for o in je_ort) if t is not None]
    faktoren = [m for m in (massstab(o['x'], r) for o in je_ort) if m]
    bef = dict(
        abw_pct=round(statistics.median(o['pct'] for o in je_ort), 1),
        schwelle_pct=round(statistics.median(o['p95'] for o in je_ort), 1),
        a_orte=len(je_ort), a_einig='ja' if a_einig else ('' if len(je_ort) < 2 else 'nein'),
        naechster_a_km=round(min(o['km'] for o in je_ort), 2),
        naechster_a=min(je_ort, key=lambda o: o['km'])['x']['name'],
        naechster_a_datei=os.path.basename(min(je_ort, key=lambda o: o['km'])['x']['file']),
        naechster_a_quelle=quelle_kurz(min(je_ort, key=lambda o: o['km'])['x']),
        zeit_min='' if not zeiten else f'{statistics.median(zeiten):+.0f}',
        massstab='' if not faktoren else f'{statistics.median(faktoren):.2f}',
        a_zeugen='; '.join(f"{o['x']['name'][:30]} {o['km']:.1f}km {o['pct']:.0f}%"
                           for o in sorted(je_ort, key=lambda o: o['km'])[:4]))
    # Die Spalten abw_pct und schwelle_pct sind Mediane ueber alle A-Orte --
    # als Paar gelesen fuehren sie in die Irre: Bei Acapulco standen 23.7 %
    # gegen 34.7 %, und das sah nach "alles gut" aus. Die 34.7 % waren aber
    # der Median aus einem nahen (21.7) und einem fernen Ort (47.7), waehrend
    # die 23.7 % am NAHEN Ort gemessen sind, wo nur 15.5 % normal waeren.
    # Entschieden wird ohnehin je Ort; deshalb steht hier zusaetzlich der fuer
    # den Satz GUENSTIGSTE Vergleich mit seiner eigenen Schwelle.
    guenstig = min(je_ort, key=lambda o: o['z'])
    bef.update(
        e_ort=guenstig['x']['name'], e_datei=os.path.basename(guenstig['x']['file']),
        e_quelle=quelle_kurz(guenstig['x']),
        e_km=round(guenstig['km'], 2), e_pct=round(guenstig['pct'], 1),
        e_p90=round(guenstig['p90'], 1), e_p95=round(guenstig['p95'], 1),
        a_tabelle=';'.join('|'.join((o['x']['name'].replace('|', '/').replace(';', ','),
                                     f"{o['km']:.2f}", f"{o['pct']:.1f}",
                                     f"{o['p90']:.1f}", f"{o['p95']:.1f}",
                                     quelle_kurz(o['x']),
                                     f"{o['x']['lat']:.4f}", f"{o['x']['lon']:.4f}"))
                           for o in sorted(je_ort, key=lambda o: o['km'])[:8]))
    if nah:
        o = min(nah, key=lambda o: o['pct'])
        andere = [q for q in je_ort if q is not o]
        bestaetigt = [q for q in andere
                      if curve_diff(o['x'], q['x'])[1] * 100 <= sw[bin_von(km(o['x'], q['x']))][1]]
        # Im Rahmen des Grundrauschens (p90) ist NOAA eine Dublette des A-Satzes.
        # Bis p95 nur, wenn ein zweiter A-Ort den nahen A-Satz bestaetigt --
        # sonst koennte auch der A-Satz der falsche sein.
        if o['pct'] <= max(o['p90'], 10.0) or (o['pct'] <= o['p95'] and bestaetigt):
            return 'loeschen:neben_A', bef
        if bestaetigt and all(q['z'] > 1.0 for q in je_ort):
            return 'loeschen:schlecht', bef
        bef['_a'] = o['x']
        return 'pruefen:widerspruch', bef
    zmed = statistics.median(o['z'] for o in je_ort)
    if len(je_ort) >= 2 and a_einig and all(o['z'] > 1.0 for o in je_ort) \
            and bef['abw_pct'] >= 20.0 and zmed >= 1.5:
        return 'loeschen:schlecht', bef
    if len(je_ort) == 1 and je_ort[0]['km'] <= 10 and je_ort[0]['pct'] >= max(25.0, 2 * je_ort[0]['p95']):
        return 'pruefen:ein_zeuge', bef
    if zmed <= 1.0:
        return 'bleibt:bestaetigt', bef
    return 'bleibt:ungeklaert', bef


# ------------------------------------------------------------------ Position / Name
def buchsprung(zeilen):
    """{(band, no): text} fuer Buchzeilen, die gegen beide Nachbarzeilen springen."""
    out = {}
    for band in P.BAENDER:
        nrs = sorted(no for (b, no) in zeilen if b == band)
        for i in range(1, len(nrs) - 1):
            z, v, n = (zeilen[(band, nrs[j])] for j in (i, i - 1, i + 1))
            if None in (z.get('lat'), v.get('lat'), n.get('lat')):
                continue
            dv, dn, vn = (km(z, v), km(z, n), km(v, n))
            if dv > 150 and dn > 150 and vn < min(dv, dn) / 3:
                out[(band, nrs[i])] = f'Buchzeile {dv:.0f}/{dn:.0f} km von den Nachbarzeilen ({vn:.0f} km untereinander)'
    return out


KARTE_KM = 24.0          # Kantenlaenge des Ausschnitts
KARTE_N = 56             # Rasterpunkte je Kante (~0.43 km)


def kartenbild(lat, lon):
    """Land/Wasser-Raster um die Position, als base64-Bitmaske (Norden oben).

    Kachelserver sind in Artifacts gesperrt (CSP), also wird die Kueste selbst
    gezeichnet -- aus derselben Landmaske, die auch die Positionsprobe nutzt.
    Ihre Aufloesung ist rund 1 km: fuer den Ueberblick genug, fuer Flusslaeufe
    und Hafenbecken nicht.
    """
    import base64
    import numpy as np
    from global_land_mask import globe
    halb = KARTE_KM / 2
    dla = halb / 111.2
    dlo = halb / 111.2 / max(0.05, math.cos(math.radians(lat)))
    las = np.linspace(lat + dla, lat - dla, KARTE_N)          # Norden oben
    los = np.linspace(lon - dlo, lon + dlo, KARTE_N)
    gitter_la, gitter_lo = np.meshgrid(las, los, indexing='ij')
    gitter_la = np.clip(gitter_la, -89.9, 89.9)
    gitter_lo = (gitter_lo + 180) % 360 - 180
    bits = globe.is_land(gitter_la, gitter_lo).astype(np.uint8)
    return dict(b=base64.b64encode(np.packbits(bits.ravel()).tobytes()).decode(),
                n=KARTE_N, km=KARTE_KM, lat=round(lat, 4), lon=round(lon, 4),
                dla=round(dla, 6), dlo=round(dlo, 6))


def landabstand(lat, lon):
    """0 im Wasser, sonst km bis zum naechsten Wasserpunkt (Landmaske, ~1 km Raster), max 10."""
    from global_land_mask import globe
    if not globe.is_land(lat, lon):
        return 0.0
    for r_km in (0.5, 1, 2, 3, 5, 7, 10):
        for k in range(24):
            w = 2 * math.pi * k / 24
            la = lat + r_km / 111.2 * math.cos(w)
            lo = lon + r_km / 111.2 / max(0.05, math.cos(math.radians(lat))) * math.sin(w)
            if -90 < la < 90 and not globe.is_land(la, ((lo + 180) % 360) - 180):
                return float(r_km)
    return 10.0


def schluessel(s):
    """Vergleichsform ohne Leerzeichen: "Ust'-Bol'sheretsk" -> "ustbolsheretsk"."""
    return flach(re.sub(r"[\u2019\u02bc\u02b9'`\"]", '', s)).replace(' ', '')


def kernschluessel(s):
    return kern(re.sub(r"[\u2019\u02bc\u02b9'`\"]", '', s)).replace(' ', '')


def geonames_laden(recs):
    """-> Gitter {(lat*10, lon*10): [(eintrag, hauptschluessel, alle schluessel)]}."""
    zellen = set()
    for r in recs:
        a, b = int(math.floor(r['lat'] * 10)), int(math.floor(r['lon'] * 10))
        spalten = max(2, int(math.ceil(2 / max(0.05, math.cos(math.radians(r['lat']))))))
        for da in range(-2, 3):
            for db in range(-spalten, spalten + 1):
                zellen.add((a + da, b + db))
    gitter = collections.defaultdict(list)
    with open(GEONAMES, encoding='utf-8') as fh:
        for line in fh:
            p = line.rstrip('\n').split('\t')
            lat, lon = float(p[4]), float(p[5])
            z = (int(math.floor(lat * 10)), int(math.floor(lon * 10)))
            if z not in zellen:
                continue
            e = (p[1], lat, lon, p[6], p[7], p[8])
            haupt = {schluessel(p[1]), schluessel(p[2]), kernschluessel(p[1]), kernschluessel(p[2])} - {''}
            alle = set(haupt)
            for alt in p[3].split(','):
                if alt and len(alt) < 60:
                    alle |= {schluessel(alt), kernschluessel(alt)}
            gitter[z].append((e, haupt, alle - {''}))
    return gitter


def umkreis_eintraege(r, gitter, km_max):
    a, b = int(math.floor(r['lat'] * 10)), int(math.floor(r['lon'] * 10))
    n_la = int(math.ceil(km_max / 11.1))
    n_lo = int(math.ceil(km_max / 11.1 / max(0.05, math.cos(math.radians(r['lat'])))))
    for da in range(-n_la, n_la + 1):
        for db in range(-n_lo, n_lo + 1):
            for t in gitter.get((a + da, b + db), ()):
                d = km(r, {'lat': t[0][1], 'lon': t[0][2]})
                if d <= km_max:
                    yield d, t


ORTSRANG = {'PPL': 0, 'PPLA': 0, 'PPLA2': 0, 'PPLA3': 0, 'PPLA4': 0, 'PPLC': 0, 'PORT': 0, 'HBR': 1,
            'PPLL': 1, 'PPLX': 1, 'BAY': 2, 'COVE': 2, 'ISL': 2, 'CAPE': 2, 'PT': 2, 'ANCH': 2, 'LGN': 2}


def latin1(s):
    s = re.sub(r"[\u2019\u02bc\u02b9`]", '', s)
    try:
        s.encode('iso-8859-1')
        return s
    except UnicodeEncodeError:
        z = unicodedata.normalize('NFKD', s)
        return ''.join(c for c in z if not unicodedata.combining(c)).encode('iso-8859-1', 'ignore').decode('iso-8859-1')


def namensprobe(r, gitter):
    """-> (befund, vorschlag_name, vorschlag_lat, vorschlag_lon, text)."""
    import difflib
    teile = ortsname(r['name'])
    ks = {schluessel(t) for t in teile} | {kernschluessel(t) for t in teile}
    ks = {k for k in ks if len(k) >= 3}
    if not ks:
        return '', '', '', '', ''
    nah = list(umkreis_eintraege(r, gitter, 15.0))
    if any(ks & haupt for _d, (_e, haupt, _a) in nah):
        return '', '', '', '', ''
    alt = sorted((d, e) for d, (e, _h, alle) in nah if ks & alle)
    if alt:
        d, e = alt[0]
        return ('name:alternativ', latin1(e[0]), '', '',
                f'GeoNames: nur Alternativname von "{e[0]}" ({e[4]}, {d:.1f} km)')
    unscharf = []
    for d, (e, haupt, _a) in nah:
        for h in haupt:
            for k in ks:
                if abs(len(h) - len(k)) <= 3 and h[:1] == k[:1]:
                    q = difflib.SequenceMatcher(None, h, k).ratio()
                    if q >= 0.8:
                        unscharf.append((-q, d, e))
    if unscharf:
        q, d, e = min(unscharf)
        return ('name:schreibweise', latin1(e[0]), '', '',
                f'GeoNames: "{e[0]}" ({e[4]}, {d:.1f} km, Aehnlichkeit {-q:.2f})')
    fern = sorted((d, e) for d, (e, haupt, alle) in umkreis_eintraege(r, gitter, 50.0)
                  if d > 15 and ks & alle and e[3] in ('P', 'H', 'T', 'L', 'S'))
    if fern:
        d, e = fern[0]
        return ('namenspos', latin1(e[0]), f'{e[1]:.4f}', f'{e[2]:.4f}',
                f'GeoNames: "{e[0]}" ({e[4]}) {d:.0f} km entfernt')
    orte = sorted(((d > 3.0, ORTSRANG.get(e[4], 5), d), d, e) for d, (e, _h, _a) in nah
                  if d <= 8 and e[3] in ('P', 'H', 'T', 'S', 'L'))
    if orte:
        _k, d, e = orte[0]
        return ('name:unbekannt', latin1(e[0]), '', '',
                f'Name bis 50 km unbekannt; naechster Ort "{e[0]}" ({e[4]}, {d:.1f} km)')
    return 'name:unbekannt', '', '', '', 'Name bis 50 km unbekannt; kein Ort bis 8 km'


def bearbeitet(r, zeilen, band, no):
    """Name weicht schon vom Buchnamen ab (frueher oder von Oliver umbenannt)?"""
    v = P.vermerk(r)
    if re.search(r'Name(?:/Position)? berichtigt|umbenannt|renamed', v):
        return True
    z = zeilen.get((band, no))
    if not z:
        return False
    buch = schluessel(re.sub(r'\s*[(\[].*', '', z['name'].split(',')[0]))
    return bool(buch) and buch not in schluessel(r['name'])


def schiedsrichter(r, a, alle_nb, sw):
    """Widerspruch NOAA gegen EINEN nahen A-Satz: wer weicht von den uebrigen Nachbarn ab?

    Zeugen sind alle Saetze bis 25 km (jeder Klasse) ausser den beiden Streitern,
    ihrer Abstammung (Uebertragungen vom selben Bezugsort bzw. vom A-Satz) und
    Fingerabdruck-Kopien. -> ('A'|'NOAA'|'', text)
    """
    a_kern = schluessel(a['name'].split(',')[0])
    zeugen = []
    for x, d in alle_nb:
        if x is a or x['fp'] in (r['fp'], a['fp']) or x['sippe'] == r['sippe']:
            continue
        if x['sippe'].startswith('bezug:') and a_kern and a_kern in schluessel(x['sippe'][6:]):
            continue
        zeugen.append((x, d))
    gruppen = orte(zeugen)
    if len(gruppen) < 2:
        return '', f'{len(gruppen)} Zeugenort(e)', dict(schieds_orte='', schieds_noaa='', schieds_a='',
                                                        schieds_tabelle='')
    dn, da, tab = [], [], []
    for g in gruppen:
        bn = min(curve_diff(r, x)[1] for x, _d in g) * 100
        ba = min(curve_diff(a, x)[1] for x, _d in g) * 100
        dn.append(bn)
        da.append(ba)
        bester = min(g, key=lambda p: curve_diff(a, p[0])[1])[0]
        tab.append((bester['name'].replace('|', '/').replace(';', ','), g[0][1], bn, ba,
                    quelle_kurz(bester), bester['lat'], bester['lon']))
    mn, ma = statistics.median(dn), statistics.median(da)
    namen = '; '.join(f'{g[0][0]["name"][:34]} ({g[0][1]:.1f} km)'
                      for g in sorted(gruppen, key=lambda g: g[0][1])[:3])
    text = f'{len(gruppen)} Zeugenorte: NOAA {mn:.0f} %, A {ma:.0f} %'
    einzel = dict(schieds_orte=namen, schieds_noaa=round(mn, 1), schieds_a=round(ma, 1),
                  schieds_tabelle=';'.join('|'.join((t[0], f'{t[1]:.2f}', f'{t[2]:.1f}',
                                                     f'{t[3]:.1f}', t[4], f'{t[5]:.4f}', f'{t[6]:.4f}'))
                                           for t in sorted(tab, key=lambda t: t[1])[:6]))
    if ma <= 0.67 * mn and ma < mn - 5:
        return 'A', text, einzel
    if mn <= 0.67 * ma and mn < ma - 5:
        return 'NOAA', text, einzel
    return '', text, einzel


# ------------------------------------------------------------------ main
def main(argv):
    recs = [r for r in load_records()
            if r['lat'] is not None and r['lon'] is not None and not r['current']]
    for r in recs:
        r['kl'] = P.klasse(r)
    recs_a = [r for r in recs if r['kl'] == 'A']
    ziel = [r for r in recs if '/noaa/' in r['file'] and 'current' not in r['file'] and not us_satz(r)]
    print(f'{len(ziel)} NOAA-Saetze ausserhalb der USA, {len(recs_a)} Klasse-A-Saetze')

    sw = schwellen(recs_a)
    for i, (a, b) in enumerate(BINS):
        p50, p90, p95, n = sw[i]
        print(f'  A-A {a:4.0f}-{b:4.0f} km: p50 {p50:5.1f} %  p90 {p90:5.1f} %  p95 {p95:5.1f} %  (n={n})')

    import json
    with open(os.path.join(HELP, 'noaa_guete_schwellen.json'), 'w', encoding='utf-8') as fh:
        json.dump([dict(von=BINS[i][0], bis=BINS[i][1], p50=round(sw[i][0], 1), p90=round(sw[i][1], 1),
                        p95=round(sw[i][2], 1), paare=sw[i][3]) for i in range(len(BINS))], fh)

    nb = P_nachbarn(ziel, recs_a, UMKREIS)
    komm = __import__('pegel_dubletten').vermerke()
    for r in recs:
        r['sippe'] = sippe(r, komm.get((r['file'], r['line']), ''))
    nb_alle = P_nachbarn(ziel, recs, UMKREIS)
    zeilen, _zon, _refz = P.buch()
    sprung = buchsprung(zeilen)

    land = {}
    ent = {}
    if os.path.exists(LANDENTSCHEIDUNG):
        for z in csv.DictReader(open(LANDENTSCHEIDUNG, encoding='utf-8')):
            ent[(os.path.basename(z['datei']), z['name'])] = (z.get('entscheidung') or '').strip()
    for z in csv.DictReader(open(LANDLISTE, encoding='utf-8')):
        land[(os.path.basename(z['datei']), z['name'])] = z


    print('GeoNames laden ...', flush=True)
    gitter = geonames_laden(ziel)
    out = []
    for r in ziel:
        liste, bef = guete(r, nb[id(r)], sw)
        a = bef.pop('_a', None)
        if a is not None:
            wer, text, einzel = schiedsrichter(r, a, nb_alle[id(r)], sw)
            bef['schiedsrichter'] = text
            bef.update(einzel)
            if wer == 'A':
                liste = 'loeschen:schlecht'
                bef['schiedsrichter'] += ' -> NOAA weicht ab'
            elif wer == 'NOAA':
                liste = 'bleibt:A_verdaechtig'
                bef['schiedsrichter'] += ' -> A-Satz weicht ab'
            elif bef['zeit_min'] and 45 <= abs(int(bef['zeit_min'])) <= 75 \
                    and bef['massstab'] and 0.8 <= float(bef['massstab']) <= 1.25:
                # Glatte Stunde bei gleicher Amplitude: Zonenfehler -- bei wem?
                liste = 'pruefen:stunde'
            else:
                liste = 'loeschen:widerspruch'
        if liste == 'loeschen:neben_A' and bef.get('naechster_a_km', 99) <= NAH:
            a_nah = min((x for x, d in nb[id(r)] if d <= NAH), key=lambda x: curve_diff(r, x)[1])
            if not namensprobe(r, gitter)[0] and namensprobe(a_nah, gitter)[0] in (
                    'name:alternativ', 'name:schreibweise', 'name:unbekannt'):
                bef['name_hinweis'] = f'NOAA-Name bei GeoNames, A-Name "{a_nah["name"]}" nicht'
        datei = os.path.basename(r['file'])
        band, no = P.band_und_nummer(r)
        z = dict(liste=liste, datei=datei, name=r['name'], lat=f"{r['lat']:.4f}", lon=f"{r['lon']:.4f}",
                 uid='' if band is None else f'{band}-{no}', **bef)
        lz = land.get((datei, r['name']))
        if lz:
            e = ent.get((datei, r['name']), '')
            z['land'] = f"liegt in {lz['liegt_in']} ({lz['km_dorthin']} km)" + (f'; entschieden: {e}' if e else '')
        if (band, no) in sprung:
            z['buchpos'] = sprung[(band, no)]
        if liste in ('loeschen:schlecht', 'loeschen:neben_A', 'loeschen:widerspruch',
                     'pruefen:stunde', 'bleibt:A_verdaechtig'):
            import json as _json
            z['karte'] = _json.dumps(kartenbild(r['lat'], r['lon']), separators=(',', ':'))
        out.append(z)
        if liste.startswith('loeschen'):
            continue
        la = landabstand(r['lat'], r['lon'])
        if la >= 3.0:
            z['an_land'] = f'{la:.0f} km bis Wasser' + (' (Fluss?)' if P_FLUSS.search(r['name']) else '')
        befund, vn, vla, vlo, text = namensprobe(r, gitter)
        if befund and bearbeitet(r, zeilen, band, no):
            z['name_text'] = 'schon umbenannt; ' + text
        elif befund:
            z['name_befund'] = befund
            z['vorschlag_name'] = vn
            z['vorschlag_lat'] = vla
            z['vorschlag_lon'] = vlo
            z['name_text'] = text

    felder = ['liste', 'datei', 'name', 'uid', 'lat', 'lon', 'abw_pct', 'schwelle_pct', 'a_orte', 'a_einig',
              'naechster_a_km', 'naechster_a', 'naechster_a_datei', 'naechster_a_quelle',
              'e_ort', 'e_datei', 'e_quelle', 'e_km', 'e_pct', 'e_p90', 'e_p95', 'a_tabelle', 'karte', 'zeit_min', 'massstab', 'a_zeugen', 'schiedsrichter', 'schieds_orte', 'schieds_noaa', 'schieds_a', 'schieds_tabelle', 'name_hinweis',
              'land', 'buchpos', 'an_land', 'name_befund', 'vorschlag_name', 'vorschlag_lat', 'vorschlag_lon',
              'name_text', 'entscheidung']
    rang = {'loeschen:schlecht': 0, 'loeschen:neben_A': 1, 'loeschen:widerspruch': 1.5, 'pruefen:stunde': 1.7,
            'pruefen:widerspruch': 2, 'pruefen:ein_zeuge': 3,
            'bleibt:A_verdaechtig': 3.5, 'bleibt:ungeklaert': 4, 'bleibt:bestaetigt': 5, 'bleibt:ohne_zeugen': 6}
    out.sort(key=lambda z: (rang[z['liste']], z['datei'], z['name']))
    with open(AUS, 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=felder)
        w.writeheader()
        w.writerows(out)
    print()
    for k, n in sorted(collections.Counter(z['liste'] for z in out).items(), key=lambda x: rang[x[0]]):
        print(f'  {k:22} {n:5d}')
    print(f"  land falsch            {sum(1 for z in out if z.get('land')):5d}")
    print(f"  Buchposition springt   {sum(1 for z in out if z.get('buchpos')):5d}")
    print(f"  an Land (>=3 km)       {sum(1 for z in out if z.get('an_land')):5d}")
    for b in ('namenspos', 'name:alternativ', 'name:schreibweise', 'name:unbekannt'):
        print(f"  {b:22} {sum(1 for z in out if z.get('name_befund') == b):5d}")
    print('->', os.path.relpath(AUS, ROOT))


if __name__ == '__main__':
    main(sys.argv[1:])
