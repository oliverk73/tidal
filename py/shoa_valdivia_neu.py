"""Valdivia (Rio Calle-Calle): SHOA-Tafelfit neu (Oliver 21.10.2026).

Der Satz in harmonics_utide_chile_shoa.txt war mit fester CONSTIT_67-Liste gefittet; in 3 Monaten explodieren
die Tagestiden (K1 12 h neben FES, FES-Fehler 56 %). Neu: UTide 'auto' wie batch_utide_shoa_chile, danach K2/P1
per py/kopplung_analytisch.py aus S2/K1 herausgerechnet. Ersetzt nur die Konstanten, Z0 und die R^2-Zeile.
"""
import sys, os, glob, re
sys.path.insert(0, '/home/oliver/weather/py'); sys.path.insert(0, '/home/oliver/weather/batch')
import numpy as np, utide
import batch_utide_shoa_chile as B
import kopplung_analytisch as A, stroemung_kopplung as K, xtide_modell as X, sicher_schreiben
from generate_germany_harmonics_175 import CONSTITUENTS_175, find_xtide_match
F = '/home/oliver/weather/harmonics/utide/harmonics_utide_chile_shoa.txt'
NAME = 'Valdivia (Río Calle-Calle), Chile'
ent = []
for f in sorted(glob.glob('/home/oliver/weather/tide_tables/chile/valdivia_rio_calle_calle/*.htm')):
    ent += B.parse_shoa_html(f)
ent = sorted({e[0]: e for e in ent}.values(), key=lambda e: e[0])
pts = sorted((B.local_to_utc(t), h) for t, h, _ in ent)
t, h = B.cosine_interpolate(pts)
coef = utide.solve(t, h, lat=-39.8, nodal=True, trend=False, method='ols', conf_int='none', verbose=False, constit='auto')
rec = utide.reconstruct(t, coef, verbose=False)['h']
r2 = 1 - np.sum((h - rec) ** 2) / np.sum((h - np.mean(h)) ** 2); rms = float(np.sqrt(np.mean((h - rec) ** 2)))
from utide._ut_constants import ut_constants
tab = ut_constants['const']; un = [x.strip() for x in tab.name]
konst = {}
for i, n in enumerate(coef['name']):
    n = n.strip()
    if n in un:
        xt, _ = find_xtide_match(n, tab.freq[un.index(n)] * 360)
        if xt: konst[xt] = (float(coef['A'][i]), float(coef['g'][i]) % 360)
la, lo = -39.8, -73.2
L = open(F, encoding='iso-8859-1').read().split('\n'); k = L.index(NAME)
la = float(next(re.search(r'# !latitude: (\S+)', l).group(1) for l in L[k - 30:k] if '!latitude' in l))
lo = float(next(re.search(r'# !longitude: (\S+)', l).group(1) for l in L[k - 30:k] if '!longitude' in l))
assert L[k + 1].startswith('+00:00'), L[k + 1]
rat, pn, km = K.verhaeltnisse(la, lo, 300)
neu = A.korrigiere(K.KOPF, konst, t[0].timestamp() if hasattr(t[0], 'timestamp') else A.unix(str(t[0])[:10]), (t[-1].timestamp() if hasattr(t[-1], 'timestamp') else A.unix(str(t[-1])[:10])), rat)
print(len(pts), 'HW/LW', t[0], t[-1], 'r2 %.4f rms %.3f' % (r2, rms), {x: (round(neu[x][0], 3), round(neu[x][1])) for x in ('M2', 'S2', 'K2', 'K1', 'P1', 'O1') if x in neu}, pn, '%.0f km' % km)
N175 = [n for n, _ in CONSTITUENTS_175]
for j, n in enumerate(N175):
    a = neu.get(n)
    L[k + 3 + j] = '%-15s %.4f  %.2f' % (n, a[0], a[1]) if a and a[0] >= 0.00005 else 'x 0 0'
z = L[k + 2].split(); L[k + 2] = '%.4f %s' % (float(np.mean(h)), z[1] if len(z) > 1 else 'meters')
j = k - 1
while L[j].startswith('#'):
    if L[j].startswith('# R^2'): L[j] = '# R^2 = %.4f, RMS error = %.4f m (refit 20261021: constit auto + K2/P1 coupled)' % (r2, rms)
    j -= 1
L.insert(k, '# note: 20261021 refit with UTide constit=auto (fixed 67-list blew up the diurnal band in 3 months); K2/P1 coupled via %s (%.0f km)' % (pn.split(',')[0][:30], km))
if '--schreiben' in sys.argv:
    sicher_schreiben.schreiben(F, '\n'.join(L))
