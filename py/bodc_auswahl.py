"""BODC-Lieferung: Gruppen nach Abstandsregel mit bester-Satz-Vorrang auswaehlen, Phasen gegen Nachbarn (Oliver 21.10.2026).
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
    if g['r']['r2'] < 0.8 or g['r']['m2'] < 0.15: continue
    ng = min(osm_land.km(g['lat'], g['lon'], t['lat'], t['lon']) for t in PEG)
    g['offshore'] = ng > 30
    kand.append(g)
wahl = []
for g in sorted(kand, key=guete, reverse=True):
    dmin_b = min(osm_land.km(g['lat'], g['lon'], c['lat'], c['lon']) for c in CUR)
    dmin_n = min([osm_land.km(g['lat'], g['lon'], w['lat'], w['lon']) for w in wahl] or [1e9])
    a_b, a_n = (20, 40) if g['offshore'] else (3, 5)
    if dmin_b >= a_b and dmin_n >= a_n: wahl.append(g)
    elif dmin_b < a_b:
        c = min(CUR, key=lambda c: osm_land.km(g['lat'], g['lon'], c['lat'], c['lon']))
        L_ = open('/home/oliver/weather/' + c['file'], encoding='iso-8859-1').read().split('\n'); k = L_.index(c['name'])
        hs = next((int(l.split()[1]) for l in L_[k - 40:k] if 'hourly samples' in l), None)
        if hs and g['r']['n'] > 1.5 * hs:
            print('BESSER ALS BESTAND? %s n=%d gegen %s n=%d (%.1f km)' % (g['refs'][0], g['r']['n'], c['name'][:50], hs, dmin_b))
d = lambda x, y: (x - y + 180) % 360 - 180
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
