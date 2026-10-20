import sys; sys.path.insert(0, '/home/oliver/weather/py/mde_engstellen')
import eintrag as E
SC = 'Scotland, United Kingdom'
L = [dict(ort='Fall of Warness', ref=(59.1275, -2.8063), teile=[('orkney.pkl', 'FoW13')], id='CES-94', site='EMEC Fall of Warness FoW-SMADCP-13',
          instr='RDI Workhorse 600 kHz seabed ADCP, depth average to 85 % of surface range', inst='European Marine Energy Centre (EMEC)', land=SC,
          notiz=['position 59 08.147N 2 48.391W (MDE metadata); time check: ADCP pressure M2 within 3 min of Egilsay tide gauge']),
     dict(ort='Kylerhea', ref=(57.2223, -5.6661), teile=[('kyle.pkl', 'K2')], id='CES-197', site='Kyle Rhea Site 2 (2012)',
          instr='RDI 600 kHz seabed ADCP, beam coordinates transformed to earth, depth average', inst='Partrac / Marine Current Turbines', land=SC,
          notiz=['position from Partrac site metadata (57 13.8054N 5 39.6827W); 4 sites within 200 m',
                 'time check: ADCP pressure M2 between Glenelg Bay and Kyle of Lochalsh tide gauges']),
     dict(ort='The Skerries', ref=(53.4219, -4.6081), teile=[('skerries.pkl', 'S2')], id='TCE-2014', site='Skerries Location 2 (2012)',
          instr='RDI seabed ADCP, depth average', inst='Partrac / Marine Current Turbines', land='Wales, United Kingdom',
          notiz=['position from Partrac site metadata (53 25.1184N 4 34.8436W); 5 sites within 300 m',
                 'time check: ADCP pressure M2 between Holyhead and Cemaes Bay tide gauges'])]
E.eintragen(L, '--schreiben' in sys.argv)
