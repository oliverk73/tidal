import sys; sys.path.insert(0, '/home/oliver/weather/py/mde_engstellen')
import eintrag as E
E.S = '/home/oliver/weather/currents/UK_MDE/_arbeit/'
L = [dict(ort='Stroma', ref=(58.6818, -3.1134), teile=[('inner.pkl', 'AWAC D2'), ('meygen2013.pkl', 'MeyGen 2013')], plus=['K2', 'P1'],
          id='CES-119/125', site='MeyGen Inner Sound 2011+2013',
          instr='depth average', inst='EMU Ltd / ERI / MeyGen', land='Scotland, United Kingdom',
          notiz=['AWAC D2 Jun-Jul 2011 (CES-125) + ERI seabed ADCP Feb-Mar 2013 (CES-119), 58 39.590N 3 07.722W', 'deployments 0.7 km apart and 4 months apart in season: S2 and K2 separated (single series: S2 1.45 resp. 2.29 kn)',
                 'time check: instrument pressure M2 between Stroma and Gills Bay tide gauges (both deployments)'])]
E.eintragen(L, '--schreiben' in sys.argv)
