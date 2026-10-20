import sys, pickle, warnings; warnings.filterwarnings('ignore')
sys.path.insert(0, '/home/oliver/weather/py/mde_engstellen')
import pruef as P, cmems_stroemung_nachholen as C
D = pickle.load(open(sys.argv[1], 'rb'))
for k, x in D.items():
    df = x['df']
    r = C.analyse(df, x['lat'], None if len(df) >= 8766 else 'auto') if len(df) > 24 * 14 else None
    print('##', k, '%.4f %.4f' % (x['lat'], x['lon']), 'n=%d' % len(df), r and 'r2 %.2f achse %.0f M2 %.2f@%.0f S2 %.2f' % (r['r2'], r['achse'], *r['konst']['M2'], r['konst']['S2'][0]))
    print(P.druck(x.get('p'), x['lat'], x['lon']))
    print('  Strom-Nachbarn:', ' | '.join('%.1f %s' % (a, b[:40]) for a, b in P.nachbarn(x['lat'], x['lon'])), flush=True)
    x['r'] = r
pickle.dump(D, open(sys.argv[1], 'wb'))
