"""NOAA-Uebertragungen aus Lisboa gegen unabhaengige Nachbarn (Puertos, TICON, uTide, IHM ...)."""
import sys, os, re, statistics, csv, numpy as np
sys.path.insert(0, 'py')
import xtide_modell as X, scheitelfit as S
from noaa_s2_nachziehen import kommentare
from health_check import load_records, km
kopf = X.kopf_lesen(S.KOPFQUELLE); sp = kopf[1]
recs = load_records()
kom = kommentare('harmonics/noaa/harmonics_noaa_eutt.txt')
unabh = [r for r in recs if '/noaa/' not in r['file'] and 'current' not in r['file'].lower()]
T = np.arange(1767225600, 1767225600 + 60 * 86400, 600.)
_c = {}
def kurve(r):
    k = (r['file'], r['name'])
    if k not in _c:
        z0, w, e, mer = X.satz_lesen(r['file'], r['name']); sk = 0.3048 if e.startswith('f') else 1
        g = {c: (a * sk, X.greenwich(p, sp[c], mer)) for c, (a, p) in w.items() if c in sp}
        h = S.hoehe_und_ableitungen(T, z0 * sk, g, kopf)[0]
        _c[k] = (g, h - h.mean())
    return _c[k]
def vergleich(a, b):
    ga, ha = kurve(a); gb, hb = kurve(b)
    dm2 = ((ga['M2'][1] - gb['M2'][1] + 180) % 360 - 180) / sp['M2'] * 60
    return float(np.sqrt(np.mean((ha - hb) ** 2))), dm2, ga['M2'][0] / gb['M2'][0], float(np.ptp(hb))
zeilen = []
for r in recs:
    if not r['file'].endswith('harmonics_noaa_eutt.txt') or 'transfer from Lisboa' not in kom.get(r['name'], ''):
        continue
    if r['lat'] < 41.8:
        continue
    nb = sorted([q for q in unabh if km(q, r) <= 15], key=lambda q: km(q, r))
    if not nb:
        zeilen.append(dict(name=r['name'], lat=r['lat'], lon=r['lon'], naechster='', km='', kurve_cm='', m2_min='', m2_amp='',
                           konsens_kurve_cm='', konsens_m2_min='', konsens_m2_amp='', grundrauschen_cm='', n=0, urteil='keine Nachbarn <=15 km'))
        continue
    v = [(q, *vergleich(r, q)) for q in nb]
    q0 = v[0]
    # Grundrauschen: unabhaengige Nachbarn untereinander (erste gegen die anderen, <=15 km)
    rausch = [vergleich(nb[0], q)[0] for q in nb[1:6]]
    kk = statistics.median(x[1] for x in v); km2 = statistics.median(x[2] for x in v); ka = statistics.median(x[3] for x in v)
    gr = statistics.median(rausch) if rausch else None
    hub = q0[4]
    if gr is not None and kk > max(2.5 * gr, 0.04 * hub):
        urteil = 'weicht ab'
    elif gr is None and q0[1] > 0.05 * hub:
        urteil = 'weicht ab (nur ein Nachbar)'
    else:
        urteil = 'passt'
    zeilen.append(dict(name=r['name'], lat=round(r['lat'], 4), lon=round(r['lon'], 4), naechster=f"{q0[0]['name']} [{os.path.basename(q0[0]['file'])}]",
                       km=round(km(q0[0], r), 1), kurve_cm=round(q0[1] * 100, 1), m2_min=round(q0[2]), m2_amp=round(q0[3], 2),
                       konsens_kurve_cm=round(kk * 100, 1), konsens_m2_min=round(km2), konsens_m2_amp=round(ka, 2),
                       grundrauschen_cm='' if gr is None else round(gr * 100, 1), n=len(nb), urteil=urteil))
for z in zeilen:
    print(f"{z['name'][:40]:40} {z['lat']:7} n={z['n']:2} naechster {str(z['km']):>4} km Kurve {str(z['kurve_cm']):>5} M2 {str(z['m2_min']):>4} min x{z['m2_amp']} | Konsens {z['konsens_kurve_cm']} cm, M2 {z['konsens_m2_min']} min x{z['konsens_m2_amp']} | Rauschen {z['grundrauschen_cm']} -> {z['urteil']}")
with open('harmonics/help/noaa_lisboa_nord.csv', 'w', newline='', encoding='utf-8') as fh:
    w = csv.DictWriter(fh, fieldnames=list(zeilen[0].keys())); w.writeheader(); w.writerows(zeilen)
