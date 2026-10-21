"""RN-3449 Kurzreihen (Oliver 21.10.2026): DAFS 11808 + 11857 (Maerz/August 1969, 33 m) vor Aberdeen,
gekoppelt gefittet (K2->S2, P1->K1 vom naechsten Pegel). Uebrige Kurzreihen verworfen (Uhr Okt. 1968,
MAFF 1968/69, Abstand zum Bestand, tiefere Ebene) -- siehe Commit."""
import sys, os, math
sys.path.insert(0, '/home/oliver/weather/py')
import pandas as pd
import bodc_stroemung as B, cmems_stroemung_nachholen as C, stroemung_kopplung as K, osm_land, sicher_schreiben, health_check as hc
M = B.metadaten()
REFS = ['11808', '11857']
dfs = [B.reihe(os.path.join(M[r]['_dir'], 'b%07d.qxf' % int(r)), float(M[r]['Sea floor depth (m)'] or 'nan'))[0] for r in REFS]
df = pd.concat(dfs).sort_index(); df = df[~df.index.duplicated()]
la = sum(float(M[r]['Latitude A']) for r in REFS) / 2; lo = sum(float(M[r]['Longitude A']) for r in REFS) / 2
frei = list(C.analyse(df, la, 'auto')['konst'])
rat, pn, km = K.verhaeltnisse(la, lo)
r = K.fit(df, frei, {b: (h, rat[b][0], rat[b][1]) for h, b in [('S2', 'K2'), ('K1', 'P1')]})
D = ['N','NNE','NE','ENE','E','ESE','SE','SSE','S','SSW','SW','WSW','W','WNW','NW','NNW']
g = [x for x in hc.load_records() if not x['current'] and x['name'].startswith('Aberdeen, Scotland')][0]
y = math.sin(math.radians(lo - g['lon'])) * math.cos(math.radians(la)); x = math.cos(math.radians(g['lat'])) * math.sin(math.radians(la)) - math.sin(math.radians(g['lat'])) * math.cos(math.radians(la)) * math.cos(math.radians(lo - g['lon']))
dr = D[int(((math.degrees(math.atan2(y, x)) + 360) % 360 + 11.25) // 22.5) % 16]
name = 'Aberdeen (%.0f km %s, 33 m deep; BODC 11808), Scotland, United Kingdom Current' % (osm_land.km(g['lat'], g['lon'], la, lo), dr)
k = dict(code='BODC11808', inst=M['11808']['Organisation'][:60])
b = C.block(k, r, la, lo, 33.0)
b = b.replace('# Harmonic constants derived from CMEMS in-situ', '# Harmonic constants derived from BODC current meter\n# 2 deployments combined, BODC refs 11808 11857 (Mar + Aug 1969)')
b = b.replace('# (UTide v0.3.1, principal-axis projection)', '# K2/P1 coupled to S2/K1 by ratio/lag of %s (%.0f km), own least squares (XTide model)\n# time check: M2 phase within 8 deg of the existing station 10 km away\n# (principal-axis projection)' % (pn.split(',')[0], km))
b = b.replace('# source: CMEMS in-situ, UTide analysis', '# source: BODC current meter, short-series analysis with inference')
b = b.replace('station_id_context: CMEMS-BODC', 'station_id_context: BODC-').replace('cmems_code:', 'bodc_ref:')
b = b.replace('\nBODC11808 Current\n', '\n%s\n' % name).replace('# BEGIN HOT COMMENTS\n', '# BEGIN HOT COMMENTS\n# country: United Kingdom\n')
assert '\n' + name + '\n' in b and len(name) <= 85
print(len(name), name, 'n=%d r2 %.3f M2 %.2f@%.0f S2 %.2f K2 %.2f' % (r['n'], r['r2'], *r['konst']['M2'], r['konst']['S2'][0], r['konst']['K2'][0]))
f = '/home/oliver/weather/harmonics/utide/harmonics_utide_current_observations.txt'
if '--schreiben' in sys.argv:
    T = open(f, encoding='iso-8859-1').read().rstrip('\n'); sicher_schreiben.schreiben(f, T + '\n' + b + '\n')
