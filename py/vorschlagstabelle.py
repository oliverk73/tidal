#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Vorsortierte Tabelle der Namens- und Positionsbefunde einer Pruefliste fuer Oliver.

Erzeugt aus harmonics/help/pruefliste_<land>_<datum>.json eine HTML-Seite
harmonics/help/vorschlaege_<land>_<datum>.html mit drei Gruppen:
  B  Fehlalarm (Riff, Bank, Barre, Kanal, Strasse: Position im Wasser normal) -- zum Bestaetigen
  C  Amtspegel mit Kreis-/Insel-/Stadtnamen: was liegt am Pegel? (kein Namensvorschlag)
  D  unklar, braucht Olivers Blick
Je Zeile: Befund, urspruengliche (Buch-)Position, gleichnamige Objekte in der Naehe mit Abstand
zum Pegel und zur Buchposition, OSM- und Google-Maps-Link.

Keine erfundenen Namen (Indonesien 15.10.2026: Automatik schlug "Marapokot Dua" vor und haette
Olivers Tepeleu -> Tepeleo zurueckgedreht). Von Hand gesetzte Namen/Positionen sind markiert (N/P).
Aendert nichts an den Harmonics-Dateien.

Usage: venv/bin/python py/vorschlagstabelle.py <Land>
"""
import csv
import difflib
import glob
import html
import json
import os
import re
import sys

LAND = sys.argv[1] if len(sys.argv) > 1 else 'Indonesia'
os.environ['PRUEF_LAND'] = LAND
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pruefe_namen_positionen as P                                # noqa: E402

ROOT = P.ROOT
VIRT = re.compile(r'\b(Outer Bar|Bar|Karang|Gosong|Reef|Reefs|Beting|Channel|Bank|Shoal|Passage|Pass|Strait|Sound|Entrance)\b|^(Selat|Mui|Hon|Ko|Pulau) ', re.I)
AMT = ('big (badan', 'pushidrosal', 'bmkg', 'vho navy', 'icoe', 'nchmf', 'royal thai navy', 'nmdis', 'namria',
       'khoa', 'survey of india', 'hko', 'cwa')


def quelle(d, kopf):
    k = kopf.lower()
    for a in AMT:
        if a in k:
            return a.split(' (')[0].upper().replace('BIG', 'BIG').strip()
    if 'observations' in d:
        return 'UHSLC'
    for t, n in (('ticon', 'TICON'), ('att_np', 'ATT'), ('noaa', 'NOAA'), ('fes', 'FES'), ('classic', 'Altsatz')):
        if t in d:
            return n
    return os.path.basename(d)


def main():
    stem = LAND.lower().replace(' ', '_')
    js = sorted(glob.glob(os.path.join(ROOT, 'harmonics/help/pruefliste_%s_*.json' % stem)))[-1]
    J = json.load(open(js))
    lock = {r['name']: r for r in csv.DictReader(open(os.path.join(ROOT, 'harmonics/help/positions_locked.csv'), encoding='utf-8'))}
    import dubletten_kurven as D
    kopf = {(s['name'], s['file']): s['kopf'] for s in D.saetze(LAND, sorted({z['datei'] for z in J}))}
    zeilen = []
    for z in J:
        bef = [b for b in z['befunde'] if b.startswith(('NAME', 'LAND', 'MEER', 'ANLEGER'))]
        if not bef:
            continue
        n = z['satz'].rsplit(', ' + LAND, 1)[0]
        teil = n.split(',')[0]
        haupt = re.sub(r'\s*\(.*?\)', '', teil).strip()
        b = ' / '.join(bef)
        q = quelle(z['datei'], kopf.get((z['satz'], z['datei']), ''))
        lk = lock.get(z['satz'], {})
        hn, hp = bool(lk.get('orig_name')), (lk.get('moved_m') or '').strip() not in ('', '0')
        u = (float(lk['orig_lat']), float(lk['orig_lon'])) if (lk.get('orig_lat') or '').strip() else None
        # gleichnamige Objekte bis 25 km
        nk = P.norm(haupt)
        kand = []
        for o in P.OBJ:
            if abs(o['lat'] - z['lat']) > 0.25 or abs(o['lon'] - z['lon']) > 0.25:
                continue
            s = max((difflib.SequenceMatcher(None, nk, v).ratio() for v in o['v']), default=0)
            if s >= 0.85:
                d = P.m((z['lat'], z['lon']), (o['lat'], o['lon']))
                du = P.m(u, (o['lat'], o['lon'])) if u else None
                kand.append((-s, d, o['anzeige'], o['art'], d, du))
        kand.sort()
        kt = '; '.join('%s [%s] %d m%s' % (k[2], k[3], k[4], (' / %d m vom Buchwert' % k[5]) if k[5] is not None else '') for k in kand[:3])
        if VIRT.search(haupt) and not b.startswith('NAME') and 'NAME' not in b:
            kat, vor = 'B', 'bestaetigen'
        elif q not in ('ATT', 'NOAA', 'Altsatz', 'TICON', 'UHSLC', 'FES') and ('passt nicht' in b or 'nicht gefunden' in b):
            kat, vor = 'C', 'Ortsteil/Hafen in die Klammer?'
        else:
            kat, vor = 'D', ''
        zeilen.append(dict(kat=kat, satz=n, q=q, b=b, vor=vor, kand=kt, hier=z['hier'], lat=z['lat'], lon=z['lon'], u=u, h=('N' if hn else '') + ('P' if hp else '')))
    zeilen.sort(key=lambda r: (r['kat'], r['satz']))
    K = {'B': 'Fehlalarm, bestaetigen (Riff/Bank/Barre/Kanal)', 'C': 'Amtspegel mit Kreis-/Insel-/Stadtnamen: Ortsteil oder Hafen in die Klammer?',
         'D': 'Unklar, braucht deinen Blick'}
    osm = lambda la, lo: 'https://www.openstreetmap.org/?mlat=%.5f&mlon=%.5f#map=15/%.5f/%.5f' % (la, lo, la, lo)
    gm = lambda la, lo: 'https://www.google.com/maps/search/?api=1&query=%.5f,%.5f' % (la, lo)
    out = ['<!doctype html><meta charset="utf-8"><title>Vorschlaege %s</title>' % html.escape(LAND),
           '<style>body{font:14px sans-serif;margin:16px}td{padding:3px 6px;border-bottom:1px solid #ddd;vertical-align:top}th{text-align:left}</style>',
           '<h1>%s: Namen und Positionen, vorsortiert</h1><p>Nichts davon ist umgesetzt. Keine erfundenen Namen. H = von Hand gesetzt '
           '(N Name, P Position). Gueteprobleme (Zeit, Dubletten) sind schon entschieden.</p>' % html.escape(LAND)]
    for kat in 'BCD':
        rr = [r for r in zeilen if r['kat'] == kat]
        if not rr:
            continue
        out.append('<h2>%s: %s (%d)</h2><table><tr><th>#</th><th>Satz</th><th>Quelle</th><th>Befund</th><th>Vorschlag</th>'
                   '<th>Gleichnamig in der Naehe</th><th>Am Pegel</th><th>H</th><th>Karte</th></tr>' % (kat, K[kat], len(rr)))
        for i, r in enumerate(rr, 1):
            karte = '<a href="%s">OSM</a> <a href="%s">GM</a>' % (osm(r['lat'], r['lon']), gm(r['lat'], r['lon']))
            if r['u']:
                karte += ' <a href="%s">Buchwert</a>' % gm(*r['u'])
            out.append('<tr><td>%s%d</td><td>%s</td><td>%s</td><td>%s</td><td><b>%s</b></td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>' % (
                kat, i, html.escape(r['satz']), r['q'], html.escape(r['b'][:200]), html.escape(r['vor']), html.escape(r['kand'][:200]),
                html.escape(r['hier'][:160]), r['h'], karte))
        out.append('</table>')
    ziel = js.replace('pruefliste_', 'vorschlaege_').replace('.json', '.html')
    open(ziel, 'w').write('\n'.join(out))
    from collections import Counter
    print(LAND, dict(Counter(r['kat'] for r in zeilen)), '->', os.path.relpath(ziel, ROOT))


if __name__ == '__main__':
    P.URSPRUNG = P.ursprung()
    main()
