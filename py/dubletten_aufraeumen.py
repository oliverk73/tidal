#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Raeumt doppelte Saetze weg -- entschieden an der Tafel, nicht am Rang.

Der Bestand soll je Pegel einen Satz fuehren, und zwar den genauesten.
"Der genaueste" ist eine gemessene Groesse: der Fehler gegen eine
unabhaengige Quelle, in Metern und im Verhaeltnis zum Tidenhub. Ein
erster Anlauf hat stattdessen nach Herkunft sortiert -- uTide vor
TICON-4 vor den alten Verteilungen -- und damit 1174 von 1258 Saetzen
allein ueber den Rang geloescht. Das ist die Abkuerzung, die der
Bestand nicht haben soll: die Schwelle "Kurven unter zehn Prozent
verschieden" klingt eng, sind bei vier Metern Hub aber vierzig
Zentimeter, und welcher der beiden Saetze naeher an der Tafel liegt,
sagt sie gerade nicht.

Gemessen wird deshalb aus den Guetetabellen, die die Pruefwerkzeuge
je Quelle hinterlassen (harmonics/help/*_qualitaet.csv): dort steht
zu jedem Satz der RMS gegen die Tafel des Amtes, der groesste
Einzelfehler, der Zeitversatz und der Hub. Verglichen wird nur
innerhalb derselben Tabelle -- gleiche Station, gleiches Jahr,
dieselbe Tafel.

Geloescht wird ein Satz nur, wenn er DEUTLICH schlechter ist:
mindestens drei Zentimeter mehr RMS, oder doppelt so viel bei
mindestens einem Zentimeter Unterschied -- oder deutlich mehr
Zeitfehler.

Die Zeit musste dazu, weil der RMS sie kaum sieht. In Helgoland liegt
der TICON-Satz vierzig Minuten zu spaet, und im RMS macht das 31.0
gegen 29.8 Zentimeter: gut ein Zentimeter, weit unter jeder Schwelle.
Der Grund ist der Windstau, der in der Deutschen Bucht dreissig
Zentimeter ausmacht und den Zeitfehler unter sich begraebt. Dasselbe
bei Arica, wo ein um den Faktor 2.4 falsches S2 im RMS nur 1.1
Zentimeter kostete. Der Zeitversatz steht ohnehin in jeder Zeile der
Guetetabellen; er war nur nie gelesen worden.

Die Zeit schuetzt auch: liegt der Verlierer zwanzig Minuten NAEHER an
der Reihe als der Sieger, bleibt er stehen, egal was der RMS sagt.
Sonst loescht die Runde den puenktlichen Satz zugunsten eines
glatteren. Die drei Zentimeter sind
dieselbe Untergrenze wie in py/tafel_kaputt.py -- darunter misst man
die Tafel, nicht den Satz.

Wo beide gleich gut sind, bleibt beides stehen. Das ist Absicht: die
Dublette kostet nichts als einen Eintrag in der Liste, eine falsche
Loeschung kostet den besseren Satz.

Gruppiert wird wahlweise nach dem Namen (Vorgabe) oder nach den Haufen
aus py/pegel_dubletten.py (--haufen). Der zweite Weg findet auch die
Dubletten, die in verschiedenen Sprachen heissen -- und braucht deshalb
einen Nachweis, DASS es derselbe Pegel ist, bevor etwas geloescht wird.
Bei gleichem Namen liegt der Nachweis im Namen. Sonst muss ihn eine der
Spuren liefern:

  L  beide standen einmal auf derselben Position (positions_locked.csv)
  H/K  einer der beiden ist eine gerechnete Uebertragung -- dann darf
     auch nur dieser geloescht werden, nie der gemessene Satz

Bleibt als Beleg nur "liegt nah beieinander und sieht aehnlich aus",
wird nichts geloescht. Moji und Shimonoseki liegen 1.5 km auseinander,
ihre Kurven unterscheiden sich um 4 Prozent, und sie sind zwei Pegel.

Usage: python3 py/dubletten_aufraeumen.py [--csv] [--offen] [--haufen]
       --offen   auch die Gruppen ohne Messung auflisten
       --haufen  nach py/pegel_dubletten.py gruppieren statt nach dem Namen
"""
from __future__ import annotations

import collections
import csv
import glob
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from health_check import load_records, km, curve_diff, ROOT       # noqa: E402

HELP = os.path.join(ROOT, 'harmonics/help')
HAUFEN = os.path.join(HELP, 'pegel_dubletten.csv')
HANDBELEG = os.path.join(HELP, 'dubletten_handbeleg.csv')
NAH_KM = 1.0          # weiter auseinander ist es nicht derselbe Pegel
GLEICH = 0.10         # ab hier ist es ein Widerspruch, keine Dublette
MIND_M = 0.03         # so viel mehr RMS muss der Verlierer haben
FAKTOR = 2.0          # oder so viel mal so viel
MIND_FAKTOR_M = 0.01  # und dann immer noch diesen Abstand
UNSINN_M = 1.00       # darueber misst man die Reihe, nicht den Satz
TAUB = 0.25           # liegt schon der Sieger so weit daneben, taugt die Reihe nicht
MIND_MIN = 25         # so viele Minuten mehr Zeitfehler machen einen Satz schlechter
SPRUNG_MIN = 240      # darueber ist es ein Periodensprung, kein Uhrfehler
# Die Zahl haengt an der Aufloesung: py/messreihe_qualitaet.py sucht den
# Zeitversatz in Zehn-Minuten-Schritten. Bei einer Schwelle von genau 20
# entscheiden zwei Rasterschritte, und ein Satz mit wahren 15 Minuten
# faellt schon. 25 verlangt drei Schritte -- der erste Wert, der zaehlt,
# ist 30.


def messungen():
    """-> {(Satzname, Datei): [(Station, Jahr, Quelle, rms, max, hub, blind)]}.

    "blind" heisst: dieser Satz wurde aus eben dieser Reihe gefittet und
    hat auf ihr trainiert (Spalte eigen aus py/messreihe_qualitaet.py).
    Ein solcher Satz darf verlieren, aber nicht gewinnen -- sein guter
    Wert waere nur die Erinnerung an die eigenen Trainingsdaten. Wurde
    ausserhalb des Fitfensters gemessen (Spalte ausserhalb), zaehlt er
    wieder voll.
    """
    out = collections.defaultdict(list)
    for pfad in sorted(glob.glob(os.path.join(HELP, '*qualitaet*.csv'))):
        quelle = os.path.basename(pfad).replace('_qualitaet.csv', '')
        for r in csv.DictReader(open(pfad, encoding='utf-8')):
            try:
                rms = float(r['rms_m'])
            except (KeyError, TypeError, ValueError):
                continue
            if not math.isfinite(rms) or rms > UNSINN_M:
                # Ein RMS von hunderten Metern heisst nicht, dass der Satz
                # schlecht ist, sondern dass die Reihe nicht stimmt --
                # Millimeter als Meter gelesen etwa. Solche Zeilen duerfen
                # nichts entscheiden.
                continue
            hub = None
            try:
                hub = float(r['hub_m']) or None
            except (KeyError, TypeError, ValueError):
                pass
            gross = None
            try:
                gross = float(r['max_m'])
            except (KeyError, TypeError, ValueError):
                pass
            zeit = None
            try:
                zeit = float(r['zeit_min'])
            except (KeyError, TypeError, ValueError):
                pass
            eigen = r.get('eigen') == '1'
            draussen = r.get('ausserhalb', 'nein') == 'ja'
            out[(r.get('satz', ''), r.get('datei', ''))].append(
                (r.get('station', ''), r.get('jahr', ''), quelle, rms, gross, hub,
                 eigen and not draussen, eigen and draussen, zeit))
    return out


def gruppen(recs):
    """-> Gruppen gleichen Namens, die wirklich derselbe Pegel sind."""
    nach = collections.defaultdict(list)
    for r in recs:
        nach[r['name']].append(r)
    out = []
    for name, alle in sorted(nach.items()):
        for menge in ([r for r in alle if not r['current']],
                      [r for r in alle if r['current']]):
            if len(menge) < 2:
                continue
            if max(km(a, b) for i, a in enumerate(menge) for b in menge[i + 1:]) >= NAH_KM:
                continue
            if max(curve_diff(a, b)[1] for i, a in enumerate(menge)
                   for b in menge[i + 1:]) >= GLEICH:
                continue
            out.append((name, menge))
    return out


def handbeleg():
    """-> Menge der von Hand bestaetigten Namenspaare.

    Die Spuren finden Haufen ohne Ruecksicht auf den Namen, der Beleg
    verlangt danach den vollen Namen -- und daran haengen 228 Saetze,
    die an der Tafel messbar schlechter sind und trotzdem stehen
    bleiben, weil ihr Name einen Zusatz traegt: "Belan Point, Menai
    Strait" neben "Fort Belan" auf derselben Position, "St. Malo" neben
    "Saint-Malo", die halbe NOAA-Reihe mit Bucht- oder Flussnamen im
    Titel.

    Ein Namensvergleich, der das automatisch aufloest, ist nicht in
    Sicht: derselbe Zusatz, der hier ueberfluessig ist, unterscheidet
    anderswo zwei Pegel ("Elsfleth (Weser)" und "Elsfleth Ohrt
    (Hunte)"). Also entscheidet ein Mensch, und zwar einmal je Paar,
    nachpruefbar im Baum: harmonics/help/dubletten_handbeleg.csv mit den
    Spalten name_a, name_b, begruendung.

    Bestaetigt wird damit NUR die Identitaet -- wer bleibt, entscheidet
    weiterhin die Messung. Ein Handbeleg ohne freien Massstab loescht
    nichts (Bach Long Vi, Mys Menaputsy), und ein blinder Sieger gewinnt
    auch mit Handbeleg nicht (Bahia Coliumo).

    Der Beleg haengt an den Namen, nicht an der Haufennummer: die
    vergibt py/pegel_dubletten.py bei jedem Lauf neu, und nach einer
    Loeschung stuende die Bestaetigung auf einer fremden Gruppe.
    """
    if not os.path.exists(HANDBELEG):
        return set()
    out = set()
    for r in csv.DictReader(open(HANDBELEG, encoding='utf-8')):
        a, b = (r.get('name_a') or '').strip(), (r.get('name_b') or '').strip()
        if a and b and a != b:
            out.add(frozenset((a, b)))
    return out


def _hand_belegt(menge, bestaetigt):
    """Ist JEDES Namenspaar der Gruppe von Hand bestaetigt?

    Ein einzelnes bestaetigtes Paar reicht nicht: in einer Dreiergruppe
    hiesse das, dass der dritte Satz ueber ein fremdes Urteil mitgeloescht
    wird.
    """
    namen = sorted({r['name'] for r in menge})
    if len(namen) < 2:
        return False
    return all(frozenset((namen[i], namen[j])) in bestaetigt
               for i in range(len(namen)) for j in range(i + 1, len(namen)))


def haufen_gruppen(recs):
    """-> Gruppen aus py/pegel_dubletten.py, mit ihrem Identitaetsbeleg.

    Ketten werden uebersprungen: dort sind mehrere Pegel ueber gemeinsame
    Nachbarn zusammengewachsen, und welcher Satz zu welchem gehoert,
    entscheidet keine Guetetabelle.
    """
    if not os.path.exists(HAUFEN):
        sys.exit(f'{HAUFEN} fehlt -- erst python3 py/pegel_dubletten.py --csv')
    bestaetigt = handbeleg()
    nach_ort = {(r['file'], r['line']): r for r in recs}
    zeilen = collections.defaultdict(list)
    for row in csv.DictReader(open(HAUFEN, encoding='utf-8')):
        zeilen[row['haufen']].append(row)
    out = []
    for nr, rows in sorted(zeilen.items(), key=lambda t: int(t[0])):
        if rows[0].get('kette'):
            continue
        menge, abgeleitet = [], set()
        for row in rows:
            r = nach_ort.get((row['datei'], int(row['zeile'])))
            if r is None or r['name'] != row['name']:
                menge = []
                break
            menge.append(r)
            if row['abgeleitet']:
                abgeleitet.add(id(r))
        if len(menge) < 2:
            continue
        spur = rows[0]['spur']
        namen = rows[0]['namen']
        # Woran haengt die Identitaet? Verlangt wird der VOLLE Name, nicht
        # der Namensschluessel. Der Schluessel wirft Klammerzusaetze und
        # Woerter wie harbour/point/entrance weg, und genau die
        # unterscheiden oft zwei Pegel: "Chatham (Lock Approaches)" und
        # "Chatham, Medway River" fallen auf denselben Schluessel,
        # "Elsfleth (Weser)" und "Elsfleth Ohrt (Hunte)" liegen an zwei
        # Fluessen, und "Deokjeokdo Jinri" und "Deokjeokdo Bukri" sind
        # zwei Pegel auf einer Insel. Sonst muss die Altlage den Beleg
        # liefern oder der Umstand, dass einer der Saetze nur gerechnet ist.
        if len({r['name'] for r in menge}) == 1:
            beleg = 'Name'
        elif _hand_belegt(menge, bestaetigt):
            beleg = 'Hand'
        elif 'L' in spur:
            beleg = 'Altlage'
        elif ('H' in spur or 'K' in spur) and abgeleitet:
            beleg = 'nur abgeleitet'
        else:
            beleg = None
        out.append((menge[0]['name'], menge,
                    dict(nr=nr, spur=spur, namen=namen, beleg=beleg,
                         abgeleitet=abgeleitet)))
    return out


def zeitlich_schlechter(zeit, best):
    """Liegt der Satz deutlich weiter von der Reihe entfernt als der Sieger?

    Der Vergleich taugt nur, wenn der Sieger selbst nahe an der Reihe
    liegt. In Jamestown auf St. Helena messen sich -490 und -440 Minuten:
    beide Saetze sind gleich unbrauchbar, und die fuenfzig Minuten
    Unterschied dazwischen sind Rauschen einer Reihe, in der die
    Versatzsuche um halbe Perioden springt. Steht der Sieger nicht selbst
    innerhalb der Schwelle, entscheidet die Zeit nichts.
    """
    if zeit is None or best is None or abs(best) > MIND_MIN:
        return False
    if abs(zeit) > SPRUNG_MIN:
        # Jenseits von vier Stunden ist es kein Uhrfehler mehr, sondern ein
        # halber Periodensprung: Sorel am Sankt-Lorenz-Strom misst -720
        # Minuten, also genau zwoelf Stunden. Solche Werte entscheiden
        # nichts -- wenn der Satz wirklich schlecht ist, sagt es der RMS.
        return False
    return abs(zeit) - abs(best) >= MIND_MIN


def deutlich_schlechter(rms, best, nur_absolut=False):
    """Ist der Satz gegenueber dem besten deutlich schlechter?

    nur_absolut gilt, wenn der Sieger aus derselben Quelle stammt wie die
    Vergleichsreihe, nur ausserhalb seines Fitfensters gemessen wurde:
    die JMA-Tafel fuer 2026 gegen eine Anpassung an die JMA-Tafeln
    2011-2025. Das ist keine Zirkularitaet mehr, aber auch keine
    Unabhaengigkeit -- der Sieger zielt auf genau die Konstanten, die
    die Reihe erzeugt haben. Abashiri kommt so auf 1.05 cm gegen 2.30 cm
    fuer TICON-4, und ueber die Verhaeltnisregel wuerde TICON-4 wegen
    eines Zentimeters geloescht. Deshalb zaehlt dort nur der absolute
    Abstand.
    """
    if nur_absolut:
        return rms - best >= MIND_M
    return rms - best >= MIND_M or (rms >= FAKTOR * best and rms - best >= MIND_FAKTOR_M)


def main(argv):
    mess = messungen()
    recs = [r for r in load_records() if r['lat'] is not None]
    if '--haufen' in argv:
        quelle = haufen_gruppen(recs)
    else:
        quelle = [(n, m, dict(beleg='Name', spur='', namen='gleich',
                              abgeleitet=set())) for n, m in gruppen(recs)]
    weg, gleichauf, ohne, zirkulaer, unbelegt, taub = [], [], [], [], [], []
    for name, menge, meta in quelle:
        if meta['beleg'] is None:
            unbelegt.append((name, menge))
            continue
        # Messungen der Gruppe nach Tabelle buendeln: nur was gegen
        # dieselbe Station im selben Jahr gemessen wurde, ist vergleichbar.
        nach_tabelle = collections.defaultdict(dict)
        for r in menge:
            for (station, jahr, quelle, rms, gross, hub, blind, halbblind,
                 zeit) in mess.get((r['name'], os.path.basename(r['file'])), ()):
                nach_tabelle[(quelle, station, jahr)][id(r)] = (rms, gross, hub,
                                                                blind, halbblind,
                                                                zeit)
        vergleichbar = {k: v for k, v in nach_tabelle.items() if len(v) == len(menge)}
        if not vergleichbar:
            ohne.append((name, menge))
            continue
        # Mehrere Jahre derselben Tafel: den Median je Satz nehmen.
        # Blind ist ein Satz JE TABELLE, nicht ueberhaupt. In Heysham
        # liegen drei Massstaebe nebeneinander -- die BODC-Reihe, eine
        # aeltere BODC-Jahresdatei und die tidetimes-Tafel --, und jeder
        # der drei Saetze ist in genau einem davon trainiert: der
        # dwf-Satz gegen BODC, der uTide-Satz gegen die 2024er Reihe, der
        # tidetimes-Satz gegen tidetimes. Wer das ueber alle Tabellen
        # verodert, erklaert alle drei fuer blind und faellt aus der
        # Wertung -- obwohl fuer jeden ein unabhaengiger Massstab
        # danebenliegt. Gezaehlt werden deshalb nur die Tabellen, in
        # denen ein Satz NICHT trainiert hat; blind bleibt er nur, wenn
        # es keine solche gibt.
        werte = collections.defaultdict(list)
        blindwerte = collections.defaultdict(list)
        zeiten = collections.defaultdict(list)
        blind = collections.defaultdict(bool)
        halb = collections.defaultdict(bool)
        hub = None
        for k, v in vergleichbar.items():
            for i, (rms, _gross, h, b, hb, zt) in v.items():
                # halbblind (auf der Reihe trainiert, aber ausserhalb des
                # Fitfensters gemessen) ist NICHT blind -- es muss deshalb
                # ausserhalb des Zweigs gesetzt werden, sonst faellt die
                # Nur-Absolut-Regel weg, und ein Sieger, der die Reihe
                # selbst erzeugt hat, gewinnt schon mit anderthalb
                # Zentimetern.
                halb[i] = halb[i] or hb
                if b:
                    blindwerte[i].append(rms)
                else:
                    werte[i].append(rms)
                    if zt is not None:
                        zeiten[i].append(zt)
                hub = hub or h
        for r in menge:
            i = id(r)
            if not werte[i]:
                blind[i] = True
                werte[i] = blindwerte[i]
        med = {i: sorted(v)[len(v) // 2] for i, v in werte.items()}
        zmed = {i: sorted(v)[len(v) // 2] for i, v in zeiten.items() if v}
        # Wer auf der Reihe trainiert hat, ist kein Massstab und wird auch
        # nicht geloescht. Verglichen wird gegen den besten der uebrigen --
        # sonst faellt eine ganze Dreiergruppe aus, nur weil einer davon
        # nicht beurteilbar ist.
        frei = [r for r in menge if not blind[id(r)]]
        if not frei:
            zirkulaer.append((name, menge))
            continue
        best = min(med[id(r)] for r in frei)
        sieger = [r for r in frei if med[id(r)] == best][0]
        if zmed.get(id(sieger)) is not None and abs(zmed[id(sieger)]) > SPRUNG_MIN:
            # Liegt schon der Sieger Stunden neben der Reihe, entscheidet
            # die Gruppe nichts. Georgetown auf Ascension misst +330
            # Minuten fuer den Sieger und -410 fuer die beiden anderen --
            # dort stimmt die Reihe nicht, nicht die Saetze.
            taub.append((name, menge))
            continue
        if hub and best > TAUB * hub:
            # Saint-Louis am Senegal: der beste Satz kommt auf 74.7 cm RMS
            # bei 1.35 m Hub, die beiden anderen auf 80.4 und 80.6. Der
            # Abstand reicht formal fuer eine Loeschung, aber gemessen wird
            # hier der Fluss, nicht der Satz.
            taub.append((name, menge))
            continue
        if len(frei) < len(menge):
            zirkulaer.append((name, [r for r in menge if blind[id(r)]]))
        zbest = zmed.get(id(sieger))
        for v in frei:
            if v is sieger:
                continue
            zv = zmed.get(id(v))
            if zeitlich_schlechter(zbest, zv):
                # Der Verlierer trifft die Reihe zeitlich deutlich besser als
                # der Sieger. Dann ist der RMS kein Urteil, sondern ein
                # Zufall der Reihe -- beide bleiben.
                gleichauf.append((v, sieger, med[id(v)], best, hub))
            elif (not deutlich_schlechter(med[id(v)], best, halb[id(sieger)])
                    and not zeitlich_schlechter(zv, zbest)):
                gleichauf.append((v, sieger, med[id(v)], best, hub))
            elif meta['beleg'] == 'nur abgeleitet' and id(v) not in meta['abgeleitet']:
                # Die Gruppe haelt nur zusammen, weil einer der Saetze eine
                # Rechnung ist. Dann darf auch nur die Rechnung weichen --
                # ein gemessener Satz waere hier kein Duplikat, sondern ein
                # Nachbar, den die Spur faelschlich eingesammelt hat.
                gleichauf.append((v, sieger, med[id(v)], best, hub))
            else:
                weg.append((v, sieger, med[id(v)], best, hub, len(vergleichbar),
                            meta, zv, zbest))

    print(f'{len(weg)} Saetze sind an der Tafel deutlich schlechter und koennen weg')
    if taub:
        print(f'{len(taub)} Haufen bleiben stehen -- schon der beste Satz liegt '
              f'ueber {TAUB * 100:.0f} % des Hubs daneben, da misst die Reihe sich selbst')
    if unbelegt:
        print(f'{len(unbelegt)} Haufen bleiben unangetastet -- nah und '
              f'aehnlich, aber kein Beleg, dass es derselbe Pegel ist')
    print(f'{len(gleichauf)} sind gleichauf -- beide bleiben')
    print(f'{len(zirkulaer)} Saetze bleiben unbeurteilt (auf der Reihe trainiert)')
    print(f'{len(ohne)} Gruppen haben keine Messung')
    d = collections.Counter(os.path.basename(v['file']) for v, *_ in weg)
    print(f'\n{"Datei":42} {"geht":>6}')
    for k, n in d.most_common():
        print(f'{k[:42]:42} {n:6}')
    print(f'\nBeispiele:')
    for v, s, rms, best, hub, n, _meta, _zv, _zb in sorted(
            weg, key=lambda x: -(x[2] - x[3]))[:12]:
        h = f'{(rms - best) / hub * 100:4.1f} % Hub' if hub else '   ?'
        print(f'  {v["name"][:34]:34} {rms * 100:6.1f} cm gegen {best * 100:5.1f} cm '
              f'({h})  {os.path.basename(v["file"])[:24]} raus, '
              f'{os.path.basename(s["file"])[:24]} bleibt')

    if '--offen' in argv:
        print('\nGruppen ohne Messung:')
        laender = collections.Counter(n.split(',')[-1].strip() for n, _m in ohne)
        for land, c in laender.most_common(20):
            print(f'  {c:5}  {land}')

    if '--csv' in argv:
        p = os.path.join(HELP, 'dubletten_loeschen.csv')
        with open(p, 'w', newline='', encoding='utf-8') as fh:
            w = csv.writer(fh)
            w.writerow(['datei', 'name', 'fehler_prozent', 'begruendung'])
            for v, s, rms, best, hub, n, meta, zv, zb in weg:
                anteil = (rms / hub * 100) if hub else 0.0
                w.writerow([v['file'], v['name'], f'{anteil:.1f}',
                            f'Dublette: {km(v, s) * 1000:.0f} m von "{s["name"]}" '
                            f'({os.path.basename(s["file"])}), Kurve '
                            f'{curve_diff(v, s)[1] * 100:.0f} % gleich. An der Tafel '
                            f'({n} Vergleich(e)) {rms * 100:.1f} cm RMS gegen '
                            f'{best * 100:.1f} cm' +
                            (f', Zeitversatz {zv:+.0f} gegen {zb:+.0f} min'
                             if zv is not None and zb is not None else '') +
                            (f' [Spur {meta["spur"]}, Beleg {meta["beleg"]}]'
                             if meta['spur'] else '') +
                            (f' bei {hub:.2f} m Hub' if hub else '') + '.'])
        print(f'\n-> {p}')
        q = os.path.join(HELP, 'dubletten_gleichauf.csv')
        with open(q, 'w', newline='', encoding='utf-8') as fh:
            w = csv.writer(fh)
            w.writerow(['name', 'datei_a', 'rms_a_cm', 'datei_b', 'rms_b_cm', 'hub_m'])
            for v, s, rms, best, hub in gleichauf:
                w.writerow([v['name'], os.path.basename(v['file']), f'{rms * 100:.1f}',
                            os.path.basename(s['file']), f'{best * 100:.1f}',
                            f'{hub:.2f}' if hub else ''])
        print(f'-> {q}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
