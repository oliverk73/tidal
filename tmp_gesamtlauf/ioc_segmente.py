"""Monatsweise Konsistenz der Reihen hinter IOC-Fits: Sprung in Zeit, Pegel oder RMS."""
import sys, os, csv, statistics, datetime as dt, collections, numpy as np
sys.path.insert(0, 'py')
import messreihe_qualitaet as M, xtide_modell as X, scheitelfit as SF
from pegel_dubletten import vermerke
kopf = X.kopf_lesen(SF.KOPFQUELLE); namen, speeds, arg, fak = kopf
k = vermerke()
_, recs, anker = M.alle_anker(None)
aus = []
gesehen = set()
for r, pfad, fit, _b in anker:
    q = k.get((r['file'], r['line']), '')
    if 'IOC' not in q or 'utide_observations' not in r['file']:
        continue
    if (r['name'], pfad) in gesehen:
        continue
    gesehen.add((r['name'], pfad))
    try:
        z0, rw, e, mer = X.satz_lesen(r['file'], r['name'])
    except Exception:
        continue
    g = {c: (a, X.greenwich(kap, speeds[c], mer)) for c, (a, kap) in rw.items() if c in speeds}
    obs = M.lies(pfad)
    if len(obs) < 2000:
        continue
    t = np.array([x[0] for x in obs]); h = np.array([x[1] for x in obs])
    monat = np.array([dt.datetime.fromtimestamp(x, dt.timezone.utc).strftime('%Y-%m') for x in t])
    zeilen = []
    for mo in sorted(set(monat)):
        m = monat == mo
        if m.sum() < 150:
            continue
        best = None
        for v in range(-180, 181, 10):
            hv, _a, _b = SF.hoehe_und_ableitungen(t[m] + v * 60, z0, g, kopf)
            d = h[m] - hv
            rr = float(np.sqrt(np.mean((d - d.mean()) ** 2)))
            if best is None or rr < best[0]:
                best = (rr, v, float(d.mean()))
        zeilen.append((mo, int(m.sum()), best[1], best[0], best[2]))
    if len(zeilen) < 3:
        continue
    medv = statistics.median(z[2] for z in zeilen)
    medr = statistics.median(z[3] for z in zeilen)
    medp = statistics.median(z[4] for z in zeilen)
    schlecht = [z for z in zeilen if abs(z[2] - medv) >= 30 or abs(z[4] - medp) >= 0.30 or z[3] > 2.5 * medr]
    aus.append(dict(satz=r['name'], reihe=os.path.relpath(pfad, 'water_levels'), monate=len(zeilen),
                    schlecht=len(schlecht), versatz_median=medv, rms_median_cm=round(medr * 100, 1),
                    schlechte_monate='; '.join(f'{z[0]} dt{z[2]:+d} rms{z[3]*100:.0f} pegel{z[4]-medp:+.2f}' for z in schlecht[:8])))
    print(f"{r['name'][:36]:36} {len(zeilen):3d} Monate, auffaellig {len(schlecht):2d}, Median-Versatz {medv:+4.0f} min, RMS {medr*100:5.1f} cm", flush=True)
with open('tmp_gesamtlauf/ioc_segmente.csv', 'w', newline='', encoding='utf-8') as fh:
    w = csv.DictWriter(fh, fieldnames=list(aus[0].keys())); w.writeheader(); w.writerows(sorted(aus, key=lambda z: -z['schlecht']))
print('FERTIG', len(aus), 'IOC-Fits geprueft')
