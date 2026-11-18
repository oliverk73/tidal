"""Gelöschte NOAA-Übertragungen mit korrigiertem S2 gegen die Reihen am Ort.

Je gelöschtem Satz: alle Reihen (Messung oder amtliche Tafel, wie in
messreihe_qualitaet) unter UMKREIS km. An jeder Reihe RMS ohne Versatz für
  - den gelöschten Satz wie er war,
  - denselben mit S2/K2 nach py/noaa_s2_nachziehen.py,
  - jeden heutigen Satz unter UMKREIS km vom gelöschten (der Überlebende).
Schreibt nichts in den Bestand. -> harmonics/help/noaa_geloescht_s2.csv
"""
import csv, json, os, re, sys, statistics, datetime as dt
import numpy as np
sys.path.insert(0, 'py')
import xtide_modell as X, scheitelfit as S, messreihe_qualitaet as M
import noaa_s2_nachziehen as N
from health_check import km, MERIDIAN

UMKREIS = 3.0
PUNKTE = 6000
kopf = X.kopf_lesen(S.KOPFQUELLE); sp = kopf[1]
B = N.buch()


def blocke_lesen(pfad):
    L = open(pfad, encoding='iso-8859-1').read().split('\n')
    out = []
    for i in range(1, len(L) - 2):
        if L[i].startswith('#') or not MERIDIAN.match(L[i + 1]):
            continue
        j = i - 1
        while j >= 0 and L[j].startswith('#'):
            j -= 1
        kom = '\n'.join(L[j + 1:i])
        mer = L[i + 1].split()[0]
        sg = -1 if mer.startswith('-') else 1
        hh, mm = mer.lstrip('+-').split(':')
        mer_h = sg * (int(hh) + int(mm) / 60)
        z0s = L[i + 2].split()
        einheit = z0s[1] if len(z0s) > 1 else 'meters'
        sk = 0.3048 if einheit.startswith('f') else 1.0
        w = {}
        k = i + 3
        while k < len(L) and L[k] and not L[k].startswith('#'):
            p = L[k].split()
            if p[0] != 'x' and len(p) >= 3 and p[0] in sp:
                w[p[0]] = (float(p[1]) * sk, float(p[2]))
            if k + 1 < len(L) and MERIDIAN.match(L[k + 1]):
                break
            k += 1
        la = re.search(r'!latitude: ([-\d.]+)', kom); lo = re.search(r'!longitude: ([-\d.]+)', kom)
        if not la or not lo:
            continue
        uid = re.search(r'noaa_uid: (\w+)-(\d+)', kom); num = re.search(r'noaa_number: (\d+)', kom)
        out.append(dict(name=L[i], kom=kom, z0=float(z0s[0]) * sk, w=w, mer=mer_h,
                        lat=float(la.group(1)), lon=float(lo.group(1)),
                        band=uid.group(1) if uid else None,
                        no=int(uid.group(2)) if uid else (int(num.group(1)) if num else None)))
    return out


def greenwich(w, mer):
    return {c: (a, X.greenwich(g, sp[c], mer)) for c, (a, g) in w.items()}


_reihe = {}
def reihe(pfad):
    if pfad not in _reihe:
        obs = M.lies(pfad)
        if len(obs) < 1500:
            _reihe[pfad] = None
        else:
            t = np.array([o[0] for o in obs]); h = np.array([o[1] for o in obs])
            m = t >= t[-1] - 365 * 86400
            t, h = t[m], h[m]
            if len(t) > PUNKTE:
                ix = np.linspace(0, len(t) - 1, PUNKTE).astype(int); t, h = t[ix], h[ix]
            _reihe[pfad] = (t, h, float(np.percentile(h, 99) - np.percentile(h, 1)))
    return _reihe[pfad]


def rms(t, h, z0, g, versatz_min=0):
    d = h - S.hoehe_und_ableitungen(t + versatz_min * 60, z0, g, kopf)[0]
    return float(np.sqrt(np.mean((d - d.mean()) ** 2)))


def versatz(t, h, z0, g):
    return min((rms(t, h, z0, g, v), v) for v in range(-180, 181, 15))[1]


_kopf, recs, anker = M.alle_anker(None)
reihen = {}
for r, pfad, fit, _b in anker:
    reihen.setdefault(pfad, (r['lat'], r['lon']))
r_pfade = list(reihen)
r_lat = np.array([reihen[p][0] for p in r_pfade]); r_lon = np.array([reihen[p][1] for p in r_pfade])
eigen = {(r['file'], r['name'], pfad) for r, pfad, fit, _b in anker}

geloescht = {(z['datei'], z['name']): z for z in csv.DictReader(open('tmp_gesamtlauf/noaa_geloescht.csv', encoding='utf-8'))}
zeilen = []
for datei in N.DATEIEN:
    for s in blocke_lesen(f'tmp_gesamtlauf/noaa_geloescht/{datei}'):
        info = geloescht.get((datei, s['name']), {})
        d = np.hypot((r_lat - s['lat']) * 111.2, (r_lon - s['lon']) * 111.2 * np.cos(np.radians(s['lat'])))
        nah = [r_pfade[i] for i in np.argsort(d)[:3] if d[i] <= UMKREIS]
        f = None
        band = s['band'] or datei[15:19]
        e = B.get((band, s['no']))
        if e and e.get('coltype') == 'MS' and e.get('mean_ft') and e.get('spring_ft') and e['spring_ft'] > e['mean_ft']:
            f = N.faktor(s['w'], sp, N.CAL * (e['spring_ft'] - e['mean_ft']) * N.FT)
        z = dict(datei=datei, name=s['name'], schluessel=info.get('schluessel', ''), geloescht_nach=info.get('letzter_commit', ''),
                 liste=info.get('liste', ''), art=info.get('art', ''), faktor='' if f is None else round(f, 2),
                 reihe='', reihe_km='', hub_m='', noaa_alt_cm='', noaa_s2_cm='', noaa_s2_versatz_min='',
                 bester_heute='', bester_datei='', bester_cm='', bester_eigen='', vorschlag='')
        if not nah:
            z['vorschlag'] = 'kein Massstab (keine Reihe unter 3 km)'
            zeilen.append(z); continue
        pfad = nah[0]; rr = reihe(pfad)
        if rr is None:
            z['vorschlag'] = 'kein Massstab (Reihe zu kurz)'
            zeilen.append(z); continue
        t, h, hub = rr
        g = greenwich(s['w'], s['mer'])
        a = rms(t, h, s['z0'], g)
        g2 = {c: ((x * f if (f and c in ('S2', 'K2')) else x), p) for c, (x, p) in g.items()}
        b = rms(t, h, s['z0'], g2)
        v = versatz(t, h, s['z0'], g2)
        best = None
        for q in recs:
            if abs(q['lat'] - s['lat']) > 0.05 or km(q, s) > UMKREIS or 'current' in q['file'].lower():
                continue
            try:
                qz0, qw, qe, qm = X.satz_lesen(q['file'], q['name'])
            except (KeyError, IndexError, ValueError):
                continue
            qs = 0.3048 if qe.startswith('f') else 1.0
            qg = {c: (x * qs, X.greenwich(p, sp[c], qm)) for c, (x, p) in qw.items() if c in sp}
            qr = rms(t, h, qz0 * qs, qg)
            if best is None or qr < best[0]:
                best = (qr, q)
        z.update(reihe=os.path.relpath(pfad, 'water_levels'), reihe_km=round(float(d[r_pfade.index(pfad)]), 2),
                 hub_m=round(hub, 2), noaa_alt_cm=round(a * 100, 1), noaa_s2_cm=round(b * 100, 1), noaa_s2_versatz_min=v)
        if best:
            q = best[1]
            z.update(bester_heute=q['name'], bester_datei=os.path.basename(q['file']), bester_cm=round(best[0] * 100, 1),
                     bester_eigen='ja' if (q['file'], q['name'], pfad) in eigen else '')
        if abs(v) >= 30:
            z['vorschlag'] = 'weg lassen (Zeitfehler)'
        elif not best:
            z['vorschlag'] = 'zurueckholen? (kein heutiger Satz am Ort)'
        elif b * 100 <= best[0] * 100 - 1.0:
            z['vorschlag'] = 'zurueckholen (besser als heutiger Satz)'
        elif b * 100 <= best[0] * 100 + 1.0:
            z['vorschlag'] = 'gleichauf (heutiger Satz genuegt)'
        else:
            z['vorschlag'] = 'weg lassen (heutiger Satz besser)'
        zeilen.append(z)
        if len(zeilen) % 50 == 0:
            print(len(zeilen), flush=True)
with open('harmonics/help/noaa_geloescht_s2.csv', 'w', newline='', encoding='utf-8') as fh:
    wr = csv.DictWriter(fh, fieldnames=list(zeilen[0].keys())); wr.writeheader(); wr.writerows(zeilen)
import collections
print(len(zeilen), collections.Counter(z['vorschlag'] for z in zeilen))
