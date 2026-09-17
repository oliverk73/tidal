#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Schreibt Bestandsdateien, ohne sie im Fehlerfall zu vernichten.

Zweimal an einem Tag ist dasselbe passiert: ein Werkzeug schrieb mit

    open(pfad, 'w', encoding='iso-8859-1').write(text)

und der Text enthielt ein Zeichen, das ISO-8859-1 nicht kennt -- einmal
das Makron in einem Natural-Earth-Namen, einmal das typografische
Apostroph in einem von Hand vergebenen Namen. open(...,'w') leert die
Datei SOFORT, die Ausnahme kam erst beim Schreiben, und zurueck blieben
null Bytes: harmonics_att_np203.txt, harmonics_noaa_eutt.txt und
harmonics_utide_observations.txt. Alle drei liessen sich aus der
Sicherung wiederherstellen, aber darauf soll sich niemand verlassen
muessen.

Hier wird deshalb erst in eine Nebendatei geschrieben und dann
umbenannt. os.replace ist auf demselben Dateisystem unteilbar: entweder
steht die neue Fassung da oder die alte, nie eine halbe.

Und Zeichen jenseits von ISO-8859-1 werden umgeschrieben statt zum
Abbruch zu fuehren -- "Manawatū" wird zu "Manawatu", das typografische
Apostroph zum geraden. Der Bestand ist ISO-8859-1, weil XTide das so
liest; das laesst sich nicht umgehen, nur sauber behandeln.
"""
from __future__ import annotations

import os
import re
import unicodedata

ERSATZ = {'’': "'", '‘': "'", '“': '"', '”': '"',
          '–': '-', '—': '-', '…': '...', ' ': ' ',
          '′': "'", '″': '"', 'ʻ': "'", 'ʼ': "'"}


def latin1(s):
    """-> Fassung, die sich in ISO-8859-1 schreiben laesst."""
    try:
        s.encode('iso-8859-1')
        return s
    except (UnicodeEncodeError, AttributeError):
        pass
    for a, b in ERSATZ.items():
        s = s.replace(a, b)
    try:
        s.encode('iso-8859-1')
        return s
    except UnicodeEncodeError:
        ohne = ''.join(c for c in unicodedata.normalize('NFD', s)
                       if unicodedata.category(c) != 'Mn')
        gerade = unicodedata.normalize('NFC', ohne)
        try:
            gerade.encode('iso-8859-1')
            return gerade
        except UnicodeEncodeError:
            return gerade.encode('ascii', 'ignore').decode('ascii')


GRENZE = 180


def kommentare_umbrechen(text, grenze=GRENZE):
    """Bricht zu lange Kommentarzeilen um -- sonst frisst build_tide_db Saetze.

    build_tide_db liest eine Kommentarzeile nur bis zu einer festen Laenge;
    der Rest landet als Datenzeile im Satz ("Invalid level units for record -
    g im Ortsgebiet."), und der Satz sowie seine Nachbarn fallen stumm aus der
    TCD. Am 16.09.2026 kostete eine 330 Zeichen lange Notiz 12 Saetze in
    harmonics_utide_tidetables. Umgebrochen wird bevorzugt am Semikolon, sonst
    am letzten Leerzeichen; jede Folgezeile bekommt wieder ihr Praefix.
    """
    if not any(len(z) > grenze and z.startswith('#') for z in text.split('\n')):
        return text
    aus = []
    for z in text.split('\n'):
        if not z.startswith('#') or len(z) <= grenze:
            aus.append(z)
            continue
        m = re.match(r'^#\s*\w+:\s*', z)
        praefix = m.group(0) if m else '# '
        rest = z[len(praefix):]
        while len(rest) > grenze - len(praefix):
            schnitt = rest.rfind('; ', 0, grenze - len(praefix))
            if schnitt < 40:
                schnitt = rest.rfind(' ', 0, grenze - len(praefix))
            if schnitt < 1:
                break
            aus.append(praefix + rest[:schnitt + 1].rstrip())
            rest = rest[schnitt + 1:].lstrip()
        aus.append(praefix + rest)
    return '\n'.join(aus)


def schreiben(pfad, text, encoding='iso-8859-1'):
    """Schreibt text nach pfad -- erst daneben, dann umbenennen.

    Harmonics-Dateien bekommen dabei ihre Kommentarzeilen gekuerzt (siehe
    kommentare_umbrechen); andere Dateien bleiben unangetastet.
    """
    if pfad.endswith('.txt') and os.sep + 'harmonics' + os.sep in os.path.abspath(pfad):
        text = kommentare_umbrechen(text)
    if encoding.lower() in ('iso-8859-1', 'latin-1', 'latin1'):
        text = latin1(text)
    neben = pfad + '.neu'
    with open(neben, 'w', encoding=encoding) as fh:
        fh.write(text)
    os.replace(neben, pfad)
