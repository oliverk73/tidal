#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sammelt die Laenderberichte der IHO-Regionalkommissionen.

Wer welche Gezeitentafeln herausgibt, steht nirgends gesammelt -- ausser in
diesen Berichten: Jeder Mitgliedsstaat schreibt seiner Regionalkommission
regelmaessig auf, was sein hydrographisches Amt veroeffentlicht. Der Bericht
Mosambiks nennt zum Beispiel genau die elf Haefen, fuer die INAHINA Tafeln
druckt. Das ist kein Suchen mehr, sondern ein Verzeichnis.

Aufbau der Seiten (iho.int, 16.09.2026):
  /en/rhcs                     Liste der Kommissionen
  /en/<kommission>             Liste der Tagungen
  /en/<tagung>                 Liste der Dokumente (PDF-Links)
  /uploads/user/Inter-Regional Coordination/RHC/<K>/<K><N>/<datei>.pdf

Geladen wird hoeflich: eine Anfrage je Sekunde, ehrlicher User-Agent, und
nichts wird zweimal geholt. Die PDFs landen unter
tide_tables/catalogues/iho_berichte/, ihr Text daneben als .txt.

Usage: python3 py/iho_berichte_sammeln.py [--nur EAtHC] [--sammeln] [--auswerten]
       --suchen     Seiten abklappern und die Linkliste neu bauen
       --altseiten  alte _Docs.htm-Listen und Suchtreffer (ZUSATZ) dazunehmen
       --sammeln    PDFs laden (sonst nur die vorhandene Liste benutzen)
       --auswerten  Text nach Gezeitentafeln und Haefen durchsuchen
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from health_check import ROOT                                       # noqa: E402

BASIS = 'https://iho.int'
UA = 'oliver-weather-tides/1.0 (private tide research; oliver.k73@gmail.com)'
ZIEL = os.path.join(ROOT, 'tide_tables/catalogues/iho_berichte')
LISTE = os.path.join(ZIEL, 'dokumente.json')
PAUSE = 1.0

# Die Kommissionsseiten heissen nicht wie ihre Kuerzel; hier beides.
KOMMISSIONEN = {
    'ARHC': 'arctic-region-hc', 'BSHC': 'baltic-sea-hc', 'EAHC': 'east-asia-hc',
    'EAtHC': 'eastern-atlantic-hc', 'MACHC': 'machc',
    'MBSHC': 'mediterranean-and-black-seas-hc', 'NHC': 'nordic-hc',
    'NIOHC': 'north-indian-ocean-hc', 'NSHC': 'north-sea-hc',
    'RSAHC': 'ropme-sea-area-hc', 'SAIHC': 'southern-african-and-islands-hc',
    'SWAtHC': 'swathc', 'SWPHC': 'swphc', 'SEPRHC': 'seprhc',
}
# Die Slugs stammen aus /en/rhcs (16.09.2026). Bei SAIHC, MACHC, SWAtHC, EAHC
# und NHC verlinkt die Kommissionsseite ihre Tagungen nicht; deren Berichte
# kommen ueber ZUSATZ (Suchmaschine) herein.
BERICHT = re.compile(r'national[_%\s\-]*report|rapport[_%\s\-]*national|informe[_%\s\-]*nacional', re.I)
TAFEL = re.compile(r'tide table|tidal table|tide-table|tabela de mar|tabla de marea|'
                   r'annuaire des mar|tide predictions|tidal predictions|tide book', re.I)


def hole(url, roh=False):
    # Manche Dateinamen auf iho.int enthalten Leerzeichen ("ARHC8 B3 DK National
    # Report Denmark.pdf"); urllib lehnt sie ungeschuetzt ab. Nur der Pfad wird
    # kodiert, das Schema und der Host bleiben, wie sie sind.
    teile = urllib.parse.urlsplit(url)
    url = urllib.parse.urlunsplit(teile._replace(
        path=urllib.parse.quote(teile.path, safe='/%'),
        query=urllib.parse.quote(teile.query, safe='=&%')))
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=90) as r:
        d = r.read()
    time.sleep(PAUSE)
    return d if roh else d.decode('utf-8', errors='replace')


def links(html, muster, basis=BASIS):
    """Alle passenden Links, absolut gemacht.

    Manche Seiten verlinken relativ ("../uploads/..."); stumpf angehaengt ergab
    das "https://iho.int../uploads/..." und damit 75 fehlgeschlagene Abrufe
    (16.09.2026). urljoin loest das gegen die Seitenadresse auf.
    """
    out = []
    for m in re.finditer(r'href="([^"]+)"', html):
        u = m.group(1)
        if re.search(muster, u, re.I):
            out.append(urllib.parse.urljoin(basis, u))
    return sorted(set(out))


def dokumente(nur=None):
    """-> [(kommission, tagungsseite, pdf-url)] aller Laenderberichte."""
    out = []
    for kurz, seite in KOMMISSIONEN.items():
        if nur and nur.lower() not in (kurz.lower(), seite):
            continue
        try:
            html = hole(f'{BASIS}/en/{seite}')
        except Exception as e:
            print(f'  {kurz}: {e}', file=sys.stderr)
            continue
        tagungen = [u for u in links(html, r'/en/' + kurz.lower() + r'[0-9]', f'{BASIS}/en/{seite}')]
        print(f'{kurz}: {len(tagungen)} Tagungen', flush=True)
        for t in tagungen:
            try:
                h2 = hole(t)
            except Exception as e:
                print(f'    {t}: {e}', file=sys.stderr)
                continue
            pdfs = [u for u in links(h2, r'\.pdf$', t) if BERICHT.search(urllib.parse.unquote(u))]
            for p in pdfs:
                out.append((kurz, t, p))
            print(f'    {t.rsplit("/", 1)[-1]}: {len(pdfs)} Laenderberichte', flush=True)
    return out


# Aeltere Tagungen haben eine HTML-Dokumentliste /mtg_docs/rhc/<K>/<K><N>/<K><N>_Docs.htm
# (HREF oft ohne oeffnendes Anfuehrungszeichen). Fuer die Kommissionen, deren
# neue Seiten ihre Tagungen nicht verlinken, werden diese Listen durchprobiert.
INDEXSEITEN = {'SAIHC': range(8, 17), 'MACHC': range(12, 21), 'EAHC': range(8, 14),
               'SWATHC': range(3, 13), 'NHC': range(55, 64)}
# Einzelne Berichte, die nur ueber die Suchmaschine auftauchten (16.09.2026).
ZUSATZ = [
    ('SAIHC', 'https://iho.int/uploads/user/Inter-Regional%20Coordination/RHC/SAIHC/SAIHC17/SAIHC17_2021_6.3_MOZAMBIQUE_National%20report.pdf'),
    ('SAIHC', 'https://iho.int/uploads/user/Inter-Regional%20Coordination/RHC/SAIHC/SAIHC17/SAIHC17_2021_6.5_South%20Africa_national%20report.pdf'),
    ('SAIHC', 'https://iho.int/uploads/user/Inter-Regional%20Coordination/RHC/SAIHC/SAIHC18/SAIHC18_2022_6.4%20National_Report_Mauritius.pdf'),
    ('SAIHC', 'https://iho.int/uploads/user/Inter-Regional%20Coordination/RHC/SAIHC/SAIHC18/SAIHC18_2022_6.7_National_Report_South_Africa.pdf'),
    ('SAIHC', 'https://iho.int/uploads/user/Inter-Regional%20Coordination/RHC/SAIHC/SAIHC19/SAIHC19-7.11_2023_India%20National%20Report.pdf'),
    ('SAIHC', 'https://iho.int/uploads/user/Inter-Regional%20Coordination/RHC/SAIHC/SAIHC20/SAIHC20_2024_08.02_EN_DMI_REX_SAIHC20_NATIONAL-REPORT-France.pdf'),
    ('MACHC', 'https://iho.int/uploads/user/Inter-Regional%20Coordination/RHC/MACHC/MACHC21/MACHC21_2020_03.9_EN_National_Report_Mexico.pdf'),
    ('MACHC', 'https://iho.int/uploads/user/Inter-Regional%20Coordination/RHC/MACHC/MACHC21/MACHC21_2020_03.14_EN_National_Report_USA.pdf'),
    ('MACHC', 'https://iho.int/uploads/user/Inter-Regional%20Coordination/RHC/MACHC/MACHC23/MACHC23_2022_03.1_EN_National_Report_Brazil_v1.pdf'),
    ('NIOHC', 'https://iho.int/mtg_docs/rhc/NIOHC/NIOHC18/NIOHC18-06d-National_Rport-IDN.pdf'),
]


def indexseiten():
    """-> [(kommission, indexseite, pdf-url)] aus den alten _Docs.htm-Listen."""
    out = []
    for kurz, nummern in INDEXSEITEN.items():
        for n in nummern:
            seite = f'{BASIS}/mtg_docs/rhc/{kurz}/{kurz}{n}/{kurz}{n}_Docs.htm'
            try:
                html = hole(seite)
            except Exception:
                continue
            for m in re.findall(r'''href=["']?([^"' >]+)''', html, re.I):
                u = urllib.parse.urljoin(seite, m)
                if u.lower().endswith('.pdf') and BERICHT.search(urllib.parse.unquote(u)):
                    out.append((kurz.upper() if kurz != 'SWATHC' else 'SWAtHC', seite, u))
            print(f'  {kurz}{n}: Indexseite gefunden', flush=True)
    return out


def laden(docs):
    os.makedirs(ZIEL, exist_ok=True)
    for kurz, _t, url in docs:
        name = urllib.parse.unquote(url.rsplit('/', 1)[-1])
        name = re.sub(r'[^A-Za-z0-9._-]+', '_', name)
        pfad = os.path.join(ZIEL, f'{kurz}_{name}')
        if os.path.exists(pfad) and os.path.getsize(pfad) > 0:
            continue
        # Erst holen, dann schreiben: open(...,'wb') legt die Datei sofort an,
        # und ein Fehler beim Abruf hinterliess 72 leere PDFs, die beim naechsten
        # Lauf als "schon da" galten (16.09.2026).
        try:
            daten = hole(url, roh=True)
        except Exception as e:
            print(f'  {name}: {e}', file=sys.stderr)
            continue
        with open(pfad + '.teil', 'wb') as fh:
            fh.write(daten)
        os.replace(pfad + '.teil', pfad)
        print(f'  geladen: {os.path.basename(pfad)} ({len(daten) // 1024} kB)', flush=True)


def auswerten():
    """Sucht in den Texten nach Gezeitentafeln und den genannten Haefen."""
    treffer = []
    for f in sorted(os.listdir(ZIEL)):
        if not f.endswith('.pdf'):
            continue
        txt = os.path.join(ZIEL, f[:-4] + '.txt')
        if not os.path.exists(txt):
            subprocess.run(['pdftotext', '-layout', os.path.join(ZIEL, f), txt],
                           capture_output=True)
        try:
            t = open(txt, encoding='utf-8', errors='replace').read()
        except OSError:
            continue
        stellen = []
        for m in TAFEL.finditer(t):
            a = max(0, m.start() - 200)
            stellen.append(' '.join(t[a:m.end() + 400].split()))
        if stellen:
            treffer.append(dict(datei=f, land=f.split('_', 1)[1][:40], stellen=stellen[:4]))
    json.dump(treffer, open(os.path.join(ZIEL, 'tafelstellen.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print(f'{len(treffer)} Berichte nennen Gezeitentafeln -> tafelstellen.json')
    for z in treffer[:15]:
        print(f'\n== {z["datei"]}')
        print('   ', z['stellen'][0][:300])


def main(argv):
    nur = argv[argv.index('--nur') + 1] if '--nur' in argv else None
    os.makedirs(ZIEL, exist_ok=True)
    # Die Schritte sind einzeln schaltbar und bauen aufeinander auf: ohne
    # --suchen wird die vorhandene Linkliste benutzt, statt die Seiten erneut
    # abzuklappern. (Erste Fassung sprang bei --auswerten sofort in die
    # Auswertung und lud deshalb nie etwas.)
    if '--suchen' in argv or not os.path.exists(LISTE):
        neu = dokumente(nur)
        # Zusammenfuehren statt ersetzen: ein Lauf mit --nur SWPHC darf die
        # Eintraege der anderen Kommissionen nicht loeschen (ist am 16.09.2026
        # einmal passiert; die Liste kam aus der Sicherung zurueck).
        alt = json.load(open(LISTE, encoding='utf-8')) if os.path.exists(LISTE) else []
        if nur:
            alt = [d for d in alt if d[0].lower() != nur.lower()]
        docs = alt + [d for d in neu if d not in alt]
        json.dump(docs, open(LISTE, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        print(f'\n{len(neu)} Laenderberichte gefunden, {len(docs)} in der Liste -> {os.path.relpath(LISTE, ROOT)}')
    else:
        docs = json.load(open(LISTE, encoding='utf-8'))
        print(f'{len(docs)} Laenderberichte aus der Liste')
    if '--altseiten' in argv:
        extra = indexseiten() + [(k, 'Suchmaschine', u) for k, u in ZUSATZ]
        vorher = len(docs)
        docs = docs + [d for d in extra if d[2] not in {x[2] for x in docs}]
        json.dump(docs, open(LISTE, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        print(f'{len(docs) - vorher} Berichte aus alten Indexseiten und Suche dazu, {len(docs)} in der Liste')
    if '--sammeln' in argv:
        laden(docs)
    if '--auswerten' in argv:
        auswerten()
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
