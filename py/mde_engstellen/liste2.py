import sys; sys.path.insert(0, '/home/oliver/weather/py/mde_engstellen')
import eintrag as E
SC = 'Scotland, United Kingdom'
eg = E.pegel('Egilsay, Scotland')
L = [dict(ort='Egilsay', ref=(eg['lat'], eg['lon']), teile=[('westray.pkl', 'Site 3')], id='CES-317', site='Westray South Site 3 (2011)',
          instr='RDI seabed ADCP, depth average', inst='Partrac / SSE Renewables', land=SC,
          notiz=['one of 6 sites within 5 km (Westray Firth); time check: instrument pressure M2 between Egilsay and Rapness tide gauges']),
     dict(ort='Portnahaven', ref=(55.6806, -6.5078), teile=[('islay.pkl', 'DP2')], id='CES-173', site='Islay DP2 (2014)',
          instr='RDI seabed ADCP, depth average', inst='Applied Renewables Research', land=SC,
          notiz=['position from ARR report (55 39 12.056N 6 35 25.607W)',
                 'source time as decimal day with day 0 = 1 Jan (instrument pressure then within 1 min of Orsay; day 1 = 1 Jan gave M2 +25 deg, S2 0 deg)']),
     dict(ort='Cantick Head', ref=(58.7871, -3.1313), teile=[('brims.pkl', 'ST008')], id='CES-46', site='Cantick Phase 1 Site 8 (2010)',
          instr='RDI seabed ADCP, depth average', inst='Partrac / SSE Renewables', land=SC,
          notiz=['position from MDE metadata; time check: instrument pressure M2 within 4 min of Widewall Bay and Gills Bay']),
     dict(ort='Brims', ref=(58.7779, -3.2317), teile=[('brims2.pkl', 'Site22')], id='CES-50', site='Brims Tidal Array Site 22 (2012)',
          instr='RDI seabed ADCP, depth average', inst='Partrac / SSE Renewables', land=SC,
          notiz=['position from MDE metadata; time check: instrument pressure M2 within 20 min of Gills Bay/Widewall Bay (15 km)']),
     dict(ort='Stroma', ref=(58.6818, -3.1134), teile=[('inner.pkl', 'AWAC D2')], id='CES-125', site='MeyGen Inner Sound AWAC D2 (2011)',
          instr='Nortek AWAC, depth average', inst='EMU Ltd / MeyGen', land=SC,
          notiz=['time check: pressure of the co-deployed ADCP (7 days) M2 between Stroma and Gills Bay tide gauges'])]
E.eintragen(L, '--schreiben' in sys.argv)
