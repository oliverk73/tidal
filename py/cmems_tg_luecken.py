#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Messfits fuer CMEMS-Pegel ohne Bestandssatz im Umkreis von 5 km (1.11.2026, Oliver: Gruppen 1 und 2).

Laedt die Stundenreihen aus INSITU_GLO_PHY_SSH_DISCRETE_MY_013_053 und nutzt py/cmems_tg_fit.py. Namen
in Landessprache, nur ISO-8859-1; Oliver prueft Namen und Positionen.

Usage: venv/bin/python py/cmems_tg_luecken.py [--laden] [--schreiben] [Name ...]
Uebernommen 1.11.2026: 17 Saetze. Verworfen: Iles du Salut, Inhambane, Padang, L9, North Cormorant (schon im Bestand),
Blue Bay (M2 doppelt so gross wie Port Louis), Menton, Nice, Pantelleria, Portopalo, Cassis, Carro (Reihe zu kurz oder Probe schlecht),
Etaples (Fluss), Bodrum (-4 min), La Capte, Le Brusc, Oursinieres, La Redonne, Le Castella (wie der Nachbar).
"""
import os
import re
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cmems_tg_fit as C                                           # noqa: E402

BASIS = 'https://s3.waw3-1.cloudferro.com/mdl-native-03/native/INSITU_GLO_PHY_SSH_DISCRETE_MY_013_053/cmems_obs-ins_glo_phy-ssh_my_na_PT1H_202411/history/TG/'
INDEX = sys.argv[sys.argv.index('--index') + 1] if '--index' in sys.argv else None
# Stichwort der Datei -> Name, Land, Zeitzone
LISTE = {'GL_TS_TG_IlesDuSalutTG': ('Îles du Salut, French Guiana', 'French Guiana', 'America/Cayenne'),
         'IR_TS_TG_Rosslare': ('Rosslare, Ireland', 'Ireland', 'Europe/Dublin'),
         'GL_TS_TG_Inhambane': ('Inhambane, Mozambique', 'Mozambique', 'Africa/Maputo'),
         'GL_TS_TG_BlueBay': ('Blue Bay, Mauritius', 'Mauritius', 'Indian/Mauritius'),
         'GL_TS_TG_Padang': ('Padang, Sumatera Barat, Indonesia', 'Indonesia', 'Asia/Jakarta'),
         'NO_TS_TG_NorthCormorantTG': ('North Cormorant (Platform), United Kingdom', 'United Kingdom', 'Europe/London'),
         'NO_TS_TG_L91TG': ('L9 (Platform), Netherlands', 'Netherlands', 'Europe/Amsterdam'),
         'GL_TS_TG_EtaplesVigicruesTG': ('Étaples, Hauts-de-France, France', 'France', 'Europe/Paris'),
         'IR_TS_TG_AlboranTG': ('Isla de Alborán, Spain', 'Spain', 'Europe/Madrid'),
         'MO_TS_TG_Aigio': ('Aigio, Greece', 'Greece', 'Europe/Athens'),
         'MO_TS_TG_Hrakleio': ('Irakleio (Heraklion, Crete), Greece', 'Greece', 'Europe/Athens'),
         'MO_TS_TG_Ierapetra': ('Ierapetra (Crete), Greece', 'Greece', 'Europe/Athens'),
         'MO_TS_TG_Kapsali': ('Kapsali (Kythira), Greece', 'Greece', 'Europe/Athens'),
         'MO_TS_TG_Kerkyra': ('Kerkyra (Corfu), Greece', 'Greece', 'Europe/Athens'),
         'MO_TS_TG_Koroni': ('Koroni, Greece', 'Greece', 'Europe/Athens'),
         'MO_TS_TG_PaleaFokea': ('Palaia Fokaia, Greece', 'Greece', 'Europe/Athens'),
         'MO_TS_TG_Paleochora': ('Palaiochora (Crete), Greece', 'Greece', 'Europe/Athens'),
         'MO_TS_TG_Samothraki': ('Samothraki, Greece', 'Greece', 'Europe/Athens'),
         'MO_TS_TG_Skopelos': ('Skopelos, Greece', 'Greece', 'Europe/Athens'),
         'MO_TS_TG_BODRUM': ('Bodrum, Turkey', 'Turkey', 'Europe/Istanbul'),
         'MO_TS_TG_BOZYAZI': ('Bozyazi, Turkey', 'Turkey', 'Europe/Istanbul'),
         'MO_TS_TG_MARMARIS': ('Marmaris, Turkey', 'Turkey', 'Europe/Istanbul'),
         'MO_TS_TG_RMN-LeCastella': ('Le Castella, Italy', 'Italy', 'Europe/Rome'),
         'MO_TS_TG_RMN-Pantelleria': ('Pantelleria, Italy', 'Italy', 'Europe/Rome'),
         'MO_TS_TG_RMN-PortopaloDiCap': ('Portopalo di Capo Passero, Italy', 'Italy', 'Europe/Rome'),
         'GL_TS_TG_CassisTG': ('Cassis, France', 'France', 'Europe/Paris'),
         'GL_TS_TG_LaCiotatTG': ('La Ciotat, France', 'France', 'Europe/Paris'),
         'GL_TS_TG_GiensLaMadragueTG': ('La Madrague (Giens), France', 'France', 'Europe/Paris'),
         'GL_TS_TG_LaCapteTG': ('La Capte (Hyères), France', 'France', 'Europe/Paris'),
         'GL_TS_TG_LeBruscTG': ('Le Brusc, France', 'France', 'Europe/Paris'),
         'GL_TS_TG_LesOursinieresTG': ('Les Oursinières, France', 'France', 'Europe/Paris'),
         'GL_TS_TG_MentonTG': ('Menton, France', 'France', 'Europe/Paris'),
         'GL_TS_TG_NiceVigicruesTG': ('Nice (Port), France', 'France', 'Europe/Paris'),
         'GL_TS_TG_PortCrosTG': ('Port-Cros, France', 'France', 'Europe/Paris'),
         'GL_TS_TG_PortDeCarroTG': ('Port de Carro, France', 'France', 'Europe/Paris'),
         'GL_TS_TG_PortDeLaRedonneTG': ('La Redonne, France', 'France', 'Europe/Paris')}


def eintraege():
    aus = []
    for l in open(INDEX, encoding='utf-8', errors='replace'):
        if l.startswith('#'):
            continue
        f = l.split(',')
        d = f[1].split('/')[-1]
        for k, (n, land, tz) in LISTE.items():
            if d.startswith(k + '_') or d.startswith(k):
                aus.append((d, n, float(f[2]), float(f[4]), land, tz, None, 'kein Bestandssatz im Umkreis von 5 km'))
    return aus


def main():
    E = eintraege()
    print(len(E), 'von', len(LISTE), 'fehlt', [k for k in LISTE if not any(x[0].startswith(k) for x in E)])
    if '--laden' in sys.argv:
        for x in E:
            p = os.path.join(C.REIHEN, x[0])
            if not os.path.exists(p):
                urllib.request.urlretrieve(BASIS + x[0], p)
                time.sleep(1)
        print('geladen')
    C.PEGEL = [x for x in E]
    C.main([a for i, a in enumerate(sys.argv[1:]) if a not in ('--laden', '--index') and sys.argv[i] != '--index'])


if __name__ == '__main__':
    main()
