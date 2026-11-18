"""NOAA-Table-2-Uebertragungen: S2/M2 gegen unabhaengige Nachbarn und gegen die
Buchformel S2/M2 = Springhub/Mittlerer Hub - 1. Schreibt nichts."""
import sys, os, re, json, csv, statistics, collections
sys.path.insert(0, 'py')
import xtide_modell as X, scheitelfit as S
from health_check import load_records, km
kopf = X.kopf_lesen(S.KOPFQUELLE); sp = kopf[1]
BUCH = {}
for vol in ('eutt2020', 'ectt2020', 'wctt2020', 'cptt2018'):
    for e in json.load(open(f'harmonics/help/{vol}_table2_full.json')):
        BUCH[(vol[:4], e['no'])] = e
def kommentare(pfad):
    L = open(pfad, encoding='iso-8859-1').read().split('\n'); out = {}
    for i in range(1, len(L) - 1):
        if X.__dict__.get('MERIDIAN_RE') is None and re.match(r'^[+-]?\d{1,2}:\d{2} :', L[i+1]) and not L[i].startswith('#'):
            j = i - 1; c = []
            while j >= 0 and L[j].startswith('#'): c.append(L[j]); j -= 1
            out[L[i]] = '\n'.join(c)
    return out
recs = load_records()
def s2m2(r):
    try:
        z0, w, e, mer = X.satz_lesen(r['file'], r['name'])
    except Exception: return None
    if 'M2' not in w or 'S2' not in w or w['M2'][0] < 0.05: return None
    return w['S2'][0] / w['M2'][0], w['M2'][0]
unabh = [r for r in recs if '/noaa/' not in r['file'] and 'current' not in r['file'].lower()
         and 'utide_tidetables' not in r['file'] and 'bsh_germany' not in r['file']]
zeilen = []
for datei in ('harmonics_noaa_eutt.txt', 'harmonics_noaa_amtt.txt', 'harmonics_noaa_cptt.txt'):
    pfad = 'harmonics/noaa/' + datei; kom = kommentare(pfad)
    for r in [r for r in recs if os.path.basename(r['file']) == datei]:
        c = kom.get(r['name'], '')
        m = re.search(r'noaa_uid: (\w+)-(\d+)', c); n = re.search(r'noaa_number: (\d+)', c)
        if 'Table 2 transfer' not in c: continue
        vol = m.group(1) if m else {'harmonics_noaa_eutt.txt': 'eutt', 'harmonics_noaa_cptt.txt': 'cptt'}.get(datei)
        no = int(m.group(2)) if m else (int(n.group(1)) if n else None)
        b = BUCH.get((vol, no))
        if not b or not b.get('mean_ft') or not b.get('spring_ft') or b.get('coltype') != 'MS': continue
        v = s2m2(r)
        if not v: continue
        buch = b['spring_ft'] / b['mean_ft'] - 1
        nb = []
        for q in unabh:
            if km(q, r) <= 5:
                w = s2m2(q)
                if w: nb.append(w[0])
        zeilen.append(dict(datei=datei, name=r['name'], no=no, satz=v[0], buch=buch, m2=v[1],
                           nachbar=statistics.median(nb) if nb else None, n_nb=len(nb)))
mit = [z for z in zeilen if z['nachbar'] is not None]
print(f'{len(zeilen)} MS-Uebertragungen mit Buchhub, davon {len(mit)} mit unabhaengigem Nachbarn <= 5 km')
for d in ('harmonics_noaa_eutt.txt', 'harmonics_noaa_amtt.txt', 'harmonics_noaa_cptt.txt'):
    zz = [z for z in mit if z['datei'] == d]
    if not zz: continue
    q_satz = [z['satz'] / z['nachbar'] for z in zz if z['nachbar'] > 0.05]
    q_buch = [z['buch'] / z['nachbar'] for z in zz if z['nachbar'] > 0.05]
    besser = sum(1 for z in zz if abs(z['buch'] - z['nachbar']) < abs(z['satz'] - z['nachbar']))
    print(f"  {d[14:18]}: n={len(zz):4d}  S2/M2 Satz/Nachbar Median {statistics.median(q_satz):.2f} "
          f"(unter 0.8: {sum(1 for x in q_satz if x < 0.8)}, ueber 1.25: {sum(1 for x in q_satz if x > 1.25)})  "
          f"Buchformel/Nachbar Median {statistics.median(q_buch):.2f}  Buchformel naeher: {besser}")
alle_q = [z['satz'] / z['buch'] for z in zeilen if z['buch'] > 0.05]
print(f"  Satz gegen Buchformel (alle {len(alle_q)}): Median {statistics.median(alle_q):.2f}, unter 0.8: {sum(1 for x in alle_q if x < 0.8)}")
with open('tmp_gesamtlauf/noaa_s2_studie.csv', 'w', newline='') as fh:
    w = csv.DictWriter(fh, fieldnames=list(zeilen[0].keys())); w.writeheader(); w.writerows(zeilen)
