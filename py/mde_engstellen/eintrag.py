"""Gemeinsamer MDE-Eintrag: Stationen aus Pickles (lat, lon, df stuendlich, richtig gestempelt)."""
import sys, math, pickle, warnings; warnings.filterwarnings('ignore')
S = '/home/oliver/weather/currents/UK_MDE/_arbeit/'
sys.path.insert(0, '/home/oliver/weather/py'); sys.path.insert(0, '/home/oliver/weather/py')
import pandas as pd, utide
import stroemung_kurzfit as K, cmems_stroemung_nachholen as C, osm_land, sicher_schreiben, health_check as hc
F = '/home/oliver/weather/harmonics/utide/harmonics_utide_current_observations.txt'
D = ['N','NNE','NE','ENE','E','ESE','SE','SSE','S','SSW','SW','WSW','W','WNW','NW','NNW']
_T = None


def pegel(p):
    global _T
    _T = _T or [t for t in hc.load_records() if not t['current'] and t['lat'] is not None]
    return [x for x in _T if x['name'].startswith(p)][0]


def geo(a, b, c, d):
    y = math.sin(math.radians(d-b))*math.cos(math.radians(c)); x = math.cos(math.radians(a))*math.sin(math.radians(c))-math.sin(math.radians(a))*math.cos(math.radians(c))*math.cos(math.radians(d-b))
    return osm_land.km(a, b, c, d), D[int(((math.degrees(math.atan2(y, x))+360) % 360+11.25)//22.5) % 16]


def fit(st):
    teile = [pickle.load(open(S + p, 'rb'))[k] for p, k in st['teile']]
    dfs = [t['df'] for t in teile]
    df = pd.concat(dfs).sort_index()
    df = df[~df.index.duplicated()]
    n = sum(len(x) for x in dfs)
    la = sum(t['lat'] * len(t['df']) for t in teile) / n
    lo = sum(t['lon'] * len(t['df']) for t in teile) / n
    if len(df) < 600:
        g = pegel(st['pegel'])
        return K.fit(df, K.pegel_verhaeltnisse('/home/oliver/weather/' + g['file'], g['name'])), la, lo, g['name']
    if len(df) >= 8766:
        konst = None
    elif len(dfs) == 1:
        konst = 'auto'
    else:
        L = max(dfs, key=len)
        konst = list(utide.solve(L.index.to_pydatetime(), L['u'].values, lat=la, constit='auto', nodal=True, trend=False,
                                 method='ols', conf_int='none', verbose=False)['name']) + st.get('plus', [])
    return C.analyse(df, la, konst), la, lo, None


def block(st):
    r, la, lo, kurz = fit(st)
    d, dr = geo(*st['ref'], la, lo)
    name = '%s (%.0f km %s, %s; MDE %s), %s Current' % (st['ort'], d, dr, st.get('tiefe', 'depth mean'), st['id'], st['land'])
    if len(name) > 85:
        name = name.replace(', %s;' % st.get('tiefe', 'depth mean'), ';')
    assert len(name) <= 85, name
    code = st['id'].replace('-', '')
    b = C.block(dict(code=code, inst=st['inst']), r, la, lo, float('nan'))
    kopf = '# Harmonic constants derived from Marine Data Exchange (The Crown Estate) %s, %s, %s' % (st['id'], st['site'], st['instr'])
    if len(st['teile']) > 1:
        kopf += '\n# %d deployments combined' % len(st['teile'])
    if kurz:
        kopf += '\n# short series (%d days): N2, K2, P1 inferred from %s (ratio and phase lag of tide gauge), own least squares (XTide model)' % (round(r['n'] / 24), kurz)
        b = b.replace('# (UTide v0.3.1, principal-axis projection)', '# (principal-axis projection)').replace('# confidence: 8', '# confidence: 6')
    for z in st.get('notiz', []):
        kopf += '\n# ' + z
    b = b.replace('# Harmonic constants derived from CMEMS in-situ', kopf)
    b = b.replace('# source: CMEMS in-situ, UTide analysis', '# source: Marine Data Exchange %s (%s), %s' % (st['id'], st['site'], 'short-series analysis with inference' if kurz else 'UTide analysis'))
    b = b.replace('station_id_context: CMEMS-%s' % code, 'station_id_context: MDE-%s' % st['id']).replace('# cmems_code: %s' % code, '# mde_id: %s' % st['id'])
    b = b.replace('\n%s Current\n' % code, '\n%s\n' % name).replace('# BEGIN HOT COMMENTS\n', '# BEGIN HOT COMMENTS\n# country: United Kingdom\n')
    assert all(len(l) <= 95 for l in b.split('\n') if l.startswith('# source:')), 'source > 90'
    assert '\n' + name + '\n' in b and max(len(l) for l in b.split('\n')) < 200
    print('%2d n=%d r2 %.2f M2 %.2f@%.0f %.4f %.4f %s' % (len(name), r['n'], r['r2'], *r['konst']['M2'], la, lo, name), flush=True)
    return b


def eintragen(liste, schreiben):
    neu = [block(st) for st in liste]
    if schreiben:
        T0 = open(F, encoding='iso-8859-1').read().rstrip('\n')
        sicher_schreiben.schreiben(F, T0 + '\n' + '\n'.join(neu) + '\n')
