"""Flutrichtung ueber die Laufrichtung der Tidenwelle: FES-Phase vor (in Flutrichtung) minus hinter dem Punkt.

Zweite Probe fuer Saetze, bei denen py/flutrichtung_pruefen.py "unklar" sagt (Meerengen zwischen zwei
Becken, wo der Phasenabstand Strom-Wasserstand nichts entscheidet). Flut = Richtung zur spaeteren M2-Phase,
abgetastet 8 und 15 km vor und hinter dem Punkt entlang der Hauptachse.
Geeicht 26.10.2026 an den Saetzen mit sicherem Phasenurteil: Japan ab 5 Grad Gefaelle 56/56, weltweit nur
~90 % (Fluesse, Buchten mit Knoten) -> ausserhalb Japans nur als Hinweis.

Usage: venv/bin/python py/flutrichtung_welle.py [japan]   (liest harmonics/help/flutrichtung_<heute>.csv)
       venv/bin/python py/flutrichtung_welle.py eichung
"""
import sys, os, csv, re, math, collections
import numpy as np, netCDF4 as nc
sys.path.insert(0, 'py')
from fes_ersatz_inseln import sample, FES_DIR
fes = {k: nc.Dataset(os.path.join(FES_DIR, '%s_fes2022.nc' % k.lower())) for k in ('M2', 'K1')}
def achsen():
    A = {}
    for f in ('harmonics/utide/harmonics_utide_current_tables.txt', 'harmonics/utide/harmonics_utide_current_observations.txt'):
        L = open(f, encoding='iso-8859-1').read().split('\n'); ax = None
        for l in L:
            m = re.match(r'# major_axis_deg_true: ([-\d.]+)', l)
            if m: ax = float(m.group(1))
            elif l and not l.startswith('#') and ax is not None and l.endswith('Current'):
                A[l] = ax; ax = None
    return A
def punkt(lat, lon, az, d):
    return lat + d / 111.2 * math.cos(math.radians(az)), lon + d / (111.2 * math.cos(math.radians(lat))) * math.sin(math.radians(az))
def welle(lat, lon, az, k):
    out = []
    for d in (8, 15):
        a = sample(fes[k], *punkt(lat, lon, az, d))[1]; b = sample(fes[k], *punkt(lat, lon, az + 180, d))[1]
        out.append(None if a is None or b is None else (a - b + 180) % 360 - 180)
    return out
def urteil(w):
    if None in w: return 'kein FES'
    if all(x > 3 for x in w): return 'richtig'
    if all(x < -3 for x in w): return 'drehen'
    return 'unklar'
if __name__ == '__main__' and sys.argv[1:] != ['eichung']:
    A = achsen()
    Z = list(csv.DictReader(open('harmonics/help/flutrichtung_%s.csv' % __import__('datetime').date.today().strftime('%Y%m%d'))))
    nur = sys.argv[1] if len(sys.argv) > 1 else None
    tab = collections.Counter()
    for z in Z:
        if z['name'] not in A: continue
        if nur == 'japan' and 'Japan' not in z['name']: continue
        w = welle(float(z['lat']), float(z['lon']), A[z['name']], z['konst'])
        u = urteil(w)
        tab[(z['urteil'], u)] += 1
        if z['urteil'] == 'unklar' and 'Japan' in z['name']:
            print('%-62s Achse %5.1f  Welle %s -> %s' % (z['name'][:62], A[z['name']], w, u))
    print(sorted(tab.items()))

def eichung():
    A = achsen(); Z = list(csv.DictReader(open('harmonics/help/flutrichtung_%s.csv' % __import__('datetime').date.today().strftime('%Y%m%d'))))
    R = []
    for z in Z:
        if z['name'] in A and z['urteil'] == 'richtig':
            w = welle(float(z['lat']), float(z['lon']), A[z['name']], z['konst'])
            if None not in w: R.append(('Japan' in z['name'], min(w, key=abs), w))
    for gr in (3, 5, 8, 12):
        for jp in (True, False):
            S = [r for r in R if r[0] == jp and all(abs(x) > gr for x in r[2]) and (r[2][0] > 0) == (r[2][1] > 0)]
            ok = sum(1 for r in S if r[2][0] > 0)
            print('  Gefaelle > %2d Grad  %-6s  %3d eindeutig, %3d stimmen (%.0f %%)' % (gr, 'Japan' if jp else 'Welt', len(S), ok, 100 * ok / max(1, len(S))))
eichung()
