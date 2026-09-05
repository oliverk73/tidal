#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Misst Saetze gegen die Pegelreihen, die schon im Haus liegen.

Die Guetepruefung gab es bisher nur je Quelle -- chs_qualitaet gegen die
kanadischen Tafeln, bom_qualitaet gegen die australischen, dazu SHN,
SHOA, SEMAR, CICESE, DHN, Hidronav, CPA. Zusammen decken sie rund 300
der 1119 Dublettengruppen ab. Fuer den Rest fehlte der Massstab, und
ohne Massstab wurde zuletzt nach Herkunft entschieden -- eine
Abkuerzung, die der Bestand nicht haben soll.

Der Massstab liegt aber da: in water_levels/ stehen 43 GB Pegelreihen,
darunter genau die grossen Loecher -- JMA_Japan mit 239 Stationen ueber
fuenfzehn Jahre, Norway_Kartverket, India_IOC, Portugal_IOC, die
UHSLC-Reihen fuer Bangladesch, Myanmar und Mosambik.

Zugeordnet wird ueber station_id_context: die Saetze, die wir selbst
aus einer Reihe gefittet haben, nennen deren Kennung ("JMA AS",
"UHSLC-878", "IOC-oran"), und damit ist auch die Position bekannt. Um
diesen Anker herum werden alle Saetze im Umkreis gegen dieselbe Reihe
gerechnet.

Zwei Dinge, ohne die die Zahl nichts wert waere:

  Der Satz, der AUS dieser Reihe stammt, ist gegen sie kein
  unabhaengiger Kandidat -- er hat auf ihr trainiert. Die Spalte
  "eigen" markiert ihn; ein Vergleich, in dem er gewinnt, beweist
  nichts. Wo die Reihe ueber sein Fitfenster hinausreicht, wird
  ausserhalb gemessen, und die Spalte "ausserhalb" sagt es.

  Die Reihe ist gemessen, nicht vorhergesagt: Wind und Luftdruck
  stehen mit drin. Der RMS liegt deshalb hoeher als gegen eine Tafel,
  meist um zehn bis zwanzig Zentimeter Sturmanteil. Fuer den Vergleich
  ZWEIER Saetze an derselben Reihe macht das nichts -- der Sturm ist
  fuer beide derselbe und faellt in der Differenz heraus. Absolut mit
  den Tafelwerten vergleichbar sind diese Zahlen aber nicht.

Usage: python3 py/messreihe_qualitaet.py [--km 3] [--tage 365]
                                         [--ordner JMA_Japan]
                                         > harmonics/help/messreihe_qualitaet.csv
"""
from __future__ import annotations

import collections
import csv
import datetime as dt
import glob
import json
import math
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from health_check import load_records, km, active_files, ROOT, MERIDIAN   # noqa: E402

TCD = '/usr/share/xtide'
REIHEN = os.path.join(ROOT, 'water_levels')
SCHRITT_MIN = 10             # Aufloesung der Vorhersage
SUCHE_MIN = 720              # Zeitversatz wird in diesem Rahmen gesucht
MIND_PUNKTE = 2000
# Hoch- und Niedrigwassertafeln haben nur vier Werte am Tag, also rund
# 1400 im Jahr. Fuer sie gilt eine eigene Schwelle: die Punkte liegen
# dafuer genau auf den Scheiteln, wo eine Kurve am meisten aussagt.
MIND_PUNKTE_TAFEL = 600
TAFELREIHEN = ('NewZealand_LINZ', 'UK_tidetimes')


def kopfdaten():
    """-> {(datei, zeile): (station_id_context, fitzeitraum, quelle)}."""
    out = {}
    for path in active_files():
        lines = open(os.path.join(ROOT, path), encoding='iso-8859-1').read().split('\n')
        sid = zeit = quelle = None
        for k, line in enumerate(lines):
            if line.startswith('# station_id_context:'):
                sid = line.split(':', 1)[1].strip()
            elif line.startswith('# source:'):
                quelle = line.split(':', 1)[1].strip()
            elif line.startswith('# utide:'):
                m = re.search(r'period=(\d{4}-\d\d-\d\d)\.\.(\d{4}-\d\d-\d\d)', line)
                if m:
                    zeit = (m.group(1), m.group(2))
            elif (line and not line.startswith('#') and k + 1 < len(lines)
                  and MERIDIAN.match(lines[k + 1])):
                out[(path, k + 1)] = (sid, zeit, quelle or '')
                sid = zeit = quelle = None
    return out


# Woerter, die in Stationsnamen so haeufig vorkommen, dass sie als
# Kennung nichts taugen. Ohne diese Liste griff "SHOM-PORT-TUDY" ueber
# das Paar (SHOM, PORT) nach ERQUY_PORT.csv, 250 km entfernt, und
# "pointe_noire-234a-cog-uhslc_rq" ueber (UHSLC, POINTE) nach
# h272_pointe_a_pitre.csv -- Pointe-a-Pitre in Guadeloupe statt
# Pointe-Noire im Kongo, ein halber Erdumfang. Beide Messungen kamen mit
# 119 Metern RMS heraus und waren damit zwar unschaedlich (ueber
# UNSINN_M wird nichts entschieden), aber sie verstopften die Tafel.
UNSPEZIFISCH = {
    'PORT', 'PORTS', 'POINTE', 'POINT', 'PUERTO', 'PORTO', 'HAFEN', 'HARBOUR',
    'HARBOR', 'BAIE', 'BAY', 'CAP', 'CAPE', 'ILE', 'ILES', 'ISLA', 'ISLAND',
    'ISLANDS', 'RIVER', 'RIO', 'SAN', 'SANTA', 'SANTO', 'SAINT', 'ST', 'NORD',
    'SUD', 'EST', 'OUEST', 'NORTH', 'SOUTH', 'EAST', 'WEST', 'NEW', 'LA', 'LE',
    'LES', 'LOS', 'DU', 'DE', 'DEL', 'DER', 'DAS', 'PULAU', 'TELUK', 'KUALA',
    'TANJUNG', 'MUARA', 'BANDAR', 'W', 'H', 'WL', 'WLO', 'WLP', 'CSV', 'TXT',
}


def reihendateien(nur=None):
    """-> {(anbieter, kennung): pfad} fuer alles, was wir lesen koennen."""
    out = {}
    for pfad in glob.glob(os.path.join(REIHEN, '**', '*'), recursive=True):
        if not os.path.isfile(pfad) or os.path.splitext(pfad)[1] not in ('.csv', '.txt'):
            continue
        rel = os.path.relpath(pfad, REIHEN)
        ordner = rel.split(os.sep)[0]
        if nur and nur != ordner:
            continue
        stamm = os.path.splitext(os.path.basename(pfad))[0]
        teile = [t for t in re.split(r'[_\-. ]', stamm) if t]
        for anbieter in re.split(r'[_\-]', ordner):
            for t in teile:
                # Keine Mindestlaenge: die JMA-Kennungen heissen A0 und
                # B1, und eine Laengenregel hat den ganzen japanischen
                # Weg stillgelegt. Ausgeschlossen werden Woerter, nicht
                # kurze Kennungen.
                if t.upper() in UNSPEZIFISCH:
                    continue
                out.setdefault((anbieter.upper(), t.upper()), pfad)
        # JMA legt die Kennung allein in den Dateinamen (A0.txt).
        out.setdefault((ordner.upper(), stamm.upper()), pfad)
    return out


def lies(pfad):
    """-> [(unixzeit, hoehe_m)], grob von Ausreissern befreit."""
    return _sauber(_lies(pfad))


def _sauber(reihe, spanne=20.0, mindest_m=3.0):
    """Wirft heraus, was weit ausserhalb der Streuung liegt.

    Die irischen Rohreihen enthalten Spitzen von dreissig Metern --
    Sensorfehler, die den RMS einer ganzen Station unbrauchbar machen.
    Gemessen wird an der mittleren absoluten Abweichung vom Median, die
    ein einzelner Ausreisser nicht verschiebt.
    """
    if len(reihe) < 100:
        return reihe
    werte = sorted(h for _t, h in reihe)
    med = werte[len(werte) // 2]
    mad = sorted(abs(h - med) for h in werte)[len(werte) // 2] or 0.01
    grenze = max(mindest_m, spanne * mad)
    return [(t, h) for t, h in reihe if abs(h - med) <= grenze]


def _lies(pfad):
    if os.path.basename(os.path.dirname(pfad)).upper().startswith('JMA'):
        return _lies_jma(pfad)
    if 'bodc' in pfad:
        alle = _lies_bodc_alle(pfad)
        return alle if alle is not None else _lies_bodc(pfad)
    if pfad.endswith('.npz'):
        return _lies_npz(pfad)
    if 'Japan_JHOD' in pfad and jhod_kopf(pfad):
        return _lies_jhod(pfad)
    if 'NewZealand_LINZ' in pfad and linz_kopf(pfad):
        return _lies_linz(pfad)
    if pfad.endswith('.json') and os.sep + 'ea' + os.sep in pfad:
        return _lies_ea(pfad)
    if 'UK_tidetimes' in pfad and pfad.endswith('.json'):
        return _lies_tidetimes(pfad)
    return _lies_csv(pfad)


def _lies_tidetimes(pfad):
    """Die Hoch- und Niedrigwassertafeln von tidetimes.co.uk.

    678 Stationen liegen als JSON da -- Name, Lage, Zeitzone und eine
    Liste aus Datum, Uhrzeit, Hoehe und Art. Sie sind die Quelle, aus der
    672 unserer britischen Saetze mit UTide angepasst wurden, und wurden
    seither nie zurueckgemessen.

    Das ist ein gueltiger Pruefstein fuer die RECHNUNG: trifft unsere
    Anpassung die Tafel, hat der Fit die Quelle sauber wiedergegeben, und
    gebrochene Anpassungen, Zeitzonenfehler oder falsche Zuordnungen
    fallen auf. Als Schiedsrichter zwischen zwei Saetzen taugt sie nicht
    -- wer daraus gemacht wurde, gewinnt fast zwangslaeufig. Dafuer gibt
    es die Spalte eigen: solche Saetze duerfen daran scheitern, aber
    nichts gewinnen.

    Die Zeitbasis ist die Falle. Die Datei nennt als timezone
    "Europe/London", aber tidetimes.co.uk publiziert GANZJAEHRIG BST,
    also festes UTC+1 -- im Winter gibt es diese Stunde gar nicht. Wer
    die Zone nimmt, wie sie dasteht, liegt von Oktober bis Maerz eine
    Stunde daneben. Genau darauf ist schon der urspruengliche Einlesebatch
    hereingefallen (siehe py/refit_tidetimes_bst.py, das alle davon
    abgeleiteten Saetze deshalb neu angepasst hat), und beim ersten
    Anlauf hier noch einmal: die Messung fand als Kompromiss zwischen
    Sommer und Winter -30 Minuten und blies den RMS der eigenen
    Anpassungen von rund 5 auf 25 Zentimeter auf.

    Gemessen wird an den Scheiteln; was tidetimes zwischen ihnen
    kosinusfoermig interpoliert, geht damit nicht ein. Umgekehrt ist ein
    Hoehen-RMS an Scheiteln fuer Zeitfehler fast blind -- dort ist die
    Kurve flach. Fuer die Zeit taugt der Vergleich der Scheitelzeiten,
    nicht dieser RMS.
    """
    try:
        d = json.load(open(pfad, encoding='utf-8'))
    except Exception:
        return []
    zone = dt.timezone(dt.timedelta(hours=1))     # festes BST, siehe oben
    out = []
    for e in d.get('entries', ()):
        try:
            j, m, t = (int(x) for x in e['date'].split('-'))
            st, mi = (int(x) for x in e['time'].split(':'))
            h = float(e['height_m'])
        except (KeyError, ValueError, TypeError):
            continue
        try:
            out.append((dt.datetime(j, m, t, st, mi, tzinfo=zone).timestamp(), h))
        except ValueError:
            continue
    out.sort()
    return out


def tidetimes_reihen(nur=None):
    """Je tidetimes-Station eine Reihe; Name und Lage stehen in der Datei."""
    out = []
    if nur and nur != 'UK_tidetimes':
        return out
    for pfad in sorted(glob.glob(os.path.join(REIHEN, 'UK_tidetimes', '*.json'))):
        try:
            d = json.load(open(pfad, encoding='utf-8'))
            la, lo = float(d['lat']), float(d['lon'])
        except Exception:
            continue
        out.append((dict(lat=la, lon=lo, name=f"{d.get('name', '')} (tidetimes)",
                         file='(UK_tidetimes)', line=0),
                    pfad, None, 'tidetimes.co.uk'))
    return out


def _lies_ea(pfad):
    """Die 15-Minuten-Messungen der englischen Environment Agency.

    py/download_ea_tides.py sammelt sie aus der check-for-flooding-CSV
    (die liefert nur ein rollierendes Fenster von etwa fuenf Tagen) und
    legt sie je Pegel als JSON ab: Zeitstempel in UTC auf Wert in Metern.
    104 Stationen lagen so auf der Platte, ohne dass sie je jemand
    gemessen haette -- der Leser kannte nur csv, txt und npz.

    Fuer Grossbritannien ist das die einzige offene Messquelle neben den
    44 BODC-Netzpegeln, und der Skriptkopf nennt sie zu Recht den
    Goldstandard: die 672 Saetze, die wir aus tidetimes.co.uk
    angepasst haben, stammen aus cosinus-interpolierten Tafeln und sind
    gegen sich selbst nicht zu pruefen.
    """
    try:
        d = json.load(open(pfad, encoding='utf-8'))
    except Exception:
        return []
    out = []
    for zeit, wert in (d.items() if isinstance(d, dict) else d):
        try:
            out.append((_zeit(zeit), float(wert)))
        except (ValueError, TypeError):
            continue
    out.sort()
    return out


def ea_reihen(nur=None):
    """Je Pegel der Environment Agency eine Reihe, Lage aus der Karte."""
    out = []
    if nur and nur != 'ea':
        return out
    karte = os.path.join(REIHEN, 'ea', 'ea_station_map.json')
    if not os.path.exists(karte):
        return out
    try:
        eintraege = json.load(open(karte, encoding='utf-8'))
    except Exception:
        return out
    gesehen = set()
    for e in eintraege:
        rloi = str(e.get('rloi', ''))
        if not rloi or rloi in gesehen:
            continue
        pfad = os.path.join(REIHEN, 'ea', f'rloi{rloi}.json')
        if not os.path.exists(pfad):
            continue
        gesehen.add(rloi)
        out.append((dict(lat=float(e['ea_lat']), lon=float(e['ea_lon']),
                         name=f"{e.get('ea_label', rloi)} (EA)",
                         file='(ea)', line=0), pfad, None, 'EA'))
    return out


LINZ_KOPF = re.compile(r"^\ufeff?(\d+),([^,]+),(\d+)[^\d]+(\d+)'([NS]),(\d+)[^\d]+(\d+)'([EW])")


def linz_kopf(pfad):
    """-> (Kennung, Name, lat, lon) aus der Kopfzeile einer LINZ-Tafel."""
    try:
        erste = open(pfad, encoding='utf-8-sig', errors='replace').readline()
    except Exception:
        return None
    m = LINZ_KOPF.match(erste)
    if not m:
        return None
    la = int(m.group(3)) + int(m.group(4)) / 60.0
    lo = int(m.group(6)) + int(m.group(7)) / 60.0
    if m.group(5) == 'S':
        la = -la
    if m.group(8) == 'W':
        lo = -lo
    return m.group(1), m.group(2).strip(), la, lo


def _lies_linz(pfad):
    """Die Gezeitentafeln von LINZ: je Zeile ein Tag mit bis zu vier Gezeiten.

    Zeile: Tagnummer, Wochentag, Monat, Jahr, dann Paare aus Uhrzeit und
    Hoehe in Metern. Die dritte Kopfzeile sagt "Local Std or Daylight
    Time" -- die Zeiten stehen also in neuseelaendischer Ortszeit MIT
    Sommerzeit. Ein fester Versatz waere falsch; gerechnet wird ueber die
    Zonenregeln.
    """
    from zoneinfo import ZoneInfo
    zone = ZoneInfo('Pacific/Auckland')
    out = []
    with open(pfad, encoding='utf-8-sig', errors='replace') as fh:
        for zeile in fh:
            f = [x.strip() for x in zeile.rstrip('\n').split(',')]
            if len(f) < 6 or not f[0].isdigit() or not f[3].isdigit():
                continue
            try:
                tag, monat, jahr = int(f[0]), int(f[2]), int(f[3])
            except ValueError:
                continue
            for i in range(4, len(f) - 1, 2):
                zeit, hoehe = f[i], f[i + 1]
                if not zeit or ':' not in zeit or not hoehe:
                    continue
                try:
                    st, mi = (int(x) for x in zeit.split(':'))
                    h = float(hoehe)
                    t = dt.datetime(jahr, monat, tag, st, mi, tzinfo=zone)
                except ValueError:
                    continue
                out.append((t.timestamp(), h))
    out.sort()
    return out


JHOD_KOPF = re.compile(r'^(\d{4}),([^,]+),(\d+)-(\d+)([NS]),(\d+)-(\d+)([EW])')
JHOD_STUNDEN = 9.0      # die Tafeln des JHOD stehen in japanischer Zeit


def _lies_jhod(pfad):
    """Die Vorhersagetafeln des japanischen Hydrographischen Dienstes.

    Kopfzeile: Kennung, Name, Breite, Laenge, Rasterweite, Z0. Danach je
    Zeile ein Tag mit Jahr, Monat, Tag und 144 Zehn-Minuten-Werten in
    Zentimetern. Ein Monat je Datei; gelesen wird der ganze Ordner, denn
    die zwoelf Dateien sind eine Reihe.

    Die Zeitbasis stand nicht im Kopf und war zu messen. Gegen sechs
    unserer japanischen Saetze -- Nemuro, Wakkanai, Hakodate, Harumi,
    Yokohama, Nagoya -- ergibt die Verschiebung einheitlich -540 Minuten
    bei 1.1 bis 2.6 cm RMS: japanische Zeit, UTC+9. Ein erster Versuch
    ueber die Hochwasserzeiten hatte -19 bis -114 Minuten geliefert und
    damit in die Irre gefuehrt; bei den Mischgezeiten von Tokio und
    Hakodate greift der Vergleich zum falschen der beiden Tagesgipfel.
    """
    ordner = os.path.dirname(pfad)
    out = []
    for datei in sorted(glob.glob(os.path.join(ordner, '*.txt'))):
        try:
            zeilen = open(datei, encoding='shift_jis',
                          errors='replace').read().split('\n')
        except Exception:
            continue
        for zeile in zeilen[1:]:
            teile = zeile.split()
            if len(teile) != 147:
                continue
            try:
                tag = dt.datetime(int(teile[0]), int(teile[1]), int(teile[2]),
                                  tzinfo=dt.timezone.utc).timestamp()
            except ValueError:
                continue
            for i, wert in enumerate(teile[3:]):
                try:
                    h = int(wert) / 100.0
                except ValueError:
                    continue
                out.append((tag + i * 600 - JHOD_STUNDEN * 3600, h))
    out.sort()
    return out


def jhod_kopf(pfad):
    """-> (Kennung, Name, lat, lon) aus der Kopfzeile."""
    try:
        erste = open(pfad, encoding='shift_jis', errors='replace').readline()
    except Exception:
        return None
    m = JHOD_KOPF.match(erste)
    if not m:
        return None
    la = int(m.group(3)) + int(m.group(4)) / 60.0
    lo = int(m.group(6)) + int(m.group(7)) / 60.0
    if m.group(5) == 'S':
        la = -la
    if m.group(8) == 'W':
        lo = -lo
    return m.group(1), m.group(2).strip(), la, lo


def _lies_npz(pfad):
    """Die irischen Reihen liegen als numpy-Archiv mit allem drin."""
    import numpy as np
    d = np.load(pfad, allow_pickle=True)
    t = d['datetimes_utc'].astype('datetime64[s]').astype('int64')
    # Die irischen Reihen fuehren Meter, die deutschen Zentimeter.
    if 'levels_m' in d:
        h = d['levels_m'].astype(float)
    elif 'levels_cm' in d:
        h = d['levels_cm'].astype(float) / 100.0
    else:
        return []
    gut = np.isfinite(h)
    return sorted(zip(t[gut].tolist(), h[gut].tolist()))


BODC_ZEILE = re.compile(r'^\s*\d+\)\s+(\d{4})/(\d\d)/(\d\d)\s+(\d\d):(\d\d):(\d\d)'
                        r'\s+(-?[\d.]+)([A-Z]?)\s+(-?[\d.]+)([A-Z]?)')


def _lies_bodc_alle(pfad):
    """Alle Monatsdateien einer BODC-Station als eine Reihe."""
    m = re.match(r'^([A-Z]{3})\d{4}\.txt$', os.path.basename(pfad))
    if not m:
        return None
    out = []
    for f in sorted(glob.glob(os.path.join(os.path.dirname(pfad),
                                           f'{m.group(1)}[0-9][0-9][0-9][0-9].txt'))):
        out += _lies_bodc(f)
    out.sort()
    return out


def bodc_kopf(pfad):
    """-> (Site, lat, lon) aus dem Kopf einer BODC-Datei."""
    site = lat = lon = None
    with open(pfad, encoding='iso-8859-1', errors='replace') as fh:
        for _ in range(12):
            z = fh.readline()
            if z.startswith('Site:'):
                site = z.split(':', 1)[1].strip()
            elif z.startswith('Latitude:'):
                lat = float(z.split(':', 1)[1])
            elif z.startswith('Longitude:'):
                lon = float(z.split(':', 1)[1])
    return site, lat, lon


def _lies_bodc(pfad):
    """BODC-Pegelreihe. Gibt den GEZEITENANTEIL zurueck: Wert minus Residuum.

    Die Dateien fuehren neben dem Messwert das Residuum mit, also den
    nicht-astronomischen Anteil. Zieht man es ab, bleibt die Tide ohne
    Wind und Luftdruck -- damit misst diese Reihe wie eine Tafel und
    nicht wie eine Messung, der Sturmboden von zehn bis zwanzig
    Zentimetern faellt weg.

    Verworfen werden nur Zeilen mit dem Kennbuchstaben N (Luecke) und
    Werte unter -90.
    """
    out = []
    for zeile in open(pfad, encoding='iso-8859-1', errors='replace'):
        m = BODC_ZEILE.match(zeile)
        if not m:
            continue
        # Nur 'N' heisst fehlend ("gaps are filled in with null values,
        # marked with an 'N' flag"); 'M' steht an fast der Haelfte aller
        # Zeilen und markiert keine Luecke, sondern eine Nachbearbeitung.
        if 'N' in (m.group(8), m.group(10)):
            continue
        wert, rest = float(m.group(7)), float(m.group(9))
        if wert < -90 or rest < -90:
            continue
        t = dt.datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)),
                        int(m.group(4)), int(m.group(5)), int(m.group(6)),
                        tzinfo=dt.timezone.utc).timestamp()
        out.append((t, wert - rest))
    out.sort()
    return out


def _lies_csv(pfad):
    with open(pfad, encoding='utf-8', errors='replace') as fh:
        kopf = fh.readline().strip().split(',')
        kl = [c.strip().lower() for c in kopf]
        zi = next((i for i, c in enumerate(kl) if 'time' in c or 'date' in c), None)
        wi = next((i for i, c in enumerate(kl)
                   if 'level' in c or 'water' in c or 'height' in c or 'sea' in c), None)
        if zi is None or wi is None:
            return []
        # Manche UHSLC-Dateien setzen eine zweite Kopfzeile mit den
        # Einheiten darunter ("UTC,millimeters,"). Ohne sie werden
        # Millimeter als Meter gelesen, und der RMS kommt in
        # Hunderten von Metern heraus statt in Zentimetern.
        merker = fh.tell()
        zweite = fh.readline().split(',')
        einheit = kl[wi]
        if len(zweite) > wi:
            try:
                float(zweite[wi])
                fh.seek(merker)
            except ValueError:
                einheit = zweite[wi].strip().lower() or einheit
        faktor = 0.001 if einheit.startswith('milli') or einheit == 'mm' else (
            0.01 if 'cm' in einheit or einheit.startswith('centi') else 1.0)
        out = []
        for zeile in fh:
            f = zeile.rstrip('\n').split(',')
            if len(f) <= max(zi, wi):
                continue
            try:
                wert = float(f[wi]) * faktor
                # Die UHSLC-Reihen schreiben Luecken als "nan" -- float()
                # nimmt das an, und ein einziger davon macht den ganzen
                # RMS zu nan.
                if not math.isfinite(wert):
                    continue
                out.append((_zeit(f[zi]), wert))
            except (ValueError, TypeError):
                continue
    out.sort()
    return out


def _zeit(s):
    """-> Unixzeit. Ein Zonenoffset im Zeitstempel wird BEACHTET.

    Hier stand bis zum 05.09.2026 ein Abschneiden: "+01:00" wurde
    weggeworfen und der Rest zu UTC erklaert. Damit wurde jede Reihe, die
    ihre Zeitzone mitschreibt, um genau diese Zone falsch gelesen -- die
    niederlaendischen RWS-Reihen stehen in "+01:00" und im Sommer in
    "+02:00", und alle niederlaendischen Saetze massen sich daran auf
    -60 bis -80 Minuten, Sieger wie Verlierer. Nicht die Saetze waren
    verschoben, sondern die Reihe.
    """
    s = s.strip().replace('T', ' ')
    versatz = 0.0
    rest = s[10:]
    for zeichen in ('+', '-'):
        if zeichen in rest:
            teil = rest.split(zeichen)[-1]
            m = re.match(r'^(\d{2}):?(\d{2})$', teil.strip())
            if m:
                versatz = (int(m.group(1)) + int(m.group(2)) / 60.0) * 3600
                if zeichen == '-':
                    versatz = -versatz
                s = s[:10] + rest.split(zeichen)[0]
            break
    s = s.replace('Z', '').strip()
    for muster in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d %H:%M:%S.%f'):
        try:
            t = dt.datetime.strptime(s, muster).replace(tzinfo=dt.timezone.utc)
            return t.timestamp() - versatz
        except ValueError:
            pass
    raise ValueError(s)


def _lies_jma(pfad):
    """JMA-Festbreite: 24 Stundenwerte in cm, dann JJMMTT und Stationskuerzel.

    9999 heisst fehlend. Die Zeiten stehen in japanischer Ortszeit
    (UTC+9); gerechnet wird durchweg in UTC.
    """
    out = []
    for zeile in open(pfad, encoding='iso-8859-1', errors='replace'):
        if len(zeile) < 78:
            continue
        try:
            werte = [int(zeile[3 * i:3 * i + 3]) for i in range(24)]
            jj, mm, tt = int(zeile[72:74]), int(zeile[74:76]), int(zeile[76:78])
        except ValueError:
            continue
        jahr = 2000 + jj if jj < 70 else 1900 + jj
        try:
            tag = dt.datetime(jahr, mm, tt, tzinfo=dt.timezone.utc)
        except ValueError:
            continue
        for stunde, w in enumerate(werte):
            if w >= 999:
                continue
            out.append((tag.timestamp() + (stunde - 9) * 3600, w / 100.0))
    out.sort()
    return out


def vorhersage(tcd, name, von, bis, schritt=SCHRITT_MIN):
    """-> (numpy-Zeiten, numpy-Hoehen) aus XTide im Rohmodus."""
    import numpy as np
    out = subprocess.run(
        ['tide', '-l', name, '-b', von, '-e', bis, '-m', 'r',
         '-s', f'{schritt // 60:02d}:{schritt % 60:02d}', '-u', 'm', '-z'],
        env=dict(os.environ, HFILE_PATH=os.path.join(TCD, tcd)),
        capture_output=True, encoding='iso-8859-1', errors='replace').stdout
    t, h = [], []
    for zeile in out.split('\n'):
        f = zeile.split()
        if len(f) == 2:
            try:
                t.append(float(f[0]))
                h.append(float(f[1]))
            except ValueError:
                pass
    return np.array(t), np.array(h)


def messe(obs_t, obs_h, vt, vh, mind=None):
    """-> (n, rms, max, zeitversatz_min, hoehenversatz, hub) oder None."""
    import numpy as np
    mind = mind or MIND_PUNKTE
    if len(vt) < 100 or len(obs_t) < mind:
        return None
    schritt = vt[1] - vt[0]
    best = None
    for versatz in range(-SUCHE_MIN, SUCHE_MIN + 1, SCHRITT_MIN):
        i = np.round((obs_t + versatz * 60 - vt[0]) / schritt).astype(int)
        gut = (i >= 0) & (i < len(vh))
        if gut.sum() < mind:
            continue
        d = obs_h[gut] - vh[i[gut]]
        rms = float(np.sqrt(np.mean((d - d.mean()) ** 2)))
        if best is None or rms < best[0]:
            best = (rms, versatz, gut, d)
    if best is None:
        return None
    rms, versatz, gut, d = best
    return (int(gut.sum()), rms, float(np.max(np.abs(d - d.mean()))),
            versatz, float(d.mean()), float(vh.max() - vh.min()))


def bodc_reihen(nur=None):
    """BODC-Dateien: sie bringen Name und Position selbst mit.

    Zwei Benennungen liegen dort nebeneinander. Die aelteren heissen
    2023IMM.txt -- ein Jahr je Datei --, die neueren IMM2509.txt, also
    Stationskuerzel plus Jahr und Monat. Der Leser kannte nur die erste
    Form, und damit blieben 517 Dateien an 40 Stationen ungelesen, im
    Median 14 Monate: ausgerechnet die juengsten, 2025 und 2026. In der
    Bestandsaufnahme standen sie als Brache und sahen nach alten
    Jahrgaengen aus, die man nicht braucht.

    Die Monatsdateien werden zu einer Reihe zusammengefasst; genannt wird
    die erste, gelesen werden alle Geschwister mit demselben Kuerzel.
    """
    ordner = glob.glob(os.path.join(REIHEN, 'UK', 'bodc*', ''))
    if nur and nur != 'UK':
        return []
    neueste, monate = {}, collections.defaultdict(list)
    for verzeichnis in ordner:
        for name in os.listdir(verzeichnis):
            m = re.match(r'^(\d{4})([A-Z]{3})\.txt$', name)
            if m and int(m.group(1)) >= neueste.get(m.group(2), (0, ''))[0]:
                neueste[m.group(2)] = (int(m.group(1)), os.path.join(verzeichnis, name))
                continue
            m = re.match(r'^([A-Z]{3})(\d{4})\.txt$', name)
            if m:
                monate[m.group(1)].append(os.path.join(verzeichnis, name))
    # Wo Monatsdateien vorliegen, sind sie die juengeren und dichteren.
    for code, pfade in monate.items():
        neueste[code] = (9999, sorted(pfade)[0])
    out = []
    for _code, (_jahr, pfad) in sorted(neueste.items()):
        site, lat, lon = bodc_kopf(pfad)
        if lat is None or lon is None:
            continue
        out.append((dict(lat=lat, lon=lon, name=site or os.path.basename(pfad),
                         file='(BODC)', line=0), pfad, None, 'BODC'))
    return out


def beiblatt_reihen(nur=None):
    """Reihen, die ein stationen.json neben sich haben.

    Der Hauptweg ist satzgetrieben: eine Reihe wird nur gelesen, wenn
    ein Satz sie in station_id_context nennt. Damit lagen 2694 von 4659
    Dateien brach -- allein die kanadischen Provinzordner fuehren 1007
    Reihen, von denen zehn ankamen. Wo ein Beiblatt Position und Name
    liefert, geht es auch ohne Namensnennung: gesucht wird dann wie bei
    den npz-Reihen ueber die Lage.
    """
    out = []
    for pfad in sorted(glob.glob(os.path.join(REIHEN, '*', 'stationen.json'))):
        ordner = os.path.relpath(pfad, REIHEN).split(os.sep)[0]
        if nur and nur != ordner:
            continue
        try:
            eintraege = json.load(open(pfad, encoding='utf-8'))
        except Exception:
            continue
        for datei, e in sorted(eintraege.items()):
            voll = os.path.join(REIHEN, ordner, datei)
            if not os.path.exists(voll):
                continue
            out.append((dict(lat=float(e['lat']), lon=float(e['lon']),
                             name=e.get('name', datei), file=f'({ordner})', line=0),
                        voll, None, ordner))
    return out


def linz_reihen(nur=None):
    """Je LINZ-Tafel eine Reihe -- Kopfzeile bringt Name und Lage mit."""
    out = []
    if nur and nur != 'NewZealand_LINZ':
        return out
    for pfad in sorted(glob.glob(os.path.join(REIHEN, 'NewZealand_LINZ', '*.csv'))):
        kopf = linz_kopf(pfad)
        if not kopf:
            continue
        _code, name, la, lo = kopf
        out.append((dict(lat=la, lon=lo, name=f'{name} (LINZ)',
                         file='(NewZealand_LINZ)', line=0), pfad, None, 'LINZ'))
    return out


def jhod_reihen(nur=None):
    """Je Station des JHOD eine Reihe -- Kopfzeile bringt Name und Lage mit."""
    out = []
    if nur and nur != 'Japan_JHOD':
        return out
    for ordner in sorted(glob.glob(os.path.join(REIHEN, 'Japan_JHOD', '*', ''))):
        dateien = sorted(glob.glob(os.path.join(ordner, '*.txt')))
        if not dateien:
            continue
        kopf = jhod_kopf(dateien[0])
        if not kopf:
            continue
        _code, name, la, lo = kopf
        out.append((dict(lat=la, lon=lo, name=f'{name} (JHOD)',
                         file='(Japan_JHOD)', line=0),
                    dateien[0], None, 'JHOD'))
    return out


def npz_reihen(nur=None):
    """Reihen im numpy-Format.

    Die meisten bringen Name und Position selbst mit. Die deutschen
    PEGELONLINE-Reihen nicht: sie enthalten nur datetimes_utc und
    levels_cm, und damit fielen alle 99 aus jeder Guetepruefung heraus --
    genau der Bestand, in dem die TICON-Saetze 38 Minuten zu spaet
    liegen. Fuer solche Ordner liegt die Zuordnung als
    npz_stationen.json daneben, einmal von Hand geprueft, statt bei
    jedem Lauf neu geraten.
    """
    import numpy as np
    out = []
    beiblatt = {}
    for pfad in glob.glob(os.path.join(REIHEN, '*', 'npz_stationen.json')):
        ordner = os.path.relpath(pfad, REIHEN).split(os.sep)[0]
        try:
            beiblatt[ordner] = json.load(open(pfad, encoding='utf-8'))
        except Exception:
            pass
    for pfad in sorted(glob.glob(os.path.join(REIHEN, '**', '*.npz'), recursive=True)):
        ordner = os.path.relpath(pfad, REIHEN).split(os.sep)[0]
        if nur and nur != ordner:
            continue
        try:
            d = np.load(pfad, allow_pickle=True)
            lat, lon = float(d['latitude']), float(d['longitude'])
            name = str(d['name'])
        except Exception:
            e = beiblatt.get(ordner, {}).get(os.path.basename(pfad)[:-4])
            if not e:
                continue
            lat, lon, name = float(e['lat']), float(e['lon']), e['name']
        out.append((dict(lat=lat, lon=lon, name=name, file=f'({ordner})', line=0),
                    pfad, None, 'Marine Institute' if 'Ireland' in ordner else ordner))
    return out


def main(argv):
    import numpy as np
    umkreis = float(argv[argv.index('--km') + 1]) if '--km' in argv else 3.0
    tage = int(argv[argv.index('--tage') + 1]) if '--tage' in argv else 365
    nur = argv[argv.index('--ordner') + 1] if '--ordner' in argv else None

    kopf = kopfdaten()
    dateien = reihendateien(nur)
    recs = [r for r in load_records()
            if r['lat'] is not None and r['lon'] is not None and not r['current']]
    anker = []
    for r in recs:
        sid, fit, _q = kopf.get((r['file'], r['line']), (None, None, ''))
        if not sid:
            continue
        teile = [t for t in re.split(r'[ \-_]', sid) if t]
        pfad = None
        for i in range(len(teile)):
            for j in range(len(teile)):
                if i == j:
                    continue
                pfad = pfad or dateien.get((teile[i].upper(), teile[j].upper()))
        if pfad:
            anker.append((r, pfad, fit, None))
    anker += bodc_reihen(nur)
    anker += npz_reihen(nur)
    anker += beiblatt_reihen(nur)
    anker += jhod_reihen(nur)
    anker += linz_reihen(nur)
    anker += ea_reihen(nur)
    anker += tidetimes_reihen(nur)
    print(f'{len(anker)} Reihen zugeordnet, Umkreis {umkreis:.0f} km, '
          f'{tage} Tage Fenster', file=sys.stderr)

    w = csv.writer(sys.stdout)
    w.writerow(['station', 'lat', 'lon', 'jahr', 'satz', 'datei', 'abstand_m', 'n',
                'rms_m', 'max_m', 'zeit_min', 'hoehe_off_m', 'hub_m', 'reihe',
                'eigen', 'ausserhalb'])
    for nr, (a, pfad, fit, anbieter) in enumerate(anker, 1):
        mind = (MIND_PUNKTE_TAFEL if any(t in pfad for t in TAFELREIHEN)
                else MIND_PUNKTE)
        obs = lies(pfad)
        if len(obs) < mind:
            print(f'  {os.path.basename(pfad)}: nur {len(obs)} Werte', file=sys.stderr)
            continue
        ende = obs[-1][0]
        start = ende - tage * 86400
        ausserhalb = 'nein'
        if fit:
            fit_von = dt.datetime.strptime(fit[0], '%Y-%m-%d').replace(
                tzinfo=dt.timezone.utc).timestamp()
            fit_bis = dt.datetime.strptime(fit[1], '%Y-%m-%d').replace(
                tzinfo=dt.timezone.utc).timestamp()
            if start > fit_bis or ende < fit_von:
                # Die Reihe liegt schon ganz ausserhalb -- etwa die
                # JMA-Tafel fuer 2026 gegen einen Fit bis 2025.
                ausserhalb = 'ja'
            elif obs[0][0] < fit_von - tage * 86400:
                # Sonst nach vorn ausweichen: vor dem Fitfenster ist die
                # Reihe fuer alle Kandidaten gleich neu.
                ende, start, ausserhalb = fit_von, fit_von - tage * 86400, 'ja'
        paare = [(t, h) for t, h in obs if start <= t <= ende]
        if len(paare) < mind:
            continue
        obs_t = np.array([p[0] for p in paare])
        obs_h = np.array([p[1] for p in paare])
        von = dt.datetime.fromtimestamp(start - 7200, dt.timezone.utc).strftime('%Y-%m-%d %H:%M')
        bis = dt.datetime.fromtimestamp(ende + 7200, dt.timezone.utc).strftime('%Y-%m-%d %H:%M')
        for x in sorted(recs, key=lambda q: km(a, q)):
            d = km(a, x)
            if d > umkreis:
                break
            tcd = os.path.basename(x['file'])[:-4] + '.tcd'
            if not os.path.exists(os.path.join(TCD, tcd)):
                continue
            vt, vh = vorhersage(tcd, x['name'], von, bis)
            g = messe(obs_t, obs_h, vt, vh, mind)
            if not g:
                continue
            n, rms, gross, versatz, off, hub = g
            # "eigen" heisst: dieser Satz stammt aus eben dieser Quelle.
            # Bei den Ankern ueber station_id_context ist es derselbe
            # Satz, bei den BODC-Reihen erkennt man es am Quellenvermerk.
            eigen = 1 if x is a else 0
            if anbieter and anbieter.lower() in kopf.get(
                    (x['file'], x['line']), ('', None, ''))[2].lower():
                eigen = 1
            w.writerow([os.path.basename(pfad), f'{a["lat"]:.4f}', f'{a["lon"]:.4f}',
                        dt.datetime.fromtimestamp(ende, dt.timezone.utc).year,
                        x['name'], os.path.basename(x['file']), round(d * 1000), n,
                        round(rms, 4), round(gross, 3), versatz, round(off, 3),
                        round(hub, 3), os.path.relpath(pfad, REIHEN).split(os.sep)[0],
                        eigen, ausserhalb])
            sys.stdout.flush()
        if nr % 20 == 0:
            print(f'  {nr}/{len(anker)}', file=sys.stderr, flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
