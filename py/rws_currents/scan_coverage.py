#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Schritt 1: RWS STROOMSHD-Stationen klassifizieren + Jahres-Coverage scannen.
Nutzt den billigen Zaehl-Endpunkt (OphalenAantalWaarnemingen, Groeperingsperiode=Jaar).
Baut NICHTS, laedt keine Messdaten -> nur Coverage-Uebersicht."""
import json, time, sys, urllib.request

BASE = 'https://ddapi20-waterwebservices.rijkswaterstaat.nl'
CNT = f'{BASE}/ONLINEWAARNEMINGENSERVICES/OphalenAantalWaarnemingen'

# --- Klassifikation: Binnenkanal/Fluss (nicht-tidal) ausschliessen ---
INLAND = ('bunde.kanaal', 'smeermaas', 'weert.lozen', 'ommen.ommerkanaal', 'ommen.vecht',
          'maarssen.kanaal', 'nieuwegein.doorslag', 'nieuwegein.lekkanaal',
          'wijkbijduurstede.amsterdamrijnkanaal', 'genemuiden', 'zwartsluis.meppelerdiep',
          'eemdijk', 'megen.maas', 'driel.boven', 'hagestein.boven', 'helmond',
          'lemmer.stroomkanaal.teroelsterkolk', 'lemmer.stroomkanaal.woudagemaal',
          'nederweert.bovenstroomsluis')

def classify(code, naam):
    c = code.lower()
    if c in INLAND:
        return 'inland'
    if 'uitdekust' in c:
        return 'offshore'
    if 'stroommeetpaal' in c or 'erosiegeul' in c or c.startswith('ijgeul'):
        return 'havenmond'
    if any(k in c for k in ('waddenzee', 'borndiep', 'ameland', 'eemshaven', 'denhelder',
                            'holwerd', 'dantziggat', 'slenk', 'schaar.stroomgat',
                            'buitenbanken', 'suurhof')):
        return 'wadden'
    if any(k in c for k in ('oudemaas', 'hollandschdiep', 'dordtschekil', 'spijkenisse',
                            'haringvliet', 'alblasserdam')):
        return 'estuary'
    return 'overig'

def post(url, body):
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={'Content-Type': 'application/json', 'X-API-KEY': 'dummy'})
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.loads(r.read().decode())

def year_counts(code, lon, lat, b='2005-01-01', e='2027-01-01'):
    body = {"AquoMetadataLijst": [{"Grootheid": {"Code": "STROOMSHD"}}],
            "LocatieLijst": [{"X": lon, "Y": lat, "Code": code, "Coordinatenstelsel": "ETRS89"}],
            "Periode": {"Begindatumtijd": f"{b}T00:00:00.000+01:00",
                        "Einddatumtijd": f"{e}T00:00:00.000+01:00"},
            "Groeperingsperiode": "Jaar"}
    try:
        d = post(CNT, body)
    except Exception as ex:
        return None, str(ex)[:40]
    out = {}
    for blk in d.get('AantalWaarnemingenPerPeriodeLijst', []):
        for m in blk.get('AantalMetingenPerPeriodeLijst', []):
            yr = m['Groeperingsperiode'].get('Jaarnummer')
            if yr:
                out[yr] = out.get(yr, 0) + m['AantalMetingen']
    return out, None

def main():
    cat = json.load(open('rws_cat.json'))
    md = cat['AquoMetadataLijst']; rel = cat['AquoMetadataLocatieLijst']
    locby = {l['Locatie_MessageID']: l for l in cat['LocatieLijst']}
    shd = {m['AquoMetadata_MessageID'] for m in md if m.get('Grootheid', {}).get('Code') == 'STROOMSHD'}
    stations = {}
    for r in rel:
        if r['AquoMetaData_MessageID'] in shd:
            l = locby.get(r['Locatie_MessageID'])
            if l and l.get('Lat'):
                stations[l['Code']] = (l['Naam'], l['Lon'], l['Lat'])

    # Dordrecht-Tiefenbins zu je 1 Repraesentant (.000) zusammenfassen
    skip_bins = {c for c in stations if ('.oudemaas.' in c or '.hollandschdiep.' in c)
                 and not c.endswith('.000')}
    rows = []
    cand = sorted(c for c in stations if c not in skip_bins)
    print(f"# {len(stations)} STROOMSHD-Locations, {len(skip_bins)} Tiefenbins zusammengefasst, "
          f"{len(cand)} zu scannen\n", file=sys.stderr)
    for code in cand:
        naam, lon, lat = stations[code]
        cls = classify(code, naam)
        if cls == 'inland':
            rows.append((cls, code, naam, lat, lon, '', 0, 0)); continue
        yc, err = year_counts(code, lon, lat)
        time.sleep(0.2)
        if err:
            rows.append((cls, code, naam, lat, lon, f'ERR:{err}', 0, 0)); continue
        yrs = sorted(y for y, n in yc.items() if n > 1000)   # Jahre mit nennenswerten Daten
        span = f"{yrs[0]}-{yrs[-1]}" if yrs else '-'
        maxn = max(yc.values()) if yc else 0
        rows.append((cls, code, naam, lat, lon, span, len(yrs), maxn))
        print(f"  {cls:9s} {code:34s} {span:10s} {len(yrs):2d}J max={maxn}", file=sys.stderr)

    json.dump(rows, open('coverage.json', 'w'))
    print("\n=== ZUSAMMENFASSUNG nach Klasse (nur tidal-relevante) ===")
    order = ['havenmond', 'wadden', 'offshore', 'estuary', 'overig', 'inland']
    for cls in order:
        sub = [r for r in rows if r[0] == cls]
        good = [r for r in sub if r[6] >= 1]
        print(f"\n## {cls}: {len(sub)} Stationen, {len(good)} mit Daten")
        for cls_, code, naam, lat, lon, span, nyr, maxn in sorted(sub, key=lambda r:-r[6]):
            flag = '✓' if nyr >= 1 else ' '
            print(f"  {flag} {code:34s} {naam[:30]:30s} {lat:.3f},{lon:.3f}  {span:10s} {nyr:2d}J")

if __name__ == '__main__':
    main()
