#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Raeumt Haufen und Dubletten nach festen Regeln auf -- ohne Einzelfall-Listen.

Oliver 17.09.2026: Die CSV-Listen und Pruefseiten sind zu muehselig. Die
Listen sollen sich selbst aktualisieren und automatisch abgearbeitet
werden; weil jede Loeschung dokumentiert und archiviert ist, laesst sich
jeder Satz zurueckholen (py/satz_zurueckholen.py).

Freigegeben wird deshalb nicht mehr der Einzelfall, sondern die Regel
(Tabelle FREIGABE unten). Eine Regel ohne Freigabedatum wird nur im
Probelauf gezeigt.

Rangfolge der Quellen (kleiner = besser), am selben Ort bleibt der beste:
  0  Messung        eigene UTide-Fits auf Pegelreihen, NOAA CO-OPS, TICON,
                    Puertos del Estado
  1  amtlich        kontinuierliche amtliche Vorhersagen (NMDIS, SHOM, CHS ...),
                    JMA-Tafeln, Admiralty-Konstanten (ATT Part III), Lavergne
  2  Altbestand     XTide-Sammlungen 1997 und 2004
  3  Tafel-Fit      Fits auf Hoch-/Niedrigwassertafeln (Klasse B)
  4  Uebertragung   NOAA Table 2, ATT Part II
  5  Modell         FES2022

Regeln:
  R1  Dublette      schlechterer Rang neben besserem Satz, Kurve im Rahmen:
                      Rang 0-2 gegen Rang 0-2:  bis 1 km und bis 10 %
                      Rang 3-5 gegen besseren:  bis 1 km und bis 15 %,
                                                bis 3 km und bis 10 %
  R2  Doppelt       gleicher Rang, bis 0,5 km, Kurve bis 5 % (dieselbe
                    Quelle zweimal eingelesen); es bleibt der Satz aus der
                    bevorzugten Datei
  R3  Messreihe     NOAA-Uebertragung widerspricht einem Messsatz, und eine
                    unabhaengige Pegelreihe gibt dem Messsatz recht
                    (py/noaa_widerspruch_messreihen.py, Urteil "A besser")

Namen: Automatisch geloescht wird nur, wenn beide Saetze denselben Ortsnamen
tragen (health_check.namekey: erster Namensteil ohne Zusaetze). Heissen sie
verschieden -- "Bullenbaai" gegen "Bullen Bay", "Walem" gegen "Rumst" --, steht
der Fall als <Regel>:name im Probelauf und bleibt, bis die Namensfrage
geklaert ist; sonst ginge der bessere Name mit dem schlechteren Satz verloren.

Lage (Oliver 3.11.2026): Unterscheiden sich die Namen in Lagewoertern --
Ober-/Unterpegel, binnen/buiten, inside/outside, Schleuse, Sperrwerk, Dock,
Lagune ... (LAGE, mehrsprachig) --, stehen die Saetze vermutlich vor und
hinter einem Bauwerk oder einer Enge. Solche Paare werden nie automatisch
geloescht (<Regel>:lage), auch wenn die Kurven fast gleich sind.

Gleiche Quelle (Oliver 3.11.2026): Zwei Saetze derselben aktuellen Quelle mit
verschiedenem Namen sind eigene Pegel und keine Dubletten (Eugene Island
Atchafalaya Bay / north of, Walem / Rumst ...). Nur im Altbestand 1997/2004
kann eine Datei denselben Pegel zweimal fuehren; dort bleibt es eine Frage.

Nie automatisch geloescht wird:
  - ein Satz in harmonics/help/behalten.csv (dort landet jeder zurueckgeholte)
  - ein Satz mit Vermerk HANDENTSCHEIDUNG oder Handkorrektur
  - ein Satz, von dem andere Saetze uebertragen sind (Bezugsort), ausser der
    bleibende Satz traegt denselben Namen (dann laeuft der Bezug weiter)
  - Stromsaetze
Wo zwei Saetze sich widersprechen und keine Messreihe entscheidet, bleiben
beide stehen -- es wird nicht geraten.

Ablauf mit --ausfuehren:
  Vorschlag -> harmonics/help/loeschen_auto_<datum>.csv
  -> py/saetze_loeschen.py (Dateisicherung + Archiv je Satz)
  -> Protokoll harmonics/help/automatisch_geloescht.csv
  -> TCD bauen, Kartenmarker bauen

Usage: python3 py/bestand_aufraeumen.py                 Probelauf, schreibt aufraeumen_probelauf.csv
       python3 py/bestand_aufraeumen.py --ausfuehren    freigegebene Regeln anwenden
       python3 py/bestand_aufraeumen.py --antworten <datei.ods|csv> [--ausfuehren]
           Olivers Antworten (Spalte "antwort"; Zuordnung ueber name/datei/bleibt/bleibt_datei, nicht nr):
           Ja -> archivieren (nur bei Vorschlag "archivieren ..."), Nein / Beide bleiben -> behalten.csv,
           anderer Text -> wird angezeigt und von Hand erledigt. Ohne --ausfuehren nur Anzeige.
"""
from __future__ import annotations

import collections
import csv
import datetime as dt
import math
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import noaa_guete_probelauf as G                                    # noqa: E402
import noaa_pruefstand as P                                         # noqa: E402
from health_check import ROOT, curve_diff, km, load_records, namekey        # noqa: E402
from nachbarprobe import BEZUG                                      # noqa: E402

HELP = os.path.join(ROOT, 'harmonics/help')
PROBE = os.path.join(HELP, 'aufraeumen_probelauf.csv')
PROTOKOLL = os.path.join(HELP, 'automatisch_geloescht.csv')
BEHALTEN = os.path.join(HELP, 'behalten.csv')
MESSREIHEN = os.path.join(HELP, 'noaa_widerspruch_messreihen.csv')

# Regel -> Datum der Freigabe durch Oliver (leer = nur Probelauf)
FREIGABE = {'R1': '', 'R2': '', 'R3': ''}

# Nur echte Entscheidungen schuetzen. Das blosse Wort "Oliver" steht auch in meinen eigenen Notizen
# ("bitte pruefen (Oliver)", "..., Oliver." als Auftraggeber) -- das schuetzte am 3.11. Henslung Cove,
# Gold Coast, Bundaberg zu Unrecht. Olivers Entscheidungen landen in behalten.csv (--antworten).
HAND = re.compile(r'HANDENTSCHEIDUNG|Handkorrektur')
RANGNAME = ['Messung', 'amtlich', 'Altbestand', 'Tafel-Fit', 'Uebertragung', 'Modell']
# Innerhalb eines Rangs: frueher in der Liste = bevorzugt
DATEIFOLGE = ['harmonics_utide_observations', 'harmonics-dwf-20251228-free', 'harmonics_noaa_carib',
              'harmonics_noaa_censam', 'harmonics_noaa_pacif', 'harmonics_puertos_spain',
              'harmonics_ticon4', 'harmonics_utide_tidetables', 'harmonics_att_np2',
              'harmonics-pierre-lavergne', 'harmonics-dwf-2010', 'harmonics-dwf-2007',
              'harmonics-2004', 'harmonics-1997']


# Lagewoerter -> Gruppe. Gleiche Gruppe in beiden Namen zaehlt als gleich.
LAGE = [
    ('oben', r'\b(?:ober(?:wasser|pegel)?|OP|OW|upper|upstream|amont|opwaarts|bovenstrooms|aguas arriba|montante)\b'),
    ('unten', r'\b(?:unter(?:wasser|pegel)?|UP|UW|lower|downstream|aval|afwaarts|benedenstrooms|aguas abajo|jusante)\b'),
    ('innen', r'binnen|\binnen\w*|\b(?:inner|inside|interior|int[eé]rieur|interno|indre|inre|lagoon|lagune|laguna|lagoa|lagon|backwater)\b'),
    ('aussen', r'au(?:ss|ß)en|buiten|\b(?:outer|outside|exterior|ext[eé]rieur|esterno|ytre|yttre|seaward|ocean|offshore|avant[- ]port|vorhafen)\b'),
    ('bauwerk', r'schleuse|sluis|sperrwerk|kering|\b(?:sluice|locks?|[eé]cluse|esclusa|eclusa|chiusa|conca|sluse|sluss|shlyuz|'
                r'barrage|barragem|weir|wehr|stuw|siel|dam|presa)\b'),
    ('becken', r'dock\b|\b(?:basin|bassin|hafenbecken|d[aá]rsena|darse|kom)\b'),
]
LAGE_RE = [(g, re.compile(m, re.I)) for g, m in LAGE]


def lage(name):
    """Menge der Lagegruppen im Stationsnamen (ohne Land/Region nach dem ersten Komma)."""
    s = name.split(',')[0]
    return {g for g, m in LAGE_RE if m.search(s)}


FUELL = set('river bay harbour harbor port puerto pier jetty island islands isla ile point bay roads entrance '
             'lighthouse st saint the of de la le les du des el los las da do dos at and channel creek sound '
             'north south east west upper lower inside outside ny no rocks rock cove wan bight'.split())


def woerter(name):
    import unicodedata
    s = unicodedata.normalize('NFKD', name.split(',')[0]).encode('ascii', 'ignore').decode().lower()
    return {w for w in re.findall(r'[a-z]{3,}', s) if w not in FUELL}


# Meine Einzelurteile zu Namensfragen (3.11.2026), Schluessel = archivierter Name
HAND_VORSCHLAG = {
    'Bullenbaai, Curaçao': 'archivieren; bleibender Satz heisst dann "Bullenbaai, Curaçao" (Landessprache)',
    "Cox's Bazar, Bangladesh": 'archivieren; bleibender Satz heisst dann "Cox\'s Bazar" (amtliche Schreibung)',
    'Colón, Panama': 'archivieren; bleibender Satz heisst dann "Cristóbal (Colón), Panama" (Hafen Cristóbal liegt in Colón)',
    'Puntarenas, Costa Rica': 'archivieren; bleibender Satz heisst dann "Puntarenas, Costa Rica" (amtliche Schreibung)',
    'Paradip, Odisha, India': 'archivieren; bleibender Satz heisst dann "Paradip" (amtliche Schreibung)',
    'Sainte-Anne-des-Monts, Québec, Canada': 'archivieren; bleibender Satz heisst dann "Sainte-Anne-des-Monts" (amtliche Schreibung)',
    'Second Severn Crossing, England, United Kingdom': 'archivieren; bleibender Satz heisst dann "Prince of Wales Bridge (Second Severn Crossing)" (2018 umbenannt)',
    'Breakwater Harbor, Delaware': 'archivieren; bleibender Satz heisst dann "Lewes (Fort Miles, Breakwater Harbor), Delaware"',
    'Longbranch (USCOE dredge depot), Florida': 'archivieren (Long Branch = Longbranch); Name des bleibenden Satzes bleibt',
    'Marina Point, Antarctica': 'archivieren; bleibender Satz heisst dann "Faraday (Marina Point)" -- oder lieber "Vernadsky (Faraday)"?',
    'Shiashkotan (Severo-zapadnyy Bereg, Kuril\'skiye Ostrova), Sakhalin Oblast, Russia': 'beide bleiben (Nordwest- gegen Suedostkueste)',
    'Hoi Ha Wan (Jone\'s Cove), Hong Kong': 'beide bleiben (verschiedene Buchten, 3 km)',
    'La Cayenne (Seudre), France': 'beide bleiben (verschiedene Orte an der Seudre, 1,5 km)',
    'Narlwood Rocks, England, United Kingdom': 'beide bleiben (verschiedene Felsen im Severn)',
    'Baleeira (Sagres), Portugal': 'archivieren; bleibender Satz heisst dann "Sagres (Baleeira)" (Pegel liegt im Hafen Baleeira)',
    'Base Melchior (Archipiélago Melchior), Antártida Argentina, Argentina': 'FRAGE: Base Melchior (Isla Gamma) und Melchior Harbour 2,5 km -- dieselbe Stelle?',
    'Menemsha Bight (Martha\'s Vineyard), Massachusetts': 'FRAGE: Bucht draussen gegen Hafen drinnen (0,5 km) -- eine Stelle?',
    'Blaine (Semiahmoo Bay), Washington': 'FRAGE: Semiahmoo Bay draussen gegen Drayton Harbor drinnen (0,9 km) -- eine Stelle?',
    'Scarinish (Tiree), Scotland, United Kingdom': 'FRAGE: Scarinish-Hafen und Gott Bay 1 km -- eine Stelle?',
    'Keizersveer (Bergsche Maas), Netherlands': 'FRAGE: Keizersveer und Hank sind verschiedene Orte, stehen aber 0,1 km auseinander -- welche Position stimmt?',
}


def vorschlag_text(z):
    """Mein Vorschlag je Zeile (nur Hilfe fuer Oliver, wird nie automatisch ausgefuehrt)."""
    regel, d = z['regel'], float(z['km'])
    if z['name'] in HAND_VORSCHLAG and regel.endswith(':name'):
        return HAND_VORSCHLAG[z['name']]
    haupt = lambda n: woerter(n.split('(')[0])
    gemeinsam = haupt(z['name']) & haupt(z['bleibt'])
    if regel.endswith(':lage'):
        return 'beide bleiben (Lage verschieden: vor/hinter Bauwerk, innen/aussen) -- oder doch dieselbe Stelle?'
    if regel.endswith(':geschuetzt'):
        return 'bleibt (geschuetzt); nur archivieren, wenn du es ausdruecklich willst'
    if regel.endswith(':name'):
        if z['quelle'] == z['bleibt_quelle']:
            if z['rang'] == 'Altbestand':
                return 'FRAGE: Altbestand fuehrt denselben Pegel evtl. zweimal unter zwei Namen -- ein Ort oder zwei?'
            if float(z['fehler_prozent']) >= 1.0:
                return 'beide bleiben (eigene Pegel derselben Quelle)'
            return 'FRAGE: dieselbe Quelle, fast identische Tafel (<1 %) -- ein Pegel unter zwei Namen?'
        if d >= 1.5 and not gemeinsam:
            return 'beide bleiben (verschiedene Orte mit eigenem Namen)'
        if gemeinsam or (d < 1.5 and woerter(z['name']) & woerter(z['bleibt'])):
            return 'archivieren; Name des bleibenden Satzes behalten, Klammer pruefen'
        return 'FRAGE: derselbe Ort unter anderem Namen? Welcher Name bleibt?'
    return 'archivieren (gleicher Name, fast gleiche Kurve)'


def kurz(datei):
    """harmonics/classic/harmonics-dwf-20251228-free.txt -> dwf-20251228-free (Dateinamen sind eindeutig)."""
    return re.sub(r'^harmonics[_-]', '', os.path.splitext(os.path.basename(datei))[0])


def lang(k):
    """Kurzname -> Pfad relativ zu ROOT (Gegenstueck zu kurz)."""
    import glob
    for f in glob.glob(os.path.join(ROOT, 'harmonics', '*', '*.txt')):
        if '/backup/' not in f and kurz(f) == k:
            return os.path.relpath(f, ROOT)
    raise KeyError(k)


def rang(r):
    f = os.path.basename(r['file'])
    kl = P.klasse(r)
    q = G.quelle_kurz(r)
    if 'fes' in f:
        return 5
    if '/noaa/' in r['file']:
        return 0 if 'CO-OPS' in q else 4
    if 'secondary' in f or 'Uebertragung' in q:
        return 4
    if kl == 'B' or kl is None:
        return 3
    if 'JMA' in q:                                   # Vorhersagetafeln, keine Messung
        return 1
    if f.startswith(('harmonics_utide_observations', 'harmonics-dwf-20251228', 'harmonics_ticon4',
                     'harmonics_puertos')):
        return 0
    if f.startswith(('harmonics-1997', 'harmonics-2004')):
        return 2
    return 1


def folge(r):
    f = os.path.basename(r['file'])
    return next((i for i, k in enumerate(DATEIFOLGE) if f.startswith(k)), len(DATEIFOLGE))


def grenze(ra, rb, d):
    """Groesster Kurvenunterschied (Anteil), bei dem b neben a geloescht wird; None = nie."""
    if ra == rb:
        return 0.05 if d <= 0.5 else None
    if rb <= 2:
        return 0.10 if d <= 1.0 else None
    if d <= 1.0:
        return 0.15
    return 0.10 if d <= 3.0 else None


def geschuetzt(recs):
    """{(datei, name): grund}"""
    out = {}
    if os.path.exists(BEHALTEN):
        for z in csv.DictReader(open(BEHALTEN, encoding='utf-8')):
            out[(z['datei'], z['name'])] = 'behalten.csv'
    bezug = set()
    for r in recs:
        v = P.vermerk(r)
        for m in BEZUG:
            for treffer in m.findall(v):
                bezug.add(' '.join(treffer.split()).strip(' ,'))
        for t in re.findall(r'Bezug ([^\[\n]+?) \[', v):
            bezug.add(t.strip())
    for r in recs:
        schluessel = (r['file'], r['name'])
        if schluessel in out:
            continue
        if HAND.search(P.vermerk(r)):
            out[schluessel] = 'Vermerk Oliver'
        elif r['name'] in bezug or r['name'].split(',')[0] in bezug:
            out[schluessel] = 'Bezugsort fuer Uebertragungen'
    return out


def nachbarn(recs, radius=3.0):
    gitter = collections.defaultdict(list)
    for r in recs:
        gitter[(int(r['lat'] * 20), int(r['lon'] * 20))].append(r)
    for r in recs:
        gi, gj = int(r['lat'] * 20), int(r['lon'] * 20)
        dl = 1 + int(1 / max(0.05, math.cos(math.radians(r['lat']))))
        for i in (gi - 1, gi, gi + 1):
            for j in range(gj - dl, gj + dl + 1):
                for x in gitter.get((i, j), ()):
                    if x is not r:
                        d = km(r, x)
                        if d <= radius:
                            yield r, x, d


def vorschlag(recs, schutz):
    rg = {id(r): rang(r) for r in recs}
    paare = collections.defaultdict(list)
    for a, b, d in nachbarn(recs):
        paare[id(b)].append((a, d))
    reihenfolge = sorted(recs, key=lambda r: (rg[id(r)], folge(r), r['file'], r['line']))
    bleibt, raus, geschont = set(), [], []
    for b in reihenfolge:
        treffer = None
        for a, d in sorted(paare[id(b)], key=lambda p: p[1]):
            if id(a) not in bleibt:
                continue                             # nur gegen einen Satz, der selbst bleibt
            ra, rb = rg[id(a)], rg[id(b)]
            if ra > rb or (ra == rb and (folge(a), a['file'], a['line']) > (folge(b), b['file'], b['line'])):
                continue
            # Oliver 3.11.2026: gleiche (aktuelle) Quelle, anderer Name = eigener Pegel, nie Dublette.
            # Nur im Altbestand (XTide 1997/2004) kann eine Datei denselben Pegel zweimal fuehren.
            if (a['name'] != b['name'] and rb != 2 and G.quelle_kurz(a) == G.quelle_kurz(b)):
                continue
            g = grenze(ra, rb, d)
            if g is None:
                continue
            _abs, rel = curve_diff(a, b)
            if rel <= g:
                treffer = (a, d, rel, 'R2' if ra == rb else 'R1')
                break
        if not treffer:
            bleibt.add(id(b))
            continue
        grund = schutz.get((b['file'], b['name']))
        if grund == 'Bezugsort fuer Uebertragungen' and treffer[0]['name'].casefold() == b['name'].casefold():
            grund = None                             # gleichnamiger Satz bleibt -- der Bezug laeuft weiter
        if not grund and lage(treffer[0]['name']) != lage(b['name']):
            grund = 'lage'
        if not grund and namekey(a_name := treffer[0]['name']) != namekey(b['name']):
            grund = 'name'
        if grund:
            bleibt.add(id(b))
            geschont.append((b, treffer, grund))
            continue
        raus.append((b, treffer))
    return raus, geschont, rg


def regel_r3(recs, schutz, schon):
    """NOAA-Saetze, die laut unabhaengiger Messreihe gegen den A-Satz verlieren."""
    if not os.path.exists(MESSREIHEN):
        return []
    nach = {(os.path.basename(r['file']), r['name']): r for r in recs}
    urteile = collections.defaultdict(list)
    for z in csv.DictReader(open(MESSREIHEN, encoding='utf-8')):
        urteile[(z['noaa_datei'], z['noaa'], z['a_datei'], z['a_satz'])].append(z)
    out = []
    for (nd, nn, ad, an), zeilen in urteile.items():
        n, a = nach.get((nd, nn)), nach.get((ad, an))
        if not n or not a or (n['file'], n['name']) in schon or (n['file'], n['name']) in schutz:
            continue
        u = {z['urteil'] for z in zeilen}
        if u == {'A besser'}:
            z = zeilen[0]
            out.append((n, a, km(n, a), z))
    return out


def antworten(pfad):
    """{(name, datei, bleibt, bleibt_datei): antwort} aus Olivers Tabelle (.ods ueber LibreOffice, sonst CSV)."""
    if pfad.lower().endswith(('.ods', '.xlsx')):
        import tempfile
        tmp = tempfile.mkdtemp()
        subprocess.run(['soffice', '--headless', '--convert-to',
                        'csv:Text - txt - csv (StarCalc):44,34,76,1,,0,false,true,false,false,false,-1',
                        '--outdir', tmp, pfad], check=True, capture_output=True)
        pfad = os.path.join(tmp, sorted(os.listdir(tmp))[0])
    out = {}
    for z in csv.DictReader(open(pfad, encoding='utf-8')):
        a = ' '.join((z.get('antwort') or '').split())
        if a:
            out[(z['name'], kurz(lang(z['datei'])), z['bleibt'], kurz(lang(z['bleibt_datei'])))] = a
    return out


def antworten_zuordnen(zeilen, antw):
    """-> (archivieren, behalten, von_hand, veraltet)"""
    nach = {(z['name'], kurz(z['datei']), z['bleibt'], kurz(z['bleibt_datei'])): z for z in zeilen}
    raus, beh, hand, alt = [], [], [], []
    for k, a in antw.items():
        z = nach.get(k)
        ja = a.lower() in ('ja', 'j', 'yes', 'ok', 'einverstanden')
        if z is None:
            alt.append((k, a))                       # Paar steht nicht mehr in der Liste (Regel geaendert)
        elif a.lower() == 'archivieren':
            raus.append(z)                           # ausdruecklich, auch gegen "beide bleiben"/geschuetzt
        elif ja and z['vorschlag'].startswith('archivieren'):
            raus.append(z)
        elif ja:
            beh.append((z, 'beide bleiben (Ja zu: ' + z['vorschlag'][:60] + ')'))   # merken, sonst kommt das Paar jede Runde wieder
        elif a.lower() in ('nein', 'n', 'no', 'beide bleiben'):
            beh.append((z, a))
        else:
            hand.append((z, a))
    return raus, beh, hand, alt


def main(argv):
    ausfuehren = '--ausfuehren' in argv
    recs = [r for r in load_records() if not r['current'] and r['lat'] is not None and r['lon'] is not None]
    print(f'{len(recs)} Gezeitensaetze', flush=True)
    schutz = geschuetzt(recs)
    raus, geschont, rg = vorschlag(recs, schutz)
    schon = {(b['file'], b['name']) for b, _t in raus}
    r3 = regel_r3(recs, schutz, schon)

    zeilen = []
    for b, (a, d, rel, regel) in raus:
        zeilen.append(dict(
            regel=regel, datei=b['file'], name=b['name'], fehler_prozent=f'{100 * rel:.1f}',
            rang=RANGNAME[rg[id(b)]], quelle=G.quelle_kurz(b),
            bleibt=a['name'], bleibt_datei=a['file'], bleibt_rang=RANGNAME[rg[id(a)]],
            bleibt_quelle=G.quelle_kurz(a), km=f'{d:.2f}',
            begruendung=(f'REGEL {regel}: {G.quelle_kurz(b)} ({RANGNAME[rg[id(b)]]}) {d:.2f} km neben '
                         f'"{a["name"]}" ({G.quelle_kurz(a)}, {RANGNAME[rg[id(a)]]}); '
                         f'Kurvenunterschied {100 * rel:.1f} %.')))
    for n, a, d, z in r3:
        zeilen.append(dict(
            regel='R3', datei=n['file'], name=n['name'], fehler_prozent=z['abw_pct'],
            rang=RANGNAME[4], quelle=G.quelle_kurz(n), bleibt=a['name'], bleibt_datei=a['file'],
            bleibt_rang=RANGNAME[rg.get(id(a), 1)], bleibt_quelle=G.quelle_kurz(a), km=f'{d:.2f}',
            begruendung=(f'REGEL R3: widerspricht "{a["name"]}" ({G.quelle_kurz(a)}, {d:.2f} km); '
                         f'Pegelreihe {z["reihe"]} ({z["reihe_km"]} km): RMS NOAA {float(z["rms_noaa"]):.3f} m, '
                         f'A {float(z["rms_a"]):.3f} m.')))
    for b, (a, d, rel, regel), grund in geschont:
        if grund == 'behalten.csv':
            continue                                 # schon entschieden (Oliver/zurueckgeholt) -- nicht erneut vorlegen
        zeilen.append(dict(
            regel=regel + (':' + grund if grund in ('name', 'lage') else ':geschuetzt'), datei=b['file'], name=b['name'], fehler_prozent=f'{100 * rel:.1f}',
            rang=RANGNAME[rg[id(b)]], quelle=G.quelle_kurz(b), bleibt=a['name'], bleibt_datei=a['file'],
            bleibt_rang=RANGNAME[rg[id(a)]], bleibt_quelle=G.quelle_kurz(a), km=f'{d:.2f}',
            begruendung=('Namen verschieden' if grund == 'name' else
                         f'Lage verschieden ({"/".join(sorted(lage(b["name"]))) or "-"} gegen '
                         f'{"/".join(sorted(lage(a["name"]))) or "-"})' if grund == 'lage' else f'geschuetzt ({grund})')))

    for i, z in enumerate(zeilen, 1):
        z['nr'] = i
        z['vorschlag'] = vorschlag_text(z) if z['regel'] != 'R3' else 'archivieren (Messreihe gibt dem Messsatz recht)'
    felder = ['nr', 'regel', 'vorschlag', 'name', 'bleibt', 'km', 'fehler_prozent', 'rang', 'quelle',
              'bleibt_rang', 'bleibt_quelle', 'datei', 'bleibt_datei', 'begruendung']
    with open(PROBE, 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=felder)
        w.writeheader()
        w.writerows({**z, 'datei': kurz(z['datei']), 'bleibt_datei': kurz(z['bleibt_datei'])} for z in zeilen)

    zaehl = collections.Counter(z['regel'] for z in zeilen)
    print('\nRegel            Saetze  Freigabe')
    for regel in sorted(zaehl):
        basis = regel.split(':')[0]
        print(f'  {regel:16} {zaehl[regel]:5}   {FREIGABE.get(basis) or "-" if ":" not in regel else ""}')
    wer = collections.Counter((z['regel'], z['rang'], z['bleibt_rang']) for z in zeilen if ':' not in z['regel'])
    print('\nwer weicht wem:')
    for (regel, r1, r2), n in sorted(wer.items(), key=lambda p: -p[1]):
        print(f'  {regel}  {r1:13} weicht {r2:13} {n:5}')
    print(f'\n-> {os.path.relpath(PROBE, ROOT)}')

    heute = dt.date.today()
    if '--antworten' in argv:
        quelle = argv[argv.index('--antworten') + 1]
        frei, beh, hand, alt = antworten_zuordnen(zeilen, antworten(quelle))
        print(f'\nAntworten {os.path.basename(quelle)}: {len(frei)} archivieren, {len(beh)} behalten, '
              f'{len(hand)} von Hand, {len(alt)} nicht mehr in der Liste')
        for z, a in hand:
            print(f'  VON HAND  {z["name"]} | {z["bleibt"]}: {a}')
        for k, a in alt:
            print(f'  ENTFALLEN {k[0]} | {k[2]}: {a}')
        if not ausfuehren:
            return 0
        if beh:
            neu = not os.path.exists(BEHALTEN)
            with open(BEHALTEN, 'a', newline='', encoding='utf-8') as fh:
                w = csv.DictWriter(fh, fieldnames=['datei', 'name', 'datum', 'grund'])
                if neu:
                    w.writeheader()
                for z, a in beh:
                    w.writerow(dict(datei=z['datei'], name=z['name'], datum=f'{heute:%Y%m%d}',
                                    grund=f'Oliver: {a} (neben {z["bleibt"]})'))
        for z in frei:
            z['begruendung'] += f' Freigabe Oliver {heute:%d.%m.%Y} ({os.path.basename(quelle)}).'
    else:
        if not ausfuehren:
            return 0
        frei = [z for z in zeilen if FREIGABE.get(z['regel'])]
        for z in frei:
            z['begruendung'] += f' Regelfreigabe Oliver {FREIGABE[z["regel"]]}.'
    if not frei:
        print('\nNichts freigegeben -- nichts geloescht.')
        return 0
    liste = os.path.join(HELP, f'loeschen_auto_{heute:%Y%m%d}.csv')
    n = 2
    while os.path.exists(liste):                     # zweite Runde am selben Tag nicht ueberschreiben (3.11.2026)
        liste = os.path.join(HELP, f'loeschen_auto_{heute:%Y%m%d}_runde{n}.csv')
        n += 1
    with open(liste, 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=['datei', 'name', 'fehler_prozent', 'begruendung'])
        w.writeheader()
        w.writerows({k: z[k] for k in ('datei', 'name', 'fehler_prozent', 'begruendung')} for z in frei)
    py = os.path.join(ROOT, 'py')
    erg = subprocess.run([sys.executable, os.path.join(py, 'saetze_loeschen.py'), liste, '--schreiben'])
    if erg.returncode:
        print('Loeschen fehlgeschlagen -- Protokoll nicht geschrieben.')
        return 1
    neu = not os.path.exists(PROTOKOLL)
    with open(PROTOKOLL, 'a', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=['datum'] + felder)
        if neu:
            w.writeheader()
        w.writerows(dict(z, datum=f'{heute:%Y%m%d}') for z in frei)
    print(f'{len(frei)} Saetze geloescht, Protokoll {os.path.relpath(PROTOKOLL, ROOT)}')
    subprocess.run([sys.executable, os.path.join(py, 'tcd_bauen.py')])
    subprocess.run([sys.executable, os.path.join(py, 'build_tide_station_markers.py')])
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
