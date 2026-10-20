import sys; sys.path.insert(0, '/home/oliver/weather/py/mde_engstellen')
import eintrag as E
L = [dict(ort="St David's Head", ref=(51.9030, -5.3127), teile=[('stdavids.pkl', 'St Davids')], id='TCE-2032', site="St David's Head 2014",
          instr='seabed ADCP, depth average', inst='Tidal Energy Ltd / SEACAMS', land='Wales, United Kingdom',
          notiz=['time check: ADCP surface elevation M2 within 1 min of Ramsey Sound tide gauge']),
     dict(ort='Fair Head', ref=(55.2241, -6.1403), teile=[('fairhead.pkl', 'L1'), ('fairhead.pkl', 'L4')], id='TCE-349', site='Fair Head ADCP 1 (2014) + 4 (2014/15)',
          instr='RDI Workhorse seabed ADCP, depth average', inst='Applied Renewables Research / DP Energy', land='Northern Ireland, United Kingdom',
          notiz=['positions from ARR deployment reports (55 13.810N 6 06.855W; 55 14.039N 6 06.750W)',
                 'near the Rathlin amphidrome: pressure M2 too weak for a time check; current M2 phase of both campaigns within 6 deg'])]
E.eintragen(L, '--schreiben' in sys.argv)
