import sys, os, csv, statistics, numpy as np
sys.path.insert(0, 'py')
import xtide_modell as X, scheitelfit as S, messreihe_qualitaet as M
kopf = X.kopf_lesen(S.KOPFQUELLE); sp = kopf[1]
studie = {(z['datei'], z['name']): z for z in csv.DictReader(open('tmp_gesamtlauf/noaa_s2_studie.csv'))}
import glob
kand = []
for q in ('messreihe_qualitaet_alle.csv', 'bodc_qualitaet.csv', 'ea_qualitaet.csv'):
    for zz in csv.DictReader(open('harmonics/help/' + q, encoding='utf-8')):
        if (zz['datei'], zz['satz']) in studie and zz['rms_m'] and float(zz['abstand_m'] or 9e9) <= 3000:
            kand.append(zz)
kand.sort(key=lambda zz: float(zz['abstand_m']))
gesehen = set(); erg = []
for zz in kand:
    key = (zz['datei'], zz['satz'])
    if key in gesehen: continue
    pfad = os.path.join('water_levels', zz['reihe'], zz['station'])
    if not os.path.exists(pfad):
        t_ = glob.glob(os.path.join('water_levels', zz['reihe'], '*', zz['station']))
        if len(t_) != 1: continue
        pfad = t_[0]
    gesehen.add(key)
    r = {'file': 'harmonics/noaa/' + key[0], 'name': key[1]}
    z = studie[key]; f = float(z['buch']) / float(z['satz'])
    f = min(max(f, 0.5), 3.0)
    z0, w, e, mer = X.satz_lesen(r['file'], r['name']); sk = 0.3048 if e.startswith('f') else 1
    g = {c: (a*sk, X.greenwich(k, sp[c], mer)) for c, (a, k) in w.items() if c in sp}
    g2 = {c: ((a*f if c in ('S2', 'K2') else a), p) for c, (a, p) in g.items()}
    obs = M.lies(pfad)
    if len(obs) < 3000: continue
    t = np.array([o[0] for o in obs])[-35000:]; h = np.array([o[1] for o in obs])[-35000:]
    def rms(gg):
        d = h - S.hoehe_und_ableitungen(t, z0*sk, gg, kopf)[0]; return float(np.sqrt(np.mean((d-d.mean())**2)))
    a, b = rms(g), rms(g2)
    erg.append((key, f, a, b))
    print(f"{r['name'][:40]:40} {key[0][14:18]} Faktor {f:4.2f}  {a*100:5.1f} -> {b*100:5.1f} cm", flush=True)
    if len(erg) >= 80: break
print(f"n={len(erg)}  besser {sum(1 for e in erg if e[3] < e[2]-0.002)}  schlechter {sum(1 for e in erg if e[3] > e[2]+0.002)}  "
      f"Median {statistics.median(e[2] for e in erg)*100:.1f} -> {statistics.median(e[3] for e in erg)*100:.1f} cm")
