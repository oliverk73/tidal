"""BODC-Lieferung eintragen (Oliver 21.10.2026): Gruppen aus currents/BODC/_arbeit/<rn>_wahl.pkl (py/bodc_auswahl.py).
Bezugsort = naechster Pegel (Name vor Klammer/Komma), Land wie beim Pegel. Kurzreihen danach mit
py/stroemung_kopplung_lauf.py gekoppelt neu fitten."""
import sys, math, pickle, re
sys.path.insert(0, '/home/oliver/weather/py')
import cmems_stroemung_nachholen as C, osm_land, sicher_schreiben, health_check as hc
W = pickle.load(open('/home/oliver/weather/currents/BODC/_arbeit/%s_wahl.pkl' % sys.argv[1].lower() + '', 'rb'))
PEG = [t for t in hc.load_records() if not t['current'] and t['lat'] is not None and re.search(r'(Wales|England|Ireland|Scotland|Isle of Man)', t['name'])]
D = ['N','NNE','NE','ENE','E','ESE','SE','SSE','S','SSW','SW','WSW','W','WNW','NW','NNW']
def geo(a, b, c, d):
    y = math.sin(math.radians(d-b))*math.cos(math.radians(c)); x = math.cos(math.radians(a))*math.sin(math.radians(c))-math.sin(math.radians(a))*math.cos(math.radians(c))*math.cos(math.radians(d-b))
    return osm_land.km(a, b, c, d), D[int(((math.degrees(math.atan2(y, x))+360) % 360+11.25)//22.5) % 16]
OHNE = set(sys.argv[sys.argv.index('--ohne') + 1].split(',')) if '--ohne' in sys.argv else set()
neu, namen = [], set()
_f = '/home/oliver/weather/harmonics/utide/harmonics_utide_current_observations.txt'
_vorhanden = set(re.findall(r'BODC ?(\d+)', open(_f, encoding='iso-8859-1').read()))
for x in W:
    if x['refs'][0] in OHNE:
        continue
    if any(r in _vorhanden for r in x['refs']):      # schon im Bestand (auch aus einer anderen Lieferung)
        continue
    p = min(PEG, key=lambda t: osm_land.km(x['lat'], x['lon'], t['lat'], t['lon']))
    ort = re.split(r' \(|, ', p['name'])[0].replace(' Of ', ' of ').replace('-On-', '-on-')
    land = p['name'].split(', ', 1)[1] if ', ' in p['name'] else 'United Kingdom'
    land = re.sub(r'^[^,]*\), ', '', land)
    d, dr = geo(p['lat'], p['lon'], x['lat'], x['lon'])
    ref = x['refs'][0]
    name = '%s (%.0f km %s, %.0f m deep; BODC %s), %s Current' % (ort, d, dr, x['tiefe'], ref, land)
    if len(name) > 85:                                 # Tiefe steht auch im Kopf
        name = '%s (%.0f km %s; BODC %s), %s Current' % (ort, d, dr, ref, land)
    assert len(name) <= 85 and name not in namen, name
    namen.add(name)
    k = dict(code='BODC%s' % ref, inst=x['inst'][:60])
    b = C.block(k, x['r'], x['lat'], x['lon'], x['tiefe'])
    b = b.replace('# source: CMEMS in-situ, UTide analysis', '# source: BODC current meter, UTide analysis')
    b = b.replace('# Harmonic constants derived from CMEMS in-situ', '# Harmonic constants derived from BODC current meter')
    if x['n_eins'] > 1:
        b = b.replace('# (UTide', '# %d deployments combined, BODC refs %s\n# (UTide' % (x['n_eins'], ' '.join(x['refs'])), 1)
    b = b.replace('station_id_context: CMEMS-BODC', 'station_id_context: BODC-').replace('cmems_code:', 'bodc_ref:')
    country = 'Ireland' if land.startswith('Ireland') else 'United Kingdom'
    b = b.replace('\n%s Current\n' % k['code'], '\n%s\n' % name).replace('# BEGIN HOT COMMENTS\n', '# BEGIN HOT COMMENTS\n# country: %s\n' % country)
    assert '\n' + name + '\n' in b and max(len(l) for l in b.split('\n')) < 200
    neu.append(b); print('%2d r2=%.2f M2 %.2f %s' % (len(name), x['r']['r2'], x['r']['m2'], name))
f = '/home/oliver/weather/harmonics/utide/harmonics_utide_current_observations.txt'
if '--schreiben' in sys.argv:
    T = open(f, encoding='iso-8859-1').read().rstrip('\n'); sicher_schreiben.schreiben(f, T + '\n' + '\n'.join(neu) + '\n')
