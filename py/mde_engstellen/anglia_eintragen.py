import sys, math, pickle, warnings; warnings.filterwarnings('ignore')
S = '/home/oliver/weather/currents/UK_MDE/_arbeit/'
sys.path.insert(0, '/home/oliver/weather/py'); sys.path.insert(0, '/home/oliver/weather/py')
import stroemung_kurzfit as K, cmems_stroemung_nachholen as C, osm_land, sicher_schreiben, health_check as hc
T = [t for t in hc.load_records() if not t['current'] and t['lat'] is not None]
def gauge(p): return [x for x in T if x['name'].startswith(p)][0]
D = ['N','NNE','NE','ENE','E','ESE','SE','SSE','S','SSW','SW','WSW','W','WNW','NW','NNW']
def geo(a, b, c, d):
    y = math.sin(math.radians(d-b))*math.cos(math.radians(c)); x = math.cos(math.radians(a))*math.sin(math.radians(c))-math.sin(math.radians(a))*math.cos(math.radians(c))*math.cos(math.radians(d-b))
    return osm_land.km(a, b, c, d), D[int(((math.degrees(math.atan2(y, x))+360) % 360+11.25)//22.5) % 16]
A = pickle.load(open(S + 'mde2/anglia.pkl', 'rb'))
ORT = {'BM1': ('Hunstanton', 'Hunstanton, England'), 'BM2': ('Blakeney', 'Blakeney, England'), 'BM4': ('Felixstowe', 'Felixstowe, England'),
       'BM5': ('Walton-on-the-Naze', 'Walton-on-the-Naze, England'), 'BM6': ('Clacton-on-Sea', 'Clacton-On-Sea, England'),
       'BM7': ('West Mersea', 'West Mersea, England'), 'BM8': ('Burnham-on-Crouch', 'Burnham-On-Crouch, England'), 'BM9': ('Southend-on-Sea', 'Southend-on-Sea (Pier)')}
neu = []
for site, x in A.items():
    ort, gp = ORT[site[:3]]; g = gauge(gp)
    df = x['df']
    if len(df) < 600:
        r = K.fit(df, K.pegel_verhaeltnisse('/home/oliver/weather/' + g['file'], g['name'])); kurz = True
    else:
        r = C.analyse(df, x['lat'], 'auto'); kurz = False
    d, dr = geo(g['lat'], g['lon'], x['lat'], x['lon'])
    name = '%s (%.0f km %s, depth mean; MDE TCE-3952), England, United Kingdom Current' % (ort, d, dr)
    if len(name) > 85:
        name = name.replace(', depth mean;', ';')
    assert len(name) <= 85, name
    k = dict(code='TCE3952', inst='Partrac / Anglian Water Services')
    b = C.block(k, r, x['lat'], x['lon'], float('nan'))
    inst = 'Nortek %s, depth average' % x['instr']
    b = b.replace('# Harmonic constants derived from CMEMS in-situ', '# Harmonic constants derived from Marine Data Exchange (The Crown Estate) TCE-3952, %s, %s' % (site, inst)
                  + ('\n# short series (%d days): N2, K2, P1 inferred from %s (ratio and phase lag of tide gauge), own least squares (XTide model)' % (round(r['n'] / 24), g['name']) if kurz else '')
                  + ('\n# position: metadata longitude 001 deg E read as 000 deg E (site named after this estuary)' if site[:3] in ('BM7', 'BM8', 'BM9') else '')
                  + '\n# time check: instrument pressure M2 within 10 min of nearby tide gauges')
    if kurz:
        b = b.replace('# (UTide v0.3.1, principal-axis projection)', '# (principal-axis projection)').replace('# confidence: 8', '# confidence: 6')
    b = b.replace('# source: CMEMS in-situ, UTide analysis', '# source: Marine Data Exchange TCE-3952 (%s), %s' % (site, 'short-series analysis with inference' if kurz else 'UTide analysis'))
    b = b.replace('station_id_context: CMEMS-TCE3952', 'station_id_context: MDE-TCE-3952').replace('# cmems_code: TCE3952', '# mde_id: TCE-3952')
    b = b.replace('\nTCE3952 Current\n', '\n%s\n' % name).replace('# BEGIN HOT COMMENTS\n', '# BEGIN HOT COMMENTS\n# country: United Kingdom\n')
    assert '\n' + name + '\n' in b and max(len(l) for l in b.split('\n')) < 200
    neu.append(b); print('%2d n=%d r2 %.2f M2 %.2f@%.0f %s' % (len(name), r['n'], r['r2'], *r['konst']['M2'], name))
f = '/home/oliver/weather/harmonics/utide/harmonics_utide_current_observations.txt'
if '--schreiben' in sys.argv:
    T0 = open(f, encoding='iso-8859-1').read().rstrip('\n'); sicher_schreiben.schreiben(f, T0 + '\n' + '\n'.join(neu) + '\n')
