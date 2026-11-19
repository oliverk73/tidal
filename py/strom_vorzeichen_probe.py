# Vorzeichenprobe 19.11.2026: Stromsatz gegen FES2014+TPXO10 inkl. Vorzeichen (pruefen-Skripte sind vorzeichenfrei).
# Ausgabe: (quelle, modelle_einig, vorzeichen) und die Saetze mit Vorzeichen -1 bei einigen Modellen.
import sys, os, re, cmath, math, collections
sys.path.insert(0, '/home/oliver/weather/py')
os.chdir('/home/oliver/weather')
import fes2014_strom as F, tpxo_strom as T, health_check as H, xtide_modell as X
_n, speeds, _a, _f = X.kopf_lesen('harmonics/utide/harmonics_fes2022.txt')
R = [r for r in H.load_records() if r['current'] and r['lat'] is not None and ('australia_oceancurrent' in r['file'] or 'current_observations' in r['file'])]
texte, saetze = {}, []
for r in R:
    p = r['file'] if r['file'].startswith('/') else os.path.join(T.ROOT, r['file'])
    if p not in texte: texte[p] = open(p, encoding='iso-8859-1').read().split('\n')
    L = texte[p]; i = L.index(r['name'])
    a = i
    while a > 0 and L[a-1].startswith('#'): a -= 1
    kopf = '\n'.join(L[a:i])
    m = re.findall(r'major_axis_deg_true: ([\d.]+)', kopf) or re.findall(r'Major axis: ([\d.]+)', kopf) or re.findall(r'flood_dir: (\d+)', kopf)
    if not m: continue
    _z0, w, _e, mer = X.satz_lesen(p, r['name'])
    s = {k: cmath.rect(w[k][0], -math.radians(X.greenwich(w[k][1], speeds[k], mer))) for k in T.KS if k in w and w[k][0] > 0}
    if 'M2' in s: saetze.append((r, float(m[-1]), s, 'gedreht' in kopf))
zl = F.zellen([(r['lat'], r['lon']) for r, *_ in saetze])
FF = F.stroeme(zl)
st = collections.Counter()
out = []
for n, ((r, ax, s, gd), z) in enumerate(zip(saetze, zl)):
    tz = T.wasserzelle(r['lat'], r['lon'])
    if z is None or tz is None or FF['M2'][n] is None: continue
    pf = {k: F.proj(FF[k][n], ax) for k in s}
    pt = T.projektion(tz[0], tz[1], ax, list(s))
    ef, vf = F.kurve(pf, s); et, vt = F.kurve(pt, s); ab, vab = F.kurve(pf, pt)
    src = 'AUS' if 'australia' in r['file'] else 'OBS'
    klar = ab < 25 and vab == 1 and vf == vt     # Modelle einig
    st[(src, klar, vf)] += 1
    if src == 'AUS' or (klar and vf == -1):
        out.append((src, vf, vt, round(ef), round(et), round(ab), gd, r['name'][:60], ax))
for k in sorted(st): print(k, st[k])
for o in sorted(out): print(o)
