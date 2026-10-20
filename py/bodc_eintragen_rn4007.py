import sys, os, math, pickle
sys.path.insert(0, '/home/oliver/weather/py')
import cmems_stroemung_nachholen as C, osm_land, sicher_schreiben, health_check as hc
S = '/home/oliver/weather/currents/BODC/_arbeit/'
G = {g['refs'][0]: g for rn in ('rn-3866', 'rn-4007') for g in pickle.load(open(S + rn + '.pkl', 'rb'))}
D = ['N','NNE','NE','ENE','E','ESE','SE','SSE','S','SSW','SW','WSW','W','WNW','NW','NNW']
def geo(a, b, c, d):
    y = math.sin(math.radians(d-b))*math.cos(math.radians(c)); x = math.cos(math.radians(a))*math.sin(math.radians(c))-math.sin(math.radians(a))*math.cos(math.radians(c))*math.cos(math.radians(d-b))
    return osm_land.km(a, b, c, d), D[int(((math.degrees(math.atan2(y, x))+360) % 360+11.25)//22.5) % 16]
R = [x for x in hc.load_records() if not x['current']]
def pos(p):
    r = [x for x in R if x['name'].startswith(p)]; assert len(r) == 1, (p, len(r)); return r[0]['lat'], r[0]['lon']
E_, F_ = ('England, United Kingdom', 'United Kingdom'), ('France', 'France')
L = [('14241', 'Deal', pos('Deal,'), E_), ('16002', 'Dover', pos('Dover,'), E_), ('14253', 'Calais', pos('Calais,'), F_),
     ('28408', 'Île-de-Batz', pos('Île-de-Batz'), F_), ('28144', "St Mary's", pos("St. Mary's (Isles of Scilly)"), E_),
     ('28040', 'Lizard Point', pos('Lizard Point,'), E_), ('28200', 'Lizard Point', pos('Lizard Point,'), E_),
     ('28390', 'Lizard Point', pos('Lizard Point,'), E_), ('27927', 'Plymouth', (50.3684, -4.1852), E_),
     ('22683', 'Start Point', pos('Start Point,'), E_), ('15453', 'Cape Cornwall', pos('Cape Cornwall,'), E_),
     ('6369', 'Freshwater Bay', pos('Freshwater Bay (Isle of Wight)'), E_), ('22818', 'Nab Tower', pos('Nab Tower,'), E_),
     ('14566', 'Cape Cornwall', pos('Cape Cornwall,'), E_), ('21422', 'Lundy', pos('Lundy,'), E_),
     ('48169', 'Minehead', pos('Minehead,'), E_), ('21575', 'Ilfracombe', pos('Ilfracombe,'), E_)]
neu = []
for ref, ort, o, (land, country) in L:
    x = G[ref]; r = x['r']
    d, dr = geo(*o, x['lat'], x['lon'])
    name = '%s (%.0f km %s, %.0f m deep; BODC %s), %s Current' % (ort, d, dr, x['tiefe'], ref, land)
    assert len(name) <= 85, (len(name), name)
    k = dict(code='BODC%s' % ref, inst=x['inst'][:60])
    b = C.block(k, r, x['lat'], x['lon'], x['tiefe'])
    b = b.replace('# source: CMEMS in-situ, UTide analysis', '# source: BODC current meter, UTide analysis')
    b = b.replace('# Harmonic constants derived from CMEMS in-situ', '# Harmonic constants derived from BODC current meter')
    if x['n_eins'] > 1:
        b = b.replace('# (UTide', '# %d deployments combined, BODC refs %s\n# (UTide' % (x['n_eins'], ' '.join(x['refs'])), 1)
    b = b.replace('# (UTide', '# time check: M2 phase within 15 min of the Shom tidal stream atlas\n# (UTide', 1) if ref not in ('28144', '28200', '15453', '14566', '21422', '48169', '21575') else b
    b = b.replace('station_id_context: CMEMS-BODC', 'station_id_context: BODC-').replace('cmems_code:', 'bodc_ref:')
    b = b.replace('\n%s Current\n' % k['code'], '\n%s\n' % name).replace('# BEGIN HOT COMMENTS\n', '# BEGIN HOT COMMENTS\n# country: %s\n' % country)
    assert '\n' + name + '\n' in b and max(len(l) for l in b.split('\n')) < 200
    neu.append(b); print('%2d r2=%.2f M2 %.2f %s' % (len(name), r['r2'], r['m2'], name))
f = '/home/oliver/weather/harmonics/utide/harmonics_utide_current_observations.txt'
T = open(f, encoding='iso-8859-1').read().rstrip('\n')
if '--schreiben' in sys.argv:
    sicher_schreiben.schreiben(f, T + '\n' + '\n'.join(neu) + '\n')
