#!/usr/bin/env python3
"""NP160 (UKHO Tidal Harmonic Constants, European Waters) -> harmonics/att/harmonics_att_np160.txt

Nur Saetze, die der Zeugenabgleich (py/np160_zeugen.py, 24.11.2026) als Gewinn belegt:
  * LUECKE: kein Gezeitensatz bis 3 km, naechster deutlich weiter (Machrihanish 9 km auf der anderen
    Kintyre-Seite, Drogheda 7 km Boyne-Muendung, Mys Mikulkin 63 km, Tobruk 111 km);
  * ERSATZ: gleichnamiger Bestandssatz (Tafel-Fit) liegt gegen FES2022 mindestens doppelt so weit
    daneben wie NP160 (Vektorfehler M2/S2/K1/O1), NP160 hoechstens 0,20 -> alter Satz wird archiviert,
    Name und Position bleiben.
Abschrift: harmonics/help/np160_part3.tsv. Simplified Harmonic Method: M2/S2/K1/O1 aus dem Buch,
N2/K2 inferiert (wie NP203), P1 = 0.33*K1; M4/M6 aus den S.W.-Korrekturen (Faktor: H = F*H_M2^n,
g = n*g_M2 + f). Danach FES2022-Nebentiden am Ort (att_anreichern_quelle-Verfahren, nur diese Datei),
M4/M6 aus dem Buch bleiben.

    venv/bin/python py/build_np160.py [--schreiben]
"""
import csv
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_np203_scs as B                                          # noqa: E402
import health_check as H                                             # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TSV = os.path.join(ROOT, 'harmonics', 'help', 'np160_part3.tsv')
OUT = os.path.join(ROOT, 'harmonics', 'att', 'harmonics_att_np160.txt')
ALT = 'harmonics/utide/harmonics_utide_tidetables.txt'

# nr -> (Name, Land, IANA-Zone, lat, lon, Begruendung)
LUECKE = {
    '390': ('Machrihanish (Kintyre), Scotland, United Kingdom', 'United Kingdom', 'Europe/London', 55.4250, -5.7400,
            'Luecke: West-Kintyre (Amphidromie, M2 0,18 m); naechster Satz Campbeltown 9 km auf der Ostseite (M2 0,93 m).'),
    '623a': ('Drogheda, Ireland', 'Ireland', 'Europe/Dublin', 53.7155, -6.3480,
             'Luecke: Boyne, 7 km oberhalb der Muendung (River Boyne Entrance); Phase 7 Grad spaeter, ML 2,88 m.'),
    '1026a': ("Mys Mikulkin, Nenets Autonomous Okrug, Russia", 'Russia', 'Europe/Moscow', 67.8068, 46.6877,
              'Luecke: Kanin-Halbinsel, naechster Satz 63 km (Reka Vostochnaya Kambal\'nitsa). Position UKHO-Index.'),
    '1995': ('Tobruk, Libya', 'Libya', 'Africa/Tripoli', 32.0750, 23.9750,
             'Luecke: naechster Satz Mina Bardiyah 111 km. Mikrotide (M2 0,01 m), ML abgeleitet (x).'),
}
# nr -> (Name des Bestandssatzes, FES-Abstand Buch, FES-Abstand alt)
ERSATZ = {
    '607': ('Courtown, Ireland', 0.28, 0.99),
    '1815': ('Al Hoceima, Morocco', 0.20, 0.99),
    '34a': ('Mupe Bay, England, United Kingdom', 0.11, 0.43),
    '143': ('Caister-On-Sea, England, United Kingdom', 0.12, 0.28),
    '387': ('Carsaig Bay, Scotland, United Kingdom', 0.16, 0.47),
    '296': ('Bay Of Quendale (Shetlands), Scotland, United Kingdom', 0.13, 0.24),
    '43': ('Stansore Point, England, United Kingdom', 0.14, 0.27),
}
ZONE_TZ = {'Ireland': 'Europe/Dublin', 'United Kingdom': 'Europe/London', 'Morocco': 'Africa/Casablanca'}
# Weisses Meer (Oliver 24.11.2026 "ja"): Bestand dort nur NP202-Part-II-Uebertragungen; NP160 hat eigene
# Analysen, die an den zwei unabhaengigen Classic-Saetzen (Archangelsk, Kem) auf 1,7 % passen. FES taugt dort
# nicht als Schiedsrichter. Ausgenommen: Ostrov Veshnyak (K1/O1-180-Grad-Spruenge wie Kola), Umba, Sosnovets.
ALT_WM = 'harmonics/att/harmonics_att_np202_secondary.txt'
WEISS = {
    '1036': 'Ostrov Morzhovets, Arkhangelsk Oblast, Russia',
    '1038': 'Reka Megra, Arkhangelsk Oblast, Russia',
    '1039': 'Mys Intsy, Arkhangelsk Oblast, Russia',
    '1043': "Mys Yuzhnyy (Ostrov Mud'yugskiy), Arkhangelsk Oblast, Russia",
    '1044': 'Lapominka, Arkhangelsk Oblast, Russia',
    '1048': 'Pertominsk (Unskaya Guba), Arkhangelsk Oblast, Russia',
    '1050': 'Ostrov Zhizhginskiy, Arkhangelsk Oblast, Russia',
    '1053': 'Mys Chesmenskiy, Arkhangelsk Oblast, Russia',
    '1055': 'Ostrov Kiy (Onezhskaya Guba), Arkhangelsk Oblast, Russia',
    '1056': 'Onega, Arkhangelsk Oblast, Russia',
    '1057': 'Ostrov Paskanets, Arkhangelsk Oblast, Russia',
    '1059': 'Ostrov Berezhnoy, Republic of Karelia, Russia',
    '1072': 'Gridino, Republic of Karelia, Russia',
    '1075': 'Kandalaksha, Murmansk Oblast, Russia',
    '1076': "Guba Por'ya, Murmansk Oblast, Russia",
    '1084': 'Mys Orlov-Terskiy Tonkiy, Murmansk Oblast, Russia',
}


def zahl(s):
    try:
        return float(s)
    except ValueError:
        return None


def konstanten(r):
    con = {}
    for k, gk, hk in (('M2', 'm2g', 'm2h'), ('S2', 's2g', 's2h'), ('K1', 'k1g', 'k1h'), ('O1', 'o1g', 'o1h')):
        a, g = zahl(r[hk]), zahl(r[gk])
        if a is not None and a > 0 and g is not None:
            con[k] = (a, g)
    for k, gk, hk, n in (('M4', 'f4', 'F4', 2), ('M6', 'f6', 'F6', 3)):
        f, F = zahl(r[gk]), zahl(r[hk])
        if f is not None and F is not None and 'M2' in con:
            con[k] = (round(F * con['M2'][0] ** n, 4), round((n * con['M2'][1] + f) % 360, 2))
    if 'M2' in con and 'S2' in con:
        con['N2'], con['K2'] = B.inferenz(con['M2'], con['S2'])
    if 'K1' in con:
        con['P1'] = (0.33 * con['K1'][0], con['K1'][1])
    return con


def main(argv):
    schreiben = '--schreiben' in argv
    heute = dt.date.today().strftime('%Y%m%d')
    HEADER, ORDER = B.kopf()
    buch = {r['nr']: r for r in csv.DictReader(open(TSV), delimiter='\t')}
    recs = H.load_records()
    alt = {r['name']: r for r in recs if r['file'] == os.path.relpath(OUT, ROOT)}   # schon ersetzte: Position aus NP160
    alt.update({r['name']: r for r in recs if r['file'] == ALT})
    alt_wm = {r['name']: r for r in recs if r['file'] == ALT_WM}
    bloecke, loeschliste, loesch_wm = [], [], []
    for nr, spec in list(LUECKE.items()) + list(ERSATZ.items()) + list(WEISS.items()):
        r = buch[nr]
        if nr in LUECKE:
            name, land, tz, lat, lon, grund = spec
        elif nr in WEISS:
            name, land, tz = spec, 'Russia', 'Europe/Moscow'
            a = alt_wm[name]
            lat, lon = a['lat'], a['lon']
            grund = ('Ersatz fuer die NP202-Part-II-Uebertragung gleicher ATT-Nummer (archiviert ' + heute + '): NP160 hat '
                     'eigene harmonische Konstanten; Archangelsk/Kem (Classic 1997) bestaetigen NP160 auf 1,7 %.')
            loesch_wm.append(dict(datei=ALT_WM, name=name, fehler_prozent='',
                                  begruendung=f'Part-II-Uebertragung ersetzt durch NP160-Analyse Nr. {nr} (Buch S.{r["buchseite"]}), '
                                              f'harmonics_att_np160.txt (Weisses Meer, Oliver {heute})'))
        else:
            name, fb, fa = spec
            a = alt[name]
            lat, lon = a['lat'], a['lon']
            land = name.split(',')[-1].strip()
            tz = ZONE_TZ[land]
            grund = (f'Ersatz fuer den gleichnamigen Tafel-Fit ({os.path.basename(ALT)}, archiviert {heute}): '
                     f'gegen FES2022 Vektorfehler M2/S2/K1/O1 NP160 {fb:.2f}, alter Satz {fa:.2f}.')
            loeschliste.append(dict(datei=ALT, name=name, fehler_prozent=round(100 * fa),
                                    begruendung=f'NP160 Nr. {nr} (Buch S.{r["buchseite"]}) deutlich naeher an FES2022 '
                                                f'({fb:.2f} gegen {fa:.2f}) -> ersetzt durch harmonics_att_np160.txt ({heute})'))
        zone = r['zone']
        mer = '+00:00' if zone == '0' else f'{-int(zone[:3]):+03d}:{zone[3:]}'
        con = konstanten(r)
        sw = ' M4/M6 aus den S.W.-Korrekturen.' if 'M4' in con else ''
        b = ['# BEGIN HOT COMMENTS',
             f'# country: {land}',
             '# source: UKHO NP160 Tidal Harmonic Constants, European Waters, Simplified Harmonic Method',
             f'# att_number: {nr}',
             f'# note: NP160 S.{r["buchseite"]}, Buchname "{r["name"]}", Zone {"UT" if zone == "0" else zone}.'
             + (f' Buchvermerk: {r["bem"]}.' if r['bem'] else ''),
             f'# note: {grund}',
             f'# note: N2/K2 inferiert, P1 = 0.33*K1.{sw} Zeugenabgleich: py/np160_zeugen.py.',
             f'# date_imported: {heute}',
             '# datum: Chart Datum (Z0 = mean level above CD)',
             '# confidence: 5',
             '# !units: meters',
             f'# !longitude: {lon:.4f}',
             f'# !latitude: {lat:.4f}',
             name,
             f'{mer} :{tz}',
             f'{float(r["ml"]):.4f} meters']
        for c in ORDER:
            b.append(f'{c:<15s} {con[c][0]:.4f}  {con[c][1]:.2f}' if c in con else 'x 0 0')
        bloecke.append(b)
        print(f'{nr:6s} {name:55s} {len(con)} Konstituenten, M2 {con["M2"][0]:.2f}/{con["M2"][1]:.0f}')
    if not schreiben:
        return 0
    txt = '\n'.join(HEADER) + '\n' + '\n'.join('\n'.join(b) for b in bloecke) + '\n'
    open(OUT, 'w', encoding='iso-8859-1').write(txt)
    os.chmod(OUT, 0o600)
    liste = os.path.join(ROOT, 'harmonics', 'help', f'loeschen_{heute}_np160_ersatz.csv')
    with open(liste, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=['datei', 'name', 'fehler_prozent', 'begruendung'])
        w.writeheader()
        w.writerows(loeschliste)
    liste_wm = os.path.join(ROOT, 'harmonics', 'help', 'loeschen_20261124_np160_weisses_meer.csv')
    with open(liste_wm, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=['datei', 'name', 'fehler_prozent', 'begruendung'])
        w.writeheader()
        w.writerows(loesch_wm)
    print(f'{len(bloecke)} Saetze -> {os.path.relpath(OUT, ROOT)}; Loeschlisten {os.path.relpath(liste, ROOT)}, '
          f'{os.path.relpath(liste_wm, ROOT)}')
    return 0


def anreichern(schreiben):
    """FES2022-Nebentiden am Ort wie att_anreichern_quelle.fes_alle, nur fuer OUT; Buch-M4/M6 bleiben."""
    import collections
    import netCDF4 as nc
    import att_anreichern as A
    import att_anreichern_quelle as Q
    import fes_kuestentyp as F
    import scheitelfit as SF
    import xtide_modell as X
    heute = dt.date.today().strftime('%Y%m%d')
    rel = os.path.relpath(OUT, ROOT)
    kand = []
    for r in H.load_records():
        if r['file'] == rel:
            z0, w, _, m = X.satz_lesen(OUT, r['name'])
            kand.append(dict(r, z0=z0, w=w, m=m))
    F.fes_dazu(kand)
    for fn, c in Q.FES_NAMEN.items():
        d = nc.Dataset(os.path.join(F.FES, f'{fn}_fes2022.nc'))
        for p in kand:
            i, j = p['ij']
            p.setdefault('voll', {})[c] = (float(d['amplitude'][i, j]) / 100.0, float(d['phase'][i, j]))
        d.close()
    zahl = collections.Counter()
    namen, speeds = X.kopf_lesen(OUT)[:2]
    for p in kand:
        if p['fes_wasser_km'] > 5:
            zahl['FES-Wasser > 5 km'] += 1
            continue
        if F.typ(dict(lat=p['lat'], lon=p['lon'])) == 'binnen':
            zahl['binnen'] += 1
            continue
        buch_sw = {c: v for c, v in p['w'].items() if c in ('M4', 'M6') and v[0] > 0}
        basis = {c: v for c, v in p['w'].items() if c not in buch_sw}
        wf = {c: v for c, v in p['voll'].items() if v[0] > 0 and c in speeds and c not in buch_sw}
        if not A.passt(basis, wf):
            zahl['NP160/FES > Faktor 1,5'] += 1
            print('  nicht angereichert (Faktor 1,5):', p['name'])
            continue
        neu = A.ergaenzt(basis, p['m'], wf, 0.0, speeds)
        neu.update(buch_sw)
        zahl['angereichert'] += 1
        if schreiben:
            SF.satz_schreiben(OUT, p['name'], p['z0'], neu, namen,
                              [f'{heute} angereichert (py/build_np160.py --fes): M2/S2/K1/O1 (und M4/M6) aus NP160',
                               f'unveraendert, uebrige {len(neu) - 4 - len(buch_sw)} aus FES2022 am Ort umgerechnet.'])
    print(dict(zahl))


if __name__ == '__main__':
    if '--fes' in sys.argv:
        anreichern('--schreiben' in sys.argv)
        sys.exit(0)
    sys.exit(main(sys.argv[1:]))
