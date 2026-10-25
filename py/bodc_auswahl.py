"""BODC-Lieferung: Gruppen auswaehlen (Dubletten nach Aehnlichkeit, bester Satz zuerst), Phasen gegen Nachbarn (Oliver 21./25.10.2026).
Usage: venv/bin/python py/bodc_auswahl.py RN-xxxx [AUSSCHLUSS-REF ...]"""
import sys, pickle, warnings; warnings.filterwarnings('ignore'); sys.path.insert(0, '/home/oliver/weather/py')
import health_check as hc, osm_land, xtide_modell as X, bodc_stroemung as B
M = B.metadaten()
G = pickle.load(open('/home/oliver/weather/currents/BODC/_arbeit/%s.pkl' % sys.argv[1].lower() + '', 'rb'))
ALL = hc.load_records(); CUR = [c for c in ALL if c['current'] and c['lat'] is not None]; PEG = [t for t in ALL if not t['current'] and t['lat'] is not None]
F = '/home/oliver/weather/harmonics/utide/harmonics_utide_current_observations.txt'
AUS = {'19417', '19429', '19442', '19466'} | set(sys.argv[2:])   # MAFF Irische See Nov. 1969: Uhr
def guete(g): return (g['r']['n'], g['r']['r2'])
kand = []
for g in G:
    if g['refs'][0] in AUS or any(r in AUS for r in g['refs']): continue
    ng = min(osm_land.km(g['lat'], g['lon'], t['lat'], t['lon']) for t in PEG)
    g['offshore'] = ng > 30
    if g['r']['r2'] < (0.8 if g['offshore'] else 0.6) or g['r']['m2'] < 0.15: continue   # Kueste 0,6 / See 0,8
    kand.append(g)
# Stationen dieser Lieferung, die schon im Bestand sind, werden nicht neu gewaehlt
REFS = {r for r, m in M.items() if m['_dir'].endswith(sys.argv[1])}
import re as _re
_txt = open(F, encoding='iso-8859-1').read()
_eigen = set(_re.findall(r'BODC (\d+)\), [^\n]*Current', _txt)) & REFS
CUR_ALT = [c for c in CUR if not any('BODC %s)' % r in c['name'] for r in _eigen)]
CUR_EIGEN = [c for c in CUR if c not in CUR_ALT]
wahl = [dict(lat=c['lat'], lon=c['lon'], _bestand=True) for c in CUR_EIGEN]
# Auswahl nach Aehnlichkeit statt festem Abstand (Oliver 25.10.2026: "Wenn eine Meerenge, ein Fjord
# oder ein Kanal schmaler ist als 3 km, dann kann die Station doch gar nicht mehr Abstand haben?").
# Dublette = bis 2 km neben einem Strom aus Bestand oder Auswahl UND praktisch gleiche Stroemung
# (M2-Betrag +-15 %, Phase < 15 Grad modulo 180). Sonst wird der Satz genommen.
_m2 = {}
def m2_bestand(c):
    if c['name'] not in _m2:
        try:
            z, w, e, mm = X.satz_lesen('/home/oliver/weather/' + c['file'], c['name'])
            sp = X.kopf_lesen('/home/oliver/weather/' + c['file'])[1]
            _m2[c['name']] = (w['M2'][0] * (0.3048 if e.startswith('f') else 1), X.greenwich(w['M2'][1], sp['M2'], mm) % 360)
        except Exception:
            _m2[c['name']] = None
    return _m2[c['name']]
def gleich(a, b):
    dg = abs((a[1] - b[1] + 180) % 360 - 180); dg = min(dg, 180 - dg)
    return min(a[0], b[0]) / max(a[0], b[0]) > 0.85 and dg < 15
for g in sorted(kand, key=guete, reverse=True):
    m = tuple(g['r']['konst']['M2'])
    nah_b = [c for c in CUR if osm_land.km(g['lat'], g['lon'], c['lat'], c['lon']) < 2 and m2_bestand(c) and gleich(m, m2_bestand(c))]
    nah_w = [w for w in wahl if not w.get('_bestand') and osm_land.km(g['lat'], g['lon'], w['lat'], w['lon']) < 2 and gleich(m, tuple(w['r']['konst']['M2']))]
    if not nah_b and not nah_w:
        wahl.append(g)
    elif nah_b:
        c = nah_b[0]
        L_ = open('/home/oliver/weather/' + c['file'], encoding='iso-8859-1').read().split('\n'); k = L_.index(c['name'])
        hs = next((int(l.split()[1]) for l in L_[k - 40:k] if 'hourly samples' in l), None)
        if hs and g['r']['n'] > 1.5 * hs:
            print('BESSER ALS BESTAND? %s n=%d gegen %s n=%d' % (g['refs'][0], g['r']['n'], c['name'][:50], hs))
d = lambda x, y: (x - y + 180) % 360 - 180
wahl = [g for g in wahl if not g.get('_bestand')]
for g in wahl:
    m2 = g['r']['konst']['M2']; org = M[g['refs'][0]]['Organisation'][:18]
    nb = sorted(CUR, key=lambda c: osm_land.km(g['lat'], g['lon'], c['lat'], c['lon']))[:2]
    s = []
    for c in nb:
        try: z, w, e, mm = X.satz_lesen(F, c['name'])
        except KeyError: continue
        dm = d(m2[1], w['M2'][1]); dm = d(dm, 180) if abs(dm) > 90 else dm
        s.append('%.0fkm %s %+.0f' % (osm_land.km(g['lat'], g['lon'], c['lat'], c['lon']), c['name'].split(' (')[0][:14], dm))
    print('%-8s %-18s %d %s %.3f %.3f n=%4d r2 %.2f M2 %.2f@%.0f | %s' % (g['refs'][0], org, g['r']['t0'].year, 'off' if g['offshore'] else 'kst', g['lat'], g['lon'], g['r']['n'], g['r']['r2'], *m2, ' ; '.join(s)))
pickle.dump(wahl, open('/home/oliver/weather/currents/BODC/_arbeit/%s_wahl.pkl' % sys.argv[1].lower() + '', 'wb'))
print(len(wahl), 'von', len(kand))
