#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Leitet die NP202-Part-II-Sekundaerhaefen neu ab -- aus dem Buch statt aus dem
verlorengegangenen Import von 2026-06.

Drei Fehler des alten Imports werden hier behoben:

1. Falscher Bezugshafen. In ATT gilt der eingerahmte Standardhafen ueber einer
   Gruppe bis zum naechsten eingerahmten Kopf. Ein Standardhafen, der INNERHALB
   der Liste an seiner geografischen Stelle steht ("STANDARD PORT / See Table V"),
   ist nur ein Eintrag -- kein neuer Bezug. Der alte Import hat ab jedem solchen
   Eintrag gewechselt und dadurch 105 der 436 Stationen an den falschen Hafen
   gehaengt: die Faeroeer an Torshavn statt Reykjavik, das Weisse Meer an
   Arkhangelsk statt Port of Kem', die Finnmark an Kirkenes statt Ostrov
   Yekaterininskiy, Troms an Tromso statt Narvik, und so fort.

2. Gerechneter statt publizierter Bezugshub. Der Skalierungsfaktor muss gegen den
   im Gruppenkopf gedruckten Hub gebildet werden:

       SR = MHWS - MLWS          NR = MHWN - MLWN
       fS = (SR + dMHWS - dMLWS) / SR
       fN = (NR + dMHWN - dMLWN) / NR

   ACHTUNG NP202-Besonderheit: die Hoehenspalten sind DIFFERENZEN IN METERN
   ("HEIGHT DIFFERENCES (IN METRES)"), keine Faktoren. Deshalb darf der
   Bezugshafen beliebig weit weg liegen -- das Buch nimmt Helgoland fuer die
   sibirische Arktis und Galveston fuer die Kleinen Antillen. Das ist kein
   Fehler der Vorlage, sondern ihre Systematik.

3. Zonenversatz in der Zeitdifferenz. Die Differenzen gelten zwischen den
   ORTSZEITEN beider Haefen. Fuer die Phasenverschiebung brauchen wir die echte
   Verzoegerung in Weltzeit:

       dt_UT = dt_Buch + (Zone_Bezug - Zone_Sekundaer)

   Bei der Finnmark unter Yekaterininskiy sind das 2 Stunden, bei Pitlekaj unter
   Helgoland 11. In M2 ist eine Stunde 29 Grad Phase.

Quellen: harmonics/help/np202_part2_gruppenkoepfe.tsv und
         harmonics/help/np202_part2_stationen.tsv, beide am 05.08.2026 aus
         tide_tables/att/np202_2015_secondary_ports_p358-403.pdf gelesen.

Aufruf: venv/bin/python py/rebuild_np202_transfer.py [--write]
Ohne --write wird nur berichtet, nichts geaendert.
"""
from __future__ import annotations
import os
import re
import shutil
import sys
from datetime import date

HARM = '/home/oliver/weather/harmonics'
TXT = f'{HARM}/att/harmonics_att_np202_secondary.txt'
GRUPPEN = f'{HARM}/help/np202_part2_gruppenkoepfe.tsv'
STATIONEN = f'{HARM}/help/np202_part2_stationen.tsv'

SPEED = {
    'M2': 28.9841042, 'S2': 30.0, 'N2': 28.4397295, 'K2': 30.0821373, 'K1': 15.0410686,
    'O1': 13.9430356, 'P1': 14.9589314, 'Q1': 13.3986609, 'M4': 57.9682084, 'M6': 86.9523127,
    'MK3': 44.0251729, 'S4': 60.0, 'MN4': 57.4238337, 'NU2': 28.5125831, 'S6': 90.0,
    'MU2': 27.9682084, '2N2': 27.8953548, 'OO1': 16.1391017, 'LAMBDA2': 29.4556253,
    'S1': 15.0, 'M1': 14.4966939, 'J1': 15.5854433, 'MM': 0.5443747, 'SSA': 0.0821373,
    'SA': 0.0410686, 'MSF': 1.0158958, 'MF': 1.0980331, 'RHO1': 13.4715145,
    'Q1_': 13.3986609, 'T2': 29.9589333, 'R2': 30.0410667, '2Q1': 12.8542862,
    'P1_': 14.9589314, '2SM2': 31.0158958, 'M3': 43.4761563, 'L2': 29.5284789,
    '2MK3': 42.9271398, 'K2_': 30.0821373, 'M8': 115.9364169, 'MS4': 58.9841042,
}
SEMI_M = {'N2', 'NU2', 'MU2', '2N2', 'LAMBDA2', 'L2', 'T2', 'R2', '2SM2'}
SHALLOW = {'M4', 'M6', 'M8', 'MN4', 'MS4', 'MK3', '2MK3', 'S4', 'S6', 'M3'}
DIURNAL = {'K1', 'O1', 'P1', 'Q1', '2Q1', 'RHO1', 'M1', 'J1', 'OO1', 'S1'}
LANGZEIT = {'SA', 'SSA', 'MM', 'MSF', 'MF'}

# unsere att-Nummer -> Nummer im Buch (nur wo beide auseinandergehen)
VERSATZ = {
    '1086': '1085', '1295b': '1295a', '1295c': '1295b', '1330': '1338',
    '1412.5': '1412a', '1425.5': '1425a', '1433.6': '1435a', '1588': '1587a',
    '1589': '1588', '1615': '1611b', '2504': '2505', '2547': '2546',
    '2548': '2547', '2997': '3423', '3423': '3423a', '3434': '3434b',
}

# Bezugshafen -> (Stationsname, Datei). Ausgewaehlt nach Uebereinstimmung des
# gerechneten Springhubs 2*(M2+S2) mit dem im Gruppenkopf gedruckten.
DONOR = {
    '819':  ('Reykjavik, Iceland', 'ticon/harmonics_ticon4_worldwide.txt'),
    '1067': ("Port Kem, Russia", 'classic/harmonics-1997-05-25_mod.txt'),
    '1101': ('Yekaterininskaya, Russia', 'classic/harmonics-1997-05-25_mod.txt'),
    '1188': ('Narvik, Norway', 'ticon/harmonics_ticon4_worldwide.txt'),
    '1258': ('Bergen, Norway', 'ticon/harmonics_ticon4_worldwide.txt'),
    '1417': ('Esbjerg, Denmark', 'ticon/harmonics_ticon4_worldwide.txt'),
    '1431': ('Helgoland, Germany', 'classic/harmonics-dwf-20070318_mod.txt'),
    '1438': ('Cuxhaven (Steubenhöft), Germany', 'classic/harmonics-dwf-20070318_mod.txt'),
    '1579': ('Dieppe, France', 'utide/harmonics_utide_observations.txt'),
    '1582': ('Le Havre (Marégraphe), France', 'ticon/harmonics_ticon4_worldwide.txt'),
    '1614': ('Saint-Malo, France', 'utide/harmonics_utide_observations.txt'),
    '1638': ('Brest (Moulin Blanc), France', 'utide/harmonics_utide_tidetables.txt'),
    '1681': ('Port-Bloc (La Pointe de Grave), France', 'ticon/harmonics_ticon4_worldwide.txt'),
    '2290': ('Georgetown, Guyana', 'utide/harmonics_utide_tidetables.txt'),
    '2321': ('Port of Spain, Trinidad and Tobago', 'ticon/harmonics_ticon4_worldwide.txt'),
    '2398': ('Cristobal, Panama', 'utide/harmonics_utide_observations.txt'),
    '2437': ('Bridgetown, Barbados', 'utide/harmonics_utide_observations.txt'),
    '2569': ("St. George's Island, Bermuda", 'noaa/harmonics_noaa_carib.txt'),
    # Galveston Pier 21 ist der Pegel, den ATT als Standardhafen GALVESTON
    # fuehrt. Der alte Import nahm Clear Lake, 30 km weiter oben in der Bucht.
    # ACHTUNG: dieser Datensatz steht in FUSS -- lies_donor rechnet um.
    '2590': ('Galveston Pier 21, Galveston Channel, Texas',
             'classic/harmonics-dwf-20251228-free.txt'),
    '2997': ('Pictou, Nova Scotia, Canada', 'ticon/harmonics_ticon4_worldwide.txt'),
    '3067': ('Pointe-au-Père, Québec, Canada', 'ticon/harmonics_ticon4_worldwide.txt'),
    '3114': ('Harrington Harbour, Québec, Canada', 'ticon/harmonics_ticon4_worldwide.txt'),
}

# Zone des Bezugshafens als UTC-Versatz in Stunden (Buchangabe "Zone -0100"
# heisst Ortszeit = UT+1, also +1).
ZONE_REF = {
    '819': 0, '1067': 3, '1101': 3, '1188': 1, '1258': 1, '1417': 1, '1431': 1,
    '1438': 1, '1579': 1, '1582': 1, '1614': 1, '1638': 1, '1681': 1,
    '2290': -4, '2321': -4, '2398': -5, '2437': -4, '2569': -4, '2590': -6,
    '2997': -4, '3067': -5, '3114': -4,
}

# Zone der Sekundaerhaefen, aus den Zwischenueberschriften des Scans.
# (von, bis, UTC-Versatz in Stunden)
ZONE_SEC = [
    ('780', '875', 0), ('880', '902', 1), ('903', '903', 0), ('904', '906', 1),
    ('910', '912', 5), ('920', '920', 6), ('930', '930', 10), ('950', '958', 12),
    ('959', '959', 11), ('966', '966', 9), ('971', '987', 7), ('989', '998', 5),
    ('1000', '1119', 3), ('1130', '1342', 1), ('1349', '1353', 2),
    ('1357', '1357', 3), ('1358', '1375', 2), ('1376', '1693', 1),
    ('2308', '2318', -4.5), ('2319', '2339', -4), ('2344', '2360', -4.5),
    ('2362', '2362', -4.5), ('2368', '2372a', -4), ('2373', '2382', -4.5),
    ('2385', '2401', -5), ('2402', '2428', -6), ('2430', '2433', -5),
    ('2439', '2473', -4), ('2475', '2567', -5), ('2568', '2570', -4),
    ('2573', '2586b', -6), ('3389', '3398', -7), ('3400', '3404', -5),
    ('3406', '3408', -4), ('3413', '3456', -3), ('3459', '3469', -1),
]


def key(att):
    m = re.match(r'([\d.]+)(.*)', att)
    return (float(m.group(1)), m.group(2))


def zone_sec(att):
    k = key(att)
    for v, b, z in ZONE_SEC:
        if key(v) <= k <= key(b):
            return z
    return None


def hhmm(s):
    """'+0345' -> 225 Minuten. Buchstabencodes -> None."""
    if not re.match(r'^[+-]\d{4}$', s):
        return None
    return (1 if s[0] == '+' else -1) * (int(s[1:3]) * 60 + int(s[3:5]))


def zahl(s):
    try:
        return float(s)
    except ValueError:
        return None


def lies_gruppen():
    out = []
    for l in open(GRUPPEN, encoding='utf-8'):
        if l.startswith('#') or not l.strip():
            continue
        f = l.rstrip('\n').split('\t')
        out.append(dict(ref=f[1], name=f[2], pegel=[float(x) for x in f[3:7]],
                        von=f[7], bis=f[8]))
    return out


def gruppe(att, gruppen):
    k = key(att)
    for g in gruppen:
        if key(g['von']) <= k <= key(g['bis']):
            return g
    return None


def lies_buch():
    out = {}
    for l in open(STATIONEN, encoding='utf-8'):
        if l.startswith('#') or not l.strip():
            continue
        f = l.rstrip('\n').split('\t')
        out[f[0]] = dict(name=f[1], lat=f[2], lon=f[3],
                         t=[hhmm(x) for x in f[4:8]],
                         h=[zahl(x) for x in f[8:12]],
                         ml=zahl(f[12]), roh=f)
    return out


def lies_donor():
    """Bezugshafen-Konstituenten aus der Sammlung."""
    out = {}
    for ref, (name, datei) in DONOR.items():
        L = open(f'{HARM}/{datei}', encoding='iso-8859-1').read().split('\n')
        idx = [i for i, l in enumerate(L) if l.strip() == name
               and re.match(r'^[+-]\d\d:\d\d :', L[i + 1] if i + 1 < len(L) else '')]
        if not idx:
            print(f'ACHTUNG: Bezug {ref} "{name}" nicht in {datei}')
            continue
        i = idx[0]
        mer, tz = L[i + 1].split(' :', 1)
        # Einheit! In harmonics-dwf-20251228-free.txt stehen die
        # NOAA-Stationen in FUSS. Wer das uebersieht, macht die ganze
        # Gruppe um den Faktor 3.28 zu gross -- genau das ist dem alten
        # Import bei der Galveston-Gruppe passiert.
        fak = 0.3048 if L[i + 2].split()[-1].startswith('feet') else 1.0
        con = {}
        for x in L[i + 3:]:
            if x.startswith('# BEGIN') or x.startswith('# att_number'):
                break
            m = re.match(r'^([A-Z][A-Z0-9_]*)\s+([\d.]+)\s+([\d.]+)\s*$', x.strip())
            if m:
                con[m.group(1)] = (float(m.group(2)) * fak, float(m.group(3)))
        out[ref] = dict(name=name, con=con, mer=mer, tz=tz, einheit=fak,
                        z0=float(L[i + 2].split()[0]) * fak)
    return out


def transfer(ref_con, pegel, h, t, dz=0.0, ml=None):
    """Wie py/rebuild_np203_transfer.py, siehe dort die Begruendung."""
    MHWS, MHWN, MLWN, MLWS = pegel
    SR, NR = MHWS - MLWS, MHWN - MLWN
    dMHWS, dMHWN, dMLWN, dMLWS = h
    if dMHWS is None:
        dMHWS = 0.0
    if dMLWS is None:
        dMLWS = 0.0
    if dMHWN is None:
        dMHWN = dMHWS
    if dMLWN is None:
        dMLWN = dMLWS
    MLref = 0.5 * (MHWS + MLWS)
    lw_fehlt = h[3] is None and ml is not None and MHWS > MLref + .01
    if lw_fehlt:
        fS = (MHWS + h[0] - ml) / (MHWS - MLref)
        fN = ((MHWN + (h[1] if h[1] is not None else h[0]) - ml) / (MHWN - MLref)
              if MHWN > MLref + .01 else fS)
    else:
        SRs = SR + (dMHWS - dMLWS)
        NRs = NR + (dMHWN - dMLWN)
        if SRs <= 0:
            SRs = max(0.10, 0.10 * SR)
        fS = SRs / SR
        fN = NRs / NR if NR > .01 else fS
    fS = max(.02, min(3., fS))
    fN = max(.02, min(3., fN))
    fD = .5 * (fS + fN)

    M2, S2 = ref_con.get('M2', (0, 0))[0], ref_con.get('S2', (0, 0))[0]
    if M2 <= 0:
        return None
    su, di = fS * (M2 + S2), fN * (M2 - S2)
    M2n, S2n = max(0, .5 * (su + di)), max(0, .5 * (su - di))
    rM = M2n / M2 if M2 > 0 else fS
    rS = S2n / S2 if S2 > 0 else fS

    v = [x for x in t if x is not None]
    dt = (sum(v) / len(v) / 60.0 + dz) if v else 0.0

    out = {}
    for c, (a, g) in ref_con.items():
        if c == 'M2':
            na = M2n
        elif c == 'S2':
            na = S2n
        elif c in SEMI_M:
            na = a * rM
        elif c == 'K2':
            na = a * rS
        elif c in SHALLOW:
            na = a * rM * rM
        elif c in DIURNAL:
            na = a * fD
        elif c in LANGZEIT:
            na = a
        else:
            na = a * fD
        sp = SPEED.get(c, 0.0)
        out[c] = (round(na, 4), round((g + sp * dt) % 360, 2))
    return dict(con=out, fS=fS, fN=fN, dt=dt, M2n=M2n, S2n=S2n,
                pegel_sek=[MHWS + dMHWS, MHWN + dMHWN, MLWN + dMLWN, MLWS + dMLWS])


def lies_unsere():
    """att -> dict(start, ni, ende, name, mer, tz, z0)."""
    L = open(TXT, encoding='iso-8859-1').read().split('\n')
    out, att, start = {}, None, None
    for i, l in enumerate(L):
        if l.startswith('# att_number:'):
            att, start = l.split(':', 1)[1].strip(), i
        elif att and re.match(r'^[+-]\d\d:\d\d :', l):
            ende = i + 2
            while ende < len(L) and not (L[ende].startswith('# BEGIN HOT')
                                         or L[ende].startswith('# att_number:')):
                ende += 1
            mer, tz = L[i].split(' :', 1)
            out[att] = dict(start=start, ni=i - 1, ende=ende, name=L[i - 1].strip(),
                            mer=mer, tz=tz, z0=float(L[i + 1].split()[0]))
            att = None
    return L, out


def main():
    schreiben = '--write' in sys.argv
    gruppen = lies_gruppen()
    buch = lies_buch()
    donor = lies_donor()
    L, unsere = lies_unsere()

    print('Bezugshaefen -- gerechneter Springhub 2*(M2+S2) gegen den im Buch gedruckten:')
    pub = {}
    for g in gruppen:
        pub.setdefault(g['ref'], g['pegel'])
    for ref in sorted(donor, key=lambda x: key(x)):
        d = donor[ref]
        M2 = d['con'].get('M2', (0, 0))[0]
        S2 = d['con'].get('S2', (0, 0))[0]
        p = pub.get(ref)
        if not p:
            continue
        SRb = p[0] - p[3]
        SRr = 2 * (M2 + S2)
        print(f'  {ref:5s} {d["name"][:38]:38s} Buch {SRb:5.2f} m  gerechnet {SRr:5.2f} m'
              f'  {"" if SRb < .01 else f"{SRr / SRb:5.2f}x"}')

    print(f'\n{"att":8s} {"Station":34s} {"fS":>6s} {"fN":>6s} {"dt/h":>6s}  Bezug')
    neu, uebersprungen = {}, []
    for att in sorted(unsere, key=lambda a: key(a)):
        b = unsere[att]
        batt = VERSATZ.get(att, att)
        row = buch.get(batt)
        if row is None:
            uebersprungen.append((att, b['name'], 'keine Buchzeile'))
            continue
        if row['roh'][4] == 'S':
            uebersprungen.append((att, b['name'], 'im Buch selbst Standardhafen'))
            continue
        g = gruppe(batt, gruppen)
        if g is None or g['ref'] not in donor:
            uebersprungen.append((att, b['name'],
                                  f'kein Bezugsdatensatz ({g["name"] if g else "keine Gruppe"})'))
            continue
        zs = zone_sec(batt)
        if zs is None:
            uebersprungen.append((att, b['name'], 'keine Zone'))
            continue
        dz = ZONE_REF[g['ref']] - zs
        tr = transfer(donor[g['ref']]['con'], g['pegel'], row['h'], row['t'],
                      dz=dz, ml=row['ml'])
        if tr is None:
            uebersprungen.append((att, b['name'], 'Bezug ohne M2'))
            continue
        tr['ref'] = g['ref']
        tr['refname'] = g['name']
        tr['row'] = row
        tr['dz'] = dz
        neu[att] = tr

    for att in sorted(neu, key=lambda a: key(a)):
        t = neu[att]
        print(f'{att:8s} {unsere[att]["name"][:34]:34s} {t["fS"]:6.2f} {t["fN"]:6.2f} '
              f'{t["dt"]:6.2f}  {t["refname"]}')
    print(f'\n{len(neu)} Stationen neu berechnet, {len(uebersprungen)} uebersprungen.')
    for a, n, warum in uebersprungen:
        print(f'  {a:8s} {n[:40]:40s} {warum}')

    if not schreiben:
        print('\n(Probelauf -- nichts geschrieben. Mit --write ausfuehren.)')
        return

    sich = f'{HARM}/backup/harmonics_att_np202_secondary_pre_rebuild_{date.today():%Y%m%d}.txt'
    shutil.copy(TXT, sich)
    print(f'\nSicherung: {sich}')

    reihenfolge = [c for c in ordnung(L)]
    # Rueckwaerts nach ZEILENNUMMER, nicht nach att -- in der Datei stehen
    # einige Stationen nicht in Nummernfolge (2551 hinter 2564, 2997 hinter
    # 3456). Nach att zu sortieren verschiebt sonst fremde Bloecke.
    for att in sorted(neu, key=lambda a: unsere[a]['start'], reverse=True):
        t, b = neu[att], unsere[att]
        d = donor[t['ref']]
        p = t['row']
        MHWS, MHWN, MLWN, MLWS = t['pegel_sek']
        z0 = p['ml'] if p['ml'] is not None else round(
            (MHWS + MHWN + MLWN + MLWS) / 4, 2)
        kopf = [
            f'# att_number: {att}',
            f'# note: NP202 Part II Sekundaerhafen-Transfer von {d["name"]} '
            f'(att {t["ref"]}).',
            f'# note: fS={t["fS"]:.2f} fN={t["fN"]:.2f} dt={t["dt"] * 60:+.0f}min '
            f'(davon {t["dz"] * 60:+.0f}min Zonenversatz), skaliert gegen die',
            f'# note: publizierten Pegel [{MHWS:.1f}, {MHWN:.1f}, {MLWN:.1f}, '
            f'{MLWS:.1f}] des Gruppenkopfs.',
            f'# note: 20260805 neu abgeleitet aus np202_part2_stationen.tsv '
            f'(Buchzeile {VERSATZ.get(att, att)}).',
        ]
        alt = L[b['start']:b['ni']]
        behalten = [x for x in alt if not (
            x.startswith('# att_number:') or x.startswith('# note: NP202 Part II')
            or re.match(r'# note: fS=', x) or x.startswith('# note: publizierten')
            or x.startswith('# note: 2026'))]
        rumpf = [b['name'], f'{d["mer"]} :{b["tz"]}', f'{z0:.4f} meters']
        for c in reihenfolge:
            if c in t['con']:
                a, g = t['con'][c]
                rumpf.append(f'{c:<15s} {a:7.4f} {g:7.2f}')
            else:
                rumpf.append('x 0 0')
        L[b['start']:b['ende']] = kopf + behalten + rumpf
    open(TXT, 'w', encoding='iso-8859-1').write('\n'.join(L))
    print(f'{len(neu)} Stationen geschrieben.')


def ordnung(L):
    i = next(k for k, l in enumerate(L) if l.startswith('# Constituent speeds'))
    out = []
    for l in L[i + 1:]:
        if not l.strip():
            continue
        if l.startswith('#'):
            continue
        m = re.match(r'^(\S+)\s+([\d.]+)\s*$', l.strip())
        if not m:
            break
        out.append(m.group(1))
        if len(out) == 175:
            break
    return out


if __name__ == '__main__':
    main()
