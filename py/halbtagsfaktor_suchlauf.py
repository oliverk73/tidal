"""Suchlauf 5.11.2026: ATT-Uebertragungen, deren Tagestiden mit dem Halbtagsfaktor skaliert wurden.
Signatur: M2 passt zu FES (Faktor m), K1 und O1 weichen gemeinsam um einen anderen Faktor ab (k).
Zeuge: naechster eigenstaendiger Satz (keine ATT-Uebertragung, kein FES-Satz) bis 120 km.
Usage: venv/bin/python py/halbtagsfaktor_suchlauf.py harmonics/help/halbtagsfaktor_tagestiden_<datum>.csv
Urteil: reparieren (Zeuge bis 80 km bestaetigt FES, keiner den Satz), Satz bestaetigt, ohne Zeugen.
Reparatur danach per py/tagestiden_aus_fes.py --liste (Ausnahmen von Hand, siehe Commit 5.11.2026)."""
import sys, math, csv
sys.path.insert(0, '/home/oliver/weather/py')
import fes_kuestentyp as F
from health_check import load_records

recs = [r for r in load_records() if r['lat'] is not None and not r['current']]
for r in recs:
    r['uebertr'] = '/att/' in r['file'] and 'secondary' in r['file']
    r['fesatz'] = 'fes2022' in r['file']
kand = [r for r in recs if r['uebertr']]
zeugen = [r for r in recs if not r['uebertr'] and not r['fesatz'] and 'tidetables_roundtrip' not in r['file']]
F.fes_dazu(kand + zeugen)


def km(a, b):
    return math.hypot((a['lat'] - b['lat']) * 111, (a['lon'] - b['lon']) * 111 * math.cos(math.radians(a['lat'])))


def amp(r, c):
    v = r['z'].get(c)
    return abs(v) if v is not None else None


out = []
for r in kand:
    f = r['fes_rec']['z']
    a = {c: amp(r, c) for c in ('M2', 'K1', 'O1')}
    if None in a.values() or any(f.get(c) is None or abs(f[c]) < 0.01 for c in ('M2', 'K1', 'O1')):
        continue
    m = a['M2'] / abs(f['M2'])
    k1, o1 = a['K1'] / abs(f['K1']), a['O1'] / abs(f['O1'])
    if not (0.75 < m < 1.33):
        continue                                  # Halbtagestide selbst daneben -> anderer Fall
    if k1 <= 0 or o1 <= 0:
        continue
    k = math.sqrt(k1 * o1)
    if abs(math.log(k / m)) < math.log(1.5) or abs(k1 / o1 - 1) > 0.5:
        continue                                  # Tagestiden passen, oder K1/O1 nicht gemeinsam verschoben
    dk = a['K1'] + a['O1'] - (abs(f['K1']) + abs(f['O1'])) * m
    if abs(dk) < 0.03:
        continue
    z = sorted(((km(r, w), w) for w in zeugen), key=lambda x: x[0])
    z = [(d, w) for d, w in z if d < 120][:3]
    zeug, pro, contra = [], [], []
    for d, w in z:
        fw = w['fes_rec']['z']
        if fw.get('K1') is None or amp(w, 'K1') is None or amp(w, 'M2') is None or abs(fw['K1']) < 0.005 or amp(w, 'K1') <= 0:
            continue
        q = amp(w, 'K1') / abs(fw['K1'])
        zeug.append('%s %.0fkm K1 %.3f/FES %.3f' % (w['name'][:28], d, amp(w, 'K1'), abs(fw['K1'])))
        if d <= 80 and 0.8 <= q <= 1.25:
            pro.append(w['file'] + '|' + w['name'])
        if d <= 80 and abs(math.log(q / k1)) < math.log(1.25):
            contra.append(w['name'])
    urteil = 'reparieren' if pro and not contra else ('Satz bestaetigt' if contra else 'ohne Zeugen')
    out.append([r['file'].split('/')[-1], r['name'], f"{r['lat']:.3f}", f"{r['lon']:.3f}", f'{m:.2f}', f'{k1:.2f}', f'{o1:.2f}',
                f"{a['K1']:.3f}", f"{abs(f['K1']) * m:.3f}", f'{dk:+.3f}', f"{r['fes_wasser_km']:.1f}", F.typ(r), ' | '.join(zeug), urteil, ';'.join(pro)])

out.sort(key=lambda x: -abs(float(x[9])))
with open(sys.argv[1], 'w', newline='', encoding='utf-8') as fh:
    w = csv.writer(fh)
    w.writerow(['datei', 'name', 'lat', 'lon', 'm2_faktor', 'k1_faktor', 'o1_faktor', 'k1_satz', 'k1_fes_skaliert',
                'dk1o1_m', 'fes_wasser_km', 'typ', 'zeugen', 'urteil', 'referenzen'])
    w.writerows(out)
print(len(kand), 'Uebertragungen,', len(out), 'auffaellig')
import collections
print(collections.Counter(x[13] for x in out))
for x in out:
    if x[13] != 'reparieren': continue
    print('%-40s m %s k1 %s o1 %s  K1 %s->%s  d %s  %s %skm | %s' % (x[1][:40], x[4], x[5], x[6], x[7], x[8], x[9], x[11], x[10], x[12][:150]))
